"""Integration-shaped adapter tests using Core 1.0's public object contracts.

This is not native qualification; tests simulate Core's host notifications.
"""
from __future__ import annotations
from concurrent.futures import Future
import json
import os
import sys
import threading
from types import ModuleType
import pytest


class FakeRPC:
    def __init__(self):
        self.callbacks = {}
        self.shutdown_requested = threading.Event()
        self.closed = False
    def on_notification(self, name, fn):
        self.callbacks[name] = fn


class FakeDoc:
    def __init__(self, html):
        self.html = html
        self.id = "doc-1"
        self.batches = []
        self.sheets = {}
        self.next_sheet = 1
        self.listeners = {}
        self.attributes = {}
        self.values = {}
    def on(self, name, fn, *, element=None):
        self.listeners.setdefault(name, []).append((element, fn))
        return lambda: self.listeners[name].remove((element, fn))
    def add_stylesheet(self, css):
        sid = self.next_sheet
        self.next_sheet += 1
        self.sheets[sid] = css
        return {'sheet': sid}
    def replace_stylesheet(self, sheet, css):
        self.sheets[sheet] = css
    def batch(self, ops):
        self.batches.extend(ops)
    def environment(self):
        return {'color_scheme': 'light'}
    def set_environment(self, **kw):
        return kw
    def set_value(self, element, value):
        self.values[element] = value
    def get_value(self, element):
        return self.values.get(element, '')
    def set_checked(self, element, checked):
        self.values[element] = checked
    def get_checked(self, element):
        return bool(self.values.get(element))
    def query(self, selector):
        return {'ids': ['fake-element'] if selector == '#fake-element' else []}
    def command(self, op, **fields):
        if op == 'get_html': return {'html':self.html}
        if op == 'get_rect': return {'rect':None}
        if op == 'get_attribute': return {'value':None}
        return {}
    def scroll_to(self, **kw): pass
    def focus(self, element): pass
    def scroll_into_view(self, element, **kw): pass
    def prevent_default(self, element, event, **kw): pass

class FakeCoreWindow:
    def __init__(self, application, html):
        self.app = application
        self.id = 'window-1'
        self.document = FakeDoc(html)
        self.closed = False
        self.properties = {}
    def set(self, **kw):
        self.properties.update(kw)
        return {}
    def request_close(self):
        self.closed = True
    def on_before_close(self, policy):
        self.policy = policy
    def state(self):
        return self.properties
    def open_files(self, *, wait=False, **kw):
        f = Future()
        f.set_result({'paths':['/tmp/fake.txt'], 'cancelled':False})
        return f
    def save_file(self, *, wait=False, **kw):
        return self.open_files(wait=wait, **kw)
    def choose_folder(self, *, wait=False, **kw):
        return self.open_files(wait=wait, **kw)

class FakeCoreApp:
    last = None
    def __init__(self):
        self.rpc = FakeRPC()
        self._windows = {}
        self.ready_called = False
        self.is_closed = False
        FakeCoreApp.last = self
    @classmethod
    def from_environment(cls):
        return cls()
    def _window_event(self, event):
        if event.get('type') == 'closed':
            self._windows.pop(event.get('window_id'), None)
    def open_html(self, html, *, title, width, height, asset_root=None):
        window = FakeCoreWindow(self, html)
        self._windows[window.id] = window
        return window
    def ready(self):
        self.ready_called = True
    def run(self):
        self.ready()
    def request_quit(self):
        self.rpc.shutdown_requested.set()
    def capabilities(self):
        return {'native':True}
    def close(self):
        self.is_closed = True
    def clipboard_text(self): return 'test'
    def set_clipboard_text(self, text): pass

@pytest.fixture
def fake_core(monkeypatch):
    module = ModuleType('ui4me_core')
    module.__version__ = '1.0.0'
    module.Application = FakeCoreApp
    monkeypatch.setitem(sys.modules, 'ui4me_core', module)
    monkeypatch.setenv('UI4ME_ENDPOINT','test-endpoint')
    monkeypatch.setenv('UI4ME_TOKEN','test-token')
    from ui4me._ui import core_compat
    core_compat.require.cache_clear()
    yield
    core_compat.require.cache_clear()


def test_full_component_build_over_new_host_api(fake_core):
    from ui4me import ui
    with ui.app('V2', theme='light') as app:
        state = ui.state(1)
        ui.text(lambda: str(state.value))
        ui.button('Save')
    native_doc = FakeCoreApp.last._windows['window-1'].document
    assert 'Save' in native_doc.html
    assert len(native_doc.sheets) == 1
    assert app.main.core.native is FakeCoreApp.last._windows['window-1']
    assert app.main.core.document is native_doc
    state.set(3)
    app.scheduler.flush()
    assert native_doc.batches
    app.close()
    assert FakeCoreApp.last.is_closed


def test_post_dispatch_runs_on_original_owner_thread(fake_core):
    from ui4me import ui
    with ui.app('Dispatcher') as app:
        button = ui.button('Click')
    owner = threading.get_ident()
    executed = []
    # Core callback workers must never directly mutate the UI component tree.
    app.core.post(lambda: (executed.append(threading.get_ident()), app.stop()))
    app.run()
    assert executed == [owner]
    assert FakeCoreApp.last.ready_called


def test_core_escape_hatch_and_theme_replacement(fake_core):
    from ui4me import ui
    with ui.app('Bridge') as app:
        ui.text('Bridge')
    doc = app.main.core.document
    app.theme.load('.u4-app {color:purple}', mode='replace')
    assert '.u4-app {color:purple}' in doc.sheets.values()
    assert app.main.core.has_element('fake-element')
    assert app.main.core.query('#fake-element') == ['fake-element']
    app.close()


def test_unsupported_legacy_native_services_fail_explicitly(fake_core):
    from ui4me import ui
    with ui.app('Bridge') as app:
        ui.text('Bridge')
    with pytest.raises(NotImplementedError, match='not exposed'):
        app.main.core.export_pdf('sample.pdf')
    app.close()


def test_direct_execution_without_host_has_actionable_error(fake_core, monkeypatch):
    from ui4me import ui
    monkeypatch.delenv('UI4ME_ENDPOINT')
    with pytest.raises(RuntimeError, match='ui4me-run'):
        ui.app('Outside host')


def test_manifest_safe_escaping(tmp_path):
    from ui4me.launcher import build_manifest
    p = tmp_path / 'my file.py'
    p.write_text('pass', encoding='utf8')
    manifest = build_manifest(p, program='/opt/python', app_id='org.example.Test',title='Hello "UI"')
    assert 'org.example.Test' in manifest
    assert 'my file.py' in manifest
    assert 'Hello \\"UI\\"' in manifest
    with pytest.raises(ValueError):
        build_manifest(p, program='python', app_id='bad\n[host]', title='X')


def test_closing_window_waits_for_actual_native_closed_event(fake_core):
    from ui4me import ui
    with ui.app('Close policy') as app:
        ui.text('Remain mounted until host confirms closure')
    high = app.main
    native = high.core.native
    high.close()  # requests graceful close; cannot assume it was accepted
    assert not high.closed
    assert native.closed  # fake Core records the request, not an event
    # Core's window.event first retires Core handles, then high-level disposal
    app.core.native.rpc.callbacks['window.event']({'window_id':native.id, 'type':'closed'})
    app.core.post(app.stop)
    app.run()
    assert high.closed


def test_close_request_handlers_run_once_per_request(fake_core):
    """Regression: Core sends both the window.before_close request and an informational
    window.event close_requested; handlers must run once (found on KWin, 2026-11-13)."""
    from ui4me import ui
    with ui.app('Once') as app:
        ui.text('x')
    calls = []
    app.main.on_close_request(lambda: calls.append(1) or False)
    native = app.main.core.native
    results = []

    def user_close():
        native.app.rpc.callbacks['window.event']({'window_id': native.id, 'type': 'close_requested'})
        results.append(native.policy())  # Core's lifecycle worker asks the policy
        app.core.post(app.stop)
    threading.Thread(target=user_close).start()
    app.run()
    assert calls == [1]
    assert results == [False]


def test_dropped_files_window_event_reaches_file_drop_listeners(fake_core):
    from ui4me import ui
    with ui.app('Drop') as app:
        ui.text('x')
    seen = []
    app.main.on('file_drop', lambda e: seen.append(e.get('paths')))
    native = app.main.core.native
    native.app.rpc.callbacks['window.event']({'window_id': native.id, 'type': 'dropped_files',
                                              'data': {'paths': ['/tmp/a.txt']}})
    app.core.post(app.stop)
    app.run()
    assert seen == [['/tmp/a.txt']]


def test_adapter_document_is_the_current_generation(fake_core):
    from ui4me import ui
    with ui.app('Gen') as app:
        ui.text('x')
    native = app.main.core.native
    first = app.main.core.document
    native.document = FakeDoc('<p>new</p>')
    assert app.main.core.document is native.document is not first
    native.document = None
    with pytest.raises(RuntimeError):
        app.main.core.document
    app.close()


def test_on_close_runs_once_when_app_ends_before_closed_event(fake_core):
    """Regression: the host's app.shutdown can overtake the queued window `closed` event;
    the main window's on_close must still run exactly once (found on KWin, 2026-11-13)."""
    from ui4me import ui
    with ui.app('Ending') as app:
        ui.text('x')
    calls = []
    app.main.on_close(lambda: calls.append('main'))
    native = app.main.core.native
    # stop() → shutdown; then the late `closed` notification still arrives.
    app.core.post(app.stop)
    app.run()
    native.app.rpc.callbacks['window.event']({'window_id': native.id, 'type': 'closed'})
    assert calls == ['main']


def test_callbacks_queued_before_shutdown_still_run(fake_core):
    from ui4me import ui
    with ui.app('Drain') as app:
        ui.text('x')
    seen = []

    def finish():
        app.core.native.rpc.shutdown_requested.set()
        app.core.post(lambda: seen.append('late-but-queued'))
    app.core.post(finish)
    app.run()
    assert seen == ['late-but-queued']


def test_close_policy_is_answered_when_post_queue_is_full(fake_core):
    """Regression: under a post flood the bounded owner queue was full, so the close
    policy's post raised and every user close was vetoed (found on Windows, 2026-11-13)."""
    from ui4me import ui
    from ui4me._ui.errors import UiBusyError
    with ui.app('Flood') as app:
        ui.text('x')
    app.main.on_close_request(lambda: True)
    native = app.main.core.native
    filled = 0
    with pytest.raises(UiBusyError):
        for _ in range(10_000):
            app.post(lambda: None)
            filled += 1
    assert 500 <= filled <= 512  # the initial commit flush may already be queued
    answers = []

    def user_close():
        answers.append(native.policy())
        app.core.post(app.stop, priority=True)
    threading.Thread(target=user_close).start()
    app.run()
    assert answers == [True]


def test_raw_document_replacement_stops_management(fake_core):
    """Core 1.0 generations: after a raw load_html the old ids are gone; UI4ME must not
    patch the new document and must release its components (reported once)."""
    from ui4me import ui
    with ui.app('Gen') as app:
        count = ui.state(0)
        label = ui.text(lambda: str(count.value))
    errors = []
    app.on_error(lambda e, ctx: errors.append(ctx))
    native = app.main.core.native
    replacement = FakeDoc('<p>raw</p>')
    replacement.id = 'doc-2'
    native.document = replacement
    count.set(1)
    app.scheduler.flush()
    app.main.commit()
    assert replacement.batches == []
    assert label.disposed
    assert errors == ['document generation']
    app.close()


def test_settings_persist_atomically_and_survive_corruption(fake_core, tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setenv('APPDATA', str(tmp_path))
    from ui4me import ui
    with ui.app('Settings Demo') as app:
        ui.text('x')
    assert app.app_id == 'org.ui4me.app.settings-demo'
    theme = app.settings.state('theme', 'system')
    assert theme.peek() == 'system' and 'theme' not in app.settings
    theme.set('dark')
    app.scheduler.flush()
    app.settings.set('recent', ['a.txt', 'b.txt'])
    stored = json.loads(app.settings.path.read_text(encoding='utf-8'))
    assert stored == {'theme': 'dark', 'recent': ['a.txt', 'b.txt']}
    with pytest.raises(Exception):
        app.settings.set('bad', object())
    app.close()
    app.settings.path.write_text('{not json', encoding='utf-8')
    with ui.app('Settings Demo') as again:
        ui.text('x')
    errors = []
    again.on_error(lambda e, ctx: errors.append(ctx))
    assert again.settings.get('theme', 'fallback') == 'fallback'
    assert app.settings.path.with_name('settings.json.corrupt').exists()
    assert errors and errors[0].startswith('settings')
    again.close()


def test_vetoed_programmatic_close_keeps_events_working(fake_core):
    """Review finding: Window.close() dropped every document subscription before the
    (vetoable) close request, so a vetoed window stayed open with dead controls."""
    from ui4me import ui
    with ui.app('Veto') as app:
        clicks = ui.state(0)
        button = ui.button('b', on_click=lambda: clicks.set(clicks.value + 1))
    app.main.on_close_request(lambda: False)
    native = app.main.core.native
    doc = native.document
    app.main.close()                      # request only; the policy vetoes
    assert native.policy() is False
    for element, fn in doc.listeners['click']:
        fn({'type': 'click', 'element': button.id, 'path': [button.id]})
    app.core.post(app.stop)
    app.run()
    assert clicks.peek() == 1


def test_core_events_are_not_dropped_when_user_posts_fill_the_queue(fake_core):
    """Review finding: events and `closed` notifications went through the bounded user
    queue and were silently dropped under a post flood."""
    from ui4me import ui
    from ui4me._ui.errors import UiBusyError
    with ui.app('Flood') as app:
        clicks = ui.state(0)
        button = ui.button('b', on_click=lambda: clicks.set(clicks.value + 1))
    closed = []
    app.main.on_close(lambda: closed.append(1))
    with pytest.raises(UiBusyError):
        for _ in range(1000):
            app.post(lambda: None)
    native = app.main.core.native
    for element, fn in native.document.listeners['click']:
        fn({'type': 'click', 'element': button.id, 'path': [button.id]})
    native.app.rpc.callbacks['window.event']({'window_id': native.id, 'type': 'closed'})
    app.core.post(app.stop, priority=True)
    app.run()
    assert clicks.peek() == 1
    assert closed == [1]


def test_one_shot_timers_are_released_and_settings_remove_none(fake_core, tmp_path, monkeypatch):
    import time as _time
    from ui4me import ui
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.setenv('APPDATA', str(tmp_path))
    with ui.app('Timers') as app:
        ui.text('x')
    fired = []
    app.after(0.01, lambda: fired.append(1))
    deadline = _time.monotonic() + 2
    while not fired and _time.monotonic() < deadline:
        _time.sleep(0.02)
        app.core._drain(0.05)
    assert fired == [1]
    assert app.core.stats()['timers'] == 0
    app.settings.set('k', None)
    app.settings.remove('k')
    assert 'k' not in app.settings and json.loads(app.settings.path.read_text()) == {}
    app.close()
