# ui4me for PowerShell

Use the repository build and package commands to create an installable module. Source module import fails clearly until managed and native payloads have been staged. See the generated evidence report for test results on a specific candidate.

```powershell
Import-Module Ui4me
Invoke-Ui4meApp {
    param($app)
    $window = New-Ui4meWindow '<h1>Hello</h1><button id="hello">Click me</button><p id="status">Ready</p>'
    $null = Register-Ui4meEvent $window click {
        param($event)
        Set-Ui4meText $window status 'Hello from PowerShell'
    } -Element hello
}
```

`Invoke-Ui4meApp` owns a persistent native thread and creates a new runspace for each application. An initializer receives `$app` followed by `-ArgumentList` values. Pass data explicitly; the caller's session variables, modules and closures are not imported. Event callbacks capture their registration scope and execute on the application's owner thread.

Seven cmdlets cover the common path. App and Window objects expose advanced operations without adding another cmdlet for each native command: `On`, `Timer`, `Post`, `Stop`, `OpenFile`, `Resize`, `SetTitle`, `Snapshot`, and diagnostics.

Only `Stop` and the managed `PostManaged` entry point may be called from other threads. PowerShell ScriptBlocks are runspace-bound: `Post(scriptblock)` must be registered on the owner thread. For external managed worker code use `PostManaged(Func<object>)`, and never access UI objects directly from that worker.

`$app.Work($script, $arguments, $completion)` runs a background script in an isolated runspace and dispatches its completion back to the owner. Completion receives an array of output objects and an exception (or `$null`). Pass arguments explicitly and treat shared mutable argument objects as your synchronization responsibility. At most four workers may be active in the process, including uncooperative workers left after a session stops. Each worker retains at most 256 output entries; this does not bound memory allocated inside arbitrary user code or one enormous returned object. Diagnostic streams are discarded; return structured diagnostics as data. Cancel via the returned worker's `Cancel()` method. Application cleanup also requests worker cancellation.

`Invoke-Ui4meApp` forwards bounded output and diagnostic streams. It requests native stop and asynchronous pipeline cancellation when the caller is interrupted. Cancellation of arbitrary unmanaged or uncooperative user code is not guaranteed. A still-running initializer prevents another application from starting in the same process.

Return `$false` from a `close_requested` callback to veto a normal close. `Stop-Ui4meApp` ignores vetoes. Retrieve a completed post with its `GetResult()` method. Do not block a callback or wait for posted work on the owner thread; `GetResult()` rejects such a wait. Callback failures propagate after native cleanup. Keep the returned subscription only when you intend to dispose it before the window closes.

The module targets PowerShell 7.4 APIs and a net8.0 assembly; contributors and CI use .NET 10 and PowerShell 7.6. The PowerShell host supplies its runtime. No separate .NET runtime installer is bundled. Windows PowerShell 5.1 is unsupported.

The published module contains Windows and Linux payloads in one package. Once the native DLL is loaded, module removal does not unload it. Start a fresh process after upgrading. `UI4ME_NATIVE_LIB` is an explicit absolute-path development override and should be absent in installed-consumer verification.
