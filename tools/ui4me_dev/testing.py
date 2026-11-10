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


def new_receipt(binding: str, suite: str, manifest: Path | None = None) -> tuple[Path, dict]:
    folder = run_directory(f"{host()}-{binding}-{suite}")
    value = {"schema": 1, "kind": "test", "id": folder.name, "started_at": now(), "status": "running", "binding": binding, "suite": suite, "platform": host(), "source_id": source_id(), "git_revision": revision(), "backend": "native" if suite == "native" else "headless", "cases": [], "steps": [], "origin": {"github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_repository": os.environ.get("GITHUB_REPOSITORY"), "github_sha": os.environ.get("GITHUB_SHA")}}
    if manifest:
        value["manifest_sha256"] = sha256(manifest)
        value["manifest_name"] = manifest.name
    write_json(folder / "run.json", value)
    return folder, value


def finish(folder: Path, receipt: dict) -> None:
    receipt["finished_at"] = now()
    if receipt["status"] == "running":
        statuses = {c["status"] for c in receipt["cases"]}
        receipt["status"] = "passed" if statuses == {"passed"} else "failed" if "failed" in statuses else "blocked" if "blocked" in statuses else "not_run"
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
            if not receipt["cases"] or step["status"] != "passed":
                receipt["cases"].append({"id": "UNIT-process", "status": step["status"] if step["status"] != "passed" else "failed", "details": "No tests or test process unsuccessful"})
        else:
            raise DevError(f"Unknown unit binding: {binding}")
    except (DevError, OSError, ValueError) as error:
        receipt["status"] = "blocked"
        receipt["error"] = str(error)
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
    finally:
        finish(folder, receipt)
    return receipt["status"] == "passed"


def installed(binding: str, manifest_path: Path, native: bool = False, interactive: bool = False) -> bool:
    manifest_path = manifest_path.resolve()
    manifest = load_manifest(manifest_path)
    suite = "native" if native else "installed"
    folder, receipt = new_receipt(binding, suite, manifest_path)
    expected = NATIVE if native else INSTALLED
    receipt["cases"] = [{"id": key, "status": "not_run", "details": "Operator acceptance required" if native else "Consumer has not completed"} for key in sorted(expected)]
    try:
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
                    safe_extract(manifest_path.parent / item["path"], module)
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
                receipt["build_info"] = info
                if native:
                    if data.get("backend") != "native":
                        raise DevError("Native consumer did not identify the native backend")
                    receipt["native_session_completed"] = True
                    receipt["status"] = "not_run"
                    if (folder / "renderer.png").exists():
                        receipt["renderer_snapshot"] = {"path": "renderer.png", "sha256": sha256(folder / "renderer.png"), "native_capture": False}
                    print("Native consumer completed. Review each requirement and use attest for individual observations.")
                else:
                    cases = data.get("cases", [])
                    if {c.get("id") for c in cases} != INSTALLED or len(cases) != len(INSTALLED):
                        raise DevError("Installed consumer must report each of F01/F09/F11/F12 exactly once")
                    receipt["cases"] = cases
    except (DevError, OSError, ValueError, KeyError) as error:
        if receipt["status"] in {"running", "not_run"}:
            receipt["status"] = "blocked"
        receipt["error"] = str(error)
        for case in receipt["cases"]:
            if case["status"] == "not_run":
                case.update(status="blocked", details=str(error))
    except KeyboardInterrupt:
        receipt["status"] = "interrupted"
    finally:
        finish(folder, receipt)
    return receipt["status"] in {"passed", "not_run"}
