"""Distribution contracts independent from a native Core installation."""
from __future__ import annotations
import re
import tomllib
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def test_python_name_version_dependency_and_console_script():
    meta = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    project = meta['project']
    assert project['name'] == 'ui4me'
    assert re.fullmatch(r'2\.\d+\.\d+', project['version'])
    assert project['dependencies'] == ['ui4me-core>=1.0.1,<2.0.0']
    assert meta['project']['scripts']['ui4me-run'] == 'ui4me.launcher:main'


def test_public_core_api_names_are_unchanged(monkeypatch):
    module = ModuleType('ui4me_core')
    from ui4me import _CORE_NAMES
    for symbol in _CORE_NAMES:
        setattr(module, symbol, object())
    monkeypatch.setitem(sys.modules, 'ui4me_core', module)
    import ui4me
    for symbol in _CORE_NAMES:
        assert getattr(ui4me, symbol) is getattr(module, symbol)
    assert ui4me.__version__ == tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    assert 'ui' in ui4me.__all__


def test_powershell_ui_has_own_core_dependency_without_legacy_engine():
    manifest = (ROOT / 'powershell/Ui4me/Ui4me.psd1').read_text(encoding='utf8')
    module = (ROOT / 'powershell/Ui4me/Ui4me.psm1').read_text(encoding='utf8')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    assert f"ModuleVersion = '{version}'" in manifest  # both bindings release together
    assert "ModuleName = 'UI4ME.Core'" in manifest
    sources = module + ''.join(p.read_text(encoding='utf8') for p in (ROOT/'powershell/Ui4me/private').glob('*.ps1'))
    assert 'Start-UI4MEScript' in sources
    assert 'Set-UI4MEReady' in sources
    assert 'Wait-UI4ME' in sources
    assert 'Start-UI4MEHost' in sources
    assert 'Add-Type' not in sources
    definitions = set(re.findall(r'^function\s+([A-Za-z0-9-]+)\s*\{', sources, flags=re.M))
    declared = set(re.findall(r"'((?:Invoke|New|Get|Set|Show|Add|Start)-UI4ME[A-Za-z0-9-]+)'", manifest))
    assert declared <= definitions, sorted(declared - definitions)
    assert len(declared) >= 30


def test_no_old_runtime_package_in_public_imports():
    from ui4me import ui
    assert callable(ui.app) and callable(ui.button) and callable(ui.theme)
    from ui4me._ui import core_compat
    assert core_compat.MAX_CORE_MAJOR == 1
    assert (ROOT / 'src/ui4me/_ui/assets/functional.css').is_file()
    assert (ROOT / 'src/ui4me/_ui/assets/theme.css').is_file()
