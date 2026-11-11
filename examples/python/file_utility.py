"""Core-only file utility (UI4ME 0.4). Uses only the public ui4me API.

Native open/save/folder dialogs, a text editor, a folder listing, clipboard, a modal settings
<dialog> with a <select>, a second "Details" window and responsive layout.

    python file_utility.py [--start DIR] [--state FILE]

``--state`` rewrites a small JSON file after each visible change, for automated journeys.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

from ui4me import App

MAX_BYTES = 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", type=Path)
    parser.add_argument("--start", type=Path, help="initial directory for the file dialogs")
    args = parser.parse_args(argv)
    page = Path(__file__).resolve().parents[1] / "foundation" / "files.html"
    state = {"file": None, "folder": None, "entries": [], "saved": None, "cancelled": 0, "copied": None,
             "theme": "light", "details_open": False, "details_closed": 0, "resized": [], "closed": False}

    with App(app_id="org.ui4me.files") as app:
        window = app.open_file(page, title="UI4ME file utility", width=900, height=640)
        details = {"window": None}

        def save_state() -> None:
            if not args.state or window.closed:
                return
            snapshot = dict(state)
            snapshot["rects"] = {e: window.get_rect(e) for e in ("open", "save", "folder", "copy", "details", "settings", "editor", "theme", "prefs-close", "entries")}
            snapshot["editor"] = window.get_value("editor")
            snapshot["focus"] = window.query(":focus")
            snapshot["dialog"] = window.get_dialog("prefs")
            snapshot["layout"] = "column" if window.get_rect("entries")["width"] > 400 else "row"
            try:
                snapshot["clipboard"] = window.get_clipboard_text()
            except Exception as error:  # an unavailable OS clipboard is reported, not fatal
                snapshot["clipboard"] = f"<unavailable: {error}>"
            tmp = args.state.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, args.state)

        def status(text: str) -> None:
            window.set_text("status", text)
            save_state()

        def opened(result: dict) -> None:
            paths = result.get("paths")
            if not paths:
                state["cancelled"] += 1
                return status("Open cancelled." if "error" not in result else f"Open failed: {result['error']}")
            path = Path(paths[0])
            try:
                if path.stat().st_size > MAX_BYTES:
                    return status("That file is larger than 1 MiB.")
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                return status(f"Cannot open {path.name}: {error}")
            state["file"] = str(path)
            window.set_value("editor", text)
            window.set_text("path", str(path))
            status(f"Opened {path.name} ({len(text)} characters).")

        def saved(result: dict) -> None:
            paths = result.get("paths")
            if not paths:
                state["cancelled"] += 1
                return status("Save cancelled.")
            path = Path(paths[0])
            try:
                path.write_text(window.get_value("editor"), encoding="utf-8")
            except OSError as error:
                return status(f"Cannot save: {error}")
            state["saved"] = state["file"] = str(path)
            window.set_text("path", str(path))
            status(f"Saved {path.name}.")

        def chose_folder(result: dict) -> None:
            paths = result.get("paths")
            if not paths:
                state["cancelled"] += 1
                return status("No folder chosen.")
            folder = Path(paths[0])
            try:
                names = sorted(p.name + ("/" if p.is_dir() else "") for p in folder.iterdir())[:500]
            except OSError as error:
                return status(f"Cannot list {folder}: {error}")
            state["folder"], state["entries"] = str(folder), names
            window.replace_children_html("entries", "".join(f"<li>{html.escape(n)}</li>" for n in names) or "<li>(empty)</li>")
            status(f"{len(names)} entries in {folder.name}.")

        def start_dir():
            if state["folder"]:
                return state["folder"]
            if state["file"]:
                return str(Path(state["file"]).parent)
            return str(args.start.absolute()) if args.start else None

        window.on("click", lambda _: window.open_file_dialog(opened, title="Open text file", directory=start_dir(),
                                                            filters={"Text": ["txt", "md", "log"]}), element="open")
        window.on("click", lambda _: window.save_file_dialog(saved, title="Save text file", directory=start_dir(),
                                                            file_name=Path(state["file"]).name if state["file"] else "untitled.txt"), element="save")
        window.on("click", lambda _: window.folder_dialog(chose_folder, title="Choose folder", directory=start_dir()), element="folder")

        def copy(_):
            text = state["file"] or ""
            window.set_clipboard_text(text)
            state["copied"] = text
            status("Copied path." if text else "No file path to copy.")

        def show_details(_):
            if details["window"] is not None and not details["window"].closed:
                details["window"].activate()
                return
            info = state["file"] or "No file open"
            w = app.open(f'<h3>Details</h3><p id="info">{html.escape(info)}</p><button id="close">Close</button>',
                         title="UI4ME file details", width=420, height=220)
            w.on("click", lambda _: w.close(), element="close")
            details["window"] = w
            state["details_open"] = True
            save_state()

        def theme(event):
            state["theme"] = event.get("value", window.get_value("theme"))
            (window.add_class if state["theme"] == "dark" else window.remove_class)("page", "dark")
            save_state()

        def closed(event):
            if details["window"] is not None and event["window"] == details["window"].id:
                state["details_open"] = False
                state["details_closed"] += 1
                details["window"] = None
                save_state()
            elif event["window"] == window.id:
                state["closed"] = True
                app.stop()

        window.on("click", copy, element="copy")
        window.on("click", show_details, element="details")
        window.on("click", lambda _: (window.show_dialog("prefs"), save_state()), element="settings")
        window.on("click", lambda _: window.close_dialog("prefs", "closed"), element="prefs-close")
        window.on("close", lambda _: save_state(), element="prefs")
        window.on("commit", theme, element="theme")
        window.on("keyup", lambda _: save_state())
        window.on("mouseup", lambda _: save_state())
        app.on("resized", lambda e: (state["resized"].append([e.get("width"), e.get("height")]), save_state()))
        app.on("closed", closed)
        app.on("started", lambda _: save_state())
        app.run()
    if args.state:
        final = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
        final.update({k: state[k] for k in ("file", "saved", "closed", "details_closed", "theme")})
        final["exited"] = True
        args.state.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
