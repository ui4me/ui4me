# Core ↔ UI Handoff Ledger

Purpose: record future Core issues, contracts, enhancements and blockers discovered while implementing UI. This is NOT a list of confirmed defects in UI4ME Core. Core source supplied is 1.0.1; UI 0.4 compatibility evidence and Core mapping are pinned to Core 1.0.0. Do not open speculative Core bug reports as if they are reproduced.

## Core contracts / verification requests

| ID | Type | Priority | Request / concrete test | Known evidence | UI action until resolved |
|---|---|---|---|---|---|
| CORE-U01 | Compatibility verification | High | Run UI 0.4 tests against supplied Core 1.0.1 and publish method/capability matrix | UI docs pin 1.0.0, Core supplied VERSION=1.0.1 | Retain tested 1.0.0 claim, do not assert 1.0.1 certified yet |
| CORE-U02 | Behavior verification | High | Test Core `add_stylesheet`, `replace_stylesheet`, `remove_stylesheet` during live theme swap, across windows, with focus/scroll preserved and no stylesheet accumulation | Existing public Core 0.6+ APIs; UI currently only adds CSS | Implement UI theme manager using stable Core sheet handles |
| CORE-U03 | Contract clarification | High | Verify exact failure semantics/atomicity of rejected `batch` operations and possible DOM/patch visibility | Core public docs describe atomic batch; UI currently reports batch failure | Build UI recovery strategy; request stronger Core guarantee only if tests show need |
| CORE-U04 | Regression verification | High | Verify move/insert/remove preserves focus/IME/selection and frame correct on same-key list updates/reorder | Core docs claim preserved; UI must exploit behavior correctly | First fix UI reconciliation; escalate only failing Core repro |
| CORE-U05 | Accessibility verification | High | Test full APG semantics for combobox/tree/menu/slider and accessible descriptions/error relationships through AccessKit AT-SPI/UIA | Core supplies accessibility tree; UI components not full screen-reader-journey tested | Compose semantic markup + test AT; raise targeted Core issues with tree snapshots |
| CORE-U06 | Cross-platform limitation | Medium | Native menubar on Linux not currently supported (Core docs); investigate GTK/KDE portal or alternative only if justified | UI docs explicitly call Linux window menubars unsupported | Provide in-app accessible menubar fallback; no false native promise |
| CORE-U07 | Cross-platform limitation | Medium | External file drop Wayland not delivered with current winit 0.30; assess future windowing backend update | Core docs say Windows/X11 file drops; no Wayland drops | UI dropzone fallback via file picker; expose capability bit |
| CORE-U08 | API capability verification | Medium | Popover positioning/anchor alignment/collision, nested popover focus and z-index under resize | Core has show/hide/get popover and get_rect APIs | Implement UI overlay placement first; escalate concrete missing geometry hook |
| CORE-U09 | API capability verification | Medium | Native print/PDF public methods, output scaling, page headers/footers, platform errors | Core 1.0 API lists paginate/export_pdf/print_document | Wrap public APIs; no separate UI print engine |
| CORE-U10 | Editing capability verification | Medium | Rich edit control selection/undo/IME, event sequencing in reactive host | Core 1.0 `exec_edit`/`get_edit_state` | Start with basic rich text; avoid promising full IDE editor |
| CORE-U11 | Pointer/drag capability verification | Medium | Pointer capture, touch, scroll and DnD input during resizable panes / drag reorder | Core 0.8 pointer capture present | Build pointer behavior in UI; report missing OS event only with repro |
| CORE-U12 | Responsive CSS verification | High | Container queries, media queries, CSS custom properties, scoped tokens, load order on Linux/Windows | Core 1.0 docs list modern CSS support | Prefer CSS-only adaptations; document any actual mismatch |
| CORE-U13 | Capability diagnostics | Medium | Ensure `capabilities()`, unsupported reason and `explain()` report enough context for UI fallback and public support docs | Core has public diagnostics methods | UI UI-level capability and diagnostic renderer |
| CORE-U14 | Performance evidence request | Medium | Measured DOM rows, tree/grid and CSS/theme swap budgets with live update and high DPI | Core docs include indicative logs but no UI-specific costs | Profile real reference apps before requesting virtualization primitives |
| CORE-U15 | Security/resource verification | Medium | CSS theme files, local SVG/icons/fonts, CSP-equivalent local resource limits, untrusted HTML escaping | Core public base_path/resources and UI trusted HTML contract | Restrict theme packages to local/trusted CSS; request API fixes only if proven |
| CORE-U16 | Native platform fallback | Low | Wayland activation/minimize/icon capability reporting consistency | Core docs report platform restrictions explicitly | Show unsupported feedback and document | 

## UI bugs not to misroute to Core

| ID | UI issue | Evidence | Primary fix owner |
|---|---|---|---|
| UI-B01 | `Each` does not provide update callback, changed existing items can be remounted despite same key | `src/ui4me_ui/components/regions.py` `KeyedChildren` and `Each` | UI |
| UI-B02 | Async continuations should be associated with originating component scope | `src/ui4me_ui/aio.py`, `component.py`, `app.py` | UI |
| UI-B03 | `Navigation` defaults to shared app-wide selection signal | `src/ui4me_ui/components/layout.py` | UI |
| UI-B04 | UI theme CSS always included and `app.css()` additive; no first-class full replacement | `src/ui4me_ui/theme.py`, `app.py` | UI |
| UI-B05 | DOM patch queue failure can leave UI state and native document inconsistent if no recovery | `src/ui4me_ui/window.py` | UI first, then Core batch semantics if needed |
| UI-B06 | Field help/error accessibility relations incomplete | `src/ui4me_ui/components/basic.py` | UI |
| UI-B07 | Original `component_matrix.json` labels existing components NOT_STARTED | spec archive vs UI source 0.4 | Documentation/process |
| UI-B08 | `Command.enabled` callable handling differs from other reactive callable props | UI command implementation | UI |

## How to hand off to the Core agent

Every *confirmed* Core issue must contain: (1) Core version/commit/OS/backend; (2) minimal program using public Core alone, without UI4ME UI; (3) expected and observed behavior; (4) screenshots/logs/diagnostic or accessibility tree if applicable; (5) severity and UI scenario it blocks; (6) proposed public API/behavior change, if needed; (7) native and headless regression criterion; (8) exact UI feature depending on resolution.

Do not ask a Core agent to build high-level UI components, menus, data models, state, theme presets or form validators. Do not assign issues merely because UI cannot yet expose something Core already supports. Use `CORE-Uxx` as research/verification ticket IDs, and mark bugs `CONFIRMED` only when reproducible in Core alone.
