# Application lifecycle, threading and scripts

```text
python app.py / pwsh -File app.ps1
            │
            ▼
 Core direct-start bootstrap (initial launcher)
            │
            ▼
 native ui4me-host (Rust, windows/layout/rendering)
            │ authenticated local IPC
            ▼
 same script as supervised Python/PowerShell backend
            │
            ▼
 UI4ME components, callbacks and application run loop
```

The native host is the **only** renderer and owns native window events. The backend is supervised separately; UI4ME never serves HTML over HTTP or runs JavaScript. Code before Core bootstrap may execute twice, so put filesystem writes, network actions and threads after the high-level start.

Python's `ui.app()` uses `Application.start()` internally, and `app.run()` pumps UI4ME's owner-thread queue while Core manages native event delivery. `app.stop()` requests an orderly quit. The adapter subscribes through `Application.on_window_event()`, not Core private members; shutdown must drain already delivered callbacks in order. `app.window(...)` creates additional windows sharing app state.

PowerShell's `Invoke-UI4MEApp` uses `Start-UI4MEScript` and `Wait-UI4ME` to pump events on one runspace. Scriptblocks run synchronously on that runspace, not in background runspaces. Core callbacks may issue nested RPCs, but long UI callbacks will slow response; use `Start-UI4MEUiTask` for background work.

Both languages retain legacy manifest launch and explicit host CLI for advanced deployment, but **daily development uses normal scripts**. User-initiated close and quit vetoes must run exactly once and fail closed where state might be lost. Run full native lifecycle suites after any adapter change.
