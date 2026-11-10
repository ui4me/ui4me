# Acceptance overview

This checked-in overview is the initial **not-run baseline**. The current report
is generated from receipts into `build/reports/overview/overview.md` and
`build/reports/overview/index.html` by `python dev.py report`.

There are no historical passes or screenshots in this reconstruction. Run tests
and record real native observations to populate the generated report. Do not edit
this baseline into a passing badge or copy evidence from a different source.

| ID | Requirement | Python Linux | Python Windows | PowerShell Linux | PowerShell Windows |
| --- | --- | --- | --- | --- | --- |
| F01 | Clean artifact installation | not_run | not_run | not_run | not_run |
| F02 | Useful native startup | not_run | not_run | not_run | not_run |
| F03 | Input and state change | not_run | not_run | not_run | not_run |
| F04 | Window lifetime | not_run | not_run | not_run | not_run |
| F05 | Close and forced stop | not_run | not_run | not_run | not_run |
| F06 | Owner-thread dispatch | not_run | not_run | not_run | not_run |
| F07 | Cancellation and stop races | not_run | not_run | not_run | not_run |
| F08 | Reuse in one process | not_run | not_run | not_run | not_run |
| F09 | ABI and callback lifetime | not_run | not_run | not_run | not_run |
| F10 | Bounds and idle behavior | not_run | not_run | not_run | not_run |
| F11 | Resources and diagnostics | not_run | not_run | not_run | not_run |
| F12 | Release and upgrade | not_run | not_run | not_run | not_run |

[Scenario definitions](scenarios.json) · [Testing guide](../docs/testing.md) ·
[Foundation requirements](../specs/001-foundation/spec.md).

Generated reports include links to detailed results and available captures. A
renderer PNG is labeled separately from a native desktop capture. The latest
failed, blocked or interrupted attempt remains visible, with the last successful
attempt linked separately.
