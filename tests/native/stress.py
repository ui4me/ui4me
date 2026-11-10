"""Exercise native lifecycle, bounded queues and cancellation in one process.

Run with the installed candidate on a real Linux or Windows desktop.
"""
import json, threading, time
from ui4me import App, build_info

observed={}
def watchdog(_event):
    raise AssertionError('Native stress probe timed out')
# Fill a bounded queue before entering the loop. Admission must not block and
# stop must remain available even while all ordinary slots are occupied.
with App(handle_sigint=False) as app:
    app.open('<p>Queue saturation</p>')
    accepted=[app.post(lambda: 1) for _ in range(512)]
    rejected=app.post(lambda: 2)
    assert rejected.done() and rejected.exception() is not None
    app.stop(); app.run()
    stats=app.stats()
    assert all(f.done() and f.cancelled() for f in accepted)
    assert stats['pending_posts']==0 and stats['windows']==0 and stats['timers']==0, stats
    observed['queue_full_stop']={'accepted':len(accepted),'cancelled':sum(f.cancelled() for f in accepted),'rejected':type(rejected.exception()).__name__,'stats':stats}

# A running callback cannot be cancelled; a queued callback can. A worker
# signals stop while the owner is inside the callback, then releases it.
entered=threading.Event(); release=threading.Event(); worker_result={}; worker_errors=[]
with App(handle_sigint=False) as app:
    app.open('<p>Running cancellation</p>')
    def running():
        entered.set()
        if not release.wait(5): raise AssertionError('worker did not release running callback')
        return 7
    active=app.post(running)
    queued=app.post(lambda: (_ for _ in ()).throw(AssertionError('cancelled callback ran')))
    def worker():
        try:
            if not entered.wait(5):
                raise AssertionError('running callback did not start')
            worker_result['cancel_running']=active.cancel()
            worker_result['cancel_queued']=queued.cancel()
        except BaseException as error:
            worker_errors.append(error)
        finally:
            try:
                app.stop()
            except BaseException as error:
                worker_errors.append(error)
            release.set()
    app.timer(10000, watchdog)
    thread=threading.Thread(target=worker, daemon=True); thread.start()
    try: app.run()
    finally: release.set(); thread.join(5)
    assert not thread.is_alive()
    if worker_errors:
        raise AssertionError('worker assertion failed') from worker_errors[0]
    assert worker_result=={'cancel_running':False,'cancel_queued':True},worker_result
    assert active.result()==7 and queued.cancelled()
    observed['running_queued_cancellation']={**worker_result,'running_result':active.result(),'queued_cancelled':queued.cancelled(),'stats':app.stats()}

# A producer that outlives a stopped session must not enqueue into a later one.
ready=threading.Event(); deliver=threading.Event(); late={}; late_errors=[]
with App(handle_sigint=False) as old:
    oldwin=old.open('<p id="state">old</p>')
    def producer():
        try:
            ready.set()
            if not deliver.wait(5):
                raise AssertionError('late producer was not released')
            late['future']=old.post(lambda: oldwin.set_text('state','bad'))
        except BaseException as error:
            late_errors.append(error)
    thread=threading.Thread(target=producer, daemon=True); thread.start(); assert ready.wait(5)
    old.on('started',lambda _: old.stop()); old.timer(10000,watchdog); old.run()
with App(handle_sigint=False) as new:
    newwin=new.open('<input id="state" value="new">')
    def started(_):
        deliver.set(); thread.join(5)
        assert not thread.is_alive()
        if late_errors:
            raise AssertionError('late producer failed') from late_errors[0]
        assert late['future'].done() and isinstance(late['future'].exception(),RuntimeError)
        assert newwin.get_value('state')=='new'
        try: oldwin.set_text('state','late'); raise AssertionError('stale mutation accepted')
        except RuntimeError: pass
        new.stop()
    new.on('started',started); new.timer(10000,watchdog); new.run()
    observed['late_session']={'late_rejected':True,'new_window_value':'new','stats':new.stats()}

# Sessions run serially on one owner; count idle loop turns over a monotonic
# timer interval and ensure state counts return to zero after every stop.
turns=[]
for _ in range(10):
    with App(handle_sigint=False) as app:
        app.open('<p>Idle</p>')
        start=time.monotonic()
        app.timer(10000,watchdog)
        app.timer(200,lambda _:app.stop())
        app.run()
        elapsed=time.monotonic()-start; stats=app.stats()
        assert stats['windows']==0 and stats['timers']==0 and stats['pending_posts']==0,stats
        assert elapsed >= .15 and stats['loop_turns'] < 500, (elapsed,stats)
        turns.append({'elapsed':round(elapsed,3),'turns':stats['loop_turns'],'waits':stats['wait_requests']})
observed['repeated_idle_sessions']=turns
print(json.dumps({'build_info':build_info(),'observations':observed},indent=2))
