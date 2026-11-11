"""Authored contract tests. They require the real built native library; no fake engine."""
import json
import gc
from pathlib import Path
import tempfile
import threading
import time
import unittest

from ui4me import App, Ui4meError, __version__, build_info


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing native payload is a failure, not a zero-test success.
        cls.info = build_info()

    def app(self):
        return App(backend="headless", handle_sigint=False)

    def test_version_and_abi(self):
        self.assertEqual(__version__, self.info["binding_version"])
        self.assertEqual(self.info["version"], __version__)
        self.assertEqual(self.info["abi"], 1)

    def test_multiple_terminal_sessions(self):
        for _ in range(2):
            with self.app() as app:
                app.on("started", lambda _: app.stop())
                app.run()
                with self.assertRaises(RuntimeError):
                    app.run()

    def test_input_value_preserves_unicode(self):
        with self.app() as app:
            window = app.open('<input id="value" value="A">')
            window.set_text("value", "Příliš žluťoučký")
            self.assertEqual(window.get_value("value"), "Příliš žluťoučký")

    def test_explicit_file_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="ui4me ž ") as directory:
            path = Path(directory) / "form ü.html"
            path.write_text('<input id="x" value="resource">', encoding="utf-8")
            with self.app() as app:
                self.assertEqual(app.open_file(path).get_value("x"), "resource")

    def test_post_runs_once_on_owner(self):
        owner = threading.get_ident()
        seen = []
        with self.app() as app:
            future = app.post(lambda: seen.append(threading.get_ident()) or 42)
            app.post(app.stop)
            with self.assertRaises(RuntimeError):
                future.result()
            app.run()
            self.assertEqual(future.result(), 42)
        self.assertEqual(seen, [owner])

    def test_post_exception_is_on_future(self):
        def fail():
            raise ValueError("posted failure")
        with self.app() as app:
            future = app.post(fail)
            app.post(app.stop)
            app.run()
            with self.assertRaisesRegex(ValueError, "posted failure"):
                future.result()

    def test_future_completion_callback_failure_keeps_settled_result(self):
        with self.app() as app:
            future = app.post(lambda: 42)
            def interrupted(_):
                raise KeyboardInterrupt("completion interrupted")
            future.add_done_callback(interrupted)
            with self.assertRaisesRegex(KeyboardInterrupt, "completion interrupted"):
                app.run()
            self.assertEqual(future.result(), 42)

    def test_worker_can_post_but_not_command(self):
        seen = []
        with self.app() as app:
            def worker():
                try:
                    app.open("<p>Wrong thread</p>")
                except RuntimeError:
                    seen.append("rejected")
                app.post(lambda: seen.append("posted"))
                app.post(app.stop)
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            app.run()
        self.assertEqual(seen, ["rejected", "posted"])

    def test_cancelled_post_does_not_execute(self):
        seen = []
        with self.app() as app:
            future = app.post(lambda: seen.append(True))
            self.assertTrue(future.cancel())
            app.post(app.stop)
            app.run()
        self.assertEqual(seen, [])

    def test_pre_stop_settles_pending_work(self):
        with self.app() as app:
            future = app.post(lambda: 1)
            app.stop()
            app.run()
            self.assertTrue(future.done())
            self.assertIsInstance(app.stats(), dict)

    def test_pre_stop_with_signal_bridge_enabled(self):
        with App(backend="headless") as app:
            app.stop()
            app.run()
            self.assertIsInstance(app.stats(), dict)

    def test_dispose_cancels_unrun_work(self):
        app = self.app()
        future = app.post(lambda: 1)
        app.close()
        self.assertTrue(future.cancelled())
        app.close()

    def test_timer_runs_and_stops(self):
        seen = []
        with self.app() as app:
            app.timer(1, lambda event: (seen.append(event["type"]), app.stop()))
            app.run()
        self.assertEqual(seen, ["timer"])

    def test_cancelled_timer_does_not_fire(self):
        seen = []
        with self.app() as app:
            timer = app.timer(1, lambda _: seen.append(True))
            timer.cancel()
            app.post(app.stop)
            app.run()
        self.assertEqual(seen, [])

    def test_callback_exception_survives_cleanup(self):
        def fail(_):
            raise LookupError("callback identity")
        with self.app() as app:
            app.on("started", fail)
            with self.assertRaisesRegex(LookupError, "callback identity"):
                app.run()
        with self.app() as again:
            again.on("started", lambda _: again.stop())
            again.run()

    def test_subscription_identity_and_gc(self):
        seen = []
        with self.app() as app:
            removed = app.on("started", lambda _: seen.append("removed"))
            app.on("started", lambda _: seen.append("kept"))
            app.on("started", lambda _: app.stop())
            removed.close()
            gc.collect()
            app.run()
        self.assertEqual(seen, ["kept"])

    def test_closed_window_is_rejected(self):
        with self.app() as app:
            window = app.open('<p id="x">Text</p>')
            app.on("started", lambda _: app.stop())
            app.run()
            with self.assertRaises(RuntimeError):
                window.set_text("x", "stale")

    def test_invalid_native_request_is_error(self):
        with self.app() as app:
            with self.assertRaises(Ui4meError):
                app.open("<p>bad dimensions</p>", width=0)

    def test_document_mutations_and_checked_state(self):
        with self.app() as app:
            window = app.open('<div id="rows"><p id="first">One</p></div><input id="name" value="Keep"><input id="flag" type="checkbox">')
            window.set_value("name", "Příliš žluťoučký")
            window.set_checked("flag", True)
            self.assertTrue(window.get_checked("flag"))
            window.set_attribute("rows", "class", "list")
            window.add_class("rows", "active")
            window.remove_class("rows", "list")
            window.replace_children_html("rows", '<p id="replacement">Two</p>')
            window.set_text("replacement", "Updated")
            self.assertEqual(window.get_value("name"), "Příliš žluťoučký")
            with self.assertRaises(Ui4meError):
                window.set_text("first", "stale")

    def test_dom_insert_remove_move_and_read(self):
        with self.app() as app:
            window = app.open('<ul id="list"><li id="b" data-k="v">B</li></ul><input id="edit" value="keep">')
            window.prepend_html("list", '<li id="a">A</li>')
            window.append_html("list", '<li id="d">D</li>')
            window.insert_html_after("b", '<li id="c">Č</li>')
            window.insert_html_before("list", '<p id="title">Title</p>')
            self.assertEqual(window.query("#list > li"), ["a", "b", "c", "d"])
            self.assertEqual(window.get_text("list"), "ABČD")
            self.assertEqual(window.get_attribute("b", "data-k"), "v")
            self.assertIsNone(window.get_attribute("b", "title"))
            self.assertEqual(window.get_attributes("b"), {"id": "b", "data-k": "v"})
            with self.assertRaises(Ui4meError):
                window.append_html("list", '<li id="e">E</li><li id="a">dup</li>')
            self.assertFalse(window.has_element("e"))
            window.focus("edit")
            window.move_element("edit", "c")
            self.assertEqual(window.query("#c > input:focus"), ["edit"])
            self.assertEqual(window.get_value("edit"), "keep")
            with self.assertRaises(Ui4meError):
                window.move_element("list", "c")
            window.remove_element("c")
            self.assertFalse(window.has_element("edit"))
            with self.assertRaises(Ui4meError):
                window.get_text("c")

    def test_batch_is_atomic(self):
        with self.app() as app:
            window = app.open('<ul id="log"><li id="l1">one</li></ul>')
            window.batch([
                {"op": "insert_html", "element": "log", "position": "beforeend", "html": '<li id="l2">two</li>'},
                {"op": "add_class", "element": "l2", "name": "new"},
                {"op": "move_element", "element": "l2", "target": "l1", "position": "beforebegin"},
            ])
            self.assertEqual(window.query("#log > li"), ["l2", "l1"])
            with self.assertRaisesRegex(Ui4meError, "batch operation 1"):
                window.batch([
                    {"op": "remove_element", "element": "l1"},
                    {"op": "set_text", "element": "missing", "text": "x"},
                ])
            self.assertEqual(window.query("#log > li"), ["l2", "l1"])

    def test_default_action_rule_registration(self):
        with self.app() as app:
            window = app.open('<form id="f"><textarea id="msg"></textarea></form>')
            window.set_default_action("f", "keydown", key="Enter", shift=False)
            window.set_default_action("f", "keydown", key="Enter", shift=False, prevent=False)
            with self.assertRaises(Ui4meError):
                window.set_default_action("f", "input")

    def test_validity_and_check_validity(self):
        with self.app() as app:
            window = app.open('<form id="f"><input id="n" required><input id="m" type="email" value="a@b.co"><button id="go">Go</button></form>')
            v = window.get_validity("n")
            self.assertFalse(v["valid"])
            self.assertTrue(v["flags"]["valueMissing"])
            self.assertEqual(v["message"], "Please fill out this field.")
            self.assertTrue(window.get_validity("go")["valid"])
            result = window.check_validity("f")
            self.assertEqual(result, {"valid": False, "invalid": ["n"], "count": 1})
            window.set_value("n", "ok")
            window.set_value("m", "a@b.co")
            self.assertTrue(window.check_validity("f")["valid"])
            with self.assertRaises(Ui4meError):
                window.get_validity("missing")

    def test_scroll_geometry_and_follow(self):
        with self.app() as app:
            window = app.open('<style>body{margin:0}.r{height:30px}</style><div id="log" style="height:100px;overflow:auto">'
                              + '<div id="r0" class="r"></div>' + '<div class="r"></div>' * 4 + '</div>', width=400, height=300)
            self.assertEqual(window.get_scroll("log")["max_y"], 50.0)
            self.assertEqual(window.scroll_to("log", y=1000)["y"], 50.0)
            self.assertEqual(window.scroll_by("log", dy=-20)["y"], 30.0)
            window.scroll_into_view("r0", block="start")
            self.assertEqual(window.get_rect("r0"), {"x": 0.0, "y": 0.0, "width": 400.0, "height": 30.0})
            window.set_scroll_follow("log")
            window.append_html("log", '<div class="r"></div>')
            self.assertEqual(window.get_scroll("log")["y"], 80.0)

    def test_scroll_behavior_argument(self):
        with self.app() as app:
            window = app.open('<style>body{margin:0}.r{height:100px}</style><div id="box" style="height:100px;overflow:auto">'
                              + '<div class="r"></div>' * 4 + '</div>', width=400, height=300)
            result = window.scroll_to("box", y=100)
            self.assertEqual((result["y"], result["animating"]), (100.0, False))
            self.assertEqual(window.scroll_by("box", dy=50, behavior="instant")["y"], 150.0)
            self.assertTrue(window.scroll_to("box", y=0, behavior="smooth")["animating"])
            time.sleep(0.6)
            self.assertEqual(window.get_scroll("box"), {**window.get_scroll("box"), "y": 0.0, "animating": False})
            with self.assertRaises(Ui4meError):
                window.scroll_to("box", y=1, behavior="slow")
            window.scroll_into_view("box", behavior="instant")

    def test_selection_and_clipboard(self):
        with self.app() as app:
            window = app.open('<p id="a">Příliš žluťoučký</p><p id="b">кінь</p><input id="pw" type="password" value="secret">')
            window.select_text("a")
            self.assertEqual(window.get_selection(), "Příliš žluťoučký")
            self.assertEqual(window.copy_selection(), "Příliš žluťoučký")
            self.assertEqual(window.get_clipboard_text(), "Příliš žluťoučký")
            window.select_text()
            self.assertEqual(window.get_selection(), "Příliš žluťoučký\nкінь")
            window.clear_selection()
            self.assertEqual(window.get_selection(), "")
            window.set_clipboard_text("pasted ✓")
            self.assertEqual(window.get_clipboard_text(), "pasted ✓")

    def test_streaming_append_and_trim(self):
        with self.app() as app:
            window = app.open('<div id="log"></div><p id="msg"></p>')
            for i in range(300):
                window.batch([
                    {"op": "insert_html", "element": "log", "position": "beforeend", "html": f'<div id="l{i}">{i}</div>'},
                    {"op": "trim_children", "element": "log", "keep": 100},
                ])
                window.append_text("msg", "ž")
            self.assertEqual(len(window.query("#log > div")), 100)
            self.assertFalse(window.has_element("l199"))
            self.assertEqual(window.query("#log > div:first-child"), ["l200"])
            self.assertEqual(window.get_text("msg"), "ž" * 300)
            window.trim_children("log", 10, from_="end")
            self.assertEqual(window.query("#log > div:last-child"), ["l209"])

    def test_dialog_and_select(self):
        with self.app() as app:
            window = app.open('<button id="b">Open</button><dialog id="d"><input id="i"></dialog>'
                              '<select id="s"><option value="a">A</option><option value="b">B</option></select>'
                              '<select id="m" multiple><option value="x">X</option><option value="y">Y</option></select>')
            closes = []
            window.on("close", lambda e: closes.append(e.get("return_value")), element="d")
            window.show_dialog("d")
            self.assertEqual(window.get_dialog("d"), {"open": True, "modal": True, "return_value": ""})
            self.assertEqual(window.query(":focus"), ["i"])
            window.close_dialog("d", "done")
            self.assertFalse(window.get_dialog("d")["open"])
            window.set_value("s", "b")
            self.assertEqual(window.get_value("s"), "b")
            window.set_selected_values("m", ["x", "y"])
            self.assertEqual([o["selected"] for o in window.get_options("m")], [True, True])
            app.on("started", lambda _: app.stop())
            app.run()
            self.assertEqual(closes, ["done"])

    def test_popover(self):
        with self.app() as app:
            window = app.open('<button id="b" popovertarget="p">Open</button>'
                              '<div id="p" popover><button id="in">x</button></div>'
                              '<div id="m" popover="manual">m</div>')
            states = []
            window.on("toggle", lambda e: states.append(e.get("new_state")), element="p")
            self.assertEqual(window.get_popover("p"), {"open": False, "kind": "auto"})
            self.assertEqual(window.get_popover("m")["kind"], "manual")
            window.show_popover("p")
            self.assertTrue(window.get_popover("p")["open"])
            self.assertEqual(window.query(":popover-open"), ["p"])
            self.assertFalse(window.toggle_popover("p"))
            self.assertTrue(window.toggle_popover("p"))
            window.hide_popover("p")
            self.assertFalse(window.get_popover("p")["open"])
            with self.assertRaises(Exception):
                window.show_popover("b")
            app.on("started", lambda _: app.stop())
            app.run()
            self.assertEqual(states, ["open", "closed", "open", "closed"])

    def test_pointer_capture(self):
        with self.app() as app:
            window = app.open('<div id="a">A</div>')
            self.assertFalse(window.set_pointer_capture("a"), "no button is pressed")
            with self.assertRaises(Exception):
                window.set_pointer_capture("a", pointer_id=5)
            window.release_pointer_capture("a")
            self.assertIsNone(window.get_pointer_capture())
            app.on("started", lambda _: app.stop())
            app.run()

    def test_document_html_stylesheets_and_nodes(self):
        with self.app() as app:
            w = app.open("<div id=box><span>no id</span>žluť</div>")
            self.assertEqual(w.get_html("box"), "<span>no id</span>žluť")
            self.assertTrue(w.get_html("box", outer=True).startswith('<div id="box">'))
            sheet = w.add_stylesheet("#box{width:77px} p{colr:red}")
            self.assertTrue(sheet["diagnostics"])
            self.assertEqual(w.get_rect("box")["width"], 77)
            w.replace_stylesheet(sheet["sheet"], "#box{width:66px}")
            self.assertEqual(w.get_rect("box")["width"], 66)
            self.assertEqual([s["kind"] for s in w.stylesheets()], ["attached"])
            w.remove_stylesheet(sheet["sheet"])
            with self.assertRaises(Ui4meError):
                w.remove_stylesheet(sheet["sheet"])
            ref = w.node_of("box")
            kids = w.node_children(ref)
            self.assertEqual((kids["total"], kids["children"][0]["name"]), (2, "span"))
            text = kids["children"][1]["node"]
            self.assertEqual(w.get_node(text)["text"], "žluť")
            self.assertEqual(w.get_html(node=kids["children"][0]["node"], outer=True), "<span>no id</span>")
            cs = w.computed_style("box", "color", "width", "--brand", "not-a-property")
            self.assertEqual(cs["color"]["status"], "supported")
            self.assertTrue(cs["color"]["inherited"])
            self.assertEqual(cs["not-a-property"]["status"], "invalid")
            with self.assertRaises(Ui4meError):
                app.set_link_policy(["javascript"])
            app.set_link_policy(["https"], hosts=["*.example.com"])
            files = app.open("<input id=pick type=file>")
            self.assertEqual(files.get_files("pick"), [])
            geo = w.text_rects("box")
            self.assertEqual((geo["text"], geo["length"]), ("no idžluť", 9))
            self.assertTrue(geo["rects"] and all(r["width"] > 0 for r in geo["rects"]))
            r0 = w.text_rects("box", start=0, end=1)["rects"][0]
            hit = w.text_at_point(r0["x"] + r0["width"] * 0.75, r0["y"] + r0["height"] / 2)
            self.assertEqual((hit["element"], hit["offset"]), ("box", 1))
            w.remove_element("box")
            with self.assertRaises(Ui4meError):
                w.get_node(ref)

    def test_desktop_services_headless(self):
        with self.app() as app:
            w = app.open("<p>x</p>")
            self.assertEqual(app.notify("Hi", "there")["status"], "unavailable")
            self.assertEqual(app.set_tray(tooltip="t", menu=[{"id": "q", "label": "Quit"}])["status"], "unavailable")
            r = w.set_menu([{"label": "File", "items": [{"id": "save", "label": "Save", "accelerator": "Ctrl+S"}]}])
            self.assertTrue(r["accelerators"])
            with self.assertRaises(Ui4meError):
                w.set_menu([{"id": "a", "label": "A", "accelerator": "Ctrl+S"}, {"id": "b", "label": "B", "accelerator": "Ctrl+S"}])
            self.assertEqual(app.register_hotkey("k", "Ctrl+Alt+K")["status"], "unavailable")

    def test_window_actions_and_state(self):
        with self.app() as app:
            window = app.open("<p>w</p>")
            self.assertTrue(window.maximize()["applied"])
            self.assertTrue(window.state()["maximized"])
            window.restore()
            self.assertFalse(window.state()["maximized"])
            window.set_constraints(min_size=(300, 200), resizable=False)
            self.assertEqual(window.state()["min_size"], [300, 200])
            self.assertEqual(app.monitors(), [])
            caps = app.capabilities()
            self.assertEqual((caps["backend"], caps["platform"]), ("headless", "headless"))
            self.assertEqual(caps["features"]["window.focus"]["status"], "unavailable")
            self.assertTrue(caps["features"]["window.focus"]["reason"])
            styled = app.open("<style>#b{width:10px;height:5px}@media (prefers-color-scheme: dark){#b{width:20px}}</style><div id=b></div>")
            self.assertEqual(styled.environment()["color_scheme_source"], "default")
            env = styled.set_environment(color_scheme="dark")
            self.assertEqual((env["color_scheme"], env["color_scheme_source"]), ("dark", "app"))
            self.assertEqual(styled.get_rect("b")["width"], 20)
            styled.set_environment(color_scheme="system")
            self.assertEqual(styled.get_rect("b")["width"], 10)
            with self.assertRaises(Ui4meError):
                styled.set_environment(color_scheme="blue")
            with self.assertRaises(Ui4meError):
                window.window_action("spin")

    def test_file_dialog_headless_completes_as_cancelled(self):
        results = []
        with self.app() as app:
            window = app.open("<p>f</p>")
            window.open_file_dialog(results.append, title="Pick", filters={"Text": ["txt"]})
            window.save_file_dialog(results.append, file_name="notes ž.txt")
            with self.assertRaises(Ui4meError):
                window.file_dialog("delete", results.append)
            app.timer(50, lambda _: app.stop())
            app.run()
        self.assertEqual(results, [{"paths": None}, {"paths": None}])

    def test_accessibility_tree(self):
        with self.app() as app:
            window = app.open('<button id="b">Save</button><label for="n">Name</label><input id="n">')
            text = json.dumps(window.accessibility_tree())
            self.assertIn("Save", text)
            self.assertIn("Name", text)

    def test_rejected_fragment_preserves_previous_subtree(self):
        with self.app() as app:
            window = app.open('<div id="rows"><input id="old" value="Keep"></div><p id="outside">Outside</p>')
            with self.assertRaises(Ui4meError):
                window.replace_children_html("rows", '<p id="outside">Duplicate</p>')
            self.assertEqual(window.get_value("old"), "Keep")

    def test_subscription_removal_during_dispatch(self):
        seen = []
        with self.app() as app:
            app.on("started", lambda _: later.close())
            later = app.on("started", lambda _: seen.append("removed"))
            app.on("started", lambda _: app.stop())
            app.run()
        self.assertEqual(seen, [])

    def test_element_subscription_matches_ancestor_path_once(self):
        seen = []
        with self.app() as app:
            window = app.open('<button id="button"><span id="caption">Press</span></button>')
            window.on("click", lambda event: seen.append(event["element"]), element="button")
            window.on("click", lambda _: seen.append("wrong"), element="other")
            event = ('{"type":"click","window":' + str(window.id) + ',"element":"caption","path":["caption","button"]}').encode()
            self.assertEqual(app._dispatch(app._session, event, None), 0)
        self.assertEqual(seen, ["caption"])

    def test_closed_state_visible_in_terminal_callback(self):
        seen = []
        with self.app() as app:
            window = app.open('<p>Window</p>')
            window.on("closed", lambda _: seen.append(window.closed))
            app.on("started", lambda _: app.stop())
            app.run()
        self.assertEqual(seen, [True])

    def test_dispose_forbidden_in_stopped_callback(self):
        seen = []
        with self.app() as app:
            def stopped(_):
                with self.assertRaises(RuntimeError):
                    app.close()
                seen.append(True)
            app.on("stopped", stopped)
            app.on("started", lambda _: app.stop())
            app.run()
        self.assertEqual(seen, [True])

    def test_stop_after_dispose_is_idempotent_from_worker(self):
        app = self.app()
        app.close()
        errors = []
        def stop():
            try:
                app.stop()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=stop)
        thread.start()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
