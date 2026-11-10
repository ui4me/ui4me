"""Validate the origin of an artifact before download in privileged workflows."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workflow", choices=("ci.yml", "native-evidence.yml"), required=True)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run_id):
        raise SystemExit("Run ID must be a positive decimal integer")
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Read-only Actions token is required")

    def api(path: str):
        request = urllib.request.Request("https://api.github.com/repos/" + repository + path,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ui4me-release"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    repo = api("")
    run = api("/actions/runs/" + args.run_id)
    checks = {
        "repository": run.get("repository", {}).get("full_name") == repository,
        "head repository": run.get("head_repository", {}).get("full_name") == repository,
        "default branch": run.get("head_branch") == repo["default_branch"],
        "commit": run.get("head_sha") == os.environ["GITHUB_SHA"],
        "workflow": run.get("path") == ".github/workflows/" + args.workflow,
        "event": run.get("event") in {"push", "workflow_dispatch"},
        "completion": run.get("status") == "completed" and run.get("conclusion") == "success",
    }
    if not all(checks.values()):
        raise SystemExit("Artifact producer refused: " + ", ".join(k for k, v in checks.items() if not v))
    values = []
    page = 1
    while True:
        part = api(f"/actions/runs/{args.run_id}/artifacts?per_page=100&page={page}")["artifacts"]
        values.extend(part)
        if len(part) < 100:
            break
        page += 1
        if page > 10:
            raise SystemExit("Unexpected artifact count")
    matches = [a for a in values if a["name"] == args.artifact and not a.get("expired")]
    if len(matches) != 1:
        raise SystemExit("Expected exactly one nonexpired artifact with the requested name")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write("artifact_id=" + str(int(matches[0]["id"])) + "\n")
    print("Verified producer", args.run_id, "at", run["head_sha"], "artifact", matches[0]["id"])


if __name__ == "__main__":
    main()
