# Core 0.3 → 0.4 progress (authoritative incremental ledger)

**Baseline:** Owner reports Core 0.2 is implemented and already running/tested. Publication workflow for 0.2 is being handled separately. No tests were executed when this handoff was assembled. Existing `docs/PROJECT_STATUS.md` may describe an earlier release-candidate snapshot.

**Working milestone:** 0.3, slice S6 (cross-binding contract, demo and desktop gate).

**0.3 status:** IN PROGRESS — S1–S5 done; S6 gate pending.

**0.4 status:** NOT STARTED by this handoff.

## Update convention (keep this short)

After each completed slice, append ONE concise entry with:

`Date | Git SHA | Slice | Changed files | Tests actually run + host/binding | Result PASS/FAIL/BLOCKED/NOT_RUN | Important limitations | Next slice`

Do not paste massive raw logs, long audit reports or all research feature records here. Actual build receipts stay in the project's existing evidence mechanism. An unchecked box in `ACCEPTANCE.md` is not proof that current code is missing a feature — first inspect current implementation and mark preexisting abilities only with evidence.

## Implemented slices

- 2026-11-11 | (S1 commit) | **S1 DOM mutation and identities** | `crates/ui4me-document/src/parse/fragment.rs` (checked `insertAdjacentHTML`), `crates/ui4me-renderer/src/document.rs` (insert_html/remove_element/move_element/get_text/get_attribute(s)/has_element/query_ids), `crates/ui4me-core/src/{protocol,runtime,tests}.rs`, Python `app.py` + `test_app.py`, PowerShell `App.cs` + `smoke.ps1`, contract in `docs/PROJECT_STATUS.md` | `cargo test -p ui4me-core dom_mutation` (Linux), `cargo test -p ui4me-document` (Linux), `dev.py test --suite unit` python 26/26 + powershell 24/24 (Linux headless) | PASS | Identity = HTML `id` (existing 0.2 model); elements without an ID are counted by `query` but not addressable. Whole-document validation per insert is O(N) — revisit in S5 with 10k-line logs (MAX_NODES 16384 also caps log size). Windows not run for this slice (no native change). | S2
- 2026-11-11 | (S2 commit) | **S2 Batching and events** | `ui4me-document/src/batch/exec.rs` (`Document::transaction` over the existing undo log), `ui4me-renderer/src/document.rs` (`DomOp`, `apply_batch`, single ops now share `apply_op`; `set_default_action` rules applied in `invoke`, `default_prevented` on events), `ui4me-core` protocol/runtime/tests, Python/PowerShell `batch` + `set_default_action` and tests | `cargo test -p ui4me-core --lib` 23/23, `cargo test -p ui4me-renderer --lib` 221/221, clippy core/renderer/document clean, `dev.py test --suite unit` python 28/28 + powershell 25/25 (Linux headless) | PASS | Cancellation is declarative (host rules), since binding callbacks run after dispatch. Batch excludes value/checked/focus. Stale targets: existing generational recheck, rules keyed by generational NodeId. | S3
- 2026-11-11 | (S3 commit) | **S3 Scroll and geometry** | `ui4me-renderer/src/document.rs` (scroll_state/to/by/into_view, element_rect, set_scroll_follow + follow applied before input/render/queries, set_viewport), `ui4me-core` protocol/runtime (`query` helper delivers scroll events; resize/scale apply viewport immediately)/tests, Python + PowerShell wrappers/tests | `cargo test -p ui4me-core --lib` 24/24 (incl. wheel-away, resize and scale 2.0), clippy clean, `dev.py test --suite unit` python 29/29 + powershell 26/26 (Linux headless) | PASS | Smooth scrolling not offered (instant only). Follow is vertical-end only. Native KDE/Windows scroll journeys deferred to the S6 milestone gate. | S4
- 2026-11-11 | (S4 commit) | **S4 Selection and clipboard** | new `ui4me-renderer/src/document/selection.rs` (DOM-anchored paragraph selection, hit testing via cluster extents, highlight blended after raster, word/paragraph multi-click, Ctrl+A/C), `document.rs` hooks, core protocol/runtime, Python/PowerShell wrappers + tests (PowerShell `$null`→`""` element handled) | `cargo test -p ui4me-renderer --lib` 222/222 (new drag/copy/password/mutation test), `cargo test -p ui4me-core --lib` 24/24, clippy clean, `dev.py test --suite unit` python 30/30 + powershell 27/27 (Linux headless) | PASS | No new donor code (donor had no document selection). Highlight is an overlay, not painted behind glyphs. No drag auto-scroll, no selectionchange event, bidi is logical-order. Native clipboard path is the existing 0.2 arboard path; real KDE/Windows copy is verified at the S6 gate. | S5
- 2026-11-11 | (S5 commit) | **S5 Sustained updates** | `ui4me-renderer/src/document.rs` (`append_text` with 4 KiB text-node chunking, `trim_children`, MAX_NODES 16,384→65,536), protocol/runtime (+ batch ops), bindings + tests, renderer soak test `sustained_log_and_chat_streams_stay_bounded` and ignored measurement `measure_long_log_append` | soak (10k streamed lines kept at 300 + 3 chat windows streaming tokens, focus/value/follow/selection preserved, arena < 2,000 live nodes) PASS release 4.6 s / debug 50 s; core 24/24; python 31/31 + powershell 28/28 (Linux headless) | PASS | **Known limitation (measured, release, this host):** style+layout+scene run over the whole document per change: one frame ≈ 10 ms @300 lines, 33 ms @1k, 250 ms @6k (layout ~105 ms, scene ~60 ms). Inserts stay ≤ 2 ms. Bounded retention via trim is the supported pattern; incremental append layout is a 0.5+ candidate. | S6

## Deferred non-blocking items

- Incremental layout for append-only containers (full relayout per change; see S5 numbers).
- Selection: no drag auto-scroll, no selectionchange event; highlight is an overlay.
- Host needed .NET SDK 10 (global.json) — installed user-locally at `~/.dotnet` (set `DOTNET_ROOT`/`PATH`).

## Hard blockers

None confirmed by this handoff. Do not fabricate blockers from unexecuted tests.
