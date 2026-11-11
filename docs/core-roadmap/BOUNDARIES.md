# Exactly what does NOT go into Core

- **UI library:** declarative/component API, reactive values, in-app dialogs/tooltips/toasts/command palettes, themes and tokens, tables/virtual lists/tree widgets, generated forms, localization of labels and validation messages, UI navigation, code highlighting/Markdown components.
- **Application:** file manager logic, databases and app persistence, ACP/MCP/LLM agents, networking/HTTP client, file browser model, auth, domain entities, settings migrations.
- **Specialized extensions:** terminal emulator/PTY, full multi-language code editor, WYSIWYG toolbar/editor product, charts/plotting/maps/3D, audio/video players, full document/PDF viewer and plugin manager. An inline static SVG rendering primitive belongs in Core; a visual chart *component* does not.
- **Browser platform:** JavaScript execution, remote URL loader, service workers, page navigation/history, CSSOM for scripts, custom-element Shadow DOM browser model, WebGL/WebRTC/browser extensions. These are deliberately unsupported by the native desktop Core.

The original 224-feature source lists 47 UI library, 12 application, 10 extension, 17 delivery/QA and 138 Core features. The 138 Core features are reconciled in the machine catalogue, even if already supported or only internally implemented. Some QA records belong to milestone process, not the runtime engine.
