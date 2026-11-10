from ui4me import App

with App() as app:
    window = app.open('<h1>Hello</h1><button id="hello">Click me</button><p id="status">Ready</p>')
    window.on("click", lambda event: window.set_text("status", "Hello from Python"), element="hello")
    app.run()
