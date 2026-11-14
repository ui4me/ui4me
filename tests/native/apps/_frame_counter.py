"""Diagnostic (test tooling): count host->backend frames by method/event type.

Imported by a journey when UI4ME_DIAG_FRAMES=<file>; a watchdog thread rewrites
the counts every 0.5 s so they survive a hang of the owner or reader thread.
"""
import collections
import json
import os
import threading
import time

PATH = os.environ.get("UI4ME_DIAG_FRAMES")
if PATH:
    PATH = f"{PATH}.{os.getpid()}"  # launcher and backend run the same script
counts: collections.Counter = collections.Counter()
recent: collections.deque = collections.deque(maxlen=40)


def install() -> None:
    if not PATH:
        return
    from ui4me_core import client
    original = client.read_frame

    def counting(stream):
        message = original(stream)
        if isinstance(message, dict):
            method = message.get("method") or ("response" if "id" in message else "?")
            params = message.get("params") or {}
            event = params.get("event") if isinstance(params, dict) else None
            kind = (event or {}).get("type") if isinstance(event, dict) else params.get("type") if isinstance(params, dict) else None
            key = f"{method}:{kind}" if kind else method
            counts[key] += 1
            recent.append((round(time.monotonic(), 3), key))
        return message
    client.read_frame = counting

    def watchdog():
        while True:
            time.sleep(0.5)
            try:
                with open(PATH, "w", encoding="utf-8") as f:
                    json.dump({"t": time.monotonic(), "counts": counts, "recent": list(recent)}, f)
            except OSError:
                pass
    threading.Thread(target=watchdog, daemon=True, name="frame-counter").start()


install()
