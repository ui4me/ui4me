"""Component lifecycle, build context and the common ``ComponentRef`` API.

Lifecycle: CREATED -> MOUNTED -> DISPOSED. A component owns its elements, reactive
bindings, event listeners, cleanups and tasks; disposing it releases all of them and
removes its DOM (if it was the top of the removed subtree).

Components are created inside a *frame*: ``with ui.app(...)``, ``with ui.row():``,
a dynamic region, or ``with some_container:`` at runtime (which appends live).
"""
from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterator

from .dom import Element, check_name
from .errors import DisposedComponentError, InvalidComponentProps, UiError, WrongThreadError
from .reactive import Computed, Reaction, Signal, is_reactive, read

if TYPE_CHECKING:  # pragma: no cover
    from .app import UiApp
    from .window import UiWindow

_local = threading.local()

CREATED, MOUNTED, DISPOSED = "created", "mounted", "disposed"


@dataclass
class Frame:
    app: "UiApp"
    owner: "Component | None"
    slot: Element | None
    window: "UiWindow | None" = None
    live: bool = False                     # children are inserted into a mounted document on exit
    created: list = field(default_factory=list)
    position: tuple[str, str] | None = None  # (target id, insertAdjacent position) for live inserts


def _stack() -> list[Frame]:
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    return stack


def current_frame(required: bool = True) -> Frame | None:
    stack = _stack()
    if stack:
        return stack[-1]
    if required:
        raise UiError("Create UI components inside `with ui.app(...)`, a layout block such as "
                      "`with ui.column():`, or a dynamic region (ui.when / ui.each)")
    return None


def push(frame: Frame) -> Frame:
    _stack().append(frame)
    return frame


def pop(frame: Frame) -> None:
    stack = _stack()
    if stack and stack[-1] is frame:
        stack.pop()
    elif frame in stack:
        stack.remove(frame)


def current_app(required: bool = True) -> "UiApp | None":
    frame = current_frame(required=False)
    if frame is not None:
        return frame.app
    app = getattr(_local, "app", None)
    if app is None and required:
        raise UiError("No active UI4ME UI app; use `with ui.app(...) as app:`")
    return app


def adapt(fn: Callable | None, *args_if_wanted: Any) -> Callable | None:
    """Wrap ``fn`` so it is called with as many of ``args_if_wanted`` as it accepts."""
    if fn is None:
        return None
    if not callable(fn):
        raise InvalidComponentProps(f"expected a callable, got {fn!r}")
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return fn
    # Only *required* positional parameters receive values. Parameters with defaults are
    # left alone so the loop-capture idiom ``lambda i=i: ...`` keeps its bound value.
    positional = 0
    for p in params:
        if p.kind == p.VAR_POSITIONAL:
            positional = 99
            break
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty:
            positional += 1
    return lambda *given: fn(*given[:positional])


class ClassList:
    """``ref.classes``: add/remove/toggle CSS classes on the component root."""

    def __init__(self, component: "Component"):
        self._c = component

    def add(self, *names: str) -> "ClassList":
        self._c._live_check()
        self._c.root.add_class(*names)
        self._c._touch()
        return self

    def remove(self, *names: str) -> "ClassList":
        self._c._live_check()
        self._c.root.remove_class(*names)
        self._c._touch()
        return self

    def toggle(self, name: str, on: Any = None) -> "ClassList":
        """Toggle ``name``; ``on`` may be a bool, Signal or callable (reactive)."""
        if on is None:
            on = name not in self._c.root.classes
        self._c._bind(on, lambda v: self._c.root.toggle_class(name, bool(v)), f"class {name}")
        self._c._touch()
        return self

    def __contains__(self, name: str) -> bool:
        return name in self._c.root.classes

    def __iter__(self) -> Iterator[str]:
        return iter(list(self._c.root.classes))


class StyleMap:
    """``ref.style``: set/remove individual inline CSS properties."""

    def __init__(self, component: "Component"):
        self._c = component

    def set(self, name: str, value: Any) -> "StyleMap":
        """Set a property; ``value`` may be reactive (Signal/Computed/callable)."""
        self._c._bind(value, lambda v: self._c.root.set_style(name, v), f"style {name}")
        self._c._touch()
        return self

    def remove(self, name: str) -> "StyleMap":
        self._c.root.set_style(name, None)
        self._c._touch()
        return self

    __setitem__ = set

    def __getitem__(self, name: str) -> str | None:
        return self._c.root.style.get(name)


class Component:
    """Base of every UI element. Instances are returned to users as *refs*."""

    kind = "Component"

    def __init__(self, *, classes: str | None = None, style: dict | str | None = None,
                 visible: Any = True, place: bool = True):
        frame = current_frame()
        self.app: "UiApp" = frame.app
        self.parent: Component | None = frame.owner
        self.window: "UiWindow | None" = None
        self._state = CREATED
        self._elements: list[Element] = []
        self._children: list[Component] = []
        self._reactions: list[Reaction] = []
        self._listeners: list[tuple[str, str, Callable]] = []
        self._cleanups: list[Callable[[], Any]] = []
        self._slot_parent: Element | None = None
        self.root = self._build()
        if classes:
            self.root.add_class(*str(classes).split())
        if style:
            self._apply_style(style)
        if visible is not True:
            self._bind(visible, lambda v: self.root.set_attr("hidden", not v), "visible")
        if place:
            self._place(frame)

    # -- construction ---------------------------------------------------------------------
    def _build(self) -> Element:  # pragma: no cover - overridden
        return Element("div", self)

    def _place(self, frame: Frame) -> None:
        if frame.slot is None:
            raise UiError(f"{self.kind} cannot be created here: this callback has no container. "
                          "Use `with container:` to add children at runtime, or ui.when / ui.each.")
        frame.slot.add(self)
        self._slot_parent = frame.slot
        if frame.owner is not None:
            frame.owner._children.append(self)
        if frame.live:
            frame.created.append(self)

    def _apply_style(self, style: dict | str) -> None:
        if isinstance(style, str):
            for decl in style.split(";"):
                if ":" in decl:
                    name, value = decl.split(":", 1)
                    self.root.set_style(name.strip(), value.strip())
        else:
            for name, value in style.items():
                self.style.set(name, value)

    def _html(self) -> str:
        return self.root.html()

    def _bind(self, value: Any, apply: Callable[[Any], Any], prop: str) -> None:
        """Apply ``value`` now; if reactive, re-apply whenever its dependencies change."""
        if is_reactive(value):
            reaction = Reaction(lambda: apply(read(value)), self.app.scheduler, priority=Reaction.RENDER,
                                context=f"{self.path()}.{prop}")
            self._reactions.append(reaction)
        else:
            apply(value)

    def path(self) -> str:
        return f"{self.kind}#{self.root.id if getattr(self, 'root', None) else '?'}"

    # -- lifecycle ------------------------------------------------------------------------
    @property
    def mounted(self) -> bool:
        return self._state == MOUNTED

    @property
    def disposed(self) -> bool:
        return self._state == DISPOSED

    def _mount(self, window: "UiWindow") -> None:
        if self._state != CREATED:
            return
        self.window = window
        for element in self._elements:
            element.window = window
            window._elements[element.id] = self
        for element_id, event, handler in self._listeners:
            window._add_listener(element_id, event, self, handler)
        self._state = MOUNTED
        for child in list(self._children):
            child._mount(window)
        self._on_mount()

    def _on_mount(self) -> None:
        """Hook: runs once after the component's DOM exists."""

    def _teardown(self) -> None:
        if self._state == DISPOSED:
            return
        for child in list(self._children):
            child._teardown()
        self._children.clear()
        for reaction in self._reactions:
            reaction.dispose()
        self._reactions.clear()
        window = self.window
        if window is not None:
            for element_id, event, handler in self._listeners:
                window._remove_listener(element_id, event, self, handler)
            for element in self._elements:
                window._elements.pop(element.id, None)
        self._listeners.clear()
        for element in self._elements:
            element.window = None
        cleanups, self._cleanups = self._cleanups, []
        for cleanup in reversed(cleanups):
            try:
                cleanup()
            except Exception as error:  # cleanup failures are reported, never fatal
                self.app._report(error, f"{self.path()} cleanup")
        self._state = DISPOSED

    def dispose(self) -> None:
        """Remove the component from the UI and release everything it owns."""
        if self._state == DISPOSED:
            return
        self._owner_check()
        mounted = self._state == MOUNTED and self.window is not None and not self.window.closed
        if mounted:
            self.root._op("remove_element")
        if self.parent is not None and self in self.parent._children:
            self.parent._children.remove(self)
        if self._slot_parent is not None and self in self._slot_parent.children:
            self._slot_parent.children.remove(self)
        self._teardown()
        if mounted:
            self.app._request_commit()

    def _emit(self, fn: Callable | None, *args: Any) -> Any:
        """Call a user callback from inside a component handler; drives ``async def`` callbacks."""
        if fn is None:
            return None
        result = fn(*args)
        if inspect.iscoroutine(result):
            from .aio import drive
            return drive(self.app, result, self.path(), owner=self)
        return result

    def on_dispose(self, fn: Callable[[], Any]) -> None:
        """Register a cleanup that runs when this component is disposed."""
        self._cleanups.append(fn)

    def _owner_check(self) -> None:
        if threading.get_ident() != self.app._owner:
            raise WrongThreadError("Components belong to the UI owner thread; use app.post()")

    def _live_check(self) -> None:
        if self._state == DISPOSED:
            raise DisposedComponentError(f"{self.path()} was disposed")
        self._owner_check()

    def _touch(self) -> None:
        if self._state == MOUNTED:
            self.app._request_commit()

    # -- events -----------------------------------------------------------------------------
    def on(self, event: str, handler: Callable, *, element: Element | str | None = None) -> "Component":
        """Call ``handler`` (with the event dict if it takes an argument) for a DOM event."""
        self._live_check()
        check_name(event, "event")
        element_id = element.id if isinstance(element, Element) else (element or self.root.id)
        wrapped = adapt(handler, None)
        self._listen(element_id, event, wrapped)
        return self

    def _listen(self, element_id: str, event: str, handler: Callable) -> None:
        entry = (element_id, event, handler)
        self._listeners.append(entry)
        if self._state == MOUNTED and self.window is not None:
            self.window._add_listener(element_id, event, self, handler)

    # -- common ref API ------------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.root.id

    @property
    def classes(self) -> ClassList:
        return ClassList(self)

    @property
    def style(self) -> StyleMap:
        return StyleMap(self)

    def attr(self, name: str, value: Any = ...) -> Any:
        """Get (one argument) or set an attribute on the root element. ``value`` may be reactive."""
        if value is ...:
            return self.root.attrs.get(name)
        self._live_check()
        self._bind(value, lambda v: self.root.set_attr(name, v), f"attr {name}")
        self._touch()
        return self

    @property
    def visible(self) -> bool:
        return "hidden" not in self.root.attrs

    @visible.setter
    def visible(self, value: Any) -> None:
        self._bind(value, lambda v: self.root.set_attr("hidden", not v), "visible")
        self._touch()

    def focus(self) -> None:
        """Move keyboard focus to this component's focusable element."""
        self._live_check()
        target = self._focus_target()
        if self.window is not None:
            self.window._queue({"op": "focus", "element": target.id})
            self._touch()

    def _focus_target(self) -> Element:
        return self.root

    def scroll_into_view(self, block: str = "nearest") -> None:
        self._live_check()
        if self.window is not None:
            self.window._queue({"op": "scroll_into_view", "element": self.root.id, "block": block})
            self._touch()

    def core_element(self) -> "CoreElement":
        """Validated public Core access to this component's root element."""
        self._live_check()
        if self.window is None or self.window.core is None:
            raise UiError(f"{self.path()} is not mounted in a window yet")
        return CoreElement(self, self.root.id)

    @property
    def core_window(self):
        """The public ``ui4me.Window`` hosting this component (commits pending UI patches first)."""
        self._live_check()
        if self.window is None or self.window.core is None:
            raise UiError(f"{self.path()} is not mounted in a window yet")
        self.window.commit()
        return self.window.core

    @property
    def core_document(self):
        """The raw ``ui4me_core.Document`` (current generation) hosting this component.

        Pending UI patches are committed first. Raw DOM changes inside UI4ME-managed
        elements are not reconciled; prefer a ``ui.html`` island for direct Core work.
        """
        self._live_check()
        if self.window is None or self.window.core is None:
            raise UiError(f"{self.path()} is not mounted in a window yet")
        self.window.commit()
        return self.window.core.document

    def detach_dom_ownership(self) -> None:
        """Stop managing this component's DOM: bindings and listeners are released, DOM stays."""
        self._live_check()
        for reaction in self._reactions:
            reaction.dispose()
        self._reactions.clear()
        if self.window is not None:
            for element_id, event, handler in self._listeners:
                self.window._remove_listener(element_id, event, self, handler)
        self._listeners.clear()
        for element in self._elements:
            element.window = None

    def __repr__(self) -> str:
        return f"<{self.kind} {self.root.id} {self._state}>"


class CoreElement:
    """Thin proxy that binds a Core window method to one element id and validates lifetime."""

    def __init__(self, component: Component, element_id: str):
        self._component, self.element_id = component, element_id

    def __getattr__(self, name: str):
        component = self._component
        component._live_check()
        window = component.window.core
        method = getattr(window, name)
        component.window.commit()
        return lambda *args, **kwargs: method(self.element_id, *args, **kwargs)


class Container(Component):
    """A component with a child slot. Usable as ``with container:`` at build time and later."""

    kind = "Container"

    @property
    def slot(self) -> Element:
        return self.root

    def __enter__(self) -> "Container":
        self._live_check()
        live = self._state == MOUNTED
        self._frame = push(Frame(self.app, self, self.slot, self.window, live=live,
                                 position=(self.slot.id, "beforeend") if live else None))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        frame = self._frame
        pop(frame)
        if frame.live:
            self.app._insert_created(frame, discard=exc is not None)

    def clear(self) -> None:
        """Dispose all children."""
        self._live_check()
        for child in list(self._children):
            child.dispose()


class Group(Container):
    """Plain container with a configurable tag and classes (used by layouts)."""

    kind = "Group"

    def __init__(self, tag: str = "div", cls: str = "", attrs: dict | None = None, **kw):
        self._tag, self._cls, self._attrs = tag, cls, attrs
        super().__init__(**kw)

    def _build(self) -> Element:
        return Element(self._tag, self, cls=self._cls, attrs=self._attrs)


def run_builder(fn: Callable, *args: Any) -> Any:
    """Call a builder function inside the current frame."""
    return adapt(fn, *args)(*args) if args else fn()
