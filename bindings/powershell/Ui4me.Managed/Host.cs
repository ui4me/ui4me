using System.Collections.Concurrent;
using System.Management.Automation;
using System.Management.Automation.Runspaces;
using System.Runtime.ExceptionServices;

namespace Ui4me.Managed;

public sealed record StreamItem(string Kind, object? Value);

public sealed class ApplicationOperation
{
    private readonly ManualResetEventSlim completed = new(false);
    private readonly ConcurrentQueue<StreamItem> output = new();
    private int buffered;
    private int cancelled;
    private int overflow;
    internal ExceptionDispatchInfo? Error;
    internal volatile App? ActiveApp;
    internal volatile PowerShell? Pipeline;
    internal readonly string Script;
    internal readonly object[] Arguments;
    internal readonly string ModulePath;
    internal readonly string Backend;
    internal ApplicationOperation(string script, object[] arguments, string modulePath, string backend)
    { Script = script; Arguments = arguments; ModulePath = modulePath; Backend = backend; }
    public bool IsCompleted => completed.IsSet;
    public bool IsCancelled => Volatile.Read(ref cancelled) != 0;
    public bool Wait(int milliseconds) => completed.Wait(milliseconds);
    public StreamItem[] Drain()
    {
        var result = new List<StreamItem>();
        while (output.TryDequeue(out var item)) { Interlocked.Decrement(ref buffered); result.Add(item); }
        return result.ToArray();
    }
    internal void Add(string kind, object? value)
    {
        if (Interlocked.Increment(ref buffered) > 1024)
        {
            Interlocked.Decrement(ref buffered);
            if (Interlocked.Exchange(ref overflow, 1) == 0)
            {
                Error = ExceptionDispatchInfo.Capture(new InvalidOperationException("Ui4me output queue exceeded 1024 entries; application stopped."));
                Cancel();
            }
            return;
        }
        output.Enqueue(new StreamItem(kind, value));
    }
    public void Cancel()
    {
        if (Interlocked.Exchange(ref cancelled, 1) != 0) return;
        try { ActiveApp?.Stop(); } catch (Exception) { /* Terminal race; retain the original outcome. */ }
        var running = Pipeline;
        if (running is not null)
        {
            try { running.BeginStop(result => { try { running.EndStop(result); } catch (Exception) { } }, null); }
            catch (ObjectDisposedException) { }
            catch (InvalidOperationException) { }
        }
    }
    internal void Complete() => completed.Set();
    public void ThrowIfFailed()
    {
        if (!IsCompleted) throw new InvalidOperationException("Application has not finished.");
        Error?.Throw();
    }
}

public static class Host
{
    private static readonly BlockingCollection<ApplicationOperation> Queue = new(1);
    private static readonly object Gate = new();
    private static Thread? ownerThread;
    private static int busy;
    private const string Script = """
        param($App, $InitializerText, $UserArguments, $Ui4meManifest)
        $ErrorActionPreference = 'Stop'
        Import-Module -Name $Ui4meManifest -ErrorAction Stop
        & ([scriptblock]::Create($InitializerText)) $App @UserArguments
        $App.Run()
        """;

    public static ApplicationOperation Start(string initializer, object[] arguments, string modulePath, string backend)
    {
        if (Interlocked.CompareExchange(ref busy, 1, 0) != 0)
            throw new InvalidOperationException("Only one Ui4me application may run in this process. The previous application must finish first.");
        try
        {
            lock (Gate)
            {
                if (ownerThread is null)
                {
                    ownerThread = new Thread(RunOwner) { IsBackground = true, Name = "ui4me native owner" };
                    if (OperatingSystem.IsWindows()) ownerThread.SetApartmentState(ApartmentState.STA);
                    ownerThread.Start();
                }
            }
            var operation = new ApplicationOperation(initializer, arguments, Path.GetFullPath(modulePath), backend);
            Queue.Add(operation);
            return operation;
        }
        catch { Interlocked.Exchange(ref busy, 0); throw; }
    }

    private static void Stream<T>(PSDataCollection<T> source, ApplicationOperation operation, string kind)
    {
        source.DataAdded += (_, _) =>
        {
            foreach (var item in source.ReadAll()) operation.Add(kind, item);
        };
    }

    private static void RunOwner()
    {
        foreach (var operation in Queue.GetConsumingEnumerable())
        {
            try
            {
                if (operation.IsCancelled) continue;
                using var runspace = RunspaceFactory.CreateRunspace(InitialSessionState.CreateDefault2());
                runspace.ThreadOptions = PSThreadOptions.UseCurrentThread;
                if (OperatingSystem.IsWindows()) runspace.ApartmentState = ApartmentState.STA;
                runspace.Open();
                var previous = Runspace.DefaultRunspace;
                Runspace.DefaultRunspace = runspace;
                try
                {
                    using var app = new App(operation.Backend);
                    operation.ActiveApp = app;
                    if (operation.IsCancelled) { app.Stop(); continue; }
                    using var pipeline = PowerShell.Create();
                    pipeline.Runspace = runspace;
                    operation.Pipeline = pipeline;
                    using var input = new PSDataCollection<PSObject>();
                    using var output = new PSDataCollection<PSObject>();
                    input.Complete();
                    Stream(output, operation, "output");
                    Stream(pipeline.Streams.Warning, operation, "warning");
                    Stream(pipeline.Streams.Verbose, operation, "verbose");
                    Stream(pipeline.Streams.Debug, operation, "debug");
                    Stream(pipeline.Streams.Information, operation, "information");
                    Stream(pipeline.Streams.Progress, operation, "progress");
                    Stream(pipeline.Streams.Error, operation, "error");
                    pipeline.AddScript(Script).AddArgument(app).AddArgument(operation.Script)
                        .AddArgument(operation.Arguments).AddArgument(operation.ModulePath);
                    // A synchronous Invoke on UseCurrentThread preserves native owner affinity.
                    pipeline.Invoke<PSObject, PSObject>(input, output, new PSInvocationSettings());
                    if (pipeline.HadErrors && operation.Error is null)
                        operation.Error = ExceptionDispatchInfo.Capture(new InvalidOperationException("Application pipeline reported errors; see the forwarded error stream."));
                }
                finally
                {
                    operation.Pipeline = null;
                    operation.ActiveApp = null;
                    Runspace.DefaultRunspace = previous;
                }
            }
            catch (PipelineStoppedException) when (operation.IsCancelled) { }
            catch (Exception e) { operation.Error ??= ExceptionDispatchInfo.Capture(e); }
            finally
            {
                Interlocked.Exchange(ref busy, 0);
                operation.Complete();
            }
        }
    }
}
