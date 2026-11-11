#!/usr/bin/env python3
"""Answer the file-dialog probe's native dialogs with real input on a private virtual KWin.

    python3 dialog_journey.py --out DIR -- python3 tests/native/file_dialog_app.py --state {state} --root {root}

Uses the KWin fake_input helper of chat_journey.py. Automated; not a person.
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

ANSWERS = {
    "open_cancel": ("Probe open (cancel)", [f"key 1"]),
    "save_unicode": ("Probe save", [f"key {cj.KEY['enter']}"]),
    "open_unicode": ("Probe open", [f"kd {cj.KEY['ctrl']}", f"key {cj.KEY['v']}", f"ku {cj.KEY['ctrl']}", "sleep 300", f"key {cj.KEY['enter']}"]),
    "folder": ("Probe folder", [f"key {cj.KEY['enter']}"]),
}


def captions(log: Path) -> list[str]:
    out = cj.kwin_script(log, "workspace.windowList().forEach(function(w){ print('UI4ME_WIN|'+w.caption); });")
    return out


def journey(out: Path, command: list[str]) -> dict:
    state_path = out / "state.json"
    root = out / "files"
    command = [c.replace("{state}", str(state_path)).replace("{root}", str(root)) for c in command]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-dialog-{os.getpid()}"
    log = runtime / f"{sock}.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280", "--height", "900"],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    cases: list[dict] = []
    app = fake = None
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
        answered: set[str] = set()
        deadline = time.monotonic() + 150
        seen_captions: dict[str, list[str]] = {}
        while time.monotonic() < deadline:
            s = cj.read_state(state_path)
            if s.get("done"):
                break
            waiting = s.get("waiting")
            if waiting and waiting not in answered:
                caption, keys = ANSWERS[waiting]
                for _ in range(60):
                    names = captions(log)
                    if any(caption in n for n in names):
                        break
                    time.sleep(0.5)
                seen_captions[waiting] = names
                time.sleep(1.0)
                for k in keys:
                    fake(k)
                answered.add(waiting)
            time.sleep(0.3)
        s = cj.read_state(state_path)
        expected = s.get("expected") or {}
        results = s.get("results", {})
        def check(name, ok, detail):
            cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})
        check("D01_open_cancel", results.get("open_cancel") == {"paths": None}, results.get("open_cancel"))
        check("D02_save_unicode_name", results.get("save_unicode") == {"paths": [expected.get("new")]}, results.get("save_unicode"))
        check("D03_open_unicode_file", results.get("open_unicode") == {"paths": [expected.get("file")]}, results.get("open_unicode"))
        check("D04_folder", results.get("folder") == {"paths": [expected.get("folder")]}, results.get("folder"))
        check("D05_dialogs_were_os_windows", all(any(ANSWERS[k][0] in c for c in v) for k, v in seen_captions.items()) and len(seen_captions) == 4, seen_captions)
        if app.wait(timeout=20) != 0:
            cases.append({"id": "D06_exit", "status": "failed", "details": app.returncode})
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
    return {"schema": 1, "kind": "file-dialog-journey", "environment": "kwin_wayland --virtual + xdg-desktop-portal (automated, not a person)", "status": status, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.inner:
        return subprocess.call(["dbus-run-session", "--", sys.executable, __file__, "--inner", "--out", str(args.out), "--", *command],
                               env=cj.isolated_environment())
    result = journey(args.out.resolve(), command)
    (args.out / "journey.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in result["cases"]:
        print(f"{c['status']:7} {c['id']}  {json.dumps(c.get('details'), ensure_ascii=False)[:200]}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
