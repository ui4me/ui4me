#!/usr/bin/env python3
"""Real-input journey for the Core-only file utility on a private virtual KWin (Core 0.4 gate).

    python3 files_journey.py --out DIR -- <demo command with {state} and {start}>

Prepares {start} = DIR/files/ünïcødé složka with notes.txt, starts KWin, and drives the native
open/save/folder dialogs (xdg-desktop-portal), settings dialog, select, clipboard, second window,
resize and close with KWin fake_input. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat_journey as cj  # noqa: E402

TITLE = "UI4ME file utility"
K = dict(cj.KEY, esc=1, down=108, home=102)


def caption_present(log: Path, text: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(text in c for c in cj.kwin_script(log, "workspace.windowList().forEach(function(w){ print('UI4ME_WIN|'+w.caption); });")):
            return True
        time.sleep(0.4)
    return False


def journey(out: Path, command: list[str]) -> dict:
    state_path = out / "state.json"
    start = out / "files" / "ünïcødé složka"
    start.mkdir(parents=True, exist_ok=True)
    (start / "notes.txt").write_text("Hello from ui4me", encoding="utf-8")
    (start / "žluťoučký.md").write_text("# Unicode name", encoding="utf-8")
    command = [c.replace("{state}", str(state_path)).replace("{start}", str(start)) for c in command]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-files-{os.getpid()}"
    log = runtime / f"{sock}.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280", "--height", "900"],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    cases: list[dict] = []
    app = fake = None
    geo: dict = {}
    try:
        for _ in range(100):
            if (runtime / sock).exists():
                break
            time.sleep(0.1)
        time.sleep(1.0)
        env["WAYLAND_DISPLAY"] = sock
        os.environ["WAYLAND_DISPLAY"] = sock
        cj.use_virtual_display(sock)
        app = subprocess.Popen(command, env=env, stdout=(out / "app.log").open("w"), stderr=subprocess.STDOUT)
        fake = cj.Input(cj.build_fakeinput(out))
        state = lambda: cj.read_state(state_path)
        wait = lambda predicate, timeout=15: cj.wait(state_path, predicate, timeout)

        def at(s, element, fx=0.5, fy=0.5):
            r = s["rects"][element]
            return f"{geo['o'][0] + r['x'] + r['width'] * fx:.0f} {geo['o'][1] + r['y'] + r['height'] * fy:.0f}"

        def click(element):
            fake(f"click {at(state(), element)}")

        def keys(*names):
            for n in names:
                fake(f"key {K[n]}")

        def chord(mod, key):
            fake(f"kd {K[mod]}")
            fake(f"key {K[key]}")
            fake(f"ku {K[mod]}")

        def case(name, action):
            try:
                cases.append({"id": name, "status": "passed", "details": action()})
            except Exception as error:
                cases.append({"id": name, "status": "failed", "details": f"{type(error).__name__}: {error}"})

        def shown():
            wait(lambda s: s["rects"]["open"], 30)
            g = None
            for _ in range(50):
                g = cj.window_geometry(log, TITLE, (40, 40, 900, 680))
                if g:
                    break
                time.sleep(0.2)
            time.sleep(0.6)
            geo["o"] = cj.window_geometry(log, TITLE)
            s = wait(lambda s: s["rects"]["editor"]["width"] > 0)
            return {"client": geo["o"], "layout": s["layout"]}

        def open_cancel():
            click("open")
            if not caption_present(log, "Open text file"):
                raise AssertionError("no OS open dialog appeared")
            time.sleep(0.8)
            keys("esc")
            s = wait(lambda s: s["cancelled"] == 1)
            return {"cancelled": s["cancelled"]}

        def folder():
            click("folder")
            if not caption_present(log, "Choose folder"):
                raise AssertionError("no OS folder dialog appeared")
            time.sleep(0.8)
            keys("enter")
            s = wait(lambda s: s["folder"] == str(start))
            if "žluťoučký.md" not in s["entries"] or "notes.txt" not in s["entries"]:
                raise AssertionError(f"listing {s['entries']}")
            return {"folder": s["folder"], "entries": s["entries"]}

        def open_file():
            click("open")
            if not caption_present(log, "Open text file"):
                raise AssertionError("no OS open dialog appeared")
            time.sleep(0.8)
            fake("type notes.txt")
            keys("enter")
            s = wait(lambda s: s["file"] == str(start / "notes.txt") and s["editor"] == "Hello from ui4me")
            return {"file": s["file"], "editor": s["editor"]}

        def edit_save():
            click("editor")
            chord("ctrl", "end")
            fake("type  edited")
            wait(lambda s: s["editor"].endswith(" edited"))
            click("save")
            if not caption_present(log, "Save text file"):
                raise AssertionError("no OS save dialog appeared")
            time.sleep(0.8)
            chord("ctrl", "a")
            fake("type copy.txt")
            keys("enter")
            target = start / "copy.txt"
            s = wait(lambda s: s["saved"] == str(target))
            content = target.read_text(encoding="utf-8")
            if content != "Hello from ui4me edited":
                raise AssertionError(f"saved content {content!r}")
            return {"saved": s["saved"], "content": content}

        def copy_path():
            click("copy")
            s = wait(lambda s: s["clipboard"] == str(start / "copy.txt"))
            return {"os_clipboard": s["clipboard"]}

        def settings():
            click("settings")
            s = wait(lambda s: s["dialog"]["open"] and s["dialog"]["modal"])
            if s["focus"] != ["theme"]:
                raise AssertionError(f"modal focus {s['focus']}")
            keys("down")
            s = wait(lambda s: s["theme"] == "dark")
            keys("esc")
            s = wait(lambda s: not s["dialog"]["open"])
            if s["focus"] != ["settings"]:
                raise AssertionError(f"focus not restored: {s['focus']}")
            return {"theme": s["theme"], "focus": s["focus"]}

        def second_window():
            click("details")
            s = wait(lambda s: s["details_open"])
            if not caption_present(log, "UI4ME file details", 10):
                raise AssertionError("details window not shown")
            cj.kwin_script(log, "workspace.windowList().forEach(function(w){ if (w.caption.indexOf('UI4ME file details')>=0) w.closeWindow(); });")
            s = wait(lambda s: s["details_closed"] == 1 and not s["details_open"])
            return {"details_closed": s["details_closed"], "main_still": s["editor"]}

        def responsive():
            cj.window_geometry(log, TITLE, (40, 40, 640, 680))
            s = wait(lambda s: s["layout"] == "column" and s["resized"])
            return {"layout": s["layout"], "resized": s["resized"][-1]}

        def close():
            cj.kwin_script(log, f"workspace.windowList().forEach(function(w){{ if (w.caption.indexOf('{TITLE}')>=0) w.closeWindow(); }});")
            code = app.wait(timeout=20)
            s = state()
            if code != 0 or not s.get("exited") or not s.get("closed"):
                raise AssertionError(f"exit {code} exited={s.get('exited')} closed={s.get('closed')}")
            return {"exit_code": code}

        case("G01_window_shown", shown)
        case("G02_open_dialog_cancel", open_cancel)
        case("G03_folder_dialog_unicode_listing", folder)
        case("G04_open_dialog_reads_file", open_file)
        case("G05_edit_and_save_dialog_writes", edit_save)
        case("G06_copy_path_os_clipboard", copy_path)
        case("G07_settings_modal_select_escape", settings)
        case("G08_second_window_lifetime", second_window)
        case("G09_responsive_resize", responsive)
        case("G10_close_exits_cleanly", close)
    finally:
        if fake:
            try:
                fake.close()
            except Exception:
                fake.p.kill()
        if app and app.poll() is None:
            app.kill()
        cj.reap_private_bus()
        kwin.terminate()
        try:
            kwin.wait(timeout=10)
        except subprocess.TimeoutExpired:
            kwin.kill()
        if log.exists():
            shutil.copy(log, out / "kwin.log")
            log.unlink()
    status = "passed" if cases and all(c["status"] == "passed" for c in cases) else "failed"
    return {"schema": 1, "kind": "file-utility-journey", "environment": "kwin_wayland --virtual + xdg-desktop-portal (automated, not a person)",
            "command": command, "status": status, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.inner:
        env = cj.isolated_environment()
        try:
            return subprocess.call(["dbus-run-session", "--", sys.executable, __file__, "--inner", "--out", str(args.out), "--", *command], env=env)
        finally:
            shutil.rmtree(env["XDG_RUNTIME_DIR"], ignore_errors=True)
    result = journey(args.out.resolve(), command)
    (args.out / "journey.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in result["cases"]:
        print(f"{c['status']:7} {c['id']}  {json.dumps(c.get('details'), ensure_ascii=False)[:200]}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
