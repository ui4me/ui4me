"""Paged data-source table for local databases, files, or remote APIs.

The loader is user-provided and runs on a UI4ME background worker thread. It must
return PageResult(rows, total) or (rows, total). It must never touch UI objects.
Only the newest request is allowed to update UI state, even when a worker ignores
cooperative cancellation. No HTTP, ORM or database dependency is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ..component import Container, Frame, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps
from ..reactive import Signal
from .basic import Button, Text, TextField
from .table import Table


@dataclass(frozen=True)
class PageResult:
    rows: Sequence[Any]
    total: int


class QueryTable(Container):
    """Background paging + live search + stale-result rejection over the standard Table."""

    kind = "QueryTable"

    def __init__(self, loader: Callable[[int, int, str], PageResult | tuple[Sequence[Any], int]], *,
                 key: Any, columns: Any, page_size: int = 50, search: bool = True,
                 on_select: Callable | None = None, **kw: Any):
        if not callable(loader):
            raise InvalidComponentProps("loader must be callable")
        if page_size < 1 or page_size > 10000:
            raise InvalidComponentProps("page_size must be 1..10000")
        self.loader, self.page_size = loader, page_size
        self.rows: Signal[list[Any]] = Signal([], name="query table rows")
        self.page = Signal(0, name="query table page")
        self.query = Signal("", name="query table search")
        self.total = Signal(0, name="query table total")
        self.loading = Signal(False, name="query table loading")
        self.error = Signal(None, name="query table error")
        self._generation = 0
        self._task = None
        self._search_enabled = search
        self._debounce = None
        super().__init__(**kw)
        self.on_dispose(lambda: self._task.cancel() if self._task is not None else None)
        self.on_dispose(lambda: self._debounce.cancel() if self._debounce is not None else None)
        frame = push(Frame(self.app, self, self.slot, self.window))
        try:
            if search:
                self.input = TextField("Search", bind=self.query, placeholder="Search records",
                                       on_change=lambda _: self._change_query())
            self.table = Table(self.rows, key=key, columns=columns, loading=self.loading,
                               error=self.error, search=False, sort=False, page_size=None,
                               on_select=on_select)
            self._footer = ContainerControls(self)
        finally:
            pop(frame)

    def _build(self) -> Element:
        return Element("section", self, cls="u4-query-table u4-column u4-gap-sm")

    def _on_mount(self) -> None:
        self.refresh()

    def _change_query(self) -> None:
        self.page.set(0)
        if self._debounce is not None:
            self._debounce.cancel()
        self._debounce = self.app.after(0.25, self.refresh)

    def goto(self, number: int) -> None:
        if number < 0:
            raise InvalidComponentProps("page number cannot be negative")
        total = self.total.peek()
        if total > 0 and number > (total - 1) // self.page_size:
            return
        if self.page.peek() != number:
            self.page.set(number)
            self.refresh()

    def refresh(self) -> None:
        """Re-query on worker. Safe for manual reload or retries; previous result is discarded."""
        self._live_check()
        if not self.mounted or self.disposed:
            return
        self._generation += 1
        generation = self._generation
        if self._task is not None and not self._task.done:
            self._task.cancel()
        self.loading.set(True)
        self.error.set(None)
        page, size, query = self.page.peek(), self.page_size, self.query.peek()

        def work():
            return self.loader(page, size, query)

        def done(value):
            if self.disposed or generation != self._generation:
                return
            try:
                if isinstance(value, PageResult):
                    rows, total = value.rows, value.total
                elif isinstance(value, tuple) and len(value) == 2:
                    rows, total = value
                else:
                    raise InvalidComponentProps("loader must return PageResult or (rows, total)")
                if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                    raise InvalidComponentProps("loader total must be nonnegative integer")
                page_rows = list(rows)
            except Exception as exc:
                failed(exc)
                return
            self.rows.set(page_rows)
            self.total.set(total)
            self.loading.set(False)

        def failed(error):
            if not self.disposed and generation == self._generation:
                self.loading.set(False)
                self.error.set(str(error))

        self._task = self.app.tasks.submit(work, on_done=done, on_error=failed, label="query table load")


class ContainerControls(Container):
    kind = "QueryTableControls"

    def __init__(self, owner: QueryTable):
        self.controller = owner
        super().__init__()
        frame = push(Frame(self.app, self, self.slot, self.window))
        try:
            Button("Previous", variant="secondary", on_click=lambda: owner.goto(owner.page.peek() - 1),
                   disabled=lambda: owner.page.value == 0 or owner.loading.value)
            Text(lambda: f"Page {owner.page.value + 1} / {max(1, (owner.total.value + owner.page_size - 1) // owner.page_size)} · {owner.total.value} records", tone="muted")
            Button("Next", variant="secondary", on_click=lambda: owner.goto(owner.page.peek() + 1),
                   disabled=lambda: owner.loading.value or (owner.page.value + 1) * owner.page_size >= owner.total.value)
            Button("Refresh", variant="ghost", on_click=owner.refresh)
        finally:
            pop(frame)

    def _build(self) -> Element:
        return Element("div", self, cls="u4-row u4-wrap u4-gap-sm u4-query-controls")
