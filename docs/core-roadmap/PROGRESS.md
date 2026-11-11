# Core long-range roadmap progress

**Baseline:** 0.4.0 released, 2026-11-11, tag `v0.4.0` at `8138e78feed4d63dcd6f189b0f96bb0fbbbc6ba6` (per release metadata). This roadmap was prepared by static reading only; no build/test of Core executed.

**Next milestone:** 0.5 (`versions/0_5.md`). **Status:** NOT_STARTED (this package does not implement code).

## Version ledger

| Version | Status | Source SHA | Linux GUI | Windows GUI | C/Python/PowerShell | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.4 | OWNER-REPORTED RELEASED | `8138e78` release tag | repository-reported PASS | repository-reported PASS | repository-reported release jobs | Do not requalify unless relevant change/new defect |
| 0.5 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.6 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.7 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.8 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.9 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.10 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 1.0 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 1.1 | FUTURE OPTIONAL | — | NOT_RUN | NOT_RUN | NOT_RUN | — |

## Work-item ledger

Maintain ONE entry after each completed item:

`DATE | VERSION | ITEM | COMMIT SHA | changed paths | tests actually run / OS and binding | PASS/FAIL/BLOCKED/NOT_RUN | user-observable limitation | next task`

When a new session starts, choose the earliest release not marked GO, then first unresolved item. The agent can mark items `SATISFIED_EXISTING` with exact code/evidence to prevent reimplementation. The source doc `docs/PROJECT_STATUS.md` remains the authoritative current product status after each milestone; this is only an execution ledger.

## Outstanding defects / intentional exclusions

None verified by this package. The `WORK_ITEMS.json` statuses are static leads, not executed test failures.
