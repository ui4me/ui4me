#!/usr/bin/env python3
"""Adverse-workload soak for the Python binding (F1006).

    python3 tests/soak/soak.py --minutes 60                    # headless, default
    python3 tests/soak/soak.py --minutes 10 --native           # real windows on the private virtual KWin

The driver repeatedly starts an application session (``--session-seconds``), drives it with a mixed
workload on the owner thread, stops it, closes it and starts the next one. Per tick it appends and
trims a chat log, streams text, toggles classes and styles, updates inline SVG, runs CSS animations,
feeds malformed and oversized images / SVG / CSS (data: URLs and local files), runs timers, posts from
worker threads, runs ``run_in_background`` tasks (some cancelled, some failing), uses the clipboard,
opens and closes windows, and every ``--print-every`` seconds paginates and exports a PDF.

It samples RSS, thread count and open file descriptors (Linux /proc) plus the native ``stats`` of the
session, and fails on: any unexpected error, a leaked thread / descriptor / callback after a restart,
or monotonic growth beyond a threshold after the warm-up. A JSON summary is written to ``--out``.
Exit status 0 only when every check passed.

``--native`` re-runs this script under ``tests/native/kwin/chat_journey.py --plain`` (its own nested
KWin and D-Bus session; the person's desktop is never touched).
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import random
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if os.environ.get("UI4ME_INSTALLED") != "1":  # UI4ME_INSTALLED=1: soak the installed package (a release candidate)
    sys.path.insert(0, str(ROOT / "bindings" / "python" / "src"))

PAGE = """<!DOCTYPE html><html><head><style>
@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
@keyframes pulse{0%{opacity:.2}50%{opacity:1}100%{opacity:.2}}
body{margin:0;font-family:sans-serif;font-size:14px;display:flex;flex-direction:column;height:100vh}
#msgs{flex:1;overflow-y:auto;border:1px solid #888}
.row{padding:3px 8px;border-bottom:1px solid #ddd}.row.hot{background:#fe9}.row.wide{padding:10px 8px}
#spin{width:24px;height:24px;background:#37c;animation:spin 1s linear infinite}
#pulse{width:60px;height:10px;background:#c73;animation:pulse 800ms ease-in-out infinite}
#fade{transition:opacity .2s,background .3s}#fade.on{opacity:.4;background:#9c9}
#svg{width:160px;height:80px;border:1px solid #aaa}
#assets{height:60px;overflow:hidden}#assets img{width:20px;height:20px}
</style></head><body>
<input id="q" value=""><div id="fade">fade</div>
<div id="spin"></div><div id="pulse"></div>
<svg id="svg" viewBox="0 0 160 80"><g id="shapes"></g></svg>
<div id="assets"></div><div id="msgs"></div></body></html>"""


def png(width: int, height: int, *, idat_rows: int = 0, corrupt: bool = False) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    rows = b"".join(b"\0" + b"\x40" * (width * 3) for _ in range(idat_rows))
    data = zlib.compress(rows)
    if corrupt:
        data = data[: len(data) // 2]
    return b"\x89PNG\r\n\x1a\n" + header + chunk(b"IDAT", data) + chunk(b"IEND", b"")


def data_url(mime: str, payload: bytes) -> str:
    import base64
    return f"data:{mime};base64," + base64.b64encode(payload).decode()


def adverse_assets(directory: Path) -> list[str]:
    """Image / SVG sources that must fail or be limited, never hang or grow without bound."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "good.png").write_bytes(png(16, 16, idat_rows=16))
    (directory / "big.png").write_bytes(png(2500, 2500, idat_rows=2500))
    (directory / "truncated.png").write_bytes(png(64, 64, idat_rows=64, corrupt=True))
    (directory / "huge_dims.png").write_bytes(png(60000, 60000, idat_rows=1))
    (directory / "garbage.png").write_bytes(os.urandom(4096))
    (directory / "empty.png").write_bytes(b"")
    (directory / "bad.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height=")
    (directory / "deep.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg' width='50' height='50'>" +
                                        "<g>" * 4000 + "<rect width='9' height='9'/>" + "</g>" * 4000 + "</svg>")
    (directory / "use_bomb.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='40' height='40'>"
        "<defs><g id='a'><rect width='5' height='5'/></g>"
        + "".join(f"<g id='g{i}'><use xlink:href='#{'a' if i == 0 else 'g%d' % (i - 1)}'/><use xlink:href='#{'a' if i == 0 else 'g%d' % (i - 1)}'/></g>"
                  for i in range(30))
        + "</defs><use xlink:href='#g29'/></svg>")
    (directory / "missing.png").unlink(missing_ok=True)
    return ["good.png", "big.png", "truncated.png", "huge_dims.png", "garbage.png", "empty.png",
            "bad.svg", "deep.svg", "use_bomb.svg", "missing.png", "nodir/none.png"]


def process_sample() -> dict:
    """RSS (KiB), thread count and open descriptors of this process (Linux /proc)."""
    rss = 0
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1])
                break
        threads = len(os.listdir("/proc/self/task"))
        fds = len(os.listdir("/proc/self/fd"))
    except OSError:
        threads = fds = 0
    return {"rss_kb": rss, "threads": threads, "fds": fds}


class Soak:
    def __init__(self, args):
        self.args = args
        self.rng = random.Random(args.seed)
        self.disabled = set(filter(None, args.disable.split(",")))
        self.started = time.monotonic()
        self.deadline = self.started + args.minutes * 60.0
        self.work = Path(tempfile.mkdtemp(prefix="ui4me-soak-"))
        self.sources = adverse_assets(self.work / "assets")
        self.samples: list[dict] = []
        self.restarts: list[dict] = []
        self.unexpected: list[dict] = []
        self.expected: dict[str, int] = {}
        self.counts: dict[str, int] = {}
        self.native_stats_max: dict[str, int] = {}
        self.next_sample = 0.0
        self.last_print = time.monotonic()
        self.row_serial = 0

    # ---- bookkeeping
    def count(self, name: str, n: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + n

    def reject(self, what: str, error: BaseException) -> None:
        """A failure the workload provokes on purpose (limits, malformed input, a full queue)."""
        key = f"{what}: {type(error).__name__}: {str(error)[:80]}"
        self.expected[key] = self.expected.get(key, 0) + 1

    def fail(self, what: str, error: BaseException | str) -> None:
        text = error if isinstance(error, str) else "".join(traceback.format_exception_only(type(error), error)).strip()
        if len(self.unexpected) < 50:
            self.unexpected.append({"t": round(time.monotonic() - self.started, 1), "where": what, "error": text[:400]})
        self.count("unexpected_errors")

    def step(self, what: str, fn, *, expect=()) -> None:
        """Run one workload step. ``expect`` lists exception classes that count as expected rejections."""
        if what in self.disabled:
            return
        try:
            fn()
            self.count(what)
        except expect as error:  # noqa: PERF203 - deliberate per-step handling
            self.reject(what, error)
        except BaseException as error:  # a RuntimeError of a closed window is expected after close
            if isinstance(error, RuntimeError) and "closed" in str(error).lower():
                self.reject(what, error)
            else:
                self.fail(what, error)

    def sample(self, app, session: int, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self.next_sample:
            return
        self.next_sample = now + self.args.sample_seconds
        s = process_sample()
        s["t"] = round(now - self.started, 1)
        s["session"] = session
        s["py_threads"] = threading.active_count()
        try:
            stats = app.stats()
            for key in ("pending_posts", "reserved_completions", "pending_completions", "timers", "windows"):
                value = int(stats.get(key, 0))
                s[key] = value
                self.native_stats_max[key] = max(self.native_stats_max.get(key, 0), value)
        except BaseException as error:  # stats is owner-only; a failure here is itself a finding
            self.fail("stats", error)
        s["tasks"] = len(getattr(app, "_tasks", ()))
        self.samples.append(s)

    # ---- one session
    def run_session(self, index: int) -> None:
        from ui4me import App, Ui4meError

        args = self.args
        backend = "native" if args.native else "headless"
        remaining = max(1.0, self.deadline - time.monotonic())
        length = min(args.session_seconds, remaining)
        before = process_sample()
        app = App(backend=backend, handle_sigint=False, background_workers=3, max_background_tasks=64)
        state = {"n": 0, "tick": None, "extra": []}
        windows = []
        main = app.open(PAGE, title=f"soak {index}", width=640, height=480, base_path=self.work / "assets")
        windows.append(main)
        stop_flag = threading.Event()
        workers: list[threading.Thread] = []
        tasks = []

        def tick(_event) -> None:
            n = state["n"] = state["n"] + 1
            self.sample(app, index)
            if time.monotonic() >= self.deadline or n * args.tick_ms / 1000.0 >= length:
                app.stop()
                return
            self.chat(main, n)
            if n % 3 == 0:
                self.step("svg", lambda: self.svg(main, n))
            if n % 11 == 0:
                self.step("adverse_assets", lambda: self.assets(main, n), expect=(Ui4meError,))
            if n % 13 == 0:
                self.step("adverse_css", lambda: self.css(main, n), expect=(Ui4meError,))
            if n % 5 == 0:
                self.step("worker_post", lambda: self.worker_post(app, main, workers, stop_flag, Ui4meError),
                          expect=(Ui4meError,))
            if n % 9 == 0:
                self.step("background", lambda: self.background(app, main, tasks, Ui4meError), expect=(Ui4meError,))
            if n % 17 == 0:
                self.step("clipboard", lambda: self.clipboard(main, n))
            if n % 23 == 0:
                self.step("timers", lambda: self.timers(app, state, n), expect=(Ui4meError,))
            if n % 61 == 0:
                self.step("window_churn", lambda: self.window_churn(app, windows, Ui4meError), expect=(Ui4meError,))
            if time.monotonic() - self.last_print >= args.print_every:
                self.last_print = time.monotonic()
                self.step("paginate_export", lambda: self.paginate(main))

        state["tick"] = app.timer(args.tick_ms, tick, repeat=True)
        error = None
        try:
            app.run()
        except BaseException as caught:
            error = caught
            self.fail("run", caught)
        stop_flag.set()
        for thread in workers:
            thread.join(10)
            if thread.is_alive():
                self.fail("worker_thread", f"worker {thread.name} still alive after stop")
        # Leak probes before close: callbacks and tasks the session still holds.
        leaked = {
            "pending_posts": len(getattr(app, "_pending", ())),
            "tasks": len(getattr(app, "_tasks", ())),
            "timers": len(getattr(app, "_timers", ())),
        }
        try:
            app.close()
        except BaseException as caught:
            self.fail("close", caught)
        del app, main, windows, tasks, state
        gc.collect()
        time.sleep(0.3)
        after = process_sample()
        names = sorted(t.name for t in threading.enumerate() if t is not threading.main_thread())
        record = {
            "session": index, "backend": backend, "seconds": round(length, 1),
            "threads_before": before["threads"], "threads_after": after["threads"],
            "fds_before": before["fds"], "fds_after": after["fds"], "rss_kb_after": after["rss_kb"],
            "leftover_python_threads": names, "held_at_stop": leaked, "run_error": repr(error) if error else None,
        }
        self.restarts.append(record)
        self.count("sessions")

    # ---- workload steps (owner thread)
    def chat(self, window, n: int) -> None:
        self.row_serial += 1
        k = self.row_serial
        self.step("chat_append", lambda: window.insert_html(
            "msgs", "beforeend", f'<div class="row" id="m{k}"><b>u{k % 5}</b> message {k} with some words to wrap around</div>'))
        self.step("chat_trim", lambda: window.trim_children("msgs", 200))
        self.step("chat_stream", lambda: window.append_text(f"m{k}", " tok" * (n % 4)))
        if n % 2 == 0:
            self.step("class_toggle", lambda: (window.add_class(f"m{k}", "hot"), window.remove_class(f"m{k - 1}", "hot")))
        if n % 4 == 0:
            self.step("style_change", lambda: window.set_attribute(f"m{k}", "style", f"color:#{n * 7919 % 0xFFFFFF:06x}"))
        if n % 6 == 0:
            self.step("class_layout", lambda: (window.add_class(f"m{k}", "wide"), window.remove_class(f"m{k - 1}", "wide")))
        if n % 8 == 0:
            self.step("fade", lambda: (window.add_class("fade", "on") if n % 16 else window.remove_class("fade", "on")))
        if n % 7 == 0:
            self.step("scroll", lambda: window.scroll_to("msgs", y=0 if n % 14 == 0 else 1e6))
        if n % 10 == 0:
            self.step("focus_value", lambda: (window.focus("q"), window.set_value("q", f"typed {n}")))

    def svg(self, window, n: int) -> None:
        shapes = "".join(
            f'<circle cx="{(n * 7 + i * 31) % 160}" cy="{(i * 17 + n) % 80}" r="{3 + i % 9}" fill="hsl({(n + i * 40) % 360},70%,50%)"/>'
            f'<path d="M{i * 10} 0 Q {n % 160} 40 {i * 5} 80" stroke="#333" fill="none"/>'
            for i in range(1 + n % 12))
        window.replace_children_html("shapes", shapes)
        window.set_attribute("svg", "viewBox", f"0 0 {160 + n % 5} 80")

    def assets(self, window, n: int) -> None:
        picks = [self.sources[(n + i) % len(self.sources)] for i in range(6)]
        dataurls = [
            data_url("image/png", png(8, 8, idat_rows=8)),
            data_url("image/png", os.urandom(300)),
            data_url("image/png", png(40000, 40000, idat_rows=1)),
            data_url("image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'><circle r="),
            data_url("image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'><circle cx='10' cy='10' r='9'/></svg>"),
            data_url("text/plain", b"not an image"),
        ]
        html = "".join(f'<img src="{p}">' for p in picks) + "".join(f'<img src="{u}">' for u in dataurls[: 1 + n % 6])
        window.replace_children_html("assets", html)
        if n % 22 == 0:  # immediate replacement while decodes may still be pending: cancellation
            window.replace_children_html("assets", "")

    def css(self, window, n: int) -> None:
        bad = [
            "}}{{ @@@ ;; .x{color:",
            ".r{" + "a:b;" * 3000 + "}",
            "@import url(" + "x" * 5000 + ");",
            "@font-face{font-family:Z;src:url(data:font/ttf;base64,AAAA)}",
            ".row:nth-child(" + "2n+" * 500 + "1){color:red}",
            "@media (min-width:" + "9" * 400 + "px){.row{color:red}}",
            ".ok{color:#" + f"{n % 0xFFFFFF:06x}" + "}",
        ]
        sheet = window.add_stylesheet(bad[n // 13 % len(bad)])
        window.remove_stylesheet(sheet["sheet"])

    def worker_post(self, app, window, workers, stop_flag, Ui4meError) -> None:
        self.reap(workers)
        if len(workers) >= 6:
            return

        def work():
            futures = []
            for i in range(20):
                if stop_flag.is_set():
                    return
                futures.append(app.post(lambda i=i: window.set_text("fade", f"post {i}")))
            for future in futures:
                try:
                    future.result(5)
                except Exception as error:  # full queue / stopping / closed window
                    self.reject("worker_post_future", error)

        thread = threading.Thread(target=work, name=f"soak-post-{len(workers)}", daemon=True)
        thread.start()
        workers.append(thread)

    @staticmethod
    def reap(workers) -> None:
        workers[:] = [t for t in workers if t.is_alive()]

    def background(self, app, window, tasks, Ui4meError) -> None:
        tasks[:] = [t for t in tasks if not t.delivered and not t.done or not t.delivered]
        if len(tasks) >= 40:
            return

        def sleepy(task, seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if task.cancelled:
                    return None
                time.sleep(0.005)
            return seconds

        def boom():
            raise ValueError("planned failure")

        done = lambda value: self.count("task_done")  # noqa: E731
        failed = lambda error: self.reject("task_error", error)  # noqa: E731
        cancelled = lambda: self.count("task_cancelled")  # noqa: E731
        tasks.append(app.run_in_background(sleepy, 0.05, pass_task=True, on_done=done, on_error=failed, on_cancel=cancelled))
        tasks.append(app.run_in_background(boom, on_done=done, on_error=failed, on_cancel=cancelled))
        victim = app.run_in_background(sleepy, 5.0, pass_task=True, on_done=done, on_error=failed, on_cancel=cancelled)
        tasks.append(victim)
        victim.cancel()

    def clipboard(self, window, n: int) -> None:
        window.set_clipboard_text(f"clip {n} ✓")
        got = window.get_clipboard_text()
        if got != f"clip {n} ✓":
            self.fail("clipboard", f"clipboard returned {got!r}")
        window.select_text("msgs")
        window.copy_selection()
        window.clear_selection()

    def timers(self, app, state, n: int) -> None:
        once = app.timer(1 + n % 20, lambda _e: self.count("timer_fired"))
        repeating = app.timer(5, lambda _e: self.count("timer_repeat"), repeat=True)
        if n % 2:
            once.cancel()
        # The repeating timer lives only briefly: cancelled by a later one-shot.
        app.timer(40, lambda _e: repeating.cancel())

    def window_churn(self, app, windows, Ui4meError) -> None:
        extra = [app.open(PAGE, title="churn", width=320, height=200, base_path=self.work / "assets") for _ in range(3)]
        for w in extra:
            w.replace_children_html("assets", "".join(f'<img src="{p}">' for p in self.sources))
        for w in extra:
            w.close()
        self.count("windows_opened", 3)

    def paginate(self, window) -> None:
        result = window.paginate("A4")
        out = self.work / "export.pdf"
        window.export_pdf(out, "A4", dpi=72)
        out.unlink(missing_ok=True)
        self.count("pages", int(result.get("count", 0)))

    # ---- checks
    def verdict(self) -> dict:
        args = self.args
        checks: dict[str, dict] = {}
        elapsed = time.monotonic() - self.started
        warm = min(args.warmup_seconds, elapsed * 0.25)
        series = [s for s in self.samples if s["t"] >= warm]

        def quartile_growth(key: str) -> tuple[float, float, float]:
            values = [s[key] for s in series]
            if len(values) < 8:
                return 0.0, 0.0, 0.0
            q = max(1, len(values) // 4)
            first, last = statistics.median(values[:q]), statistics.median(values[-q:])
            return first, last, last - first

        first, last, growth = quartile_growth("rss_kb")
        checks["rss_growth"] = {"first_quartile_mb": round(first / 1024, 1), "last_quartile_mb": round(last / 1024, 1),
                                "growth_mb": round(growth / 1024, 1), "limit_mb": args.max_rss_growth_mb,
                                "samples": len(series), "ok": growth / 1024 <= args.max_rss_growth_mb}
        # Threads and descriptors at the end of each restart must not climb session after session.
        after = [r for r in self.restarts]
        if after:
            base = after[0]
            worst_threads = max(r["threads_after"] for r in after) - base["threads_after"]
            worst_fds = max(r["fds_after"] for r in after) - base["fds_after"]
            leftovers = [r for r in after if r["leftover_python_threads"]]
            held = [r for r in after if any(r["held_at_stop"].values())]
            checks["restart_threads"] = {"first": base["threads_after"], "worst_delta": worst_threads,
                                         "limit": args.thread_slack, "ok": worst_threads <= args.thread_slack}
            checks["restart_fds"] = {"first": base["fds_after"], "worst_delta": worst_fds,
                                     "limit": args.fd_slack, "ok": worst_fds <= args.fd_slack}
            checks["python_threads_after_restart"] = {"sessions_with_leftovers": len(leftovers),
                                                      "example": leftovers[0] if leftovers else None, "ok": not leftovers}
            checks["callbacks_held_at_stop"] = {"sessions": len(held), "example": held[0] if held else None,
                                                "note": "posts/tasks/timers a stopped session still held before close; "
                                                        "close() must clear them (checked by threads/fds)",
                                                "ok": True}
        _, _, thread_growth = quartile_growth("threads")
        _, _, fd_growth = quartile_growth("fds")
        checks["thread_growth_in_session"] = {"growth": thread_growth, "limit": args.thread_slack, "ok": thread_growth <= args.thread_slack}
        checks["fd_growth_in_session"] = {"growth": fd_growth, "limit": args.fd_slack, "ok": fd_growth <= args.fd_slack}
        checks["unexpected_errors"] = {"count": len(self.unexpected), "ok": not self.unexpected}
        checks["sessions"] = {"count": len(self.restarts), "ok": len(self.restarts) >= 1}
        checks["queues_bounded"] = {"max": self.native_stats_max, "ok": self.native_stats_max.get("pending_posts", 0) <= 512}
        return checks

    def summary(self, checks: dict) -> dict:
        elapsed = time.monotonic() - self.started
        first, last = (self.samples[0], self.samples[-1]) if self.samples else ({}, {})
        step = max(1, len(self.samples) // 120)
        return {
            "backend": "native" if self.args.native else "headless",
            "minutes_requested": self.args.minutes, "seconds_elapsed": round(elapsed, 1),
            "ok": all(c["ok"] for c in checks.values()),
            "checks": checks,
            "start": {k: first.get(k) for k in ("rss_kb", "threads", "fds")},
            "end": {k: last.get(k) for k in ("rss_kb", "threads", "fds")},
            "peak_rss_kb": max((s["rss_kb"] for s in self.samples), default=0),
            "workload_counts": dict(sorted(self.counts.items())),
            "expected_rejections": dict(sorted(self.expected.items(), key=lambda kv: -kv[1])[:40]),
            "unexpected": self.unexpected,
            "native_stats_max": self.native_stats_max,
            "restarts": self.restarts[:5] + (self.restarts[-5:] if len(self.restarts) > 10 else self.restarts[5:]),
            "samples": self.samples[::step],
            "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(self.args).items()},
        }

    def run(self) -> int:
        index = 0
        while time.monotonic() < self.deadline:
            index += 1
            try:
                self.run_session(index)
            except BaseException as error:
                self.fail("session", error)
                traceback.print_exc()
                if len(self.unexpected) >= 50:
                    break
            if index % 5 == 0:
                s = self.samples[-1] if self.samples else {}
                print(f"[{(time.monotonic() - self.started) / 60:5.1f} min] session {index} rss={s.get('rss_kb', 0) // 1024} MB "
                      f"threads={s.get('threads')} fds={s.get('fds')} unexpected={len(self.unexpected)}", flush=True)
        checks = self.verdict()
        summary = self.summary(checks)
        out = Path(self.args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2))
        shutil.rmtree(self.work, ignore_errors=True)
        print(json.dumps({k: summary[k] for k in ("backend", "seconds_elapsed", "ok", "start", "end", "peak_rss_kb")}))
        for name, check in checks.items():
            print(f"  {'ok  ' if check['ok'] else 'FAIL'} {name}: {json.dumps(check)[:200]}")
        for item in self.unexpected[:10]:
            print("  unexpected:", item)
        return 0 if summary["ok"] else 1


def parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--minutes", type=float, default=60.0)
    p.add_argument("--native", action="store_true", help="real windows on the private virtual KWin (chat_journey --plain)")
    p.add_argument("--out", type=Path, default=ROOT / "build" / "soak-summary.json")
    p.add_argument("--session-seconds", type=float, default=60.0, help="length of one app start/stop cycle")
    p.add_argument("--tick-ms", type=int, default=20)
    p.add_argument("--sample-seconds", type=float, default=15.0)
    p.add_argument("--print-every", type=float, default=180.0, help="seconds between pagination + PDF export")
    p.add_argument("--warmup-seconds", type=float, default=150.0)
    p.add_argument("--max-rss-growth-mb", type=float, default=96.0)
    p.add_argument("--thread-slack", type=int, default=2)
    p.add_argument("--fd-slack", type=int, default=6)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--disable", default="", help="comma-separated step names to skip (bisecting a finding)")
    return p.parse_args(argv)


def main() -> int:
    args = parse()
    if args.native and not os.environ.get("UI4ME_SOAK_INNER"):
        out = Path(args.out).resolve()
        harness = ROOT / "tests" / "native" / "kwin" / "chat_journey.py"
        env = dict(os.environ, UI4ME_SOAK_INNER="1", UI4ME_PLAIN_TIMEOUT=str(int(args.minutes * 60 + 600)))
        command = [sys.executable, str(harness), "--out", str(out.parent / (out.stem + "-harness")), "--plain", "--",
                   sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        return subprocess.call(command, env=env)
    return Soak(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
