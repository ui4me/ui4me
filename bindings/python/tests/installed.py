"""Run outside the source tree against an installed wheel. Native results need human review."""
import argparse
import gc
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

import ui4me
from ui4me import App, Ui4meError, build_info


FORM = '''<h1>ui4me native acceptance</h1>
<input id="name" value="Edit me">
<button id="echo">Echo typed value</button>
<button id="second">Open another window</button>
<button id="resize">Resize this window</button>
<button id="allow">Allow normal close</button>
<button id="worker">Post from a worker thread</button>
<button id="bounds">Exercise timer capacity</button>
<button id="race">Queue work then force stop</button>
<button id="error">Raise a callback error</button>
<button id="stop">Force stop</button>
<p id="status">Normal close initially vetoed. Use Allow or Force stop.</p>'''


def installed_cases():
    cases = []
    def check(identifier, action, description):
        try:
            action()
            cases.append({"id": identifier, "status": "passed", "details": description})
        except BaseException as error:
            cases.append({"id": identifier, "status": "failed", "details": f"{type(error).__name__}: {error}"})

    def install_load():
        if os.environ.get("UI4ME_NATIVE_LIB"):
            raise AssertionError("Installed consumers must not use UI4ME_NATIVE_LIB")
        info = build_info()
        package = Path(ui4me.__file__).resolve().parent
        if not Path(info["library_path"]).resolve().is_relative_to(package):
            raise AssertionError("Native library is not inside the installed package")
        with App(backend="headless", handle_sigint=False) as app:
            app.on("started", lambda _: app.stop())
            app.run()

    def abi_lifetime():
        assert build_info()["abi"] == 1
        seen = []
        with App(backend="headless", handle_sigint=False) as app:
            app.on("started", lambda _: (seen.append("started"), app.stop()))
            gc.collect()
            app.run()
        assert seen == ["started"]

        # The first closed window is no longer a valid native target while the
        # second remains alive. Exercise both the native stale status and token
        # identity rather than merely checking that callbacks survive GC.
        with App(backend="headless", handle_sigint=False) as app:
            first = app.open('<p id="value">first</p>')
            second = app.open('<p id="value">second</p>')
            removed = app.on("closed", lambda _: seen.append("removed"))
            removed.close()
            app.on("started", lambda _: first.close())
            def closed(event):
                if event["window"] == first.id:
                    try:
                        first.get_value("value")
                    except Ui4meError as error:
                        assert error.code == 4
                    else:
                        raise AssertionError("Native accepted a closed window ID")
                    assert second.get_value("value") == "second"
                    seen.append("closed")
                    app.stop()
            app.on("closed", closed)
            app.run()
        assert seen == ["started", "closed"]

        def fail(_):
            raise LookupError("installed callback failure")
        with App(backend="headless", handle_sigint=False) as app:
            app.on("started", fail)
            try:
                app.run()
            except LookupError as error:
                assert str(error) == "installed callback failure"
            else:
                raise AssertionError("Callback exception was not propagated")
        # A failure must still release the native session for reuse.
        with App(backend="headless", handle_sigint=False) as app:
            app.on("started", lambda _: app.stop())
            app.run()

    def resource_diagnostics():
        resource = files("ui4me").joinpath("resources/demo.html").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="ui4me space ž ") as directory:
            target = Path(directory) / "form ü.html"
            target.write_text(resource, encoding="utf-8")
            with App(backend="headless", handle_sigint=False) as app:
                window = app.open_file(target)
                assert window.get_value("name") == "World"
                try:
                    app.open_file(target.with_name("missing.html"))
                except FileNotFoundError:
                    pass
                else:
                    raise AssertionError("Missing resource was accepted")
        assert build_info()["source_id"]

    def candidate_identity():
        info = build_info()
        assert ui4me.__version__ == "0.1.0" == info["version"]
        assert info["source_id"] and Path(info["library_path"]).is_file()
        # A second session proves local disposal/recreate; public upgrade is a separate release check.
        for _ in range(2):
            with App(backend="headless", handle_sigint=False) as app:
                app.on("started", lambda _: app.stop())
                app.run()

    check("F01", install_load, "Installed package resolves its own native payload; headless session completes")
    check("F09", abi_lifetime, "ABI 1, callback lifetime, failure propagation, stale windows and subscription removal")
    check("F11", resource_diagnostics, "Explicit Unicode/space resource path and source diagnostics")
    check("F12", candidate_identity, "Local candidate identity and fresh session; public upgrade not assessed by this probe")
    return cases


def native_session(args, number, observations):
    errors = []
    posts = []
    state = {"allow_close": False}
    owner = threading.get_ident()
    with App() as app:
        window = app.open(FORM, title=f"ui4me native acceptance — session {number}", width=760, height=740)
        def record(event):
            if len(observations) < 4096:
                observations.append({"session": number, "time_monotonic": time.monotonic(), **event})
        for event_type in ("started", "stopped", "resized", "closed", "change", "click"):
            app.on(event_type, record)
        def close_requested(event):
            record({**event, "veto": not state["allow_close"]})
            if not state["allow_close"]:
                window.set_text("status", "Close vetoed. Click Allow normal close, or Force stop.")
                return False
        window.on("close_requested", close_requested)
        window.on("click", lambda _: window.set_text("status", window.get_value("name")), element="echo")
        window.on("click", lambda _: app.open('<p>Second window. Close me independently.</p>', title="Second window"), element="second")
        window.on("click", lambda _: window.resize(860, 780), element="resize")
        def allow(_):
            state["allow_close"] = True
            window.set_text("status", "Normal close is now allowed")
        window.on("click", allow, element="allow")
        def worker(_):
            def work():
                posts.append(app.post(lambda: (record({"type": "worker_dispatch", "owner_correct": threading.get_ident() == owner}), window.set_text("status", "Worker result delivered on UI owner"))))
            threading.Thread(target=work, name="acceptance-worker", daemon=True).start()
        window.on("click", worker, element="worker")
        def bounds(_):
            registrations = []
            rejected = False
            try:
                for _ in range(129):
                    registrations.append(app.timer(60000, lambda _: None))
            except Exception as error:
                rejected = True
                record({"type": "capacity_rejected", "registered": len(registrations), "error": str(error)})
            finally:
                for registration in registrations:
                    registration.cancel()
            window.set_text("status", "Timer capacity rejection observed" if rejected else "ERROR: capacity not rejected")
        window.on("click", bounds, element="bounds")
        def race(_):
            posts.extend(app.post(lambda: record({"type": "queued_work_ran"})) for _ in range(32))
            app.stop()
        window.on("click", race, element="race")
        def fail(_):
            raise RuntimeError("Deliberate native callback failure")
        window.on("click", fail, element="error")
        window.on("click", lambda _: app.stop(), element="stop")
        def sample(_):
            record({"type": "runtime_stats", "stats": app.stats()})
            if args.capture:
                capture = str(Path(args.capture).with_name(Path(args.capture).stem + f"-{number}.png"))
                record({"type": "renderer_snapshot", "path": capture, "native_capture": False, "result": window.snapshot(capture)})
        app.timer(1000, sample)
        try:
            app.run()
        except RuntimeError as error:
            if "Deliberate native callback failure" not in str(error):
                raise
            errors.append(str(error))
        observations.append({"session": number, "type": "terminal_stats", "stats": app.stats()})
    observations.append({"session": number, "type": "terminal_posts", "total": len(posts), "settled": sum(p.done() for p in posts), "cancelled": sum(p.cancelled() for p in posts), "callback_errors": errors})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--capture")
    parser.add_argument("--scenario", choices=("all", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F10"), default="all")
    args = parser.parse_args()
    result = {"binding": "python", "backend": "native" if args.native else "headless", "build_info": {}, "cases": [], "observations": []}
    failed = False
    try:
        result["build_info"] = build_info()
        if args.native:
            print("Interact with the labeled controls. Close session 1 to open session 2. Record native screenshots externally.")
            print("This probe records observations only. A human must assess F02-F08/F10; a renderer snapshot is not desktop evidence.")
            for number in range(1, 3 if args.scenario in ("all", "F08") else 2):
                native_session(args, number, result["observations"])
            result["manual_review_required"] = True
            result["native_capture"] = False
        else:
            result["cases"] = installed_cases()
            failed = any(case["status"] != "passed" for case in result["cases"])
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        failed = True
    finally:
        target = Path(args.result)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
