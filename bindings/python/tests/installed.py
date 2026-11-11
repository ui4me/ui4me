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
from ui4me import App, build_info


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
        # second remains alive. The binding must mark closed before callbacks;
        # the external C consumer separately checks native stale status codes.
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
                    except RuntimeError:
                        assert first.closed
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
        with tempfile.TemporaryDirectory(prefix="ui4me space ž ") as directory:
            for resource in files("ui4me").joinpath("resources").iterdir():
                if resource.is_file():
                    (Path(directory) / resource.name).write_bytes(resource.read_bytes())
            target = Path(directory) / "form ü.html"
            (Path(directory) / "index.html").rename(target)
            with App(backend="headless", handle_sigint=False) as app:
                window = app.open_file(target)
                assert window.get_value("name") == "Příliš žluťoučký kůň"
                try:
                    app.open_file(target.with_name("missing.html"))
                except FileNotFoundError:
                    pass
                else:
                    raise AssertionError("Missing resource was accepted")
                probe_file = Path(directory) / "assets ü.html"
                probe_file.write_text('''<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body>
<div id="paint" style="width:120px;height:120px;padding:0"></div>
<img id="asset" width="28" height="28" style="position:absolute;left:8px;top:8px;width:28px;height:28px">
</body></html>''', encoding="utf-8")
                probe = app.open_file(probe_file, width=160, height=160)
                capture = Path(directory) / "assets.png"
                probe.snapshot(capture)
                state = {"phase": "css", "previous": capture.read_bytes()}
                probe.add_class("paint", "sidebar")
                def sample(_):
                    probe.snapshot(capture)
                    pixels = capture.read_bytes()
                    if pixels == state["previous"]:
                        return
                    state["previous"] = pixels
                    if state["phase"] == "css":
                        state["phase"] = "image"
                        probe.set_attribute("asset", "src", "icon.png")
                    else:
                        assert not any(item.get("stage") == "resource" for item in probe.diagnostics()["diagnostics"])
                        state["phase"] = "done"
                        app.stop()
                def timeout(_):
                    raise AssertionError("Local stylesheet/image did not change rendered pixels: " + state["phase"])
                app.timer(10, sample, repeat=True)
                app.timer(3000, timeout)
                app.run()
                assert state["phase"] == "done"
        assert build_info()["source_id"]

    def candidate_identity():
        info = build_info()
        assert ui4me.__version__ == info["binding_version"] == info["version"]
        assert info["source_id"] and Path(info["library_path"]).is_file()
        # A second session proves local disposal/recreate; public upgrade is a separate release check.
        for _ in range(2):
            with App(backend="headless", handle_sigint=False) as app:
                app.on("started", lambda _: app.stop())
                app.run()

    def core_03_contract():
        page = ('<style>body{margin:0}.r{height:30px}</style><div id="log" style="height:100px;overflow:auto">'
                '<div id="r0" class="r">Příliš</div></div><form id="f"><textarea id="t"></textarea></form>')
        with App(backend="headless", handle_sigint=False) as app:
            window = app.open(page, width=400, height=300)
            window.set_scroll_follow("log")
            for i in range(1, 8):
                window.batch([{"op": "insert_html", "element": "log", "position": "beforeend", "html": f'<div id="r{i}" class="r">{i}</div>'},
                              {"op": "trim_children", "element": "log", "keep": 6}])
            assert window.query("#log > div") == [f"r{i}" for i in range(2, 8)]
            scroll = window.get_scroll("log")
            assert scroll["y"] == scroll["max_y"] == 80.0, scroll
            window.scroll_into_view("r2", block="start")
            assert window.get_rect("r2")["y"] == 0.0
            window.move_element("r7", "r2", "beforebegin")
            window.append_text("r7", " ✓")
            assert window.get_text("r7") == "7 ✓" and window.get_attribute("r7", "class") == "r"
            window.select_text("r7")
            assert window.copy_selection() == "7 ✓" == window.get_clipboard_text()
            window.set_default_action("f", "keydown", key="Enter", shift=False)
            try:
                window.batch([{"op": "remove_element", "element": "r3"}, {"op": "remove_element", "element": "missing"}])
            except ui4me.Ui4meError as error:
                assert "batch operation 1" in str(error)
            else:
                raise AssertionError("invalid batch accepted")
            assert window.has_element("r3")
            app.on("started", lambda _: app.stop())
            app.run()

    def core_04_contract():
        results = []
        with App(backend="headless", handle_sigint=False) as app:
            window = app.open('<button id="b">Open</button><dialog id="d"><select id="s"><option value="a">A</option><option value="b">B</option></select></dialog>')
            window.show_dialog("d")
            assert window.get_dialog("d") == {"open": True, "modal": True, "return_value": ""}
            assert window.query(":focus") == ["s"]
            window.set_value("s", "b")
            assert [o["selected"] for o in window.get_options("s")] == [False, True]
            window.close_dialog("d", "ok")
            assert window.maximize()["applied"] and window.state()["maximized"] is True
            window.set_constraints(min_size=(400, 300))
            window.resize(200, 200)
            assert (window.state()["width"], window.state()["height"]) == (400.0, 300.0)
            window.open_file_dialog(results.append, title="Pick", filters={"Text": ["txt"]})
            app.timer(50, lambda _: app.stop())
            app.run()
        assert results == [{"paths": None}], results

    def core_05_contract():
        with App(backend="headless", handle_sigint=False) as app:
            caps = app.capabilities()
            focus = caps["features"]["window.focus"]
            assert caps["backend"] == "headless" and focus["status"] == "unavailable" and focus["reason"], caps
            assert all(f["status"] == "supported" or f.get("reason") for f in caps["features"].values())
            window = app.open('<style>#b{width:10px;height:5px}@media (prefers-color-scheme: dark){#b{width:20px}}</style><div id=b></div><textarea id=t>ab\ncd</textarea>')
            env = window.set_environment(color_scheme="dark")
            assert (env["color_scheme"], env["color_scheme_source"]) == ("dark", "app"), env
            assert window.get_rect("b")["width"] == 20
            window.focus("t")
            field = next(n for n in window.accessibility_tree()["nodes"] if n.get("html_id") == "t")
            assert len(field["children"]) == 2 and field["selection"] == {"value": [5, 5]}, field
            app.on("started", lambda _: app.stop())
            app.run()

    check("F01", install_load, "Installed package resolves its own native payload; headless session completes")
    check("F09", abi_lifetime, "ABI 1, callback lifetime, failure propagation, stale windows and subscription removal")
    check("F11", resource_diagnostics, "Unicode/space document root; packaged CSS and asynchronous PNG change actual rendered pixels; resource diagnostics stay clear")
    check("F12", candidate_identity, "Local candidate identity and fresh session; public upgrade not assessed by this probe")
    check("F14", core_04_contract, "0.4 Core contract: modal dialog focus/select/return, window actions and size constraints, headless file dialog completion")
    check("F15", core_05_contract, "0.5 Core contract: capability report with causes, media environment override, per-line accessible text with the caret")
    check("F13", core_03_contract, "0.3 Core contract: batch/trim, follow scroll, into-view geometry, move/append/read, selection copy, clipboard, default-action rule")
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
