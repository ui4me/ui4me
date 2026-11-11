from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .common import ROOT, DevError, find_artifact, host, load_manifest, normalized_bytes, now, output_path, sha256, source_files, source_id, version, write_json
from .evidence import require_qualified
from .process import run
from .testing import installed


def source_zip(destination: Path) -> Path:
    destination = output_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = sorted(source_files())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            entry = zipfile.ZipInfo("ui4me/" + path.relative_to(ROOT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
            archive.writestr(entry, normalized_bytes(path))
    destination.with_suffix(destination.suffix + ".sha256").write_text(sha256(destination) + "  " + destination.name + "\n", encoding="utf-8")
    write_json(destination.with_suffix(destination.suffix + ".json"), {"source_id": source_id(), "files": len(paths), "sha256": sha256(destination), "status": "source_only", "execution_claim": "Creating a source archive does not compile or test its contents."})
    print(destination)
    return destination


def publish(manifest_path: Path, registry: str, execute: bool) -> None:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    qualification = require_qualified(manifest_path)
    folder = ROOT / "build/publish" / registry
    folder.mkdir(parents=True, exist_ok=True)
    if registry in {"pypi", "testpypi"}:
        wheels = [str(manifest_path.parent / a["path"]) for a in manifest["artifacts"] if a["kind"] == "python-wheel"]
        command = [sys.executable, "-m", "twine", "upload", "--non-interactive", "--repository", registry, *wheels]
        note = "CI should use PyPI Trusted Publishing; this explicit CLI route uses TWINE_USERNAME/TWINE_PASSWORD supplied by the operator."
    elif registry == "powershell":
        package = find_artifact(manifest, "powershell-package")
        command = ["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts/publish-powershell.ps1"), "-PackagePath", str(manifest_path.parent / package["path"])]
        note = "PSGALLERY_API_KEY is read from the environment by the publisher, never passed in command arguments."
    elif registry == "github":
        notes = folder / "release-notes.md"
        native_note = "Full native desktop acceptance was not run under the CI-only release policy.\n\n" if qualification.get("policy") == "ci" else ""
        notes.write_text(f"# ui4me {manifest['version']}\n\nSource `{manifest['source_id']}`.\n\n{native_note}See the supplied manifest and qualification record for exact artifact identity and acceptance.\n", encoding="utf-8")
        assets = [str(manifest_path.parent / a["path"]) for a in manifest["artifacts"]]
        assets += [str(manifest_path), str(manifest_path.parent / "qualification.json")]
        evidence_zip = folder / f"ui4me-{version()}-evidence.zip"
        with zipfile.ZipFile(evidence_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in qualified_evidence_files(qualification):
                archive.write(item, item.relative_to(ROOT).as_posix())
        assets.append(str(evidence_zip))
        command = ["gh", "release", "create", "v" + manifest["version"], "--repo", "ui4me/ui4me", "--verify-tag", "--title", "ui4me " + manifest["version"], "--notes-file", str(notes), *assets]
        note = "The version tag must already identify the reviewed commit; existing assets are not overwritten."
    else:
        raise DevError("Unknown registry")
    print(json.dumps({"execute": execute, "registry": registry, "command": command, "note": note}, indent=2))
    if execute:
        if registry in {"pypi", "testpypi"}:
            pending = python_upload_plan(manifest_path, registry, folder / "existing")
            if not pending:
                write_json(folder / "publish.json", {"registry": registry, "manifest_sha256": sha256(manifest_path), "time": now(), "status": "already_published_identical", "note": "Public bytes were downloaded and matched; no upload attempted."})
                print("All qualified wheels are already published with identical bytes. Run verify for consumer verification.")
                return
            command = [sys.executable, "-m", "twine", "upload", "--non-interactive", "--repository", registry, *[str(p) for p in pending]]
        if registry == "powershell":
            item = find_artifact(manifest, "powershell-package")
            existing = folder / "existing.nupkg"
            try:
                download(f"https://www.powershellgallery.com/api/v2/package/Ui4me/{manifest['version']}", existing)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
            else:
                if sha256(existing) != item["sha256"]:
                    raise DevError("PowerShell Gallery already contains different bytes for this version; increment VERSION, do not overwrite")
                write_json(folder / "publish.json", {"registry": registry, "manifest_sha256": sha256(manifest_path), "time": now(), "status": "already_published_identical"})
                print("The exact PowerShell package is already published. Run verify for consumer verification.")
                return
        if registry == "github":
            tag = "v" + manifest["version"]
            remote = subprocess.run(["gh", "api", "repos/ui4me/ui4me/commits/" + tag, "--jq", ".sha"], cwd=ROOT, text=True, capture_output=True, timeout=30)
            if remote.returncode or remote.stdout.strip() != manifest["git_revision"]:
                raise DevError("The GitHub release tag does not resolve to the exact qualified commit; publication refused")
        result = run(command, cwd=ROOT, log=folder / "publish.log", timeout=1800)
        write_json(folder / "publish.json", {"registry": registry, "manifest_sha256": sha256(manifest_path), "time": now(), "result": result})


def qualified_evidence_files(qualification: dict, root: Path = ROOT) -> list[Path]:
    """Include only proof referenced by the reviewed qualification record."""
    root = root.resolve()
    reports = (root / "build/reports").resolve()
    selected: set[Path] = set()

    def add(path: Path) -> Path:
        if path.is_symlink():
            raise DevError("Evidence symlinks are not allowed")
        path = path.resolve()
        if not path.is_relative_to(reports) or not path.is_file():
            raise DevError("Qualified evidence path is missing or outside build/reports")
        selected.add(path)
        return path

    for reference in qualification.get("evidence", []):
        receipt = add(root / reference["path"])
        if sha256(receipt) != reference.get("sha256"):
            raise DevError("Qualified receipt changed after review")
        data = json.loads(receipt.read_text(encoding="utf-8"))
        for proof in data.get("proof_files", []):
            target = add(receipt.parent / proof["path"])
            if sha256(target) != proof.get("sha256"):
                raise DevError("Qualified evidence proof changed after review")
        for case in data.get("cases", []):
            screenshot = case.get("screenshot")
            if screenshot:
                target = add(receipt.parent / screenshot["path"])
                if sha256(target) != screenshot.get("sha256"):
                    raise DevError("Qualified screenshot changed after review")
    if not selected:
        raise DevError("No reviewed evidence was selected")
    return sorted(selected)


def python_upload_plan(manifest_path: Path, registry: str, existing_directory: Path) -> list[Path]:
    """Resume only when every already-published wheel has identical downloaded bytes."""
    if registry not in {"pypi", "testpypi"}:
        raise DevError("Python upload plan requires pypi or testpypi")
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    require_qualified(manifest_path)
    existing_directory = output_path(existing_directory)
    existing_directory.mkdir(parents=True, exist_ok=True)
    base = "https://pypi.org" if registry == "pypi" else "https://test.pypi.org"
    try:
        with urllib.request.urlopen(base + f"/pypi/ui4me/{manifest['version']}/json", timeout=60) as response:
            published = json.load(response)["urls"]
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        published = []
    pending = []
    for item in manifest["artifacts"]:
        if item["kind"] != "python-wheel":
            continue
        name = Path(item["path"]).name
        matches = [record for record in published if record["filename"] == name]
        if not matches:
            pending.append(manifest_path.parent / item["path"])
        elif len(matches) == 1:
            target = existing_directory / name
            download(matches[0]["url"], target)
            if target.stat().st_size != item["size"] or sha256(target) != item["sha256"]:
                raise DevError("PyPI already contains different bytes for " + name + "; a new version is required")
        else:
            raise DevError("Ambiguous published wheel filename")
    return pending


def download(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise DevError("Publication verification requires HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "ui4me-release-verifier/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.geturl().startswith("https://"):
            raise DevError("Refusing a non-HTTPS redirect")
        with destination.open("wb") as stream:
            shutil.copyfileobj(response, stream)


def verify(manifest_path: Path, registry: str) -> bool:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    require_qualified(manifest_path)
    destination = ROOT / "build/public-verification" / registry
    destination.mkdir(parents=True, exist_ok=True)
    for item in manifest["artifacts"]:
        shutil.copy2(manifest_path.parent / item["path"], destination / Path(item["path"]).name)
    shutil.copy2(manifest_path, destination / "manifest.json")
    selected = []
    if registry in {"pypi", "testpypi"}:
        base = "https://pypi.org" if registry == "pypi" else "https://test.pypi.org"
        with urllib.request.urlopen(base + f"/pypi/ui4me/{manifest['version']}/json", timeout=60) as response:
            index = json.load(response)
        for item in manifest["artifacts"]:
            if item["kind"] == "python-wheel":
                matches = [a for a in index["urls"] if a["filename"] == Path(item["path"]).name]
                if len(matches) != 1:
                    raise DevError(f"Published wheel missing: {item['path']}")
                download(matches[0]["url"], destination / item["path"])
                selected.append(item)
        binding = "python"
    elif registry == "powershell":
        item = find_artifact(manifest, "powershell-package")
        download(f"https://www.powershellgallery.com/api/v2/package/Ui4me/{manifest['version']}", destination / item["path"])
        selected.append(item)
        binding = "powershell"
    elif registry == "github":
        for item in manifest["artifacts"]:
            target = destination / item["path"]
            target.unlink(missing_ok=True)
            run(["gh", "release", "download", "v" + manifest["version"], "--repo", "ui4me/ui4me", "--pattern", Path(item["path"]).name, "--dir", str(destination)], cwd=ROOT, log=destination / (Path(item["path"]).name + ".log"))
            selected.append(item)
        binding = "all"
    else:
        raise DevError("Unknown registry")
    for item in selected:
        if sha256(destination / item["path"]) != item["sha256"]:
            raise DevError("Public bytes differ from qualified candidate: " + item["path"])
    load_manifest(destination / "manifest.json")
    bindings = ("python", "powershell", "core") if binding == "all" else (binding,)
    passed = all([installed(b, destination / "manifest.json", phase="public") for b in bindings])
    write_json(destination / "verification.json", {"registry": registry, "checked_at": now(), "platform": host(), "manifest_sha256": sha256(manifest_path), "downloaded_artifacts": selected, "status": "passed" if passed else "failed", "scope": "Exact downloaded bytes plus installed consumer on this host; does not constitute desktop acceptance on other platforms."})
    return passed
