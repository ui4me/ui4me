"""Screen-reader journey with NVDA (Core 1.0 F1108). Run INSIDE the interactive Windows session:

    python nvda_journey.py --nvda C:\\path\\to\\nvda-portable\\nvda.exe --out nvda.json

Starts a portable NVDA with a fresh configuration (no welcome dialog, the silent synthesizer, the
speech it would say logged at IO level), opens a UI4ME window with labelled controls, moves the
focus and operates the controls with real key presses (SendInput), and checks what NVDA spoke:
the names, roles and states that reach a screen reader through UI Automation. NVDA quits at the
end. Automated keystrokes; the speech is NVDA's, not a person's judgement of usability.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from ui4me import App

user32 = ctypes.WinDLL("user32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def key(vk: int, up: bool = False) -> None:
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, 0, 2 if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    time.sleep(0.04)


def press(*vks: int) -> None:
    for v in vks:
        key(v)
    for v in reversed(vks):
        key(v, True)
    time.sleep(0.9)  # NVDA speaks after the focus event


VK_TAB, VK_SPACE, VK_SHIFT = 0x09, 0x20, 0x10

HTML = """<style>body{font:18px sans-serif;padding:16px} label{display:block;margin:8px 0}</style>
<h1>Order form</h1>
<label for=name>Customer name</label><input id=name value="Ada">
<label><input type=checkbox id=sub> Subscribe to news</label>
<label for=qty>Quantity</label><input id=qty type=number value=2 min=1 max=9>
<button id=send>Send order</button>
<div id=notes contenteditable aria-label="Order notes">Deliver after five</div>"""

INI = """[general]
	showWelcomeDialogAtStartup = False
	language = en
[update]
	autoCheck = False
	startupNotification = False
[speech]
	synth = silence
[keyboard]
	speakTypedCharacters = False
	speakTypedWords = False
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nvda", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="ui4me-nvda-"))
    (work / "config").mkdir()
    (work / "config" / "nvda.ini").write_text(INI, encoding="utf-8")
    log = work / "nvda.log"
    nvda = subprocess.Popen([str(args.nvda), "-m", "--disable-addons", "-c", str(work / "config"), "-f", str(log), "-l", "12", "-r"])
    time.sleep(10)
    cases: list[dict] = []

    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    def spoken_since(mark: int) -> str:
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        lines = [l for l in text[mark:].splitlines() if "Speaking" in l or "speak" in l.lower()]
        return "\n".join(lines)

    try:
        with App(app_id="org.ui4me.nvdajourney") as app:
            w = app.open(HTML, title="ui4me screen reader journey", width=520, height=420)

            def driver():
                try:
                    time.sleep(2.0)
                    hwnd = user32.FindWindowW(None, "ui4me screen reader journey")
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(2.0)
                    mark = len(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else 0
                    check("N00_nvda_running", nvda.poll() is None and log.exists(), {"log": str(log)})
                    steps = [
                        ("N01_name_field", (VK_TAB,), [r"Customer name", r"edit"], {}),
                        ("N02_checkbox", (VK_TAB,), [r"Subscribe to news", r"check ?box", r"not checked"], {}),
                        ("N03_checkbox_toggle", (VK_SPACE,), [r"\bchecked"], {}),
                        ("N04_spin_button", (VK_TAB,), [r"Quantity", r"spin ?button|edit", r"\b2\b"], {}),
                        ("N05_button", (VK_TAB,), [r"Send order", r"button"], {}),
                        ("N06_editing_host", (VK_TAB,), [r"Order notes", r"edit|multi line"], {}),
                        ("N07_back_to_button", (VK_SHIFT, VK_TAB), [r"Send order"], {}),
                    ]
                    for name, keys, patterns, _ in steps:
                        before = len(log.read_text(encoding="utf-8", errors="replace"))
                        press(*keys)
                        said = spoken_since(before)
                        missing = [p for p in patterns if not re.search(p, said, re.I)]
                        check(name, not missing, {"spoken": said[-400:], "missing": missing})
                    state = {}
                    done = threading.Event()

                    def read():
                        state["checked"] = w.get_checked("sub")
                        done.set()
                    app.post(read)
                    done.wait(5)
                    check("N08_state_matches_speech", state.get("checked") is True, state)
                    del mark
                finally:
                    app.post(app.stop)

            app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
            app.timer(120_000, lambda _: app.stop())
            app.run()
    finally:
        subprocess.run([str(args.nvda), "-q"], timeout=30)
        try:
            nvda.wait(timeout=20)
        except subprocess.TimeoutExpired:
            nvda.kill()
    result = {"status": "passed" if len(cases) == 9 and all(c["status"] == "passed" for c in cases) else "failed",
              "nvda": str(args.nvda), "cases": cases}
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    (args.out.parent / "nvda-speech.log").write_text(spoken_since(0), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"])[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
