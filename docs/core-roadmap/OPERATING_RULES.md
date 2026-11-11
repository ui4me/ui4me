# Execution rules for autonomous Claude Code

## Scope/precedence

`main` is the live source of truth, public `include/ui4me.h` + typed protocol remain the native contract, Python and PowerShell expose equivalent outcomes. The uploaded 0.4 archive and this roadmap are **snapshots**, not permission to revert newer changes. First inspect Git status and latest version, read project safety rules, and scan only files relevant to the next work item. Historic `CLAUDE.md` 0.2→0.4 completion requirement is superseded by the user's new 0.5+ roadmap mandate; all its nonmilestone engineering constraints remain valid.

## Autonomy and models

- Primary **Sonnet** session performs normal architecture integration, coding, source lookup, edits and tests. Run `claude --model sonnet` if your config differs; existing shared `.claude/settings.json` should already select Sonnet.
- Max **one** extra Sonnet worker, only for a genuinely separable task (e.g. source-path discovery or isolated Windows native adapter). Main owns contract and merges. No swarm, long-lived worktree farm or independent agents editing the same protocol/ABI files.
- **Opus** only for one precise hard architectural question after Sonnet failed to resolve it: unsound lifetime, platform semantics, ABI-breaking incompatibility, irreducible safety tradeoff. Return implementation to Sonnet. No Opus for copying, docs or routine testing.
- Work autonomously through small end-to-end slices. No plans-only response, no routine approval requests. Pause for credentials, irreversible/destructive operations, registry publication, essential unresolved architecture, or actual inability to validate a required native path.
- Prefer copy/adapt existing implementation; **do not bulk port** old modules. Verify parser/layout/paint integration, C ABI and two bindings before declaring work complete.

## Testing discipline

- During edits: compile and run **targeted** unit/contract/fixture tests for modified module and dependency; affected C/Python/PowerShell boundary tests. Do not re-run broad 3,000+ Rust or full WPT for an unrelated docs or small module change.
- At one release candidate: existing supported Linux KDE Wayland + Windows x64 GUI journeys, C/Python/PowerShell installed examples and the relevant focused regression suites. Use the existing cross-platform skill. SSH alone is not interactive native Windows evidence.
- Rerun only failing relevant suites after a fix; perform a final integrated gate once for the final candidate. Capture exact source SHA and artifact identity. Explicit `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED` status; never infer.
- Judge perf by visible stalls/unbounded resource usage and structural regressions, not tiny 5–10ms differences. CPU/GPU parity should satisfy correctness, not arbitrary speed targets.
- OS-impossible operations (Wayland activation/position/host restrictions) must have explicit capability/unsupported status rather than invented implementation or indefinite retries.

## Git / publication / reporting

- Prefer main as the stream; one short-lived branch/worktree only if isolation helps. Do not force push, delete user branches, reset user edits or overwrite a live checkout without explicit approval. Commit coherent slices promptly and safely. Follow existing branch protections.
- Do not automatically publish to PyPI, PSGallery, create tags or releases, push major breaking changes, change remote secrets/rulesets or delete files other people own. Report a GO candidate and leave separate approval step for publication.
- Update only `docs/core-roadmap/PROGRESS.md` after slices; on release closure update the authoritative `docs/PROJECT_STATUS.md` to fix stale 0.4 assertions and include new 0.x behavior and limitations.
- Release success means *source and observable installed behavior qualified*, not only unit tests, not just a merge to main, and not a text claim.

## Strict component boundary

Core owns HTML parsing/DOM/layout/CSS/text/paint/interactions/windows/native desktop services/C ABI and raw bindings. It **does not own** reactive state, UI components, themes, high-level forms, toasts, virtualized tables, app persistence, browser/JS, custom plug-in host, terminal/code editor engine, rich WYSIWYG editor, plotting/map/video/3D app-specific logic.

The Core may provide low-level `contenteditable` primitives; a WYSIWYG editing component belongs to optional UI/extensions. Native OS notifications belong Core; in-app toast component belongs UI.

## Long-term 1.0 contract

1.0 is a specified support profile, complete native desktop functionality across two target platforms, stable API/ABI, repeatable installed examples, and a maintenance procedure. It does **not** promise every browser feature, zero bugs or no future security updates.
