"""Build a standalone sdist and exercise its installed wheel outside the checkout."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ui4me_dev.common import clean_environment, host, revision, sha256, source_id, write_json
sys.path.insert(0, str(ROOT / "bindings/python"))
from _build_support import stage_native_source


def main() -> None:
    output = ROOT / "build/sdist-check"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    report = {"status": "failed", "platform": host(), "git_revision": revision(),
              "source_id": source_id(), "python": sys.version.split()[0],
              "outside_checkout": True, "desktop_acceptance": "not_run"}
    env = clean_environment()
    for key in ("UI4ME_SOURCE_ID", "UI4ME_GIT_REVISION", "CARGO_TARGET_DIR"):
        env.pop(key, None)

    def run(name: str, args: list[str], directory: Path) -> None:
        with (output / (name + ".log")).open("w", encoding="utf-8") as log:
            print("Source distribution check:", name, flush=True)
            subprocess.run(args, check=True, cwd=directory, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=1200)

    try:
        with tempfile.TemporaryDirectory(prefix="ui4me sdist ž ") as temporary:
            work = Path(temporary).resolve()
            if work.is_relative_to(ROOT):
                raise RuntimeError("Source distribution check requires a temporary directory outside the checkout")
            source = work / "source"
            (source / "bindings").mkdir(parents=True)
            shutil.copytree(ROOT / "bindings/python", source / "bindings/python",
                            ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", ".venv"))
            stage_native_source(ROOT, source)
            # Prior staged wheel outputs must not leak into the portable sdist.
            for name in ("_native/staged-library.bin", "_notices/staged-notice.txt"):
                generated = source / "bindings/python/src/ui4me" / name
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_bytes(b"generated output")
            run("build-sdist", [sys.executable, "-m", "build", "--no-isolation", "--sdist", "--outdir", str(output),
                                str(source / "bindings/python")], work)
            archives = list(output.glob("*.tar.gz"))
            if len(archives) != 1:
                raise RuntimeError("Expected one source distribution")
            with tarfile.open(archives[0], "r:gz") as archive:
                names = archive.getnames()
                if any("/src/ui4me/_native/" in name or "/src/ui4me/_notices/" in name for name in names):
                    raise RuntimeError("Generated payload or notices leaked into source distribution")
                if not any(name.endswith("/native-source/Cargo.lock") for name in names):
                    raise RuntimeError("Source distribution is missing the native dependency lock")
            # Remove the original staging source: only the archive may supply the build.
            shutil.rmtree(source)
            wheels = work / "wheels"
            run("build-wheel", [sys.executable, "-m", "pip", "wheel", "--no-cache-dir", "--no-deps", "--no-build-isolation",
                                "--wheel-dir", str(wheels), str(archives[0])], work)
            built = list(wheels.glob("*.whl"))
            if len(built) != 1:
                raise RuntimeError("Expected one source-built wheel")
            consumer = work / "consumer"
            run("create-consumer", [sys.executable, "-m", "venv", str(consumer)], work)
            python = consumer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run("install", [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(built[0])], work)
            script = work / "installed.py"
            shutil.copy2(ROOT / "bindings/python/tests/installed.py", script)
            run("consumer", [str(python), "-I", str(script), "--result", str(output / "consumer.json")], work)
            data = json.loads((output / "consumer.json").read_text(encoding="utf-8"))
            cases = data.get("cases", [])
            expected = {"F01", "F09", "F11", "F12", "F13", "F14"}  # keep in step with tools/ui4me_dev/testing.py INSTALLED
            if len(cases) != len(expected) or {c.get("id") for c in cases} != expected or any(c.get("status") != "passed" for c in cases):
                raise RuntimeError("Source-built consumer did not pass every installed case")
            info = data.get("build_info", {})
            payload = Path(info.get("library_path", "")).resolve()
            if not info.get("source_id", "").startswith("sdist-sha256:") or not payload.is_relative_to(consumer):
                raise RuntimeError("Consumer did not load its own source-built native payload")
            if not (payload.parent.parent / "_notices/third-party.json").is_file():
                raise RuntimeError("Source-built wheel is missing dependency notices")
            report.update(status="passed", sdist={"path": archives[0].name, "sha256": sha256(archives[0])},
                          consumer_sha256=sha256(output / "consumer.json"), build_info=info)
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        write_json(output / "report.json", report)
    print("Standalone source distribution and installed consumer passed:", output / "report.json")


if __name__ == "__main__":
    main()
