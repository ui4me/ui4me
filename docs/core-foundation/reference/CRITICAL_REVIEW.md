# Critical review, brainstorming and hard tradeoffs

This document is intentionally adversarial. A feature is not justified by competitor presence, source-code existence or a screenshot. Every capability should have an owner, user-value hypothesis, dependency, failure model, acceptance test and release gate.

## Eleven pitfalls most likely to derail the project

1. **Turning Core into a second NiceGUI.** A chart widget, reactive store and route manager feel useful but are developer conveniences. Preserve a tiny external API and move wrappers out.
2. **Claiming full HTML/CSS compatibility.** The old 0.5.0-rc.1 donor has real rendering code but seven official Linux and seven provisional Windows pixel comparisons still failing at its stop checkpoint. Do not turn crate breadth or WPT test count into a support claim.
3. **Confusing source code with a shipped feature.** Files can contain stubs, experiments, incomplete platform hooks or intentionally disabled algorithms. Provenance anchors indicate source to inspect, not acceptance.
4. **Native owner/thread reuse bugs.** Winit process owner, Python main thread and PowerShell runspace semantics must survive high-frequency event callbacks, close/reopen and callback errors.
5. **Duplicated UI state.** A reactive library should never overwrite canonical input values, caret or selection just because a model object was polled. Updates must preserve identity where possible.
6. **Unbounded streaming.** One token → one DOM rewrite is wasteful. Batch with explicit backpressure while allowing cancellation and preserving scroll anchoring. No hardcoded fixed-size 16 KiB text restriction for legitimate long responses without a better bounded alternative.
7. **Gaps in generic DOM mutation.** Whole-subtree replace is not an acceptable long-term substitute for append/remove/move/query. It destroys focus and may invalidate event targets in unrelated components.
8. **Accessibility deferred indefinitely.** Raw HTML controls need keyboard focus semantics and exposed roles/names/states in Core; optional component widgets must maintain these patterns. Testing CSS appearance alone is insufficient.
9. **Misplaced OS features.** A file picker or system clipboard is native Core service; an upload workflow, file explorer or user settings window is not. Wayland/Windows feature differences must be explicit.
10. **Premature plugin/platform breadth.** A general extension registry, GPU renderer, server, media engine, multithreading rewrite or mobile port is not needed to prove Core 0.3 value.
11. **Untrusted markup.** No-JavaScript is not equivalent to safe HTML. Markdown from LLMs should default to sanitization in the optional package; assets/network and external links need explicit policy.

## High-value 0.3 slices: alternative designs and decisions

### DOM mutation: command API vs public Node tree

- **Option A:** expose every document node and iterator as a Python object; powerful but complex lifetimes/staleness and large ABI.
- **Option B:** ID/selector-based generic commands (`append_html`, `insert_before`, `remove`, `query`, `get_attribute`, `batch`) with opaque stable node handles internally.
- **Option C:** only replace-subtree; minimal API but expensive and state-destructive.
- **Preferred:** B for 0.3. Keep A possible as a future optional ergonomic adapter. Preserve generation-based identity and no partial commit.

### Scroll: library simulation vs Core geometry

- **Option A:** component guesses scroll from CSS/class or DOM rebuilding.
- **Option B:** Core exposes clamped scroll offsets, scrollport/query geometry and target reveal.
- **Preferred:** B. Focus/selection/scrollbar must all use the renderer's actual scroll state. Library autoscroll only composes these primitives.

### Streaming text: append chunks vs full replacement

- **Option A:** every token calls `set_text` with all accumulated output.
- **Option B:** append text through bounded chunks, batch frame updates, preserve text selection and scroll anchor.
- **Preferred:** B, with a budget/overflow protocol. Test stream cancellation at arbitrary chunk boundaries, Unicode split boundaries and expensive layout reflows.

### Reactive state: polling vs push-only

- **Option A:** continuous background polling of all arbitrary Python dictionaries (NiceGUI can do this for non-bindable objects).
- **Option B:** observable values/events push updates; optional explicit `poll` adapter for legacy objects.
- **Preferred:** B. No hidden polling, globally owned state or enforced state class in Core. UI library may expose both with clear costs.

### Dialog: OS modal vs HTML modal vs component modal

These are **three different things**:

- Native OS file/message picker: Core/Host service, platform capability.
- HTML `<dialog>` top layer, inertness, focus/escape: Core/Renderer input semantics.
- `ui.dialog(...)` form/approval convenience: Optional UI package that composes either Core HTML dialog or native service.

Do not accept a fake semi-modal overlay with no keyboard trapping as a passing dialog.

### Accessibility support levels

1. **Semantic model** in DOM with names/roles/checked state (source present in donor).
2. **Platform bridge** to AT-SPI/UIA with actions/updates (donor has code; not proof of qualified product).
3. **Automated integration checks** verifying exposed tree/states.
4. **Actual assistive-technology run** (screen reader and keyboard), a distinct evidence category.

Only claim the level actually tested. A `role=dialog` attribute alone does not make a component accessible.

### Extensions and browser-like features

A code editor, terminal and graph visualization deserve research because they may need generic input/selection/drawing primitives. Their specialized logic should remain optional. One component prototype must establish which *generic* missing primitive is actually needed; avoid creating a GPU/plugin substrate for hypothetical future apps.

## Release risks register

| Risk | Probability | Impact | Mitigation / owner |
| --- | --- | --- | --- |
| New 0.3 API breaks 0.2 callbacks | High | High | Semantics/ABI tests; explicit compatibility adapter; Core owner |
| Old donor algorithm is incomplete/stub | High | Medium–High | Trace to exact line, inspect tests and status; implementation owner |
| Stale resource/event resurrects deleted element | Medium | High | Generational handles and async retirement regressions; Core DOM owner |
| High-frequency streaming floods UI queue | High | High | Bounded batching, backpressure, cancellation; Core + UI helper |
| Text selection incorrect in bidi/code spans | Medium | High | Static text geometry and real desktop clipboard tests; Core text owner |
| Cross-OS platform differences | High | Medium | Capability APIs, Wayland/KDE and Windows native acceptance; Host owner |
| Widget layer introduces hidden global state | Medium | High | Per-component/app ownership; no implicit persistence; UI owner |
| Accessibility missing in UI widgets | High | High | WAI-ARIA APG patterns and AT-SPI/UIA tests; Core/UI owners |
| Artifact/version mismatch on public publication | Medium | High | Same-source release manifest, installed upgrade tests; Delivery owner |
| Dependency size expands to browser-like stack | Medium | High | Core dependency audit each release; architecture review |
| Performance optimization destabilizes correctness | Medium | High | Compare before/after same fixture/build; selected pixel/geometry oracle |
| Too many roadmap items land in one release | High | High | Milestone scope lock, stretch items removed on first failure |

## Candidate benchmark scenarios (proposed; thresholds decided from baseline)

- Open ordinary forms on real KDE/Windows; first paint and control interaction latency.
- Resize at fractional scale while editing and scrolling; input latency and layout consistency.
- 100, 1,000 and 10,000 message/item datasets; measure DOM live nodes, repaint cost, select/copy behavior and memory over time.
- Token-like streaming at multiple rates: 10, 100 and 1,000 chunks/sec incoming; UI may coalesce at a reasonable display rate, preserve exact output and settle cancellation.
- Open/close 100 sequential app sessions and multiple windows; count leftover threads, file descriptors, outstanding jobs, callback roots.
- Deny file roots, invalid UTF-8 and oversized fragment in mid-batch; ensure error without partial document mutation.
- If a performance threshold cannot be measured repeatably, label exploratory rather than establishing a gate from one sample.

**Do not set hard FPS, memory or latency promises without target hardware baselines and acceptance data.** The old repo's 50ms budgets and exceptions are historical evidence for different code paths, not thresholds automatically inherited by a refactored product.

## Explicitly deferred or rejected work

| Idea | Disposition |
| --- | --- |
| Browser engine/Chromium/WebKit/JavaScript baked into Core | Reject — violates product purpose |
| Web server, HTTP/SSE, database, auth built into Core | Reject — application concerns |
| Framework-wide app `State` class required to use raw HTML | Reject — optional UI-only |
| Full NiceGUI/Quasar feature parity by 0.5 | Reject — not a meaningful milestone |
| Network resource fetching enabled implicitly by HTML assets | Reject — capability and security mismatch |
| Entire old donor runtime copied into new host | Reject — ownership and lifetime divergence |
| All WPT suites as obligatory per-change gate | Reject — scoped targeted tests instead |
| GPU rewrite before app performance proves need | Defer |
| macOS/mobile first-party before Linux/Windows qualification | Defer |
| Generic plugin registry before two real plugins | Defer |
| Static HTML text selection deferred to optional chat widgets | Reject — Core semantic gap |

## Open decisions requiring future evidence

- **Grid promotion:** what bounded CSS Grid subset can be qualified without delaying 0.4? Define exact old tests and native app fixture.
- **Modal placement:** when should a UI dialog use HTML top layer versus native OS dialog? Avoid two incompatible focus contracts.
- **Widget rendering extension point:** can code/terminal/chart UIs be sufficiently built from DOM/canvas-like primitives? Prototype a consumer before choosing new Core APIs.
- **Text maximum:** split host command size, per-node content size and document total size rather than one arbitrary 16 KiB ceiling. Define backpressure and decoding behavior first.
- **Component state retention:** choose keyed identities and mutation journal strategy compatible with Core node generations.
- **Native icon/menu/tray integration:** define cross-platform minimal semantic API and documented supported matrix.
- **Accessibility release claim:** define exact AT-SPI/UIA client and desktop acceptance script for promoted controls.
- **Optional PowerShell UI parity:** decide whether shared HTML/CSS generated assets suffice or a PS-native declarative DSL is warranted; don't couple languages accidentally.

## Principle for agent implementation

A future agent must validate current main, not blindly treat this roadmap as an implementation mandate. When it proposes a feature, it should answer: **Why Core? Why now? Which original code is relevant and what has changed? Which consumer proves value? What breaks if absent? What is explicitly out of scope? How will it be tested?**
