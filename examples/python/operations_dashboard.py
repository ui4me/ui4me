"""Native operations dashboard: live state, table search and safe background refresh.

Run: python examples/python/operations_dashboard.py
No network access: simulated metrics exist solely to exercise widget contracts.
"""
from __future__ import annotations
import datetime as dt
from ui4me import ui

SERVICES = [
    {"id": 1, "service": "Gateway", "owner": "Platform", "health": "Healthy", "latency": 19},
    {"id": 2, "service": "Sync", "owner": "Operations", "health": "Healthy", "latency": 43},
    {"id": 3, "service": "Backup", "owner": "Storage", "health": "Warning", "latency": 108},
    {"id": 4, "service": "Alerts", "owner": "Security", "health": "Healthy", "latency": 31},
]


def main() -> None:
    with ui.app("UI4ME Operations", width=1100, height=760,
                app_id="org.ui4me.examples.OperationsDashboard") as app:
        rows = ui.state(list(SERVICES))
        last_checked = ui.state("Not checked yet")
        status = ui.state("Idle")
        selected = ui.state("No service selected")
        selected_number = ui.state(0)

        def choose(row):
            selected.set(row["service"] + " — " + row["health"])
            selected_number.set(selected_number.value + 1)

        def refresh(event):
            now = dt.datetime.now().strftime("%H:%M:%S")
            last_checked.set(now)
            status.set("Updated at " + now)
            ui.notify("Status refreshed", kind="success")

        with ui.row(align="center"):
            ui.heading("Operations", level=1)
            ui.spacer()
            ui.button("Refresh", on_click=refresh)
        with ui.grid(3, gap="md"):
            ui.metric("Services", len(SERVICES), detail="Local sample records")
            ui.metric("Warnings", 1, tone="warning", detail="Review backup")
            ui.metric("Last check", last_checked, detail="Desktop local time")
        with ui.resizable_split(percent=32, label="Resize navigation") as split:
            with split.side:
                ui.heading("Workspace", level=3)
                ui.text("Services, states and interaction examples")
                ui.text(selected)
                ui.text(lambda: f"Selections: {selected_number.value}")
                ui.badge("Native", tone="info")
            with split.main:
                ui.heading("Service inventory", level=3)
                ui.table(rows, key="id", columns=["service", "owner", "health", "latency"],
                         search=True, sort=True, page_size=10, on_select=choose)
        ui.text(status)
    app.run()


if __name__ == "__main__":
    main()
