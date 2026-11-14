# Changelog

## 2.1.0 — 2026-11-14

Normal scripts are now the way to run UI4ME apps: `python app.py`, `uv run app.py`,
`python -m package.app`, `pwsh -File app.ps1` and `powershell.exe -File app.ps1`. UI4ME delegates
startup and supervision to UI4ME Core 1.0.1 (`Application.start` / `Start-UI4MEScript`); `ui4me-run`
and `Start-UI4MEUiScript` remain for compatibility and headless tests. Requires `ui4me-core` /
`UI4ME.Core` `>=1.0.1,<2`.

### New

* Python: `ui.fieldset`, `ui.multiselect`, `ui.resizable_split` (keyboard-operable), `ui.metric`,
  `ui.tooltip`, `ui.copy_button`; forms track `dirty` / `touched` / `valid` and validate on
  `submit`, `change` or `blur` (`ui.form(validation_mode=...)`).
* PowerShell: the module is split into purpose-oriented private files (still pure script, 5.1 and 7);
  new shell layout (`New-UI4MEShell`, sidebar, header, footer, status bar), `New-UI4MEFieldset`,
  `New-UI4MEMultiSelect`, `New-UI4MESegmented`, `New-UI4MEResizableSplit`, `New-UI4MEMetric`,
  `New-UI4MELog`/`Add-UI4MELogLine`, icons, breadcrumbs, empty/loading states, `New-UI4METooltip`,
  `New-UI4MECopyButton`.
* Project generator `ui4me-ui-new` and coding-agent skill installers `ui4me-ui-skill` /
  `Install-UI4MEUiSkill` (Claude, Codex, OpenCode, Copilot, Cursor, Gemini; never overwrite edits).
* New documentation: install guides, quickstarts, recipes, API references, component catalog,
  [feature matrix](docs/reference/feature-matrix.md), gallery and reference apps (operations
  dashboard, settings) in both languages.

### Fixed during native qualification

* Windows: an app could be closed by the host during a theme switch. Core 1.0.1 forwards every DOM
  event; colour transitions on all controls produced a burst larger than the host's per-connection
  queue. The default theme no longer animates control colours, and UI4ME suspends transitions while
  it switches theme or colour scheme (both languages).
* A dialog opened from a button (`on_click=lambda: dlg.open()`) now returns focus to that button on
  close; a rejected focus move no longer stops all further window updates.
* Exceptions raised while building the UI are printed before the native host ends the process.
* Closing a window while the app is shutting down no longer raises.
* Owner-thread work is coalesced: callbacks already queued share one reactive flush and one DOM
  commit, removing a backlog under high-rate `app.post` use.
* Titles without ASCII letters (for example `日本語ツール`) get a unique settings folder instead of a
  shared `org.ui4me.app.app`; PowerShell titles starting with a digit no longer throw. Settings are
  flushed to disk before the atomic replace.
* PowerShell: `New-UI4MERadio` / `New-UI4MESegmented` failed (missing `-Class`); radio class values
  are escaped; the skills installer recognised its own managed files on Linux/macOS; removed runtime
  content no longer accumulates in its parent; logs accept empty lines.
* Accessibility and styling: tooltips are linked with `aria-describedby`; fieldsets and radio groups
  are themed; the adjustable split uses slider styling.

### Qualification

Native journeys with real input on KDE Plasma 6 Wayland and on Windows Server 2022 (RDP), Python
and PowerShell 7 / Windows PowerShell 5.1, including real pinyin IME composition on both systems.
Details, commands and hashes: [release notes](docs/release/RELEASE_NOTES_2.1.0.md) and
[`tools/release/records/qualification-2.1.0.json`](tools/release/records/qualification-2.1.0.json).

## 2.0.1 — 2026-11-14

* PowerShell: the module files are now `Ui4me.psd1`/`Ui4me.psm1` in a `Ui4me` folder, matching
  the PowerShell Gallery package id `Ui4me`. With 2.0.0, `Install-Module UI4ME` on Linux created a
  `Ui4me` folder holding `UI4ME.psd1`, which PowerShell cannot load on a case-sensitive file
  system (Windows was unaffected). `Import-Module UI4ME` keeps working with any casing.
  CI now imports the module from the Gallery folder layout, and the publish workflow installs the
  published module on Linux afterwards.
* Python: no changes; version aligned with the PowerShell module.

## 2.0.0 — 2026-11-14

UI4ME 2 is a component framework for Python and PowerShell on UI4ME Core 1.x. It replaces the
thin 0.1 facade in this repository; the native host now lives in `ui4me-core` / `UI4ME.Core`.

### Python (`ui4me` 2.0.0)

* `ui` component framework: reactive state, ~95 components, keyed lists, forms, tables and data
  sources, tasks/timers/`async` callbacks owned by components, multiple windows, commands,
  themes and presets, persistent settings (`app.settings`).
* Core adapter with an owner-thread dispatcher (priority lane for close decisions; bounded
  posts), delegated event subscriptions, atomic patch batches, and document-generation checks.
* `ui4me-run` launcher (`--headless` test mode, script arguments, `instance = "multiple"`).
* Date/time/month/week/colour fields with in-window calendar and swatches (Core 1.x refuses the
  native input types).
* `app.desktop`: Core-backed open/reveal, attention, window state, file drop, preferences;
  unsupported native services raise `NotImplementedError` with an in-window alternative.

### PowerShell (`UI4ME` 2.0.0)

* New module on `UI4ME.Core`: 59 commands — state/computed, bound inputs (text, number, date,
  time, colour, checkbox, select, radio, slider), layout, tabs, tables, keyed lists, `When`,
  dialogs, toasts, timers, cancellable runspace tasks, file dialogs, settings, theme replacement,
  `-Headless` and smoke mode, Windows PowerShell 5.1 backends.

### Fixed during qualification (each has a regression test)

* Components listened for a `commit` event Core never sends (now `change`).
* Window close handlers ran twice per close request (policy request + informational event).
* Core `dropped_files` events never reached `file_drop` listeners; event data is flattened.
* The main window's `on_close` was skipped when shutdown overtook the `closed` event; queued
  updates were discarded at shutdown.
* Under a post flood the bounded owner queue rejected the close policy, so the window could not
  be closed (Windows).
* `on_click=lambda i=i: ...` received the event instead of `i`.
* `ui.date`/`ui.time`/`ui.color`… produced inputs that made Core reject the whole document.
* Raw document replacement left UI4ME patching a document it no longer owned.
* Task state names (`succeeded`/`failed`) were never reported; a task cancelled before it
  started stayed "queued".
* A programmatic `window.close()` that the close policy vetoed left the window open with all
  its event subscriptions removed.
* Core events, timer ticks and task/dialog completions shared the bounded user post queue and
  were silently dropped under a post flood (they now use an unbounded internal lane).
* Fired one-shot timers were never released; command shortcuts could skip a new window whose
  `id()` reused a collected one; `settings.remove()` ignored keys stored as `None`;
  `ui.date(min=datetime)` raised `TypeError`.
* PowerShell: parameter variables were overwritten by same-named locals (`$disabled`, `$tone`),
  so buttons and badges threw; two-way input binding wrote stale values over newer keystrokes
  (lost characters on Windows); Windows PowerShell 5.1 backends failed to start through an
  absolute program path (Core issue C1, worked around); content rebuilt by `New-UI4MEWhen`/
  `New-UI4MEEach` during updates had no owner and outlived its item; a timer or task callback that
  pumped again could fire a one-shot timer twice or finish a task twice; timer and task callbacks
  now run under Core's dispatching guard; `-Min/-Max` dates ignore the time of day.
