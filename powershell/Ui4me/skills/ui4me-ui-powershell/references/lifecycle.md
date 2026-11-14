# Core and lifecycle constraints

`UI4ME.Core>=1.0.1` manages native startup. `Invoke-UI4MEApp` invokes `Start-UI4MEScript` (unless host-managed), establishes authenticated IPC, creates the document, subscribes events, and runs the PowerShell owner-runspace pump until shutdown.

App code prior to `Invoke-UI4MEApp` can run twice; only initialize side effects in `-Content` or `-OnReady`. Use `-OnCloseRequest` to return `$false` and veto closing, `-OnClose` to release resources once, and `Stop-UI4MEUiApp` for orderly app quit. No host metadata or token is hardcoded.

`Start-UI4MEUiTask -Work { ... } -OnDone {...}` runs work in a separate runspace; UI calls are only legal in the completion callback on the owner runspace. Scoped dynamic content and `New-UI4MEWhen`/`Each` cancel/suppress abandoned callbacks and timers. `Wait-UI4MEUi` pumps on the owner runspace; nested UI callbacks do not receive additional UI event callbacks until they finish.

`Get-UI4MEUiContext` exposes `App`, `Window`, `Document` Core objects for supported native services. Do not read raw connection tokens or modify an active managed node outside UI4ME; only use Core's public methods.

Core Linux baseline: Debian 13/KDE Wayland. Core Windows baseline: Windows Server 2022 x64. Native focus/placement, some clipboard requests and OS dialogs depend on platform/desktop policies. Core does not implement native tray, global hotkeys, system notifications, printing/PDF or rich clipboard.
