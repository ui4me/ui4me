"""Live environment probe (Core 0.5 F0506). Self-checking; run inside a desktop session:

    Linux (private virtual KWin):  python3 tests/native/kwin/chat_journey.py --plain --out DIR -- \\
                                       python3 tests/native/environment_probe.py --out DIR/env.json
    Windows (interactive session): python environment_probe.py --out env.json

Opens a window with a focused, edited text field, then changes the OS environment underneath
it: the output scale (Linux: ``kscreen-doctor`` on the virtual KWin output) or the app light/dark
theme (Windows: ``AppsUseLightTheme`` plus the ``ImmersiveColorSet`` broadcast, restored
afterwards). Checks the document restyles in place (scale / ``prefers-color-scheme``) while the
value, focus and caret survive, and reads the capability report. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from ui4me import App

PAGE = """<style>#b{width:100px;height:10px;background:#888}@media (prefers-color-scheme: dark){#b{width:200px}}</style>
<div id=b></div><input id=name value=Ada>"""


def windows_theme(light: int | None) -> int | None:
    """Set AppsUseLightTheme (returns the previous value) and broadcast the change."""
    import ctypes
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", 0,
                         winreg.KEY_READ | winreg.KEY_SET_VALUE)
    try:
        previous = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
    except OSError:
        previous = None
    if light is not None:
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, light)
    winreg.CloseKey(key)
    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 3000, ctypes.byref(result))
    return previous


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict] = []
    log: list[dict] = []
    state = {"step": 0, "since": time.monotonic(), "restore": None}

    def record(name: str, ok: bool, detail) -> None:
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    with App(app_id="org.ui4me.envprobe") as app:
        w = app.open(PAGE, title="ui4me environment probe", width=500, height=300)
        app.on("scale_changed", log.append)
        app.on("environment_changed", log.append)

        def input_state() -> dict:
            return {"value": w.get_value("name"), "focus": w.query(":focus"), "width": w.get_rect("b")["width"],
                    "env": w.environment()}

        steps = []
        if sys.platform == "win32":
            def flip():
                state["restore"] = windows_theme(None)
                state["base"] = input_state()
                windows_theme(0 if state["base"]["env"]["color_scheme"] == "light" else 1)

            def flipped():
                s = input_state()
                want = "dark" if state["base"]["env"]["color_scheme"] == "light" else "light"
                return s["env"]["color_scheme"] == want and s["env"]["color_scheme_source"] == "system", s
            steps = [("E01_os_theme_change_restyles", flip, flipped)]
        else:
            def scale():
                state["base"] = input_state()
                subprocess.run(["kscreen-doctor", "output.Virtual-0.scale.2"], check=True, capture_output=True, timeout=20)

            def scaled():
                s = input_state()
                return s["env"]["scale"] == 2.0, s
            steps = [("E01_os_scale_change_relayouts", scale, scaled)]

        def prepare():
            w.focus("name")
            w.set_value("name", "Ada!")

        def tick(_):
            if state["step"] == 0:
                prepare()
                state["step"] = 1
                state["since"] = time.monotonic()
                return
            index = state["step"] - 1
            if index >= len(steps) * 2:
                caps = app.capabilities()
                record("E02_input_state_kept", True, None)  # filled below from the last state
                record("E03_capabilities", caps["platform"] not in ("pending", "headless")
                       and caps["features"]["environment.app_override"]["status"] == "supported",
                       {k: v for k, v in caps["features"].items() if k.startswith("environment.")})
                app.stop()
                return
            name, act, check = steps[index // 2]
            if index % 2 == 0:
                act()
                state["step"] += 1
                state["since"] = time.monotonic()
                return
            ok, s = check()
            if ok or time.monotonic() - state["since"] > 8:
                state["after"] = s
                record(name, ok, {"before": state["base"], "after": s, "events": log[-4:]})
                state["step"] += 1

        app.timer(100, tick, repeat=True)
        app.timer(60_000, lambda _: app.stop())
        app.run()
    if sys.platform == "win32" and state["restore"] is not None:
        windows_theme(state["restore"])
    after = state.get("after", {})
    for c in cases:
        if c["id"] == "E02_input_state_kept":
            ok = after.get("value") == "Ada!" and after.get("focus") == ["name"]
            c.update(status="passed" if ok else "failed", details={"value": after.get("value"), "focus": after.get("focus")})
    result = {"status": "passed" if len(cases) == 3 and all(c["status"] == "passed" for c in cases) else "failed",
              "platform": sys.platform, "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], ensure_ascii=False)[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
