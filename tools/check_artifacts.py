"""Fail CI if UI4ME facade accidentally packages Core or native binaries."""
from __future__ import annotations

import email
import sys
from pathlib import Path
from zipfile import ZipFile


def verify(folder: Path) -> None:
    wheels = sorted(folder.glob('ui4me-*-py3-none-any.whl'))
    sdists = sorted(folder.glob('ui4me-*.tar.gz'))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(f'Expected one portable wheel and one source archive, got {wheels}, {sdists}')
    with ZipFile(wheels[0]) as z:
        names = z.namelist()
        prohibited = ('.so', '.dll', '.exe', '.dylib', '.pyd', '.rs', '.psm1', '.wasm')
        if any(name.endswith(prohibited) for name in names):
            raise SystemExit('Facade wheel unexpectedly contains a native binary or old source')
        info = [n for n in names if n.endswith('.dist-info/METADATA')]
        if len(info) != 1:
            raise SystemExit('Wheel missing metadata')
        metadata = email.message_from_bytes(z.read(info[0]))
        assert metadata['Name'] == 'ui4me'
        assert metadata['Version'] == '0.1.0'
        requirements = metadata.get_all('Requires-Dist', [])
        if not any('ui4me-core' in x.lower() and '1.0.0' in x for x in requirements):
            raise SystemExit(f'Missing Core dependency: {requirements}')
        if 'ui4me/__init__.py' not in names:
            raise SystemExit('Missing facade implementation')
    print('PASS portable wrapper wheel and source distribution:', wheels[0], sdists[0])


if __name__ == '__main__':
    verify(Path(sys.argv[1] if len(sys.argv) > 1 else 'dist'))
