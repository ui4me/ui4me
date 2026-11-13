"""Desktop/UI building blocks composed only from UI4ME Core DOM and existing UI runtime.

No browser, JS, network, or new native backend. Public APIs live in ui.py.
Builder callbacks are evaluated in an owned component scope. Event callbacks run on
UI4ME's owner thread; reactive props follow the standard Signal/computed contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from ..component import Component, Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps
from ..reactive import Signal, read, untracked
from .basic import TextField
from .feedback import Dialog
from .layout import Box


class Surface(Box):
    """Generic semantic surface for paper, sections, headers, status bars, and toolbars."""
    kind = "Surface"

    def __init__(self, *, role: str = "paper", tag: str | None = None, padding: str = "md", **kw: Any):
        allowed = {"paper": "section", "toolbar": "div", "header": "header", "footer": "footer",
                   "statusbar": "div", "section": "section", "center": "div", "group": "div",
                   "sticky": "div", "container": "div"}
        if role not in allowed:
            raise InvalidComponentProps(f"unknown surface role {role!r}")
        if padding not in ("none", "xs", "sm", "md", "lg", "xl"):
            raise InvalidComponentProps("padding must be none, xs, sm, md, lg or xl")
        attrs = {"role": "toolbar" if role == "toolbar" else "status"} if role in ("toolbar", "statusbar") else None
        super().__init__(["u4-surface", f"u4-{role}", f"u4-pad-{padding}"], tag=tag or allowed[role],
                         attrs=attrs, **kw)


class AspectRatio(Container):
    """Aspect-ratio wrapper; content is normal managed UI, not rasterized."""
    kind = "AspectRatio"

    def __init__(self, ratio: float = 16 / 9, **kw: Any):
        if not 0 < ratio <= 100:
            raise InvalidComponentProps("ratio must be positive and <=100")
        self._ratio = ratio
        super().__init__(**kw)
        self.root.set_style("aspect-ratio", str(ratio))

    def _build(self) -> Element:
        return Element("div", self, cls="u4-aspect")


class LabelText(Component):
    """Inline presentation for kbd, inline code, initials, or a descriptive label."""
    kind = "LabelText"

    def __init__(self, content: Any, *, kind: str, **kw: Any):
        tags = {"kbd": "kbd", "inline-code": "code", "avatar": "span", "mark": "mark", "small": "small"}
        if kind not in tags:
            raise InvalidComponentProps(f"unsupported text kind {kind}")
        self._tag, self._kind = tags[kind], kind
        super().__init__(**kw)
        self._bind(content, lambda v: self.root.set_text(v), "content")

    def _build(self) -> Element:
        return Element(self._tag, self, cls=f"u4-{self._kind}")


class Link(Component):
    """A safe explicit anchor or button-like link. Never evaluates JavaScript URLs."""
    kind = "Link"

    def __init__(self, label: Any, *, href: str | None = None, on_click: Callable | None = None,
                 external: bool = False, **kw: Any):
        if href is None and on_click is None:
            raise InvalidComponentProps("link requires href or on_click")
        if href is not None:
            parts = urlsplit(href)
            if parts.scheme not in ("", "http", "https", "mailto") or href.lstrip().lower().startswith("javascript:"):
                raise InvalidComponentProps("links support local, http(s), or mailto URLs only")
        self._href, self._external = href, external
        super().__init__(**kw)
        self._bind(label, self.root.set_text, "label")
        self._action = adapt(on_click, None)
        if on_click is not None:
            self._listen(self.root.id, "click", self._clicked)

    def _build(self) -> Element:
        if self._href is None:
            return Element("button", self, cls="u4-link", attrs={"type": "button"})
        attrs = {"href": self._href}
        if self._external:
            attrs.update(target="_blank", rel="noopener noreferrer")
        return Element("a", self, cls="u4-link", attrs=attrs)

    def _clicked(self, event: dict) -> None:
        self._emit(self._action, event)


# Small bundled SVG path catalogue. Additional user icons are supported via trusted SVG markup.
_ICONS: dict[str, str] = {
    "plus": 'M12 5v14M5 12h14', "minus": 'M5 12h14', "check": 'M20 6 9 17l-5-5',
    "x": 'M18 6 6 18M6 6l12 12', "search": 'm21 21-4.35-4.35M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16',
    "menu": 'M4 7h16M4 12h16M4 17h16', "chevron-down": 'm6 9 6 6 6-6',
    "chevron-right": 'm9 18 6-6-6-6', "chevron-left": 'm15 18-6-6 6-6',
    "arrow-left": 'm12 19-7-7 7-7M5 12h14', "arrow-right": 'M5 12h14m-7-7 7 7-7 7',
    "settings": 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M19.07 4.93l-1.41 1.41M6.34 17.66l-1.41 1.41',
    "home": 'm3 10 9-7 9 7v10H3V10m6 10v-7h6v7', "folder": 'M3 6h6l2 3h10v11H3V6',
    "file": 'M5 3h10l4 4v14H5V3m10 0v5h4', "refresh": 'M20 11a8 8 0 1 0-2 6m2-5v-6m0 6h-6',
    "info": 'M12 17v-5m0-5h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
    "warning": 'm12 2 10 19H2L12 2m0 7v5m0 4h.01', "download": 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
    "upload": 'M12 17V5m-5 5 5-5 5 5M4 17v4h16v-4', "edit": 'm4 20 5-1 11-11-4-4L5 15l-1 5',
    "trash": 'M3 6h18M8 6V4h8v2m2 0-1 15H7L6 6m4 4v7m4-7v7',
}


class Icon(Component):
    """Inline stroke SVG. Unknown icon names fail visibly; no remote icon/font dependency."""
    kind = "Icon"

    def __init__(self, name: str, *, size: int = 18, label: str | None = None, **kw: Any):
        if name not in _ICONS:
            raise InvalidComponentProps(f"unknown icon {name!r}; use ui.icon_names() to list installed icons")
        if not 8 <= size <= 128:
            raise InvalidComponentProps("icon size must be 8..128 px")
        self._name, self._size, self._label = name, int(size), label
        super().__init__(**kw)

    def _build(self) -> Element:
        attrs = {"viewBox": "0 0 24 24", "width": str(self._size), "height": str(self._size),
                 "fill": "none", "stroke": "currentColor", "stroke-width": "1.8",
                 "stroke-linecap": "round", "stroke-linejoin": "round",
                 "role": "img" if self._label else "presentation",
                 "aria-label": self._label, "aria-hidden": None if self._label else "true"}
        root = Element("svg", self, cls="u4-icon", attrs=attrs)
        root.add(Element("path", self, attrs={"d": _ICONS[self._name]}))
        return root


def icon_names() -> tuple[str, ...]:
    return tuple(sorted(_ICONS))


class IconButton(Component):
    kind = "IconButton"

    def __init__(self, icon: str, *, label: str, on_click: Callable | None = None, variant: str = "ghost",
                 disabled: Any = False, **kw: Any):
        if not label:
            raise InvalidComponentProps("icon buttons require an accessible label")
        if icon not in _ICONS:
            raise InvalidComponentProps(f"unknown icon {icon!r}")
        if variant not in ("primary", "secondary", "outline", "ghost", "danger"):
            raise InvalidComponentProps("unknown button variant")
        self._icon, self._label, self._variant = icon, label, variant
        self._action = adapt(on_click, None)
        super().__init__(**kw)
        self._bind(disabled, lambda v: self.root.set_attr("disabled", bool(v)), "disabled")
        self._listen(self.root.id, "click", lambda e: self._emit(self._action, e) if not self.root.attrs.get("disabled") else None)

    def _build(self) -> Element:
        root = Element("button", self, cls=f"u4-icon-button u4-btn u4-btn-{self._variant}",
                       attrs={"type": "button", "aria-label": self._label, "title": self._label})
        svg = Element("svg", self, attrs={"viewBox": "0 0 24 24", "width": "18", "height": "18",
                                           "stroke": "currentColor", "fill": "none", "stroke-width": "2",
                                           "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true"})
        svg.add(Element("path", self, attrs={"d": _ICONS[self._icon]}))
        return root.add(svg)


class Breadcrumbs(Component):
    """Navigation breadcrumb from [(label, callback-or-href), ...]."""
    kind = "Breadcrumbs"

    def __init__(self, items: Sequence[tuple[str, Any]], *, separator: str = "/", **kw: Any):
        self._items, self._separator = list(items), separator
        super().__init__(**kw)
        for element, action in self._actions:
            if callable(action):
                self._listen(element.id, "click", lambda e, fn=adapt(action, None): self._emit(fn, e))

    def _build(self) -> Element:
        root = Element("nav", self, cls="u4-breadcrumbs", attrs={"aria-label": "Breadcrumbs"})
        listing = Element("ol", self, cls="u4-breadcrumb-list")
        self._actions = []
        for index, (label, action) in enumerate(self._items):
            li = Element("li", self, cls="u4-breadcrumb")
            if index:
                li.add(Element("span", self, cls="u4-breadcrumb-separator", attrs={"aria-hidden": "true"},
                               text=self._separator))
            if index == len(self._items) - 1:
                li.add(Element("span", self, attrs={"aria-current": "page"}, text=str(label)))
            elif callable(action):
                control = Element("button", self, cls="u4-link", attrs={"type": "button"}, text=str(label))
                li.add(control)
                self._actions.append((control, action))
            else:
                uri = str(action)
                if urlsplit(uri).scheme not in ("", "http", "https", "mailto"):
                    raise InvalidComponentProps("invalid breadcrumb URL scheme")
                li.add(Element("a", self, attrs={"href": uri}, text=str(label)))
            listing.add(li)
        root.add(listing)
        return root


class Disclosure(Container):
    """Native details/summary disclosure; no overlay or JS requirements."""
    kind = "Disclosure"

    def __init__(self, label: Any, *, open: Any = False, **kw: Any):
        self._label = label
        super().__init__(**kw)
        self._bind(label, self._summary.set_text, "label")
        self._bind(open, lambda value: self.root.set_attr("open", bool(value)), "open")

    def _build(self) -> Element:
        root = Element("details", self, cls="u4-disclosure")
        self._summary = Element("summary", self, cls="u4-disclosure-title")
        self._body = Element("div", self, cls="u4-disclosure-body")
        root.add(self._summary, self._body)
        return root

    @property
    def slot(self) -> Element:
        return self._body


class Accordion(Container):
    """A small collection of disclosures. Builders create normal managed child components."""
    kind = "Accordion"

    def __init__(self, sections: Mapping[str, Callable[[], Any]], *, initial: str | None = None, **kw: Any):
        if not sections:
            raise InvalidComponentProps("accordion requires sections")
        self._sections, self._initial = dict(sections), initial
        super().__init__(**kw)
        for title, slot in self._slots.items():
            frame = push(Frame(self.app, self, slot, self.window))
            try:
                untracked(self._sections[title])
            finally:
                pop(frame)

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-accordion")
        self._slots = {}
        for title in self._sections:
            details = Element("details", self, cls="u4-disclosure", attrs={"open": title == self._initial})
            summary = Element("summary", self, cls="u4-disclosure-title", text=title)
            content = Element("div", self, cls="u4-disclosure-body")
            details.add(summary, content)
            root.add(details)
            self._slots[title] = content
        return root


class InputType(TextField):
    """Native HTML input types with UI4ME field binding and validation chrome."""
    kind = "SpecialInput"

    def __init__(self, label: str = "", *, type: str, value: str = "", **kw: Any):
        if type not in ("email", "url", "search", "tel"):
            raise InvalidComponentProps(
                "unsupported input type; UI4ME Core 1.x has no native date/time/colour pickers, "
                "use ui.date, ui.time, ui.datetime, ui.month, ui.week or ui.color")
        super().__init__(label, type=type, value=value, **kw)


class Segmented(Component):
    """Accessible reactive single-choice button group (no hidden form control)."""
    kind = "Segmented"

    def __init__(self, options: Mapping[str, str] | Sequence[str], *, selected: str | None = None,
                 bind: Signal | None = None, on_change: Callable | None = None, **kw: Any):
        self._options = dict(options) if isinstance(options, Mapping) else {str(k): str(k) for k in options}
        if not self._options:
            raise InvalidComponentProps("segmented options cannot be empty")
        self.state = bind if bind is not None else Signal(selected or next(iter(self._options)), name="segmented")
        if self.state.peek() not in self._options:
            raise InvalidComponentProps("segmented selected value not in options")
        self._changed = adapt(on_change, None)
        super().__init__(**kw)
        for value, button in self._buttons.items():
            self._listen(button.id, "click", lambda _e, v=value: self.select(v))
        self._bind(lambda: self.state.value, self._refresh, "selected")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-segmented", attrs={"role": "group"})
        self._buttons = {}
        for key, label in self._options.items():
            b = Element("button", self, cls="u4-segmented-item", attrs={"type": "button", "aria-pressed": "false"},
                        text=label)
            root.add(b)
            self._buttons[key] = b
        return root

    def _refresh(self, value: str) -> None:
        for key, button in self._buttons.items():
            button.set_attr("aria-pressed", "true" if value == key else "false")
            button.toggle_class("u4-selected", value == key)

    def select(self, value: str) -> None:
        if value not in self._options:
            raise InvalidComponentProps("value is not one of the segmented options")
        if value != self.state.peek():
            self.state.set(value)
            self._emit(self._changed, value)

    @property
    def value(self) -> str:
        return self.state.value


@dataclass(frozen=True)
class TreeNode:
    id: str
    label: str
    children: tuple["TreeNode", ...] = field(default_factory=tuple)


class TreeView(Component):
    """Local immutable tree with stable node IDs, expansion and keyboard selection.

    This is the lightweight navigation tree, *not* a virtualized filesystem model.
    """
    kind = "TreeView"

    def __init__(self, nodes: Sequence[TreeNode], *, selected: str | None = None,
                 on_select: Callable[[str], Any] | None = None, **kw: Any):
        self._nodes = tuple(nodes)
        self.selected = Signal(selected, name="tree selection")
        self.expanded = Signal(frozenset(), name="tree expanded")
        self._action = adapt(on_select, None)
        self._all: dict[str, TreeNode] = {}
        self._entries: dict[str, tuple[Element, Element | None]] = {}
        super().__init__(**kw)
        for node_id, (entry, _) in self._entries.items():
            self._listen(entry.id, "click", lambda _e, name=node_id: self.select(name))
            self._listen(entry.id, "keydown", lambda e, name=node_id: self._key(e, name))
        self._bind(lambda: (self.selected.value, self.expanded.value), self._refresh, "selection")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-tree", attrs={"role": "tree", "aria-label": "Tree view"})

        def add(items: Sequence[TreeNode], parent: Element, *, depth: int) -> None:
            for item in items:
                if item.id in self._all:
                    raise InvalidComponentProps(f"duplicate tree node id {item.id!r}")
                self._all[item.id] = item
                wrap = Element("div", self, cls="u4-tree-node")
                entry = Element("button", self, cls="u4-tree-item", text=item.label,
                                attrs={"type": "button", "role": "treeitem", "aria-level": str(depth),
                                       "aria-selected": "false", "aria-expanded": "false" if item.children else None})
                entry.set_style("padding-left", f"{(depth - 1) * 18 + 8}px")
                wrap.add(entry)
                sub = None
                if item.children:
                    sub = Element("div", self, cls="u4-tree-group", attrs={"role": "group", "hidden": True})
                    add(item.children, sub, depth=depth + 1)
                    wrap.add(sub)
                parent.add(wrap)
                self._entries[item.id] = (entry, sub)

        add(self._nodes, root, depth=1)
        return root

    def select(self, node_id: str) -> None:
        if node_id not in self._all:
            raise InvalidComponentProps(f"unknown tree node {node_id!r}")
        if self.selected.peek() != node_id:
            self.selected.set(node_id)
            self._emit(self._action, node_id)

    def toggle(self, node_id: str) -> None:
        if node_id not in self._all:
            raise InvalidComponentProps(f"unknown tree node {node_id!r}")
        values = set(self.expanded.peek())
        if node_id in values:
            values.remove(node_id)
        else:
            values.add(node_id)
        self.expanded.set(frozenset(values))

    def _refresh(self, value: tuple[str | None, frozenset]) -> None:
        selection, expanded = value
        for key, (button, sub) in self._entries.items():
            button.set_attr("aria-selected", "true" if key == selection else "false")
            button.toggle_class("u4-selected", key == selection)
            if sub is not None:
                sub.set_attr("hidden", key not in expanded)
                button.set_attr("aria-expanded", "true" if key in expanded else "false")

    def _key(self, event: dict, node_id: str) -> None:
        key = event.get("key")
        if key in ("Enter", " "):
            self.select(node_id)
        elif key in ("ArrowRight", "ArrowLeft") and self._all[node_id].children:
            expanded = node_id in self.expanded.peek()
            if (key == "ArrowRight" and not expanded) or (key == "ArrowLeft" and expanded):
                self.toggle(node_id)
        elif key in ("ArrowUp", "ArrowDown"):
            visible: list[str] = []
            def visit(items):
                for item in items:
                    visible.append(item.id)
                    if item.id in self.expanded.peek():
                        visit(item.children)
            visit(self._nodes)
            idx = visible.index(node_id) + (-1 if key == "ArrowUp" else 1)
            if 0 <= idx < len(visible):
                target = visible[idx]
                self.select(target)
                if self.window is not None:
                    self.window._queue({"op": "focus", "element": self._entries[target][0].id})


class Drawer(Dialog):
    """Side dialog with Core's modal semantics and focus trapping."""
    kind = "Drawer"

    def __init__(self, title: str | None = None, *, side: str = "right", **kw: Any):
        if side not in ("left", "right"):
            raise InvalidComponentProps("drawer side must be left or right")
        self._side = side
        super().__init__(title, **kw)
        self.root.add_class("u4-drawer", f"u4-drawer-{side}")


class EmptyDiv(Container):
    """Composable slot with a named anatomy class for custom library components."""
    kind = "Slot"

    def __init__(self, name: str, **kw: Any):
        if not name or not all(ch.isalnum() or ch in "-_" for ch in name):
            raise InvalidComponentProps("slot name must contain letters, digits, dashes or underscores")
        self._name = name
        super().__init__(**kw)

    def _build(self) -> Element:
        return Element("div", self, cls=f"u4-slot u4-slot-{self._name}", attrs={"data-slot": self._name})


@dataclass(frozen=True)
class MenuItem:
    label: str
    action: Callable[[], Any] | None = None
    disabled: bool = False
    shortcut: str | None = None
    separator: bool = False


class Menu(Component):
    """Accessible in-window menu, usable where Core native menus are unavailable.

    Keyboard: Enter/Space/ArrowDown open; arrows navigate; Escape closes;
    actions close the menu. Outside-click dismissal is deliberately not claimed.
    """
    kind = "Menu"

    def __init__(self, label: str, items: Sequence[MenuItem], **kw: Any):
        self._label, self._items = label, tuple(items)
        if not label:
            raise InvalidComponentProps("menu requires an accessible trigger label")
        self.is_open = Signal(False, name="menu open")
        super().__init__(**kw)
        self._listen(self.trigger.id, "click", lambda _: self.toggle())
        self._listen(self.trigger.id, "keydown", self._on_trigger_key)
        self._listen(self.list_el.id, "keydown", self._on_menu_key)
        for index, button in self._buttons.items():
            self._listen(button.id, "click", lambda _e, i=index: self.select(i))
        self._bind(lambda: self.is_open.value, self._update_open, "open")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-menu-wrap")
        self.list_el = Element("div", self, cls="u4-menu-list", attrs={"role": "menu", "hidden": True})
        self.trigger = Element("button", self, cls="u4-btn u4-btn-secondary u4-menu-trigger",
                               attrs={"type": "button", "aria-haspopup": "menu",
                                      "aria-expanded": "false", "aria-controls": self.list_el.id}, text=self._label)
        self._buttons: dict[int, Element] = {}
        for index, item in enumerate(self._items):
            if item.separator:
                self.list_el.add(Element("hr", self, cls="u4-menu-separator", attrs={"role": "separator"}))
            else:
                button = Element("button", self, cls="u4-menu-item", attrs={"type": "button", "role": "menuitem",
                                                                          "tabindex": "-1", "disabled": item.disabled})
                button.add(Element("span", self, text=item.label))
                if item.shortcut:
                    button.add(Element("kbd", self, cls="u4-kbd", text=item.shortcut))
                self.list_el.add(button)
                self._buttons[index] = button
        root.add(self.trigger, self.list_el)
        return root

    def _update_open(self, value: bool) -> None:
        self.trigger.set_attr("aria-expanded", "true" if value else "false")
        self.list_el.set_attr("hidden", not value)

    def _valid(self) -> list[int]:
        return [idx for idx, item in enumerate(self._items) if not item.disabled and not item.separator]

    def open(self) -> None:
        self.is_open.set(True)
        self._focus_index(0)

    def close(self) -> None:
        self.is_open.set(False)
        if self.window is not None:
            self.window._queue({"op": "focus", "element": self.trigger.id})

    def toggle(self) -> None:
        if self.is_open.peek():
            self.close()
        else:
            self.open()

    def select(self, index: int) -> None:
        if index not in self._valid():
            return
        self.close()
        action = self._items[index].action
        if action is not None:
            self._emit(action)

    def _focus_index(self, position: int) -> None:
        choices = self._valid()
        if choices and self.window is not None:
            target = self._buttons[choices[position % len(choices)]]
            self.window._queue({"op": "focus", "element": target.id})

    def _on_trigger_key(self, event: dict) -> None:
        if event.get("key") in ("ArrowDown", "Enter", " "):
            self.open()

    def _on_menu_key(self, event: dict) -> None:
        key = event.get("key")
        if key == "Escape":
            self.close()
        elif key in ("ArrowDown", "ArrowUp", "Home", "End"):
            choices = self._valid()
            if not choices:
                return
            current = next((i for i, k in enumerate(choices) if self._buttons[k].id == event.get("element")), 0)
            position = (current + (1 if key == "ArrowDown" else -1)) % len(choices)
            if key == "Home":
                position = 0
            elif key == "End":
                position = len(choices) - 1
            self._focus_index(position)


class ProgressRing(Component):
    """Indeterminate? No: this is a determinate SVG progress indicator (0..1)."""
    kind = "ProgressRing"

    def __init__(self, value: Any = 0, *, size: int = 48, thickness: int = 5, **kw: Any):
        if not 20 <= size <= 240 or not 1 <= thickness <= size / 4:
            raise InvalidComponentProps("progress ring size must be 20..240; thickness 1..size/4")
        self._size, self._thickness = size, thickness
        self._radius = (size - thickness) / 2
        self._circumference = 2 * 3.141592653589793 * self._radius
        super().__init__(**kw)
        self._bind(value, self._set, "value")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-progress-ring", attrs={"role": "progressbar", "aria-valuemin": "0",
                                                                   "aria-valuemax": "100"})
        svg = Element("svg", self, attrs={"viewBox": f"0 0 {self._size} {self._size}",
                                           "width": str(self._size), "height": str(self._size),
                                           "aria-hidden": "true"})
        common = {"cx": str(self._size / 2), "cy": str(self._size / 2), "r": str(self._radius),
                  "fill": "none", "stroke-width": str(self._thickness)}
        svg.add(Element("circle", self, cls="u4-ring-track", attrs=common))
        self.bar = Element("circle", self, cls="u4-ring-value", attrs={**common, "stroke-dasharray": str(self._circumference)})
        svg.add(self.bar)
        root.add(svg)
        return root

    def _set(self, value: float) -> None:
        ratio = min(1.0, max(0.0, float(value)))
        self.root.set_attr("aria-valuenow", str(round(ratio * 100)))
        self.bar.set_attr("stroke-dashoffset", str(self._circumference * (1 - ratio)))


class Sparkline(Component):
    """Tiny static/fully reactive line chart using Core SVG, no JS or third-party renderer."""
    kind = "Sparkline"

    def __init__(self, values: Any, *, width: int = 160, height: int = 48, **kw: Any):
        if width < 20 or height < 10:
            raise InvalidComponentProps("sparkline needs width>=20 and height>=10")
        self._width, self._height = width, height
        super().__init__(**kw)
        self._bind(values, self._draw, "values")

    def _build(self) -> Element:
        root = Element("svg", self, cls="u4-sparkline", attrs={"viewBox": f"0 0 {self._width} {self._height}",
                                                             "width": str(self._width), "height": str(self._height),
                                                             "role": "img", "aria-label": "Trend chart"})
        self.line = Element("polyline", self, attrs={"fill": "none", "stroke": "currentColor", "stroke-width": "2"})
        root.add(self.line)
        return root

    def _draw(self, data: Sequence[float]) -> None:
        values = [float(v) for v in data or ()]
        if not values:
            self.line.set_attr("points", "")
            return
        lo, hi = min(values), max(values)
        span = max(hi - lo, 1e-12)
        points = []
        for i, v in enumerate(values):
            x = 3 + i * (self._width - 6) / max(len(values) - 1, 1)
            y = 3 + (1 - (v - lo) / span) * (self._height - 6)
            points.append(f"{x:.2f},{y:.2f}")
        self.line.set_attr("points", " ".join(points))
        self.root.set_attr("aria-label", f"Trend chart from {values[0]:g} to {values[-1]:g}")


class PathPicker(Container):
    """Text field + native Core picker. Path remains an editable string Signal."""
    kind = "PathPicker"

    def __init__(self, label: str = "Path", *, mode: str = "open", value: str = "",
                 bind: Signal | None = None, on_change: Callable | None = None, **kw: Any):
        if mode not in ("open", "save", "folder"):
            raise InvalidComponentProps("path picker mode must be open, save, or folder")
        self._label, self._mode = label, mode
        self.state = bind if bind is not None else Signal(value, name="path picker")
        self._action = adapt(on_change, None)
        super().__init__(**kw)
        frame = push(Frame(self.app, self, self.slot, self.window))
        try:
            self.input = TextField(label, bind=self.state, on_change=self._changed)
            from .basic import Button
            self.browse = Button("Browse…", variant="secondary", on_click=self._choose)
        finally:
            pop(frame)

    def _build(self) -> Element:
        return Element("div", self, cls="u4-path-picker u4-row u4-gap-sm")

    def _changed(self, value: str) -> None:
        self._emit(self._action, value)

    async def _choose(self) -> None:
        picker = {"open": self.app.dialogs.open_file, "save": self.app.dialogs.save_file,
                  "folder": self.app.dialogs.folder}[self._mode]
        result = await picker(window=self.window)
        if result is not None and not self.disposed:
            value = str(result)
            if self.state.peek() != value:
                self.state.set(value)
                self._changed(value)

    @property
    def value(self) -> str:
        return self.state.value


class FileField(Component):
    """Native Core-backed file input, with chosen paths exposed as reactive strings."""
    kind = "FileField"

    def __init__(self, label: str = "Choose file", *, multiple: bool = False, accept: str | None = None,
                 on_change: Callable | None = None, **kw: Any):
        self._label, self._multiple, self._accept = label, multiple, accept
        self.paths: Signal[list[str]] = Signal([], name="file paths")
        self._action = adapt(on_change, None)
        super().__init__(**kw)
        self._listen(self.control.id, "change", self._changed)

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-field")
        self.control = Element("input", self, cls="u4-input", attrs={"type": "file",
                                                                       "multiple": self._multiple,
                                                                       "accept": self._accept})
        root.add(Element("label", self, cls="u4-label", attrs={"for": self.control.id}, text=self._label),
                 self.control)
        return root

    def _changed(self, event: dict) -> None:
        paths = event.get("files")
        if paths is None and self.window is not None:
            paths = self.window.core.get_files(self.control.id)
        values = [str(p) for p in (paths or [])]
        self.paths.set(values)
        self._emit(self._action, values)

    @property
    def value(self) -> list[str]:
        return self.paths.value

    def _focus_target(self) -> Element:
        return self.control


class ComboBox(Container):
    """Searchable, keyboard-operable local listbox with a stable controlled selection.

    This is intentionally bounded to a local sequence; remote autocomplete should
    use an application-supplied search service with cancellation and a separate
    source model, not silently perform network calls from a UI component.
    """
    kind = "ComboBox"

    def __init__(self, options: Mapping[str, str] | Sequence[str], *, label: str = "Choose",
                 selected: str | None = None, bind: Signal | None = None,
                 on_change: Callable | None = None, **kw: Any):
        self.options = dict(options) if isinstance(options, Mapping) else {str(x): str(x) for x in options}
        if len(self.options) > 2000:
            raise InvalidComponentProps("local combobox supports up to 2000 entries; use a data source for larger sets")
        if selected is not None and selected not in self.options:
            raise InvalidComponentProps("initial combobox selection not in options")
        self.selected = bind if bind is not None else Signal(selected, name="combobox selected")
        if self.selected.peek() is not None and self.selected.peek() not in self.options:
            raise InvalidComponentProps("bound combobox selection not in options")
        self.query = Signal(self.options.get(self.selected.peek(), ""), name="combobox query")
        self.is_open = Signal(False, name="combobox open")
        self._on_change = adapt(on_change, None)
        self._active_index = 0
        super().__init__(**kw)
        frame = push(Frame(self.app, self, self.slot, self.window))
        try:
            self.input = TextField(label, bind=self.query, placeholder="Type to filter", on_change=self._on_input)
        finally:
            pop(frame)
        self.input.control.set_attr("role", "combobox")
        self.input.control.set_attr("aria-haspopup", "listbox")
        self.input.control.set_attr("aria-autocomplete", "list")
        self.input.control.set_attr("aria-controls", self.listbox.id)
        self._listen(self.input.control.id, "focus", lambda _: self.show())
        self._listen(self.input.control.id, "keydown", self._key)
        for value, element in self._buttons.items():
            self._listen(element.id, "click", lambda _e, name=value: self.choose(name))
        self._bind(lambda: self.selected.value, self._sync_external_selection, "selected")
        self._bind(lambda: (self.query.value, self.is_open.value, self.selected.value),
                   self._render, "filter and selected")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-combobox")
        self._input_slot = Element("div", self, cls="u4-combobox-input")
        self.listbox = Element("div", self, cls="u4-combobox-list", attrs={"role": "listbox", "hidden": True})
        self._buttons: dict[str, Element] = {}
        for value, label in self.options.items():
            entry = Element("button", self, cls="u4-combobox-option",
                            attrs={"role": "option", "type": "button", "aria-selected": "false"},
                            text=str(label))
            self.listbox.add(entry)
            self._buttons[value] = entry
        root.add(self._input_slot, self.listbox)
        return root

    @property
    def slot(self) -> Element:
        return self._input_slot

    @property
    def value(self) -> str | None:
        return self.selected.value

    def _visible(self) -> list[str]:
        text = self.query.peek().casefold().strip()
        return [key for key, label in self.options.items() if text in str(label).casefold()]

    def _render(self, state: tuple[str, bool, str | None]) -> None:
        query, is_open, selected = state
        self.listbox.set_attr("hidden", not is_open)
        self.input.control.set_attr("aria-expanded", "true" if is_open else "false")
        search = query.strip().casefold()
        for key, entry in self._buttons.items():
            entry.set_attr("hidden", search not in str(self.options[key]).casefold())
            entry.set_attr("aria-selected", "true" if key == selected else "false")

    def _sync_external_selection(self, selected: str | None) -> None:
        if selected is not None and selected not in self.options:
            raise InvalidComponentProps(f"bound combobox selection {selected!r} is not in options")
        self.query.set(str(self.options[selected]) if selected is not None else "")

    def _on_input(self, _value: str) -> None:
        self._active_index = 0
        self.is_open.set(True)

    def show(self) -> None:
        self.is_open.set(True)

    def hide(self) -> None:
        self.is_open.set(False)

    def choose(self, value: str) -> None:
        if value not in self.options:
            raise InvalidComponentProps(f"unknown combobox value {value!r}")
        old = self.selected.peek()
        self.selected.set(value)
        self.query.set(str(self.options[value]))
        self.hide()
        if old != value:
            self._emit(self._on_change, value)

    def _key(self, event: dict) -> None:
        key = event.get("key")
        if key == "Escape":
            self.hide()
        elif key in ("ArrowDown", "ArrowUp"):
            values = self._visible()
            if values:
                delta = 1 if key == "ArrowDown" else -1
                self._active_index = (self._active_index + delta) % len(values)
                self.show()
        elif key == "Enter":
            values = self._visible()
            if self.is_open.peek() and values:
                self.choose(values[min(self._active_index, len(values) - 1)])

