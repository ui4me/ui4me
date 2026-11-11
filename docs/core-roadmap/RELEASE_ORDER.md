# Version sequence, prerequisites and scope freeze

| Version | Intent | Gate | Dependencies |
| --- | --- | --- | --- |
| 0.5 | International keyboard, IME, assistive correctness | Native input and screen-reader journeys; callback lifecycle | released 0.4 |
| 0.6 | Public DOM/CSS/HTML completeness | Both bindings/C support serialization, stylesheet, text geometry, validity, file input | 0.5 owner-thread/input invariants |
| 0.7 | System menus, tray, notifications, global hotkeys, platform capabilities | Real Windows/KDE desktop services; graceful restrictions | 0.6 public command contract |
| 0.8 | Plain text editing, pointer/touch, scroll behaviors, host interaction polish | Interactive editable/selectable controls without leaks | 0.5 input + 0.6 events |
| 0.9 | CSS animations, SVG, typography, modern visual semantics | Updated CSS profile and golden fixtures | 0.8 event/scroll model |
| 0.10 | Printing, safe rich editing, scalable layout, GPU option | CPU correctness, native print, renderer failover and integrated long-run tests | 0.9 paint/selection model |
| 1.0 | Stable ABI, supported profile, security and release gate | Independent installed consumer and native Linux/Windows results | 0.5–0.10 complete |
| 1.1 | Optional macOS/ARM64 and extra language portability | Per-target native qualification before support claim | stable 1.0 ABI |

## Deciding whether already implemented

On every work item, inspect **current** code rather than blindly using 0.4 flags. If full functionality already exists, run only focused tests or inspect actual recent qualifying evidence and mark `SATISFIED_EXISTING` with source refs. If only an internal algorithm is present but no public ABI, status is `PARTIAL`, and expose the missing public contract. If platform fundamentally denies an operation, implement accurate capabilities and a safe documented alternative. For newly discovered needs, add a scoped work item with a stable ID; don't silently push work into Core without an ownership check.

## Backlog completeness semantics

This is a finite planned product profile, not an open-ended browser engine. Every original Core feature candidate is accounted for in `ORIGINAL_INVENTORY_RECONCILED.json`; additional explicit issues are in `WORK_ITEMS.json`; every non-On CSS profile row appears in `CSS_PROFILE_V0_4.json` for triage. `Off`/`Unavailable` does not itself imply it is desirable or feasible: classify future browser-only features as `INTENTIONALLY_UNSUPPORTED`, not silent omission. This preserves a complete decision trail while keeping 1.0 achievable.

## Release result vocabulary

- `NOT_STARTED`: uninspected feature or incomplete task.
- `SATISFIED_EXISTING`: present in current tree with genuine acceptance evidence, no change needed.
- `IMPLEMENTED_UNVERIFIED`: source added or internal code exists; no release qualification yet.
- `PASS`: exact source/artifact tested per acceptance.
- `FAIL`: executed test failed.
- `BLOCKED`: dependency/platform prevents acceptance; explicit evidence and fallback.
- `NOT_RUN`: no test performed.
- `DEFERRED_APPROVED`: product-level deliberate exclusion with justification; cannot be used to hide a required 0.x item.

A version is GO only after its required tasks are `PASS` or evidence-backed `SATISFIED_EXISTING`, with documented OS-impossible semantics and no P0/P1 defects. GO is a development gate; external publishing is independent authorization.
