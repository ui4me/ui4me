# UI4ME 2.1 implementation status and source boundary

Baseline feature inventory: [`BASELINE_FEATURE_MATRIX_2_0_1.csv`](BASELINE_FEATURE_MATRIX_2_0_1.csv), copied unchanged from the owner's UI 2.0.1 snapshot. It contains 155 feature rows: Python 71 implemented/17 partial/61 absent/6 Core-limited; PowerShell 29 implemented/16 partial/104 absent/6 Core-limited. These counts describe the **old baseline**, not a claim of new 2.1 runtime verification.

## 2.1.0 qualification result (2026-11-14, local agent)

The candidate below was qualified natively and released as 2.1.0; defects found during
qualification were fixed with regression tests. Evidence: `docs/release/RELEASE_NOTES_2.1.0.md`,
`tools/release/records/qualification-2.1.0.json`, `docs/reference/feature-matrix.md`.

| Area | Implementation | Native verification |
| --- | --- | --- |
| Python direct start | `Application.start()` delegate; Core public window events | PASS: KDE Wayland + Windows (python, uv run, python -m, Unicode paths) |
| Python components | Fieldset, multiselect, adjustable split, metric, tooltip, copy button | PASS: real input on KDE + Windows (`py_v21`) |
| Forms | Dirty/touched/valid state; validation modes submit/change/blur | PASS: real typing (`py_v21`) |
| PowerShell direct start | `Invoke-UI4MEApp` delegates Core `Start-UI4MEScript` (caller script path) | PASS: pwsh 7 Linux/Windows, Windows PowerShell 5.1 |
| PowerShell organization | One public module loading purpose-oriented `private/` scripts | PASS: Pester 55/55 on pwsh 7.6.9 and 5.1; 54+1 skipped on Linux pwsh 7.7 |
| PowerShell widgets | Shell, sections, multiselect, segmented, metrics, icons, logs, split, tooltip, clipboard | PASS: real input (`ps_v21`) on all three PowerShell targets |
| Skills | Python CLI and pure-PowerShell installer, six agent targets | PASS: CLI on Linux; Pester on pwsh 7 / 5.1 |
| Gallery and apps | Python/PS galleries + operations/settings demos | PASS: every example run unmodified natively with screenshots |

## Original source-candidate notes

### New in this source candidate

| Area | Implementation | Cloud verification | Native verification |
| --- | --- | --- | --- |
| Python direct start | `Application.start()` delegate; no env gate; Core public window events | Fake Core adapter tests | PENDING |
| Python components | Fieldset, multiselect, adjustable split, metric, tooltip, copy button | Fake Core API and markup tests | PENDING |
| Forms | Dirty/touched/valid state; validation modes submit/change/blur | Fake Core behavior tests | PENDING |
| PowerShell direct start | `Invoke-UI4MEApp` delegates Core `Start-UI4MEScript` | Static inspection | PENDING, needs pwsh |
| PowerShell organization | One public module loading purpose-oriented `private/` scripts | Static export/definition checks | PENDING, needs PS 7+5.1 |
| PowerShell widgets | Shell, sections, multiselect, segmented, metrics, icons, logs, split, tooltip, clipboard | Static inspection | PENDING, needs pwsh |
| Skills | Python CLI and pure-PowerShell installer, six agent targets, packaged SKILL.md/reference | Python unit and content sync tests | PS importer PENDING |
| Docs and packaging | New README, Python/PowerShell quickstarts/API/recipes, publisher docs, full repository archive | Doc links, wheel/sdist/PS zip structural checks | Registry publication PENDING |
| Gallery and apps | Python/PS component gallery + operational/settings demos | Python fake-host build | Native apps PENDING |

## Deliberately not declared complete

- Core 1.x lacks native menu/tray/hotkey/OS notification/printing/PDF export and certain browser input types: these cannot be invented in UI4ME.
- UI4ME PowerShell P1 parity is incomplete: e.g., automatic reactive dependencies, rich data queries, fully equivalent typed schema forms, complex navigation, multiwindow, Markdown and chat. Some features have in-window alternatives. Prioritize user-facing reference-app parity and record supported APIs honestly.
- Python focus/IME/screen reader keyboard coverage and native event backpressure need actual platform evidence. The Python adapter internal high-priority queue is unbounded by design for lifecycle delivery; measure/coalesce continuous events safely before claiming long-session memory stability.
- No Native Linux/Windows/PowerShell programs could be executed in this cloud container. Source/packaging tests alone do **not** imply production-ready UI. The local agent must prove acceptance gates and fix any defects.

## Scope rule

Do not count feature inventory status or static code presence as evidence of working native behavior. Update the matrix from actual code plus native test evidence before publishing. Favor a maintainable, stable developer API over maximizing component count.
