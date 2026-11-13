"""Counter with derived state and a theme toggle."""
from ui4me import ui

with ui.app("Counter", width=420, height=320) as app:
    count = ui.state(0)
    parity = ui.computed(lambda: "even" if count.value % 2 == 0 else "odd")
    with ui.card():
        ui.heading(lambda: f"Count: {count.value}", level=1)
        ui.badge(parity, tone="info")
        with ui.row():
            ui.button("−", variant="secondary", on_click=lambda: count.update(lambda n: n - 1))
            ui.button("+", on_click=lambda: count.update(lambda n: n + 1))
            ui.button("Reset", variant="ghost", on_click=lambda: count.set(0), disabled=lambda: count.value == 0)
    ui.button("Toggle theme", variant="outline", on_click=app.theme.toggle)
app.run()
