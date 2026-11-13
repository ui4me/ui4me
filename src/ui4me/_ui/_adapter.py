"""UI4ME Core 1.0 host adapter for the UI4ME 2.0 component engine.

This translates the former in-process UI interface to the *published*
``ui4me_core`` document/window API.  No native renderer, protocol or second
window host is shipped.  The adapter owns an explicit owner-thread dispatch
queue because Core 1.0 delivers document notifications on a worker thread.

Only methods supported by Core 1.0 are implemented.  Unsupported legacy desktop
services fail visibly instead of presenting false capability claims.
"""
from __future__ import annotations

import collections
import concurrent.futures
import os
import queue
import threading
from typing import Any, Callable


def unsupported(name: str) -> None:
    raise NotImplementedError(
        f"{name} is not exposed by the UI4ME Core 1.0.0 Python host API. "
        "Use an in-window UI or add this service through a separately reviewed Core change."
    )


class _Timer:
    def __init__(self, app: 'App', milliseconds: int, callback: Callable, repeat: bool):
        self._app, self._callback, self._repeat = app, callback, repeat
        self._seconds = max(0.001, milliseconds / 1000.0)
        self._lock = threading.Lock()
        self._cancelled = False
        self._timer = None
        self._schedule()

    def _schedule(self):
        with self._lock:
            if self._cancelled or self._app.closed:
                return
            self._timer = threading.Timer(self._seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            if self._cancelled or self._app.closed:
                return
        def deliver():
            if not self._cancelled and not self._app.closed:
                self._callback({'type': 'timer'})
        try:
            self._app.post(deliver, internal=True)
        except RuntimeError:
            pass
        if self._repeat:
            self._schedule()
        else:
            self._app._timers.discard(self)

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._timer is not None:
                self._timer.cancel()
        self._app._timers.discard(self)


class _Task:
    def __init__(self):
        self.state = 'pending'
        self.cancelled = False
        self._lock = threading.Lock()
        self._future = None
    def cancel(self):
        with self._lock:
            self.cancelled = True
            if self._future is None:
                self.state = 'cancelled'
                return True
            if self._future.cancel():
                self.state = 'cancelled'
                return True
            return self.state == 'running'


class App:
    """UI-owner-thread bridge around ``ui4me_core.Application``."""
    # Core 1.0 window.event type -> UI4ME window event name
    _WINDOW_EVENT_NAMES = {'dropped_files': 'file_drop', 'dropped_text': 'text_drop'}
    def __init__(self, *, backend: str = 'native', app_id: str = 'org.ui4me.ui', handle_sigint: bool = True):
        if backend != 'native':
            raise RuntimeError('Core 1.0 has no public headless App backend; run actual native host tests')
        from ui4me_core import Application
        if not os.environ.get('UI4ME_ENDPOINT') or not os.environ.get('UI4ME_TOKEN'):
            raise RuntimeError(
                'UI4ME applications must be started by the native host. '
                'Use `ui4me-run your_app.py` or `ui4me-host run --app app.toml`; '
                'do not directly invoke `python your_app.py`.')
        self.native = Application.from_environment()
        self.owner = threading.get_ident()
        self.app_id = app_id
        self.closed = False
        # Owner-thread work. Normal posts are bounded (MAX_POSTS); lifecycle decisions
        # (close/quit policy) use an unbounded priority lane so a flooded queue can
        # never veto a user's close request.
        self._queue: queue.Queue = queue.Queue()
        self._priority: collections.deque = collections.deque()
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._windows: dict[str, Window] = {}
        self._events: dict[str, list[Callable]] = {}
        self._timers: set[_Timer] = set()
        self._workers = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='ui4me-ui')
        self._tasks: set[_Task] = set()
        self._install_native_events()

    def _install_native_events(self):
        original_window = getattr(self.native, '_window_event', None)
        if original_window is None:
            raise RuntimeError(
                'UI4ME Core 1.0 window events changed: the UI bridge needs a public '
                'window-event subscription API; see docs/CORE_HANDOFF_2.md')
        def relay(event):
            original_window(event)  # keep Core's generational state and stale-reference protection
            win = self._windows.get(event.get('window_id'))
            if win is None:
                return
            kind = self._WINDOW_EVENT_NAMES.get(event.get('type', ''), event.get('type', ''))
            if kind == 'close_requested':
                # Close decisions are answered by the window.before_close policy
                # request; the informational notification must not run the
                # application's close handlers a second time.
                return
            if kind == 'closed':
                self._windows.pop(win.id, None)
            data = event.get('data') if isinstance(event.get('data'), dict) else {}
            flat = {**data, **event, 'type': kind}  # e.g. event['paths'] for file_drop
            self._post_safely(lambda w=win, k=kind, e=flat: w._notify(k, e))
        self.native.rpc.on_notification('window.event', relay)
        def shutdown(event):
            for callback in self._events.get('stopped', ()): 
                self._post_safely(lambda cb=callback: cb({'type': 'stopped'}))
        self.native.rpc.on_notification('app.shutdown', shutdown)

    def _post_safely(self, fn):
        """Deliver a Core/internal callback to the owner thread (dropped only after close)."""
        try:
            self.post(fn, internal=True)
        except RuntimeError:
            pass  # dispatcher closed: the application has ended

    def on(self, name, fn):
        self._events.setdefault(name, []).append(fn)
        return lambda: self._events.get(name, []).remove(fn) if fn in self._events.get(name, []) else None

    def open(self, html: str, *, title: str, width: int, height: int, base_path=None):
        w = self.native.open_html(html, title=title, width=width, height=height, asset_root=base_path)
        result = Window(self, w)
        self._windows[w.id] = result
        return result

    MAX_POSTS = 512

    def post(self, callback, *, priority: bool = False, internal: bool = False):
        """Queue ``callback`` for the UI owner thread.

        User posts are bounded (MAX_POSTS). ``internal`` items — events, timers, task
        and dialog completions coming from Core or UI4ME itself — are never refused,
        so a flooding producer cannot make the UI lose clicks or ``closed`` events.
        ``priority`` items (close/quit decisions) run before anything queued.
        """
        if self.closed:
            raise RuntimeError('UI owner dispatcher is closed')
        result = concurrent.futures.Future()
        if priority:
            self._priority.append((callback, result, False))
            self._queue.put_nowait(None)  # wake the owner loop
            return result
        if not internal:
            with self._pending_lock:
                if self._pending >= self.MAX_POSTS:
                    raise RuntimeError(f'UI owner queue full ({self.MAX_POSTS} pending)')
                self._pending += 1
        self._queue.put_nowait((callback, result, not internal))
        return result

    def _next(self, timeout: float):
        """Next owner-thread item: priority lane first, then posts in order."""
        if self._priority:
            return self._priority.popleft()
        item = self._queue.get(timeout=timeout)
        if item is None:
            return self._priority.popleft() if self._priority else None
        if item[2]:
            with self._pending_lock:
                self._pending -= 1
        return item

    @staticmethod
    def _execute(item) -> None:
        callback, future, _counted = item
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(callback())
        except BaseException as exc:
            future.set_exception(exc)

    def timer(self, milliseconds, callback, *, repeat=False):
        timer = _Timer(self, milliseconds, callback, repeat)
        self._timers.add(timer)
        return timer

    def run(self):
        # Core owns the native host event loop. The Python main thread instead
        # serializes UI mutations posted by its own host-event worker and timers.
        self.native.ready()
        while not self.closed and not self.native.rpc.shutdown_requested.is_set():
            try:
                item = self._next(0.08)
            except queue.Empty:
                if self.native.rpc.closed:
                    raise RuntimeError('UI4ME Core host disconnected unexpectedly')
                continue
            if item is not None:
                self._execute(item)
        self._drain()

    def _drain(self, seconds: float = 0.5) -> None:
        """Run callbacks that were already queued when shutdown began (bounded).

        Core delivers ``app.shutdown`` outside the ordered notification queue, so
        the final ``closed`` window events and state updates can still be queued
        here. They run once; anything posted after the deadline is cancelled.
        """
        import time
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                item = self._next(0.05)
            except queue.Empty:
                break
            if item is not None:
                self._execute(item)

    def stop(self):
        if not self.closed:
            self.native.request_quit()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for timer in list(self._timers):
            timer.cancel()
        self._workers.shutdown(wait=False, cancel_futures=True)
        self.native.close()
        while self._priority:
            self._priority.popleft()[1].cancel()
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                item[1].cancel()

    def run_in_background(self, fn, *args, pass_task=False, on_done=None, on_error=None, on_cancel=None):
        if self.closed:
            raise RuntimeError('App closed')
        task = _Task()
        self._tasks.add(task)
        def execute():
            with task._lock:
                if task.cancelled:
                    return ('cancel', None)
                task.state = 'running'
            try:
                value = fn(task, *args) if pass_task else fn(*args)
                with task._lock:
                    task.state = 'cancelled' if task.cancelled else 'done'
                    return ('cancel', None) if task.cancelled else ('done', value)
            except BaseException as exc:
                with task._lock:
                    task.state = 'error'
                return ('error', exc)
        future = self._workers.submit(execute)
        task._future = future
        def completed(f):
            self._tasks.discard(task)
            try:
                state, value = f.result() if not f.cancelled() else ('cancel', None)
            except BaseException as exc:
                state, value = 'error', exc
            callback = on_done if state == 'done' else on_error if state == 'error' else on_cancel
            if callback is not None:
                self._post_safely(lambda cb=callback,v=value,s=state: cb() if s == 'cancel' else cb(v))
        future.add_done_callback(completed)
        return task

    def capabilities(self):
        return self.native.capabilities()

    def stats(self):
        return {'pending_posts': self._pending, 'timers': len(self._timers)}

    def notify(self, *a, **kw):
        unsupported('Native system notifications')

    def set_tray(self, **kw):
        unsupported('Tray icons')

    def remove_tray(self):
        unsupported('Tray icons')

    def register_hotkey(self, *_):
        unsupported('Global hotkeys')

    def unregister_hotkey(self, *_):
        unsupported('Global hotkeys')


class Window:
    """Compatibility surface atop a generation-bound Core Window + Document.

    ``window.native`` and ``window.document`` remain available for direct Core use.
    """
    # Native window notifications (Core ``window.event``), delivered on the owner thread.
    WINDOW_EVENTS = frozenset({'closed', 'resized', 'scale_changed', 'focused', 'file_drop', 'text_drop'})

    def __init__(self, app: App, window):
        self.app, self.native = app, window
        self.id = window.id
        self.managed_document_id = window.document.id if window.document is not None else None
        self._events: dict[str, list[Callable]] = {}
        self._unsubscribers = []
        self._close_requested = False

    def on(self, event, callback, element=None):
        if event == 'close_requested':
            callbacks = self._events.setdefault(event, [])
            callbacks.append(callback)
            if not self._close_requested:
                self._close_requested = True
                def policy():
                    if self.app.closed:
                        return True
                    # Core can ask this while the owner dispatch loop is handling
                    # another UI callback. Keep a strict bound on the decision.
                    future = self.app.post(lambda: all(cb({'type': event}) is not False for cb in callbacks),
                                           priority=True)
                    try:
                        return bool(future.result(timeout=4.0))
                    except Exception:
                        return False  # fail closed; never discard unsaved changes
                self.native.on_before_close(policy)
            return lambda: callbacks.remove(callback) if callback in callbacks else None
        if event in self.WINDOW_EVENTS:
            callbacks = self._events.setdefault(event, [])
            callbacks.append(callback)
            return lambda: callbacks.remove(callback) if callback in callbacks else None
        # Other window events are received through Core's document event notifications.
        unsubscribe = self.document.on(event,
            lambda raw: self.app._post_safely(lambda e=raw: callback(e)), element=element)
        self._unsubscribers.append(unsubscribe)
        return unsubscribe

    @property
    def document(self):
        """The window's *current* Core Document (never a retired generation)."""
        document = self.native.document
        if document is None or self.native.closed:
            import ui4me_core
            raise getattr(ui4me_core, 'StaleDocumentError', RuntimeError)('This window has no live document (closed, unloaded or failed)')
        return document

    @property
    def replaced(self) -> bool:
        """True once the window shows a different document generation than UI4ME built
        (raw ``load_html``/``load_file``/``unload`` or a fatal renderer error)."""
        document = self.native.document
        return self.native.closed or document is None or document.id != self.managed_document_id

    def _notify(self, event, raw):
        for fn in list(self._events.get(event, ())):
            fn(raw)

    def batch(self, operations):
        return self.document.batch(operations)
    def set_value(self, element, value):
        return self.document.set_value(element, str(value))
    def get_value(self, element):
        return self.document.get_value(element)
    def get_checked(self, element):
        return self.document.get_checked(element)
    def set_checked(self, element, checked):
        return self.document.set_checked(element, bool(checked))
    def get_text(self, element):
        return self.document.get_text(element)
    def set_text(self, element, text):
        return self.document.set_text(element, str(text))
    def get_attribute(self, element, name):
        result = self.document.command('get_attribute', element=element, name=name)
        return result.get('value')
    def focus(self, element):
        return self.document.focus(element)
    def scroll_into_view(self, element, *, block='nearest'):
        return self.document.scroll_into_view(element, block=block)
    def set_scroll_follow(self, element, follow):
        return self.document.command('set_scroll_follow', element=element, follow=follow)
    def get_scroll(self, element=None):
        return self.document.scroll(element)
    def scroll_to(self, element, *, x=None, y=None):
        return self.document.scroll_to(element=element, x=x, y=y)
    def show_dialog(self, element, *, modal=True):
        return self.document.show_dialog(element, modal=modal)
    def close_dialog(self, element, value=''):
        return self.document.close_dialog(element, value or '')
    def set_selected_values(self, element, values):
        return self.document.set_selected_values(element, values)
    def set_default_action(self, element, event, **options):
        return self.document.prevent_default(element, event, **options)
    def add_stylesheet(self, css):
        return self.document.add_stylesheet(css)
    def replace_stylesheet(self, sheet, css):
        return self.document.replace_stylesheet(sheet, css)
    def remove_stylesheet(self, sheet):
        return self.document.remove_stylesheet(sheet)
    def set_environment(self, **kw):
        return self.document.set_environment(**kw)
    def environment(self):
        return self.document.environment()
    def get_files(self, element):
        return self.document.files(element)
    def get_clipboard_text(self):
        return self.app.native.clipboard_text()
    def set_clipboard_text(self, text):
        return self.app.native.set_clipboard_text(text)
    def query(self, selector):
        return self.document.query(selector).get('ids', [])
    def has_element(self, element):
        return bool(self.document.query('#' + element).get('ids'))
    def computed_style(self, element, prop):
        return self.document.computed_style([prop], element)
    def state(self):
        return self.native.state()
    def set_title(self, title):
        return self.native.set(title=title)
    def resize(self, width, height):
        return self.native.set(width=width, height=height)
    def close(self):
        # Graceful request: the before-close policy may veto it, so keep every
        # subscription. Core retires the document's handlers when it really closes.
        return self.native.request_close()
    def file_dialog(self, kind, done, **opts):
        opts = dict(opts)
        filters = opts.get('filters')
        if isinstance(filters, dict):
            opts['filters'] = [{'name': str(name), 'extensions': list(values)} for name, values in filters.items()]
        if 'directory' in opts and opts['directory'] is not None:
            opts['directory'] = str(opts['directory'])
        opts.pop('multiple', None)
        if kind in ('open', 'open_multiple'):
            f = self.native.open_files(multiple=kind == 'open_multiple', wait=False, **opts)
        elif kind == 'save':
            f = self.native.save_file(wait=False, **opts)
        elif kind == 'folder':
            opts.pop('filters', None)
            f = self.native.choose_folder(wait=False, **opts)
        else:
            raise ValueError(f'unknown dialog type: {kind}')
        def completed(future):
            try:
                value = future.result()
            except BaseException as exc:
                value = {'error': str(exc)}
            self.app._post_safely(lambda: done(value))
        f.add_done_callback(completed)
        return f
    def get_html(self, element=None, outer=False):
        if element is None:
            return self.document.command('get_html').get('html', '')
        return self.document.command('get_html', element=element, outer=outer).get('html', '')
    def get_rect(self, element):
        return self.document.command('get_rect', element=element).get('rect')
    def set_menu(self, _):
        unsupported('Native menu bars')
    def show_context_menu(self, *_):
        unsupported('Native context menus')
    def export_pdf(self, *_a, **_kw):
        unsupported('Native PDF export')
    def print_document(self, *_a, **_kw):
        unsupported('Native printing')
    def set_clipboard_html(self, *_a, **_kw):
        unsupported('HTML clipboard')
    def window_action(self, action):
        actions = {'minimize': {'minimized': True}, 'maximize': {'maximized': True},
                   'restore': {'minimized': False, 'maximized': False},
                   'fullscreen': {'fullscreen': True}}
        if action not in actions:
            unsupported(f'Window action {action!r}')
        return self.native.set(**actions[action])
    def snapshot(self, path):
        unsupported('Native bitmap screenshot')
