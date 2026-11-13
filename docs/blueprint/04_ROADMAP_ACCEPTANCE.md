# Implementation Roadmap and Acceptance Gates

This is a dependency order, NOT a schedule estimate or instruction to implement everything at once. Do not freeze public APIs until at least one realistic full desktop application exercises them. Keep Python/PowerShell parity at milestone boundaries.

## Wave 0 — reconcile source-of-truth and contract (before new widgets)
- Replace stale original `contracts/component_matrix.json` entries marked NOT_STARTED with an evidence-backed inventory from actual UI 0.4 source; distinguish proposed/new/partial, Core requirement, Python+PowerShell API names, test links.
- Update Core mapping from tested 1.0.0 to supplied 1.0.1 with verified compatibility where applicable. Do not claim tested solely because source exists.
- Reconcile old design spec against current implementation and mark historical assumptions.
- Freeze a draft v1 component contract: lifecycle, identity, parts/slots, props/events, owner thread, CSS/token and theme layering, generic errors, platform degraded mode.
- Add current-version Python and PowerShell component gallery and a short agent-facing reference (`llms.txt` already exists).

**Gate**: every public 0.4 component has an accurate implemented/partial/unsupported status and an example; false NOT_STARTED claims are gone.

## Wave 1 — P0 correctness and composability
- Stable-key region update preserves child mounted state and focus even when item payload changes. Define new data propagation model and test reorder/update/delete/recreate, nested lists, input IME, selection and state.
- Every event-started async continuation inherits component/window owner task scope; cancellation or late-result ignore, no stale window posting.
- Failed DOM patch queue has explicit error/recovery/termination policy with deterministic test injection.
- Standard focus/keyboard helpers and field accessibility relationships; keyboard workflows tested.
- Per-window navigation controller; command scopes and callable-enabled predicates.
- Component API normalization across classes/styles/attrs/values/slots/ref/owner lifecycle.
- Shared Python/PowerShell behavior conformance harness with same fixtures.

**Gate**: correctness and lifecycle scenarios pass headless and native Linux/Windows; no public state leak on key updates; controlled failover proof.

## Wave 2 — CSS/theming and application skeleton
- Split functional CSS mechanics from visual theme skin, add named preset and genuine full replacement, editable/add/remove stylesheet handles.
- Add semantic tokens, stable CSS parts/data-state attributes, focus/high-contrast/reduced-motion, density presets, icon loading + SVG and theme/assets packaging.
- Create component gallery: default, light/dark, compact, high contrast, 1 wholly independent CSS theme; compare on Linux/Windows.
- Add responsive breakpoint properties/container-query recipes and tested app shells (header/sidebar/drawer/content/footer/status bar).
- Add toolbars, breadcrumbs, resizable panes and responsive navigation.

**Gate**: same app theme swaps by CSS without source changes and without losing focus/state; responsive narrow/medium/wide journeys pass.

## Wave 3 — standard components and overlays
- Implement shared overlay coordinator and command registry integrated with Core popovers/native menus where supported.
- Components: accordion, dropdown/menu/context menu, tooltip, popover, drawer, combobox/autocomplete, multiselect, segmented control, icon buttons, input groups, file/path/date/time, skeleton, badge/list group/link.
- Use WAI-ARIA keyboard patterns and Core accessibility tree; verify practical screen reader journey.
- Wire print/PDF, rich clipboard, file-drop, and Core native menu/hotkey/tray with graceful fallbacks.

**Gate**: Bootstrap-style essential component coverage with parity and reasonable desktop keyboard usability; no dependency on JS/web host.

## Wave 4 — data-heavy applications and higher-level helpers
- Define selection model and data-source protocol (local first, optional async); cancellation, error, loading, stale response handling.
- Upgrade table with selection, row actions, filters, columns; add tree/list views and property grid.
- Upgrade forms (dirty/touched, async validation, nested/conditional, field registry) and stepper wizard.
- Add optional layout preference storage, SVG charts and progress dashboard helpers after practical app need.
- Defer virtualization until profiling; do not implement a full model-view engine merely to mirror Qt API names.

**Gate**: file-manager-style and admin-dashboard reference apps use public UI APIs with satisfactory measured typing, sorting and navigation latencies.

## Wave 5 — stable packaging and developer ecosystem
- Publish precise Core compatibility/version constraints; installable package for Python + PowerShell with dependency resolution; one-command test in clean environment.
- Write CSS theme-author guide, component cookbook, API reference, accessibility table, capability fallback docs, component anatomy cheatsheets.
- Define deprecation/versioning policy, stable token names, stable behavior contracts and migration support.
- Optional premade CSS presets / component-gallery showcase; do not ship heavy editors unless user demand and Core capabilities are proven.

**Gate**: source package install, gallery, examples, native platform matrix, accessibility checks and release evidence independently verifiable. Release/publish only with owner authorization.

## Minimum reference applications (not product-specific framework features)
1. **Personal task/settings app**: CRUD local state, form, validation, notifications, theme swap.
2. **File explorer**: tree/list, resizable split, context menu, drag/drop + fallback, file operations performed by app.
3. **Admin dashboard**: data source, search/filter/sort, KPI/graphs, task-driven refresh.
4. **Live monitor**: stream, tasks/progress, status, native notifications, long-lived stability.
5. **Multiwindow editor**: controllers scoped per window; reusable custom component; Core escape hatch.
6. **Theme showcase**: one app across distinct CSS presets and desktop widths.

## Definition of done for each component
- Python/PowerShell public function signatures and expected semantics documented.
- Shared test fixtures cover state changes, events, error, owner disposal, key/focus behavior, keyboard/AT.
- Styles documented: tokens, classes/parts, variants, size/density and disabled/loading/focus/error.
- At least one single-file example per language, including a customization example.
- Core API usage and platform capability fallback documented.
- Native Linux Wayland/X11 and Windows smoke as appropriate, plus headless unit tests.
- No silent fallback to browser/JS/local HTTP; no unnecessary Core changes.

## Agent operating guidance
Implement waves sequentially with bounded parallel sub-work: independent widgets and docs can run in parallel after shared contracts are settled. Run targeted tests for local changes and the full gate at the wave boundary. Have reviewers audit mismatches independently. Log proven Core blockers in `05_CORE_HANDOFF.md`; do not patch Core casually from UI branch. Avoid broad refactoring solely for module aesthetics.
