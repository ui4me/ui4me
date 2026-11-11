# Feature catalogue — source-indexed

**Snapshot:** 2026-11-11. **Features:** 224. **Original archive source anchors:** 144.

Interpretation: `current_02` is an API/documentation assessment, not a fresh pass. `old_evidence` means code was located in the **old, unqualified** donor archive, not that the feature is stable or that it is publicly accessible in the current Core.

The relative paths are rooted at `ui4me-main/` inside `bigbatmanorg-ui4me-old.zip`; line ranges refer to that exact archive. Do not apply them to a refactored current repo.

## Core / Document (23)

### DOM-001 · HTML5 tree parsing

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Every raw HTML application starts with standards-oriented parsing.

**Acceptance:** Exercise html5 tree parsing through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/parse/mod.rs:102-118` · exact match line 105: `pub fn create(id: DocumentId, html: &str, url: &str, limits: DomLimits) -> Result<Document, Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/slice_parse.rs:53-66`

### DOM-002 · Document and generational node identity

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Stale event and resource references must not target replacements.

**Acceptance:** Exercise document and generational node identity through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/arena.rs:33-49` · exact match line 36: `pub struct Arena {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/handles_lifetime.rs:15-28`

### DOM-003 · ID lookup

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Stable element addressing for explicit bindings.

**Acceptance:** Exercise id lookup through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/query.rs:22-38` · exact match line 25: `pub fn element_by_id(&self, id: &str) -> Option<NodeId> {` · implementation-anchor · symbol-or-code

### DOM-004 · Public CSS selector query

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Enable generic document querying without a Python component tree.

**Acceptance:** Exercise public css selector query through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** DOM-003, CSS-002

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/query.rs:221-237` · exact match line 224: `pub fn query_all(&self, doc: &Document, list: &ParsedSelectorList, root: NodeId) -> Result<Vec<NodeId>, Status> {` · implementation-anchor · symbol-or-code

### DOM-005 · Text content read and write

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Expose unambiguous plain text semantics and reads.

**Acceptance:** Exercise text content read and write through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/chardata.rs:15-31` · exact match line 18: `pub fn utf16_len(s: &str) -> usize {` · implementation-anchor · symbol-or-code

### DOM-006 · HTML subtree replacement

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Atomic replacement is already the minimum useful mutation.

**Acceptance:** Exercise html subtree replacement through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/parse/fragment.rs:48-64` · exact match line 51: `pub fn set_inner_html(&mut self, el: NodeId, html: &str) -> Result<(), Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/fragment_serialize.rs:15-28`

### DOM-007 · Incremental HTML insertion

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Allow append/prepend/before/after without rebuilding the transcript.

**Acceptance:** From both installed bindings append and prepend 100 independently identified nodes; existing input/focus/scroll state is retained, wrong IDs/oversize markup reject atomically, and stale completions cannot update removed nodes.

**Dependencies:** DOM-002, DOM-006

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/parse/fragment.rs:96-112` · exact match line 99: `pub fn insert_adjacent_html(&mut self, el: NodeId, position: &str, html: &str) -> Result<(), Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/fragment_serialize.rs:15-28`

### DOM-008 · Remove and move nodes

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Remove old messages or move items while retiring identity safely.

**Acceptance:** Remove and reparent identified nodes; stale event targets are rejected, keyboard focus repairs deterministically, and assets are retired; verify with independent reference DOM order.

**Dependencies:** DOM-002

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/mutate/remove.rs:21-37` · exact match line 24: `pub(crate) fn remove_nodes_ex(&mut self, rev: u64, parent: NodeId, nodes: &[NodeId], journal_it: bool) {` · implementation-anchor · symbol-or-code

### DOM-009 · Atomic mutation batch

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Prevent partial updates and reduce repeated layout work.

**Acceptance:** Apply several valid changes under one commit/invalidation; inject an invalid step and prove zero partial application and deterministic error; test nested/reentrant callbacks.

**Dependencies:** DOM-007, DOM-008

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/batch/exec.rs:18-34` · exact match line 21: `pub fn document_word(id: DocumentId) -> u64 {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/batch_atomic.rs:71-84`

### DOM-010 · Attribute and class operations

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Support declarative CSS state using the raw core API.

**Acceptance:** Exercise attribute and class operations through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/attrs.rs:30-46` · exact match line 33: `pub fn qualified_name(n: &QualName) -> String {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/attributes.rs:16-29`

### DOM-011 · Read attributes and class lists

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Make DOM inspection possible without hidden state mirrors.

**Acceptance:** Exercise read attributes and class lists through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/attrs.rs:114-130` · exact match line 117: `pub fn get_attribute(&self, n: NodeId, name: &str) -> Result<Option<&str>, Status> {` · implementation-anchor · symbol-or-code

### DOM-012 · DOM serialization

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Enable inspection/export without leaking internal arena objects.

**Acceptance:** Exercise dom serialization through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/serialize.rs:111-127` · exact match line 114: `pub fn outer_html(&self, n: NodeId) -> Result<String, Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/fragment_serialize.rs:15-28`

### DOM-013 · Document fragments and staging

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Validate content before mutation and preserve unrelated state.

**Acceptance:** Exercise document fragments and staging through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/parse/fragment.rs:121-137` · exact match line 124: `pub fn parse_fragment_for_element(&mut self, context: NodeId, html: &str) -> Result<NodeId, Status> {` · implementation-anchor · symbol-or-code

### DOM-014 · Stylesheet add/remove/query

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Load and manipulate local author CSS predictably.

**Acceptance:** Exercise stylesheet add/remove/query through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/stylesheets.rs:45-61` · exact match line 48: `pub fn is_stylesheet_source(e: &ElementData) -> bool {` · implementation-anchor · file-lead

### DOM-015 · Safe URL and base resolution

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Keep local asset policy separate from application network requests.

**Acceptance:** Exercise safe url and base resolution through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/src/uri.rs:29-45` · exact match line 32: `pub fn of(url: &Url) -> Scheme {` · implementation-anchor · file-lead

### DOM-016 · DOM mutation journal

**Owner:** Core / Core / Document · **Current 0.2:** `internal` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Use precise invalidation rather than full-document rebuilds.

**Acceptance:** Exercise dom mutation journal through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/journal.rs:54-70` · exact match line 57: `pub struct JournalEntry {` · implementation-anchor · symbol-or-code

### DOM-017 · Read-only element geometry

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Needed by popovers, drag targets, scroll and accessibility.

**Acceptance:** Exercise read-only element geometry through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** CSS-012

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/geometry_query.rs:48-64` · exact match line 51: `pub fn box_rects(fragments: &FragmentTree, node: NodeId) -> Vec<BoxRects> {` · implementation-anchor · file-lead

### DOM-018 · DOM resource retirement

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Old asynchronous results must not revive removed nodes.

**Acceptance:** Exercise dom resource retirement through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** DOM-002

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/retain.rs:21-37` · exact match line 24: `pub fn retain(&mut self, n: NodeId) -> Result<(), Status> {` · implementation-anchor · file-lead

### DOM-019 · HTML form-associated control state

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Canonical control value/checked/selection state belongs in the engine.

**Acceptance:** Exercise html form-associated control state through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/control_state.rs:59-75` · exact match line 62: `pub struct ControlState {` · implementation-anchor · symbol-or-code

### DOM-020 · Form reset and validation semantics

**Owner:** Core / Core / Document · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Plain HTML forms need predictable browser-like defaults.

**Acceptance:** Exercise form reset and validation semantics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/forms.rs:18-34` · exact match line 21: `pub fn is_form_associated(e: &ElementData) -> bool {` · implementation-anchor · file-lead

### DOM-021 · Input/depth/document size limits

**Owner:** Core / Core / Document · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Limits must reject atomically, not silently truncate messages.

**Acceptance:** Exercise input/depth/document size limits through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/limits.rs:39-55` · exact match line 42: `pub struct DomLimits {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-dom/tests/lifecycle_limits.rs:18-31`

### DOM-022 · HTML templates and nested content

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Support reusable ordinary markup without an application DSL.

**Acceptance:** Exercise html templates and nested content through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/parse/sink.rs:6-22` · exact match line 9: `//! * The template contents fragment is created with every template element (FR-014).` · implementation-anchor · symbol-or-code

### DOM-023 · Link activation and navigation policy

**Owner:** Core / Core / Document · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Expose explicit app-controlled navigation; never automatically fetch arbitrary remote content.

**Acceptance:** Exercise link activation and navigation policy through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/api/navigation.rs:62-78` · exact match line 65: `pub unsafe extern "C" fn $name(n: ui4me_node, out: *mut ui4me_node) -> ui4me_status {` · implementation-anchor · file-lead

## Core / CSS and Layout (27)

### CSS-001 · Author CSS parsing and cascade

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Every raw HTML app requires author CSS applied consistently.

**Acceptance:** Exercise author css parsing and cascade through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/sheets/mod.rs:35-51` · exact match line 38: `pub(crate) fn parse_sheet(` · implementation-anchor · symbol-or-code

### CSS-002 · Selectors specificity and pseudo classes

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Support common stylesheet behavior without claiming all web CSS.

**Acceptance:** Exercise selectors specificity and pseudo classes through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/query.rs:212-228` · exact match line 215: `pub fn matches(&self, doc: &Document, list: &ParsedSelectorList, element: NodeId, scope_root: Option<NodeId>) -> Result<bool, Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-style/tests/cascade.rs:15-28`

### CSS-003 · Custom properties and var()

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Enable theming via ordinary CSS variables.

**Acceptance:** Exercise custom properties and var() through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/computed.rs:186-202` · exact match line 189: `pub fn computed_value(&self, doc: &Document, node: NodeId, name: &str) -> Result<String, Status> {` · implementation-anchor · symbol-or-code

### CSS-004 · Media queries and responsive styles

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Allow resize/DPI-driven app layouts.

**Acceptance:** Exercise media queries and responsive styles through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/device.rs:1-17` · exact match line 4: `//! published by HostRuntime/WindowPresenter (viewport, device size, DPR, colour scheme) and the` · implementation-anchor · file-lead

### CSS-005 · Box model and inline flow

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Support typical document typography and spacing.

**Acceptance:** Exercise box model and inline flow through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/ifc/inline/driver.rs:35-51` · exact match line 38: `pub fn intrinsic(shaped: &ShapedParagraph, host: &mut dyn InlineLayoutHost) -> IntrinsicOutcome {` · implementation-anchor · file-lead

### CSS-006 · Flexbox layout

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Primary practical desktop layout primitive.

**Acceptance:** Exercise flexbox layout through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/coordinator/mod.rs:196-212` · exact match line 199: `pub fn layout_document(src: &impl StyledSource, viewport: Viewport, text: &mut TextServices) -> LayoutOutput {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-layout/tests/t1_flex.rs:67-80`

### CSS-007 · CSS Grid basics

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Promote a bounded basic grid profile when targeted cases pass.

**Acceptance:** Exercise css grid basics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** CSS-006

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/box_tree/typed_layout.rs:1-16` · exact match line 3: `//! Flex, box-alignment and grid longhands from 006's typed ComputedStyleView groups` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-layout/tests/t1_grid.rs:59-72`

### CSS-008 · CSS table layout

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Tables are basic HTML but their full algorithm needs qualification.

**Acceptance:** Exercise css table layout through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/table/layout.rs:70-86` · exact match line 73: `pub(crate) fn node_edges(&self, n: usize, basis: f32) -> (Rect<f32>, Rect<f32>) {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-layout/tests/t1_tables.rs:66-79`

### CSS-009 · Relative and absolute positioning

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Needed for positioned badges and overlays.

**Acceptance:** Exercise relative and absolute positioning through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/coordinator/oof.rs:34-50` · exact match line 37: `pub const INLINE_CONTAINING_BLOCK: &str = "css.value.position-inline-containing-block";` · implementation-anchor · file-lead

### CSS-010 · Sticky and fixed positioning

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Useful for persistent headers, but geometry correctness is demanding.

**Acceptance:** Exercise sticky and fixed positioning through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/coordinator/sticky.rs:1-17` · exact match line 4: `//! position and publishes StickyConstraints on its fragment (the nearest scroll container or the` · implementation-anchor · file-lead

### CSS-011 · Floats and inline wrapping

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `internal` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Legacy text flow should follow demand, not block app productivity.

**Acceptance:** Exercise floats and inline wrapping through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/coordinator/floats.rs:11-27` · exact match line 14: `pub(crate) struct BfcSpace<'a, 'b> {` · implementation-anchor · file-lead

### CSS-012 · Overflow and scroll-range geometry

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Scrolling and hit testing must share one geometry source.

**Acceptance:** Exercise overflow and scroll-range geometry through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/coordinator/overflow.rs:2-18` · exact match line 5: `//! **Published by layout** (in fragment::builder, from Taffy's ScrollableOverflow): for every` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-layout/tests/t1_overflow.rs:61-74`

### CSS-013 · Multi-column layout

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Preserve internally until a real use case appears.

**Acceptance:** Exercise multi-column layout through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/fragmentation/multicol.rs:21-37` · exact match line 24: `pub const BALANCE_GROWTH_STEPS: u32 = 6;` · implementation-anchor · file-lead

### CSS-014 · Paged media and printing

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Not essential for app foundation.

**Acceptance:** Exercise paged media and printing through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/fragmentation/paged.rs:33-49` · exact match line 36: `pub const MAX_PAGE_PASSES: usize = 6;` · implementation-anchor · file-lead

### CSS-015 · Border/background/radius painting

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Common app styling must be correct at scale factors.

**Acceptance:** Exercise border/background/radius painting through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/paint/background.rs:14-30` · exact match line 17: `pub const MAX_TILES: usize = 4096;` · implementation-anchor · file-lead

### CSS-016 · Gradients and background images

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Basic visual expressiveness without JS.

**Acceptance:** Exercise gradients and background images through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/paint/background.rs:1-14` · exact match line 1: `//! owner: 010-paint-render — created by 010 T001; gradient layers by 010 T068/T069 (subset)` · implementation-anchor · symbol-or-code

### CSS-017 · Shadows and visual effects

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Optimize quality only after rendering semantics are stable.

**Acceptance:** Exercise shadows and visual effects through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/paint/shadow.rs:13-29` · exact match line 16: `pub(crate) fn push_box_shadow(b: &mut Builder, bx: &PaintBox, rr: &RoundedRect, widths: [f32; 4], s: &BoxShadowSpec, out: &mut Vec<Pending>, phase: PaintPhase, scope: Option<ScopeId>) {` · implementation-anchor · file-lead

### CSS-018 · Transforms and stacking context

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Popovers and complex layering depend on stable stacking.

**Acceptance:** Exercise transforms and stacking context through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/stacking.rs:3-14` · exact match line 6: `//! flex/grid items with z-index, containment) join when 006 publishes them.` · implementation-anchor · file-lead

### CSS-019 · Clipping, overflow, rounded hit region

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Paint and hit tests must agree about visible geometry.

**Acceptance:** Exercise clipping, overflow, rounded hit region through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/clip_tree.rs:16-32` · exact match line 19: `pub(crate) fn overflow_clip_scope(b: &mut Builder, bx: &PaintBox, parent: Option<ScopeId>) -> ScopeId {` · implementation-anchor · file-lead

### CSS-020 · Pseudo elements and generated content

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Do not advertise until focus and accessibility interactions are sound.

**Acceptance:** Exercise pseudo elements and generated content through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/box_tree/pseudo.rs:23-39` · exact match line 26: `pub(crate) fn enter_counters(&mut self, node: NodeId, style: &BoxStyle) {` · implementation-anchor · file-lead

### CSS-021 · Container queries

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Useful but not foundational for the first apps.

**Acceptance:** Exercise container queries through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/container.rs:27-43` · exact match line 30: `pub struct ContainerSize {` · implementation-anchor · file-lead

### CSS-022 · CSS animation and transitions

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Animation timing should not complicate basic UI correctness.

**Acceptance:** Exercise css animation and transitions through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/animation.rs:34-50` · exact match line 37: `pub enum AnimationEventKind {` · implementation-anchor · file-lead

### CSS-023 · Writing modes and RTL layout

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.5-core` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Important for internationalization; needs dedicated layout acceptance.

**Acceptance:** Exercise writing modes and rtl layout through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/writing_mode/mod.rs:25-41` · exact match line 28: `pub mod physical;` · implementation-anchor · file-lead

### CSS-024 · List marker and counters

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Correct HTML lists and numbering without manual CSS.

**Acceptance:** Exercise list marker and counters through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/box_tree/lists.rs:8-24` · exact match line 11: `pub enum Rendered {` · implementation-anchor · file-lead

### CSS-025 · Text overflow and ellipsis

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Avoid layout corruption with long filenames and agent messages.

**Acceptance:** Exercise text overflow and ellipsis through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/ifc/container.rs:505-521` · exact match line 508: `let (start, end) = b.style.flow.text_overflow.start_end(rtl);` · implementation-anchor · symbol-or-code

### CSS-026 · CSS profile and unsupported diagnostics

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Claims must follow a defined subset rather than assumptions from retained code.

**Acceptance:** Exercise css profile and unsupported diagnostics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/profile/table.rs:6-22` · exact match line 9: `//! * [FEATURES] is the public feature list (id, state) of §1–§3/§7.` · implementation-anchor · file-lead

### CSS-027 · CSS framework compatibility

**Owner:** Core / Core / CSS and Layout · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Bootstrap/Tailwind examples do not establish compatibility tiers.

**Acceptance:** Exercise css framework compatibility through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-style/src/profile/mod.rs:20-36` · exact match line 23: `pub mod filter;` · implementation-anchor · file-lead

## Core / Text (16)

### TEXT-001 · Unicode shaping and grapheme handling

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Readable natural language and code depend on correct shaping.

**Acceptance:** Exercise unicode shaping and grapheme handling through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/shaped.rs:22-38` · exact match line 25: `pub struct ShapedCache {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-text/tests/slice_text.rs:73-86`

### TEXT-002 · Font fallback and matching

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Support accented text, symbols and missing glyphs.

**Acceptance:** Exercise font fallback and matching through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/fonts/faces.rs:27-43` · exact match line 30: `pub(crate) struct FaceRecord {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-text/tests/t1_font_environment.rs:39-52`

### TEXT-003 · Local font faces and WOFF

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Installed apps need self-contained fonts.

**Acceptance:** Exercise local font faces and woff through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/src/fonts/registry.rs:19-35` · exact match line 22: `pub use ui4me_core::resource_ids::FontEpoch;` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-resources/tests/woff2.rs:95-108`

### TEXT-004 · Text line breaks and wraps

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Prevent overflow and layout shifts in labels and responses.

**Acceptance:** Exercise text line breaks and wraps through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/scratch.rs:192-208` · exact match line 195: `inner: self.layout.break_lines(),` · implementation-anchor · symbol-or-code

### TEXT-005 · Bidirectional text

**Owner:** Core / Core / Text · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Accept mixed RTL/LTR content without corrupting caret order.

**Acceptance:** Exercise bidirectional text through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/bidi.rs:19-35` · exact match line 22: `pub const LRE: char = '\u{202A}';` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-text/tests/t1_bidi.rs:66-79`

### TEXT-006 · Caret geometry and selection in inputs

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Text controls are usable only with correct navigation and selection.

**Acceptance:** Exercise caret geometry and selection in inputs through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/frozen.rs:1065-1081` · exact match line 1068: `pub fn caret_stops(&self, line_index: usize) -> CaretStops {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-text/tests/t1_caret_stops.rs:45-58`

### TEXT-007 · Read-only document text selection

**Owner:** Core / Core / Text · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Copy code and responses across ordinary rendered text, not only textareas.

**Acceptance:** With no text control, drag/Shift-select wrapped and bidi text and copy selection to another OS application on KDE and Windows; test fragments and DPI.

**Dependencies:** TEXT-006, INTERACTION-001

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/frozen.rs:199-215` · exact match line 202: `pub struct CaretStops {` · partial-or-related · symbol-or-code

### TEXT-008 · OS clipboard text operations

**Owner:** Core / Core / Text · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Expose clipboard independently of a focused text control.

**Acceptance:** Read/write plain text using platform service from host callbacks without requiring focused inputs; denied/unavailable backends return explicit errors.

**Dependencies:** HOST-021

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/editing/clipboard.rs:30-46` · exact match line 33: `pub(crate) enum Command {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/clipboard_ime.rs:164-177`

### TEXT-009 · IME preedit and commit

**Owner:** Core / Core / Text · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Native KDE and Windows acceptance must include real composition.

**Acceptance:** Exercise ime preedit and commit through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/editing/ime.rs:34-50` · exact match line 37: `pub(crate) struct Comp {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-platform/tests/platform_clipboard_ime_t3.rs:73-86`

### TEXT-010 · Text edits and undo/redo

**Owner:** Core / Core / Text · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Normal typing, cut/paste and undo cannot be simulated by the UI library.

**Acceptance:** Exercise text edits and undo/redo through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/editing/history.rs:14-30` · exact match line 17: `pub(super) const LIMIT: usize = 100;` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/text_editing.rs:146-159`

### TEXT-011 · Text metrics and character position queries

**Owner:** Core / Core / Text · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Needed for selections, tooltip placement and caret-aware popovers.

**Acceptance:** Exercise text metrics and character position queries through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/metrics.rs:28-44` · exact match line 31: `pub struct MetricsService {` · implementation-anchor · file-lead

### TEXT-012 · Text decoration and spans

**Owner:** Core / Core / Text · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Link and code styling must be visually consistent.

**Acceptance:** Exercise text decoration and spans through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/decoration.rs:32-48` · exact match line 35: `pub(crate) struct DecoFont {` · implementation-anchor · file-lead

### TEXT-013 · Hyphenation and soft breaks

**Owner:** Core / Core / Text · **Current 0.2:** `internal` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Language-aware line breaking is useful after baseline wrapping.

**Acceptance:** Exercise hyphenation and soft breaks through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/hyphenation.rs:45-61` · exact match line 48: `pub enum Dictionary {` · implementation-anchor · file-lead

### TEXT-014 · Text transform and capitalization

**Owner:** Core / Core / Text · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Standard CSS text behavior belongs below components.

**Acceptance:** Exercise text transform and capitalization through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/transform.rs:25-41` · exact match line 28: `pub enum CaseTransform {` · implementation-anchor · file-lead

### TEXT-015 · Vertical text and advanced typography

**Owner:** Core / Core / Text · **Current 0.2:** `unpromoted` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Preserve source but do not delay early releases.

**Acceptance:** Exercise vertical text and advanced typography through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/vertical.rs:19-35` · exact match line 22: `pub enum GlyphOrientation {` · implementation-anchor · file-lead

### TEXT-016 · Caching and epoch retirement

**Owner:** Core / Core / Text · **Current 0.2:** `internal` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Long-running apps must not grow unbounded through text changes.

**Acceptance:** Exercise caching and epoch retirement through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-text/src/paragraph/shaped.rs:184-200` · exact match line 187: `pub struct ContentCache {` · implementation-anchor · symbol-or-code

## Core / HTML Semantics and Events (21)

### INTERACTION-001 · Pointer hit testing

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Paint and interactions must use the same geometry revision.

**Acceptance:** Exercise pointer hit testing through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/hit_index.rs:141-157` · exact match line 144: `pub fn hit_test(&self, point: ViewportPoint, opts: HitOptions) -> HitResult {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/transformed_geometry.rs:16-29`

### INTERACTION-002 · Keyboard events and shortcuts

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Expose keyboard input consistently to raw callers.

**Acceptance:** Exercise keyboard events and shortcuts through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/keyboard.rs:28-44` · exact match line 31: `pub fn sequential_order(d: &Document) -> Vec<NodeId> {` · implementation-anchor · file-lead

### INTERACTION-003 · Focus and tab order

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Accessible navigation needs correct focus state.

**Acceptance:** Exercise focus and tab order through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/focus.rs:19-35` · exact match line 22: `pub enum FocusSource {` · implementation-anchor · file-lead

### INTERACTION-004 · Native button activation semantics

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Enter/Space/button defaults belong to HTML engine.

**Acceptance:** Exercise native button activation semantics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/activation.rs:27-43` · exact match line 30: `pub fn has_activation_behaviour(d: &Document, n: NodeId) -> bool {` · implementation-anchor · file-lead

### INTERACTION-005 · Wheel and scrollbar interaction

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Scrollable content must respond to mouse and keyboard.

**Acceptance:** Exercise wheel and scrollbar interaction through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/scroll.rs:224-240` · exact match line 227: `pub(crate) fn on_wheel(host: &mut dyn DispatchHost, doc: DocumentId, x: f64, y: f64, dx: f64, dy: f64, m: Modifiers, origin: DispatchOrigin, ts: Option<f64>) -> Result<(), Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/scrollbar_interaction.rs:7-20`

### INTERACTION-006 · Programmatic scroll_to and scroll_by

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Chat, logs and file browsers need explicit scrolling.

**Acceptance:** Raw Python and PowerShell callers can query and move viewport or named scroll container, with clamped offsets, events and geometry consistent after resize and DPI change.

**Dependencies:** CSS-012

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/scroll.rs:183-199` · exact match line 186: `pub fn scroll_to(host: &mut dyn DispatchHost, doc: DocumentId, target: Option<NodeId>, x: f64, y: f64) -> Result<ScrollApplied, Status> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/scroll_api.rs:18-31`

### INTERACTION-007 · Scroll into view and focus scrolling

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `missing` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Generic element visibility is an engine concern.

**Acceptance:** Callers can reveal an element from nested scrollers; hidden and disconnected targets behave predictably; keyboard focus reveal works without a UI library.

**Dependencies:** INTERACTION-006, DOM-017

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/scroll.rs:8-24` · exact match line 11: `//! listeners, scrollbar parts (hit routing, drag, paging, visibility), scrollIntoView, the` · partial-or-related · symbol-or-code

### INTERACTION-008 · Native checkbox/radio semantics

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Checkbox/radio need event/value correctness.

**Acceptance:** Exercise native checkbox/radio semantics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/controls.rs:34-50` · exact match line 37: `pub(crate) struct RangeDrag {` · implementation-anchor · file-lead

### INTERACTION-009 · Native select/option and listbox

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Ordinary HTML select must not depend on optional UI library.

**Acceptance:** Exercise native select/option and listbox through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/select.rs:16-32` · exact match line 19: `pub fn display_size(size: Option<&str>, multiple: bool) -> u32 {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/listbox_scroll.rs:5-18`

### INTERACTION-010 · Range and number input

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Standard input types need correct keyboard and pointer behavior.

**Acceptance:** Exercise range and number input through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/controls.rs:8-24` · exact match line 11: `//! * input type=range: arrows, PageUp/PageDown, Home and End, and the pointer on the track and` · implementation-anchor · file-lead

### INTERACTION-011 · Progress and meter element semantics

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Basic HTML controls are engine primitives, not fancy UI widgets.

**Acceptance:** Exercise progress and meter element semantics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-layout/src/replaced/controls.rs:3-19` · exact match line 6: `//! line height), checkbox/radio (13×13), range (129×16), progress (10em×1em), meter` · implementation-anchor · symbol-or-code

### INTERACTION-012 · Details and summary activation

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Standard HTML disclosure needs default behavior.

**Acceptance:** Exercise details and summary activation through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/activation.rs:150-166` · exact match line 153: `/// A details summary: toggle the details (015 HTML-2).` · implementation-anchor · symbol-or-code

### INTERACTION-013 · Dialog top layer and focus trapping

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** HTML dialog semantics are distinct from optional dialog service.

**Acceptance:** HTML dialog showModal/show/close supports Escape and Tab trapping, outside inertness, focus return and nested close; keyboard and screen-reader evidence.

**Dependencies:** INTERACTION-003, INTERACTION-021

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/dialog.rs:34-50` · exact match line 37: `pub enum ElementTaskKind {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/html_dialog_details.rs:149-162`

### INTERACTION-014 · Label association and form semantics

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Labels must activate controls and expose names correctly.

**Acceptance:** Exercise label association and form semantics through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-dom/src/forms.rs:18-34` · exact match line 21: `pub fn is_form_associated(e: &ElementData) -> bool {` · implementation-anchor · file-lead

### INTERACTION-015 · Default actions and cancellable events

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Generic event cancellation is required for composable widgets.

**Acceptance:** Exercise default actions and cancellable events through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/dispatch.rs:28-44` · exact match line 31: `pub const EVENT_LOG_CAPACITY: usize = 1024;` · implementation-anchor · file-lead

### INTERACTION-016 · Pointer capture and drag selection

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Interaction under dragging must survive layout changes.

**Acceptance:** Exercise pointer capture and drag selection through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/pointer.rs:21-37` · exact match line 24: `pub struct HoverState {` · implementation-anchor · file-lead

### INTERACTION-017 · Accessibility semantic tree

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Screen readers need document semantics before UI patterns claim accessibility.

**Acceptance:** Verify names, roles, states, text and coordinates on Windows UIA and Linux AT-SPI; tree changes and focus editing produce coherent announcements; no human AT claim without run.

**Dependencies:** DOM-002, INTERACTION-003

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-a11y/src/lib.rs:22-38` · exact match line 25: `pub use build::{build, BuildInput, Rendering, RenderInfo};` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/accessibility.rs:99-112`

### INTERACTION-018 · Accessibility actions and state updates

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Assistive actions should map to the same control editing path.

**Acceptance:** Exercise accessibility actions and state updates through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** INTERACTION-017

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/a11y.rs:8-24` · exact match line 11: `//! - **After the frames step** ([Runtime::a11y_publish_step]): for each window whose adapter is` · implementation-anchor · file-lead

### INTERACTION-019 · HTML file input and native picker bridge

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** File input needs host capability; avoid hidden network upload behavior.

**Acceptance:** Exercise html file input and native picker bridge through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/api/dialog.rs:13-29` · exact match line 16: `pub extern "C" fn ui4me_dialog_show(el: ui4me_node) -> ui4me_status {` · partial-or-related · file-lead

### INTERACTION-020 · Drag/drop DOM events

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `unpromoted` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Enable generic drag/drop primitives without implementing app-specific transfer.

**Acceptance:** Exercise drag/drop dom events through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/pointer.rs:21-37` · exact match line 24: `pub struct HoverState {` · implementation-anchor · file-lead

### INTERACTION-021 · Event propagation, target/path identity

**Owner:** Core / Core / HTML Semantics and Events · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Callbacks must have consistent target, bubbling and stale-ID behavior.

**Acceptance:** Exercise event propagation, target/path identity through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-interaction/src/dispatch.rs:28-44` · exact match line 31: `pub const EVENT_LOG_CAPACITY: usize = 1024;` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-interaction/tests/dispatch_core.rs:40-53`

## Core / Raster and Graphics (11)

### PAINT-001 · Scene display-list construction

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Avoid exposing browser-like scene internals in API.

**Acceptance:** Exercise scene display-list construction through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/display_list.rs:13-29` · exact match line 16: `pub struct Color {` · implementation-anchor · file-lead

### PAINT-002 · Paint ordering and stacking

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Rendered layers must match hit-test layers.

**Acceptance:** Exercise paint ordering and stacking through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/appendix_e.rs:44-60` · exact match line 47: `pub enum PaintPhase {` · implementation-anchor · file-lead

### PAINT-003 · Text glyph rasterization

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Unicode glyphs must display sharply at supported scales.

**Acceptance:** Exercise text glyph rasterization through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-raster/src/lower/vello_cpu.rs:136-152` · exact match line 139: `pub(crate) struct VelloRaster {` · implementation-anchor · file-lead

### PAINT-004 · Raster image decoding

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Local PNG/JPEG in installed apps must work.

**Acceptance:** Exercise raster image decoding through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/src/decode/image_rs.rs:24-40` · exact match line 27: `pub struct ImageRsDecoder;` · implementation-anchor · file-lead

### PAINT-005 · SVG decoding and raster cache

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `unpromoted` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Icons are useful but cached pixels need correct lifetime accounting.

**Acceptance:** Exercise svg decoding and raster cache through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/src/svg/raster_cache.rs:18-34` · exact match line 21: `pub struct RasterStats {` · implementation-anchor · file-lead

### PAINT-006 · Border images and masks

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `unpromoted` · **Target:** `0.5-core` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Advanced effects should follow common app needs.

**Acceptance:** Exercise border images and masks through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/paint/border_image.rs:18-34` · exact match line 21: `pub struct Placement {` · implementation-anchor · file-lead

### PAINT-007 · Color and alpha blending

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Correct compositing and opacity are engine primitives.

**Acceptance:** Exercise color and alpha blending through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/paint/background.rs:14-30` · exact match line 17: `pub const MAX_TILES: usize = 4096;` · implementation-anchor · file-lead

### PAINT-008 · Damage and incremental paint

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `partial` · **Target:** `0.5-core` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Optimize measured hot paths after correctness baselines.

**Acceptance:** Exercise damage and incremental paint through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-raster/src/damage.rs:37-53` · exact match line 40: `pub type DeviceBox = [f64; 4];` · implementation-anchor · file-lead

### PAINT-009 · CPU framebuffer and snapshot

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Reference frame output must be deterministic.

**Acceptance:** Exercise cpu framebuffer and snapshot through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-raster/src/headless.rs:207-223` · exact match line 210: `pub fn render_headless(&mut self, scene: &SceneSnapshot, scale: f32) -> Result<(PixelBuffer, RenderReceipt), Box<RenderFailure>> {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-platform/tests/presenter_headless.rs:21-34`

### PAINT-010 · High-DPI scaling and pixel snapping

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Real desktops use fractional display scaling.

**Acceptance:** Exercise high-dpi scaling and pixel snapping through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-scene/src/appendix_e.rs:759-775` · exact match line 762: `// The reference browser snaps straight border box edges in CSS pixels` · implementation-anchor · symbol-or-code

### PAINT-011 · GPU raster backend

**Owner:** Core / Core / Raster and Graphics · **Current 0.2:** `missing` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** Do not add GPU complexity without data showing need.

**Acceptance:** Exercise gpu raster backend through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

## Core / Native Application Host (24)

### HOST-001 · Native window creation and close lifecycle

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Raw applications require dependable OS windows.

**Acceptance:** Exercise native window creation and close lifecycle through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:31-47` · exact match line 34: `pub struct PlatformWindowState {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/windows.rs:76-89`

### HOST-002 · Multiple independent windows

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Documents and windows must have independent lifetimes.

**Acceptance:** Exercise multiple independent windows through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/windows.rs:119-135` · exact match line 122: `impl Runtime {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/slice_runtime_window.rs:64-77`

### HOST-003 · Sequential app sessions on one process owner

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Avoid native event-loop reuse violations.

**Acceptance:** Exercise sequential app sessions on one process owner through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/owner.rs:6-22` · exact match line 9: `pub use ui4me_core::owner::OwnerCx;` · implementation-anchor · file-lead

### HOST-004 · Window title and size

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Basic window management is Core, not a widget.

**Acceptance:** Exercise window title and size through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:81-97` · exact match line 84: `pub fn attributes(opts: &WindowOptions) -> WindowAttributes {` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `engine/crates/ui4me-platform/tests/platform_window.rs:12-25`

### HOST-005 · Minimize maximize restore

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Expose supported OS state operations with clear failures.

**Acceptance:** Exercise minimize maximize restore through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:14-30` · exact match line 17: `use winit::window::{Window, WindowAttributes};` · partial-or-related · symbol-or-code

### HOST-006 · Show hide focus raise window

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Desktop utilities need visibility and focus primitives.

**Acceptance:** Exercise show hide focus raise window through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:108-124` · exact match line 111: `pub fn with_platform_attributes(a: WindowAttributes, token: Option<winit::window::ActivationToken>) -> WindowAttributes {` · partial-or-related · symbol-or-code

### HOST-007 · Fullscreen and window decoration

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Support presentation windows and kiosk-like utilities.

**Acceptance:** Exercise fullscreen and window decoration through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:87-103` · exact match line 90: `.with_decorations(opts.decorations)` · partial-or-related · symbol-or-code

### HOST-008 · Window icons and minimum size constraints

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Native identity and constraints should not be simulated by HTML.

**Acceptance:** Exercise window icons and minimum size constraints through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:14-30` · exact match line 17: `use winit::window::{Window, WindowAttributes};` · partial-or-related · symbol-or-code

### HOST-009 · Screen and monitor enumeration

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Respect compositor limits, do not promise arbitrary window placement.

**Acceptance:** Exercise screen and monitor enumeration through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:17-33` · exact match line 20: `pub type Lifecycle = WindowState;` · partial-or-related · file-lead

### HOST-010 · DPI scale and geometry events

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Scale factors must be coherent across layout/paint/input.

**Acceptance:** Exercise dpi scale and geometry events through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:136-152` · exact match line 139: `pub fn css_of(device: (u32, u32), scale: f64) -> (f64, f64) {` · implementation-anchor · symbol-or-code

### HOST-011 · OS clipboard read/write service

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Expose plain text clipboard outside editing controls.

**Acceptance:** Exercise os clipboard read/write service through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/clipboard/mod.rs:9-25` · exact match line 12: `pub mod wayland;` · implementation-anchor · file-lead

### HOST-012 · Native file picker dialog

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Generic OS capability independent of apps or uploads.

**Acceptance:** Open/Save/Folder picker on both target desktops, including cancel, permissions and non-ASCII paths; UI loop remains responsive and result ownership is safe.

**Dependencies:** HOST-021

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/api/dialog.rs:13-29` · exact match line 16: `pub extern "C" fn ui4me_dialog_show(el: ui4me_node) -> ui4me_status {` · partial-or-related · file-lead

### HOST-013 · Native folder picker and save dialog

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** File-management utilities need standard chooser semantics.

**Acceptance:** Exercise native folder picker and save dialog through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Dependencies:** HOST-012

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/api/dialog.rs:13-29` · exact match line 16: `pub extern "C" fn ui4me_dialog_show(el: ui4me_node) -> ui4me_status {` · partial-or-related · file-lead

### HOST-014 · OS drag and drop files

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Allow applications to accept dropped files without embedding upload server.

**Acceptance:** Exercise os drag and drop files through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/input.rs:21-37` · exact match line 24: `pub const WHEEL_LINE_PX: f64 = 40.0;` · partial-or-related · file-lead

### HOST-015 · Native application menus

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Menus are OS capability; component menus can be optional.

**Acceptance:** Exercise native application menus through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-016 · System tray icon and menu

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Useful for background utilities but not core release blocker.

**Acceptance:** Exercise system tray icon and menu through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-017 · OS notifications

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Different from in-app UI toasts.

**Acceptance:** Exercise os notifications through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-018 · Global shortcuts and hotkeys

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** OS policies and permissions vary; handle with explicit capability errors.

**Acceptance:** Exercise global shortcuts and hotkeys through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-019 · OS color-scheme preference

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Report current light/dark preference, leave theme application to UI library.

**Acceptance:** Exercise os color-scheme preference through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-020 · Window bounds persistence

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `missing` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Persistence policy belongs outside Core; Core reports geometry only.

**Acceptance:** Exercise window bounds persistence through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### HOST-021 · Owner-thread event and work queue

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** No app code may mutate the native document off the owner.

**Acceptance:** Saturate normal posts, stop and destroy; no callback on worker thread, no lost accepted completion, no use-after-destroy or deadlock.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/queue.rs:32-48` · exact match line 35: `pub struct PostedTask {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/queue_stress.rs:50-63`

### HOST-022 · Timers and wakeup integration

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Time-based UI interactions need wakeup correctness.

**Acceptance:** Exercise timers and wakeup integration through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/timers.rs:18-34` · exact match line 21: `pub struct TimerId(pub u64);` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/timers_virtual.rs:38-51`

### HOST-023 · Native input platform adapters

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Normalize keyboard/mouse/IME per OS, not per component.

**Acceptance:** Exercise native input platform adapters through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/input.rs:21-37` · exact match line 24: `pub const WHEEL_LINE_PX: f64 = 40.0;` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-platform/tests/platform_input_t3.rs:62-75`

### HOST-024 · Window activation tokens and limitations

**Owner:** Core / Core / Native Application Host · **Current 0.2:** `partial` · **Target:** `0.4` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Honor desktop security and focus stealing rules.

**Acceptance:** Exercise window activation tokens and limitations through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:108-124` · exact match line 111: `pub fn with_platform_attributes(a: WindowAttributes, token: Option<winit::window::ActivationToken>) -> WindowAttributes {` · implementation-anchor · symbol-or-code

## Core / Bindings and Runtime Contracts (16)

### BIND-001 · Stable C ABI contracts

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Python and PowerShell should share one protocol.

**Acceptance:** Exercise stable c abi contracts through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/entry.rs:74-90` · exact match line 77: `pub(crate) type R<T = ()> = Result<T, Status>;` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-ffi/tests/abi_conformance.rs:208-221`

### BIND-002 · Python bindings and callback ownership

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Bindings must settle callbacks and propagate errors.

**Acceptance:** Exercise python bindings and callback ownership through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `bindings/python/src/ui4me/runtime.py:95-111` · exact match line 98: `class Runtime:` · implementation-anchor · symbol-or-code

### BIND-003 · PowerShell bindings and runspace lifetime

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Native owner stays independent of foreground PowerShell sessions.

**Acceptance:** Exercise powershell bindings and runspace lifetime through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `bindings/powershell/src/Ui4me/Hosting/HostedOwner.cs:23-39` · exact match line 26: `internal sealed class HostedOwner` · implementation-anchor · symbol-or-code

### BIND-004 · Event callbacks and subscription removal

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Destroy or replace callbacks without stale invocation.

**Acceptance:** Exercise event callbacks and subscription removal through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/callbacks.rs:27-43` · exact match line 30: `pub struct CallbackError {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-runtime/tests/callbacks_release.rs:74-87`

### BIND-005 · Cross-thread deferred post

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Worker threads only schedule owner-thread changes.

**Acceptance:** Exercise cross-thread deferred post through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/queue.rs:32-48` · exact match line 35: `pub struct PostedTask {` · implementation-anchor · file-lead

### BIND-006 · Asyncio bridge helper

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `missing` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Nice developer helper; Core only needs safe posting.

**Acceptance:** Exercise asyncio bridge helper through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

### BIND-007 · Reserved background completion delivery

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Accepted work must settle even when normal posting queue is full.

**Acceptance:** Exercise reserved background completion delivery through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/queue.rs:32-48` · exact match line 35: `pub struct PostedTask {` · partial-or-related · file-lead

### BIND-008 · Managed background worker pool

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `partial-or-related`

**Why:** Application/optional helper should own worker strategies.

**Acceptance:** Exercise managed background worker pool through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-runtime/src/timers.rs:18-34` · exact match line 21: `pub struct TimerId(pub u64);` · partial-or-related · file-lead

### BIND-009 · Error code and diagnostics API

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Errors must be machine-readable across languages.

**Acceptance:** Exercise error code and diagnostics api through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-core/src/status.rs:8-24` · exact match line 11: `pub struct Status {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-core/tests/status.rs:7-20`

### BIND-010 · Version and installed library provenance

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Installed binaries must match declared bindings.

**Acceptance:** Exercise version and installed library provenance through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/version.rs:4-20` · exact match line 7: `pub const ABI_MAJOR: u32 = 0;` · implementation-anchor · file-lead

### BIND-011 · Resource budgets and bounded admission

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Avoid unbounded work and late completion leaks.

**Acceptance:** Exercise resource budgets and bounded admission through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/src/worker.rs:27-43` · exact match line 30: `pub struct CancelToken(Arc<AtomicBool>);` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-resources/tests/limits.rs:86-99`

### BIND-012 · Thread safety and lifecycle lease

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** No use-after-dispose across FFI callbacks.

**Acceptance:** Exercise thread safety and lifecycle lease through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-core/src/owner.rs:16-32` · exact match line 19: `pub struct OwnerCx<'a> {` · implementation-anchor · file-lead

### BIND-013 · Headless testing backend

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Test rendering without requiring a real display.

**Acceptance:** Exercise headless testing backend through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-raster/src/headless.rs:19-35` · exact match line 22: `pub enum PixelFormat {` · implementation-anchor · file-lead

### BIND-014 · Public Python API ergonomic parity

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Keep the raw API straightforward and unopinionated.

**Acceptance:** Exercise public python api ergonomic parity through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `bindings/python/src/ui4me/document.py:18-34` · exact match line 21: `class DocumentType(Node):` · implementation-anchor · symbol-or-code

### BIND-015 · Public PowerShell API ergonomic parity

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Use matching semantics while respecting runspace ownership.

**Acceptance:** Exercise public powershell api ergonomic parity through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `bindings/powershell/src/Ui4me/Document.cs:15-31` · exact match line 18: `public sealed class DocumentOptions` · implementation-anchor · symbol-or-code

### BIND-016 · Third-language ABI consumability

**Owner:** Core / Core / Bindings and Runtime Contracts · **Current 0.2:** `partial` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `implementation-source-present`

**Why:** Keep C ABI language-neutral; no new bindings until demand.

**Acceptance:** Exercise third-language abi consumability through raw HTML/CSS or a documented Core API (not optional UI helpers); check success, invalid inputs, lifecycle/cleanup, and Linux/Windows behavior when platform-dependent.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/types.rs:9-25` · exact match line 12: `pub type ui4me_status = i32;` · implementation-anchor · file-lead

## Optional / UI Library (47)

### UI-001 · Declarative markup builders

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Generate ordinary HTML and CSS; no compiler or special runtime syntax.

**Acceptance:** Implement declarative markup builders entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-002 · Component base/slots/context managers

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Composable elements that lower into Core mutation commands.

**Acceptance:** Implement component base/slots/context managers entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-003 · Row column card layout helpers

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Thin wrappers around flex and CSS, not new layout algorithms.

**Acceptance:** Implement row column card layout helpers entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-004 · Typed component properties

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Keep component configuration explicit and discoverable.

**Acceptance:** Implement typed component properties entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-005 · Reactive observable values

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Observe Python objects without making Core own state.

**Acceptance:** Implement reactive observable values entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-002

### UI-006 · Computed bindings and one-way links

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Derive UI props from application values; avoid polling by default.

**Acceptance:** Implement computed bindings and one-way links entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-007 · Refreshable dynamic subtrees

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Keyed updates preserve focus and scroll where possible.

**Acceptance:** Implement refreshable dynamic subtrees entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-008 · Diff reconciliation and batching

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Avoid full-component rebuild on each data event.

**Acceptance:** Implement diff reconciliation and batching entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-005, DOM-009

### UI-009 · Theme variables and dark mode

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Build on standard CSS variables and OS preference notifications.

**Acceptance:** Implement theme variables and dark mode entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-010 · Icon packs and asset bundling

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Assets remain optional and licensed; Core does not ship icon fonts by default.

**Acceptance:** Implement icon packs and asset bundling entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-011 · Markdown conversion and sanitization

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Render agent answers as safe HTML, with explicit trust model.

**Acceptance:** Optional package converts fenced code, lists, tables, links and malicious raw HTML to safe fragments; Core remains unaffected and optional package can be absent.

**Dependencies:** DOM-006

### UI-012 · Code syntax highlighting

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Generate styled code spans; do not require a code editor.

**Acceptance:** Implement code syntax highlighting entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-011

### UI-013 · Chat message component

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Reusable markup for sender, content, status and actions.

**Acceptance:** Implement chat message component entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-014, UI-011

### UI-014 · Streaming text and message helper

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Coalesce chunks and schedule bounded updates; network stays in app.

**Acceptance:** Consume synthetic 5k-token stream at high frequency; coalesce to bounded UI updates; cancellation and final content are correct with no DOM rebuild per token.

**Dependencies:** DOM-007, DOM-009, INTERACTION-006

### UI-015 · Bounded append-only log viewer

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Efficient streaming tool-output UI with line retention.

**Acceptance:** Implement bounded append-only log viewer entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** DOM-007, INTERACTION-006

### UI-016 · In-app notification/toast service

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Not the same as OS notifications or error handling policy.

**Acceptance:** Implement in-app notification/toast service entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-017 · Modal dialog service

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Compose Core dialog/focus primitives and return result futures.

**Acceptance:** Implement modal dialog service entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** INTERACTION-013

### UI-018 · Popovers and tooltips

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Position from Core geometry, use generic focus/pointer event semantics.

**Acceptance:** Implement popovers and tooltips entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** DOM-017

### UI-019 · Context menu and dropdown menu

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Implement accessible menu UI above Core.

**Acceptance:** Implement context menu and dropdown menu entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-018

### UI-020 · Tabs and panels

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Switch agent sessions and preserve nested content state.

**Acceptance:** Implement tabs and panels entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-021 · Drawer sidebar and accordion

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Common application organization primitives.

**Acceptance:** Implement drawer sidebar and accordion entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-022 · Switch and toggle widgets

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Higher-level visual variants of ordinary controls.

**Acceptance:** Implement switch and toggle widgets entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-023 · Searchable select and multiselect

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** More than standard HTML select; complex keyboard semantics.

**Acceptance:** Implement searchable select and multiselect entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-024 · Form validation display helpers

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Show developer-authored validity; policy remains app-owned.

**Acceptance:** Implement form validation display helpers entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-025 · Slider and input grouping

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Compose standard HTML range/number behavior.

**Acceptance:** Implement slider and input grouping entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-026 · File-attachment component

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Compose native picker + app-managed storage; no built-in upload service.

**Acceptance:** Implement file-attachment component entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** HOST-012

### UI-027 · Progress spinner and skeleton

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Provide busy and progress indication without Core business state.

**Acceptance:** Implement progress spinner and skeleton entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-028 · Selectable navigation list

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Useful for project and agent session sidebar.

**Acceptance:** Implement selectable navigation list entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-029 · Tree view and hierarchy component

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Folder and agent hierarchy with keyboard navigation.

**Acceptance:** Implement tree view and hierarchy component entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** UI-028

### UI-030 · Data table sorting and pagination

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** High-level data operations; lower-level table layout remains Core.

**Acceptance:** Implement data table sorting and pagination entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-031 · Virtualized list and scroll anchoring

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Do not hold huge transcripts as a permanent DOM tree.

**Acceptance:** Navigate 10k item transcript with bounded live nodes; scroll anchor survives append/prepend and selection; responsiveness measured on native hosts.

**Dependencies:** INTERACTION-006, DOM-017, DOM-007

### UI-032 · Pagination helpers

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Data paging must not become Core policy.

**Acceptance:** Implement pagination helpers entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-033 · Breadcrumbs and step indicators

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Navigation presentation for applications.

**Acceptance:** Implement breadcrumbs and step indicators entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-034 · Command palette

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Advanced combined input/list/dialog component.

**Acceptance:** Implement command palette entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-035 · Toolbar and status bar

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Pure component layout above Core windows.

**Acceptance:** Implement toolbar and status bar entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-036 · Application shortcut manager

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Map generic key events to app commands, optional conflict handling.

**Acceptance:** Implement application shortcut manager entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-037 · Responsive component rules

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** CSS-first helpers for sidebars/panels and narrow windows.

**Acceptance:** Implement responsive component rules entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-038 · UI preferences storage adapter

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Optional persistence provider; Core does not store business data.

**Acceptance:** Implement ui preferences storage adapter entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-039 · Static chart rendering adapter

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Accept SVG/image from existing Python plotting libs.

**Acceptance:** Implement static chart rendering adapter entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-040 · Image gallery and viewer

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Images plus navigation, zoom if Core primitives suffice.

**Acceptance:** Implement image gallery and viewer entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-041 · OS notification convenience wrapper

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Friendly wrapper around platform capability, not a new OS backend.

**Acceptance:** Implement os notification convenience wrapper entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-042 · Internationalized labels and formatting

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Application selects locale; components only consume formatters.

**Acceptance:** Implement internationalized labels and formatting entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-043 · Accessible pattern implementations

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Keyboard and ARIA behavior must match supported Core semantics.

**Acceptance:** Implement accessible pattern implementations entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

**Dependencies:** INTERACTION-003, INTERACTION-017

### UI-044 · Template/component composition from files

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Keep reusable HTML/CSS files inspectable.

**Acceptance:** Implement template/component composition from files entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-045 · Managed async task and progress helpers

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** User tasks belong above owner-post primitive.

**Acceptance:** Implement managed async task and progress helpers entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-046 · PowerShell convenience components

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.2` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Parallel experience through separate module; avoid embedded Python dependency.

**Acceptance:** Implement powershell convenience components entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

### UI-047 · LLM-friendly component API reference

**Owner:** Optional UI / Optional / UI Library · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Ship stable examples and source-level usage rules for coding agents.

**Acceptance:** Implement llm-friendly component api reference entirely in the separately installable UI layer over public Core primitives; verify keyboard/state/lifecycle handling with optional package installed and Core-only tests without it.

## Optional / Specialized Extensions (10)

### EXT-001 · Terminal emulator and PTY adapter

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Only build when terminal-specific performance/input primitives are demonstrated.

**Acceptance:** Proof of concept for terminal emulator and pty adapter in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-002 · Multi-language code editor

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Syntax, folding and editor state exceed basic text inputs.

**Acceptance:** Proof of concept for multi-language code editor in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-003 · Rich-text WYSIWYG editor

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** Require a separate editing surface and selection model.

**Acceptance:** Proof of concept for rich-text wysiwyg editor in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-004 · Interactive chart and plotting engine

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** No GPU chart engine in minimal Core.

**Acceptance:** Proof of concept for interactive chart and plotting engine in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-005 · Graph and diagram explorer

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Node/edge hit testing and pan/zoom are domain components.

**Acceptance:** Proof of concept for graph and diagram explorer in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-006 · Map and geographic layers

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** Do not add tile networking to renderer.

**Acceptance:** Proof of concept for map and geographic layers in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-007 · Audio and video players

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** OS decoder/media backend may justify separate extension.

**Acceptance:** Proof of concept for audio and video players in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-008 · 3D scene and WebGL alternative

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** Native graphics extension should not imply browser JS.

**Acceptance:** Proof of concept for 3d scene and webgl alternative in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-009 · PDF/document viewer

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `extension-backlog` · **Priority:** `P2` · **Old evidence:** `none`

**Why:** Independent renderer or read-only integration with document selection.

**Acceptance:** Proof of concept for pdf/document viewer in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

### EXT-010 · Custom widget/plugin registration

**Owner:** Extension / Optional / Specialized Extensions · **Current 0.2:** `absent` · **Target:** `later` · **Priority:** `P3` · **Old evidence:** `none`

**Why:** Avoid speculative plugin architecture before a second external implementation.

**Acceptance:** Proof of concept for custom widget/plugin registration in its own optional distribution; show an independent app consumer and document native dependencies, performance and accessibility limits.

## Application Owned / Not UI4ME (12)

### APP-001 · ACP JSON-RPC session client

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Agent protocol must not enter Core or UI convenience package.

**Acceptance:** Show acp json-rpc session client in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-002 · SSE and HTTP transport

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Use asyncio, HTTPX or any app-selected client.

**Acceptance:** Show sse and http transport in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-003 · WebSocket/API backend

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Application chooses endpoint, auth and retry policy.

**Acceptance:** Show websocket/api backend in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-004 · Agent subprocess launch and permissions

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Security policy is application-specific and external to UI.

**Acceptance:** Show agent subprocess launch and permissions in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-005 · Model/provider selection

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Core must know nothing about LLM vendors.

**Acceptance:** Show model/provider selection in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-006 · Project and agent-session persistence

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Databases and schemas are app-owned.

**Acceptance:** Show project and agent-session persistence in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-007 · User authentication and RBAC

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Multi-user infrastructure is not a UI renderer feature.

**Acceptance:** Show user authentication and rbac in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-008 · Business validation and application rules

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** UI library can show validation, not decide business outcome.

**Acceptance:** Show business validation and application rules in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-009 · Application navigation/routes

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Optional routing helper possible, but route history remains app-owned.

**Acceptance:** Show application navigation/routes in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-010 · Secret storage and credential flows

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** Use OS/keyring or app-selected security libraries.

**Acceptance:** Show secret storage and credential flows in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-011 · Telemetry consent and analytics

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** No silent telemetry in Core.

**Acceptance:** Show telemetry consent and analytics in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

### APP-012 · Agent streaming aggregation policy

**Owner:** Application / Application Owned / Not UI4ME · **Current 0.2:** `outside` · **Target:** `app-owned` · **Priority:** `NA` · **Old evidence:** `none`

**Why:** App chooses stream granularity; UI helper may coalesce display changes.

**Acceptance:** Show agent streaming aggregation policy in an independent consumer without adding its protocol, storage or policy to UI4ME Core or the optional component package.

## Delivery / Quality and Ecosystem (17)

### QA-001 · Linux KDE Wayland native acceptance

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `not-qualified` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Validate actual compositor events and screenshots, not only headless tests.

**Acceptance:** Exercise actual KDE/Wayland interaction and capture screenshots from the installed package, not only headless raster; distinguish person/automated observations.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:17-33` · exact match line 20: `pub type Lifecycle = WindowState;` · partial-or-related · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-platform/tests/platform_lifecycle_t3.rs:43-56`

### QA-002 · Windows x64 native acceptance

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `not-qualified` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `partial-or-related`

**Why:** Cross-check of code is not native execution.

**Acceptance:** Build and link on actual Windows MSVC host; interact through Windows desktop from installed wheel/module and collect matching artifact hashes.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-platform/src/window.rs:17-33` · exact match line 20: `pub type Lifecycle = WindowState;` · partial-or-related · file-lead

### QA-003 · Installed Python wheel consumer

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Candidate must work outside checkout with its bundled library.

**Acceptance:** Produce repeatable source/artifact-bound evidence for installed python wheel consumer; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `tools/installed_consumer.py:21-37` · exact match line 24: `def selected_wheel(root: Path, target: str) -> Path:` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `tools/installed_consumer.py:1-14`

### QA-004 · Installed PowerShell module consumer

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Validate correct PS version, assembly load and shutdown.

**Acceptance:** Produce repeatable source/artifact-bound evidence for installed powershell module consumer; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `tools/installed_psmodule.ps1:52-68` · exact match line 55: `Import-Module (Join-Path $copy 'Ui4me.psd1') -ErrorAction Stop -Force` · implementation-anchor · symbol-or-code

**Related old regression lead (not verified):** `tools/installed_psmodule.ps1:1-14`

### QA-005 · C ABI independent consumer

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Keep backward ABI compatibility and error semantics.

**Acceptance:** Produce repeatable source/artifact-bound evidence for c abi independent consumer; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/tests/abi_conformance.rs:27-43` · exact match line 30: `fn st(c: Code) -> i32 {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-ffi/tests/abi_conformance.rs:208-221`

### QA-006 · Pinned dependency and source provenance

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Record exact source, fonts, patches and binary identity.

**Acceptance:** Produce repeatable source/artifact-bound evidence for pinned dependency and source provenance; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/src/version.rs:4-20` · exact match line 7: `pub const ABI_MAJOR: u32 = 0;` · implementation-anchor · file-lead

### QA-007 · Screen reader accessibility acceptance

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `not-qualified` · **Target:** `0.4` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Real assistive technology with keyboard and names/roles/state.

**Acceptance:** Produce repeatable source/artifact-bound evidence for screen reader accessibility acceptance; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-a11y/src/tests.rs:9-25` · exact match line 12: `fn rendering(&self, element: NodeId) -> Rendering {` · implementation-anchor · file-lead

### QA-008 · Scoped WPT conformance gates

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.5-core` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Target in-scope standards, do not claim all of WPT.

**Acceptance:** Produce repeatable source/artifact-bound evidence for scoped wpt conformance gates; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-oracle/src/harness.rs:34-50` · exact match line 37: `pub struct HarnessError {` · implementation-anchor · file-lead

### QA-009 · Pixel oracle and text geometry comparisons

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** No false PASS from matching both paths with same defect.

**Acceptance:** Produce repeatable source/artifact-bound evidence for pixel oracle and text geometry comparisons; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-oracle/src/compare/pixels.rs:19-35` · exact match line 22: `pub struct DeviceRect {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-oracle/tests/fixture_validation.rs:135-148`

### QA-010 · Focus and callback fault injection

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Test panic, callback reentry, stale handles and rejection.

**Acceptance:** Produce repeatable source/artifact-bound evidence for focus and callback fault injection; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/tests/panic_containment.rs:22-38` · exact match line 25: `fn st(c: Code) -> i32 {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-ffi/tests/panic_containment.rs:3-16`

### QA-011 · Long-session resource and worker soak

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Bounded thread count and decoded-memory retention across sessions.

**Acceptance:** Produce repeatable source/artifact-bound evidence for long-session resource and worker soak; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-resources/tests/shutdown.rs:18-34` · exact match line 21: `unsafe fn alloc(&self, l: Layout) -> *mut u8 {` · implementation-anchor · file-lead

**Related old regression lead (not verified):** `engine/crates/ui4me-resources/tests/shutdown.rs:77-90`

### QA-012 · App consumer contract examples

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `implementation-source-present`

**Why:** Raw HTML app must run with zero optional UI package dependencies.

**Acceptance:** Produce repeatable source/artifact-bound evidence for app consumer contract examples; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-integration-tests/src/bin/ui4me-render.rs:44-60` · exact match line 47: `fn parse_args() -> Result<Args, String> {` · implementation-anchor · file-lead

### QA-013 · Optional UI package compatibility matrix

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `absent` · **Target:** `ui-0.1` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** UI library tests against declared Core minimum and newest supported.

**Acceptance:** Produce repeatable source/artifact-bound evidence for optional ui package compatibility matrix; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Dependencies:** BIND-001

### QA-014 · Release and upgrade qualification

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `implementation-source-present`

**Why:** Verify 0.1-to-0.2 and later upgrade without republishing in tests.

**Acceptance:** Build same-source Linux/Windows packages, verify installed consumers in isolation and 0.1→candidate upgrade; do not pass on skipped or missing mandatory evidence.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-ffi/tests/abi_manifest.rs:12-28` · exact match line 15: `fn manifest_is_generated_from_the_header_and_committed() {` · implementation-anchor · file-lead

### QA-015 · Benchmarks for update and cold frame

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.5-core` · **Priority:** `P2` · **Old evidence:** `implementation-source-present`

**Why:** Performance comparisons should be repeatable and thresholded.

**Acceptance:** Produce repeatable source/artifact-bound evidence for benchmarks for update and cold frame; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

**Original old-source anchors (candidate code, not proof of qualification):**

- `engine/crates/ui4me-pipeline/src/clock.rs:28-44` · exact match line 31: `pub const TICK_TARGET_MS: f64 = 16.0;` · implementation-anchor · file-lead

### QA-016 · Docs, examples and agent-readable contracts

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `partial` · **Target:** `0.3` · **Priority:** `P1` · **Old evidence:** `none`

**Why:** Publish one status document, supported features and source map.

**Acceptance:** Produce repeatable source/artifact-bound evidence for docs, examples and agent-readable contracts; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

### QA-017 · No-JavaScript/no-webserver core policy

**Owner:** Delivery / Delivery / Quality and Ecosystem · **Current 0.2:** `present` · **Target:** `0.2-harden` · **Priority:** `P0` · **Old evidence:** `none`

**Why:** Prevent accidental insertion of a browser runtime into required package.

**Acceptance:** Produce repeatable source/artifact-bound evidence for no-javascript/no-webserver core policy; distinguish pass, fail, unavailable and unrun; reject stale or missing mandatory checks.

