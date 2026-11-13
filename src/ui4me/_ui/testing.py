"""Pilot: scripted UI tests that run inside a real UI4ME Core host process.

    # test_app.py, run with: ui4me-run --headless test_app.py
    from ui4me import ui
    from ui4me._ui.testing import Pilot

    with ui.app("Test") as app:
        name = ui.input("Name")
        greeting = ui.text(lambda: f"Hi {name.value}")

    def script(pilot):
        pilot.type(name, "Ada")
        assert app.main.core.document.get_text(greeting.id) == "Hi Ada"

    Pilot(app).run(script)

DOM operations, batching, stylesheets and lifecycle go through the real Core host
(``--headless`` keeps it off the desktop). *User input is simulated*: the pilot sets the
control value through Core and delivers the canonical Core event (``input``, ``change``,
``click``, ``keydown``...) through UI4ME's own dispatcher. Native input devices, focus
policy, IME and OS dialogs are not exercised; use real-input tests for those.
"""
from __future__ import annotations

import traceback
from typing import Any, Callable

from .component import Component
from .dom import Element


class Pilot:
    def __init__(self, app, *, timeout: float = 10.0):
        self.app = app
        self.timeout = timeout
        self.errors: list[tuple[BaseException, str | None]] = []
        app.on_error(lambda error, context: self.errors.append((error, context)))

    # -- running ---------------------------------------------------------------------------------
    def run(self, script: Callable[["Pilot"], Any], *, raise_app_errors: bool = True) -> None:
        """Run the app, execute ``script(pilot)`` on the owner thread, then stop. Re-raises failures."""
        outcome: dict = {}
        app = self.app

        def step() -> None:
            from .component import Frame, pop, push
            frame = push(Frame(app, None, None, app.main))
            try:
                script(self)
                self.flush()
            except BaseException as error:  # noqa: BLE001 - re-raised after the app stops
                outcome["error"] = error
                outcome["trace"] = traceback.format_exc()
            finally:
                pop(frame)
                app.stop()

        guard = app.core.timer(int(self.timeout * 1000), lambda _e: (outcome.setdefault(
            "error", TimeoutError("Pilot script timed out")), app.stop()))
        app.core.post(step)
        app.run()
        if "error" in outcome:
            raise outcome["error"]
        if raise_app_errors and self.errors:
            error, context = self.errors[0]
            raise AssertionError(f"app reported an error in {context}: {error!r}") from error
        del guard

    def flush(self) -> None:
        """Apply pending state changes and DOM patches now."""
        self.app.scheduler.flush()

    # -- simulated user input -------------------------------------------------------------------------
    def _window(self, ref: Component):
        window = ref.window or self.app.main
        return window

    def _control(self, ref: Component | Element) -> Element:
        if isinstance(ref, Element):
            return ref
        return getattr(ref, "control", None) or ref.root

    def event(self, ref: Component | Element | None, kind: str, **fields: Any) -> None:
        """Deliver a raw event of type ``kind`` targeting ``ref`` (or the window when None)."""
        if ref is None:
            window = self.app.main
            payload = {"type": kind, "window": window.core.id, **fields}
        else:
            element = self._control(ref) if kind in ("input", "change", "keydown", "compositionstart",
                                                     "compositionend") else (
                ref if isinstance(ref, Element) else ref.root)
            window = ref.window if isinstance(ref, Component) else element.window
            path = [element.id]
            owner = element.owner
            while owner is not None:
                if owner.root.id not in path:
                    path.append(owner.root.id)
                owner = owner.parent
            payload = {"type": kind, "window": window.core.id, "element": element.id, "path": path, **fields}
        window._dispatch(kind, payload)
        self.flush()

    def click(self, ref: Component | Element) -> None:
        self.event(ref, "click")

    def type(self, ref: Component, text: str, *, append: bool = False) -> None:
        """Replace (or append to) a text control's value as the user would, firing ``input``."""
        control = self._control(ref)
        core = ref.window.core
        value = (core.get_value(control.id) + text) if append else text
        core.set_value(control.id, value)
        self.event(ref, "input", value=value)

    def check(self, ref: Component, checked: bool = True) -> None:
        control = self._control(ref)
        ref.window.core.set_checked(control.id, checked)
        self.event(control, "input", checked=checked)

    def choose(self, ref: Component, value: Any) -> None:
        """Pick an option of a select (by python value or wire value) or radio group."""
        wire = None
        for w, _, python in ref.options if hasattr(ref, "options") else ref._options:
            if python == value or w == value:
                wire = w
        if wire is None:
            raise ValueError(f"{value!r} is not an option")
        if hasattr(ref, "_radios"):
            radio = next(r for r in ref._radios if r.attrs.get("value") == wire)
            ref.window.core.set_checked(radio.id, True)
            self.event(radio, "input", checked=True)
            return
        ref.window.core.set_value(ref.control.id, wire)
        self.event(ref, "input", value=wire)

    def key(self, key: str, ref: Component | None = None, *, ctrl: bool = False, shift: bool = False,
            alt: bool = False, meta: bool = False) -> None:
        self.event(ref, "keydown", key=key, ctrl=ctrl, shift=shift, alt=alt, meta=meta)

    # -- observation ------------------------------------------------------------------------------
    def html(self, ref: Component | None = None) -> str:
        window = self._window(ref) if ref is not None else self.app.main
        window.commit()
        return window.core.get_html(ref.root.id if ref is not None else None, outer=ref is not None)

    def text(self, ref: Component | Element) -> str:
        element = ref if isinstance(ref, Element) else ref.root
        element.window.commit()
        return element.window.core.get_text(element.id)

    def value(self, ref: Component) -> str:
        control = self._control(ref)
        ref.window.commit()
        return ref.window.core.get_value(control.id)

    def checked(self, ref: Component) -> bool:
        control = self._control(ref)
        ref.window.commit()
        return ref.window.core.get_checked(control.id)

    def attr(self, ref: Component | Element, name: str) -> str | None:
        element = ref if isinstance(ref, Element) else ref.root
        element.window.commit()
        return element.window.core.get_attribute(element.id, name)

    def exists(self, ref: Component | Element) -> bool:
        element = ref if isinstance(ref, Element) else ref.root
        window = element.window or self.app.main
        window.commit()
        return window.core.has_element(element.id)

    def focused(self) -> str | None:
        """Id of the focused element (from the accessibility-independent document state)."""
        window = self.app.main
        window.commit()
        ids = window.core.query(":focus")
        return ids[0] if ids else None


class StateProbe:
    """Publish component rects, values and focus to a JSON file for native journey harnesses.

    ``StateProbe(app, path, refs={'name': input_ref}, values={'greeting': lambda: ...})`` writes
    the file every ``interval`` seconds. Harness commands can be appended (one JSON per line) to
    ``commands`` (``{"op": "snapshot", "path": ...}``, ``{"op": "stop"}``, ``{"op": "eval", ...}``).
    """

    def __init__(self, app, path, *, refs: dict | None = None, values: dict | None = None,
                 commands=None, interval: float = 0.1):
        import json as _json
        import os as _os
        from pathlib import Path as _Path
        self.app, self.path = app, _Path(path)
        self.refs, self.values = dict(refs or {}), dict(values or {})
        self.commands = _Path(commands) if commands else None
        self._offset = 0
        self._json, self._os = _json, _os
        self.handled = 0
        app.main.on_close(self._write_closed)
        app.every(interval, self._tick)

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(self._json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        self._os.replace(tmp, self.path)

    def _write_closed(self) -> None:
        self._write({"closed": True})

    def _tick(self) -> None:
        window = self.app.main
        if window.core is None or window.closed:
            return
        window.commit()
        core = window.core
        rects, values = {}, {}
        for name, ref in self.refs.items():
            element = getattr(ref, "control", None) or ref.root
            try:
                rects[name] = core.get_rect(element.id) if not ref.disposed else None
            except Exception:
                rects[name] = None
        for name, fn in self.values.items():
            try:
                values[name] = fn()
            except Exception as error:
                values[name] = f"<error {error}>"
        focus = core.query(":focus")
        by_id = {(getattr(r, "control", None) or r.root).id: n for n, r in self.refs.items()}
        self._read_commands()
        self._write({"rects": rects, "values": values, "focus": [by_id.get(f, f) for f in focus],
                     "state": window.core.state(), "environment": window.core.environment(),
                     "handled": self.handled, "diagnostics": self.app.diagnostics()})

    def _read_commands(self) -> None:
        if self.commands is None or not self.commands.exists():
            return
        with self.commands.open("r", encoding="utf-8") as f:
            f.seek(self._offset)
            lines = f.readlines()
            self._offset = f.tell()
        for line in lines:
            if not line.strip():
                continue
            op = self._json.loads(line)
            kind = op.get("op")
            if kind == "snapshot":
                self.app.main.snapshot(op["path"])
            elif kind == "stop":
                self.app.stop()
            elif kind == "theme":
                self.app.theme.set(op["name"])
            elif kind == "computed_style":
                ref = self.refs[op["ref"]]
                self.values[f"style:{op['ref']}:{op['property']}"] = (
                    lambda r=ref, p=op["property"]: self.app.main.core.computed_style(r.root.id, p)[p].get("value"))
            self.handled += 1
