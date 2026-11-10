"""Authored contract tests. They require the real built native library; no fake engine."""
import gc
from pathlib import Path
import tempfile
import threading
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
        self.assertEqual(__version__, "0.1.0")
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


if __name__ == "__main__":
    unittest.main()
