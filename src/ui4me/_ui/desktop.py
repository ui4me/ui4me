"""``app.desktop``: native desktop services that UI4ME Core 1.x actually provides.

Supported (through documented Core APIs): opening URLs/files with the OS handler,
revealing a file, window attention, window state, file drops and desktop
appearance preferences.

Not provided by Core 1.x, so these raise ``NotImplementedError`` instead of
pretending to work: native menu bars and context menus, tray icons, global hotkeys,
OS notifications, printing/PDF export and rich (HTML) clipboard. Use the in-window
alternatives named in each error (``ui.menu``, ``ui.command_palette``,
``app.commands`` shortcuts, ``ui.notify`` toasts, plain-text clipboard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from .component import current_frame
from .errors import InvalidComponentProps, NativeServiceError, UiError

if TYPE_CHECKING:  # pragma: no cover
    from .app import UiApp
    from .window import UiWindow


def _unsupported(feature: str, alternative: str) -> None:
    raise NotImplementedError(
        f"{feature} is not provided by UI4ME Core 1.x, so UI4ME cannot offer it natively. "
        f"In-window alternative: {alternative}.")


@dataclass(frozen=True)
class NativeMenuItem:
    """Description of a native menu entry (reserved; Core 1.x has no native menus)."""
    label: str = ""
    action: Callable[[], Any] | None = None
    shortcut: str | None = None
    enabled: bool = True
    checked: bool = False
    separator: bool = False
    items: tuple["NativeMenuItem", ...] = field(default_factory=tuple)


_WINDOW_ACTIONS = {
    "minimize": {"minimized": True},
    "maximize": {"maximized": True},
    "restore": {"minimized": False, "maximized": False, "fullscreen": False},
    "fullscreen": {"fullscreen": True},
    "exit_fullscreen": {"fullscreen": False},
    "show": {"visible": True},
    "hide": {"visible": False},
    "focus": {"focus": True},
}


class Desktop:
    def __init__(self, app: "UiApp"):
        self.app = app

    def _window(self, window: "UiWindow | None") -> "UiWindow":
        if window is not None:
            target = window
        else:
            frame = current_frame(required=False)
            target = frame.window if frame is not None and frame.window is not None else self.app.main
        if target.core is None or target.closed:
            raise UiError("this desktop action needs an open UI4ME window")
        return target

    def _native(self, call: Callable[[], Any], what: str) -> Any:
        try:
            return call()
        except NotImplementedError:
            raise
        except Exception as error:
            code = getattr(error, "code", None)
            raise NativeServiceError(f"{what} failed{f' ({code})' if code is not None else ''}: {error}") from error

    # -- supported --------------------------------------------------------------------------
    def open_external(self, target: str | Path, *, window: "UiWindow | None" = None) -> dict:
        """Open an http(s)/mailto/file URL or a document with the OS default handler.

        Executables, scripts and shortcuts are refused by Core on Windows.
        """
        self.app._active()
        core_window = self._window(window).core.native if window is not None else None
        return self._native(lambda: self.app.core.native.open_external(target, window=core_window), "open_external")

    def reveal_file(self, path: str | Path, *, window: "UiWindow | None" = None) -> dict:
        """Show a file in the system file manager."""
        self.app._active()
        return self._native(lambda: self.app.core.native.reveal_file(path, window=self._window(window).core.native),
                            "reveal_file")

    def request_attention(self, kind: str = "informational", *, window: "UiWindow | None" = None) -> dict:
        """Ask the window manager to flag the window ('informational', 'critical' or None to clear)."""
        self.app._active()
        if kind not in ("informational", "critical", None):
            raise InvalidComponentProps("attention kind must be 'informational', 'critical' or None")
        return self._native(lambda: self._window(window).core.native.request_attention(kind), "request_attention")

    def window_action(self, action: str, *, window: "UiWindow | None" = None) -> dict:
        """minimize / maximize / restore / fullscreen / exit_fullscreen / show / hide / focus.

        Wayland compositors refuse client focus requests; that raises NativeServiceError.
        """
        if action not in _WINDOW_ACTIONS:
            raise InvalidComponentProps(f"unknown window action {action!r}; choose {', '.join(_WINDOW_ACTIONS)}")
        self.app._active()
        return self._native(lambda: self._window(window).core.native.set(**_WINDOW_ACTIONS[action]),
                            f"window action {action}")

    def window_state(self, *, window: "UiWindow | None" = None) -> dict:
        """Requested and observed native window state (size, scale, focus, maximized, ...)."""
        self.app._active()
        return self._window(window).core.native.state()

    def file_drop(self, callback: Callable[[dict], Any], *, window: "UiWindow | None" = None):
        """Call ``callback(event)`` when files are dropped on the window (``event['paths']``).

        Returns an unsubscribe function. Availability depends on the desktop; see
        ``app.capabilities()``.
        """
        self.app._active()
        return self._window(window).on("file_drop", callback)

    def preferences(self) -> dict:
        """Observed desktop appearance/motion preferences and their source."""
        self.app._active()
        return self.app.core.native.desktop_preferences()

    def on_preferences(self, callback: Callable[[dict], Any]) -> None:
        """Call ``callback(preferences)`` on the UI thread when desktop preferences change."""
        self.app._active()
        app = self.app
        app.core.native.on_desktop_preferences(
            lambda prefs: app.core._post_safely(lambda: app._call(callback, prefs, context="desktop preferences")))

    # -- not provided by Core 1.x -------------------------------------------------------------
    def menu_bar(self, items: Sequence[NativeMenuItem], *, window: "UiWindow | None" = None) -> dict:
        _unsupported("A native menu bar", "ui.menu(...) in a ui.toolbar(), plus app.commands shortcuts")

    def context_menu(self, x: float, y: float, items: Sequence[NativeMenuItem], *,
                     window: "UiWindow | None" = None) -> dict:
        _unsupported("A native context menu", "an in-window ui.menu opened from a 'contextmenu' event")

    def tray(self, *, icon: str | None = None, tooltip: str = "", menu: Sequence[NativeMenuItem] = ()) -> dict:
        _unsupported("A system tray icon", "keep the window open (minimized) and use window attention")

    def remove_tray(self) -> dict:
        _unsupported("A system tray icon", "none needed")

    def global_hotkey(self, identity: str, accelerator: str, callback: Callable[[], Any]) -> dict:
        _unsupported("A global (system-wide) hotkey", "app.commands.add(..., shortcut=...) while the window has focus")

    def unregister_hotkey(self, identity: str) -> None:
        _unsupported("A global (system-wide) hotkey", "app.commands")

    def export_pdf(self, path: str | Path, *, window: "UiWindow | None" = None, size: str = "A4") -> dict:
        _unsupported("PDF export", "generate the PDF in Python with a PDF library")

    def print_document(self, *, window: "UiWindow | None" = None, size: str = "A4") -> dict:
        _unsupported("Printing", "export a file and app.desktop.open_external(path) to print from its viewer")

    def clipboard_html(self, html: str, *, text: str = "", window: "UiWindow | None" = None) -> None:
        _unsupported("The rich (HTML) clipboard", "app.clipboard.copy(text) for plain text")

    def notify(self, title: str, body: str = "", **_: Any) -> dict:
        _unsupported("Operating-system notifications", "ui.notify(...) in-window toasts")
