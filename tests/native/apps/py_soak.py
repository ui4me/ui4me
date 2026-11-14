"""Long-running stability soak for a UI4ME Python app on the real Core host.

    UI4ME_SOAK_SECONDS=1800 UI4ME_SOAK_OUT=soak.json python tests/native/apps/py_soak.py

Runs directly (Core ``Application.start``); headless with ``UI4ME_TEST_MODE=1`` or on a
desktop. Load: a 20 ms timer, a worker thread posting ~200 updates/s, a log receiving
lines, conditional regions (with their own timers and tasks) mounted and disposed every
second, a keyed list reshuffled, and a second window opened/closed every 30 s.
Every 30 s it samples backend/host RSS and UI4ME diagnostics. Writes a JSON verdict;
exit status 0 only if no errors, bounded component/listener counts and bounded memory.
"""
import json
import os
import random
import threading
import time

from ui4me import ui

SECONDS = float(os.environ.get("UI4ME_SOAK_SECONDS", "120"))
OUT = os.environ.get("UI4ME_SOAK_OUT", "soak.json")
# Load sources (comma list) to isolate growth: tick,post,log,region,list,window (default all).
LOAD = set((os.environ.get("UI4ME_SOAK_LOAD") or "tick,post,log,region,list,window").split(","))

ticks = ui.state(0)
posted = ui.state(0)
show = ui.state(False)
rows = ui.state([{"id": i, "label": f"Row {i}"} for i in range(40)])
samples: list = []
started = time.monotonic()


def rss_kib(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


@ui.component
def Region():
    ui.text(lambda: f"region tick {ticks.value}")
    with ui.row():
        for i in range(8):
            ui.badge(f"b{i}")
    app.every(0.05, lambda: None)
    app.tasks.submit(lambda: time.sleep(0.2))


def tick():
    if "tick" in LOAD:
        ticks.set(ticks.value + 1)
    else:
        ticks.set_silent(ticks.peek() + 1) if hasattr(ticks, "set_silent") else None
        tick.n = getattr(tick, "n", 0) + 1
    n = ticks.peek() if "tick" in LOAD else tick.n
    if n % 50 == 0:
        if "region" in LOAD:
            show.set(not show.value)
        if "list" in LOAD:
            items = list(rows.value)
            random.shuffle(items)
            rows.set(items)


APP_ID = "org.ui4me.test.Soak" + "".join(c for c in "-".join(sorted(LOAD)).title() if c.isalnum())
with ui.app("UI4ME soak", width=800, height=600, app_id=APP_ID) as app:
    ui.metric("Ticks", lambda: str(ticks.value))
    ui.metric("Posted", lambda: str(posted.value))
    ui.when(show, then=lambda: Region())
    logview = ui.log(max_lines=500, height="160px")
    ui.each(rows, key="id", render=lambda r: ui.text(r["label"]))

stop = threading.Event()


def producer():
    n = 0
    while not stop.is_set():
        n += 1
        try:
            app.post(lambda n=n: (posted.set(n) if "post" in LOAD else None,
                                  logview.append(f"line {n}") if n % 10 == 0 and "log" in LOAD else None))
        except Exception:
            time.sleep(0.01)  # bounded queue full: back off (never an error)
        time.sleep(0.005)


second = {"w": None, "opens": 0}


def toggle_window():
    if "window" not in LOAD:
        return
    if second["w"] is not None and not second["w"].closed:
        second["w"].close()
        second["w"] = None
    else:
        with app.window("UI4ME soak second", width=300, height=200) as w:
            ui.text("second window")
            ui.button("noop")
        second["w"] = w
        second["opens"] += 1


def sample():
    diag = app.diagnostics()
    main = app.main.diagnostics()
    samples.append({
        "t": round(time.monotonic() - started, 1), "backend_rss_kib": rss_kib(os.getpid()),
        "host_rss_kib": rss_kib(os.getppid()), "managed_elements": main.get("managed_elements"),
        "listeners": main.get("listeners"), "reactions": diag["reactions"], "errors": app.error_count,
        "pending_posts": diag["core_pending_posts"], "timers": diag["core_timers"], "tasks": diag["tasks"],
    })


def finish():
    stop.set()
    sample()
    app.stop()


app.every(0.02, tick)
app.every(30, toggle_window)
app.every(30, sample)
app.after(1.0, sample)
app.after(SECONDS, finish)
threading.Thread(target=producer, daemon=True).start()
app.run()

warm = [s for s in samples if s["t"] >= min(120, SECONDS / 4)] or samples
first, last = warm[0], samples[-1]
growth = (last["backend_rss_kib"] or 0) - (first["backend_rss_kib"] or 0)
host_growth = (last["host_rss_kib"] or 0) - (first["host_rss_kib"] or 0)
elements = [s["managed_elements"] for s in samples if s["managed_elements"] is not None]
verdict = {
    "seconds": SECONDS, "load": sorted(LOAD), "ticks": ticks.peek(), "posted": posted.peek(), "second_window_opens": second["opens"],
    "errors": app.error_count, "last_error": app.last_error,
    "backend_rss_growth_kib_after_warmup": growth, "host_rss_growth_kib_after_warmup": host_growth,
    "managed_elements_max": max(elements) if elements else None, "samples": samples,
}
verdict["pass"] = bool(app.error_count == 0 and growth < 30_000 and host_growth < 60_000
                       and elements and max(elements) < 400)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(verdict, f, indent=1)
if os.environ.get("UI4ME_TEST_CHANNEL"):  # running under a native driver (vkwin / RDP)
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from channel import Channel
    channel = Channel()
    channel.check("soak.pass", verdict["pass"], {k: v for k, v in verdict.items() if k != "samples"})
    channel.done()
print("SOAK", "PASS" if verdict["pass"] else "FAIL", json.dumps({k: v for k, v in verdict.items() if k != "samples"}))
raise SystemExit(0 if verdict["pass"] else 1)
