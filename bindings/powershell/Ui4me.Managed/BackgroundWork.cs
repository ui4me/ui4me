using System.Management.Automation;
using System.Management.Automation.Runspaces;

namespace Ui4me.Managed;

public sealed class BackgroundWork
{
    // Slots are released when workers actually exit, including workers from stopped sessions.
    private static readonly SemaphoreSlim Slots = new(4, 4);
    private volatile PowerShell? pipeline;
    private int cancelled;
    private int completed;
    public bool IsCompleted => Volatile.Read(ref completed) != 0;
    public bool IsCancelled => Volatile.Read(ref cancelled) != 0;
    public void Cancel()
    {
        if (Interlocked.Exchange(ref cancelled, 1) != 0) return;
        var running = pipeline;
        if (running is null) return;
        try
        {
            running.BeginStop(result => { try { running.EndStop(result); } catch (Exception) { } }, null);
        }
        catch (ObjectDisposedException) { }
        catch (InvalidOperationException) { }
    }

    internal static BackgroundWork Start(App app, ScriptBlock script, object[] arguments, ScriptBlock completion)
    {
        app.OwnerOnly();
        if (!Slots.Wait(0)) throw new InvalidOperationException("At most four background scripts may be active in this process.");
        var worker = new BackgroundWork();
        var text = script.ToString();
        var finished = ScriptClosure.Capture(completion);
        try
        {
            ThreadPool.QueueUserWorkItem(_ => worker.Run(app, text, arguments, finished));
            return worker;
        }
        catch { Slots.Release(); throw; }
    }

    private void Run(App app, string text, object[] arguments, ScriptBlock completion)
    {
        object[] result = Array.Empty<object>();
        Exception? error = null;
        try
        {
            if (IsCancelled) return;
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
                if (IsCancelled) return;
                using var input = new PSDataCollection<PSObject>();
                using var output = new PSDataCollection<PSObject>();
                input.Complete();
                var values = new List<object>();
                Exception? overflow = null;
                output.DataAdded += (_, _) =>
                {
                    foreach (var item in output.ReadAll())
                    {
                        if (values.Count < 256) values.Add(item);
                        else { overflow ??= new InvalidOperationException("Background output exceeded 256 entries."); Cancel(); }
                    }
                };
                // Do not retain unbounded diagnostic streams in an unattended worker.
                ps.Streams.Warning.DataAdded += (_, _) => ps.Streams.Warning.Clear();
                ps.Streams.Verbose.DataAdded += (_, _) => ps.Streams.Verbose.Clear();
                ps.Streams.Debug.DataAdded += (_, _) => ps.Streams.Debug.Clear();
                ps.Streams.Information.DataAdded += (_, _) => ps.Streams.Information.Clear();
                ps.Streams.Progress.DataAdded += (_, _) => ps.Streams.Progress.Clear();
                ps.Streams.Error.DataAdded += (_, _) =>
                {
                    foreach (var item in ps.Streams.Error.ReadAll()) error ??= item.Exception;
                };
                ps.AddScript("param($text,$arguments) $ErrorActionPreference='Stop'; & ([scriptblock]::Create($text)) @arguments")
                    .AddArgument(text).AddArgument(arguments);
                ps.Invoke<PSObject, PSObject>(input, output, new PSInvocationSettings());
                error ??= overflow;
                result = values.ToArray();
            }
            finally { pipeline = null; Runspace.DefaultRunspace = previous; }
        }
        catch (PipelineStoppedException) when (IsCancelled) { }
        catch (Exception failure) { error = failure; }
        finally
        {
            pipeline = null;
            Volatile.Write(ref completed, 1);
            Slots.Release();
            // A terminal App rejects this post. The worker never calls native UI methods directly.
            if (!IsCancelled)
                app.PostManaged(() =>
                {
                    try { return completion.InvokeReturnAsIs(result, error); }
                    catch (Exception callbackFailure) { app.FailCallback(callbackFailure); return null; }
                });
        }
    }
}
