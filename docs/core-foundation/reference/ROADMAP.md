# Dependency-aware roadmap: UI4ME Core and optional UI4ME UI

**Important:** versions here are recommendations, not promises or a request to implement all catalogue items. **Do not develop version 0.3 before finishing the 0.2 release gate.** Every target bucket in `data/features.json` is a *candidate pool*, not a release checklist. Product benefit, dependencies and risk determine the actual release slice.

## Track A — UI4ME Core (separate version line)

### 0.2 stabilization and final qualification (current work)

**Goal:** declare current minimal native HTML/CSS app foundation reliable. No major new features.

Must pass actual installed Linux KDE/Wayland and Windows x64 consumers through Python and PowerShell. Validate first paint, text rendering, typing/IME/clipboard, window/close/repeated sessions, DPI/resizing, resource lifetimes and package upgrades; repair concrete blockers. Keep the existing source layout and native host. Confirm the release source snapshot and manifest before claiming evidence. Current 0.2 is a *source candidate*; the old repository does not waive failed comparisons.

**Release rule:** don't publish based solely on Rust compilation, headless screenshots or Windows cross-checks. Human/automated native desktop evidence must be labeled precisely.

### Core 0.3 — programmable DOM, text selection and scroll (first high-value feature release)

**User result:** developers build streaming chat, log viewers, file lists and reactive UI manually with **only Core**. No separate UI package is necessary to exercise the new features.

Recommended contract, in order:

1. **DOM mutation:** append/prepend/insert/remove/move nodes, read attributes/text, stable internal identities and atomic bounded batch operations. Preserve unrelated focus, input values, scroll position and callbacks. Explicit invalid-op rollback semantics.
2. **Scroll and geometry:** `scroll_to`, `scroll_by`, offsets/ranges, element rectangle, `scroll_into_view`, resize/DPI-correct query results and scroll position callbacks.
3. **Selection and clipboard:** read-only document selection across wrapped/bidi text; copy text to native clipboard, host clipboard get/set. Keep text-input selection and password rules intact.
4. **Event cancellation and batching:** consistent bubbling/cancelable default actions, safe callback reentry, no stale target resurrection; coalesce document invalidation after a verified command batch.
5. **Long content/responsiveness:** replace the blanket 16 KiB host-set text limit with a reviewed, bounded mechanism for chunks/large content (not an unlimited string); benchmark streaming updates with realistic workloads, handle queue pressure and cancellation.
6. **Platform and packaging fixes that block the above:** keyboard/fractional DPI, resource retirement, Python+PowerShell API parity, typed failures and source identity.

**Core-only acceptance demo:** a local deterministic stream simulator updates 2–3 conversations and a 10k-line log while a user edits a search field and scrolls away from the bottom. No ACP, HTTP, Markdown or component framework dependency. Exercise Linux+Windows installed consumers and test no stale updates/selection errors.

**Exit gates:** all five contracts exposed through the C ABI and both language bindings; selected old regressions ported as targeted modern tests, selected WPT under a defined subset, independent installed consumer, one desktop human/automation journey per OS; no unbounded memory/queue growth in documented stress scenario.

### Core 0.4 — standard HTML behavior + native OS utility completeness

**User result:** raw HTML forms, menus and document interactions behave predictably; desktop tools can access common OS services without third-party webviews.

Candidate scope: baseline `<select>/<option>` and listbox, basic `<dialog>` top layer and focus semantics, `<details>/<summary>`, form association/label behavior, grid subset and table rendering where proven, common media queries, rounded/hit geometry, basic accessibility semantic/actions on Windows UIA and Linux AT-SPI; native open/save/folder dialog, show/hide/focus/minimize/maximize/fullscreen, icons/constraints, monitor/DPI and drag/drop capability negotiation.

**Do not require:** advanced date/time pickers, widgets with autocomplete/chips, custom animated popovers, global keyboard hooks, system tray, full Chromium CSS coverage or print engine.

**Exit gates:** a **Core-only file utility** on both OSes can pick a file, show a form with native select and dialog, use keyboard and screen-reader interfaces, and operate several windows. Declare per-platform unsupported services explicitly. WAI-ARIA practices are references for keyboard/focus where Core claims relevant semantics.

### Core 0.5 — reliability, coverage and measured performance

**User result:** dependable public foundation across long-running applications. Do **not** use 0.5 as a catch-all for postponed components.

Prioritize reference conformance and stabilization of features already promised in 0.2–0.4. Include RTL/writing mode quality, positioned/sticky regions where needed, response to OS theme/DPI, performance of incremental paint/layout, cache retirement and long-session soak, useful public diagnostics, and backward-compatible ABI maturity. Broader grid/tables/pseudo elements/visual effects enter only with explicit demand and tests.

**Exit gates:** final installed Linux and Windows matrices, published per-feature support tier, no unresolved P0 correctness/ownership regressions, upgrade and rollback procedure, reproducible package hashes, bounded resource soak and accessibility evidence for promoted controls. Avoid a misleading blanket 'browser compatible' label.

### Core later / research-only

Complex multicolumn/paged printing, container queries, CSS animations/effects beyond common app demands, GPU renderer, 3D, video, web networking, arbitrary embedded content, true browser features. These are tracked for research, not auto-scoped into 0.5. Preserve donor source as reference when helpful.

## Track B — optional UI4ME UI (independently versioned)

**Package rule:** `ui4me-ui` starts at **0.1.0** (not Core version 0.5), requires a declared minimum Core API/ABI, and cannot be imported by Core. PowerShell convenience modules may have a different release cadence while sharing a semantic behavior contract.

### UI 0.1 — minimal convenience foundation (after Core 0.3 APIs are usable)

Declarative markup/component composition, simple `row/column/card`, typed component props, local CSS themes/icons, safe Markdown-to-HTML and code highlight, chat/log components, tabs and session sidebar, status/progress/notification, thin managed task helpers and one complete keyboard-accessible demonstration. Support Python first *without* baking Python into Rust; define PowerShell parity and test the same HTML output semantics.

**Acceptance:** install Core alone and verify no dependency on UI. Install UI layer in a different consumer project and build chat/layout without editing engine. Use pure helpers and public mutation protocol; no hidden renderer APIs. Streaming remains simulated in integration tests; ACP/SSE transports are app-owned.

### UI 0.2 — reactivity and broader components

Observable/computed state, keyed reconciliation/batch refresh, popover/menu/tooltip helpers, trees/selects/checkbox variants, optional form validation display, virtual list, tab panels, reusable dialogs and file-picker wrappers, pagination/data table and async worker cancellation convenience. Publish independently of Core; features requiring Core 0.4 must declare that constraint.

### UI 0.3 and extensions — only when consumers demand

Advanced editors, terminal/log PTY, rich-text, interactive charts, maps, audio/video, specialized productivity widgets. Prefer separately installable `ui4me-ui-<extension>` packages instead of silently turning the required UI package into an alternative browser runtime.

## Track C — developer applications and examples

- **Core-only raw app:** a no-UI-library HTML/CSS app; verifies the renderer and native callbacks.
- **Core-only OS utility:** file/folder picker, multiple windows and clipboard; verifies platform abstractions.
- **Optional UI chat application:** exercises components and long streams, but ACP/SSE implementation remains in its own application package/repository.
- **Long-session agent app:** a demanding real consumer for update performance, resource retention and permission UI; it cannot define Core's business behavior.

## Critical dependency gates

| Prerequisite | Needed by | Rule |
| --- | --- | --- |
| Stable node identity / subtree semantics | append/remove and reactive reconciliation | No stale IDs reused after replacement |
| DOM batch atomicity | streaming/chat/UI keyed refresh | Do not claim atomic semantics for OS calls or callback side effects |
| Geometry and programmatic scroll | tooltip/menus/dialog positioning and virtual lists | Complete Core contracts before adding UI wrappers |
| Read-only selection and clipboard | chat/code views | UI should not fake it with hidden textarea selections |
| Core dialog/focus behavior | UI modal/dialog service | Don't call overlays accessible until focus trapping is verified |
| OS chooser capability | file-attachment component | Upload and app storage remain outside Core |
| Accessibility semantic tree | UI accessible patterns | A component's ARIA flags alone aren't a native screen-reader claim |
| Python/PS ABI symmetry | optional UI implementations | Same event/result/error meaning, language-specific ergonomics allowed |
| Source + artifact identity | release qualification | Any post-build source change invalidates dependent receipts |

## Release decision algorithm (must run before each milestone)

1. Pull current `main`, record SHA, public API, supported-feature docs and current installed evidence.
2. Compare each candidate with the Core/UI/application ownership test. Reclassify only through a documented ADR.
3. Prioritize **user-visible utility × generic reuse × feasibility ÷ correctness/compatibility risk**. Never promote a feature solely because old code exists.
4. Select the **smallest coherent vertical slice** that solves one core developer problem. Keep stretch items separate.
5. Agree exact acceptance fixtures and failure modes **before** implementation. Use targeted regressions per edit, wider suite at integration milestones.
6. Finish cross-OS installed checks and evidence before claiming release; carry incomplete items forward rather than declaring them green.
7. Update registry status, record implementation files and tests, and freeze version artifacts.

## Milestone status template

| Field | Meaning |
| --- | --- |
| Milestone ID and release channel | e.g. `core/0.3` or `ui/0.1` |
| Feature IDs included | IDs from `data/features.json`, no fuzzy names |
| Current baseline SHA and source provenance | Actual clone and review date |
| User scenario delivered | What installed consumer can now do |
| Contract and ABI changes | Semantics, return types, error behavior, compatibility |
| Known divergences | Supported/unsupported by OS and rendering tier |
| Targeted test results | Exact test names and commit |
| Native/installed evidence | OS, package hash, display server, user action evidence |
| Blocking P0/P1 defects | Explicit unresolved items |
| Publication status | Never infer from build success |

