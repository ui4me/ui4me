"""Native desktop services probe for KDE (Core 0.7). Self-checking; run on the private virtual KWin:

    python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/services_probe.py --out DIR/services.json

Starts ``kded6`` (StatusNotifierWatcher) and ``plasmashell`` (notification server, tray host) inside
the private session with private config/data/cache directories, then drives the app's
notifications, tray icon and menu, global shortcut, OS preference and menu requests through the
public API. Tray activation and the tray-menu click are sent over D-Bus the way the tray host
does. Needs PyGObject (Gio). Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import zlib
import struct
from pathlib import Path

from ui4me import App


def png(path: Path) -> None:
    w = h = 16
    raw = b"".join(b"\x00" + bytes([40, 120, 220, 255]) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def has(name: str) -> bool:
        r = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                          GLib.Variant("(s)", (name,)), None, Gio.DBusCallFlags.NONE, 2000, None)
        return r.unpack()[0]

    private = Path(tempfile.mkdtemp(prefix="ui4me-plasma-"))
    env = dict(os.environ, XDG_CONFIG_HOME=str(private / "config"), XDG_DATA_HOME=str(private / "data"),
               XDG_CACHE_HOME=str(private / "cache"), XDG_CURRENT_DESKTOP="KDE", KDE_FULL_SESSION="true")
    helpers = [subprocess.Popen(["kded6"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
               subprocess.Popen(["plasmashell", "--no-respawn"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline and not (has("org.kde.StatusNotifierWatcher") and has("org.freedesktop.Notifications")):
        time.sleep(0.5)
    cases: list[dict] = []
    events: list[dict] = []
    icon = private / "icon.png"
    png(icon)

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

    try:
        with App(app_id="org.ui4me.servicesprobe") as app:
            w = app.open("<h1>Services probe</h1>", title="ui4me services probe", width=420, height=240)
            for kind in ("notification", "tray", "menu_command", "hotkey", "environment_changed", "pointer_grab"):
                app.on(kind, events.append)
            results: dict = {}

            def owner(fn):
                """Run fn on the owner thread and wait for its result."""
                done = threading.Event()
                box = {}
                def run():
                    try:
                        box["v"] = fn()
                    except Exception as e:  # noqa: BLE001 - reported as the case detail
                        box["v"] = f"{type(e).__name__}: {e}"
                    done.set()
                app.post(run)
                done.wait(15)
                return box.get("v")

            def driver():
                try:
                    caps = owner(lambda: app.capabilities()["features"])
                    check("S01_capabilities", caps["notifications"]["status"] == "supported" and caps["system_tray"]["status"] == "supported",
                          {k: caps.get(k) for k in ("notifications", "system_tray", "global_hotkeys", "native_menus", "environment.theme_changes")})
                    n = owner(lambda: app.notify("ui4me probe", "Native notification žluťoučký", urgency="normal", actions=[("open", "Open")]))
                    check("S02_notify_sent", isinstance(n, dict) and n.get("status") == "sent", n)
                    time.sleep(1.0)
                    owner(lambda: app.close_notification(n["token"]))
                    e = wait(lambda e: e.get("type") == "notification" and e.get("token") == n["token"])
                    check("S03_close_reports_outcome", e is not None and e.get("event") in ("closed", "dismissed"), e)
                    t = owner(lambda: app.set_tray(icon=icon, tooltip="ui4me probe tray", menu=[{"id": "show", "label": "Show"}, {"separator": True}, {"id": "quit", "label": "Quit"}]))
                    check("S04_tray_set", isinstance(t, dict) and t.get("status") == "ok", t)
                    watcher = bus.call_sync("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.freedesktop.DBus.Properties", "Get",
                                            GLib.Variant("(ss)", ("org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems")), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
                    item = next((i for i in watcher if f"-{os.getpid()}-" in i or "StatusNotifierItem" in i), None)
                    check("S05_tray_registered_with_watcher", item is not None, watcher)
                    service = item.split("/")[0] if item else ""
                    bus.call_sync(service, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "Activate", GLib.Variant("(ii)", (10, 10)), None, Gio.DBusCallFlags.NONE, 3000, None)
                    e = wait(lambda e: e.get("type") == "tray" and e.get("event") == "activate")
                    check("S06_tray_activate_event", e is not None, e)
                    layout = bus.call_sync(service, "/MenuBar", "com.canonical.dbusmenu", "GetLayout", GLib.Variant("(iias)", (0, -1, [])), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
                    children = layout[1][2]
                    quit_id = next((c[0] for c in children if c[1].get("label") == "Quit"), None)
                    bus.call_sync(service, "/MenuBar", "com.canonical.dbusmenu", "Event", GLib.Variant("(isvu)", (quit_id, "clicked", GLib.Variant("s", ""), 0)), None, Gio.DBusCallFlags.NONE, 3000, None)
                    e = wait(lambda e: e.get("type") == "menu_command" and e.get("command") == "quit")
                    check("S07_tray_menu_command", e is not None and e.get("source") == "tray", {"event": e, "labels": [c[1].get("label") for c in children]})
                    r = owner(lambda: app.remove_tray())
                    time.sleep(0.5)
                    after = bus.call_sync("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.freedesktop.DBus.Properties", "Get",
                                          GLib.Variant("(ss)", ("org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems")), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
                    check("S08_tray_removed", isinstance(r, dict) and r.get("status") == "ok" and item not in after, {"result": r, "registered": after})
                    hk = owner(lambda: app.register_hotkey("probe", "Ctrl+Alt+K"))
                    check("S09_hotkey_honest_status", isinstance(hk, dict) and hk.get("status") in ("registered", "denied", "unsupported", "unavailable", "conflict"), hk)
                    env_now = owner(lambda: w.environment())
                    check("S10_os_preferences_read", isinstance(env_now, dict) and env_now.get("color_scheme_source") in ("system", "default"), env_now)
                    m = owner(lambda: w.set_menu([{"label": "File", "items": [{"id": "save", "label": "Save", "accelerator": "Ctrl+S"}]}]))
                    c = owner(lambda: w.show_context_menu(10, 10, [{"id": "copy", "label": "Copy"}]))
                    owner(lambda: w.set_pointer_grab("confined"))
                    g = wait(lambda e: e.get("type") == "pointer_grab")
                    # The virtual KWin window is not focused: an honest refusal (or a grant) is reported.
                    check("S12_pointer_grab_reported", g is not None and (g.get("applied") is True or g.get("reason")), g)
                    check("S11_menus_report_unsupported_with_accelerators", m.get("status") == "unsupported" and m.get("accelerators") is True and c.get("status") == "unsupported", {"menu": m, "context": c})
                finally:
                    app.post(app.stop)

            app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
            app.timer(120_000, lambda _: app.stop())
            app.run()
    finally:
        for p in helpers:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        subprocess.run(["rm", "-rf", str(private)], check=False)
    result = {"status": "passed" if len(cases) == 12 and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], ensure_ascii=False, default=str)[:300])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
