"""UI4ME UI — batteries-included desktop UI for Python on top of UI4ME Core.

    from ui4me import ui

    with ui.app("Hello") as app:
        name = ui.input("Your name")
        ui.text(lambda: f"Hello, {name.value or 'world'}!")
    app.run()
"""
from . import ui
from ._version import __version__
from .app import UiApp
from .errors import *  # noqa: F401,F403
from .reactive import Computed, Signal

__all__ = ["ui", "UiApp", "Signal", "Computed", "__version__"]
