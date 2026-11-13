"""Pure-Python structural tests. The local agent must additionally run real Core headless/native suites."""
from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from ui4me import ui
from ui4me._ui import core_compat
from ui4me._ui.aio import UiFuture, drive


class FakeWindow:
    def __init__(self):
        self.sheets = {}
        self.next_sheet = 1
        self.events = {}
        self.batches = []
        self.fail_batch = False

    def add_stylesheet(self, css):
        sheet = self.next_sheet
        self.next_sheet += 1
        self.sheets[sheet] = css
        return {"sheet": sheet, "diagnostics": []}

    def replace_stylesheet(self, sheet, css):
        assert sheet in self.sheets
        self.sheets[sheet] = css
        return {"sheet": sheet, "diagnostics": []}

    def on(self, name, fn):
        self.events[name] = fn
        return None

    def set_environment(self, **kw):
        pass

    def batch(self, ops):
        if self.fail_batch:
            raise RuntimeError("injected Core failure")
        self.batches.extend(ops)

    def close(self):
        pass


class FakeTask:
    state = "running"
    cancelled = False

    def cancel(self):
        self.cancelled = True
        return True


class FakeApp:
    def __init__(self, **kw):
        self.windows = []
        self.jobs = []

    def on(self, name, fn):
        return None

    def open(self, *a, **kw):
        w = FakeWindow()
        self.windows.append(w)
        return w

    def post(self, fn, **_):
        return Future()  # no real event loop; tests call scheduler.flush explicitly

    def run_in_background(self, fn, *args, **kw):
        task = FakeTask()
        self.jobs.append((fn, task, kw))
        return task

    def stats(self):
        return {}

    def capabilities(self):
        return {}

    def close(self):
        pass


@pytest.fixture

def fake_core(monkeypatch):
    monkeypatch.setattr(core_compat, "require", lambda: SimpleNamespace(App=FakeApp))


def test_theme_replacement_and_core_escape_hatch(fake_core):
    with ui.app("Style") as app:
        ui.button("Save")
    native = app.main.core
    sheet = app._visual_sheets[id(app.main)]
    assert "--u4-primary" in native.sheets[sheet]
    assert "[hidden]" in app.main.document()  # structural invariants are retained
    app.theme.load(".u4-btn { color: red; }", mode="replace")
    assert native.sheets[sheet] == ".u4-btn { color: red; }"
    app.theme.load(".mine { background: blue; }", mode="append")
    assert any(".mine" in x for x in native.sheets.values())
    app.theme.reset_css()
    assert "--u4-primary" in native.sheets[sheet]
    app.close()


def test_broad_component_markup_and_state(fake_core):
    with ui.app("Kit") as app:
        with ui.toolbar():
            ui.icon_button("check", label="Accept")
            ui.icon("folder", label="Folder")
            ui.link("Docs", href="https://example.org", external=True)
        with ui.paper():
            ui.breadcrumbs([("Home", "#home"), ("Page", None)])
            ui.segmented(["All", "Recent"])
            ui.kbd("Ctrl+S")
            ui.avatar("AB")
            with ui.disclosure("More", open=True):
                ui.text("Details")
            ui.accordion({"A": lambda: ui.text("One"), "B": lambda: ui.text("Two")})
        with ui.center():
            with ui.aspect():
                ui.text("Preview")
        ui.tree([ui.TreeNode("root", "Root", (ui.TreeNode("child", "Child"),))])
        ui.date("Start")
        ui.color("Colour")
    markup = app.main.document()
    for cls in ("u4-toolbar", "u4-breadcrumbs", "u4-segmented", "u4-tree", "u4-disclosure", "u4-aspect"):
        assert cls in markup
    assert 'aria-label="Accept"' in markup
    assert "https://example.org" in markup
    app.close()


def test_tree_selection_and_expand(fake_core):
    with ui.app("Tree") as app:
        tree = ui.tree([ui.TreeNode("r", "Root", (ui.TreeNode("c", "Child"),))])
    tree.toggle("r")
    tree.select("c")
    app.scheduler.flush()
    assert tree.selected.peek() == "c"
    assert "r" in tree.expanded.peek()
    assert tree._entries["r"][1].attrs.get("hidden") is None
    app.close()


def test_reactive_items_preserve_scope_identity(fake_core):
    with ui.app("List") as app:
        rows = ui.state([{"id": 1, "title": "Old"}])
        each = ui.each(rows, key="id", preserve=True,
                       render=lambda item: ui.text(lambda: item["title"]))
    original = each.scope(1)
    label = original._children[0]
    rows.set([{"id": 1, "title": "New"}])
    app.scheduler.flush()
    assert each.scope(1) is original
    assert label.root.text == "New"
    assert not label.disposed
    app.close()


def test_owned_async_stops_after_disposal(fake_core):
    with ui.app("Async") as app:
        owner = ui.button("Async")
    pending = UiFuture(app, "pending")

    async def work():
        return await pending

    outcome = drive(app, work(), "test", owner=owner)
    assert not outcome.done
    owner.dispose()
    assert outcome.done
    pending.set_result(123)
    assert outcome.state == "cancelled"
    app.close()


def test_dom_failure_fails_closed(fake_core):
    with ui.app("DOM") as app:
        label = ui.text("Good")
    app.main.core.fail_batch = True
    label.set("Changed")
    app.scheduler.flush()
    assert app.main._desynced
    assert app.error_count > 0
    label.set("Again")
    app.scheduler.flush()
    assert app.main._ops == []
    app.close()


def test_query_table_rejects_obsolete_results(fake_core):
    with ui.app("Data") as app:
        q = ui.query_table(lambda page, size, search: ([{"id": page, "name": str(page)}], 120),
                           key="id", columns=["id", "name"], page_size=25)
    first = app.core.jobs[0]
    q.goto(1)
    assert first[1].cancelled
    last = app.core.jobs[-1]
    # Worker completion simulation: on_done callbacks execute on UI owner.
    first[2]["on_done"](( [{"id": 0, "name": "stale"}], 120))
    last[2]["on_done"](( [{"id": 1, "name": "current"}], 120))
    app.scheduler.flush()
    assert q.rows.peek()[0]["name"] == "current"
    assert q.page.peek() == 1
    app.close()


def test_combobox_menu_palette_and_density(fake_core):
    ran = []
    with ui.app("Controls") as app:
        app.commands.add("Refresh", lambda: ran.append("refresh"))
        combo = ui.combobox({"us": "United States", "cz": "Czechia"}, selected="cz")
        menu = ui.menu("Actions", [ui.MenuItem("Refresh", lambda: ran.append("menu")),
                                   ui.MenuItem("Noop", disabled=True)])
        palette = ui.command_palette()
        ui.density("compact")
        ui.theme_preset("sage")
    assert combo.value == "cz"
    combo.choose("us")
    assert combo.value == "us"
    assert combo.query.peek() == "United States"
    menu.select(0)
    menu.select(1)
    assert ran == ["menu"]
    assert "u4-density-compact" in app.main.document()
    sheet = app._visual_sheets[id(app.main)]
    assert "UI4ME preset: sage" in app.main.core.sheets[sheet]
    assert palette.search.value is None
    assert "Open command palette" in app.commands._commands
    app.close()


def test_bad_data_source_result_exposes_error_state(fake_core):
    with ui.app("Queries") as app:
        table = ui.query_table(lambda _p, _s, _q: "bad result", key="id", columns=["id"])
    task = app.core.jobs[0]
    task[2]["on_done"]("bad result")
    app.scheduler.flush()
    assert table.error.peek() is not None
    assert not table.loading.peek()
    app.close()


def test_desktop_services_are_core_backed_or_explicitly_unsupported(fake_core):
    with ui.app("Native") as app:
        ui.text("Native integrations")
    calls = []
    app.main.core.native = SimpleNamespace(set=lambda **kw: calls.append(kw) or {})
    app.desktop.window_action("maximize")
    app.desktop.window_action("restore")
    assert calls == [{"maximized": True}, {"minimized": False, "maximized": False, "fullscreen": False}]
    for name, call in {
        "menu_bar": lambda: app.desktop.menu_bar([ui.NativeMenuItem("File")]),
        "context_menu": lambda: app.desktop.context_menu(1, 2, []),
        "tray": lambda: app.desktop.tray(),
        "global_hotkey": lambda: app.desktop.global_hotkey("x", "Ctrl+K", lambda: None),
        "export_pdf": lambda: app.desktop.export_pdf("out.pdf"),
        "print_document": lambda: app.desktop.print_document(),
        "clipboard_html": lambda: app.desktop.clipboard_html("<b>x</b>"),
        "notify_system": lambda: app.notify_system("hello"),
    }.items():
        with pytest.raises(NotImplementedError, match="not provided by UI4ME Core"):
            call()
    with pytest.raises(Exception):
        app.desktop.window_action("teleport")
    app.close()
