"""UiApp: owns one Core application session, its windows, scheduler and desktop services."""
from __future__ import annotations

import inspect
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

from . import core_compat
from .aio import UiFuture, drive
from .component import Component, Frame, current_frame, pop, push
from .errors import (AppClosedError, InvalidComponentProps, NativeServiceError, TaskError, UiBusyError, UiError,
                     WrongThreadError)
from .reactive import Reaction, Scheduler, Signal, read
from .theme import THEMES, theme_css, functional_css, PRESET_TOKENS, preset_css
from .window import UiWindow

log = logging.getLogger("ui4me.ui")


class UiApp:
    """One desktop application. Build it in ``with ui.app(...) as app:``, then ``app.run()``."""

    def __init__(self, title: str = "UI4ME", *, width: int = 960, height: int = 680, theme: str = "system",
                 backend: str | None = None, app_id: str | None = None, css: str | None = None,
                 assets: str | os.PathLike | None = None,
                 on_error: Callable[[BaseException, str | None], Any] | None = None):
        ui4me = core_compat.require()
        self.assets = Path(assets).resolve() if assets is not None else None
        if self.assets is not None and not self.assets.is_dir():
            raise InvalidComponentProps(f"assets must be an existing directory: {self.assets}")
        backend = backend or "native"
        if backend != "native":
            raise InvalidComponentProps("UI4ME 2 always runs in the UI4ME Core host process model; for tests "
                                        "without a desktop use `ui4me-run --headless app.py` (backend must be 'native')")
        self._owner = threading.get_ident()
        self.title = title
        self.backend = backend
        self.app_id = app_id or _derived_app_id(title)
        self.core = ui4me.App(backend=backend, app_id=self.app_id,
                              handle_sigint=threading.current_thread() is threading.main_thread())
        self.closed = False
        self.running = False
        self.stopping = False
        self.core.on("stopped", lambda _e: setattr(self, "stopping", True))
        self.windows: list[UiWindow] = []
        self.scheduler = Scheduler(request=self._request_flush, commit=self._commit_all, on_error=self._report)
        self._css: list[str] = [css] if css else []  # user cascade after visual theme
        self._visual_css: str = theme_css()
        self._visual_sheets: dict[int, int] = {}  # native window identity -> sheet id
        self._density = "comfortable"
        self._runtime_sheets: list[str] = []
        self._error_handlers: list[Callable] = []
        if on_error is not None:
            self._error_handlers.append(on_error)
        self.last_error: tuple[str, str | None] | None = None
        self.error_count = 0
        self._reporting = False
        self.theme = Theme(self, theme)
        self.main = UiWindow(self, title, width, height, main=True)
        self.dialogs = Dialogs(self)
        self.clipboard = Clipboard(self)
        self.tasks = Tasks(self)
        self.commands = Commands(self)
        from .desktop import Desktop
        from .settings import Settings
        self.desktop = Desktop(self)
        self.settings = Settings(self, self.app_id)
        self.navigation = Signal("", name="navigation")  # legacy opt-in shared controller
        self._navigation_regions: list[Any] = []
        self._frame: Frame | None = None

    def __repr__(self) -> str:
        return f"<UiApp {self.title!r} {'closed' if self.closed else 'running' if self.running else 'building'}>"

    # -- building ---------------------------------------------------------------------------
    def __enter__(self) -> "UiApp":
        self._owner_check()
        self._frame = push(Frame(self, self.main.root, self.main.root.slot, self.main))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pop(self._frame)
        if exc is not None:
            self._shutdown()
            return
        self.main.open()

    def window(self, title: str, *, width: int = 640, height: int = 480,
               on_close: Callable[[], Any] | None = None) -> UiWindow:
        """A second native window: ``with app.window('About'): ui.text(...)`` opens it on exit."""
        self._active()
        return UiWindow(self, title, width, height, on_close=on_close)

    def css(self, css: str) -> None:
        """Add trusted application CSS to every window (current and future)."""
        self._active()
        if any(w.core is not None for w in self.windows):
            self._runtime_sheets.append(css)
            for window in self.windows:
                if window.core is not None and not window.closed:
                    window.core.add_stylesheet(css)
        else:
            self._css.append(css)

    def density(self, value: str) -> str:
        """Set visual density on every managed window, including future windows."""
        self._active()
        if value not in ("comfortable", "compact", "dense"):
            raise InvalidComponentProps("density must be comfortable, compact, or dense")
        old = self._density
        self._density = value
        for window in [self.main, *self.windows]:
            window.root.root.remove_class(f"u4-density-{old}")
            if value != "comfortable":
                window.root.root.add_class(f"u4-density-{value}")
        return self._density

    def _stylesheets(self) -> list[str]:
        return [functional_css()]

    def _install_css(self, window: UiWindow) -> None:
        """Install theme as a replaceable Core attached sheet, then app overrides."""
        result = window.core.add_stylesheet(self._visual_css)
        self._visual_sheets[id(window)] = int(result["sheet"])
        for css in self._css + self._runtime_sheets:
            window.core.add_stylesheet(css)

    # -- running ----------------------------------------------------------------------------
    def run(self) -> None:
        """Show the windows and block until the last one closes or :meth:`stop` is called."""
        self._owner_check()
        if self.main.core is None:
            raise UiError("call app.run() after the `with ui.app(...) as app:` block has finished")
        if self.closed:
            raise AppClosedError("this application already ran; create a new ui.app() to run again")
        smoke = os.environ.get("UI4ME_UI_SMOKE")
        if smoke:  # unattended example checks: stop after N seconds
            self.after(float(smoke), self.stop)
        self.running = True
        try:
            self.core.run()
        finally:
            self.running = False
            self._shutdown()
        if smoke and self.error_count:
            raise UiError(f"{self.error_count} error(s) reported while running (last: {self.last_error})")

    def stop(self) -> None:
        """Close all windows and return from :meth:`run`. Safe from any thread."""
        if not self.closed:
            self.stopping = True
            self.core.stop()

    def close(self) -> None:
        """Release the Core session without running (``run()`` does this automatically)."""
        self._owner_check()
        if self.running:
            raise UiError("call app.stop() while running; the app closes when run() returns")
        self._shutdown()

    def post(self, fn: Callable[[], Any]):
        """Run ``fn`` on the UI owner thread soon. Thread-safe; returns a ``concurrent.futures.Future``.

        Use this from worker threads to update state: ``app.post(lambda: status.set('done'))``.
        """
        if self.closed:
            raise AppClosedError("the application has stopped")
        try:
            return self.core.post(lambda: self._call(fn, context="posted callback"))
        except RuntimeError as error:
            if "full" in str(error):
                raise UiBusyError("the UI owner queue is full (512 pending posts); slow down producers "
                                  "or batch updates, e.g. log.extend(lines)") from error
            raise AppClosedError(str(error)) from error

    def after(self, seconds: float, fn: Callable[[], Any]) -> "TimerHandle":
        """Call ``fn`` once after ``seconds`` on the owner thread."""
        return self._timer(seconds, fn, repeat=False)

    def every(self, seconds: float, fn: Callable[[], Any]) -> "TimerHandle":
        """Call ``fn`` every ``seconds`` until cancelled (or until the owning component is disposed)."""
        return self._timer(seconds, fn, repeat=True)

    def _timer(self, seconds: float, fn: Callable[[], Any], *, repeat: bool) -> "TimerHandle":
        self._active()
        milliseconds = max(1, int(round(seconds * 1000)))
        owner = _frame_owner()
        handle = TimerHandle()
        handle._core = self.core.timer(milliseconds, lambda _e: self._call(fn, context="timer", owner=owner),
                                       repeat=repeat)
        if owner is not None:
            owner.on_dispose(handle.cancel)
        return handle

    def sleep(self, seconds: float) -> UiFuture[None]:
        """Awaitable pause for ``async def`` callbacks: ``await app.sleep(0.5)``."""
        future: UiFuture = UiFuture(self, "sleep")
        self.core.timer(max(1, int(seconds * 1000)), lambda _e: future.set_result(None))
        return future

    def navigate(self, page: str) -> None:
        """Navigate automatically only when the destination is unambiguous."""
        frame = current_frame(required=False)
        active_window = frame.window if frame is not None else None
        candidates = [n for n in self._navigation_regions if not n.disposed and page in n._pages]
        if active_window is not None:
            local = [n for n in candidates if n.window is active_window]
            if len(local) == 1:
                local[0].select(page)
                return
        if len(candidates) == 1:
            candidates[0].select(page)
            return
        if not candidates:
            self.navigation.set(page)  # legacy shared state or pre-navigation setup
            return
        raise InvalidComponentProps(f"page {page!r} exists in multiple navigation controllers; pass controller=")

    def notify_system(self, title: str, body: str = "", *, urgency: str | None = None,
                      on_click: Callable[[], Any] | None = None) -> dict:
        """Not available: UI4ME Core 1.x has no OS notifications (raises NotImplementedError).

        Use ``ui.notify(...)`` for an in-window toast.
        """
        self._active()
        return self.desktop.notify(title, body)

    def on_error(self, handler: Callable[[BaseException, str | None], Any]) -> None:
        """Receive errors raised by callbacks, bindings and tasks (instead of the default toast)."""
        self._error_handlers.append(handler)

    # -- internals: owner thread, callbacks, flushing ------------------------------------------
    def _owner_check(self) -> None:
        if threading.get_ident() != self._owner:
            raise WrongThreadError("UI objects belong to the thread that created the app; use app.post()")

    def _active(self) -> None:
        self._owner_check()
        if self.closed:
            raise AppClosedError("the application has stopped")

    def _call(self, fn: Callable, *args: Any, context: str | None = None, owner: Component | None = None,
              raw: bool = False) -> Any:
        """Run a user callback on the owner thread: batched, error-isolated, coroutine-aware."""
        if self.closed:
            return None
        if owner is not None and owner.disposed:
            return None
        frame = push(Frame(self, owner, None, owner.window if owner is not None else None))
        try:
            with self.scheduler.batch():
                try:
                    result = fn(*args)
                    if not raw and inspect.iscoroutine(result):
                        return drive(self, result, context, owner=owner)
                    return result
                except Exception as error:
                    self._report(error, context)
                    return None
        finally:
            pop(frame)

    def _dispatch_batch(self, run: Callable[[], None]) -> None:
        with self.scheduler.batch():
            run()

    def _request_flush(self) -> None:
        if self.closed or self.stopping:
            return
        self.core.post(self._flush_posted, internal=True)  # never refused by a full user queue

    def _flush_posted(self) -> None:
        if self.closed:
            return
        frame = push(Frame(self, None, None))
        try:
            self.scheduler.flush()
        finally:
            pop(frame)

    def _request_commit(self) -> None:
        if self.closed:
            return
        self.scheduler.request()

    def _commit_all(self) -> None:
        if self.stopping or self.closed:
            return
        for window in list(self.windows):
            window.commit()

    def _insert_created(self, frame: Frame, *, discard: bool = False) -> None:
        """Insert components created in a live frame into the mounted document."""
        created = frame.created
        if not created:
            return
        if discard:
            for component in created:
                component.dispose()
            return
        target, position = frame.position
        window = frame.window
        html = "".join(component._html() for component in created)
        window._queue({"op": "insert_html", "element": target, "position": position, "html": html})
        for component in created:
            component._mount(window)
        self._request_commit()

    def _report(self, error: BaseException, context: str | None) -> None:
        self.last_error = (type(error).__name__, context)
        self.error_count += 1
        if self._reporting:
            log.error("error while reporting an error in %s: %s", context, error)
            return
        self._reporting = True
        try:
            if self._error_handlers:
                for handler in list(self._error_handlers):
                    try:
                        handler(error, context)
                    except Exception as nested:
                        log.exception("on_error handler failed: %s", nested)
                return
            log.error("Error in %s: %s", context or "UI callback", error, exc_info=error)
            if self.running and not self.closed:
                try:
                    from .components.feedback import _target_window, show_toast
                    window = _target_window(self)
                    if window.core is not None and not window.closed:
                        show_toast(self, window, f"{type(error).__name__}: {error}", kind="danger", duration=8.0)
                except Exception:  # pragma: no cover - never fail while reporting
                    pass
        finally:
            self._reporting = False

    def _shutdown(self) -> None:
        if self.closed:
            return
        # Windows still open when the application ends are closed with it: their
        # on_close handlers run exactly once, as for a native `closed` event.
        for window in [self.main, *self.windows]:
            if window.core is not None and not window.closed:
                try:
                    window._closed_by_core()
                except Exception as error:  # pragma: no cover - never block shutdown
                    log.warning("window close handler failed during shutdown: %s", error)
        self.closed = True
        self.scheduler.close()
        for window in list(self.windows) + [self.main]:
            window.closed = True
            window.root._teardown()
        self.windows.clear()
        try:
            self.core.close()
        except Exception as error:  # pragma: no cover
            log.warning("Core close failed: %s", error)

    # -- diagnostics -------------------------------------------------------------------------
    def diagnostics(self) -> dict:
        """Counters for leaks and load: windows, components, reactions, queues, last error."""
        info = core_compat.info()
        stats = {}
        if not self.closed:
            try:
                stats = self.core.stats()
            except Exception:
                stats = {}
        return {
            "core_version": info.get("version"), "abi": info.get("abi"), "backend": self.backend,
            "windows": [w.diagnostics() for w in self.windows],
            "reactions": self.scheduler.reactions, "pending_reactions": self.scheduler.pending,
            "flushes": self.scheduler.flushes, "errors": self.scheduler.errors,
            "tasks": self.tasks.active, "last_error": self.last_error,
            "core_pending_posts": stats.get("pending_posts"), "core_timers": stats.get("timers"),
        }

    def capabilities(self) -> dict:
        """Core platform capability report (``features`` -> ``{status, reason}``)."""
        return self.core.capabilities()


def _derived_app_id(title: str) -> str:
    """Stable default id from the title (used for the settings folder): 'My App' -> org.ui4me.app.my-app."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "app"
    return f"org.ui4me.app.{slug}"


def _frame_owner() -> Component | None:
    frame = current_frame(required=False)
    return frame.owner if frame is not None else None


class TimerHandle:
    _core = None

    def cancel(self) -> None:
        if self._core is not None:
            try:
                self._core.cancel()
            except Exception:
                pass
            self._core = None


class Theme:
    """``app.theme``: light / dark / system colour scheme and token overrides."""

    def __init__(self, app: UiApp, name: str):
        self._app = app
        self.name = self._check(name)
        self.signal = Signal(self.name, name="theme")

    @staticmethod
    def _check(name: str) -> str:
        if name not in THEMES:
            raise InvalidComponentProps(f"theme must be one of {', '.join(THEMES)}; got {name!r}")
        return name

    def load(self, css: str, *, mode: str = "replace") -> None:
        """Apply a trusted visual stylesheet. mode='replace' swaps the current theme.

        'append' adds application CSS over the theme. Structural functional.css is
        always retained, so reactive hidden regions/ownership remain predictable.
        """
        if mode not in ("replace", "append"):
            raise InvalidComponentProps("CSS mode must be 'replace' or 'append'")
        self._app._active()
        if mode == "append":
            self._app.css(css)
            return
        self._app._visual_css = css
        for window in self._app.windows:
            if window.core is not None and not window.closed:
                sheet = self._app._visual_sheets[id(window)]
                window.core.replace_stylesheet(sheet, css)

    def load_file(self, path: str | os.PathLike, *, mode: str = "replace") -> None:
        """Load local UTF-8 CSS; caller owns its content and referenced resources."""
        self.load(Path(path).read_text(encoding="utf-8"), mode=mode)

    def reset_css(self) -> None:
        self.load(theme_css(), mode="replace")

    def preset(self, name: str) -> None:
        """Choose a bundled CSS visual preset. Custom themes can still replace it."""
        if name not in PRESET_TOKENS:
            raise InvalidComponentProps(f"unknown preset {name!r}; choose {', '.join(PRESET_TOKENS)}")
        self.load(preset_css(name), mode="replace")


    def set(self, name: str) -> None:
        self.name = self._check(name)
        self.signal.set(self.name)
        for window in self._app.windows:
            self._apply(window)

    def toggle(self) -> None:
        """Switch between light and dark (from system, picks the opposite of what is shown)."""
        self.set("light" if self.is_dark else "dark")

    @property
    def is_dark(self) -> bool:
        if self.name != "system":
            return self.name == "dark"
        window = next((w for w in self._app.windows if w.core is not None and not w.closed), None)
        if window is None:
            return False
        return window.core.environment().get("color_scheme") == "dark"

    def tokens(self, **tokens: str) -> None:
        """Override design tokens, e.g. ``app.theme.tokens(primary='#7c3aed', radius_md='14px')``."""
        from .dom import check_css
        lines = []
        for key, value in tokens.items():
            prop = "--u4-" + key.replace("_", "-")
            lines.append(f"{prop}: {check_css(prop, value)};")
        self._app.css(":root { " + " ".join(lines) + " }")

    def _apply(self, window: UiWindow) -> None:
        if window.core is None or window.closed:
            return
        try:
            window.core.set_environment(color_scheme=self.name)
        except Exception as error:
            self._app._report(error, "theme")


class Dialogs:
    """``app.dialogs``: native OS file dialogs. Results are awaitable; cancel gives ``None``."""

    def __init__(self, app: UiApp):
        self._app = app

    def _window(self, window: UiWindow | None) -> UiWindow:
        if window is not None:
            return window
        frame = current_frame(required=False)
        if frame is not None and frame.window is not None and frame.window.core is not None \
                and not frame.window.closed:
            return frame.window
        for candidate in [self._app.main] + self._app.windows:
            if candidate.core is not None and not candidate.closed:
                return candidate
        raise UiError("native dialogs need an open window")

    def _request(self, kind: str, label: str, on_result, window, *, many: bool = False, **options) -> UiFuture:
        app = self._app
        app._active()
        target = self._window(window)
        future: UiFuture = UiFuture(app, label)
        options = {k: v for k, v in options.items() if v is not None}
        if "filters" in options and isinstance(options["filters"], (list, tuple)):
            options["filters"] = {"Files": list(options["filters"])}

        def done(result: dict) -> None:
            if result.get("error"):
                future.set_exception(NativeServiceError(f"{label} failed: {result['error']}"))
                return
            paths = result.get("paths")
            if paths is None:
                future.set_result(None)
            elif many:
                future.set_result([Path(p) for p in paths])
            else:
                future.set_result(Path(paths[0]) if paths else None)
        target.commit()
        target.core.file_dialog(kind, done, **options)
        if on_result is not None:
            future.then(on_result)
        return future

    def open_file(self, *, title: str | None = None, filters: dict | Sequence[str] | None = None,
                  directory=None, multiple: bool = False, on_result: Callable | None = None,
                  window: UiWindow | None = None) -> UiFuture:
        """Native open dialog -> ``Path`` (``list[Path]`` with ``multiple``) or ``None`` on cancel.

        ``filters`` is ``{"Images": ["png", "jpg"]}`` or a list of extensions.
        """
        return self._request("open_multiple" if multiple else "open", "open file dialog", on_result, window,
                             many=multiple, title=title, filters=filters, directory=directory)

    def save_file(self, *, title: str | None = None, file_name: str | None = None,
                  filters: dict | Sequence[str] | None = None, directory=None,
                  on_result: Callable | None = None, window: UiWindow | None = None) -> UiFuture:
        """Native save dialog -> chosen ``Path`` or ``None``. The app writes the file itself."""
        return self._request("save", "save file dialog", on_result, window, title=title, file_name=file_name,
                             filters=filters, directory=directory)

    def folder(self, *, title: str | None = None, directory=None, on_result: Callable | None = None,
               window: UiWindow | None = None) -> UiFuture:
        """Native folder picker -> ``Path`` or ``None``."""
        return self._request("folder", "folder dialog", on_result, window, title=title, directory=directory)


class Clipboard:
    """``app.clipboard``: native plain-text clipboard (process memory in headless sessions)."""

    def __init__(self, app: UiApp):
        self._app = app

    def _core(self):
        return self._app.dialogs._window(None).core

    @property
    def text(self) -> str | None:
        self._app._active()
        return self._core().get_clipboard_text()

    @text.setter
    def text(self, value: str) -> None:
        self.copy(value)

    def copy(self, text: str) -> None:
        self._app._active()
        self._core().set_clipboard_text(str(text))

    def paste(self) -> str:
        return self.text or ""


class TaskHandle:
    """A background task. States: queued, running, succeeded, failed, cancelled."""

    # Core-side task states -> public names
    _STATES = {"pending": "queued", "running": "running", "done": "succeeded", "error": "failed",
               "cancelled": "cancelled"}

    def __init__(self, app: UiApp, label: str):
        self._app = app
        self.label = label
        self._core = None
        self.future: UiFuture = UiFuture(app, label)

    def __repr__(self) -> str:
        return f"<TaskHandle {self.label} {self.state}>"

    @property
    def state(self) -> str:
        return self._STATES.get(self._core.state, self._core.state) if self._core is not None else "queued"

    @property
    def done(self) -> bool:
        return self.future.done

    @property
    def cancelled(self) -> bool:
        """For the worker: cooperative cancellation flag."""
        return self._core is not None and self._core.cancelled

    @property
    def error(self) -> BaseException | None:
        return self.future.error

    @property
    def result(self) -> Any:
        return self.future.result()

    def cancel(self) -> bool:
        """Cancel before start, or ask a running worker to stop (it should check ``task.cancelled``)."""
        if self._core is None:
            return False
        return self._core.cancel()

    def then(self, on_done=None, on_error=None) -> "TaskHandle":
        self.future.then(on_done, on_error)
        return self

    def __await__(self):
        return self.future.__await__()


class Tasks:
    """``app.tasks``: bounded background work with owner-thread completion."""

    def __init__(self, app: UiApp):
        self._app = app
        self.active = 0

    def submit(self, fn: Callable, *args: Any, on_done: Callable | None = None,
               on_error: Callable | None = None, on_cancel: Callable | None = None,
               label: str | None = None) -> TaskHandle:
        """Run ``fn(*args)`` on a worker thread (never touch UI there). Returns an awaitable handle.

        If ``fn`` has a ``task`` parameter it receives the handle to poll ``task.cancelled``.
        Results arrive on the UI thread via ``on_done(result)`` / ``await handle``. Errors go to
        ``on_error`` or the app error reporter. If the component that started the task is
        disposed first, its callbacks are skipped.
        """
        app = self._app
        app._active()
        owner = _frame_owner()
        handle = TaskHandle(app, label or getattr(fn, "__name__", "task"))
        wants_task = _accepts_keyword(fn, "task")

        def work(core_task, *values):
            return fn(*values, task=handle) if wants_task else fn(*values)

        def finish(state: str, value: Any) -> None:
            self.active -= 1
            if owner is not None and owner.disposed:
                handle.future.cancel()
                return
            if state == "done":
                handle.future.set_result(value)
                if on_done is not None:
                    app._call(on_done, value, context=f"task {handle.label} on_done", owner=owner)
            elif state == "error":
                error = value if isinstance(value, Exception) else TaskError(str(value))
                handle.future.set_exception(error)
                if on_error is not None:
                    app._call(on_error, error, context=f"task {handle.label} on_error", owner=owner)
                elif not handle.future._observed:
                    app._report(error, f"task {handle.label}")
            else:
                handle.future.cancel()
                if on_cancel is not None:
                    app._call(on_cancel, context=f"task {handle.label} on_cancel", owner=owner)

        try:
            handle._core = app.core.run_in_background(
                work, *args, pass_task=True,
                on_done=lambda value: finish("done", value),
                on_error=lambda error: finish("error", error),
                on_cancel=lambda: finish("cancel", None))
        except Exception as error:
            raise UiBusyError(f"could not start background task: {error}") from error
        self.active += 1
        if owner is not None:
            owner.on_dispose(handle.cancel)
        return handle

    def run(self, fn: Callable, *args: Any) -> TaskHandle:
        """Awaitable shortcut: ``result = await app.tasks.run(load, path)``."""
        return self.submit(fn, *args)


def _accepts_keyword(fn: Callable, name: str) -> bool:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    p = params.get(name)
    return p is not None and p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)


class Command:
    def __init__(self, registry: "Commands", name: str, action: Callable, shortcut: str | None,
                 enabled: Any, description: str | None):
        self._registry, self.name, self.action, self.shortcut = registry, name, action, shortcut
        self.description = description
        self.enabled = enabled if isinstance(enabled, Signal) else Signal(bool(read(enabled)), name=f"{name} enabled")
        self._enabled_source = enabled
        self.key = _parse_shortcut(shortcut) if shortcut else None

    def run(self) -> Any:
        if not bool(read(self._enabled_source)):
            return None
        return self._registry._app._call(self.action, context=f"command {self.name}")

    def remove(self) -> None:
        self._registry._commands.pop(self.name, None)


def _parse_shortcut(text: str) -> tuple:
    parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise InvalidComponentProps(f"invalid shortcut {text!r}")
    mods = {p.lower() for p in parts[:-1]}
    allowed = {"ctrl", "control", "shift", "alt", "meta", "cmd", "super"}
    if not mods <= allowed:
        raise InvalidComponentProps(f"invalid shortcut modifiers in {text!r}")
    key = parts[-1]
    named = {"esc": "Escape", "escape": "Escape", "enter": "Enter", "return": "Enter", "space": " ",
             "tab": "Tab", "del": "Delete", "delete": "Delete", "backspace": "Backspace", "up": "ArrowUp",
             "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End",
             "pageup": "PageUp", "pagedown": "PageDown"}
    key = named.get(key.lower(), key)
    if len(key) == 1:
        key = key.lower()
    return (key, "ctrl" in mods or "control" in mods, "shift" in mods, "alt" in mods,
            bool(mods & {"meta", "cmd", "super"}))


class Commands:
    """``app.commands``: named actions with optional in-window keyboard shortcuts."""

    def __init__(self, app: UiApp):
        self._app = app
        self._commands: dict[str, Command] = {}

    def add(self, name: str, action: Callable, *, shortcut: str | None = None, enabled: Any = True,
            description: str | None = None) -> Command:
        if name in self._commands:
            raise InvalidComponentProps(f"command {name!r} already exists")
        command = Command(self, name, action, shortcut, enabled, description)
        if command.key is not None:
            for other in self._commands.values():
                if other.key == command.key:
                    raise InvalidComponentProps(f"shortcut {shortcut} is already used by command {other.name!r}")
        self._commands[name] = command
        return command

    def __getitem__(self, name: str) -> Command:
        return self._commands[name]

    def __iter__(self):
        return iter(list(self._commands.values()))

    def run(self, name: str) -> Any:
        return self._commands[name].run()

    def _on_key(self, event: dict) -> None:
        key = event.get("key") or ""
        if len(key) == 1:
            key = key.lower()
        combo = (key, bool(event.get("ctrl")), bool(event.get("shift")), bool(event.get("alt")),
                 bool(event.get("meta")))
        for command in self._commands.values():
            if command.key == combo:
                command.run()
                event_stop = getattr(event, "stop", None)
                if event_stop:
                    event_stop()
                return

    def _hook(self, window: UiWindow) -> None:
        # A flag on the window, not id(window): ids are reused after garbage collection.
        if getattr(window, "_commands_hooked", False):
            return
        window._commands_hooked = True
        window.on("keydown", self._on_key)
