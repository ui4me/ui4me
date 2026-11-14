"""Native journey for the UI4ME 2.1 additions, started DIRECTLY (``python py_v21.py``).

No ``ui4me-run``: Core 1.0.1 ``Application.start`` bootstraps the host, which runs this
script again as its supervised backend. Run through a driver:

    python3 tests/native/linux/vkwin.py --out DIR -- python tests/native/apps/py_v21.py

Covers fieldset/multiselect, adjustable split (keyboard), metric, tooltip (focus), copy
button + clipboard, change-mode form validation and dirty state, table sort/search/
selection with the keyboard, dialog Escape + focus return, toast, theme switch, a raising
callback that must not stop the app, and a final user-approved native close.
"""
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from channel import center, on_owner, run_scenario, until  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _frame_counter  # noqa: E402,F401  (no-op unless UI4ME_DIAG_FRAMES is set)

from ui4me import ui  # noqa: E402

TITLE = "UI4ME 2.1 journey"
log: list = []


@dataclasses.dataclass
class Profile:
    name: str = dataclasses.field(default="", metadata={"required": True, "min_length": 3})
    email: str = dataclasses.field(default="", metadata={"pattern": "email"})


PEOPLE = [{"id": i, "name": n, "team": t} for i, (n, t) in enumerate(
    [("Mallory", "Ops"), ("Alice", "Dev"), ("Trent", "Ops"), ("Bob", "Dev"), ("Carol", "QA")], start=1)]

jobs = ui.state(4)
features = ui.state(("alpha",))
chosen = ui.state(None)
submitted: list = []


def explode(event):
    raise RuntimeError("deliberate callback failure")


def bump(event):
    jobs.set(jobs.value + 1)


def toast(event):
    ui.notify("Saved notification", kind="success", duration=1.5)


with ui.app(TITLE, width=1100, height=900) as app:
    with ui.row():
        metric = ui.metric("Pending jobs", lambda: str(jobs.value), detail="queue")
        more = ui.button("More jobs", on_click=bump)
        boom = ui.button("Fail", on_click=explode, variant="secondary")
        note = ui.button("Notify", on_click=toast, variant="secondary")
        with ui.tooltip("Copies the sample text") as tip:
            copy = ui.copy_button("Sample ✓ text", on_copy=lambda v: log.append(("copied", v)))
    with ui.fieldset("Options", description="Choose enabled features"):
        multi = ui.multiselect("Features", options={"alpha": "Alpha", "beta": "Beta", "gamma": "Gamma"},
                               bind=features)
    split = ui.resizable_split(percent=30, minimum=20, maximum=80, label="Pane size")
    with split.side:
        ui.text("side pane")
    with split.main:
        ui.text("main pane")
    form = ui.form(Profile, validation_mode="change", on_submit=lambda v: submitted.append(v))
    table = ui.table(PEOPLE, key="id", columns=["name", "team"], sort=True, search=True,
                     page_size=None, selected=chosen)
    opener = ui.button("Open dialog", variant="secondary", on_click=lambda: dlg.open())
    with ui.dialog("Confirm") as dlg:
        ui.text("Dialog body")
        ui.button("OK", on_click=lambda: dlg.close("ok"))

app.main.on_close(lambda: log.append(("main_closed",)))


def ctl(component):
    return component._focus_target().id


def click(ch, win, element_id):
    x, y = center(win, element_id)
    ch.request("click", window=TITLE, x=x, y=y)


def focused(win):
    return (win.core.document.focused_element() or {}).get("element")


def scenario(ch):
    win = app.main
    doc = lambda: win.core.document  # noqa: E731
    ch.note("launch", {"direct": "UI4ME_ENDPOINT handled by Core Application.start", "argv": sys.argv})

    # 1. Metric reacts to a real button click.
    ch.note("step", 1)
    click(ch, win, more.id)
    ok = until(app, lambda: jobs.value == 5)
    text = on_owner(app, lambda: doc().get_text(metric._value_el.id))
    ch.check("metric.click_updates", ok and text == "5", {"jobs": jobs.peek(), "dom": text})

    # 2. Multi-select: click Beta on, Alpha off.
    ch.note("step", 2)
    click(ch, win, ctl(multi.items["beta"]))
    click(ch, win, ctl(multi.items["alpha"]))
    ok = until(app, lambda: tuple(features.value) == ("beta",))
    ch.check("multiselect.clicks", ok, features.peek())
    on_owner(app, lambda: multi.set_value(["gamma", "alpha"]))
    ok = until(app, lambda: (win.commit(), doc().get_checked(ctl(multi.items["gamma"]))
                             and not doc().get_checked(ctl(multi.items["beta"])))[1])
    ch.check("multiselect.state_to_dom", ok, features.peek())

    # 3. Adjustable split with the keyboard (focus the range, Right x3).
    ch.note("step", 3)
    click(ch, win, split._control.id)
    start = split.position.peek()
    for _ in range(3):
        ch.request("key", key="right")
    ok = until(app, lambda: split.position.value == start + 3, timeout=5)
    style = on_owner(app, lambda: win.core.get_attribute(split._panes.id, "style"))
    ch.check("split.keyboard_resizes", ok and f"{start + 3}%" in str(style),
             {"start": start, "now": split.position.peek(), "style": style})

    # 4. Tooltip: hidden until its trigger has focus (focus-within), then visible.
    ch.note("step", 4)
    tip_el = tip.root.children[1].id
    hidden = on_owner(app, lambda: doc().computed_style(["visibility"], tip_el))
    on_owner(app, lambda: doc().focus(copy.root.id))
    time.sleep(0.3)
    shown = on_owner(app, lambda: doc().computed_style(["visibility"], tip_el))
    ch.check("tooltip.focus_within_shows", "hidden" in str(hidden) and "visible" in str(shown),
             {"before": hidden, "after": shown})

    # 5. Copy button -> Core clipboard (read back through the native clipboard).
    ch.note("step", 5)
    click(ch, win, copy.root.id)
    ok = until(app, lambda: ("copied", "Sample ✓ text") in log, timeout=5)
    text = on_owner(app, lambda: app.clipboard.paste())
    ch.check("copy_button.clipboard_roundtrip", ok and text == "Sample ✓ text", {"clipboard": text})

    # 6. Form with change-mode validation and dirty tracking, real typing.
    ch.note("step", 6)
    name_field, email_field = form.fields["name"], form.fields["email"]
    click(ch, win, ctl(name_field))
    ch.request("type", text="Al")
    ok = until(app, lambda: name_field.error == "Use at least 3 characters", timeout=5)
    ch.check("form.change_validation_error", ok and form.dirty.value and form.valid.value is False,
             {"error": name_field.error, "dirty": form.dirty.peek(), "valid": form.valid.peek()})
    err_dom = on_owner(app, lambda: doc().get_text(name_field.error_el.id) if hasattr(name_field, "error_el") else None)
    ch.note("form.error_dom", err_dom)
    ch.request("type", text="ice")
    ok = until(app, lambda: name_field.error is None and form.valid.value, timeout=5)
    ch.check("form.change_validation_clears", ok, {"error": name_field.error, "valid": form.valid.peek()})
    click(ch, win, ctl(email_field))
    ch.request("type", text="not-an-email")
    until(app, lambda: email_field.error is not None, timeout=5)
    ch.request("key", key="enter")
    time.sleep(0.4)
    ch.check("form.invalid_submit_blocked", not submitted and email_field.error is not None,
             {"submitted": submitted, "error": email_field.error})
    for _ in range(len("not-an-email")):
        ch.request("key", key="backspace", settle=0.02)
    ch.request("type", text="alice@example.org")
    until(app, lambda: email_field.error is None, timeout=5)
    ch.request("key", key="enter")
    ok = until(app, lambda: len(submitted) == 1, timeout=5)
    ch.check("form.submit_valid", ok and submitted and submitted[0].name == "Alice"
             and submitted[0].email == "alice@example.org" and not form.dirty.value,
             {"submitted": [dataclasses.asdict(s) for s in submitted], "dirty": form.dirty.peek()})

    # 7. Table: click Name header to sort, search by typing, select with click + ArrowDown.
    ch.note("step", 7)
    name_button = table._sort_buttons["name"]
    click(ch, win, name_button.id)
    ok = until(app, lambda: [r["name"] for r in table.page_rows.value][:2] == ["Alice", "Bob"])
    sort_attr = on_owner(app, lambda: win.core.get_attribute(table._headers[0].id, "aria-sort"))
    ch.check("table.sort_click", ok and sort_attr == "ascending", {"rows": [r["name"] for r in table.page_rows.peek()],
                                                                   "aria-sort": sort_attr})
    click(ch, win, ctl(table.search_input))
    ch.request("type", text="ops")
    ok = until(app, lambda: sorted(r["name"] for r in table.page_rows.value) == ["Mallory", "Trent"])
    ch.check("table.search_typing", ok, [r["name"] for r in table.page_rows.peek()])
    first = table.row_component(1)
    click(ch, win, first.root.id)
    ok = until(app, lambda: chosen.value == 1, timeout=5)
    ch.request("key", key="down")
    ok2 = until(app, lambda: chosen.value == 3, timeout=5)
    ch.check("table.select_click_and_arrow", ok and ok2, {"selected": chosen.peek(),
                                                          "focused": on_owner(app, lambda: focused(win))})

    # 8. Dialog: open with a real click, Escape closes, focus returns to the opener.
    ch.note("step", 8)
    click(ch, win, opener.id)
    opened = until(app, lambda: dlg.is_open.value, timeout=5)
    time.sleep(0.3)
    ch.request("key", key="escape")
    closed = until(app, lambda: not (dlg.is_open.value), timeout=5)
    back = until(app, lambda: focused(win) == opener.id, timeout=5)
    ch.check("dialog.escape_and_focus_return", opened and closed and back,
             {"focused": on_owner(app, lambda: focused(win)), "opener": opener.id})

    # 9. Toast appears in the live region and expires.
    ch.note("step", 9)
    click(ch, win, note.id)
    seen = until(app, lambda: len(doc().query(".u4-toast").get("ids", [])) >= 1, timeout=5)
    gone = until(app, lambda: len(doc().query(".u4-toast").get("ids", [])) == 0, timeout=8)
    ch.check("toast.shows_and_expires", seen and gone, None)

    # 10. Theme switch changes computed colors; switching back restores them.
    ch.note("step", 10)
    before = on_owner(app, lambda: str(doc().computed_style(["color"], note.id)))
    on_owner(app, lambda: app.theme.set("dark"))
    time.sleep(0.3)
    dark = on_owner(app, lambda: str(doc().computed_style(["color"], note.id)))
    on_owner(app, lambda: app.theme.set("light"))
    time.sleep(0.3)
    light = on_owner(app, lambda: str(doc().computed_style(["color"], note.id)))
    ch.check("theme.dark_light_switch", dark != light, {"initial": before, "dark": dark, "light": light})

    # 11. A raising callback is reported (toast + counter) and the app keeps working.
    ch.note("step", 11)
    errors = on_owner(app, lambda: app.error_count)
    click(ch, win, boom.id)
    reported = until(app, lambda: app.error_count == errors + 1, timeout=5)
    click(ch, win, more.id)
    alive = until(app, lambda: jobs.value == 6, timeout=5)
    ch.check("error.callback_isolated", reported and alive,
             {"errors": on_owner(app, lambda: app.error_count), "last": on_owner(app, lambda: app.last_error)})
    on_owner(app, lambda: setattr(app, "error_count", 0))

    diag = on_owner(app, lambda: app.diagnostics())
    ch.note("diagnostics", diag)
    ch.done()  # remaining verdict: exit code 0 and no leftover processes after native close
    ch.request("native-close", window=TITLE)
    time.sleep(10)
    ch.fatal("app did not exit after an allowed native close")


run_scenario(app, scenario)
app.run()
from channel import Channel  # noqa: E402
Channel().check("window.main.on_close_once", log.count(("main_closed",)) == 1, log)
