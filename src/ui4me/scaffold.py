"""Generate a complete single-language UI4ME project that runs as an ordinary script."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import sys


def slug(value: str) -> str:
    name = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_\t ")
    if not name or not name[0].isalpha():
        name = "app-" + (name or "demo")
    return name[:48]


def templates(name: str, *, language: str) -> dict[str, str]:
    if not name.strip() or any(ord(c) < 32 for c in name) or len(name) > 128:
        raise ValueError("Project name must be nonempty, <=128 chars, without control characters")
    if language not in ("python", "powershell"):
        raise ValueError("Language must be python or powershell")
    label = name.strip()
    safe_label = html.escape(label, quote=True)
    css = '''body { margin: 0; font-family: system-ui, sans-serif; }
.u4-app { max-width: 920px; margin: 0 auto; }
'''
    if language == "python":
        code = '''"""A UI4ME desktop app; run `python app.py` or `uv run app.py`."""
from ui4me import ui


def main() -> None:
    with ui.app(%r, width=800, height=560) as app:
        clicks = ui.state(0)
        ui.heading(%r, level=1)
        ui.text("Native HTML/CSS desktop UI. No JavaScript or browser runtime.")

        def add_click(event):
            clicks.set(clicks.value + 1)

        with ui.row():
            ui.button("Click me", on_click=add_click)
            ui.text(lambda: f"Clicks: {clicks.value}")

    app.run()


if __name__ == "__main__":
    main()
''' % (label, label)
        return {
            "app.py": code,
            "pyproject.toml": '[project]\nname = ' + json.dumps(slug(label)) +
                              '\nversion = "0.1.0"\nrequires-python = ">=3.11"\n' +
                              'dependencies = ["ui4me>=2.1.0,<3"]\n',
            "README.md": f"# {label}\n\nRun with `uv run app.py` after `uv sync`, or `python app.py` in an environment with UI4ME installed.\n",
        }
    ps = '''$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title '%s' -Content {
    $count = New-UI4MEState -Value 0
    New-UI4MEHeading -Text '%s' -Level 1
    New-UI4METext -Text 'Native HTML/CSS desktop UI. No JavaScript or Python runtime.'
    New-UI4MERow -Content {
        New-UI4MEButton -Text 'Click me' -OnClick { $count.Set([int]$count.Value + 1) }
        New-UI4METext -Bind $count
    }
}
''' % (label.replace("'", "''"), label.replace("'", "''"))
    return {"app.ps1": ps,
            "README.md": f"# {label}\n\nRun with `pwsh -File ./app.ps1` (or `powershell.exe -File .\\app.ps1` on Windows PowerShell 5.1).\nInstall the `UI4ME` module and its `UI4ME.Core` dependency first.\n"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path, help="New directory for the project")
    ap.add_argument("--name", default="UI4ME App")
    ap.add_argument("--language", choices=("python", "powershell"), default="python")
    args = ap.parse_args(argv)
    target = args.path.expanduser()
    try:
        files = templates(args.name, language=args.language)
        if target.exists():
            if not target.is_dir() or any(target.iterdir()):
                raise FileExistsError(f"Refusing to overwrite existing directory: {target}")
        else:
            target.mkdir(parents=True)
        for name, body in files.items():
            (target / name).write_text(body, encoding="utf-8")
        print(f"Created {args.language} app at {target.resolve()}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
