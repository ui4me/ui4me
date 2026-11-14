# Feature matrix (UI4ME 2.1.0)

What each language package provides, and how it was verified for 2.1.0. **Status:** ✅ implemented ·
◐ partial (limits in the note) · — not provided · ✖ not possible on Core 1.x.
**Evidence** names the test that exercised the feature on the released code:

- `KDE` — native journey on KDE Plasma 6 Wayland (KWin 6.3.6 virtual output), real compositor keyboard/mouse input.
- `WIN` — native journey on Windows Server 2022 through a real RDP session (keyboard/mouse input).
- `PS7`/`PS51` — the same PowerShell journey under PowerShell 7 and Windows PowerShell 5.1.
- `host` — real Core host, headless (DOM, IPC, lifecycle; simulated input); `unit` — no host; `Pester` — PowerShell unit tests.

Journeys: Python `tests/native/apps/py_basic.py`, `py_lifecycle.py`, `py_v21.py`, `py_ime.py`, `py_showcase.py` (every example);
PowerShell `ps_basic.ps1`, `ps_v21.ps1`, `ps_showcase.ps1` (every example). The full machine-readable record is
[`tools/release/records/qualification-2.1.0.json`](../../tools/release/records/qualification-2.1.0.json).

## Application, lifecycle and state

| Feature | Python API | PowerShell API | Py | PS | Evidence |
| --- | --- | --- | --- | --- | --- |
| Direct start (`python app.py`, `uv run`, `python -m`, `pwsh -File`, `powershell.exe -File`) | `ui.app(...)` + `app.run()` | `Invoke-UI4MEApp` | ✅ | ✅ | KDE, WIN, PS7, PS51; uv/`-m`/Unicode paths: host on Linux and Windows |
| Compatibility launchers | `ui4me-run [--headless]` | `Start-UI4MEUiScript` | ✅ | ✅ | KDE (`py_basic`, `py_lifecycle`), host |
| Single instance (second launch forwards) | `ui.app(app_id=...)` | `-AppId` | ✅ | ✅ | host (Python only; PowerShell uses the same Core mechanism, not separately tested) |
| Ctrl+C / SIGTERM / window close, no orphan host | — | — | ✅ | ✅ | Ctrl+C/SIGTERM: host, Python on Linux (exit 130, no leftovers); window close: every native journey in both languages checks leftovers |
| Startup error visible, exit status 1 | — | — | ✅ | ✅ | host Linux + Windows |
| Close veto | `window.on_close_request` | `-OnCloseRequest` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Multiple windows | `app.window(...)` | — | ✅ | — | KDE, WIN (`py_lifecycle`) |
| Reactive state, computed, batch | `ui.state`, `ui.computed`, `ui.batch` | `New-UI4MEState`, `New-UI4MEComputed -DependsOn` | ✅ | ◐ explicit dependencies | KDE, WIN, PS7, PS51 |
| Keyed lists keep DOM identity and typed text | `ui.each` | `New-UI4MEEach` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Conditional regions dispose timers, tasks, async | `ui.when` | `New-UI4MEWhen` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Thread-safe updates from workers | `app.post` (bounded, ordered) | runspace tasks (`Start-UI4MEUiTask`) | ✅ | ✅ | KDE, WIN (400 ordered posts), soak |
| Background tasks with cancel | `app.tasks.submit`, `TaskHandle.cancel` | `Start-UI4MEUiTask`, `Stop-UI4MEUiTask` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Timers | `app.after`, `app.every` | `Start-UI4MEUiTimer` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Persistent settings (atomic, shared JSON format) | `app.settings` | `Get/Set-UI4MEUiSetting` | ✅ | ✅ | unit, Pester, native examples |
| Callback errors isolated and reported | `app.on_error`, default toast | `-OnError` | ✅ | ✅ | KDE, WIN (`py_v21`), PS diagnostics |

## Inputs and forms

| Feature | Python API | PowerShell API | Py | PS | Evidence |
| --- | --- | --- | --- | --- | --- |
| Button, link | `ui.button`, `ui.link` | `New-UI4MEButton`, `New-UI4MELink` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Text input, textarea, number, password | `ui.input`, `ui.textarea`, `ui.number`, `ui.password` | `New-UI4MEInput`, `New-UI4METextArea`, `New-UI4MENumber` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| IME composition (pinyin) | any text field | any text field | ✅ | ✅ | KDE (fcitx5), WIN (Microsoft Pinyin) with the Python journey; PowerShell uses the same Core text input, not separately tested |
| Checkbox, switch, radio, select, slider | `ui.checkbox`, `ui.switch`, `ui.radio`, `ui.select`, `ui.slider` | `New-UI4MECheckbox`, `New-UI4MERadio`, `New-UI4MESelect`, `New-UI4MESlider` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Segmented choice | `ui.segmented` | `New-UI4MESegmented` | ✅ | ✅ | PS7, PS51, KDE (2.1 fix: PS segmented/radio `-Class`) |
| Multi-select (checkbox group) | `ui.multiselect` | `New-UI4MEMultiSelect` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Fieldset with legend | `ui.fieldset` | `New-UI4MEFieldset` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Date, time, color (in-window pickers) | `ui.date`, `ui.time`, `ui.color` | `New-UI4MEDate`, `New-UI4METime`, `New-UI4MEColor` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Generated forms with validation, dirty/touched/valid, change/blur modes | `ui.form(Model, validation_mode=...)` | `New-UI4MEForm` | ✅ | ◐ no typed schema/validation modes | KDE, WIN (`py_v21`) |
| Native file dialogs | `app.dialogs.open_file/save_file/folder` | `Show-UI4MEUiFileDialog` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Clipboard text | `app.clipboard`, `ui.copy_button` | `New-UI4MECopyButton`, Core `Get/Set-UI4MEClipboard` | ✅ | ✅ | KDE, WIN, PS7, PS51 (Unicode round-trip) |

## Layout, data and feedback

| Feature | Python API | PowerShell API | Py | PS | Evidence |
| --- | --- | --- | --- | --- | --- |
| Row, column, grid, card, scroll, spacer | `ui.row` … | `New-UI4MERow` … | ✅ | ✅ | native examples (all) |
| App shell, sidebar, header/footer/status bar | `ui.shell`, `ui.sidebar`, … | `New-UI4MEShell`, `New-UI4MESidebar`, … | ✅ | ✅ | native examples, Pester |
| Adjustable split (keyboard-operable) | `ui.resizable_split` | `New-UI4MEResizableSplit` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Tabs | `ui.tabs` | `New-UI4METabs` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Navigation pages, commands, command palette | `ui.navigation`, `app.commands`, `ui.command_palette` | — | ✅ | — | host, unit |
| Table: sort, search, keyboard selection, paging | `ui.table(..., sort=, search=, selected=)` | `New-UI4METable -OnRowClick` | ✅ | ◐ rows + click only | KDE, WIN (`py_v21`) |
| Data source with paging/progress/cancel | `ui.query_table` | — | ✅ | — | KDE, WIN (`py_lifecycle`) |
| Metric / KPI | `ui.metric` | `New-UI4MEMetric` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Log view (bounded) | `ui.log` | `New-UI4MELog`, `Add-UI4MELogLine` | ✅ | ✅ | KDE, PS7, PS51; soak |
| Markdown, code, chat, tree, sparkline | `ui.markdown`, `ui.code`, `ui.chat`, `ui.tree`, `ui.sparkline` | `New-UI4MECode` only | ✅ | ◐ | host, unit, native examples |
| Dialog (Escape, focus return), confirm | `ui.dialog`, `ui.confirm` | `Show-UI4MEUiDialog` | ✅ | ✅ | KDE, WIN (`py_v21`) |
| Toast | `ui.notify` | `Show-UI4MEUiToast` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Tooltip (hover/focus, `aria-describedby`) | `ui.tooltip` | `New-UI4METooltip` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Themes: light/dark/system, tokens, CSS replace | `app.theme`, `ui.theme_preset`, `ui.stylesheet` | `Set-UI4MEUiTheme`, `Add-UI4MEUiCss` | ✅ | ✅ | KDE, WIN, PS7, PS51 |
| Icons | `ui.icon`, `ui.icon_button` | `New-UI4MEIcon`, `New-UI4MEIconButton` | ✅ | ✅ | Pester, unit, examples |

## Tooling

| Feature | Python | PowerShell | Evidence |
| --- | --- | --- | --- |
| Project generator | `ui4me-ui-new [--language powershell]` | — | host (generated app runs with `uv run`) |
| Coding-agent skills (Claude, Codex, OpenCode, Copilot, Cursor, Gemini), refuses to overwrite edits | `ui4me-ui-skill` | `Install-UI4MEUiSkill` | Linux CLI, Pester on PS7 and PS51 |

## Not possible on UI4ME Core 1.x (✖ in both languages)

System notifications, tray icons, global hotkeys, native menu bars and context menus, printing / PDF
export, HTML clipboard, native date/time/color OS pickers, JavaScript. UI4ME provides in-window
alternatives (toasts, in-window menus and pickers) and raises `NotImplementedError` / throws instead of
pretending. See [Core integration](../concepts/core-integration.md).

## Not covered by 2.1.0 evidence

Screen readers / assistive-technology output, HiDPI scale factors other than 100 %, multi-monitor,
file drag and drop, and a person at a physical monitor. Automated input on virtual displays is not the
same as manual use.
