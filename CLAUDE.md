# UI4ME Core — autonomous foundation development

Project: https://github.com/ui4me/ui4me. The working tree is the source of truth.
Read `AGENTS.md`, `docs/PROJECT_STATUS.md` and `docs/core-foundation/EXECUTION.md` before implementation. For milestone targets read `docs/core-foundation/ACCEPTANCE.md`. Reference research lives at `docs/core-foundation/reference/` and is **not** an automatic backlog.

## Mission and accepted baseline

- The owner reports Core **0.2 implemented, running and tested** on their development setup. **Accept 0.2 as the engineering baseline.** Do not re-open all 0.2 release checks or launch a general codebase audit. Check Git revision and the small relevant interface before changes. Fix 0.2 only for a reproducible regression affecting new work.
- PyPI/PowerShell Gallery publication and its administrative/workflow qualification are a **separate task**; do not let that work block Core 0.3/0.4. Never publish, create releases/tags, or change remote release protections without explicit authorization for that action.
- Core 0.4 is released and is the stable baseline. The long-range post-0.4 Core development mission is defined by `docs/core-roadmap/RELEASE_ORDER.md` and `docs/core-roadmap/versions/`. Work sequentially from the first incomplete milestone through 1.0 without expanding optional UI/application scope; 1.1 is a future portability track. Preserve the existing Sonnet-default, few-worktree, proportional testing and publication-authorization rules. This replaces the old stop-at-0.4/skip-0.5 mandate. Ledger: `docs/core-roadmap/PROGRESS.md`.
- Still out of Core scope: UI4ME UI framework/components, JS, webview, embedded browser/server, MCP/agent protocols, plugin framework (see `docs/core-roadmap/BOUNDARIES.md`).

## Default operating mode

1. **Implement, don't repeatedly plan.** Inspect only the relevant source, choose the first incomplete acceptance slice, implement it end-to-end, verify proportionally, commit, and move to the next slice. Don't stop after an audit or ask for routine decisions.
2. Main Claude Code model **Sonnet**; a single primary agent ordinarily does the work. Use focused Sonnet subagent(s) for source-location, mechanical migration or isolated independent tasks. **At most two concurrent implementation agents total** (primary + one delegate) unless the owner asks otherwise. No agent teams / multi-worktree swarm.
3. Use **Opus only for hard unresolved architecture, unsafe lifetime/concurrency, ABI-breaking decisions or difficult cross-platform semantics** where a focused Sonnet investigation cannot settle the problem. Prefer the `core-architect` subagent once with a precise question, have Sonnet apply the answer, and do not assign routine searches/tests/copying to Opus.
4. Use existing current implementation first. For missing capabilities, look up exact old-source paths/line ranges in `docs/core-foundation/DONOR_PRIORITY_MAP.md` and `reference/data/features.json`, and port **small compatible pieces**, not entire old crates. Keep owner-thread, generational identity, bounded queues/assets and language-neutral ABI intact.
5. One development stream: commit coherent slices to `main` when safe and authorized in the working session. Use one short-lived branch/worktree only when parallel changes truly require isolation; integrate promptly and delete temporary worktrees. Never force-push or discard user changes.
6. Debug and test only modified feature surfaces during iteration. Expand to integrated feature tests at the end of a slice, and full supported platform/binding/package suites at 0.3/0.4 qualification. Do not re-run lengthy WPT/full renderer suites for unmodified areas. Never manufacture a PASS; record `pass`, `fail`, `blocked`, `not_run` accurately.
7. Don't optimize 50 ms into 45 ms or chase arbitrary benchmarks. Fix perceptible stalls, repeated-update hangs, unbounded memory, large correctness regressions and leaks. Record small deviations as follow-ups, not blockers.
8. Keep the checkout clean. Implement changes and relevant tests; update `docs/core-foundation/PROGRESS.md` after each slice and the existing `docs/PROJECT_STATUS.md` on milestone closure. Avoid multiple giant status docs, reports after every edit, and re-review loops.
9. On Linux test the actual KDE/Wayland path where relevant. The authorized Windows test machine is reachable as `ssh administrator@omegaui`, subject to verification. Read the local cross-platform skill. SSH compilation alone is not real Windows GUI acceptance.
10. Never claim platform support that was not observed, never conceal a release blocker, and never silently broaden the scope to satisfy an old checklist.

## Immediate instructions

Start at `docs/core-foundation/EXECUTION.md`. The exact continuation directive is in `docs/core-foundation/START_PROMPT.md`. Carry out real implementation rather than re-describing the plan. For ambiguous tasks, choose the smallest safe workable contract and document that choice. Pause only for credential/permission issues, destructive operations, explicit publication authority, or genuinely irreducible product decisions.


Old implementation reference:
  /home/toor/projects/ui4me-old-reference

Use this local source when consulting DONOR_PRIORITY_MAP.md.
Do not clone or fetch old code unless the local reference is missing.
Never bulk-copy old crates; selectively port compatible implementations.
