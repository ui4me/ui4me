"""Command-line entry point for repository development tasks."""
from __future__ import annotations

import argparse
import sys

from .common import DevError
from .packages import lock_dependencies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ui4me development tasks")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock", help="generate Cargo and NuGet dependency locks")
    args = parser.parse_args(argv)

    try:
        if args.command == "lock":
            lock_dependencies()
    except (DevError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
