"""Reactive state: Signal, Computed, Reaction and the owner-thread Scheduler.

Model (push-dirty / pull-value):

* ``Signal.set`` changes the value and marks every dependent *stale*.
* A ``Computed`` marks itself stale and forwards the mark; it recomputes lazily when read.
* A ``Reaction`` (component binding or user effect) is queued once on its scheduler.
* ``Scheduler.flush`` runs queued render reactions, commits DOM patches, then runs effects,
  repeating until quiet (bounded, so self-triggering loops end with ``ReactiveCycleError``).

Dependencies are dynamic: each run records what it read and drops edges it no longer uses.
State belongs to the thread that created it; other threads must use ``app.post``.
"""
from __future__ import annotations

import itertools
import threading
from contextlib import contextmanager
from typing import Any, Callable, Generic, Iterator, TypeVar

from .errors import ReactiveCycleError, WrongThreadError

T = TypeVar("T")

_local = threading.local()
_sequence = itertools.count(1)
_UNSET: Any = object()

MAX_FLUSH_PASSES = 100


def _frame() -> set | None:
    return getattr(_local, "frame", None)


def _track(source: "_Source") -> None:
    frame = getattr(_local, "frame", None)
    if frame is not None:
        frame.add(source)


@contextmanager
def _collect() -> Iterator[set]:
    previous = getattr(_local, "frame", None)
    frame: set = set()
    _local.frame = frame
    try:
        yield frame
    finally:
        _local.frame = previous


def untracked(fn: Callable[[], T]) -> T:
    """Run ``fn`` without recording dependencies for the surrounding computation."""
    previous = getattr(_local, "frame", None)
    _local.frame = None
    try:
        return fn()
    finally:
        _local.frame = previous


def _default_equals(old: Any, new: Any) -> bool:
    if old is new:
        return True
    try:
        return bool(old == new)
    except Exception:  # objects with exotic __eq__ (e.g. arrays) are treated as changed
        return False


class _Source:
    """Something that can be depended upon."""

    __slots__ = ()

    def _observers_set(self) -> set:
        raise NotImplementedError


def _relink(observer: Any, old: Any, new: Any) -> None:
    """Move ``observer`` from the sources in ``old`` to those in ``new`` (sets or dict keys)."""
    for source in old:
        if source not in new:
            source._observers.discard(observer)
            if isinstance(source, Computed) and not source._observers:
                source._unlink()
    for source in new:
        if source not in old:
            first = not source._observers
            source._observers.add(observer)
            if first and isinstance(source, Computed):
                source._link()


class Signal(_Source, Generic[T]):
    """Mutable observable state. Read ``.value`` (tracked), write ``.set`` / ``.update``.

    Writes are ignored when the new value equals the current one. Mutating a contained
    list or dict in place is *not* observed: assign a new value, or use :meth:`mutate`.
    """

    __slots__ = ("_value", "_observers", "_owner", "_equals", "name", "_version", "__weakref__")

    def __init__(self, value: T, *, equals: Callable[[Any, Any], bool] | None = None, name: str | None = None):
        self._value = value
        self._observers: set = set()
        self._owner = threading.get_ident()
        self._equals = equals or _default_equals
        self.name = name
        self._version = 0

    def __repr__(self) -> str:
        label = f" {self.name}" if self.name else ""
        return f"<Signal{label} {self._value!r}>"

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise WrongThreadError(
                "State belongs to the UI owner thread; from another thread use "
                "app.post(lambda: state.set(value))")

    @property
    def value(self) -> T:
        _track(self)
        return self._value

    @value.setter
    def value(self, new: T) -> None:
        self.set(new)

    def get(self) -> T:
        _track(self)
        return self._value

    def peek(self) -> T:
        """Read without recording a dependency."""
        return self._value

    def set(self, new: T) -> None:
        self._check_owner()
        if self._equals(self._value, new):
            return
        self._value = new
        self._notify()

    def update(self, fn: Callable[[T], T]) -> None:
        """Replace the value with ``fn(current)``."""
        self.set(fn(self._value))

    def mutate(self, fn: Callable[[T], Any]) -> None:
        """Mutate the contained object in place with ``fn(value)`` and notify dependents."""
        self._check_owner()
        fn(self._value)
        self._notify()

    def notify(self) -> None:
        """Tell dependents the value changed (after an in-place mutation)."""
        self._check_owner()
        self._notify()

    def _notify(self) -> None:
        self._version += 1
        for observer in tuple(self._observers):
            observer._mark()

    def subscribe(self, fn: Callable[[T], Any], scheduler: "Scheduler | None" = None) -> "Reaction":
        """Call ``fn(value)`` after each change (not immediately). Returns a disposable Reaction."""
        scheduler = scheduler or current_scheduler()
        first = [True]

        def run() -> None:
            value = self.value
            if first[0]:
                first[0] = False
                return
            untracked(lambda: fn(value))

        return Reaction(run, scheduler, priority=Reaction.EFFECT, name=f"subscribe({self.name or 'signal'})")


class Computed(_Source, Generic[T]):
    """Read-only derived state, computed lazily and cached until a dependency changes.

    While something observes it, a Computed is linked into the graph and receives change
    marks. When nothing observes it, reads validate the cache against source versions, so
    an unobserved Computed holds no references from its sources (no leak) yet stays cached.
    """

    __slots__ = ("_fn", "_value", "_stale", "_sources", "_observers", "_computing", "_equals", "name",
                 "_version", "_linked", "__weakref__")

    def __init__(self, fn: Callable[[], T], *, equals: Callable[[Any, Any], bool] | None = None,
                 name: str | None = None):
        if not callable(fn):
            raise TypeError("computed() needs a function")
        self._fn = fn
        self._value: Any = _UNSET
        self._stale = True
        self._sources: dict = {}
        self._observers: set = set()
        self._computing = False
        self._equals = equals or _default_equals
        self._version = 0
        self._linked = False
        self.name = name or getattr(fn, "__name__", None)

    def __repr__(self) -> str:
        return f"<Computed {self.name or ''} {'stale' if self._stale else repr(self._value)}>"

    @property
    def value(self) -> T:
        _track(self)
        return self._get()

    def get(self) -> T:
        return self.value

    def peek(self) -> T:
        return untracked(self._get)

    def _get(self) -> T:
        if self._computing:
            raise ReactiveCycleError(f"computed '{self.name or 'value'}' depends on itself")
        if (self._value is _UNSET or (self._linked and self._stale)
                or (not self._linked and self._sources_changed())):
            self._recompute()
        self._stale = False
        return self._value

    def _sources_changed(self) -> bool:
        for source, version in self._sources.items():
            if isinstance(source, Computed):
                source._get()
            if source._version != version:
                return True
        return False

    def _recompute(self) -> None:
        self._computing = True
        previous = getattr(_local, "frame", None)
        frame: set = set()
        _local.frame = frame
        try:
            value = self._fn()
        except BaseException:
            self._stale = True
            raise
        finally:
            _local.frame = previous
            self._computing = False
            sources = {source: source._version for source in frame}
            if self._linked:
                _relink(self, self._sources, sources)
            self._sources = sources
        self._stale = False
        if self._value is _UNSET or not self._equals(self._value, value):
            self._value = value
            self._version += 1

    def _mark(self) -> None:
        if self._stale:
            return
        self._stale = True
        for observer in tuple(self._observers):
            observer._mark()

    def _link(self) -> None:
        if self._linked:
            return
        self._linked = True
        if self._sources_changed():
            self._stale = True
        _relink(self, (), self._sources)

    def _unlink(self) -> None:
        if not self._linked:
            return
        self._linked = False
        _relink(self, self._sources, ())
        self._stale = True


class Reaction:
    """A tracked side effect, re-run by its scheduler whenever a dependency changes.

    ``fn`` may return a cleanup callable; it runs before the next run and on dispose.
    """

    RENDER = 0
    EFFECT = 1

    __slots__ = ("_fn", "_scheduler", "priority", "_sources", "_dirty", "_disposed", "_cleanup", "name",
                 "context", "seq", "__weakref__")

    def __init__(self, fn: Callable[[], Any], scheduler: "Scheduler", *, priority: int = 1,
                 name: str | None = None, context: str | None = None, run: bool = True):
        self._fn = fn
        self._scheduler = scheduler
        self.priority = priority
        self._sources: set = set()
        self._dirty = False
        self._disposed = False
        self._cleanup: Callable[[], Any] | None = None
        self.name = name
        self.context = context
        self.seq = next(_sequence)
        scheduler._reactions += 1
        if run:
            self.run()

    @property
    def disposed(self) -> bool:
        return self._disposed

    def _mark(self) -> None:
        if self._dirty or self._disposed:
            return
        self._dirty = True
        self._scheduler._enqueue(self)

    def run(self) -> None:
        if self._disposed:
            return
        self._dirty = False
        self._run_cleanup()
        with _collect() as frame:
            try:
                result = self._fn()
            except BaseException as error:
                result = None
                if not isinstance(error, Exception):
                    raise
                self._scheduler.report(error, self.context or self.name)
            finally:
                # Relink even after failure so a fix to the inputs re-runs the reaction.
                if not self._disposed:
                    _relink(self, self._sources, frame)
                    self._sources = frame
        if callable(result):
            self._cleanup = result

    def _run_cleanup(self) -> None:
        cleanup, self._cleanup = self._cleanup, None
        if cleanup is not None:
            try:
                cleanup()
            except Exception as error:
                self._scheduler.report(error, self.context or self.name)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._scheduler._reactions -= 1
        _relink(self, self._sources, set())
        self._sources = set()
        self._run_cleanup()

    # Subscription-like aliases
    close = dispose


class Scheduler:
    """Owner-thread queue of dirty reactions.

    ``request`` asks the host to call :meth:`flush` soon (an owner post); inside
    :meth:`batch` the flush runs synchronously when the outermost batch exits.
    ``commit`` is called between render reactions and effects to apply DOM patches.
    """

    def __init__(self, *, request: Callable[[], Any] | None = None, commit: Callable[[], Any] | None = None,
                 on_error: Callable[[BaseException, str | None], Any] | None = None):
        self._request = request
        self._commit = commit
        self._on_error = on_error
        self._pending: list[Reaction] = []
        self._batch_depth = 0
        self._flushing = False
        self._requested = False
        self._reactions = 0
        self.flushes = 0
        self.errors = 0
        self.last_error: BaseException | None = None
        self.closed = False
        self._owner = threading.get_ident()

    # -- queueing -------------------------------------------------------------------------
    def _enqueue(self, reaction: Reaction) -> None:
        self._pending.append(reaction)
        if self._batch_depth == 0 and not self._flushing:
            self._ask()

    def _ask(self) -> None:
        if self._requested or self.closed:
            return
        if self._request is None:
            self.flush()
            return
        self._requested = True
        try:
            self._request()
        except Exception:
            self._requested = False
            raise

    def request(self) -> None:
        """Make sure a flush (and DOM commit) happens soon."""
        if self._batch_depth == 0 and not self._flushing:
            self._ask()

    @property
    def pending(self) -> int:
        return len(self._pending)

    @property
    def reactions(self) -> int:
        return self._reactions

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Coalesce writes; flush once when the outermost batch exits (also on error)."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and not self._flushing:
                self.flush()

    def flush(self) -> None:
        """Run everything that is dirty; bounded."""
        self._requested = False
        if self._flushing or self.closed:
            return
        self._flushing = True
        self.flushes += 1
        try:
            passes = 0
            while True:
                if not self._pending:
                    self._run_commit()
                    if not self._pending:
                        break
                passes += 1
                if passes > MAX_FLUSH_PASSES:
                    names = sorted({r.context or r.name or "reaction" for r in self._pending})[:5]
                    self._pending.clear()
                    self.report(ReactiveCycleError(
                        "state updates kept re-triggering each other; stopped after "
                        f"{MAX_FLUSH_PASSES} passes (involved: {', '.join(names)})"), None)
                    self._run_commit()
                    break
                renders = [r for r in self._pending if r.priority == Reaction.RENDER]
                if renders:
                    self._pending = [r for r in self._pending if r.priority != Reaction.RENDER]
                    for reaction in sorted(renders, key=lambda r: r.seq):
                        if reaction._dirty:
                            reaction.run()
                    continue
                self._run_commit()
                effects, self._pending = self._pending, []
                for reaction in sorted(effects, key=lambda r: r.seq):
                    if reaction._dirty:
                        reaction.run()
        finally:
            self._flushing = False

    def _run_commit(self) -> None:
        if self._commit is not None:
            try:
                self._commit()
            except Exception as error:
                self.report(error, "DOM commit")

    def report(self, error: BaseException, context: str | None) -> None:
        self.errors += 1
        self.last_error = error
        if self._on_error is not None:
            self._on_error(error, context)
        else:
            raise error

    def close(self) -> None:
        self.closed = True
        self._pending.clear()


# -- current scheduler (set by the active app/builder) -------------------------------------

def current_scheduler() -> Scheduler:
    scheduler = getattr(_local, "scheduler", None)
    if scheduler is None:
        scheduler = getattr(_local, "default_scheduler", None)
        if scheduler is None:
            scheduler = _local.default_scheduler = Scheduler()
    return scheduler


@contextmanager
def using_scheduler(scheduler: Scheduler) -> Iterator[Scheduler]:
    previous = getattr(_local, "scheduler", None)
    _local.scheduler = scheduler
    try:
        yield scheduler
    finally:
        _local.scheduler = previous


def is_reactive(value: Any) -> bool:
    """Signal, Computed or a zero-argument function (classes such as Enums are plain values)."""
    return isinstance(value, (Signal, Computed)) or (callable(value) and not isinstance(value, type))


def read(value: Any) -> Any:
    """Resolve a plain value, Signal, Computed or zero-argument callable (tracked)."""
    if isinstance(value, (Signal, Computed)):
        return value.value
    if callable(value) and not isinstance(value, type):
        return value()
    return value
