"""Platform capability probe (Core 1.0 F1102). Run on a real desktop session (the private virtual
KWin on Linux, the interactive session on Windows):

    python capabilities_probe.py --out caps.json [--update]

Reads `app.capabilities()` once the native backend runs and compares every feature status with
`docs/core-roadmap/data/PLATFORM_CAPABILITIES_V1.json` for this platform (`--update` records it
instead; reasons are informational, statuses are the contract). Automated; not a person.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ui4me import App

PROFILE = Path(__file__).resolve().parents[2] / "docs" / "core-roadmap" / "data" / "PLATFORM_CAPABILITIES_V1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--profile", type=Path, default=PROFILE)
    parser.add_argument("--kde-services", action="store_true", help="start kded6 (status notifier watcher) in the private session first")
    args = parser.parse_args()
    helper = None
    if args.kde_services and sys.platform.startswith("linux"):
        private = Path(tempfile.mkdtemp(prefix="ui4me-caps-"))
        env = dict(os.environ, XDG_CONFIG_HOME=str(private / "config"), XDG_DATA_HOME=str(private / "data"), XDG_CACHE_HOME=str(private / "cache"))
        helper = subprocess.Popen(["kded6"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
    seen: dict = {}
    with App(app_id="org.ui4me.capsprobe") as app:
        app.open("<p>capabilities</p>", title="ui4me capabilities probe", width=320, height=160)

        def started(_):
            seen.update(app.capabilities())
            app.stop()

        app.on("started", started)
        app.timer(30_000, lambda _: app.stop())
        app.run()
    if helper:
        helper.terminate()
        helper.wait(timeout=10)
    platform = seen.get("platform", "unknown")
    statuses = {k: v.get("status") for k, v in sorted(seen.get("features", {}).items())}
    data = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile.exists() else {}
    data.pop("note", None)
    cases = []
    if args.update:
        data[platform] = statuses
        args.profile.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cases.append({"id": "C00_recorded", "status": "passed", "details": {"platform": platform, "features": len(statuses)}})
    else:
        expected = data.get(platform)
        diff = {k: {"expected": (expected or {}).get(k), "actual": statuses.get(k)}
                for k in sorted(set(statuses) | set(expected or {})) if (expected or {}).get(k) != statuses.get(k)}
        cases.append({"id": "C01_capabilities_match_profile", "status": "passed" if expected and not diff else "failed",
                      "details": {"platform": platform, "differences": diff, "features": len(statuses)}})
    result = {"status": "passed" if all(c["status"] == "passed" for c in cases) else "failed", "cases": cases, "capabilities": seen}
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for c in cases:
        print(c["status"], c["id"], json.dumps(c["details"])[:400])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
