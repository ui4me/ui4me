# Primary-source research notes (checked 2026-11-12)

Official sources reviewed and key ideas transferred to UI4ME UI. These links support architectural comparisons but are not proof that UI4ME currently implements the referenced feature.

1. Bootstrap v5.3 documentation: https://getbootstrap.com/docs/5.3/getting-started/introduction/ — extensive components, forms, content, responsive layout and utility taxonomy. Target comparable *coverage* where sensible; do not port Bootstrap JS/browser runtime.
2. Bootstrap responsive utilities: https://getbootstrap.com/docs/5.3/layout/utilities/ — class-based breakpoints and spacing/alignment convenience. Adapt via Core CSS and small Python/PowerShell responsive prop helpers.
3. Bootstrap color modes: https://getbootstrap.com/docs/5.3/customize/color-modes/ — CSS tokens and per-component theme scoping. Emulate with `--u4-*` and `data-u4-theme` where Core supports it.
4. Mantine component catalogue: https://mantine.dev/core/accordion/ — broad categories for inputs, combobox, navigation, feedback, overlays, data, charts and layout. Use as a completeness checklist, not an obligation to implement every specialty component.
5. Mantine CSS variables: https://mantine.dev/styles/css-variables/ — typography/color/spacing/elevation/overlay token hierarchy, global and local overrides.
6. Mantine package overview: https://mantine.dev/getting-started/ — core components plus modular separate dates/charts/notifications/spotlight extensions; useful for separating default components from optional heavyweight extras.
7. NiceGUI docs: https://nicegui.io/documentation — concise Python-first component construction, state binding, container composition, native-mode caveat. UI4ME differs by not requiring an HTTP server or browser runtime.
8. NiceGUI styling: https://nicegui.io/documentation/section_styling_appearance — simple per-element class/props/style override model; borrowed customization ladder, but with native Core and original CSS.
9. Qt model/view: https://doc.qt.io/qt-6/model-view-programming.html — separation of data model, selection and presentation; apply to tables/list/tree rather than coupling to SQL or OS model APIs.
10. Qt style sheets: https://doc.qt.io/qt-6/stylesheet-reference.html — stable component subcontrols/states; UI4ME instead offers HTML/CSS tokens/parts.
11. Flet responsive row: https://flet.dev/docs/controls/responsiverow/ — intuitive breakpoint-to-grid-span mappings for Python API; implement using Core CSS.
12. Radix primitives: https://www.radix-ui.com/primitives — accessible, unstyled, composable overlay/menu/input primitives, explicit keyboard/focus behavior.
13. Radix composition: https://www.radix-ui.com/primitives/docs/guides/composition — granular part composition and user-supplied event/ref forwarding; adapt concept to Python/PowerShell component slots and raw Core refs, not React cloning.
14. WAI-ARIA combobox: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/ — keyboard/focus semantics for list popup and editable combobox; use as component test oracle together with real AT clients.
15. MUI X data-source model: https://mui.com/x/react-data-grid/server-side-data/ — data loading abstraction encapsulating pagination/sort/filter/cancel/cache. UI4ME interface should work equally with local files/databases or optional network services.
16. Python packaging dependencies: https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/ — package dependencies resolve on install without source merger.
17. PowerShell PSResourceGet: https://learn.microsoft.com/powershell/module/microsoft.powershell.psresourceget/install-psresource — default dependency-aware install and skip-dependency option.

## Research synthesis
- Bootstrap offers a **component coverage** and responsive utility checklist.
- Mantine offers **full featured components**, theme tokens and optional modular feature packages.
- Radix offers **quality of interaction**: keyboard, focus, accessible structure and stable composition internals.
- NiceGUI offers **developer speed**: a few lines that create a working app, with CSS escape hatches.
- Qt offers **desktop breadth and model/view**: tree, tables, menus, selection and window patterns.
- Flet offers a readable cross-language-style **responsive property model**.
- MUI X shows why a **generic data source** is better than manual table pagination plumbing.

Avoid adopting mandatory React/Vue/Flutter/Qt/Bootstrap-JS/web process dependencies. The point is to reproduce ergonomic outcomes on UI4ME Core, not ports of unrelated engines.
