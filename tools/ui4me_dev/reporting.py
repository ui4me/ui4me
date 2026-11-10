"""Conservative summaries of recorded test evidence."""
from __future__ import annotations

import html
import os
from pathlib import Path

from .common import ROOT, DevError, load_manifest, output_path, read_json, sha256, source_id

SCENARIOS = {
    "F01": "Clean package installation", "F02": "Native startup",
    "F03": "Input and application state", "F04": "Window lifetime",
    "F05": "Close interception and shutdown", "F06": "Thread ownership",
    "F07": "Cancellation and shutdown races", "F08": "Same-process runtime reuse",
    "F09": "ABI and callback lifetime", "F10": "Queue bounds and resources",
    "F11": "Resource paths and diagnostics", "F12": "Release and upgrade",
}
PLATFORMS = ("linux-x64", "win-x64")
BINDINGS = ("python", "powershell")
VALID = {"passed", "failed", "blocked", "interrupted", "not_run"}
INSTALLED_SCENARIOS = {"F01", "F09", "F11", "F12"}


def receipts() -> list[tuple[Path, dict]]:
    entries = []
    for path in (ROOT / "build/reports").glob("*/run.json"):
        try:
            data = read_json(path)
            if data.get("kind") == "test":
                entries.append((path, data))
        except (OSError, ValueError):
            continue
    return sorted(entries, key=lambda pair: (pair[1].get("started_at", ""), str(pair[0])))


def matrix(entries: list[tuple[Path, dict]], *, manifest_hash: str | None = None, current: bool = False) -> dict:
    result = {(p, b, f): [] for p in PLATFORMS for b in BINDINGS for f in SCENARIOS}
    identity = source_id() if current else None
    for path, run in entries:
        if manifest_hash is not None and run.get("manifest_sha256") != manifest_hash:
            continue
        if identity is not None and run.get("source_id") != identity:
            continue
        # A failed or incomplete run cannot confer a passing scenario.
        for case in run.get("cases", []):
            key = (run.get("platform"), run.get("binding"), case.get("id"))
            if key not in result:
                continue
            expected_suite = "installed" if key[2] in INSTALLED_SCENARIOS else "native"
            if run.get("suite") != expected_suite:
                continue
            status = case.get("status", "not_run")
            if status not in VALID:
                status = "failed"
            if status == "passed" and run.get("status") != "passed":
                status = run.get("status") if run.get("status") in VALID else "failed"
            result[key].append((status, path, case.get("details", "")))
    return result


def report(out: Path) -> None:
    out = output_path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = matrix(receipts())
    lines = ["# Foundation evidence overview", "", "This overview includes local receipts, including evidence from older source revisions. It is not release qualification. Missing evidence is not a pass.", "", "| Scenario | Platform | Binding | Latest attempt | Last success |", "| --- | --- | --- | --- | --- |"]
    html_rows = []
    for (platform, binding, scenario), history in rows.items():
        latest = history[-1][0] if history else "not_run"
        latest_link = os.path.relpath(history[-1][1], out).replace(os.sep, "/") if history else None
        success_path = next((p for status, p, _ in reversed(history) if status == "passed"), None)
        success_link = os.path.relpath(success_path, out).replace(os.sep, "/") if success_path else None
        latest_md = f"[{latest}]({latest_link})" if latest_link else latest
        success_md = f"[receipt]({success_link})" if success_link else "none"
        lines.append(f"| {scenario} {SCENARIOS[scenario]} | {platform} | {binding} | {latest_md} | {success_md} |")
        latest_html = f'<a href="{html.escape(latest_link, quote=True)}">{html.escape(latest)}</a>' if latest_link else html.escape(latest)
        success_html = f'<a href="{html.escape(success_link, quote=True)}">receipt</a>' if success_link else "none"
        html_rows.append(f"<tr><td>{scenario} {html.escape(SCENARIOS[scenario])}</td><td>{platform}</td><td>{binding}</td><td>{latest_html}</td><td>{success_html}</td></tr>")
    lines += ["", "Published-release evidence: none recorded by this tool.", ""]
    content = "\n".join(lines)
    (out / "index.md").write_text(content, encoding="utf-8")
    page = ('<!doctype html><html><head><meta charset="utf-8"><title>ui4me evidence</title></head><body>'
            '<h1>Foundation evidence overview</h1><p>Local receipts may be from older source revisions. This is not release qualification.</p>'
            '<table><thead><tr><th>Scenario</th><th>Platform</th><th>Binding</th><th>Latest attempt</th><th>Last success</th></tr></thead><tbody>'
            + "\n".join(html_rows) + '</tbody></table><p>Published-release evidence: none recorded by this tool.</p></body></html>\n')
    (out / "index.html").write_text(page, encoding="utf-8")
    print(out / "index.md")


def qualify(manifest_path: Path) -> bool:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    if manifest.get("platform") != "combined" or manifest.get("profile") != "release":
        raise DevError("Qualification requires the combined release manifest")
    rows = matrix(receipts(), manifest_hash=sha256(manifest_path), current=True)
    missing = [(key, values[-1][0] if values else "not_run") for key, values in rows.items() if not values or values[-1][0] != "passed"]
    for (platform, binding, scenario), status in missing:
        print(f"{platform} {binding} {scenario}: {status}")
    print("NOT QUALIFIED" if missing else "QUALIFIED: complete matching evidence found")
    return not missing
