"""Run an unmodified example app natively, screenshot it and smoke its keyboard focus.

    python3 tests/native/linux/vkwin.py --out DIR -- python tests/native/apps/py_showcase.py examples/python/gallery.py

The example runs exactly as a user starts it (direct ``python app.py`` semantics; this
wrapper is the script Core relaunches). Once its window is up: screenshot, press Tab
through the first focusable controls (focus must move and stay inside the window),
check no callback errors were reported, then close it through the compositor; the
driver verifies exit status 0 and no leftover processes.
"""
import os
import runpy
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import Channel, on_owner  # noqa: E402

from ui4me._ui.app import UiApp  # noqa: E402

EXAMPLE = Path(sys.argv[1]).resolve()
SHOT = os.environ.get("UI4ME_SHOWCASE_SHOT", EXAMPLE.stem + ".png")
_run = UiApp.run


def scenario(app: UiApp, ch: Channel) -> None:
    title = app.title
    ch.request("wait-window", window=title, timeout=20)
    ch.request("move", window=title, x=4, y=4)  # park the pointer: no hover styles in the shot
    time.sleep(1.5)  # let data sources / timers paint once
    shot = ch.request("screenshot", window=title, name=SHOT)
    ch.check("showcase.screenshot", bool(shot.get("path")), shot)
    seen = []
    for _ in range(8):
        ch.request("key", key="tab", settle=0.15)
        focused = on_owner(app, lambda: (app.main.core.document.focused_element() or {}).get("element"))
        seen.append(focused)
    focusable = on_owner(app, lambda: app.main.core.query(
        "button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])"))
    want = min(3, len(focusable))  # small examples may have a single control
    ch.check("showcase.tab_moves_focus", len({f for f in seen if f}) >= want, {"seen": seen, "focusable": len(focusable)})
    ch.check("showcase.no_errors", on_owner(app, lambda: app.error_count) == 0,
             on_owner(app, lambda: app.last_error))
    ch.note("diagnostics", on_owner(app, app.diagnostics))
    ch.done()
    ch.request("native-close", window=title)
    time.sleep(10)
    ch.fatal("example did not exit after a native close")


def run(self: UiApp) -> None:
    if self.main is not None and not getattr(run, "started", False):
        run.started = True
        ch = Channel()

        def body():
            try:
                scenario(self, ch)
            except Exception as error:  # pragma: no cover - reported to the driver
                import traceback
                ch.fatal(f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
                ch.done()
                self.stop()
        self.after(0.8, lambda: threading.Thread(target=body, daemon=True).start())
    return _run(self)


UiApp.run = run
os.chdir(EXAMPLE.parent)
sys.argv = [str(EXAMPLE), *sys.argv[2:]]
runpy.run_path(str(EXAMPLE), run_name="__main__")
