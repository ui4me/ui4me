"""Local chat UI with a simulated streaming reply (no network, no model client)."""
from ui4me import ui

with ui.app("Chat", width=720, height=640) as app:
    async def reply(text: str):
        message = chat.add("assistant", "", name="Echo bot")
        for word in f"You said **{text}**. Here is `code` and a list:\n\n- one\n- two".split(" "):
            message.stream(word + " ")
            await ui.sleep(0.04)

    ui.heading("Chat")
    chat = ui.chat([("assistant", "Hi! Type a message and press **Enter**.")], on_send=reply)
app.run()
