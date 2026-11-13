"""One-command host-backed launcher for Python UI4ME scripts.

Core 1.0 *requires* a native host-created IPC environment. The launcher writes
only a transient host manifest and does not shadow a host feature or embed a
browser. The app runs as a separate host-managed backend process.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def _toml(s: str) -> str:
    # JSON double-quoted strings are a strict subset of TOML basic strings.
    import json
    return json.dumps(s, ensure_ascii=False)


def build_manifest(script: str | Path, *, program: str | Path, app_id: str, title: str,
                   script_args: list[str] | tuple[str, ...] = ()) -> str:
    src = Path(script).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', app_id):
        raise ValueError('app id may contain only ASCII letters, digits, dots, hyphens and underscores')
    return ('[app]\n'
            f'id = {_toml(app_id)}\nname = {_toml(title)}\nversion = "2.0.0"\n\n'
            '[backend]\n'
            f'program = {_toml(str(program))}\n'
            f'args = [{", ".join(_toml(a) for a in ["-m", "ui4me._bootstrap", str(src), *script_args])}]\n'
            f'cwd = {_toml(str(src.parent))}\n\n'
            '[host]\nstartup_timeout_ms = 30000\nshutdown_timeout_ms = 5000\n'
            'max_windows = 16\ninstance = "multiple"\n')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='ui4me-run', description='Run a UI4ME 2 app through the Core native host')
    ap.add_argument('script', help='Python script containing `from ui4me import ui`')
    ap.add_argument('--title', default=None)
    ap.add_argument('--app-id', default='org.ui4me.UserApp')
    ap.add_argument('--headless', action='store_true',
                    help='test mode: run through the real host without a desktop window '
                         '(protocol, DOM and lifecycle only; no native input, focus or dialogs)')
    ap.add_argument('script_args', nargs=argparse.REMAINDER, help='arguments passed to the script')
    args = ap.parse_args(argv)
    script = Path(args.script).expanduser().resolve()
    from ui4me_core import host_binary
    manifest = build_manifest(script, program=sys.executable, app_id=args.app_id,
                              title=args.title or script.stem.replace('_', ' ').title(),
                              script_args=args.script_args)
    command = [str(host_binary()), 'run']
    if args.headless:
        command.append('--headless')
    with tempfile.TemporaryDirectory(prefix='ui4me-run-') as folder:
        conf = Path(folder) / 'app.toml'
        conf.write_text(manifest, encoding='utf-8')
        return subprocess.call([*command, '--app', str(conf)], env=os.environ.copy())


if __name__ == '__main__':
    raise SystemExit(main())
