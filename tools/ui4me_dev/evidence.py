from __future__ import annotations

import html
import os
import shutil
import subprocess
from pathlib import Path

from .common import ROOT, DevError, find_artifact, load_manifest, now, output_path, read_json, revision, sha256, source_id, write_json
from .packages import require_locks
from .testing import NATIVE
from .validation import proof_errors, upgrade_errors


def catalog() -> list[dict]:
    return read_json(ROOT / "quality/scenarios.json")["scenarios"]


def receipts(directory: Path | None = None) -> list[tuple[Path, dict]]:
    values = []
    for path in (directory or ROOT / "build/reports").rglob("run.json"):
        try:
            data = read_json(path)
        except (OSError, ValueError) as error:
            raise DevError(f"Unreadable evidence {path}: {error}") from error
        if data.get("schema") != 1 or data.get("kind") != "test":
            raise DevError(f"Unknown receipt format: {path}")
        values.append((path, data))
    return sorted(values, key=lambda pair: (pair[1].get("started_at", ""), pair[1].get("id", "")))


def observation_rows(values: list[tuple[Path, dict]], source: str, manifest_hash: str | None = None) -> list[dict]:
    rows = []
    for platform in ("linux-x64", "win-x64"):
        for binding in ("python", "powershell"):
            for scenario in catalog():
                selected = []
                for path, data in values:
                    if data.get("phase", "candidate") != "candidate":
                        continue
                    if (data.get("platform"), data.get("binding"), data.get("source_id")) != (platform, binding, source):
                        continue
                    if data.get("suite") != scenario["suite"]:
                        continue
                    if manifest_hash is not None and data.get("manifest_sha256") != manifest_hash:
                        continue
                    matches = [c for c in data.get("cases", []) if c.get("id") == scenario["id"]]
                    if len(matches) > 1:
                        raise DevError(f"Duplicate scenario in {path}")
                    case = matches[0] if matches else {"id": scenario["id"], "status": "not_run", "details": "No scenario observation in latest attempt"}
                    selected.append((path, data, case))
                latest = selected[-1] if selected else None
                success = next((record for record in reversed(selected) if record[2].get("status") == "passed" and record[1].get("status") == "passed"), None)
                status = latest[2].get("status", "not_run") if latest else "not_run"
                if latest and latest[1].get("status") in {"running", "interrupted", "failed", "blocked"}:
                    status = "interrupted" if latest[1].get("status") == "running" else latest[1]["status"]
                rows.append({"platform": platform, "binding": binding, "scenario": scenario, "status": status, "latest": latest, "last_success": success})
    return rows


def attest(run_path: Path, scenario: str, status: str, notes: str, operator: str, screenshot: Path | None, capture_kind: str) -> None:
    run_path = run_path.resolve()
    data = read_json(run_path)
    if data.get("suite") != "native" or data.get("backend") != "native" or not data.get("native_session_completed"):
        raise DevError("Attestation requires a completed native consumer session from test --suite native")
    if data.get("source_id") != source_id() or scenario not in NATIVE:
        raise DevError("Stale source or unknown native scenario")
    if not operator.strip() or len(notes.strip()) < 40:
        raise DevError("Provide an operator name and meaningful expected/actual observations (at least 40 characters)")
    cases = [c for c in data["cases"] if c["id"] == scenario]
    if len(cases) != 1:
        raise DevError("Scenario must occur exactly once in run")
    evidence = None
    if status == "passed" and screenshot is None:
        raise DevError("A passed native observation requires an actual desktop PNG screenshot")
    if screenshot:
        screenshot = screenshot.resolve()
        if capture_kind != "desktop" or screenshot.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" or screenshot.stat().st_size > 10 * 1024 * 1024:
            raise DevError("Provide a desktop PNG capture at most 10 MiB")
        renderer_hashes = {s.get("sha256") for s in data.get("renderer_snapshots", [])}
        renderer_hashes.add(data.get("renderer_snapshot", {}).get("sha256"))
        if sha256(screenshot) in renderer_hashes:
            raise DevError("Renderer output cannot be attested as an OS desktop capture")
        target = run_path.parent / (scenario + "-desktop.png")
        if screenshot != target:
            shutil.copy2(screenshot, target)
        evidence = {"path": target.name, "sha256": sha256(target), "native_capture": True, "capture_kind": "operator_desktop"}
    case = cases[0]
    case.update(status=status, details=notes.strip(), attestation={"operator": operator.strip(), "recorded_at": now(), "trust": "human_review", "scope": "Operator attests this scenario was exercised on the exact native candidate; screenshot alone is not proof of behavior."})
    if evidence:
        case["screenshot"] = evidence
    states = {c["status"] for c in data["cases"]}
    data["status"] = "passed" if states == {"passed"} else "failed" if "failed" in states else "blocked" if "blocked" in states else "not_run"
    data["finished_at"] = now()
    write_json(run_path, data)
    print(run_path)


def evidence_errors(path: Path, data: dict, case: dict) -> list[str]:
    errors = []
    if not data.get("proof_files"):
        errors.append(f"Missing supporting proof: {path}")
    for item in data.get("proof_files", []):
        proof = (path.parent / item["path"]).resolve()
        if not proof.is_relative_to(path.parent.resolve()) or not proof.is_file() or sha256(proof) != item["sha256"]:
            errors.append(f"Changed supporting proof: {path} {item['path']}")
    consumer = path.parent / "consumer.json"
    if not consumer.is_file() or sha256(consumer) != data.get("consumer_sha256"):
        errors.append(f"Consumer proof missing or changed: {path}")
    if data.get("suite") == "native":
        shot = case.get("screenshot", {})
        name = shot.get("path", "")
        image = (path.parent / name).resolve()
        if not name or not image.is_relative_to(path.parent.resolve()) or not image.is_file() or sha256(image) != shot.get("sha256") or not shot.get("native_capture"):
            errors.append(f"Missing or changed native desktop evidence: {case['id']} {path}")
        if not case.get("attestation", {}).get("operator"):
            errors.append(f"Missing operator attestation: {path}")
    elif data.get("suite") == "installed":
        checks = data.get("installation_checks", {})
        if not checks.get("missing_payload_rejected") or not checks.get("exact_candidate_reinstalled"):
            errors.append(f"Missing negative-loader or exact-reinstall acceptance: {path}")
    return errors


def qualify(manifest_path: Path, reviewer: str | None = None, review_url: str | None = None, *, save: bool = True) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    errors = []
    try:
        require_locks("all")
    except DevError as error:
        errors.append(str(error))
    if manifest.get("platform") != "combined" or manifest.get("profile") != "release":
        errors.append("Qualification requires the combined release candidate")
    if manifest.get("git_revision") == "uncommitted":
        errors.append("Release candidate requires a committed Git revision")
    if manifest.get("git_revision") != revision():
        errors.append("Release manifest revision differs from current HEAD")
    try:
        state = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, capture_output=True, text=True, timeout=15)
        if state.returncode or state.stdout.strip():
            errors.append("Qualification requires a clean tracked source checkout")
        locks = subprocess.run(["git", "ls-files", "--error-unmatch", "Cargo.lock", "bindings/powershell/Ui4me.Managed/packages.lock.json"], cwd=ROOT, capture_output=True, text=True, timeout=15)
        if locks.returncode:
            errors.append("Both dependency lock files must be tracked in Git")
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"Cannot verify Git provenance: {error}")
    values = [(p, d) for p, d in receipts() if d.get("phase", "candidate") == "candidate"]
    rows = observation_rows(values, manifest["source_id"], sha256(manifest_path))
    references = {}
    upgrade_failures, upgrade_paths = upgrade_errors(values, manifest, sha256(manifest_path))
    errors.extend(upgrade_failures)
    for path in upgrade_paths:
        references[path.relative_to(ROOT).as_posix()] = sha256(path)
    for row in rows:
        key = f"{row['platform']}/{row['binding']}/{row['scenario']['id']}"
        if row["status"] != "passed":
            errors.append(f"{key}: {row['status']}")
        if row["latest"]:
            path, data, case = row["latest"]
            if data.get("status") != "passed":
                errors.append(f"Acceptance run incomplete or unsuccessful: {key}")
            expected_artifact = find_artifact(manifest, "python-wheel", row["platform"]) if row["binding"] == "python" else find_artifact(manifest, "powershell-package")
            if data.get("consumed_artifact") != expected_artifact:
                errors.append(f"Consumed package differs from manifest: {key}")
            errors.extend(evidence_errors(path, data, case))
            references[path.relative_to(ROOT).as_posix()] = sha256(path)
    # Latest unit attempt for each required host/binding must pass, even if an older run was green.
    for platform in ("linux-x64", "win-x64"):
        for binding in ("core", "python", "powershell", "tools"):
            matching = [(p, d) for p, d in values if (d.get("source_id"), d.get("platform"), d.get("binding"), d.get("suite")) == (manifest["source_id"], platform, binding, "unit")]
            if not matching or matching[-1][1].get("status") != "passed" or not matching[-1][1].get("cases") or matching[-1][1].get("test_count", 0) <= 0:
                errors.append(f"Latest unit suite not passed: {platform}/{binding}")
            else:
                path, unit_data = matching[-1]
                if any(case.get("status") != "passed" for case in unit_data["cases"]):
                    errors.append(f"Unit suite contains a non-passing case: {platform}/{binding}")
                errors.extend(proof_errors(path, unit_data))
                references[path.relative_to(ROOT).as_posix()] = sha256(path)
        sdk_runs = [(p, d) for p, d in values if (d.get("source_id"), d.get("manifest_sha256"), d.get("platform"), d.get("binding"), d.get("suite")) == (manifest["source_id"], sha256(manifest_path), platform, "core", "installed")]
        if not sdk_runs or sdk_runs[-1][1].get("status") != "passed" or not sdk_runs[-1][1].get("cases"):
            errors.append(f"Installed C SDK consumer not passed: {platform}")
        else:
            path, sdk_data = sdk_runs[-1]
            if sdk_data.get("consumed_artifact") != find_artifact(manifest, "native-sdk", platform) or not sdk_data.get("proof_files"):
                errors.append(f"Missing or mismatched C SDK proof: {path}")
            errors.extend(proof_errors(path, sdk_data))
            references[path.relative_to(ROOT).as_posix()] = sha256(path)
    if not reviewer or not review_url or not review_url.startswith("https://github.com/"):
        errors.append("Explicit release reviewer and HTTPS GitHub review/run URL required")
    result = {"schema": 1, "status": "qualified" if not errors else "blocked", "source_id": manifest["source_id"], "manifest_sha256": sha256(manifest_path), "reviewer": reviewer, "review_url": review_url, "recorded_at": now(), "trust_boundary": "Maintainer reviews trusted workflow origin and manual observations; JSON hashes do not authenticate human claims.", "evidence": [{"path": path, "sha256": digest} for path, digest in sorted(references.items())], "errors": errors}
    if save:
        write_json(manifest_path.parent / "qualification.json", result)
    return result


def require_qualified(manifest_path: Path) -> dict:
    saved_path = manifest_path.resolve().parent / "qualification.json"
    if not saved_path.is_file():
        raise DevError("No qualification record. Run qualify after collecting the complete matrix.")
    saved = read_json(saved_path)
    current = qualify(manifest_path, saved.get("reviewer"), saved.get("review_url"), save=False)
    if saved.get("status") != "qualified" or current["status"] != "qualified" or saved.get("manifest_sha256") != current["manifest_sha256"]:
        raise DevError("Release qualification absent, stale or incomplete: " + "; ".join(current["errors"][:8]))
    if saved.get("evidence") != current["evidence"]:
        raise DevError("Evidence changed after qualification; review and qualify again")
    return current


def report(destination: Path, manifest_path: Path | None = None) -> Path:
    destination = output_path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_hash = sha256(manifest_path) if manifest_path else None
    if manifest_path:
        load_manifest(manifest_path)
    values = receipts()
    rows = observation_rows(values, source_id(), manifest_hash)
    lines = ["# ui4me acceptance overview", "", f"Generated: {now()}", "", f"Source: `{source_id()}`", "", "Latest attempts determine status. An earlier pass never overrides a later failed, interrupted or missing attempt. Native screenshots are operator evidence; renderer snapshots alone are not desktop proof.", "", "| Platform | Binding | Requirement | Status | Latest | Last pass | Screenshot |", "| --- | --- | --- | --- | --- | --- | --- |"]
    html_rows = []
    image_sections = []
    for row in rows:
        latest = row["latest"]
        old = row["last_success"]
        path = latest[0] if latest else None
        latest_link = Path(os.path.relpath(path, destination)).as_posix() if path else ""
        old_link = Path(os.path.relpath(old[0], destination)).as_posix() if old else ""
        shot_link = ""
        shot_label = ""
        if latest:
            shot = latest[2].get("screenshot") or latest[1].get("renderer_snapshot")
            if shot:
                shot_link = Path(os.path.relpath(path.parent / shot["path"], destination)).as_posix()
                shot_label = "desktop capture" if shot.get("native_capture") else "renderer snapshot (not desktop)"
        requirement = row["scenario"]["id"] + " " + row["scenario"]["title"]
        shot_md = f"[{shot_label}]({shot_link})" if shot_link else "—"
        lines.append(f"| {row['platform']} | {row['binding']} | {requirement} | {row['status']} | " + (f"[run]({latest_link})" if latest_link else "—") + " | " + (f"[run]({old_link})" if old_link else "—") + f" | {shot_md} |")
        h = html.escape
        preview = f'<a href="{h(shot_link)}"><img src="{h(shot_link)}" alt="{h(requirement)} {h(shot_label)}" loading="lazy"></a><br>{h(shot_label)}' if shot_link else "No capture"
        html_rows.append(f'<tr data-status="{h(row["status"])}"><td>{h(row["platform"])}</td><td>{h(row["binding"])}</td><td><strong>{h(requirement)}</strong><br>{h(row["scenario"]["acceptance"])}</td><td>{h(row["status"])}</td><td>' + (f'<a href="{h(latest_link)}">Latest receipt</a>' if latest_link else "Not run") + f'</td><td>{preview}</td></tr>')
        if shot_link:
            image_sections += ["", f"### {row['platform']} · {row['binding']} · {requirement}", "", f"![{requirement} {shot_label}]({shot_link})", ""]
    lines += image_sections
    (destination / "overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ui4me acceptance overview</title><style>body{font:16px/1.5 system-ui;margin:0;background:#f3f5f8;color:#152338}main{max-width:1300px;margin:auto;padding:32px}h1{font-size:32px}table{width:100%;border-collapse:collapse;background:white}td,th{padding:14px;border-bottom:1px solid #dce2e9;text-align:left;vertical-align:top}td:nth-child(3){max-width:420px}img{max-width:180px;max-height:140px}code{overflow-wrap:anywhere}select{padding:8px;margin:16px 0}tr[data-status=passed] td:nth-child(4){color:#07693d}tr[data-status=failed] td:nth-child(4){color:#b12c2c}@media(max-width:700px){main{padding:12px}.scroll{overflow:auto}table{min-width:780px}}@media print{select{display:none}main{padding:0}}</style><main><h1>ui4me acceptance overview</h1><p>Latest attempts, exact source, explicit missing coverage.</p><p>Source <code>''' + html.escape(source_id()) + '''</code></p><p>Results shown are for the current source. A renderer snapshot does not prove desktop behavior.</p><label>Filter <select id="status"><option value="">All observations</option><option>passed</option><option>failed</option><option>blocked</option><option>not_run</option><option>interrupted</option></select></label><div class="scroll"><table><thead><tr><th>Platform</th><th>Binding</th><th>Requirement</th><th>Status</th><th>Evidence</th><th>Capture</th></tr></thead><tbody>''' + "".join(html_rows) + '''</tbody></table></div></main><script>document.getElementById('status').addEventListener('change',function(){for(const row of document.querySelectorAll('tbody tr'))row.hidden=!!this.value&&row.dataset.status!==this.value})</script></html>'''
    (destination / "index.html").write_text(document, encoding="utf-8")
    print(destination / "index.html")
    return destination / "index.html"
