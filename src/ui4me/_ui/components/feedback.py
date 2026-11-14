"""Toasts, dialogs, confirm, alerts and empty/loading/error states."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ..aio import UiFuture
from ..component import Component, Container, Frame, current_frame, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps, UiError
from ..reactive import Signal

if TYPE_CHECKING:  # pragma: no cover
    from ..app import UiApp
    from ..window import UiWindow

KINDS = ("info", "success", "warning", "danger")
MAX_TOASTS = 5


def _kind(kind: str) -> str:
    if kind == "error":
        kind = "danger"
    if kind not in KINDS:
        raise InvalidComponentProps(f"kind must be one of {', '.join(KINDS)}; got {kind!r}")
    return kind


def _target_window(app: "UiApp") -> "UiWindow":
    """The window of the current callback, else the first open window (main if still open)."""
    frame = current_frame(required=False)
    window = frame.window if frame is not None else None
    if window is None or window.closed:
        window = next((w for w in [app.main, *app.windows] if w.core is not None and not w.closed), app.main)
    return window


def _overlay_frame(app: "UiApp", window: "UiWindow") -> Frame:
    root = window.root
    live = window.core is not None and not window.closed
    return Frame(app, root, root.overlay, window, live=live, position=(root.overlay.id, "beforeend") if live else None)


class Toast(Component):
    kind = "Toast"

    def __init__(self, message: Any, *, kind: str = "info", **kw: Any):
        self._kind = _kind(kind)
        super().__init__(**kw)
        self._bind(message, lambda v: self.text_el.set_text(v), "message")
        self._listen(self.close_el.id, "click", lambda _e: self.dispose())

    def _build(self) -> Element:
        root = Element("div", self, cls=f"u4-toast u4-toast-{self._kind}",
                       attrs={"role": "alert" if self._kind == "danger" else "status"})
        self.text_el = Element("div", self, cls="u4-grow")
        self.close_el = Element("button", self, cls="u4-toast-close", attrs={"type": "button", "aria-label": "Close"},
                                text="×")
        root.add(self.text_el, self.close_el)
        return root

    def close(self) -> None:
        self.dispose()


def show_toast(app: "UiApp", window: "UiWindow", message: Any, *, kind: str = "info",
               duration: float | None = 4.0) -> Toast:
    frame = push(_overlay_frame(app, window))
    try:
        toast = Toast(message, kind=kind)
    finally:
        pop(frame)
    if frame.live:
        app._insert_created(frame)
    toasts = [c for c in window.root._children if isinstance(c, Toast)]
    for old in toasts[:-MAX_TOASTS]:
        old.dispose()
    if duration and window.core is not None:
        timer = app.core.timer(max(1, int(duration * 1000)),
                               lambda _e: app._call(toast.dispose, context="toast timeout"))

        def cancel() -> None:
            if not app.closed:
                try:
                    timer.cancel()
                except Exception:
                    pass
        toast.on_dispose(cancel)
    return toast


def notify(message: Any, *, kind: str = "info", duration: float | None = 4.0) -> Toast:
    """Show a toast in the current window (bottom-right). ``duration=None`` keeps it until closed."""
    from ..component import current_app
    app = current_app()
    return show_toast(app, _target_window(app), message, kind=kind, duration=duration)


class Dialog(Container):
    """Modal (or non-modal) dialog: focus moves inside, Tab is trapped, Escape closes,
    focus returns to the opener. ``await dlg.open()`` gives the close result."""

    kind = "Dialog"

    def __init__(self, title: Any = None, *, modal: bool = True, dismissible: bool = True,
                 on_close: Callable | None = None, **kw: Any):
        self._title, self._modal, self._dismissible = title, modal, dismissible
        self._future: UiFuture | None = None
        self.is_open = Signal(False, name="dialog open")
        frame = current_frame()
        overlay = None
        if frame.slot is None:
            overlay = push(_overlay_frame(frame.app, _target_window(frame.app)))
        try:
            super().__init__(**kw)
        finally:
            if overlay is not None:
                pop(overlay)
        self._overlay_frame = overlay
        if title is not None:
            self._bind(title, lambda v: self.title_el.set_text(v), "title")
        self._on_close = on_close
        self._listen(self.root.id, "close", self._closed)
        if not dismissible:
            self._prevent_cancel = True

    def _build(self) -> Element:
        root = Element("dialog", self, cls="u4-dialog")
        self.body = Element("div", self, cls="u4-dialog-body")
        self.title_el = Element("h2", self, cls="u4-dialog-title", attrs={"hidden": self._title is None})
        self.body.add(self.title_el)
        root.add(self.body)
        return root

    @property
    def slot(self) -> Element:
        return self.body

    def __exit__(self, exc_type, exc, tb) -> None:
        super().__exit__(exc_type, exc, tb)
        if self._overlay_frame is not None and self._overlay_frame.live and self._state == "created":
            self._overlay_frame.created[:] = [self]
            self.app._insert_created(self._overlay_frame)

    def _on_mount(self) -> None:
        if not self._dismissible:
            self.window._queue({"op": "set_default_action", "element": self.root.id, "event": "keydown",
                                "options": {"key": "Escape"}})

    def open(self) -> UiFuture:
        """Show the dialog. The returned future resolves with the close result (``None`` on Escape)."""
        self._live_check()
        if self.window is None:
            raise UiError("the dialog's window is not open yet; open dialogs from callbacks")
        if self._future is None or self._future.done:
            self._future = UiFuture(self.app, "dialog")
        if not self.is_open.peek():
            self._opener = self._focused_element()
        self.window._queue({"op": "show_dialog", "element": self.root.id, "modal": self._modal})
        self.is_open.set(True)
        self._touch()
        return self._future

    def close(self, result: Any = None) -> None:
        """Close the dialog and resolve ``open()`` with ``result``."""
        self._live_check()
        self._result = result
        if self.window is not None and self.is_open.peek():
            self.window._queue({"op": "close_dialog", "element": self.root.id, "return_value": None})
            self._touch()
        self._finish(result)

    def _closed(self, event: dict) -> None:
        self._finish(getattr(self, "_result", None))

    def _focused_element(self) -> str | None:
        """The element that has native focus now (the opener), if Core reports one."""
        try:
            info = self.window.core.document.focused_element() or {}
        except Exception:  # no live document, or a Core without focus reporting
            return None
        element = info.get("element") if isinstance(info, dict) else None
        return element if isinstance(element, str) and element else None

    def _restore_focus(self) -> None:
        # Core restores focus to the opener natively, but an opener whose handler
        # returned the dialog's future (``on_click=lambda: dlg.open()``) is disabled as
        # "busy" until the dialog closes, so that native restore is rejected. Refocus
        # after the current dispatch has flushed the re-enable. A focus op for an
        # opener removed meanwhile is ignored by UiWindow._send_single.
        opener, self._opener = getattr(self, "_opener", None), None
        window = self.window
        if not opener or window is None or window.closed or window.core is None:
            return

        def refocus() -> None:
            if window.closed or window.core is None or self.is_open.peek():
                return
            # Apply pending reactions (the opener's re-enable) first: owner-loop
            # coalescing may run this in the same group as the close event.
            self.app.scheduler.flush()
            window._queue({"op": "focus", "element": opener})
            self.app._request_commit()
        try:
            self.app.post(refocus)
        except UiError:  # app stopping or owner queue saturated: focus no longer matters
            pass

    def _finish(self, result: Any) -> None:
        was_open = self.is_open.peek()
        self.is_open.set(False)
        self._result = None
        future, self._future = self._future, None
        if future is not None and not future.done:
            future.set_result(result)
        if was_open:
            self._restore_focus()
        if was_open and self._on_close is not None:
            self._emit(self._on_close, result)


def confirm(message: str, *, title: str = "Please confirm", ok: str = "OK", cancel: str = "Cancel",
            danger: bool = False, on_result: Callable[[bool], Any] | None = None) -> UiFuture:
    """Ask a yes/no question. ``if await ui.confirm('Delete?'):`` (or ``on_result=``)."""
    from ..component import current_app
    from .basic import Button, Text
    from .layout import Row
    app = current_app()
    window = _target_window(app)
    frame = push(_overlay_frame(app, window))
    try:
        dialog = Dialog(title)
    finally:
        pop(frame)
    inner = push(Frame(app, dialog, dialog.body, window))
    try:
        Text(message)
        actions = Row(gap="sm", justify="end", classes="u4-dialog-actions")
        actions_frame = push(Frame(app, actions, actions.slot, window))
        try:
            Button(cancel, variant="secondary", on_click=lambda: dialog.close(False))
            Button(ok, variant="danger" if danger else "primary", on_click=lambda: dialog.close(True))
        finally:
            pop(actions_frame)
    finally:
        pop(inner)
    if frame.live:
        app._insert_created(frame)
    result: UiFuture = UiFuture(app, "confirm")

    def done(future: UiFuture) -> None:
        value = bool(future._result) if future._error is None else False
        result.set_result(value)
        app._call(dialog.dispose, context="confirm cleanup")
    if window.core is None:
        raise UiError("ui.confirm needs an open window; call it from a callback")
    dialog.open().add_done_callback(done)
    if on_result is not None:
        result.then(on_result)
    return result


class Alert(Component):
    """Inline message box."""

    kind = "Alert"

    def __init__(self, message: Any, *, kind: str = "info", title: Any = None, **kw: Any):
        self._kind = _kind(kind)
        self._has_title = title is not None
        super().__init__(**kw)
        self._bind(message, lambda v: self.msg_el.set_text(v), "message")
        if title is not None:
            self._bind(title, lambda v: self.title_el.set_text(v), "title")

    def _build(self) -> Element:
        root = Element("div", self, cls=f"u4-alert u4-alert-{self._kind}",
                       attrs={"role": "alert" if self._kind == "danger" else "status"})
        box = Element("div", self, cls="u4-column u4-gap-xs")
        self.title_el = Element("div", self, cls="u4-alert-title", attrs={"hidden": not self._has_title})
        self.msg_el = Element("div", self)
        box.add(self.title_el, self.msg_el)
        root.add(box)
        return root


class StateView(Component):
    """Empty / loading / error placeholder."""

    kind = "State"

    def __init__(self, title: Any, description: Any = None, *, variant: str = "empty",
                 action: tuple[str, Callable] | None = None, **kw: Any):
        self._variant, self._has_desc, self._action = variant, description is not None, action
        super().__init__(**kw)
        self._bind(title, lambda v: self.title_el.set_text(v), "title")
        if description is not None:
            self._bind(description, lambda v: self.desc_el.set_text(v), "description")
        if action is not None:
            from ..component import adapt
            handler = adapt(action[1], None)
            self._listen(self.action_el.id, "click", lambda e: self._emit(handler, e))

    def _build(self) -> Element:
        root = Element("div", self, cls=f"u4-state u4-state-{self._variant}",
                       attrs={"role": "alert" if self._variant == "error" else "status"})
        if self._variant == "loading":
            root.add(Element("span", self, cls="u4-spinner"))
        self.title_el = Element("div", self, cls="u4-state-title")
        self.desc_el = Element("div", self, cls="u4-caption", attrs={"hidden": not self._has_desc})
        root.add(self.title_el, self.desc_el)
        if self._action is not None:
            self.action_el = Element("button", self, cls="u4-btn u4-btn-secondary u4-btn-sm",
                                     attrs={"type": "button"}, text=self._action[0])
            root.add(self.action_el)
        return root
