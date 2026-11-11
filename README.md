# ui4me

UI4ME is a native desktop UI runtime for applications written in **Python,
PowerShell or LuaJIT**. Applications supply HTML and CSS; Rust owns layout, text shaping,
painting, input and native windows. Application logic stays in the host language.

This checkout implements **1.0.0**, the stable Core. It targets
**Linux x86-64 (Wayland/X11)** and **Windows x64**, with **Python 3.11–3.14**,
**PowerShell 7.4+** or **LuaJIT 2.1**. ABI 1 and the wire schema are frozen under
[COMPATIBILITY](docs/COMPATIBILITY.md); the supported surface is listed in
[SUPPORT_PROFILE_V1.json](docs/SUPPORT_PROFILE_V1.json). It uses a software renderer, not a browser or JavaScript
runtime. Consumers of packaged wheels/modules do not need Rust or a .NET SDK.
See [PROJECT_STATUS](docs/PROJECT_STATUS.md) for the full contract, the measured
platform results and the limits.

## What Core provides

- **Documents:** nested HTML, local stylesheets/images/fonts, selectors and cascade;
  block/inline, flex, grid, positioned and sticky layout, media queries; shaped
  Unicode text with fallback.
- **Forms and HTML controls:** text/password inputs, textarea (selection,
  clipboard, undo/redo, IME), buttons, checkboxes, radio groups, labels;
  `<select>` (drop-down and listbox), `<dialog>` (modal focus trap, Escape,
  return value), `<details>`/`<summary>`.
- **Programmable document (0.3):** insert/remove/move elements, read text and
  attributes, CSS selector queries, atomic batches with one invalidation,
  streaming `append_text`, bounded logs (`trim_children`), declarative
  default-action rules (e.g. Enter sends, Shift+Enter breaks a line).
- **Scroll, geometry and selection:** programmatic scrolling, scroll-into-view,
  element rectangles, "follow the end" for logs that respects a reader who
  scrolled away; mouse/keyboard document text selection with copy and
  `selectionchange`; native clipboard read/write.
- **Desktop services (0.4):** multiple windows; show/hide, focus, minimize,
  maximize, fullscreen, size constraints and icon (unsupported actions report
  why, e.g. on Wayland); window state and monitor information; non-blocking
  native open/save/folder dialogs; file-drop events (Windows/X11).
- **Accessibility:** keyboard operation of all controls, and an AccessKit
  screen-reader bridge (AT-SPI on Linux, UI Automation on Windows) with roles,
  names, states, values and assistive actions. No WCAG conformance is claimed.
- **Runtime:** owner-thread dispatch, timers, background work that settles on the
  owner thread (`run_in_background`), bounded queues and assets, generational element
  identity (stale events are dropped).
- **Public document interface (0.6):** HTML serialization, author stylesheets with
  diagnostics, node references, text geometry, computed style, constraint validation,
  `<input type=file>`, an opt-in external link policy.
- **Desktop integration (0.5, 0.7):** keyboard layouts, dead keys and IME on Wayland and
  Windows; notifications, tray icon, menu bars and context menus, global shortcuts, dark and
  high-contrast preference, rich clipboard, drag and drop, single-instance activation.
- **Interaction and editing (0.8, 1.0):** plain-text and rich `contenteditable` (formatting,
  paragraphs, sanitized paste, undo), touch, pointer events and capture, smooth scrolling and
  scroll snapping, popovers with anchor positioning.
- **Advanced CSS (0.9):** transitions and keyframe animations, `@starting-style`,
  `content-visibility`, `field-sizing`, inline SVG with hit testing, `backdrop-filter`,
  hyphenation in nine languages.
- **Paged media and printing (1.0):** `@page`, page breaks, `paginate`, page rendering,
  PDF export and the native print dialog.
- **Developer diagnostics (1.0):** `get_diagnostics` (versioned, redacted) and `explain`.

Core-only examples: `examples/python/chat_log.py`, `examples/python/file_utility.py`,
`examples/python/data_viewer.py` (and the PowerShell equivalents in `examples/powershell/`),
and `examples/lua/notes.lua`.

Known limits: a software renderer only (no GPU backend); no macOS or ARM64 builds yet;
updates stay interactive up to roughly a thousand rows of a log and slow down linearly
beyond (keep long logs bounded; a document holds at most 65,536 nodes); PDF export is
raster; no JavaScript, network resources, embedded browser or video. See
[PROJECT_STATUS](docs/PROJECT_STATUS.md) for every reported limit.

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

## LuaJIT

```lua
local ui4me = require("ui4me")   -- bindings/lua/ui4me.lua; UI4ME_NATIVE_LIB names the library
local app = ui4me.App{ app_id = "org.example.hello" }
local win = app:open([[<input id="name" value="Ada"><button id="greet">Greet</button>
<p id="status">Ready.</p>]], { title = "Hello", width = 480, height = 240 })
win:on("click", function() win:set_text("status", "Hello, " .. win:get_value("name") .. "!") end,
       { element = "greet" })
app:run()
app:close()
```

The binding is a single FFI file over the C ABI, shipped in the GitHub release as
`ui4me-lua-1.0.0.zip` together with the native library. `tools/build_luajit.sh`
(`.cmd` on Windows) builds a pinned LuaJIT for development.

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
