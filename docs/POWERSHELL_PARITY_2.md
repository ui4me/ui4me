# PowerShell module `UI4ME` 2.0.0 — status and parity with Python

`UI4ME` is pure PowerShell on `UI4ME.Core` 1.x (no compiled assembly, no Python, no second
host). It runs on PowerShell 7.2+ (Linux, Windows) and Windows PowerShell 5.1.

## Qualification (2026-11-14, artifact `UI4ME-2.0.0.zip`)

| Gate | Linux PS 7.7 | Windows PS 7.6 | Windows PowerShell 5.1 |
| --- | --- | --- | --- |
| Manifest/import with `RequiredModules UI4ME.Core`, exports = manifest, no Core name collisions | pass | pass | pass |
| Pester unit, lifecycle and static tests (mocked Core) | 25 pass, 1 skipped (Windows-only) | 26 pass | 26 pass |
| Real-input journey `tests/native/apps/ps_basic.ps1` through the native host (25 checks) | 25/25 (KWin Wayland, fake_input) | 25/25 (RDP input) | 25/25 (RDP input) |
| Examples through the real host (`-Headless`, smoke) | pass | not run | not run |
| Python `ui4me` journeys on the same machines (for comparison) | 20/20 + 15/15 | 20/20 + 15/15 | — |
| Clean shutdown: exit 0, no leftover host/backend processes | pass | pass | pass |

The journey covers: button click → handler → state → bound text; typing into a bound input
(computed text, Enter submit); checkbox; keyboard select; tabs; keyed list reorder keeping DOM
node and typed text, removal releasing handlers, one Core subscription per event type;
`New-UI4MEWhen` disposal stopping its timer and suppressing its task; runspace task result and
cancellation; CSS replacement twice without stylesheet growth; toast auto-dismiss; in-window
calendar and colour swatches; native save dialog from a blocking click handler; close veto;
`-OnClose` once on exit.

## Commands (59)

Application: `Invoke-UI4MEApp` (`-OnReady`, `-OnCloseRequest`, `-OnClose`, `-OnError`, `-AppId`,
`-Theme`, `-Css`, `-Assets`), `Stop-UI4MEUiApp`, `Wait-UI4MEUi`, `Get-UI4MEUiContext`,
`Get-UI4MEUiDiagnostics`, `Start-UI4MEUiScript` (`-WindowsPowerShell`, `-Headless`, `-NoWait`).
State: `New-UI4MEState`, `New-UI4MEComputed`. Work: `Start-/Stop-UI4MEUiTimer`,
`Start-/Stop-UI4MEUiTask`. Inputs: `New-UI4MEInput`, `-Number`, `-TextArea`, `-Checkbox`
(`-Switch`), `-Select`, `-Radio`, `-Slider`, `-Date`, `-Time`, `-Color`, `-Form`. Layout: `-Row`,
`-Column`, `-Card`, `-Grid`, `-Toolbar`, `-Scroll`, `-Divider`, `-Spacer`, `-Tabs`,
`-Accordion`. Content: `-Text`, `-Heading`, `-Badge`, `-Alert`, `-Code`, `-Image`, `-Link`,
`-List`, `-Table`, `-Progress`, `-Spinner`, `-Html`. Dynamic: `New-UI4MEWhen`, `New-UI4MEEach`,
`Add-/Remove-UI4MEUiContent`. Overlays: `New-UI4MEDialog`, `Show-/Close-UI4MEUiDialog`,
`Show-UI4MEUiToast`. Desktop: `Show-UI4MEUiFileDialog`, `Get-/Set-UI4MEUiSetting`. Styles:
`Add-UI4MEUiCss`, `Set-UI4MEUiTheme` (`-Css`, `-ColorScheme`, `-Reset`).
Anything else: the `UI4ME.Core` commands on `Get-UI4MEUiContext`'s `App`/`Window`/`Document`.

## Differences from Python (by design or not yet built)

| Area | Python `ui4me` | PowerShell `UI4ME` |
| --- | --- | --- |
| Windows per app | several (`app.window`) | one |
| Reactivity | automatic dependency tracking, effects, batching | explicit states; computed with `-DependsOn` |
| Component tree | owned components with refs and disposal | markup functions returning element ids; runtime content via owners (`When`/`Each`/`Add-UI4MEUiContent`) |
| Background work | threads with owner-thread completion, `async def` callbacks | separate runspaces (`Start-UI4MEUiTask`) polled by the UI loop; no access to script variables |
| Tables | search, sort, paging, selection, data-source loader (`ui.query_table`) | rows (optionally a state) and row click |
| Not in PowerShell | Markdown, chat, log stream, tree, navigation shell, drawer, menus, command palette, combobox, segmented, breadcrumbs, icons, form-from-dataclass, commands/shortcuts, clipboard helpers, desktop helpers | use `UI4ME.Core` commands directly where Core offers the service |

Callbacks run on the backend's single runspace, one at a time; Core answers close/quit policy
while a callback waits (for example, inside a native file dialog). Do not call UI4ME or
UI4ME.Core commands from other runspaces or jobs.
