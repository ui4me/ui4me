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
    assert project['version'] == '2.0.0'
    assert project['dependencies'] == ['ui4me-core>=1.0.0,<2.0.0']
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
    assert ui4me.__version__ == '2.0.0'
    assert 'ui' in ui4me.__all__


def test_powershell_ui_has_own_core_dependency_without_legacy_engine():
    manifest = (ROOT / 'powershell/UI4ME/UI4ME.psd1').read_text(encoding='utf8')
    module = (ROOT / 'powershell/UI4ME/UI4ME.psm1').read_text(encoding='utf8')
    assert "ModuleVersion = '2.0.0'" in manifest
    assert "ModuleName = 'UI4ME.Core'" in manifest
    assert 'Connect-UI4ME' in module
    assert 'Set-UI4MEReady' in module
    assert 'Wait-UI4ME' in module
    assert 'Start-UI4MEHost' in module
    assert 'Add-Type' not in module
    definitions = set(re.findall(r'^function\s+([A-Za-z0-9-]+)\s*\{', module, flags=re.M))
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
