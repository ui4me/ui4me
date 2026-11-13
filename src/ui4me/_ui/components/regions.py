"""Dynamic regions: ``ui.when`` (conditional subtree) and ``ui.each`` (keyed list).

Each region is a ``display: contents`` element, so it does not disturb flex/grid layout.
``each`` reuses the DOM of items whose key survives, moves them with Core ``move_element``
(which keeps control values, selection and focus), inserts only new keys and removes only
vanished ones. Items whose value changed (by ``==``) are re-rendered in place; unchanged
items are untouched.
"""
from __future__ import annotations

from typing import Any, Callable, Hashable, Iterable, Sequence

from ..component import Component, Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import DuplicateKeyError, InvalidComponentProps
from ..reactive import Signal, _default_equals, read, untracked


class Scope(Container):
    """An invisible container that owns one dynamic item's components."""

    kind = "Item"

    def _build(self) -> Element:
        return Element("div", self, cls="u4-item")


def _render_into(container: Container, builder: Callable[[], Any]) -> None:
    frame = push(Frame(container.app, container, container.slot, container.window))
    try:
        untracked(builder)
    finally:
        pop(frame)


class When(Container):
    """Mount ``then`` while the condition is true, ``otherwise`` while false (state resets)."""

    kind = "When"

    def __init__(self, condition: Any, *, then: Callable[[], Any], otherwise: Callable[[], Any] | None = None,
                 **kw: Any):
        self._then, self._otherwise = then, otherwise
        self._current: bool | None = None
        self._scope: Scope | None = None
        super().__init__(**kw)
        self._bind(lambda: bool(read(condition)), self._switch, "condition")

    def _build(self) -> Element:
        return Element("div", self, cls="u4-region")

    def _switch(self, value: bool) -> None:
        if value == self._current:
            return
        self._current = value
        if self._scope is not None:
            self._scope.dispose()
            self._scope = None
        builder = self._then if value else self._otherwise
        if builder is None:
            return
        frame = push(Frame(self.app, self, self.root, self.window))
        try:
            scope = Scope()
        finally:
            pop(frame)
        _render_into(scope, builder)
        self._scope = scope
        if self.mounted:
            self.root._op("insert_html", position="beforeend", html=scope._html())
            scope._mount(self.window)


def lis_keep(order: Sequence[int]) -> set[int]:
    """Indices (into ``order``) forming a longest increasing subsequence: items that need not move."""
    tails: list[int] = []
    tails_idx: list[int] = []
    previous = [-1] * len(order)
    import bisect
    for i, value in enumerate(order):
        pos = bisect.bisect_left(tails, value)
        if pos == len(tails):
            tails.append(value)
            tails_idx.append(i)
        else:
            tails[pos] = value
            tails_idx[pos] = i
        previous[i] = tails_idx[pos - 1] if pos > 0 else -1
    keep: set[int] = set()
    k = tails_idx[-1] if tails_idx else -1
    while k != -1:
        keep.add(k)
        k = previous[k]
    return keep


def key_function(key: Any) -> Callable[[Any], Hashable]:
    if callable(key):
        return key
    if isinstance(key, str):
        def get(item: Any, _name: str = key) -> Hashable:
            if isinstance(item, dict):
                return item[_name]
            return getattr(item, _name)
        return get
    raise InvalidComponentProps("key must be a function or an attribute/field name")


class KeyedChildren:
    """Keyed reconciliation of child components inside one parent element.

    ``create(item, index)`` builds a component (created with ``place=False``); ``update(component,
    item)`` may patch it in place and return True, otherwise a changed item is re-created.
    Surviving keys are moved with Core ``move_element`` (focus/values preserved); a longest
    increasing subsequence stays put so a typical reorder moves few nodes.
    """

    def __init__(self, owner: Container, parent: Element, key: Callable[[Any], Hashable],
                 create: Callable[[Any, int], Component],
                 update: Callable[[Component, Any], bool] | None = None):
        self.owner, self.parent, self.key = owner, parent, key
        self.create, self.update = create, update
        self.items: dict[Hashable, tuple[Any, Component]] = {}
        self.order: list[Hashable] = []

    def _new(self, item: Any, index: int) -> Component:
        component = self.create(item, index)
        component.parent = self.owner
        component._slot_parent = self.parent
        self.owner._children.append(component)
        return component

    def reconcile(self, items: Sequence[Any]) -> None:
        keyed: list[tuple[Hashable, Any]] = []
        seen: set = set()
        for item in items:
            k = self.key(item)
            if k is None:
                raise InvalidComponentProps("key function returned None")
            if k in seen:
                raise DuplicateKeyError(f"duplicate key {k!r} in a keyed list")
            seen.add(k)
            keyed.append((k, item))
        owner = self.owner
        mounted = owner.mounted
        for k in [k for k in self.order if k not in seen]:
            self.items.pop(k)[1].dispose()
        self.order = [k for k in self.order if k in seen]
        for index, (k, item) in enumerate(keyed):
            entry = self.items.get(k)
            if entry is None:
                continue
            old_item, component = entry
            if _default_equals(old_item, item):
                self.items[k] = (item, component)
                continue
            if self.update is not None and self.update(component, item):
                self.items[k] = (item, component)
                continue
            fresh = self._new(item, index)
            if mounted:
                component.root._op("insert_html", position="afterend", html=fresh._html())
            component.dispose()
            if mounted:
                fresh._mount(owner.window)
            self.items[k] = (item, fresh)
        old_pos = {k: i for i, k in enumerate(self.order)}
        surviving = [k for k, _ in keyed if k in old_pos]
        keep = {surviving[i] for i in lis_keep([old_pos[k] for k in surviving])}
        previous: Component | None = None
        children: list[Any] = []
        for index, (k, item) in enumerate(keyed):
            entry = self.items.get(k)
            if entry is None:
                component = self._new(item, index)
                self.items[k] = (item, component)
                if mounted:
                    html = component._html()
                    if previous is None:
                        self.parent._op("insert_html", position="afterbegin", html=html)
                    else:
                        previous.root._op("insert_html", position="afterend", html=html)
                    component._mount(owner.window)
            else:
                component = entry[1]
                if mounted and k not in keep:
                    if previous is None:
                        component.root._op("move_element", target=self.parent.id, position="afterbegin")
                    else:
                        component.root._op("move_element", target=previous.root.id, position="afterend")
            children.append(component)
            previous = component
        self.order = [k for k, _ in keyed]
        extra = [c for c in self.parent.children if c not in children and not isinstance(c, Component)]
        self.parent.children = children + extra
        if mounted:
            owner.app._request_commit()

    def component(self, key: Hashable) -> Component | None:
        entry = self.items.get(key)
        return entry[1] if entry else None


class ItemRef:
    """Stable reactive view of a keyed record for ui.each(..., preserve=True).

    `lambda: item.title` reads the current record even after replacement/reorder.
    For primitive records use `item.value`; `item.index.value` tracks the position.
    Do not rely on `isinstance(item, YourType)`: it is intentionally a proxy.
    """

    def __init__(self, item: Any, index: int):
        self._item = Signal(item, name="keyed record")
        self.index = Signal(index, name="keyed index")

    @property
    def value(self) -> Any:
        return self._item.value

    def update(self, item: Any, index: int) -> None:
        self._item.set(item)
        self.index.set(index)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._item.value, name)

    def __getitem__(self, key: Any) -> Any:
        return self._item.value[key]

    def __str__(self) -> str:
        return str(self._item.value)


class Each(Container):
    """Keyed list region."""

    kind = "Each"

    def __init__(self, items: Any, *, key: Any, render: Callable[..., Any], empty: Callable[[], Any] | None = None,
                 tag: str = "div", cls: str = "u4-region", preserve: bool = False, **kw: Any):
        if key is None:
            raise InvalidComponentProps("ui.each needs key= (a function or field name); index keys break on reorder")
        self._render = adapt(render, None, None)
        self._preserve = preserve
        self._empty = empty
        self._tag, self._cls = tag, cls
        self._empty_scope: Scope | None = None
        super().__init__(**kw)
        self._key_fn = key_function(key)
        self._list = KeyedChildren(self, self.root, self._key_fn, self._make,
                                   self._update_item if preserve else None)
        self._bind(lambda: list(read(items) or ()), self._reconcile, "items")

    def _build(self) -> Element:
        return Element(self._tag, self, cls=self._cls)

    def keys(self) -> list[Hashable]:
        return list(self._list.order)

    def scope(self, key: Hashable) -> Component | None:
        return self._list.component(key)

    def _make(self, item: Any, index: int) -> Scope:
        frame = push(Frame(self.app, self, None, self.window))
        try:
            scope = Scope(place=False)
        finally:
            pop(frame)
        if self._preserve:
            scope.item_ref = ItemRef(item, index)
            _render_into(scope, lambda: self._render(scope.item_ref, index))
        else:
            _render_into(scope, lambda: self._render(item, index))
        return scope

    def _update_item(self, scope: Scope, item: Any) -> bool:
        scope.item_ref.update(item, scope.item_ref.index.peek())
        return True

    def _reconcile(self, items: list[Any]) -> None:
        self._list.reconcile(items)
        if self._preserve:
            for index, item in enumerate(items):
                scope = self._list.component(self._key_fn(item))
                if scope is not None:
                    scope.item_ref.update(item, index)
        empty_needed = not items and self._empty is not None
        if self._empty_scope is not None and not empty_needed:
            self._empty_scope.dispose()
            self._empty_scope = None
        if empty_needed and self._empty_scope is None:
            frame = push(Frame(self.app, self, self.root, self.window))
            try:
                scope = Scope()
            finally:
                pop(frame)
            _render_into(scope, self._empty)
            self._empty_scope = scope
            if self.mounted:
                self.root._op("insert_html", position="beforeend", html=scope._html())
                scope._mount(self.window)
                self.app._request_commit()
