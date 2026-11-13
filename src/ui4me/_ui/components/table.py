"""Data table: keyed rows, local search, sort, pagination, selection, empty/loading/error.

Rows keep their DOM identity by key: a changed row patches only its changed cells; a reorder
moves existing ``<tr>`` nodes. Only the visible page is in the DOM.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Callable, Hashable, Sequence

from ..component import Component, Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps
from ..reactive import Computed, Signal, read, untracked
from .regions import KeyedChildren, key_function


@dataclasses.dataclass
class ColumnSpec:
    key: str
    label: str
    format: Callable[[Any], str] | None = None
    align: str | None = None
    sortable: bool = True
    width: str | None = None
    render: Callable[[Any], Any] | None = None
    searchable: bool = True

    def text(self, row: Any) -> str:
        value = cell_value(row, self.key)
        if self.format is not None:
            return self.format(value)
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, enum.Enum):
            return str(value.value) if isinstance(value.value, str) else value.name.replace("_", " ").title()
        return str(value)


def cell_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def infer_columns(rows: Sequence[Any]) -> list[str]:
    if not rows:
        return []
    first = rows[0]
    if dataclasses.is_dataclass(first):
        return [f.name for f in dataclasses.fields(first) if not f.name.startswith("_")]
    if isinstance(first, dict):
        return [k for k in first if not str(k).startswith("_")]
    return [k for k in vars(first) if not k.startswith("_")]


def normalize_columns(columns: Any, rows: Sequence[Any]) -> list[ColumnSpec]:
    if columns is None:
        columns = infer_columns(rows)
    specs: list[ColumnSpec] = []
    for column in columns:
        if isinstance(column, ColumnSpec):
            specs.append(column)
        elif isinstance(column, str):
            specs.append(ColumnSpec(column, column.replace("_", " ").capitalize()))
        elif isinstance(column, (tuple, list)) and len(column) == 2:
            specs.append(ColumnSpec(str(column[0]), str(column[1])))
        elif isinstance(column, dict):
            known = {f.name for f in dataclasses.fields(ColumnSpec)}
            data = {k: v for k, v in column.items() if k in known}
            data.setdefault("label", str(column["key"]).replace("_", " ").capitalize())
            specs.append(ColumnSpec(**data))
        else:
            raise InvalidComponentProps(f"invalid table column {column!r}")
    return specs


def _sort_key(value: Any) -> tuple:
    if value is None:
        return (2, "")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value)
    return (1, str(value).casefold())


class TableRow(Component):
    kind = "TableRow"

    def __init__(self, table: "Table", row: Any, key: Hashable):
        self._table, self.row, self.key = table, row, key
        super().__init__(place=False)
        self._listen(self.root.id, "click", self._clicked)
        self._listen(self.root.id, "keydown", self._key)

    def _build(self) -> Element:
        table = self._table
        attrs: dict[str, Any] = {}
        if table._selectable:
            attrs.update({"tabindex": "-1", "aria-selected": "false"})
        tr = Element("tr", self, cls="u4-selectable" if table._selectable else None, attrs=attrs)
        self.cells: list[Element] = []
        self._cell_scopes: dict[int, Component] = {}
        for index, column in enumerate(table.columns):
            td = Element("td", self, cls="u4-num" if column.align == "right" else None)
            if column.render is None:
                td.text = column.text(self.row)
            tr.add(td)
            self.cells.append(td)
        return tr

    def _render_cells(self) -> None:
        from .regions import Scope
        for index, column in enumerate(self._table.columns):
            if column.render is None:
                continue
            old = self._cell_scopes.pop(index, None)
            if old is not None:
                old.dispose()
            td = self.cells[index]
            frame = push(Frame(self.app, self, td, self.window, live=self.mounted,
                               position=(td.id, "beforeend") if self.mounted else None))
            try:
                scope = Scope()
                inner = push(Frame(self.app, scope, scope.slot, self.window))
                try:
                    untracked(lambda c=column: c.render(self.row))
                finally:
                    pop(inner)
            finally:
                pop(frame)
            if frame.live:
                self.app._insert_created(frame)
            self._cell_scopes[index] = scope

    def update(self, row: Any) -> bool:
        self.row = row
        for index, column in enumerate(self._table.columns):
            if column.render is None:
                self.cells[index].set_text(column.text(row))
        if self._cell_scopes:
            self._render_cells()
        return True

    def _clicked(self, _event: dict) -> None:
        self._table._choose(self.key, activate=True)

    def _key(self, event: dict) -> None:
        self._table._row_key(self.key, event)

    def set_selected(self, on: bool) -> None:
        self.root.toggle_class("u4-selected", on)
        if self._table._selectable:
            self.root.set_attr("aria-selected", "true" if on else "false")
            self.root.set_attr("tabindex", "0" if on else "-1")


class Table(Container):
    """``ui.table(rows, columns=..., key='id', search=True, sort=True, page_size=50, on_select=...)``."""

    kind = "Table"

    def __init__(self, rows: Any, *, columns: Any = None, key: Any = None, search: bool = False, sort: bool = False,
                 page_size: int | None = 50, on_select: Callable | None = None, selected: Signal | None = None,
                 empty: str = "No rows", loading: Any = False, error: Any = None, **kw: Any):
        if key is None:
            raise InvalidComponentProps("ui.table needs key= (a field name or function) for stable row identity")
        self._rows_src = rows
        initial = list(untracked(lambda: read(rows)) or ())
        self.columns = normalize_columns(columns, initial)
        self._key = key_function(key)
        self._search_enabled, self._sort_enabled = search, sort
        self._page_size = page_size if page_size and page_size > 0 else None
        self._on_select = adapt(on_select, None)
        self._selectable = on_select is not None or selected is not None
        self._empty_text = empty
        self.query = Signal("", name="table search")
        self.sort_state: Signal[tuple[str, bool] | None] = Signal(None, name="table sort")
        self.page = Signal(0, name="table page")
        self.selected = selected if selected is not None else Signal(None, name="table selected")
        self.loading = loading if isinstance(loading, Signal) else Signal(bool(loading), name="table loading")
        self.error = error if isinstance(error, Signal) else Signal(error, name="table error")
        super().__init__(**kw)
        self.filtered = Computed(self._filter, name="table filtered")
        self.page_rows = Computed(self._page_rows, name="table page rows")
        self._list = KeyedChildren(self, self._tbody, self._key, self._make_row, lambda c, r: c.update(r))
        if search:
            self._build_search()
        self._bind(lambda: self.page_rows.value, self._show_rows, "rows")
        self._bind(lambda: self._status(), self._show_status, "status")
        self._bind(lambda: self.selected.value, self._show_selected, "selection")
        if sort:
            self._bind(lambda: self.sort_state.value, self._show_sort, "sort")
        if self._page_size:
            self._bind(lambda: self._pager_text(), self._show_pager, "pager")
        for column_key, button in self._sort_buttons.items():
            self._listen(button.id, "click", lambda _e, k=column_key: self.toggle_sort(k))
        self._listen(self._prev.id, "click", lambda _e: self.page.set(max(0, self.page.peek() - 1)))
        self._listen(self._next.id, "click", lambda _e: self.page.set(min(self.page_count - 1, self.page.peek() + 1)))

    # -- structure ------------------------------------------------------------------------------
    def _build(self) -> Element:
        root = Element("div", self, cls="u4-table-box")
        self._tools = Element("div", self, cls="u4-table-tools")
        wrap = Element("div", self, cls="u4-table-wrap")
        table = Element("table", self, cls="u4-table")
        thead = Element("thead", self)
        head_row = Element("tr", self)
        self._headers: list[Element] = []
        self._sort_buttons: dict[str, Element] = {}
        for column in self.columns:
            th = Element("th", self, cls="u4-num" if column.align == "right" else None, attrs={"scope": "col"})
            if column.width:
                th.set_style("width", column.width)
            if self._sort_enabled and column.sortable:
                button = Element("button", self, cls="u4-th", attrs={"type": "button"}, text=column.label)
                th.add(button)
                self._sort_buttons[column.key] = button
            else:
                th.add(Element("span", self, cls="u4-th", text=column.label))
            head_row.add(th)
            self._headers.append(th)
        thead.add(head_row)
        self._tbody = Element("tbody", self)
        self._status_body = Element("tbody", self)
        self._status_row = Element("tr", self, cls="u4-table-empty", attrs={"hidden": True})
        self._status_cell = Element("td", self, attrs={"colspan": str(max(1, len(self.columns)))})
        self._status_row.add(self._status_cell)
        self._status_body.add(self._status_row)
        table.add(thead, self._tbody, self._status_body)
        wrap.add(table)
        self._pager = Element("div", self, cls="u4-pager", attrs={"hidden": not self._page_size})
        self._pager_label = Element("span", self)
        self._prev = Element("button", self, cls="u4-btn u4-btn-ghost u4-btn-sm", attrs={"type": "button",
                                                                                         "aria-label": "Previous page"},
                             text="‹ Prev")
        self._next = Element("button", self, cls="u4-btn u4-btn-ghost u4-btn-sm", attrs={"type": "button",
                                                                                         "aria-label": "Next page"},
                             text="Next ›")
        self._pager.add(self._pager_label, self._prev, self._next)
        root.add(self._tools, wrap, self._pager)
        return root

    def _build_search(self) -> None:
        from .basic import TextField
        frame = push(Frame(self.app, self, self._tools, self.window))
        try:
            self.search_input = TextField(None, bind=self.query, placeholder="Search…",
                                          on_change=lambda _v: self.page.set(0))
            self.search_input.label_el.set_attr("hidden", True)
            self.search_input.control.set_attr("aria-label", "Search")
        finally:
            pop(frame)

    # -- data pipeline ----------------------------------------------------------------------------
    def _all_rows(self) -> list[Any]:
        return list(read(self._rows_src) or ())

    def _filter(self) -> list[Any]:
        rows = self._all_rows()
        query = self.query.value.strip().casefold()
        if query:
            searchable = [c for c in self.columns if c.searchable]
            rows = [r for r in rows if any(query in c.text(r).casefold() for c in searchable)]
        sort = self.sort_state.value
        if sort is not None:
            key, descending = sort
            rows = sorted(rows, key=lambda r: _sort_key(cell_value(r, key)), reverse=descending)
        return rows

    def _page_rows(self) -> list[Any]:
        rows = self.filtered.value
        if not self._page_size:
            return rows
        count = max(1, -(-len(rows) // self._page_size))
        page = min(self.page.value, count - 1)
        return rows[page * self._page_size:(page + 1) * self._page_size]

    @property
    def page_count(self) -> int:
        if not self._page_size:
            return 1
        return max(1, -(-len(self.filtered.peek()) // self._page_size))

    def _pager_text(self) -> tuple[int, int, int, int]:
        total = len(self.filtered.value)
        if not self._page_size:
            return (1, total, total, 1)
        count = max(1, -(-total // self._page_size))
        page = min(self.page.value, count - 1)
        start = page * self._page_size
        return (start + 1 if total else 0, min(total, start + self._page_size), total, count)

    def _show_pager(self, info: tuple[int, int, int, int]) -> None:
        first, last, total, count = info
        self._pager_label.set_text(f"{first}–{last} of {total}")
        page = min(self.page.peek(), count - 1)
        self._prev.set_attr("disabled", page <= 0)
        self._next.set_attr("disabled", page >= count - 1)

    def _status(self) -> tuple[str, str | None]:
        if self.error.value:
            return ("error", str(self.error.value))
        if self.loading.value:
            return ("loading", "Loading…")
        if not self.filtered.value:
            query = self.query.value.strip()
            return ("empty", f"No matches for “{query}”" if query else self._empty_text)
        return ("ok", None)

    def _show_status(self, status: tuple[str, str | None]) -> None:
        kind, text = status
        self._status_row.set_attr("hidden", kind == "ok")
        self._status_cell.set_text(text or "")
        self._status_row.toggle_class("u4-tone-danger", kind == "error")

    def _make_row(self, row: Any, _index: int) -> TableRow:
        frame = push(Frame(self.app, self, None, self.window))
        try:
            component = TableRow(self, row, self._key(row))
        finally:
            pop(frame)
        if any(c.render for c in self.columns):
            component._render_cells()
        return component

    def _show_rows(self, rows: list[Any]) -> None:
        self._list.reconcile(rows)
        self._show_selected(self.selected.peek())

    def _show_selected(self, key: Hashable) -> None:
        for k, (_row, component) in self._list.items.items():
            component.set_selected(k == key)

    def _show_sort(self, sort: tuple[str, bool] | None) -> None:
        for key, button in self._sort_buttons.items():
            th = button
            state = None if sort is None or sort[0] != key else ("descending" if sort[1] else "ascending")
            label = next(c.label for c in self.columns if c.key == key)
            arrow = "" if state is None else (" ↓" if state == "descending" else " ↑")
            button.set_text(label + arrow)
            for header in self._headers:
                if button in header.children:
                    header.set_attr("aria-sort", state or "none")

    # -- interaction ----------------------------------------------------------------------------------
    def toggle_sort(self, key: str) -> None:
        """Cycle ascending -> descending -> unsorted for a column."""
        current = self.sort_state.peek()
        if current is None or current[0] != key:
            self.sort_state.set((key, False))
        elif not current[1]:
            self.sort_state.set((key, True))
        else:
            self.sort_state.set(None)
        self.page.set(0)

    def _choose(self, key: Hashable, *, activate: bool) -> None:
        if not self._selectable:
            return
        self.selected.set(key)
        component = self._list.component(key)
        if component is not None and self.window is not None:
            self.window._queue({"op": "focus", "element": component.root.id})
        if self._on_select is not None:
            row = self._list.items.get(key, (None,))[0]
            self._emit(self._on_select, row)

    def _row_key(self, key: Hashable, event: dict) -> None:
        name = event.get("key")
        order = self._list.order
        if name in ("ArrowDown", "ArrowUp") and key in order:
            index = order.index(key) + (1 if name == "ArrowDown" else -1)
            if 0 <= index < len(order):
                self._choose(order[index], activate=False)
        elif name in ("Enter", " "):
            self._choose(key, activate=True)

    @property
    def selected_row(self) -> Any:
        key = self.selected.value
        for row in self._all_rows():
            if self._key(row) == key:
                return row
        return None

    def row_component(self, key: Hashable) -> TableRow | None:
        return self._list.component(key)  # type: ignore[return-value]
