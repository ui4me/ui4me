# Changelog

Each release ships one version of the Python wheel (`ui4me` on PyPI), the PowerShell module
(`Ui4me` on the PowerShell Gallery) and the native SDK and LuaJIT binding (GitHub release
assets), all built from one commit. The project overview is
[`docs/PROJECT_SUMMARY.md`](docs/PROJECT_SUMMARY.md), and the contract is in
[`docs/API.md`](docs/API.md).

## 1.0.1

A maintenance release: no new features; ABI 1, the wire schema and the Python and PowerShell
APIs are unchanged.

- **Python shutdown:** `App.close()` (and leaving a `with App()` block) waits at most 30 s for
  running background functions instead of indefinitely, then leaves a function that ignores
  `task.cancelled` on its worker thread with a `RuntimeWarning`. `close(timeout=None)` keeps the
  old unlimited wait. Nothing is killed.
- **LuaJIT:** published on LuaRocks as `ui4me`. The release zip now contains a README, the
  licence and the example, and states that the native library comes from the SDK zip.
  `examples/lua/notes.lua` runs from the zip layout.
- **Release gates:** the Linux and Windows native gates end with one verdict
  (`tools/gate/verdict.py`): a missing, skipped, blocked or failed mandatory step fails the
  gate, and so does a nonzero exit status. The gate scripts only delete an output directory
  they created (marked with `.ui4me-gate`) or an empty one. The Windows gate runs the Lua unit
  tests.
- **Binding verification:** support-profile coverage is no longer decided by searching binding
  sources for op names. Python and PowerShell tests call every declared operation through the
  public API on the real native library.
- **Soak and memory checks:** unmeasured metrics and too few samples now fail instead of
  passing; Windows measures working set, handles and threads; the data-app memory check on
  Windows measures the application process, not the venv launcher.
- **Publishing workflow:** runs the unit tests and smoke-tests the exact assembled packages on
  Linux and Windows before publishing to PyPI, the PowerShell Gallery, GitHub and LuaRocks, and
  reports every job's result.
- **Packaged demo resource:** the foundation page shipped in the packages keeps its UTF-8
  sample value again; a post-1.0.0 README change had replaced it and broke installed case F11
  and the 1.0.0/0.4.0 contract clients (`examples/foundation` keeps the English sample).
- **Renderer test:** the header-bomb memory bound is measured in an isolated child process (Linux)
  instead of the whole test binary's peak RSS, and is reported as not measured elsewhere.
- **Documentation:** the acceptance catalogue (`quality/scenarios.json`) covers F01–F20 and the
  current release; the 1.0.0 qualification record is corrected (its Windows LuaJIT step had
  failed).

## 1.0.0

This is the stable Core. From this release on, compatibility is governed by
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md): ABI 1, an additive wire schema, and the
canonical support profile [`docs/SUPPORT_PROFILE_V1.json`](docs/SUPPORT_PROFILE_V1.json).

- **Printing and paged media:**
  - `paginate`, `get_page_rects`, `render_page` and `export_pdf`, covering `@page`, named
    pages, margin boxes, page breaks and widows/orphans.
  - Native printing: Windows uses the system print dialog; Linux uses the desktop's print
    portal.
- **Rich editing:**
  - `contenteditable` hosts edit a bounded HTML subset: b/i/u/s/code/links, paragraphs and
    line breaks.
  - Sanitized paste and undo/redo.
  - `exec_edit` and `get_edit_state`.
  - `plaintext-only` keeps plain-text editing.
- **Background work:** `run_in_background` (Python) and `RunInBackground` (PowerShell) settle
  on the owner thread, with cancel, stop and queue-pressure handling.
- **Diagnostics:** `get_diagnostics` (schema 1, redacted by default) and `explain`, which says
  why a property has no effect.
- **Long documents and soak:** long-document scalability work and a soak driver
  (`tests/soak/soak.py`).
- **LuaJIT binding:** `bindings/lua`, a pure FFI binding over the C ABI.
- **Release engineering:**
  - The canonical support profile, with binding coverage checked against every wire op.
  - Platform capability expectations recorded on KDE (Wayland) and Windows.
  - An upgrade and rollback matrix from 0.4.0.
  - `SHA256SUMS` in the release assets.
- **Deferred by owner decision:** the GPU backend, macOS and ARM64.

## 0.9.0

- **CSS:**
  - Transitions and keyframe animations on the document clock, and `@starting-style`.
  - `content-visibility`, `contain-intrinsic-size`, `field-sizing` and `resize`.
  - `backdrop-filter` and `light-dark()` images.
- **Inline SVG:** rendered with per-shape hit testing, under a fixed static SVG profile.
- **Text:** hyphenation for pt, nl, sk, pl and uk.
- **Fixes:** clicks no longer hit the cut-off corners of rounded boxes, and blur is bounded.
- **Tests:** conformance fixtures for layout, Unicode text and framework-style markup.

## 0.8.0

- **Editing:** plain-text `contenteditable`.
- **Pointer and touch:** touch input; pointer events and pointer capture.
- **Scrolling:** smooth scrolling and `scroll-behavior`; scroll snapping and
  `overscroll-behavior`.
- **Controls:** refined range, number, progress and meter semantics.
- **Popovers:** HTML popovers and a CSS anchor-positioning subset.

## 0.7.0

- **Desktop services:** notifications, a tray/status icon with a menu, window menu bars and
  context menus (Windows; accelerators everywhere), global shortcuts, the OS dark and
  high-contrast preferences, rich clipboard HTML, drag and drop, pointer confinement and lock,
  startup activation, and single-instance open-with.

## 0.6.0

- **Document and HTML interface:** HTML serialization, author stylesheets, generation-safe node
  references, text geometry, computed style, form validity, file inputs and a link policy.

## 0.5.0

- **Input and accessibility:** international keyboard layouts and IME, assistive-technology
  correctness, the capability report, media environment overrides, and per-line accessible
  text.

## 0.4.0 and earlier

The Core foundation: windows, documents, forms, selection, clipboard, dialogs, the
programmable DOM, scrolling, and the Python and PowerShell bindings over the C ABI.
