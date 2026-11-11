# Core foundation contract — selective 0.3/0.4 acceptance

The slices below define *real usability*, not a completion percentage of the research feature inventory. A feature is complete only if public Core can perform it, the C ABI contract is documented, Python and PowerShell work (where supported) and appropriate tests/evidence exist. Use the current implementation wherever a capability already works.

## 0.3 — programmable document foundation

- [x] **S1 DOM mutation and identities** — append, prepend, insert-before/after, remove, move nodes/subtrees; safe parse/validation; read attrs/text, stable identity model and bad-ID handling. Preserve unrelated control values, focus, listeners and resource retirement. If move has a meaningful unsupported edge case, define and handle it explicitly.
- [x] **S2 Batching and events** — bounded atomic DOM batch with deterministic invalid-op behavior, coalesced invalidation, safe callback reentry, cancellation/default-action semantics and stale-target protection. Avoid claiming atomicity of arbitrary foreign callbacks/OS actions.
- [x] **S3 Scroll and geometry** — scroll_to/by/into-view, offsets/ranges, read-only element rects and resize/DPI-correct results; user scrolled-away behavior preserved during streaming updates.
- [x] **S4 Selection and clipboard** — real read-only document text selection + copy, text input selection preserved, safe unicode wrapping and enough bidi behavior for chosen profile, native clipboard get/set, password handling and focus rules.
- [x] **S5 Sustained updates** — chunked/bounded long text/HTML updates, queue pressure and cancellation under rapid updates; no stale callbacks or unmanaged resource growth. Test sustained 10k-line log and several concurrent chat views without requiring ACP/network integration.
- [x] **S6 Cross-binding contract and Core-only demo** — all promoted features accessible using installed Python and PowerShell; C ABI native standalone consumer as relevant; one deterministic Core-only dynamic chat/log demo, small targeted negative tests and actual desktop acceptance on Linux KDE and Windows.

**0.3 GO:** demo works from independent installed package on both OSes; typing, scrolling, mutation, selection/copy and shutdown survive prolonged interactive use; relevant cross-binding tests pass. Document narrow unsupported text scripts or platform limitations explicitly rather than pretending complete browser conformance.

## 0.4 — practical general-purpose native desktop core

- [x] **S7 Essential HTML semantics** — `<select>/<option>` with keyboard/labels, basic `<dialog>` and modal focus/trap/restore, standard form focus/label defaults, `<details>/<summary>` where small and reliable; explicit cancel/focus behavior. Don't rebuild a component library inside Core.
- [ ] **S8 Common native windows** — show/hide, focus/activation, minimize/restore/maximize, fullscreen, icon/size constraints, multiwindow lifetime, monitor/DPI information. On Wayland return explicit unsupported/denied where compositor forbids requested operations.
- [ ] **S9 Native file services** — open, save and folder picker with cancel/Unicode paths and correct ownership; clipboard parity; file-drop only if it is straightforward and stable, else document deferral.
- [ ] **S10 Responsive HTML/CSS reliability** — validate basic flex, media queries, overflow, responsive resize and common app layout behavior; fix only user-visible/functional correctness gaps. Limited grid/table/positioning only if actual core-only demo needs it; no comprehensive browser conformance gate.
- [ ] **S11 Accessible ordinary interactions** — keyboard navigation/focus and meaningful available host semantics; scope Windows UIA/Linux AT-SPI statements to measured behavior. Don't gate foundation on complete screen-reader coverage where the architecture does not yet support it; don't falsely claim accessibility compliance.
- [ ] **S12 Core-only OS consumer and gate** — installed Python and PowerShell standalone file utility, multiple windows, native picker/select/dialog/keyboard, resize/DPI/clipboard, clean shutdown across both target OSes; captured evidence from actual interactive desktop sessions.

**0.4 GO / Foundation Complete:** Core-only developer can build ordinary responsive multiwindow HTML/CSS desktop utilities with dynamic document behavior and common OS services using only published APIs, on Linux and Windows. No P0/P1 foundation defects. Installed packages must work without Rust/.NET developer tooling. Unsupported non-core features and honest accessibility limitations remain documented.

## 0.5 — optional short maturity pass, *not* a second feature backlog

Only if user-app validation reveals concrete high-value issues: API compatibility and error diagnostics, lifecycle resource leaks, installed upgrade problems, common CSS correctness, perceptible update stutters, a bounded continuous run. **Don't wait for 0.5 just because the research roadmap named it.** Do not block application/library development on full WPT, rich SVG, printing, animations, GPU or comprehensive screen-reader matrix.

## Demonstration gates, not microbenchmarks

1. Core-only chat/log app: mutate continuously, scroll manually, select/copy text, interact with persistent search field, resize, close and reopen.
2. Core-only OS file utility: open/save/folder dialog, select/dialog/labels, clipboard, independent windows, focus/keyboard.
3. Installed consumer from clean environment: Python and PowerShell exercise the same semantic contracts on Debian/KDE and Windows; no private Rust/runtime paths, no UI4ME UI dependency.
