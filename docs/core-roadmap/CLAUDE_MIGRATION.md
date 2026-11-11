# Integrating the new roadmap into existing Claude instructions

Your current root `CLAUDE.md` (as in the uploaded 0.4 archive) still says finish 0.3/0.4 and **do not spend time on 0.5**. That sentence contradicts the owner's new mandate. **Do not overwrite the entire file**: it contains valuable lifecycle/safety/owner-machine instructions.

When launching Claude, paste `START_AGENT.md` (the new user request has clear precedence for the scope of the task). In its first commit, Claude may edit only the stale *mission/scope* paragraph in existing `CLAUDE.md` to refer to this new roadmap and preserve every other rule and local donor path. A recommended replacement paragraph:

> Core 0.4 is released and is the stable baseline. The long-range post-0.4 Core development mission is defined by `docs/core-roadmap/RELEASE_ORDER.md` and `versions/`. Work sequentially from the first incomplete milestone through 1.0 without expanding optional UI/application scope; 1.1 is a future portability track. Preserve the existing Sonnet-default, few-worktree, proportional testing and publication-authorization rules. This replaces the old stop-at-0.4/skip-0.5 mandate.

This package deliberately does not ship root `CLAUDE.md`, `.claude/settings.json`, an agent-file override, or changed release workflows, so extraction cannot destroy your latest local customization.
