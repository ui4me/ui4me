import argparse
from importlib.resources import files
import json
import sys

from . import App, build_info, __version__


def main():
    parser = argparse.ArgumentParser(prog="python -m ui4me")
    parser.add_argument("command", choices=("doctor", "demo"))
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"binding_version": __version__, **build_info()}, indent=2))
        return 0
    html = files("ui4me").joinpath("resources/demo.html").read_text(encoding="utf-8")
    with App() as app:
        window = app.open(html, title="ui4me foundation")
        window.on("click", lambda _: window.set_text("status", "Hello, " + window.get_value("name")), element="greet")
        app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
