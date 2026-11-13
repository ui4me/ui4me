"""App side of the native test channel (see tests/native/linux/vkwin.py).

Test apps run a *scenario* on a helper thread. The scenario asks the driver for
real compositor input with :meth:`Channel.request`, inspects the app through
``app.post(...)`` (owner thread) and records verdicts with :meth:`Channel.check`.
Never imported by the shipped package.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable


class Channel:
    def __init__(self, directory: str | None = None):
        directory = directory or os.environ.get("UI4ME_TEST_CHANNEL")
        if not directory:
            raise RuntimeError("UI4ME_TEST_CHANNEL is not set; run this app through a native driver")
        self.dir = Path(directory)
        self._next = 0
        self._lock = threading.Lock()
        self.failures = 0

    def _append(self, name: str, record: dict) -> None:
        with self._lock, (self.dir / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def request(self, action: str, timeout: float = 45.0, **fields: Any) -> dict:
        with self._lock:
            self._next += 1
            rid = self._next
        self._append("requests.jsonl", {"kind": "request", "id": rid, "action": action, **fields})
        acks = self.dir / "acks.jsonl"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if acks.exists():
                for line in acks.read_text(encoding="utf-8-sig").splitlines():
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if record.get("ack") == rid:
                        if not record.get("ok", True):
                            raise RuntimeError(f"driver could not {action}: {record.get('error')}")
                        return record
            time.sleep(0.05)
        raise TimeoutError(f"driver did not acknowledge {action} #{rid}")

    def check(self, name: str, ok: Any, detail: Any = None) -> bool:
        ok = bool(ok)
        if not ok:
            self.failures += 1
        self._append("results.jsonl", {"kind": "check", "name": name, "status": "passed" if ok else "failed",
                                       "detail": detail})
        return ok

    def note(self, name: str, detail: Any) -> None:
        self._append("results.jsonl", {"kind": "note", "name": name, "detail": detail})

    def fatal(self, message: str) -> None:
        self._append("results.jsonl", {"kind": "fatal", "message": message})

    def done(self) -> None:
        self._append("results.jsonl", {"kind": "done", "failures": self.failures})


def on_owner(app, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
    """Run ``fn`` on the UI owner thread and return its result."""
    return app.post(fn).result(timeout)


def until(app, predicate: Callable[[], Any], timeout: float = 10.0, step: float = 0.05) -> Any:
    """Poll ``predicate`` on the owner thread until truthy; returns the last value."""
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = on_owner(app, predicate)
        if value:
            return value
        time.sleep(step)
    return value


def rect(window, element_id: str) -> dict:
    """Viewport rectangle (CSS px) of an element in a UiWindow, from the real Core layout."""
    def read():
        window.commit()
        return window.core.document.command("get_rect", element=element_id).get("rect")
    return on_owner(window.app, read)


def center(window, element_id: str, dx: float = 0, dy: float = 0) -> tuple[float, float]:
    r = rect(window, element_id)
    if not r:
        raise RuntimeError(f"element {element_id} has no layout box")
    return r["x"] + min(r["width"] / 2, 40) + dx, r["y"] + r["height"] / 2 + dy


def run_scenario(app, scenario: Callable[[Channel], None], *, delay: float = 0.6) -> Channel:
    """Start ``scenario(channel)`` on a helper thread once the app runs; stop the app afterwards."""
    channel = Channel()

    def body():
        try:
            scenario(channel)
        except Exception as error:
            channel.fatal(f"{type(error).__name__}: {error}\n{traceback.format_exc()}")
        finally:
            channel.done()
            try:
                app.stop()
            except Exception:
                pass

    app.after(delay, lambda: threading.Thread(target=body, name="ui4me-test-scenario", daemon=True).start())
    return channel
