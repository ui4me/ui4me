"""R01–R09, R14: reactive state contract (pure, no Core)."""
import threading

import pytest

from ui4me._ui.errors import ReactiveCycleError, WrongThreadError
from ui4me._ui.reactive import Computed, Reaction, Scheduler, Signal, untracked


def make():
    errors = []
    return Scheduler(on_error=lambda e, ctx: errors.append((e, ctx))), errors


def test_r01_reads_and_r02_propagation():
    s, _ = make()
    a = Signal(1)
    seen = []
    Reaction(lambda: seen.append(a.value), s)
    assert seen == [1]
    with s.batch():
        a.set(2)
    assert seen == [1, 2]


def test_r03_dynamic_dependency_removal():
    s, _ = make()
    flag, x, y = Signal(True), Signal("x"), Signal("y")
    runs = []
    Reaction(lambda: runs.append(x.value if flag.value else y.value), s)
    with s.batch():
        flag.set(False)
    assert runs == ["x", "y"]
    with s.batch():
        x.set("x2")  # no longer a dependency
    assert runs == ["x", "y"]
    assert not x._observers


def test_r04_computed_caching_observed_and_unobserved():
    s, _ = make()
    a = Signal(2)
    calls = []

    def square():
        calls.append(1)
        return a.value * a.value
    c = Computed(square)
    assert c.value == 4 and c.value == 4
    assert len(calls) == 1  # unobserved but cached by version check
    a.set(3)
    assert c.value == 9 and len(calls) == 2
    seen = []
    Reaction(lambda: seen.append(c.value), s)
    assert len(calls) == 2  # still valid
    with s.batch():
        a.set(4)
    assert seen == [9, 16] and len(calls) == 3


def test_unobserved_computed_does_not_retain_observers():
    a = Signal(1)
    c = Computed(lambda: a.value + 1)
    assert c.value == 2
    assert not a._observers


def test_r05_cycle_detected():
    holder = {}
    c = Computed(lambda: holder["c"].value + 1)
    holder["c"] = c
    with pytest.raises(ReactiveCycleError):
        c.value


def test_r06_nested_batches_flush_once():
    s, _ = make()
    a, b = Signal(0), Signal(0)
    seen = []
    Reaction(lambda: seen.append((a.value, b.value)), s)
    with s.batch():
        a.set(1)
        with s.batch():
            b.set(2)
        assert seen == [(0, 0)]
        a.set(3)
    assert seen == [(0, 0), (3, 2)]


def test_batch_flushes_on_exception():
    s, _ = make()
    a = Signal(0)
    seen = []
    Reaction(lambda: seen.append(a.value), s)
    with pytest.raises(RuntimeError):
        with s.batch():
            a.set(1)
            raise RuntimeError("boom")
    assert seen == [0, 1]


def test_r07_noop_set():
    s, _ = make()
    a = Signal("same")
    seen = []
    Reaction(lambda: seen.append(a.value), s)
    with s.batch():
        a.set("same")
    assert seen == ["same"]


def test_r08_reentrant_update_in_effect_settles():
    s, _ = make()
    a, b = Signal(1), Signal(0)
    Reaction(lambda: b.set(a.value * 10), s)
    seen = []
    Reaction(lambda: seen.append(b.value), s)
    with s.batch():
        a.set(2)
    assert b.peek() == 20 and seen[-1] == 20


def test_self_triggering_loop_is_bounded():
    s, errors = make()
    a = Signal(0)
    Reaction(lambda: a.set(a.value + 1), s)
    with s.batch():
        a.set(100)
    assert any(isinstance(e, ReactiveCycleError) for e, _ in errors)


def test_r09_wrong_thread():
    a = Signal(0)
    caught = []

    def worker():
        try:
            a.set(1)
        except WrongThreadError as e:
            caught.append(e)
    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert caught and a.peek() == 0


def test_r14_error_reported_with_context_and_recoverable():
    s, errors = make()
    a = Signal(1)
    seen = []

    def render():
        if a.value == 2:
            raise ValueError("bad")
        seen.append(a.value)
    Reaction(render, s, context="Text#u4-3")
    with s.batch():
        a.set(2)
    assert errors and errors[0][1] == "Text#u4-3"
    with s.batch():
        a.set(3)
    assert seen == [1, 3]


def test_dispose_removes_edges_and_cleanup_runs():
    s, _ = make()
    a = Signal(1)
    cleaned = []
    r = Reaction(lambda: (a.value, lambda: cleaned.append(1))[1], s)
    with s.batch():
        a.set(2)
    assert cleaned == [1]
    r.dispose()
    assert cleaned == [1, 1] and not a._observers


def test_diamond_glitch_free():
    s, _ = make()
    a = Signal(1)
    b = Computed(lambda: a.value + 1)
    c = Computed(lambda: a.value * 2)
    seen = []
    Reaction(lambda: seen.append((b.value, c.value)), s)
    with s.batch():
        a.set(5)
    assert seen == [(2, 2), (6, 10)]


def test_untracked_and_mutate():
    s, _ = make()
    items = Signal([1])
    other = Signal(0)
    seen = []
    Reaction(lambda: seen.append((len(items.value), untracked(lambda: other.value))), s)
    with s.batch():
        other.set(9)
    assert seen == [(1, 0)]
    with s.batch():
        items.mutate(lambda lst: lst.append(2))
    assert seen == [(1, 0), (2, 9)]


def test_render_before_effects():
    s, _ = make()
    order = []
    a = Signal(0)
    Reaction(lambda: (a.value, order.append("effect")), s, priority=Reaction.EFFECT)
    Reaction(lambda: (a.value, order.append("render")), s, priority=Reaction.RENDER)
    order.clear()
    with s.batch():
        a.set(1)
    assert order == ["render", "effect"]


def test_adapt_never_overwrites_default_bound_loop_variables():
    """Regression (real host, 2026-11-13): ``on_click=lambda i=i: ...`` received the event dict."""
    from ui4me._ui.component import adapt
    calls = []
    handlers = [adapt(lambda i=i: calls.append(i), None) for i in range(3)]
    handlers[2]({'type': 'click'})
    assert calls == [2]
    adapt(lambda event: calls.append(event['type']), None)({'type': 'click'})
    adapt(lambda *a: calls.append(len(a)), None)({'type': 'click'})
    assert calls == [2, 'click', 1]
