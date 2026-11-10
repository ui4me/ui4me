"""A small native application; install the ui4me wheel before running it."""
from threading import Thread

from ui4me import App


FORM = '''<body style="background-color: #F3F6FA">
<h1 style="color: blue">ui4me foundation</h1>
<label>Your name:</label>
<input id="name" type="text" value="World">
<button id="greet">Greet</button>
<button id="second">Open second window</button>
<button id="resize">Resize this window</button>
<button id="work">Run background work</button>
<button id="quit">Quit now</button>
<p id="status">Try a button. The first close request is intercepted.</p>
</body>'''


with App() as app:
    window = app.open(FORM, title="ui4me - Python", width=760, height=700)
    state = {"confirm_close": False, "closed": False}

    def greet(_event):
        window.set_text("status", f"Hello, {window.get_value('name')}!")

    def open_second(_event):
        app.open('<h1>Second window</h1><p>Close this window independently.</p>',
                 title="ui4me - second window", width=500, height=300)

    def close_requested(_event):
        if not state["confirm_close"]:
            state["confirm_close"] = True
            window.set_text("status", "Close again to exit, or use Quit now.")
            return False

    def work(_event):
        window.set_text("status", "Working in a background thread...")

        def calculate():
            result = sum(range(100_000))

            def display():
                if not state["closed"]:
                    window.set_text("status", f"Background result: {result}")

            # Posting is safe from the worker. The returned future is settled or
            # cancelled by the app; never wait on it from the UI thread.
            app.post(display)

        Thread(target=calculate, name="ui4me-demo-worker", daemon=True).start()

    window.on("click", greet, element="greet")
    window.on("click", open_second, element="second")
    window.on("click", lambda _: window.resize(860, 760), element="resize")
    window.on("click", work, element="work")
    window.on("click", lambda _: app.stop(), element="quit")
    window.on("close_requested", close_requested)
    window.on("closed", lambda _: state.update(closed=True))
    app.run()
