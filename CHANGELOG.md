# Changelog

Each release ships one version of the Python wheel (`ui4me` on PyPI), the PowerShell module
(`Ui4me` on the PowerShell Gallery) and the native SDK and LuaJIT binding (GitHub release
assets), all built from one commit. Qualification evidence for every release is in
[`docs/core-roadmap/PROGRESS.md`](docs/core-roadmap/PROGRESS.md), and the contract is in
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

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
