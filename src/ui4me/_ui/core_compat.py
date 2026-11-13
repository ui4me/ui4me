"""UI4ME Core 1.x dependency gate for the host-backed UI4ME 2.x framework."""
from __future__ import annotations
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from types import SimpleNamespace
from .errors import CoreCompatibilityError

MIN_CORE = (1, 0, 0)
MAX_CORE_MAJOR = 1

def _parse(value: str) -> tuple[int, int, int]:
    value = value.split('+')[0].split('-')[0]
    return tuple(int(x) for x in (value.split('.') + ['0', '0'])[:3])

@lru_cache(maxsize=1)
def require():
    try:
        import ui4me_core
    except ImportError as exc:
        raise CoreCompatibilityError('UI4ME 2 requires ui4me-core >=1,<2. Install the platform Core wheel.') from exc
    try:
        found = version('ui4me-core')
    except PackageNotFoundError:
        found = str(getattr(ui4me_core, '__version__', '0'))
    if not (MIN_CORE <= _parse(found) < (2, 0, 0)):
        raise CoreCompatibilityError(f'UI4ME 2 requires ui4me-core >=1,<2; found {found}')
    if not all(hasattr(ui4me_core.Application, attr) for attr in ('from_environment','open_html','run','close')):
        raise CoreCompatibilityError('Installed Core lacks the documented host-backed Application API')
    from . import _adapter
    return SimpleNamespace(App=_adapter.App)

def info():
    try:
        return {'version': version('ui4me-core'), 'binding': 'ui4me_core', 'abi': 'IPC-v1'}
    except PackageNotFoundError:
        return {'version': None, 'binding': 'ui4me_core', 'abi': 'IPC-v1'}
