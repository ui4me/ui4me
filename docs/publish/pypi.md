# UI4ME — native desktop UI framework for Python

Build rich desktop applications using **plain Python**, reactive state and a comprehensive set of HTML/CSS components. UI4ME renders through [UI4ME Core](https://github.com/ui4me/ui4me-core), a native Rust desktop window host. **No JavaScript, Chromium, WebKit, Electron or local web server.**

## Install

Python 3.11+ on Linux x86-64 (Wayland, glibc 2.34+) or Windows x64:

```bash
uv add ui4me
# or in a virtual environment:
python -m pip install ui4me
```

The platform-specific `ui4me-core` native host installs automatically as a dependency. Daily application development uses `python app.py` or `uv run app.py`, **not** a manual host launcher or TOML manifest.

## Your first app

```python
from ui4me import ui


def main():
    with ui.app('Hello', width=520, height=320) as app:
        count = ui.state(0)

        def increment(event):
            count.set(count.value + 1)

        ui.heading('Native Python UI')
        ui.text(ui.computed(lambda: f'Clicks: {count.value}'))
        ui.button('Click', on_click=increment)

    app.run()


if __name__ == '__main__':
    main()
```

Run: `python app.py` or `uv run app.py`.

Core launches a managed backend process; imports/side effects before `ui.app` may happen twice. Keep non-idempotent initialization after bootstrap.

## Components and applications

Reactive inputs, forms and dataclass validation, tables and keyed dynamic lists, shells and layouts, tabs, menus and dialogs, in-window notifications, themes and CSS presets, icons, date/time/color controls, file/path picking, Markdown, logs, chat, charts/metrics, background tasks, settings and multiwindow apps. Built-in components are styled using local CSS, and low-level Core objects remain accessible.

## Documentation

- [Python quickstart](https://github.com/ui4me/ui4me/blob/main/docs/guides/quickstart-python.md)
- [Component catalog](https://github.com/ui4me/ui4me/blob/main/docs/components/index.md)
- [Python API reference](https://github.com/ui4me/ui4me/blob/main/docs/reference/python-api.md)
- [Gallery and examples](https://github.com/ui4me/ui4me/blob/main/docs/gallery.md)
- [Coding-agent skills](https://github.com/ui4me/ui4me/blob/main/docs/guides/agent-skills.md)
- [Supported platforms and limitations](https://github.com/ui4me/ui4me/blob/main/docs/reference/compatibility.md)

[Source repository](https://github.com/ui4me/ui4me) · [UI4ME Core](https://github.com/ui4me/ui4me-core) · [License](https://github.com/ui4me/ui4me/blob/main/LICENSE)
