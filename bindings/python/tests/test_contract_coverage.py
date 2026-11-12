"""Public Python API vs the declared wire contract (docs/SUPPORT_PROFILE_V1.json).

Every wire op the profile declares for Python must be emitted by a call to the public API
against the real native library (headless backend), and that call must complete. An honest
refusal from a desktop service the headless backend lacks is a normal result; a protocol or
unknown-op error is not. The op table must equal the declared set, so an op without a public
method (or a method without a profile entry) fails here.
"""
import json
import tempfile
import unittest
from pathlib import Path

from ui4me import App, Ui4meError

PROFILE = Path(__file__).resolve().parents[3] / "docs" / "SUPPORT_PROFILE_V1.json"

HTML = (
    '<style>#box{width:40px;height:20px}</style>'
    '<div id="root"><p id="p">hello world</p><span id="s">x</span><div id="box">box</div>'
    '<div id="scroller" style="height:30px;overflow:auto"><div style="height:300px">tall</div></div>'
    '<ul id="list"><li id="a">a</li><li id="b">b</li><li id="c">c</li></ul>'
    '<form id="f"><input id="i" value="v" required><input id="chk" type="checkbox">'
    '<select id="sel"><option value="1">one</option><option value="2">two</option></select></form>'
    '<div id="ed" contenteditable="true">edit</div>'
    '<dialog id="dlg">dialog</dialog>'
    '<div id="pop" popover>pop</div>'
    '<input id="file" type="file">'
    '</div>'
)

# op -> callable(app, window, tmpdir) performing exactly the public call for that wire op.
CALLS = {
    "add_class": lambda a, w, t: w.add_class("p", "x"),
    "add_stylesheet": lambda a, w, t: w.add_stylesheet("p{color:red}"),
    "append_text": lambda a, w, t: w.append_text("p", "!"),
    "batch": lambda a, w, t: w.batch([{"op": "set_text", "element": "p", "text": "b"}]),
    "cancel_timer": lambda a, w, t: a.timer(10000, lambda e: None).cancel(),
    "capabilities": lambda a, w, t: a.capabilities(),
    "check_validity": lambda a, w, t: w.check_validity("f"),
    "claim_instance": lambda a, w, t: a.claim_instance(),
    "clear_selection": lambda a, w, t: w.clear_selection(),
    "close": lambda a, w, t: w.close(),
    "close_dialog": lambda a, w, t: (w.show_dialog("dlg"), w.close_dialog("dlg", "r")),
    "close_notification": lambda a, w, t: a.close_notification(1),
    "copy_selection": lambda a, w, t: w.copy_selection(),
    "diagnostics": lambda a, w, t: w.diagnostics(),
    "exec_edit": lambda a, w, t: w.exec_edit("ed", "bold"),
    "explain": lambda a, w, t: w.explain("p", "color"),
    "export_pdf": lambda a, w, t: w.export_pdf(Path(t) / "o.pdf"),
    "file_dialog": lambda a, w, t: w.open_file_dialog(lambda r: None),
    "focus": lambda a, w, t: w.focus("i"),
    "get_accessibility_tree": lambda a, w, t: w.accessibility_tree(),
    "get_attribute": lambda a, w, t: w.get_attribute("p", "id"),
    "get_attributes": lambda a, w, t: w.get_attributes("p"),
    "get_checked": lambda a, w, t: w.get_checked("chk"),
    "get_clipboard_html": lambda a, w, t: w.get_clipboard_html(),
    "get_clipboard_text": lambda a, w, t: w.get_clipboard_text(),
    "get_computed_style": lambda a, w, t: w.computed_style("p", "color"),
    "get_diagnostics": lambda a, w, t: w.get_diagnostics(),
    "get_dialog": lambda a, w, t: w.get_dialog("dlg"),
    "get_edit_state": lambda a, w, t: w.get_edit_state("ed"),
    "get_environment": lambda a, w, t: w.environment(),
    "get_files": lambda a, w, t: w.get_files("file"),
    "get_html": lambda a, w, t: w.get_html("p"),
    "get_node": lambda a, w, t: w.get_node(w.node_of("p")),
    "get_options": lambda a, w, t: w.get_options("sel"),
    "get_page_rects": lambda a, w, t: (w.paginate(), w.get_page_rects("p")),
    "get_pointer_capture": lambda a, w, t: w.get_pointer_capture(),
    "get_popover": lambda a, w, t: w.get_popover("pop"),
    "get_rect": lambda a, w, t: w.get_rect("box"),
    "get_scroll": lambda a, w, t: w.get_scroll("scroller"),
    "get_selection": lambda a, w, t: w.get_selection(),
    "get_text": lambda a, w, t: w.get_text("p"),
    "get_validity": lambda a, w, t: w.get_validity("i"),
    "get_value": lambda a, w, t: w.get_value("i"),
    "get_window_state": lambda a, w, t: w.state(),
    "has_element": lambda a, w, t: w.has_element("p"),
    "hide_popover": lambda a, w, t: w.hide_popover("pop"),
    "insert_html": lambda a, w, t: w.append_html("list", "<li>d</li>"),
    "list_monitors": lambda a, w, t: a.monitors(),
    "list_stylesheets": lambda a, w, t: w.stylesheets(),
    "move_element": lambda a, w, t: w.move_element("a", "list", "beforeend"),
    "node_children": lambda a, w, t: w.node_children(w.node_of("list")),
    "node_of": lambda a, w, t: w.node_of("p"),
    "notify": lambda a, w, t: a.notify("t", "b"),
    "open": lambda a, w, t: a.open("<p>x</p>"),
    "open_file": lambda a, w, t: a.open_file(Path(t) / "doc.html"),
    "paginate": lambda a, w, t: w.paginate(),
    "print": lambda a, w, t: w.print_document(),
    "query": lambda a, w, t: w.query("li"),
    "register_hotkey": lambda a, w, t: a.register_hotkey("h", "Ctrl+Alt+K"),
    "remove_attribute": lambda a, w, t: w.remove_attribute("p", "title"),
    "remove_class": lambda a, w, t: w.remove_class("p", "x"),
    "remove_element": lambda a, w, t: w.remove_element("s"),
    "remove_stylesheet": lambda a, w, t: w.remove_stylesheet(w.add_stylesheet("p{color:red}")["sheet"]),
    "remove_tray": lambda a, w, t: a.remove_tray(),
    "render_page": lambda a, w, t: (w.paginate(), w.render_page(0, Path(t) / "p.png")),
    "replace_children_html": lambda a, w, t: w.replace_children_html("list", "<li>z</li>"),
    "replace_stylesheet": lambda a, w, t: w.replace_stylesheet(w.add_stylesheet("p{color:red}")["sheet"], "p{color:blue}"),
    "resize": lambda a, w, t: w.resize(320, 240),
    "scroll_by": lambda a, w, t: w.scroll_by("scroller", dy=5),
    "scroll_into_view": lambda a, w, t: w.scroll_into_view("c"),
    "scroll_to": lambda a, w, t: w.scroll_to("scroller", y=5),
    "select_text": lambda a, w, t: w.select_text("p"),
    "set_attribute": lambda a, w, t: w.set_attribute("p", "title", "t"),
    "set_checked": lambda a, w, t: w.set_checked("chk", True),
    "set_clipboard_html": lambda a, w, t: w.set_clipboard_html("<b>x</b>", "x"),
    "set_clipboard_text": lambda a, w, t: w.set_clipboard_text("x"),
    "set_default_action": lambda a, w, t: w.set_default_action("p", "click"),
    "set_environment": lambda a, w, t: w.set_environment(color_scheme="dark"),
    "set_link_policy": lambda a, w, t: a.set_link_policy(["https"]),
    "set_menu": lambda a, w, t: w.set_menu([{"id": "m", "label": "M"}]),
    "set_pointer_capture": lambda a, w, t: w.set_pointer_capture("box"),
    "set_pointer_grab": lambda a, w, t: w.set_pointer_grab("none"),
    "set_scroll_follow": lambda a, w, t: w.set_scroll_follow("scroller", True),
    "set_selected_values": lambda a, w, t: w.set_selected_values("sel", ["2"]),
    "set_text": lambda a, w, t: w.set_text("p", "t"),
    "set_title": lambda a, w, t: w.set_title("T"),
    "set_tray": lambda a, w, t: a.set_tray(tooltip="t"),
    "set_value": lambda a, w, t: w.set_value("i", "x"),
    "set_window_constraints": lambda a, w, t: w.set_constraints(min_size=(100, 100)),
    "set_window_icon": lambda a, w, t: w.set_icon(),
    "show_context_menu": lambda a, w, t: w.show_context_menu(1, 1, [{"id": "c", "label": "C"}]),
    "show_dialog": lambda a, w, t: w.show_dialog("dlg"),
    "show_popover": lambda a, w, t: w.show_popover("pop"),
    "snapshot": lambda a, w, t: w.snapshot(Path(t) / "s.png"),
    "stats": lambda a, w, t: a.stats(),
    "text_at_point": lambda a, w, t: w.text_at_point(5, 5),
    "text_rects": lambda a, w, t: w.text_rects("p"),
    "timer": lambda a, w, t: a.timer(10000, lambda e: None),
    "toggle_popover": lambda a, w, t: w.toggle_popover("pop"),
    "trim_children": lambda a, w, t: w.trim_children("list", 1),
    "unregister_hotkey": lambda a, w, t: a.unregister_hotkey("h"),
    "window_action": lambda a, w, t: w.window_action("show"),
}

UNPROTOCOL = ("unknown", "unsupported op", "unrecognized", "invalid command", "protocol", "missing field", "unknown variant")


class _Recorder:
    """Stands in for ``app._native`` and records every command sent to the native layer."""

    def __init__(self, native):
        self._native, self.ops = native, []

    def command(self, session, command):
        self.ops.append(command["op"])
        return self._native.command(session, command)

    def __getattr__(self, name):
        return getattr(self._native, name)


def declared(binding):
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    return {c["op"] for c in profile["commands"] if c[binding]}


class ContractCoverageTests(unittest.TestCase):
    def test_table_equals_declared_python_contract(self):
        expected, actual = declared("python"), set(CALLS)
        self.assertEqual(
            (sorted(expected - actual), sorted(actual - expected)), ([], []),
            "ops declared for Python without a public-API call / calls for undeclared ops")

    def test_every_declared_op_is_emitted_by_its_public_call(self):
        failures = []
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "doc.html").write_text("<p>doc</p>", encoding="utf-8")
            for op in sorted(declared("python") & set(CALLS)):
                # A fresh session per op isolates state (window limit, claimed instance, closes).
                with App(backend="headless", handle_sigint=False) as app:
                    window = app.open(HTML)
                    recorder = _Recorder(app._native)
                    app._native = recorder
                    try:
                        CALLS[op](app, window, tmp)
                    except Ui4meError as error:
                        # An honest refusal is fine; a protocol-level rejection is not.
                        if any(word in str(error).lower() for word in UNPROTOCOL):
                            failures.append(f"{op}: protocol error {error}")
                    except Exception as error:  # noqa: BLE001 - report every op, not the first
                        failures.append(f"{op}: {type(error).__name__}: {error}")
                    if op not in recorder.ops:
                        failures.append(f"{op}: public call did not emit it (sent {recorder.ops})")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
