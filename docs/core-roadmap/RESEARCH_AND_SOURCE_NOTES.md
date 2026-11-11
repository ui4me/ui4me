# Grounding and limitations

**Source A:** uploaded `ui4me-main (1)(1).zip`, version file 0.4.0, retrieved in this conversation (2026-11-11); static file inspection, *no execution*. Selected references in `WORK_ITEMS.json` include exact archive-relative file names and keyword match lines. They are **reading leads** and may refer to internal-only implementations.

**Source B:** original architecture/research inventory in `docs/core-foundation/reference/data/features.json` (224 features). Its `current_02`, `target`, and old donor anchors describe the *older 0.2 planning state*, not current v0.4 status. This roadmap deliberately retains those fields under historical names and adds conservative v0.4 disposition.

**Source C:** `docs/PROJECT_STATUS.md`, `docs/core-foundation/PROGRESS.md` and public GitHub release tag `v0.4.0`; release was reported/confirmed in the previous conversation. The status doc also has obsolete subsections stating pre-release details: prioritize latest release header and actual tagged code, but never silently mutate conflicting historical evidence.

**Additional design:** all `F05xx`–`F12xx` tasks, milestone assignment, priorities, target APIs and future features beyond the original catalog are **proposed specifications** derived from the requested full long-term Core program, not proof those capabilities are absent.

**Caveats:** This is a finite ownership-controlled product plan, not proof every possible HTML/CSS standard feature has been enumerated. The `CSS_PROFILE_V0_4.json` snapshot retains all profile entries for systematic triage. New standards/OS changes after v1.0 may require maintenance; hardware and compositor limitations cannot be engineered away from the Rust library by fiat.

**Documentation:** Claude Code project skills live under `.claude/skills/<name>/SKILL.md`; `model: sonnet` or `model: opus` can be specified in a focused subagent. This archive does not overwrite existing `.claude/settings.json` or `CLAUDE.md` to respect live repo customizations.
