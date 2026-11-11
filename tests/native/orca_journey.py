"""Screen-reader journey with Orca (Core 1.0 F1108). Run inside the private virtual KWin session:

    python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/orca_journey.py --out DIR/orca.json

Starts Orca with private preferences (`-u`) and a debug file, opens a UI4ME window with labelled
controls, moves the focus and operates the controls with real key presses through the
compositor (KWin fake input), and checks what Orca presented: its braille presentation
(`BRAILLE LINE` in the debug output, written with or without a braille display). Speech is
disabled (`-d speech`): the private session has no speech server, and Orca blocks on the
speech-dispatcher client without one. Names, roles and states reach Orca through AT-SPI. Automated keystrokes; the
speech is Orca's, not a person's judgement of usability.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from ui4me import App

sys.path.insert(0, str(Path(__file__).resolve().parent / "kwin"))
from chat_journey import Input, build_fakeinput  # noqa: E402

KEY_TAB, KEY_SPACE, KEY_LEFTSHIFT = 15, 57, 42

HTML = """<style>body{font:18px sans-serif;padding:16px} label{display:block;margin:8px 0}</style>
<h1>Order form</h1>
<label for=name>Customer name</label><input id=name value="Ada">
<label><input type=checkbox id=sub> Subscribe to news</label>
<label for=qty>Quantity</label><input id=qty type=number value=2 min=1 max=9>
<button id=send>Send order</button>
<div id=notes contenteditable aria-label="Order notes">Deliver after five</div>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="ui4me-orca-"))
    debug = work / "orca-debug.out"
    fake = Input(build_fakeinput(work))
    # Orca 48 reads the X keyboard map with `xkbcomp $DISPLAY`; the private Wayland session has no
    # X display, and the owner's display must not be used: a display number that does not exist
    # makes that lookup fail softly.
    import os
    orca_env = dict(os.environ, DISPLAY=":7531")
    orca = subprocess.Popen(["orca", "--replace", "-d", "speech", "-u", str(work / "prefs"), "--debug-file", str(debug)], env=orca_env,
                            stdout=subprocess.DEVNULL, stderr=(work / "orca-stderr.log").open("w"))
    time.sleep(8)
    cases: list[dict] = []

    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    def text() -> str:
        return debug.read_text(encoding="utf-8", errors="replace") if debug.exists() else ""

    def lines() -> list[str]:
        # Counted in whole lines: the log is read while Orca appends to it.
        return [l.strip() for l in text().splitlines() if "BRAILLE LINE" in l]

    def spoken(since: int) -> str:
        return "\n".join(lines()[since:])

    def press(*codes: int) -> None:
        for c in codes:
            fake(f"kd {c}")
        for c in reversed(codes):
            fake(f"ku {c}")
        time.sleep(0.3)

    plan: list = []
    try:
        with App(app_id="org.ui4me.orcajourney") as app:
            w = app.open(HTML, title="ui4me screen reader journey", width=520, height=420)

            def driver():
                try:
                    time.sleep(3.0)
                    check("O00_orca_running", orca.poll() is None and debug.exists(), {"debug": str(debug)})
                    steps = [
                        # Braille: `$l` marks an editable text line, `< >`/`<x>` an unchecked/checked box.
                        ("O01_name_field", (KEY_TAB,), [r"Customer name Ada \$l"]),
                        ("O02_checkbox", (KEY_TAB,), [r"< > Subscribe to news check box"]),
                        ("O03_checkbox_toggle", (KEY_SPACE,), [r"<x> Subscribe to news check box"]),
                        ("O04_spin_button", (KEY_TAB,), [r"Quantity 2 \$l"]),
                        ("O05_button", (KEY_TAB,), [r"Send order button"]),
                        ("O06_editing_host", (KEY_TAB,), [r"Order notes Deliver after five \$l"]),
                        ("O07_back_to_button", (KEY_LEFTSHIFT, KEY_TAB), [r"Send order"]),
                    ]
                    # Orca writes its debug file through a buffer: the presentation is checked
                    # after Orca has quit and flushed it (below), in the order of the steps.
                    for _name, keys, _patterns in steps:
                        press(*keys)
                        time.sleep(0.7)
                    plan.extend(steps)
                    state = {}
                    done = threading.Event()

                    def read():
                        state["checked"] = w.get_checked("sub")
                        done.set()
                    app.post(read)
                    done.wait(5)
                    check("O08_state_matches_speech", state.get("checked") is True, state)
                finally:
                    app.post(app.stop)

            app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
            app.timer(120_000, lambda _: app.stop())
            app.run()
    finally:
        orca.terminate()
        try:
            orca.wait(timeout=10)
        except subprocess.TimeoutExpired:
            orca.kill()
        fake.close()
    # The presentation, in order: each step's lines follow the previous step's.
    shown = lines()
    at = 0
    for name, _keys, patterns in plan:
        hit = None
        for i in range(at, len(shown)):
            if all(re.search(p, shown[i], re.I) for p in patterns):
                hit = i
                break
        check(name, hit is not None, {"line": shown[hit] if hit is not None else None, "searched_from": at})
        if hit is not None:
            at = hit + 1
    cases.sort(key=lambda c: c["id"])
    result = {"status": "passed" if len(cases) == 9 and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    (args.out.parent / "orca-braille.log").write_text(spoken(0), encoding="utf-8")
    err = work / "orca-stderr.log"
    if err.exists():
        (args.out.parent / "orca-stderr.log").write_text(err.read_text(errors="replace")[-20000:], encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"])[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
