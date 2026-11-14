# Reactive state, forms, tasks and lifecycle

- `s = ui.state(0)`; `s.value`, `s.peek()`, `s.set(new)`, `s.update(fn)`; `ui.computed(fn)` and `ui.effect(fn)` track dependencies. `ui.batch()` groups multiple state changes.
- Component construction and updates must happen on the UI owner thread. In background tasks do I/O/CPU only, then update state via `app.post()` or `on_done` on the owner thread.
- `app.tasks.submit(load, arg, on_done=display, on_error=report)` supports cancellation; owner disposal ignores late completions. `app.after(seconds, callback)` and `app.every(seconds,callback)` return cancellable timer handles.
- `ui.form(Dataclass, value=..., validation_mode="submit"|"change"|"blur", on_submit=...)`. Fields may declare metadata `label`, `required`, `pattern`, `min`, `max`, `choices`, `widget`, `validator`. Use `.values`, `.value`, `.dirty`, `.touched`, `.valid`, `.submitting`, `.validate()`, `.reset()` and `.mark_clean()`.
- `ui.each(items, key="id", render=..., preserve=True)` preserves keyed component scope; in preserved mode item is an `ItemRef` whose fields are reactive.
- App notifications, Core window events and owner-thread scheduling are serialized safely. A real native window's `on_close` runs once and close policy can veto; final host shutdown must drain ordered events.
- For multiple windows use `with app.window("Secondary"):` and window-scoped content/navigation; closing a window tears down its components, tasks and listeners.

## Example: a background operation

```python
with ui.app("Loader") as app:
    status = ui.state("Idle")
    ui.text(lambda: status.value)

    def load():
        return 42  # Replace with filesystem, network or database work.

    def done(result):
        status.set(f"Loaded {result}")

    def begin(event):
        status.set("Loading")
        app.tasks.submit(load, on_done=done)

    ui.button("Load", on_click=begin)
app.run()
```
