from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import subprocess
import tomllib
import zipfile
from pathlib import Path

from .common import ROOT, DevError, artifact, find_artifact, host, load_manifest, native_name, output_path, read_json, revision, safe_extract, sha256, source_id, version, write_json, zip_tree
from .process import run


def native_output(profile: str) -> Path:
    return ROOT / "build/cargo" / host() / native_target() / ("release" if profile == "release" else "debug") / native_name()


def native_target() -> str:
    return {"linux-x64": "x86_64-unknown-linux-gnu", "win-x64": "x86_64-pc-windows-msvc"}[host()]


def output_identity(path: Path, kind: str) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path), "kind": kind}


def lock_dependencies() -> None:
    logs = ROOT / "build" / "lock"
    run(["cargo", "generate-lockfile"], cwd=ROOT, log=logs / "cargo.log")
    run(["dotnet", "restore", str(ROOT / "bindings/powershell/Ui4me.Managed/Ui4me.Managed.csproj"), "--use-lock-file"], cwd=ROOT, log=logs / "nuget.log")
    print("Dependency locks generated. Review and commit Cargo.lock and packages.lock.json before CI/release.")


def require_locks(binding: str = "all") -> None:
    required = [ROOT / "Cargo.lock"]
    if binding in {"all", "powershell"}:
        required.append(ROOT / "bindings/powershell/Ui4me.Managed/packages.lock.json")
    missing = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
    if missing:
        raise DevError("Missing dependency locks: " + ", ".join(missing) + ". Run python dev.py lock, review and commit the result.")


def build(binding: str, profile: str) -> Path:
    from .versioning import synchronize
    synchronize()
    require_locks(binding)
    folder = ROOT / "build" / host() / profile
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": 1, "kind": "build", "status": "running", "source_id": source_id(), "platform": host(), "profile": profile, "binding": binding, "version": version(), "git_revision": revision(), "steps": []}
    write_json(folder / "build.json", receipt)
    env = dict(os.environ, UI4ME_SOURCE_ID=receipt["source_id"], UI4ME_GIT_REVISION=receipt["git_revision"])
    env["CARGO_TARGET_DIR"] = str(ROOT / "build/cargo" / host())
    env.pop("CARGO_BUILD_TARGET", None)
    receipt["configuration"] = {"package": "ui4me-core", "features": "default", "target": native_target(),
                                "toolchain": tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"],
                                "rustflags": env.get("RUSTFLAGS", ""), "cargo_encoded_rustflags": env.get("CARGO_ENCODED_RUSTFLAGS", "")}
    try:
        receipt["configuration"]["rustc"] = subprocess.check_output(["rustc", "--version"], cwd=ROOT, text=True, env=env).strip()
        args = ["cargo", "build", "--locked", "--target", native_target(), "-p", "ui4me-core"]
        if profile == "release":
            args.append("--release")
        receipt["steps"].append(run(args, cwd=ROOT, log=folder / "cargo-build.log", env=env))
        if binding in {"all", "powershell"}:
            project = ROOT / "bindings/powershell/Ui4me.Managed/Ui4me.Managed.csproj"
            receipt["steps"].append(run(["dotnet", "restore", str(project), "--locked-mode"], cwd=ROOT, log=folder / "dotnet-restore.log"))
            managed = folder / "managed"
            if managed.exists():
                shutil.rmtree(managed)
            receipt["configuration"]["dotnet_sdk"] = subprocess.check_output(["dotnet", "--version"], cwd=ROOT, text=True).strip()
            receipt["steps"].append(run(["dotnet", "build", str(project), "--no-restore", "--configuration", "Release" if profile == "release" else "Debug", "--output", str(managed)], cwd=ROOT, log=folder / "dotnet-build.log"))
        if source_id() != receipt["source_id"]:
            raise DevError("Source changed during build; repeat against a stable checkout")
        native = native_output(profile)
        if not native.is_file():
            raise DevError(f"Expected native output is missing: {native}")
        outputs = [output_identity(native, "native")]
        if binding in {"all", "powershell"}:
            bridge = folder / "managed/Ui4me.Managed.dll"
            if not bridge.is_file():
                raise DevError("The managed build did not produce Ui4me.Managed.dll")
            outputs.append(output_identity(bridge, "managed"))
            outputs += [output_identity(p, "managed-dependencies") for p in sorted((folder / "managed").glob("*.deps.json"))]
        receipt.update(status="passed", native_sha256=sha256(native), outputs=outputs)
    except BaseException as error:
        receipt.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error))
        raise
    finally:
        write_json(folder / "build.json", receipt)
    return folder


def checked_build(profile: str, binding: str) -> Path:
    folder = ROOT / "build" / host() / profile
    if not (folder / "build.json").is_file():
        raise DevError("Build first; packaging never silently rebuilds")
    data = read_json(folder / "build.json")
    if data.get("status") != "passed" or data.get("source_id") != source_id():
        raise DevError("Build receipt is missing, failed or stale")
    if sha256(native_output(profile)) != data.get("native_sha256"):
        raise DevError("Native output changed after the build receipt")
    if binding in {"all", "powershell"} and data.get("binding") not in {"all", "powershell"}:
        raise DevError("This build does not include PowerShell")
    expected = {native_output(profile).relative_to(ROOT).as_posix()}
    if data.get("binding") in {"all", "powershell"}:
        expected.add((folder / "managed/Ui4me.Managed.dll").relative_to(ROOT).as_posix())
        expected.update(p.relative_to(ROOT).as_posix() for p in (folder / "managed").glob("*.deps.json"))
    outputs = data.get("outputs", [])
    if {item.get("path") for item in outputs} != expected or len(outputs) != len(expected):
        raise DevError("Build receipt does not identify every delivered output; rebuild")
    for item in outputs:
        path = (ROOT / item["path"]).resolve()
        if not path.is_relative_to((ROOT / "build").resolve()) or not path.is_file() or sha256(path) != item.get("sha256"):
            raise DevError(f"Build output changed after its receipt: {item['path']}")
    return folder


def notices(stage: Path, log_folder: Path) -> None:
    """Inventory the exact resolved native dependencies; retain available license text."""
    import subprocess
    metadata = subprocess.run(["cargo", "metadata", "--locked", "--format-version", "1"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    (log_folder / "cargo-metadata.log").write_text(metadata.stderr, encoding="utf-8")
    if metadata.returncode:
        raise DevError("Cannot obtain locked dependency inventory")
    import importlib.util
    spec = importlib.util.spec_from_file_location("ui4me_build_support", ROOT / "bindings/python/_build_support.py")
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    support.collect_notices(json.loads(metadata.stdout), stage)
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", stage / "LICENSE")


def stage_powershell(folder: Path, native: Path, rid: str, target: Path) -> None:
    shutil.copytree(ROOT / "bindings/powershell/Ui4me", target, dirs_exist_ok=True)
    library = target / "lib"
    library.mkdir(parents=True, exist_ok=True)
    managed = folder / "managed/Ui4me.Managed.dll"
    if not managed.is_file():
        raise DevError("Managed bridge not built")
    shutil.copy2(managed, library / managed.name)
    # The host supplies System.Management.Automation; never ship a second copy.
    for extra in (folder / "managed").glob("*.deps.json"):
        shutil.copy2(extra, library / extra.name)
    payload = target / "runtimes" / rid / "native"
    payload.mkdir(parents=True, exist_ok=True)
    shutil.copy2(native, payload / native.name)


def package(binding: str, profile: str) -> Path:
    folder = checked_build(profile, binding)
    rid = host()
    destination = ROOT / "dist" / rid
    destination.mkdir(parents=True, exist_ok=True)
    staging = ROOT / "build" / "package" / rid
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    native = native_output(profile)
    artifacts = []
    notice = staging / "notices"
    notice.mkdir()
    notices(notice, staging)
    sdk = staging / "sdk"
    (sdk / "lib").mkdir(parents=True)
    (sdk / "include").mkdir()
    shutil.copy2(native, sdk / "lib" / native.name)
    shutil.copy2(ROOT / "include/ui4me.h", sdk / "include/ui4me.h")
    shutil.copytree(notice, sdk / "notices")
    sdk_path = destination / f"ui4me-sdk-{version()}-{rid}.zip"
    zip_tree(sdk, sdk_path)
    artifacts.append(artifact(sdk_path, "native-sdk", destination, rid))
    if binding in {"all", "python"}:
        python_stage = staging / "python"
        shutil.copytree(ROOT / "bindings/python", python_stage, ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", ".venv"))
        payload = python_stage / "src/ui4me/_native"
        payload.mkdir(parents=True, exist_ok=True)
        shutil.copy2(native, payload / native.name)
        shutil.copytree(notice, python_stage / "src/ui4me/_notices", dirs_exist_ok=True)
        wheels = staging / "wheels"
        run([sys.executable, "-m", "build", "--wheel", "--outdir", str(wheels), str(python_stage)], cwd=ROOT, log=staging / "wheel-build.log")
        candidates = list(wheels.glob("*.whl"))
        if len(candidates) != 1:
            raise DevError("Expected exactly one built wheel")
        wheel = candidates[0]
        if rid == "linux-x64":
            repaired = staging / "repaired"
            run([sys.executable, "-m", "auditwheel", "repair", "--wheel-dir", str(repaired), str(wheel)], cwd=ROOT, log=staging / "auditwheel.log")
            candidates = list(repaired.glob("*.whl"))
            if len(candidates) != 1:
                raise DevError("Expected exactly one repaired wheel")
            wheel = candidates[0]
        run([sys.executable, "-m", "twine", "check", str(wheel)], cwd=ROOT, log=staging / "twine-check.log")
        with zipfile.ZipFile(wheel) as contents:
            metadata = [name for name in contents.namelist() if name.endswith(".dist-info/WHEEL")]
            if len(metadata) != 1 or b"Root-Is-Purelib: false" not in contents.read(metadata[0]):
                raise DevError("Native-inclusive wheel must be a platform wheel")
            if not any(name.endswith(native.name) for name in contents.namelist()):
                raise DevError("Native library missing from wheel")
        final_wheel = destination / wheel.name
        shutil.copy2(wheel, final_wheel)
        artifacts.append(artifact(final_wheel, "python-wheel", destination, rid))
    if binding in {"all", "powershell"}:
        module = staging / "Ui4me"
        stage_powershell(folder, native, rid, module)
        shutil.copytree(notice, module / "notices", dirs_exist_ok=True)
        archive = destination / f"Ui4me-{version()}-{rid}-stage.zip"
        zip_tree(module, archive, "Ui4me")
        artifacts.append(artifact(archive, "powershell-stage", destination, rid))
    data = {"schema": 1, "product": "ui4me", "version": version(), "source_id": source_id(), "git_revision": revision(), "platform": rid, "profile": profile, "artifacts": artifacts, "qualification": "not_qualified"}
    write_json(destination / "manifest.json", data)
    print(destination / "manifest.json")
    return destination / "manifest.json"


def assemble(manifests: list[Path], out: Path) -> Path:
    if len(manifests) != 2:
        raise DevError("Assembly requires one Linux and one Windows manifest")
    loaded = sorted(((p.resolve(), load_manifest(p)) for p in manifests), key=lambda item: item[1]["platform"])
    if {m["platform"] for _, m in loaded} != {"linux-x64", "win-x64"}:
        raise DevError("Assembly requires linux-x64 and win-x64")
    for key in ("source_id", "version", "git_revision"):
        if len({m[key] for _, m in loaded}) != 1:
            raise DevError(f"Candidates disagree on {key}")
    if any(m.get("profile") != "release" for _, m in loaded):
        raise DevError("Only release profile packages can be assembled")
    out = output_path(out)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = []
    stage = ROOT / "build/assembly"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    module = stage / "Ui4me"
    for index, (path, data) in enumerate(loaded):
        for kind in ("python-wheel", "native-sdk"):
            item = find_artifact(data, kind, data["platform"])
            target = out / Path(item["path"]).name
            shutil.copy2(path.parent / item["path"], target)
            artifacts.append(artifact(target, kind, out, data["platform"]))
        item = find_artifact(data, "powershell-stage", data["platform"])
        part = stage / data["platform"]
        safe_extract(path.parent / item["path"], part)
        incoming = part / "Ui4me"
        if index == 0:
            shutil.copytree(incoming, module)
        else:
            # Source is identical, but managed binaries vary with the SDK and
            # build host. Use the Linux build as the canonical adapter and
            # test the assembled package on both platforms.
            for file in incoming.rglob("*"):
                if file.is_file() and not file.relative_to(incoming).parts[0] in {"runtimes", "notices"}:
                    if file.relative_to(incoming).as_posix() in {"lib/Ui4me.Managed.dll", "lib/Ui4me.Managed.deps.json"}:
                        continue
                    other = module / file.relative_to(incoming)
                    if not other.is_file() or sha256(file) != sha256(other):
                        raise DevError(f"PowerShell platform stages disagree: {file.relative_to(incoming)}")
            shutil.copytree(incoming / "runtimes", module / "runtimes", dirs_exist_ok=True)
            shutil.copytree(incoming / "notices", module / "notices" / data["platform"], dirs_exist_ok=True)
    run(["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts/powershell-package.ps1"), "-ModulePath", str(module), "-Destination", str(out)], cwd=ROOT, log=stage / "compress.log")
    packages = list(out.glob(f"*{version()}*.nupkg"))
    if len(packages) != 1:
        raise DevError("Expected one combined PowerShell nupkg")
    artifacts.append(artifact(packages[0], "powershell-package", out))
    result = {"schema": 1, "product": "ui4me", "version": version(), "source_id": source_id(), "git_revision": loaded[0][1]["git_revision"], "platform": "combined", "profile": "release", "artifacts": artifacts, "qualification": "not_qualified"}
    write_json(out / "manifest.json", result)
    print(out / "manifest.json")
    return out / "manifest.json"
