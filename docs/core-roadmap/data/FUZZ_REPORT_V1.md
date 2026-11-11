# Core 1.0 F1104: conformance, fuzz and negative gate report

Records the harnesses, their runs, every finding and the residual risk. Host: Linux x86_64,
release profile, `nice -n 10`, pinned stable toolchain. Harnesses are `#[ignore]`d tests (no new
dependencies; a xorshift PRNG; seeds and budgets come from environment variables). The regression
tests for every fixed finding and the foreign-boundary contracts are ordinary tests.

## Scope and honesty notes

- **Conformance (the "curated WPT slice")**: there is no WPT harness in the repository and none was
  imported. Conformance is covered by the existing renderer fixtures that run in every
  `cargo test -p ui4me-renderer --lib`: `layout_conformance_tests` (17), `framework_fixtures_tests`
  (Bootstrap/Tailwind/Mantine-style, 4, phone/tablet/desktop), `svg_tests` (20) with the SVG corpus
  (`crates/ui4me-assets/tests/fixtures/resources-svg`), `visual_tests` (15), `bidi_tests` (8),
  `unicode_corpus_tests`, the DOM parser corpus (`crates/ui4me-document/tests/parser_corpus.rs`)
  and the CSS feature profile table. F1104 adds no WPT claim.
- **Toolchain**: `cargo-fuzz` needs nightly and the toolchain is pinned (`rust-toolchain.toml`), so
  these are deterministic mutation fuzzers inside the crates instead (coverage-blind: they mutate
  real corpora, they do not steer by coverage). The same seeds reproduce the same cases.
- The harnesses ran on Linux only. They compile on Windows, but `/proc`-based memory checks read 0
  there and symlink cases are `cfg(unix)`.

## Harnesses

Run any of them (release, one at a time):

    UI4ME_FUZZ_SECS=300 UI4ME_FUZZ_SEED=1 nice cargo test -p ui4me-renderer --lib --release \
        fuzz_gate::harness -- --ignored --nocapture --test-threads=1      # html_pipeline, css, dom_sequences
    UI4ME_FUZZ_SECS=300 nice cargo test -p ui4me-renderer --lib --release \
        fuzz_resources::harness -- --ignored --nocapture                  # images
    UI4ME_FUZZ_SECS=300 nice cargo test -p ui4me-core --lib --release \
        fuzz_gate::harness -- --ignored --nocapture --test-threads=1      # protocol, abi_sequences

Environment: `UI4ME_FUZZ_SEED` (default 1), `UI4ME_FUZZ_ITERS` (cases; default 2000, protocol
20000, ABI 300), `UI4ME_FUZZ_SECS` (wall budget, overrides the case count), `UI4ME_FUZZ_TIMEOUT_MS`
(watchdog, default 30000), `UI4ME_FUZZ_OUT` (directory where failing inputs are saved).
A case runs on a worker thread with an 8 MiB stack; a panic or a watchdog timeout is a finding.

| # | Harness | Source | What it does |
|---|---|---|---|
| 1 | `fuzz_gate::harness_html_pipeline` | renderer | Mutates the repo's HTML/SVG corpus plus built-in documents (flip/insert/delete/duplicate/splice, dictionary tokens, nesting bombs to 600 levels, random bytes, 120 KB cap), parses, renders at random size/scale, sends pointer/wheel/key/text/IME input, reads the accessibility tree, serializes, paginates. |
| 2 | `fuzz_gate::harness_css` | renderer | Mutated stylesheets from the corpus through `add_stylesheet` (up to 4 sheets, 60 KB), `replace_stylesheet`/`remove_stylesheet` (second removal must be the stale error), mutated `style=` attributes, `computed_style`, render. Asserts sheet diagnostics <= 50 and total diagnostics <= 128. |
| 3 | `fuzz_gate::harness_dom_sequences` | renderer | 40-160 random public-facade operations per sequence (insert/replace/remove/move, set text/attribute/value/checked, append, trim, atomic `apply_batch` with a before/after document comparison, popover and dialog toggles, selection and copy, focus, scroll, viewport, pagination, stylesheet attach, select options, text rects), interleaved with input and renders. After each step: every recorded node reference either resolves to the node it named (same reference, same id) or is rejected with the stale code (4); queued events that are still "current" name existing elements; the node budget holds. |
| 4 | `fuzz_resources::harness_images` | renderer | Mutated PNG/JPEG/GIF/WebP/BMP/SVG (the codec and SVG fixtures plus crafted header bombs: 65535 x 65535 PNG/GIF/JPEG, 2^24 x 2^24 WebP, 2^31 PNG, 1e9 SVG, blur 1e9) as `data:` URLs and local files, used by `<img>`, CSS `background`, `<picture>/srcset` and SVG `<image>`; render after the resource workers settle. Asserts the process peak RSS grows < 1.5 GiB. |
| 5 | `fuzz_gate::harness_protocol` (core) | core | Random JSON into `Session::command` for every one of the 104 command variants (the catalogue is parsed from `protocol.rs`, fields typed by their Rust types, with wrong types, missing and unknown fields, non-objects, stale and random window ids; file paths confined to a scratch directory). Every result is `Ok` or an error with a registered code 1-9 and a message; the runtime must not be poisoned. |
| 6 | `fuzz_gate::harness_abi_sequences` (core) | core | Per session: create with a hostile callback, open windows, post, run, then in every callback a random choice of stop, post, re-entrant command, destroy, re-entrant run, create, complete, wrong-thread command/run/destroy, open, timer, close, reserve, error return (-1) or close veto (1). After run: post/run/double destroy/stale id codes are checked. |
| 7 | `fuzz_resources::untrusted_resources_are_not_fetched_or_escaped` (regular test) | renderer | Red team: 33 hostile documents (remote http/https/protocol-relative URLs in `img`, `srcset`, `picture`, `input type=image`, `link`, `@import`, CSS `url()` in background/list-style/border-image/cursor/content/mask, `@font-face`, SVG `image`/`use`/fill/filter, SVG files with remote and escaping references, video poster, iframe/object/embed, meta refresh/base; absolute `file:` outside the root, `..` traversal plain/encoded/backslash/in CSS/in `@import`, symlink file and directory escaping the root, `file://host/`, ftp/ws/blob/about/javascript). A loopback listener counts connections; a solid red PNG outside the root must never appear in the framebuffer (control: the same PNG inside the root does). |

Regression and boundary tests added (all in normal test runs):
`fuzz_resources::{untrusted_resources_are_not_fetched_or_escaped, header_bombs_are_rejected_before_allocation,
failed_file_images_settle_instead_of_retrying_every_frame}` (renderer) and
`fuzz_gate::{abi_rejects_null_invalid_and_stale_arguments_with_codes, abi_wrong_thread_calls_are_refused_and_stop_is_safe,
abi_callback_errors_destroy_and_post_after_stop_have_defined_codes}` (core).

## Runs

Seed 11, release, six processes in parallel (16 cores, `nice`), 2026-11-11:

| Harness | Budget | Result |
|---|---|---|
| html_pipeline | 600 s | 1146 cases, slowest 3.1 s, 0 findings |
| css | 480 s | 538 cases, slowest 2.7 s, 0 findings |
| dom_sequences | 720 s | 136 sequences (about 14 000 operations), slowest 17.6 s, 0 findings |
| images | 480 s | 1811 cases, slowest 0.55 s, peak RSS 6.6 MiB -> 67.2 MiB, 0 findings |
| protocol | 300 s | 1 498 380 commands (404 816 ok, 1 093 564 errors: 1 004 604 invalid-argument, 59 429 stale, 11 573 state, 11 552 limit, 6 383 io, 23 thread), 0 findings |
| abi_sequences | 300 s | 1423 sessions (894 `run` returned ok, 529 returned the callback error code 7), 0 findings |

About 48 CPU-minutes in about 12 minutes wall. Smoke runs with seed 1 (60-3000 cases each) were
also clean. The red-team test found the one real defect below before the long runs.

## Findings

| # | Severity | Finding | Fix | Regression test |
|---|---|---|---|---|
| F-1 | P2 (resource churn, not an escape) | A file image that failed to load (missing, outside the document root, truncated/undecodable, over a limit) was restarted on every frame: `ResourceTable::begin` treated a `Broken` request with the same URL as changed, and the renderer asks for the image again on each layout. The document therefore stayed "pending" forever (`has_pending_resources` true, `next_wake_in` 50 ms), re-ran the failing load on a worker every frame (a decompression bomb or a slow undecodable file would re-run its decode each time), and a host would wake forever. Found by the red team (denied `file:` and `..` cases never settled). | `crates/ui4me-assets/src/request.rs`: a `Broken` request with the same URL and density is `Unchanged`; a changed URL/density or `begin_again` (bundle replaced) still starts a new load. Only `Canceled` restarts as before. All `ui4me-assets` tests pass unchanged. | `failed_file_images_settle_instead_of_retrying_every_frame` |

No P0/P1: no panic, hang, memory-unsafe behaviour, stale-identity aliasing, malformed-input escape or
uncontrolled resource access was found. The access controls held in every red-team case: no remote
URL was fetched (zero connections to the trap listener), no file outside the root (absolute,
`..`, encoded, backslash, symlink) rendered, and active elements (`iframe`, `object`, `embed`) are
refused at parse time.

## Triaged non-issues

- `[]` (a JSON array) is accepted as a session config: serde reads the all-default struct from an
  empty sequence. Harmless (same defaults as `{}`); not pinned by a test.
- An idle headless `run` waits for input forever by design; the ABI harness stops it from another
  thread (which also exercises the cross-thread stop).
- Worst-case latencies (DOM sequence 17.6 s for ~160 operations with renders, 3 s for a 120 KB
  mutated page) are CPU contention plus large pathological inputs, below the 30-60 s watchdog; no
  case was unbounded. They are possible follow-up perf work, not blockers.
- The pixel check for "no outside content" uses a pure-red PNG; an image that failed *silently*
  by being tinted would pass. The connection trap and the settled/broken state cover the rest.

## Residual risks

- Mutation without coverage guidance finds shallow bugs; run a cargo-fuzz/AFL campaign on a
  nightly toolchain outside this pinned repo for deeper parser coverage (html5ever, stylo, the
  image crates and usvg are third-party and fuzzed upstream).
- The DOM harness uses string ids; very large documents (65 536 nodes) are bounded by limits but
  not stressed by it. The soak (F1106) covers long-running growth.
- Windows was not fuzzed. Path semantics (drive letters, UNC, reserved names, junctions) have
  their own cases in `crates/ui4me-assets/tests/policy_windows.rs`; the red-team test builds its
  `file:` URLs with `Url::from_file_path` and should be run once on Windows.
- Print/PDF paths, native dialogs and the OS clipboard are not reachable from these headless
  harnesses; they are covered by the native probes.
