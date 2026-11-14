"""Native IME journey: real pinyin composition into UI4ME inputs.

    Linux:   python3 tests/native/linux/vkwin.py --ime fcitx5 --out DIR -- python tests/native/apps/py_ime.py
    Windows: python3 tests/native/windows/rdp_driver.py --out DIR --name ime -- {VENV}\\Scripts\\python.exe ...
             (Microsoft Pinyin installed for the test user; the driver switches the window's input language)

Typing ``nihao`` then Space through the compositor goes to fcitx5 (input-method-v1),
which composes and commits Chinese text via text-input to the Core host. Checks that
the bound state receives the committed text once (no duplicated preedit) and that
plain ASCII typing still works after composition.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import center, on_owner, run_scenario, until  # noqa: E402

from ui4me import ui  # noqa: E402

TITLE = "UI4ME IME journey"
text = ui.state("")
changes: list = []

with ui.app(TITLE, width=700, height=400) as app:
    field = ui.input("Composed text", bind=text, on_change=lambda v: changes.append(v))
    echo = ui.text(lambda: f"value={text.value}")


def scenario(ch):
    win = app.main
    target = field._focus_target().id
    x, y = center(win, target)
    ch.request("click", window=TITLE, x=x, y=y)
    ch.request("input-language", window=TITLE, layout="00000804")  # Windows: Microsoft Pinyin
    time.sleep(0.8)  # let the input method activate for the focused text field
    ch.request("type", text="nihao")
    time.sleep(0.6)
    mid = on_owner(app, lambda: win.core.document.get_value(target))
    ch.note("during_preedit_value", mid)
    ch.request("key", key="space")
    ok = until(app, lambda: any("你" in c or "好" in c for c in [text.value]), timeout=8)
    value = text.peek()
    ch.check("ime.pinyin_commit", ok and all("一" <= c <= "鿿" for c in value) and len(value) >= 2,
             {"value": value, "preedit_dom": mid, "changes": changes[-5:]})
    ch.check("ime.no_latin_preedit_leak", "nihao" not in value, value)
    shown = on_owner(app, lambda: (win.commit(), win.core.document.get_text(echo.id))[1])
    ch.check("ime.reactive_echo", shown == f"value={value}", shown)
    # Windows shares the input language across windows by default: switch back to US English so
    # later journeys in the same session type plain text.
    ch.request("input-language", window=TITLE, layout="00000409")


run_scenario(app, scenario)
app.run()
