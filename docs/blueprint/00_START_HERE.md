# UI4ME UI: Product Blueprint and Implementation Program

Date: 2026-11-12. Status: architecture proposal / unimplemented backlog, not a claim of working functionality.

## Objective
Make UI4ME UI the easiest way to build polished, responsive, native desktop applications with Python or PowerShell while keeping full CSS/DOM/native Core access. Default development should feel like NiceGUI + Bootstrap/Mantine; advanced development should retain Qt-like desktop patterns and Radix-like composition and accessible behavior. No mandatory JS, browser, local HTTP server, Node toolchain, or separate rendering engine.

## Evidence and scope
Static inspection of these supplied archives only (no application code, tests, builds or benchmarks executed):
- ui4me_ui.zip: UI package 0.4.0, Python and PowerShell implementations, actual API, published release-gate assertions, theme.css, documentation.
- ui4me-main(7).zip: Core 1.0.1 source and docs/API.md.
- UI4ME_UI_Implementation_Specification.zip: original implementation spec and stale component matrix.
- Official framework documentation from Bootstrap 5.3, Mantine, NiceGUI, Qt 6, Flet, Radix, MUI X, WAI-ARIA, and Python/PowerShell packaging.

## Decisions recommended
1. UI4ME Core remains sole native runtime and owner of HTML/CSS, layout, DOM, events, window/OS and accessibility primitives.
2. UI4ME UI owns components, CSS presets, behavior, state, validation, responsive abstractions, navigation, commands, overlay orchestration, and generic desktop application utilities.
3. Keep raw Core escape hatches supported and documented, but protect managed DOM ownership and ID validity.
4. Support whole-theme *replacement*, additive stylesheets, token overrides, and per-instance classes/styles; do not assume today's additive `app.css` is sufficient for theme replacement.
5. Maintain Python and PowerShell parity by shared semantics, schema, reference examples and conformance; independent idiomatic implementations remain appropriate.
6. Preserve package separation while UI evolves. A single install experience does not require merging source repos or release trains. Python `ui4me-ui` already depends on Core `ui4me`; PowerShell module already declares `Ui4me` in `RequiredModules`.
7. Build a wide component catalogue over time but prioritize core behavioral infrastructure, customization and forms/data/overlays before low-value decorative widgets.
8. Clearly distinguish real Core blockers from UI-level wrappers, compatibility verification, and platform limitations.

## Document index
- `01_ARCHITECTURE_API_AND_THEMING.md`: architectural contract, proposed APIs, styling, customization, extensibility, safety and developer experience.
- `02_FEATURE_CATALOG.md`: wide categorized feature list with status and priority; see also machine-readable `FEATURE_MATRIX.csv`.
- `03_DEVELOPER_JOURNEYS.md`: scenarios and developer workflows at each customization level.
- `04_ROADMAP_ACCEPTANCE.md`: dependency-ordered implementation program and release gates.
- `05_CORE_HANDOFF.md`: separate Core issues, enhancements, and verification requests; not unverified bug accusations.
- `06_PACKAGING_AND_VERSIONING.md`: separate vs merged analysis and recommended distribution strategy.
- `07_RESEARCH_SOURCES.md`: primary-source links and transferable design lessons.

## Definitions
- `Existing`: present in 0.4 source/docs, not independently re-tested.
- `Partial`: code exists but proposed contract is missing or incomplete.
- `New`: not present as a high-level UI feature in inspected 0.4 public API.
- `P0`: correctness/architecture prerequisite; `P1`: essential general-public GUI; `P2`: broad toolkit coverage; `P3`: optional/specialized.
- `Owner=UI`: implement in UI; `Core API`: use existing Core methods; `Core request`: request upstream capability/verification; `App`: leave domain-specific behavior to applications.

## Immediate next agent task
Do not implement the full catalogue in a single pass. Reconcile current specification, audit P0 semantics with tests, define component contracts and theme replacement, implement waves in `04_ROADMAP_ACCEPTANCE.md`, and keep the Core handoff independent. Every candidate feature must name a public API, user use-case, Core mapping, Python/PowerShell parity, keyboard/AT behavior, theme/CSS contract, degradation strategy, examples, unit/integration tests, and release acceptance gate.
