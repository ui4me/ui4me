"""Build every UI4ME release artifact into one folder, then verify it.

    python tools/build_dist.py [OUT_DIR]

Produces ``ui4me-X-py3-none-any.whl`` and ``ui4me-X.tar.gz`` (python -m build) and
``UI4ME-X.zip`` (the ``Ui4me/`` PowerShell module folder, ready for Publish-Module or for
extraction into a PSModulePath folder), plus ``SHA256SUMS``. The PowerShell theme
CSS is copied from the Python package so both bindings ship identical styles.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_artifacts  # noqa: E402
from sync_skills import sync as sync_skills


def sync_assets() -> None:
    for name in ('theme.css', 'functional.css'):
        source = ROOT / 'src/ui4me/_ui/assets' / name
        target = ROOT / 'powershell/Ui4me/assets' / name
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copyfile(source, target)
            print(f'synced {target.relative_to(ROOT)}')


def module_zip(out: Path, version: str) -> Path:
    folder = ROOT / 'powershell/Ui4me'
    target = out / f'UI4ME-{version}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(('Ui4me/' + path.relative_to(folder).as_posix()), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, path.read_bytes())
    return target


def sync_docs() -> None:
    """Keep published PowerShell Gallery README aligned with the canonical docs."""
    source = ROOT / 'docs/publish/powershell-gallery.md'
    target = ROOT / 'powershell/Ui4me/README.md'
    if target.read_bytes() != source.read_bytes():
        shutil.copyfile(source, target)
        print('synced PowerShell Gallery README')


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'dist').resolve()
    if out.exists():
        for old in list(out.glob('ui4me-*')) + list(out.glob('UI4ME-*.zip')) + list(out.glob('SHA256SUMS')):
            old.unlink()
    out.mkdir(parents=True, exist_ok=True)
    sync_assets()
    sync_skills(check=False)
    sync_docs()
    subprocess.run([sys.executable, '-m', 'build', '--outdir', str(out), str(ROOT)], check=True)
    version = next(out.glob('ui4me-*-py3-none-any.whl')).name.split('-')[1]
    module_zip(out, version)
    check_artifacts.verify(out)
    lines = []
    for path in sorted(p for p in out.iterdir() if p.name != 'SHA256SUMS'):
        lines.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
    (out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
