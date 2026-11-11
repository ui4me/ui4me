# Toolkit research: transferable lessons vs architectural traps

**Research date: 2026-11-11.** This is a primary-source architecture and capability comparison, **not** a verified cross-framework performance benchmark or a promise of feature parity. NiceGUI was checked against its `main` commit `d63120457588a778c5a98b209fe39c57adbdbe4b`; UI4ME against `cbb8a5efa50505e262b1747c55e38be5838e6b8d`. See [`research/SOURCES.md`](research/SOURCES.md) for links. Names, optional dependencies and APIs may change after the snapshot.

## Synthesis

Competing frameworks solve several different products under the same label “GUI toolkit”:

- **Rendering engines** decide layout, text, painting, native input and hit testing.
- **Native hosts** integrate windows, OS dialogs/menus, clipboard, accessibility, monitors and lifecycle.
- **Component libraries** supply cards, lists, tabs, dialogs, data grids, common widgets and themes.
- **Application frameworks** supply reactive state, dependency injection, routing, background tasks, server sessions and persistence.
- **Domain apps** supply ACP/SSE/LLM logic, authorization, storage, workflows and product behavior.

UI4ME should deliberately cover the **first two** and a **small typed callback/mutation bridge**. Optional `ui4me-ui` covers most of the third and selected generic convenience from the fourth. The fifth is always external.

## Framework-level comparison

| Framework | Rendering/host model | Strongest useful feature | What not to copy into Core | Primary reference |
| --- | --- | --- | --- | --- |
| **NiceGUI** | Python backend → FastAPI / Socket.IO → Vue/Quasar/browser, native view via pywebview | Declarative component composability, reactive binding, async tasks, update outbox, chat/log/Markdown, easy documentation | Required web server, JS/Vue, Quasar runtime, multi-user storage/routing | [Docs](https://nicegui.io/documentation), [source](https://github.com/zauberzeug/nicegui), [foundations](https://nicegui.io/documentation/section_foundations) |
| **Textual** | Python-managed widget tree and event/message loop rendered primarily to terminal | Reactive property and message lifecycle, managed workers bound to widgets and cancellation | Make GUI Core decide Python app worker policy or require TUI-specific styling | [Workers](https://textual.textualize.io/guide/workers/), [docs](https://textual.textualize.io/) |
| **Flet** | Python app UI and events over Flutter rendering/runtime | Extensive desktop window facade, cross-platform property model, async handler support | Flutter engine, full widget runtime, app-wide state model | [Window](https://flet.dev/docs/types/window/), [async](https://flet.dev/docs/cookbook/async-apps/) |
| **Toga** | Common Python interface with platform-specific native widget backends | Honest platform capability matrix and asynchronous native dialogs | Core GUI widgets bound to native widget types rather than HTML/CSS | [Docs](https://toga.beeware.org/en/stable/), [dialogs](https://toga.beeware.org/en/stable/reference/api/application/dialogs/) |
| **Reflex** | Python state/events + declarative components → React frontend + web backend | Explicit state/derived state/events, components, validation of user-driven updates | Full-stack database/backend, React compilation, server app requirements | [Introduction](https://reflex.dev/docs/getting-started/introduction/), [state](https://reflex.dev/docs/library/state/) |
| **pywebview** | Python-native windows around system WebView; optional JS bridge and local HTTP serving | Clean window object, lifecycle events, show/hide/restore and dialog APIs | Browser engine and JS API; its local HTTP server is not a desirable Core dependency | [Usage](https://pywebview.flowrl.com/guide/usage) |
| **Tauri 2** | Rust native host, system WebView, explicit plugin/permission capabilities | Minimal Core/plugin split, capability boundaries, native integration separated from app state | Mandatory webview and frontend JS bindings, broad plugin system in UI4ME 0.3 | [Plugins](https://tauri.app/plugin/), [capabilities](https://tauri.app/security/capabilities/) |
| **Qt for Python** | Large, mature native widget/scene ecosystem through Python binding | OS-level window geometry, widgets, accessibility, lifetimes and comprehensive input semantics | Massive Qt/widget layer or different rendering model | [Qt for Python](https://www.qt.io/development/qt-framework/python-bindings), [QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html) |
| **Slint** | Declarative `.slint` language compiled/interpreted to native rendering; Rust/C++/Python | Clear separation of UI declaration, properties and host business logic; compiled component optimization | Mandatory new DSL or compiler for raw UI4ME adopters | [Architecture](https://github.com/slint-ui/slint), [Python](https://github.com/slint-ui/slint/blob/master/api/python/slint/README.md) |
| **Dear PyGui** | Python retained API over immediate/GPU draw backend | Highly dynamic inspector/admin UIs and developer tooling patterns | GPU renderer or 70 widgets in minimum Core | [What & Why](https://dearpygui.readthedocs.io/en/latest/about/what-why.html) |

## NiceGUI in more detail

NiceGUI is the best source for **optional UI ergonomics**, not the target Core architecture.

**What it does well:**

- `ui` exposes a broad declarative element and HTML surface; row, column, card, tabs, drawer, dialogs, data grids, logs, chat messages, markdown and code/terminal wrappers.
- **Reactive bindings** connect model values to elements. NiceGUI's binding code uses both push propagation on bindable properties and polling of ordinary Python values. In UI4ME UI, prefer explicit push by default and optionally opt-in observed-object polling; don't start a hidden 100ms scanning loop in Core.
- **Outbox batching** accumulates updates and sends them over a client socket. UI4ME has no socket; borrow the idea of *coalescing document mutations before style/layout invalidation*, not the transport.
- **Refreshable sections** recreate components when their dependencies change. For UI4ME, use keyed reconciliation where possible to preserve text selection, focus and scroll; don't treat rebuilding an entire subtree as equivalent to a small text patch.
- **Managed tasks and error handlers** keep background work associated with an application context. The optional UI package may own a task manager; Core should expose only safe thread dispatch and cancellation contracts.
- **Markdown, syntax highlighting, chat and log** demonstrate what can be built from primitives. Markdown remains an *application-side transformation* to sanitized HTML; code/log widgets can use raw engine mutations and scrolling.
- **Human-readable agent documentation** (`nicegui/llms.md`) makes the framework easier for coding assistants to use correctly. UI4ME should publish a concise current-version counterpart and raw-Core examples.

**What should not be imported:** Vue, Quasar, Socket.IO, FastAPI/ASGI server, browser-only `run_javascript`, multi-user cookie/session storage, generic backend routes or a mandatory React-like component tree.

**Dependency nuance:** NiceGUI Markdown and syntax highlighting are Python conversion/rendering helpers, while its CodeMirror and xterm components depend on browser JavaScript packages. UI4ME can reproduce Markdown and static highlighting without JS, but a full native code editor and terminal emulator require independent engineering or optional integrations—not a direct code port.

Primary NiceGUI source anchors: [`nicegui/ui.py`](https://github.com/zauberzeug/nicegui/blob/d63120457588a778c5a98b209fe39c57adbdbe4b/nicegui/ui.py), [`nicegui/binding.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/binding.py), [`nicegui/elements/markdown.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/markdown.py), [`nicegui/elements/chat_message.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/chat_message.py), [`nicegui/elements/log.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/log.py), [`nicegui/elements/scroll_area.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/scroll_area.py), [`nicegui/native/native_mode.py`](https://github.com/zauberzeug/nicegui/blob/main/nicegui/native/native_mode.py).

## Lessons from the others

**Textual:** workers have pending/running/cancelled/error/success lifecycle and are associated with their widget/screen/app; thread work marshals changes back to UI. Borrow **observable task ownership and deterministic cancellation** for optional helpers. Do not make Python-specific job policy the only Core concurrency API. Keep Core thread-safe `post()` and `stop()`.

**Flet:** exposing platform-neutral window properties is highly useful. Emulate the **capability-reporting interface**, not its full Flutter property/widget ecosystem. `window.minimize()` can be a Core call even if `ui.window_controls()` is a convenience component. Non-supported operations on Wayland must return a clear status rather than claim universal behavior.

**Toga:** opening a file or folder should return a path or cancellation *and* leave UI responsive. This belongs to Core/OS. `file_attachment()` with thumbnails and uploads belongs to UI plus app. Toga's documented platform variation is worth copying as honesty, not as arbitrary limitation.

**Reflex:** use derived values and explicit events as an **optional** declarative mode. The Core shouldn't acquire a mandatory state class, web compiler or database just because a framework does.

**Tauri:** plugin/capability declarations help once there are OS features with different trust levels; do not implement a generic plugin host early. Maintain a small allowlist of native privileged actions and resource roots. Native services remain discoverable and fallible.

**Qt/Slint:** component composition can be elegant with a compiled tree, but UI4ME explicitly promises raw HTML/CSS control. A UI library DSL must be optional and generate normal document mutations; no new markup language required.

**Dear PyGui:** specialized data visualization and developer tools are valuable examples, but the GPU-first approach would distract from text accuracy and OS integration. Optimize only measured long-session workloads.

## Risk comparison by architecture

| Design temptation | Immediate benefit | Long-term cost | Decision |
| --- | --- | --- | --- |
| Put every NiceGUI component in Core | Easy demo parity | Huge public API, difficult independent releases | **Reject** |
| Add Node/npm/JS for interactivity | Existing browser component ecosystem | Breaks native HTML/CSS/no-JS promise | **Reject by default** |
| Add FastAPI local server for reactive updates | Simple Python async | Transport, security and lifecycle burden | **Reject for Core** |
| Expose entire old donor DOM API immediately | Lots of apparent functionality | ABI explosion and unqualified behavior | **Reject**; add small generic primitives |
| Hide all runtime behavior behind optional components | Convenience | Raw HTML/CSS users become second-class | **Reject** |
| Use static HTML-only updates | Easy implementation | Poor streaming and lists, loss of focus/scroll | **Reject after 0.2** |
| Implement a custom renderer from scratch again | Maximum control | Repeats years of layout/text bugs | **Reject** unless measured defect justifies focused rewrite |
| Keep old code without checking ownership | Faster initial port | FFI lifetimes, cache bugs and native regression | **Reject**; source is a donor, not an authority |
| Separate Core/UI/app ownership, incremental release | Some API design overhead | Requires discipline rather than rework | **Adopt** |

## Prioritization conclusion

The frameworks show **two distinct must-haves**: (a) generic HTML/CSS/OS interaction primitive completeness, (b) optional developer ergonomics. **Version 0.3 should prioritize (a) and prove a streaming application can be built with only the Core.** Start optional UI components once those primitives are stable, and version UI separately. Full code editing, terminal and charting are specialized extensions, not milestones blocking 0.3.
