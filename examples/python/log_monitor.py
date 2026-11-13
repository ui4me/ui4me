"""J4: streaming log from a background worker — bounded, smart scroll-follow, no UI threading code."""
import random
import time

from ui4me import ui

with ui.app("Log Monitor", width=900, height=600) as app:
    running = ui.state(False)
    task = {}

    def produce(task):
        n = 0
        while not task.cancelled:
            n += 1
            level = random.choices(["info", "warning", "error"], [90, 8, 2])[0]
            log.post([(f"{time.strftime('%H:%M:%S')}  event {n:>6}  value={random.random():.4f}", level)])
            time.sleep(0.002)

    def toggle():
        if running.value:
            task["t"].cancel()
        else:
            task["t"] = app.tasks.submit(produce, on_cancel=lambda: None)
        running.update(lambda r: not r)

    toolbar = ui.row()
    log = ui.log(max_lines=5000, follow="smart")
    with toolbar:
        ui.heading("Log Monitor", level=2)
        ui.spacer()
        ui.caption(lambda: f"{log.count.value:,} lines kept")
        ui.button(lambda: "Stop" if running.value else "Start", on_click=toggle)
        ui.button("Clear", variant="secondary", on_click=lambda: log.clear())
app.run()
