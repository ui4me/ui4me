# Project status and development handoff

This document is the authoritative engineering handoff for ui4me. The
language-neutral API is specified by [`include/ui4me.h`](../include/ui4me.h).

## Product and verification status

ui4me is a native, in-process UI runtime for Python and PowerShell applications.
The Rust core owns session/window state, the software form renderer and native
event loop; host languages own application logic. The initial distribution is
version 0.1.0, native ABI 1. [PyPI](https://pypi.org/project/ui4me/0.1.0/) and
[PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/0.1.0/)
publish independent packages from this monorepo. No browser, IPC broker, plugin
framework, or old rendering engine is part of the runtime.

The published candidate is source commit `884647892c6969e925eb4dea46aaa45eeeb4620f`.
Its [CI run](https://github.com/ui4me/ui4me/actions/runs/42848001121) passed
Linux and Windows builds, core/Python/PowerShell/tooling contract suites and
installed consumers of the combined final artifacts. Its Linux x86-64 Python
wheel, Windows x64 Python wheel and combined PowerShell module were downloaded
from their public registries, matched to the qualified hashes, and exercised by
isolated consumers on both hosts. Automated native sessions tested two bindings
on Debian 13 using nested KWin Wayland on a virtual X11 display, and on Windows
Server 2022 via an interactive ordinary-user RDP desktop. These are not claims
of physical-monitor coverage. Public package consumers were also installed in
fresh environments using Linux Python 3.13.5 and PowerShell 7.6.9, and Windows
Python 3.14.10 and PowerShell 7.6.9; F01/F09/F11/F12 passed on each binding and
host. The owner reviewed the recorded observations; the
[review-only release workflow](https://github.com/ui4me/ui4me/actions/runs/42872599592)
qualified that candidate. **Those results belong to that exact source and
artifacts, not to a later checkout.** Run and record new checks after changes.

The first TestPyPI and PyPI publishing attempts uploaded successfully but their
post-upload verification failed because the publishing job reported a source
identity mismatch. Verification-only retries skipped already-published identical
wheels and passed; the initial mismatch's cause remains unresolved. The
publication workflow now runs Python public-download verification in a fresh
job to avoid reusing a potentially changed publishing checkout. This mitigation
has not yet been verified through a real publishing run. The Gallery publication
and public-download verification passed. There is no GitHub Release
or version tag for 0.1.0. PowerShell static analysis on the published candidate
reported warning-level findings; PSScriptAnalyzer 1.25.0/1.24.0 also raised a
null-reference exception in `PSUseCmdletCorrectly` on PowerShell 7.6.9. An
error-severity run with PSScriptAnalyzer 1.22.0 on PowerShell 7.4.0 completed
with zero errors. Treat this as a partial static-analysis result, not a clean
full default-rule pass.

## Architecture and public interfaces

| Location | Responsibility |
| --- | --- |
| `crates/ui4me-core` | Rust session lifecycle, bounded work, document model, software rendering and winit/softbuffer native integration |
| `include/ui4me.h` | Versioned C ABI using UTF-8 JSON commands/events and opaque monotonic IDs |
| `bindings/python` | `ctypes` loader, Python facade, wheel metadata and binding tests |
| `bindings/powershell` | PowerShell module and .NET managed bridge; one retained UI-owner thread, fresh runspace per application |
| `examples` | Equivalent small native forms using public APIs |
| `tests` and `quality/scenarios.json` | Cross-component checks, native stress checks and F01–F12 acceptance catalog |
| `dev.py`, `tools/ui4me_dev`, `scripts` | Local build, test, packaging, reports and explicit release operations |
| `.github/workflows` | Locked builds, artifact/consumer tests, controlled evidence collection and manual publication |

A host process has at most one active session. The first native session fixes the
native owner thread, and subsequent native sessions must use that retained owner.
Windows belong to their session, and stale session/window identities are never
recycled. Python creates the app on its owner, normally the main thread, and
`run()` blocks until it returns. PowerShell's `Invoke-Ui4meApp` uses a persistent
hosted owner thread; its initializer receives `$app` and explicit `-ArgumentList`
values in a fresh runspace. Caller locals do not implicitly cross runspaces.
Callbacks run synchronously on the owner with no core registry/queue mutex held;
long callbacks stall the UI. Normal last-window close returns to the host. Forced
stop bypasses vetoes, cancels queued work, destroys windows and returns control;
no path deliberately exits the embedding process.

The Python package exports `App`, `Window`, `Subscription`, `Timer`,
`Ui4meError`, `build_info`, and `__version__`. `App` offers `open`, `open_file`,
`on`, `timer`, `post`, `stop`, `run`, `stats`, and context-manager cleanup.
`Window` offers `on`, `set_text`, `get_value`, `set_title`, `resize`, `snapshot`,
and `close`. Only `post` and `stop` are safe from other threads. Posts always
defer; their futures settle with a value, exception, or cancellation. A pending
future cannot be synchronously awaited by the UI owner. A close-request handler
returns `False` to veto. `App(handle_sigint=True)` temporarily bridges SIGINT
while running on the main thread, using one timer; the prior handler is restored.

The PowerShell module exports `Invoke-Ui4meApp`, `Get-Ui4meInfo`,
`New-Ui4meWindow`, `Register-Ui4meEvent`, `Set-Ui4meText`, `Get-Ui4meValue`,
and `Stop-Ui4meApp`. App/Window objects also expose `On`, `Timer`, `Post`,
`Stop`, `OpenFile`, `Resize`, `SetTitle` and `Snapshot`. `Work` executes a script
in an isolated background runspace and dispatches completion to the owner;
arguments are explicit, and a callback receives result values and an error.
ScriptBlocks are runspace-bound: register `Post` on the owner; external managed
workers may use `PostManaged(Func<object>)`. `GetResult()` on unfinished posted
work rejects an owner-thread wait. Subscription disposal is token-specific.
Background cancellation is cooperative, not forced termination; up to four
workers may remain active process-wide and each retains at most 256 output
entries. Stop requests worker cancellation but cannot safely kill arbitrary user
code. Start a fresh host process after changing a loaded native library version.

Both packages load a package-relative native library and check its ABI/version.
`UI4ME_NATIVE_LIB` is an explicit absolute-path development override; unset it
for installed-consumer tests. The loader does not search the current directory,
PATH, or another checkout. `build_info()` / `Get-Ui4meInfo` expose diagnostic
identity without opening a window. Renderer snapshots are software framebuffer
images, **not** desktop captures and not evidence of focus, input or compositor
behavior.

## Runtime contract

The following is the ABI 1 contract; change it together with the header, bindings
and regression tests. In particular, never bypass ownership checks to make a
binding appear to work.

### Boundary and ownership

`include/ui4me.h` is the C-facing contract. Native filenames are `ui4me_core.dll` on Windows and `libui4me_core.so` on Linux. All strings are UTF-8 and NUL terminated. The caller must pass valid readable pointers and writable output pointers. This ABI cannot validate arbitrary addresses or catch access violations caused by invalid pointers.

`ui4me_session_create(config, callback, user, out)` creates one session. The creating thread owns its commands, `run` and `destroy`. Only `post` and `stop` are callable from other threads. Exactly one session exists at a time; destroy the previous one before creating another.

The callback and user data remain rooted until destroy succeeds. Callbacks execute on the owner thread, with no core mutex held, and may issue commands. Callbacks must catch language exceptions and return a negative status; foreign exceptions must never unwind through Rust. Return `1` to veto `close_requested`; other positive values do not veto. Return `0` to continue.

The output of `ui4me_session_command` is borrowed thread-local memory. Copy it before another command on that thread. Never free it. The caller should also copy `ui4me_last_error()` immediately after a failing call. `ui4me_build_info()` has process lifetime.

### Startup, run and shutdown

Configuration is a JSON object with optional `backend` (`native`, default, or `headless`), `app_id` (default `org.ui4me.app`) and `allow_any_thread` (boolean, default false). Unknown configuration keys are rejected. `app_id` maps to the Wayland application ID, X11 WM_CLASS names and Windows window class name. It does not create a desktop file, Windows AppUserModelID, installer identity or OS registration.

Sessions move from ready to running to stopped. A session runs at most once. Commands can create windows before run, but actual OS windows are created only after the event loop resumes. `started` means the loop can accept work, not that a frame has been presented.

The first native session fixes the process's native owner thread. The winit loop is retained on that thread and reused for later sessions. No window survives between runs. The PowerShell host sets `allow_any_thread: true` to explicitly enable winit's supported any-thread option on Windows and Linux. A subsequent native session on another thread returns an error. This is not a portable promise for macOS, mobile or Web.

Native initialization failure requires a new process before another native attempt. The original startup error is returned. A caught Rust panic poisons the process runtime and refuses new sessions. Panic containment cannot recover arbitrary foreign memory corruption, process abort, stack overflow or an exception thrown through the C boundary.

`stop` is idempotent for an existing session. It cancels queued posts, clears timers, releases native windows, emits `closed`, then `stopped`, and returns from run. `stop` overrides a close veto. `destroy` is rejected while run is active. Destroying a ready session releases its pending model/work without callbacks. The host binding must settle its own pending Future or delegate objects on disposal.

The last window's accepted close stops the session. A session that never opened a window remains active until stopped, which supports headless lifecycle and timer tests. Calling stop before run produces terminal cleanup without a started event.

### Commands

| `op` | Fields | Result / behavior |
| --- | --- | --- |
| `open` | `html`, optional `title`, `width`, `height` | Returns `{ "window": id }`; creation is deferred to the native loop. |
| `set_text` | `window`, `element`, `text` | Updates literal text or input value, never parses the replacement as HTML. |
| `get_value` | `window`, `element` | Returns `{ "value": "..." }`. |
| `close` | `window` | Requests close; veto can be returned from the later callback. |
| `set_title` | `window`, `title` | Updates the requested native title. |
| `resize` | `window`, `width`, `height` | Requests logical-pixel size; actual native size is reported separately. |
| `snapshot` | `window`, `path` | Writes a renderer PNG; response includes dimensions and `native_capture: false`. |
| `timer` | `token`, `milliseconds`, optional `repeat` | Adds or replaces a timer; interval must be 1–86,400,000 ms. |
| `cancel_timer` | `token` | Returns whether a timer existed. |
| `stats` | none | Returns phase, window/timer/queue counts and execution/cancellation counters. Allowed after stop. |

IDs are process-monotonic, never raw pointers, and stale IDs are rejected. A window ID does not become valid again for a later window. JSON strings are bounded to 2 MiB; the C caller still has to supply a valid NUL-terminated string.

### Events

Every event contains `type`. Window events contain `window`; element events contain `element`, and change events also contain `value`.

- `started`, `stopped`
- `post` and `timer`, with `token`
- `click`, `change`
- `close_requested`, `closed`
- `resized`, with actual `width`, `height`, and `units: "physical_pixels"`

Closed means core-owned native window resources were released before notification. It does not guarantee that an external compositor has already removed the last visible pixels. Callbacks are synchronous; long callbacks stall input and rendering. Background work must post its result back to the owner thread.

### Queues, timers and idle behavior

There are at most 512 pending posts, 128 timers and 32 windows. A post accepted before stop is either dispatched once or counted as cancelled. Rejected posts are not counted as accepted. A callback failure while dispatching a post counts it as executed, with the error returned after cleanup.

The native loop drains bounded batches to avoid starving OS events. Repeating timers skip missed intervals rather than replaying a backlog. Timers use monotonic time. Callback commands can cancel later due timers before their callbacks are dispatched.

An idle loop waits for OS events or the next timer. A continuously full post queue may use polling so that bounded batches continue. Bindings can add their own interruption timer; that policy is separate from the core idle behavior.

### Minimal document and renderer

The supported tags are `html`, `body`, `div`, `h1`, `p`, `label`, `button` and `input`. Attributes are quoted `id`, inline `style`, and input-only `value` and `type="text"`. Inline styles on rendered elements support `color` and `background-color`; `body` supports only `background-color`. Colors are `#RRGGBB`, `black`, `white`, `red`, `green`, or `blue`. Styles do not inherit. Unsupported declarations are errors. Comments and an optional HTML doctype are accepted. IDs must be unique and whitespace-free. Unknown tags/attributes, malformed nesting, unsupported entities and oversized input are errors.

The renderer uses a fixed vertical layout, basic bitmap text, pointer interaction, forward Tab navigation, Enter/Space activation, input append/Backspace and vertical scrolling. Unsupported glyphs display as `?`; UTF-8 values remain intact. There are no CSS stylesheets or layout properties, JavaScript, network fetch, accessibility bridge, IME composition, clipboard integration, text selection, caret positioning or browser compatibility claim.

Document limits: 1 MiB HTML, 128 rendered elements, 64 levels of nesting, 16 KiB text per element. Requested window dimensions are 160–4096 by 120–4096 logical pixels. Native buffers have a 16,777,216-pixel limit; a large high-DPI resize can exceed that limit and returns a runtime error instead of allocating unbounded memory.

Renderer snapshots use the model's pixel dimensions and scale. They are not OS desktop captures and never qualify focus, DPI, input or window-manager acceptance by themselves. A headless session never proves native startup.

### Error codes

| Code | Category |
| --- | --- |
| 0 | Success |
| 1 | Invalid argument or document |
| 2 | Lifecycle violation |
| 3 | Wrong owner thread |
| 4 | Stale or unknown handle / element |
| 5 | Resource limit |
| 6 | Native runtime or display initialization |
| 7 | Binding callback failure |
| 8 | Poisoned runtime |
| 9 | File / snapshot IO |

`last_error` is JSON with `code` and `message`. A successful status-returning ABI call clears the current thread's error. The host binding should retain its original language exception when a callback returns a failure.

## Development and build

The repository targets Linux x86-64 and Windows x64. The Python metadata allows
3.11–3.14; this range is package metadata, not evidence that every interpreter
version has been tested. PowerShell 7.4 is the managed API floor, with a
`net8.0` bridge; Windows PowerShell 5.1 is unsupported. Rust 1.90 is selected by
`rust-toolchain.toml`, and `global.json` selects a .NET 10 SDK. Contributors
need a C compiler, Windows MSVC x64 tools on Windows, and Linux Wayland/X11
headers and runtime libraries. On Debian install a compiler, `pkg-config`,
`libx11-dev`, `libxkbcommon-dev`, `libwayland-dev`, `libxkbcommon-x11-0`,
`libegl1`, and `libgl1`. PowerShell packaging needs PSResourceGet 1.1+.

```sh
python -m venv .venv
# Linux: . .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

The tracked `Cargo.lock` and `bindings/powershell/Ui4me.Managed/packages.lock.json`
are used with locked Cargo/NuGet resolution. Run `python dev.py lock` only for a
planned dependency update, then review and commit the result. Use
`scripts/bootstrap.sh` or `scripts/bootstrap.ps1` for the documented setup path;
read their installation options before executing. Build receipts bind the exact
source identity, host and native output; changing source or artifacts makes the
receipt stale. Keep generated output and logs in ignored `build/` or `dist/`.

For small changes use `python dev.py build --binding python --profile dev`
followed by `python dev.py test --binding python --suite unit --profile dev`;
substitute `core`, `powershell`, or `tools` as appropriate. Tooling tests need no
native build. Shared core/ABI changes need both binding suites. Run
`cargo fmt --all -- --check` and `cargo clippy --locked --all-targets -- -D warnings`
for Rust changes. `python -m ui4me demo` launches the packaged Python example.

### Package and install

```sh
python dev.py build --binding all --profile release
python dev.py package --binding all --profile release
```

These produce a host-specific manifest at `dist/linux-x64/manifest.json` or
`dist/win-x64/manifest.json`, a platform wheel, native SDK archive and staged
PowerShell module. Linux wheel repair uses auditwheel; the published 0.1 wheel
is `manylinux_2_34_x86_64`. Build on both platforms from the **same committed
revision**, then assemble the exact host outputs:

```sh
python dev.py assemble --manifest dist/linux-x64/manifest.json --manifest dist/win-x64/manifest.json --out dist/release
python dev.py test --binding all --suite installed --manifest dist/release/manifest.json
```

Repeat installed tests on the other OS using the same assembled directory. The
combined module contains both native payloads, and installed tests use an
isolated consumer directory with spaces/Unicode and clear development
loader overrides. Windows C SDK checks need an x64 Visual Studio developer shell
(or the CI MSVC setup). A wheel is the supported Python registry artifact; the
current packaging setup requires a staged matching native runtime to create a
usable platform wheel. A contributor source distribution can be built with
`python -m build --sdist --outdir build/sdist bindings/python`; building from
that sdist invokes locked Cargo and requires Rust 1.90 and the host compiler and
native dependencies. The published 0.1.0 release contains platform wheels only;
do not infer that source installation works on an untested platform.

## Tests and evidence

Unit tests live beside the Rust and Python owners; PowerShell smoke tests are in
`bindings/powershell/tests`, and cross-component tooling tests in `tests/tooling`.
The native SDK has an external C consumer. Headless contracts are useful but do
not prove native focus, compositor input, resize, close, or real event-loop reuse.
For an installed candidate, run on the target desktop:

```sh
python dev.py test --binding python --suite native --manifest dist/release/manifest.json --interactive
python dev.py test --binding powershell --suite native --manifest dist/release/manifest.json --interactive
python dev.py report --manifest dist/release/manifest.json
```

Supplementary real-native tests against the installed packages are:

```sh
python tests/native/stress.py
python tests/native/ownership.py
pwsh -NoProfile -File tests/native/stress.ps1 -ModulePath /absolute/installed/Ui4me/0.1.0
pwsh -NoProfile -File tests/native/ownership.ps1 -ModulePath /absolute/installed/Ui4me/0.1.0
```

Use the appropriate installed module path on Windows. These scripts print
structured assertions and build identity, exit nonzero on failure and require a
real native display session; they do not create a human attestation.

Native acceptance includes startup, input/state, window lifecycle, close
interception, owner dispatch, shutdown races, reuse and bounded resources. The
F01–F12 catalog in `quality/scenarios.json` also covers clean install,
ABI/callback lifetime, resources and release identity. A full release matrix is
both bindings × both platforms × all twelve scenarios. Automated GUI observations
require review and documented operator attestation; a renderer snapshot alone
is not a desktop capture. `python dev.py attest --help` describes recording a
scenario, and `python dev.py qualify --help` describes release qualification.
Statuses `passed`, `failed`, `blocked`, `interrupted`, and `not_run` are distinct;
missing or zero-test required suites do not pass. The latest failed attempt must
not be hidden by an older success. Logs, screenshots and receipts belong in
`build/reports` and stay out of Git. Do not carry results across source identity
or package-hash changes.

## Release and publication

Build, package, assemble, test, attest, qualify, publish and public-download
verification are separate operations. Normal pushes and pull requests never
publish. `.github/workflows/ci.yml` builds both platforms, assembles the release
candidate, checks isolated installed consumers and uploads `ci-bundle`.
`native-evidence.yml` collects exact-candidate desktop receipts from trusted
self-hosted Windows/Linux collectors labeled `ui4me-native`, configured with
`UI4ME_EVIDENCE_DIRECTORY` outside their checkout. Collection alone is not human
attestation. The manual `publish.yml` requires the successful CI run and both
native-evidence run IDs at the same default-branch commit. Its `execute=false`
mode verifies and prepares; publishing is an explicit separate action.

Trusted publishers must match owner `ui4me`, repository `ui4me`, workflow
`publish.yml`, and environment `pypi` or `testpypi`; the registries are separate.
The Gallery job reads `PSGALLERY_API_KEY` from the `psgallery` environment, not
from pull requests. Configure GitHub environment and repository permissions
intentionally, keep secrets out of source and logs, and do not assume any
organization or registry ownership is approved. A GitHub Release requires an
explicitly created version tag at the qualified commit and is a separate action.
Never overwrite a published version: record partial cross-registry publication
and retry the same bytes, or use a new version with new evidence.

Qualification checks the complete required matrix, current source and candidate
hashes, unit and SDK receipts, proof files and a reviewer. Hashes do not prove
that a human observed a test; release review must verify provenance. After an
explicit upload, `python dev.py verify --manifest dist/release/manifest.json
--registry pypi` (or `testpypi`, `powershell`, `github`) downloads and compares
the published files, then runs installed consumers. Repeat on the other target
as applicable. The fresh-job mitigation for the PyPI/TestPyPI identity mismatch
noted above still requires verification in a future authorized publishing run.

## Next work and instructions for agents

Prioritize renderer/layout work in small reviewed steps: preserve lifecycle,
window ownership, package loading, real GUI acceptance and stale-handle tests.
Accessibility, IME, selection/clipboard, richer text shaping, CSS layout and
stylesheets, and macOS/ARM are not implemented. Do not describe the renderer as
a browser or claim asyncio, notebook, or arbitrary external event-loop support.
Do not import historical rendering-engine artifacts.

For each change, inspect this document and the C header, keep the API narrow,
place tests by their owner, and run the affected host/binding commands. Respect
caller requests for source-only work. Report actual failures and missing evidence
rather than inferring a pass from source or other artifacts. Never publish or
configure registry credentials as a consequence of a build, test or pull request.
Do not commit generated binaries, logs, screenshots, virtual environments,
credentials, or local evidence. Update this handoff when behavior or support
changes, including exact revision and environment for any test claim.
