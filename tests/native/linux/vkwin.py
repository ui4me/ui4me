#!/usr/bin/env python3
"""Run a UI4ME app on a private virtual KWin and drive it with real compositor input.

    python3 tests/native/linux/vkwin.py --out DIR [--timeout S] -- COMMAND ...

Test tooling only; never shipped. A private D-Bus session, a private
``XDG_RUNTIME_DIR`` and ``kwin_wayland --virtual`` are started, so nothing is
drawn on, or typed into, the person's real desktop. Input goes through KWin's
``org_kde_kwin_fake_input`` (enabled by ``KWIN_WAYLAND_NO_PERMISSION_CHECKS``):
the compositor delivers it to the focused Wayland surface exactly like device
input, then the native Core host turns it into DOM events.

COMMAND (usually ``ui4me-run app.py`` or ``ui4me-host run --app app.toml``)
receives ``UI4ME_TEST_CHANNEL=DIR``. The app asks for input by appending
``{"kind": "request", "id": N, "action": ...}`` lines to DIR/requests.jsonl and
waits for the matching line in DIR/acks.jsonl (see ``channel.py``/``Channel.ps1``).
It records its own verdicts as ``{"kind": "check", ...}`` lines in
DIR/results.jsonl. This driver writes DIR/harness.json and exits nonzero if a
check failed, the command failed, timed out, or left processes behind.

Evidence produced here is *automated compositor input on a virtual output*, not
a person at a physical monitor.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = {"enter": 28, "tab": 15, "escape": 1, "backspace": 14, "space": 57, "shift": 42, "ctrl": 29,
        "alt": 56, "up": 103, "down": 108, "left": 105, "right": 106, "home": 102, "end": 107,
        "delete": 111, "pageup": 104, "pagedown": 109, "f2": 60}
for _i, _c in enumerate("qwertyuiop"):
    KEYS[_c] = 16 + _i
for _i, _c in enumerate("asdfghjkl"):
    KEYS[_c] = 30 + _i
for _i, _c in enumerate("zxcvbnm"):
    KEYS[_c] = 44 + _i


def isolated_environment() -> dict:
    env = dict(os.environ)
    for name in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS",
                 "XDG_ACTIVATION_TOKEN", "DESKTOP_STARTUP_ID"):
        env.pop(name, None)
    env["XDG_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="ui4me-vkwin-")
    os.chmod(env["XDG_RUNTIME_DIR"], 0o700)
    return env


def private_bus_processes(only: tuple[str, ...] = ()) -> list[int]:
    bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not bus:
        return []
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in (os.getpid(), os.getppid()):
            continue
        try:
            environ = (entry / "environ").read_bytes().split(b"\0")
            cmdline = (entry / "cmdline").read_bytes().decode(errors="replace")
        except OSError:
            continue
        if only and not any(o in cmdline for o in only):
            continue
        if f"DBUS_SESSION_BUS_ADDRESS={bus}".encode() in environ:
            found.append(int(entry.name))
    return found


def reap(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def build_fakeinput(out: Path) -> Path:
    binary = out / "fakeinput"
    with tempfile.TemporaryDirectory() as t:
        xml = HERE / "fake-input.xml"
        subprocess.run(["wayland-scanner", "client-header", xml, f"{t}/fi.h"], check=True)
        subprocess.run(["wayland-scanner", "private-code", xml, f"{t}/fi.c"], check=True)
        src = (HERE / "fakeinput.c").read_text().replace('"fake-input-client-protocol.h"', '"fi.h"')
        Path(t, "main.c").write_text(src)
        subprocess.run(["gcc", "-O1", f"-I{t}", "-o", binary, f"{t}/main.c", f"{t}/fi.c", "-lwayland-client"],
                       check=True)
    return binary


class Input:
    def __init__(self, binary: Path, env: dict):
        self.p = subprocess.Popen([binary, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)

    def __call__(self, line: str) -> None:
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        if self.p.stdout.readline().strip() != "ok":
            raise RuntimeError(f"fakeinput failed on {line!r}")

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class KWin:
    def __init__(self, log: Path):
        self.log = log

    def script(self, body: str) -> list[str]:
        fd, name = tempfile.mkstemp(suffix=".js")
        os.close(fd)
        js = Path(name)
        js.write_text(body, encoding="utf-8")
        before = self.log.read_text(errors="replace").count("\n")
        tag = f"ui4me{os.getpid()}{time.monotonic_ns()}"
        subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(js), tag],
                       check=True, capture_output=True, timeout=10)
        subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"], check=True,
                       capture_output=True, timeout=10)
        time.sleep(0.35)
        subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", tag],
                       capture_output=True, timeout=10)
        js.unlink()
        lines = self.log.read_text(errors="replace").splitlines()[before:]
        return [line.split("UI4ME_WIN|", 1)[1] for line in lines if "UI4ME_WIN|" in line]

    def windows(self) -> list[dict]:
        out = self.script(
            "var r=[]; workspace.windowList().forEach(function(w){ if (!w.normalWindow && !w.dialog) return;"
            " var g=w.clientGeometry; r.push({caption:w.caption, pid:w.pid, x:g.x, y:g.y, w:g.width, h:g.height,"
            " active:w.active, minimized:w.minimized, dialog:w.dialog, modal:w.modal}); });"
            " print('UI4ME_WIN|'+JSON.stringify(r));")
        return json.loads(out[-1]) if out else []

    def find(self, caption: str) -> dict | None:
        for w in self.windows():
            if caption in w["caption"]:
                return w
        return None

    def each(self, caption: str, action: str) -> None:
        self.script(f"workspace.windowList().forEach(function(w){{ if (w.caption.indexOf({json.dumps(caption)})>=0)"
                    f" {{ {action} }} }});")

    def activate(self, caption: str) -> None:
        self.each(caption, "workspace.activeWindow = w;")

    def close(self, caption: str) -> None:
        self.each(caption, "w.closeWindow();")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass  # a partially written last line; read again next poll
    return out


def wait_for(pred, timeout: float, step: float = 0.2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = pred()
        if value:
            return value
        time.sleep(step)
    return None


def perform(request: dict, fake: Input, kwin: KWin, out: Path) -> dict:
    action = request["action"]
    caption = request.get("window")
    result: dict = {}

    def origin() -> tuple[float, float]:
        w = wait_for(lambda: kwin.find(caption), 10)
        if not w:
            raise RuntimeError(f"window {caption!r} not found")
        return w["x"], w["y"]

    if action in ("click", "dblclick", "rclick", "move"):
        kwin.activate(caption)
        time.sleep(0.15)
        ox, oy = origin()
        x, y = ox + float(request["x"]), oy + float(request["y"])
        fake(f"move {x:.1f} {y:.1f}")
        time.sleep(0.05)
        if action == "click":
            fake("down")
            time.sleep(0.03)
            fake("up")
        elif action == "dblclick":
            for _ in range(2):
                fake("down")
                time.sleep(0.02)
                fake("up")
                time.sleep(0.06)
        result["at"] = [x, y]
    elif action == "drag":
        kwin.activate(caption)
        ox, oy = origin()
        x0, y0 = ox + request["x"], oy + request["y"]
        x1, y1 = ox + request["x2"], oy + request["y2"]
        fake(f"move {x0:.1f} {y0:.1f}")
        fake("down")
        for i in range(1, 16):
            fake(f"move {x0 + (x1 - x0) * i / 15:.1f} {y0 + (y1 - y0) * i / 15:.1f}")
            time.sleep(0.015)
        fake("up")
    elif action == "type":
        fake("type " + request["text"])
    elif action == "key":
        mods = [KEYS[m] for m in request.get("mods", [])]
        for m in mods:
            fake(f"kd {m}")
        fake(f"key {KEYS[request['key']]}")
        for m in reversed(mods):
            fake(f"ku {m}")
    elif action == "wheel":
        fake(f"wheel {float(request['dy'])}")
    elif action == "native-close":
        kwin.close(caption)
    elif action == "activate":
        kwin.activate(caption)
    elif action == "windows":
        result["windows"] = kwin.windows()
    elif action == "wait-window":
        w = wait_for(lambda: kwin.find(caption), float(request.get("timeout", 15)))
        result["window"] = w
    elif action == "dialog-key":
        # Wait for a (native) dialog, focus it and press a key, e.g. Enter to accept.
        w = wait_for(lambda: kwin.find(caption), float(request.get("timeout", 20)))
        result["window"] = w
        if w:
            time.sleep(0.8)
            kwin.activate(caption)
            time.sleep(0.3)
            fake(f"key {KEYS[request['key']]}")
    elif action == "wait-window-gone":
        result["gone"] = wait_for(lambda: kwin.find(caption) is None, float(request.get("timeout", 15))) is not None
    elif action == "screenshot":
        # Captured by spectacle inside the private session (virtual output only).
        target = out / Path(request.get("name", "screenshot.png")).name
        if caption:
            kwin.activate(caption)
            time.sleep(0.4)
        mode = "--activewindow" if request.get("window_only", True) else "--fullscreen"
        proc = subprocess.run(["spectacle", "--background", "--nonotify", mode, "--output", str(target)],
                              capture_output=True, text=True, timeout=30, env=dict(os.environ))
        result["path"] = str(target) if target.exists() else None
        result["rc"] = proc.returncode
        if not target.exists():
            result["error"] = (proc.stderr or proc.stdout)[-500:]
    elif action == "input-language":
        result["skipped"] = "Linux: the input method (fcitx5, --ime) is already active"
    elif action == "sleep":
        time.sleep(float(request.get("seconds", 0.2)))
    else:
        raise ValueError(f"unknown action {action}")
    time.sleep(float(request.get("settle", 0.15)))
    return result


def inner(args) -> int:
    out: Path = args.out
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = "wayland-ui4me-test"
    klog = out / "kwin.log"
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1")
    # Activated services (portals, file chooser) must only ever see the virtual display.
    subprocess.run(["dbus-update-activation-environment", f"WAYLAND_DISPLAY={sock}", "QT_QPA_PLATFORM=wayland",
                    "XDG_CURRENT_DESKTOP=KDE"], check=True, capture_output=True)
    kwin_cmd = ["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width",
                str(args.width), "--height", str(args.height)]
    kwin_env = dict(env)
    if args.ime:
        # A real input method (fcitx5 + pinyin) that KWin starts and connects through
        # input-method-v1; the app receives composition via text-input like on a desktop.
        # Private profile: pinyin active by default, nothing read from the person's config.
        config = Path(os.environ["XDG_RUNTIME_DIR"]) / "ime-config"
        (config / "fcitx5" / "conf").mkdir(parents=True, exist_ok=True)
        (config / "fcitx5" / "profile").write_text(
            "[Groups/0]\nName=Default\nDefault Layout=us\nDefaultIM=pinyin\n\n"
            "[Groups/0/Items/0]\nName=keyboard-us\nLayout=\n\n[Groups/0/Items/1]\nName=pinyin\nLayout=\n\n"
            "[GroupOrder]\n0=Default\n", encoding="utf-8")
        (config / "fcitx5" / "config").write_text("[Behavior]\nActiveByDefault=True\nShareInputState=All\n",
                                                  encoding="utf-8")
        (config / "fcitx5" / "conf" / "pinyin.conf").write_text("CloudPinyinEnabled=False\n", encoding="utf-8")
        kwin_env["XDG_CONFIG_HOME"] = str(config)
        kwin_cmd += ["--inputmethod", shutil.which(args.ime) or args.ime]
    kwin_proc = subprocess.Popen(kwin_cmd, env=kwin_env, stdout=klog.open("w"), stderr=subprocess.STDOUT)
    harness: dict = {"command": args.command, "machine": platform.node(), "kernel": platform.release(),
                     "kwin": args.kwin_version, "supervision": "unsupervised (UI4ME_ALLOW_UNSUPERVISED=1)",
                     "observations": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    app = None
    fake = None
    code = 1
    try:
        if not wait_for(lambda: (runtime / sock).exists(), 15, 0.1):
            raise RuntimeError("virtual KWin did not start")
        time.sleep(0.8)
        env["WAYLAND_DISPLAY"] = sock
        os.environ["WAYLAND_DISPLAY"] = sock
        subprocess.run(["dbus-update-activation-environment", f"WAYLAND_DISPLAY={sock}", "QT_QPA_PLATFORM=wayland",
                        "XDG_CURRENT_DESKTOP=KDE"], check=True, capture_output=True)
        reap(private_bus_processes(("xdg-desktop-portal", "kioworker")))
        kwin = KWin(klog)
        fake = Input(build_fakeinput(out), env)
        # The private bus has no systemd user manager, so the host's systemd-run
        # containment cannot start here. Core documents --allow-unsupervised /
        # UI4ME_ALLOW_UNSUPERVISED as its explicit diagnostic mode for this case.
        app_env = dict(env, UI4ME_TEST_CHANNEL=str(out), UI4ME_ALLOW_UNSUPERVISED="1")
        app_env.pop("KWIN_WAYLAND_NO_PERMISSION_CHECKS", None)
        t0 = time.monotonic()
        app = subprocess.Popen(args.command, env=app_env, stdout=(out / "app.log").open("w"),
                               stderr=subprocess.STDOUT, start_new_session=True)
        harness["app_pid"] = app.pid
        done: set = set()
        while app.poll() is None and time.monotonic() - t0 < args.timeout:
            for request in read_jsonl(out / "requests.jsonl"):
                rid = request.get("id")
                if rid in done:
                    continue
                done.add(rid)
                record = {"ack": rid}
                try:
                    record.update(perform(request, fake, kwin, out))
                    record["ok"] = True
                except Exception as error:
                    record.update(ok=False, error=f"{type(error).__name__}: {error}")
                harness["observations"].append({"request": request, "ack": record})
                with (out / "acks.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(0.05)
        if app.poll() is None:
            harness["timeout"] = True
            os.killpg(app.pid, signal.SIGTERM)
            try:
                app.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(app.pid, signal.SIGKILL)
        harness["app_exit"] = app.wait(10)
        harness["seconds"] = round(time.monotonic() - t0, 2)
        time.sleep(0.5)
        # Processes of the app's session (host + backend) must all have ended.
        leftovers = []
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                try:
                    if os.getsid(int(entry.name)) == app.pid:
                        leftovers.append({"pid": int(entry.name),
                                          "cmd": (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode()[:200]})
                except OSError:
                    pass
        harness["leftover_processes"] = leftovers
        if leftovers:
            os.killpg(app.pid, signal.SIGKILL)
        harness["windows_after_exit"] = kwin.windows()
        checks = [r for r in read_jsonl(out / "results.jsonl") if r.get("kind") == "check"]
        harness["checks"] = len(checks)
        harness["failed"] = [c for c in checks if c.get("status") != "passed"]
        fatal = [r for r in read_jsonl(out / "results.jsonl") if r.get("kind") == "fatal"]
        harness["fatal"] = fatal
        ok = (not harness.get("timeout") and harness["app_exit"] == 0 and not harness["failed"] and not fatal
              and not leftovers and checks and any(r.get("kind") == "done" for r in read_jsonl(out / "results.jsonl")))
        harness["status"] = "passed" if ok else "failed"
        code = 0 if ok else 1
    except Exception as error:
        harness["status"] = "failed"
        harness["error"] = f"{type(error).__name__}: {error}"
    finally:
        if fake is not None:
            fake.close()
        if app is not None and app.poll() is None:
            os.killpg(app.pid, signal.SIGKILL)
        kwin_proc.terminate()
        try:
            kwin_proc.wait(10)
        except subprocess.TimeoutExpired:
            kwin_proc.kill()
        reap(private_bus_processes())
        (out / "harness.json").write_text(json.dumps(harness, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in read_jsonl(out / "results.jsonl"):
        if c.get("kind") == "check":
            print(f"{c['status']:7} {c['name']}  {str(c.get('detail', ''))[:140]}")
    print(f"harness: {harness['status']} app_exit={harness.get('app_exit')} checks={harness.get('checks')} "
          f"failed={len(harness.get('failed', []))} leftovers={len(harness.get('leftover_processes', []))}"
          + (f" error={harness['error']}" if harness.get("error") else "")
          + (" TIMEOUT" if harness.get("timeout") else ""))
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--ime", default="", help="input method KWin starts, e.g. fcitx5 (pinyin active)")
    ap.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--kwin-version", default="", help=argparse.SUPPRESS)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    args.command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.command:
        ap.error("missing COMMAND")
    args.out = args.out.resolve()
    if args.inner:
        return inner(args)
    if args.out.exists():
        for name in ("requests.jsonl", "acks.jsonl", "results.jsonl", "harness.json", "app.log"):
            (args.out / name).unlink(missing_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    env = isolated_environment()
    kwin_version = subprocess.run(["kwin_wayland", "--version"], capture_output=True, text=True,
                                  env={"PATH": os.environ["PATH"]}).stdout.strip()
    try:
        bus_log = (args.out / "session-bus.log").open("w")
        return subprocess.call(stderr=bus_log, args=["dbus-run-session", "--", sys.executable, __file__, "--inner", "--out", str(args.out),
                                "--kwin-version", kwin_version,
                                "--timeout", str(args.timeout), "--width", str(args.width), "--height",
                                str(args.height), *(["--ime", args.ime] if args.ime else []),
                                "--", *args.command], env=env)
    finally:
        shutil.rmtree(env["XDG_RUNTIME_DIR"], ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
