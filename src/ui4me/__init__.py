"""UI4ME 2.0 — batteries-included UI components on UI4ME Core.

Use ``from ui4me import ui`` for the high-level component framework.
Use ``from ui4me import Application, Window, Document`` for the exact,
unmodified Core classes.  Both APIs may coexist in one application.

The lower-level ``ui4me_core`` package owns all native rendering and IPC.
"""
from __future__ import annotations
from importlib import import_module
from typing import Any, TYPE_CHECKING

__version__ = '2.0.1'
__all__ = [
    'ui', 'UiApp', 'Signal', 'Computed',
    'Application', 'Window', 'Document', 'StaleDocumentError',
    'RpcClient', 'RpcError', 'ProtocolError', 'DisconnectedError',
    'LiveBitmap', 'host_binary', '__version__',
]
_CORE_NAMES = frozenset({
    'Application', 'Window', 'Document', 'StaleDocumentError',
    'RpcClient', 'RpcError', 'ProtocolError', 'DisconnectedError',
    'LiveBitmap', 'host_binary',
})
_UI_NAMES = {'ui': 'ui', 'UiApp': 'UiApp', 'Signal': 'Signal', 'Computed': 'Computed'}

if TYPE_CHECKING:
    from ui4me_core import (Application, Window, Document, StaleDocumentError,
        RpcClient, RpcError, ProtocolError, DisconnectedError, LiveBitmap, host_binary)
    from ._ui import ui, UiApp, Signal, Computed


def __getattr__(name: str) -> Any:
    if name in _CORE_NAMES:
        return getattr(import_module('ui4me_core'), name)
    if name in _UI_NAMES:
        return getattr(import_module('ui4me._ui'), _UI_NAMES[name])
    raise AttributeError(f'module ui4me has no attribute {name!r}')


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
