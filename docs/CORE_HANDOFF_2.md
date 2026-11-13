# UI4ME Core issues found while building UI4ME 2.0

Core revision tested: `ui4me/ui4me-core` `main` `158036d` (source identical to `023859c` plus
publication records); published artifacts `ui4me-core` 1.0.0 (PyPI: manylinux_2_34 and
win_amd64 wheels, sdist) and `UI4ME.Core` 1.0.0 (PowerShell Gallery). Environments: Debian 13
(Linux 6.12, KWin 6 Wayland, virtual output) and Windows Server 2022 (10.0.20348) interactive
RDP session; Python 3.13, PowerShell 7.7 (Linux) / 7.6 (Windows), Windows PowerShell 5.1.
No change was made to the Core repository. Each item below is ready to file upstream.

## Bugs

### C1. Windows: an absolute `backend.program` is spawned through its `\\?\` path; Windows PowerShell 5.1 cannot start

* **Where:** `crates/ui4me-host/src/config.rs`, backend program resolution: on non-Unix the
  canonicalized path (`\\?\C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`) is
  executed instead of the path the manifest names (the Unix branch already keeps `candidate`).
* **Repro:** `app.toml` with `program = "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"`
  and a one-line backend; `ui4me-host run --app app.toml`.
* **Observed:** the backend exits 0xffff0000 with "The shell cannot be started. A failure occurred
  during initialization: The type initializer for 'System.Net.ServicePointManager' threw an
  exception." The same manifest with `program = "powershell.exe"` works. PowerShell 7 and Python
  backends are unaffected.
* **Expected:** spawn the path as written (or strip the verbatim prefix), as on Unix.
* **UI4ME workaround:** `Start-UI4MEUiScript` names `powershell.exe` without a path for 5.1
  backends (Pester regression test in `powershell/tests/UI4ME.Tests.ps1`).

### C2. `<input type=date|time|datetime-local|month|week|color>` makes the whole document fail to load

* **Where:** `crates/ui4me-renderer/src/document.rs`, `validate_input_type`.
* **Observed:** `document.load` fails with `-32602 INVALID_ARGUMENT: Input type 'date' requires a
  native picker and is unavailable in UI4ME Core`; the window stays empty.
* **Request:** either implement the pickers (and report them in `host.capabilities`), or degrade
  these types to a text control with a diagnostic instead of rejecting the whole document.
  The current behaviour turns one unsupported attribute in generated HTML into a fatal error.
  Also list the refused types in `docs/reference` and the capability report.
* **UI4ME workaround:** date/time/month/week/colour fields are validated text inputs with an
  in-window calendar and swatch palette; `ui.input(type='date')` and `New-UI4MEInput -Type date`
  are rejected with a clear message.

## API requests (no defect demonstrated)

### C3. Public window-event subscription in the Python client

`Application` registers the single `window.event` notification handler privately
(`Application._window_event`). A framework that needs `closed`, `resized`, `focused` or
`dropped_files` must wrap that private method and re-register it. Please add
`Application.on_window_event(callback)` that runs after Core's own bookkeeping (the PowerShell
binding already offers this through `Register-UI4MENotification`).

### C4. Public shutdown hook in the Python client

`app.shutdown` is consumed inside `RpcClient`; a framework has to replace the notification
handler to learn that shutdown began. Please add `Application.on_shutdown(callback)`.

### C5. Ordering of the final `window.event closed` and `app.shutdown`

With `ordered_notifications=True`, `app.shutdown` bypasses the ordered queue, so the last
window's `closed` event can still be queued when the shutdown flag is set. A loop that stops on
`shutdown_requested` loses it. UI4ME drains already-queued callbacks for up to 0.5 s and runs
window close handlers on shutdown. Please document the guarantee or deliver window `closed`
before `app.shutdown`.

### C6. Native services absent from Core 1.x

UI4ME 2.0 raises `NotImplementedError` (with an in-window alternative) for: native menu bars and
context menus, tray icons, global hotkeys, OS notifications, printing/PDF export, HTML clipboard,
and the native pickers in C2. If any of these are wanted natively, they need Core capabilities
with per-platform availability in `host.capabilities` and permission semantics (Wayland: global
hotkeys and tray are compositor-dependent).

## Observations (no action needed)

* Linux host supervision uses `systemd-run --user`; inside a private D-Bus session (UI4ME's
  isolated KWin test harness) it fails unless `UI4ME_ALLOW_UNSUPERVISED=1`
  (`--allow-unsupervised`). The harness sets it and records that supervision was not exercised.
* `ui4me-host run --headless` runs a complete backend without a desktop; UI4ME uses it for its
  real-host CI suite (`ui4me-run --headless`, `Start-UI4MEUiScript -Headless`).
* Verified under the real host with UI4ME's journeys: ordered event delivery, document
  generations (a raw `load_html` retires the old document; UI4ME then stops managing the
  window), repeated `replace_stylesheet` without sheet growth, 256-subscription ceiling avoided by
  delegation (one Core subscription per event type), > 1024 operations split into atomic
  batches, native file dialog cancel (`Escape` → no paths) on KDE and Windows, close veto during
  an open dialog (KDE) and while the owner is modal-disabled (Windows).
