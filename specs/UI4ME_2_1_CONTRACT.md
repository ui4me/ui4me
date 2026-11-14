# UI4ME 2.1 — implementation and acceptance contract

**Baseline:** user-provided `ui4me-main(20261114-044324).zip` and `ui4me-core-main(5).zip` (Core 1.0.1).
**Target:** 2.1.0; source-compatible high-level UI framework. **No native renderer or IPC copy.**

## Architectural decisions

1. UI4ME Core is the only window host, document engine, accessibility provider and native integration layer. This package is pure Python and pure PowerShell plus CSS and assets.
2. The normal entry point is the user script: `python app.py`, `uv run app.py`, `pwsh -File app.ps1`, `powershell.exe -File app.ps1` on Windows. Core's `Application.start` / `Start-UI4MEScript` perform bootstrap, preserve process supervision. Advanced Core manifests and `ui4me-run` / `Start-UI4MEUiScript` are compatibility/test modes only.
3. Python user code runs on one UI owner thread. Core notification threads post immutable event payloads to owner thread; lifecycle and shutdown cannot starve. Event queue backpressure is bounded/coalesced where safe; discrete clicks, control edits and close events must never be silently dropped.
4. PowerShell callbacks execute on the application runspace, not worker threads. Background work may use isolated runspaces; completion delivery, cancellation and handler disposal happen on owner runspace.
5. Every component has an owner, stable DOM identifier, lifecycle, immutable public meaning, readable props and styling hooks, accessible role/name and keyboard behavior. Dynamic regions must dispose removed state, callbacks and timers. Raw Core escape hatch is explicit and must not mutate UI4ME-owned nodes.
6. Functional CSS and visual CSS are separate. Themes override the visual layer only; CSS token names and `data-u4-*`/`u4-*` classes are stable. Python and PowerShell ship byte-identical default CSS.
7. Python and PowerShell APIs are idiomatic but feature contracts and acceptance fixtures are shared. Unsupported native services are capability-checked, not invented.
8. Version compatibility: `ui4me` 2.1 requires `ui4me-core` >=1.0.1,<2; `UI4ME` 2.1 requires `UI4ME.Core` >=1.0.1,<2. Release artifacts must not vendor Core or Rust.
9. Core launcher runs the module/script twice at start. User side effects must happen after the high-level UI bootstrap. Document this in both languages.

## Cross-language P0 / P1 behavior requirements

- Bootstrap & lifecycle: real `python/uv/pwsh/powershell` direct launch; single/multiple instances; default app ID noncolliding; pass through arguments; backend failure visible; no stale process; optional old launch modes.
- Reactivity: state snapshots; computed dependencies / explicit dependency list where idiomatic; transaction/batch; deterministic subscriber ordering; callback errors captured; disposal removes subscriptions.
- Control inputs: button, link, input, textarea, number, checkbox, switch, radio, select, slider, date, time, color; value/disabled/label/error semantics; no event feedback overwriting newer input; IME composition tested.
- Layout: row/column/grid/scroll/card/shell/sidebar/toolbar/panels/responsive CSS; demo narrow window.
- Overlays: dialogs and confirm, toast, drawer/menu, accessible focus restoration and Escape. Never promise native OS menus when Core cannot provide them.
- Data: table with sort/search/selection/paging (at least locally), keyed list and reactive conditional regions; full data-source progress/cancel/error path in Python and useful equivalent in PowerShell.
- App services: persistent settings; cancellable background work; desktop clipboard/file dialogs; capability inspection; multiwindow in both languages.
- Documentation: runnable Python and PowerShell quickstart, user-facing API references, components and recipes, offline gallery, coding agent skills, publisher-specific descriptions, platform limitations.
- Qualification: fast unit/contract tests, real Core headless tests, native KDE Wayland on Linux, native Windows, PowerShell 7 and Windows PowerShell 5.1; installed wheel & module with zero local source leakage; release readouts separate executed from not run.

## Non-goals / legitimate constraints

- No WebKit/Chromium/JS, Node/npm runtime, HTTP server, multiuser service, or duplicate renderer.
- No invented OS notification/tray/native menu/PDF/export APIs until Core supports them.
- No browser-exact HTML/CSS guarantees; use Core capabilities and document exceptions.
- No fake accessibility certification based on static markup tests.

## Release gates (local agent must execute in order)

0. Establish clean source identity and resolve version registry collisions; do not publish if version already exists.
1. Linux Python: pytest, package builds, direct `python`, `uv`, real-host headless, native interactive gallery, stress and failure paths.
2. Windows Python: fresh wheel install, direct Python, real RDP/desktop input, shutdown/error/IME.
3. Linux PowerShell: module import, Pester, native application, direct `pwsh`, model binding, gallery, resource/lifecycle checks.
4. Windows PowerShell: pwsh and Windows PowerShell 5.1; Gallery-layout install; real input, callbacks, module casing.
5. Full integration/release gate: all Python and PowerShell journeys, source manifest, docs examples, dependency checks, build artifacts, user permission + publishing.

**No simultaneous GUI tests on the same display, no concurrent edits to a shared release file, no full expensive suites after every small change.**
