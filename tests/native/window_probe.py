"""Native window-service probe (Core 0.4 S8). Run with an installed or development ui4me.

    python window_probe.py --out RESULT.json

Opens two native windows and drives maximize/restore, fullscreen, size constraints,
focus/hide (reported unsupported where the platform forbids them), multi-window lifetime,
monitor enumeration and minimize, waiting for the platform's ``window_state``/``resized``
reports. Exit 0 when every check passed. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ui4me import App


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict] = []
    with App(app_id="org.ui4me.windowprobe") as app:
        w1 = app.open('<p id="t">first</p>', title="ui4me probe one", width=700, height=500)
        w2 = app.open('<p id="t">second</p>', title="ui4me probe two", width=400, height=300)
        events: list[dict] = []
        app.on("window_state", events.append)
        app.on("resized", events.append)
        app.on("closed", events.append)
        steps = []
        state = {"step": 0, "since": 0.0, "platform": None}

        def record(name, ok, detail):
            cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

        def wait_for(predicate, name, detail=lambda: None, timeout=4.0):
            def step():
                if predicate():
                    record(name, True, detail())
                    return True
                if time.monotonic() - state["since"] > timeout:
                    record(name, False, {"timeout": timeout, "state": w1.state() if not w1.closed else None})
                    return True
                return False
            return step

        def act(fn):
            def step():
                fn()
                return True
            return step

        platform = lambda: w1.state()["platform"]
        steps += [
            act(lambda: state.update(platform=platform(), caps=app.capabilities())),
            # 0.5 F0508: the capability report names the running platform and agrees with the
            # window rules below (focus/hide unsupported with a cause on Wayland only).
            wait_for(lambda: True, "S8_capabilities_report", lambda: {
                "platform": state["caps"]["platform"],
                "focus": state["caps"]["features"]["window.focus"],
                "file_drop": state["caps"]["features"]["file_drop"],
                "consistent": state["caps"]["platform"] == state["platform"]
                and (state["caps"]["features"]["window.focus"]["status"] == "unsupported") == (state["platform"] == "wayland")
                and all(f["status"] == "supported" or f.get("reason") for f in state["caps"]["features"].values())}),
            act(lambda: w1.maximize()),
            wait_for(lambda: w1.state()["maximized"] is True, "S8_maximize", lambda: w1.state()),
            act(lambda: w1.restore()),
            wait_for(lambda: w1.state()["maximized"] is False, "S8_restore", lambda: w1.state()),
            act(lambda: w1.set_fullscreen(True)),
            wait_for(lambda: w1.state()["fullscreen"] is True, "S8_fullscreen", lambda: w1.state()),
            act(lambda: w1.set_fullscreen(False)),
            wait_for(lambda: w1.state()["fullscreen"] is False and w1.state()["width"] < 1000, "S8_exit_fullscreen", lambda: w1.state()),
            act(lambda: (w1.set_constraints(min_size=(520, 420)), w1.resize(300, 300))),
            wait_for(lambda: abs(w1.state()["width"] - 520) < 1.5 and abs(w1.state()["height"] - 420) < 1.5, "S8_min_size_constraint", lambda: [w1.state()["width"], w1.state()["height"]]),
            act(lambda: state.update(focus=w2.activate(), hide=w2.hide())),
            wait_for(lambda: True, "S8_focus_hide_reported", lambda: {"focus": state["focus"], "hide": state["hide"],
                     "consistent": all(r["applied"] == (state["platform"] != "wayland") for r in (state["focus"], state["hide"]))}),
            act(lambda: w2.show()),
            wait_for(lambda: bool(app.monitors()), "S8_monitors", lambda: app.monitors()),
            act(lambda: w2.close()),
            wait_for(lambda: w2.closed and w1.get_value("t") == "first", "S8_multiwindow_lifetime", lambda: {"w2_closed": w2.closed, "w1": w1.get_value("t")}),
            act(lambda: w1.minimize()),
            wait_for(lambda: w1.state()["minimized"] in (True, None), "S8_minimize", lambda: w1.state()),
        ]

        def tick(_):
            while state["step"] < len(steps):
                if not steps[state["step"]]():
                    return
                state["step"] += 1
                state["since"] = time.monotonic()
            app.stop()

        app.on("started", lambda _: state.update(since=time.monotonic()))
        app.timer(50, tick, repeat=True)
        app.timer(60_000, lambda _: app.stop())
        app.run()
    # A case reported "passed" for focus/hide only when its result matches the platform rule.
    for c in cases:
        if c["id"] in ("S8_focus_hide_reported", "S8_capabilities_report") and not c["details"]["consistent"]:
            c["status"] = "failed"
    result = {"platform": state["platform"], "status": "passed" if cases and all(c["status"] == "passed" for c in cases) and len(cases) == 10 else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], ensure_ascii=False)[:160])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
