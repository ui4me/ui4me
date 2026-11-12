"""Release-gate verdict: every mandatory step must have run and passed.

    python tools/gate/verdict.py RESULTS_DIR --platform linux|windows

RESULTS_DIR is the results folder written by tools/gate/linux_gate.sh or
tools/gate/windows/run_gate.ps1 (plus the Windows upgrade matrix, see docs/DEVELOPMENT.md).
A step passes only when its process exited 0 (as recorded in summary.txt), its result file
exists, its overall status is "passed", it reports at least one case and every case passed.
A missing, skipped, blocked, not-run or failed mandatory step fails the gate. Prints one line
per step and writes RESULTS_DIR/verdict.json. Exit status 0 only when every step passed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# step -> result files (relative to RESULTS_DIR) that must each pass.
LINUX = {
    "chat-python": ["chat-python/journey.json"],
    "chat-powershell": ["chat-powershell/journey.json"],
    "files-python": ["files-python/journey.json"],
    "files-powershell": ["files-powershell/journey.json"],
    "dialogs": ["dialogs/journey.json"],
    "window-probe": ["window-probe/probe.json"],
    "a11y": ["a11y/a11y.json"],
    "input-python": ["input-python/journey.json"],
    "input-powershell": ["input-powershell/journey.json"],
    "environment": ["environment/env.json"],
    "file-input": ["file-input/journey.json"],
    "services": ["services/services.json"],
    "animation": ["animation/animation.json"],
    "print": ["print/print.json"],
    "orca": ["orca/orca.json"],
    "capabilities": ["capabilities/caps.json"],
    "data-app": ["data-app/data.json"],
    "lua": ["lua/lua.json"],
    "upgrade": ["upgrade/upgrade.json"],
}
WINDOWS = {
    "chat-python": ["chat-python/journey.json"],
    "chat-powershell": ["chat-powershell/journey.json"],
    "files-python": ["files-python/journey.json"],
    "files-powershell": ["files-powershell/journey.json"],
    "window-probe": ["window-probe/probe.json"],
    "input-python": ["input-python/journey.json"],
    "input-powershell": ["input-powershell/journey.json"],
    "uia": ["uia/uia.json", "uia/uia_native.json"],
    "environment": ["environment/env.json"],
    "file-input": ["file-input/journey.json"],
    "services": ["services/services.json"],
    "animation": ["animation/animation.json"],
    "print": ["print/print.json"],
    "capabilities": ["capabilities/caps.json"],
    "data-app": ["data-app/data.json"],
    "lua": ["lua/command.log"],  # the binding's unit tests (the KWin Lua probe is Linux-only)
    "nvda": ["nvda/nvda.json"],
    "upgrade": ["upgrade/upgrade.json"],  # run from the checkout, outside run_gate.ps1
}
# Steps whose exit status is not recorded in summary.txt by the gate runner.
NO_EXIT_RECORD = {"windows": {"upgrade"}}


def check_cases(path: Path) -> str | None:
    """None when the result passed, else the reason."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return "result missing"
    except (OSError, ValueError) as error:
        return f"unreadable result: {error}"
    cases = data.get("cases") if isinstance(data, dict) else None
    if isinstance(cases, dict):  # {"case": bool}
        bad = [k for k, v in cases.items() if v is not True]
    elif isinstance(cases, list):
        bad = [f"{c.get('id')}={c.get('status')}" for c in cases if not isinstance(c, dict) or c.get("status") != "passed"]
    else:
        return "result has no cases"
    if not cases:
        return "no cases reported"
    if bad:
        return "not passed: " + ", ".join(bad[:8]) + (" ..." if len(bad) > 8 else "")
    if data.get("status") != "passed":
        return f"status {data.get('status')!r}"
    return None


def check_lua_log(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return "result missing"
    found = re.findall(r"^\s*(\d+) passed, (\d+) failed\s*$", text, re.M)
    if not found:
        return "no test summary in log"
    passed, failed = map(int, found[-1])
    if failed or not passed:
        return f"{passed} passed, {failed} failed"
    return None


def exit_codes(results: Path) -> tuple[dict[str, int], bool]:
    codes: dict[str, int] = {}
    done = False
    try:
        lines = (results / "summary.txt").read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return codes, False
    for line in lines:
        line = line.strip()
        if line == "done":
            done = True
        match = re.fullmatch(r"(\S+) exit (-?\d+)", line)
        if match:
            codes[match.group(1)] = int(match.group(2))
    return codes, done


def verdict(results: Path, platform: str) -> dict:
    steps = LINUX if platform == "linux" else WINDOWS
    codes, done = exit_codes(results)
    rows = []
    for step, files in steps.items():
        reasons = []
        if step not in NO_EXIT_RECORD.get(platform, set()):
            if step not in codes:
                reasons.append("did not run (no exit status)")
            elif codes[step] != 0:
                reasons.append(f"exit {codes[step]}")
        for rel in files:
            reason = check_lua_log(results / rel) if rel.endswith(".log") else check_cases(results / rel)
            if reason:
                reasons.append(f"{rel}: {reason}")
        rows.append({"step": step, "status": "failed" if reasons else "passed", "reasons": reasons})
    unknown = sorted(set(codes) - set(steps))
    problems = [] if done else ["gate runner did not finish (no 'done' in summary.txt)"]
    ok = done and all(r["status"] == "passed" for r in rows)
    return {"platform": platform, "status": "passed" if ok else "failed", "steps": rows,
            "problems": problems, "unlisted_steps": unknown}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path)
    parser.add_argument("--platform", choices=("linux", "windows"), required=True)
    args = parser.parse_args(argv)
    result = verdict(args.results, args.platform)
    for row in result["steps"]:
        print(f"{'PASS' if row['status'] == 'passed' else 'FAIL'} {row['step']}" + (f": {'; '.join(row['reasons'])}" if row["reasons"] else ""))
    for problem in result["problems"]:
        print("FAIL", problem)
    passed = sum(r["status"] == "passed" for r in result["steps"])
    print(f"{result['platform']} gate {result['status'].upper()}: {passed}/{len(result['steps'])} mandatory steps passed")
    try:
        (args.results / "verdict.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"FAIL cannot write verdict.json: {error}")
        return 1
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
