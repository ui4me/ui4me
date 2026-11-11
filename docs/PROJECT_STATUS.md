# UI4ME 0.2: implementation and verification handoff

This is the authoritative engineering handoff for the 0.2 source delivery.
The public native boundary is [`include/ui4me.h`](../include/ui4me.h); the
wire requests are defined in
[`protocol.rs`](../crates/ui4me-core/src/protocol.rs).

## Current status

**0.2.0 is implemented as a source candidate. It is not yet a qualified public
release.** The implementation replaces the 0.1 fixed form painter with the
consolidated HTML/CSS document engine while retaining the new repository's
native window host, package separation and release workflow.

The delivery work executed Linux compilation, Rust regression checks, Python
and PowerShell binding checks, the C ABI consumer and isolated package checks.
The source archive includes `build/delivery/verification.json` and selected
logs/receipts with the exact results, source identity and limitations. Those
files are ignored build evidence, not application source. A result belongs to
the recorded source/artifact identity, never automatically to a later edit.

**Still required locally:** link and run the final candidate on Windows;
exercise native input, window management, clipboard, DPI and IME on the target
KDE/Wayland and Windows desktops; test the assembled two-platform packages.
The Windows MSVC target passed a Rust cross-check on Linux, which checks
conditional code and dependency types but does not link or run a Windows binary.
The implementation environment had no usable native display, and no Windows
host was reachable. Renderer images and headless input tests do not satisfy
those desktop checks. The previous 0.1 release's evidence does not qualify 0.2.

No registry upload, remote Git push or public release is part of this delivery.
The branch name used for the source work is `implementation/v0.2`. The ZIP has
repository files at its root, includes no `.git` directory, and is intended to
replace a clean checkout's files while preserving that checkout's `.git`.

## Product scope

0.2 is the base for useful local desktop forms and small multi-window apps.
It has one fixed, compiled renderer profile. Python and PowerShell call the
same C ABI and own application logic; there is no embedded JavaScript engine,
browser, HTTP resource loader, out-of-process UI broker or plugin system.
Authentication and application-specific user records belong to the application.

| Area | Promoted 0.2 foundation | Practical boundary |
| --- | --- | --- |
| Documents | Nested HTML, text/entities, unique public IDs, local file source base | Active script, iframe/object/embed, inline event-handler attributes and unimplemented native picker input types are rejected; malformed HTML still follows the HTML parser's recovery rules |
| CSS and layout | Author/inline CSS, local linked sheets and imports, cascade/selectors, classes, custom properties, block/inline/flex, ordinary sizing/spacing, basic positioning | This is a defined application subset, not general browser compatibility; grid/table/advanced positioning remain unpromoted |
| Painting | Backgrounds, borders, clipping, shaped text, raster images, ordinary overflow/scroll | Advanced effects and SVG breadth are not release promises; animations/transitions and paged-media rules are outside this profile |
| Text | Unicode shaping and wrapping, font fallback, system font snapshot, local `@font-face` TTF/OTF/WOFF/WOFF2 | System font/theme changes are not live-reloaded; platform font availability affects output |
| Controls | Text/password input, textarea, button, checkbox/radio, labels, disabled/readonly/placeholder, Tab/focus | Select/complex widgets and browser form navigation are not promoted |
| Editing | Selection, cursor movement, deletion, plain-text copy/cut/paste, undo/redo, composition plumbing | Real KDE/Windows IME, dead-key and AltGr acceptance remains pending; no HTML clipboard or touch/pen/drag-and-drop claim |
| Updates | Text/value/checked, attributes/classes, focus and atomic child replacement | Existing unrelated controls retain state; replaced controls are new identities |
| Windows | Independent documents, resize, close veto, forced stop, timers, owner dispatch, repeated sessions | One active application session per process; subsequent native sessions reuse the first native owner thread |
| Assets | Local CSS/images/fonts, explicit file roots, data URLs, bounded asynchronous loading | Remote URLs denied; large/over-capacity inputs return diagnostics instead of silently growing work |
| Delivery | One version authority, native-inclusive Python wheel, PowerShell module, native SDK, portable sdist | Only both-platform release builds plus actual installed/native evidence can qualify publication |

Retained backend code is deliberately private. Grid, select, printing/paging,
advanced SVG/effects and accessibility may be developed later, but their source
presence is not an assertion that they work through this 0.2 public facade.

## Architecture and ownership

| Location | Owns |
| --- | --- |
| `crates/ui4me-core` | C ABI, typed protocol, application/session lifecycle, windows, bounded host queues, timers and winit/softbuffer integration |
| `crates/ui4me-document` | Canonical DOM, generational identities, parsing, control state and atomic mutations |
| `crates/ui4me-renderer` | One document facade; private style, text, layout, scene, raster, interaction and pipeline modules |
| `crates/ui4me-assets` | Local resource policy, decoding/font sources, cache accounting, finite admission and process-owned asset workers |
| `crates/ui4me-engine-types` | Internal identifiers, status codes and value types shared by the engine; no second public host API |
| `bindings/python` | ctypes loader, Python facade, package backend and tests |
| `bindings/powershell` | PowerShell module, .NET bridge, retained owner thread and isolated background runspaces |
| `patches` | Exact carried Stylo/Taffy source and corrections; required for reproducible source builds |
| `tools`, `scripts`, `.github` | Existing build/package/evidence/publication structure, strengthened for the larger source graph |
| `examples/foundation` | One shared HTML/CSS app fixture used by both language examples |

Rendering stages do not become public crates or public ABI objects. The host
sees a document interface, input messages, immutable rendered pixels and plain
event records. Native event processing and resource completions update the
canonical document; hit testing uses committed layout/scene geometry.

Mutable windows, documents and timers live on the owner thread. The shared
session handle contains control queues and lifecycle state, not a mutex around
the renderer. The owner releases its document borrow before calling Python or
PowerShell. A callback can safely issue another supported command. Rendering,
snapshots and decoding do not hold the shared post/stop queue lock.

Run and callback leases are tracked independently of the lifecycle phase.
Destroy is rejected until run and every callback have returned, including a
`stopped` callback. Foreign callbacks never unwind across the ABI. A Rust panic
is contained, the active session is stopped/poisoned and new sessions are refused
until the host process restarts. Ordinary argument, asset and callback failures
have distinct errors and do not imply a successful operation.

### Asset lifetime

The process has two fixed asset worker threads. A new application registers an
interest in that service; it does not create a fresh pool. Shutdown stops intake,
cancels interests, closes delivery atomically and returns without joining a
codec on the UI owner. A cancelled job remains owned by the process service
until it returns; later sessions cannot create extra worker threads around it.

Admission remains charged while a job is queued, executing or awaiting delivery.
A rejected job becomes a structured resource failure. Mailbox closure and
publication use the same lock. Late image completions release their cache pins.
Removing a DOM generation retires its image/style/font interests. An evicted
raster still held by a frame remains charged until that frame releases it.
These are operational budgets, not a claim that all process RSS or third-party
codec temporary allocations are exactly bounded by one counter.

## Public contract

### Session and threads

Python creates `App` on its owner thread, normally the main thread. `run()` blocks
until the last window closes or stop completes. After shutdown, that App is
terminal; construct a new App for another run. `post()` and `stop()` are safe
from other threads. Other operations require the owner. Posts always defer,
and their futures settle as result, exception or cancellation. Waiting for an
unfinished future on the owner is rejected.

PowerShell's `Invoke-Ui4meApp` retains one native owner thread and creates a fresh
runspace for each application. The initializer receives `$app` and explicit
`-ArgumentList` values; caller locals do not cross the runspace boundary
implicitly. ScriptBlocks are runspace-bound. Register `Post` from the owner;
external managed workers may use `PostManaged(Func<object?>)`.

`Work(script, arguments, completion)` uses an isolated background runspace.
Its result/error/cancel state is observable. It reserves a completion ticket
before accepting work, so a full ordinary post queue cannot lose the result.
Cancellation is cooperative. An executing arbitrary user script retains its
process worker slot until it actually exits; stopping the UI does not kill it.
The process permits four such workers, with at most 256 captured output entries
per work item. Keep long operations off UI callbacks.

### Binding methods

| Operation | Python | PowerShell/.NET |
| --- | --- | --- |
| Create document | `app.open(html, ..., base_path=...)` | `$app.Open(html, title, width, height, basePath)` / `New-Ui4meWindow` |
| Preserve a file's local base | `app.open_file(path, ...)` | `$app.OpenFile(path, ...)` |
| Subscribe | `window.on(name, handler, element="id")` | `$window.On(...)` / `Register-Ui4meEvent` |
| Set literal text | `window.set_text(id, text)` | `$window.SetText(id, text)` / `Set-Ui4meText` |
| Form value | `get_value` / `set_value` | `GetValue` / `SetValue`, corresponding cmdlets |
| Checkbox/radio | `get_checked` / `set_checked` | `GetChecked` / `SetChecked`, corresponding cmdlets |
| Attributes | `set_attribute` / `remove_attribute` | `SetAttribute` / `RemoveAttribute` |
| Classes | `add_class` / `remove_class` | `AddClass` / `RemoveClass` |
| Focus | `focus(id)` | `Focus(id)` |
| Replace children | `replace_children_html(id, html)` | `ReplaceChildrenHtml(id, html)` |
| Diagnostics | `diagnostics()` | `DiagnosticsJson()` |
| Window operations | `set_title`, `resize`, `snapshot`, `close`, `closed` | `SetTitle`, `Resize`, `Snapshot`, `Close`, `IsClosed` |
| App operations | `on`, `timer`, `post`, `stop`, `stats`, `run`, `close` | `On`, `Timer`, `Post`, `Work`, `Stop`, `StatsJson`, `Run`, `Dispose` |

`set_text` inserts literal text; it never treats that text as markup. For 0.1
compatibility, calling it on a supported value control updates its value.
New applications should use `set_value` for form controls. `replace_children_html`
parses and validates a fragment before committing it. Duplicate IDs, unsupported
active content and limits cannot leave a half-replaced subtree. Unrelated
control values, selection and scroll are preserved; removed nodes' focus,
resource interests and queued events are retired.

`open_file` reads bounded UTF-8 and keeps the canonical containing directory as
the resource base/root. Relative stylesheet/image/font URLs resolve there, with
nested stylesheet URLs resolving relative to their sheet. For a string document,
use `base_path` explicitly if it has local resources. Without a base, arbitrary
local files are not implicitly available. Native clipboard is plain text and
uses the OS; the headless clipboard is process memory.

### Events and compatibility

Typical element events are `click`, `input`, `change`, `commit`, focus/blur,
key and mouse events, scrolling and composition events. A user edit emits
canonical `input` and the legacy per-edit `change` alias. A committed value
change emits `commit` (for example blur or Enter where appropriate). Programmatic
value/checked updates do not pretend to be user typing. Do not subscribe to both
`input` and its `change` alias for the same action unless duplicate notification
is intentional.

Document and window events include `type` and `window` plus relevant value,
checked, keyboard, modifier, mouse or composition fields. Application events
include `type` and relevant fields such as `token`, `backend` or `app_id`,
without a window ID. `element` is the nearest identified
target and `path` contains identified ancestors for bubbling events. An
ID-filtered handler can receive a click on nested content within its button;
each subscription is invoked at most once for that dispatch. Before delivering
each queued document event to the binding, the host rechecks its generational
target identity. Replacing a node with the same HTML ID cannot revive an obsolete
queued event. Within one event's binding dispatch, matching handlers receive the
same event/path snapshot; identity is not rechecked between individual language
handlers.

Application/window lifecycle includes `started`, `stopped`, `shown`, `closed`,
`close_requested`, `resized`, `scale_changed`, timer and post/completion delivery. A close-request
handler returns `False`/`$false` to veto. Forced stop bypasses veto, closes windows,
settles pending work and returns to the embedding host. No intended runtime
path exits the Python or PowerShell process.

### C ABI and errors

ABI remains **1**, with an additive 0.2 entry point:
`ui4me_session_complete(session, token)`. Reserve/cancel tickets through typed
`reserve_completion` / `cancel_completion` commands before/after background
work. Up to 128 can be reserved. Completion publication is thread-safe and uses
its reserved capacity independently of ordinary posts. Stop retires remaining
tickets; bindings own payload storage and must settle their tasks on teardown.

Strings are UTF-8, NUL-terminated and borrowed. Copy command output before the
next command on that thread; never free it. The caller keeps callback/user data
alive until destroy succeeds. The ABI assumes valid readable/writable pointers;
it cannot validate arbitrary foreign addresses. Unknown JSON fields and wrong
types are rejected at the boundary before mutation.

| Status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Invalid argument/protocol |
| 2 | Lifecycle/state |
| 3 | Wrong thread |
| 4 | Stale handle |
| 5 | Capacity/size limit |
| 6 | Native runtime |
| 7 | Callback |
| 8 | Poisoned runtime |
| 9 | I/O/resource failure |

`ui4me_last_error()` returns the calling thread's diagnostic JSON. Successful
status calls clear it. Unhandled event, timer or completion-handler errors stop the session and are
raised after native cleanup. A posted action's exception is retained by its
returned future/work object; it does not automatically stop the application. `build_info()` / `Get-Ui4meInfo` exposes
version, ABI, source identity, target and explicit package library path.
`UI4ME_NATIVE_LIB` is an absolute-path development override; installed tests
clear it and never search the working directory or PATH for an alternative
library. Restart the process after changing a loaded native version.

### Limits

Current public limits include 32 windows, 512 queued ordinary posts, 128 timers,
128 reserved completions, 1 MiB HTML input/fragment, 16,384 DOM nodes, depth 256,
16 KiB host-set text and a 16,777,216-pixel framebuffer. Requested window sizes
are 160–4096 by 120–4096 logical pixels. Physical allocation is also checked after
DPI scaling. Timer intervals are 1–86,400,000 ms. Source JSON is capped at 2 MiB.

The fixed asset service admits 128 jobs, with 16 MiB queued source descriptions,
128 MiB in-flight encoded-input allowance and 256 MiB completed-result allowance.
Each document defaults to a 128 MiB decoded asset cache allowance, 64 MiB
unreferenced cache and 16,777,216 decoded image pixels, plus encoded-file limits.
The retained SVG backend has its own 128 MiB raster allowance; scene-held pixel
Arcs remain charged after eviction in both caches. There can be 4,096
current requesters per resource document. Text/layout/decorations and diagnostics
also have bounded caches/history. Exceeding a bound is an explicit error; avoid
submitting hundreds of distinct assets in a single burst.

## Development

Use Python 3.11+, Rust **1.99.1** (selected by `rust-toolchain.toml`), .NET SDK
**10** (`global.json`) and PowerShell **7.4+**. The managed bridge targets .NET 8
and the PowerShell 7.4 API floor. Windows PowerShell 5.1 and ARM/macOS are not
supported targets. Python 3.11–3.14 is the metadata range; testing one interpreter
does not establish the whole range.

Linux needs a native compiler, `pkg-config`, X11/Wayland/xkbcommon development
libraries and a working desktop for native acceptance. On Debian/Ubuntu the
convenience bootstrap supports `scripts/bootstrap.sh --install-system` after
reviewing its system-install option. Windows needs Visual Studio Build Tools
with the C++ x64 toolset and Windows SDK; use its x64 developer shell. The
PowerShell packaging path needs PSResourceGet 1.1+. `scripts/bootstrap.ps1`
provides optional WinGet installation and Python-environment setup.

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py version --check
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

`VERSION` is authoritative. `python dev.py version --check` checks derived Rust,
Python, PowerShell and managed metadata; `python dev.py version --set X.Y.Z` updates it
intentionally. Keep Cargo/NuGet locks. `python dev.py lock` is for a planned
reviewed dependency update, not a routine cure for a failed build.

The Stylo/Taffy source patches are part of the build input. Do not remove them
from a source ZIP or sdist. The build backend computes the local dependency/patch
closure, rejects paths outside the source root and stages that complete closure.
Packages retain native dependency notices and bundled font licenses.

### Run the development example

After the development build, Linux Python can run the checkout directly:

```sh
export UI4ME_NATIVE_LIB="$PWD/build/cargo/linux-x64/x86_64-unknown-linux-gnu/debug/libui4me_core.so"
export PYTHONPATH="$PWD/bindings/python/src"
python examples/python/hello.py
```

On Windows use the absolute DLL at
`build/cargo/win-x64/x86_64-pc-windows-msvc/debug/ui4me_core.dll` and set
`PYTHONPATH` to `bindings/python/src`. To run PowerShell without manual bridge staging, first run
`python dev.py package --binding all --profile dev`, then start a fresh PowerShell
process and run:

```powershell
Import-Module ./build/package/linux-x64/Ui4me/Ui4me.psd1
./examples/powershell/hello.ps1
```

Use `win-x64` on Windows. A regular installed package can run the examples with
no native override. Both examples use the same fixture and public APIs.

### Build packages and test installed consumers

Freeze/commit a source checkpoint first. Build receipts include exact normalized
source identity, compiler/configuration and hashes of native, managed and
managed-dependency outputs. Packaging refuses a stale receipt or changed output.

```sh
python dev.py build --binding all --profile release
python dev.py test --binding all --suite unit --profile release
python dev.py package --binding all --profile release
python .github/scripts/check-sdist.py
python dev.py test --binding all --suite installed --manifest dist/linux-x64/manifest.json
python dev.py upgrade-check --binding python --manifest dist/linux-x64/manifest.json
```

Substitute `win-x64` on Windows. The source-distribution check builds from an
archive outside the checkout, installs its own resulting wheel and checks that
consumer. It needs a native compiler and pinned Rust; it does not claim a wheel
can be built on arbitrary systems without build tools. Upgrade checks install
public 0.1.0 in isolation, exercise it, install the exact candidate and exercise
it in a fresh process. An exact-candidate reinstall is a separate check.

Build both hosts from the same committed source, collect the two platform
artifact directories and assemble:

```sh
python dev.py assemble --manifest dist/linux-x64/manifest.json --manifest dist/win-x64/manifest.json --out dist/release
python dev.py test --binding all --suite installed --manifest dist/release/manifest.json
python dev.py upgrade-check --binding powershell --manifest dist/release/manifest.json
```

Repeat installed checks on the other OS against that same combined directory.
The PowerShell module contains both native payloads. Its upgrade check requires
this assembled `.nupkg`; a host staging ZIP is not the registry package. Wheels
remain per platform.
The external C consumer needs a C compiler (MSVC developer environment on Windows).
The Linux wheel tag is determined by auditwheel and actual build dependencies;
do not infer compatibility from an earlier release's tag.

### Native acceptance and publication

Use installed candidate bytes on the actual target desktops:

```sh
python dev.py test --binding python --suite native --manifest dist/release/manifest.json --interactive
python dev.py test --binding powershell --suite native --manifest dist/release/manifest.json --interactive
python dev.py report --manifest dist/release/manifest.json
```

The F01–F12 catalog is in `quality/scenarios.json`. Run the shared foundation
app as well as the native lifecycle harness when observing F03; the harness alone
does not contain every 0.2 control. Native checks must include
first paint, title, keyboard/pointer input, selection/clipboard/undo, Czech and
combining text, checkbox/radio labels, resize/fractional DPI, scrolling, two
independent windows, close veto, background completion under queue pressure,
stop/reuse and explicit failure reporting. Record the actual compositor,
PowerShell/Python versions and ordinary desktop user. A framebuffer PNG is not
a desktop capture. Basic IME plumbing is implemented, but do not claim full IME
support from synthetic composition events.

Automated results and native observations are distinct. `attest` records an
observed scenario; the default `qualify` policy requires all native scenarios.
For an explicitly requested release, the publication workflow uses `qualify
--ci-only`: it checks the complete automated CI matrix for the exact commit and
artifacts, and records full native desktop acceptance as `not_run`. It does not
claim that missing desktop observations passed. Missing/zero-test suites, failed
latest attempts, stale source/artifacts and absent upgrades still block release.
The workflow obtains its candidate from a successful CI run on the default
branch. PowerShell 7.4 floor checks remain part of that matrix.

Publication remains explicit in the existing manual workflows. Source changes
after a candidate build invalidate its receipts. Rebuild/repackage the affected
candidate before further release checks, and verify the public downloaded
bytes only after an authorized upload. No 0.2 publication has been performed by
the ZIP delivery.

## Instructions for the local AI agent

Copy the following prompt into the agent operating on the replacement checkout.
The implementation is present; the task is local establishment and defect repair.

```text
Establish and verify the UI4ME 0.2 implementation in this checkout on branch
implementation/v0.2. Read AGENTS.md, README.md and docs/PROJECT_STATUS.md first,
plus build/delivery/verification.json if present. Keep the new repository layout
and VERSION=0.2.0. The source ZIP is the implementation, not a migration plan.

Inspect git status and the replacement diff. Preserve .git and user changes.
Install/use the pinned toolchains and committed Cargo/NuGet locks. Run the version,
format and clippy checks, then build both bindings and run the workspace/core,
Python, PowerShell and tooling suites through dev.py. Fix concrete failures in
source, add only focused regressions for those defects, and rerun affected checks.
Do not hide failures with skips, broad lint suppression, fabricated receipts or
an unreviewed dependency upgrade.

Run the shared foundation application on my actual Linux KDE desktop and Windows
ordinary-user desktop, from both bindings. Verify the new rendering/editing and
local asset behavior, targeted updates preserving other input state, independent
windows, close/veto/stop, background completion, thread ownership and repeated
sessions. Check real clipboard, Czech/dead-key/AltGr input, composition and
fractional scaling. Report unsupported or unverified behavior accurately.
Use the available Windows connection if configured; request access only if that
host really cannot be reached. SSH-only headless success is not desktop evidence.

Once fixes are complete, commit a coherent source checkpoint on this branch.
Build release artifacts from that same source on Linux x64 and Windows x64.
Run the standalone sdist build, isolated installed consumers, real 0.1.0-to-0.2.0
upgrade checks and PowerShell 7.4 compatibility check. Assemble the two host
outputs, then test the exact combined candidate on both hosts. Keep receipts,
logs and screenshots under ignored build/ or dist/ and bind them to the actual
source and artifact hashes. If source changes, repeat the affected build/package
checks before claiming candidate results.

Finish with the changes made, commands actually run, exact pass/fail/not-run
results, working example launch commands and remaining release blockers.
Do not publish, tag a release, merge or push without my instruction. Keep the
scope to a dependable 0.2 foundation; defer new widgets and broad feature work.
```

## Source provenance

The replacement starts from the supplied `ui4me/ui4me` snapshot, preserving its
host/package layout. Rendering and interaction algorithms were reviewed and
consolidated from the supplied older repository, with ownership, protocol,
resource lifetime and public-facade changes for this implementation. The old
migration plan is advisory, not an implementation authority.

| Supplied source | Archive label | Archive SHA-256 |
| --- | --- | --- |
| New UI4ME repository | `69ab68732e1697ae858bfc06ac55cee0fe589fa1` | `823c285eb676abb6042d3d0eabda2c93aa12df1f9d1e5c72e17dabdd30673590` |
| Older repository | `ac1ddb3c3b3bc4952aa546077ede6a5da16dace2` | `5008aae9c8e3f460938667589c0a358b97e2f23558854925257a923925accdbc` |

These labels identify the supplied archives, not a claim of a newly fetched
remote HEAD. The archive delivered to the user is a complete source replacement;
it intentionally omits compiler caches, binary packages, virtual environments
and private Git metadata.
