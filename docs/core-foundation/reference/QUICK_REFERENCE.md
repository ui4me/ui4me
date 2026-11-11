# One-page planning reference for UI4ME

**Identity:** Minimal native Rust HTML/CSS engine with raw Python/PowerShell API, NOT a browser and NOT an agent framework. One Core runtime, optional components, app-owned logic.

| Ownership | Engine/platform responsibilities | What stays out |
| --- | --- | --- |
| Core Renderer | HTML/CSS, DOM mutations, standard control defaults, text selection, focus, hit testing, geometry, scroll, paint, event dispatch | Markdown, reactive state, chat components, models, routing |
| Core Native Host | Windows, lifecycle, owner queue, DPI, clipboard, file/folder dialogs, display/OS capabilities | File-manager workflows, upload, credentials, API connections |
| Optional UI4ME UI | Component markup, themes, bindings, Markdown, chat/log, menus, tabs, dialogs composition, virtual list | Browser engine, hidden Rust APIs, mandatory core dependency |
| Specialized extensions | Code editor, terminal/PTY, charts, maps, media, PDF viewer | Mandatory install footprint |
| Applications | ACP/SSE, databases, auth, project/session management, permissions policy | Changes to Core semantics driven by a single app |

**Now:** finish Core 0.2 native/installed qualification. **Core 0.3:** append/mutate/batch DOM, scroll/geometry, static selection/copy, bounded streaming. **Core 0.4:** standard HTML controls/modal/focus, native OS file picker/windows, a11y semantics. **Core 0.5:** proven stability/performance and selected feature conformance. **Optional UI 0.1:** independently versioned components after useful Core 0.3 APIs. **Optional UI 0.2:** reactivity and advanced component composition when Core constraints allow. **Extensions:** demand-driven, never gate Core 0.3.

**Evidence:** 224 feature records. 144 original donor-code anchors with verified file/line ranges (129 source-present, 15 partial/related). Original donor was NOT release-qualified. 46 separate test-file leads are **not pass claims**. Use `FEATURE_CATALOG.md` and `data/features.json`.

**First source to inspect:** `ui4me_old/engine/crates/ui4me-dom/src/parse/fragment.rs` for incremental HTML; `.../ui4me-interaction/src/scroll.rs` for scroll API; `.../ui4me-text/src/paragraph/frozen.rs` for related text selection geometry; `.../ui4me-ffi/src/api/dialog.rs` for dialog API leads; the exact ranges are in `data/old-source-references.csv`.

**Agent order:** current repo SHA → old source match → ownership rubric → bounded feature slice → public contract → targeted tests → installed desktop verification → record evidence → publication authorization.

**No-go defaults:** add JS/browser/Node/webserver to Core; force `State` base classes; embed LLM protocol in UI; use old crate count as roadmap; promise NiceGUI parity; run all WPT every small change; claim a11y from ARIA attributes alone.
