# UI4ME architectural charter

## What is being built

Core is a **native window host + HTML/CSS document and rendering engine + event/OS bridge**. Native logic is implemented in Rust and exposed through one stable C ABI to Python and PowerShell. A developer who installs only `ui4me` can write raw HTML/CSS, open a native window, receive events, update the DOM and interact with supported OS services. There is no required server, JavaScript engine, component framework, application storage or routing.

A separate optional `ui4me-ui` distribution provides declarative components and convenient Python bindings; a similarly optional PowerShell module (`Ui4me.UI`, name provisional) mirrors the same behavior where practical. These call public Core APIs. Core never imports or loads them implicitly. Both distributions version independently.

## The four ownership classes

| Class | Owns | Excludes |
| --- | --- | --- |
| **Core/Renderer** | HTML tree and attribute semantics, CSS profile/cascade, text, layout, painting, hit testing, text selection, input defaults, DOM and event commands | Application state, templates, routing, network protocols, Markdown conversion, custom business controls |
| **Core/Native Host** | Windows and lifecycle, event-loop ownership, DPI and desktop input, OS clipboard, file dialogs, monitor capabilities, native events, safe owner-post/timers, platform errors | File-management workflows, credential storage, HTTP fetch, background job policy |
| **UI4ME UI (optional)** | Component rendering, layout helpers, reactive properties, theme tokens, Markdown/syntax highlighting, tabs/menus/dialog *compositions*, toast, chat/log views, keyed updates, accessibility patterns | Rust renderer internals, privileged OS APIs not exposed by Core, mandatory runtime dependencies, app-specific protocols |
| **Applications / extensions** | ACP/SSE, model providers, databases, workflows, authorization, business validation, telemetry consent, app settings, and independently packaged terminal/editor/chart/media engines | Changes to Core merely to embed a proprietary protocol or app feature |

The **UI library** may wrap native dialogs but cannot implement the underlying native picker. It can wrap `<select>` with search and chips, but baseline HTML `<select>` remains a renderer problem. It can display a permission dialog but must not decide whether a tool command is safe. It may coalesce a stream for display but must not own the SSE or ACP transport.

## Feature assignment decision test

Apply tests in order:

1. **HTML/CSS default-action test:** If a raw standard element or CSS property should work identically in an app that imports no optional package, it belongs in Core/Renderer. Support remains subset-scoped and conformance-gated.
2. **OS capability test:** If it calls native APIs or needs compositor-/session-specific capability negotiation, it belongs in Core/Native Host (or a narrowly versioned Core-native optional adapter when rare), never in pure markup convenience.
3. **Composition test:** If it can be built from existing markup, CSS, events, geometry and Core mutations without privileged access, it belongs in optional UI4ME UI.
4. **Domain policy test:** If it chooses app behavior, stores domain data, accesses a network endpoint, manages credentials, interprets agent messages, or decides business permissions, it is application-owned.
5. **Special engine test:** If it needs a separate editor, PTY, media, map or 3D backend, create a separately installable extension after a measured consumer proves demand.
6. **No unnecessary abstraction test:** If a feature is only cosmetic and duplicable with 8 lines of CSS, do not create a new Core API.

For disputed features, create an ADR with a Core-only usage example and a boundary test before coding.

## Explicit invariants

- The **raw Core** consumer remains viable on supported Linux/Windows with only the relevant `ui4me` distribution installed.
- One canonical mutable DOM/control state per document. UI library state is a view model, not a second authoritative copy of input values.
- Styles, layout, paint and hit geometry must agree on committed revisions; stale IDs or late resources cannot act on newly recreated nodes.
- Foreign callbacks run outside locks and mutable render borrows. No C exception unwinds across ABI. Current source uses owner-thread confinement; do not silently relax it.
- Background work can be written in Python/PowerShell using normal language libraries. Core provides safe bounded owner dispatch, not an opinionated job scheduler.
- No embedded JavaScript, browser DOM, Node/npm runtime, FastAPI server, WebSocket bridge, or general HTTP fetcher in Core.
- Browser-grade compatibility is **not** implied by parsing HTML or retaining old donor algorithms. Document supported subset by feature ID, platform and evidence.
- Core and UI library cannot depend on each other cyclically. `ui4me-ui` may depend on a minimum Core version; Core can neither import it nor require its assets.
- OS capabilities are fallible. Wayland window placement/global shortcuts and background dialogs must report support limitations rather than pretend to succeed.
- Application logic is never inferred from a UI component type. A button raises an event; the application decides the command.
- Python and PowerShell should expose the same *semantics* even where surface syntax differs. Native ABI is the single protocol authority.
- The UI library can expose abstract syntax conveniences but must compile to public Core mutations, not a privileged hidden native API.

## Architecture without premature crate explosion

Proposed internal bounded responsibilities: document/identity; style/text/layout/paint pipeline; input and event defaults; native platform/window; resource/caches; C ABI; thin language bindings. Existing crates need not be renamed to fit a diagram. Refactor only when a boundary causes duplicate state, unsafe lifetime coupling, slow builds or demonstrable maintenance cost. Avoid new service brokers, external runtime processes, object RPC, multi-tenant database packages or plugin registries in the default distribution.

When a Core requirement needs sophisticated internal code (bidi shaping, CSS grid, AT-SPI), it is still Core by semantics. **Minimal public responsibilities are not the same as trivial internal implementation.** Conversely, 100 UI widgets can remain outside the Core even if their combined code is large.

## Examples resolving ambiguous placement

| Question | Correct owner | Reason |
| --- | --- | --- |
| `<select>` keyboard/option selection | Core renderer | Standard HTML control semantics |
| Searchable multiselect with chips | UI4ME UI | Composite widget, validation, menu/popup |
| Native open/save/folder chooser | Core native host | Requires OS API and capability reporting |
| File upload progress and transfer | Application + UI helper | File handling and network policy aren't rendering |
| `scrollIntoView` and read-only text selection | Core renderer | Generic document operations, not chat conveniences |
| Chat bubbles / token batching / Markdown | UI4ME UI | Presentation and transformation of app data |
| ACP tool approval UI | UI4ME UI for dialog; **application for approval decision** | Presentation and policy must be separate |
| OS notifications | Core platform opt-in | Native OS action |
| Toast/snackbar | UI4ME UI | An overlay composed from markup and a timer |
| Password field masking, IME, label association | Core renderer/input | Ordinary HTML behavior and accessibility |
| Password hashing, credential vault | Application | Security policy and storage |
| User account, RBAC, sessions | Application | Not a native UI feature |
| Code editor, terminal, interactive graph | Independent optional extension | Large specialized rendering/input/problem domain |

## Untrusted markup and security

Core excludes script execution but that is **not a universal sanitization guarantee**. Applications that display agent-generated Markdown/HTML must sanitize according to their trust policy, and UI4ME UI's Markdown helper should default to safe output. Core must enforce its declared asset roots and resource limits. External-link opening is an explicit policy handoff; do not auto-open arbitrary URLs from a click on untrusted content. Avoid introducing full HTTP rendering and plugin scripting into Core as an accidental consequence of a new element.

## Public ABI and API posture

Favor a compact set of typed commands and return values: load/read document; get/set attribute/value; append/insert/remove/replace; batch; query geometry/scroll/selection; event subscribe/unsubscribe/default cancellation; window lifecycle/state; native OS capability and file dialogs; error/provenance. Bound operations by size and count. Keep old 0.1/0.2 behavior compatible where possible; breaking shifts require a documented version/adapter and upgrade evidence. IDs are opaque, scope-bound and generation-checked. No direct raw pointer access to DOM or renderer in public Python/PowerShell.

## What success looks like

A stranger can build: (1) raw HTML/CSS file manager or configuration utility, (2) independent native OS app, and (3) optional component-driven agent chat. None must modify Rust to add app-specific logic; each must work from an installed package in a clean environment and have truthful desktop acceptance evidence.
