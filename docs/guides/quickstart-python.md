# Python: your first UI4ME app

Install with `uv add ui4me` or `pip install ui4me`. Create `app.py`:

```python
from ui4me import ui


def main():
    with ui.app('Greeter', width=560, height=360) as app:
        name = ui.input('Your name', placeholder='Type here')
        answer = ui.text('Welcome!')

        def greet(event):
            answer.set('Hello, ' + (name.value or 'world') + '!')

        with ui.row():
            ui.button('Greet', on_click=greet)
            ui.button('Quit', on_click=app.stop, variant='secondary')

    app.run()


if __name__ == '__main__':
    main()
```

Run directly:

```bash
uv run app.py
# or: python app.py (in an environment with ui4me installed)
```

No manifest or manual host launcher. UI4ME calls `ui4me_core.Application.start()`, which internally starts a native host and reruns the script as the managed backend. **Code before bootstrap executes twice**; keep side effects after `with ui.app(...)` begins (or within the callback), and guard the entry point with `if __name__ == '__main__'`.

State updates can be automatic too:

```python
with ui.app('Counter') as app:
    count = ui.state(0)

    def increment(event):
        count.set(count.value + 1)

    ui.text(lambda: f'Count: {count.value}')
    ui.button('Increment', on_click=increment)
app.run()
```

The `lambda` here is a **reactive expression**, not a callback; write named callbacks for actions and use `ui.computed` for complex derived values. See [reactivity](../concepts/reactivity.md).

Generate a project with `ui4me-ui-new my-app --name 'My App'`, or inspect runnable [examples](https://github.com/ui4me/ui4me/tree/main/examples/python). Keep [Core raw APIs](../concepts/core-integration.md) for special native operations.
