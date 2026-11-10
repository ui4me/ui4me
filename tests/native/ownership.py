"""Verify owner-thread dispatch and error recovery in native sessions.

Run with an installed ui4me package and an available native display.
"""

import json
import threading

from ui4me import App, build_info


def timeout(_event):
    raise AssertionError("Native ownership probe timed out")


observed = []
worker_errors = []
owner = threading.get_ident()
worker_thread = None
with App(handle_sigint=False) as app:
    window = app.open('<p id="status">Owner test</p>')

    def begin(_event):
        global worker_thread
        try:
            app.run()
            raise AssertionError('nested run accepted')
        except RuntimeError:
            observed.append('nested-run-rejected')
        future = app.post(lambda: observed.append('owner-post-dispatched'))
        try:
            future.result()
            raise AssertionError('owner blocked on pending future')
        except RuntimeError:
            observed.append('owner-wait-rejected')
        assert not future.done(), 'post executed before callback returned'
        observed.append('deferred')

        def worker():
            try:
                try:
                    window.set_text('status', 'wrong thread')
                    raise AssertionError('wrong-thread mutation accepted')
                except RuntimeError:
                    observed.append('wrong-thread-rejected')
            except BaseException as error:
                worker_errors.append(error)
            finally:
                def complete():
                    observed.append('worker-post-owner' if threading.get_ident() == owner else 'worker-post-wrong-thread')
                    app.stop()
                app.post(complete)

        # A hung foreign call must not keep the test process alive after the watchdog.
        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

    app.on('started', begin)
    app.timer(10000, timeout)
    app.run()
    if worker_thread is not None:
        worker_thread.join(5)
        assert not worker_thread.is_alive(), 'worker failed to terminate'
    if worker_errors:
        raise AssertionError('worker assertion failed') from worker_errors[0]

assert set(observed) == {'nested-run-rejected', 'owner-wait-rejected', 'deferred', 'wrong-thread-rejected', 'owner-post-dispatched', 'worker-post-owner'}, observed
assert observed.index('deferred') < observed.index('owner-post-dispatched')
try:
    with App(handle_sigint=False) as app:
        app.open('<p>Callback failure</p>')
        def fail(_event):
            raise ValueError('deliberate callback failure')
        app.on('started', fail)
        app.timer(10000, timeout)
        app.run()
    raise AssertionError('callback failure was not propagated')
except ValueError as error:
    assert str(error) == 'deliberate callback failure', str(error)
    observed.append('callback-failure-propagated')
with App(handle_sigint=False) as app:
    app.open('<p>Session after callback failure</p>')
    app.on('started', lambda _: (observed.append('session-after-failure'), app.stop()))
    app.timer(10000, timeout)
    app.run()
assert 'session-after-failure' in observed
print(json.dumps({'build_info': build_info(), 'checks': observed}, indent=2))
