# ui4me

ui4me is a small native UI runtime for applications written in Python or
PowerShell. A Rust engine owns windows, a minimal HTML form renderer and the
application event loop; application logic stays in the host language. The
bindings communicate with the engine through a versioned C ABI.

Version 0.1.0 is available for **Linux x86-64** and **Windows x64**, using
**Python 3.11–3.14** or **PowerShell 7.4+**. Python wheels and the PowerShell
module include their native libraries; consumers do not need Rust or a .NET SDK.
Linux requires a working Wayland or X11 desktop and the native system libraries
listed in [PROJECT_STATUS](docs/PROJECT_STATUS.md).

## Install

From [PyPI](https://pypi.org/project/ui4me/):

```sh
python -m pip install ui4me==0.1.0
```

From [PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/):

```powershell
Install-PSResource -Name Ui4me -Version 0.1.0 -Scope CurrentUser
```

## Python

```python
from ui4me import App

with App() as app:
    window = app.open('<h1>Hello</h1><button id="quit">Quit</button>')
    window.on("click", lambda event: app.stop(), element="quit")
    app.run()
```

## PowerShell

```powershell
Import-Module Ui4me
Invoke-Ui4meApp {
    param($app)
    $window = New-Ui4meWindow '<h1>Hello</h1><button id="quit">Quit</button>'
    $null = Register-Ui4meEvent $window click { $app.Stop() } -Element quit
}
```

Both calls return control to the host when the application stops. Larger examples
in [`examples/`](examples/) demonstrate input, a second window, resizing,
close interception and background work.

## Features and limitations

The runtime provides multiple native windows, text and button events, close
veto, forced shutdown, timers, bounded deferred work, owner-thread dispatch,
and same-process sequential sessions. The renderer supports a small fixed-layout
HTML subset, text input, and limited inline colors. It is **not a browser**:
stylesheets, CSS layout, JavaScript, network loading, IME, full text shaping,
clipboard/selection and an accessibility bridge are not implemented.

## Develop and test

Install Python 3.11+, Rust 1.90 (selected by `rust-toolchain.toml`), a native
compiler, .NET SDK 10 and PowerShell 7.4+. Create a virtual environment, then:

```sh
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

For targeted work use `--binding core`, `python`, `powershell`, or `tools` as
appropriate. Build and installed-package tests are separate; see
[PROJECT_STATUS](docs/PROJECT_STATUS.md) for complete platform prerequisites,
packaging, native tests, verification history and release procedures. Build
outputs and test evidence stay in ignored `build/` and `dist/` directories.

[Source and issues](https://github.com/ui4me/ui4me) ·
[PyPI](https://pypi.org/project/ui4me/) ·
[PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/) ·
[MIT license](LICENSE)
