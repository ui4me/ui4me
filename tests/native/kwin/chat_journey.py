#!/usr/bin/env python3
"""Automated real-input desktop journey for the Core chat/log demo on a private virtual KWin.

    python3 chat_journey.py --out DIR -- <demo command ...>

The demo command must accept ``--state FILE`` (Python) or ``-StatePath FILE`` (PowerShell);
pass the literal token ``{state}`` where the path goes. A private D-Bus session and a
``kwin_wayland --virtual`` compositor are started; input is sent through KWin's
``org_kde_kwin_fake_input`` (test-only, enabled by KWIN_WAYLAND_NO_PERMISSION_CHECKS). The
result is DIR/journey.json. This is automated compositor input on a virtual output, not a
person at a physical monitor; label evidence accordingly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = {"enter": 28, "shift": 42, "ctrl": 29, "backspace": 14, "a": 30, "c": 46, "v": 47, "end": 107}


def isolated_environment() -> dict:
    """The environment for the private session bus: no route to the person's real desktop.

    D-Bus-activated services (xdg-desktop-portal and its file chooser) inherit the bus's
    activation environment; without this they would draw on the real session's display."""
    env = dict(os.environ)
    for name in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS"):
        env.pop(name, None)
    # A private runtime directory: the compositor socket, the AT-SPI bus (otherwise the user-wide
    # $XDG_RUNTIME_DIR/at-spi/bus of the real session) and portal state stay inside the run.
    env["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="ui4me-runtime-")
    return env


def use_virtual_display(sock: str) -> None:
    """Point the private bus's activated services at the virtual KWin. KWin's startup already
    activated the portals without a display, so they are restarted to re-activate on demand."""
    subprocess.run(["dbus-update-activation-environment", f"WAYLAND_DISPLAY={sock}", "QT_QPA_PLATFORM=wayland",
                    "XDG_CURRENT_DESKTOP=KDE"], check=True, capture_output=True)
    reap_private_bus(("xdg-desktop-portal", "kioworker"))
    time.sleep(0.5)


def reap_private_bus(only: tuple[str, ...] = ()) -> list[int]:
    """Stop processes attached to this run's private session bus (all, or those whose command
    line contains one of ``only``)."""
    bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not bus.startswith("unix:path=/tmp/dbus-"):
        return []
    stopped = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in (os.getpid(), os.getppid()):
            continue
        try:
            environ = (entry / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if only:
            try:
                cmdline = (entry / "cmdline").read_bytes().decode(errors="replace")
            except OSError:
                continue
            if not any(o in cmdline for o in only):
                continue
        if f"DBUS_SESSION_BUS_ADDRESS={bus}".encode() in environ:
            try:
                os.kill(int(entry.name), 15)
                stopped.append(int(entry.name))
            except OSError:
                pass
    return stopped


def build_fakeinput(out: Path) -> Path:
    binary = out / "fakeinput"
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["wayland-scanner", "client-header", HERE / "fake-input.xml", f"{t}/fake-input-client-protocol.h"], check=True)
        subprocess.run(["wayland-scanner", "private-code", HERE / "fake-input.xml", f"{t}/fake-input-protocol.c"], check=True)
        subprocess.run(["gcc", "-O1", f"-I{t}", "-o", binary, HERE / "fakeinput.c", f"{t}/fake-input-protocol.c", "-lwayland-client"], check=True)
    return binary


class Input:
    def __init__(self, binary: Path):
        self.p = subprocess.Popen([binary, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def __call__(self, line: str) -> None:
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        if self.p.stdout.readline().strip() != "ok":
            raise RuntimeError(f"fakeinput failed on {line!r}")

    def close(self) -> None:
        self.p.stdin.close()
        self.p.wait(timeout=5)


def kwin_script(log: Path, body: str) -> list[str]:
    js = Path(tempfile.mkstemp(suffix=".js")[1])
    js.write_text(body, encoding="utf-8")
    before = log.read_text(errors="replace").count("\n")
    name = f"ui4me{os.getpid()}{time.monotonic_ns()}"
    subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(js), name], check=True, capture_output=True)
    subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"], check=True, capture_output=True)
    time.sleep(0.5)
    subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", name], capture_output=True)
    js.unlink()
    lines = log.read_text(errors="replace").splitlines()[before:]
    return [l.split("UI4ME_WIN|", 1)[1] for l in lines if "UI4ME_WIN|" in l]


def window_geometry(log: Path, caption: str, frame: tuple[int, int, int, int] | None = None) -> tuple[float, float, float, float] | None:
    set_frame = f"w.frameGeometry = {{x:{frame[0]},y:{frame[1]},width:{frame[2]},height:{frame[3]}}};" if frame else ""
    out = kwin_script(log, f"workspace.windowList().forEach(function(w){{ if (w.caption.indexOf('{caption}')>=0) {{ {set_frame} var g=w.clientGeometry; print('UI4ME_WIN|'+g.x+'|'+g.y+'|'+g.width+'|'+g.height); }} }});")
    if not out:
        return None
    x, y, w, h = (float(v) for v in out[-1].split("|")[:4])
    return x, y, w, h


def close_window(log: Path, caption: str) -> None:
    kwin_script(log, f"workspace.windowList().forEach(function(w){{ if (w.caption.indexOf('{caption}')>=0) w.closeWindow(); }});")


def snake(key: str) -> str:
    """PowerShell records use PascalCase (MaxY); Python dicts use snake_case (max_y)."""
    return "".join(("_" + c.lower()) if c.isupper() and i else c.lower() for i, c in enumerate(key))


def norm(value):
    if isinstance(value, dict):
        return {snake(k): norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [norm(v) for v in value]
    return value


def read_state(path: Path) -> dict:
    try:
        return norm(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return {}


def wait(path: Path, predicate, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    state = {}
    while time.monotonic() < deadline:
        state = read_state(path)
        try:
            if state and predicate(state):
                return state
        except (KeyError, TypeError, IndexError):
            pass
        time.sleep(0.1)
    raise TimeoutError(f"condition not reached; last state keys {sorted(state)}")


def journey(out: Path, command: list[str]) -> dict:
    cases: list[dict] = []
    state_path = out / "state.json"
    command = [c.replace("{state}", str(state_path)) for c in command]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-journey-{os.getpid()}"
    log = runtime / f"{sock}.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280", "--height", "900"],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    app = None
    fake = None
    try:
        for _ in range(100):
            if (runtime / sock).exists():
                break
            time.sleep(0.1)
        time.sleep(1.0)
        env["WAYLAND_DISPLAY"] = sock
        os.environ["WAYLAND_DISPLAY"] = sock
        use_virtual_display(sock)
        app_log = (out / "app.log").open("w")
        app = subprocess.Popen(command, env=env, stdout=app_log, stderr=subprocess.STDOUT)
        fake = Input(build_fakeinput(out))

        def case(name, action):
            started = time.monotonic()
            try:
                detail = action()
                cases.append({"id": name, "status": "passed", "details": detail, "seconds": round(time.monotonic() - started, 2)})
            except Exception as error:  # record and continue: later cases report independently
                cases.append({"id": name, "status": "failed", "details": f"{type(error).__name__}: {error}"})

        geo: dict = {}

        def shown():
            s = wait(state_path, lambda s: s["rects"]["compose"], timeout=30)
            for _ in range(50):
                g = window_geometry(log, "UI4ME chat demo", (40, 40, 1000, 740))
                if g:
                    break
                time.sleep(0.2)
            if not g:
                raise RuntimeError("KWin does not list the demo window")
            time.sleep(0.5)
            geo["origin"] = window_geometry(log, "UI4ME chat demo")
            s = wait(state_path, lambda s: s["rects"]["log"]["width"] > 0)
            return {"client": geo["origin"], "compose": s["rects"]["compose"]}

        def at(s: dict, element: str, fx: float = 0.5, fy: float = 0.5, dx: float = 0, dy: float = 0) -> str:
            r = s["rects"][element]
            x0, y0 = geo["origin"][0], geo["origin"][1]
            return f"{x0 + r['x'] + r['width'] * fx + dx:.0f} {y0 + r['y'] + r['height'] * fy + dy:.0f}"

        def send_enter():
            s = read_state(state_path)
            fake(f"click {at(s, 'compose')}")
            fake("type hello core")
            fake(f"key {KEY['enter']}")
            s = wait(state_path, lambda s: s["sent"] == ["hello core"] and s["compose"] == "")
            return {"sent": s["sent"], "focus": s["focus"]}

        def shift_enter():
            fake("type line one")
            fake(f"kd {KEY['shift']}")
            fake(f"key {KEY['enter']}")
            fake(f"ku {KEY['shift']}")
            fake("type line two")
            fake(f"key {KEY['enter']}")
            s = wait(state_path, lambda s: len(s["sent"]) == 2)
            if s["sent"][1] != "line one\nline two":
                raise AssertionError(f"Shift+Enter: {s['sent'][1]!r}")
            return {"sent": s["sent"][1]}

        def search_persists():
            s = read_state(state_path)
            fake(f"click {at(s, 'search')}")
            fake("type worker")
            s = wait(state_path, lambda s: s["search"] == "worker")
            lines = s["lines"]
            time.sleep(1.5)
            s = wait(state_path, lambda s: s["lines"] > lines + 10)
            if s["search"] != "worker" or s["focus"] != ["search"]:
                raise AssertionError(f"search {s['search']!r} focus {s['focus']}")
            return {"search": s["search"], "focus": s["focus"], "lines_during": s["lines"] - lines}

        def drag_select():
            # Let both streamed replies finish so the conversation stops scrolling, then use a
            # state saved after that (rectangles must match what is on screen).
            # Streaming stops when the conversation's scroll extent stops growing across saves.
            last, stable_since = None, time.monotonic()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                cur = read_state(state_path).get("msgs_scroll", {}).get("max_y")
                if cur != last:
                    last, stable_since = cur, time.monotonic()
                elif time.monotonic() - stable_since > 2.5:
                    break
                time.sleep(0.2)
            # Bring the first message into view (a small window scrolls it away), then use fresh state.
            fake(f"move {at(read_state(state_path), 'msgs')}")
            for _ in range(10):
                fake("wheel -5")
            wait(state_path, lambda s: s["msgs_scroll"]["y"] == 0, timeout=10)
            before = read_state(state_path)["lines"]
            wait(state_path, lambda s: s["lines"] > before + 25, timeout=10)
            s = read_state(state_path)
            fake(f"move {at(s, 'm0', 0.0, 0.75, dx=12)}")
            fake("down")
            fake(f"move {at(s, 'm0', 0.5, 0.75)}")
            fake(f"move {at(s, 'm0', 0.98, 0.75)}")
            fake("up")
            s = wait(state_path, lambda s: len(s["selection"]) > 10)
            if not s["selection"].startswith("Hello") or "you" in s["selection"]:
                raise AssertionError(f"selection {s['selection']!r}")
            return {"selection": s["selection"]}

        def copy_button():
            s = read_state(state_path)
            selected = s["selection"]
            fake(f"click {at(s, 'copy')}")
            s = wait(state_path, lambda s: s["copied"] == selected and s["clipboard"] == selected)
            return {"copied": s["copied"], "os_clipboard": s["clipboard"]}

        def ctrl_c_and_paste():
            s = read_state(state_path)
            fake(f"click {at(s, 'm0', 0.0, 0.25, dx=12)}")  # collapse; then a double-click word
            time.sleep(0.6)
            fake(f"click {at(s, 'm0', 0.0, 0.25, dx=20)}")
            fake(f"click {at(s, 'm0', 0.0, 0.25, dx=20)}")
            s = wait(state_path, lambda s: s["selection"] == "assistant")
            fake(f"kd {KEY['ctrl']}")
            fake(f"key {KEY['c']}")
            fake(f"ku {KEY['ctrl']}")
            s = wait(state_path, lambda s: s["clipboard"] == "assistant")
            fake(f"click {at(s, 'compose')}")
            fake(f"kd {KEY['ctrl']}")
            fake(f"key {KEY['v']}")
            fake(f"ku {KEY['ctrl']}")
            s = wait(state_path, lambda s: s["compose"] == "assistant")
            fake(f"kd {KEY['ctrl']}")
            fake(f"key {KEY['a']}")
            fake(f"ku {KEY['ctrl']}")
            fake(f"key {KEY['backspace']}")
            wait(state_path, lambda s: s["compose"] == "")
            return {"os_clipboard": s["clipboard"], "pasted": s["compose"]}

        def wheel_scroll_away():
            s = read_state(state_path)
            fake(f"move {at(s, 'log')}")
            for _ in range(5):
                fake("wheel -5")
            s = wait(state_path, lambda s: s["log_scroll"]["y"] < s["log_scroll"]["max_y"] - 50, timeout=5)
            time.sleep(1.5)
            s = wait(state_path, lambda s: True)
            if s["log_scroll"]["y"] >= s["log_scroll"]["max_y"] - 50:
                raise AssertionError("follow yanked the reader back to the end")
            return {"log_scroll": s["log_scroll"]}

        def resize():
            s = read_state(state_path)
            before = s["rects"]["log"]["width"]
            window_geometry(log, "UI4ME chat demo", (40, 40, 1200, 800))
            s = wait(state_path, lambda s: s["resized"] and s["rects"]["log"]["width"] > before + 50)
            geo["origin"] = window_geometry(log, "UI4ME chat demo")
            return {"resized": s["resized"][-1], "log_width": [before, s["rects"]["log"]["width"]]}

        def close():
            close_window(log, "UI4ME chat demo")
            code = app.wait(timeout=15)
            s = read_state(state_path)
            if code != 0 or not s.get("exited") or not s.get("closed"):
                raise AssertionError(f"exit {code} state exited={s.get('exited')} closed={s.get('closed')}")
            return {"exit_code": code}

        case("J01_window_shown", shown)
        case("J02_type_enter_sends", send_enter)
        case("J03_shift_enter_newline", shift_enter)
        case("J04_search_field_survives_stream", search_persists)
        case("J05_drag_select_document_text", drag_select)
        case("J06_copy_button_os_clipboard", copy_button)
        case("J07_ctrl_c_then_ctrl_v_into_control", ctrl_c_and_paste)
        case("J08_wheel_scroll_away_stops_follow", wheel_scroll_away)
        case("J09_resize_relayout", resize)
        case("J10_close_exits_cleanly", close)
    finally:
        if fake:
            try:
                fake.close()
            except Exception:
                fake.p.kill()
        if app and app.poll() is None:
            app.terminate()
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()
        reap_private_bus()
        kwin.terminate()
        try:
            kwin.wait(timeout=10)
        except subprocess.TimeoutExpired:
            kwin.kill()
        if log.exists():
            shutil.copy(log, out / "kwin.log")
            log.unlink()
    statuses = {c["status"] for c in cases}
    return {"schema": 1, "kind": "desktop-journey", "environment": "kwin_wayland --virtual 1280x900 scale 1, org_kde_kwin_fake_input (automated, not a person)",
            "command": command, "status": "passed" if statuses == {"passed"} else "failed", "cases": cases}


def run_plain(out: Path, command: list[str]) -> int:
    """Run any command on a private virtual KWin (for probes that check themselves)."""
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-plain-{os.getpid()}"
    log = runtime / f"{sock}.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280", "--height", "900"],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if (runtime / sock).exists():
                break
            time.sleep(0.1)
        time.sleep(1.0)
        env["WAYLAND_DISPLAY"] = sock
        use_virtual_display(sock)
        with (out / "command.log").open("w") as output:
            return subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=float(os.environ.get("UI4ME_PLAIN_TIMEOUT", "1700"))).returncode
    finally:
        reap_private_bus()
        kwin.terminate()
        try:
            kwin.wait(timeout=10)
        except subprocess.TimeoutExpired:
            kwin.kill()
        if log.exists():
            shutil.copy(log, out / "kwin.log")
            log.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--plain", action="store_true", help="run COMMAND on the virtual KWin and return its exit code")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.inner:
        plain = ["--plain"] if args.plain else []
        env = isolated_environment()
        try:
            return subprocess.call(["dbus-run-session", "--", sys.executable, __file__, "--inner", *plain, "--out", str(args.out), "--", *command], env=env)
        finally:
            shutil.rmtree(env["XDG_RUNTIME_DIR"], ignore_errors=True)
    if args.plain:
        return run_plain(args.out.resolve(), command)
    result = journey(args.out.resolve(), command)
    (args.out / "journey.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in result["cases"]:
        print(f"{c['status']:7} {c['id']}  {json.dumps(c.get('details'), ensure_ascii=False)[:160]}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
