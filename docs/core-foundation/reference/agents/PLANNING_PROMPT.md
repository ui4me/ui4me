# Prompt to give an autonomous planning/implementation agent

Copy the block below to an agent with a checkout of `https://github.com/ui4me/ui4me` and **this entire research ZIP** available. The agent must inspect both this package and the actual current source. For donor-code investigation provide `bigbatmanorg-ui4me-old.zip` separately if available.

---

You are the responsible architect and implementation agent for UI4ME's next release. The attached `UI4ME_Future_Architecture_and_Roadmap_2026-11-11` package is a research baseline, not executable source or an unconditional scope mandate.

**Product boundaries:**
- UI4ME Core is a minimal native window and HTML/CSS/DOM/text/layout/input/event/OS runtime with stable Python/PowerShell bindings and language-neutral C ABI. It has NO required JavaScript, browser engine, local server, app storage, ACP/SSE code, business logic or component framework.
- `ui4me-ui` is a separately installed/versioned optional convenience package for declarative components, reactive state, Markdown, chat/log UI, themes and composable widgets. It must depend solely on public Core capabilities; Core cannot depend on it.
- Specialized editors/terminals/charts/media are optional extensions. ACP/SSE, authentication, databases, project/session management and tool approval policies belong to consumer applications.

**Before editing:**
1. Record current `main` SHA, dirty state and existing branches. Preserve user work. Current research was pinned to `cbb8a5efa50505e262b1747c55e38be5838e6b8d`; reconcile any later changes rather than assuming it is still HEAD.
2. Read `README.md`, `ARCHITECTURE_CHARTER.md`, `ROADMAP.md`, `FEATURE_CATALOG.md`, `OLD_SOURCE_TRACEABILITY.md`, `CRITICAL_REVIEW.md`, `RELEASE_ENGINEERING.md`, and `decisions/ADR_INDEX.md` from this package.
3. Read current repo `AGENTS.md`, `docs/PROJECT_STATUS.md`, current source/tests/packaging and the relevant APIs. The package's `current_02` field is *historical inspection*, not a live test result.
4. Select the smallest coherent version slice (finish 0.2 qualification first; then 0.3 core DOM/scroll/selection). Do not start implementing the whole 224-feature backlog. For each chosen ID, give current implementation status, owner, dependencies, old donor anchors, alternatives, acceptance tests, and explicit exclusions.
5. If original `bigbatmanorg-ui4me-old.zip` is available, SHA-256-verify it, then inspect the exact paths and line ranges in `data/old-source-references.json`. Look for stubs, disabled code, ownership assumptions, old regressions and release-blocking failures. Source location is an engineering lead, not success evidence. Use `data/old-test-index.csv` only for test discovery.

**Execution:**
- Implement full functionality rather than an audit-only status, where authorized by the user's task. Work autonomously, use focused tests per change and larger suite only at integration/final source freeze. Preserve the current native host and both binding contracts unless a demonstrated defect requires a bounded change.
- Every new Core primitive must be usable via public Python and PowerShell bindings by an app that installs no optional UI component library. Run a Core-only consumer fixture that uses raw HTML/CSS and exercises the primitive.
- Component/library features must live in an independent package, with Core-only install checks showing no reverse dependency. Never silently import a network stack, browser, npm, JS, auth system or database into Core.
- Keep DOM identities generation-checked, callbacks outside locks/borrows, worker results bounded, and installed artifacts source-bound. Preserve explicit OS unsupported outcomes (especially Wayland limitations).
- Use the existing repo packaging/CI workflows; do not create redundant tools or large showcase projects. Compare actual behavior on Linux KDE/Wayland and Windows native desktop where available.
- No arbitrary or unverified performance claims; measure repeatable candidate scenarios against a recorded baseline.

**Before declaring completion:**
- Re-run relevant unit, source/ABI, headless, installed and native tests for the exact final source. Use a single combined release manifest where required and test real upgrades from public prior versions.
- Update feature registry for chosen IDs: actual current implementation files/lines, native OS support, exact tests, acceptance, known limitations, source SHA, version and evidence status. Update project handoff, release notes and relevant ADRs.
- Report PASS/FAIL/UNRUN/BLOCKED distinctly and identify remaining public-release blockers. Do not pass missing evidence by default.
- Do not push/merge/tag/publish without explicit authorization. Stop for truly unavailable access or dangerous permission only; otherwise complete the agreed bounded milestone autonomously.

**Final response:** the implemented features by ID, architectural decisions, precise code changes, affected API/ABI, build/package commands, OS verification, source/artifact hashes and remaining blockers. Keep the Core/UI/application boundaries explicit.

---

## Suggested next specific request

> Plan and implement Core 0.3, taking the smallest dependency-complete P0/P1 subset of DOM-007/008/009, DOM-017, INTERACTION-006/007, TEXT-007/008 and related BIND/QA acceptance features, after first reconciling whether 0.2 has completed native qualification. Add actual implementation references to the source inventory. Do not build optional UI widgets as part of this Core release.

Use the actual IDs from `data/features.json` as the authority. The sample above is illustrative, not an accepted change order.
