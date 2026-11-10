"""Build and install a wheel from the standalone source distribution."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tarfile
import venv

root = Path(__file__).resolve().parents[2]
work = root / "build" / "sdist-check"
if work.exists():
    shutil.rmtree(work)
source = work / "source"
(source / "bindings").mkdir(parents=True)
shutil.copytree(root / "bindings/python", source / "bindings/python",
                ignore=shutil.ignore_patterns("build", "dist", "*.egg-info", "__pycache__", ".venv"))
shutil.copytree(root / "crates/ui4me-core", source / "crates/ui4me-core")
for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "LICENSE"):
    shutil.copy2(root / name, source / name)
# Simulate a prior staged wheel: generated payloads must not enter an sdist.
for name in ("_native/staged-library.bin", "_notices/staged-notice.txt"):
    generated = source / "bindings/python/src/ui4me" / name
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"generated output")
artifacts = work / "artifacts"
artifacts.mkdir()
subprocess.run([sys.executable, "-m", "build", "--sdist", "--outdir", str(artifacts),
                str(source / "bindings/python")], check=True, cwd=work)
archives = list(artifacts.glob("*.tar.gz"))
if len(archives) != 1:
    raise SystemExit("Expected one source distribution")
with tarfile.open(archives[0], "r:gz") as archive:
    names = archive.getnames()
    if any("/src/ui4me/_native/" in name or "/src/ui4me/_notices/" in name for name in names):
        raise SystemExit("Generated native payload or notices leaked into source distribution")
    if not any(name.endswith("/native-source/Cargo.lock") for name in names):
        raise SystemExit("Source distribution is missing the native dependency lock")
subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-cache-dir", "--no-deps", "--no-build-isolation",
                "--wheel-dir", str(artifacts), str(archives[0])], check=True, cwd=work)
wheels = list(artifacts.glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected one source-built wheel")
consumer = work / "consumer"
venv.EnvBuilder(with_pip=True).create(consumer)
python = consumer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])], check=True, cwd=work)
probe = """from importlib.resources import files
from ui4me import App, build_info
info = build_info()
assert info['source_id'].startswith('sdist-sha256:')
assert files('ui4me').joinpath('_notices/third-party.json').is_file()
with App(backend='headless', handle_sigint=False) as app:
    app.on('started', lambda _: app.stop())
    app.run()
print(info)
"""
subprocess.run([str(python), "-I", "-c", probe], check=True, cwd=work)
