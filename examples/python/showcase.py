"""Open an application whose HTML and CSS live in files (examples/showcase) and wire a few events.

    python examples/python/showcase.py

The directory of index.html becomes the window's local asset root, so style.css (and any
images or fonts next to it) load from there.
"""
import html
from pathlib import Path

from ui4me import App

SHOWCASE = Path(__file__).resolve().parents[1] / "showcase" / "index.html"


def main() -> None:
    with App() as app:
        window = app.open_file(SHOWCASE, title="UI4ME showcase", width=1000, height=760)

        def select_tab(event):
            for tab in ("tab-overview", "tab-jobs", "tab-settings"):
                (window.add_class if tab == event["element"] else window.remove_class)(tab, "active")

        for tab in ("tab-overview", "tab-jobs", "tab-settings"):
            window.on("click", select_tab, element=tab)

        def create(_event):
            name = html.escape(window.get_value("name").strip() or "untitled")
            window.append_html("jobs-body", f"<tr><td>{name}</td><td>You</td><td>—</td>"
                                            "<td><span class='pill run'>Queued</span></td></tr>")
            window.set_value("name", "")
            window.focus("name")

        window.on("click", create, element="create")
        app.run()


if __name__ == "__main__":
    main()
