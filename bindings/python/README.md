# ui4me for Python

ui4me provides a native application runtime for Python. Install the platform
wheel with `python -m pip install ui4me`, then create an `App`, open a window,
register callbacks and call `run()`. The wheel includes its matching native
library; Python 3.11–3.14 and Linux x86-64 or Windows x64 are supported.

```python
from ui4me import App

with App() as app:
    window = app.open('<h1>Hello</h1><button id="quit">Quit</button>')
    window.on("click", lambda event: app.stop(), element="quit")
    app.run()
```

Version 1.0 provides HTML documents, CSS layout (flex, grid, multicolumn, positioning, media
queries), transitions and animations, inline SVG, shaped Unicode text, local stylesheets,
images and fonts, form controls and rich `contenteditable`, independent windows, desktop
services (dialogs, notifications, tray, menus, shortcuts), printing and PDF export, and a
screen-reader bridge. Use
`app.open_file("ui/index.html")` to keep the document directory for relative
assets, or pass `base_path` to `app.open()`. JavaScript, network resources and
embedded browsers are not part of ui4me.

Update a document with `set_text`, `set_value`, `set_checked`, attributes and
classes. Element methods include `insert_html` and its shortcuts,
`remove_element`, `move_element`, atomic `batch([...])`, streaming `append_text`
and `trim_children`. Read with `get_text`, `get_attribute` and
`query(selector)`. Scrolling uses `scroll_to`, `scroll_into_view`, `get_rect`
and `set_scroll_follow`. The selection and clipboard use `get_selection` and
`copy_selection`. The window is controlled with `maximize`, `set_constraints`
and `state()`. Native dialogs: `open_file_dialog`, `save_file_dialog` and
`folder_dialog`. Programmatic changes keep unrelated form state and do not
synthesize input events.

Register handlers such as `click`, `input`, `commit`, `keydown`, `toggle`,
`close`, `selectionchange`, `file_dialog` or `window_state` with an element ID
where relevant. Ancestor IDs in an event's `path` also match. Default actions
such as Enter in a textarea are cancelled declaratively with
`set_default_action`, because handlers run after dispatch.
`window.accessibility_tree()` shows the tree that screen readers see.

Create and run native applications on the main thread. Only `app.post()` and
`app.stop()` are safe from worker threads. A posted callback runs on the UI owner
and returns a Future with its result or exception; do not wait for an unfinished
Future on the owner. Stop the app, let `run()` return and then dispose it through
the context manager. An App runs once; create a fresh App for the next session.

Run `python -m ui4me demo` for the packaged foundation application, which
demonstrates these APIs with local HTML/CSS, a second window and background work.
Background work runs with `app.run_in_background(fn, on_done=...)`; its result is delivered on
the UI owner thread. The full API, platform support and limits are documented at
[github.com/ui4me/ui4me](https://github.com/ui4me/ui4me/blob/main/docs/API.md).
