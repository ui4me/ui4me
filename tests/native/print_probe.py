"""Native print probe (Core 1.0 F1002). Self-checking; run INSIDE the private virtual KWin session
(Linux, the desktop's print portal) or the interactive Windows session:

    python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/print_probe.py --out DIR/print.json
    python print_probe.py --out print.json        (Windows: drives the system dialog with SendInput)

P01 opens the native print dialog and cancels it with Escape (the job settles `cancelled`; if the
dialog never appeared, Escape would reach the app and the job would not settle). P02 opens it
again and accepts with Enter: with no physical printer the default destination is the desktop's
print-to-PDF (KDE "Print to File", Windows "Microsoft Print to PDF", whose save dialog gets a
file name and Enter); the job settles `printed` and the PDF exists. P03 exports a PDF directly.
Files the dialog writes are removed. Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

from ui4me import App

HTML = "<style>@page{size:A5;margin:15mm} .b{break-before:page} h1{font:24px sans-serif}</style><h1>Print probe</h1><p>Page one.</p><p class=b>Page two.</p>"
WINDOWS = sys.platform == "win32"


def keys_factory():
    if WINDOWS:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        def send(vk=0, ch=None):
            for up in (0, 2):
                i = INPUT(type=1)
                if ch is not None:
                    i.ki = KEYBDINPUT(0, ord(ch), 0x0004 | up, 0, 0)  # KEYEVENTF_UNICODE
                else:
                    i.ki = KEYBDINPUT(vk, 0, up, 0, 0)
                user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
                time.sleep(0.03)

        return {"esc": lambda: send(0x1B), "enter": lambda: send(0x0D), "type": lambda s: [send(ch=c) for c in s], "output_file": None}
    sys.path.insert(0, str(Path(__file__).resolve().parent / "kwin"))
    from chat_journey import Input, build_fakeinput  # noqa: E402
    out = Path(tempfile.mkdtemp(prefix="ui4me-printprobe-"))
    fake = Input(build_fakeinput(out))
    def output_file(path: str) -> None:
        # KDE's dialog defaults "Print to File (PDF)" to a directory: click its Output file field
        # (the dialog is centred on the 1280 x 900 virtual output), select all, type a file path.
        fake("click 657 500")
        fake("kd 29")
        fake("key 30")
        fake("ku 29")
        fake(f"type {path}")
    return {"esc": lambda: fake("key 1"), "enter": lambda: fake("key 28"), "type": lambda s: fake(f"type {s}"), "output_file": output_file}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    keys = keys_factory()
    cases: list[dict] = []
    events: list[dict] = []
    home = Path.home()
    before = {p.name for p in home.glob("*.pdf")} | {p.name for p in (home / "Documents").glob("*.pdf")} if (home / "Documents").exists() else {p.name for p in home.glob("*.pdf")}

    def check(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})

    def wait(job, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            got = [e for e in list(events) if e.get("job") == job]
            if got:
                return got[0]
            time.sleep(0.1)
        return None

    with App() as app:
        w = app.open(HTML, title="ui4me print probe", width=420, height=300)
        app.on("print", events.append)

        def owner(fn):
            done = threading.Event()
            box = {}

            def run():
                try:
                    box["v"] = fn()
                except Exception as e:  # noqa: BLE001
                    box["v"] = {"error": f"{type(e).__name__}: {e}"}
                done.set()

            app.post(run)
            done.wait(60)
            return box.get("v")

        def driver():
            try:
                time.sleep(1.0)
                r = owner(lambda: w.print_document(title="ui4me print probe", dpi=150))
                time.sleep(5.0)
                keys["esc"]()
                e = wait(r.get("job"), 20)
                check("P01_dialog_cancel", r.get("status") == "started" and e is not None and e.get("status") == "cancelled", {"start": r, "event": e})
                r = owner(lambda: w.print_document(title="ui4meprobe", dpi=150))
                time.sleep(5.0)
                target = Path(tempfile.gettempdir()) / f"ui4me-print-{os.getpid()}.pdf"
                if keys["output_file"]:
                    keys["output_file"](str(target))
                    time.sleep(0.5)
                keys["enter"]()
                if WINDOWS:
                    # Microsoft Print to PDF asks for a file name.
                    time.sleep(4.0)
                    keys["type"](str(target))
                    time.sleep(0.5)
                    keys["enter"]()
                e = wait(r.get("job"), 60)
                written = []
                time.sleep(2.0)
                if target.exists():
                    written.append(target)
                else:
                    for d in (home, home / "Documents"):
                        for p in d.glob("*.pdf") if d.exists() else []:
                            if p.name not in before and time.time() - p.stat().st_mtime < 120:
                                written.append(p)
                head = written[0].read_bytes()[:5] if written else b""
                check("P02_dialog_print_to_pdf", e is not None and e.get("status") == "printed" and head == b"%PDF-",
                      {"start": r, "event": e, "files": [str(p) for p in written]})
                for p in written:
                    p.unlink(missing_ok=True)
                pdf = Path(tempfile.gettempdir()) / f"ui4me-export-{os.getpid()}.pdf"
                x = owner(lambda: w.export_pdf(pdf, dpi=96, title="probe"))
                check("P03_export_pdf", isinstance(x, dict) and x.get("pages") == 2 and pdf.read_bytes()[:5] == b"%PDF-", x)
                pdf.unlink(missing_ok=True)
            finally:
                app.post(app.stop)

        app.on("started", lambda _: threading.Thread(target=driver, daemon=True).start())
        app.timer(240_000, lambda _: app.stop())
        app.run()
    result = {"status": "passed" if len(cases) == 3 and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"], default=str)[:400])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
