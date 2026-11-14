"""Regression tests for defects found while qualifying UI4ME 2.1 (no native host needed)."""
from __future__ import annotations

import hashlib
import inspect

from ui4me._ui import app as app_module
from ui4me._ui import settings as settings_module
from ui4me import launcher


def test_derived_app_id_keeps_ascii_titles_stable():
    assert app_module._derived_app_id("My App") == "org.ui4me.app.my-app"
    assert app_module._derived_app_id("UI4ME — Component Gallery") == "org.ui4me.app.ui4me-component-gallery"


def test_derived_app_id_never_collides_for_non_ascii_titles():
    first = app_module._derived_app_id("日本語ツール")
    second = app_module._derived_app_id("Обработка")
    assert first != second
    assert first == "org.ui4me.app.app-" + hashlib.sha256("日本語ツール".encode()).hexdigest()[:12]
    for value in (first, second):
        settings_module.settings_dir(value)  # valid settings folder name


def test_settings_write_is_durable(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    synced = []
    real_fsync = settings_module.os.fsync
    monkeypatch.setattr(settings_module.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))

    class Reporter:
        def _report(self, error, context):
            raise AssertionError(f"unexpected settings error: {error}")
    store = settings_module.Settings(Reporter(), "org.example.Durable")
    store.set("theme", "dark")
    assert synced, "settings must be flushed to disk before the atomic replace"
    assert settings_module.Settings(Reporter(), "org.example.Durable").get("theme") == "dark"
    assert not list(store.path.parent.glob(".settings-*.tmp"))


def test_launcher_imports_version_once():
    source = inspect.getsource(launcher)
    assert source.count("from . import __version__") == 1


def test_tooltip_trigger_is_described_by_tip(monkeypatch):
    import re
    from types import SimpleNamespace
    from ui4me import ui
    from ui4me._ui import core_compat
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("v05", pathlib.Path(__file__).with_name("test_v05_features.py"))
    v05 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v05)
    monkeypatch.setattr(core_compat, "require", lambda: SimpleNamespace(App=v05.FakeApp))
    with ui.app("Tips") as app:
        with ui.tooltip("Explains the action"):
            ui.button("Act")
    html = app.main.document()
    tip = re.search(r'<span id="([^"]+)" class="u4-tooltip-text" role="tooltip"', html)
    assert tip, html
    assert re.search(r'class="u4-tooltip-trigger"[^>]*aria-describedby="%s"' % tip.group(1), html) or \
        re.search(r'aria-describedby="%s"[^>]*class="u4-tooltip-trigger"' % tip.group(1), html), html
    app.close()


def _fake_core(monkeypatch):
    import importlib.util, pathlib
    from types import SimpleNamespace
    from ui4me._ui import core_compat
    spec = importlib.util.spec_from_file_location("v05", pathlib.Path(__file__).with_name("test_v05_features.py"))
    v05 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v05)
    monkeypatch.setattr(core_compat, "require", lambda: SimpleNamespace(App=v05.FakeApp))
    return v05


def test_dialog_close_returns_focus_to_opener_after_busy_reenable(monkeypatch):
    """``on_click=lambda: dlg.open()`` disables the opener while the dialog is open.

    Found natively on KDE: Core restored focus to the still-disabled opener (rejected),
    UI4ME's own refocus was rejected too and that desynchronized the whole window.
    """
    from types import SimpleNamespace
    from ui4me import ui
    _fake_core(monkeypatch)
    with ui.app("Dialog focus") as app:
        opener = ui.button("Open", on_click=lambda: dlg.open())
        with ui.dialog("Confirm") as dlg:
            ui.text("Body")
    core = app.main.core
    calls, posted = [], []
    core.document = SimpleNamespace(focused_element=lambda: {"element": opener.id})
    core.show_dialog = lambda element, modal=True: calls.append(("show", element))
    core.close_dialog = lambda element, value=None: calls.append(("close", element))
    core.focus = lambda element: calls.append(("focus", element))
    monkeypatch.setattr(app, "post", lambda fn: posted.append(fn))
    opener.click()
    app.scheduler.flush()
    app.main.commit()
    assert opener.disabled and calls == [("show", dlg.root.id)]
    ops = []
    real_batch = core.batch
    core.batch = lambda run: (ops.extend(o["op"] + ":" + str(o.get("name")) for o in run), real_batch(run))
    real_focus = core.focus
    core.focus = lambda element: (ops.append("focus"), real_focus(element))
    # Escape: Core reports the native close; the posted refocus may run in the SAME
    # coalesced owner group, before that group's flush (worst case, simulated here).
    with app.scheduler.batch():
        dlg._closed({"type": "close"})
        assert ("focus", opener.id) not in calls  # deferred through app.post
        for fn in posted:
            fn()
    app.main.commit()
    assert not opener.disabled and calls[-1] == ("focus", opener.id), calls
    assert ops.index("remove_attribute:disabled") < ops.index("focus"), ops
    app.close()


def test_rejected_focus_does_not_desynchronize_window(monkeypatch):
    from ui4me import ui
    _fake_core(monkeypatch)
    with ui.app("Focus reject") as app:
        field = ui.input("Name")
    core = app.main.core

    def reject(element):
        raise RuntimeError("-32602: FOCUS_MOVE_REJECTED: not a focusable area")
    core.focus = reject
    core.has_element = lambda element: True
    field.focus()
    app.main.commit()
    assert not app.main._desynced and app.error_count == 0
    app.close()


def test_owner_loop_coalesces_queued_items_in_order_with_isolation():
    """Queued owner items share one group (one flush/commit) and keep their order."""
    import contextlib
    import threading
    from ui4me._ui import _adapter

    class Rpc:
        shutdown_requested = threading.Event()
        closed = False

    app = _adapter.App.__new__(_adapter.App)
    app.native = type("Native", (), {"ready": lambda self: None, "rpc": Rpc()})()
    app.closed = False
    app._queue = _adapter.queue.Queue()
    app._priority = _adapter.collections.deque()
    app._pending = 0
    app._pending_lock = threading.Lock()
    groups, seen = [], []

    @contextlib.contextmanager
    def group():
        groups.append([])
        yield
        groups[-1].append("flush")

    def item(n):
        def run():
            seen.append(n)
            groups[-1].append(n)
            if n == 3:
                raise ValueError("isolated")
        return run
    futures = [app.post(item(n)) for n in range(1, 41)]
    futures.append(app.post(lambda: Rpc.shutdown_requested.set()))
    app.run(group=group)
    Rpc.shutdown_requested.clear()
    assert seen == list(range(1, 41))
    assert isinstance(futures[2].exception(), ValueError) and futures[3].result() is None
    assert len(groups[0]) == _adapter.App.GROUP_ITEMS + 1 and groups[0][-1] == "flush"
    assert all(g[-1] == "flush" for g in groups)


def test_build_error_traceback_printed_before_core_disconnect(monkeypatch, capsys):
    """Found headless: the host ended the backend on disconnect before Python printed it."""
    import pytest
    from ui4me import ui
    _fake_core(monkeypatch)
    order = []
    with pytest.raises(ValueError) as info:
        with ui.app("Broken") as app:
            monkeypatch.setattr(app.core, "close", lambda: order.append(("close", capsys.readouterr().err)),
                                raising=False)
            raise ValueError("boom ✓")
    assert order and "ValueError: boom ✓" in order[0][1]
    assert getattr(info.value, "_ui4me_traceback_reported", False)


def test_window_close_racing_app_shutdown_is_quiet(monkeypatch):
    """Found in the 30-minute soak: a timer closed a window as the host shut down."""
    import pytest
    from ui4me import ui
    _fake_core(monkeypatch)
    with ui.app("Race") as app:
        ui.text("main")
    with app.window("Second") as second:
        ui.text("second")

    def shutting_down():
        raise RuntimeError("-32008: Application is shutting down or failed")
    second.core.close = shutting_down
    second.close()  # host already shutting down: no error
    app.stopping = True
    second.close()
    app.stopping = False
    second.core.close = lambda: (_ for _ in ()).throw(RuntimeError("-32602: other failure"))
    with pytest.raises(RuntimeError):
        second.close()
    app.close()


def test_theme_switch_suspends_transitions_and_default_theme_has_none(monkeypatch):
    """Found on Windows: a theme switch started ~300 transition events at once; Core 1.0.1
    forwards all of them and disconnects a backend that falls behind its event queue."""
    import re
    from ui4me import ui
    from ui4me._ui.theme import functional_css, theme_css
    _fake_core(monkeypatch)
    assert not re.search(r"\.u4-(btn|input)[^{]*\{[^}]*transition:\s*(?!none)", theme_css())
    assert ".u4-theme-switching, .u4-theme-switching * { transition: none !important; }" in functional_css()
    with ui.app("Theme") as app:
        ui.button("A")
    core = app.main.core
    seen, timers = [], []
    core.set_environment = lambda **kw: seen.append(("env", app.main.root.root.has_class("u4-theme-switching")
                                                     if hasattr(app.main.root.root, "has_class")
                                                     else "u4-theme-switching" in app.main.root.root.classes))
    app.core.timer = lambda ms, fn, repeat=False: timers.append((ms, fn))
    app.theme.set("dark")
    assert seen == [("env", True)] and timers and timers[0][0] == 250
    sent = [op for op in core.batches if op.get("name") == "u4-theme-switching"]
    assert sent and sent[0]["op"] == "add_class"
    timers[0][1]({"type": "timer"})
    app.main.commit()
    assert "u4-theme-switching" not in app.main.root.root.classes
    app.close()
