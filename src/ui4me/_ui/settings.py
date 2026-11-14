"""``app.settings``: small persistent per-user settings (JSON), shared format with PowerShell.

Stored at ``%APPDATA%\\UI4ME\\<app id>\\settings.json`` on Windows and
``$XDG_CONFIG_HOME/ui4me/<app id>/settings.json`` (default ``~/.config``) on Linux.
Writes are atomic (temporary file + replace). A corrupt file is kept as
``settings.json.corrupt`` and the app starts with defaults instead of failing.
Values must be JSON-serialisable (str, int, float, bool, None, lists, dicts).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import InvalidComponentProps
from .reactive import Signal

if TYPE_CHECKING:  # pragma: no cover
    from .app import UiApp

MAX_BYTES = 1024 * 1024
_APP_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}")


def settings_dir(app_id: str) -> Path:
    if not _APP_ID.fullmatch(app_id):
        raise InvalidComponentProps("app_id may contain only letters, digits, '.', '-' and '_'")
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "UI4ME"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "ui4me"
    return base / app_id


class Settings:
    def __init__(self, app: "UiApp", app_id: str):
        self._app = app
        self.path = settings_dir(app_id) / "settings.json"
        self._data: dict[str, Any] | None = None
        self._signals: dict[str, Signal] = {}
        self._reactions: dict[str, Any] = {}  # keep persisting reactions alive

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = {}
            try:
                raw = self.path.read_bytes()
                if len(raw) > MAX_BYTES:
                    raise ValueError("settings file is larger than 1 MiB")
                data = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("settings file must contain a JSON object")
                self._data = data
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as error:
                try:
                    os.replace(self.path, self.path.with_name("settings.json.corrupt"))
                except OSError:
                    pass
                self._app._report(error, f"settings {self.path}")
        return self._data

    def _save(self) -> None:
        text = json.dumps(self._load(), ensure_ascii=False, indent=2, sort_keys=True)
        if len(text.encode()) > MAX_BYTES:
            raise InvalidComponentProps("settings are limited to 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())  # never replace good settings with an unwritten file
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _key(key: str) -> str:
        if not isinstance(key, str) or not key or len(key) > 200:
            raise InvalidComponentProps("setting names must be non-empty strings (at most 200 characters)")
        return key

    def get(self, key: str, default: Any = None) -> Any:
        return self._load().get(self._key(key), default)

    def set(self, key: str, value: Any) -> None:
        key = self._key(key)
        try:
            json.dumps(value)
        except (TypeError, ValueError) as error:
            raise InvalidComponentProps(f"setting {key!r} must be JSON-serialisable: {error}") from None
        data = self._load()
        if key in data and data[key] == value:
            return
        data[key] = value
        self._save()
        signal = self._signals.get(key)
        if signal is not None and signal.peek() != value:
            signal.set(value)

    def remove(self, key: str) -> None:
        data = self._load()
        key = self._key(key)
        if key in data:  # a stored None is still a stored value
            del data[key]
            self._save()

    def state(self, key: str, default: Any = None) -> Signal:
        """A Signal initialised from the stored value; setting it persists the new value.

        ``theme = app.settings.state('theme', 'system')`` then ``ui.select(..., bind=theme)``.
        """
        key = self._key(key)
        if key not in self._signals:
            signal = Signal(self.get(key, default), name=f"setting {key}")
            self._signals[key] = signal
            from .reactive import Reaction
            first = [True]

            def persist() -> None:
                value = signal.value  # tracked
                if first[0]:  # the initial run only subscribes; defaults are not written
                    first[0] = False
                    return
                self._persist(key, value)
            self._reactions[key] = Reaction(persist, self._app.scheduler, context=f"setting {key}")
        return self._signals[key]

    def _persist(self, key: str, value: Any) -> None:
        if self._load().get(key, object()) != value:
            self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return self._key(key) in self._load()

    def as_dict(self) -> dict[str, Any]:
        return dict(self._load())
