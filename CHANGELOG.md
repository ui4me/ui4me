# Changelog

## 2.0.0 — unreleased

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
