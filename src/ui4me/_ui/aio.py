"""Owner-thread awaitables.

UI callbacks may be ``async def``. They are driven on the UI owner thread by UI4ME UI
itself (no asyncio loop): each ``await`` suspends the callback until the awaited
:class:`UiFuture` settles (a native dialog result, a background task, a timer, a confirm
dialog). Awaiting anything else raises a clear ``TypeError``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

if TYPE_CHECKING:  # pragma: no cover
    from .app import UiApp

T = TypeVar("T")
PENDING, DONE, FAILED, CANCELLED = "pending", "done", "failed", "cancelled"


class UiFuture(Generic[T]):
    """A result that arrives later on the UI owner thread. ``await`` it or use ``then``."""

    def __init__(self, app: "UiApp", label: str = "operation"):
        self._app = app
        self.label = label
        self.state = PENDING
        self._result: Any = None
        self._error: BaseException | None = None
        self._callbacks: list[Callable[["UiFuture"], Any]] = []
        self._observed = False  # someone awaits it or registered a callback (handles errors)

    def __repr__(self) -> str:
        return f"<UiFuture {self.label} {self.state}>"

    @property
    def done(self) -> bool:
        return self.state != PENDING

    def result(self) -> T:
        if self.state == PENDING:
            raise RuntimeError(f"{self.label} has not finished; await it or use .then()")
        if self._error is not None:
            raise self._error
        return self._result

    @property
    def error(self) -> BaseException | None:
        return self._error

    def set_result(self, value: T) -> None:
        if self.state != PENDING:
            return
        self.state, self._result = DONE, value
        self._fire()

    def set_exception(self, error: BaseException) -> None:
        if self.state != PENDING:
            return
        self.state, self._error = FAILED, error
        self._fire()

    def cancel(self) -> bool:
        if self.state != PENDING:
            return False
        from concurrent.futures import CancelledError
        self.state, self._error = CANCELLED, CancelledError(self.label)
        self._fire()
        return True

    def add_done_callback(self, fn: Callable[["UiFuture"], Any]) -> None:
        self._observed = True
        if self.state != PENDING:
            fn(self)
        else:
            self._callbacks.append(fn)

    def then(self, on_done: Callable[[T], Any] | None = None,
             on_error: Callable[[BaseException], Any] | None = None) -> "UiFuture[T]":
        """Run ``on_done(result)`` / ``on_error(exc)`` on the owner thread when settled."""
        def settle(future: UiFuture) -> None:
            if future._error is None:
                if on_done is not None:
                    self._app._call(on_done, future._result, context=f"{self.label} result")
            elif on_error is not None:
                self._app._call(on_error, future._error, context=f"{self.label} error")
            elif future.state == FAILED:
                self._app._report(future._error, self.label)
        self.add_done_callback(settle)
        return self

    def _fire(self) -> None:
        callbacks, self._callbacks = self._callbacks, []
        for fn in callbacks:
            try:
                fn(self)
            except Exception as error:  # a callback failure must not break other waiters
                self._app._report(error, f"{self.label} callback")

    def __await__(self):
        if self.state == PENDING:
            yield self
        return self.result()


def drive(app: "UiApp", coroutine: Any, context: str | None, owner: Any = None) -> UiFuture:
    """Run an ``async def`` UI callback to completion on the owner thread."""
    outcome: UiFuture = UiFuture(app, context or "async callback")
    if owner is not None:
        def dispose_coroutine() -> None:
            if not outcome.done:
                outcome.cancel()
                try:
                    coroutine.close()
                except (RuntimeError, ValueError):
                    pass
        owner.on_dispose(dispose_coroutine)

    def step(value: Any = None, error: BaseException | None = None) -> None:
        if outcome.done or app.closed or (owner is not None and owner.disposed):
            return
        try:
            awaited = coroutine.throw(error) if error is not None else coroutine.send(value)
        except StopIteration as stop:
            outcome.set_result(stop.value)
            return
        except Exception as failure:
            outcome.set_exception(failure)
            app._report(failure, context)
            return
        if not isinstance(awaited, UiFuture):
            coroutine.close()
            failure = TypeError(
                "UI callbacks can only await UI4ME UI awaitables (dialogs, app.tasks, ui.sleep, "
                f"ui.confirm); got {awaited!r}. Run asyncio code with app.tasks.submit().")
            outcome.set_exception(failure)
            app._report(failure, context)
            return

        def resume(future: UiFuture) -> None:
            if outcome.done or app.closed or (owner is not None and owner.disposed):
                return
            if future._error is None:
                app._call(step, future._result, context=context, owner=owner, raw=True)
            else:
                app._call(step, None, future._error, context=context, owner=owner, raw=True)
        awaited.add_done_callback(resume)

    step()
    return outcome
