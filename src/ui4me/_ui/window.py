"""UiWindow: one native Core window, its managed document, patch queue and event delegation."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable

from .component import Container, Frame, pop, push
from .dom import Element, escape_text
from .errors import AppClosedError, UiError

if TYPE_CHECKING:  # pragma: no cover
    from .app import UiApp
    from .component import Component

# Operations Core accepts inside one atomic `batch`.
BATCHABLE = frozenset({"set_text", "set_attribute", "remove_attribute", "add_class", "remove_class",
                       "insert_html", "replace_children_html", "remove_element", "move_element",
                       "trim_children"})
MAX_BATCH_OPS = 1024
MAX_BATCH_BYTES = 1024 * 1024
# Events whose `element` is the managed control itself; others are delegated along `path`.
WINDOW_EVENTS = ("closed", "close_requested", "resized", "scale_changed", "environment_changed",
                 "window_state", "file_drop", "menu_command")


class EventInfo(dict):
    """The Core event as a dict, with attribute access and ``stop()`` for UI-level bubbling."""

    stopped = False

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def stop(self) -> None:
        self.stopped = True


class RootComponent(Container):
    kind = "Window"

    def __init__(self, window: "UiWindow"):
        self._window_ref = window
        super().__init__(place=False)

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-app")
        self._main = Element("main", self, cls="u4-main u4-column u4-gap-md")
        self._overlay = Element("div", self, cls="u4-toasts", attrs={"aria-live": "polite"})
        root.add(self._main, self._overlay)
        return root

    @property
    def slot(self) -> Element:
        return self._main

    @property
    def overlay(self) -> Element:
        return self._overlay

    def __enter__(self):
        raise UiError("use `with app.window(...)` instead of entering the window root")


class UiWindow:
    """A native window owned by a :class:`UiApp`. Use ``with app.window(title):`` to build one."""

    def __init__(self, app: "UiApp", title: str, width: int, height: int, *, main: bool = False,
                 on_close: Callable | None = None):
        self.app = app
        self.title = title
        self.width, self.height = width, height
        self.main = main
        self._density = app._density
        self.core = None
        self.closed = False
        self._ops: list[dict] = []
        self._desynced = False
        self._elements: dict[str, "Component"] = {}
        self._listeners: dict[str, dict[str, list[tuple["Component", Callable]]]] = {}
        self._subscribed: dict[str, Any] = {}
        self._close_handlers: list[Callable] = []
        self._close_request_handlers: list[Callable] = []
        if on_close is not None:
            self._close_handlers.append(on_close)
        frame = Frame(app, None, None)
        push(frame)
        try:
            self.root = RootComponent(self)
            if self._density != "comfortable":
                self.root.root.add_class(f"u4-density-{self._density}")
        finally:
            pop(frame)
        self._frame: Frame | None = None

    def __repr__(self) -> str:
        state = "closed" if self.closed else ("open" if self.core else "building")
        return f"<UiWindow {self.title!r} {state}>"

    # -- building -------------------------------------------------------------------------
    def __enter__(self) -> "UiWindow":
        if self.core is not None:
            raise UiError("this window is already open; add content with `with container:`")
        self._frame = push(Frame(self.app, self.root, self.root.slot, self))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pop(self._frame)
        if exc is None and not self.main:
            self.open()

    def document(self) -> str:
        app = self.app
        title = escape_text(self.title)
        sheets = "".join(f"<style>{css}</style>" for css in app._stylesheets())
        return (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{title}</title>{sheets}</head>"
                f"<body class=\"u4-body\">{self.root._html()}</body></html>")

    def open(self) -> "UiWindow":
        """Open the native window (done automatically when the ``with`` block ends)."""
        app = self.app
        if self.core is not None:
            return self
        if app.closed:
            raise AppClosedError("the application has stopped")
        app._owner_check()
        app.scheduler.flush()
        self.core = app.core.open(self.document(), title=self.title, width=self.width, height=self.height,
                                  base_path=app.assets)
        app.windows.append(self)
        self._ops.clear()
        self.root._mount(self)
        for event in WINDOW_EVENTS[:2]:
            self._subscribe(event)
        app._install_css(self)
        app.theme._apply(self)
        app.commands._hook(self)
        self._post_open()
        app._request_commit()
        return self

    def _post_open(self) -> None:
        pass

    # -- patch queue -------------------------------------------------------------------------
    def _queue(self, op: dict) -> None:
        if self._desynced or self.closed or self.core is None:
            return
        self._ops.append(op)

    def _check_generation(self) -> bool:
        """Stop managing a window whose document was replaced outside UI4ME."""
        if self._desynced or self.core is None or self.closed or not getattr(self.core, "replaced", False):
            return not self._desynced
        self._desynced = True
        self._ops.clear()
        self.root._teardown()
        self._listeners.clear()
        self._elements.clear()
        self.app._report(UiError(f"window {self.title!r}: its document was replaced or unloaded outside UI4ME; "
                                 "managed components were disposed and will not update"), "document generation")
        return False

    def commit(self) -> None:
        """Send queued patches to Core: batchable runs atomically, the rest in order."""
        if self._desynced or not self._ops or self.closed or self.core is None or self.app.stopping:
            self._ops.clear()
            return
        if not self._check_generation():
            return
        ops, self._ops = self._ops, []
        run: list[dict] = []
        size = 0
        for op in ops:
            if op["op"] in BATCHABLE:
                length = len(op.get("html", "")) + len(op.get("text", "")) + 64
                if len(run) >= MAX_BATCH_OPS or size + length > MAX_BATCH_BYTES:
                    self._send_batch(run)
                    run, size = [], 0
                run.append(op)
                size += length
            else:
                self._send_batch(run)
                run, size = [], 0
                self._send_single(op)
        self._send_batch(run)

    def _send_batch(self, run: list[dict]) -> None:
        if not run or self.closed:
            return
        try:
            self.core.batch(run)
        except Exception as error:
            self._desynced = True
            self._ops.clear()
            self.app._report(error, f"DOM batch failed; window {self.title!r} is desynchronized and updates stopped")

    def _send_single(self, op: dict) -> None:
        if self.closed:
            return
        core = self.core
        kind = op["op"]
        try:
            if kind == "set_value":
                core.set_value(op["element"], op["value"])
            elif kind == "set_checked":
                core.set_checked(op["element"], op["checked"])
            elif kind == "focus":
                core.focus(op["element"])
            elif kind == "scroll_into_view":
                core.scroll_into_view(op["element"], block=op.get("block", "nearest"))
            elif kind == "set_scroll_follow":
                core.set_scroll_follow(op["element"], op["follow"])
            elif kind == "scroll_to":
                core.scroll_to(op["element"], x=op.get("x"), y=op.get("y"))
            elif kind == "show_dialog":
                core.show_dialog(op["element"], modal=op.get("modal", True))
            elif kind == "close_dialog":
                core.close_dialog(op["element"], op.get("return_value"))
            elif kind == "set_selected_values":
                core.set_selected_values(op["element"], op["values"])
            elif kind == "set_default_action":
                core.set_default_action(op["element"], op["event"], **op.get("options", {}))
            elif kind == "call":
                op["fn"](core)
            else:  # pragma: no cover - programming error
                raise UiError(f"unknown queued operation {kind}")
        except Exception as error:
            if kind == "focus" and not core.has_element(op["element"]):
                return
            self._desynced = True
            self._ops.clear()
            self.app._report(error, f"{kind} failed; window desynchronized: {op.get('element')}")

    def call(self, fn: Callable[[Any], Any]) -> None:
        """Queue ``fn(core_window)`` to run in order with pending patches."""
        self._queue({"op": "call", "fn": fn})
        self.app._request_commit()

    # -- events -----------------------------------------------------------------------------
    def _subscribe(self, event: str) -> None:
        if event in self._subscribed or self.core is None or self.closed:
            return
        self._subscribed[event] = self.core.on(event, lambda raw, _e=event: self._dispatch(_e, raw))

    def _add_listener(self, element_id: str, event: str, component: "Component", handler: Callable) -> None:
        self._listeners.setdefault(element_id, {}).setdefault(event, []).append((component, handler))
        self._subscribe(event)

    def _remove_listener(self, element_id: str, event: str, component: "Component", handler: Callable) -> None:
        events = self._listeners.get(element_id)
        if not events:
            return
        entries = events.get(event)
        if entries:
            try:
                entries.remove((component, handler))
            except ValueError:
                pass
            if not entries:
                del events[event]
        if not events:
            del self._listeners[element_id]

    def on(self, event: str, handler: Callable) -> Callable[[], None]:
        """Window-level listener (e.g. ``keydown`` anywhere, ``resized``). Returns an unsubscribe."""
        wrapped = handler
        root = self.root
        self._add_listener("*", event, root, wrapped)
        return lambda: self._remove_listener("*", event, root, wrapped)

    def on_close(self, handler: Callable[[], Any]) -> None:
        self._close_handlers.append(handler)

    def on_close_request(self, handler: Callable[[], Any]) -> None:
        """``handler()`` returning False vetoes a user close request."""
        self._close_request_handlers.append(handler)

    def _dispatch(self, kind: str, raw: dict) -> Any:
        if kind == "closed":
            self._closed_by_core()
            return None
        if kind == "close_requested":
            veto = False
            for handler in list(self._close_request_handlers):
                if self.app._call(handler, context=f"window {self.title!r} close request") is False:
                    veto = True
            return False if veto else None
        event = EventInfo(raw)
        targets: list[str] = list(dict.fromkeys(event.get("path") or ()))
        element = event.get("element")
        if element and element not in targets:
            targets.insert(0, element)
        calls = []
        for target in targets:
            entries = self._listeners.get(target, {}).get(kind)
            if entries:
                calls.extend(entries)
        calls.extend(self._listeners.get("*", {}).get(kind, ()))
        if not calls:
            return None

        def run() -> None:
            for component, handler in calls:
                if event.stopped:
                    break
                if component.disposed:
                    continue
                self.app._call(handler, event, context=f"{component.path()} {kind}", owner=component)
        self.app._dispatch_batch(run)
        return None

    # -- lifecycle ----------------------------------------------------------------------------
    def close(self) -> None:
        """Close this window (its components are disposed)."""
        if self.closed or self.core is None:
            return
        self.app._owner_check()
        # Core request_close is graceful and can be vetoed.  Do not dispose
        # the component tree until Core confirms the actual `closed` event.
        # Disposing here would break open windows whose before-close policy
        # rejects a user/programmatic close request.
        self.core.close()

    def _closed_by_core(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._ops.clear()
        handlers, self._close_handlers = self._close_handlers, []
        for handler in handlers:
            self.app._call(handler, context=f"window {self.title!r} close")
        self.root._teardown()
        self._listeners.clear()
        self._elements.clear()
        self._subscribed.clear()
        if self in self.app.windows:
            self.app.windows.remove(self)

    # -- native services ------------------------------------------------------------------
    def set_title(self, title: str) -> None:
        self.title = title
        if self.core is not None and not self.closed:
            self.core.set_title(title)

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        if self.core is not None and not self.closed:
            self.core.resize(width, height)

    def snapshot(self, path) -> dict:
        self.commit()
        return self.core.snapshot(path)

    def diagnostics(self) -> dict:
        return {"title": self.title, "open": self.core is not None and not self.closed,
                "managed_elements": len(self._elements), "listeners": sum(
                    len(v) for events in self._listeners.values() for v in events.values()),
                "subscriptions": len(self._subscribed), "queued_ops": len(self._ops)}

    def html(self, element: str | None = None) -> str:
        """Serialized current document (or one element) — handy in tests."""
        self.commit()
        return self.core.get_html(element)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
