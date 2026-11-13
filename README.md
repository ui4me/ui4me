# UI4ME 2 — native desktop UI components for Python and PowerShell

UI4ME is a component framework for desktop apps whose interface is HTML/CSS and whose
logic is Python or PowerShell. It runs on **[UI4ME Core](https://github.com/ui4me/ui4me-core)**,
the native host that owns windows, input, layout, rendering, accessibility and dialogs.
There is no browser, JavaScript engine, Electron or web server.

| Package | Install | Depends on |
| --- | --- | --- |
| Python `ui4me` 2.0.0 | `pip install ui4me` | `ui4me-core>=1.0.0,<2` (platform wheel with the native host) |
| PowerShell `UI4ME` 2.0.0 | `Install-Module UI4ME` | `UI4ME.Core` 1.x (`RequiredModules`) |

Supported: Linux x64 (KDE Plasma / Wayland qualified) and Windows x64; Python 3.11+;
PowerShell 7.2+ (Linux, Windows) and Windows PowerShell 5.1.

## Python

```python
from ui4me import ui

with ui.app("Hello", width=520, height=300) as app:
    name = ui.input("Your name", placeholder="Type here")
    ui.heading(lambda: f"Hello, {name.value or 'world'}!")
    ui.button("Close", on_click=app.stop)
app.run()
```

```bash
pip install ui4me
ui4me-run hello.py
```

The native host starts your script as its backend process and gives it an authenticated
IPC channel, so **run apps with `ui4me-run` (or a committed Core `app.toml` and
`ui4me-host run --app app.toml`), not `python hello.py`.**

What you get: reactive state (`ui.state`, `ui.computed`, `ui.effect`), 80+ components
(forms with validation, tables, keyed lists with `ui.each`, tabs, navigation, dialogs,
toasts, menus, command palette, Markdown, logs, chat, date/time/colour fields with
in-window pickers), owner-thread background tasks with cancellation (`app.tasks`,
`async def` callbacks), timers, persistent settings (`app.settings`), native file
dialogs, plain-text clipboard, multiple windows, close/quit vetoes and full CSS theming.

Raw Core is always available: `from ui4me import Application, Window, Document` are the
unchanged `ui4me_core` classes, and `component.core_document` / `window.core.native`
expose the live Core objects behind a UI4ME window.

## PowerShell

```powershell
Import-Module UI4ME
Invoke-UI4MEApp -Title 'Counter' -Content {
    $count = New-UI4MEState -Value 0
    New-UI4METext -Bind $count
    New-UI4MEButton -Text 'Add one' -OnClick { $count.Set($count.Value + 1) }
}
```

```powershell
Start-UI4MEUiScript -Path ./counter.ps1                     # PowerShell 7
Start-UI4MEUiScript -Path ./counter.ps1 -WindowsPowerShell  # Windows PowerShell 5.1 backend
```

The `-Content` block is dot-sourced, so states and helpers it defines stay visible to
callbacks. The module offers state and computed values, two-way bound controls, keyed
lists (`New-UI4MEEach`), conditional content (`New-UI4MEWhen`), tabs, tables, dialogs,
toasts, timers, cancellable background tasks (`Start-UI4MEUiTask`), native file dialogs,
settings and theme replacement. Every native operation goes through `UI4ME.Core`
commands; `Get-UI4MEUiContext` returns the Core `App`/`Window`/`Document` for direct use.
See [PowerShell parity](docs/POWERSHELL_PARITY_2.md) for what differs from Python.

## Themes

Components use semantic CSS tokens. Customise in layers: token overrides
(`app.theme.tokens(primary="#7c3aed")`), extra CSS (`ui.css(...)`, `Add-UI4MEUiCss`),
presets (`ui.theme_preset("ocean")`), full visual replacement
(`app.theme.load(css, mode="replace")`, `Set-UI4MEUiTheme -Css`), or your own trusted
HTML islands (`ui.html`). Light/dark follows the desktop unless set explicitly.

## Not available natively

UI4ME Core 1.x does not provide native menu bars or context menus, tray icons, global
hotkeys, OS notifications, printing/PDF export, rich (HTML) clipboard, or the
`date/time/month/week/color` input pickers. UI4ME does not fake them: the related
Python calls raise `NotImplementedError` naming an in-window alternative (`ui.menu`,
`ui.command_palette`, `app.commands` shortcuts, `ui.notify`), and the date/time/colour
fields are built from supported controls. See [Core handoff](docs/CORE_HANDOFF_2.md).

## Testing your app

`ui4me-run --headless app.py` and `Start-UI4MEUiScript -Headless` run through the real
host without a desktop window (DOM, IPC and lifecycle only; no native input or dialogs).
`ui4me._ui.testing.Pilot` scripts simulated user events in that mode.

## Documentation

- [Architecture](docs/ARCHITECTURE_2.md) — process model, threading, document generations, theming
- [Development](docs/DEVELOPMENT.md) — tests (unit, real host, real input on KWin/Windows), building, releasing
- [PowerShell parity](docs/POWERSHELL_PARITY_2.md) and [feature status](docs/FEATURE_STATUS_2.csv)
- [Core handoff](docs/CORE_HANDOFF_2.md) — Core issues found while building UI4ME 2
- [Migration](docs/MIGRATION_2.md) — from the 0.x/1.x `ui4me` packages
- [Changelog](CHANGELOG.md)

`docs/blueprint/` is the historical 155-feature planning backlog, not a statement of what
is implemented.

## License

MIT. See [LICENSE](LICENSE).
