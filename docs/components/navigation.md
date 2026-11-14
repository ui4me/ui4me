# Navigation, menus and composite controls

**Python:** `ui.tabs`, `ui.navigation`, `ui.breadcrumbs`, `ui.accordion`, `ui.disclosure`, `ui.menu`, `ui.command_palette`, `ui.drawer`, `ui.tree`, `ui.segmented`. App-scoped `app.commands` supports in-window shortcuts. Prefer per-window navigation state.

**PowerShell:** `New-UI4METabs`, `New-UI4MEAccordion`, `New-UI4MEBreadcrumbs`, `New-UI4MESegmented`, shell/sidebar/content layout helpers. Other widgets are still available through composing Core DOM and existing handlers; do not assume all Python menus/command registries have PowerShell equivalents.

Every interactive control needs an accessible name and keyboard behavior. Test Tab, ArrowUp/Down, Home/End, Enter, Space and Escape as applicable. Close overlays with focus restoration. Native OS menu bars are **not** provided by UI4ME Core 1.x; available menus live inside the window. Browser JavaScript is neither bundled nor supported.
