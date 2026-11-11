#!/usr/bin/env python3
"""Real-input journey for `<input type=file>` on a private virtual KWin (Core 0.6 F0606).

    python3 file_input_journey.py --out DIR -- python3 tests/native/file_input_app.py --state {state} --root {root}

A KWin fake_input pointer click on the input opens the KDE xdg-desktop-portal file chooser:
Escape cancels it; a pasted Unicode path plus Enter chooses that file; Space on the focused
multiple input opens it again. Automated; not a person.
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

CAPTION = "ui4me file input probe"
ESC = 1
SPACE = 57


def journey(out: Path, command: list[str]) -> dict:
    state_path = out / "state.json"
    root = out / "files"
    command = [c.replace("{state}", str(state_path)).replace("{root}", str(root)) for c in command]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-fileinput-{os.getpid()}"
    log = runtime / f"{sock}.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280", "--height", "900"],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    cases: list[dict] = []
    app = fake = None

    def case(name, action):
        try:
            cases.append({"id": name, "status": "passed", "details": action()})
        except Exception as error:
            cases.append({"id": name, "status": "failed", "details": f"{type(error).__name__}: {error}"})

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
        geo: dict = {}

        def others() -> list[str]:
            return [c for c in cj.kwin_script(log, "workspace.windowList().forEach(function(w){ print('UI4ME_WIN|'+w.caption); });")
                    if c and CAPTION not in c and c.strip()]

        def wait_picker(before: list[str]) -> list[str]:
            for _ in range(60):
                now = others()
                if len(now) > len(before):
                    time.sleep(1.5)
                    return now
                time.sleep(0.5)
            raise TimeoutError(f"no picker window appeared (windows {before})")

        def at(element: str) -> str:
            r = cj.read_state(state_path)["rects"][element]
            return f"{geo['origin'][0] + r['x'] + r['width'] / 2:.0f} {geo['origin'][1] + r['y'] + r['height'] / 2:.0f}"

        def events(kind: str, element: str) -> list:
            return [e for e in cj.read_state(state_path).get("events", []) if e["type"] == kind and e["element"] == element]

        def shown():
            cj.wait(state_path, lambda s: s["rects"]["pick"], timeout=30)
            for _ in range(50):
                g = cj.window_geometry(log, CAPTION, (40, 40, 520, 320))
                if g:
                    break
                time.sleep(0.2)
            time.sleep(0.5)
            geo["origin"] = cj.window_geometry(log, CAPTION)
            return {"client": geo["origin"]}

        def cancel():
            before = others()
            fake(f"click {at('pick')}")
            names = wait_picker(before)
            fake(f"key {ESC}")
            cj.wait(state_path, lambda s: len(events("cancel", "pick")) == 1, timeout=15)
            return {"picker": names[len(before):], "files": cj.read_state(state_path)["files"]["pick"]}

        def choose_unicode():
            before = others()
            fake(f"click {at('pick')}")
            wait_picker(before)
            fake(f"kd {cj.KEY['ctrl']}")
            fake(f"key {cj.KEY['a']}")
            fake(f"key {cj.KEY['v']}")
            fake(f"ku {cj.KEY['ctrl']}")
            time.sleep(0.4)
            fake(f"key {cj.KEY['enter']}")
            s = cj.wait(state_path, lambda s: s["files"]["pick"], timeout=20)
            expected = s["expected"]
            commits = events("commit", "pick")
            if s["files"]["pick"] != [expected] or not commits or commits[-1]["files"] != [expected]:
                raise AssertionError(f"files {s['files']['pick']} commits {commits} expected {expected}")
            return {"files": s["files"]["pick"]}

        def keyboard_multiple():
            before_cancel = len(events("cancel", "many"))
            before = others()
            fake(f"click {at('many')}")
            # The click opened the picker: dismiss it, then reopen with Space on the focused input.
            wait_picker(before)
            fake(f"key {ESC}")
            cj.wait(state_path, lambda s: len(events("cancel", "many")) == before_cancel + 1, timeout=15)
            before = others()
            fake(f"key {SPACE}")
            wait_picker(before)
            fake(f"kd {cj.KEY['ctrl']}")
            fake(f"key {cj.KEY['a']}")
            fake(f"key {cj.KEY['v']}")
            fake(f"ku {cj.KEY['ctrl']}")
            time.sleep(0.4)
            fake(f"key {cj.KEY['enter']}")
            s = cj.wait(state_path, lambda s: s["files"]["many"], timeout=20)
            if s["files"]["many"] != [s["expected"]]:
                raise AssertionError(f"files {s['files']['many']}")
            return {"files": s["files"]["many"], "focus": s.get("focus")}

        case("P00-window-shown", shown)
        case("P01-click-opens-picker-escape-cancels", cancel)
        case("P02-choose-unicode-path", choose_unicode)
        case("P03-keyboard-space-multiple", keyboard_multiple)
        cj.close_window(log, CAPTION)
        try:
            app.wait(timeout=20)
        except subprocess.TimeoutExpired:
            cases.append({"id": "P04-exit", "status": "failed", "details": "app did not exit after close"})
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
    return {"schema": 1, "kind": "file-input-journey", "environment": "kwin_wayland --virtual + xdg-desktop-portal (automated, not a person)", "status": status, "cases": cases}


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
