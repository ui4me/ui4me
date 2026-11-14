#!/usr/bin/env python3
"""Run a UI4ME app in the interactive Windows session and drive it with real RDP input.

    python3 tests/native/windows/rdp_driver.py --out DIR --name RUN [--setup-python WHEEL] -- ARGV...

Test tooling only; never shipped. Runs on the Linux workstation and needs:

* an ``xfreerdp3`` client on an X display (default ``:88``, ``UI4ME_RDP_DISPLAY``) that is
  logged on to the test user's desktop session, full screen at 1:1 scale; ``xdotool`` there
  produces genuine RDP keyboard/mouse input for Windows;
* the lab agent running *as the test user inside that session* (``F:\\ui4me\\lab``),
  reached through the administrator SSH relay. It launches the app in the session,
  observes windows/processes and relays files, so the app is a normal desktop process.

ARGV runs on Windows; ``{STAGE}``, ``{RUN}`` and ``{VENV}`` are replaced by Windows paths.
The app receives ``UI4ME_TEST_CHANNEL={RUN}`` and talks the same request/ack/results
protocol as the Linux driver (tests/native/channel.py, Channel.ps1). Evidence is automated
RDP input on a virtual display, not a person at a physical monitor.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DISPLAY = os.environ.get("UI4ME_RDP_DISPLAY", ":88")
OUT_DIR = Path(".")
ROOT = r"F:\ui4me\ui2"
REPO = Path(__file__).resolve().parents[3]
XKEYS = {"enter": "Return", "tab": "Tab", "escape": "Escape", "backspace": "BackSpace", "space": "space",
         "up": "Up", "down": "Down", "left": "Left", "right": "Right", "home": "Home", "end": "End",
         "delete": "Delete", "pageup": "Prior", "pagedown": "Next", "f2": "F2"}
XMODS = {"ctrl": "ctrl", "shift": "shift", "alt": "alt"}


class Agent:
    def __init__(self):
        self.p = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15", "administrator@omegaui",
             r"F:\ui4me\lab\venv\Scripts\python.exe -u F:\ui4me\lab\relay.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")

    def __call__(self, code: str):
        self.p.stdin.write(json.dumps({"exec": code}) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("agent relay closed")
        r = json.loads(line)
        if not r["ok"]:
            raise RuntimeError(r["error"] + "\n" + r.get("trace", ""))
        return r["result"]

    def put(self, local: Path, remote: str) -> None:
        data = base64.b64encode(local.read_bytes()).decode()
        self(f"p = Path(r'{remote}'); p.parent.mkdir(parents=True, exist_ok=True);"
             f" import base64; p.write_bytes(base64.b64decode({data!r})); result = p.stat().st_size")

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(10)
        except Exception:
            self.p.kill()


def xdo(*args):
    subprocess.run(["xdotool", *map(str, args)], env=dict(os.environ, DISPLAY=DISPLAY), check=True)


def click(x, y, button=1, double=False):
    xdo("mousemove", int(round(x)), int(round(y)))
    time.sleep(0.08)
    if double:
        xdo("click", "--repeat", "2", "--delay", "60", button)
    else:
        xdo("click", button)
    time.sleep(0.08)


def title_bar(win):
    fx, fy, fw, _ = win["frame"]
    return fx + fw / 2, fy + 12


def stage(agent: Agent, files: list[tuple[Path, str]]) -> None:
    for local, remote in files:
        agent.put(local, remote)


def stage_tree(agent: Agent, local_root: Path, remote_root: str, patterns=("*",)) -> int:
    count = 0
    for path in sorted(local_root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",):
            rel = path.relative_to(local_root).as_posix().replace("/", "\\")
            agent.put(path, remote_root + "\\" + rel)
            count += 1
    return count


def setup_python(agent: Agent, wheel: Path) -> dict:
    remote_wheel = ROOT + r"\wheels" + "\\" + wheel.name
    agent.put(wheel, remote_wheel)
    return agent(f"""
import subprocess, sys, shutil
venv = Path(r'{ROOT}\\venv')
base = sys._base_executable.replace('pythonw.exe', 'python.exe')
if venv.exists():  # every qualification run starts from a fresh environment
    shutil.rmtree(venv)
subprocess.run([base, '-m', 'venv', str(venv)], check=True, capture_output=True, timeout=300)
py = str(venv / 'Scripts' / 'python.exe')
r1 = subprocess.run([py, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', 'ui4me-core>=1.0.1,<2'], capture_output=True, text=True, timeout=900)
r2 = subprocess.run([py, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', '--force-reinstall', '--no-deps', r'{remote_wheel}'], capture_output=True, text=True, timeout=900)
r3 = subprocess.run([py, '-c', 'import ui4me, ui4me_core, sys; print(ui4me.__version__, ui4me_core.__version__, ui4me.__file__, sys.version)'], capture_output=True, text=True, timeout=120)
result = {{'core': r1.returncode, 'core_err': r1.stderr[-800:], 'ui': r2.returncode, 'ui_err': r2.stderr[-800:], 'import': r3.stdout.strip() or r3.stderr[-800:],
          'wheel_sha256': w.sha256(r'{remote_wheel}')}}
""")


def perform(agent: Agent, request: dict, title: str | None) -> dict:
    action = request["action"]
    caption = request.get("window") or title
    reply: dict = {}

    def win():
        return agent(f"result = w.window({caption!r}, timeout=10)")

    def on_screen():
        # Windows cascades new windows; after many runs a tall window can extend below the
        # work area (taskbar), where clicks would miss. Move it fully into the work area first.
        wnd = win()
        x, y, width, height = wnd["rect"]
        moved = agent("import ctypes, ctypes.wintypes as wt\n"
                      "r = wt.RECT(); ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)\n"
                      f"x, y, wd, ht = {x}, {y}, {width}, {height}\n"
                      "nx = min(max(x, r.left), max(r.left, r.right - wd)); ny = min(max(y, r.top), max(r.top, r.bottom - ht))\n"
                      f"result = None if (nx, ny) == (x, y) else ctypes.windll.user32.SetWindowPos({wnd['hwnd']}, 0, nx, ny, 0, 0, 0x0001 | 0x0004)")
        if moved:
            time.sleep(0.4)
            wnd = win()
        return wnd

    if action in ("click", "dblclick", "rclick", "move"):
        wnd = on_screen()
        x, y = wnd["cx"] + float(request["x"]), wnd["cy"] + float(request["y"])
        if action == "move":
            xdo("mousemove", int(round(x)), int(round(y)))
        else:
            click(x, y, 3 if action == "rclick" else 1, double=action == "dblclick")
        reply["at"] = [x, y]
    elif action == "drag":
        wnd = win()
        x0, y0 = wnd["cx"] + request["x"], wnd["cy"] + request["y"]
        x1, y1 = wnd["cx"] + request["x2"], wnd["cy"] + request["y2"]
        xdo("mousemove", int(x0), int(y0)); time.sleep(0.1)
        xdo("mousedown", 1); time.sleep(0.1)
        for i in range(1, 16):
            xdo("mousemove", int(x0 + (x1 - x0) * i / 15), int(y0 + (y1 - y0) * i / 15)); time.sleep(0.02)
        xdo("mouseup", 1)
    elif action == "type":
        xdo("type", "--delay", "35", request["text"])
    elif action == "key":
        combo = "+".join([XMODS[m] for m in request.get("mods", [])] + [XKEYS.get(request["key"], request["key"])])
        xdo("key", combo)
    elif action == "wheel":
        button = 5 if float(request["dy"]) > 0 else 4
        for _ in range(max(1, int(abs(float(request["dy"])) / 15))):
            xdo("click", button)
    elif action in ("native-close", "activate"):
        wnd = win()
        click(*title_bar(wnd))
        if action == "native-close":
            time.sleep(0.2)
            xdo("key", "alt+F4")
    elif action == "windows":
        reply["windows"] = [dict(caption=x["title"], pid=x["pid"]) for x in agent("result = w.windows()") if x["title"]]
    elif action == "wait-window":
        try:
            reply["window"] = agent(f"result = w.window({caption!r}, timeout={float(request.get('timeout', 15))})")
        except RuntimeError:
            reply["window"] = None
    elif action == "wait-window-gone":
        gone = False
        for _ in range(int(float(request.get("timeout", 15)) / 0.5)):
            if not agent(f"result = w.windows({caption!r})"):
                gone = True
                break
            time.sleep(0.5)
        reply["gone"] = gone
    elif action == "dialog-key":
        try:
            d = agent(f"result = w.window({caption!r}, timeout={float(request.get('timeout', 20))})")
        except RuntimeError:
            d = None
        reply["window"] = d
        if d:
            time.sleep(1.0)
            click(*title_bar(d))
            time.sleep(0.3)
            xdo("key", XKEYS[request["key"]])
    elif action == "sleep":
        time.sleep(float(request.get("seconds", 0.2)))
    elif action == "input-language":
        # Switch the target window's input language (e.g. "00000804" = Chinese (PRC), with
        # Microsoft Pinyin installed for the test user) the way the language bar does.
        wnd = win()
        reply["hkl"] = agent(f"import ctypes; u = ctypes.windll.user32; u.LoadKeyboardLayoutW.restype = ctypes.c_void_p;"
                             f" hkl = u.LoadKeyboardLayoutW({request['layout']!r}, 1);"
                             f" u.PostMessageW({wnd['hwnd']}, 0x0050, 0, ctypes.c_void_p(hkl)); result = hex(hkl or 0)")
    elif action == "screenshot":
        # Captured inside the interactive session (PIL ImageGrab), cropped to the window
        # frame, then copied back next to the run's evidence (OUT_DIR).
        name = Path(request.get("name", "screenshot.png")).name
        wnd = win()
        # Move the whole window on screen (SWP_NOSIZE|SWP_NOZORDER), focus it, re-read its frame.
        agent(f"import ctypes; u = ctypes.windll.user32; u.SetWindowPos({wnd['hwnd']}, 0, 0, 0, 0, 0, 0x0001 | 0x0004);"
              f" u.SetForegroundWindow({wnd['hwnd']}); result = None")
        time.sleep(0.8)
        wnd = win()
        data = agent(f"import base64\npath = w.screenshot({name!r}, bbox={list(wnd['frame'])!r})\n"
                     "result = base64.b64encode(Path(path).read_bytes()).decode()")
        target = OUT_DIR / name
        target.write_bytes(base64.b64decode(data))
        reply["path"] = str(target)
    else:
        raise ValueError(f"unknown action {action}")
    time.sleep(float(request.get("settle", 0.15)))
    return reply


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--setup-python", type=Path, help="wheel to install into the session venv first")
    ap.add_argument("--stage-module", action="store_true", help="stage powershell/Ui4me for PSModulePath")
    ap.add_argument("--stage-examples", action="store_true", help="stage examples/ under {STAGE}\\examples")
    ap.add_argument("--stage-module-zip", type=Path, help="stage the built UI4ME-X.zip artifact instead")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for the app")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    argv = a.command[1:] if a.command[:1] == ["--"] else a.command
    out: Path = a.out
    out.mkdir(parents=True, exist_ok=True)
    global OUT_DIR
    OUT_DIR = out
    agent = Agent()
    run_dir = ROOT + r"\run" + "\\" + a.name
    harness: dict = {"name": a.name, "argv": argv, "observations": [], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    code = 1
    pid = None
    try:
        harness["machine"] = agent("import platform, getpass; result = {'node': platform.node(), 'user': getpass.getuser(),"
                                   " 'win': platform.version(), 'session': w.session_id()}")
        harness["staged_tests"] = stage_tree(agent, REPO / "tests" / "native", ROOT + r"\stage\tests\native")
        if a.stage_examples:
            harness["staged_examples"] = stage_tree(agent, REPO / "examples", ROOT + r"\stage\examples")
        if a.stage_module:
            harness["staged_module"] = stage_tree(agent, REPO / "powershell" / "Ui4me", ROOT + r"\stage\psmodules\Ui4me")
        if a.stage_module_zip:
            remote = ROOT + r"\artifacts" + "\\" + a.stage_module_zip.name
            agent.put(a.stage_module_zip, remote)
            harness["staged_module_zip"] = agent(f"""
import shutil, zipfile
target = Path(r'{ROOT}\\stage\\psmodules')
if (target / 'Ui4me').exists(): shutil.rmtree(target / 'Ui4me')
target.mkdir(parents=True, exist_ok=True)
zipfile.ZipFile(r'{remote}').extractall(target)
result = {{'sha256': w.sha256(r'{remote}'), 'files': sorted(str(p.relative_to(target)) for p in (target / 'Ui4me').rglob('*') if p.is_file())}}
""")
        if a.setup_python:
            harness["python_setup"] = setup_python(agent, a.setup_python)
            if harness["python_setup"]["core"] or harness["python_setup"]["ui"]:
                raise RuntimeError(f"python setup failed: {harness['python_setup']}")
        subst = {"{STAGE}": ROOT + r"\stage", "{RUN}": run_dir, "{VENV}": ROOT + r"\venv"}
        win_argv = []
        for part in argv:
            for k, v in subst.items():
                part = part.replace(k, v)
            win_argv.append(part)
        env = {"UI4ME_TEST_CHANNEL": run_dir}
        for item in a.env:
            k, v = item.split("=", 1)
            for kk, vv in subst.items():
                v = v.replace(kk, vv)
            env[k] = v
        pid = agent(f"""
import shutil
d = Path(r'{run_dir}')
if d.exists(): shutil.rmtree(d)
d.mkdir(parents=True)
env = {env!r}
if 'PSModulePath+' in env:
    env['PSModulePath'] = env.pop('PSModulePath+') + ';' + os.environ.get('PSModulePath', '')
import subprocess
# Windows env names are case-insensitive and os.environ upper-cases them; merge the same
# way so no name appears twice (.NET Framework / PowerShell 5.1 fails on duplicates).
e = os.environ.copy(); e.update({{k.upper(): v for k, v in env.items()}})
proc = subprocess.Popen({win_argv!r}, cwd=str(d), env=e, stdout=open(d / 'app.log', 'ab'), stderr=subprocess.STDOUT,
                        creationflags=0x00000200)
if not hasattr(w, 'ui2_procs'): w.ui2_procs = {{}}
w.ui2_procs[proc.pid] = proc
result = proc.pid
""")
        harness["pid"] = pid
        seen_tree: dict = {}
        done: set = set()
        t0 = time.time()
        while time.time() - t0 < a.timeout:
            state = agent(f"""
import psutil
d = Path(r'{run_dir}')
req = (d / 'requests.jsonl').read_text(encoding='utf-8-sig').splitlines() if (d / 'requests.jsonl').exists() else []
alive = psutil.pid_exists({pid}) and psutil.Process({pid}).status() != 'zombie'
result = {{'requests': req, 'alive': alive, 'tree': w.tree({pid}) if alive else None}}
""")
            for proc in state["tree"] or []:
                seen_tree[proc["pid"]] = proc["name"]
            for line in state["requests"]:
                try:
                    request = json.loads(line)
                except ValueError:
                    continue
                if request.get("id") in done:
                    continue
                done.add(request["id"])
                record = {"ack": request["id"]}
                try:
                    record.update(perform(agent, request, None))
                    record["ok"] = True
                except Exception as error:
                    record.update(ok=False, error=f"{type(error).__name__}: {error}")
                harness["observations"].append({"request": request, "ack": record})
                agent(f"""
with open(Path(r'{run_dir}') / 'acks.jsonl', 'a', encoding='utf-8') as f:
    f.write({json.dumps(record, ensure_ascii=False)!r} + '\\n')
result = True
""")
            if not state["alive"]:
                break
            time.sleep(0.2)
        else:
            harness["timeout"] = True
        final = agent(f"""
import psutil
code = None
try:
    code = w.ui2_procs.pop({pid}).wait(20)
except Exception as error:
    code = repr(error)
time.sleep(1)
left = [{{'pid': p, 'name': n}} for p, n in {seen_tree!r}.items() if psutil.pid_exists(p)]
d = Path(r'{run_dir}')
def rd(name):
    p = d / name
    return p.read_text(encoding='utf-8-sig', errors='replace') if p.exists() else ''
result = {{'exit': code, 'leftovers': left, 'results': rd('results.jsonl'), 'log': rd('app.log')[-20000:]}}
""")
        if harness.get("timeout"):
            agent(f"import psutil\nfor c in (w.tree({pid}) or []):\n    psutil.Process(c['pid']).kill()\npsutil.Process({pid}).kill()\nresult=True")
        (out / "results.jsonl").write_text(final["results"], encoding="utf-8")
        (out / "app.log").write_text(final["log"], encoding="utf-8")
        harness["app_exit"] = final["exit"]
        harness["leftover_processes"] = final["leftovers"]
        harness["process_tree_seen"] = seen_tree
        records = [json.loads(l) for l in final["results"].splitlines() if l.strip()]
        checks = [r for r in records if r.get("kind") == "check"]
        harness["checks"] = len(checks)
        harness["failed"] = [c for c in checks if c.get("status") != "passed"]
        harness["fatal"] = [r for r in records if r.get("kind") == "fatal"]
        ok = (not harness.get("timeout") and final["exit"] == 0 and checks and not harness["failed"]
              and not harness["fatal"] and not final["leftovers"] and any(r.get("kind") == "done" for r in records))
        harness["status"] = "passed" if ok else "failed"
        code = 0 if ok else 1
        for c in checks:
            print(f"{c['status']:7} {c['name']}  {str(c.get('detail', ''))[:140]}")
        for f in harness["fatal"]:
            print("FATAL", f.get("message", "")[:2000])
    except Exception as error:
        harness["status"] = "failed"
        harness["error"] = f"{type(error).__name__}: {error}"
        print("driver error:", harness["error"])
    finally:
        (out / "harness.json").write_text(json.dumps(harness, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        agent.close()
    print(f"harness: {harness.get('status')} app_exit={harness.get('app_exit')} checks={harness.get('checks')} "
          f"failed={len(harness.get('failed', []))} leftovers={len(harness.get('leftover_processes', []))}"
          + (" TIMEOUT" if harness.get("timeout") else ""))
    return code


if __name__ == "__main__":
    sys.exit(main())
