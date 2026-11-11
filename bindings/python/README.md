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

Version 0.2 provides HTML documents, CSS layout, shaped Unicode text, local
stylesheets and images, editable inputs, checkboxes/radio groups and independent
windows. Use `app.open_file("ui/index.html")` to preserve the document directory
for relative assets, or pass `base_path` to `app.open()`. JavaScript, network
resources, embedded browsers and operating-system account management are outside
this foundation.

Update a document through `set_text`, `set_value`, `set_checked`, attributes,
classes and `replace_children_html`. Programmatic changes preserve unrelated
form state and do not synthesize input events. Register `click`, `input`,
`change`, `focus` or `blur` handlers with an element ID; ancestor IDs in an
event's `path` also match, so a button handler receives clicks on its contents.
`window.diagnostics()` reports bounded resource and renderer diagnostics.

Create and run native applications on the main thread. Only `app.post()` and
`app.stop()` are safe from worker threads. A posted callback runs on the UI owner
and returns a Future with its result or exception; do not wait for an unfinished
Future on the owner. Stop the app, let `run()` return and then dispose it through
the context manager. An App runs once; create a fresh App for the next session.

Run `python -m ui4me demo` for the packaged foundation application, which
demonstrates these APIs with local HTML/CSS, a second window and background work.
Current support limits and the native lifecycle contract are maintained at
[github.com/ui4me/ui4me](https://github.com/ui4me/ui4me).
