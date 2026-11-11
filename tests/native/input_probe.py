"""Keyboard/IME probe app for native input journeys (Core 0.5 F0501/F0502/F0507).

    python input_probe.py --state STATE.json --commands COMMANDS.jsonl [--seconds N]

Opens one window with two text inputs and a textarea and records, in arrival order, every
``keydown``/``keyup``, ``input``, ``composition*``, ``focus`` and ``blur`` event the public API
delivers, plus the current values. A driver appends JSON lines to the commands file to request
host actions (``focus``, ``set_value``, ``clear``, ``close``, ``stop``). Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ui4me import App

PAGE = """<!doctype html><html><head><style>
body { font: 18px sans-serif; margin: 16px; }
input, textarea { display: block; width: 520px; font-size: 20px; margin: 10px 0; padding: 4px; }
textarea { height: 120px; }
</style></head><body>
<label for=a>First</label><input id=a>
<label for=b>Second</label><input id=b>
<label for=t>Notes</label><textarea id=t></textarea>
<button id=go>Go</button>
</body></html>"""
FIELDS = ("a", "b", "t")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--commands", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=300.0)
    args = parser.parse_args(argv)
    log: list[list] = []
    read = {"offset": 0}

    with App(app_id="org.ui4me.inputprobe") as app:
        window = app.open(PAGE, title="ui4me input probe", width=640, height=460)

        def save() -> None:
            if window.closed:
                return
            state = {
                "log": log,
                "values": {f: window.get_value(f) for f in FIELDS},
                "focus": window.query(":focus"),
                "rects": {e: window.get_rect(e) for e in (*FIELDS, "go")},
                "commands": read["offset"],
                "scroll_t": window.get_scroll("t").get("y"),
            }
            tmp = args.state.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, args.state)

        def record(event: dict) -> None:
            kind = event["type"]
            if kind in ("keydown", "keyup"):
                entry = [kind, event.get("key"), event.get("code"), bool(event.get("ctrl")),
                         bool(event.get("alt")), bool(event.get("shift")), bool(event.get("repeat"))]
            elif kind == "input":
                entry = [kind, event.get("element"), event.get("input_type"), event.get("data"),
                         bool(event.get("is_composing"))]
            elif kind.startswith("composition"):
                entry = [kind, event.get("element"), event.get("data")]
            elif kind == "touch":
                entry = [kind, event.get("phase"), event.get("id")]
            else:
                entry = [kind, event.get("element")]
            log.append(entry)
            save()

        for kind in ("keydown", "keyup", "input", "compositionstart", "compositionupdate",
                     "compositionend", "focus", "blur", "touch"):
            window.on(kind, record)

        def poll(_=None) -> None:
            try:
                data = args.commands.read_bytes()
            except OSError:
                return
            if len(data) <= read["offset"]:
                return
            chunk = data[read["offset"]:]
            if not chunk.endswith(b"\n"):
                return
            read["offset"] = len(data)
            for line in chunk.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                command = json.loads(line)
                op = command["op"]
                if op == "focus":
                    window.focus(command["element"])
                elif op == "set_value":
                    window.set_value(command["element"], command["value"])
                elif op == "clear":
                    log.clear()
                    for f in FIELDS:
                        window.set_value(f, "")
                elif op == "close":
                    window.close()
                    return
                elif op == "stop":
                    app.stop()
                    return
            save()

        app.on("closed", lambda _: app.stop())
        app.timer(50, poll, repeat=True)
        app.timer(int(args.seconds * 1000), lambda _: app.stop())
        save()
        app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
