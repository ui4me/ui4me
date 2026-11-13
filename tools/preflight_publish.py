"""Block UI4ME facade publication until the corresponding Core wheels exist.

CI invokes this only for an explicitly approved PyPI publication. This script
never uploads anything and needs no credentials. Errors fail closed.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

CORE_INDEX = 'https://pypi.org/pypi/ui4me-core/1.0.0/json'
WRAPPER_INDEX = 'https://pypi.org/pypi/ui4me/0.1.0/json'


def get_release(url: str) -> dict | None:
    try:
        with urlopen(url, timeout=15) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f'PyPI check failed with HTTP {exc.code}: {url}') from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f'PyPI unavailable; refusing to publish: {url}') from exc


def preflight() -> None:
    core = get_release(CORE_INDEX)
    if core is None:
        raise SystemExit('Publish ui4me-core==1.0.0 first; it is not yet on PyPI')
    wheels = [f.get('filename', '') for f in core.get('urls', []) if f.get('packagetype') == 'bdist_wheel']
    archives = [f.get('filename', '') for f in core.get('urls', []) if f.get('packagetype') == 'sdist']
    if not any('manylinux' in f for f in wheels) or not any('win_amd64' in f for f in wheels) or not archives:
        raise SystemExit('Core 1.0.0 needs Linux + Windows wheels and an sdist on PyPI before facade publishing')
    if get_release(WRAPPER_INDEX) is not None:
        raise SystemExit('ui4me==0.1.0 is already published; bump the facade version instead of reusing it')
    print('PASS: Core 1.0.0 published for Linux/Windows, facade 0.1.0 not yet published')


if __name__ == '__main__':
    preflight()
