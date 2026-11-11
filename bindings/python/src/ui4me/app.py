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

# A C callback pointer cannot root a Python object. Explicit close releases this root.
_live_apps: dict[int, "App"] = {}


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
            if self._app._state in ("created", "running") and not self._app._stopping:
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
        self._token_lock = threading.Lock()
        self._native = library()
        self._state = "created"
        self._run_active = False
        self._stopping = False
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
        _live_apps[self._session] = self

    def _owner_only(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("UI commands belong to the creating thread; use app.post()")

    def _next_token(self) -> int:
        with self._token_lock:
            return next(self._sequence)

    def _active(self) -> None:
        self._owner_only()
        if self._state not in ("created", "running") or self._stopping:
            raise RuntimeError("Application session is stopping or terminal; create a fresh App")

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
        token = self._next_token()
        self._handlers[token] = (event, window, element, handler)
        return Subscription(self, token)

    def _opened(self, result: dict) -> Window:
        window = Window(self, result["window"])
        self._windows[window.id] = window
        return window

    def open(self, html: str, *, title: str = "ui4me", width: int = 640, height: int = 480,
             base_path=None) -> Window:
        """Open HTML. Relative assets require an explicit base directory."""
        command = {"op": "open", "title": title, "html": html, "width": width, "height": height}
        if base_path is not None:
            command["base_path"] = str(Path(base_path).resolve())
        return self._opened(self._command(command))

    def open_file(self, path, *, title: str = "ui4me", width: int = 640, height: int = 480) -> Window:
        """Load a document and resolve its assets against the file's directory."""
        return self._opened(self._command({"op": "open_file", "path": str(Path(path).resolve(strict=True)),
                                          "title": title, "width": width, "height": height}))

    def timer(self, milliseconds: int, handler: Callable[[dict], object], *, repeat: bool = False) -> Timer:
        self._active()
        if not callable(handler):
            raise TypeError("handler must be callable")
        token = self._next_token()
        self._command({"op": "timer", "token": token, "milliseconds": milliseconds, "repeat": repeat})
        self._timers[token] = (handler, repeat)
        return Timer(self, token)

    def post(self, callback: Callable[[], object]) -> Future:
        if not callable(callback):
            raise TypeError("callback must be callable")
        future = OwnerFuture(self._owner)
        with self._lock:
            if self._state not in ("created", "running") or self._stopping:
                future.set_exception(RuntimeError("Application is no longer accepting work"))
                return future
            if len(self._pending) >= 512:
                future.set_exception(Ui4meError("Deferred work queue is full"))
                return future
            token = self._next_token()
            self._pending[token] = (future, callback)
            # post/stop/destroy do not dispatch callbacks. Keep admission and
            # disposal linearized so an accepted post never uses a freed session.
            try:
                self._native.check(self._native.session_post(self._session, token))
                failure = None
            except BaseException as error:
                self._pending.pop(token, None)
                failure = error
        if failure is not None:
            future.set_exception(failure)
        return future

    def stop(self) -> None:
        with self._lock:
            if self._state in ("stopped", "closed"):
                return
            identifier = self._session
            self._stopping = True
            self._native.check(self._native.session_stop(identifier))

    def _dispatch(self, _session, raw, _user) -> int:
        try:
            event = json.loads(raw)
            kind = event["type"]
            if kind == "stopped":
                with self._lock:
                    self._stopping = True
                    self._state = "stopped"
            if kind == "closed":
                window = self._windows.pop(event.get("window"), None)
                if window:
                    window._closed = True
            if kind == "post":
                with self._lock:
                    entry = self._pending.pop(event["token"], None)
                if entry:
                    future, callback = entry
                    if future.set_running_or_notify_cancel():
                        try:
                            result = callback()
                        except BaseException as error:
                            future.set_exception(error)
                        else:
                            future.set_result(result)
            elif kind == "timer":
                entry = self._timers.get(event["token"])
                if entry:
                    handler, repeat = entry
                    if not repeat:
                        self._timers.pop(event["token"], None)
                    handler(event)
            veto = False
            for token in tuple(self._handlers):
                entry = self._handlers.get(token)
                if entry is None:
                    continue
                event_type, window_id, element_id, handler = entry
                if (event_type == kind and (window_id is None or window_id == event.get("window"))
                        and (element_id is None or element_id == event.get("element") or element_id in (event.get("path") or ()))):
                    if handler(event) is False and kind == "close_requested":
                        veto = True
            if kind == "closed":
                self._handlers = {key: item for key, item in self._handlers.items() if item[1] != event.get("window")}
            return 1 if veto else 0
        except BaseException as error:
            if self._callback_error is None:
                self._callback_error = error
            self._stopping = True
            # Stop is explicitly safe from a callback and does not replace the original exception.
            self._native.session_stop(self._session)
            return -1

    def run(self) -> None:
        self._owner_only()
        if self._state != "created":
            raise RuntimeError("Application is already running")
        previous_handler = None
        bridge = None
        install_signal = self._handle_sigint and threading.current_thread() is threading.main_thread() and not self._stopping
        if install_signal:
            # Reserve before changing the signal handler or session state. Failure is retryable.
            try:
                bridge = self.timer(100, lambda _: None, repeat=True)
            except (Ui4meError, RuntimeError):
                # A concurrent stop can win between the check and the native command.
                if not self._stopping:
                    raise
                install_signal = False
        if install_signal:
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
                    self._stopping = True
                    self._native.session_stop(self._session)

            signal.signal(signal.SIGINT, interrupt)
        with self._lock:
            self._state = "running"
            self._run_active = True
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
                self._run_active = False
                pending = list(self._pending.values())
                self._pending.clear()
            self._timers.clear()
            for window in self._windows.values():
                window._closed = True
            self._windows.clear()
            self._handlers.clear()
            for future, _ in pending:
                future.cancel()

    def stats(self) -> dict:
        self._owner_only()
        if self._state == "closed":
            raise RuntimeError("Application has been disposed")
        return self._native.command(self._session, {"op": "stats"})

    def close(self) -> None:
        self._owner_only()
        with self._lock:
            if self._state == "closed":
                return
            if self._run_active:
                raise RuntimeError("Call stop() during run(); close the App after run() returns")
            self._native.check(self._native.session_destroy(self._session))
            self._state = "closed"
            self._stopping = True
            pending = list(self._pending.values())
            self._pending.clear()
        self._handlers.clear()
        self._timers.clear()
        for window in self._windows.values():
            window._closed = True
        self._windows.clear()
        _live_apps.pop(self._session, None)
        for future, _ in pending:
            future.cancel()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        try:
            self.close()
        except Exception as cleanup_error:
            if exception is None:
                raise
            exception.add_note(f"Additional ui4me cleanup error: {cleanup_error}")


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

    def diagnostics(self) -> dict:
        """Return bounded document/resource/render diagnostics for this window."""
        return self._command("diagnostics")

    def set_value(self, element: str, value: str) -> None:
        self._command("set_value", element=element, value=value)

    def get_checked(self, element: str) -> bool:
        return self._command("get_checked", element=element)["checked"]

    def set_checked(self, element: str, checked: bool) -> None:
        if not isinstance(checked, bool):
            raise TypeError("checked must be bool")
        self._command("set_checked", element=element, checked=checked)

    def set_attribute(self, element: str, name: str, value: str) -> None:
        self._command("set_attribute", element=element, name=name, value=value)

    def remove_attribute(self, element: str, name: str) -> None:
        self._command("remove_attribute", element=element, name=name)

    def add_class(self, element: str, name: str) -> None:
        self._command("add_class", element=element, name=name)

    def remove_class(self, element: str, name: str) -> None:
        self._command("remove_class", element=element, name=name)

    def focus(self, element: str) -> None:
        self._command("focus", element=element)

    def replace_children_html(self, element: str, html: str) -> None:
        """Replace a subtree after validation; rejection leaves it unchanged."""
        self._command("replace_children_html", element=element, html=html)

    @property
    def closed(self) -> bool:
        return self._closed

    def set_title(self, title: str) -> None:
        self._command("set_title", title=title)

    def resize(self, width: int, height: int) -> None:
        self._command("resize", width=width, height=height)

    def snapshot(self, path) -> dict:
        return self._command("snapshot", path=str(Path(path).absolute()))

    def close(self) -> None:
        self._command("close")
