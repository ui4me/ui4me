"""Native journey: buttons, text input, checkbox, select, focus, keyed list, CSS replacement.

Run through a driver (tests/native/linux/vkwin.py or the Windows driver):
    ui4me-run tests/native/apps/py_basic.py
Every check uses real compositor/OS input and reads results back from the
real Core document; nothing is simulated inside the app.
"""
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import center, on_owner, rect, run_scenario, until  # noqa: E402

from ui4me import ui  # noqa: E402

TITLE = "UI4ME basic journey"

clicks = ui.state(0)
name = ui.state("")
agree = ui.state(False)
color = ui.state("red")
items = ui.state([{"id": i, "label": f"Item {i}"} for i in range(1, 6)])
events: list = []

with ui.app(TITLE, width=900, height=760) as app:
    with ui.row():
        button = ui.button("Press me", on_click=lambda: clicks.set(clicks.value + 1))
        count = ui.text(lambda: f"clicks={clicks.value}")
    field = ui.input("Name", bind=name, on_submit=lambda v: events.append(("submit", v)))
    second = ui.input("Second")
    greeting = ui.heading(lambda: f"Hello {name.value or 'nobody'}")
    box = ui.checkbox("I agree", bind=agree)
    choice = ui.select("Color", options=["red", "green", "blue"], bind=color)
    styled = ui.text("styled text", classes="probe-styled")
    with ui.row():
        when = ui.date("When", value=dt.date(2026, 2, 14))
        colour = ui.color("Colour")
    rows = {}

    def render(item):
        with ui.row() as r:
            ui.text(item["label"])
            entry = ui.input("note")
        rows[item["id"]] = (r, entry)

    keyed = ui.each(items, key="id", render=render)


def ctl(component):
    return component._focus_target().id


def scenario(ch):
    win = app.main
    # 1. Real click on a button -> on_click -> reactive text in the real DOM.
    x, y = center(win, button.id)
    ch.request("click", window=TITLE, x=x, y=y)
    ok = until(app, lambda: clicks.value == 1)
    dom = on_owner(app, lambda: win.core.document.get_text(count.id))
    ch.check("button.click", ok and dom == "clicks=1", {"clicks": clicks.peek(), "dom": dom})
    ch.request("click", window=TITLE, x=x, y=y)
    ch.check("button.click.twice", until(app, lambda: clicks.value == 2), clicks.peek())

    # 2. Real keyboard text into a bound input -> Signal -> computed heading.
    x, y = center(win, ctl(field))
    ch.request("click", window=TITLE, x=x, y=y)
    ch.request("type", text="Ada Lovelace")
    ok = until(app, lambda: name.value == "Ada Lovelace")
    heading = on_owner(app, lambda: win.core.document.get_text(greeting.id))
    ch.check("input.type.binds", ok and heading == "Hello Ada Lovelace", {"value": name.peek(), "heading": heading})
    ch.request("key", key="enter")
    ch.check("input.enter.submit", until(app, lambda: ("submit", "Ada Lovelace") in events), events)
    focused = on_owner(app, lambda: win.core.document.focused_element())
    ch.check("focus.after_click", focused and focused.get("element") == ctl(field), focused)
    # Programmatic state -> DOM value (no echo loop).
    on_owner(app, lambda: name.set("Grace"))
    value = until(app, lambda: (win.commit(), win.core.document.get_value(ctl(field)))[1] == "Grace")
    ch.check("input.state_to_dom", value, on_owner(app, lambda: win.core.document.get_value(ctl(field))))

    # 3. Tab moves native focus to the next field.
    ch.request("key", key="tab")
    focused = until(app, lambda: (win.core.document.focused_element() or {}).get("element") == ctl(second))
    ch.check("focus.tab_next", focused, on_owner(app, lambda: win.core.document.focused_element()))

    # 4. Checkbox via real click.
    x, y = center(win, ctl(box))
    ch.request("click", window=TITLE, x=x, y=y)
    ch.check("checkbox.click", until(app, lambda: agree.value is True),
             {"agree": agree.peek(), "rect": rect(win, ctl(box))})
    on_owner(app, lambda: agree.set(False))
    checked = until(app, lambda: (win.commit(), not win.core.document.get_checked(ctl(box)))[1])
    ch.check("checkbox.state_to_dom", checked, None)

    # 5. Select via keyboard on the focused native <select>.
    on_owner(app, lambda: choice.focus())
    time.sleep(0.2)
    ch.request("key", key="down")
    picked = until(app, lambda: color.value == "green", timeout=5)
    ch.check("select.keyboard", picked, {"color": color.peek()})
    if not picked:
        ch.request("key", key="escape")
    on_owner(app, lambda: color.set("blue"))
    dom = until(app, lambda: (win.commit(), win.core.document.get_value(ctl(choice)))[1] == "blue")
    ch.check("select.state_to_dom", dom, None)

    # 6. Keyed list: type into row 3, reverse + remove + insert; DOM node and typed value survive.
    r3, e3 = rows[3]
    x, y = center(win, ctl(e3))
    ch.request("click", window=TITLE, x=x, y=y)
    ch.request("type", text="keep")
    until(app, lambda: e3.value == "keep")
    node_before = on_owner(app, lambda: win.core.document.node(ctl(e3)).id)

    def mutate():
        new = list(reversed(items.peek()))
        new = [i for i in new if i["id"] != 2] + [{"id": 9, "label": "Item 9"}]
        items.set(new)
    on_owner(app, mutate)
    time.sleep(0.3)

    labels = on_owner(app, lambda: [rows[i][0].parent.root.id for i in (5, 4, 3, 1, 9)])
    dom_order = on_owner(app, lambda: [e for e in win.core.document.query(f"#{keyed.root.id} > *").get("ids", [])])
    node_after = on_owner(app, lambda: win.core.document.node(ctl(e3)).id)
    typed = on_owner(app, lambda: win.core.document.get_value(ctl(e3)))
    ch.check("each.reorder.order", dom_order == labels, {"dom": dom_order, "expected": labels})
    ch.check("each.reorder.preserves_dom", node_before == node_after and typed == "keep",
             {"before": node_before, "after": node_after, "typed": typed})
    ch.check("each.remove.disposes", rows[2][0].disposed and rows[2][1].disposed, None)
    diag = on_owner(app, lambda: app.diagnostics())
    ch.note("diagnostics.after_each", diag)

    # 7. CSS: full visual replacement twice; the computed style changes, sheet count stays bounded.
    def sheets():
        return len(win.core.document.stylesheets())
    before = on_owner(app, sheets)
    on_owner(app, lambda: app.theme.load(".probe-styled { color: rgb(1, 2, 3); }", mode="replace"))
    c1 = on_owner(app, lambda: win.core.document.computed_style(["color"], styled.id))
    on_owner(app, lambda: app.theme.load(".probe-styled { color: rgb(200, 10, 20); }", mode="replace"))
    c2 = on_owner(app, lambda: win.core.document.computed_style(["color"], styled.id))
    after = on_owner(app, sheets)
    ch.check("css.replace.applies", "1, 2, 3" in str(c1) and "200, 10, 20" in str(c2), {"c1": c1, "c2": c2})
    ch.check("css.replace.no_sheet_leak", before == after, {"before": before, "after": after})
    on_owner(app, lambda: app.theme.reset_css())
    # 8. In-window date picker and colour swatches with real clicks and typing.
    x, y = center(win, when.toggle_el.id)
    ch.request("click", window=TITLE, x=x, y=y)
    opened = until(app, lambda: when.calendar_open)
    day = when._day_id(dt.date(2026, 2, 20))
    focused = until(app, lambda: (win.core.document.focused_element() or {}).get("element") == when._day_id(dt.date(2026, 2, 14)))
    x, y = center(win, day)
    ch.request("click", window=TITLE, x=x, y=y)
    ch.check("date.calendar.click_day", opened and until(app, lambda: when.value == dt.date(2026, 2, 20))
             and not when.calendar_open, {"value": str(when.state.peek()), "focused_selected_day": bool(focused)})
    x, y = center(win, ctl(when))
    ch.request("click", window=TITLE, x=x, y=y)
    ch.request("key", key="end")
    ch.request("type", text="x")
    ch.check("date.invalid_text_error", until(app, lambda: when.error == "Enter a date as YYYY-MM-DD"), when.error)
    x, y = center(win, f"{colour.swatches.id}-6")
    ch.request("click", window=TITLE, x=x, y=y)
    ch.check("color.swatch_click", until(app, lambda: colour.value == "#16a34a"), colour.state.peek())
    errors = on_owner(app, lambda: app.error_count)
    ch.check("no.app.errors", errors == 0, on_owner(app, lambda: app.last_error))


run_scenario(app, scenario)
app.run()
