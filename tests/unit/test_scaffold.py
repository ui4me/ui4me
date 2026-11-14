"""New project generator must produce syntactically valid, directly runnable scripts."""
from __future__ import annotations
import ast
import tempfile
import tomllib
from pathlib import Path

import pytest
from ui4me import scaffold


def test_python_generates_plain_script_and_uv_project(tmp_path):
    files = scaffold.templates('A neat \'idea\' ✓', language='python')
    ast.parse(files['app.py'])
    assert "with ui.app(" in files['app.py']
    assert "if __name__ ==" in files['app.py']
    data = tomllib.loads(files['pyproject.toml'])
    assert 'ui4me>=2.1.0,<3' in data['project']['dependencies']
    assert scaffold.main([str(tmp_path / 'new'), '--name', 'A neat idea']) == 0
    assert (tmp_path / 'new/app.py').is_file()
    assert scaffold.main([str(tmp_path / 'new')]) == 2


def test_powershell_project_avoids_old_launcher(tmp_path):
    files = scaffold.templates("Ada's Tool", language='powershell')
    assert 'Invoke-UI4MEApp' in files['app.ps1']
    assert 'Start-UI4MEUiScript' not in files['app.ps1']
    assert "-Title 'Ada''s Tool'" in files['app.ps1']
    assert scaffold.main([str(tmp_path / 'ps'), '--language', 'powershell']) == 0
    assert (tmp_path / 'ps/app.ps1').is_file()


@pytest.mark.parametrize('name', ['', '\n', 'a' * 129])
def test_invalid_project_name_rejected(name):
    with pytest.raises(ValueError):
        scaffold.templates(name, language='python')
