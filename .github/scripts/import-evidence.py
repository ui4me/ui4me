"""Copy portable native receipts from a trusted operator's configured directory."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ui4me_dev.common import load_manifest, sha256, source_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("linux-x64", "win-x64"), required=True)
    args = parser.parse_args()
    source = Path(os.environ["UI4ME_EVIDENCE_DIRECTORY"]).expanduser().resolve()
    if not source.is_dir() or source == ROOT or source.is_relative_to(ROOT):
        raise SystemExit("UI4ME_EVIDENCE_DIRECTORY must be a separate directory containing complete run folders")
    manifest = ROOT / "dist/release/manifest.json"
    load_manifest(manifest)
    identity, manifest_hash = source_id(), sha256(manifest)
    out = ROOT / "build/native-upload/build/reports"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    count = 0
    for receipt in sorted(source.rglob("run.json")):
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if (data.get("kind"), data.get("suite"), data.get("platform"), data.get("source_id"), data.get("manifest_sha256")) != ("test", "native", args.platform, identity, manifest_hash):
            continue
        folder = receipt.parent
        files = list(folder.rglob("*"))
        if any(p.is_symlink() for p in files) or sum(p.stat().st_size for p in files if p.is_file()) > 200 * 1024 * 1024:
            raise SystemExit("Unsafe or oversized evidence folder")
        target = out / folder.name
        if target.exists():
            raise SystemExit("Duplicate evidence folder name")
        shutil.copytree(folder, target)
        count += 1
    if not count:
        raise SystemExit("No exact-candidate native receipts matched; nothing uploaded")
    print("Collected", count, "native run folders. Qualification still checks every case and proof.")


if __name__ == "__main__":
    main()
