"""Settings utility with typed form, validation and persisted choices.

Run directly: python examples/python/settings_manager.py
"""
from __future__ import annotations
from dataclasses import dataclass, field
from ui4me import ui


@dataclass
class Preferences:
    display_name: str = field(default="Operator", metadata={"required": True, "min_length": 2})
    email: str = field(default="user@example.org", metadata={"pattern": "email"})
    show_tips: bool = True


def main():
    with ui.app("UI4ME Settings", width=760, height=640,
                app_id="org.ui4me.examples.SettingsManager") as app:
        ui.heading("Settings", level=1)
        ui.text("Configure a desktop application without building a web server.")
        ui.alert("This demonstration writes only the UI4ME app settings JSON file.", kind="info")

        def saved(values: Preferences):
            app.settings.set("display_name", values.display_name)
            app.settings.set("email", values.email)
            app.settings.set("show_tips", values.show_tips)
            ui.notify("Settings saved", kind="success")

        starting = Preferences(
            display_name=app.settings.get("display_name", "Operator"),
            email=app.settings.get("email", "user@example.org"),
            show_tips=app.settings.get("show_tips", True),
        )
        form = ui.form(Preferences, value=starting, on_submit=saved, validation_mode="change")
        ui.text(lambda: "Unsaved changes: " + ("Yes" if form.dirty.value else "No"))
        with ui.row():
            ui.button("Reset", on_click=form.reset, variant="outline")
            ui.button("Quit", on_click=app.stop, variant="secondary")
    app.run()


if __name__ == "__main__":
    main()
