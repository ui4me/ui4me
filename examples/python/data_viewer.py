"""Core-only data viewer (UI4ME 1.0). Uses only the public ui4me API.

A data-heavy desktop app: 20 000 generated rows (or ``--csv PATH``) in a paged table that keeps
the DOM bounded (200 rows per page), a live filter, sorting by clicking a column header, row
selection by mouse or keyboard (Up/Down/PageUp/PageDown/Home/End, Enter opens the detail window),
one detail window per row (open and close as often as you like), background loading, filtering,
sorting and aggregation through ``app.run_in_background``, and an export of the current page to
PDF (``window.export_pdf``). Text is selectable and copyable (Ctrl+C).

    python data_viewer.py [--csv PATH] [--rows N] [--state FILE] [--export-dir DIR] [--seconds N]

``--state`` rewrites a small JSON file after each visible change, for the automated journeys
(tests/native/data_journey.py). The page is built in this file: nothing but the installed
``ui4me`` package is needed.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import tempfile
from pathlib import Path

from ui4me import App

PAGE = 200
COLUMNS = ["id", "name", "city", "amount", "score"]
CITIES = ["Praha", "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc", "Hradec", "Pardubice",
          "Zlín", "Jihlava", "Tábor", "Kladno"]

PAGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>UI4ME data viewer</title>
<style>
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.35 sans-serif; color: #1d2330; background: #f3f5f9; }
header { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 10px; background: #24324a; color: #fff; }
header h1 { font-size: 15px; margin: 0 auto 0 0; }
#filter { width: 220px; padding: 3px 6px; }
#app { padding: 8px; }
#summary, #status { font-size: 12px; color: #55607a; margin: 2px 2px 6px; }
#head { width: 100%; table-layout: fixed; border-collapse: collapse; background: #dfe5f0; }
#head th { text-align: left; padding: 4px 8px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #b9c3d6; }
#scroller { height: calc(100vh - 190px); min-height: 120px; overflow: auto; background: #fff; border: 1px solid #ccd3df; }
#grid { width: 100%; table-layout: fixed; border-collapse: collapse; }
#grid td { padding: 2px 8px; height: 22px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid #eef1f6; }
#grid tr.sel td { background: #cfe0ff; }
.num { text-align: right; }
#pager { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
@media print {
  header, #pager, #head, #status { display: none; }
  #scroller { height: auto; overflow: visible; border: 0; }
  #grid td { height: auto; }
}
</style></head>
<body id="page">
<header>
  <h1>UI4ME data viewer</h1>
  <label>Filter <input id="filter" placeholder="type to filter rows"></label>
  <button id="detail">Details</button>
  <button id="export">Export PDF</button>
  <button id="copy">Copy selection</button>
</header>
<div id="app">
  <div id="summary">Loading...</div>
  <table id="head"><colgroup><col style="width:12%"><col style="width:30%"><col style="width:22%"><col style="width:18%"><col style="width:18%"></colgroup>
  <tr><th id="h-0">id</th><th id="h-1">name</th><th id="h-2">city</th><th id="h-3">amount</th><th id="h-4">score</th></tr></table>
  <div id="scroller" tabindex="0"><table id="grid"><colgroup><col style="width:12%"><col style="width:30%"><col style="width:22%"><col style="width:18%"><col style="width:18%"></colgroup><tbody id="rows"></tbody></table></div>
  <div id="pager"><button id="prev">Prev</button><span id="pageinfo">-</span><button id="next">Next</button></div>
  <div id="status">Ready.</div>
</div>
</body></html>"""

DETAIL_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; padding: 12px; font: 14px/1.4 sans-serif; background: #fff; color: #1d2330; }
h2 { font-size: 16px; margin: 0 0 8px; } dl { margin: 0 0 10px; } dt { font-size: 12px; color: #55607a; } dd { margin: 0 0 6px; }
</style></head><body id="d"><h2 id="dtitle">Row {row}</h2><dl>{fields}</dl><button id="dclose">Close</button></body></html>"""


def generate(count: int) -> tuple[list[str], list[tuple]]:
    rows = []
    for i in range(count):
        rows.append((i, f"Name {i:05d}", CITIES[i % len(CITIES)], ((i * 7919) % 100000) / 100.0, (i * 31) % 101))
    return COLUMNS, rows


def load_csv(path: str) -> tuple[list[str], list[tuple]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])[:8]
        rows = []
        for line in reader:
            if len(rows) >= 200000:
                break
            line = (line + [""] * len(header))[:len(header)]
            rows.append(tuple(_number(cell) for cell in line))
    return header or ["value"], rows


def _number(cell: str):
    try:
        return int(cell)
    except ValueError:
        try:
            return float(cell)
        except ValueError:
            return cell


def filter_sort(rows, query: str, column: int, desc: bool):
    """Runs on a worker thread: filter, sort and aggregate. Returns (indices, summary)."""
    needle = query.lower()
    if needle:
        indices = [i for i, row in enumerate(rows) if needle in " ".join(map(str, row)).lower()]
    else:
        indices = list(range(len(rows)))
    if column >= 0:
        def key(i):
            value = rows[i][column]
            return (0, value, "") if isinstance(value, (int, float)) else (1, 0, str(value).lower())
        indices.sort(key=key, reverse=desc)
    numeric = [column_index for column_index in range(len(rows[0]) if rows else 0)
               if rows and isinstance(rows[0][column_index], float)]
    total = average = None
    if numeric and indices:
        values = [rows[i][numeric[0]] for i in indices]
        total, average = sum(values), sum(values) / len(values)
    return indices, {"count": len(indices), "sum": total, "avg": average}


def cell_text(value) -> str:
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=("native", "headless"), default="native")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--seconds", type=float)
    args = parser.parse_args(argv)
    export_dir = args.export_dir or Path(tempfile.gettempdir())
    state = {"loaded": False, "total": 0, "matched": 0, "filter": "", "sort": {"col": -1, "desc": False},
             "page": 0, "pages": 0, "dom_rows": 0, "selected": None, "details_open": [], "details_opened": 0,
             "details_closed": 0, "exports": [], "resized": [], "closed": False, "errors": [], "tasks": 0,
             "summary": "", "keydowns": 0, "copied": None}
    data = {"columns": COLUMNS, "rows": [], "view": [], "generation": 0}
    details: dict[int, object] = {}

    with App(backend=args.backend, app_id="org.ui4me.dataviewer") as app:
        window = app.open(PAGE_HTML, title="UI4ME data viewer", width=1000, height=700)

        def save() -> None:
            if not args.state or window.closed:
                return
            snapshot = dict(state)
            snapshot["details_open"] = sorted(details)
            rects = {}
            for name in ("page", "filter", "export", "copy", "detail", "scroller", "rows", "prev", "next", "h-0", "h-1", "h-2", "h-3", "h-4", "summary"):
                rects[name] = _rect(name)
            snapshot["rects"] = rects
            ids = window.query("#rows tr", limit=PAGE + 10)
            snapshot["dom_rows"] = len(ids)
            snapshot["row_ids"] = ids[:3] + ids[-2:]
            snapshot["row_rects"] = [_rect(i) for i in ids[:6]]
            snapshot["selected_rect"] = _rect(f"r{state['selected']}") if state["selected"] is not None else None
            snapshot["filter_value"] = window.get_value("filter")
            snapshot["scroll"] = window.get_scroll("scroller")
            snapshot["selection"] = window.get_selection()
            try:
                snapshot["clipboard"] = window.get_clipboard_text()
            except Exception as error:  # an empty or unavailable OS clipboard is not fatal here
                snapshot["clipboard"] = f"<unavailable: {error}>"
            snapshot["focus"] = window.query(":focus")
            temporary = args.state.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, args.state)

        def _rect(element: str):
            try:
                return window.get_rect(element)
            except Exception:
                return None

        def status(text: str) -> None:
            window.set_text("status", text)

        def render_page() -> None:
            view = data["view"]
            pages = max(1, (len(view) + PAGE - 1) // PAGE)
            state["page"] = min(state["page"], pages - 1)
            state["pages"] = pages
            start = state["page"] * PAGE
            rows = data["rows"]
            parts = []
            for index in view[start:start + PAGE]:
                cells = "".join(
                    f'<td class="num">{html.escape(cell_text(v))}</td>' if isinstance(v, (int, float)) else f"<td>{html.escape(str(v))}</td>"
                    for v in rows[index])
                cls = ' class="sel"' if index == state["selected"] else ""
                parts.append(f'<tr id="r{index}"{cls}>{cells}</tr>')
            window.replace_children_html("rows", "".join(parts))
            window.set_text("pageinfo", f"Page {state['page'] + 1} / {pages}")
            window.set_text("summary", state["summary"])

        def refresh(reset_page: bool = True) -> None:
            """Filter and sort on a worker thread; the newest request wins."""
            data["generation"] += 1
            generation = data["generation"]
            query, column, desc = state["filter"], state["sort"]["col"], state["sort"]["desc"]

            def done(result) -> None:
                if generation != data["generation"] or window.closed:
                    return
                data["view"], summary = result
                state["matched"] = summary["count"]
                state["tasks"] += 1
                text = f"{summary['count']} of {state['total']} rows"
                if summary["sum"] is not None:
                    text += f" - total {summary['sum']:,.2f}, average {summary['avg']:,.2f}"
                state["summary"] = text
                if reset_page:
                    state["page"] = 0
                render_page()
                for position, name in enumerate(data["columns"][:5]):
                    mark = ("▲" if not desc else "▼") if position == column else ""
                    window.set_text(f"h-{position}", f"{name} {mark}".strip())
                status(f"Showing {summary['count']} rows.")
                save()

            def failed(error: BaseException) -> None:
                state["errors"].append(repr(error))
                status(f"Error: {error}")
                save()

            app.run_in_background(filter_sort, data["rows"], query, column, desc, on_done=done, on_error=failed)

        def loaded(result) -> None:
            data["columns"], data["rows"] = result
            state["loaded"] = True
            state["total"] = len(data["rows"])
            refresh()

        def load() -> tuple[list[str], list[tuple]]:
            return load_csv(str(args.csv)) if args.csv else generate(args.rows)

        def select_position(position: int) -> None:
            view = data["view"]
            if not view:
                return
            position = max(0, min(len(view) - 1, position))
            old = state["selected"]
            state["selected"] = view[position]
            new_page = position // PAGE
            if new_page != state["page"]:
                state["page"] = new_page
                render_page()
            else:
                if old is not None and window.has_element(f"r{old}"):
                    window.remove_class(f"r{old}", "sel")
                window.add_class(f"r{state['selected']}", "sel")
            window.scroll_into_view(f"r{state['selected']}", block="nearest")
            status(f"Selected row {state['selected']} (position {position + 1} of {len(view)}).")
            save()

        def selected_position() -> int:
            if state["selected"] is None:
                return -1
            try:
                return data["view"].index(state["selected"])
            except ValueError:
                return -1

        def open_detail(index: int | None = None) -> None:
            index = state["selected"] if index is None else index
            if index is None:
                status("Select a row first.")
                return save()
            existing = details.get(index)
            if existing is not None and not existing.closed:
                existing.activate()
                return
            row = data["rows"][index]
            fields = "".join(f"<dt>{html.escape(str(name))}</dt><dd id=\"f{n}\">{html.escape(cell_text(v))}</dd>"
                             for n, (name, v) in enumerate(zip(data["columns"], row)))
            detail = app.open(DETAIL_HTML.replace("{row}", str(index)).replace("{fields}", fields),
                              title=f"UI4ME row {index}", width=360, height=300)
            details[index] = detail
            state["details_opened"] += 1
            save()

        def close_detail_window(window_id: int) -> None:
            for index, detail in list(details.items()):
                if detail.id == window_id:
                    del details[index]
                    state["details_closed"] += 1
                    save()
                    return

        def export(_=None) -> None:
            path = export_dir / f"data-view-{len(state['exports']) + 1}.pdf"
            try:
                result = window.export_pdf(path, size="A4", title="UI4ME data viewer")
                state["exports"].append({"path": str(path), "pages": result.get("pages"), "bytes": path.stat().st_size})
                status(f"Exported {result.get('pages')} page(s) to {path.name}.")
            except Exception as error:
                state["errors"].append(f"export: {error}")
                status(f"Export failed: {error}")
            save()

        def sort_by(column: int) -> None:
            current = state["sort"]
            state["sort"] = {"col": column, "desc": (not current["desc"]) if current["col"] == column else False}
            refresh()

        def clicked(event: dict) -> None:
            element = event.get("element") or ""
            if event.get("window") != window.id:
                if element == "dclose":
                    for detail in list(details.values()):
                        if detail.id == event.get("window"):
                            detail.close()
                return
            if element.startswith("r") and element[1:].isdigit():
                index = int(element[1:])
                if index in set(data["view"][state["page"] * PAGE:(state["page"] + 1) * PAGE]):
                    select_position(data["view"].index(index))
                window.focus("scroller")
            elif element.startswith("h-"):
                sort_by(int(element[2:]))
            elif element == "next":
                state["page"] = min(state["pages"] - 1, state["page"] + 1)
                render_page()
                save()
            elif element == "prev":
                state["page"] = max(0, state["page"] - 1)
                render_page()
                save()
            elif element == "detail":
                open_detail()
            elif element == "export":
                export()
            elif element == "copy":
                state["copied"] = window.copy_selection()
                status(f"Copied {len(state['copied'])} characters." if state["copied"] else "Nothing selected.")
                save()

        def keydown(event: dict) -> None:
            key = event.get("key")
            if event.get("window") == window.id:
                state["keydowns"] += 1
                position = selected_position()
                if key == "ArrowDown":
                    select_position(position + 1)
                elif key == "ArrowUp":
                    select_position(max(0, position - 1) if position >= 0 else 0)
                elif key == "PageDown":
                    select_position(position + 10)
                elif key == "PageUp":
                    select_position(max(0, position - 10))
                elif key == "Home" and event.get("element") != "filter":
                    select_position(0)
                elif key == "End" and event.get("element") != "filter":
                    select_position(len(data["view"]) - 1)
                elif key == "Enter" and not event.get("ctrl"):
                    open_detail()
                elif key == "Escape" and window.get_value("filter"):
                    window.set_value("filter", "")
                    state["filter"] = ""
                    refresh()
            elif key == "Escape":
                for detail in list(details.values()):
                    if detail.id == event.get("window"):
                        detail.close()

        def typed(event: dict) -> None:
            if event.get("window") == window.id and event.get("element") == "filter":
                state["filter"] = window.get_value("filter")
                refresh()

        def closed(event: dict) -> None:
            if event.get("window") == window.id:
                state["closed"] = True
                for detail in list(details.values()):
                    if not detail.closed:
                        detail.close()
                app.stop()
            else:
                close_detail_window(event.get("window"))

        app.on("click", clicked)
        app.on("keydown", keydown)
        app.on("input", typed)
        app.on("closed", closed)
        def resized(event: dict) -> None:
            if event.get("window") == window.id:  # detail windows resize too: only the main window counts
                state["resized"] = (state["resized"] + [[event.get("width"), event.get("height")]])[-50:]
                save()

        app.on("resized", resized)
        app.on("error", lambda e: state["errors"].append(e))
        window.on("mouseup", lambda _: save())
        window.on("keyup", lambda _: save())
        window.on("scroll", lambda _: save(), element="scroller")
        app.on("started", lambda _: save())
        status("Loading rows in the background...")
        app.run_in_background(load, on_done=loaded, on_error=lambda e: (state["errors"].append(repr(e)), status(f"Load failed: {e}"), save()))
        if args.seconds:
            app.timer(int(args.seconds * 1000), lambda _: app.stop())
        app.run()
    if args.state:
        final = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
        final.update({k: state[k] for k in ("closed", "details_opened", "details_closed", "exports", "errors", "total")})
        final["exited"] = True
        args.state.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
