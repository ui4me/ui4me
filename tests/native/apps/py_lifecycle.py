"""Native journey: windows, close veto, file dialogs, async/task cancellation, data source,
timers, high-frequency posts and native shutdown under load.

The last step closes the main window through the compositor; the app must exit 0
by itself with no leftover host/backend processes (checked by the driver).
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import Channel, center, on_owner, until  # noqa: E402

from ui4me import ui  # noqa: E402

TITLE = "UI4ME lifecycle journey"
log: list = []
allow_close = ui.state(False)
show_worker = ui.state(False)
dialog_result = ui.state("none")
second_clicks = ui.state(0)


def slow(task):
    for _ in range(100):
        if task.cancelled:
            return "cancelled"
        time.sleep(0.02)
    return "finished"


def loader(page, size, query):
    rows = [{"id": i, "name": f"Row {i}"} for i in range(1, 101) if query.lower() in f"row {i}"]
    time.sleep(0.05)
    return rows[page * size:(page + 1) * size], len(rows)


@ui.component
def Worker():
    ui.text("worker running")
    app.tasks.submit(slow, on_done=lambda v: log.append(("task_done", v)),
                     on_cancel=lambda: log.append(("task_cancel_callback",)))

    async def later():
        await app.sleep(0.8)
        log.append(("async_after_dispose",))
    ui.button("async", on_click=later)._emit(later)
    app.every(0.05, lambda: log.append(("tick",)))


with ui.app(TITLE, width=900, height=700) as app:
    save_btn = ui.button("Save as…", on_click=lambda: save())
    open_btn = ui.button("Open…", on_click=lambda: open_())
    ui.text(lambda: f"dialog={dialog_result.value}")
    ui.when(show_worker, then=lambda: Worker())
    table = ui.query_table(loader, key="id", columns=["id", "name"], page_size=10)


def save():
    app.dialogs.save_file(title="UI4ME save probe", file_name="probe-out.txt",
                          on_result=lambda p: dialog_result.set(f"save:{p}"))


def open_():
    async def go():
        path = await app.dialogs.open_file(title="UI4ME open probe")
        dialog_result.set(f"open:{path}")
    return go()


app.main.on_close_request(lambda: log.append(("close_request", allow_close.peek())) or allow_close.peek())
app.main.on_close(lambda: log.append(("main_closed",)))


def scenario(ch: Channel):
    win = app.main
    # 1. Data source: first page loads in the background and renders rows.
    ok = until(app, lambda: len(table.rows.value) == 10 and table.total.value == 100, timeout=10)
    ch.check("datasource.first_page", ok, {"rows": len(table.rows.peek()), "total": table.total.peek()})
    x, y = center(win, table.input._focus_target().id)
    ch.request("click", window=TITLE, x=x, y=y)
    ch.request("type", text="row 7")
    ok = until(app, lambda: table.total.value == 11 and not table.loading.value, timeout=10)  # row 7, row 70..79
    ch.check("datasource.search", ok, {"total": table.total.peek(), "rows": table.rows.peek()})

    # 2. Async/task cancellation when the owning component is disposed (before they finish).
    on_owner(app, lambda: show_worker.set(True))
    until(app, lambda: ("tick",) in log, timeout=5)
    on_owner(app, lambda: show_worker.set(False))
    ticks = log.count(("tick",))
    time.sleep(2.5)
    ch.check("task.owner_dispose_skips_callbacks", ("task_done", "finished") not in log
             and ("task_done", "cancelled") not in log, [e for e in log if e[0] != "tick"])
    ch.check("async.owner_dispose_stops_coroutine", ("async_after_dispose",) not in log, None)
    ch.check("timer.owner_dispose_cancels", log.count(("tick",)) <= ticks + 1, {"before": ticks, "after": log.count(("tick",))})

    # 3. Second window built at runtime, real click inside it, native close -> disposal.
    def make_second():
        with app.window("UI4ME second window", width=420, height=260,
                        on_close=lambda: log.append(("second_closed",))) as w:
            b = ui.button("In second", on_click=lambda: second_clicks.set(second_clicks.value + 1))
        return w, b
    second, sbtn = on_owner(app, make_second)
    ch.request("wait-window", window="UI4ME second window")
    x, y = center(second, sbtn.id)
    ch.request("click", window="UI4ME second window", x=x, y=y)
    ch.check("window.second.click", until(app, lambda: second_clicks.value == 1), second_clicks.peek())
    ch.request("native-close", window="UI4ME second window")
    ok = until(app, lambda: second.closed and second not in app.windows and sbtn.disposed, timeout=10)
    ch.check("window.second.native_close_disposes", ok and ("second_closed",) in log,
             {"closed": second.closed, "disposed": sbtn.disposed})

    # 4. Close veto on the main window (user close through the compositor).
    ch.request("native-close", window=TITLE)
    until(app, lambda: ("close_request", False) in log, timeout=5)
    time.sleep(0.8)
    still = ch.request("windows")["windows"]
    ch.check("close.veto_keeps_window", any(TITLE in w["caption"] for w in still) and not win.closed,
             {"log": [e for e in log if e[0] != "tick"]})

    # 5. Native save dialog: real typing + Enter returns the path.
    x, y = center(win, save_btn.id)
    ch.request("click", window=TITLE, x=x, y=y)
    seen = ch.request("wait-window", window="UI4ME save probe", timeout=20).get("window")
    ch.check("dialog.save.appears", seen, seen)
    if seen:
        # Re-entrancy: a user close while the dialog is open. On KDE the portal dialog is
        # not modal for the compositor, so the close reaches the veto policy. On Windows the
        # native dialog disables its owner window, so the close cannot be requested at all.
        ch.request("native-close", window=TITLE)
        time.sleep(0.8)
        if sys.platform == "win32":
            ch.check("dialog.owner_stays_open_while_modal", not win.closed, [e for e in log if e[0] != "tick"])
        else:
            ch.check("dialog.close_veto_while_open", not win.closed and log.count(("close_request", False)) >= 2,
                     [e for e in log if e[0] != "tick"])
        ch.request("activate", window="UI4ME save probe")
        ch.request("key", key="enter", settle=1.0)
        ok = until(app, lambda: dialog_result.value.startswith("save:"), timeout=15)
        ch.check("dialog.save.result", ok and dialog_result.peek().endswith("probe-out.txt"), dialog_result.peek())
    # Open dialog, cancelled with Escape -> None.
    x, y = center(win, open_btn.id)
    ch.request("click", window=TITLE, x=x, y=y)
    seen = ch.request("wait-window", window="UI4ME open probe", timeout=20).get("window")
    if seen:
        ch.request("activate", window="UI4ME open probe")
        ch.request("key", key="escape", settle=1.0)
    ok = until(app, lambda: dialog_result.value == "open:None", timeout=15)
    ch.check("dialog.open.cancel_is_none", seen and ok, dialog_result.peek())

    # 6. High-frequency owner posts from a worker thread are delivered in order.
    seen_values: list = []
    counter = on_owner(app, lambda: ui.state(0))  # signals belong to the owner thread

    def producer():
        for i in range(1, 401):
            while True:
                try:
                    app.post(lambda i=i: (counter.set(i), seen_values.append(i)))
                    break
                except Exception:
                    time.sleep(0.005)
    t = threading.Thread(target=producer)
    t.start()
    t.join(30)
    ok = until(app, lambda: counter.value == 400, timeout=10)
    ch.check("post.high_frequency_ordered", ok and seen_values == list(range(1, 401)),
             {"count": len(seen_values), "last": counter.peek()})
    ch.check("no.app.errors", on_owner(app, lambda: app.error_count) == 0, on_owner(app, lambda: app.last_error))

    # 7. Shutdown under load: a producer keeps posting while the user closes the window.
    stop = threading.Event()

    def flood():
        while not stop.is_set():
            try:
                app.post(lambda: dialog_result.set(f"tick {time.monotonic()}"))
            except Exception:
                pass
            time.sleep(0.002)
    threading.Thread(target=flood, daemon=True).start()
    on_owner(app, lambda: allow_close.set(True))
    ch.done()  # the remaining verdict is the driver's: exit code 0, no leftovers
    ch.request("native-close", window=TITLE)
    time.sleep(10)
    stop.set()
    ch.fatal("app did not exit after an allowed native close")


def start():
    ch = Channel()

    def body():
        try:
            scenario(ch)
        except Exception as error:
            import traceback
            ch.fatal(f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
            ch.done()
            app.stop()
    threading.Thread(target=body, daemon=True).start()


app.after(0.6, start)
app.run()
# After the user-approved close: on_close ran exactly once and run() returned normally.
Channel().check("window.main.on_close_once_on_exit", log.count(("main_closed",)) == 1,
                [e for e in log if e[0] != "tick"])
print("run() returned; log:", [e for e in log if e[0] != "tick"], flush=True)
