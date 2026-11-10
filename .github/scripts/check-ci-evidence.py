"""Fail CI when required current-candidate suites or their proof are missing."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ui4me_dev.common import find_artifact, load_manifest, read_json, revision, sha256, write_json
from tools.ui4me_dev.evidence import evidence_errors, receipts
from tools.ui4me_dev.testing import INSTALLED

PLATFORMS = ("linux-x64", "win-x64")
PYTHONS = ("3.11", "3.12", "3.13", "3.14")


def proof_errors(path: Path, data: dict) -> list[str]:
    errors = []
    if not data.get("proof_files"):
        errors.append(f"Missing proof files: {path}")
    for item in data.get("proof_files", []):
        proof = (path.parent / item["path"]).resolve()
        if not proof.is_relative_to(path.parent.resolve()) or not proof.is_file() or sha256(proof) != item["sha256"]:
            errors.append(f"Missing or changed proof: {path} {item['path']}")
    return errors


def check_receipts(values: list[tuple[Path, dict]], manifest: dict, manifest_hash: str) -> list[str]:
    errors = []
    values = [(p, d) for p, d in values if d.get("phase", "candidate") == "candidate"
              and d.get("source_id") == manifest["source_id"] and d.get("git_revision") == manifest["git_revision"]]
    for platform in PLATFORMS:
        for binding in ("core", "python", "powershell", "tools"):
            matches = [(p, d) for p, d in values if (d.get("platform"), d.get("binding"), d.get("suite")) == (platform, binding, "unit")]
            if not matches:
                errors.append(f"Missing unit suite: {platform}/{binding}")
                continue
            path, data = matches[-1]
            if data.get("status") != "passed" or data.get("test_count", 0) <= 0 or not data.get("cases") or any(c.get("status") != "passed" for c in data["cases"]):
                errors.append(f"Required unit suite did not pass: {platform}/{binding}")
            errors.extend(proof_errors(path, data))
        for binding in ("core", "python", "powershell"):
            for python in PYTHONS if binding == "python" else (None,):
                label = f"{platform}/{binding}" + (f"/Python {python}" if python else "")
                matches = [(p, d) for p, d in values if (d.get("platform"), d.get("binding"), d.get("suite")) == (platform, binding, "installed")
                           and (python is None or d.get("harness", {}).get("python", "").startswith(python + "."))]
                if not matches:
                    errors.append(f"Missing installed consumer: {label}")
                    continue
                path, data = matches[-1]
                expected = {"C01"} if binding == "core" else INSTALLED
                cases = data.get("cases", [])
                if data.get("status") != "passed" or len(cases) != len(expected) or {c.get("id") for c in cases} != expected or any(c.get("status") != "passed" for c in cases):
                    errors.append(f"Required installed consumer did not pass: {label}")
                kind = {"core": "native-sdk", "python": "python-wheel", "powershell": "powershell-package"}[binding]
                artifact = find_artifact(manifest, kind, None if binding == "powershell" else platform)
                if data.get("manifest_sha256") != manifest_hash or data.get("consumed_artifact") != artifact:
                    errors.append(f"Installed consumer used different artifacts: {label}")
                errors.extend(proof_errors(path, data))
                if binding != "core":
                    errors.extend(evidence_errors(path, data, {}))
    return errors


def main() -> None:
    manifest_path = ROOT / "dist/release/manifest.json"
    manifest = load_manifest(manifest_path)
    if manifest.get("git_revision") != revision():
        raise SystemExit("CI manifest revision does not match checked-out HEAD")
    errors = check_receipts(receipts(), manifest, sha256(manifest_path))
    for platform in PLATFORMS:
        folder = ROOT / "build/source-check" / ("source-check-" + platform)
        path = folder / "report.json"
        if not path.is_file():
            errors.append(f"Missing source-distribution report: {platform}")
            continue
        report = read_json(path)
        if report.get("status") != "passed" or not report.get("outside_checkout") or (report.get("source_id"), report.get("git_revision"), report.get("platform")) != (manifest["source_id"], manifest["git_revision"], platform):
            errors.append(f"Source-distribution check not passed for this revision: {platform}")
        archive = (folder / report.get("sdist", {}).get("path", "")).resolve()
        consumer = folder / "consumer.json"
        if not archive.is_relative_to(folder.resolve()) or not archive.is_file() or sha256(archive) != report.get("sdist", {}).get("sha256") or not consumer.is_file() or sha256(consumer) != report.get("consumer_sha256"):
            errors.append(f"Source-distribution proof missing or changed: {platform}")
    write_json(ROOT / "build/reports/ci-summary.json", {"status": "failed" if errors else "passed", "source_id": manifest["source_id"],
               "git_revision": manifest["git_revision"], "unit_suites": 8, "installed_consumers": 12, "source_checks": 2,
               "python_versions": list(PYTHONS), "native_desktop_acceptance": "not_run", "errors": errors})
    if errors:
        raise SystemExit("CI evidence incomplete:\n" + "\n".join(errors))
    print("CI evidence passed: 8 unit suites, 12 installed consumers, 2 standalone source-distribution checks.")
    print("Native desktop acceptance remains separate and is not implied by this gate.")


if __name__ == "__main__":
    main()
