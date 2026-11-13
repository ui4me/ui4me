"""Managed DOM descriptors.

An :class:`Element` describes one HTML element owned by a component. Before mounting it
only records state (used to render the initial HTML). Once mounted in a window every
change becomes one targeted Core operation (``set_text``, ``set_attribute``, ...) queued
on that window and committed in one atomic Core ``batch`` at the end of the flush.
"""
from __future__ import annotations

import itertools
import re
from html import escape as _escape
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:  # pragma: no cover
    from .component import Component
    from .window import UiWindow

_ids = itertools.count(1)

VOID_TAGS = frozenset({"area", "br", "col", "hr", "img", "input", "link", "meta", "source", "wbr"})
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_:.-]*$")
_CSS_PROP = re.compile(r"^(--[A-Za-z0-9_-]+|-?[a-z][a-z0-9-]*)$")
_CSS_BAD = re.compile(r"[;{}<>]|/\*|\*/|url\s*\(|expression\s*\(|@import", re.I)
MAX_TEXT = 16 * 1024


def new_id(prefix: str = "u4") -> str:
    return f"{prefix}-{next(_ids)}"


def escape_text(text: Any) -> str:
    return _escape("" if text is None else str(text), quote=False)


def escape_attr(value: Any) -> str:
    return _escape("" if value is None else str(value), quote=True)


def check_name(name: str, what: str = "attribute") -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        from .errors import InvalidComponentProps
        raise InvalidComponentProps(f"invalid {what} name {name!r}")
    if what == "attribute" and name.lower().startswith("on"):
        from .errors import InvalidMarkupError
        raise InvalidMarkupError(f"event handler attributes such as {name!r} are not allowed; use .on()")
    return name


def check_css(prop: str, value: Any) -> str:
    """Validate one CSS declaration; values cannot break out of the declaration."""
    from .errors import InvalidComponentProps
    if not isinstance(prop, str) or not _CSS_PROP.match(prop):
        raise InvalidComponentProps(f"invalid CSS property {prop!r}")
    text = str(value)
    if _CSS_BAD.search(text) or "\n" in text:
        raise InvalidComponentProps(f"unsafe CSS value for {prop}: {text!r}")
    return text


def style_text(style: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in style.items())


class Element:
    """One managed HTML element."""

    __slots__ = ("tag", "id", "attrs", "classes", "style", "children", "text", "owner", "window")

    def __init__(self, tag: str, owner: "Component | None" = None, *, cls: str | Iterable[str] | None = None,
                 attrs: dict[str, Any] | None = None, text: str | None = None, id: str | None = None):
        self.tag = tag
        self.id = id or new_id()
        self.attrs: dict[str, Any] = {}
        self.classes: list[str] = []
        self.style: dict[str, str] = {}
        self.children: list[Any] = []  # Element | Component | str (literal text)
        self.text: str | None = text
        self.owner = owner
        self.window: "UiWindow | None" = None
        if cls:
            for name in (cls.split() if isinstance(cls, str) else cls):
                if name and name not in self.classes:
                    self.classes.append(name)
        if attrs:
            for name, value in attrs.items():
                if value is not None and value is not False:
                    self.attrs[check_name(name)] = value
        if owner is not None:
            owner._elements.append(self)

    def __repr__(self) -> str:
        return f"<Element {self.tag}#{self.id}>"

    # -- structure (before mount, or followed by explicit insertion) ----------------------
    def add(self, *children: Any) -> "Element":
        for child in children:
            if child is None:
                continue
            self.children.append(child)
        return self

    # -- rendering -------------------------------------------------------------------------
    def open_tag(self) -> str:
        parts = [self.tag, f'id="{self.id}"']
        if self.classes:
            parts.append(f'class="{escape_attr(" ".join(self.classes))}"')
        if self.style:
            parts.append(f'style="{escape_attr(style_text(self.style))}"')
        for name, value in self.attrs.items():
            if value is True:
                parts.append(name)
            else:
                parts.append(f'{name}="{escape_attr(value)}"')
        return "<" + " ".join(parts) + ">"

    def html(self) -> str:
        if self.tag in VOID_TAGS:
            return self.open_tag()
        out = [self.open_tag()]
        if self.text is not None:
            out.append(escape_text(self.text))
        for child in self.children:
            out.append(render(child))
        out.append(f"</{self.tag}>")
        return "".join(out)

    # -- patching ---------------------------------------------------------------------------
    def _op(self, op: str, **fields: Any) -> None:
        if self.window is not None:
            self.window._queue({"op": op, "element": self.id, **fields})

    def set_html(self, html: str) -> None:
        """Replace the content with trusted/sanitized markup."""
        self.text = None
        self.children = [RawHtml(html)]
        self._op("replace_children_html", html=html)

    def set_text(self, text: Any) -> None:
        text = "" if text is None else str(text)
        if self.text == text and not self.children:
            return
        self.text = text
        self.children = []
        if self.window is not None:
            if len(text.encode("utf-8")) > MAX_TEXT:
                self._op("replace_children_html", html=escape_text(text))
            else:
                self._op("set_text", text=text)

    def set_attr(self, name: str, value: Any) -> None:
        check_name(name)
        if value is None or value is False:
            self.remove_attr(name)
            return
        if self.attrs.get(name, None) == value and name in self.attrs:
            return
        self.attrs[name] = value
        self._op("set_attribute", name=name, value="" if value is True else str(value))

    def remove_attr(self, name: str) -> None:
        if name not in self.attrs:
            return
        del self.attrs[name]
        self._op("remove_attribute", name=name)

    def add_class(self, *names: str) -> None:
        for name in names:
            for part in str(name).split():
                if part not in self.classes:
                    check_name(part, "class")
                    self.classes.append(part)
                    self._op("add_class", name=part)

    def remove_class(self, *names: str) -> None:
        for name in names:
            for part in str(name).split():
                if part in self.classes:
                    self.classes.remove(part)
                    self._op("remove_class", name=part)

    def toggle_class(self, name: str, on: bool) -> None:
        (self.add_class if on else self.remove_class)(name)

    def set_style(self, prop: str, value: Any) -> None:
        if value is None:
            if prop in self.style:
                del self.style[prop]
                self._sync_style()
            return
        value = check_css(prop, value)
        if self.style.get(prop) == value:
            return
        self.style[prop] = value
        self._sync_style()

    def _sync_style(self) -> None:
        if self.style:
            self._op("set_attribute", name="style", value=style_text(self.style))
        else:
            self._op("remove_attribute", name="style")

    def walk(self):
        """Yield this element and owned descendant elements (not child components)."""
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()


class RawHtml:
    """Pre-sanitized/trusted markup child (output of the Markdown renderer or ``ui.html``)."""

    __slots__ = ("html",)

    def __init__(self, html: str):
        self.html = html


def render(child: Any) -> str:
    if isinstance(child, RawHtml):
        return child.html
    if isinstance(child, str):
        return escape_text(child)
    if isinstance(child, Element):
        return child.html()
    html = getattr(child, "_html", None)
    if html is not None:
        return html()
    raise TypeError(f"cannot render {child!r}")
