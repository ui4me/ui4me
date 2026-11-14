# Test and qualification plan

Order matters. Do not run multiple native GUI tests concurrently on the same desktop or edit shared source from multiple agents at once.

1. **Local fast tests (cloud/developer):** `python -m pytest -q tests/unit tests/bridge`, Python syntax, static PowerShell command/export scans, source/packaging checks, skills/link checks. These do not qualify desktop interaction.
2. **Linux Python (KDE Wayland):** install published Core 1.0.1 and candidate UI4ME wheel; run ordinary `python app.py`, `uv run app.py`, headless host tests, native gallery keyboard/mouse, component state, exception/close/kill/flood tests, 30-minute stress.
3. **Windows Python:** clean wheel/venv on Windows x64 interactive session; normal startup, Unicode paths, focus/dialog/IME/native input, DPI, shutdown, RDP automated journeys.
4. **Linux PowerShell 7:** clean install of Core module and candidate `Ui4me` module, Pester, direct `pwsh -File`, basic examples and gallery, input/binding/reorder, dialogs, keyboard, no orphaned processes.
5. **Windows PowerShell:** first pwsh 7, then Windows PowerShell 5.1 from an interactive Windows desktop/RDP session; clean package install, module casing, event runspace, .NET Framework edge cases and scripts.
6. **Conformance and release:** same cross-language acceptance scenarios, native screenshots and evidence, document link/static example checks, fresh external consumers, wheel/sdist/PowerShell ZIP, source identity and publisher preflight.

Do not mark a gate as passed because tests exist or prior Core qualification passed. Report `PASS`, `FAIL`, `BLOCKED`, `NOT RUN` separately; record commands, versions, host hashes and evidence location.

Test automation exists in `tests/native/linux/vkwin.py` and `tests/native/windows/rdp_driver.py`. Use local supervised tests, not hidden tmux. After changes use targeted tests; run the full suite only at integration gates. For each public widget exercise render, event, value, keyboard, owner disposal, styles and error boundaries.

## Native harness reference (2.1)

| What | Linux (KDE Wayland, private virtual KWin) | Windows (interactive RDP session) |
| --- | --- | --- |
| Run a journey | `python3 tests/native/linux/vkwin.py --out DIR -- python tests/native/apps/py_v21.py` | `python3 tests/native/windows/rdp_driver.py --out DIR --name py_v21 --setup-python WHEEL -- '{VENV}\Scripts\python.exe' '{STAGE}\tests\native\apps\py_v21.py'` |
| PowerShell journey | `... -- pwsh -NoProfile -File tests/native/apps/ps_v21.ps1` (module + Core on `PSModulePath`) | `... --env 'PSModulePath+=DIR' -- powershell.exe -NoProfile -ExecutionPolicy Bypass -File '{STAGE}\tests\native\apps\ps_v21.ps1'` |
| Every unmodified example (screenshot, Tab focus, no errors, native close) | `py_showcase.py EXAMPLE` / `ps_showcase.ps1 EXAMPLE` | same, with `--stage-examples` |
| Real IME | `--ime fcitx5` (pinyin active, private config) + `py_ime.py` | Microsoft Pinyin installed for the test user; `py_ime.py` asks the driver to switch the window's input language |
| Long session | `UI4ME_SOAK_SECONDS=1800 py_soak.py` (`UI4ME_SOAK_LOAD=tick,post,log,region,list,window` isolates load sources) | — |
| Event diagnostics | `UI4ME_DIAG_FRAMES=FILE` counts host→backend frames by type (`tests/native/apps/_frame_counter.py`) | same (`--env`) |

Each journey writes `harness.json` (exit status, leftover processes), `results.jsonl` (the app's own
checks) and `app.log`. A run passes only with exit status 0, no failed check and no leftover
host/backend process. The Linux driver never touches the person's desktop: it uses a private D-Bus,
`XDG_RUNTIME_DIR` and `kwin_wayland --virtual`; screenshots are taken with spectacle inside that session.
