"""Small Python API for the ui4me native foundation."""
from ._native import Ui4meError, build_info
from .app import App, Window, Subscription, Task, Timer

from ._version import __version__
__all__ = ["App", "Window", "Subscription", "Task", "Timer", "Ui4meError", "build_info", "__version__"]
