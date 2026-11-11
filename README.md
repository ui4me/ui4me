# ui4me

UI4ME is a native desktop UI runtime for applications written in **Python or
PowerShell**. Applications supply HTML and CSS; Rust owns layout, text shaping,
painting, input and native windows. Application logic stays in the host language.

This checkout implements **0.2.0**, the application foundation. It targets
**Linux x86-64 (Wayland/X11)** and **Windows x64**, with **Python 3.11–3.14** or
**PowerShell 7.4+**. It uses a software renderer, not a browser or JavaScript
runtime. Consumers of packaged wheels/modules do not need Rust or a .NET SDK.

**This is a source delivery for local verification.** Compilation, automated
checks and installed-package checks are recorded separately from real desktop
acceptance. This ZIP is not a published or fully qualified public release.
See [PROJECT_STATUS](docs/PROJECT_STATUS.md) for the current contract, remaining
platform checks and the ready-to-use verification prompt.

## What 0.2 adds

- Nested HTML, local stylesheets, inline CSS, selectors and cascade.
- Block/inline and flex layouts, wrapping, spacing, borders, backgrounds,
  clipping and scrolling.
- Shaped Unicode text, font fallback, system fonts and local `@font-face`.
- Text/password inputs, textarea, buttons, checkboxes, radio groups and labels;
  selection, plain-text clipboard, undo/redo and keyboard focus.
- Targeted text/value/checked/attribute/class updates and atomic replacement of
  one element's children, with unrelated input state preserved.
- Independent documents in multiple native windows, close interception,
  timers, owner-thread dispatch and background work.
- A bounded asset service shared across sessions, local asset roots, stale-node
  retirement and explicit error outcomes when capacity is exhausted.

Grid, select widgets, table layout, advanced rendering, accessibility and full
platform IME qualification are outside the promoted 0.2 feature set. Some backend
algorithms are retained internally; their presence is not a support claim.

## Python

```python
from ui4me import App

with App() as app:
    window = app.open('''
        <style>
          body { font-family: sans-serif; padding: 24px; background: #f2f5fa; }
          .row { display: flex; gap: 12px; align-items: center; }
          input, button { padding: 10px; }
        </style>
        <h1>Hello from UI4ME</h1>
        <div class="row">
          <input id="name" value="Příliš žluťoučký kůň">
          <button id="greet">Greet</button>
        </div>
        <p id="status">Ready.</p>
    ''', width=720, height=360)
    window.on("click", lambda event: window.set_text(
        "status", f"Hello, {window.get_value('name')}!"), element="greet")
    app.run()
```

For an application with separate files, use
`app.open_file("path/to/index.html")`. Its directory becomes the permitted local
asset root. `app.open(html, base_path="path/to/assets")` explicitly establishes
an asset root for a string document.

## PowerShell

```powershell
Import-Module Ui4me
Invoke-Ui4meApp {
    param($app)
    $window = New-Ui4meWindow @'
<style>body { font-family: sans-serif; padding: 24px; }
input, button { padding: 10px; }</style>
<h1>Hello from UI4ME</h1>
<input id="name" value="Příliš žluťoučký kůň">
<button id="greet">Greet</button><p id="status">Ready.</p>
'@
    $null = Register-Ui4meEvent $window click {
        $window.SetText('status', "Hello, $($window.GetValue('name'))!")
    } -Element greet
}
```

`Invoke-Ui4meApp` runs the initializer and handlers on a retained UI owner thread
in a fresh runspace. Pass external values through `-ArgumentList`; see the
complete example in [`examples/powershell/hello.ps1`](examples/powershell/hello.ps1).

## Build and try it

Install Python 3.11+, the Rust toolchain selected by `rust-toolchain.toml`
(**1.99.1**), a C/C++ compiler, **.NET SDK 10** and **PowerShell 7.4+**. Linux
requires Wayland/X11 development and runtime libraries; Windows requires the
MSVC x64 build tools. Detailed setup is in
[PROJECT_STATUS](docs/PROJECT_STATUS.md#development).

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py version --check
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

The same small foundation app is supplied in both bindings. It uses one local
HTML/CSS fixture, editable controls, a result list, a settings window and a
background action. Run it from installed packages using `python -m ui4me demo`, or
run `examples/python/hello.py` / `examples/powershell/hello.ps1` with the explicit
development setup documented in PROJECT_STATUS.

For distributable candidates:

```sh
python dev.py build --binding all --profile release
python dev.py package --binding all --profile release
python dev.py test --binding all --suite installed --manifest dist/linux-x64/manifest.json
```

Use `dist/win-x64/manifest.json` on Windows. Package assembly combines the two
platforms only after both were built from the same committed source. Registry
publication is an explicit later operation. Do not substitute `pip install
ui4me` for testing this source: that installs whichever version is public.

## Repository

The native application host, document model, renderer and asset service have
separate owners under [`crates/`](crates/). Python and PowerShell share the
versioned [`C ABI`](include/ui4me.h). Build, package and evidence tooling remains
in the new repository structure; `build/`, `dist/` and compiler caches are ignored.

[Source and issues](https://github.com/ui4me/ui4me) ·
[PyPI](https://pypi.org/project/ui4me/) ·
[PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/) ·
[MIT license](LICENSE)
