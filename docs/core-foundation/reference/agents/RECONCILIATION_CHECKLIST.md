# Checklist: reconcile future work against moving source

This document is a short operator review, not an additional mandatory QA framework.

- [ ] Record current `main` commit; original research baseline is `cbb8a5e` from 2026-11-11.
- [ ] Read the currently installed/built 0.2 feature support and evidence. Anything unqualified must be called unqualified.
- [ ] Pick a single Core, UI-library, Extension or Application owner for every new feature. Split ambiguous features if they cross the boundary (e.g. HTML select vs searchable UI combo; file picker vs attachment workflow).
- [ ] Find each selected feature by ID in `data/features.json` and review dependencies and explicit acceptance scenario.
- [ ] Compare old donor code source refs with current refactored code; don't assume line numbers match.
- [ ] If a donor source hint uses `partial-or-related`, confirm whether a real implementation exists before reuse.
- [ ] Check whether old code was ever release-qualified, whether its test fixture is representative, and whether current source already contains a safer replacement.
- [ ] Identify public ABI/API design, argument errors, callback ownership and threading contract before coding.
- [ ] Make raw Core consumer run with optional `ui4me-ui` not installed.
- [ ] Exclude application policy, networking, auth and persistence from Core by dependency review.
- [ ] Scope exact selected tests with expected failures, existing acceptance records and native OS checks.
- [ ] For source changes, rerun affected validations; for source freeze, run release matrix on exact candidate bytes.
- [ ] Update documentation and registry with **new** source/test links and evidence. Keep old archive refs historically immutable.
- [ ] Record qualified/rejected/deferred features separately; don't turn future research candidates into promised release requirements.
- [ ] Before public publication, ensure same-source Linux/Windows, Python/PowerShell, native ABI, prior-version upgrades, installation outside checkout and license/vulnerability review.
