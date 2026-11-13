# Developer Workflows and Scenarios

These workflows represent actual user needs, not promises that all example APIs already exist. `CURRENT` uses APIs inspected in 0.4; `PROPOSED` illustrates desired API direction. Each scenario should become a two-language documentation sample and an acceptance journey.

## Journey 1 — first window in less than a minute (CURRENT)

Python:

```python
from ui4me_ui import ui
with ui.app('Hello') as app:
    name = ui.input('Your name')
    ui.heading(lambda: f"Hello, {name.value or 'world'}!")
app.run()
```

PowerShell:

```powershell
Import-Module Ui4me.UI
Invoke-Ui4meUiApp -Title 'Hello' -Content {
    $name = New-Ui4meUiInput -Label 'Your name'
    New-Ui4meUiHeading -Value { "Hello, $($name.Value)" }
}
```

Desired: one high-level install action pulls Core transitively, simple standalone application; no HTML or manually wired event handlers required. Include 'run directly' and 'package for users' tutorials.

## Journey 2 — rapid admin/dashboard prototype (CURRENT + PROPOSED)

Start with `ui.shell`, `ui.navigation`, `ui.grid`, `ui.card`, `ui.table`, `ui.form`, `ui.notify` and an `app.tasks` worker. Add proposed KPI, toolbar, breadcrumb, command menu, and data-source widgets. No HTTP assumed. Acceptance: database/file rows can be read in worker and posted to owner thread; table selection opens a form; progress/loading/errors are automatic; app stays responsive.

## Journey 3 — replace the entire visual theme (PROPOSED)

```
with ui.app('Invoices', theme='none') as app:
    app.theme.load('styles/brand.css', mode='replace')
    with ui.card():
        ui.button('Create invoice', variant='primary')
```

Design contract: an identical application must successfully render in default, dark, high-contrast and independently authored custom brand CSS without changing source. CSS overrides use stable classes/parts/tokens rather than reverse-engineered private markup. Theme replacement must not disable keyboard/accessibility mechanics.

## Journey 4 — customize a single button (CURRENT + PROPOSED)

CURRENT: `button = ui.button('Run', variant='outline')`; then `button.classes.add('my-button')`; `button.style.set('border-radius','18px')`; `button.attr('title','Run now')`. PROPOSED: `button.part('icon')` or declarative component slots so the developer can change internal anatomy without forking the control.

Acceptance: any component exposes all common cosmetic props, external CSS can target its meaningful parts, and a custom callback can coexist with built-in accessibility and event behavior.

## Journey 5 — create a reusable project-specific component (CURRENT + PROPOSED)

Create a `ProjectCard` that combines heading, badge, menu, progress bar and action. Make state inputs reactive and child lifetime predictable. Customize only its CSS via app-level theme. Expose an icon slot, action slot, and on-open event, with docs explaining how to compose in Python and PowerShell. Must not require copying internal UI source or talking directly to Core for normal layout.

## Journey 6 — drop down into Core (CURRENT + PROPOSED)

CURRENT: `ui.html(trusted_html, css='...')`; component references support `.core_element()` and `.core_window`; `app.core` accesses native services. PROPOSED: a managed `ui.raw_element(tag, attrs, events, children=...)` or Core-island mount primitive, *only after* formalizing ownership and event routing.

Rules: read/inspect and cosmetic changes are allowed; external removal/reparenting of managed nodes must be explicitly coordinated or prohibited. Any raw HTML is trusted user source only; untrusted Markdown/data remains escaped.

## Journey 7 — settings page and generated form (CURRENT + PROPOSED)

CURRENT: dataclass or PowerShell schema + `ui.form`, control mapping and validation. PROPOSED: grouped/nested fields, field registry, dirty/touched state, date/path/enum option adapters, custom validation timing, save/reset UX, persisted preferences and accessible error summary.

Acceptance: invalid data focuses the first invalid field, errors are described to screen readers, async validation cannot overwrite newer edits, and form state is preserved while switching sections.

## Journey 8 — full-featured file manager style application

Use shell/sidebar/breadcrumb/tree/path box; resizable split; selectable file list/grid; search; sorting; context menu; command palette; drag-and-drop; dialogs; status bar; preview panel. Ordinary filesystem listing and changes remain application logic. Generic UI framework provides data view, selection, commands, feedback, layout persistence and native integration.

Needs: Core Wayland file-drop limits surfaced; fallback 'Add files' action through native file dialogs. Row edits should preserve focus. File operations run through worker scopes; cancellation and progress are visible.

## Journey 9 — long-running local utility / agent monitor

Use log/chat (existing), progress/jobs, task cancellation, bounded streams, status bar, notification/toast, command palette. User may keep app alive for days and reopen windows. Test late callbacks against destroyed components, sustained log traffic, and no unbounded retained nodes/tasks.

## Journey 10 — narrow window and HiDPI responsive UX

Same app at ~450 CSS px, ~900 px and wide desktop: sidebar collapses into drawer; cards reflow; table adopts scroll/card view without losing selected record; keyboard and screen reader relationships survive. Layout mostly via CSS media/container queries, behavior via minimal UI controllers. Test zoom/font scale, Windows DPI and KDE scaling.

## Journey 11 — multiwindow project editor

Main window shows projects; secondary window shows details; window-scoped navigation, overlay, commands, theme and focus. Shared application-level reactive model remains explicitly shared. Closing editor cancels its tasks and does not reset the main window navigation.

## Journey 12 — theming by independent third party

A contributor ships a folder of `theme.css`, optional local icons/fonts and a manifest. User installs/selects theme by name; no monkeypatching, no CSS internals assumptions, no Core rebuild. Test against component-gallery reference and check theme version/token compatibility. No plugin runtime required to load a static CSS theme.

## Journey 13 — embedding UI in existing raw-Core tool

Developer wants just one managed search/filter panel in an application that already controls raw HTML. Define component-root ownership, stylesheet isolation, lifecycle/cleanup and event delegation first. This should be a supported adoption path later, not a promise during 0.4.

## Journey 14 — PowerShell sysadmin tool

Expose forms, table, progress, multiwindow, native file dialogs and worker callbacks through idiomatic `New-Ui4meUi*` functions and native PowerShell scriptblocks. Do not require Python runtime, implicit remote networking or third-party web server. Run a same-feature conformance journey in Python.

## Journey 15 — component author / maintainer

Developer wants to add an accessible `Combobox`. They should be able to build on shared field shell, overlay/focus manager, keyboard navigation primitives, selection controller, CSS part contract and owner task scope. They should not need a bespoke DOM scheduler or duplicate theme mechanics. Once implemented, component automatically joins gallery, parity matrix and keyboard/AT test list.

## Authoring progression

- 5-minute demo: use `ui.app`, controls and CSS preset.
- 1-hour utility: add reactive state, generated form, file dialog, task and toast.
- 1-day tool: add shell, data table, navigation, commands and responsive design.
- Larger application: compose custom components, data-source views, multiwindow navigation, persistent layout, scoped tasks and direct Core escape hatches.
- Theme author: change only CSS tokens/parts and theme manifest, not Python/PowerShell source.
- Framework contributor: implement component against shared behavior/test contract, not reimplement low-level Core facilities.
