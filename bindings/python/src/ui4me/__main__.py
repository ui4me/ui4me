import argparse
import json
import sys

from . import build_info, __version__


def main():
    parser = argparse.ArgumentParser(prog="python -m ui4me")
    parser.add_argument("command", choices=("doctor", "demo"))
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"binding_version": __version__, **build_info()}, indent=2))
        return 0
    from ._demo import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
