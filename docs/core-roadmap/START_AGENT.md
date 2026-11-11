# Autonomous agent prompts — copy the relevant paragraph into Claude Code

## A. Start or continue the NEXT version

You are developing `ui4me/ui4me` Core from the already released v0.4.0 baseline. Our new mandate supersedes the old `CLAUDE.md` goal to stop after 0.4, but preserves its safety, project architecture, Sonnet-default policy and publishing restrictions. Read `docs/core-roadmap/README.md`, `OPERATING_RULES.md`, `RELEASE_ORDER.md`, `PROGRESS.md`, `data/WORK_ITEMS.json` and the specific `versions/<version>.md` for the earliest unfinished release. Inspect actual current code before touching each item. Do not re-audit the entire 0.4 baseline and do not start by writing another broad plan. Implement the next uncompleted slice end to end, reuse working internal/old-donor code where sensible, add only focused tests, commit coherent work and continue autonomously until that version meets its gate or a genuine blocker prevents it. Run the complete relevant Linux and Windows installed qualification only on a release candidate. Sonnet default; at most one extra Sonnet implementation worker; Opus only for a concrete difficult architecture/unsafe ABI blocker. Update `PROGRESS.md` and record evidence honestly. Do not create GitHub releases or publish to PyPI/PSGallery without explicit new approval. Finish with version GO/BLOCKED verdict, exact source SHA, tests and remaining issues.

## B. Implement a SPECIFIC version (e.g. 0.7)

Implement UI4ME Core version **0.7** using `docs/core-roadmap/versions/0_7.md`, `data/WORK_ITEMS.json`, `OPERATING_RULES.md`, and `PROGRESS.md`. Treat prior 0.4–0.6 implementation already present in this checkout as baseline; confirm dependencies and skip any completed functionality instead of rebuilding. Implement every applicable task in this release in source plus cross-binding/native contracts, targeted tests and milestone gate. Work autonomously with Sonnet default and minimal parallelism; escalate only serious design issues to Opus. Do not publish automatically. Update the ledger and provide evidence-bound final report.

For another version change **both** the version and its filename, e.g. `0_5.md`, `0_9.md`, `0_10.md`, `1_0.md`. Implement in dependency order; if earlier work is missing, complete the smallest prerequisite first and record it.

## C. Implement ONE named item (example F0704)

Implement `F0704` from `docs/core-roadmap/data/WORK_ITEMS.json` (or its version `.md`) within the existing architecture. Verify whether it is already implemented first; read current source anchors and optional old donor references, then make the smallest complete public C/Python/PowerShell implementation and tests. Avoid unrelated refactors, the full suite and unnecessary worktrees. Update `PROGRESS.md` with source SHA, actual tests and any limitation. Do not publish.

## D. Pause/resume on tokens

Continue the current Core roadmap release from `docs/core-roadmap/PROGRESS.md`. Resume the recorded first incomplete work item without redoing tests, source exploration or prior completed implementations unless there is evidence that current SHA changed relevant code. Work in small complete commits and do not stop after planning. At the end, record concise state and the precise next action; no new branch jungle.
