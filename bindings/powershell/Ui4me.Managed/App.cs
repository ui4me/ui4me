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
    /// <summary>A default-action rule cancelled this cancelable event (0.3).</summary>
    public bool DefaultPrevented { get; init; }
    /// <summary>The returnValue of a dialog <c>close</c> event (0.4).</summary>
    public string ReturnValue { get; init; } = "";
    /// <summary>The <c>open</c>/<c>closed</c> state after a <c>toggle</c> event (0.4).</summary>
    public string NewState { get; init; } = "";
    /// <summary>Paths of a <c>file_dialog</c> or <c>file_drop</c> event; null when cancelled (0.4).</summary>
    public string[]? Paths { get; init; }
    /// <summary>An error reported by a native service such as a file dialog.</summary>
    public string Error { get; init; } = "";
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
            DefaultPrevented = r.TryGetProperty("default_prevented", out var dp) && dp.ValueKind == JsonValueKind.True,
            ReturnValue = Text(r, "return_value"), NewState = Text(r, "new_state"), Error = Text(r, "error"),
            Paths = r.TryGetProperty("paths", out var ps) && ps.ValueKind == JsonValueKind.Array ? ps.EnumerateArray().Select(x => x.GetString() ?? "").ToArray() : null,
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
    private readonly Dictionary<ulong, ScriptBlock> fileDialogs = new();
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
    internal ulong FileDialog(ulong window, string kind, ScriptBlock handler, string? title, string? directory, string? fileName, System.Collections.IDictionary? filters)
    {
        Active();
        ArgumentNullException.ThrowIfNull(handler);
        var token = checked((ulong)Interlocked.Increment(ref counter));
        var request = new Dictionary<string, object?>(StringComparer.Ordinal) { ["op"] = "file_dialog", ["window"] = window, ["token"] = token, ["kind"] = kind };
        if (!string.IsNullOrEmpty(title)) request["title"] = title;
        if (!string.IsNullOrEmpty(directory)) request["directory"] = Path.GetFullPath(directory);
        if (!string.IsNullOrEmpty(fileName)) request["file_name"] = fileName;
        if (filters is not null)
        {
            var list = new List<object>();
            foreach (System.Collections.DictionaryEntry entry in filters)
            {
                var value = entry.Value is PSObject ps ? ps.BaseObject : entry.Value;
                var extensions = value is string one ? new[] { one } : ((System.Collections.IEnumerable)value!).Cast<object>().Select(x => x.ToString()!).ToArray();
                list.Add(new { name = entry.Key.ToString(), extensions });
            }
            request["filters"] = list;
        }
        fileDialogs.Add(token, ScriptClosure.Capture(handler));
        try { Command(request); }
        catch { fileDialogs.Remove(token); throw; }
        return token;
    }
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
    public string MonitorsJson() => Command(new { op = "list_monitors" }).GetProperty("monitors").GetRawText();
    /// <summary>The platform capability report as JSON: platform, backend and per-feature status
    /// (supported, unsupported, denied, unavailable, unknown) with the reason.</summary>
    public string CapabilitiesJson() => Command(new { op = "capabilities" }).GetRawText();
    /// <summary>Single instance per user and app id: JSON {primary, ...}; a second instance forwards
    /// its paths (delivered to the primary as "open_files" events) and should exit.</summary>
    public string ClaimInstance(string[]? openFiles = null) => Command(new { op = "claim_instance", open_files = (openFiles ?? Array.Empty<string>()).Select(Path.GetFullPath).ToArray() }).GetRawText();
    /// <summary>Show a native notification; returns JSON {status, token, reason?}. Its events
    /// arrive as "notification" with the token.</summary>
    public string Notify(string title, string body = "", string? icon = null, string? urgency = null, object? actions = null)
    {
        var token = checked((ulong)Interlocked.Increment(ref counter));
        return Command(new { op = "notify", token, title, body, icon = string.IsNullOrEmpty(icon) ? null : Path.GetFullPath(icon), urgency = string.IsNullOrEmpty(urgency) ? null : urgency, actions = actions ?? Array.Empty<object>() }).GetRawText();
    }
    public void CloseNotification(ulong token) => Command(new { op = "close_notification", token });
    /// <summary>Create or update the tray icon; menu is an array of item hashtables.</summary>
    public string SetTray(string? icon = null, string tooltip = "", object? menu = null) => Command(new { op = "set_tray", icon = string.IsNullOrEmpty(icon) ? null : Path.GetFullPath(icon), tooltip, menu = menu ?? Array.Empty<object>() }).GetRawText();
    public string RemoveTray() => Command(new { op = "remove_tray" }).GetRawText();
    /// <summary>Register a global shortcut ("Ctrl+Alt+K"); returns JSON {status, reason?}.</summary>
    public string RegisterHotkey(string id, string accelerator) => Command(new { op = "register_hotkey", id, accelerator }).GetRawText();
    public void UnregisterHotkey(string id) => Command(new { op = "unregister_hotkey", id });
    /// <summary>Allow activated links by scheme (https, http, mailto) and optional host list; with
    /// open, Core opens allowed links with the OS handler. Core never navigates the document.</summary>
    public void SetLinkPolicy(string[] schemes, string[]? hosts = null, bool open = false) => Command(new { op = "set_link_policy", schemes, hosts = hosts is { Length: > 0 } ? hosts : null, open });
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
    internal bool Accepting => Volatile.Read(ref state) <= 1 && !stopping;
    private BackgroundHost? tasks;
    /// <summary>Run a script on a bounded runspace pool (4 at a time, extra tasks queue) and deliver its
    /// outcome once on the owner thread: onDone(value) or onError(exception). Owner thread only; see
    /// <see cref="BackgroundTask"/>. Unfinished tasks become cancelled when the app stops and no callback
    /// runs afterwards. A full native post queue delays delivery with backoff; nothing is dropped.</summary>
    public BackgroundTask RunInBackground(ScriptBlock work, ScriptBlock? onDone, ScriptBlock? onError) =>
        RunInBackground(work, onDone, onError, Array.Empty<object>());
    public BackgroundTask RunInBackground(ScriptBlock work, ScriptBlock? onDone, ScriptBlock? onError, object[] arguments)
    {
        Active();
        tasks ??= new BackgroundHost(this, owner, 4);
        return tasks.Start(work, onDone, onError, arguments);
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
            tasks?.Shutdown(false);
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
            else if (evt.Type == "file_dialog" && fileDialogs.Remove(evt.Token, out var dialogHandler))
            {
                dialogHandler.InvokeReturnAsIs(evt);
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
        if (state != 3 && !runActive) tasks?.Shutdown(true);
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
    public void AppendText(string element, string text) { Check(); app.Command(new { op = "append_text", window = Id, element, text }); }
    public void TrimChildren(string element, int keep, string from = "start") { Check(); app.Command(new System.Collections.Generic.Dictionary<string, object?> { ["op"] = "trim_children", ["window"] = Id, ["element"] = element, ["keep"] = keep, ["from"] = from }); }
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
    private System.Collections.Generic.Dictionary<string, object?> Request(string op, string? element)
    {
        var request = new System.Collections.Generic.Dictionary<string, object?>(StringComparer.Ordinal) { ["op"] = op, ["window"] = Id };
        if (!string.IsNullOrEmpty(element)) request["element"] = element; // PowerShell passes $null as ""
        return request;
    }
    private static ScrollState Scroll(JsonElement e) => new(
        e.GetProperty("x").GetDouble(), e.GetProperty("y").GetDouble(),
        e.GetProperty("min_x").GetDouble(), e.GetProperty("min_y").GetDouble(),
        e.GetProperty("max_x").GetDouble(), e.GetProperty("max_y").GetDouble(),
        e.GetProperty("width").GetDouble(), e.GetProperty("height").GetDouble(),
        e.GetProperty("scrollable").GetBoolean(),
        e.TryGetProperty("animating", out var animating) && animating.GetBoolean());
    public string GetValidityJson(string element) { Check(); return app.Command(Request("get_validity", element)).GetRawText(); }
    public string CheckValidityJson(string element) { Check(); return app.Command(Request("check_validity", element)).GetRawText(); }
    public ScrollState GetScroll(string? element = null) { Check(); return Scroll(app.Command(Request("get_scroll", element))); }
    /// <summary>behavior: auto (the CSS scroll-behavior), instant or smooth; null means auto.</summary>
    public ScrollState ScrollTo(string? element, double? x, double? y, string? behavior = null)
    {
        Check();
        var request = Request("scroll_to", element);
        if (x is not null) request["x"] = x;
        if (y is not null) request["y"] = y;
        if (!string.IsNullOrEmpty(behavior)) request["behavior"] = behavior;
        return Scroll(app.Command(request));
    }
    public ScrollState ScrollBy(string? element, double dx, double dy, string? behavior = null)
    {
        Check();
        var request = Request("scroll_by", element);
        request["dx"] = dx; request["dy"] = dy;
        if (!string.IsNullOrEmpty(behavior)) request["behavior"] = behavior;
        return Scroll(app.Command(request));
    }
    public void ScrollIntoView(string element, string block = "nearest", string inline = "nearest", string? behavior = null) { Check(); app.Command(new { op = "scroll_into_view", window = Id, element, block, inline, behavior = NullIfEmpty(behavior) }); }
    static string? NullIfEmpty(string? s) => string.IsNullOrEmpty(s) ? null : s;
    /// <summary>Set (menu array of item hashtables) or clear ($null) the window menu; JSON status.</summary>
    public string SetMenu(object? menu) { Check(); return app.Command(new { op = "set_menu", window = Id, menu }).GetRawText(); }
    /// <summary>Pointer grab: none, confined or locked; outcome as a pointer_grab event.</summary>
    public string SetPointerGrab(string mode, bool cursorVisible = true) { Check(); return app.Command(new { op = "set_pointer_grab", window = Id, mode, cursor_visible = cursorVisible }).GetRawText(); }
    public string ShowContextMenu(double x, double y, object menu) { Check(); return app.Command(new { op = "show_context_menu", window = Id, x, y, menu }).GetRawText(); }
    /// <summary>Serialize an element (by id), a node reference, or the whole document (both empty).</summary>
    public string GetHtml(string? element = null, string? node = null, bool outer = false) { Check(); return app.Command(new { op = "get_html", window = Id, element = NullIfEmpty(element), node = NullIfEmpty(node), outer }).GetProperty("html").GetString()!; }
    /// <summary>Rendered text and range rectangles of an element (start/end are UTF-16 offsets
    /// into that text; a negative value means the beginning / the end). Returns JSON.</summary>
    public string TextRectsJson(string? element = null, string? node = null, int start = -1, int end = -1)
    {
        Check();
        return app.Command(new { op = "text_rects", window = Id, element = NullIfEmpty(element), node = NullIfEmpty(node), start = start < 0 ? (int?)null : start, end = end < 0 ? (int?)null : end }).GetRawText();
    }
    /// <summary>The text under a viewport point as JSON (null when there is none).</summary>
    public string TextAtPointJson(double x, double y) { Check(); return app.Command(new { op = "text_at_point", window = Id, x, y }).GetProperty("hit").GetRawText(); }
    /// <summary>Computed values (schema 1) of properties of an element, as JSON.</summary>
    /// <summary>Developer diagnostics, schema 1 (see DIAGNOSTICS_SCHEMA_V1.md): JSON {schema, items, dropped}.
    /// Paths and URL queries are redacted unless <paramref name="redact"/> is false; <paramref name="since"/> is the
    /// highest seq already seen (0 = all); <paramref name="kinds"/> filters by kind.</summary>
    public string GetDiagnosticsJson(bool redact = true, ulong since = 0, string[]? kinds = null) { Check(); return app.Command(new Dictionary<string, object?> { ["op"] = "get_diagnostics", ["window"] = Id, ["redact"] = redact, ["since"] = since == 0 ? null : since, ["kinds"] = kinds is { Length: > 0 } ? kinds : null }).GetRawText(); }
    /// <summary>Why a CSS property has no effect on an element: JSON {schema, status, reason, ...}; a removed or unknown
    /// element answers status "stale_reference".</summary>
    public string ExplainJson(string element, string? property = null, bool redact = true) { Check(); return app.Command(new Dictionary<string, object?> { ["op"] = "explain", ["window"] = Id, ["element"] = element, ["property"] = property, ["redact"] = redact }).GetRawText(); }
    public string ComputedStyleJson(string element, params string[] properties) { Check(); return app.Command(new { op = "get_computed_style", window = Id, element, properties }).GetRawText(); }
    /// <summary>The paths the user chose in a file input.</summary>
    public string[] GetFiles(string element) { Check(); return app.Command(new { op = "get_files", window = Id, element }).GetProperty("files").EnumerateArray().Select(e => e.GetString()!).ToArray(); }
    /// <summary>Attach an author stylesheet; returns JSON {sheet, diagnostics}.</summary>
    public string AddStylesheet(string css) { Check(); return app.Command(new { op = "add_stylesheet", window = Id, css }).GetRawText(); }
    public string ReplaceStylesheet(long sheet, string css) { Check(); return app.Command(new { op = "replace_stylesheet", window = Id, sheet, css }).GetRawText(); }
    public void RemoveStylesheet(long sheet) { Check(); app.Command(new { op = "remove_stylesheet", window = Id, sheet }); }
    public string StylesheetsJson() { Check(); return app.Command(new { op = "list_stylesheets", window = Id }).GetProperty("sheets").GetRawText(); }
    /// <summary>The node reference of an element, or of the document when empty.</summary>
    public string NodeOf(string? element = null) { Check(); return app.Command(new { op = "node_of", window = Id, element = NullIfEmpty(element) }).GetProperty("node").GetString()!; }
    public string NodeJson(string node) { Check(); return app.Command(new { op = "get_node", window = Id, node }).GetRawText(); }
    public string NodeChildrenJson(string node, int offset = 0, int limit = 256) { Check(); return app.Command(new { op = "node_children", window = Id, node, offset, limit }).GetRawText(); }
    /// <summary>Override media preferences (colorScheme light/dark/system, reducedMotion
    /// reduce/no-preference/system; null or empty leaves one as it is — PowerShell passes $null to a
    /// string parameter as ""). Returns the environment JSON.</summary>
    public string SetEnvironment(string? colorScheme = null, string? reducedMotion = null)
    {
        Check();
        return app.Command(new { op = "set_environment", window = Id, color_scheme = string.IsNullOrEmpty(colorScheme) ? null : colorScheme, reduced_motion = string.IsNullOrEmpty(reducedMotion) ? null : reducedMotion }).GetRawText();
    }
    /// <summary>Media preferences in force and their source, as JSON.</summary>
    public string EnvironmentJson() { Check(); return app.Command(new { op = "get_environment", window = Id }).GetRawText(); }
    public ElementRect? GetRect(string element)
    {
        Check();
        var r = app.Command(new { op = "get_rect", window = Id, element }).GetProperty("rect");
        return r.ValueKind == JsonValueKind.Null ? null : new ElementRect(r.GetProperty("x").GetDouble(), r.GetProperty("y").GetDouble(), r.GetProperty("width").GetDouble(), r.GetProperty("height").GetDouble());
    }
    public void SetScrollFollow(string? element, bool follow = true) { Check(); var request = Request("set_scroll_follow", element); request["follow"] = follow; app.Command(request); }
    public string GetSelection() { Check(); return app.Command(new { op = "get_selection", window = Id }).GetProperty("text").GetString()!; }
    public void ClearSelection() { Check(); app.Command(new { op = "clear_selection", window = Id }); }
    public void SelectText(string? element = null) { Check(); app.Command(Request("select_text", element)); }
    public string CopySelection() { Check(); return app.Command(new { op = "copy_selection", window = Id }).GetProperty("text").GetString()!; }
    public string? GetClipboardText() { Check(); var t = app.Command(new { op = "get_clipboard_text", window = Id }).GetProperty("text"); return t.ValueKind == JsonValueKind.Null ? null : t.GetString(); }
    public void SetClipboardText(string text) { Check(); app.Command(new { op = "set_clipboard_text", window = Id, text }); }
    public void SetClipboardHtml(string html, string text = "") { Check(); app.Command(new { op = "set_clipboard_html", window = Id, html, text }); }
    /// <summary>The clipboard HTML, sanitized unless raw; null without an HTML flavour.</summary>
    public string? GetClipboardHtml(bool raw = false) { Check(); var h = app.Command(new { op = "get_clipboard_html", window = Id, raw }).GetProperty("html"); return h.ValueKind == JsonValueKind.Null ? null : h.GetString(); }
    /// <summary>show, hide, focus, minimize, maximize, restore, fullscreen or exit_fullscreen.</summary>
    public WindowActionResult WindowAction(string action)
    {
        Check();
        var r = app.Command(new { op = "window_action", window = Id, action });
        return new WindowActionResult(r.GetProperty("applied").GetBoolean(), r.TryGetProperty("unsupported", out var u) ? u.GetString() : null, r.GetProperty("platform").GetString()!);
    }
    public WindowActionResult Show() => WindowAction("show");
    public WindowActionResult Hide() => WindowAction("hide");
    public WindowActionResult Activate() => WindowAction("focus");
    public WindowActionResult Minimize() => WindowAction("minimize");
    public WindowActionResult Maximize() => WindowAction("maximize");
    public WindowActionResult Restore() => WindowAction("restore");
    public WindowActionResult SetFullscreen(bool fullscreen = true) => WindowAction(fullscreen ? "fullscreen" : "exit_fullscreen");
    public void SetConstraints(int? minWidth = null, int? minHeight = null, int? maxWidth = null, int? maxHeight = null, bool resizable = true)
    {
        Check();
        var request = new System.Collections.Generic.Dictionary<string, object?>(StringComparer.Ordinal) { ["op"] = "set_window_constraints", ["window"] = Id, ["resizable"] = resizable };
        if (minWidth is not null) request["min_width"] = minWidth;
        if (minHeight is not null) request["min_height"] = minHeight;
        if (maxWidth is not null) request["max_width"] = maxWidth;
        if (maxHeight is not null) request["max_height"] = maxHeight;
        app.Command(request);
    }
    public void SetIcon(string? path)
    {
        Check();
        var request = new System.Collections.Generic.Dictionary<string, object?>(StringComparer.Ordinal) { ["op"] = "set_window_icon", ["window"] = Id };
        if (!string.IsNullOrEmpty(path)) request["path"] = System.IO.Path.GetFullPath(path);
        app.Command(request);
    }
    /// <summary>Observed state as JSON: visible, focused, minimized, maximized, fullscreen (null when unknown), size, scale, monitor.</summary>
    public string StateJson() { Check(); return app.Command(new { op = "get_window_state", window = Id }).GetRawText(); }
    /// <summary>Open a native file dialog; the handler receives the event (Paths is null when cancelled).</summary>
    public ulong OpenFileDialog(ScriptBlock handler, string? title = null, string? directory = null, System.Collections.IDictionary? filters = null, bool multiple = false) { Check(); return app.FileDialog(Id, multiple ? "open_multiple" : "open", handler, title, directory, null, filters); }
    public ulong SaveFileDialog(ScriptBlock handler, string? title = null, string? directory = null, string? fileName = null, System.Collections.IDictionary? filters = null) { Check(); return app.FileDialog(Id, "save", handler, title, directory, fileName, filters); }
    public ulong FolderDialog(ScriptBlock handler, string? title = null, string? directory = null) { Check(); return app.FileDialog(Id, "folder", handler, title, directory, null, null); }
    /// <summary>The semantic tree exposed to screen readers, as JSON.</summary>
    public string AccessibilityTreeJson() { Check(); return app.Command(new { op = "get_accessibility_tree", window = Id }).GetProperty("tree").GetRawText(); }
    public void ShowDialog(string element, bool modal = true) { Check(); app.Command(new { op = "show_dialog", window = Id, element, modal }); }
    public void CloseDialog(string element, string? returnValue = null)
    {
        Check();
        var request = Request("close_dialog", element);
        if (returnValue is not null) request["return_value"] = returnValue;
        app.Command(request);
    }
    public DialogState GetDialog(string element)
    {
        Check();
        var r = app.Command(new { op = "get_dialog", window = Id, element });
        return new DialogState(r.GetProperty("open").GetBoolean(), r.GetProperty("modal").GetBoolean(), r.GetProperty("return_value").GetString()!);
    }
    /// <summary>Show an element with a popover attribute.</summary>
    public void ShowPopover(string element) { Check(); app.Command(new { op = "show_popover", window = Id, element }); }
    /// <summary>Hide a popover (an auto popover also hides the popovers above it).</summary>
    public void HidePopover(string element) { Check(); app.Command(new { op = "hide_popover", window = Id, element }); }
    /// <summary>Toggle a popover; returns whether it is showing afterwards.</summary>
    public bool TogglePopover(string element) { Check(); return app.Command(new { op = "toggle_popover", window = Id, element }).GetProperty("open").GetBoolean(); }
    /// <summary>{"open": bool, "kind": "auto"|"manual"} as JSON.</summary>
    static Dictionary<string, object?> PageArgs(string? size, double? width, double? height, double[]? margins, bool printMedia)
    {
        var a = new Dictionary<string, object?> { ["print"] = printMedia };
        if (!string.IsNullOrEmpty(size)) a["size"] = size; // PowerShell passes $null as ""
        if (width is not null || height is not null) { a["width"] = width; a["height"] = height; }
        if (margins is not null) a["margins"] = margins;
        return a;
    }
    Dictionary<string, object?> PageRequest(string op, string? size, double? width, double? height, double[]? margins, bool printMedia)
    {
        var a = PageArgs(size, width, height, margins, printMedia);
        a["op"] = op;
        a["window"] = Id;
        return a;
    }
    /// <summary>Lay the document out as pages (CSS Paged Media); JSON <c>{count, pages, revision}</c>.</summary>
    public string PaginateJson(string? size = null, double? width = null, double? height = null, double[]? margins = null, bool printMedia = true) { Check(); return app.Command(PageRequest("paginate", size, width, height, margins, printMedia)).GetRawText(); }
    public string GetPageRectsJson(string element) { Check(); return app.Command(new { op = "get_page_rects", window = Id, element }).GetProperty("rects").GetRawText(); }
    public string RenderPage(int page, string path, double dpi = 96) { Check(); return app.Command(new { op = "render_page", window = Id, page, dpi, path }).GetRawText(); }
    public string ExportPdf(string path, string? size = null, double dpi = 150, string title = "", double? width = null, double? height = null, double[]? margins = null, bool printMedia = true)
    {
        Check();
        var a = PageRequest("export_pdf", size, width, height, margins, printMedia);
        a["path"] = path; a["dpi"] = dpi; a["title"] = title;
        return app.Command(a).GetRawText();
    }
    /// <summary>Print through the native dialog; the outcome is a <c>print</c> event.</summary>
    public string PrintDocument(string? size = null, double dpi = 300, string title = "", double? width = null, double? height = null, double[]? margins = null, bool printMedia = true)
    {
        Check();
        var a = PageRequest("print", size, width, height, margins, printMedia);
        a["dpi"] = dpi; a["title"] = title;
        return app.Command(a).GetRawText();
    }
    /// <summary>Capture the pointer (the mouse is pointer 1) for an element while a button is pressed; false when none is.</summary>
    public bool SetPointerCapture(string element, int pointerId = 1) { Check(); return app.Command(new { op = "set_pointer_capture", window = Id, element, pointer_id = pointerId, capture = true }).GetProperty("accepted").GetBoolean(); }
    public void ReleasePointerCapture(string element, int pointerId = 1) { Check(); app.Command(new { op = "set_pointer_capture", window = Id, element, pointer_id = pointerId, capture = false }); }
    public string? GetPointerCapture() { Check(); var e = app.Command(new { op = "get_pointer_capture", window = Id }).GetProperty("element"); return e.ValueKind == System.Text.Json.JsonValueKind.String ? e.GetString() : null; }
    /// <summary>Run a rich-text editing command (bold, italic, underline, strikethrough, code, link, unlink, remove_format, insert_text, insert_paragraph, undo, redo) on a contenteditable host; true when something changed.</summary>
    public bool ExecEdit(string element, string command, string? value = null) { Check(); return app.Command(new { op = "exec_edit", window = Id, element, command, value }).GetProperty("ok").GetBoolean(); }
    /// <summary>{"bold","italic","underline","strikethrough","code","link"} at the selection of a contenteditable host, as JSON.</summary>
    public string GetEditStateJson(string element) { Check(); return app.Command(new { op = "get_edit_state", window = Id, element }).GetRawText(); }
    public string GetPopoverJson(string element) { Check(); return app.Command(new { op = "get_popover", window = Id, element }).GetRawText(); }
    public SelectOption[] GetOptions(string element)
    {
        Check();
        var list = new System.Collections.Generic.List<SelectOption>();
        foreach (var o in app.Command(new { op = "get_options", window = Id, element }).GetProperty("options").EnumerateArray())
            list.Add(new SelectOption(o.GetProperty("value").GetString()!, o.GetProperty("label").GetString()!, o.GetProperty("selected").GetBoolean(), o.GetProperty("disabled").GetBoolean()));
        return list.ToArray();
    }
    public void SetSelectedValues(string element, string[] values) { Check(); app.Command(new { op = "set_selected_values", window = Id, element, values = values ?? Array.Empty<string>() }); }
    public bool IsClosed => Closed;
    public void SetTitle(string title) { Check(); app.Command(new { op = "set_title", window = Id, title }); }
    public void Resize(int width, int height) { Check(); app.Command(new { op = "resize", window = Id, width, height }); }
    public string Snapshot(string path) { Check(); return app.Command(new { op = "snapshot", window = Id, path = Path.GetFullPath(path) }).GetRawText(); }
    public void Close() { Check(); app.Command(new { op = "close", window = Id }); }
}

public sealed record ScrollState(double X, double Y, double MinX, double MinY, double MaxX, double MaxY, double Width, double Height, bool Scrollable, bool Animating = false);
public sealed record WindowActionResult(bool Applied, string? Unsupported, string Platform);
public sealed record DialogState(bool Open, bool Modal, string ReturnValue);
public sealed record SelectOption(string Value, string Label, bool Selected, bool Disabled);
public sealed record ElementRect(double X, double Y, double Width, double Height);
