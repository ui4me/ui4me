# Core integration and security

- UI4ME 2.1 depends on `ui4me-core>=1.0.1,<2` and calls `Application.start()` automatically. Do not start a second host or modify `UI4ME_ENDPOINT`/`UI4ME_TOKEN`. The native host owns window paint, editing, accessibility and lifecycle.
- Direct script startup reexecutes the script: imports and statements above `ui.app(...)` may run twice. Put I/O side effects after bootstrap.
- Core's public `on_window_event` is the only supported observer of window events; do not replace `Application._window_event`, `RpcClient._notifications`, or private handlers.
- Raw `from ui4me import Application, Window, Document` are identity aliases to Core. `component.core_document`, `window.core.native` expose actual objects. Do not remove/reparent managed nodes with raw Core APIs; use `ui.html` for explicit trusted HTML islands.
- Use `ui.text` for untrusted strings. `ui.html` requires **trusted** HTML, `ui.css` trusted CSS. Avoid `onclick`, `<script>`, HTTP URLs in resource loading, or remote fonts.
- Core 1.x may not support OS tray, native menus/hotkeys/notifications, print/PDF, rich clipboard, media, `input type=date|time|color`. UI's calendar/time/color controls are native in-window composites. Capability-check before promising native services.
- Linux Wayland focus/placement and clipboard may be compositor controlled; Windows features need real Windows testing.
- Do not claim complete WAI-ARIA compliance unless keyboard, focus, UIA/AT-SPI and screen-reader checks pass.
