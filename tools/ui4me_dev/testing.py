from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .common import ROOT, DevError, clean_environment, find_artifact, host, load_manifest, native_name, now, read_json, revision, run_directory, safe_extract, sha256, source_id, write_json
from .packages import checked_build, native_output, stage_powershell
from .process import run

INSTALLED = {"F01", "F09", "F11", "F12"}
NATIVE = {"F02", "F03", "F04", "F05", "F06", "F07", "F08", "F10"}


def new_receipt(binding: str, suite: str, manifest: Path | None = None, phase: str = "candidate") -> tuple[Path, dict]:
    folder = run_directory(f"{host()}-{binding}-{suite}")
    value = {"schema": 1, "kind": "test", "id": folder.name, "phase": phase, "started_at": now(), "status": "running", "binding": binding, "suite": suite, "platform": host(), "source_id": source_id(), "git_revision": revision(), "backend": "native" if suite == "native" else "headless", "cases": [], "steps": [], "origin": {"github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_repository": os.environ.get("GITHUB_REPOSITORY"), "github_sha": os.environ.get("GITHUB_SHA")}}
    if manifest:
        value["manifest_sha256"] = sha256(manifest) if manifest.is_file() else None
        value["manifest_name"] = manifest.name
    write_json(folder / "run.json", value)
    return folder, value


def finish(folder: Path, receipt: dict) -> None:
    receipt["finished_at"] = now()
    if receipt["status"] == "running":
        statuses = {c["status"] for c in receipt["cases"]}
        receipt["status"] = "passed" if statuses == {"passed"} else "failed" if "failed" in statuses else "interrupted" if "interrupted" in statuses else "blocked" if "blocked" in statuses else "not_run"
    proof = sorted(set(folder.glob("*.log")) | set(folder.glob("*-results.json")) | set(folder.glob("consumer*.json")))
    receipt["proof_files"] = [{"path": p.name, "sha256": sha256(p)} for p in proof]
    write_json(folder / "run.json", receipt)
    print(folder / "run.json")


def unit(binding: str, profile: str) -> bool:
    folder, receipt = new_receipt(binding, "unit")
    try:
        env = dict(os.environ)
        if binding in {"python", "powershell"}:
            built = checked_build(profile, binding)
            env["UI4ME_NATIVE_LIB"] = str(native_output(profile))
        if binding == "core":
            command = ["cargo", "test", "--locked", "-p", "ui4me-core"]
            if profile == "release":
                command.append("--release")
            env["UI4ME_SOURCE_ID"] = source_id()
            step = run(command, cwd=ROOT, env=env, log=folder / "unit.log", check=False)
            receipt["steps"].append(step)
            counts = re.findall(r"test result: ok\. (\d+) passed;", (folder / "unit.log").read_text(encoding="utf-8", errors="replace"))
            count = sum(int(n) for n in counts)
            receipt["test_count"] = count
            receipt["cases"] = [{"id": "UNIT-core", "status": "passed" if step["status"] == "passed" and count > 0 else step["status"] if step["status"] != "passed" else "failed", "tests": count, "details": "Rust test command with nonzero test count required"}]
        elif binding in {"python", "tools"}:
            tests = ROOT / ("bindings/python/tests" if binding == "python" else "tests/tooling")
            if binding == "python":
                env["PYTHONPATH"] = str(ROOT / "bindings/python/src")
            else:
                env["PYTHONPATH"] = str(ROOT)
            result = folder / "unit-results.json"
            step = run([sys.executable, str(ROOT / "tools/ui4me_dev/unittest_runner.py"), str(tests), str(result)], cwd=ROOT, env=env, log=folder / "unit.log", check=False)
            receipt["steps"].append(step)
            data = read_json(result) if result.exists() else {"cases": []}
            receipt["test_count"] = data.get("tests", 0)
            receipt["cases"] = data["cases"]
            if not receipt["cases"] or step["status"] != "passed":
                receipt["cases"].append({"id": "UNIT-process", "status": step["status"] if step["status"] != "passed" else "failed", "details": "No tests or test process unsuccessful"})
        elif binding == "powershell":
            module = folder / "Ui4me"
            stage_powershell(built, native_output(profile), host(), module)
            result = folder / "unit-results.json"
            step = run(["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "bindings/powershell/tests/smoke.ps1"), "-ModulePath", str(module), "-ResultPath", str(result)], cwd=ROOT, env=env, log=folder / "unit.log", check=False)
            receipt["steps"].append(step)
            receipt["cases"] = read_json(result).get("cases", []) if result.exists() else []
            receipt["test_count"] = len(receipt["cases"])
            if not receipt["cases"] or step["status"] != "passed":
                receipt["cases"].append({"id": "UNIT-process", "status": step["status"] if step["status"] != "passed" else "failed", "details": "No tests or test process unsuccessful"})
        else:
            raise DevError(f"Unknown unit binding: {binding}")
    except (DevError, OSError, ValueError) as error:
        receipt["status"] = getattr(error, "status", "blocked")
        receipt["error"] = str(error)
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
    finally:
        finish(folder, receipt)
    return receipt["status"] == "passed"


def installed(binding: str, manifest_path: Path, native: bool = False, interactive: bool = False, phase: str = "candidate") -> bool:
    manifest_path = manifest_path.resolve()
    suite = "native" if native else "installed"
    folder, receipt = new_receipt(binding, suite, manifest_path, phase)
    expected = NATIVE if native else INSTALLED
    receipt["cases"] = [{"id": key, "status": "not_run", "details": "Operator acceptance required" if native else "Consumer has not completed"} for key in sorted(expected)]
    try:
        manifest = load_manifest(manifest_path)
        if native and not interactive:
            raise DevError("Native acceptance requires --interactive on a real desktop")
        if native and host() == "linux-x64" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise DevError("No native desktop: neither DISPLAY nor WAYLAND_DISPLAY is set")
        env = clean_environment()
        with tempfile.TemporaryDirectory(prefix="ui4me consumer ž ") as temporary:
            consumer = Path(temporary)
            result = folder / "consumer.json"
            if binding == "python":
                item = find_artifact(manifest, "python-wheel", host())
                wheel = manifest_path.parent / item["path"]
                receipt["consumed_artifact"] = item
                run([sys.executable, "-m", "venv", str(consumer / "venv")], cwd=consumer, log=folder / "venv.log", env=env)
                python = consumer / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], cwd=consumer, log=folder / "install.log", env=env)
                script = consumer / "installed.py"
                shutil.copy2(ROOT / "bindings/python/tests/installed.py", script)
                command = [str(python), "-I", str(script), "--result", str(result)]
                if native:
                    command += ["--native", "--capture", str(folder / "renderer.png")]
            elif binding == "powershell":
                kind = "powershell-package" if manifest["platform"] == "combined" else "powershell-stage"
                item = find_artifact(manifest, kind, None if kind == "powershell-package" else host())
                receipt["consumed_artifact"] = item
                module = consumer / "modules/Ui4me"
                if kind == "powershell-package":
                    feed = consumer / "feed"
                    feed.mkdir()
                    shutil.copy2(manifest_path.parent / item["path"], feed / Path(item["path"]).name)
                    run(["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts/save-local-powershell.ps1"), "-Feed", str(feed), "-Destination", str(module.parent), "-Version", manifest["version"]], cwd=consumer, log=folder / "install.log", env=env)
                    module = module / manifest["version"]
                else:
                    safe_extract(manifest_path.parent / item["path"], module.parent)
                script = consumer / "installed.ps1"
                shutil.copy2(ROOT / "bindings/powershell/tests/installed.ps1", script)
                command = ["pwsh", "-NoLogo", "-NoProfile", "-File", str(script), "-ModulePath", str(module), "-ResultPath", str(result)]
                if native:
                    command += ["-Native", "-CapturePath", str(folder / "renderer.png")]
            elif binding == "core" and not native:
                item = find_artifact(manifest, "native-sdk", host())
                receipt["consumed_artifact"] = item
                sdk = consumer / "sdk"
                safe_extract(manifest_path.parent / item["path"], sdk)
                source = consumer / "consumer.c"
                shutil.copy2(ROOT / "tests/tooling/c_consumer.c", source)
                executable = consumer / ("consumer.exe" if os.name == "nt" else "consumer")
                if os.name == "nt":
                    compiler = ["cl", "/nologo", "/W4", "/I" + str(sdk / "include"), str(source), "/Fe:" + str(executable)]
                else:
                    compiler = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(sdk / "include"), str(source), "-ldl", "-o", str(executable)]
                run(compiler, cwd=consumer, log=folder / "compile-consumer.log", env=env)
                command = [str(executable), str(sdk / "lib" / native_name())]
            else:
                raise DevError("Native acceptance applies to Python and PowerShell")
            step = run(command, cwd=consumer, log=folder / "consumer.log", env=env, timeout=1800 if native else 120, check=False)
            receipt["steps"].append(step)
            if step["status"] != "passed":
                receipt["status"] = step["status"]
                raise DevError("Installed consumer did not finish successfully; inspect consumer.log")
            if binding == "core":
                receipt["cases"] = [{"id": "C01", "status": "passed", "details": "External C consumer compiled against packaged header and loaded packaged library"}]
            else:
                data = read_json(result)
                receipt["consumer_sha256"] = sha256(result)
                info = data.get("build_info", {})
                if info.get("source_id") != manifest["source_id"]:
                    raise DevError("Consumer loaded a native library with the wrong source identity")
                if str(info.get("version")) != manifest["version"] or info.get("abi") != 1:
                    raise DevError("Consumer native version or ABI differs from candidate")
                receipt["build_info"] = info
                if native:
                    if data.get("backend") != "native":
                        raise DevError("Native consumer did not identify the native backend")
                    receipt["native_session_completed"] = True
                    receipt["status"] = "not_run"
                    snapshots = [{"path": p.name, "sha256": sha256(p), "native_capture": False} for p in sorted(folder.glob("renderer*.png"))]
                    if snapshots:
                        receipt["renderer_snapshot"] = snapshots[0]
                        receipt["renderer_snapshots"] = snapshots
                    print("Native consumer completed. Review each requirement and use attest for individual observations.")
                else:
                    cases = data.get("cases", [])
                    if {c.get("id") for c in cases} != INSTALLED or len(cases) != len(INSTALLED):
                        raise DevError("Installed consumer must report each of F01/F09/F11/F12 exactly once")
                    if any(c.get("status") != "passed" for c in cases):
                        raise DevError("Initial installed consumer did not pass every required case")
                    shutil.copy2(result, folder / "consumer-initial.json")
                    # A fresh process must fail clearly when the package's own native payload is missing.
                    payload = Path(info["library_path"]).resolve()
                    if not payload.is_relative_to(consumer.resolve()) or not payload.is_file():
                        raise DevError("Consumer native payload is outside the isolated installation")
                    hidden = payload.with_name(payload.name + ".missing-test")
                    if hidden.exists():
                        raise DevError("Unexpected payload backup already exists")
                    negative_result = folder / "consumer-missing-native.json"
                    negative_command = [str(negative_result) if arg == str(result) else arg for arg in command]
                    payload.rename(hidden)
                    try:
                        negative = run(negative_command, cwd=consumer, log=folder / "missing-native.log", env=env, timeout=120, check=False)
                        receipt["steps"].append(dict(negative, expected_failure=True))
                        if negative["status"] == "interrupted":
                            receipt["status"] = "interrupted"
                            raise DevError("Missing-payload probe interrupted by operator")
                        diagnostic = read_json(negative_result).get("error", "") if negative_result.exists() else ""
                        diagnostic = str(diagnostic).lower()
                        if negative.get("returncode") in {None, 0} or "native" not in diagnostic or not any(word in diagnostic for word in ("missing", "not found", "does not exist", "cannot find")):
                            raise DevError("Missing native payload did not produce the expected fresh-process diagnostic")
                    finally:
                        hidden.rename(payload)
                    # Reinstall the same qualified bytes; this is not a previous-version upgrade claim.
                    if binding == "python":
                        run([str(python), "-m", "pip", "uninstall", "--yes", "ui4me"], cwd=consumer, log=folder / "uninstall.log", env=env)
                        if payload.exists():
                            raise DevError("pip uninstall left the native payload behind")
                        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], cwd=consumer, log=folder / "reinstall.log", env=env)
                    else:
                        shutil.rmtree(module)
                        if payload.exists():
                            raise DevError("Removing the isolated module left its native payload behind")
                        if kind == "powershell-package":
                            run(["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts/save-local-powershell.ps1"), "-Feed", str(feed), "-Destination", str(consumer / "modules"), "-Version", manifest["version"]], cwd=consumer, log=folder / "reinstall.log", env=env)
                        else:
                            safe_extract(manifest_path.parent / item["path"], module.parent)
                    final = run(command, cwd=consumer, log=folder / "consumer-reinstalled.log", env=env, timeout=120, check=False)
                    receipt["steps"].append(final)
                    if final["status"] != "passed":
                        receipt["status"] = final["status"]
                        raise DevError("Fresh consumer failed after exact-candidate reinstall")
                    data = read_json(result)
                    cases = data.get("cases", [])
                    final_info = data.get("build_info", {})
                    if len(cases) != len(INSTALLED) or {c.get("id") for c in cases} != INSTALLED or any(c.get("status") != "passed" for c in cases) or final_info.get("source_id") != manifest["source_id"] or str(final_info.get("version")) != manifest["version"] or final_info.get("abi") != 1:
                        raise DevError("Reinstalled consumer identity or scenarios differ from the candidate")
                    receipt["consumer_sha256"] = sha256(result)
                    receipt["build_info"] = final_info
                    receipt["installation_checks"] = {"missing_payload_rejected": True, "exact_candidate_reinstalled": True, "previous_version_upgrade": "not_applicable_for_initial_0.1"}
                    for case in cases:
                        if case["id"] == "F01":
                            case["details"] += "; fresh process rejected the deliberately removed native payload with a clear diagnostic"
                        if case["id"] == "F12":
                            case["details"] += "; exact package removed and reinstalled, then all installed checks passed in a fresh process; no previous-version upgrade claimed"
                    receipt["cases"] = cases
    except (DevError, OSError, ValueError, KeyError) as error:
        if receipt["status"] in {"running", "not_run"}:
            receipt["status"] = getattr(error, "status", "blocked")
        receipt["error"] = str(error)
        for case in receipt["cases"]:
            if case["status"] == "not_run":
                case.update(status="blocked", details=str(error))
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
    finally:
        finish(folder, receipt)
    return receipt["status"] in {"passed", "not_run"}
