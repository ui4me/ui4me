# Feature Catalogue — UI4ME UI

A target list for an extensive general-purpose desktop component framework. Presence means visible in supplied 0.4 Python/PowerShell source, not independently tested. `E` existing, `P` partial/high-level contract to improve, `N` new high-level functionality. `P0` correctness prerequisite; `P1` essential; `P2` toolkit completeness; `P3` specialized. Components may use existing Core; do not copy rendering code into UI.

## 1. Framework machinery and developer experience

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| App, window, composition context | E | P0 | Consistent app/window child contexts; multiwindow scoping |
| Component refs/common props | P | P0 | Classes, styles, attrs, visible/disabled, tooltip, element access consistent |
| Reactive signals, computed, effects, batch | E | P0 | Owner-thread, cleanup, no redundant redraw |
| Keyed dynamic children | P | P0 | Same-key changed item preserves mounted instance/local state and focus |
| Conditional regions/keep-alive | P | P1 | Show/hide/remount and explicit lifetime/state retention policy |
| Owned tasks and async event callbacks | P | P0 | Component disposal cancels/ignores late results; UI-thread completion |
| DOM batch failure recovery | P | P0 | Resync/abort with visible error; no silent model/DOM divergence |
| Custom components/decorator | P | P0 | Reusable components with props, events, slots/parts, state lifecycle |
| Mount raw Core/HTML islands | P | P1 | Supported and safe ownership boundary; predictable CSS scopes |
| Window-scoped navigation | P | P1 | Independent controllers; explicit sharing |
| Command registry and shortcuts | P | P1 | Window/component scopes, reactive enabled/visible, collision rules |
| Component event modifiers | N | P2 | Debounce, throttle, once, key filtering where useful |
| Developer inspector and tracing | N | P2 | Tree, identity, subscriptions, pending tasks, CSS/Core diagnostics |
| Capability report/fallback inspector | P | P1 | Expose Core support and platform-specific reasons |
| State persisted preferences | N | P2 | Opt-in local settings adapter, not a mandatory database |
| LLM-friendly API reference/examples | P | P1 | Accurate current source and code snippets, no stale generated contracts |
| Error boundaries / diagnostic UI | P | P1 | Component failures localized where possible, safe recovery |
| Accessibility testing helpers | N | P1 | Keyboard/focus/AT snapshots and semantic validation |

## 2. Layout and responsive

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Row, column, stack, spacer, divider | E | P1 | Unified spacing/alignment APIs |
| Cards, surfaces, sections, paper | P | P1 | Variants and semantic elevation |
| Grid, auto-fit | E | P1 | Responsive property support and CSS-native layout |
| Responsive 12-column grid | N | P2 | Bootstrap-like intuitive `span` per breakpoint |
| Container queries/responsive props | P | P1 | Per-container adaptivity using Core CSS; avoid Python rerenders |
| Scroll container | E | P1 | Smooth scroll, focus visibility, optional sticky content |
| App shell/sidebar/content | E | P1 | Header, main, sidebar, optional footer/status bar |
| User-resizable split panes | P | P1 | Drag handle, keyboard adjust, persist split, collapse |
| Header/toolbar/status bar | N | P1 | Standard desktop shell anatomy |
| Drawer/offcanvas | N | P1 | Responsive sidebar, focus/overlay behavior |
| Sticky region, affix | N | P2 | Headers, actions that remain accessible |
| Aspect ratio / center / constrain | N | P2 | Layout helpers without manual CSS |
| Responsive visibility | P | P1 | Show/hide at breakpoint with state preservation |
| Responsive adaptive view switcher | N | P2 | Table-to-card / sidebar-to-drawer with shared controller |
| Scroll restoration | N | P2 | Per navigation panel/window opt-in |
| RTL-aware layout helpers | N | P2 | Logical CSS properties; keyboard patterns reflect direction |
| Window sizing/layout persistence | N | P2 | Optional preference adapter |

## 3. Typography, display, content and assets

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Text, headings, captions, badges | E | P1 | Type scale + variants; copy-friendly text |
| Icons and icon buttons | N | P1 | SVG icon packs, fallback, accessible icon labels; no huge mandatory font |
| Link, external link, action link | N | P1 | Safe Core link policy, disabled and focus behavior |
| Lists, description lists, list groups | N | P1 | Selectable and nonselectable variants |
| Avatar, avatar group | N | P2 | Image/initials/fallback |
| Image, caption, responsive image | P | P1 | Safe local assets, fit/position/sizing |
| Markdown, code, inline code | E | P1 | Safe Markdown with themes; language display |
| Static syntax highlighting | N | P2 | Optional pure host-language lexical highlighter; no JS |
| Rich text display | P | P2 | Safe HTML subset and content anatomy |
| Editable rich text | N | P2 | Use Core contenteditable/exec_edit; toolbar, selection, undo policy |
| Copy-to-clipboard affordance | N | P2 | Reusable copy button with success feedback |
| Key/value property grid | N | P2 | Inspector/preferences pages |
| Metric/KPI, statistic cards | N | P2 | Numeric formatting and trend annotation |
| Charts: line/bar/pie/sparkline | N | P2 | SVG-based composable views, optional module; avoid second renderer |
| SVG component | N | P1 | Inline SVG with explicit trusted asset contract |
| Video, audio players | N | P3 | Do not promise until Core supports media primitives |
| Maps | N | P3 | Optional app/domain integration, not framework baseline |

## 4. Buttons, selection and general inputs

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Button, variants, loading, async | E | P1 | Button anatomy, owner-safe async continuation |
| Button group, segmented control | N | P1 | Single/multiple selection, keyboard roving tabindex |
| Icon button, close button | N | P1 | Semantic labels required for icon-only |
| Input, password, textarea, number | E | P1 | Parsers, masks, clear, prefix/suffix, IME safe |
| Checkbox, switch, radio, select | E | P1 | Consistent controlled/uncontrolled policy |
| Slider, range slider | P | P2 | Range slider and keyboard behavior separate from simple slider |
| Combo box, autocomplete | N | P1 | Typeahead, async options, accessible focus/selection |
| Multi-select / tags input | N | P1 | Keyboard navigation and removable tokens |
| File input / dropzone / path picker | N | P1 | Native dialog helper + drag file fallback |
| Date picker / time picker / date range | N | P1 | Localization and keyboard editing; native where available |
| Color input / color picker | N | P2 | Typed value + visual palette |
| Search input with clear/debounce | N | P1 | Common list/table/filter use case |
| Masked input (phone/PIN) | N | P2 | Host-language formatting, preserve cursor/IME |
| Rating | N | P2 | Stars or other scale, keyboard and readonly |
| Knob/angle/hue advanced controls | N | P3 | Rare general desktop needs |
| Input group, suffix/prefix, floating label | N | P1 | Common field composition, with accessible label |
| Inline editable field | N | P2 | Safe enter/escape/commit semantics |

## 5. Forms and validation

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Form from dataclass or PowerShell schema | E | P1 | Typed property adaptation with explicit unsupported types |
| Field label/help/error/required | P | P0 | Proper `aria-describedby`, error relationships, role/status |
| Basic field and form validators | E | P1 | Valid/invalid with first-error focus |
| Dirty/touched/submitting state | N | P1 | Observable form state and action disable |
| Validation modes | N | P1 | On blur/change/submit, configurable |
| Async/cross-field validation | P | P1 | Stale result rejection and unified error API |
| Nested forms/repeating groups | N | P2 | Stable child identity and paths |
| Field groups / fieldsets / section | N | P1 | Accessible legend and grouping |
| Conditional fields | P | P1 | Preserve/clear values explicitly |
| Custom widget mapping | P | P1 | Registration adapter and lifecycle for project-specific fields |
| Form wizard/stepper | N | P2 | Step validation, review and cancel |
| Reset/undo/changed-field controls | P | P2 | Clear model vs UI state distinction |
| Model adapters (Pydantic optional) | N | P2 | Optional integration, no mandatory model dependency |

## 6. Navigation, information architecture, selection

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Tabs | E | P1 | Controlled state, keyboard movement, keep-alive |
| Sidebar navigation, shell | E | P1 | Window scoped controller and responsive collapse |
| Breadcrumbs | N | P1 | Long project/file/settings navigation |
| Menu, dropdown and submenus | N | P1 | Core native where supported; in-window fallback |
| Context menu | N | P1 | Unified commands, native Core API where available |
| Menubar / toolbar | N | P1 | Window commands and platform adaptation |
| Command palette/search actions | N | P1 | Searchable command registry with keyboard navigation |
| Pagination | P | P2 | Reusable standalone pager + table integration |
| Accordion/collapsible section | N | P1 | Keyboard and animated/reduced motion |
| Tree navigation | N | P1 | Hierarchy, lazy expand, selection, drag optional |
| Stepper | N | P2 | Forms/workflow stages |
| Anchor/table of contents | N | P2 | Documentation views |
| Keyboard focus/roving model | P | P0 | Shared pattern for tabs, lists, menu, tree and grids |
| Multiwindow history/navigation | N | P2 | Optional controller, not required URL router |

## 7. Overlays, feedback and notifications

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Dialog and confirm | E | P1 | Native DOM focus/escape semantics and scope |
| Modal manager / stacking | P | P1 | Owner/focus/scroll/return-to-trigger across overlays |
| Toast and alerts | E | P1 | Timed, persistent, action, accessible announcement |
| Drawer/offcanvas overlay | N | P1 | Responsive panel from left/right/bottom |
| Tooltip | N | P1 | Keyboard, touch, delay and dismissal |
| Popover/flyout/hovercard | N | P1 | Core popover API, geometry and collision fallback |
| Inline loading/error/empty | E | P1 | Retry, skeleton content and error patterns |
| Skeleton | N | P2 | Reduced-motion aware |
| Progress bar/spinner | E | P1 | Determinate/indeterminate and ARIA semantics |
| Progress ring/multistep progress | N | P2 | Optional SVG primitives |
| Loading overlay | N | P2 | Block input and show task state |
| Disclosure/announcement/banner | N | P2 | Dismiss and persistence options |
| Tour/onboarding coach marks | N | P3 | Optional; costly focus and placement policy |

## 8. Data components / large collections

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Basic table search/sort/page/select | E | P1 | Preserve current simple local API |
| Data-source adapter | N | P1 | Local/async backend, server-independent, cancel stale request |
| Selection model | P | P1 | Stable keys, multi select, keyboard, observable state |
| Table filtering and custom cell renderers | P | P1 | Column configuration, filter model |
| Inline cell/row editing | N | P2 | Commit/cancel, validation and focus retention |
| Row actions/context menu | N | P1 | Commands and keyboard access |
| Column visibility/reorder/resize | N | P2 | Persisted view preferences |
| Data grid/grouping/aggregation | N | P2 | Model/view architecture, not individual ad hoc controls |
| Table/tree lazy loading | N | P1 | Reusable data-source protocol |
| Virtual rows | N | P2 | Only if native profiling proves necessary |
| List view / selectable list | N | P1 | Cards/rows backed by one selection model |
| Tree view / tree grid | N | P1/P2 | Expansion/selection, tree grid specialized later |
| Log stream / chat stream | E | P1 | Existing bounded, controlled scroll; owner-safe tasks |
| Timeline / activity feed | N | P2 | Generic events, labels, grouping |
| Transfer list / dual listbox | N | P2 | Multi-item selection and move |

## 9. Desktop integration and app conveniences

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| File open/save/folder dialog | E | P1 | Async Core wrappers, honest capability/errors |
| Clipboard text | E | P1 | Existing; extend HTML/read rich clipboard |
| System notifications | E | P1 | Existing, platform-specific result surfaced |
| Background tasks/timers | E | P0 | Extend owner-safe cancellation/late completion |
| Multiple windows | E | P1 | Window-local navigation, theme, overlay, commands |
| Native menus/context menu | N | P1 | Core wrappers with in-app fallback as necessary |
| Tray icon and actions | N | P2 | Core wrapper/capability check |
| Global hotkeys | N | P2 | Core wrapper/capability check |
| File drag-and-drop | N | P1 | Core events; Wayland file-drop limit documented |
| OS clipboard HTML | N | P2 | Core rich clipboard wrapper |
| PDF export and print | N | P1 | Core 1.0 API, no UI PDF engine |
| Window sizing/state helpers | P | P1 | Core window actions, honest unsupported results |
| OS color mode/reduced motion | P | P1 | System preference, theme, motion policy |
| Icon/app asset packaging | P | P1 | Local resource manifest and deploy-safe paths |
| Recent-file/open-files / single instance | N | P2 | Core claim-instance API plus opt-in UI help |
| Drag reorder | N | P2 | Core pointer / DnD; keyboard alternative |
| Persist local view settings | N | P2 | Optional backend, no system-wide storage requirement |

## 10. Accessibility, internationalization, performance and quality

| Feature | Today | Priority | Design / desired behavior |
|---|---|---|---|
| Semantic roles/names/label links | P | P0 | Every interactive control accessible |
| Consistent focus management | P | P0 | Trap/return, keyboard, disabled, inert, popup focus |
| Keyboard patterns for composite controls | P | P1 | WAI-ARIA APG patterns, real device journeys |
| High contrast, large text, reduced motion | P | P1 | Theme CSS and native environment |
| Accessibility tree verification | P | P1 | Core AccessKit + AT-SPI/UIA end-to-end |
| Localization of built-in strings | N | P2 | Dict/gettext adapter optional; RTL |
| Unicode and IME | E/P | P0 | Maintain native Core behavior throughout reactive updates |
| Error reporting/context traces | P | P1 | Errors link to component/action without crashing app |
| Feature/capability discovery | P | P1 | Support checks and platform degradation |
| Visual regression gallery | N | P1 | Same reference UI in each theme/OS/density |
| Headless + installed consumer tests | E | P1 | Extend to full component matrix and core compatibility |
| Performance budgets and profiling | P | P2 | Measure big tables/menus/interactive typing, not guesses |
| Cross-language shared conformance | P | P0 | Python/PowerShell semantics and examples match |
| Offline documentation / component gallery | N | P1 | Searchable examples, props, events, screenshots, Core escapes |

## Feature completeness target

**Baseline (P0 + P1)**: All commonly used Bootstrap-style components plus mature desktop shell, forms, overlays, navigation, keyboard accessibility, responsive styling and real Core escape hatches. No mandatory special-service dependencies.

**Extended (P2)**: Mantine/Qt-style data-view, theme density, sophisticated forms, complex selection, printing, optional SVG charts, extensive app usability helpers.

**Optional (P3)**: media, terminal emulator, code editor, maps, complex multi-layer charts, plugin marketplace and application-specific controls. These require separate research/possibly more Core support and should not block the standard framework.

A component is not complete merely because it renders a screenshot: it must pass public API, CSS override, state identity, keyboard/accessibility, error, responsiveness, both bindings, and native-platform gates.
