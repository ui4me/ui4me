"""Reproducible SHA-256 source manifest for the complete UI4ME release candidate.

The manifest is intentionally generated only by an explicit maintainer action;
verification never silently refreshes or accepts modified hashes.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'tools/release/SOURCE_FILES.sha256'
EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache',
            '.local', 'build', 'dist', 'dist-manylinux', 'target', 'node_modules',
            'local-evidence', '.idea', '.vscode'}
EXCLUDED_SUFFIX = {'.pyc', '.pyo', '.key', '.pem', '.secret', '.log', '.nupkg', '.whl'}


def included(root: Path = ROOT):
    for p in sorted(root.rglob('*'), key=lambda v: v.relative_to(root).parts):
        if p.is_symlink():
            rel = p.relative_to(root)
            if not any(part in EXCLUDED or part.endswith('.egg-info') for part in rel.parts):
                raise ValueError(f'Unexpected source symlink: {rel}')
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel == Path('tools/release/SOURCE_FILES.sha256'):
            continue
        if any(part in EXCLUDED or part.endswith('.egg-info') for part in rel.parts):
            continue
        if p.suffix.lower() in EXCLUDED_SUFFIX or p.name in ('.DS_Store', '.env'):
            continue
        if p.name.endswith(('.credentials.json', '.local.json')):
            continue
        yield p


def make(root: Path = ROOT) -> str:
    lines = ['# UI4ME 2.1 source SHA-256 manifest; excludes itself and build outputs.']
    for p in included(root):
        lines.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}')
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Refuse a stale manifest; do not write')
    args = parser.parse_args(argv)
    expected = make()
    if args.check:
        if not MANIFEST.is_file() or MANIFEST.read_text(encoding='utf-8') != expected:
            print('FAIL: Source manifest out of date. Review changes before regeneration.', file=sys.stderr)
            return 1
        print(f'PASS: manifest verified ({expected.count(chr(10)) - 1} source paths)')
        return 0
    MANIFEST.write_text(expected, encoding='utf-8')
    print(f'Wrote {MANIFEST} ({expected.count(chr(10)) - 1} source paths)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
