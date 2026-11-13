# Migrating to UI4ME 2.0

## Which `ui4me` you had

* **`ui4me` 0.1.0 – 1.0.1 on PyPI / `UI4ME` 0.1.0 – 1.0.1 on the PowerShell Gallery** were the
  previous all-in-one project (native host and bindings in one package). That native work now
  lives in **UI4ME Core** (`ui4me-core` / `UI4ME.Core` 1.x).
* **UI4ME 2.0** reuses the `ui4me` / `UI4ME` names for the high-level component framework on top
  of Core. There is no backward-compatibility promise with 0.x/1.x APIs.

## Python

* Install `pip install ui4me` (pulls `ui4me-core` 1.x). Do not install `ui4me-ui` — it is not a
  package.
* Start apps with `ui4me-run app.py` or a Core `app.toml`; running `python app.py` directly fails
  with an explanation, because Core apps are backends started by the native host.
* `from ui4me import Application, Window, Document` still gives you the Core classes unchanged.
  New UI code uses `from ui4me import ui` and `with ui.app(...) as app: ...; app.run()`.
* The old in-process `ui4me.App` backend and `backend="headless"` are gone. For tests without a
  desktop use `ui4me-run --headless`.
* Native menus, tray, global hotkeys, OS notifications, print/PDF and HTML clipboard raise
  `NotImplementedError` (Core 1.x does not provide them). `ui.date`/`ui.color` and friends are
  in-window controls, not OS pickers.
* Callback adaptation changed: parameters with default values are no longer filled with the
  event, so `on_click=lambda i=i: ...` keeps `i`. Declare a required parameter to receive the event.

## PowerShell

* `Install-Module UI4ME` (pulls `UI4ME.Core` 1.x). `Ui4me.Managed` and the 0.x `Ui4me.UI`
  command names (`Invoke-Ui4meUiApp`, `New-Ui4meUi*`) no longer exist; use `Invoke-UI4MEApp` and
  `New-UI4ME*`.
* Run with `Start-UI4MEUiScript -Path app.ps1` (add `-WindowsPowerShell` for a 5.1 backend), or a
  Core `app.toml` whose backend calls `Invoke-UI4MEApp`.
* `New-UI4MEInput -Type` no longer accepts `date`, `time`, `month`, `week` or `color`; use
  `New-UI4MEDate`, `New-UI4METime`, `New-UI4MEColor`.

## Repository

`ui4me/ui4me` `main` before 2.0 (`c5642dd`, the thin 0.1 facade) is preserved locally as tag
`backup/pre-v2-c5642dd` and branch `backup/pre-v2`; 2.0 continues the same Git history.
