"""Screen-reader bridge probe (Linux AT-SPI). Run on a private session bus with a compositor:

    python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/a11y_probe.py --out DIR/a11y.json

Enables accessibility on the private bus, starts a small ui4me app as a child process, reads its
tree through AT-SPI like a screen reader, and invokes a button's default action. Automated.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = r'''
import json, sys
from ui4me import App
state = {"clicks": 0}
with App(app_id="org.ui4me.a11yprobe") as app:
    w = app.open("""<h1>Probe heading</h1><button id="go">Press me</button>
      <label for="name">Your name</label><input id="name" value="Ada">
      <label><input id="ok" type="checkbox" checked> Agree</label>
      <a id="lnk" href="#x">A link</a><p style="display:none">Hidden text</p>""", title="ui4me a11y probe", width=500, height=300)
    def click(_):
        state["clicks"] += 1
        open(sys.argv[1], "w").write(json.dumps(state))
    w.on("click", click, element="go")
    app.timer(25000, lambda _: app.stop())
    app.run()
'''


def walk(node, depth=0, out=None):
    out = [] if out is None else out
    if depth > 12:
        return out
    try:
        role, name = node.get_role_name(), node.get_name()
        states = node.get_state_set()
    except Exception:
        return out
    out.append({"depth": depth, "role": role, "name": name,
                "checked": states.contains(__import__("gi.repository.Atspi", fromlist=["Atspi"]).StateType.CHECKED),
                "focusable": states.contains(__import__("gi.repository.Atspi", fromlist=["Atspi"]).StateType.FOCUSABLE),
                "node": node})
    for i in range(node.get_child_count()):
        child = node.get_child_at_index(i)
        if child is not None:
            walk(child, depth + 1, out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
                    "--method", "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", "IsEnabled", "<true>"],
                   check=False, capture_output=True)
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    clicks = Path(tempfile.mkdtemp()) / "clicks.json"
    script = Path(tempfile.mkdtemp()) / "app.py"
    script.write_text(APP, encoding="utf-8")
    app = subprocess.Popen([sys.executable, str(script), str(clicks)])
    cases = []
    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})
    try:
        nodes = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            desktop = Atspi.get_desktop(0)
            apps = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
            def titled(a):
                kids = [a.get_child_at_index(i) for i in range(min(a.get_child_count(), 5))]
                return any(k is not None and k.get_name() == "ui4me a11y probe" for k in kids)
            target = [a for a in apps if a is not None and titled(a)]
            if target:
                nodes = walk(target[0])
                if any(n["role"] in ("button", "push button") for n in nodes):
                    break
            time.sleep(0.5)
        summary = [{k: v for k, v in n.items() if k != "node"} for n in nodes]
        roles = {(n["role"], n["name"]) for n in nodes}
        check("A01_app_and_window_exposed", any(n["role"] == "frame" and n["name"] == "ui4me a11y probe" for n in nodes), summary[:3])
        check("A02_heading", ("heading", "Probe heading") in roles, sorted(r for r in roles if r[0] == "heading"))
        check("A03_button_name", ("button", "Press me") in roles or ("push button", "Press me") in roles, sorted(r for r in roles if "button" in r[0]))
        check("A04_labelled_entry", any(n["role"] in ("entry", "text") and n["name"] == "Your name" for n in nodes), sorted(r for r in roles if r[0] in ("entry", "text")))
        check("A05_checkbox_state", any(n["role"] == "check box" and n["name"] == "Agree" and n["checked"] for n in nodes), [n for n in summary if n["role"] == "check box"])
        check("A06_link", ("link", "A link") in roles, sorted(r for r in roles if r[0] == "link"))
        check("A07_hidden_excluded", all("Hidden" not in (n["name"] or "") for n in nodes), None)
        button = next((n["node"] for n in nodes if n["role"] in ("button", "push button")), None)
        acted = False
        if button is not None:
            action = button.get_action_iface()
            if action is not None and action.get_n_actions() > 0:
                action.do_action(0)
                for _ in range(40):
                    if clicks.exists():
                        acted = True
                        break
                    time.sleep(0.25)
        check("A08_button_default_action_clicks", acted, json.loads(clicks.read_text()) if acted else None)
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
    status = "passed" if all(c["status"] == "passed" for c in cases) else "failed"
    args.out.write_text(json.dumps({"status": status, "cases": cases}, indent=2, default=str), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], default=str)[:220])
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
