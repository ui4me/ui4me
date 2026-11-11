"""Run after installing the ui4me wheel. Only public App/Window methods are used."""
from pathlib import Path
from threading import Thread
from ui4me import App


def run(source: Path | None = None) -> None:
    source = source or Path(__file__).resolve().parents[1] / "foundation"
    with App() as app:
        window = app.open_file(source / "index.html", title="UI4ME · Python", width=1000, height=820)
        state = {"rows": 4, "highlight": False}

        def greet(_):
            enabled = "on" if window.get_checked("enabled") else "off"
            window.set_text("status", f"Hello, {window.get_value('name')}! Notifications: {enabled}.")

        def add(_):
            state["rows"] += 1
            window.replace_children_html("rows", "".join(
                f'<p class="row">{i} · Result row updated by Python</p>' for i in range(1, state["rows"] + 1)))
            window.set_text("status", f"{state['rows']} rows. Your other inputs are unchanged.")

        def highlight(_):
            state["highlight"] = not state["highlight"]
            (window.add_class if state["highlight"] else window.remove_class)("form", "highlight")

        def work(_):
            window.set_text("status", "Calculating in a background thread…")
            def calculate():
                total = sum(range(100_000))
                def show():
                    if not window.closed:
                        window.set_text("status", f"Background result: {total:,}. Callback is on the UI owner.")
                app.post(show)
            Thread(target=calculate, name="ui4me-example-worker", daemon=True).start()

        window.on("click", greet, element="greet")
        window.on("click", add, element="add")
        window.on("click", highlight, element="accent")
        window.on("click", work, element="work")
        window.on("click", lambda _: app.open_file(source / "settings.html", title="UI4ME · Settings", width=520, height=380), element="settings")
        window.on("click", lambda _: app.stop(), element="quit")
        app.run()

if __name__ == "__main__":
    run()
