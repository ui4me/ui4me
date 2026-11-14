"""Keep canonical agent skills synchronized with the Python wheel and PowerShell module."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
MAP = (
    (ROOT / 'skills/ui4me-ui-python', ROOT / 'src/ui4me/_skills/ui4me-ui-python'),
    (ROOT / 'skills/ui4me-ui-powershell', ROOT / 'powershell/Ui4me/skills/ui4me-ui-powershell'),
)


def sync(*, check: bool = False) -> None:
    failures = []
    for source, target in MAP:
        if not (source / 'SKILL.md').is_file():
            raise RuntimeError(f'Canonical agent skill missing: {source}')
        want = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        actual = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()} if target.is_dir() else {}
        if actual == want:
            continue
        if check:
            failures.append(str(target.relative_to(ROOT)))
            continue
        if target.is_dir():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    if failures:
        raise RuntimeError('Skill payloads differ; run python tools/sync_skills.py: ' + ', '.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        sync(check=args.check)
    except RuntimeError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise SystemExit(1)
    print('PASS: UI4ME agent skills are synchronized')
