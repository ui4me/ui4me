"""Native `<input type=file>` probe app (Core 0.6 F0606). A desktop driver answers the pickers.

    python file_input_app.py --state STATE.json --root DIR

Shows a single-file input (``accept=.txt``) and a multiple-file input. STATE.json carries the
inputs' rectangles, the events seen (``cancel``, ``commit`` with ``files``), the chosen files
and ``expected`` paths. The app puts the path to choose on the clipboard before each step, so
the driver can paste it into the OS picker. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ui4me import App

NAME = "příliš žluťoučký kůň.txt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    folder = args.root / "ünïcødé složka"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / NAME).write_text("ui4me", encoding="utf-8")
    state: dict = {"events": [], "files": {}, "expected": str(folder / NAME), "rects": {}}

    with App(app_id="org.ui4me.fileinputprobe") as app:
        w = app.open("""<style>body{font:18px sans-serif;margin:20px} input{display:block;margin:20px 0;width:300px;height:40px}</style>
            <input id=pick type=file accept=".txt"><input id=many type=file multiple><p id=s>ready</p>""",
                     title="ui4me file input probe", width=520, height=320)

        def save(_=None) -> None:
            if w.closed:
                return
            state["rects"] = {e: w.get_rect(e) for e in ("pick", "many")}
            state["files"] = {e: w.get_files(e) for e in ("pick", "many")}
            state["focus"] = w.query(":focus")
            tmp = args.state.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, args.state)

        def record(event: dict) -> None:
            state["events"].append({"type": event["type"], "element": event.get("element"), "files": event.get("files")})
            save()

        for kind in ("cancel", "commit", "click"):
            w.on(kind, record)
        app.on("started", lambda _: (w.set_clipboard_text(str(folder / NAME)), save()))
        app.timer(500, save, repeat=True)
        app.timer(150_000, lambda _: app.stop())
        app.on("closed", lambda _: app.stop())
        app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
