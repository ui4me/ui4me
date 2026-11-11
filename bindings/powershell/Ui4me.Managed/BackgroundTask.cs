using System.Management.Automation;
using System.Management.Automation.Runspaces;

namespace Ui4me.Managed;

/// <summary>
/// One queued background script started by <see cref="App.RunInBackground(ScriptBlock, ScriptBlock?, ScriptBlock?)"/>.
/// The script runs in a pooled runspace and never touches UI objects; its outcome is delivered once
/// on the owner thread (onDone or onError). States: pending, running, succeeded, failed, cancelled.
/// </summary>
public sealed class BackgroundTask
{
    private readonly object gate = new();
    private readonly int owner;
    private readonly TaskCompletionSource<object?> outcome = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal readonly string Text;
    internal readonly object[] Arguments;
    internal readonly ScriptBlock? OnDone, OnError;
    private volatile PowerShell? pipeline;
    private int cancelRequested;
    private string state = "pending";
    private Exception? error;
    private object? value;
    private int delivered;
    internal BackgroundTask(int owner, string text, object[] arguments, ScriptBlock? onDone, ScriptBlock? onError)
    { this.owner = owner; Text = text; Arguments = arguments; OnDone = onDone; OnError = onError; }

    public string Status { get { lock (gate) return state; } }
    /// <summary>The outcome is final (callbacks may still be queued).</summary>
    public bool IsCompleted => outcome.Task.IsCompleted;
    public bool IsCancelled => Status == "cancelled";
    /// <summary>Cooperative flag, also visible to the script as <c>$Ui4meTask.IsCancellationRequested</c>.</summary>
    public bool IsCancellationRequested => Volatile.Read(ref cancelRequested) != 0;
    /// <summary>The completion callback ran (false for tasks discarded by stop).</summary>
    public bool Delivered => Volatile.Read(ref delivered) != 0;
    /// <summary>Position among tasks that ran to an outcome; callbacks are delivered in this order.</summary>
    public long CompletionSequence { get; private set; }
    public Exception? Error { get { lock (gate) return error; } }
    public object? Value { get { lock (gate) return value; } }

    /// <summary>Wait from a non-owner thread. Throws the script's error or a cancellation error.</summary>
    public object? GetResult()
    {
        if (Environment.CurrentManagedThreadId == owner && !IsCompleted)
            throw new InvalidOperationException("Do not wait for background work on the UI owner thread.");
        return outcome.Task.GetAwaiter().GetResult();
    }
    public bool Wait(int milliseconds) => outcome.Task.Wait(milliseconds);

    /// <summary>A pending task is cancelled at once; a running one is asked to stop.</summary>
    public bool Cancel()
    {
        bool settled = false;
        lock (gate)
        {
            if (outcome.Task.IsCompleted) return false;
            Volatile.Write(ref cancelRequested, 1);
            if (state == "pending") { state = "cancelled"; outcome.TrySetCanceled(); settled = true; }
        }
        if (!settled) Interrupt();
        return true;
    }
    internal void Interrupt()
    {
        var running = pipeline;
        if (running is null) return;
        try { running.BeginStop(r => { try { running.EndStop(r); } catch (Exception) { } }, null); }
        catch (ObjectDisposedException) { }
        catch (InvalidOperationException) { }
    }
    internal bool TryStart()
    {
        lock (gate)
        {
            if (state != "pending") return false;
            state = "running";
            return true;
        }
    }
    internal void Attach(PowerShell ps)
    {
        pipeline = ps;
        if (IsCancellationRequested) Interrupt();
    }
    internal void Finish(object? result, Exception? failure, long sequence)
    {
        lock (gate)
        {
            if (outcome.Task.IsCompleted) return;
            CompletionSequence = sequence;
            if (IsCancellationRequested) { state = "cancelled"; outcome.TrySetCanceled(); }
            else if (failure is not null) { state = "failed"; error = failure; outcome.TrySetException(failure); }
            else { state = "succeeded"; value = result; outcome.TrySetResult(result); }
        }
    }
    /// <summary>Stop shutdown: nothing unfinished stays pending or running.</summary>
    internal void CancelForShutdown()
    {
        lock (gate)
        {
            if (outcome.Task.IsCompleted) return;
            Volatile.Write(ref cancelRequested, 1);
            if (state == "pending") { state = "cancelled"; outcome.TrySetCanceled(); return; }
        }
        Interrupt();
    }
    internal bool MarkDelivered() => Interlocked.Exchange(ref delivered, 1) == 0;
}

/// <summary>Bounded runspace-pool scheduler and ordered, retrying settlement queue of one App.</summary>
internal sealed class BackgroundHost : IDisposable
{
    private const int MaxTracked = 1024;
    private readonly App app;
    private readonly int owner;
    private readonly object gate = new();
    private readonly Queue<(BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail)> waiting = new();
    private readonly Queue<(BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail)> settle = new();
    private readonly HashSet<BackgroundTask> tracked = new();
    private readonly int maxWorkers;
    private RunspacePool? pool;
    private int active;
    private long completed;
    private bool closed;
    private bool settling;
    private readonly List<Task> running = new();

    internal BackgroundHost(App app, int owner, int maxWorkers) { this.app = app; this.owner = owner; this.maxWorkers = maxWorkers; }

    internal BackgroundTask Start(ScriptBlock script, ScriptBlock? onDone, ScriptBlock? onError, object[] arguments)
    {
        ArgumentNullException.ThrowIfNull(script);
        ArgumentNullException.ThrowIfNull(arguments);
        // Closures are captured on the owner; runspace-bound script blocks never cross threads.
        var done = onDone is null ? null : ScriptClosure.Capture(onDone);
        var fail = onError is null ? null : ScriptClosure.Capture(onError);
        var task = new BackgroundTask(owner, script.ToString(), (object[])arguments.Clone(), done, fail);
        lock (gate)
        {
            if (closed || !app.Accepting) throw new InvalidOperationException("Application stopped.");
            if (tracked.Count >= MaxTracked) throw new InvalidOperationException($"Background task limit reached ({MaxTracked}).");
            tracked.Add(task);
            waiting.Enqueue((task, done, fail));
        }
        Pump();
        return task;
    }

    private void Pump()
    {
        while (true)
        {
            (BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail) item;
            lock (gate)
            {
                if (closed || active >= maxWorkers || waiting.Count == 0) return;
                item = waiting.Dequeue();
                if (!item.Task.TryStart()) { Enqueue(item); continue; }
                active++;
                pool ??= CreatePool();
            }
            var runner = Task.Run(() => Execute(item));
            lock (gate) { running.RemoveAll(t => t.IsCompleted); running.Add(runner); }
        }
    }

    private RunspacePool CreatePool()
    {
        var created = RunspaceFactory.CreateRunspacePool(1, maxWorkers, InitialSessionState.CreateDefault2(), new NullHost());
        created.Open();
        return created;
    }

    private void Execute((BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail) item)
    {
        object? result = null;
        Exception? failure = null;
        try
        {
            using var ps = PowerShell.Create();
            ps.RunspacePool = pool;
            item.Task.Attach(ps);
            if (!item.Task.IsCancellationRequested)
            {
                var collected = new List<object>();
                ps.Streams.Error.DataAdded += (_, _) => { foreach (var e in ps.Streams.Error.ReadAll()) failure ??= e.Exception; };
                ps.AddScript("param($text,$arguments,$task) $Ui4meTask = $task; $ErrorActionPreference='Stop'; & ([scriptblock]::Create($text)) @arguments")
                    .AddArgument(item.Task.Text).AddArgument(item.Task.Arguments).AddArgument(item.Task);
                foreach (var o in ps.Invoke()) { if (collected.Count < 256) collected.Add(o?.BaseObject ?? null!); else failure ??= new InvalidOperationException("Background output exceeded 256 entries."); }
                result = collected.Count == 0 ? null : collected.Count == 1 ? collected[0] : collected.ToArray();
            }
        }
        catch (PipelineStoppedException) when (item.Task.IsCancellationRequested) { }
        catch (Exception caught) { failure ??= caught is RuntimeException r && r.InnerException is not null ? r.InnerException : caught; }
        // One critical section: the settlement queue order is exactly the completion order.
        lock (gate)
        {
            item.Task.Finish(result, failure, ++completed);
            active--;
            Enqueue(item);
        }
        Pump();
    }

    private void Enqueue((BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail) item)
    {
        bool start;
        lock (gate)
        {
            if (closed) return;
            if (!item.Task.IsCompleted) { waiting.Enqueue(item); return; }
            settle.Enqueue(item);
            start = !settling;
            settling = true;
        }
        if (start) Task.Run(SettleLoop);
    }

    // One ordered delivery loop: a full queue backs off and retries the same head; nothing is dropped.
    private void SettleLoop()
    {
        var delay = 1;
        while (true)
        {
            (BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail) item;
            lock (gate)
            {
                if (closed || settle.Count == 0) { settling = false; return; }
                item = settle.Peek();
            }
            PostedWork work;
            try { work = app.PostManaged(() => Deliver(item)); }
            catch (Exception) { Discard(); return; }
            var fault = work.Completion.Task.IsFaulted ? work.Completion.Task.Exception!.GetBaseException() : null;
            if (fault is not null)
            {
                if (fault.Message.Contains("full", StringComparison.OrdinalIgnoreCase))
                {
                    Thread.Sleep(delay);
                    delay = Math.Min(delay * 2, 50);
                    continue;
                }
                Discard();
                return;
            }
            if (work.IsCancelled) { Discard(); return; }
            delay = 1;
            lock (gate) { if (settle.Count > 0 && ReferenceEquals(settle.Peek().Task, item.Task)) settle.Dequeue(); }
        }
    }

    private void Discard()
    {
        lock (gate)
        {
            foreach (var (task, _, _) in settle) tracked.Remove(task);
            settle.Clear();
            settling = false;
        }
    }

    // Owner thread. A throwing callback follows the normal callback-error path (stops the loop).
    private object? Deliver((BackgroundTask Task, ScriptBlock? Done, ScriptBlock? Fail) item)
    {
        lock (gate) tracked.Remove(item.Task);
        if (closed || !app.Accepting || !item.Task.MarkDelivered()) return null;
        var status = item.Task.Status;
        if (status == "succeeded") item.Done?.InvokeReturnAsIs(item.Task.Value);
        else if (status == "failed") item.Fail?.InvokeReturnAsIs(item.Task.Error);
        return null;
    }

    /// <summary>Stop/dispose: unfinished work becomes cancelled; no callback runs afterwards.</summary>
    internal void Shutdown(bool wait)
    {
        List<BackgroundTask> all;
        List<Task> runners;
        RunspacePool? toDispose;
        lock (gate)
        {
            closed = true;
            all = tracked.ToList();
            tracked.Clear();
            waiting.Clear();
            settle.Clear();
            runners = running.ToList();
            toDispose = pool;
        }
        foreach (var task in all) task.CancelForShutdown();
        if (!wait) return;
        try { Task.WaitAll(runners.ToArray(), TimeSpan.FromSeconds(30)); } catch (Exception) { }
        lock (gate) { pool = null; }
        try { toDispose?.Dispose(); } catch (Exception) { }
    }
    public void Dispose() => Shutdown(true);
}

internal sealed class NullHost : System.Management.Automation.Host.PSHost
{
    private readonly Guid id = Guid.NewGuid();
    public override string Name => "Ui4meBackground";
    public override Version Version => new(1, 0);
    public override Guid InstanceId => id;
    public override System.Management.Automation.Host.PSHostUserInterface? UI => null;
    public override System.Globalization.CultureInfo CurrentCulture => System.Globalization.CultureInfo.InvariantCulture;
    public override System.Globalization.CultureInfo CurrentUICulture => System.Globalization.CultureInfo.InvariantCulture;
    public override void SetShouldExit(int exitCode) { }
    public override void EnterNestedPrompt() { }
    public override void ExitNestedPrompt() { }
    public override void NotifyBeginApplication() { }
    public override void NotifyEndApplication() { }
}
