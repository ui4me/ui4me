"""Native CSS animation probe (Core 0.9). Self-checking; runs on a real desktop window (the
private virtual KWin on Linux, the interactive session on Windows):

    python animation_probe.py --out animation.json

Opens a window with a CSS transition and an infinite keyframe animation on the native loop and
checks that the owner clock drives them (computed values change over real time, the transition
reaches its end value and fires transitionend), that the infinite animation keeps the process's
CPU use bounded (frame pacing, no busy loop), and that an idle window costs almost no CPU.
Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

from ui4me import App

HTML = """<style>
#t{width:100px;height:40px;background:#08f;transition:width .6s linear}
#t.wide{width:300px}
@keyframes spin{to{transform:rotate(1turn)}}
#a{width:40px;height:40px;background:#f80;animation:spin 1s linear infinite}
#a.off{animation:none}
</style><div id=t></div><div id=a></div>"""


def cpu() -> float:
    return time.process_time()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict] = []
    events: list[dict] = []

    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    with App() as app:
        w = app.open(HTML, title="ui4me animation probe", width=420, height=200)
        w.on("transitionend", events.append, element="t")

        def owner(fn):
            done = threading.Event()
            box = {}

            def run():
                try:
                    box["v"] = fn()
                except Exception as e:  # noqa: BLE001 - reported as the case detail
                    box["v"] = f"{type(e).__name__}: {e}"
                done.set()

            app.post(run)
            done.wait(15)
            return box.get("v")

        def style(el, prop):
            return owner(lambda: w.computed_style(el, prop)[prop]["value"])

        def driver():
            try:
                time.sleep(1.0)
                # A1: the infinite animation advances on the native clock.
                samples = []
                for _ in range(4):
                    samples.append(style("a", "transform"))
                    time.sleep(0.23)
                check("A1_keyframes_advance", len(set(samples)) >= 3, samples)
                # A2: CPU while the infinite animation runs, over 3 s of wall time.
                c0, t0 = cpu(), time.monotonic()
                time.sleep(3.0)
                busy = (cpu() - c0) / (time.monotonic() - t0)
                check("A2_running_cpu_bounded", busy < 0.6, {"cpu_fraction": round(busy, 3)})
                # A3: the transition runs and ends.
                owner(lambda: w.add_class("t", "wide"))
                time.sleep(0.25)
                mid = owner(lambda: w.get_rect("t")["width"])
                end = time.monotonic() + 3
                while not events and time.monotonic() < end:
                    time.sleep(0.05)
                final = owner(lambda: w.get_rect("t")["width"])
                check("A3_transition_runs_and_ends", 100 < mid < 300 and final == 300 and events and events[0].get("property_name") == "width",
                      {"mid": mid, "final": final, "event": events[:1]})
                # A4: idle (no animation): the process is nearly idle.
                owner(lambda: w.add_class("a", "off"))
                time.sleep(0.5)
                c0, t0 = cpu(), time.monotonic()
                time.sleep(3.0)
                idle = (cpu() - c0) / (time.monotonic() - t0)
                check("A4_idle_cpu_near_zero", idle < 0.05, {"cpu_fraction": round(idle, 4)})
            finally:
                app.post(app.stop)

        app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
        app.timer(60_000, lambda _: app.stop())
        app.run()
    result = {"status": "passed" if len(cases) == 4 and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], default=str)[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
