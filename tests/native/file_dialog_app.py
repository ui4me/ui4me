"""Native file-dialog probe app (Core 0.4 S9). A desktop driver answers the dialogs.

    python file_dialog_app.py --state STATE.json --root DIR

Runs, one at a time: open (cancelled), save (a preset new Unicode name, accepted), open (the
Unicode file, name pasted from the clipboard), folder (accepted). STATE.json carries
``waiting`` (the dialog the driver must answer) and each result. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ui4me import App

NAME = "příliš žluťoučký kůň.txt"
NEW = "nový soubor ž.txt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    folder = args.root / "ünïcødé složka"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / NAME).write_text("ui4me", encoding="utf-8")
    state: dict = {"waiting": None, "results": {}, "done": False}

    def save() -> None:
        tmp = args.state.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, args.state)

    with App(app_id="org.ui4me.dialogprobe") as app:
        window = app.open('<h1 id="h">File dialog probe</h1><p id="s">waiting</p>', title="ui4me dialog probe", width=500, height=300)
        steps = [
            ("open_cancel", lambda cb: window.open_file_dialog(cb, title="Probe open (cancel)", directory=folder)),
            ("save_unicode", lambda cb: window.save_file_dialog(cb, title="Probe save", directory=folder, file_name=NEW, filters={"Text": ["txt"]})),
            ("open_unicode", lambda cb: (window.set_clipboard_text(NAME), window.open_file_dialog(cb, title="Probe open", directory=folder))),
            ("folder", lambda cb: window.folder_dialog(cb, title="Probe folder", directory=folder)),
        ]

        def run(index: int) -> None:
            if index == len(steps):
                state.update(waiting=None, done=True)
                save()
                app.stop()
                return
            name, start = steps[index]

            def finished(result: dict) -> None:
                state["results"][name] = result
                window.set_text("s", f"{name}: {result}")
                run(index + 1)

            state["waiting"] = name
            save()
            start(finished)

        app.on("started", lambda _: app.timer(800, lambda _: run(0)))
        app.timer(120_000, lambda _: app.stop())
        app.run()
    state["expected"] = {"folder": str(folder), "file": str(folder / NAME), "new": str(folder / NEW)}
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
