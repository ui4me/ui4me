# Bootstrap → UI4ME UI parity checklist (conceptual, not API compatibility)

UI4ME UI does **not** aim to run Bootstrap's browser JavaScript or blindly support arbitrary Bootstrap CSS. Target is one-to-one *user-facing capabilities* where relevant, using original UI4ME components and CSS. Status based on public 0.4 UI names, not runtime test execution.

| Bootstrap v5.3 component | UI4ME UI status | Target |
|---|---|---|
| Accordion | New | P1 |
| Alert | Existing | Improve ARIA variants |
| Badge | Existing | Theme parts |
| Breadcrumb | New | P1 |
| Buttons | Existing | Common props and icon anatomy |
| Button group | New | P1 |
| Card | Existing | Theme parts |
| Carousel | New | P3; not essential desktop control |
| Close button | New | P1 small convenience |
| Collapse | New | P1, reusable disclosure |
| Dropdown | New | P1, shared overlay and command model |
| List group | New | P1, keyboard/selectable variant |
| Modal | Existing | Overlay scope and complex focus improvements |
| Navbar | Partial | Shell/sidebar exist; add toolbar/navbar |
| Navs/tabs | Existing | Per-window controller and keyboard contracts |
| Offcanvas | New | P1 drawer/sidebar |
| Pagination | Partial | Table pager exists; standalone P2 |
| Placeholders | Partial | Empty/loading exist; skeleton P2 |
| Popover | New | P1, Core popover exists |
| Progress | Existing | Additional display variants P2 |
| Scrollspy | New | P3 docs-heavy helper |
| Spinners | Existing | Preserve reduced-motion |
| Toasts | Existing | Actions and AT improvement |
| Tooltips | New | P1 |

## Bootstrap form parity

| Category | UI4ME 0.4 | Target |
|---|---|---|
| Input, textarea, select, checkbox/radio, range | Existing | P1 harden controlled/binding semantics |
| Input group with prefix/suffix/button | New | P1 |
| Floating labels | New | P2 visual variant |
| Layout and grid forms | Partial | P1 form grid/field group |
| Validation and invalid feedback | Existing/partial | P0 ARIA descriptions, P1 dirty/touched/timing |
| Toggle/switch | Existing | Contract parity |

## Bootstrap layout/content/utility parity

- Containers, row/column/grid/gutters: existing fundamentals, add responsive 12-column span model and breakpoint-prop consistency.
- Typography, images, tables: basics exist, add list groups, link helpers, figure/caption, truncation, visually hidden/accessibility helpers.
- Spacing, sizing, width/height, positioning, overflow, flex, grid, border, color, shadow, visibility, responsive display: prioritize a compact stable class/token vocabulary; do not copy hundreds of class names and reimplement CSS.
- Icons: Bootstrap icons are optional separate pack; UI4ME should use neutral SVG icon API that can accept other icon packs and local user assets.
- Forms with validation and error feedback must be usable via keyboard and screen reader, not merely styled.

## Mantine & Qt extension coverage

Beyond Bootstrap, UI4ME UI should add: combobox/autocomplete/multiselect/tag input, date/time/color/path controls, tree, data grid/data source, resizable pane/dock layout, command palette, native menubar/context menus, optional SVG chart primitives, advanced forms, theme density, copy button, file drop, native notifications and tray.

Lower priority/extras: cascading select, mentions input, hue/angle sliders, rich charts, emoji picker, carousel, tour, full IDE code editor, terminal emulator, video/audio players, geospatial maps. These are not prerequisites for a compelling generic desktop component library.

## Distinguish CSS compatibility

Because UI4ME Core supports modern CSS, a user can write ordinary CSS for raw HTML and UI components. This does *not* mean Bootstrap's JavaScript-interactive widgets magically work. A future optional Bootstrap CSS compatibility stylesheet might be useful for raw HTML, but full Bootstrap behavioral compatibility would require reimplementing the interactive conventions in host language and is not a recommended foundational goal.
