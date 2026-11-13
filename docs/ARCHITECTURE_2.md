# Architecture — UI4ME 2.0

## One native host, a separate ergonomic layer

UI4ME Core (`ui4me-core` / `UI4ME.Core` 1.x) is the only renderer, window host and IPC
implementation: one Rust host process owns windows, input, IME, layout, rendering,
accessibility, dialogs and the DOM. The application backend (Python or PowerShell) is a
separate process the host starts from an app manifest, connected over an authenticated local
channel. UI4ME ships no renderer, host binary, browser, JavaScript, HTTP server or C# assembly;
it builds HTML/CSS and drives the DOM through documented Core APIs only.

```
ui4me-host (Rust, native windows) ──IPC──▶ backend process
                                           ├─ Python:     ui4me_core.Application  ◀─ ui4me (components, state, tasks)
                                           └─ PowerShell: UI4ME.Core cmdlets       ◀─ UI4ME module
```

Launch: `ui4me-run app.py` / `Start-UI4MEUiScript -Path app.ps1` write a temporary manifest
(`instance = "multiple"`) and run the bundled host; deployed apps ship their own `app.toml`.

## Python

* `ui4me.ui` — components and reactive state. `ui4me.Application/Window/Document` are the
  unchanged Core classes.
* `ui4me._ui._adapter.App` wraps `ui4me_core.Application`. Core delivers document and window
  notifications on its own ordered worker thread; the adapter posts them to the **UI owner
  thread** (the thread that built the app), which runs `app.run()`. All component, state and DOM
  work happens there.
  * Normal posts are bounded (512); `app.post` raises `UiBusyError` when full.
  * Lifecycle decisions (window close veto) use an unbounded **priority lane**, so a flooded
    queue can never veto a user's close. The policy waits at most 4 s for the owner thread and
    fails closed (keeps the window) if the handler raises or times out.
  * On shutdown, callbacks already queued are drained (≤ 0.5 s) and open windows' `on_close`
    handlers run once.
* **Events** are delegated: one Core subscription per event type per window, routed along the
  event `path` to component listeners (Core allows 256 subscriptions per document).
* **Patches** are queued per window and committed after each batch of reactive work: batchable
  operations go in atomic Core batches (≤ 1024 ops, ≤ 1 MiB), form values/focus/dialogs singly.
  A failed batch marks the window desynchronized and stops updating it (reported once).
* **Document generations:** if a window's document is replaced or unloaded outside UI4ME (raw
  `load_html`, `unload`, fatal renderer error), UI4ME disposes that window's components and
  never patches the new document.
* **Owned work:** timers, tasks and `async def` callbacks belong to the component that started
  them; disposing it cancels timers/tasks and suppresses late completions.

## PowerShell

`UI4ME` is pure PowerShell (5.1 and 7.2+) on `UI4ME.Core`.

* `Invoke-UI4MEApp` builds markup from component functions (dot-sourcing the `-Content`
  block), opens one window, then runs its own pump: `Wait-UI4ME` with short timeouts plus
  timers (`Start-UI4MEUiTimer`) and task completions (`Start-UI4MEUiTask`, separate runspaces).
  Everything runs on the backend's single runspace; Core's own rule of no UI calls from other
  runspaces holds.
* Events are delegated like Python (one `Register-UI4MEDocumentEvent` per type).
* Internal callbacks are `{Fn, Data}` records dispatched by module functions, not
  `.GetNewClosure()` blocks (closures lose access to the module's private functions).
* Runtime content (`New-UI4MEWhen`, `New-UI4MEEach`, `Add-UI4MEUiContent`) is rendered into an
  *owner*; removing it releases its handlers, bindings, timers and tasks.
* Two-way bindings keep a shadow of the last value seen from the control so they never write an
  older value back over newer keystrokes.

## Customisation layers

1. Component defaults and semantic CSS tokens (`--u4-*`).
2. Classes/styles/attributes, state and events on components.
3. Presets, density and extra CSS (`app.theme.tokens`, `ui.css`, `Add-UI4MEUiCss`).
4. Full visual replacement (`app.theme.load(css, mode='replace')`, `Set-UI4MEUiTheme -Css`) —
   implemented as one replaceable Core stylesheet; structural CSS stays.
5. Trusted HTML islands and custom components.
6. Raw Core access (`component.core_document`, `window.core.native`, `Get-UI4MEUiContext`).
   Do not delete or move UI4ME-managed nodes; use islands for raw DOM work.

## Versioning

UI4ME 2.x and Core 1.x release independently. `ui4me` 2.0.0 requires `ui4me-core>=1.0.0,<2`;
`UI4ME` 2.0.0 requires `UI4ME.Core` ≥ 1.0.0. The PowerShell theme CSS is copied from the Python
package at build time so both bindings look the same.
