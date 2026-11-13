"""Verify UI4ME release artifacts before anything is published.

    python tools/check_artifacts.py DIST_DIR

DIST_DIR must contain exactly one ``ui4me-X-py3-none-any.whl``, one ``ui4me-X.tar.gz``
and one ``UI4ME-X.zip`` (the PowerShell module folder). Fails if versions disagree,
if a native binary, Core source or the old in-process backend is packaged, or if the
Core dependency is missing. Needs no network and no credentials.
"""
from __future__ import annotations

import email
import re
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

NATIVE = ('.so', '.dll', '.exe', '.dylib', '.pyd', '.rs', '.wasm', '.node')
FORBIDDEN_PARTS = ('Ui4me.Managed', 'ui4me_ui/', 'ui4me-host', '_bin/', 'ui4me_core/')


def fail(message: str) -> None:
    raise SystemExit(f'FAIL: {message}')


def check_names(kind: str, names: list[str]) -> None:
    bad = [n for n in names if n.lower().endswith(NATIVE) or any(p in n for p in FORBIDDEN_PARTS)]
    if bad:
        fail(f'{kind} contains native/Core/legacy files: {bad[:5]}')


def verify(folder: Path) -> str:
    wheels = sorted(folder.glob('ui4me-*-py3-none-any.whl'))
    sdists = sorted(folder.glob('ui4me-*.tar.gz'))
    modules = sorted(folder.glob('UI4ME-*.zip'))
    if len(wheels) != 1 or len(sdists) != 1 or len(modules) != 1:
        fail(f'expected one wheel, one sdist and one PowerShell module zip; got {wheels}, {sdists}, {modules}')
    with ZipFile(wheels[0]) as z:
        names = z.namelist()
        check_names('wheel', names)
        meta = [n for n in names if n.endswith('.dist-info/METADATA')]
        if len(meta) != 1:
            fail('wheel metadata missing')
        metadata = email.message_from_bytes(z.read(meta[0]))
        version = metadata['Version']
        if metadata['Name'] != 'ui4me':
            fail(f"wheel name is {metadata['Name']}")
        requires = metadata.get_all('Requires-Dist', [])
        if not any(re.fullmatch(r'ui4me-core\s*(\(?)\s*<2(\.0\.0)?\s*,\s*>=1\.0\.0\)?|ui4me-core\s*>=1\.0\.0\s*,\s*<2(\.0\.0)?', r.strip()) for r in requires):
            fail(f'wheel must require ui4me-core>=1.0.0,<2: {requires}')
        for required in ('ui4me/__init__.py', 'ui4me/launcher.py', 'ui4me/_ui/_adapter.py',
                         'ui4me/_ui/assets/theme.css', 'ui4me/_ui/assets/functional.css', 'ui4me/_ui/py.typed'):
            if required not in names:
                fail(f'wheel lacks {required}')
        if 'ui4me-run = ui4me.launcher:main' not in z.read([n for n in names if n.endswith('entry_points.txt')][0]).decode():
            fail('wheel lacks the ui4me-run entry point')
        init = z.read('ui4me/__init__.py').decode()
        if f"__version__ = '{version}'" not in init:
            fail('ui4me.__version__ differs from the wheel version')
    if sdists[0].name != f'ui4me-{version}.tar.gz':
        fail(f'sdist {sdists[0].name} does not match version {version}')
    with tarfile.open(sdists[0]) as t:
        names = t.getnames()
        check_names('sdist', names)
        if not any(n.endswith('/LICENSE') for n in names) or not any(n.endswith('/pyproject.toml') for n in names):
            fail('sdist lacks LICENSE or pyproject.toml')
    if modules[0].name != f'UI4ME-{version}.zip':
        fail(f'PowerShell module zip {modules[0].name} does not match version {version}')
    with ZipFile(modules[0]) as z:
        names = z.namelist()
        check_names('PowerShell module', names)
        for required in ('UI4ME/UI4ME.psd1', 'UI4ME/UI4ME.psm1', 'UI4ME/LICENSE',
                         'UI4ME/assets/theme.css', 'UI4ME/assets/functional.css'):
            if required not in names:
                fail(f'module zip lacks {required}')
        manifest = z.read('UI4ME/UI4ME.psd1').decode('utf-8-sig')
        if f"ModuleVersion = '{version}'" not in manifest:
            fail('UI4ME.psd1 ModuleVersion differs from the Python version')
        if not re.search(r"ModuleName\s*=\s*'UI4ME\.Core'", manifest):
            fail('UI4ME.psd1 must require UI4ME.Core')
    print(f'PASS ui4me {version}: {wheels[0].name}, {sdists[0].name}, {modules[0].name}')
    return version


if __name__ == '__main__':
    verify(Path(sys.argv[1] if len(sys.argv) > 1 else 'dist'))
