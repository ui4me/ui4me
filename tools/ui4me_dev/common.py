from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
IGNORED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".idea", ".vscode"}
TEXT_SUFFIXES = {".py", ".rs", ".toml", ".lock", ".md", ".json", ".yml", ".yaml", ".ps1", ".psm1", ".psd1", ".cs", ".csproj", ".xml", ".h", ".c", ".sh", ".html", ".css", ".txt", ".in", ".cfg"}


class DevError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def version(root: Path = ROOT) -> str:
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise DevError("VERSION must contain a three-part stable version")
    return value


def host() -> str:
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise DevError("This foundation packages x64 only; ARM is not qualified")
    if os.name == "nt":
        return "win-x64"
    if platform.system() == "Linux":
        return "linux-x64"
    raise DevError("Supported development/package hosts are Windows and Linux x64")


def native_name(rid: str | None = None) -> str:
    return "ui4me_core.dll" if (rid or host()) == "win-x64" else "libui4me_core.so"


def source_files(root: Path = ROOT):
    def include_directory(path: Path) -> bool:
        parts = path.relative_to(root).parts
        if path.name in IGNORED or path.name.endswith(".egg-info"):
            return False
        if parts[0] in {"build", "dist", "target"}:
            return False
        if parts[:2] == ("bindings", "python") and len(parts) == 3 and parts[-1] in {"build", "dist"}:
            return False
        if parts[:3] == ("bindings", "powershell", "Ui4me.Managed") and len(parts) == 4 and parts[-1] in {"bin", "obj"}:
            return False
        return True

    for current, dirs, names in os.walk(root):
        base = Path(current)
        dirs[:] = sorted(d for d in dirs if include_directory(base / d))
        for name in dirs + names:
            if (base / name).is_symlink():
                raise DevError(f"Source symlinks are unsupported: {base / name}")
        for name in sorted(names):
            path = base / name
            if name.endswith((".pyc", ".pyo", ".tmp")) or name in {".DS_Store", "CONTRACT-DRAFT.md"}:
                continue
            yield path


def normalized_bytes(path: Path) -> bytes:
    value = path.read_bytes()
    if path.suffix in TEXT_SUFFIXES or path.name in {"VERSION", "LICENSE", ".gitignore", ".gitattributes"}:
        value = value.replace(b"\r\n", b"\n")
    return value


def source_id(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in sorted(source_files(root), key=lambda p: p.relative_to(root).as_posix().encode("utf-8")):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = normalized_bytes(path)
        digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return "sha256:" + digest.hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def revision() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else "uncommitted"
    except (OSError, subprocess.TimeoutExpired):
        return "uncommitted"


def output_path(value: str | Path, default: str | None = None) -> Path:
    target = Path(value or default or "build").expanduser().resolve()
    if target == ROOT:
        raise DevError("An output path may not be the repository root")
    if target.is_relative_to(ROOT):
        relative = target.relative_to(ROOT)
        if not relative.parts or relative.parts[0] not in {"build", "dist"}:
            raise DevError("Generated output inside this repository must be beneath build/ or dist/")
    return target


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        if len(bundle.infolist()) > 10000 or sum(item.file_size for item in bundle.infolist()) > 1024 * 1024 * 1024:
            raise DevError("Archive exceeds the foundation's extraction limits")
        for item in bundle.infolist():
            name = PurePosixPath(item.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or (name.parts and ":" in name.parts[0]):
                raise DevError(f"Unsafe archive entry: {item.filename}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise DevError("Archive symlinks are unsupported")
            target = (destination / Path(*name.parts)).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise DevError("Archive entry escapes destination")
        bundle.extractall(destination)


def zip_tree(source: Path, target: Path, prefix: str = "") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Cargo's registry cache can preserve upstream files dated before ZIP's
    # 1980 epoch. Clamp those timestamps when packaging their license notices.
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise DevError("Packaging symlinks is unsupported")
            if path.is_file():
                bundle.write(path, (PurePosixPath(prefix) / path.relative_to(source).as_posix()).as_posix())


def artifact(path: Path, kind: str, directory: Path, rid: str | None = None) -> dict:
    value = {"kind": kind, "path": path.relative_to(directory).as_posix(), "sha256": sha256(path), "size": path.stat().st_size}
    if rid:
        value["platform"] = rid
    return value


def load_manifest(path: Path, *, current_source: bool = True) -> dict:
    path = path.resolve()
    data = read_json(path)
    if data.get("schema") != 1 or data.get("product") != "ui4me":
        raise DevError("Unsupported package manifest")
    if current_source and data.get("source_id") != source_id():
        raise DevError("Manifest source differs from this checkout; use its matching source")
    if data.get("version") != version():
        raise DevError("Manifest version differs from VERSION")
    if not data.get("artifacts"):
        raise DevError("Manifest has no artifacts")
    names = set()
    for item in data["artifacts"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or item["path"] in names:
            raise DevError("Unsafe or duplicate manifest path")
        names.add(item["path"])
        file = (path.parent / item["path"]).resolve()
        if not file.is_relative_to(path.parent) or not file.is_file() or file.is_symlink():
            raise DevError(f"Missing or unsafe artifact: {file}")
        if sha256(file) != item["sha256"] or file.stat().st_size != item["size"]:
            raise DevError(f"Artifact integrity mismatch: {file.name}")
    return data


def find_artifact(manifest: dict, kind: str, rid: str | None = None) -> dict:
    entries = [a for a in manifest["artifacts"] if a["kind"] == kind and (rid is None or a.get("platform") == rid)]
    if len(entries) != 1:
        raise DevError(f"Expected exactly one {kind} artifact for {rid}; found {len(entries)}")
    return entries[0]


def run_directory(label: str) -> Path:
    path = ROOT / "build" / "reports" / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8] + "-" + label)
    path.mkdir(parents=True)
    return path


def clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "UI4ME_NATIVE_LIB", "UI4ME_MODULE_PATH"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env
