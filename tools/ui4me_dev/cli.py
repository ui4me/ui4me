from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from .common import ROOT, DevError, host, version


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="ui4me development and release tools.")
    subs = root.add_subparsers(dest="command", required=True)
    subs.add_parser("doctor", help="Show prerequisite paths and supported host information")
    subs.add_parser("lock", help="Resolve Cargo and NuGet lock files; review/commit before building")
    metadata = subs.add_parser("version", help="Check or synchronize metadata from VERSION")
    group = metadata.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--set", dest="new_version")
    for name in ("build", "package", "test"):
        item = subs.add_parser(name)
        item.add_argument("--binding", choices=("all", "core", "python", "powershell", "tools"), default="all")
        item.add_argument("--profile", choices=("dev", "release"), default="dev")
        if name == "test":
            item.add_argument("--suite", choices=("unit", "installed", "native", "all"), default="unit")
            item.add_argument("--manifest", type=Path)
            item.add_argument("--interactive", action="store_true")
    assemble = subs.add_parser("assemble", help="Combine matching Windows/Linux candidates")
    assemble.add_argument("--manifest", type=Path, action="append", required=True)
    assemble.add_argument("--out", type=Path, default=ROOT / "dist/release")
    report = subs.add_parser("report")
    report.add_argument("--out", type=Path, default=ROOT / "build/reports/overview")
    report.add_argument("--manifest", type=Path)
    attest = subs.add_parser("attest", help="Record a human observation for a completed native candidate session")
    attest.add_argument("--run", type=Path, required=True)
    attest.add_argument("--scenario", required=True)
    attest.add_argument("--status", choices=("passed", "failed", "blocked"), required=True)
    attest.add_argument("--notes", required=True)
    attest.add_argument("--operator", required=True)
    attest.add_argument("--screenshot", type=Path)
    attest.add_argument("--capture-kind", choices=("desktop",), default="desktop")
    qualify = subs.add_parser("qualify")
    qualify.add_argument("--manifest", type=Path, required=True)
    qualify.add_argument("--reviewer", required=True)
    qualify.add_argument("--review-url", required=True)
    qualify.add_argument("--ci-only", action="store_true", help="Qualify the automated CI matrix; native desktop acceptance remains not_run")
    for name in ("publish", "verify"):
        item = subs.add_parser(name)
        item.add_argument("--manifest", type=Path, required=True)
        item.add_argument("--registry", choices=("pypi", "testpypi", "powershell", "github"), required=True)
        if name == "publish":
            item.add_argument("--execute", action="store_true", help="Perform the external publication; default is a dry run")
    source = subs.add_parser("source-zip")
    source.add_argument("--out", type=Path, default=ROOT / "dist" / "ui4me-source.zip")
    upgrade = subs.add_parser("upgrade-check", help="Install a previous public package, then upgrade to exact candidate bytes in fresh processes")
    upgrade.add_argument("--binding", choices=("python", "powershell"), required=True)
    upgrade.add_argument("--manifest", type=Path, required=True)
    upgrade.add_argument("--previous-version", default="0.1.0")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            tools = {name: shutil.which(name) for name in ("cargo", "rustc", "dotnet", "pwsh", "cc" if platform.system() != "Windows" else "cl", "gh")}
            print(json.dumps({"platform": host(), "python": sys.version.split()[0], "version": version(), "tools": tools, "cargo_lock": (ROOT / "Cargo.lock").exists(), "nuget_lock": (ROOT / "bindings/powershell/Ui4me.Managed/packages.lock.json").exists(), "note": "Presence is not a successful build or runtime test. See docs/DEVELOPMENT.md for prerequisites."}, indent=2))
            return 0 if sys.version_info >= (3, 11) else 1
        if sys.version_info < (3, 11):
            raise DevError("Python 3.11 or newer is required for repository tooling")
        from . import evidence, packages, publishing, testing
        if args.command == "version":
            from .versioning import synchronize
            synchronize(args.new_version)
        elif args.command == "lock":
            packages.lock_dependencies()
        elif args.command == "build":
            if args.binding == "tools":
                raise DevError("Tooling is Python source; use test --binding tools")
            packages.build(args.binding, args.profile)
        elif args.command == "package":
            if args.binding == "tools":
                raise DevError("Tooling has no standalone package")
            packages.package(args.binding, args.profile)
        elif args.command == "assemble":
            packages.assemble(args.manifest, args.out)
        elif args.command == "test":
            suites = ("unit", "installed", "native") if args.suite == "all" else (args.suite,)
            results = []
            for suite in suites:
                if suite != "unit" and args.manifest is None:
                    raise DevError("Installed and native tests require --manifest; they never rebuild")
                bindings = ("core", "python", "powershell", "tools") if args.binding == "all" and suite == "unit" else ("core", "python", "powershell") if args.binding == "all" and suite == "installed" else ("python", "powershell") if args.binding == "all" else (args.binding,)
                for binding in bindings:
                    results.append(testing.unit(binding, args.profile) if suite == "unit" else testing.installed(binding, args.manifest, suite == "native", args.interactive))
            return 0 if results and all(results) else 1
        elif args.command == "report":
            evidence.report(args.out, args.manifest)
        elif args.command == "attest":
            evidence.attest(args.run, args.scenario, args.status, args.notes, args.operator, args.screenshot, args.capture_kind)
        elif args.command == "qualify":
            result = evidence.qualify(args.manifest, args.reviewer, args.review_url, ci_only=args.ci_only)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "qualified" else 1
        elif args.command == "publish":
            publishing.publish(args.manifest, args.registry, args.execute)
        elif args.command == "verify":
            return 0 if publishing.verify(args.manifest, args.registry) else 1
        elif args.command == "source-zip":
            publishing.source_zip(args.out)
        elif args.command == "upgrade-check":
            return 0 if testing.upgrade(args.binding, args.manifest, args.previous_version) else 1
        return 0
    except (DevError, OSError, ValueError, KeyError) as error:
        print(f"ui4me: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ui4me: interrupted; inspect latest receipt before retrying", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
