#!/usr/bin/env python3
"""Long-running real-input journey for the Core-only data viewer (Core 1.0 F1105).

Self-checking and automated (not a person). Run INSIDE the private virtual KWin session (Linux)
or in the interactive Windows session:

    python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/data_journey.py --out DIR/data.json
    python tests\\native\\data_journey.py --out data.json --minutes 5          (Windows)

The journey launches examples/python/data_viewer.py as a subprocess with the INSTALLED ui4me
package (run it with the interpreter the package is installed in; it refuses UI4ME_NATIVE_LIB and
a package that resolves into this repository unless --allow-workspace), and drives it with real OS
input (KWin fake_input on Linux, SendInput on Windows): filter typing, header sorting, keyboard and
mouse row selection, 20 detail windows opened and closed (alternately by key and by the window
manager), resize, scroll to the end and back, text selection and copy, PDF export. Then it repeats
cycles of those steps for --minutes (default 5) while sampling the app's resident memory.

Pass criteria: every step's observed state is correct; the DOM stays bounded (<= 200 rows);
no detail window is left open (state and OS window list); the app exits 0 on close; resident
memory growth after warm-up stays under --max-rss-growth-mb.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
TITLE = "UI4ME data viewer"
ROW_TITLE = "UI4ME row"
PAGE = 200

# ---------------------------------------------------------------------------------------------
# Desktop drivers: identical interface on both platforms. Coordinates are screen pixels.
# ---------------------------------------------------------------------------------------------


class LinuxDesktop:
    KEYS = {"enter": 28, "esc": 1, "down": 108, "up": 103, "home": 102, "end": 107, "pgdn": 109, "pgup": 104,
            "backspace": 14, "ctrl": 29, "shift": 42, "a": 30, "c": 46}

    def __init__(self, work: Path):
        sys.path.insert(0, str(HERE / "kwin"))
        import chat_journey as cj  # noqa: PLC0415 - shared KWin tooling

        self.cj = cj
        sock = os.environ["WAYLAND_DISPLAY"]
        self.log = Path(os.environ["XDG_RUNTIME_DIR"]) / f"{sock}.log"
        if not self.log.exists():
            raise RuntimeError(f"KWin log {self.log} not found: run under chat_journey.py --plain")
        self.fake = cj.Input(cj.build_fakeinput(work))

    def click(self, x, y):
        self.fake(f"click {x:.0f} {y:.0f}")

    def move(self, x, y):
        self.fake(f"move {x:.0f} {y:.0f}")

    def drag(self, x1, y1, x2, y2):
        self.fake(f"move {x1:.0f} {y1:.0f}")
        self.fake("down")
        for i in range(1, 9):
            self.fake(f"move {x1 + (x2 - x1) * i / 8:.0f} {y1 + (y2 - y1) * i / 8:.0f}")
        self.fake("up")

    def wheel(self, notches):
        """Positive = scroll down."""
        self.fake(f"wheel {notches * 10}")

    def key(self, name, *mods):
        for m in mods:
            self.fake(f"kd {self.KEYS[m]}")
        self.fake(f"key {self.KEYS[name]}")
        for m in reversed(mods):
            self.fake(f"ku {self.KEYS[m]}")

    def type(self, text):
        self.fake(f"type {text}")

    def _script(self, body):
        return self.cj.kwin_script(self.log, body)

    def titles(self):
        out = self._script("workspace.windowList().forEach(function(w){ print('UI4ME_WIN|'+w.caption); });")
        return [t for t in out if "UI4ME" in t]

    def client_geometry(self, title):
        return self.cj.window_geometry(self.log, title)

    def set_frame(self, title, x, y, w, h):
        return self.cj.window_geometry(self.log, title, (x, y, w, h))

    def close(self, title):
        self.cj.close_window(self.log, title)

    def stop(self):
        self.fake.close()


class WindowsDesktop:
    VK = {"enter": 0x0D, "esc": 0x1B, "down": 0x28, "up": 0x26, "home": 0x24, "end": 0x23, "pgdn": 0x22, "pgup": 0x21,
          "backspace": 0x08, "ctrl": 0x11, "shift": 0x10, "a": 0x41, "c": 0x43}

    def __init__(self, work: Path):
        import ctypes
        import ctypes.wintypes as wt

        self.ct, self.wt = ctypes, wt
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SetProcessDPIAware()
        self.user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        self.user32.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
        self.enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        self.KEYBDINPUT, self.INPUT = KEYBDINPUT, INPUT

    # keyboard
    def _vk(self, vk, up=False):
        i = self.INPUT(type=1)
        i.ki = self.KEYBDINPUT(vk, 0, 2 if up else 0, 0, 0)
        self.user32.SendInput(1, self.ct.byref(i), self.ct.sizeof(self.INPUT))
        time.sleep(0.02)

    def key(self, name, *mods):
        for m in mods:
            self._vk(self.VK[m])
        self._vk(self.VK[name])
        self._vk(self.VK[name], True)
        for m in reversed(mods):
            self._vk(self.VK[m], True)

    def type(self, text):
        for ch in text:
            for up in (0, 2):
                i = self.INPUT(type=1)
                i.ki = self.KEYBDINPUT(0, ord(ch), 0x0004 | up, 0, 0)
                self.user32.SendInput(1, self.ct.byref(i), self.ct.sizeof(self.INPUT))
                time.sleep(0.015)

    # mouse
    def move(self, x, y):
        self.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)

    def _button(self, down):
        self.user32.mouse_event(0x0002 if down else 0x0004, 0, 0, 0, 0)
        time.sleep(0.03)

    def click(self, x, y):
        self.move(x, y)
        self._button(True)
        self._button(False)

    def drag(self, x1, y1, x2, y2):
        self.move(x1, y1)
        self._button(True)
        for i in range(1, 9):
            self.move(x1 + (x2 - x1) * i / 8, y1 + (y2 - y1) * i / 8)
        self._button(False)

    def wheel(self, notches):
        self.user32.mouse_event(0x0800, 0, 0, int(-120 * notches) & 0xFFFFFFFF, 0)
        time.sleep(0.03)

    # windows
    def _enum(self):
        found = []

        def cb(hwnd, _):
            if self.user32.IsWindowVisible(hwnd):
                buf = self.ct.create_unicode_buffer(256)
                self.user32.GetWindowTextW(hwnd, buf, 256)
                if "UI4ME" in buf.value:
                    found.append((hwnd, buf.value))
            return True

        self.user32.EnumWindows(self.enum_proc(cb), 0)
        return found

    def titles(self):
        return [t for _, t in self._enum()]

    def _hwnd(self, title):
        for hwnd, t in self._enum():
            if title in t:
                return hwnd
        return None

    def client_geometry(self, title):
        hwnd = self._hwnd(title)
        if not hwnd:
            return None
        wt = self.wt
        rect, pt = wt.RECT(), wt.POINT(0, 0)
        self.user32.GetClientRect(hwnd, self.ct.byref(rect))
        self.user32.ClientToScreen(hwnd, self.ct.byref(pt))
        return float(pt.x), float(pt.y), float(rect.right), float(rect.bottom)

    def set_frame(self, title, x, y, w, h):
        hwnd = self._hwnd(title)
        if not hwnd:
            return None
        wt = self.wt
        outer, client = wt.RECT(), wt.RECT()
        self.user32.GetWindowRect(hwnd, self.ct.byref(outer))
        self.user32.GetClientRect(hwnd, self.ct.byref(client))
        dw = (outer.right - outer.left) - client.right
        dh = (outer.bottom - outer.top) - client.bottom
        self.user32.SetWindowPos(hwnd, 0, int(x), int(y), int(w + dw), int(h + dh), 0x0004)
        time.sleep(0.3)
        return self.client_geometry(title)

    def close(self, title):
        hwnd = self._hwnd(title)
        if hwnd:
            self.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def stop(self):
        pass


MEASURED: dict = {}  # what the last rss_mib() call actually measured (pid / image / metric)


def _win_python_descendant(pid: int):
    """Deepest python child of ``pid`` (the venv python.exe is a launcher that spawns the real interpreter)."""
    import ctypes
    import ctypes.wintypes as wt

    class ENTRY(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(ENTRY)]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    snap = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (None, wt.HANDLE(-1).value):
        raise OSError(f"CreateToolhelp32Snapshot failed: winerror {ctypes.get_last_error()}")
    procs = {}
    try:
        e = ENTRY()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            procs[e.th32ProcessID] = (e.th32ParentProcessID, e.szExeFile)
            ok = kernel.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel.CloseHandle(snap)
    best, image = pid, procs.get(pid, (0, "?"))[1]
    while True:
        kids = [(p, n) for p, (parent, n) in procs.items() if parent == best and p != best and n.lower().startswith("python")]
        if not kids:
            return best, image
        best, image = min(kids)


def rss_mib(pid: int) -> float:
    """Resident memory (MiB) of the measured process; raises when it cannot be measured (never returns 0).

    Linux: VmRSS of ``pid``. Windows: WorkingSetSize of the deepest python child of ``pid`` (the venv python.exe
    launcher spawns the real interpreter), else of ``pid`` itself. ``MEASURED`` records pid / image / metric."""
    if not WINDOWS:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                MEASURED.update({"pid": pid, "image": "(linux process)", "metric": "VmRSS"})
                return int(line.split()[1]) / 1024
        raise RuntimeError(f"no VmRSS in /proc/{pid}/status")
    import ctypes
    import ctypes.wintypes as wt

    class COUNTERS(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    target, image = _win_python_descendant(pid)
    kernel, psapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(COUNTERS), wt.DWORD]
    handle = kernel.OpenProcess(0x1000 | 0x0010, False, target)  # QUERY_LIMITED_INFORMATION | VM_READ
    if not handle:
        raise OSError(f"OpenProcess({target}) failed: winerror {ctypes.get_last_error()}")
    try:
        c = COUNTERS()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb):
            raise OSError(f"GetProcessMemoryInfo({target}) failed: winerror {ctypes.get_last_error()}")
    finally:
        kernel.CloseHandle(handle)
    MEASURED.update({"pid": target, "image": image, "launcher_pid": pid, "metric": "WorkingSetSize"})
    return c.WorkingSetSize / (1024 * 1024)


# ---------------------------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------------------------


def snake_keys(value):
    """PowerShell records use PascalCase (MaxY, Width); the Python app uses snake_case (max_y, width)."""
    if isinstance(value, dict):
        return {"".join(("_" + c.lower()) if c.isupper() and i else c.lower() for i, c in enumerate(k)): snake_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [snake_keys(v) for v in value]
    return value


def amount(i: int) -> float:
    return ((i * 7919) % 100000) / 100.0


class Journey:
    def __init__(self, args, work: Path):
        self.args, self.work = args, work
        self.state_path = work / "state.json"
        self.cases: list[dict] = []
        self.desk = (WindowsDesktop if WINDOWS else LinuxDesktop)(work)
        self.origin = (0.0, 0.0)
        self.scale = 1.0
        self.proc = None
        self.retries = 0
        self.scale_known = False

    # --- state helpers
    def state(self) -> dict:
        for _ in range(20):
            try:
                return snake_keys(json.loads(self.state_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                time.sleep(0.05)
        raise RuntimeError("state file unreadable")

    def wait(self, predicate, what, timeout=15.0) -> dict:
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            try:
                last = self.state()
                if predicate(last):
                    return last
            except (KeyError, TypeError, IndexError, AttributeError):
                pass
            time.sleep(0.05)
        brief = {k: last.get(k) for k in ("filter", "matched", "sort", "page", "selected", "dom_rows", "details_open", "focus")} if last else None
        raise AssertionError(f"timeout waiting for {what}: {brief}")

    def pt(self, rect, fx=0.5, fy=0.5):
        return (self.origin[0] + (rect["x"] + rect["width"] * fx) * self.scale,
                self.origin[1] + (rect["y"] + rect["height"] * fy) * self.scale)

    def click_rect(self, rect, fx=0.5, fy=0.5):
        self.desk.click(*self.pt(rect, fx, fy))

    def locate(self, frame=None):
        for _ in range(60):
            g = self.desk.set_frame(TITLE, *frame) if frame else self.desk.client_geometry(TITLE)
            if g:
                time.sleep(0.6)  # the window system applies the new frame asynchronously
                g = self.desk.client_geometry(TITLE) or g
                self.origin = (g[0], g[1])
                time.sleep(0.3)
                s = self.state()
                page = (s.get("rects") or {}).get("page")
                # The output scale is fixed for the session: derive it once. Re-deriving it after a
                # resize reads a page width that may not have caught up with the new frame yet,
                # and every later click would land scaled away from its target.
                if page and page["width"] > 0 and not self.scale_known:
                    ratio = g[2] / page["width"]
                    self.scale = 1.0 if abs(ratio - 1.0) < 0.02 else ratio
                    self.scale_known = True
                return g
            time.sleep(0.25)
        raise RuntimeError("the data viewer window is not listed by the window system")

    def refocus(self):
        """Give the main window keyboard focus without changing the data state."""
        self.click_rect(self.state()["rects"]["summary"], 0.8, 0.5)

    def case(self, name, fn):
        started = time.monotonic()
        try:
            detail = fn()
            self.cases.append({"id": name, "status": "passed", "details": detail, "seconds": round(time.monotonic() - started, 1)})
        except Exception as error:  # noqa: BLE001 - recorded, later cases report on their own
            self.cases.append({"id": name, "status": "failed", "details": f"{type(error).__name__}: {error}"})
            print(f"FAILED {name}: {error}", flush=True)

    # --- steps shared by the first pass and the soak cycles
    def focus_filter(self):
        """Click the filter field until the app reports it focused (an input race is counted, not hidden)."""
        for attempt in range(4):
            self.click_rect(self.state()["rects"]["filter"])
            try:
                self.wait(lambda s: s["focus"] == ["filter"], "filter focused", timeout=3)
                return
            except AssertionError:
                self.retries += 1
        s = self.state()
        raise AssertionError(f"the filter field never took focus after 4 clicks: origin={self.origin} scale={self.scale} "
                             f"client={self.desk.client_geometry(TITLE)} filter={s['rects']['filter']} focus={s['focus']} "
                             f"details_open={s['details_open']} titles={self.desk.titles()}")

    def filter_step(self):
        self.focus_filter()
        self.desk.type("name 0012")
        s = self.wait(lambda s: s["filter_value"] == "name 0012" and s["matched"] == 10 and s["dom_rows"] == 10, "filter 'name 0012' -> 10 rows")
        self.desk.key("a", "ctrl")
        self.desk.key("backspace")
        s2 = self.wait(lambda s: s["filter_value"] == "" and s["matched"] == self.args.rows and s["dom_rows"] == PAGE, "filter cleared -> full page")
        return {"matched_while_filtered": s["matched"], "after_clear": s2["matched"], "dom_rows": s2["dom_rows"]}

    def sort_step(self):
        expected_max = max(range(self.args.rows), key=amount)
        s = self.state()
        self.click_rect(s["rects"]["h-3"])
        s = self.wait(lambda s: s["sort"] == {"col": 3, "desc": False} and s["row_ids"][0] == "r0", "amount ascending, first row r0")
        self.click_rect(s["rects"]["h-3"])
        s = self.wait(lambda s: s["sort"] == {"col": 3, "desc": True} and s["row_ids"][0] == f"r{expected_max}", f"amount descending, first row r{expected_max}")
        self.click_rect(s["rects"]["h-0"])
        s = self.wait(lambda s: s["sort"] == {"col": 0, "desc": False} and s["row_ids"][0] == "r0" and s["dom_rows"] == PAGE, "id ascending")
        return {"max_amount_row": expected_max, "dom_rows": s["dom_rows"]}

    def keyboard_step(self):
        s = self.state()
        self.click_rect(s["row_rects"][0], 0.5, 0.5)
        s = self.wait(lambda s: s["selected"] == 0 and s["selected_rect"], "click selects the first row")
        for _ in range(3):
            self.desk.key("down")
        s = self.wait(lambda s: s["selected"] == 3, "Down x3 -> row 3")
        self.desk.key("pgdn")
        s = self.wait(lambda s: s["selected"] == 13, "PageDown -> row 13")
        self.desk.key("up")
        s = self.wait(lambda s: s["selected"] == 12, "Up -> row 12")
        self.desk.key("end")
        last_page = (self.args.rows - 1) // PAGE
        s = self.wait(lambda s: s["selected"] == self.args.rows - 1 and s["page"] == last_page and s["dom_rows"] <= PAGE, "End -> last row on the last page")
        self.desk.key("home")
        s = self.wait(lambda s: s["selected"] == 0 and s["page"] == 0 and s["dom_rows"] == PAGE, "Home -> first row on the first page")
        self.click_rect(s["row_rects"][2])
        s = self.wait(lambda s: s["selected"] == 2, "mouse click selects row 2")
        return {"selected": s["selected"], "page": s["page"], "dom_rows": s["dom_rows"]}

    def detail_cycle(self, count, key_close_every=2):
        """Open `count` detail windows for consecutive rows and close each (alternately by Escape and by the window system)."""
        fallbacks = 0
        for n in range(count):
            s = self.state()
            row = s["selected"]
            opened, closed = s["details_opened"], s["details_closed"]
            self.desk.key("enter")
            self.wait(lambda s: s["details_opened"] == opened + 1 and s["details_open"] == [row], f"detail window for row {row}")
            title = f"{ROW_TITLE} {row}"
            for _ in range(60):
                if any(title in t for t in self.desk.titles()):
                    break
                time.sleep(0.1)
            else:
                raise AssertionError(f"the OS does not list '{title}'")
            time.sleep(0.2)
            if n % key_close_every == 0:
                self.desk.key("esc")
                try:
                    self.wait(lambda s: s["details_closed"] == closed + 1, f"Escape closes row {row}", timeout=4)
                except AssertionError:
                    fallbacks += 1  # keyboard focus did not follow the new window: the WM close is the fallback
                    self.desk.close(title)
            else:
                self.desk.close(title)
            self.wait(lambda s: s["details_closed"] == closed + 1 and s["details_open"] == [], f"row {row} detail closed", timeout=15)
            self.refocus()
            self.desk.key("down")
            self.wait(lambda s: s["selected"] == row + 1, "Down after closing the detail window")
        left = [t for t in self.desk.titles() if ROW_TITLE in t]
        if left:
            raise AssertionError(f"leaked detail windows: {left}")
        return {"opened": count, "escape_fallbacks_to_wm_close": fallbacks}

    def resize_step(self):
        out = []
        for w, h in ((900, 600), (1200, 820), (700, 520), (1000, 700)):
            before = self.state()["resized"][-1:] or [None]
            g = self.locate((40, 40, w, h))
            s = self.wait(lambda s: s["resized"] and s["rects"]["scroller"]["height"] > 100 and abs(s["rects"]["page"]["width"] * self.scale - g[2]) < 3, f"resize to {w}x{h}")
            r = s["rects"]["scroller"]
            if (r["y"] + r["height"]) * self.scale > g[3] + 2:
                raise AssertionError(f"the table is taller than the window at {w}x{h}: {r} vs {g}")
            if s["dom_rows"] > PAGE:
                raise AssertionError("DOM rows unbounded after resize")
            out.append({"client": [round(v) for v in g], "scroller_h": round(r["height"])})
        return out

    def scroll_step(self):
        s = self.state()
        self.desk.move(*self.pt(s["rects"]["scroller"], 0.5, 0.5))
        steps = 0
        while steps < 120:  # 10 notches a step (100 px on KWin, about 1000 px on Windows)
            self.desk.wheel(10)
            steps += 1
            time.sleep(0.05)
            s = self.state()
            if s["scroll"]["max_y"] and s["scroll"]["y"] >= s["scroll"]["max_y"] - 1:
                break
        s = self.wait(lambda s: s["scroll"]["max_y"] > 0 and s["scroll"]["y"] >= s["scroll"]["max_y"] - 1, "scrolled to the end")
        end_y = s["scroll"]["y"]
        for _ in range(steps + 20):
            self.desk.wheel(-10)
            time.sleep(0.05)
            if self.state()["scroll"]["y"] <= 0:
                break
        s = self.wait(lambda s: s["scroll"]["y"] <= 0.5, "scrolled back to the top")
        return {"end_y": round(end_y), "steps": steps, "dom_rows": s["dom_rows"]}

    def copy_step(self):
        self.refocus()  # a resize by the window system can leave the window without keyboard focus
        s = self.wait(lambda s: s["scroll"]["y"] <= 0.5 and len(s["row_rects"]) >= 4, "table at top")
        r0, r3 = s["row_rects"][0], s["row_rects"][3]
        x1, y1 = self.pt(r0, 0.25, 0.5)
        x2, y2 = self.pt(r3, 0.6, 0.5)
        self.desk.drag(x1, y1, x2, y2)
        s = self.wait(lambda s: len(s["selection"]) > 10, "text selected by dragging over rows")
        text = s["selection"]
        self.desk.key("c", "ctrl")
        s = self.wait(lambda s: (s["clipboard"] or "").replace("\r\n", "\n").strip() == text.replace("\r\n", "\n").strip(), "Ctrl+C puts the selection on the OS clipboard")
        return {"selection_chars": len(text), "sample": text[:60]}

    def export_step(self):
        s = self.state()
        n = len(s["exports"])
        self.click_rect(s["rects"]["export"])
        s = self.wait(lambda s: len(s["exports"]) == n + 1 and not s["errors"], "PDF export", timeout=60)
        e = s["exports"][-1]
        data = Path(e["path"]).read_bytes()
        if not data.startswith(b"%PDF") or len(data) < 1500 or not (e["pages"] and e["pages"] >= 1):
            raise AssertionError(f"bad export {e}")
        Path(e["path"]).unlink(missing_ok=True)
        return {"pages": e["pages"], "bytes": e["bytes"]}

    # --- run
    def run(self) -> dict:
        args = self.args
        independence = self.independence()
        export_dir = self.work / "exports"
        export_dir.mkdir(exist_ok=True)
        if str(args.app).endswith(".ps1"):  # the PowerShell twin, run against the installed Ui4me module
            cmd = ["pwsh", "-NoProfile", "-File", str(args.app), "-Rows", str(args.rows), "-StatePath", str(self.state_path), "-ExportDir", str(export_dir)]
        else:
            cmd = [args.python, str(args.app), "--rows", str(args.rows), "--state", str(self.state_path), "--export-dir", str(export_dir)]
        env = dict(os.environ)
        if not args.allow_workspace:
            env.pop("UI4ME_NATIVE_LIB", None)
        self.proc = subprocess.Popen(cmd, env=env, stdout=(self.work / "app.log").open("w"), stderr=subprocess.STDOUT)
        samples: list[tuple[float, float]] = []
        t_start = time.monotonic()
        try:
            def launch():
                s = self.wait(lambda s: s.get("loaded") and s["matched"] == args.rows and s["dom_rows"] == PAGE, "rows loaded in the background", timeout=60)
                g = self.locate((40, 40, 1000, 700))
                return {"total": s["total"], "dom_rows": s["dom_rows"], "client": [round(v) for v in g], "scale": self.scale, "summary": s["summary"]}

            self.case("D01_launch_background_load", launch)
            self.case("D02_filter_typing", self.filter_step)
            self.case("D03_sort_by_headers", self.sort_step)
            self.case("D04_keyboard_and_mouse_selection", self.keyboard_step)
            self.case("D05_twenty_detail_windows", lambda: self.detail_cycle(20))
            self.case("D06_resize", self.resize_step)
            self.case("D07_scroll_end_and_back", self.scroll_step)
            self.case("D08_select_text_and_copy", self.copy_step)
            self.case("D09_export_pdf", self.export_step)

            soak = {"cycles": 0, "failures": []}

            def soak_run():
                deadline = time.monotonic() + args.minutes * 60
                cycle = 0
                while time.monotonic() < deadline:
                    cycle += 1
                    try:
                        self.refocus()
                        self.filter_step()
                        self.sort_step()
                        self.keyboard_step()
                        self.detail_cycle(3)
                        self.resize_step() if cycle % 2 == 0 else None
                        self.scroll_step()
                        self.copy_step()
                        if cycle % 3 == 0:
                            self.export_step()
                        s = self.state()
                        if s["dom_rows"] > PAGE or s["details_open"] or s["details_opened"] != s["details_closed"]:
                            raise AssertionError(f"end-of-cycle state: dom_rows={s['dom_rows']} details_open={s['details_open']}")
                    except Exception as error:  # noqa: BLE001
                        soak["failures"].append(f"cycle {cycle}: {type(error).__name__}: {error}")
                        if len(soak["failures"]) >= 3:
                            break
                        try:
                            self.locate((40, 40, 1000, 700))
                        except Exception:  # noqa: BLE001
                            pass
                    samples.append((round(time.monotonic() - t_start, 1), round(rss_mib(self.proc.pid), 1)))
                    soak["cycles"] = cycle
                if soak["failures"]:
                    raise AssertionError("; ".join(soak["failures"]))
                return {"cycles": cycle, "minutes": args.minutes}

            samples.append((0.0, round(rss_mib(self.proc.pid), 1)))
            self.case("D10_soak_cycles", soak_run)

            def memory():
                if len(samples) < 4:
                    raise AssertionError(f"too few memory samples ({len(samples)}); run longer than one cycle")
                warm = samples[min(len(samples) - 2, max(1, len(samples) // 4))]
                growth = samples[-1][1] - warm[1]
                peak = max(v for _, v in samples)
                if growth > args.max_rss_growth_mb:
                    raise AssertionError(f"resident memory grew {growth:.1f} MiB after warm-up (limit {args.max_rss_growth_mb})")
                return {"warmup_mib": warm[1], "final_mib": samples[-1][1], "growth_mib": round(growth, 1), "peak_mib": peak, "samples": len(samples), "measured": dict(MEASURED)}

            self.case("D11_rss_bounded_after_warmup", memory)

            def close():
                self.desk.close(TITLE)
                code = self.proc.wait(timeout=30)
                s = self.state()
                left = [t for t in self.desk.titles()]
                if code != 0 or not s.get("exited") or not s.get("closed") or left:
                    raise AssertionError(f"exit={code} exited={s.get('exited')} closed={s.get('closed')} windows left={left}")
                return {"exit_code": code, "details_opened": s["details_opened"], "details_closed": s["details_closed"], "errors": s["errors"]}

            self.case("D12_close_exits_cleanly", close)
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            self.desk.stop()
        status = "passed" if self.cases and all(c["status"] == "passed" for c in self.cases) else "failed"
        return {"platform": "windows" if WINDOWS else "linux", "status": status, "independence": independence, "focus_click_retries": self.retries,
                "rss_samples_s_mib": samples, "cases": self.cases}

    def independence(self) -> dict:
        """The app must run against the installed package: no UI4ME_NATIVE_LIB, no repository import path."""
        if str(self.args.app).endswith(".ps1"):
            return {"powershell": "pwsh", "module_path": os.environ.get("PSModulePath", ""), "app": str(self.args.app)}
        if os.environ.get("UI4ME_NATIVE_LIB") and not self.args.allow_workspace:
            raise SystemExit("UI4ME_NATIVE_LIB is set: the journey must run against the installed package")
        probe = subprocess.run([self.args.python, *([] if self.args.allow_workspace else ["-I"]), "-c", "import ui4me,sys;print(ui4me.__file__);print(getattr(ui4me,'__version__',''))"],
                               capture_output=True, text=True, cwd=tempfile.gettempdir())
        if probe.returncode != 0:
            raise SystemExit(f"{self.args.python} cannot import the installed ui4me package: {probe.stderr.strip()}")
        path, version = (probe.stdout.splitlines() + [""])[:2]
        repo = HERE.parent.parent
        # The source package (bindings/python/src) is refused; an installed wheel in a venv that
        # happens to live under the checkout (the gate's build/evidence directory) is not.
        resolved = Path(path).resolve()
        if not self.args.allow_workspace and resolved.is_relative_to(repo) and "site-packages" not in resolved.parts:
            raise SystemExit(f"ui4me resolves into the repository ({path}); install the wheel or pass --allow-workspace")
        return {"python": self.args.python, "package": path, "version": version, "app": str(self.args.app)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="result JSON path")
    parser.add_argument("--minutes", type=float, default=5.0, help="soak duration after the first pass (default 5)")
    parser.add_argument("--app", type=Path, default=HERE.parent.parent / "examples" / "python" / "data_viewer.py",
                        help="data_viewer.py, or examples/powershell/data_viewer.ps1 for the PowerShell twin")
    parser.add_argument("--python", default=sys.executable, help="interpreter with the installed ui4me package")
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--max-rss-growth-mb", type=float, default=96.0)
    parser.add_argument("--allow-workspace", action="store_true", help="development only: allow a repository ui4me import")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui4me-datajourney-") as work:
        journey = Journey(args, Path(work))
        result = journey.run()
        log = Path(work) / "app.log"
        if log.exists():  # the app's own output, kept next to the result
            (args.out.parent / "app.log").write_text(log.read_text(encoding="utf-8", errors="replace")[-200000:], encoding="utf-8")
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in result["cases"]:
        print(f"{c['status']:7} {c['id']}  {json.dumps(c.get('details'), ensure_ascii=False)[:200]}", flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
