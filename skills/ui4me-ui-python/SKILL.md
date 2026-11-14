---
name: ui4me-ui-python
description: Build native Linux and Windows desktop GUI applications in Python using UI4ME's component framework, reactive state, forms, data tables, tasks and themes. No browser, JavaScript, Qt, Node or HTTP server.
---

# UI4ME high-level Python GUI skill

This is the **component framework** `ui4me`, not the low-level `ui4me-core` package. Prefer this skill when the user wants fast, idiomatic desktop UI. Import `from ui4me import ui`. Native rendering and all OS integration come from `ui4me-core` 1.0.1+. Do not build a web server, import browser libraries or write JavaScript.

## First create a plain script

```bash
uv add 'ui4me>=2.1,<3'
uv run app.py
```

```python
from ui4me import ui


def main():
    with ui.app("Tasks", width=800, height=540) as app:
        count = ui.state(0)
        ui.heading("Tasks", level=1)
        status = ui.text(lambda: f"Finished: {count.value}")

        def finish_one(event):
            count.set(count.value + 1)

        ui.button("Finish task", on_click=finish_one)

    app.run()


if __name__ == "__main__":
    main()
```

`ui.app()` calls Core's direct startup automatically. The Python script is started twice: first as host launcher and again as the supervised application. Put all side effects after the `ui.app(...)` call, and use a `__main__` guard. Normal dev does **not** need `app.toml` or `ui4me-run`; `ui4me-run --headless app.py` remains available for specialized host tests.

## Key rules

1. **Build inside `with ui.app(...) as app:`**. Use `with ui.row()`, `with ui.column()`, `with ui.card()` etc. `app.run()` follows the block and keeps callbacks alive until shutdown.
2. **Reactive state**: `ui.state(initial)` yields a `Signal`; read `.value`, change with `.set(...)`, `.update(...)`; use computed functions or `lambda:` only for declarative reactive display, never unnecessary beginner event-handler lambdas.
3. **Owner-thread only**: Components and signals are mutated on the UI owner thread. Use `app.tasks.submit(fn, on_done=...)`, `app.post(callback)` or `async def` UI callbacks for background work. Never access Core DOM from a worker thread.
4. **Component lifetime**: Use `ui.when`, `ui.each(..., key=..., preserve=True)`, and scoped `app.tasks`. Removed components cancel their timers/tasks and ignore late completion. Never mutate the managed DOM through raw Core APIs unless it is an explicit isolated mount.
5. **Events**: Register normal `on_click`, `on_change`, `component.on(...)` callbacks. Core has no browser JS event engine. User-facing strings use safe text APIs, not `ui.html`.
6. **Forms**: `ui.form(MyDataclass, validation_mode="change")` for generated typed forms; form `.dirty`, `.touched`, `.valid`, `.submitting`, `.fields`, `.validate()`, `.reset()`. For custom forms use `ui.fieldset` plus inputs.
7. **Data**: `ui.table(..., search=True, sort=True, selected=...)`; `ui.query_table(loader,...)` for background page loads. Set a stable row key. Use `ui.multiselect` for multiple choices.
8. **Theming**: Functional CSS is always present. Visual theme is replaceable via `app.theme.load(css,mode="replace")` or `ui.stylesheet`. Prefer CSS variables and stable classes to private DOM internals.
9. **Desktop operations**: `app.clipboard`, `app.desktop`, native file dialogs, attention and multiwindow are Core-backed. Native tray/OS notifications/print/nonnative media are unsupported unless Core reports otherwise.
10. **Testing**: pure state/unit tests first, real host headless with `Pilot` second, then native Linux Wayland and Windows interactive input. Never claim keyboard/IME/AT coverage based on fake events alone.

## When adding a new component

Follow `references/components.md`: public signature, ownership, state, styling hooks, keyboard/focus, error handling, Core mapping, examples and two-language parity. Add tests to unit, bridge and host suites; add the widget to `examples/python/gallery.py` and docs. Prefer composing existing `Field`, `Container`, `Element` and Signal primitives.

## Reference map

- [Component patterns and existing widget APIs](references/components.md)
- [Reactive state, tasks, windows and forms](references/reactivity.md)
- [Core behavior, security and platform limitations](references/core-and-security.md)
- [Packaging, testing and publishing workflow](references/testing-and-release.md)

Main repository: https://github.com/ui4me/ui4me · Core: https://github.com/ui4me/ui4me-core
