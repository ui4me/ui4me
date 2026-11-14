"""Refuse publication unless dependencies are published and the version is unused.

    python tools/preflight_publish.py VERSION [--registry pypi|psgallery|all]

Checks (read-only, no credentials, fails closed on network errors):
* PyPI has ui4me-core >=1.0.1,<2 with Linux and Windows wheels and an sdist;
* the PowerShell Gallery has UI4ME.Core >=1.0.1,<2;
* VERSION of ``ui4me`` (PyPI) / ``UI4ME`` (Gallery) is not already published.
"""
from __future__ import annotations

import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENT = {'User-Agent': 'ui4me-release-preflight'}


def fetch(url: str) -> bytes | None:
    try:
        with urlopen(Request(url, headers=AGENT), timeout=20) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise SystemExit(f'FAIL: registry check failed with HTTP {exc.code}: {url}') from exc
    except (URLError, TimeoutError) as exc:
        raise SystemExit(f'FAIL: registry unavailable; refusing to publish: {url}') from exc


def gallery_versions(name: str) -> list[str]:
    data = fetch(f"https://www.powershellgallery.com/api/v2/FindPackagesById()?id='{name}'") or b''
    return re.findall(r'<d:Version>([^<]+)</d:Version>', data.decode('utf-8', 'replace'))


def check_pypi(version: str) -> None:
    core = json.loads(fetch('https://pypi.org/pypi/ui4me-core/json') or b'{}')
    good = []
    for release, files in core.get('releases', {}).items():
        try:
            components = tuple(int(v) for v in release.split('.')[:3])
        except ValueError:
            continue
        if not ((1, 0, 1) <= components < (2, 0, 0)):
            continue
        names = [f['filename'] for f in files]
        if any('manylinux' in n for n in names) and any('win_amd64' in n for n in names) and any(n.endswith('.tar.gz') for n in names):
            good.append(release)
    if not good:
        raise SystemExit('FAIL: no ui4me-core >=1.0.1,<2 release with Linux+Windows wheels and an sdist on PyPI')
    if fetch(f'https://pypi.org/pypi/ui4me/{version}/json') is not None:
        raise SystemExit(f'FAIL: ui4me {version} is already on PyPI; choose the next unused version')
    print(f'PASS PyPI: ui4me-core {", ".join(sorted(good))} available; ui4me {version} unused')


def check_gallery(version: str) -> None:
    core = [v for v in gallery_versions('UI4ME.Core') if v.startswith('1.') and tuple(int(x) for x in v.split('.')[:3]) >= (1, 0, 1)]
    if not core:
        raise SystemExit('FAIL: UI4ME.Core >=1.0.1,<2 is not on the PowerShell Gallery')
    if version in gallery_versions('UI4ME'):
        raise SystemExit(f'FAIL: UI4ME {version} is already on the PowerShell Gallery; choose the next unused version')
    print(f'PASS Gallery: UI4ME.Core {", ".join(core)} available; UI4ME {version} unused')


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    version = argv[0]
    registry = argv[argv.index('--registry') + 1] if '--registry' in argv else 'all'
    if registry in ('pypi', 'all'):
        check_pypi(version)
    if registry in ('psgallery', 'all'):
        check_gallery(version)


if __name__ == '__main__':
    main(sys.argv[1:])
