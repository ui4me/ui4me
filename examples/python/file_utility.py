"""J3: desktop utility — sidebar pages, native open/save dialogs, clipboard, shortcuts, second window."""
from pathlib import Path

from ui4me import ui

with ui.app("File Utility", width=960, height=640) as app:
    path = ui.state(None)
    text = ui.state("")

    async def open_file():
        chosen = await app.dialogs.open_file(title="Open a text file", filters={"Text": ["txt", "md", "py", "log"]})
        if chosen is not None:
            path.set(chosen)
            text.set(await app.tasks.run(lambda: chosen.read_text(encoding="utf-8", errors="replace")))
            ui.notify(f"Opened {chosen.name}")

    async def save_as():
        target = await app.dialogs.save_file(title="Save as", file_name=path.value.name if path.value else "note.txt")
        if target is not None:
            await app.tasks.run(lambda: Path(target).write_text(text.value, encoding="utf-8"))
            path.set(target)
            ui.notify(f"Saved {target.name}", kind="success")

    def copy_all():
        app.clipboard.copy(text.value)
        ui.notify("Copied to clipboard")

    def about():
        with app.window("About File Utility", width=380, height=220):
            ui.heading("File Utility")
            ui.text("A UI4ME UI example: native dialogs, background file IO, clipboard and windows.")

    app.commands.add("Open", open_file, shortcut="Ctrl+O")
    app.commands.add("Save as", save_as, shortcut="Ctrl+S")

    def editor():
        with ui.row():
            ui.button("Open…", on_click=open_file)
            ui.button("Save as…", variant="secondary", on_click=save_as)
            ui.button("Copy all", variant="ghost", on_click=copy_all, disabled=lambda: not text.value)
            ui.spacer()
            ui.caption(lambda: str(path.value) if path.value else "No file — Ctrl+O to open")
        ui.textarea("Content", bind=text, rows=18)
        ui.caption(lambda: f"{len(text.value):,} characters · {len(text.value.splitlines()):,} lines")

    def settings():
        ui.heading("Settings", level=3)
        ui.radio("Theme", options=["system", "light", "dark"], value=app.theme.name, horizontal=True,
                 on_change=app.theme.set)
        ui.button("About…", variant="outline", on_click=about)

    ui.navigation({"Editor": editor, "Settings": settings}, title="File Utility")
app.run()
