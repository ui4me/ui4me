"""Native desktop services probe for Windows (Core 0.7). Self-checking; run INSIDE an interactive
desktop session (a scheduled task as the logged-on user):

    python services_probe.py --out services.json

Drives notifications (balloon), the tray icon, the window menu bar (F10, Enter with SendInput),
a menu accelerator (Ctrl+S), a context menu (Down, Enter), a global shortcut (Ctrl+Alt+K pressed
with SendInput) and a shortcut conflict (another holder registered first) through the public API.
Automated; not a person.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import threading
import time
from pathlib import Path

from ui4me import App

user32 = ctypes.WinDLL("user32", use_last_error=True)
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def key(vk: int, up: bool = False) -> None:
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    time.sleep(0.03)


def press(*vks: int) -> None:
    for v in vks:
        key(v)
    for v in reversed(vks):
        key(v, True)


VK_CONTROL, VK_MENU, VK_F10, VK_RETURN, VK_DOWN, VK_ESCAPE = 0x11, 0x12, 0x79, 0x0D, 0x28, 0x1B


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict] = []
    events: list[dict] = []

    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    def wait(pred, seconds=8.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            got = [e for e in list(events) if pred(e)]
            if got:
                return got[0]
            time.sleep(0.1)
        return None

    with App(app_id="org.ui4me.servicesprobe") as app:
        w = app.open("<h1>Services probe</h1><p>Windows</p>", title="ui4me services probe", width=480, height=300)
        for kind in ("notification", "tray", "menu_command", "hotkey", "menu_status", "pointer_grab"):
            app.on(kind, events.append)

        def owner(fn):
            done = threading.Event()
            box = {}
            def run():
                try:
                    box["v"] = fn()
                except Exception as e:  # noqa: BLE001
                    box["v"] = f"{type(e).__name__}: {e}"
                done.set()
            app.post(run)
            done.wait(15)
            return box.get("v")

        def foreground():
            hwnd = user32.FindWindowW(None, "ui4me services probe")
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            return hwnd

        def driver():
            try:
                caps = owner(lambda: app.capabilities()["features"])
                keys = ("notifications", "system_tray", "native_menus", "native_menus.context", "global_hotkeys")
                check("W01_capabilities", all(caps[k]["status"] == "supported" for k in keys), {k: caps.get(k) for k in keys + ("environment.contrast",)})
                n = owner(lambda: app.notify("ui4me probe", "Native notification žluťoučký"))
                check("W02_notify_sent", isinstance(n, dict) and n.get("status") == "sent", n)
                time.sleep(1.5)
                owner(lambda: app.close_notification(n["token"]))
                e = wait(lambda e: e.get("type") == "notification" and e.get("token") == n["token"])
                check("W03_notification_outcome", e is not None, e)
                t = owner(lambda: app.set_tray(tooltip="ui4me probe tray", menu=[{"id": "quit", "label": "Quit"}]))
                r = owner(lambda: app.remove_tray())
                check("W04_tray_add_remove", t == {"status": "ok"} and r == {"status": "ok"}, {"set": t, "remove": r})
                m = owner(lambda: w.set_menu([{"label": "File", "items": [{"id": "save", "label": "Save", "accelerator": "Ctrl+S"}, {"id": "quit", "label": "Quit"}]}]))
                time.sleep(0.8)
                hwnd = foreground()
                hmenu = user32.GetMenu(hwnd)
                count = user32.GetMenuItemCount(hmenu) if hmenu else -1
                check("W05_native_menu_bar", m.get("status") == "supported" and hmenu and count == 1, {"result": m, "items": count})
                press(VK_F10)
                time.sleep(0.4)
                press(VK_RETURN)
                time.sleep(0.4)
                press(VK_RETURN)
                e = wait(lambda e: e.get("type") == "menu_command" and e.get("source") == "window")
                check("W06_menu_bar_keyboard_command", e is not None and e.get("command") == "save", e)
                foreground()
                press(VK_CONTROL, ord("S"))
                e = wait(lambda e: e.get("type") == "menu_command" and e.get("source") == "accelerator")
                check("W07_accelerator", e is not None and e.get("command") == "save", e)
                c = owner(lambda: w.show_context_menu(40, 40, [{"id": "copy", "label": "Copy"}, {"id": "paste", "label": "Paste"}]))
                time.sleep(1.0)
                press(VK_DOWN)
                time.sleep(0.2)
                press(VK_DOWN)
                time.sleep(0.2)
                press(VK_RETURN)
                e = wait(lambda e: e.get("type") == "menu_command" and e.get("source") == "context")
                check("W08_context_menu", c.get("status") == "ok" and e is not None and e.get("command") in ("copy", "paste"), {"result": c, "event": e})
                hk = owner(lambda: app.register_hotkey("probe", "Ctrl+Alt+K"))
                time.sleep(0.3)
                press(VK_CONTROL, VK_MENU, ord("K"))
                e = wait(lambda e: e.get("type") == "hotkey" and e.get("id") == "probe")
                check("W09_global_hotkey", hk.get("status") == "registered" and e is not None, {"result": hk, "event": e})
                # Another holder owns Ctrl+Alt+J: the app gets an honest conflict.
                held = user32.RegisterHotKey(None, 0x7EEF, 0x0002 | 0x0001 | 0x4000, ord("J"))
                cf = owner(lambda: app.register_hotkey("taken", "Ctrl+Alt+J"))
                if held:
                    user32.UnregisterHotKey(None, 0x7EEF)
                check("W10_hotkey_conflict", bool(held) and cf.get("status") == "conflict", {"held": bool(held), "result": cf})
                foreground()
                owner(lambda: w.set_pointer_grab("confined"))
                g = wait(lambda e: e.get("type") == "pointer_grab" and e.get("mode") == "confined")
                owner(lambda: w.set_pointer_grab("none"))
                check("W12_pointer_confined", g is not None and g.get("applied") is True, g)
                env = owner(lambda: w.environment())
                check("W11_os_preferences", isinstance(env, dict) and env.get("high_contrast") in (True, False) and env.get("color_scheme_source") in ("system", "default"), env)
            finally:
                app.post(app.stop)

        app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
        app.timer(150_000, lambda _: app.stop())
        app.run()
    result = {"status": "passed" if len(cases) == 12 and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], ensure_ascii=False, default=str)[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
