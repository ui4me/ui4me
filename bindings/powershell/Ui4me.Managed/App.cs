using System.Management.Automation;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace Ui4me.Managed;

public sealed class UiEvent
{
    public string Type { get; init; } = "";
    public ulong Window { get; init; }
    public ulong Token { get; init; }
    public string Element { get; init; } = "";
    public string Value { get; init; } = "";
    public string Json { get; init; } = "{}";
    internal static UiEvent Parse(string text)
    {
        using var doc = JsonDocument.Parse(text);
        var r = doc.RootElement;
        return new UiEvent {
            Type = r.GetProperty("type").GetString()!,
            Window = r.TryGetProperty("window", out var w) ? w.GetUInt64() : 0,
            Token = r.TryGetProperty("token", out var t) ? t.GetUInt64() : 0,
            Element = r.TryGetProperty("element", out var e) ? e.GetString() ?? "" : "",
            Value = r.TryGetProperty("value", out var v) ? v.GetString() ?? "" : "",
            Json = text,
        };
    }
}

public sealed class Subscription : IDisposable
{
    private App? app;
    private readonly long key;
    internal Subscription(App app, long key) { this.app = app; this.key = key; }
    public void Dispose() { app?.RemoveHandler(key); app = null; }
}

public sealed class TimerRegistration : IDisposable
{
    private App? app;
    public ulong Token { get; }
    internal TimerRegistration(App app, ulong token) { this.app = app; Token = token; }
    public void Cancel() { app?.CancelTimer(Token); app = null; }
    public void Dispose() => Cancel();
}

public sealed class PostedWork
{
    private readonly int owner;
    private int state; // 0 queued, 1 executing, 2 settled, 3 cancelled
    internal readonly TaskCompletionSource<object?> Completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal PostedWork(int owner) => this.owner = owner;
    public bool IsCompleted => Completion.Task.IsCompleted;
    public bool IsCancelled => Completion.Task.IsCanceled;
    public bool Cancel() => Interlocked.CompareExchange(ref state, 3, 0) == 0 && Completion.TrySetCanceled();
    internal bool TryStart() => Interlocked.CompareExchange(ref state, 1, 0) == 0;
    internal void Succeed(object? value) { Volatile.Write(ref state, 2); Completion.TrySetResult(value); }
    internal void Fail(Exception error)
    {
        if (Interlocked.Exchange(ref state, 2) != 3) Completion.TrySetException(error);
    }
    // PowerShell suppresses exceptions thrown by property getters and yields $null.
    // A method preserves the owner-thread deadlock error for PowerShell callers.
    public object? GetResult()
    {
        if (Environment.CurrentManagedThreadId == owner && !IsCompleted)
            throw new InvalidOperationException("Do not wait for posted work on the UI owner thread.");
        return Completion.Task.GetAwaiter().GetResult();
    }
}

public sealed class App : IDisposable
{
    [ThreadStatic] private static App? current;
    public static App? Current => current;
    private readonly int owner = Environment.CurrentManagedThreadId;
    private readonly object gate = new();
    private readonly Native.Callback callbackRoot;
    private GCHandle selfRoot;
    private readonly Dictionary<ulong, Window> windows = new();
    private readonly Dictionary<long, (string Event, ulong Window, string? Element, ScriptBlock Handler)> handlers = new();
    private readonly Dictionary<ulong, (ScriptBlock Handler, bool Repeat)> timers = new();
    private readonly Dictionary<ulong, (PostedWork Work, Func<object?> Action)> pending = new();
    private readonly List<BackgroundWork> workers = new();
    private long counter;
    private int state; // 0 created, 1 running, 2 stopped, 3 disposed
    private volatile bool stopping;
    private ExceptionDispatchInfo? callbackError;
    internal ulong Session { get; private set; }
    public string Backend { get; }

    public App(string backend = "native")
    {
        if (backend is not ("native" or "headless")) throw new ArgumentException("Unknown backend.");
        if (current is not null) throw new InvalidOperationException("An App already exists on this owner thread.");
        Backend = backend;
        callbackRoot = Dispatch;
        Native.Check(Native.SessionCreate(JsonSerializer.Serialize(new { backend, app_id = "org.ui4me.powershell", allow_any_thread = true }), callbackRoot, IntPtr.Zero, out var id));
        Session = id;
        selfRoot = GCHandle.Alloc(this); // The foreign function pointer cannot root a managed delegate.
        current = this;
    }
    internal void OwnerOnly()
    {
        if (Environment.CurrentManagedThreadId != owner)
            throw new InvalidOperationException("UI commands require the creating thread. Use Post from other managed threads.");
    }
    private void Active()
    {
        OwnerOnly();
        if (Volatile.Read(ref state) > 1) throw new InvalidOperationException("This session is terminal; create a new App.");
    }
    internal JsonElement Command(object command) { Active(); return Native.Command(Session, command); }
    public Window Open(string html, string title = "ui4me", int width = 640, int height = 480)
    {
        var result = Command(new { op = "open", html, title, width, height });
        var window = new Window(this, result.GetProperty("window").GetUInt64());
        windows.Add(window.Id, window);
        return window;
    }
    public Window OpenFile(string path, string title = "ui4me", int width = 640, int height = 480) =>
        Open(File.ReadAllText(Path.GetFullPath(path), System.Text.Encoding.UTF8), title, width, height);
    public Subscription On(string eventName, ScriptBlock handler) => Register(eventName, handler, 0, null);
    internal Subscription Register(string eventName, ScriptBlock handler, ulong window, string? element)
    {
        Active();
        if (handlers.Count >= 512) throw new InvalidOperationException("At most 512 subscriptions may be active.");
        var id = Interlocked.Increment(ref counter);
        handlers.Add(id, (eventName, window, element, ScriptClosure.Capture(handler)));
        return new Subscription(this, id);
    }
    internal void RemoveHandler(long id) { OwnerOnly(); handlers.Remove(id); }
    public TimerRegistration Timer(int milliseconds, ScriptBlock handler, bool repeat = false)
    {
        Active();
        var token = checked((ulong)Interlocked.Increment(ref counter));
        Command(new { op = "timer", token, milliseconds, repeat });
        timers.Add(token, (ScriptClosure.Capture(handler), repeat));
        return new TimerRegistration(this, token);
    }
    internal void CancelTimer(ulong token)
    {
        OwnerOnly();
        if (!timers.ContainsKey(token)) return;
        if (state <= 1 && !stopping) Command(new { op = "cancel_timer", token });
        timers.Remove(token);
    }
    public PostedWork Post(ScriptBlock action)
    {
        // A ScriptBlock belongs to its creating runspace. Capture it only on the owner.
        OwnerOnly();
        var closure = ScriptClosure.Capture(action);
        return PostManaged(() => closure.InvokeReturnAsIs());
    }
    public PostedWork PostManaged(Func<object?> action)
    {
        ArgumentNullException.ThrowIfNull(action);
        var work = new PostedWork(owner);
        var token = checked((ulong)Interlocked.Increment(ref counter));
        lock (gate)
        {
            if (state > 1) { work.Fail(new InvalidOperationException("Application stopped.")); return work; }
            if (pending.Count >= 512) { work.Fail(new InvalidOperationException("Deferred work queue is full.")); return work; }
            pending.Add(token, (work, action));
        }
        try { Native.Check(Native.SessionPost(Session, token)); }
        catch (Exception e)
        {
            lock (gate) pending.Remove(token);
            work.Fail(e);
        }
        return work;
    }
    public string StatsJson()
    {
        OwnerOnly();
        if (state == 3) throw new ObjectDisposedException(nameof(App));
        return Native.Command(Session, new { op = "stats" }).GetRawText();
    }
    internal void FailCallback(Exception error)
    {
        OwnerOnly();
        callbackError ??= ExceptionDispatchInfo.Capture(error);
        stopping = true;
        Native.SessionStop(Session);
    }
    public BackgroundWork Work(ScriptBlock script, object[] arguments, ScriptBlock completion)
    {
        Active();
        workers.RemoveAll(worker => worker.IsCompleted);
        var worker = BackgroundWork.Start(this, script, arguments, completion);
        workers.Add(worker);
        return worker;
    }
    public void Stop()
    {
        lock (gate)
        {
            if (state > 1) return;
            stopping = true;
            Native.Check(Native.SessionStop(Session));
        }
    }
    public void Run()
    {
        Active();
        if (state != 0) throw new InvalidOperationException("Application is already running.");
        Volatile.Write(ref state, 1);
        try
        {
            var result = Native.SessionRun(Session);
            callbackError?.Throw();
            Native.Check(result);
        }
        finally
        {
            lock (gate)
            {
                state = 2;
                foreach (var (work, _) in pending.Values) work.Cancel();
                pending.Clear();
            }
            timers.Clear();
            foreach (var worker in workers) worker.Cancel();
            workers.Clear();
            handlers.Clear();
            foreach (var window in windows.Values) window.Closed = true;
            windows.Clear();
        }
    }
    private int Dispatch(ulong session, IntPtr raw, IntPtr user)
    {
        try
        {
            var evt = UiEvent.Parse(Native.Utf8(raw));
            if (evt.Type == "stopped") stopping = true;
            if (evt.Type == "post")
            {
                (PostedWork Work, Func<object?> Action) item = default;
                bool found;
                lock (gate) found = pending.Remove(evt.Token, out item);
                if (found && item.Work.TryStart())
                {
                    try { item.Work.Succeed(item.Action()); }
                    catch (Exception e) { item.Work.Fail(e); }
                }
            }
            else if (evt.Type == "timer" && timers.TryGetValue(evt.Token, out var timer))
            {
                if (!timer.Repeat) timers.Remove(evt.Token);
                timer.Handler.InvokeReturnAsIs(evt);
            }
            var veto = false;
            foreach (var registration in handlers.Values.ToArray())
            {
                if (registration.Event != evt.Type || (registration.Window != 0 && registration.Window != evt.Window)
                    || (registration.Element is not null && registration.Element != evt.Element)) continue;
                var answer = registration.Handler.InvokeReturnAsIs(evt);
                if (answer is PSObject wrapped) answer = wrapped.BaseObject;
                if (evt.Type == "close_requested" && answer is false) veto = true;
            }
            if (evt.Type == "closed")
            {
                if (windows.Remove(evt.Window, out var window)) window.Closed = true;
                foreach (var key in handlers.Where(p => p.Value.Window == evt.Window).Select(p => p.Key).ToArray()) handlers.Remove(key);
            }
            return veto ? 1 : 0;
        }
        catch (Exception error)
        {
            callbackError ??= ExceptionDispatchInfo.Capture(error);
            stopping = true;
            Native.SessionStop(Session);
            return -1;
        }
    }
    public void Dispose()
    {
        OwnerOnly();
        if (state == 3) return;
        if (state == 1) throw new InvalidOperationException("Stop the application, then dispose after Run returns.");
        Native.Check(Native.SessionDestroy(Session));
        lock (gate)
        {
            state = 3;
            foreach (var (work, _) in pending.Values) work.Cancel();
            pending.Clear();
        }
        timers.Clear(); handlers.Clear();
        foreach (var worker in workers) worker.Cancel();
        workers.Clear();
        foreach (var window in windows.Values) window.Closed = true;
        windows.Clear();
        current = null;
        if (selfRoot.IsAllocated) selfRoot.Free();
        GC.KeepAlive(callbackRoot);
    }
}

public sealed class Window
{
    private readonly App app;
    public ulong Id { get; }
    internal bool Closed;
    internal Window(App app, ulong id) { this.app = app; Id = id; }
    private void Check() { if (Closed) throw new InvalidOperationException("Window is closed."); }
    public Subscription On(string eventName, ScriptBlock handler, string? element = null) { Check(); return app.Register(eventName, handler, Id, element); }
    public void SetText(string element, string text) { Check(); app.Command(new { op = "set_text", window = Id, element, text }); }
    public string GetValue(string element) { Check(); return app.Command(new { op = "get_value", window = Id, element }).GetProperty("value").GetString()!; }
    public void SetTitle(string title) { Check(); app.Command(new { op = "set_title", window = Id, title }); }
    public void Resize(int width, int height) { Check(); app.Command(new { op = "resize", window = Id, width, height }); }
    public string Snapshot(string path) { Check(); return app.Command(new { op = "snapshot", window = Id, path = Path.GetFullPath(path) }).GetRawText(); }
    public void Close() { Check(); app.Command(new { op = "close", window = Id }); }
}
