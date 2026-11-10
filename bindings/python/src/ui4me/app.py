from __future__ import annotations

from concurrent.futures import Future
import ctypes as C
import itertools
import json
from pathlib import Path
import signal
import threading
from typing import Callable

from ._native import CALLBACK, Ui4meError, library


class OwnerFuture(Future):
    """A synchronous wait on the owner thread cannot make the event loop progress."""
    def __init__(self, owner: int):
        super().__init__()
        self._owner = owner

    def result(self, timeout=None):
        if threading.get_ident() == self._owner and not self.done():
            raise RuntimeError("Do not wait for posted work on the UI owner thread")
        return super().result(timeout)

    def exception(self, timeout=None):
        if threading.get_ident() == self._owner and not self.done():
            raise RuntimeError("Do not wait for posted work on the UI owner thread")
        return super().exception(timeout)


class Subscription:
    def __init__(self, app: App, token: int):
        self._app, self._token = app, token

    def close(self) -> None:
        self._app._owner_only()
        self._app._handlers.pop(self._token, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Timer:
    def __init__(self, app: App, token: int):
        self._app, self.token = app, token

    def cancel(self) -> None:
        self._app._owner_only()
        if self.token in self._app._timers:
            if self._app._state in ("created", "running"):
                self._app._command({"op": "cancel_timer", "token": self.token})
            self._app._timers.pop(self.token, None)


class App:
    """Own one terminal application session. Create another App for the next session."""
    def __init__(self, *, backend: str = "native", app_id: str = "org.ui4me.app", handle_sigint: bool = True):
        if backend not in ("native", "headless"):
            raise ValueError("backend must be native or headless")
        if backend == "native" and threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Create and run native Python applications on the main thread")
        self._owner = threading.get_ident()
        self._backend = backend
        self._handle_sigint = handle_sigint
        self._lock = threading.Lock()
        self._native = library()
        self._state = "created"
        self._session = 0
        self._sequence = itertools.count(1)
        self._handlers: dict[int, tuple] = {}
        self._timers: dict[int, tuple] = {}
        self._pending: dict[int, tuple[Future, Callable]] = {}
        self._windows: dict[int, Window] = {}
        self._callback_error: BaseException | None = None
        self._callback_root = CALLBACK(self._dispatch)
        identifier = C.c_uint64()
        config = json.dumps({"backend": backend, "app_id": app_id}).encode("utf-8")
        self._native.check(self._native.session_create(config, self._callback_root, None, C.byref(identifier)))
        self._session = int(identifier.value)

    def _owner_only(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("UI commands belong to the creating thread; use app.post()")

    def _active(self) -> None:
        self._owner_only()
        if self._state not in ("created", "running"):
            raise RuntimeError(f"Application session is {self._state}; create a fresh App")

    def _command(self, command: dict) -> dict:
        self._active()
        return self._native.command(self._session, command)

    def on(self, event: str, handler: Callable[[dict], object]) -> Subscription:
        return self._subscribe(event, handler, None, None)

    def _subscribe(self, event, handler, window, element):
        self._active()
        if not callable(handler):
            raise TypeError("handler must be callable")
        if len(self._handlers) >= 512:
            raise Ui4meError("At most 512 subscriptions may be active")
        token = next(self._sequence)
        self._handlers[token] = (event, window, element, handler)
        return Subscription(self, token)

    def open(self, html: str, *, title: str = "ui4me", width: int = 640, height: int = 480) -> Window:
        result = self._command({"op": "open", "title": title, "html": html, "width": width, "height": height})
        window = Window(self, result["window"])
        self._windows[window.id] = window
        return window

    def open_file(self, path, **options) -> Window:
        return self.open(Path(path).read_text(encoding="utf-8"), **options)

    def timer(self, milliseconds: int, handler: Callable[[dict], object], *, repeat: bool = False) -> Timer:
        self._active()
        if not callable(handler):
            raise TypeError("handler must be callable")
        token = next(self._sequence)
        self._command({"op": "timer", "token": token, "milliseconds": milliseconds, "repeat": repeat})
        self._timers[token] = (handler, repeat)
        return Timer(self, token)

    def post(self, callback: Callable[[], object]) -> Future:
        if not callable(callback):
            raise TypeError("callback must be callable")
        future = OwnerFuture(self._owner)
        with self._lock:
            if self._state not in ("created", "running"):
                future.set_exception(RuntimeError("Application is no longer accepting work"))
                return future
            if len(self._pending) >= 512:
                future.set_exception(Ui4meError("Deferred work queue is full"))
                return future
            token = next(self._sequence)
            self._pending[token] = (future, callback)
        try:
            self._native.check(self._native.session_post(self._session, token))
        except BaseException as error:
            with self._lock:
                entry = self._pending.pop(token, None)
            if entry is not None and not future.done():
                future.set_exception(error)
        return future

    def stop(self) -> None:
        with self._lock:
            if self._state in ("stopped", "closed"):
                return
            identifier = self._session
        self._native.check(self._native.session_stop(identifier))

    def _dispatch(self, _session, raw, _user) -> int:
        try:
            event = json.loads(raw)
            kind = event["type"]
            if kind == "post":
                with self._lock:
                    entry = self._pending.pop(event["token"], None)
                if entry:
                    future, callback = entry
                    if future.set_running_or_notify_cancel():
                        try:
                            future.set_result(callback())
                        except BaseException as error:
                            future.set_exception(error)
            elif kind == "timer":
                entry = self._timers.get(event["token"])
                if entry:
                    handler, repeat = entry
                    if not repeat:
                        self._timers.pop(event["token"], None)
                    handler(event)
            veto = False
            for event_type, window_id, element_id, handler in tuple(self._handlers.values()):
                if (event_type == kind and (window_id is None or window_id == event.get("window"))
                        and (element_id is None or element_id == event.get("element"))):
                    if handler(event) is False and kind == "close_requested":
                        veto = True
            if kind == "closed":
                window = self._windows.pop(event.get("window"), None)
                if window:
                    window._closed = True
                self._handlers = {key: item for key, item in self._handlers.items() if item[1] != event.get("window")}
            return 1 if veto else 0
        except BaseException as error:
            if self._callback_error is None:
                self._callback_error = error
            # Stop is explicitly safe from a callback and does not replace the original exception.
            self._native.session_stop(self._session)
            return -1

    def run(self) -> None:
        self._active()
        if self._state != "created":
            raise RuntimeError("Application is already running")
        previous_handler = None
        bridge = None
        install_signal = self._handle_sigint and threading.current_thread() is threading.main_thread()
        if install_signal:
            # Reserve before changing the signal handler or session state. Failure is retryable.
            bridge = self.timer(100, lambda _: None, repeat=True)
            previous_handler = signal.getsignal(signal.SIGINT)

            def interrupt(signum, frame):
                try:
                    if callable(previous_handler):
                        previous_handler(signum, frame)
                    elif previous_handler == signal.SIG_DFL:
                        raise KeyboardInterrupt()
                except BaseException as error:
                    if self._callback_error is None:
                        self._callback_error = error
                    self._native.session_stop(self._session)

            signal.signal(signal.SIGINT, interrupt)
        self._state = "running"
        try:
            status = self._native.session_run(self._session)
            if self._callback_error is not None:
                raise self._callback_error
            self._native.check(status)
        finally:
            if install_signal:
                signal.signal(signal.SIGINT, previous_handler)
            with self._lock:
                self._state = "stopped"
                pending = list(self._pending.values())
                self._pending.clear()
            for future, _ in pending:
                future.cancel()
            self._timers.clear()
            for window in self._windows.values():
                window._closed = True
            self._windows.clear()
            self._handlers.clear()

    def stats(self) -> dict:
        return self._command({"op": "stats"})

    def close(self) -> None:
        self._owner_only()
        if self._state == "closed":
            return
        if self._state == "running":
            raise RuntimeError("Call stop() during run(); close the App after run() returns")
        self._native.check(self._native.session_destroy(self._session))
        with self._lock:
            self._state = "closed"
            pending = list(self._pending.values())
            self._pending.clear()
        for future, _ in pending:
            future.cancel()
        self._handlers.clear()
        self._timers.clear()
        for window in self._windows.values():
            window._closed = True
        self._windows.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Window:
    def __init__(self, app: App, identifier: int):
        self._app, self.id, self._closed = app, identifier, False

    def _command(self, operation: str, **args) -> dict:
        if self._closed:
            raise RuntimeError("Window is closed")
        return self._app._command({"op": operation, "window": self.id, **args})

    def on(self, event: str, handler: Callable[[dict], object], *, element: str | None = None) -> Subscription:
        if self._closed:
            raise RuntimeError("Window is closed")
        return self._app._subscribe(event, handler, self.id, element)

    def set_text(self, element: str, text: str) -> None:
        self._command("set_text", element=element, text=text)

    def get_value(self, element: str) -> str:
        return self._command("get_value", element=element)["value"]

    def set_title(self, title: str) -> None:
        self._command("set_title", title=title)

    def resize(self, width: int, height: int) -> None:
        self._command("resize", width=width, height=height)

    def snapshot(self, path) -> dict:
        return self._command("snapshot", path=str(Path(path).absolute()))

    def close(self) -> None:
        self._command("close")
