"""Safely install the shipped high-level UI4ME Python coding-agent skill.

The Core skill and unrelated skills are never edited. Existing user changes
are not replaced without --force. No network, shell or elevated rights needed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SKILL_NAME = "ui4me-ui-python"
MARKER = ".ui4me-ui-managed.json"
AGENTS = ("claude", "codex", "opencode", "copilot", "cursor", "gemini")
USER_PATHS = {
    "claude": ".claude/skills", "codex": ".agents/skills",
    "opencode": ".config/opencode/skills", "copilot": ".copilot/skills",
    "cursor": ".cursor/skills", "gemini": ".gemini/skills",
}
PROJECT_PATHS = {
    "claude": ".claude/skills", "codex": ".agents/skills",
    "opencode": ".opencode/skills", "copilot": ".github/skills",
    "cursor": ".cursor/skills", "gemini": ".gemini/skills",
}


def skill_source() -> Path:
    bundled = importlib.resources.files("ui4me").joinpath("_skills", SKILL_NAME)
    path = Path(os.fspath(bundled))
    if (path / "SKILL.md").is_file():
        return path
    checkout = Path(__file__).resolve().parents[2] / "skills" / SKILL_NAME
    if (checkout / "SKILL.md").is_file():
        return checkout
    raise FileNotFoundError("UI4ME UI Python skill is missing; reinstall the Python package")


def hash_files(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in managed skill: {path}")
        if path.is_file() and path.name != MARKER:
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "SKILL.md" not in result:
        raise ValueError("Skill must contain SKILL.md")
    return result


def _guard_path(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError(f"Refusing symlinked destination: {ancestor}")


def status(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    if path.is_symlink() or not path.is_dir():
        return "unmanaged"
    marker = path / MARKER
    if marker.is_symlink() or not marker.is_file():
        return "unmanaged"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unmanaged"
    if data.get("name") != SKILL_NAME or not isinstance(data.get("files"), dict):
        return "unmanaged"
    return "installed" if hash_files(path) == data["files"] else "modified"


def install(source: Path, destination: Path, *, force: bool = False) -> str:
    _guard_path(destination)
    state = status(destination)
    if state in ("modified", "unmanaged") and not force:
        raise FileExistsError(f"Refusing to replace a {state} skill: {destination}; use --force")
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Destination is not a directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ui4me-ui-skill-", dir=destination.parent) as folder:
        stage = Path(folder) / SKILL_NAME
        shutil.copytree(source, stage, symlinks=False)
        (stage / MARKER).write_text(json.dumps({"name": SKILL_NAME, "files": hash_files(stage)},
                                             sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if not destination.exists():
            stage.rename(destination)
            return "installed"
        old = Path(folder) / "original"
        destination.rename(old)
        try:
            stage.rename(destination)
        except BaseException:
            old.rename(destination)
            raise
        return "updated"


def uninstall(destination: Path, *, force: bool = False) -> str:
    _guard_path(destination)
    state = status(destination)
    if state == "missing":
        return "missing"
    if state in ("modified", "unmanaged") and not force:
        raise FileExistsError(f"Refusing to delete a {state} skill: {destination}; use --force")
    if not destination.is_dir():
        raise ValueError(f"Destination is not a directory: {destination}")
    shutil.rmtree(destination)
    return "removed"


def locations(agents: tuple[str, ...], scope: str, *, project: Path | None = None,
              home: Path | None = None) -> dict[str, Path]:
    if scope == "user":
        mapping, base = USER_PATHS, home or Path.home()
    elif scope == "project":
        if project is None or not project.is_dir():
            raise ValueError("--scope project needs --project pointing to an existing directory")
        mapping, base = PROJECT_PATHS, project.resolve()
    else:
        raise ValueError(f"Unknown skill scope: {scope}")
    return {a: base / mapping[a] / SKILL_NAME for a in agents}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    parser.add_argument("--agents", default="all", help="all or names: claude,codex,opencode,copilot,cursor,gemini")
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.scope == "user" and args.project is not None:
        parser.error("--project requires --scope project")
    names = AGENTS if args.agents == "all" else tuple(dict.fromkeys(x.strip().lower()
                            for x in args.agents.split(",") if x.strip()))
    if not names or any(n not in AGENTS for n in names):
        parser.error(f"--agents must be all or a subset of {', '.join(AGENTS)}")
    try:
        paths = locations(names, args.scope, project=args.project)
        source = skill_source() if args.action == "install" and not args.dry_run else None
        failed = 0
        for agent, path in paths.items():
            try:
                if args.dry_run:
                    result = f"would {args.action} ({status(path)})"
                elif args.action == "status":
                    result = status(path)
                elif args.action == "install":
                    result = install(source, path, force=args.force)
                else:
                    result = uninstall(path, force=args.force)
                print(f"{agent}: {result} — {path}")
            except (OSError, ValueError) as exc:
                failed += 1
                print(f"{agent}: ERROR: {exc}", file=sys.stderr)
        return 1 if failed else 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
