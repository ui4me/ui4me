"""UI4ME UI 2.0 desktop starter. No external app services or network required.

Run after installing compatible Core 1.x and this source package:
    ui4me-run examples/python/desktop_starter.py

Native menus are not exposed by Core 1.0; this uses an in-window menu.
"""
from __future__ import annotations

from ui4me import ui

DATA = [
    {"id": i, "name": f"Project {i:02d}", "owner": "Ada" if i % 2 else "Lin", "state": "Active" if i % 3 else "New"}
    for i in range(1, 151)
]


def get_page(page: int, page_size: int, query: str):
    matches = [row for row in DATA if query.casefold() in row["name"].casefold()]
    return ui.PageResult(matches[page * page_size:(page + 1) * page_size], len(matches))


with ui.app("UI4ME 2.0 Showcase", width=1100, height=760) as app:
    ui.theme_preset("ocean")
    ui.density("compact")
    app.commands.add("Refresh", lambda: records.refresh(), description="Reload the records")
    app.commands.add("Toggle theme", app.theme.toggle, description="Switch light and dark appearance")

    with ui.toolbar():
        ui.icon("folder", label="Project folder")
        ui.heading("Project Workbench", level=2)
        ui.badge("2.0 development", tone="info")
        ui.spacer()
        ui.menu("Actions", [
            ui.MenuItem("Refresh", lambda: records.refresh()),
            ui.MenuItem("Change appearance", app.theme.toggle),
        ])
        ui.button("Commands", variant="outline", on_click=lambda: palette.open())

    with ui.container():
        ui.breadcrumbs([("Home", lambda: None), ("Workbench", None)])
        with ui.grid(min_width="260px", gap="lg"):
            with ui.paper():
                ui.heading("Quick editor", level=3)
                project_name = ui.input("Project", placeholder="Project name")
                ui.combobox({"new": "New", "active": "Active", "done": "Done"}, label="Stage")
                ui.date("Deadline")
                ui.path("Workspace folder", mode="folder")
                ui.button("Create", on_click=lambda: ui.notify(f"Created {project_name.value or 'untitled'}", kind="success"))
            with ui.paper():
                ui.heading("Quick view", level=3)
                ui.progress_ring(0.64)
                ui.sparkline([3, 8, 5, 9, 6, 14, 11, 15, 20, 17])
                ui.segmented(["Today", "Week", "Month"])
                with ui.disclosure("Advanced settings"):
                    ui.checkbox("Include archived projects")
                    ui.slider("Limit", value=75, min=0, max=100)
            with ui.paper():
                ui.heading("Project tree", level=3)
                ui.tree([ui.TreeNode("main", "Workspace", (
                    ui.TreeNode("one", "Alpha"), ui.TreeNode("two", "Beta"),
                ))])

        with ui.paper():
            ui.heading("Data source table", level=3)
            ui.caption("Loads pages on a Core background worker; stale responses cannot overwrite newer results.")
            records = ui.query_table(get_page, key="id", columns=["id", "name", "owner", "state"], page_size=20)

    with ui.statusbar():
        ui.text("Local desktop • Python + native Core", tone="muted")

    palette = ui.command_palette(title="Go to command")

app.run()
