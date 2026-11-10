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

The minimal renderer supports a small fixed-layout HTML form subset and inline
colors; it is not a browser. Documentation and the full native lifecycle
contract are maintained at [github.com/ui4me/ui4me](https://github.com/ui4me/ui4me).
