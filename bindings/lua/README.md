# UI4ME for LuaJIT

`ui4me.lua` is a pure LuaJIT FFI binding over the UI4ME C ABI 1. It needs LuaJIT 2.1 (the `ffi`
module; plain Lua 5.x is not supported) and the UI4ME native library of the same version, which
this archive does **not** contain.

## Install

1. Download the native SDK zip for your platform from the same GitHub release
   (`ui4me-sdk-<version>-linux-x64.zip` or `ui4me-sdk-<version>-win-x64.zip`).
2. Either copy its `lib/libui4me_core.so` (Linux) or `lib/ui4me_core.dll` (Windows) next to
   `ui4me.lua` (or into a `native/` directory beside it), or set `UI4ME_NATIVE_LIB` to the
   library's absolute path.
3. Put this directory on `package.path` (for example `LUA_PATH="/path/to/lua/?.lua;;"`) and
   `require("ui4me")`.

Linux also needs the system libraries the native core loads at run time (Wayland or X11,
xkbcommon, EGL/GL); a desktop session normally has them.

```sh
UI4ME_NATIVE_LIB=/opt/ui4me/lib/libui4me_core.so LUA_PATH="$PWD/?.lua;;" luajit examples/notes.lua
```

## What it covers

`ui4me.App{...}` with `open`, `open_file`, `on`, `timer`, `post`, `run`, `stop`, `capabilities`,
`stats` and `close`; `Window` methods for text, values, checked state, attributes, classes, focus,
HTML insertion, `append_text`, `remove_element`, `move_element`, `trim_children`, `query`,
`get_rect`, `batch`, `set_title`, `resize`, `diagnostics` and `close`. Every other wire operation
is reachable through `win:command{ op = "...", ... }` / `app:command{...}` with the fields in
`docs/API.md` of the repository. There is no background-work API: the Lua state is
single-threaded, and every call must run on the thread that created the App.

`build_info()` reports the loaded library's version, source identity and path. The binding is
tested by `tests/lua/test_ui4me.lua` (Linux and Windows) and by a native KWin probe on Linux.
