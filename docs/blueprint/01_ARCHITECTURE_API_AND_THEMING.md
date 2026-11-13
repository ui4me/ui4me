# Architecture, Developer API, Theming and Extensibility

## Inviolable boundary
Core is a native runtime, not a high-level UI component framework. UI is a high-level framework, not an alternate renderer. UI calls only Core public interfaces; no direct access to Core internals. Domain-specific packages live above UI. UI's generic state, commands, dialogs, data-binding, generic state persistence hooks and task management are legitimate UI features.

Architecture modules (logical boundaries, not a demand for immediate file splitting):
- `runtime`: Core adapter, capability negotiation, owner thread, patch queue, diagnostics, errors, mount registry.
- `reactivity`: signals, computed, effects, transactions, stable keyed regions, component-owned tasks.
- `component`: consistent public props, anatomy/slots, refs, lifecycle, overlay/focus/keyboard base behaviors.
- `layout`: responsive row/column/stack/grid, app shell, split, scroll, visibility, containers.
- `inputs`: generic controls, field chrome, masks, formatting, parsing, validation and accessibility.
- `data`: table/tree/list views, selection, sorting, filtering, paged/lazy data sources.
- `navigation`: independent view controllers, tab state, breadcrumbs, history optional.
- `commands`: application/window/component scopes, shortcuts, menus, toolbars and palettes.
- `feedback`: dialogs, popovers, menu placement, toasts, status and loading.
- `desktop`: file dialogs, clipboard, tray, notifications, menu bars, hotkeys, print/export, file drops.
- `styles`: themes, CSS layers/contracts, tokens, density, typography, icons, reduced motion.
- `devtools`: component inspector, update trace, capability report, accessibility checks, failure diagnostics.

Do not add required web/HTTP process, hidden polling of arbitrary data structures, mandatory new markup DSL, runtime arbitrary JS, network fetches of CSS, or embedded native window toolkit.

## Public API principles
1. **Minimal happy path**: a plain value is enough for a control; default label/style/keyboard behavior are useful.
2. **Controlled or uncontrolled**: `value=` initial value and `bind=` state are distinct and clearly documented; programmatic updates do not silently pretend to be user edits.
3. **Universal props**: `classes`, `style`, `attrs`, `visible`, `enabled/disabled`, `tooltip`, test identifier and reference access behave consistently.
4. **Equivalent idioms**: Python with-blocks and PowerShell scriptblocks differ syntactically, not in fundamental behavior.
5. **Predictable ownership**: mounted components own effects, listeners, timers, tasks; a disposed component cannot receive late work.
6. **Stable identity**: stable keys preserve mounted child identity even when item data changes. Separate structural change from state update; explicit replacement opt-in.
7. **Composition and anatomy**: all nontrivial controls expose useful named parts (e.g. trigger, content, label, icon) and stable `data-u4-part` selectors, not a CSS requiring private DOM inspection.
8. **Event composability**: developer-supplied handlers can coexist with internal behaviors, with a documented cancellation/default-preventing model.
9. **Correct failure semantics**: stale Core element, full queue, partial invalidation and failed batches do not silently corrupt managed state.
10. **No magic in Core**: high-level behavior must be detachable; raw Core remains independently useful.

## Customization ladder (each level must be demonstrated)
A. `ui.button('Save')`: sensible default.
B. `ui.button('Save', variant='secondary', size='sm', disabled=...)`: semantic props.
C. `button.classes.add('my-action')`, `button.style.set('border-radius','...')`: instance CSS.
D. `app.theme.tokens(primary='...')`: token-level brand styling (existing).
E. `app.theme.load('brand.css', mode='replace')`: **proposed**, fully substitute shipped styling.
F. Slot/anatomy APIs for changing trigger/content/icon/label without cloning internals (**proposed**).
G. `@ui.component` reusable custom component with events/state/ownership (**existing basic pattern; upgrade contract**).
H. `ui.html(trusted_html)` and `ref.core_element()` / `ref.core_window` (**existing**), or an explicitly ownership-safe Core-managed island (**proposed**).

No one level must disable the levels above or below. Raw Core operations on elements owned by UI need a written supported/unsupported mutation contract: reading and cosmetic attributes can be safe; removing/reparenting managed roots externally must be forbidden or coordinated. Preserve unique IDs, binding invalidation, and event delegation ownership.

## Theme contract — high priority change
Current 0.4 implementation always begins with built-in `theme.css`; `app.css` appends stylesheets and `theme.tokens` adds another `:root` override. This supports additive customization, NOT full replacement or clean runtime theme switching. Core has public `add_stylesheet`, `replace_stylesheet`, and `remove_stylesheet` methods; UI should use stable stylesheet handles.

Proposed API shape (examples are DESIGN ONLY):
- `ui.app(..., theme='default')`, `ui.app(..., theme='none', css='custom.css')`, `ui.app(..., theme='mybrand')`.
- `app.theme.load(path_or_text, mode='replace'|'extend')` where path vs trusted CSS is unambiguous.
- `app.theme.set('mybrand')` changes named preset and preserves application state, focus and scroll.
- `app.theme.tokens(primary=..., radius_md=...)` overrides semantic tokens.
- `app.theme.scope(container, theme='dark')` / scoped `[data-u4-theme]` support, after confirming Core inheritance and media behavior.
- CSS load order: reset/base → chosen preset → user extension sheets → explicit app overrides → local styles (document cascade and specificity).
- `theme='none'` must still provide minimal accessibility and safe functional layout resets; decide and document base-versus-visual separation.

CSS anatomy:
- Stable namespace `.u4-*`, `--u4-*`, plus `data-u4-part`, `data-state`, `data-size`, `data-variant`, `data-density`.
- Separate *behavioral CSS* (visibility/inert/portal mechanics/keyboard focus and layout invariants) from *visual skin* (colors, shadows, geometry). Theme replacement should not break focus trapping or element reachability.
- Semantic tokens: fg, muted, bg, surface, elevated, border, focus, interactive, primary/success/warning/danger, selection; spacing, density, control height, fonts, line heights, radius, border width, shadow, animation duration, z-index, icon size.
- Themes: default light/dark/system; compact/comfortable/dense density; high contrast and reduced-motion; optional named modern/Fluent-like/neutral presets built from original CSS (do not copy copyrighted designs).
- Token names are a compatibility contract. CSS class anatomy documented per component with examples.
- Theme package should be offline/local by default. Explicit assets root, font paths, SVG and icon packs; no implicit remote fonts.
- Avoid runtime CSS duplication and monotonically increasing stylesheets when toggling theme.
- Maintain a visual gallery showing *same application + different CSS theme files* to prove actual skinnability.

## Responsive behavior
- Responsive containers, grid with breakpoints (12 columns optional), responsive props per breakpoint, min-width auto-fit grid, responsive stack/split, responsive visibility, responsive type/spacing/density.
- Prefer CSS media/container queries implemented by Core; Python breakpoint logic only when a component must switch behavior, not merely colors or orientation. Core already supports @media and @container, but require resize proof.
- Breakpoints configurable at theme level; no unnecessary owner-thread resize-event rerender for CSS-only changes.
- Distinguish *responsive styling* (CSS) vs *adaptive behavior* (sidebar becomes drawer, table becomes cards, keyboard navigation changes). Define local state preservation during adaptive transitions.
- Respect min widths, window constraints, overscroll, keyboard/IME, DPI scaling, font enlargement, OS theme/reduced motion, and potentially RTL/localization.

## Behavior services, deliberately UI-owned
- Overlay coordinator: dialogs, drawers, popovers, menus, tooltips; stack order, focus return/trap, Escape, outside click, virtual anchors, collision handling, scroll lock, per-window scoping.
- Command registry: action ID, title, icon, shortcut, enabled/visible predicate, window/component scope, permission of invocation, unified render into toolbar/menu/context menu/palette; no globally conflicting accelerators.
- Navigation controller: per-window default, explicit shared controller opt-in; history and view keep-alive policies explicit.
- Resource/data views: local list initially; data source protocol with `load(page,size,sort,filters,query)` callable (sync or scheduled) returning rows/count, cancel stale request; no server assumption.
- Validation/form controllers: typed parsing, errors, touched/dirty, rules, nested groups, validation-on-change/blur/submit, asynchronous work with stale-result guard.
- Generic UI settings: opt-in interface for remembering window size, theme, split position, sidebar state; user controls storage, UI offers in-memory and local-file adapters, not a mandatory database.
- Worker/task scopes: cancellation, progress, completion, UI-owner marshaling, error reporting, dispose safety.
- Localization helpers: labels and common component strings, number/date formatting, RTL semantics; app supplies dictionaries, no hardcoded translation service.

## Design rules for new components
Each has: semantic intent; minimal API; variants/size/density; classes/parts/style; controlled/uncontrolled values; events; lifecycle; keyboard behavior; AT semantics; responsive behavior; Core mapping; fallback on unsupported platform; headless test; native Linux/Windows test; Python/PowerShell example.

## Testing and release discipline
- Unit/component tests on headless Core for pure state, lifecycle, CSS/DOM mutation ownership, serialization.
- Native journeys for focus, IME, keyboard, screen reader where possible, popovers, Windows/Wayland/X11, sizing and styling.
- Visual baselines for each theme/density/OS; inspect real rendered screenshots, not only CSS strings.
- Installed consumer tests for BOTH language packages and dependency resolution.
- Compatibility matrix for supported Core versions; feature detection where needed.
- Tests fail when API examples or component registry status drift from reality.
- Targeted tests during implementation, full suite at integration milestones. No passing status from unexecuted tests.
