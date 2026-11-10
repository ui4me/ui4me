"""Copy only the already-qualified wheels for the official PyPI action."""
from pathlib import Path
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ui4me_dev.common import load_manifest, sha256
from tools.ui4me_dev.evidence import require_qualified
from tools.ui4me_dev.publishing import python_upload_plan

manifest_path = ROOT / "dist/release/manifest.json"
manifest = load_manifest(manifest_path)
require_qualified(manifest_path)
out = ROOT / "build/pypi"
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
all_wheels = [a for a in manifest["artifacts"] if a["kind"] == "python-wheel"]
if len(all_wheels) != 2:
    raise SystemExit("Expected the two qualified platform wheels")
registry = os.environ["REGISTRY"]
if registry not in {"pypi", "testpypi"}:
    raise SystemExit("This staging script is only for PyPI and TestPyPI")
pending = python_upload_plan(manifest_path, registry, ROOT / "build/existing-pypi")
names = {p.name for p in pending}
for item in all_wheels:
    if Path(item["path"]).name not in names:
        continue
    destination = out / Path(item["path"]).name
    shutil.copy2(manifest_path.parent / item["path"], destination)
    if sha256(destination) != item["sha256"]:
        raise SystemExit("Staged wheel checksum differs")
if "GITHUB_OUTPUT" in os.environ:
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write("has_pending=" + ("true" if pending else "false") + "\n")
