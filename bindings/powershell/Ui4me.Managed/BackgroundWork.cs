using System.Management.Automation;
using System.Management.Automation.Runspaces;

namespace Ui4me.Managed;

/// <summary>One bounded background execution and its independently observable outcome.</summary>
public sealed class BackgroundWork
{
    // A stopped App cannot increase capacity while its arbitrary user code still runs.
    private static readonly SemaphoreSlim Slots = new(4, 4);
    private readonly object gate = new();
    private readonly int owner;
    private readonly TaskCompletionSource<object[]> outcome = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private volatile PowerShell? pipeline;
    private int cancelRequested;
    private int executionCompleted;
    private int delivery; // 0 pending, 1 callback running, 2 delivered, 3 discarded
    private object[] results = Array.Empty<object>();
    private Exception? error;
    private Exception? deliveryError;
    private BackgroundWork(int owner) => this.owner = owner;

    public bool IsCompleted => outcome.Task.IsCompleted;
    public bool IsExecutionCompleted => Volatile.Read(ref executionCompleted) != 0;
    public bool IsCancellationRequested => Volatile.Read(ref cancelRequested) != 0;
    public bool IsCancelled => outcome.Task.IsCanceled;
    public bool CompletionDelivered => Volatile.Read(ref delivery) == 2;
    public bool IsDeliveryCompleted => Volatile.Read(ref delivery) >= 2;
    public Exception? Error { get { lock (gate) return error; } }
    public Exception? DeliveryError { get { lock (gate) return deliveryError; } }
    public object[] Results { get { lock (gate) return (object[])results.Clone(); } }
    public string Status => !IsCompleted ? "running" : IsCancelled ? "cancelled" : Error is null ? "succeeded" : "failed";

    public object[] GetResult()
    {
        if (Environment.CurrentManagedThreadId == owner && !IsCompleted)
            throw new InvalidOperationException("Do not wait for background work on the UI owner thread.");
        return (object[])outcome.Task.GetAwaiter().GetResult().Clone();
    }

    public void Cancel()
    {
        lock (gate)
        {
            if (Interlocked.Exchange(ref cancelRequested, 1) != 0) return;
            outcome.TrySetCanceled();
        }
        RequestExecutionStop();
    }

    private void RequestExecutionStop()
    {
        var running = pipeline;
        if (running is null) return;
        try { running.BeginStop(result => { try { running.EndStop(result); } catch (Exception) { } }, null); }
        catch (ObjectDisposedException) { }
        catch (InvalidOperationException) { }
    }

    internal bool TryBeginDelivery()
    {
        lock (gate)
        {
            if (delivery != 0) return false;
            if (IsCancellationRequested) { delivery = 3; return false; }
            delivery = 1;
            return true;
        }
    }
    internal void FinishDelivery() { lock (gate) delivery = 2; }
    internal void DiscardDelivery(Exception? failure = null)
    {
        lock (gate) { if (delivery == 0) delivery = 3; deliveryError ??= failure; }
    }

    internal static BackgroundWork Start(App app, int owner, ScriptBlock script, object[] arguments, ScriptBlock completion)
    {
        app.OwnerOnly();
        ArgumentNullException.ThrowIfNull(script);
        ArgumentNullException.ThrowIfNull(arguments);
        ArgumentNullException.ThrowIfNull(completion);
        // Validate and capture before consuming process-wide capacity.
        var text = script.ToString();
        var finished = ScriptClosure.Capture(completion);
        var values = (object[])arguments.Clone();
        var worker = new BackgroundWork(owner);
        if (!Slots.Wait(0)) throw new InvalidOperationException("At most four background scripts may be active in this process.");
        ulong token = 0;
        try
        {
            token = app.ReserveBackground(worker, finished);
            var weakApp = new WeakReference<App>(app);
            if (!ThreadPool.QueueUserWorkItem(_ => worker.Run(weakApp, token, text, values)))
                throw new InvalidOperationException("The background scheduler rejected the work item.");
            return worker;
        }
        catch
        {
            try { if (token != 0) app.RollbackBackground(token); }
            finally { Slots.Release(); }
            throw;
        }
    }

    private void Run(WeakReference<App> application, ulong token, string text, object[] arguments)
    {
        var collected = new List<object>();
        Exception? failure = null;
        try
        {
            if (IsCancellationRequested) return;
            using var runspace = RunspaceFactory.CreateRunspace(InitialSessionState.CreateDefault2());
            runspace.ThreadOptions = PSThreadOptions.UseCurrentThread;
            runspace.Open();
            var previous = Runspace.DefaultRunspace;
            Runspace.DefaultRunspace = runspace;
            try
            {
                using var ps = PowerShell.Create();
                ps.Runspace = runspace;
                pipeline = ps;
                if (IsCancellationRequested) return;
                using var input = new PSDataCollection<PSObject>();
                using var output = new PSDataCollection<PSObject>();
                input.Complete();
                output.DataAdded += (_, _) =>
                {
                    foreach (var item in output.ReadAll())
                    {
                        if (collected.Count < 256) collected.Add(item);
                        else
                        {
                            failure ??= new InvalidOperationException("Background output exceeded 256 entries.");
                            // A limit failure remains an error; do not turn it into user cancellation.
                            RequestExecutionStop();
                        }
                    }
                };
                ps.Streams.Warning.DataAdded += (_, _) => ps.Streams.Warning.Clear();
                ps.Streams.Verbose.DataAdded += (_, _) => ps.Streams.Verbose.Clear();
                ps.Streams.Debug.DataAdded += (_, _) => ps.Streams.Debug.Clear();
                ps.Streams.Information.DataAdded += (_, _) => ps.Streams.Information.Clear();
                ps.Streams.Progress.DataAdded += (_, _) => ps.Streams.Progress.Clear();
                ps.Streams.Error.DataAdded += (_, _) =>
                {
                    foreach (var item in ps.Streams.Error.ReadAll()) failure ??= item.Exception;
                };
                ps.AddScript("param($text,$arguments) $ErrorActionPreference='Stop'; & ([scriptblock]::Create($text)) @arguments")
                    .AddArgument(text).AddArgument(arguments);
                ps.Invoke<PSObject, PSObject>(input, output, new PSInvocationSettings());
            }
            finally { pipeline = null; Runspace.DefaultRunspace = previous; }
        }
        catch (PipelineStoppedException) when (IsCancellationRequested || failure is not null) { }
        catch (Exception caught) { failure ??= caught; }
        finally
        {
            pipeline = null;
            lock (gate)
            {
                results = collected.ToArray();
                error = failure;
                if (IsCancellationRequested) outcome.TrySetCanceled();
                else if (failure is not null) outcome.TrySetException(failure);
                else outcome.TrySetResult(results);
                Volatile.Write(ref executionCompleted, 1);
            }
            Slots.Release();
            // Completion has reserved native capacity. It never competes with user posts.
            if (application.TryGetTarget(out var app)) app.PublishBackground(token, this);
            else DiscardDelivery();
        }
    }
}
