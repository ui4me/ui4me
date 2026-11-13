"""J6: escape hatch — trusted HTML island with direct Core DOM access next to managed components."""
from ui4me import ui

with ui.app("Escape hatch", width=600, height=360) as app:
    clicks = ui.state(0)
    with ui.card() as card:
        ui.heading("Managed UI")
        ui.text(lambda: f"Managed clicks: {clicks.value}")
        raw = ui.html('<p id="raw-status" style="font-family: monospace">Raw Core region</p>')

        def change():
            clicks.update(lambda n: n + 1)
            raw.core_window.set_text("raw-status", f"Set directly through Core ({clicks.value})")
        ui.button("Change both", on_click=change)
    card.classes.add("developer-defined")
    card.style.set("border-color", "#88aadd")
app.run()
