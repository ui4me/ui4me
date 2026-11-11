# UI4ME Core — project summary

The single overview of UI4ME Core: what it is, what is implemented, how it is built, where it
runs, how it is released and what is still missing. Details live in [`API.md`](API.md) (the
public contract), [`DEVELOPMENT.md`](DEVELOPMENT.md) (build, test, release) and
[`COMPATIBILITY.md`](COMPATIBILITY.md) (stability rules).

## What UI4ME is

UI4ME Core is a native desktop UI runtime for applications written in Python, PowerShell or
LuaJIT. An application supplies HTML and CSS; Rust owns parsing, style, layout, text shaping,
painting, input, accessibility and native windows; the application logic stays in the host
language and talks to Core through one C ABI. It is aimed at responsive local desktop utilities
and multi-window tools.

It is deliberately **not** a browser: there is no JavaScript engine, webview, network resource
loader, embedded server, plugin system or out-of-process UI broker. `<script>`, iframes,
`object`/`embed` and inline event handlers are rejected; resources load only from an
application's local asset root. A UI component framework on top of Core is a separate concern
and is not part of this repository.

## Current state

**Version 1.0.0, released** (2026-11-12) to PyPI (`ui4me`), the PowerShell Gallery (`Ui4me`) and
GitHub (`v1.0.0`: native SDKs, LuaJIT binding, `SHA256SUMS`). ABI 1 and the wire schema are
frozen by [`COMPATIBILITY.md`](COMPATIBILITY.md). Earlier releases (0.2, 0.4–0.9) are tagged;
[`CHANGELOG.md`](../CHANGELOG.md) lists what each added.

Implemented functionality, by area:

| Area | What Core provides |
| --- | --- |
| Documents | Nested HTML with unique public ids; insert/remove/move, text and attribute reads, selector queries, atomic batches, streaming `append_text`, bounded logs (`trim_children`), HTML serialization, author stylesheets with diagnostics, generation-safe node references |
| CSS and layout | Stylo cascade and selectors, custom properties, media queries, block/inline/flex/grid/multicolumn/floats (Taffy), positioning including sticky, overflow and ellipsis, transitions and keyframe animations, `@starting-style`, `content-visibility`, `field-sizing`, `resize`, anchor positioning (subset), scroll snapping and smooth scrolling, `@page` pagination. The supported subset is a fixed, versioned CSS profile (1.27.0) |
| Painting | Software rasterizer: backgrounds, gradients, borders and radii, shadows, filters and `backdrop-filter`, clip paths and masks, raster images, inline SVG (static profile) with per-shape hit testing, scrollbars |
| Text | Unicode shaping and wrapping with font fallback, system fonts and local `@font-face`, bidi-aware caret and selection, hyphenation (en, de, fr, es, pt, nl, sk, pl, uk), IME composition, keyboard layouts, dead keys and AltGr |
| Controls and editing | Text/password/number/range inputs, textarea, buttons, checkbox/radio, labels, `select`, `dialog`, `details`, popovers, `<input type=file>` with the native picker, constraint validation and form submission; plain-text and rich `contenteditable` (formatting, links, paragraphs, sanitized paste, undo) |
| Interaction | Keyboard focus and Tab order, document text selection and copy, pointer events and capture, touch, drag and drop, default-action rules, scroll API with follow-the-end logs |
| Windows and OS services | Multiple windows with show/hide, focus, minimize/maximize/fullscreen, constraints, icons and monitor information; native file dialogs; clipboard (text and sanitized HTML); notifications; tray icon; window menus and context menus; global shortcuts; OS dark/high-contrast preference; single-instance activation; printing through the native dialog; PDF export; a `capabilities()` report of what the platform actually supports |
| Accessibility | AccessKit bridge to AT-SPI (Linux) and UI Automation (Windows) with roles, names, states, values, text runs with caret and selection, and assistive actions; keyboard operation of every control |
| Runtime | Owner-thread dispatch, timers, posts, background work that settles on the owner thread, bounded queues and assets, versioned diagnostics (`get_diagnostics`) and `explain` |

## Architecture

| Location | Owns |
| --- | --- |
| `crates/ui4me-core` | The C ABI (`include/ui4me.h`), the typed JSON protocol, application and session lifecycle, the winit/softbuffer native loop, desktop services, printing, diagnostics |
| `crates/ui4me-renderer` | One document facade over private style (Stylo), layout (Taffy), text, scene, raster, interaction, accessibility and pipeline modules |
| `crates/ui4me-document` | The canonical DOM, generational identities, parsing, control state and atomic mutations |
| `crates/ui4me-assets` | Local resource policy, image and font decoding, cache accounting, bounded admission and the process asset workers |
| `crates/ui4me-engine-types` | Internal identifiers, status codes and value types shared by the engine |
| `bindings/python` | ctypes loader, the `ui4me` package and its build backend |
| `bindings/powershell` | The `Ui4me` module and its .NET bridge (`Ui4me.Managed`) with a retained owner thread |
| `bindings/lua` | `ui4me.lua`, a pure LuaJIT FFI binding over the C ABI |
| `patches/` | Carried, verified sources of Stylo, Taffy and accesskit_atspi_common with UI4ME corrections |
| `tools/`, `dev.py`, `scripts/`, `.github/` | Build, packaging, testing, release gates and publication |

Rendering stages are not public crates or ABI objects. A host sees a document interface, input
messages, rendered pixels and plain event records. Every public operation is a JSON command
(`protocol.rs`) sent through `ui4me_session_command`; new functionality is added as new commands
or optional fields, never by changing ABI 1.

**Important decisions:**

- **One fixed renderer profile.** CSS support is an explicit, versioned table
  (`style/profile/table.rs`): unsupported properties are dropped before Stylo and reported in
  diagnostics instead of half-working. Gecko-only Stylo features are enabled through small
  carried patches (`patches/stylo/P-006-*.patch`).
- **Software rendering.** The rasterizer runs on the CPU; frames are requested only while
  something animates, so an idle window uses no CPU.
- **Incremental work with a proof.** Layout replays unchanged block rows and the scene reuses
  unchanged display lists only when the result is provably the same; otherwise the whole
  document is recomputed. Differential tests compare incremental results with a cold rebuild.
- **Language-neutral host contract.** Bindings are thin: the same commands and events serve
  Python, PowerShell, LuaJIT and C.

## Engineering invariants

- **Owner thread.** Windows, documents and timers live on the thread that created the
  application. Only `post`, `stop` and completion publication are callable from other threads.
  The owner releases its document borrow before calling into Python or PowerShell, so a callback
  can issue further commands. Rendering and decoding never hold the shared queue lock.
- **Lifetimes.** Run and callback leases are tracked separately from the lifecycle phase;
  destroy is refused until `run` and every callback have returned. Foreign callbacks never
  unwind across the ABI. A Rust panic is contained: the session is stopped and poisoned, and new
  sessions are refused until the process restarts.
- **Generational identity.** Elements are addressed by HTML id, nodes by generational
  references. A removed node's queued events are dropped, and a stale reference is an explicit
  error (code 4), never a different node.
- **Bounded everything.** Windows, posts, timers, completions, DOM size, input sizes, asset
  admission, decoded caches, undo history and diagnostics all have fixed limits, and exceeding
  one is an explicit error (limits in [`API.md`](API.md#limits)).
- **Assets.** The process has two fixed asset worker threads shared by all sessions. Shutdown
  stops intake and cancels interests without joining a codec on the UI thread. Admission stays
  charged while a job is queued, running or awaiting delivery.
- **Local only.** Resources resolve inside the document's asset root; remote URLs, `file:`
  escapes and symlink escapes are refused (covered by a red-team test with a connection-counting
  listener).
- **Honest platform reporting.** Anything a platform forbids (for example window activation on
  Wayland) returns `unsupported` with a reason, and `capabilities()` reports the measured status
  per platform.

## Bindings

- **Python** (`ui4me` on PyPI, Python 3.11–3.14): `App`, windows, events, `post`, timers,
  `run_in_background`, and a method for every wire operation. Wheels include the native library
  (`manylinux_2_35_x86_64`, `win_amd64`); an sdist builds from source with the pinned toolchain.
- **PowerShell** (`Ui4me` on the PowerShell Gallery, PowerShell 7.4+): `Invoke-Ui4meApp` runs an
  application on a retained native owner thread in a fresh runspace; the module contains both
  native payloads. `Work` and `RunInBackground` run background work in isolated runspaces.
- **LuaJIT** (`ui4me-lua-1.0.0.zip` on GitHub): a single FFI file covering documents, events,
  timers, posts and values. It loads the native library named by `UI4ME_NATIVE_LIB` (an absolute path) or the one next to `ui4me.lua` (or in a `native/` directory beside it).
- **C:** `include/ui4me.h`, shipped in the native SDK zips.

Every wire operation has a Python and a PowerShell method (checked by a test that generates
[`SUPPORT_PROFILE_V1.json`](SUPPORT_PROFILE_V1.json)).

## Platforms

| Platform | Status |
| --- | --- |
| Linux x86-64, Wayland | Supported; qualified on KDE Plasma (KWin) |
| Linux x86-64, X11 | Supported through winit; not separately gated |
| Windows x64 (10/11, Server 2022) | Supported; qualified on Windows Server 2022 |
| macOS, ARM64 | Not supported (deferred) |

Platform differences are reported, not hidden: on Wayland a client cannot focus, activate, hide
or set its own icon, and receives no file drops (winit 0.30); OS theme changes are observed only
on Windows; X11 cannot lock the pointer. The measured per-platform status is
[`reference/PLATFORM_CAPABILITIES_V1.json`](reference/PLATFORM_CAPABILITIES_V1.json).

## Build, test and release infrastructure

- `dev.py` is the single entry point: `doctor`, `version`, `build`, `test` (unit, installed,
  native suites), `package`, `assemble` and the evidence and publication commands. Build receipts
  record an exact source identity, so tests and packages refuse stale builds.
- Tests: Rust unit and differential tests in each crate (including fuzz harnesses run with a
  time budget), binding unit tests, installed-package contract cases F01–F20 for C, Python and
  PowerShell, native desktop journeys driven by real OS input (private nested KWin sessions on
  Linux, an interactive test-user session on Windows) including Orca and NVDA, an
  upgrade/rollback matrix from 0.4.0, and a soak driver.
- CI (`ci.yml`) builds and tests both platforms on every push. `publish.yml`, run manually,
  builds on clean runners and publishes to PyPI, the PowerShell Gallery and GitHub.
- The release procedure, including the native gates in `tools/gate/`, is in
  [`DEVELOPMENT.md`](DEVELOPMENT.md#release).

**1.0.0 qualification** (candidate `b58399f`, identical source identity on both hosts): installed
C, Python and PowerShell suites passed on Linux and Windows. Every native journey and probe
passed on KWin and on Windows: chat, files, input with IMEs, dialogs, window, AT-SPI or UIA,
environment, file input, desktop services, animation, printing, capabilities, Orca or NVDA, the
data application, and the LuaJIT probe or unit tests. The upgrade matrix passed on both
platforms. A one-hour soak of the installed wheel completed 55 sessions with no errors and flat
memory. Fuzzing (about 48 CPU-minutes over six harnesses) found no crash. All input in these
tests is automated.

## Known limitations and technical debt

- **Large documents:** updates stay around 10–50 ms up to roughly 1,000 rows of a log, but take
  80–600 ms at 3,000–10,000 rows, because style snapshots, display-list building and raster are
  still linear in the document. Appending and trimming at the start of a log does not replay
  layout (box ids shift). A document holds at most 65,536 nodes.
- **No GPU backend;** no macOS or ARM64 builds.
- **PDF export and printing are raster** (one image per page, text not selectable); no print
  preview.
- **Rich editing** covers a bounded subset (bold, italic, underline, strike, code, links,
  paragraphs, line breaks): no lists, tables or images inside rich hosts, and element ids inside
  a rich host are not stable across edits.
- **CSS gaps** (reported as unsupported): `display` transitions, `animation-timeline`,
  `position-try-fallbacks`, `position-area`, `anchor-size()`, `popover=hint`, `clip-path` and
  `filter` `url()`, `cross-fade()`, `shape()`, `corner-shape`, `shape-outside`; ruby layout;
  `content-visibility: auto` never skips work.
- **SVG:** a static profile only ([`reference/SVG_PROFILE.md`](reference/SVG_PROFILE.md)); SVG
  `<text>` is not drawn.
- **Input and platform (winit 0.30):** no IME surrounding text, no stylus API, no Wayland
  drag and drop, OS theme changes only on Windows. A Windows Chinese IME has not been exercised.
  Windows touch has not been tested.
- **Accessibility:** no WCAG claim. Narrator has not been run; Orca was checked through its
  braille presentation (no speech server in the test session), NVDA through its speech log.
- **Clipboard:** text and HTML only, no images.
- **Fuzzing** is seeded and time-budgeted, not coverage-guided, and runs on Linux.
- **Test environment detail:** the private KWin used by `--plain` probes stores output settings
  in the user's `~/.config/kwinoutputconfig.json`; the environment probe restores the scale it
  changes.

## Third-party sources and licences

UI4ME is MIT-licensed. It carries modified copies of Stylo, Taffy and accesskit_atspi_common
under `patches/` (under their upstream licences, declared in their files and `Cargo.toml`; each has a `verify.sh` that checks the patch set), the
UA stylesheets with their provenance (`crates/ui4me-renderer/src/style/ua/PROVENANCE.md`),
hyphenation patterns with their notices (`crates/ui4me-renderer/src/text/data/hyphenation/NOTICES.txt`)
and the Noto Sans last-resort font under the OFL (`crates/ui4me-assets/assets/last-resort/`).
Packages include the native dependency notices and font licences.
