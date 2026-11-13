"""Integration tests against the real UI4ME Core host (``ui4me-run --headless``).

These run the installed ``ui4me-core`` native host process, its IPC and its DOM engine,
without a desktop window. Events are *simulated* through UI4ME's dispatcher (ui.testing
Pilot), so native input, focus and dialogs are covered by tests/native instead.
Skipped when the Core host is not installed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ui4me_core = pytest.importorskip("ui4me_core")
try:
    HOST = ui4me_core.host_binary()
except Exception:  # pragma: no cover - no packaged host
    HOST = None
pytestmark = pytest.mark.skipif(HOST is None or not Path(str(HOST)).exists(), reason="Core host binary not installed")

PRELUDE = """
import json, sys, threading, time
from ui4me import ui
from ui4me._ui.testing import Pilot
OUT = sys.argv[1]
results = {}
def record(name, value):
    results[name] = value
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, default=str)
"""


def run_app(tmp_path: Path, body: str, timeout: float = 90) -> dict:
    script = tmp_path / "app.py"
    out = tmp_path / "out.json"
    script.write_text(PRELUDE + textwrap.dedent(body), encoding="utf-8")
    env = dict(os.environ, UI4ME_ALLOW_UNSUPERVISED="1")
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("DISPLAY", None)
    proc = subprocess.run([sys.executable, "-m", "ui4me", "--headless", str(script), str(out)],
                          capture_output=True, text=True, timeout=timeout, env=env)
    log = proc.stdout + proc.stderr
    assert out.exists(), f"app produced no results (exit {proc.returncode}):\n{log[-4000:]}"
    data = json.loads(out.read_text(encoding="utf-8"))
    data["_exit"] = proc.returncode
    data["_log"] = log[-4000:]
    return data


def test_reactive_components_events_and_clean_exit(tmp_path):
    r = run_app(tmp_path, """
    name = ui.state("")
    clicks = ui.state(0)
    agree = ui.state(False)
    color = ui.state("red")
    with ui.app("Host pilot") as app:
        field = ui.input("Name", bind=name)
        hello = ui.text(lambda: f"Hello {name.value or 'nobody'}")
        btn = ui.button("Go", on_click=lambda: clicks.set(clicks.value + 1))
        box = ui.checkbox("ok", bind=agree)
        sel = ui.select("Color", options=["red", "green"], bind=color)
    closed = []
    app.main.on_close(lambda: closed.append(1))
    def script(p):
        p.type(field, "Ada")
        p.click(btn); p.click(btn)
        p.check(box, True)
        p.choose(sel, "green")
        doc = app.main.core.document
        record("hello", doc.get_text(hello.id))
        record("dom_value", doc.get_value(field._focus_target().id))
        record("state", [name.peek(), clicks.peek(), agree.peek(), color.peek()])
        record("select_dom", doc.get_value(sel._focus_target().id))
    Pilot(app).run(script)
    record("on_close", len(closed))
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["hello"] == "Hello Ada"
    assert r["dom_value"] == "Ada"
    assert r["state"] == ["Ada", 2, True, "green"]
    assert r["select_dom"] == "green"
    assert r["on_close"] == 1


def test_keyed_list_reorder_keeps_core_nodes_and_large_batches_split(tmp_path):
    r = run_app(tmp_path, """
    items = ui.state([{"id": i} for i in range(5)])
    big = ui.state([])
    rows = {}
    with ui.app("Each") as app:
        def render(item):
            rows[item["id"]] = ui.text(f"row {item['id']}")
        lst = ui.each(items, key="id", render=render)
        ui.each(big, key="id", render=lambda item: ui.text(str(item["id"])))
    def script(p):
        doc = app.main.core.document
        before = doc.node(rows[3].id).id
        items.set([{"id": i} for i in (4, 3, 1, 9)])
        p.flush(); app.main.commit()
        record("same_node", doc.node(rows[3].id).id == before)
        record("removed", rows[2].disposed)
        record("order", [doc.get_text(i) for i in doc.query(f"#{lst.root.id} .u4-text")["ids"]])
        big.set([{"id": i} for i in range(1500)])  # > 1024 DOM operations in one commit
        p.flush(); app.main.commit()
        record("big", doc.query(".u4-text", limit=4096)["total"])
        record("errors", app.error_count)
    Pilot(app).run(script)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["same_node"] is True and r["removed"] is True
    assert r["order"] == ["row 4", "row 3", "row 1", "row 9"]
    assert r["big"] == 4 + 1500
    assert r["errors"] == 0


def test_many_handlers_share_core_subscriptions(tmp_path):
    r = run_app(tmp_path, """
    hits = []
    with ui.app("Subs") as app:
        buttons = [ui.button(f"b{i}", on_click=lambda i=i: hits.append(i)) for i in range(400)]
    def script(p):
        p.click(buttons[399]); p.click(buttons[0])
        doc = app.main.core.document
        record("core_handlers", len(doc._handlers))
        record("hits", hits)
    Pilot(app).run(script)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["hits"] == [399, 0]
    assert r["core_handlers"] < 16  # one delegated Core subscription per event type, not 400


def test_theme_replacement_tokens_and_no_stylesheet_leak(tmp_path):
    r = run_app(tmp_path, """
    with ui.app("Theme") as app:
        t = ui.text("x", classes="probe")
    def script(p):
        doc = app.main.core.document
        n = len(doc.stylesheets())
        for color in ("rgb(1, 2, 3)", "rgb(4, 5, 6)", "rgb(7, 8, 9)"):
            app.theme.load(".probe { color: %s; }" % color, mode="replace")
        record("color", doc.computed_style(["color"], t.id)["properties"]["color"]["value"])
        record("sheets_same", len(doc.stylesheets()) == n)
        app.theme.reset_css()
        app.theme.set("dark")
        record("scheme", doc.environment().get("color_scheme"))
    Pilot(app).run(script)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["color"] == "rgb(7, 8, 9)"
    assert r["sheets_same"] is True
    assert r["scheme"] == "dark"


def test_raw_document_replacement_stops_management_without_stale_patches(tmp_path):
    r = run_app(tmp_path, """
    n = ui.state(0)
    with ui.app("Raw") as app:
        label = ui.text(lambda: str(n.value))
    errors = []
    app.on_error(lambda e, ctx: errors.append(ctx))
    def script(p):
        new = app.main.core.native.load_html("<p id='raw'>raw</p>")
        n.set(5); p.flush(); app.main.commit()
        record("raw_text", new.get_text("raw"))
        record("disposed", label.disposed)
        record("errors", errors)
    Pilot(app).run(script, raise_app_errors=False)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["raw_text"] == "raw"
    assert r["disposed"] is True
    assert r["errors"] == ["document generation"]


def test_second_window_close_disposes_and_stop_from_worker_thread(tmp_path):
    r = run_app(tmp_path, """
    log = []
    with ui.app("Main") as app:
        ui.text("main")
    def make():
        with app.window("Second", on_close=lambda: log.append("second closed")) as w:
            b = ui.button("x")
        return w, b
    def later():
        w, b = make()
        record("windows_open", len(app.windows))
        w.close()  # graceful request; disposal waits for Core's closed event
        def check():
            record("second_closed", [w.closed, b.disposed, log])
            threading.Thread(target=app.stop).start()  # stop() is thread-safe
        app.after(1.0, check)
    app.after(0.2, later)
    app.run()
    record("ran", True)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["windows_open"] == 2
    assert r["second_closed"] == [True, True, ["second closed"]]


def test_unsupported_native_services_fail_explicitly(tmp_path):
    r = run_app(tmp_path, """
    with ui.app("Unsupported") as app:
        ui.text("x")
    outcomes = {}
    def script(p):
        for name, call in {
            "notify_system": lambda: app.notify_system("t"),
            "pdf": lambda: app.main.core.export_pdf("x.pdf"),
            "tray": lambda: app.core.set_tray(),
            "hotkey": lambda: app.core.register_hotkey("Ctrl+K"),
            "menubar": lambda: app.main.core.set_menu([]),
        }.items():
            try:
                call(); outcomes[name] = "returned"
            except NotImplementedError as e:
                outcomes[name] = "NotImplementedError"
        record("outcomes", outcomes)
    Pilot(app).run(script)
    """)
    assert r["_exit"] == 0, r["_log"]
    assert set(r["outcomes"].values()) == {"NotImplementedError"}


def test_every_component_renders_in_one_real_host_document(tmp_path):
    """Catches markup the Core renderer refuses (e.g. <input type=date>, found 2026-11-13)."""
    r = run_app(tmp_path, """
    import datetime as dt
    rows = ui.state([{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}])
    with ui.app("Everything", width=1200, height=900) as app:
        ui.text("t"); ui.heading("h"); ui.caption("c"); ui.badge("b"); ui.button("b"); ui.input("i")
        ui.password(); ui.textarea("ta"); ui.number("n", value=3); ui.checkbox("cb"); ui.switch("sw")
        ui.radio("r", options=["a", "b"]); ui.select("s", options=["a", "b"]); ui.slider("sl")
        with ui.row(): ui.spacer(); ui.divider()
        with ui.column(): pass
        with ui.stack(): pass
        with ui.card(): pass
        with ui.grid(): pass
        with ui.scroll(height="100px"): pass
        ui.tabs({"A": lambda: ui.text("a"), "B": lambda: ui.text("b")})
        ui.when(ui.state(True), then=lambda: ui.text("yes"))
        ui.each(rows, key="id", render=lambda r: ui.text(r["name"]))
        ui.alert("a"); ui.empty(); ui.loading(); ui.error_state(); ui.spinner(); ui.progress(0.5)
        ui.html("<p>raw</p>"); ui.markdown("# Title\\n\\n*em* `code`"); ui.code("x = 1", language="python")
        ui.table(rows, columns=["id", "name"], key="id", search=True, sort=True)
        ui.log(); ui.chat()
        with ui.surface(): pass
        with ui.paper(): pass
        with ui.toolbar(): pass
        with ui.header(): pass
        with ui.footer(): pass
        with ui.statusbar(): pass
        with ui.section(): pass
        with ui.center(): pass
        with ui.sticky(): pass
        with ui.container(): pass
        with ui.aspect(): pass
        ui.kbd("Ctrl"); ui.inline_code("x"); ui.mark("m"); ui.avatar("AL"); ui.link("l", href="https://example.org")
        ui.icon("folder"); ui.icon_button("folder", label="Open")
        ui.breadcrumbs([("Home", None)])
        with ui.disclosure("d"): pass
        ui.accordion({"A": lambda: ui.text("a")})
        with ui.drawer("Drawer"): pass
        ui.segmented(["x", "y"]); ui.tree([ui.TreeNode("n", "Node")])
        ui.date(value=dt.date(2026, 1, 2)); ui.time(); ui.datetime(); ui.month(); ui.week(); ui.color()
        ui.email(); ui.url(); ui.search(); ui.telephone()
        ui.combobox(["a", "b"]); ui.command_palette(); ui.path("p"); ui.file_input()
        ui.query_table(lambda p, s, q: ([], 0), key="id", columns=["id"])
        ui.menu("Menu", [ui.MenuItem("One", lambda: None)])
        ui.progress_ring(0.3); ui.sparkline([1, 3, 2])
        with ui.dialog("Dialog"): ui.text("in dialog")
    def check():
        doc = app.main.core.document
        record("loaded", doc.query("body")["matched_nodes"] >= 1)
        record("errors", [app.error_count, app.last_error])
        record("diagnostics_ok", "diagnostics" in doc.diagnostics())
        app.stop()
    app.after(0.8, check)
    app.run()
    """)
    assert r["_exit"] == 0, r["_log"]
    assert r["loaded"] is True
    assert r["errors"] == [0, None]
