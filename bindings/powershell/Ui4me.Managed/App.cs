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
    public IReadOnlyList<string> Path { get; init; } = Array.Empty<string>();
    public string Value { get; init; } = "";
    public bool? Checked { get; init; }
    public double? Width { get; init; }
    public double? Height { get; init; }
    public double? Scale { get; init; }
    public string Units { get; init; } = "";
    public string Key { get; init; } = "";
    public string Backend { get; init; } = "";
    public string AppId { get; init; } = "";
    public IReadOnlyDictionary<string, JsonElement> Details { get; init; } = new Dictionary<string, JsonElement>();
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
            Path = r.TryGetProperty("path", out var p) && p.ValueKind == JsonValueKind.Array
                ? p.EnumerateArray().Where(id => id.ValueKind == JsonValueKind.String).Select(id => id.GetString()!).ToArray() : Array.Empty<string>(),
            Value = r.TryGetProperty("value", out var v) ? v.GetString() ?? "" : "",
            Checked = r.TryGetProperty("checked", out var c) && c.ValueKind is JsonValueKind.True or JsonValueKind.False ? c.GetBoolean() : null,
            Width = Number(r, "width"), Height = Number(r, "height"), Scale = Number(r, "scale"),
            Units = Text(r, "units"), Key = Text(r, "key"), Backend = Text(r, "backend"), AppId = Text(r, "app_id"),
            Details = r.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.Clone()),
            Json = text,
        };
    }
    private static string Text(JsonElement root, string key) => root.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
    private static double? Number(JsonElement root, string key) => root.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number) ? number : null;
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
    private readonly Dictionary<ulong, (BackgroundWork Work, ScriptBlock Completion)> background = new();
    private long counter;
    private int state; // 0 created, 1 running, 2 stopped, 3 disposed
    private volatile bool stopping;
    private bool runActive;
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
        if (Volatile.Read(ref state) > 1 || stopping) throw new InvalidOperationException("This session is stopping or terminal; create a new App.");
    }
    internal JsonElement Command(object command) { Active(); return Native.Command(Session, command); }
    private Window Opened(JsonElement result)
    {
        var window = new Window(this, result.GetProperty("window").GetUInt64());
        windows.Add(window.Id, window);
        return window;
    }
    public Window Open(string html, string title = "ui4me", int width = 640, int height = 480, string? basePath = null)
    {
        ArgumentNullException.ThrowIfNull(html);
        var request = new Dictionary<string, object?> { ["op"] = "open", ["html"] = html, ["title"] = title, ["width"] = width, ["height"] = height };
        if (basePath is not null) request["base_path"] = Path.GetFullPath(basePath);
        return Opened(Command(request));
    }
    public Window OpenFile(string path, string title = "ui4me", int width = 640, int height = 480) =>
        Opened(Command(new { op = "open_file", path = Path.GetFullPath(path), title, width, height }));
    public Subscription On(string eventName, ScriptBlock handler) => Register(eventName, handler, 0, null);
    internal Subscription Register(string eventName, ScriptBlock handler, ulong window, string? element)
    {
        Active();
        ArgumentNullException.ThrowIfNull(handler);
        if (handlers.Count >= 512) throw new InvalidOperationException("At most 512 subscriptions may be active.");
        var id = Interlocked.Increment(ref counter);
        handlers.Add(id, (eventName, window, element, ScriptClosure.Capture(handler)));
        return new Subscription(this, id);
    }
    internal void RemoveHandler(long id) { OwnerOnly(); handlers.Remove(id); }
    public TimerRegistration Timer(int milliseconds, ScriptBlock handler, bool repeat = false)
    {
        Active();
        ArgumentNullException.ThrowIfNull(handler);
        var captured = ScriptClosure.Capture(handler);
        var token = checked((ulong)Interlocked.Increment(ref counter));
        timers.Add(token, (captured, repeat));
        try { Command(new { op = "timer", token, milliseconds, repeat }); }
        catch { timers.Remove(token); throw; }
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
            if (state > 1 || stopping) { work.Fail(new InvalidOperationException("Application stopped.")); return work; }
            if (pending.Count >= 512) { work.Fail(new InvalidOperationException("Deferred work queue is full.")); return work; }
            pending.Add(token, (work, action));
            // Native admission never invokes callbacks. Serialize it with disposal.
            try { Native.Check(Native.SessionPost(Session, token)); }
            catch (Exception e) { pending.Remove(token); work.Fail(e); }
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
        return BackgroundWork.Start(this, owner, script, arguments, completion);
    }
    internal ulong ReserveBackground(BackgroundWork work, ScriptBlock completion)
    {
        Active();
        var token = checked((ulong)Interlocked.Increment(ref counter));
        lock (gate)
        {
            if (stopping || state > 1) throw new InvalidOperationException("Application stopped.");
            if (background.Count >= 128) throw new InvalidOperationException("Background completion capacity is full.");
            background.Add(token, (work, completion));
            try { Native.Command(Session, new { op = "reserve_completion", token }); }
            catch { background.Remove(token); throw; }
        }
        return token;
    }
    internal void RollbackBackground(ulong token)
    {
        OwnerOnly();
        lock (gate)
        {
            background.Remove(token);
            if (state <= 1 && !stopping) Native.Command(Session, new { op = "cancel_completion", token });
        }
    }
    internal void PublishBackground(ulong token, BackgroundWork work)
    {
        lock (gate)
        {
            if (state > 1 || stopping || !background.ContainsKey(token)) { work.DiscardDelivery(); return; }
            try { Native.Check(Native.SessionComplete(Session, token)); }
            catch (Exception error)
            {
                background.Remove(token);
                work.DiscardDelivery(error);
            }
        }
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
        OwnerOnly();
        if (state != 0) throw new InvalidOperationException("Application is already running.");
        lock (gate) { state = 1; runActive = true; }
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
                runActive = false;
                foreach (var (work, _) in pending.Values) work.Cancel();
                pending.Clear();
                foreach (var (worker, _) in background.Values) { worker.Cancel(); worker.DiscardDelivery(); }
                background.Clear();
            }
            timers.Clear();
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
            if (evt.Type == "stopped") { lock (gate) { stopping = true; state = 2; } }
            if (evt.Type == "closed" && windows.Remove(evt.Window, out var closedWindow)) closedWindow.Closed = true;
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
            else if (evt.Type == "completion")
            {
                (BackgroundWork Work, ScriptBlock Completion) item = default;
                bool found;
                lock (gate) found = background.Remove(evt.Token, out item);
                if (found && item.Work.TryBeginDelivery())
                {
                    try { item.Completion.InvokeReturnAsIs(item.Work.Results, item.Work.Error); }
                    finally { item.Work.FinishDelivery(); }
                }
            }
            var veto = false;
            foreach (var token in handlers.Keys.ToArray())
            {
                if (!handlers.TryGetValue(token, out var registration)) continue;
                if (registration.Event != evt.Type || (registration.Window != 0 && registration.Window != evt.Window)
                    || (registration.Element is not null && registration.Element != evt.Element && !evt.Path.Contains(registration.Element))) continue;
                var answer = registration.Handler.InvokeReturnAsIs(evt);
                if (answer is PSObject wrapped) answer = wrapped.BaseObject;
                if (evt.Type == "close_requested" && answer is false) veto = true;
            }
            if (evt.Type == "closed")
            {
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
        lock (gate)
        {
            if (state == 3) return;
            if (runActive) throw new InvalidOperationException("Stop the application, then dispose after Run returns.");
            Native.Check(Native.SessionDestroy(Session));
            state = 3;
            stopping = true;
            foreach (var (work, _) in pending.Values) work.Cancel();
            pending.Clear();
            foreach (var (worker, _) in background.Values) { worker.Cancel(); worker.DiscardDelivery(); }
            background.Clear();
        }
        timers.Clear(); handlers.Clear();
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
    public string DiagnosticsJson() { Check(); return app.Command(new { op = "diagnostics", window = Id }).GetRawText(); }
    public void SetValue(string element, string value) { Check(); app.Command(new { op = "set_value", window = Id, element, value }); }
    public bool GetChecked(string element) { Check(); return app.Command(new { op = "get_checked", window = Id, element }).GetProperty("checked").GetBoolean(); }
    public void SetChecked(string element, bool value) { Check(); app.Command(new { op = "set_checked", window = Id, element, @checked = value }); }
    public void SetAttribute(string element, string name, string value) { Check(); app.Command(new { op = "set_attribute", window = Id, element, name, value }); }
    public void RemoveAttribute(string element, string name) { Check(); app.Command(new { op = "remove_attribute", window = Id, element, name }); }
    public void AddClass(string element, string name) { Check(); app.Command(new { op = "add_class", window = Id, element, name }); }
    public void RemoveClass(string element, string name) { Check(); app.Command(new { op = "remove_class", window = Id, element, name }); }
    public void Focus(string element) { Check(); app.Command(new { op = "focus", window = Id, element }); }
    public void ReplaceChildrenHtml(string element, string html) { Check(); app.Command(new { op = "replace_children_html", window = Id, element, html }); }
    public void InsertHtml(string element, string position, string html) { Check(); app.Command(new { op = "insert_html", window = Id, element, position, html }); }
    public void AppendHtml(string element, string html) => InsertHtml(element, "beforeend", html);
    public void PrependHtml(string element, string html) => InsertHtml(element, "afterbegin", html);
    public void InsertHtmlBefore(string element, string html) => InsertHtml(element, "beforebegin", html);
    public void InsertHtmlAfter(string element, string html) => InsertHtml(element, "afterend", html);
    public void RemoveElement(string element) { Check(); app.Command(new { op = "remove_element", window = Id, element }); }
    public void MoveElement(string element, string target, string position = "beforeend") { Check(); app.Command(new { op = "move_element", window = Id, element, target, position }); }
    public string GetText(string element) { Check(); return app.Command(new { op = "get_text", window = Id, element }).GetProperty("text").GetString()!; }
    public string? GetAttribute(string element, string name) { Check(); var v = app.Command(new { op = "get_attribute", window = Id, element, name }).GetProperty("value"); return v.ValueKind == System.Text.Json.JsonValueKind.Null ? null : v.GetString(); }
    public System.Collections.Generic.Dictionary<string, string> GetAttributes(string element)
    {
        Check();
        var result = new System.Collections.Generic.Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var p in app.Command(new { op = "get_attributes", window = Id, element }).GetProperty("attributes").EnumerateObject()) result[p.Name] = p.Value.GetString()!;
        return result;
    }
    public bool HasElement(string element) { Check(); return app.Command(new { op = "has_element", window = Id, element }).GetProperty("exists").GetBoolean(); }
    public string[] Query(string selector, int limit = 1024)
    {
        Check();
        var list = new System.Collections.Generic.List<string>();
        foreach (var e in app.Command(new { op = "query", window = Id, selector, limit }).GetProperty("elements").EnumerateArray()) list.Add(e.GetString()!);
        return list.ToArray();
    }
    /// <summary>Apply DOM operations atomically; each is a hashtable/object with <c>op</c> and that command's fields.</summary>
    public void Batch(System.Collections.IEnumerable operations)
    {
        Check();
        var ops = new System.Collections.Generic.List<object>();
        foreach (var item in operations)
        {
            var source = item is System.Management.Automation.PSObject ps ? ps.BaseObject : item;
            if (source is System.Collections.IDictionary map)
            {
                var copy = new System.Collections.Generic.Dictionary<string, object?>(StringComparer.Ordinal);
                foreach (System.Collections.DictionaryEntry e in map) copy[e.Key.ToString()!] = e.Value is System.Management.Automation.PSObject v ? v.BaseObject : e.Value;
                ops.Add(copy);
            }
            else ops.Add(source!);
        }
        app.Command(new { op = "batch", window = Id, ops });
    }
    public void SetDefaultAction(string element, string eventName, bool prevent = true, string? key = null, bool? shift = null, bool? ctrl = null, bool? alt = null, bool? meta = null)
    {
        Check();
        var command = new System.Collections.Generic.Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["op"] = "set_default_action", ["window"] = Id, ["element"] = element, ["event"] = eventName, ["prevent"] = prevent,
        };
        if (key is not null) command["key"] = key;
        if (shift is not null) command["shift"] = shift;
        if (ctrl is not null) command["ctrl"] = ctrl;
        if (alt is not null) command["alt"] = alt;
        if (meta is not null) command["meta"] = meta;
        app.Command(command);
    }
    public bool IsClosed => Closed;
    public void SetTitle(string title) { Check(); app.Command(new { op = "set_title", window = Id, title }); }
    public void Resize(int width, int height) { Check(); app.Command(new { op = "resize", window = Id, width, height }); }
    public string Snapshot(string path) { Check(); return app.Command(new { op = "snapshot", window = Id, path = Path.GetFullPath(path) }).GetRawText(); }
    public void Close() { Check(); app.Command(new { op = "close", window = Id }); }
}
