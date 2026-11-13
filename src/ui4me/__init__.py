"""UI4ME — the thin Python facade for :mod:`ui4me_core`.

Version 0.1 contains no independent renderer, event loop, native binary,
window manager, or component engine. Names are delegated lazily to UI4ME Core.

Import examples::

    from ui4me import Application, Window, Document
    from ui4me import LiveBitmap

Future component APIs will be added here without changing Core's ownership.
"""
from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

# An explicit public re-export surface avoids inadvertently promoting internal
# Core implementation details into the facade's stable compatibility contract.
__all__ = [
    "Application",
    "Window",
    "Document",
    "StaleDocumentError",
    "RpcClient",
    "RpcError",
    "ProtocolError",
    "DisconnectedError",
    "LiveBitmap",
    "host_binary",
]

if TYPE_CHECKING:
    from ui4me_core import (
        Application, Window, Document, StaleDocumentError,
        RpcClient, RpcError, ProtocolError, DisconnectedError,
        LiveBitmap, host_binary,
    )


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module 'ui4me' has no attribute {name!r}")
    try:
        core = import_module("ui4me_core")
    except ModuleNotFoundError as exc:
        if exc.name == "ui4me_core":
            raise ModuleNotFoundError(
                "UI4ME requires ui4me-core >=1.0.0. Install the Core wheel first "
                "(or publish ui4me-core, then install ui4me normally)."
            ) from exc
        raise
    return getattr(core, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


try:
    __version__ = version("ui4me")
except PackageNotFoundError:
    __version__ = "0.1.0"
