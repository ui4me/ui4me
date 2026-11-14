"""Skill installers should preserve unrelated/unmanaged content and protect symlinks."""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from ui4me import skills


def test_sources_and_supported_agents():
    src = skills.skill_source()
    assert (src / 'SKILL.md').exists()
    assert skills.hash_files(src)['SKILL.md']
    assert len(skills.AGENTS) == 6


def test_install_update_status_and_uninstall(tmp_path):
    source = skills.skill_source()
    target = tmp_path / '.claude/skills/ui4me-ui-python'
    assert skills.status(target) == 'missing'
    assert skills.install(source, target) == 'installed'
    assert skills.status(target) == 'installed'
    assert skills.install(source, target) == 'updated'
    assert skills.uninstall(target) == 'removed'
    assert skills.status(target) == 'missing'


def test_modified_and_unmanaged_folders_protected(tmp_path):
    source = skills.skill_source()
    target = tmp_path / 'x/ui4me-ui-python'
    target.mkdir(parents=True)
    (target / 'notes.txt').write_text('mine')
    with pytest.raises(FileExistsError):
        skills.install(source, target)
    with pytest.raises(FileExistsError):
        skills.uninstall(target)
    assert (target / 'notes.txt').read_text() == 'mine'
    assert skills.install(source, target, force=True) == 'updated'
    (target / 'SKILL.md').write_text('edited by owner')
    assert skills.status(target) == 'modified'
    with pytest.raises(FileExistsError):
        skills.uninstall(target)
    assert skills.uninstall(target, force=True) == 'removed'


def test_project_and_user_agent_paths(tmp_path):
    p = skills.locations(('claude', 'codex'), 'project', project=tmp_path)
    assert p['claude'] == tmp_path.resolve() / '.claude/skills/ui4me-ui-python'
    assert p['codex'] == tmp_path.resolve() / '.agents/skills/ui4me-ui-python'
    u = skills.locations(('opencode',), 'user', home=tmp_path)
    assert u['opencode'] == tmp_path / '.config/opencode/skills/ui4me-ui-python'


def test_symlink_refused(tmp_path):
    link = tmp_path / 'link'
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Cannot create symlinks')
    with pytest.raises(ValueError):
        skills.install(skills.skill_source(), link / 'skills/ui4me-ui-python')
