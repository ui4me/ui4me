"""Date/time/colour fields: parsing, rendering, and the Core 1.x input-type restriction."""
from __future__ import annotations

import datetime as dt
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from ui4me import ui
from ui4me._ui import core_compat
from ui4me._ui.errors import InvalidComponentProps


class FakeWindow:
    def __init__(self, html):
        self.html = html
        self.batches = []
        self.singles = []

    def add_stylesheet(self, css):
        return {"sheet": 1}

    def on(self, name, fn, element=None):
        return lambda: None

    def set_environment(self, **kw):
        pass

    def batch(self, ops):
        self.batches.extend(ops)

    def set_value(self, element, value):
        self.singles.append(("value", element, value))

    def focus(self, element):
        self.singles.append(("focus", element))


class FakeApp:
    def __init__(self, **kw):
        self.windows = []

    def on(self, name, fn):
        return None

    def open(self, html, **kw):
        w = FakeWindow(html)
        self.windows.append(w)
        return w

    def post(self, fn, **_):
        return Future()

    def close(self):
        pass


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(core_compat, "require", lambda: SimpleNamespace(App=FakeApp))
    holder = {}
    yield holder
    if "app" in holder:
        holder["app"].close()


REFUSED = ("date", "time", "datetime-local", "month", "week", "color")


def test_no_core_refused_input_types_are_ever_rendered(app):
    """Regression (real host, 2026-11-13): <input type=date> made Core reject the whole document."""
    with ui.app("Pickers") as a:
        app["app"] = a
        ui.date("D"), ui.time("T"), ui.datetime("DT"), ui.month("M"), ui.week("W"), ui.color("C")
    html = a.main.core.html
    for kind in REFUSED:
        assert f'type="{kind}"' not in html
    for kind in REFUSED:
        with pytest.raises(InvalidComponentProps, match="native picker"):
            with ui.app("x") as b:
                ui.input("bad", type=kind)


def test_parsing_and_errors(app):
    with ui.app("Parse") as a:
        app["app"] = a
        d = ui.date("D", min=dt.date(2026, 1, 1))
        t = ui.time("T")
        w = ui.week("W")
        m = ui.month("M")
        c = ui.color("C", value="#ABC")
    d._on_input({"value": "2026-02-03"})
    assert d.value == dt.date(2026, 2, 3) and d.error is None
    d._on_input({"value": "2025-12-31"})
    assert d.error == "Must be on or after 2026-01-01"
    d._on_input({"value": "nope"})
    assert d.error == "Enter a date as YYYY-MM-DD"
    t._on_input({"value": "7:05"})
    assert t.value == dt.time(7, 5)
    t._on_input({"value": "24:00"})
    assert t.error
    w._on_input({"value": "2026-W07"})
    assert w.value == dt.date(2026, 2, 9)
    m._on_input({"value": "2026-13"})
    assert m.error
    assert c.value == "#aabbcc"
    c._on_input({"value": "12345"})
    assert c.error == "Enter a colour as #rrggbb"


def test_calendar_renders_month_and_picks_a_day(app):
    picked = []
    with ui.app("Calendar") as a:
        app["app"] = a
        d = ui.date("D", value=dt.date(2026, 2, 14), on_change=picked.append)
    d.toggle_calendar(True)
    a.scheduler.flush()
    a.main.commit()
    html = "".join(op.get("html", "") for op in a.main.core.batches if op["op"] == "replace_children_html")
    assert "February 2026" in html and f'{d.panel.id}-d20260214' in html and 'aria-pressed="true"' in html
    d._panel_click({"element": f"{d.panel.id}-next"})
    assert d._shown == dt.date(2026, 3, 1)
    d._panel_click({"element": f"{d.panel.id}-d20260305"})
    assert d.value == dt.date(2026, 3, 5) and picked == [dt.date(2026, 3, 5)]
    assert not d.calendar_open


def test_color_swatch_click_sets_value(app):
    with ui.app("Colour") as a:
        app["app"] = a
        c = ui.color("C")
    c._swatch_click({"element": f"{c.swatches.id}-3"})
    assert c.value == "#dc2626"


def test_datetime_bounds_are_normalised_to_dates(app):
    """Review finding: a datetime min raised TypeError when compared with a date."""
    with ui.app("Bounds") as a:
        app["app"] = a
        d = ui.date("D", min=dt.datetime(2026, 3, 1, 15, 30))
    d._on_input({"value": "2026-03-01"})
    assert d.value == dt.date(2026, 3, 1) and d.error is None
