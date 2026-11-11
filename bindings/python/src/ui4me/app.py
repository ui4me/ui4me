from __future__ import annotations

from collections import deque
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import ctypes as C
import itertools
import json
import os
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


class Task:
    """One background computation started by ``App.run_in_background``.

    ``fn`` runs on a worker thread and never touches UI objects. Its outcome is delivered to
    ``on_done`` / ``on_error`` (or ``on_cancel``) on the owner thread, in completion order, at
    most once. States: pending, running, succeeded, failed, cancelled."""
    def __init__(self, app: "App", fn, args, on_done, on_error, on_cancel, pass_task):
        self._app, self._fn, self._args = app, fn, args
        self._on_done, self._on_error, self._on_cancel = on_done, on_error, on_cancel
        self._pass_task = pass_task
        self._event = threading.Event()
        self._cancel = threading.Event()
        self._value = None
        self._error: BaseException | None = None
        self.state = "pending"
        self.sequence = 0  # completion order among tasks that ran to an outcome
        self.delivered = False
        self.callback_error: BaseException | None = None

    @property
    def cancelled(self) -> bool:
        """Cooperative flag: long-running work should poll this and return early."""
        return self._cancel.is_set()

    @property
    def done(self) -> bool:
        """The outcome is final (callbacks may still be queued; see ``delivered``)."""
        return self._event.is_set()

    def cancel(self) -> bool:
        """Cancel a pending task at once; ask a running task to stop via ``cancelled``.
        Returns False when the outcome is already final."""
        settle = False
        with self._app._task_lock:
            if self._event.is_set():
                return False
            self._cancel.set()
            if self.state == "pending":
                self.state = "cancelled"
                self._event.set()
                settle = True
        if settle:
            self._app._enqueue_settlement(self)
        return True

    def result(self, timeout: float | None = None):
        """Wait from a non-owner thread. Raises the task's exception or CancelledError."""
        if threading.get_ident() == self._app._owner and not self._event.is_set():
            raise RuntimeError("Do not wait for background work on the UI owner thread")
        if not self._event.wait(timeout):
            raise TimeoutError("Background task did not finish in time")
        if self.state == "cancelled":
            raise CancelledError()
        if self.state == "failed":
            raise self._error
        return self._value

    def _run(self) -> None:
        with self._app._task_lock:
            if self.state != "pending":
                return
            self.state = "running"
        value = error = None
        try:
            value = self._fn(self, *self._args) if self._pass_task else self._fn(*self._args)
        except BaseException as caught:
            error = caught
        with self._app._task_lock:
            if self._cancel.is_set():
                self.state = "cancelled"
            elif error is not None:
                self.state, self._error = "failed", error
            else:
                self.state, self._value = "succeeded", value
            self.sequence = next(self._app._completion_counter)
            self._event.set()
            # Same critical section: settlement order is exactly completion order.
            self._app._enqueue_settlement(self)

    def _deliver(self) -> None:
        """Owner thread. Never raises: a failing callback is recorded, not allowed to kill the loop."""
        app = self._app
        with app._task_lock:
            app._tasks.discard(self)
        if app._stopping or app._tasks_closed:
            return
        self.delivered = True
        state = self.state
        handler, argument = ((self._on_done, self._value) if state == "succeeded"
                             else (self._on_error, self._error) if state == "failed"
                             else (self._on_cancel, None))
        if handler is None:
            return
        try:
            handler(argument) if state != "cancelled" else handler()
        except BaseException as caught:
            self.callback_error = caught


class App:
    """Own one terminal application session. Create another App for the next session."""
    def __init__(self, *, backend: str = "native", app_id: str = "org.ui4me.app", handle_sigint: bool = True,
                 background_workers: int = 4, max_background_tasks: int = 1024):
        if backend not in ("native", "headless"):
            raise ValueError("backend must be native or headless")
        if backend == "native" and threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Create and run native Python applications on the main thread")
        if background_workers < 1 or max_background_tasks < 1:
            raise ValueError("background_workers and max_background_tasks must be positive")
        self._owner = threading.get_ident()
        self._backend = backend
        self._background_workers = background_workers
        self._max_background_tasks = max_background_tasks
        self._task_lock = threading.Lock()
        self._completion_counter = itertools.count(1)
        self._tasks: set[Task] = set()
        self._tasks_closed = False
        self._executor: ThreadPoolExecutor | None = None
        self._settle = threading.Condition(threading.Lock())
        self._settle_queue: deque[Task] = deque()
        self._settle_thread: threading.Thread | None = None
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

    def run_in_background(self, fn, *args, on_done=None, on_error=None, on_cancel=None,
                          pass_task: bool = False) -> Task:
        """Run ``fn(*args)`` on a bounded worker pool (``background_workers``, default 4).

        The outcome is delivered on the owner thread through ``post`` while ``run()`` is active:
        ``on_done(result)`` or ``on_error(exception)``, or ``on_cancel()`` after ``Task.cancel()``.
        Never more than one of them. Callable from any thread. With ``pass_task=True`` the worker
        receives the Task first so it can poll ``task.cancelled``. When the native post queue is
        full the delivery waits with backoff (never dropped); at most ``max_background_tasks``
        unsettled tasks are accepted (Ui4meError otherwise). Tasks unfinished at ``stop()`` become
        cancelled and no callback runs once the app is stopping."""
        if not callable(fn):
            raise TypeError("fn must be callable")
        for handler in (on_done, on_error, on_cancel):
            if handler is not None and not callable(handler):
                raise TypeError("callbacks must be callable")
        task = Task(self, fn, args, on_done, on_error, on_cancel, pass_task)
        with self._task_lock:
            if self._tasks_closed or self._stopping or self._state not in ("created", "running"):
                raise RuntimeError("Application is no longer accepting work")
            if len(self._tasks) >= self._max_background_tasks:
                raise Ui4meError("Background task limit reached (%d)" % self._max_background_tasks)
            if self._executor is None:
                self._executor = ThreadPoolExecutor(self._background_workers, thread_name_prefix="ui4me-bg")
            self._tasks.add(task)
            self._executor.submit(task._run)
        return task

    def _enqueue_settlement(self, task: Task) -> None:
        with self._settle:
            if self._tasks_closed:
                return
            self._settle_queue.append(task)
            if self._settle_thread is None:
                self._settle_thread = threading.Thread(target=self._settle_loop, name="ui4me-settle", daemon=True)
                self._settle_thread.start()
            self._settle.notify()

    def _settle_loop(self) -> None:
        delay = 0.001
        while True:
            with self._settle:
                while not self._settle_queue and not self._tasks_closed:
                    self._settle.wait()
                if self._tasks_closed:
                    return
                task = self._settle_queue[0]
            future = self.post(task._deliver)
            failure = future.exception() if future.done() and not future.cancelled() else None
            if failure is not None:
                if "full" in str(failure):
                    # Queue pressure: keep order, back off, retry. Nothing is dropped.
                    with self._settle:
                        if not self._tasks_closed:
                            self._settle.wait(delay)
                    delay = min(delay * 2, 0.05)
                    continue
                # Not accepting work any more (stopping/terminal): outcomes stay observable
                # on the Task, callbacks are discarded.
                self._discard_settlements()
                return
            delay = 0.001
            with self._settle:
                if self._settle_queue and self._settle_queue[0] is task:
                    self._settle_queue.popleft()

    def _discard_settlements(self) -> None:
        with self._settle:
            queued = list(self._settle_queue)
            self._settle_queue.clear()
            self._settle_thread = None
        with self._task_lock:
            for task in queued:
                self._tasks.discard(task)

    def _shutdown_tasks(self, wait: bool) -> None:
        """Cancel everything unfinished. Pending tasks never start; running ones see ``cancelled``."""
        with self._task_lock:
            self._tasks_closed = True
            tasks = list(self._tasks)
            executor = self._executor
            for task in tasks:
                if not task._event.is_set():
                    task._cancel.set()
                    if task.state == "pending":
                        task.state = "cancelled"
                        task._event.set()
            self._tasks.clear()
        with self._settle:
            self._settle_queue.clear()
            thread, self._settle_thread = self._settle_thread, None
            self._settle.notify_all()
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)
        if wait and thread is not None and thread is not threading.current_thread():
            thread.join()

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
            self._shutdown_tasks(wait=False)

    def monitors(self) -> list[dict]:
        """Monitors seen by the native backend (empty for headless): name, physical size,
        scale, position (None on Wayland), refresh rate and primary flag."""
        return self._command({"op": "list_monitors"})["monitors"]

    def claim_instance(self, open_files=()) -> dict:
        """Opt in to a single instance per user for this ``app_id``. The first instance gets
        ``{"primary": True}`` and later receives other instances' paths as ``open_files`` events
        (``source == "second_instance"``; its own ``open_files`` arrive with ``"startup"``). A
        later instance forwards ``open_files`` and gets ``{"primary": False}`` — it should exit.
        Paths are data only; Core installs no file associations."""
        return self._command({"op": "claim_instance", "open_files": [str(Path(p).absolute()) for p in open_files]})

    def notify(self, title: str, body: str = "", *, icon=None, urgency: str | None = None,
               actions: list[tuple[str, str]] | tuple = (), on_event: Callable[[dict], object] | None = None) -> dict:
        """Show a native system notification. Returns ``{"status": "sent" | "unsupported" |
        "unavailable" | "denied", "token", "reason"?}``; ``on_event`` receives its
        ``notification`` events (``clicked``, ``action`` with ``action``, ``dismissed``,
        ``expired``). ``actions`` are ``(id, label)`` buttons where the platform offers them."""
        token = self._next_token()
        args: dict = {"op": "notify", "token": token, "title": title, "body": body,
                      "actions": [{"id": i, "label": l} for i, l in actions]}
        if icon is not None:
            args["icon"] = str(Path(icon).absolute())
        if urgency is not None:
            args["urgency"] = urgency
        if on_event is not None:
            def handler(event: dict) -> None:
                if event.get("token") == token:
                    on_event(event)
            self.on("notification", handler)
        return self._command(args)

    def close_notification(self, token: int) -> None:
        self._command({"op": "close_notification", "token": token})

    def set_tray(self, *, icon=None, tooltip: str = "", menu: list[dict] | None = None) -> dict:
        """Create or update the application's tray/status icon (PNG ``icon``, ``menu`` items as
        for :meth:`Window.set_menu`). Activations arrive as ``tray`` events, menu choices as
        ``menu_command`` with ``source == "tray"``. Returns ``{"status", "reason"?}``."""
        args: dict = {"op": "set_tray", "tooltip": tooltip, "menu": menu or []}
        if icon is not None:
            args["icon"] = str(Path(icon).absolute())
        return self._command(args)

    def remove_tray(self) -> dict:
        return self._command({"op": "remove_tray"})

    def register_hotkey(self, id: str, accelerator: str) -> dict:
        """Register a global shortcut such as ``"Ctrl+Alt+K"``; presses arrive as ``hotkey``
        events with ``id``. Returns ``{"status": "registered" | "conflict" | "denied" |
        "unsupported" | "unavailable", "reason"?}``; shortcuts end with the session."""
        return self._command({"op": "register_hotkey", "id": id, "accelerator": accelerator})

    def unregister_hotkey(self, id: str) -> None:
        self._command({"op": "unregister_hotkey", "id": id})

    def set_link_policy(self, schemes: list[str] | tuple[str, ...] = (), *, hosts: list[str] | None = None,
                        open: bool = False) -> None:
        """Allow activated links (``link_activated`` events) by scheme (``https``, ``http``,
        ``mailto`` only) and, for http(s), by host (``example.com`` or ``*.example.com``); with
        ``open=True`` Core opens allowed links with the OS handler. Default: nothing allowed.
        Core never navigates the document."""
        self._command({"op": "set_link_policy", "schemes": list(schemes), "hosts": hosts, "open": open})

    def capabilities(self) -> dict:
        """What this backend and platform offer: ``{"platform", "backend", "features"}`` where each
        feature is ``{"status": "supported" | "unsupported" | "denied" | "unavailable" | "unknown",
        "reason": ...}``. Native platform details are known once ``run()`` has started."""
        return self._command({"op": "capabilities"})

    def stats(self) -> dict:
        self._owner_only()
        if self._state == "closed":
            raise RuntimeError("Application has been disposed")
        return self._native.command(self._session, {"op": "stats"})

    def close(self) -> None:
        self._owner_only()
        if self._state == "closed":
            return
        if self._run_active:
            raise RuntimeError("Call stop() during run(); close the App after run() returns")
        # Join workers first: running tasks must observe task.cancelled to return promptly.
        self._shutdown_tasks(wait=True)
        with self._lock:
            if self._state == "closed":
                return
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

    def insert_html(self, element: str, position: str, html: str) -> None:
        """Insert a validated fragment at an ``insertAdjacentHTML`` position.

        ``position`` is ``beforebegin``, ``afterbegin``, ``beforeend`` or ``afterend``.
        A rejected fragment (duplicate ID, active content, limits) changes nothing.
        """
        self._command("insert_html", element=element, position=position, html=html)

    def append_html(self, element: str, html: str) -> None:
        self.insert_html(element, "beforeend", html)

    def prepend_html(self, element: str, html: str) -> None:
        self.insert_html(element, "afterbegin", html)

    def insert_html_before(self, element: str, html: str) -> None:
        self.insert_html(element, "beforebegin", html)

    def insert_html_after(self, element: str, html: str) -> None:
        self.insert_html(element, "afterend", html)

    def append_text(self, element: str, text: str) -> None:
        """Append a literal text chunk (up to 16 KiB) at the end of ``element``; for streaming."""
        self._command("append_text", element=element, text=text)

    def trim_children(self, element: str, keep: int, *, from_: str = "start") -> None:
        """Keep at most ``keep`` element children, removing the oldest (``start``) or newest (``end``)."""
        self._command("trim_children", element=element, keep=int(keep), **{"from": from_})

    def remove_element(self, element: str) -> None:
        """Remove an element and its subtree; its ID becomes free for reuse."""
        self._command("remove_element", element=element)

    def move_element(self, element: str, target: str, position: str = "beforeend") -> None:
        """Move an element relative to ``target``, keeping its values and focus."""
        self._command("move_element", element=element, target=target, position=position)

    def get_text(self, element: str) -> str:
        return self._command("get_text", element=element)["text"]

    def get_attribute(self, element: str, name: str) -> str | None:
        return self._command("get_attribute", element=element, name=name)["value"]

    def get_attributes(self, element: str) -> dict[str, str]:
        return self._command("get_attributes", element=element)["attributes"]

    def has_element(self, element: str) -> bool:
        return self._command("has_element", element=element)["exists"]

    def query(self, selector: str, *, limit: int = 1024) -> list[str]:
        """IDs of identified elements matching a CSS selector, in document order."""
        return self._command("query", selector=selector, limit=limit)["elements"]

    def batch(self, operations: list[dict]) -> None:
        """Apply DOM operations atomically with one invalidation.

        Each operation is a dict with ``op`` (``set_text``, ``set_attribute``,
        ``remove_attribute``, ``add_class``, ``remove_class``, ``insert_html``,
        ``replace_children_html``, ``remove_element``, ``move_element``) and that
        command's fields. Any failure rolls back every operation; the error names its index.
        """
        ops = [dict(op) for op in operations]
        self._command("batch", ops=ops)

    def set_default_action(self, element: str, event: str, *, prevent: bool = True,
                           key: str | None = None, shift: bool | None = None,
                           ctrl: bool | None = None, alt: bool | None = None,
                           meta: bool | None = None) -> None:
        """Cancel (or stop cancelling) the default action of ``event`` at or inside ``element``.

        Handlers run after dispatch and cannot cancel; register the rule up front.
        ``key`` and modifier filters are exact when given. Delivered events include
        ``default_prevented``.
        """
        filters = {name: value for name, value in
                   (("key", key), ("shift", shift), ("ctrl", ctrl), ("alt", alt), ("meta", meta))
                   if value is not None}
        self._command("set_default_action", element=element, event=event, prevent=bool(prevent), **filters)

    def get_validity(self, element: str) -> dict:
        """Constraint validity of a control: ``{valid, flags, message, will_validate}``.

        ``flags`` has ``valueMissing``, ``typeMismatch``, ``patternMismatch``, ``tooLong``,
        ``tooShort``, ``rangeUnderflow``, ``rangeOverflow``, ``stepMismatch``, ``badInput``.
        Fires no events. The message is fixed English text.
        """
        return self._command("get_validity", element=element)

    def check_validity(self, element: str) -> dict:
        """``checkValidity()`` of a form or control: fires a non-bubbling ``invalid`` event at each
        invalid control and returns ``{valid, invalid: [ids], count}``. Never submits."""
        return self._command("check_validity", element=element)

    def get_scroll(self, element: str | None = None) -> dict:
        """Scroll offset/range/scrollport in CSS px of ``element`` (``None`` = viewport)."""
        args = {} if element is None else {"element": element}
        return self._command("get_scroll", **args)

    def scroll_to(self, element: str | None = None, *, x: float | None = None, y: float | None = None,
                  behavior: str | None = None) -> dict:
        """Scroll ``element`` (``None`` = viewport) to ``x``/``y`` (an omitted axis keeps its offset).
        ``behavior`` is ``"auto"`` (the element's CSS ``scroll-behavior``), ``"instant"`` or
        ``"smooth"``; smooth scrolling runs on the owner clock (the result's ``animating`` says so),
        a user scroll cancels it and reduced motion makes it instant. Snaps per ``scroll-snap-type``."""
        args = {key: value for key, value in (("element", element), ("x", x), ("y", y), ("behavior", behavior))
                if value is not None}
        return self._command("scroll_to", **args)

    def scroll_by(self, element: str | None = None, *, dx: float = 0.0, dy: float = 0.0,
                  behavior: str | None = None) -> dict:
        args = {"dx": float(dx), "dy": float(dy)}
        if element is not None:
            args["element"] = element
        if behavior is not None:
            args["behavior"] = behavior
        return self._command("scroll_by", **args)

    def scroll_into_view(self, element: str, *, block: str = "nearest", inline: str = "nearest",
                         behavior: str | None = None) -> None:
        args = {"element": element, "block": block, "inline": inline}
        if behavior is not None:
            args["behavior"] = behavior
        self._command("scroll_into_view", **args)

    def set_menu(self, menu: list[dict] | None) -> dict:
        """Set (or clear with ``None``) the window's menu: items ``{"id", "label", "enabled",
        "checked", "accelerator"}``, ``{"separator": True}`` or ``{"label", "items": [...]}``.
        Accelerators (``"Ctrl+S"``) work on every platform; the native menu bar where the
        platform has one (``status``). Choices arrive as ``menu_command`` events."""
        return self._command("set_menu", menu=menu)

    def set_pointer_grab(self, mode: str, *, cursor_visible: bool = True) -> dict:
        """Confine (``"confined"``) or lock (``"locked"``) the pointer to the focused window, or
        release it (``"none"``); the outcome arrives as a ``pointer_grab`` event (a platform may
        refuse a mode). A grab is released when the window loses the focus."""
        return self._command("set_pointer_grab", mode=mode, cursor_visible=cursor_visible)

    def show_context_menu(self, x: float, y: float, menu: list[dict]) -> dict:
        """Show a native context menu at viewport CSS px; the choice arrives as
        ``menu_command`` with ``source == "context"``."""
        return self._command("show_context_menu", x=x, y=y, menu=menu)

    def get_html(self, element: str | None = None, *, node: str | None = None, outer: bool = False) -> str:
        """Serialize an element (by ``id``), a node reference, or the whole document; ``outer``
        includes the node itself. Control values typed by the user are not markup."""
        return self._command("get_html", element=element, node=node, outer=outer)["html"]

    def text_rects(self, element: str | None = None, *, node: str | None = None,
                   start: int | None = None, end: int | None = None) -> dict:
        """The rendered ``text`` of an element (what selecting it copies), its ``length`` in
        UTF-16 units and the viewport ``rects`` (``x``, ``y``, ``width``, ``height``,
        ``visible``) of the range ``start..end`` of that text (default: all of it)."""
        return self._command("text_rects", element=element, node=node, start=start, end=end)

    def text_at_point(self, x: float, y: float) -> dict | None:
        """The text under a viewport point: ``element`` (nearest identified ancestor), ``offset``
        (UTF-16, in that element's rendered text) and ``block``; ``None`` without text."""
        return self._command("text_at_point", x=x, y=y)["hit"]

    def computed_style(self, element: str | None = None, *properties: str, node: str | None = None) -> dict:
        """Computed values (schema 1) of up to 64 properties: ``{name: {"status": "supported",
        "value", "inherited"} | {"status": "unsupported", "feature"} | {"status": "invalid",
        "reason"}}``."""
        return self._command("get_computed_style", element=element, node=node, properties=list(properties))["properties"]

    def get_diagnostics(self, redact: bool = True, since: int | None = None, kinds=None) -> dict:
        """Developer diagnostics (schema 1): ``{"schema": 1, "items": [{"seq", "kind", "code",
        "stage", "message", "count", "feature"?, "element"?}], "dropped"}``. ``kind`` is one of
        css_unsupported, stale_reference, layout, paint, resource, text, command. ``since`` is the
        highest ``seq`` already seen. Paths and URL queries are redacted unless ``redact=False``."""
        return self._command("get_diagnostics", redact=redact, since=since,
                             kinds=None if kinds is None else list(kinds))

    def explain(self, element: str, property: str | None = None) -> dict:
        """Why a CSS property has no effect on an element: ``{"schema": 1, "property", "element",
        "status": "applied" | "unsupported" | "overridden" | "not_applicable" | "unknown_property",
        "reason", "value"?, "feature"?}``. An unknown or removed element answers
        ``{"status": "stale_reference", ...}``. Without ``property`` the element state and its
        inline declarations are explained."""
        return self._command("explain", element=element, property=property)

    def get_files(self, element: str) -> list[str]:
        """The paths the user chose in a file input (its ``change`` event carries them as
        ``files``; ``cancel`` fires when the picker is dismissed)."""
        return self._command("get_files", element=element)["files"]

    def add_stylesheet(self, css: str) -> dict:
        """Attach an author stylesheet after the document's own; returns ``{"sheet": id,
        "diagnostics": [...]}`` (invalid rules are reported and dropped)."""
        return self._command("add_stylesheet", css=css)

    def replace_stylesheet(self, sheet: int, css: str) -> dict:
        return self._command("replace_stylesheet", sheet=sheet, css=css)

    def remove_stylesheet(self, sheet: int) -> None:
        self._command("remove_stylesheet", sheet=sheet)

    def stylesheets(self) -> list[dict]:
        """Stylesheet sources in cascade order: ``style``/``link`` elements, then attached sheets."""
        return self._command("list_stylesheets")["sheets"]

    def node_of(self, element: str | None = None) -> str:
        """The node reference (``node:<index>:<generation>``) of an element, or of the document."""
        return self._command("node_of", element=element)["node"]

    def get_node(self, node: str) -> dict:
        """One node: ``type``, ``name``, ``id``, ``attributes``, ``text``, ``parent``,
        ``previous``, ``next``, ``child_count`` (and ``content`` of a template). A removed
        node's reference is a stale-handle error."""
        return self._command("get_node", node=node)

    def node_children(self, node: str, *, offset: int = 0, limit: int = 256) -> dict:
        """``{"children": [{"node", "type", "name", "id"}...], "total"}`` (limit 1..4096)."""
        return self._command("node_children", node=node, offset=offset, limit=limit)

    def set_environment(self, *, color_scheme: str | None = None, reduced_motion: str | None = None) -> dict:
        """Override media preferences: ``color_scheme`` ``light``/``dark``/``system`` and
        ``reduced_motion`` ``reduce``/``no-preference``/``system`` (``None`` leaves one as it is).
        The document restyles in place; returns :meth:`environment`."""
        return self._command("set_environment", color_scheme=color_scheme, reduced_motion=reduced_motion)

    def environment(self) -> dict:
        """Media preferences in force and their source (``system``, ``app`` or ``default``):
        ``color_scheme``, ``system_color_scheme``, ``reduced_motion`` and ``scale``. The window
        emits ``environment_changed`` when an OS theme change alters them."""
        return self._command("get_environment")

    def get_rect(self, element: str) -> dict | None:
        """Border box in viewport CSS px (``x``, ``y``, ``width``, ``height``) or ``None``."""
        return self._command("get_rect", element=element)["rect"]

    def set_scroll_follow(self, element: str | None = None, follow: bool = True) -> None:
        """Keep a container at its end while content grows, unless the user scrolled away."""
        args = {"follow": bool(follow)}
        if element is not None:
            args["element"] = element
        self._command("set_scroll_follow", **args)

    def get_selection(self) -> str:
        """The document text selection (paragraphs joined by a line feed); '' if none."""
        return self._command("get_selection")["text"]

    def clear_selection(self) -> None:
        self._command("clear_selection")

    def select_text(self, element: str | None = None) -> None:
        """Select the document text inside ``element`` (all text for ``None``)."""
        args = {} if element is None else {"element": element}
        self._command("select_text", **args)

    def copy_selection(self) -> str:
        """Copy the document selection to the clipboard; returns the copied text."""
        return self._command("copy_selection")["text"]

    def set_clipboard_html(self, html: str, text: str = "") -> None:
        """Put HTML on the clipboard with ``text`` as its plain-text alternative."""
        self._command("set_clipboard_html", html=html, text=text)

    def get_clipboard_html(self, *, raw: bool = False) -> str | None:
        """The clipboard's HTML, sanitized for insertion (scripts, styles, handlers and unsafe
        URLs removed) unless ``raw``; ``None`` when there is no HTML flavour."""
        return self._command("get_clipboard_html", raw=raw)["html"]

    def get_clipboard_text(self) -> str | None:
        return self._command("get_clipboard_text")["text"]

    def set_clipboard_text(self, text: str) -> None:
        self._command("set_clipboard_text", text=text)

    def window_action(self, action: str) -> dict:
        """``show``, ``hide``, ``focus``, ``minimize``, ``maximize``, ``restore``, ``fullscreen``
        or ``exit_fullscreen``. Returns ``{"applied": bool, "platform": ...}``; where the
        platform forbids it (for example focus or hide on Wayland) ``applied`` is False and
        ``unsupported`` gives the reason. Observe the outcome with :meth:`state`."""
        return self._command("window_action", action=action)

    def show(self) -> dict:
        return self.window_action("show")

    def hide(self) -> dict:
        return self.window_action("hide")

    def activate(self) -> dict:
        return self.window_action("focus")

    def minimize(self) -> dict:
        return self.window_action("minimize")

    def maximize(self) -> dict:
        return self.window_action("maximize")

    def restore(self) -> dict:
        return self.window_action("restore")

    def set_fullscreen(self, fullscreen: bool = True) -> dict:
        return self.window_action("fullscreen" if fullscreen else "exit_fullscreen")

    def set_constraints(self, *, min_size: tuple[int, int] | None = None,
                        max_size: tuple[int, int] | None = None, resizable: bool = True) -> dict:
        args: dict = {"resizable": bool(resizable)}
        if min_size:
            args.update(min_width=int(min_size[0]), min_height=int(min_size[1]))
        if max_size:
            args.update(max_width=int(max_size[0]), max_height=int(max_size[1]))
        return self._command("set_window_constraints", **args)

    def set_icon(self, path=None) -> dict:
        """Window icon from a PNG (≤ 256×256, ≤ 1 MiB); ``None`` clears it."""
        args = {} if path is None else {"path": str(Path(path).absolute())}
        return self._command("set_window_icon", **args)

    def state(self) -> dict:
        """Observed state: visible, focused, minimized, maximized, fullscreen (None when the
        platform does not report it), size in CSS px and pixels, scale, monitor, constraints."""
        return self._command("get_window_state")

    def file_dialog(self, kind: str, callback: Callable[[dict], object], *, title: str | None = None,
                    directory=None, file_name: str | None = None, filters=None) -> int:
        """Open a native ``open``/``open_multiple``/``save``/``folder`` dialog without blocking.

        ``callback`` runs once on the UI owner with ``{"paths": [...]}`` or ``{"paths": None}``
        when cancelled (plus ``"error"`` if the platform failed). ``filters`` maps a label to
        extensions without dots, e.g. ``{"Images": ["png", "jpg"]}``.
        """
        if self._closed:
            raise RuntimeError("Window is closed")
        token = self._app._next_token()
        holder: dict = {}

        def handler(event: dict) -> None:
            if event.get("token") != token:
                return
            holder["subscription"].close()
            callback({k: event[k] for k in ("paths", "error") if k in event})

        holder["subscription"] = self.on("file_dialog", handler)
        args: dict = {"token": token, "kind": kind}
        if title is not None:
            args["title"] = title
        if directory is not None:
            args["directory"] = str(Path(directory).absolute())
        if file_name is not None:
            args["file_name"] = file_name
        if filters:
            items = filters.items() if isinstance(filters, dict) else filters
            args["filters"] = [{"name": name, "extensions": list(exts)} for name, exts in items]
        try:
            self._command("file_dialog", **args)
        except BaseException:
            holder["subscription"].close()
            raise
        return token

    def open_file_dialog(self, callback, *, multiple: bool = False, **options) -> int:
        return self.file_dialog("open_multiple" if multiple else "open", callback, **options)

    def save_file_dialog(self, callback, **options) -> int:
        return self.file_dialog("save", callback, **options)

    def folder_dialog(self, callback, **options) -> int:
        return self.file_dialog("folder", callback, **options)

    def accessibility_tree(self) -> dict:
        """The semantic tree exposed to screen readers (roles, names, states, values, bounds)."""
        return self._command("get_accessibility_tree")["tree"]

    def show_dialog(self, element: str, *, modal: bool = True) -> None:
        """Open a ``<dialog>``; a modal one traps focus and makes the rest inert until closed."""
        self._command("show_dialog", element=element, modal=bool(modal))

    def close_dialog(self, element: str, return_value: str | None = None) -> None:
        args = {} if return_value is None else {"return_value": return_value}
        self._command("close_dialog", element=element, **args)

    def get_dialog(self, element: str) -> dict:
        """``{"open": bool, "modal": bool, "return_value": str}``."""
        return self._command("get_dialog", element=element)

    def show_popover(self, element: str) -> None:
        """Show an element with a ``popover`` attribute (top layer; ``beforetoggle`` / ``toggle`` fire)."""
        self._command("show_popover", element=element)

    def hide_popover(self, element: str) -> None:
        """Hide a popover; hiding an ``auto`` popover also hides the popovers above it."""
        self._command("hide_popover", element=element)

    def toggle_popover(self, element: str) -> bool:
        """Toggle a popover; returns whether it is showing afterwards."""
        return bool(self._command("toggle_popover", element=element)["open"])

    @staticmethod
    def _page_args(size, width, height, margins, print_media) -> dict:
        args: dict = {"print": bool(print_media)}
        if size is not None:
            args["size"] = str(size)
        if width is not None or height is not None:
            args["width"], args["height"] = float(width), float(height)
        if margins is not None:
            args["margins"] = [float(m) for m in margins]
        return args

    def paginate(self, size: str | None = None, *, width: float | None = None, height: float | None = None,
                 margins: tuple[float, float, float, float] | None = None, print_media: bool = True) -> dict:
        """Lay the document out as pages (CSS Paged Media: ``@page`` size/margins/margin boxes, page
        breaks, widows/orphans, named pages, ``print`` media). ``size`` is a CSS page size name
        (``"A4"``, ``"letter landscape"``) or give ``width``/``height`` in CSS px; the
        document's ``@page`` size wins over it; default A4. Returns ``{"count", "pages": [{"width", "height",
        "content"}], "revision"}``; the screen is unchanged. A DOM change makes it stale."""
        return self._command("paginate", **self._page_args(size, width, height, margins, print_media))

    def get_page_rects(self, element: str) -> list[dict]:
        """Where ``element`` falls in the current pagination: ``[{"page", "x", "y", "width", "height"}]``."""
        return self._command("get_page_rects", element=element)["rects"]

    def render_page(self, page: int, path: str | os.PathLike[str], *, dpi: float = 96.0) -> dict:
        """Render one page of the current pagination to a PNG file (a print preview)."""
        return self._command("render_page", page=int(page), dpi=float(dpi), path=os.fspath(path))

    def export_pdf(self, path: str | os.PathLike[str], size: str | None = None, *, width: float | None = None,
                   height: float | None = None, margins=None, print_media: bool = True, dpi: float = 150.0,
                   title: str = "") -> dict:
        """Paginate and write a PDF (one page image per page; the text is not selectable)."""
        return self._command("export_pdf", path=os.fspath(path), dpi=float(dpi), title=str(title),
                             **self._page_args(size, width, height, margins, print_media))

    def print_document(self, size: str | None = None, *, width: float | None = None, height: float | None = None,
                       margins=None, print_media: bool = True, dpi: float = 300.0, title: str = "") -> dict:
        """Paginate and print through the native print dialog (Windows: the system dialog; Linux: the
        desktop's print portal). Returns ``{"job", "pages", "status": "started" | "unavailable"}``; the
        outcome arrives as a ``print`` event (``status``: ``printed``, ``cancelled``, ``failed``,
        ``unavailable``, with ``reason``)."""
        return self._command("print", dpi=float(dpi), title=str(title),
                             **self._page_args(size, width, height, margins, print_media))

    def set_pointer_capture(self, element: str, pointer_id: int = 1) -> bool:
        """Capture the pointer for ``element`` while a button is pressed (Pointer Events
        ``setPointerCapture``; the mouse is pointer 1): its moves and release are delivered to the
        element from the next event, with ``gotpointercapture`` / ``lostpointercapture``. Returns
        False when no button is pressed. Capture ends at the release or when the element is removed."""
        return bool(self._command("set_pointer_capture", element=element, pointer_id=int(pointer_id), capture=True)["accepted"])

    def release_pointer_capture(self, element: str, pointer_id: int = 1) -> None:
        """Release a capture ``element`` holds."""
        self._command("set_pointer_capture", element=element, pointer_id=int(pointer_id), capture=False)

    def get_pointer_capture(self) -> str | None:
        """The id of the element holding the pointer capture, else None."""
        return self._command("get_pointer_capture")["element"]

    def exec_edit(self, element: str, command: str, value: str | None = None) -> bool:
        """Run a rich-text editing command on a ``contenteditable`` host: ``bold``, ``italic``,
        ``underline``, ``strikethrough``, ``code``, ``link`` (``value`` is an http, https or mailto
        URL), ``unlink``, ``remove_format``, ``insert_text``, ``insert_paragraph``, ``undo`` and
        ``redo``. It acts on the host's selection (a caret at the end when there is none) and
        returns whether anything changed; formatting needs a rich host (not ``plaintext-only``)."""
        return bool(self._command("exec_edit", element=element, command=command, value=value)["ok"])

    def get_edit_state(self, element: str) -> dict:
        """The formats at the selection of a ``contenteditable`` host:
        ``{bold, italic, underline, strikethrough, code, link}`` (``link`` is the href or None)."""
        return self._command("get_edit_state", element=element)

    def get_popover(self, element: str) -> dict:
        """``{"open": bool, "kind": "auto" | "manual"}``."""
        return self._command("get_popover", element=element)

    def get_options(self, element: str) -> list[dict]:
        """Options of a ``<select>``: ``value``, ``label``, ``selected``, ``disabled``."""
        return self._command("get_options", element=element)["options"]

    def set_selected_values(self, element: str, values: list[str]) -> None:
        """Select exactly these option values (at most one for a single select)."""
        self._command("set_selected_values", element=element, values=list(values))

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
