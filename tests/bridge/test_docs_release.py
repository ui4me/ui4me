"""Protect documentation navigation, skills and PowerShell export/packaging contracts."""
from __future__ import annotations
import re
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_public_docs_links_and_no_old_docs():
    docs = ROOT / 'docs'
    for path in [ROOT / 'README.md', *docs.rglob('*.md')]:
        content = path.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^\)\s]+)\)', content):
            bare = target.split('#', 1)[0].split('?', 1)[0]
            if not bare or bare.startswith(('https://', 'http://', 'mailto:')):
                continue
            assert (path.parent / bare).exists(), f'Broken link in {path}: {target}'
    assert not (docs / 'blueprint').exists()
    assert not list(docs.glob('*_2.md'))


def test_published_docs_accurate_to_versions():
    meta = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    assert meta['project']['version'] == '2.1.0'
    assert 'ui4me-core>=1.0.1,<2.0.0' in meta['project']['dependencies']
    assert meta['project']['readme'] == 'docs/publish/pypi.md'
    psmanifest = (ROOT / 'powershell/Ui4me/Ui4me.psd1').read_text()
    assert "ModuleVersion = '2.1.0'" in psmanifest
    assert "ModuleVersion = '1.0.1'" in psmanifest
    assert 'ui4me-ui-new' in meta['project']['scripts']
    assert 'ui4me-ui-skill' in meta['project']['scripts']
    assert (ROOT / 'powershell/Ui4me/README.md').read_bytes() == (ROOT / 'docs/publish/powershell-gallery.md').read_bytes()
    for d in ('docs/guides/quickstart-python.md', 'docs/guides/quickstart-powershell.md',
              'docs/reference/python-api.md', 'docs/reference/powershell-api.md',
              'docs/gallery.md', 'docs/publish/pypi.md'):
        assert (ROOT / d).is_file()


def test_power_shell_loader_and_export_declarations_match():
    psdir = ROOT / 'powershell/Ui4me'
    loader = (psdir / 'Ui4me.psm1').read_text()
    manifest = (psdir / 'Ui4me.psd1').read_text()
    definitions = '\n'.join(p.read_text() for p in (psdir / 'private').glob('*.ps1'))
    exported = set(re.findall(r"'([A-Za-z]+-UI4ME\w*)'", loader.split('Export-ModuleMember', 1)[1]))
    declared = set(re.findall(r"'([A-Za-z]+-UI4ME\w*)'", manifest.split('FunctionsToExport', 1)[1].split(')', 1)[0]))
    defined = set(re.findall(r'^function\s+([A-Za-z]+-UI4ME\w*)\s*\{', definitions, flags=re.M))
    assert exported == declared, sorted(exported ^ declared)
    assert exported <= defined, sorted(exported - defined)
    assert len(exported) >= 70
    assert 'ui4me_core' not in definitions


def test_skill_payloads_synced():
    import subprocess, sys
    result = subprocess.run([sys.executable, 'tools/sync_skills.py', '--check'], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (ROOT / 'powershell/Ui4me/skills/ui4me-ui-powershell/SKILL.md').exists()
    assert (ROOT / 'src/ui4me/_skills/ui4me-ui-python/SKILL.md').exists()


def test_release_source_contains_no_core_native_binaries():
    for p in (ROOT / 'src').rglob('*'):
        if p.is_file():
            assert p.suffix not in ('.exe', '.dll', '.so', '.pyd', '.wasm')


def test_python_fenced_examples_parse():
    """Snippets need real Python syntax, even if their application context is partial."""
    import ast
    files = [ROOT / 'README.md', * (ROOT / 'docs').rglob('*.md'),
             * (ROOT / 'skills').rglob('*.md')]
    failures = []
    for path in files:
        source = path.read_text(encoding='utf-8')
        for block in re.findall(r'^```python\s*\n(.*?)^```', source, flags=re.M | re.S):
            try:
                ast.parse(block)
            except SyntaxError as error:
                failures.append(f'{path}: {error}')
    assert not failures, '\n'.join(failures)


def test_readme_normal_start_examples_and_collapsible_installs():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert text.count('<details>') >= 4
    assert text.count('</details>') == text.count('<details>')
    assert 'python app.py' in text and 'pwsh -File' in text
    assert 'ui4me-ui-skill' in text and 'Install-UI4MEUiSkill' in text
    assert 'no manual `ui4me-host run`' in text  # old launch is no longer needed


def test_full_source_manifest_current():
    from tools.release.source_manifest import make, MANIFEST
    assert MANIFEST.is_file(), 'Release source manifest is missing; regenerate only after review'
    assert MANIFEST.read_text(encoding='utf-8') == make()
