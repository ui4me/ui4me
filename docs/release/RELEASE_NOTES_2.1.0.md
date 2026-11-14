# UI4ME 2.1.0 — release notes

Released 2026-11-14 · Python `ui4me` 2.1.0 (PyPI) · PowerShell `Ui4me` 2.1.0 (PowerShell Gallery) ·
requires UI4ME Core `>=1.0.1,<2` (`ui4me-core` / `UI4ME.Core`).

## Highlights

- **Ordinary scripts are the app.** `python app.py`, `uv run app.py`, `python -m package.app`,
  `pwsh -File app.ps1` and `powershell.exe -File app.ps1` start the native window. Core 1.0.1
  supervises the host; no manifest, no `ui4me-host run`. `ui4me-run` and `Start-UI4MEUiScript`
  remain for compatibility and headless tests.
- **New components in both languages:** fieldset, multi-select, adjustable split pane, metric,
  tooltip and copy button; PowerShell also gains an application shell (sidebar, header, footer,
  status bar), log view, icons, breadcrumbs, segmented choice and empty/loading states.
- **Forms (Python):** `dirty`, `touched`, `valid` state and `validation_mode="submit" | "change" | "blur"`.
- **Tooling:** `ui4me-ui-new` project generator; coding-agent skills for Claude, Codex, OpenCode,
  Copilot, Cursor and Gemini (`ui4me-ui-skill`, `Install-UI4MEUiSkill`).
- **Documentation:** quickstarts, recipes, API references, component catalog,
  [feature matrix](../reference/feature-matrix.md) and authentic screenshots.

See the [changelog](../../CHANGELOG.md) for the full list of fixes made during qualification.

## Qualification summary

Every gate was run on the released source. The machine-readable record with commands, versions and
hashes is [`tools/release/records/qualification-2.1.0.json`](../../tools/release/records/qualification-2.1.0.json).

| Gate | Platform | Result |
| --- | --- | --- |
| A — Python, Linux | Debian 13, KDE Plasma 6.3 Wayland (KWin 6.3.6 virtual output, real compositor input), Python 3.13 | **PASS** |
| B — Python, Windows | Windows Server 2022 (10.0.20348), interactive RDP session with real keyboard/mouse input, Python 3.13.17 | **PASS** |
| C — PowerShell 7, Linux | pwsh 7.7, module installed from the release ZIP in Gallery layout, KDE Wayland | **PASS** |
| D — PowerShell, Windows | pwsh 7.6.9 and Windows PowerShell 5.1.20348, Gallery layout, RDP input | **PASS** |
| E — Integration and release | full Python + Pester suites, docs quickstarts on the real host, package checks, fresh registry installs | **PASS** |

What the native journeys covered, with real input: buttons, typing, Enter/Tab/arrow keys, checkbox,
select, radio/segmented, multi-select, adjustable split by keyboard, tooltip on focus, copy to the
native clipboard and back, form validation as you type, table sorting/search/keyboard selection,
dialog Escape with focus return, toasts, light/dark switching, native file dialogs, a raising
callback that must not stop the app, keyed lists keeping typed text across reordering, owner
disposal of timers/tasks, second windows, close veto, user-escaped text, and a final native close
with no leftover process. Real **pinyin IME** composition (`nihao` → `你好`) was verified with fcitx5
on KDE and Microsoft Pinyin on Windows. Every example app in both languages was run unmodified and
screenshotted.

## Published artifacts

Built by the [publish workflow](https://github.com/ui4me/ui4me/actions/runs/43574291898) from commit
`36450e0` after a [green CI run](https://github.com/ui4me/ui4me/actions/runs/43574203730) of the same SHA.

| Artifact | Registry | SHA-256 |
| --- | --- | --- |
| `ui4me-2.1.0-py3-none-any.whl` | [PyPI](https://pypi.org/project/ui4me/2.1.0/) | `77b422f00cf019f330e9525ce6223998d052ed0db4a95b28f9555a4eb917ab51` |
| `ui4me-2.1.0.tar.gz` | [PyPI](https://pypi.org/project/ui4me/2.1.0/) | `053a034a2bb2b6c321da5ae38d05951a92f5b16d2c08799e687cc2d92b8b6172` |
| `UI4ME-2.1.0.zip` (module `Ui4me` 2.1.0) | [PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/2.1.0) | `fec313f7101fc2670f3a9d042cb2572e59252e813ed8df7f3fc12abc6ab3fc48` |

Identity with the qualified build: the module ZIP has exactly the qualified SHA-256; the Gallery
package's 22 files and the PyPI wheel's 49 files are byte-identical to the qualified ones (the wheel
archive differs only in ZIP metadata). After publication, fresh registry installs (`pip install ui4me==2.1.0`,
`Save-Module UI4ME`) passed the native `py_v21` / `ps_v21` journeys on KDE Wayland (Python, pwsh 7)
and Windows (Python, Windows PowerShell 5.1).

The workflow's post-publish Gallery check itself failed because `Save-Module` was given a folder that
did not exist; publication was not affected. The step is fixed for the next release and its fixed form
passed when run against the published module.

## Known limitations

- **Core 1.0.1 forwards every DOM event to the application** and disconnects an application that
  falls too far behind. UI4ME avoids the bursts it caused (theme switching); avoid CSS transitions or
  animations that start on many elements at once in your own CSS.
  [Details](../concepts/core-integration.md#measured-core-101-behavior-that-affects-applications).
- **Long sessions with constant re-creation of bold/monospace content (Core issue):** in a
  30-minute stress run (≈240 updates per second, conditional regions re-created every second, list
  shuffles, a 500-line log and a window opened/closed every 30 s) the UI4ME Python backend stayed flat
  (+0.8 MiB, no errors) but the **Core 1.0.1 native host** grew from 65 to 609 MiB. Bisection
  reproduced it with Core alone: content whose font face differs from the document's base face (for
  example `font-weight: 600`) inserted and removed while other text updates frequently. Each load
  alone levels off. Reported as [ui4me-core#2](https://github.com/ui4me/ui4me-core/issues/2); until
  it is fixed, prefer updating long-lived elements over re-creating them in hot loops.
- Core 1.0.1 forwards unsubscribed DOM events and disconnects slow backends:
  [ui4me-core#1](https://github.com/ui4me/ui4me-core/issues/1).
- IME composition updates bound values with intermediate preedit text (browser semantics).
- PowerShell is not a feature-for-feature copy of Python: no multiple windows, navigation/command
  palette, typed schema forms, data-source tables, Markdown or chat. See the
  [feature matrix](../reference/feature-matrix.md).
- Not part of the automated qualification: screen-reader output, HiDPI scaling other than 100 %,
  multi-monitor, file drag and drop, macOS, X11, ARM.
- Not possible on Core 1.x: OS notifications, tray icons, global hotkeys, native menus, printing/PDF,
  HTML clipboard.

## Upgrading from 2.0.x

- Install `ui4me-core` / `UI4ME.Core` 1.0.1 or later (pip and Install-Module do this automatically).
- Replace `ui4me-run app.py` with `python app.py` (optional; `ui4me-run` still works).
- `ui4me-run` now derives a per-script app id instead of the shared `org.ui4me.UserApp`; pass
  `--app-id` to keep an old single-instance identity.
- Default theme: buttons and inputs no longer animate colour changes.
