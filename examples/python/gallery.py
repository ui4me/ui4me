"""UI4ME 2.1 component gallery. Run directly: python examples/python/gallery.py.

This is a real, keyboard-accessible native desktop application. It doubles as
an interactive integration test. No JavaScript, HTTP server or browser runtime.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import ui4me
from ui4me import ui

HERE = Path(__file__).resolve().parent


@dataclass
class Contact:
    full_name: str = field(default="", metadata={"required": True, "min_length": 2})
    email: str = field(default="", metadata={"pattern": "email", "required": True})
    active: bool = True


def main() -> None:
    with ui.app("UI4ME — Component Gallery", width=1120, height=800,
                assets=HERE / "assets") as app:
        theme = ui.state("system")
        clicks = ui.state(0)
        statuses = ui.state([{"id": i, "service": f"Service {i:02}",
                             "state": "Healthy" if i % 5 else "Warning", "latency": 18 + i * 3}
                            for i in range(1, 38)])

        def toggle_theme(event):
            current = theme.peek()
            next_theme = "dark" if current in ("light", "system") else "light"
            theme.set(next_theme)
            app.theme.set(next_theme)

        def show_toast(event):
            ui.notify("Action completed", kind="success")

        def count_click(event):
            clicks.set(clicks.value + 1)

        def gallery_home():
            ui.heading("Native desktop widgets", level=2)
            ui.text("All rendered by the Rust Core host — Python controls the behavior.")
            with ui.row(wrap=True):
                ui.metric("Components", "95+", detail="Python UI ecosystem", tone="info")
                ui.metric("Platform", "2", detail="Linux / Windows")
                ui.metric("Current count", clicks, detail="Click the counter")
            with ui.row(wrap=True):
                ui.button("Increment", on_click=count_click)
                ui.button("Toast", on_click=show_toast, variant="secondary")
                ui.copy_button("UI4ME — native Python and PowerShell GUI", label="Copy demo text")
            ui.markdown("### Design goal\nUse familiar **Python / PowerShell components** backed by local HTML and CSS. "
                        "No JS, browser, Node or web server.")
            with ui.tooltip("This is a CSS tooltip, visible on hover or keyboard focus"):
                ui.button("Focus me for a tooltip", variant="outline")

        def inputs():
            ui.heading("Inputs and forms", level=2)
            with ui.grid(2, gap="lg"):
                with ui.fieldset("Text inputs"):
                    name = ui.input("Name", placeholder="Ada Lovelace", description="Your public display name")
                    ui.password("Password")
                    ui.email("Email")
                    ui.textarea("Notes", rows=3)
                    ui.text(lambda: "Hello, " + (name.value or "visitor") + "!")
                with ui.fieldset("Selection controls"):
                    ui.number("Threads", value=4, min=1, max=24)
                    ui.select("Country", options={"cz": "Czechia", "de": "Germany", "at": "Austria"})
                    ui.multiselect("Topics", options=["Desktop", "Security", "Testing"], value=("Testing",))
                    ui.checkbox("Enable automatic updates", value=True)
                    ui.switch("Verbose logging", value=False)
            with ui.row(wrap=True):
                ui.radio("Size", options=["Small", "Medium", "Large"], value="Medium", horizontal=True)
                ui.slider("Volume", value=30)
                ui.segmented({"system": "System", "light": "Light", "dark": "Dark"})

        def advanced_inputs():
            ui.heading("Advanced controls", level=2)
            with ui.grid(3):
                ui.date("Deadline")
                ui.time("Start time")
                ui.color("Accent color")
                ui.search("Filter")
                ui.combobox({"one": "Option one", "two": "Option two"}, label="Combobox")
                ui.path("Choose path")
            ui.text("Date/time/color are in-window controls; native browser pickers are not required.")

        def forms():
            ui.heading("Dataclass form validation", level=2)
            ui.text("Change validation marks dirty/touched fields and reports errors next to the input.")

            def save(contact: Contact):
                ui.notify("Saved " + contact.full_name, kind="success")

            form = ui.form(Contact, on_submit=save, validation_mode="change")
            ui.text(lambda: "Dirty: " + str(form.dirty.value) + ", touched: " +
                    ", ".join(sorted(form.touched.value)))

        def tables():
            ui.heading("Tables and state", level=2)

            def selected(row):
                ui.notify(row["service"])

            ui.table(statuses, key="id", columns=["service", "state", "latency"],
                     search=True, sort=True, page_size=9, on_select=selected)
            ui.sparkline([2, 6, 5, 8, 7, 12, 14, 9, 15])
            ui.progress_ring(0.74)

        def layouts():
            ui.heading("Layouts, navigation and density", level=2)
            with ui.resizable_split(percent=34, label="Sidebar width") as split:
                with split.side:
                    ui.heading("Sidebar", level=3)
                    ui.text("Use keyboard arrows on the range control to resize.")
                with split.main:
                    ui.heading("Detail pane", level=3)
                    with ui.card():
                        ui.text("Resizable split uses native HTML range input.")
                        ui.badge("Active", tone="success")
            with ui.row(wrap=True):
                for density in ("comfortable", "compact", "dense"):
                    def set_density(event, name=density):
                        ui.density(name)
                    ui.button(density.title(), on_click=set_density, variant="outline")
            ui.accordion({"First section": lambda: ui.text("First content"),
                          "Second section": lambda: ui.text("Second content")})

        def feedback():
            ui.heading("Feedback and progress", level=2)
            for tone in ("info", "success", "warning", "danger"):
                ui.alert("A " + tone + " status message", kind=tone, title=tone.title())
            with ui.row(wrap=True):
                ui.button("Show toast", on_click=show_toast)
                ui.empty("No data", "Empty states can include a next action")
                ui.loading("Working...")
            ui.progress(0.62)

        with ui.row(align="center", wrap=True):
            ui.image("logo.png", alt="UI4ME", width="34px")
            ui.heading("UI4ME", level=1)
            ui.badge(f"v{ui4me.__version__}", tone="info")
            ui.spacer()
            ui.button("Switch light / dark", on_click=toggle_theme, variant="outline")

        ui.tabs({
            "Overview": gallery_home,
            "Inputs": inputs,
            "Pickers": advanced_inputs,
            "Forms": forms,
            "Tables": tables,
            "Layouts": layouts,
            "Feedback": feedback,
        })
    app.run()


if __name__ == "__main__":
    main()
