# ui4me 0.1 foundation specification

Status: implementation candidate; acceptance pending. Product version: 0.1.0.

## Outcome

A contributor can clone or unzip one monorepo, build the current host's bindings,
run granular tests, create installable packages, inspect evidence and use the same
operations in CI. A consumer installs a Python wheel or PowerShell module that
contains its native library. The application opens a useful basic form, returns
control to its embedding process on completion, and can run another session on
the supported retained native owner.

Version 0.1 establishes this delivery and lifecycle contract. Rendering expansion
is separate work. The archive is not a promise that the contract has passed:
every acceptance scenario must run against this source's actual packages.

## Supported initial scope

- One product repository, proposed `ui4me/ui4me`.
- Organization documentation at `https://ui4me.github.io/` using a generated-output hosting repository.
- Rust native library and a narrow C ABI, Python and PowerShell first-party bindings.
- Windows x64 and Linux x86-64 package targets. Exact OS/backend/runtime support is earned by recorded acceptance, not inferred from metadata.
- Basic form rendering, input, multiple windows, resize, close veto, timers, deferred posts and diagnostics.
- Installed-package, unit/contract and native-interactive test layers.
- No renderer migration, browser engine, IPC broker, plugin framework, automatic updater or general installer generator.

## Lifetimes and ownership

The process host, application session, native window/document and language wrapper
have distinct lifetimes. One native owner thread remains fixed once the backend
is initialized. There is at most one active application session in a process.
Multiple windows belong to that session. Concurrent sessions and wrong-thread UI
mutation return actionable errors. Stale session/window IDs never reach a newer
generation. An accepted close is terminal for that native window.

Python's simple path uses its owner thread and a blocking `run()`. PowerShell's
simple path retains one hosted UI thread and creates a fresh runspace per
session. Arguments cross the PowerShell runspace boundary explicitly; caller
scope is not implicitly captured. A new application session can reuse the native
host, but a new native library version needs a new process.

## Startup

1. Locate the packaged native library using an explicit package-relative path.
2. Check ABI, platform and version identity before ordinary runtime operations.
3. Validate configuration and resources.
4. Acquire the supported native owner and create the session.
5. Realize windows, present the first frame and begin native input.

Library loading, session creation, frame submission and visible input readiness
are separate observations. Import must not open a window, change current working
directory or install a permanent signal handler. Startup failure releases owned
resources. An unrecoverable backend failure explicitly requires a fresh process.

## Work and callbacks

- Post is always deferred, including posts from the owner thread.
- A successful admission produces exactly one success, error or cancellation outcome.
- Queue saturation rejects work without blocking the UI owner; stop/wake is not ordinary queued work.
- User callbacks run without core registry/queue mutexes held.
- Foreign exceptions do not unwind through C. Rust panics are contained where unwind is available and poison unsafe process state.
- Owner-thread blocking waits for work queued to that same owner are rejected.
- Timers use a monotonic clock, are session-owned and skip missed repeat intervals rather than creating an unbounded catch-up burst.
- Subscription removal is token-specific, so an old token cannot remove a later registration.
- User-supplied code must cooperate with cancellation. No promise is made to kill arbitrary blocked native calls or force threads to end safely.

## Shutdown

Ordinary close can be vetoed. An accepted close releases native resources and
delivers a terminal notification. Closing one window leaves others usable;
closing the last owned window ends the ordinary session. Forced stop bypasses
close vetoes, stops new work, cancels queued work, releases windows and callbacks,
and returns the outcome to the host. Cleanup is idempotent. No library path calls
process exit to terminate the embedding Python or PowerShell process.

## Errors and diagnostics

Stable error statuses distinguish invalid input, wrong state/thread, missing
resources, stale handles, saturation, callback failure and terminal native host
damage. Diagnostics report binding/product/ABI versions, native path, source ID,
target and backend without creating a window. Do not log full documents,
credentials or arbitrary application state by default.

## Delivery

The product version, native ABI version and exact artifact identity are separate.
Package metadata versions stay synchronized for the initial release train. Python
wheels are platform-specific even though the facade uses ctypes. No unusable
source distribution is published as a fallback. A final PowerShell package
contains both platform native payloads. Runtime consumers do not need Rust or a
.NET SDK. OS runtime dependencies must be documented and tested.

Build, assemble, install/test, qualify, publish and public download verification
are distinct stages. Qualification binds results to final file hashes. Publishing
does not rebuild the files. Registry publication is not atomic across destinations;
record a partial release honestly and retry the same intended bytes.

## Acceptance catalog

| ID | Requirement | Required evidence |
| --- | --- | --- |
| F01 | Clean install | Exact artifact installed outside checkout; packaged native path; missing payload fails clearly |
| F02 | Useful native startup | Visible first frame and input readiness; missing-display failure and rollback |
| F03 | Input and state | Type, focus, activate button; assert changed state and capture visible result |
| F04 | Window lifetime | Two windows, resize, close one, continue using the other, return after last close |
| F05 | Close and stop | Veto, accept, callback failure and forced stop cleanup |
| F06 | Owner dispatch | Worker post, always-deferred order, correct callback owner, wrong-thread and nested-run rejection |
| F07 | Cancellation | Accepted posts settle once; stop races; late work cannot mutate a later session |
| F08 | Native reuse | Two real native sessions in the same process and on the retained owner |
| F09 | ABI/callback lifetime | ABI mismatch, callback roots, stale handles and subscription identity |
| F10 | Bounds and idle | Saturation remains stoppable, stable owned-resource accounting, no busy spin |
| F11 | Resources/diagnostics | Unrelated working directory, Unicode/spaces, explicit asset base, correct build diagnostics |
| F12 | Release and upgrade | Final package install, fresh-process remove/reinstall, version identity and negative qualification controls |

The release matrix is 12 scenarios × 2 bindings × 2 platforms. This is not a
unit-test count or a claim of coverage of every OS version. The scenario catalog
in `quality/scenarios.json` is the machine-readable index. Scenario procedures
must distinguish automated assertions from the operator's native observations.

## Evidence semantics

`passed`, `failed`, `blocked`, `interrupted` and `not_run` are different states.
Only successful required evidence qualifies a candidate. The latest attempt
remains visible after failure. Keep last success and published-release evidence
separate. Logs/images have hashes and stable links. A screenshot of the engine's
framebuffer is not a desktop capture. Nonvisual races require assertions and
counters, not a picture of a window.

Manual evidence depends on an accountable operator and trusted release review.
JSON and file hashes alone cannot prove that a human actually performed a test.

## Deferred scope

Full CSS/layout migration, IME, selection/clipboard editing, full Unicode font
shaping, screen-reader accessibility, application installers, signing/notarization
for unsupported platforms, macOS/ARM, asyncio/notebook embedding, process
isolation and broad performance claims are outside this foundation. Basic
accessibility roles and native desktop integration remain explicit gaps until
implemented and accepted; the minimal renderer does not establish them.
