# Architecture decisions

These are the selected contracts for the foundation, with acceptance still
pending. They are intentionally smaller than a general application framework.

## One product repository, separate packages

The engine, C header, bindings, examples, specifications and CI share a commit
and version. Python and PowerShell are independently installable distributions;
separate registry packages do not require separate source repositories. An ABI
change and both wrapper changes can be reviewed and tested together.

The organization Pages repository is deployment output only. Editable
documentation remains here. There is no second engine repository or parallel
development history to merge later.

## Responsibilities

| Layer | Owns | Does not own |
| --- | --- | --- |
| Binding facade | Idiomatic API, host exceptions, callback roots, package loading | Native ownership rules or a second renderer |
| Runtime | Sessions, windows, posted work, timers, shutdown | Registries, release promotion |
| Platform adapter | Event loop, native windows, input, presentation surfaces | PowerShell runspaces or Python Futures |
| Small renderer | Document state, viewport and pixels | Process exit or package discovery |
| Developer tooling | Builds, packaging, evidence, reports and publishing | Application callbacks |

One Rust crate is sufficient initially. Module boundaries are preferable to a
large crate graph without independent ownership or reuse needs.

## Native host and language hosts

Keep the engine in process. No IPC broker is required for trusted applications.
The process native owner survives an application session so same-process native
reuse can work. PowerShell retains one owner thread and creates session runspaces
there; Python uses its documented owner. The active session is exclusive.

The C ABI uses integer session/window identities, copied UTF-8 JSON commands and
events, stable status codes and explicit borrowed-string lifetimes. The small
JSON protocol makes foreign-language wrappers inspectable without exposing Rust
layout. It adds serialization work, which is acceptable for this control-level
API. It is not intended for streaming every pixel or bulk data.

Commands issued inside callbacks must not deadlock: callbacks run outside runtime
locks and native effects are applied by the event-loop owner. Post always queues.
See [native contract](native-contract.md) for exact rules and limits.

## Failure and cancellation

Stop is a protocol, not process termination. Queued work settles, window resources
are released, and the binding reports the result. Arbitrary user computation
cannot be forcibly cancelled safely. Host poisoning after a native invariant
failure is more honest than allowing another session on uncertain state.

A snapshot of the software framebuffer helps compare renderer output. Desktop
composition, focus and input need real desktop evidence. The two are labeled
separately in the test report.

## Package ownership

Every package carries its matching native payload; no ambient current-directory
or PATH search is used. `UI4ME_NATIVE_LIB` is an explicit contributor override,
and installed-consumer tests clear it. Keep wheel platform tags even for ctypes.
Only wheels are intended for PyPI until a complete native source-install contract
is designed and tested.

Each host produces a platform candidate. Assembly produces one PowerShell module
with both native payloads, two Python wheels and native SDK archives. Final file
hashes are calculated after assembly, before installed acceptance. The publisher
transfers those bytes without rebuilding.

## Deliberate tradeoffs

- Native correctness and beginner APIs take priority over supporting arbitrary external event loops.
- One active session simplifies ownership; multiple windows remain available within it.
- The basic renderer makes the lifecycle observable but is not the final rendering product.
- Manual desktop acceptance is suitable for the first release, provided its procedures, operator and captures are explicit.
- Checksums provide integrity, not proof that hand-written test results are true. Trusted CI and release review establish origin.
- The source reconstruction is unexecuted. Dependency locks, compiler compatibility and platform runtime behavior must be established locally.

## Reference decisions

The design adopts explicit ownership and close semantics informed by Qt/GTK,
owner dispatch and embedding lessons from Slint, lifecycle/packaging separation
from Electron/Tauri, and package-manager publication practices. None of those
frameworks becomes a runtime dependency merely because its contract is useful.
See [source references](references.md) for primary documentation.
