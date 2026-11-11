# Research sources and provenance

**Research checked:** 2026-11-11. External documents and projects change. These are official/primary source links wherever possible, and are used to support *comparative architecture decisions*, not to assert every feature is implemented/qualifies in UI4ME.

## UI4ME-specific sources

1. [UI4ME current repository](https://github.com/ui4me/ui4me/tree/cbb8a5efa50505e262b1747c55e38be5838e6b8d) — pinned inspection baseline.
2. [UI4ME `docs/PROJECT_STATUS.md`](https://github.com/ui4me/ui4me/blob/cbb8a5efa50505e262b1747c55e38be5838e6b8d/docs/PROJECT_STATUS.md) — current supported core feature and verification boundary.
3. [UI4ME C ABI protocol](https://github.com/ui4me/ui4me/blob/cbb8a5efa50505e262b1747c55e38be5838e6b8d/crates/ui4me-core/src/protocol.rs) — public command set; note missing public append/scroll/OS facade operations.
4. [UI4ME Python API](https://github.com/ui4me/ui4me/blob/cbb8a5efa50505e262b1747c55e38be5838e6b8d/bindings/python/src/ui4me/app.py) — current App/Window façade.
5. **User-supplied original:** `bigbatmanorg-ui4me-old.zip` (SHA-256 `5008aae9c8e3f460938667589c0a358b97e2f23558854925257a923925accdbc`), whose `PRODUCT_STATUS.md` records `0.5.0-rc.1` unqualified rendering evidence and whose owned source is indexed in `data/old-source-references.csv`.
6. **User-supplied advisory migration plan:** `ui4me-migration-plan-d0fb3df(1).zip` (SHA-256 in `data/catalog-summary.json`); not followed as a mandatory implementation plan.

## Toolkit/framework primary references

| Framework | Source | What it supports |
| --- | --- | --- |
| NiceGUI | [official docs](https://nicegui.io/documentation), [repository](https://github.com/zauberzeug/nicegui), [fundamentals](https://nicegui.io/documentation/section_foundations) | Backend-first Python, browser/UI components, reactive data binding, native-webview mode, component/API map |
| NiceGUI actual components | [UI namespace](https://github.com/zauberzeug/nicegui/blob/d63120457588a778c5a98b209fe39c57adbdbe4b/nicegui/ui.py) | Broad list of chat/log/markdown, controls, tables, trees, chart, code editor/terminal |
| NiceGUI binding | [binding.py](https://github.com/zauberzeug/nicegui/blob/main/nicegui/binding.py) | Push-style and active-link refresh strategies |
| NiceGUI chat/Markdown/log | [chat](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/chat_message.py), [markdown](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/markdown.py), [log](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/log.py) | Components that can be replicated as optional presentation helpers |
| Textual | [Worker guide](https://textual.textualize.io/guide/workers/), [docs](https://textual.textualize.io/) | Worker's lifecycle, cancellation, UI thread handoff, widget/task ownership |
| Flet | [Window API](https://flet.dev/docs/types/window/), [async apps](https://flet.dev/docs/cookbook/async-apps/) | Native window abstraction and event-loop guidance |
| Toga | [Main documentation](https://toga.beeware.org/en/stable/), [dialogs](https://toga.beeware.org/en/stable/reference/api/application/dialogs/) | Platform-neutral native dialog APIs and platform-specific differences |
| Reflex | [Introduction](https://reflex.dev/docs/getting-started/introduction/), [state](https://reflex.dev/docs/library/state/) | State/events/components example of application framework coupling |
| pywebview | [Usage](https://pywebview.flowrl.com/guide/usage) | Window object/events, browser JS bridge, local HTTP behavior to avoid copying |
| Tauri 2 | [Plugin features](https://tauri.app/plugin/), [Capabilities](https://tauri.app/security/capabilities/), [Plugin design](https://tauri.app/develop/plugins/) | Narrow OS plugins and explicit permission/capability model |
| Qt for Python | [Overview](https://www.qt.io/development/qt-framework/python-bindings), [QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html) | Mature native UI and geometry/ownership reference |
| Slint | [Architecture](https://github.com/slint-ui/slint), [Python binding](https://github.com/slint-ui/slint/blob/master/api/python/slint/README.md) | Optional declarative property and component model |
| Dear PyGui | [Overview](https://dearpygui.readthedocs.io/en/latest/about/what-why.html) | GPU-first developer UI, diagnostics and widgets as a distinct product model |

## Standards and testing references

- [W3C WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/practices/) — keyboard navigation and accessible names/roles/states.
- [WAI-ARIA dialog modal pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) — focus trapping, Escape and inert background.
- [WAI-ARIA keyboard practices](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/) — custom component keyboard support.
- [Web Platform Tests overview](https://wpt-docs.readthedocs.io/en/latest/introduction.html) — scoped cross-browser tests; do not treat total WPT count as a UI4ME acceptance criterion.
- [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk) — an **application-owned protocol**, not Core dependency.
- [ACP transport specification](https://agentclientprotocol.com/protocol/transports) — JSON-RPC stdio; remote transports optional/app-owned.
- [HTTPX asynchronous streaming docs](https://www.python-httpx.org/async/) — application-owned SSE/HTTP streams in Python.

## Method and confidence

- Repo-level feature lists were corroborated with public primary documents or source files where available.
- The 224-feature inventory is an **architectural taxonomy and planning hypothesis**, not a benchmark nor proof that NiceGUI or UI4ME supports every behavior listed.
- Old-code references were verified by script against the extracted bytes of the exact user-provided archive. Some are **file-level leads** and should be reviewed further; exact `line_start/line_end` and `match_text` are preserved.
- Current 0.2 classifications are based on source/docs review, **not** execution of a new UI4ME test suite. The old 0.5 implementation's qualification status is explicitly not transferred.
- W3C conformance requirements apply where the corresponding HTML behavior is claimed as supported; UI4ME need not implement every web platform standard to remain useful as a native toolkit.
