# Development

## Layout

| Path | Contents |
| --- | --- |
| `src/ui4me/` | Python package (`ui4me.ui`, launcher, Core adapter) |
| `powershell/Ui4me/` | PowerShell module `UI4ME` (`Ui4me.psd1`, `Ui4me.psm1` — file casing matches the Gallery id `Ui4me`; theme assets copied from Python at build) |
| `tests/unit`, `tests/bridge` | Python tests against a fake Core (fast, no host) |
| `tests/host` | Python tests against the real Core host in `--headless` mode |
| `powershell/tests` | Pester 5 tests (mocked Core cmdlets, static checks) |
| `tests/native` | Real-input journeys and drivers (Linux KWin, Windows RDP) |
| `tools/` | `build_dist.py`, `check_artifacts.py`, `preflight_publish.py` |

## Python

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e . pytest build
pytest -q                       # unit + bridge + real host (headless; skipped without ui4me-core)
```

`tests/host` runs apps with `python -m ui4me --headless app.py`: the real host process, IPC and
DOM without a desktop window. Events there are simulated (`ui4me._ui.testing.Pilot`).

## PowerShell

```powershell
Save-Module UI4ME.Core -RequiredVersion 1.0.0 -Path ./.psmodules   # or Install-Module
$env:PSModulePath = "$PWD/.psmodules$([IO.Path]::PathSeparator)$PWD/powershell$([IO.Path]::PathSeparator)$env:PSModulePath"
Invoke-Pester ./powershell/tests
```

Run the same tests in Windows PowerShell 5.1 on Windows. Example smoke test (real host, no window):

```powershell
$env:UI4ME_UI_SMOKE = 2; Start-UI4MEUiScript -Headless -Path ./examples/powershell/gallery.ps1
```

## Real-input journeys

`tests/native/apps/*` are apps that script their own checks and ask a driver for real input
through `tests/native/channel.py` / `Channel.ps1` (request → ack → results JSONL).

**Linux** (`tests/native/linux/vkwin.py`): starts a private D-Bus session, private
`XDG_RUNTIME_DIR` and `kwin_wayland --virtual`, and injects pointer/keyboard input through
KWin's `org_kde_kwin_fake_input`. Nothing reaches the person's desktop. Needs `kwin_wayland`,
`qdbus6`, `wayland-scanner`, `gcc`, `libwayland-client`. The host runs unsupervised there
(`UI4ME_ALLOW_UNSUPERVISED=1`) because the private bus has no systemd user manager.

```bash
python3 tests/native/linux/vkwin.py --out /tmp/run -- ui4me-run tests/native/apps/py_basic.py
python3 tests/native/linux/vkwin.py --out /tmp/run -- pwsh -NoProfile -c \
    "Import-Module UI4ME; Start-UI4MEUiScript -Path tests/native/apps/ps_basic.ps1"
```

**Windows** (`tests/native/windows/rdp_driver.py`, run from Linux): needs an `xfreerdp3`
session to the test user's desktop on an X display (`UI4ME_RDP_DISPLAY`, default `:88`) and the
lab agent running *inside* that session. The driver stages files through the agent, launches the
app in the interactive session and sends real RDP input with `xdotool`.

```bash
python3 tests/native/windows/rdp_driver.py --out /tmp/w --name py_basic \
    --setup-python dist/ui4me-2.0.0-py3-none-any.whl -- '{VENV}\Scripts\ui4me-run.exe' '{STAGE}\tests\native\apps\py_basic.py'
```

Both drivers fail the run on any failed check, a missing `done` record, a non-zero exit, a
timeout, or processes left behind. Evidence is automated input on virtual displays, not a person
at a physical monitor.

## Building artifacts

```bash
python tools/build_dist.py dist      # wheel, sdist, UI4ME-X.zip, SHA256SUMS; runs check_artifacts
python tools/preflight_publish.py 2.0.0
```

`UI4ME-X.zip` contains the `Ui4me/` module folder: extract it into a `PSModulePath` folder, or
publish it with `Publish-Module -Path ./Ui4me`. Keep the `Ui4me` casing: the Gallery package id is
`Ui4me`, and on Linux the folder and manifest names must match exactly.

## Releasing

`.github/workflows/publish.yml` is manual (`workflow_dispatch`). It requires a successful `CI`
run for the same commit, rebuilds and checks the artifacts, runs the registry preflight
(Core published, version unused), and publishes only the targets you tick: PyPI through Trusted
Publishing (environment `pypi`) and the PowerShell Gallery with `PSGALLERY_API_KEY`
(environment `psgallery`). Never reuse a published version number.
