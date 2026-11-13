"""J1: a reactive greeting in a native window."""
from ui4me import ui

with ui.app("Hello UI4ME UI", width=520, height=300) as app:
    name = ui.input("Your name", placeholder="Type here")
    ui.heading(lambda: f"Hello, {name.value or 'world'}!")
app.run()
