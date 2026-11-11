"""Shared, dependency-free source staging and notices for wheels and sdists.

This module is also included in an sdist. Building a source distribution must not
need the original checkout, donor repository or a maintainer's Cargo cache.
"""
from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
import shutil
import tomllib

_IGNORED = {".git", "target", "build", "dist", "__pycache__", ".pytest_cache", ".venv"}
_REQUIRED_ROOT = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "LICENSE")


def _inside(root: Path, path: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Native source dependency escapes the source root: {path}")
    return path


def _dependencies(data: dict, *, include_dev: bool = True):
    kinds = ("dependencies", "dev-dependencies", "build-dependencies") if include_dev else ("dependencies", "build-dependencies")
    for kind in kinds:
        for value in data.get(kind, {}).values():
            if isinstance(value, dict):
                yield value
    for target in data.get("target", {}).values():
        yield from _dependencies(target, include_dev=include_dev)
    for table in data.get("patch", {}).values():
        for value in table.values():
            if isinstance(value, dict):
                yield value


def native_source_roots(source: Path) -> list[Path]:
    """Resolve the checked-in local Cargo closure and reject missing paths."""
    source = source.resolve()
    for name in _REQUIRED_ROOT:
        if not (source / name).is_file():
            raise ValueError(f"Native source is missing {name}")
    workspace = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))
    manifests = [source / "Cargo.toml"]
    roots: set[Path] = set()
    for member in workspace.get("workspace", {}).get("members", []):
        matches = [Path(p) for p in glob.glob(str(source / member))]
        if not matches:
            raise ValueError(f"Workspace member does not exist: {member}")
        for path in matches:
            path = _inside(source, path)
            roots.add(path)
            manifests.append(path / "Cargo.toml")
    # Copy each carried upstream tree as one reviewed unit, including nested
    # workspace manifests/build assets and patch/license provenance.
    if (source / "patches").is_dir():
        roots.add(source / "patches")
    seen: set[Path] = set()
    while manifests:
        manifest = manifests.pop().resolve()
        if manifest in seen:
            continue
        seen.add(manifest)
        if not manifest.is_file():
            raise ValueError(f"Missing local Cargo manifest: {manifest}")
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        # Vendored packages are dependencies, not workspace test targets. Their
        # upstream-only dev dependencies need not be materialized to build us.
        values = list(_dependencies(data, include_dev=not manifest.is_relative_to(source / "patches")))
        values.extend(v for v in data.get("workspace", {}).get("dependencies", {}).values() if isinstance(v, dict))
        for value in values:
            relative = value.get("path")
            if relative is None:
                continue
            path = _inside(source, manifest.parent / relative)
            if not (path / "Cargo.toml").is_file():
                raise ValueError(f"Missing local dependency {relative!r} in {manifest}")
            roots.add(path)
            manifests.append(path / "Cargo.toml")
    selected = sorted(roots, key=lambda p: (len(p.parts), p.as_posix()))
    return [p for p in selected if not any(p != q and p.is_relative_to(q) for q in selected)]


def _ignore(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in _IGNORED or name.endswith((".pyc", ".pyo"))}


def stage_native_source(source: Path, target: Path) -> None:
    """Stage all local native sources/assets; validate the staged graph again."""
    source, target = source.resolve(), target.resolve()
    if source == target or source.is_relative_to(target):
        raise ValueError("Source staging destination must not replace the source")
    roots = native_source_roots(source)
    target.mkdir(parents=True, exist_ok=True)
    for name in _REQUIRED_ROOT:
        shutil.copy2(source / name, target / name)
    for name in ("VERSION", "include"):
        path = source / name
        if path.is_dir():
            shutil.copytree(path, target / name, dirs_exist_ok=True, ignore=_ignore)
        elif path.is_file():
            shutil.copy2(path, target / name)
    for path in roots:
        if path.is_symlink():
            raise ValueError(f"Native source root must not be a symlink: {path}")
        # Refuse links outside the source tree; copying them would otherwise
        # silently import files absent from an independently extracted sdist.
        for entry in path.rglob("*"):
            if entry.is_symlink():
                _inside(source, entry)
        shutil.copytree(path, target / path.relative_to(source), dirs_exist_ok=True, ignore=_ignore)
    native_source_roots(target)


def collect_notices(metadata: dict, target: Path) -> None:
    """Copy declared and bundled-asset notices from exact Cargo metadata."""
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    copied: list[dict] = []
    for package in sorted(metadata.get("packages", []), key=lambda p: (p["name"], p["version"], p.get("source") or "")):
        rows.append({key: package.get(key) for key in ("name", "version", "license", "repository", "source")})
        directory = Path(package["manifest_path"]).parent
        candidates: set[Path] = set()
        if package.get("license_file"):
            candidates.add(directory / package["license_file"])
        for pattern in ("LICENSE*", "COPYING*", "NOTICE*", "OFL*"):
            candidates.update(directory.glob(pattern))
        # Embedded fonts/dictionaries are part of the delivered binary. Their
        # notices are often below assets/ or data/, not next to Cargo.toml.
        if package.get("source") is None:
            for base_name in ("assets", "data", "src"):
                base = directory / base_name
                if base.is_dir():
                    for pattern in ("LICENSE*", "COPYING*", "NOTICE*", "OFL*"):
                        candidates.update(base.rglob(pattern))
        for path in sorted(candidates):
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                continue
            relative = path.relative_to(directory) if path.is_relative_to(directory) else Path(path.name)
            destination = target / "licenses" / f"{package['name']}-{package['version']}" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied.append({"path": destination.relative_to(target).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (target / "third-party.json").write_text(json.dumps({"packages": rows, "notice_files": copied}, indent=2) + "\n", encoding="utf-8")
