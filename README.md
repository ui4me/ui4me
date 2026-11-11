# UI4ME

UI4ME is a native desktop UI runtime for applications written in **Python, PowerShell or
LuaJIT**. Applications supply HTML and CSS; Rust owns layout, text shaping, painting, input,
accessibility and native windows. Application logic stays in the host language. It is not a
browser: there is no JavaScript engine, webview or network loader.

**Version 1.0.0** runs on **Linux x86-64 (Wayland/X11)** and **Windows x64**, with
**Python 3.11–3.14**, **PowerShell 7.4+** or **LuaJIT 2.1**. Packages include the native
library, so users don't need Rust or a .NET SDK.

## Install

```sh
pip install ui4me                       # Python
```

```powershell
Install-PSResource Ui4me                # PowerShell 7.4+
```

For LuaJIT and C, download `ui4me-lua-1.0.0.zip` or the native SDK from the
[GitHub release](https://github.com/ui4me/ui4me/releases/latest).

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

`app.open_file("path/to/index.html")` opens an application with separate files; its directory
becomes the permitted local asset root.

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

`Invoke-Ui4meApp` runs the initializer and handlers on a retained UI owner thread in a fresh
runspace; pass external values through `-ArgumentList`.

## LuaJIT

```lua
local ui4me = require("ui4me")   -- ui4me.lua; UI4ME_NATIVE_LIB names the native library
local app = ui4me.App{ app_id = "org.example.hello" }
local win = app:open([[<input id="name" value="Ada"><button id="greet">Greet</button>
<p id="status">Ready.</p>]], { title = "Hello", width = 480, height = 240 })
win:on("click", function() win:set_text("status", "Hello, " .. win:get_value("name") .. "!") end,
       { element = "greet" })
app:run()
app:close()
```

## What Core provides

- **Documents and CSS:** nested HTML, local stylesheets, images and fonts; Stylo cascade;
  block, inline, flex, grid, multicolumn and positioned layout; transitions and animations;
  inline SVG; shaped Unicode text with fallback and hyphenation.
- **Controls and editing:** inputs, textarea, buttons, checkboxes, radios, `select`, `dialog`,
  `details`, popovers, file inputs, form validation; plain-text and rich `contenteditable`.
- **Programmable document:** insert, move and remove elements, selector queries, atomic
  batches, streaming text, bounded logs, scrolling, geometry, selection and clipboard.
- **Desktop integration:** multiple windows, native file dialogs, notifications, tray icon,
  menus, global shortcuts, dark and high-contrast preference, drag and drop, IME and keyboard
  layouts, printing and PDF export.
- **Accessibility:** keyboard operation of every control and a screen-reader bridge (AT-SPI on
  Linux, UI Automation on Windows).
- **Runtime:** owner-thread dispatch, timers, background work, bounded queues, generational
  element identity, versioned diagnostics.

Examples: `examples/python/` and `examples/powershell/` (hello, chat log, file utility, data
viewer), `examples/lua/notes.lua`.

Known limits: software rendering only; no macOS or ARM64 builds; updates slow down beyond about
a thousand rows of a log (keep long logs bounded); PDF export is raster. Every reported limit is
in the [project summary](docs/PROJECT_SUMMARY.md#known-limitations-and-technical-debt).

## Documentation

- [Project summary](docs/PROJECT_SUMMARY.md): scope, architecture, platforms, status and limits.
- [API reference](docs/API.md): the public contract for every binding and the C ABI.
- [Development](docs/DEVELOPMENT.md): building, testing, contributing and releasing.
- [Compatibility](docs/COMPATIBILITY.md) and the generated
  [support profile](docs/SUPPORT_PROFILE_V1.json).
- [Changelog](CHANGELOG.md).

## Building from source

```sh
python -m venv .venv && source .venv/bin/activate    # .\.venv\Scripts\Activate.ps1 on Windows
python -m pip install -r requirements-dev.txt
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

This needs Rust 1.99.1 (`rust-toolchain.toml`), .NET SDK 10, PowerShell 7.4+ and a C compiler;
see [DEVELOPMENT.md](docs/DEVELOPMENT.md) for the details.

## Repository

| Path | Contents |
| --- | --- |
| `crates/` | The Rust engine and native host (`ui4me-core` exposes the C ABI in `include/ui4me.h`) |
| `bindings/` | Python, PowerShell and LuaJIT bindings |
| `patches/` | Carried Stylo, Taffy and AccessKit sources with UI4ME corrections |
| `examples/` | Example applications |
| `tests/` | Native desktop journeys, packaging, soak and tooling tests |
| `tools/`, `dev.py`, `scripts/`, `.github/` | Build, packaging, release gates and publication |

[Source and issues](https://github.com/ui4me/ui4me) ·
[PyPI](https://pypi.org/project/ui4me/) ·
[PowerShell Gallery](https://www.powershellgallery.com/packages/Ui4me/) ·
[MIT license](LICENSE)
