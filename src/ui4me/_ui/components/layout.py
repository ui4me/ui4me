"""Flexbox/grid layout containers, cards, the application shell, tabs and navigation."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from ..component import Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps
from ..reactive import Signal, read, untracked

GAPS = ("none", "xs", "sm", "md", "lg", "xl", "2xl")
ALIGN = {"start": "start", "center": "center", "end": "end", "stretch": "stretch", "baseline": "baseline"}
JUSTIFY = ("start", "center", "end", "between", "around", "evenly")
BREAKPOINTS = ("base", "sm", "md", "lg")
PADS = ("none", "xs", "sm", "md", "lg", "xl")


def _gap(gap: str) -> str:
    if gap not in GAPS:
        raise InvalidComponentProps(f"gap must be one of {', '.join(GAPS)}; got {gap!r}")
    return f"u4-gap-{gap}"


def _align(align: str | None) -> str | None:
    if align is None:
        return None
    if align not in ALIGN:
        raise InvalidComponentProps(f"align must be one of {', '.join(ALIGN)}; got {align!r}")
    return f"u4-align-{align}"


def _justify(justify: str | None) -> str | None:
    if justify is None:
        return None
    if justify not in JUSTIFY:
        raise InvalidComponentProps(f"justify must be one of {', '.join(JUSTIFY)}; got {justify!r}")
    return f"u4-justify-{justify}"


class Box(Container):
    """Generic flex container."""

    kind = "Box"

    def __init__(self, cls: list[str], tag: str = "div", attrs: dict | None = None, **kw: Any):
        self._cls, self._tag, self._attrs = [c for c in cls if c], tag, attrs
        super().__init__(**kw)

    def _build(self) -> Element:
        return Element(self._tag, self, cls=self._cls, attrs=self._attrs)


class Row(Box):
    kind = "Row"

    def __init__(self, *, gap: str = "md", align: str | None = "center", justify: str | None = None,
                 wrap: bool = False, grow: bool = False, **kw: Any):
        super().__init__(["u4-row", _gap(gap), _align(align), _justify(justify), "u4-wrap" if wrap else "",
                          "u4-grow" if grow else ""], **kw)


class Column(Box):
    kind = "Column"

    def __init__(self, *, gap: str = "md", align: str | None = None, justify: str | None = None,
                 grow: bool = False, **kw: Any):
        super().__init__(["u4-column", _gap(gap), _align(align), _justify(justify), "u4-grow" if grow else ""],
                         **kw)


class Stack(Box):
    """Direction that changes at window-width breakpoints: ``direction={'base':'column','md':'row'}``."""

    kind = "Stack"

    def __init__(self, *, direction: str | Mapping[str, str] = "column", gap: str = "md",
                 align: str | None = None, justify: str | None = None, wrap: bool = False, **kw: Any):
        mapping = {"base": direction} if isinstance(direction, str) else dict(direction)
        classes = ["u4-stack", _gap(gap), _align(align), _justify(justify), "u4-wrap" if wrap else ""]
        for point, value in mapping.items():
            if point not in BREAKPOINTS:
                raise InvalidComponentProps(f"breakpoint must be one of {', '.join(BREAKPOINTS)}; got {point!r}")
            if value not in ("row", "column"):
                raise InvalidComponentProps(f"direction must be 'row' or 'column'; got {value!r}")
            classes.append(f"u4-dir-{value}" if point == "base" else f"u4-{point}-dir-{value}")
        if "base" not in mapping:
            classes.append("u4-dir-column")
        super().__init__(classes, **kw)


class Card(Box):
    kind = "Card"

    def __init__(self, *, padding: str = "lg", variant: str = "outlined", gap: str = "md", **kw: Any):
        if variant not in ("outlined", "elevated", "filled", "plain"):
            raise InvalidComponentProps("card variant must be outlined, elevated, filled or plain")
        if padding not in PADS:
            raise InvalidComponentProps(f"padding must be one of {', '.join(PADS)}")
        super().__init__(["u4-card", f"u4-card-{variant}", "" if padding == "lg" else f"u4-pad-{padding}",
                          "" if gap == "md" else _gap(gap)], tag="section", **kw)


class Grid(Box):
    """CSS grid with a fixed column count, or ``min_width`` for auto-fill responsive columns."""

    kind = "Grid"

    def __init__(self, columns: int | None = 2, *, min_width: str | None = None, gap: str = "md", **kw: Any):
        cls = ["u4-grid-auto" if min_width else "u4-grid", _gap(gap)]
        super().__init__(cls, **kw)
        if min_width:
            self.root.set_style("--u4-min", min_width)
        elif columns:
            self.root.set_style("--u4-cols", str(int(columns)))


class Scroll(Box):
    """Scrollable area; give it a height (``height='300px'``) or let a flex parent bound it."""

    kind = "Scroll"

    def __init__(self, *, height: str | None = None, gap: str = "sm", **kw: Any):
        super().__init__(["u4-scroll", "u4-column", _gap(gap)], **kw)
        if height:
            self.root.set_style("max-height", height)

    def scroll_to_end(self) -> None:
        self._live_check()
        if self.window is not None:
            self.window._queue({"op": "scroll_to", "element": self.root.id, "y": 1e9})
            self._touch()


class Shell(Box):
    """Application shell: ``with ui.shell(): with ui.sidebar(): ...; with ui.content(): ...``."""

    kind = "Shell"

    def __init__(self, **kw: Any):
        super().__init__(["u4-shell"], **kw)


class Sidebar(Box):
    kind = "Sidebar"

    def __init__(self, title: str | None = None, **kw: Any):
        super().__init__(["u4-sidebar"], tag="nav", **kw)
        if title:
            self.root.add(Element("div", self, cls="u4-sidebar-title", text=title))


class Content(Box):
    kind = "Content"

    def __init__(self, **kw: Any):
        super().__init__(["u4-content"], tag="section", **kw)


class Split(Container):
    """Two panes side by side (stacked on narrow windows): ``with split.side: ...; with split.main: ...``."""

    kind = "Split"

    def __init__(self, *, side: str = "40%", **kw: Any):
        self._side_width = side
        super().__init__(**kw)
        self.root.set_style("--u4-split", side)
        self.side = _Pane(self, self._side_el, "side")
        self.main = _Pane(self, self._main_el, "main")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-split")
        self._side_el = Element("div", self, cls="u4-split-side")
        self._main_el = Element("div", self, cls="u4-split-main")
        root.add(self._side_el, self._main_el)
        return root

    @property
    def slot(self) -> Element:
        return self._side_el


class _Pane:
    """A named slot of a multi-slot container, usable as a context manager."""

    def __init__(self, owner: Container, element: Element, name: str):
        self._owner, self._element, self.name = owner, element, name

    def __enter__(self):
        owner = self._owner
        owner._live_check()
        live = owner.mounted
        self._frame = push(Frame(owner.app, owner, self._element, owner.window, live=live,
                                 position=(self._element.id, "beforeend") if live else None))
        return self

    def __exit__(self, exc_type, exc, tb):
        pop(self._frame)
        if self._frame.live:
            self._owner.app._insert_created(self._frame, discard=exc is not None)


class Tabs(Container):
    """Tabbed views. Panels render on first selection and keep their state afterwards."""

    kind = "Tabs"

    def __init__(self, tabs: Mapping[str, Callable[[], Any]], *, selected: Any = None, on_change=None, **kw: Any):
        if not tabs:
            raise InvalidComponentProps("ui.tabs needs at least one tab")
        self._tabs = dict(tabs)
        names = list(self._tabs)
        if isinstance(selected, Signal):
            self.state = selected
        else:
            self.state = Signal(selected if selected is not None else names[0], name="tabs selected")
        if untracked(lambda: self.state.value) not in self._tabs:
            raise InvalidComponentProps(f"selected tab {self.state.peek()!r} is not one of {names}")
        self._built: set[str] = set()
        super().__init__(**kw)
        self._on_change = adapt(on_change, None)
        for name, button in self._buttons.items():
            self._listen(button.id, "click", lambda _e, n=name: self._select(n))
        self._listen(self._list.id, "keydown", self._on_key)
        self._bind(lambda: self.state.value, self._show, "selected")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-tabs")
        self._list = Element("div", self, cls="u4-tab-list", attrs={"role": "tablist"})
        self._buttons: dict[str, Element] = {}
        self._panels: dict[str, Element] = {}
        for name in self._tabs:
            panel = Element("div", self, cls="u4-tab-panel", attrs={"role": "tabpanel", "hidden": True})
            button = Element("button", self, cls="u4-tab", attrs={"type": "button", "role": "tab",
                                                                    "aria-selected": "false",
                                                                    "aria-controls": panel.id}, text=name)
            self._list.add(button)
            self._buttons[name], self._panels[name] = button, panel
        root.add(self._list, *self._panels.values())
        return root

    @property
    def slot(self) -> Element:
        return self._panels[self.state.peek()]

    def _select(self, name: str) -> None:
        if name != self.state.peek():
            self.state.set(name)
            self._emit(self._on_change, name)

    def _on_key(self, event: dict) -> None:
        key = event.get("key")
        names = list(self._tabs)
        index = names.index(self.state.peek())
        if key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            index = {"ArrowRight": (index + 1) % len(names), "ArrowLeft": (index - 1) % len(names),
                     "Home": 0, "End": len(names) - 1}[key]
            self._select(names[index])
            if self.window is not None:
                self.window._queue({"op": "focus", "element": self._buttons[names[index]].id})

    def _show(self, name: str) -> None:
        if name not in self._tabs:
            return
        for tab, button in self._buttons.items():
            active = tab == name
            button.set_attr("aria-selected", "true" if active else "false")
            button.set_attr("tabindex", None if active else "-1")
            self._panels[tab].set_attr("hidden", not active)
        if name not in self._built:
            self._built.add(name)
            panel = self._panels[name]
            live = self.mounted
            frame = push(Frame(self.app, self, panel, self.window, live=live,
                               position=(panel.id, "beforeend") if live else None))
            try:
                untracked(self._tabs[name])
            finally:
                pop(frame)
            if live:
                self.app._insert_created(frame)

    @property
    def selected(self) -> str:
        return self.state.value

    def select(self, name: str) -> None:
        if name not in self._tabs:
            raise InvalidComponentProps(f"no tab named {name!r}")
        self.state.set(name)


class Navigation(Container):
    """Sidebar navigation between named pages (in-process view state, no URLs).

    ``ui.navigation({'Home': home, 'Settings': settings}, title='My app')``. Pages render on
    first visit and keep their state. ``app.navigation`` / ``ui.navigate(name)`` switch pages.
    """

    kind = "Navigation"

    def __init__(self, pages: Mapping[str, Callable[[], Any]], *, title: str | None = None,
                 selected: str | None = None, state: Signal | None = None, **kw: Any):
        if not pages:
            raise InvalidComponentProps("ui.navigation needs at least one page")
        self._pages = dict(pages)
        self._title = title
        super().__init__(**kw)
        self.state = (state if state is not None else
                      self.app.navigation if not self.app._navigation_regions else
                      Signal(selected or next(iter(self._pages)), name="navigation selected"))
        self.app._navigation_regions.append(self)
        self.on_dispose(lambda: self.app._navigation_regions.remove(self) if self in self.app._navigation_regions else None)
        if untracked(lambda: self.state.value) not in self._pages:
            self.state.set(selected or next(iter(self._pages)))
        self._built: set[str] = set()
        for name, item in self._items.items():
            self._listen(item.id, "click", lambda _e, n=name: self.state.set(n))
        self._bind(lambda: self.state.value, self._show, "page")

    def select(self, page: str) -> None:
        if page not in self._pages:
            raise InvalidComponentProps(f"unknown page {page!r}")
        self.state.set(page)

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-shell")
        nav = Element("nav", self, cls="u4-sidebar")
        if self._title:
            nav.add(Element("div", self, cls="u4-sidebar-title", text=self._title))
        self._items: dict[str, Element] = {}
        self._pages_el: dict[str, Element] = {}
        content = Element("section", self, cls="u4-content")
        for name in self._pages:
            item = Element("button", self, cls="u4-nav-item", attrs={"type": "button"}, text=name)
            nav.add(item)
            page = Element("div", self, cls="u4-column u4-gap-md", attrs={"hidden": True})
            content.add(page)
            self._items[name], self._pages_el[name] = item, page
        root.add(nav, content)
        return root

    @property
    def slot(self) -> Element:
        return self._pages_el[self.state.peek()]

    def _show(self, name: str) -> None:
        if name not in self._pages:
            return
        for page, item in self._items.items():
            active = page == name
            item.set_attr("aria-current", "page" if active else None)
            self._pages_el[page].set_attr("hidden", not active)
        if name not in self._built:
            self._built.add(name)
            element = self._pages_el[name]
            live = self.mounted
            frame = push(Frame(self.app, self, element, self.window, live=live,
                               position=(element.id, "beforeend") if live else None))
            try:
                untracked(self._pages[name])
            finally:
                pop(frame)
            if live:
                self.app._insert_created(frame)
