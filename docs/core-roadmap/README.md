# UI4ME Core long-range development program

**Status:** Planning and agent-handoff artifact, based on the uploaded **released v0.4.0 source archive**. This package does not modify source, run tests or assert all listed gaps are definitively missing on later `main`.

The purpose is to make Core a bounded, mature, long-lived HTML/CSS/DOM/native desktop engine for Linux and Windows, while keeping optional `ui4me-ui` components and application business logic outside the engine.

## Start here

1. `START_AGENT.md` — reusable prompt: next milestone, a named version, or one item.
2. `OPERATING_RULES.md` — cost-effective Claude Code autonomy, model selection, tests, commits and progress.
3. `versions/` — concrete design, source anchors and acceptance for each milestone.
4. `data/WORK_ITEMS.json` — **67** sequenced work items with old and current source leads.
5. `data/ORIGINAL_INVENTORY_RECONCILED.json` — **224** original records preserved and classified, including non-Core ownership so they cannot drift into Core.
6. `data/CSS_PROFILE_V0_4.json` — **154** inspected CSS profile entries (On/Off/Unavailable/Filtered), a triage ledger; not a command to enable browser-only features.
7. `PROGRESS.md` — one short durable ledger, updated by agents as versions are delivered.

## Versions (work-item counts)

0.5 (8), 0.6 (10), 0.7 (11), 0.8 (8), 0.9 (11), 0.10 (8), 1.0 (8), 1.1 (3)

**Version 1.0 is the bounded product-complete gate on the supported Linux/Windows desktop profile**, not a claim of full browser standards or future-proof software with no maintenance. Version 1.1 is explicitly optional future portability work. A maintained stable Core still needs security/platform dependency patches. Avoid new arbitrary features after 1.0 unless an app reveals a concrete gap.

## Deployment

Extract into the root of the existing `ui4me` repository. Paths added are only `docs/core-roadmap/` and `.claude/skills/core-roadmap/SKILL.md`; existing `CLAUDE.md`, `.claude/settings.json`, `docs/core-foundation/`, code and release workflows are untouched. Then give Claude the full prompt from `START_AGENT.md` for the desired version.

The existing root `CLAUDE.md` describes the old 0.2→0.4 mission. The **new explicit user request** and this version roadmap supersede its historic milestones, not its architecture/safety constraints. It is wise to update that old mission language when beginning 0.5; see `CLAUDE_MIGRATION.md`. Do not overwrite custom settings or other users' edits automatically.

**Original donor:** `../ui4me-old-reference` (or `/home/toor/projects/ui4me-old-reference`, if present). Old anchors refer to the prior architecture; present source always wins. The source already contains a copied research catalogue at `docs/core-foundation/reference/data/features.json`. The package's data is self-contained for planning; the old donor itself is deliberately not bundled.
