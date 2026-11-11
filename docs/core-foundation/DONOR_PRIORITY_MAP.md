# Donor priority map — exact original source locations

**Source:** `reference/data/features.json` from the supplied 2026-11-11 architecture research. These are search leads in the **old archive**, not proof of working support in current `main`, and not instructions to migrate every record. Start with `ACCEPTANCE.md` and current code.

| Slice | Feature ID / capability | Old source anchor(s) | 0.2 research observation |
| --- | --- | --- | --- |
| 0.3 S1 | **DOM-004** Public CSS selector query | `engine/crates/ui4me-style/src/query.rs:221-237` | missing |
| 0.3 S1 | **DOM-005** Text content read and write | `engine/crates/ui4me-dom/src/chardata.rs:15-31` | partial |
| 0.3 S1 | **DOM-007** Incremental HTML insertion | `engine/crates/ui4me-dom/src/parse/fragment.rs:96-112` | missing |
| 0.3 S1 | **DOM-008** Remove and move nodes | `engine/crates/ui4me-dom/src/mutate/remove.rs:21-37` | missing |
| 0.3 S1 | **DOM-011** Read attributes and class lists | `engine/crates/ui4me-dom/src/attrs.rs:114-130` | missing |
| 0.3 S1 | **DOM-013** Document fragments and staging | `engine/crates/ui4me-dom/src/parse/fragment.rs:121-137` | partial |
| 0.3 S1 | **DOM-018** DOM resource retirement | `engine/crates/ui4me-dom/src/retain.rs:21-37` | partial |
| 0.3 S2 | **DOM-009** Atomic mutation batch | `engine/crates/ui4me-dom/src/batch/exec.rs:18-34` | missing |
| 0.3 S2 | **DOM-016** DOM mutation journal | `engine/crates/ui4me-dom/src/journal.rs:54-70` | internal |
| 0.3 S2 | **INTERACTION-015** Default actions and cancellable events | `engine/crates/ui4me-interaction/src/dispatch.rs:28-44` | partial |
| 0.3 S2 | **QA-010** Focus and callback fault injection | `engine/crates/ui4me-ffi/tests/panic_containment.rs:22-38` | partial |
| 0.3 S3 | **DOM-017** Read-only element geometry | `engine/crates/ui4me-runtime/src/geometry_query.rs:48-64` | missing |
| 0.3 S3 | **INTERACTION-006** Programmatic scroll_to and scroll_by | `engine/crates/ui4me-interaction/src/scroll.rs:183-199` | missing |
| 0.3 S3 | **INTERACTION-007** Scroll into view and focus scrolling | `engine/crates/ui4me-interaction/src/scroll.rs:8-24` | missing |
| 0.3 S3 | **HOST-010** DPI scale and geometry events | `engine/crates/ui4me-platform/src/window.rs:136-152` | partial |
| 0.3 S4 | **TEXT-007** Read-only document text selection | `engine/crates/ui4me-text/src/paragraph/frozen.rs:199-215` | missing |
| 0.3 S4 | **TEXT-008** OS clipboard text operations | `engine/crates/ui4me-interaction/src/editing/clipboard.rs:30-46` | partial |
| 0.3 S4 | **HOST-011** OS clipboard read/write service | `engine/crates/ui4me-platform/src/clipboard/mod.rs:9-25` | partial |
| 0.3 S4 | **TEXT-011** Text metrics and character position queries | `engine/crates/ui4me-text/src/metrics.rs:28-44` | missing |
| 0.3 S5 | **TEXT-016** Caching and epoch retirement | `engine/crates/ui4me-text/src/paragraph/shaped.rs:184-200` | internal |
| 0.3 S5 | **BIND-011** Resource budgets and bounded admission | `engine/crates/ui4me-resources/src/worker.rs:27-43` | partial |
| 0.3 S5 | **QA-011** Long-session resource and worker soak | `engine/crates/ui4me-resources/tests/shutdown.rs:18-34` | partial |
| 0.3 S6 | **BIND-014** Public Python API ergonomic parity | `bindings/python/src/ui4me/document.py:18-34` | partial |
| 0.3 S6 | **BIND-015** Public PowerShell API ergonomic parity | `bindings/powershell/src/Ui4me/Document.cs:15-31` | partial |
| 0.3 S6 | **QA-012** App consumer contract examples | `engine/crates/ui4me-integration-tests/src/bin/ui4me-render.rs:44-60` | partial |
| 0.3 S6 | **QA-016** Docs, examples and agent-readable contracts | No anchored donor; inspect current repo | partial |
| 0.4 S7 | **INTERACTION-009** Native select/option and listbox | `engine/crates/ui4me-dom/src/select.rs:16-32` | unpromoted |
| 0.4 S7 | **INTERACTION-013** Dialog top layer and focus trapping | `engine/crates/ui4me-interaction/src/dialog.rs:34-50` | unpromoted |
| 0.4 S7 | **INTERACTION-014** Label association and form semantics | `engine/crates/ui4me-dom/src/forms.rs:18-34` | partial |
| 0.4 S7 | **INTERACTION-012** Details and summary activation | `engine/crates/ui4me-interaction/src/activation.rs:150-166` | unpromoted |
| 0.4 S7 | **DOM-019** HTML form-associated control state | `engine/crates/ui4me-dom/src/control_state.rs:59-75` | partial |
| 0.4 S8 | **HOST-005** Minimize maximize restore | `engine/crates/ui4me-platform/src/window.rs:14-30` | missing |
| 0.4 S8 | **HOST-006** Show hide focus raise window | `engine/crates/ui4me-platform/src/window.rs:108-124` | missing |
| 0.4 S8 | **HOST-007** Fullscreen and window decoration | `engine/crates/ui4me-platform/src/window.rs:87-103` | missing |
| 0.4 S8 | **HOST-008** Window icons and minimum size constraints | `engine/crates/ui4me-platform/src/window.rs:14-30` | missing |
| 0.4 S8 | **HOST-009** Screen and monitor enumeration | `engine/crates/ui4me-platform/src/window.rs:17-33` | missing |
| 0.4 S9 | **HOST-012** Native file picker dialog | `engine/crates/ui4me-ffi/src/api/dialog.rs:13-29` | missing |
| 0.4 S9 | **HOST-013** Native folder picker and save dialog | `engine/crates/ui4me-ffi/src/api/dialog.rs:13-29` | missing |
| 0.4 S9 | **HOST-014** OS drag and drop files | `engine/crates/ui4me-platform/src/input.rs:21-37` | missing |
| 0.4 S10 | **CSS-004** Media queries and responsive styles | `engine/crates/ui4me-style/src/device.rs:1-17` | partial |
| 0.4 S10 | **CSS-007** CSS Grid basics | `engine/crates/ui4me-layout/src/box_tree/typed_layout.rs:1-16` | unpromoted |
| 0.4 S10 | **CSS-009** Relative and absolute positioning | `engine/crates/ui4me-layout/src/coordinator/oof.rs:34-50` | partial |
| 0.4 S10 | **CSS-025** Text overflow and ellipsis | `engine/crates/ui4me-layout/src/ifc/container.rs:505-521` | partial |
| 0.4 S11 | **INTERACTION-017** Accessibility semantic tree | `engine/crates/ui4me-a11y/src/lib.rs:22-38` | unpromoted |
| 0.4 S11 | **INTERACTION-018** Accessibility actions and state updates | `engine/crates/ui4me-runtime/src/a11y.rs:8-24` | unpromoted |
| 0.4 S11 | **QA-007** Screen reader accessibility acceptance | `engine/crates/ui4me-a11y/src/tests.rs:9-25` | not-qualified |

## Reading rule

Where an old path shows `engine/crates/...`, locate it under the old archive's internal `ui4me-main/` root. The anchor may cover only one routine, and other code can depend on the original architecture. Read the current public surface in `include/ui4me.h`, `crates/ui4me-core/src/protocol.rs`, current bindings and tests before porting. Never import old host/thread lifecycle wholesale.

For other optional items, query `reference/data/features.json` by feature ID. Do not turn this map into a required 0.4 feature count.
