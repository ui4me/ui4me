"""Run the documented quickstarts on the real Core host (headless), exactly as published.

Each Python block in README.md and docs/guides/quickstart-python.md is saved as app.py
and started directly (``python app.py`` -> Core ``Application.start``) with
``UI4ME_UI_SMOKE`` so it stops by itself; it must exit 0 without reported errors. The
README quickstart is also driven: type a name, press Greet, read the greeting from the
real Core document. PowerShell quickstart blocks run with ``pwsh -File`` when pwsh and
the UI4ME / UI4ME.Core modules are importable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ui4me_core = pytest.importorskip("ui4me_core")
ROOT = Path(__file__).resolve().parents[2]
try:
    HOST = ui4me_core.host_binary()
except Exception:  # pragma: no cover - no packaged host
    HOST = None
pytestmark = pytest.mark.skipif(HOST is None or not Path(str(HOST)).exists(), reason="Core host binary not installed")


def blocks(path: Path, language: str) -> list[str]:
    if not path.is_file():  # tests copied outside the repository (CI consumer check)
        return []
    return re.findall(rf"```{language}\n(.*?)```", path.read_text(encoding="utf-8"), re.S)


def app_blocks(language: str) -> list[tuple[str, str]]:
    found = []
    for doc in ("README.md", "docs/guides/quickstart-python.md", "docs/guides/quickstart-powershell.md"):
        for index, code in enumerate(blocks(ROOT / doc, language)):
            # Complete programs only; fragments that continue an earlier block are skipped.
            runnable = (("from ui4me import ui" in code and "ui.app(" in code and "app.run()" in code)
                        if language == "python" else ("Import-Module UI4ME" in code and "Invoke-UI4MEApp" in code))
            if runnable:
                found.append((f"{doc}#{index}", code))
    return found


def headless_env(**extra) -> dict:
    env = dict(os.environ, UI4ME_TEST_MODE="1", **extra)
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("DISPLAY", None)
    return env


@pytest.mark.parametrize("name,code", app_blocks("python"), ids=lambda v: v if isinstance(v, str) and "#" in v else None)
def test_python_quickstart_block_runs_directly(tmp_path, name, code):
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    proc = subprocess.run([sys.executable, "app.py"], cwd=tmp_path, capture_output=True, text=True,
                          timeout=90, env=headless_env(UI4ME_UI_SMOKE="1.5"))
    assert proc.returncode == 0, f"{name} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-3000:]}"


def test_readme_python_quickstart_greets(tmp_path):
    code = next((c for n, c in app_blocks("python") if n.startswith("README.md")), None)
    if code is None:
        pytest.skip("README.md is not next to these tests")
    driver = textwrap.dedent("""
        import json, os, runpy, sys
        from ui4me._ui.app import UiApp
        from ui4me._ui.testing import Pilot
        from ui4me._ui.components.basic import Button, TextField, Text
        # Core rebuilds the backend command from __main__ (app.py under runpy) and puts it in
        # the first argument slot: take app.py as that argument and the output path from env.
        OUT = os.environ["UI4ME_DOCS_OUT"]
        _run = UiApp.run
        def run(self):
            UiApp.run = _run
            def walk(component):
                yield component
                for child in list(getattr(component, "_children", ()) or ()):
                    yield from walk(child)
            def script(p):
                parts = list(walk(self.main.root))
                field = next(c for c in parts if isinstance(c, TextField))
                greet = next(c for c in parts if isinstance(c, Button)
                             and "Greet" in self.main.core.document.get_text(c.root.id))
                p.type(field, "Ada")
                p.click(greet)
                doc = self.main.core.document
                texts = [doc.get_text(c.root.id) for c in parts if type(c) is Text]
                json.dump({"texts": texts}, open(OUT, "w"))
            Pilot(self).run(script)
        UiApp.run = run
        sys.argv = [sys.argv[1]]
        runpy.run_path(sys.argv[0], run_name="__main__")
    """)
    (tmp_path / "app.py").write_text(code, encoding="utf-8")
    (tmp_path / "drive.py").write_text(driver, encoding="utf-8")
    out = tmp_path / "out.json"
    proc = subprocess.run([sys.executable, "drive.py", "app.py"], cwd=tmp_path, capture_output=True, text=True,
                          timeout=90, env=headless_env(UI4ME_DOCS_OUT=str(out)))
    assert proc.returncode == 0 and out.exists(), proc.stdout[-2000:] + proc.stderr[-3000:]
    import json
    assert "Hello, Ada!" in json.loads(out.read_text(encoding="utf-8"))["texts"]


def _pwsh_ready() -> bool:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        return False
    probe = subprocess.run([pwsh, "-NoProfile", "-Command", "Import-Module UI4ME -ErrorAction Stop; 'ok'"],
                           capture_output=True, text=True, timeout=120)
    return proc_ok(probe)


def proc_ok(proc) -> bool:
    return proc.returncode == 0 and "ok" in proc.stdout


@pytest.mark.skipif(not _pwsh_ready(), reason="pwsh with the UI4ME module is not available")
@pytest.mark.parametrize("name,code", app_blocks("powershell"), ids=lambda v: v if isinstance(v, str) and "#" in v else None)
def test_powershell_quickstart_block_runs_directly(tmp_path, name, code):
    script = tmp_path / "app.ps1"
    script.write_bytes(b"\xef\xbb\xbf" + code.encode("utf-8"))
    proc = subprocess.run([shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-File", str(script)], cwd=tmp_path,
                          capture_output=True, text=True, timeout=120, env=headless_env(UI4ME_UI_SMOKE="1.5"),
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, f"{name} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-3000:]}"
