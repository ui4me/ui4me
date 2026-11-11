"""Shared integrity rules for CI evidence and release qualification."""
from __future__ import annotations

from pathlib import Path

from .common import find_artifact, sha256


def proof_errors(path: Path, data: dict) -> list[str]:
    errors = []
    if not data.get("proof_files"):
        errors.append(f"Missing proof files: {path}")
    for item in data.get("proof_files", []):
        proof = (path.parent / item["path"]).resolve()
        if not proof.is_relative_to(path.parent.resolve()) or not proof.is_file() or sha256(proof) != item["sha256"]:
            errors.append(f"Missing or changed proof: {path} {item['path']}")
    return errors


def upgrade_errors(values: list[tuple[Path, dict]], manifest: dict, manifest_hash: str) -> tuple[list[str], list[Path]]:
    """The 0.2 candidate must exercise both installed 0.1 packages on both hosts."""
    if manifest.get("version", "0.1.0") == "0.1.0":
        return [], []
    errors, references = [], []
    for platform in ("linux-x64", "win-x64"):
        for binding in ("python", "powershell"):
            label = f"{platform}/{binding}"
            matches = [(p, d) for p, d in values
                       if d.get("phase", "candidate") == "candidate"
                       and (d.get("source_id"), d.get("git_revision"), d.get("platform"), d.get("binding"), d.get("suite"))
                       == (manifest["source_id"], manifest["git_revision"], platform, binding, "upgrade")]
            if not matches:
                errors.append(f"Missing previous-version upgrade: {label}")
                continue
            path, data = matches[-1]
            references.append(path)
            cases = data.get("cases", [])
            if data.get("status") != "passed" or len(cases) != 1 or cases[0].get("id") != "UPGRADE-" + binding or cases[0].get("status") != "passed":
                errors.append(f"Previous-version upgrade did not pass: {label}")
            artifact = find_artifact(manifest, "python-wheel", platform) if binding == "python" else find_artifact(manifest, "powershell-package")
            if data.get("manifest_sha256") != manifest_hash or data.get("consumed_artifact") != artifact:
                errors.append(f"Previous-version upgrade used different artifacts: {label}")
            if data.get("previous_version") != "0.1.0" or not data.get("previous_native_sha256"):
                errors.append(f"Missing previous-version identity: {label}")
            names = {item["path"] for item in data.get("proof_files", [])}
            if not {"consumer-previous.json", "consumer.json"}.issubset(names):
                errors.append(f"Missing previous-version or upgraded consumer proof: {label}")
            errors.extend(proof_errors(path, data))
    return errors, references
