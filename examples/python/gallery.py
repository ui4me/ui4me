"""Component gallery: every built-in component with light/dark switching."""
from pathlib import Path

from ui4me import ui

with ui.app("UI4ME UI Gallery", width=1100, height=760, assets=Path(__file__).parent / "assets") as app:
    def inputs():
        with ui.grid(2):
            name = ui.input("Name", placeholder="Ada", description="Your full name")
            ui.password("Password")
            ui.number("Age", value=36, min=0, max=150)
            ui.select("Country", options={"cz": "Czechia", "at": "Austria", "de": "Germany"})
            ui.textarea("Notes", rows=3)
            ui.slider("Volume", value=40)
        with ui.row(wrap=True):
            ui.checkbox("Subscribe")
            ui.switch("Dark mode", on_change=lambda on: app.theme.set("dark" if on else "light"))
            ui.radio("Size", options=["S", "M", "L"], value="M", horizontal=True)
        ui.text(lambda: f"Hello {name.value or '…'}")

    def buttons():
        with ui.row(wrap=True):
            for variant in ("primary", "secondary", "outline", "ghost", "danger"):
                ui.button(variant.capitalize(), variant=variant)
            ui.button("Loading", loading=True)
            ui.button("Disabled", disabled=True)
        with ui.row(wrap=True):
            for tone in ("default", "info", "success", "warning", "danger"):
                ui.badge(tone, tone=tone)
        ui.progress(0.62)

    def feedback():
        for kind in ("info", "success", "warning", "danger"):
            ui.alert(f"This is a {kind} message.", kind=kind, title=kind.capitalize())
        with ui.row():
            ui.button("Toast", on_click=lambda: ui.notify("Saved!", kind="success"))
            ui.button("Confirm", variant="secondary",
                      on_click=lambda: ui.confirm("Are you sure?", on_result=lambda ok: ui.notify(f"Answer: {ok}")))
        with ui.grid(3):
            ui.empty("No customers", "Create the first one to get started")
            ui.loading()
            ui.error_state(description="The server did not answer", retry=lambda: ui.notify("Retrying…"))

    def data():
        rows = [{"id": i, "name": f"Item {i}", "price": i * 3.5, "stock": i % 7} for i in range(1, 41)]
        ui.table(rows, key="id", search=True, sort=True, page_size=8, on_select=lambda r: ui.notify(r["name"]))
        ui.markdown("### Markdown\nSupports **bold**, *italic*, `code`, [links](https://example.com) and lists:\n"
                    "- one\n- two\n\n> Raw <b>HTML</b> is shown as text.")

    with ui.row():
        ui.image("logo.png", alt="UI4ME logo", width="36px")
        ui.heading("UI4ME UI", level=1)
        ui.spacer()
        ui.button("Toggle theme", variant="outline", on_click=app.theme.toggle)
    ui.tabs({"Inputs": inputs, "Buttons": buttons, "Feedback": feedback, "Data": data})
app.run()
