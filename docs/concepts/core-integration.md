# UI4ME Core boundary and unsupported native features

UI4ME depends on `ui4me-core >=1.0.1,<2` / `UI4ME.Core` 1.x and **does not ship native code**. Core owns Rust host, HTML/CSS parser/layout/paint, native windows, IPC authentication, accessibility, dialogs and desktop services. UI4ME owns high-level widget composition, state/validation, managed DOM and styling.

Python raw Core handles: `from ui4me import Application, Window, Document`; high-level `app.core`, `component.core_document`, `window.core.native` permit advanced integration. PowerShell `Get-UI4MEUiContext` exposes Core `App`, `Window`, `Document` objects.

**Ownership boundary:** managed nodes are owned by UI4ME. External Core calls must not remove/reparent/reload UI4ME-managed nodes or replace their document. Use `ui.html(trusted_markup)` islands for trusted custom markup. A full raw document replacement retires high-level managed components and causes safe de-synchronization, rather than silently editing stale nodes.

**Core 1.x limitations:** no general browser JS execution, web fetch, WebKit/Chromium, OS tray/global hotkeys, native OS menus, system notifications, arbitrary HTML clipboard, PDF export/printing, native date/time/color input pickers, or full browser CSS. UI4ME supplies in-window menus/toasts/pickers where appropriate, and clearly marks unsupported OS features rather than pretending they work.

## Measured Core 1.0.1 behavior that affects applications

These were observed while qualifying UI4ME 2.1.0 on KDE Plasma 6 Wayland and Windows Server 2022
and are properties of Core 1.0.1, not of UI4ME. UI4ME works around them where it can.

| Behavior | Effect | What UI4ME does / what you should do |
| --- | --- | --- |
| The host sends **every** DOM event of a document to the application ([ui4me-core#1](https://github.com/ui4me/ui4me-core/issues/1)) (pointer moves, focus, `transitionrun/start/end`, `selectionchange`, …); filtering happens in the client. A connection that falls more than ~128–256 messages behind is **disconnected** by the host, which ends the app. | A restyle that starts CSS transitions on many elements at once (a theme switch with colour transitions on every control) produced ~300 events in a millisecond. Over a Windows named pipe the backend could not drain them in time and the host closed the application. | The default theme has no colour transitions on controls, and UI4ME suspends transitions (`.u4-theme-switching`) while *it* switches theme or colour scheme. In your own CSS, avoid transitions/animations on many elements at once, especially properties that change together with a theme. |
| Rejected focus moves (`FOCUS_MOVE_REJECTED`) for disabled, inert or hidden targets. | A busy (disabled) button cannot take focus back from a closing dialog. | UI4ME never treats a rejected focus as a fatal DOM failure, and restores focus to a dialog's opener after it is re-enabled. |
| Composition (IME) updates the field value during preedit and sends ordinary `input` events, like browsers. | `on_change` / `-OnChange` handlers and `bind=` state see intermediate preedit text (`ni`, `ni hao`) before the committed text (`你好`). | Validate on submit or blur for IME-heavy fields (`ui.form(validation_mode="blur")`), or treat intermediate values as provisional. |
| Native host memory grows while content in a non-base font face (bold, monospace) is repeatedly inserted and removed during frequent text updates ([ui4me-core#2](https://github.com/ui4me/ui4me-core/issues/2)). | Measured 65 → 609 MiB host RSS over 30 minutes of extreme load (the UI4ME backend stayed flat). Typical apps re-create far less content. | Keep frequently changing content mounted and update its text/state (`ui.each` keeps rows, bound text updates in place) instead of re-creating subtrees with `ui.when` in a hot loop. |
| Headless test mode (`UI4ME_TEST_MODE=1`, `--headless`) host memory grows with every DOM mutation (≈0.3–0.5 KiB per operation). | Long headless soaks grow the *host* process. | Use native runs for long-session memory measurements. |
| Direct start runs the script twice (launcher, then supervised backend). | Side effects before `ui.app(...)` / `Invoke-UI4MEApp` happen twice. | Keep side effects inside the app or after it starts. |

Latest Core docs: [Python reference](https://github.com/ui4me/ui4me-core/blob/main/docs/reference/python-api.md), [PowerShell reference](https://github.com/ui4me/ui4me-core/blob/main/docs/reference/powershell-api.md), [lifecycle](https://github.com/ui4me/ui4me-core/blob/main/docs/concepts/lifecycle.md).
