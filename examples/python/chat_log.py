"""Core-only chat and log demo (UI4ME 0.3). Uses only the public ui4me API.

A deterministic assistant streams its replies token by token while a log streams lines,
bounded to the newest LOG_KEEP. Press Enter to send and Shift+Enter for a new line. Drag to
select text in the conversation or log, then press Ctrl+C or use "Copy selection". Lines
containing the search text are highlighted.

    python chat_log.py [--backend native|headless] [--state FILE] [--seconds N]

``--state`` rewrites a small JSON file after each user-visible change, for automated
desktop journeys. ``--seconds`` stops the app after N seconds.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

from ui4me import App

LOG_KEEP = 400
MESSAGE_KEEP = 200
REPLY = ("Streaming reply {n}: UI4ME Core appends each token with append_text, keeps the "
         "conversation at its end unless you scroll away, and leaves your draft, focus and "
         "selection alone while it updates. Příliš žluťoučký kůň úpěl ďábelské ódy.").split(" ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("native", "headless"), default="native")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--seconds", type=float)
    args = parser.parse_args(argv)
    page = Path(__file__).resolve().parents[1] / "foundation" / "chat.html"
    state = {"sent": [], "copied": None, "lines": 0, "replies": 0, "paused": False,
             "closed": False, "resized": [], "keydowns": 0, "errors": []}

    with App(backend=args.backend, app_id="org.ui4me.chatdemo") as app:
        window = app.open_file(page, title="UI4ME chat demo", width=1000, height=700)
        window.set_scroll_follow("msgs")
        window.set_scroll_follow("log")
        # Enter sends instead of inserting a line break; Shift+Enter keeps the default.
        window.set_default_action("composer", "keydown", key="Enter", shift=False)
        stream = {"tokens": [], "target": None, "count": 0}

        def save() -> None:
            if not args.state or window.closed:
                return
            snapshot = dict(state)
            snapshot["rects"] = {e: window.get_rect(e) for e in ("compose", "send", "copy", "msgs", "log", "search", "m0")}
            snapshot["compose"] = window.get_value("compose")
            snapshot["search"] = window.get_value("search")
            snapshot["selection"] = window.get_selection()
            try:
                snapshot["clipboard"] = window.get_clipboard_text()
            except Exception as error:  # an empty or unavailable OS clipboard is not fatal here
                snapshot["clipboard"] = f"<unavailable: {error}>"
            snapshot["focus"] = window.query(":focus")
            snapshot["msgs_scroll"] = window.get_scroll("msgs")
            snapshot["log_scroll"] = window.get_scroll("log")
            temporary = args.state.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, args.state)

        def status(text: str) -> None:
            window.set_text("status", text)

        def send(_=None) -> None:
            text = window.get_value("compose").strip()
            if not text:
                return
            n = len(state["sent"]) + 1
            state["sent"].append(text)
            window.set_value("compose", "")
            body = "<br>".join(html.escape(line) for line in text.split("\n"))
            stream["count"] += 1
            reply = f"r{stream['count']}"
            window.batch([
                {"op": "insert_html", "element": "msgs", "position": "beforeend",
                 "html": f'<p class="msg me" id="u{n}"><b>you</b>{body}</p><p class="msg" id="{reply}"><b>assistant</b></p>'},
                {"op": "trim_children", "element": "msgs", "keep": MESSAGE_KEEP},
            ])
            stream["tokens"] = [t.replace("{n}", str(n)) for t in REPLY]
            stream["target"] = reply
            status(f"Sent message {n}.")
            save()

        def keydown(event: dict) -> None:
            state["keydowns"] += 1
            if event.get("key") == "Enter" and event.get("default_prevented"):
                send()

        def tick(_) -> None:
            if state["paused"] or window.closed:
                return
            state["lines"] += 1
            i = state["lines"]
            query = window.get_value("search").strip()
            text = f"{i:05d} worker-{i % 7} processed item {i * 37 % 1000} ✓"
            cls = ' class="hit"' if query and query in text else ""
            window.batch([
                {"op": "insert_html", "element": "log", "position": "beforeend",
                 "html": f"<div{cls}>{html.escape(text)}</div>"},
                {"op": "trim_children", "element": "log", "keep": LOG_KEEP},
            ])
            if stream["tokens"] and window.has_element(stream["target"]):
                window.append_text(stream["target"], stream["tokens"].pop(0) + " ")
                if not stream["tokens"]:
                    state["replies"] += 1
            if i % 25 == 0:
                save()

        def copy(_) -> None:
            state["copied"] = window.copy_selection()
            status(f"Copied {len(state['copied'])} characters." if state["copied"] else "Nothing selected.")
            save()

        def pause(_) -> None:
            state["paused"] = not state["paused"]
            window.set_text("pause", "Resume stream" if state["paused"] else "Pause stream")
            save()

        def resized(event: dict) -> None:
            state["resized"].append([event.get("width"), event.get("height")])
            save()

        window.on("keydown", keydown, element="compose")
        window.on("click", send, element="send")
        window.on("click", copy, element="copy")
        window.on("click", pause, element="pause")
        window.on("click", lambda _: app.stop(), element="quit")
        window.on("keyup", lambda _: save())
        window.on("mouseup", lambda _: save())
        app.on("resized", resized)
        app.on("closed", lambda _: (state.update(closed=True), app.stop()))
        app.on("error", lambda event: state["errors"].append(event))
        app.timer(40, tick, repeat=True)
        if args.seconds:
            app.timer(int(args.seconds * 1000), lambda _: app.stop())
        app.on("started", lambda _: save())
        app.run()
    if args.state:
        final = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
        final.update({k: state[k] for k in ("sent", "copied", "lines", "replies", "closed", "resized", "errors")})
        final["exited"] = True
        args.state.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
