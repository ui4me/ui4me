# UI4ME 2.1.0 — local Claude Code qualification, remediation and release mission

## Starting point and responsibility

You are the autonomous engineer and release maintainer for `ui4me/ui4me`. You receive **the complete UI4ME 2.1 source tree**, built from the owner's two uploaded source snapshots. It is not an overlay and no separate source patch is required. It intentionally replaces the previous 2.0.x UI code and old blueprint documentation. UI4ME Core 1.0.1 is an independently published and qualified dependency; **do not rewrite Core or vendor its host into UI4ME**.

The owner has authorized local troubleshooting, editing, installation of test dependencies, rigorous native testing, Git commit/push and PyPI/PowerShell Gallery publication **once all required gates pass**. Do not publish when a gate is unresolved. If 2.1.0 is already in a registry, choose the next unused version and update metadata/tests/docs/release artifacts uniformly. Never force-push or overwrite a published release. No passwords/tokens should be embedded in the repository.

Platform access: primary Debian 13/KDE Plasma 6 Wayland Linux machine; an existing Windows `Omega UI` desktop/VM (with RDP and PowerShell 7/Windows PowerShell 5.1); Proxmox lab available if needed. Discover existing connections safely rather than guessing endpoints, credentials or stopping unrelated VMs. Use the existing `tests/native/` harness. Respect real desktop sessions, and avoid testing both agents on the same interactive display at once.

## Immediate procedure

1. Preserve the current Git repository history and last published tag. Create a backup/snapshot before replacing the working tree. If this ZIP was unpacked over an old tree, remove orphaned **tracked and untracked** files only after verifying them; `git status`, `git ls-files`, inspect and reconcile. Do not revert the new source to a stale remote commit. Compare the current remote HEAD to the uploaded baseline and document any intervening changes.
2. Read `specs/UI4ME_2_1_CONTRACT.md`, `specs/CRITICAL_REVIEW.md`, `specs/IMPLEMENTATION_STATUS.md`, `docs/index.md` and `docs/release/testing.md`. Inspect both published Core 1.0.1 API docs and source before modifying startup, events or IPC. Confirm Python package `ui4me` and PowerShell Gallery module `Ui4me` version availability.
3. Inspect `python -m pytest -q tests/unit tests/bridge` and `python tools/sync_skills.py --check`. Use targeted tests during fixes. Keep progress visible in the primary CLI, not hidden in tmux. Maintain an explicit gate ledger (`local-evidence/` ignored/untracked and summarized in the final report).
4. **Before qualification**, review the new Python `src/ui4me/_ui/_adapter.py` lifecycle against Core 1.0.1 event/shutdown semantics, and new `powershell/Ui4me/private/` modules with Pester. Confirm PowerShell `Invoke-UI4MEApp` calls `Start-UI4MEScript` with the correct caller script path. Fix startup, Unicode, startup errors and native host cleanup as needed. This is an implementation candidate, not a verified final release.

## Mandatory sequential qualification

### Gate A — Linux Python only

Use Core 1.0.1 from PyPI, no native engine source patches. Fresh Python venv/uv project, independently install candidate wheel. Run `python -m pytest -q tests/unit tests/bridge tests/host`, compileall, Core host doctor, `uv run app.py`, `python app.py`, old `ui4me-run` CLI, generator-created app, user skill installer, every `examples/python/*.py` app (including gallery, operations and settings). Execute headless and **native KDE Wayland** runs: real typing, IME, navigation, focus, forms, multi-select, table, adjustable pane, clipboard, theme, notification and file dialog; close/veto/exception/second-launch/Ctrl+C and no-orphan checks. Test `app.post` thread-safe calls, owner cleanup, stale Core documents, event backlog, and long-lived session stability. Write deterministic unit regression tests for every fix. Do not proceed until qualified or explicitly BLOCKED.

### Gate B — Windows Python only

On Windows x64, install the same candidate wheel into a fresh venv. Test direct `python app.py`, `uv run app.py`, `python -m`, Unicode paths, Windows message loop, DPI/scaling/IME, keyboard/AT, native dialogs, startup errors, gallery and reference apps. Exercise real interactive RDP desktop input via the Windows driver (`tests/native/windows/rdp_driver.py`) and compare semantics against Linux. Preserve SHA identity and record native host and wheel versions. Fix Windows-only issues without breaking Linux tests. Re-run Linux targeted regressions after cross-platform changes; reserve full Linux suites for integration gates.

### Gate C — Linux PowerShell 7 only

Install Core PowerShell module >=1.0.1,<2 and UI `Ui4me` from candidate staging. Validate real module casing and source ZIP's module folder; `Test-ModuleManifest` + Pester; `Import-Module UI4ME` with empty user modules; plain `pwsh -File ./examples/powershell/gallery.ps1` and `dashboard.ps1/settings.ps1`; check `Invoke-UI4MEApp` direct Core bootstrap, IPC, returned connection and callback runspace. Exercise all new high-level `private/55-advanced.ps1` functions (fieldset, metric, shell, multi-select, logs, icons, responsive split, tooltip, clipboard, etc.) with real input. Confirm timers and tasks stop with owner, current window/delayed callbacks don't leak, user-input escaping and skills installer works. Native KDE Wayland coverage at same level as Python where capabilities are shared. Do not use Python as PowerShell runtime.

### Gate D — Windows PowerShell 7, then Windows PowerShell 5.1

Test the candidate module from an actual Gallery-style install directory, preserving `Ui4me` exact case. Run all Pester tests on pwsh 7 and then Windows PowerShell 5.1; ensure scripts parse in 5.1, avoid syntax requiring only PowerShell 7, handle UTF-8/ANSI console behavior and .NET Framework quirks. Direct `pwsh -File ./app.ps1`, `powershell.exe -NoProfile -File app.ps1`; real keyboard and RDP, UI callbacks and window close, no orphaned Rust host. Verify published module has all private files, functional/theme CSS, documentation and agent skill and does not depend on Python. Fix and rerun targeted tests on both PS editions.

### Gate E — Cross-language conformance and release

Reconcile P0 contracts and representative P1 flows with shared scenario fixtures. Make `gallery.py` and `gallery.ps1` demonstrate each implemented high-value component. Run state/keystroke/close/conditional content/field validation/tables/theme/native dialogs with actual user input on both OSes. Test long-running apps and resource cleanup. Full Python + Pester suites, package builds, `twine check`, `tools/check_artifacts.py`, skills sync, docs link/example validators and fresh installations. Check screenshots are captured from actual UI4ME apps, not mockups; include Linux and Windows gallery screenshots in README only after qualification.

## High-priority remediation and enhancement list

- **P0**: Core 1.0.1 public event/shutdown integration; direct script startup in both languages; consistent event queue/failure behavior; reliable native component focus and accessibility, input/IME, and safe cleanup; strong validated settings and app IDs.
- **P0/P1 PowerShell**: test and complete modularization; verify component contracts across new and existing modules; expand form/validation, command/navigation, and multiwindow semantics **when needed for reference apps**. Do not claim exact Python feature parity for any unimplemented API. A working reference application in each language is more valuable than 30 fake wrappers.
- **P1**: fix any gallery crashes, stylesheet conflicts, resource leaks, unsupported native component attributes, reactive stale-result handling. Diagnose using Core diagnostics; keep old `ui4me-run` and `Start-UI4MEUiScript` for compatibility until replacements are fully qualified.
- **Security**: no JS, HTTP daemon, browser renderer or second native engine; no unsafe user HTML; safe native external-open; no false desktop capabilities or invented native menu/tray/printing APIs.
- **Documentation**: README collapsible installs, beginner-friendly non-lambda callback examples, exact Python/PowerShell quickstarts, recipes, component pages, full language APIs, release notes, skills, gallery and authentic screenshots. Fix inaccurate docs when tests prove a limit. No old blueprint/milestone reports in published docs.

## Engineering process

Use independent subagents/worktrees only for non-overlapping tasks (e.g., docs vs unit tests, separate stateless components). **Single owner for ABI/adapter, PowerShell module exports, version manifests, release files and native display automation.** Never have two workers editing the same file or testing the same Wayland/RDP display. Run focused suites after each component change and full suites at integration milestones only. Prefer simple Python/PowerShell/CSS without shipping Node/npm. Track exact failures before changes; no blind repeated large reruns.

## Release and publication — automatically after mandatory PASS

- Version target `2.1.0`; registry availability preflight for PyPI and PowerShell Gallery. If occupied choose a new higher version before build, never overwrite published bytes.
- Ensure `pyproject.toml`, `src/ui4me/__init__.py`, `_version.py`, PowerShell manifest and module, docs/changelog and artifact names match.
- Build packages from the same reviewed commit: Python pure wheel + sdist, and PowerShell `UI4ME-<version>.zip`/`.nupkg` with no Core binary; compare static dependencies `ui4me-core>=1.0.1,<2` and `UI4ME.Core` >=1.0.1,<2.
- Publish **only if all gates PASS**. Use existing protected/manual GitHub Actions workflows for PyPI Trusted Publishing and PSGallery API key, not personal insecure upload scripts. Gate publication on a green CI run for the final exact source SHA. After upload, fresh-install from **registries**, run native smoke, create/push release tag (never retag or force-push), report artifact hashes and URLs.
- Commit full repository replacement on `main` after review; normal fast-forward push only. If current origin has unrelated new work, reconcile and retest, never force-push. Leave the repo clean.

## Final report

Produce `docs/release/RELEASE_NOTES_<version>.md`, a precise machine-readable qualification ledger (`tools/release/records/qualification-<version>.json`) with platform/tool/command/result/hash, updated feature matrix (feature, API, Python/PowerShell status, tested evidence), screenshots with provenance, and a concise final operator verdict. Every mandatory gate PASS/FAIL/BLOCKED/NOT RUN. Report missing Core capabilities distinctly. If anything essential remains BLOCKED, do not publish; continue remediation autonomously and provide reproducible blocker details.

**Finish the code and release, not just a plan. The user asked for an installable and usable UI4ME framework in both languages.**
