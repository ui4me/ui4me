"""Export local documentation and selected test evidence. Never pushes a repository.

Optional contributor dependency: python -m pip install Markdown==3.7
Run `python dev.py report` first to include the current acceptance overview.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/site"
STYLE = """
:root{color-scheme:light;--ink:#172330;--muted:#526170;--line:#dce4ea;--accent:#096775}
*{box-sizing:border-box}body{margin:0 auto;max-width:1100px;padding:36px 28px 70px;font:16px/1.65 system-ui;color:var(--ink)}
header{border-bottom:3px solid var(--accent);padding-bottom:20px;margin-bottom:32px}header a{font-size:23px;font-weight:700;text-decoration:none}
nav{margin:16px 0;color:var(--muted)}a{color:var(--accent)}h1,h2,h3{line-height:1.25;margin-top:36px}h1{font-size:32px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid var(--line);padding:11px;vertical-align:top;text-align:left}th{background:#edf4f6}
pre{background:#f3f6f8;border:1px solid var(--line);padding:16px;overflow:auto}code{font-size:.9em;overflow-wrap:anywhere}blockquote{border-left:3px solid var(--accent);padding-left:20px;color:var(--muted)}
.scroll{overflow:auto}img{max-width:100%;height:auto}footer{margin-top:42px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted);font-size:14px}
@media(max-width:600px){body{padding:22px 16px}h1{font-size:28px}table{font-size:12px}}
"""


def main() -> None:
    try:
        import markdown
    except ImportError as error:
        raise SystemExit("Install the optional exporter dependency: python -m pip install Markdown==3.7") from error
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    sources = [ROOT / "README.md", ROOT / "STATUS.md"]
    for directory in ("docs", "specs"):
        sources.extend(sorted((ROOT / directory).rglob("*.md")))
    sources.extend([ROOT / "bindings/python/README.md", ROOT / "bindings/powershell/README.md"])
    for source in sources:
        relative = source.relative_to(ROOT)
        target = OUT / relative.with_suffix(".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        content = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "toc"])
        def local_link(match):
            value = match.group(1)
            if not value.startswith(("https://", "http://", "mailto:", "#")):
                value = re.sub(r"\.md(?=#|$)", ".html", value)
            return 'href="' + value + '"'
        content = re.sub(r'href="([^"]+)"', local_link, content)
        home = Path(os.path.relpath(OUT / "index.html", target.parent)).as_posix()
        overview = Path(os.path.relpath(OUT / "evidence/overview/index.html", target.parent)).as_posix()
        title = source.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
        page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>' + STYLE + '</style></head><body><header><a href="' + home + '">ui4me</a><nav>Native application foundation · <a href="' + overview + '">Acceptance evidence</a></nav></header><main class="scroll">' + content + '</main><footer>Source documentation is maintained in <a href="https://github.com/ui4me/ui4me">ui4me/ui4me</a>. Compatibility claims depend on recorded acceptance.</footer></body></html>'
        target.write_text(page, encoding="utf-8")
    shutil.copy2(OUT / "README.html", OUT / "index.html")
    shutil.copy2(ROOT / "LICENSE", OUT / "LICENSE")
    evidence = ROOT / "build/reports"
    destination = OUT / "evidence"
    destination.mkdir()
    if evidence.exists():
        for source in evidence.rglob("*"):
            if source.is_file() and not source.is_symlink() and source.suffix.lower() in {".json", ".log", ".png", ".md", ".html", ".txt"}:
                target = destination / source.relative_to(evidence)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    if not (destination / "overview/index.html").exists():
        (destination / "overview").mkdir(exist_ok=True)
        (destination / "overview/index.html").write_text('<!doctype html><meta charset="utf-8"><title>Acceptance pending</title><h1>Acceptance not run</h1><p>Run python dev.py report and export again. No passing evidence was supplied with the source reconstruction.</p>', encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(OUT)
    print("Review this output, then copy it to the ui4me.github.io hosting repository. No publication was performed.")


if __name__ == "__main__":
    main()
