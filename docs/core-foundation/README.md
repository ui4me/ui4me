# UI4ME Core 0.3–0.4 handoff

This **drop-in agent guidance package** adds no Rust/Python/PowerShell source changes and does not alter existing release workflows. It assumes Core 0.2 is owner-verified and concentrates on pragmatic future implementation.

Start by reading `EXECUTION.md` and `ACCEPTANCE.md`. `PROGRESS.md` is the lean running state. `DONOR_PRIORITY_MAP.md` points to exact old-source line ranges. `REFERENCE_USAGE.md` explains how to keep the large original old repository outside Git. `reference/` preserves the research bundle for in-depth lookup only.

Claude Code configuration lives at repository root `CLAUDE.md` and `.claude/`: Sonnet default, one Sonnet donor worker, optional Opus architecture escalation, local cross-platform skill, `/core-next` continuation skill. The startup text is in `START_PROMPT.md`.

**Out of scope:** registry publication, source replacement, large code migrations by this package itself, tests, UI component framework and broad 0.5 feature collection.
