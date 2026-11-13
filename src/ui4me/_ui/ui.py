"""The public UI4ME UI API: ``from ui4me import ui``.

Everything a typical application needs is a function here. Each returns a *ref* (a
component object) with ``.classes``, ``.style``, ``.attr``, ``.on``, ``.core_element()``
and ``.dispose()``. Values given as ``ui.state``, ``ui.computed`` or a ``lambda`` are
reactive: the UI updates automatically when the state they read changes.
"""
from __future__ import annotations

import contextlib
import functools
from typing import Any, Callable, Hashable, Iterator, Mapping, Sequence, TypeVar

from .desktop import NativeMenuItem
from .aio import UiFuture
from .app import UiApp
from .component import Component, Container, Frame, current_app, current_frame, pop, push
from .components.basic import (Badge, Button, Checkbox, Divider, Heading, Html, NumberField, PasswordField,
                               Progress, RadioGroup, Select, Slider, Spacer, Spinner, Text, TextArea, TextField)
from .components.feedback import Alert, Dialog, StateView, Toast, confirm, notify
from .components.layout import (Card, Column, Content, Grid, Navigation, Row, Scroll, Shell, Sidebar, Split,
                                Stack, Tabs)
from .components.regions import Each, When
from .errors import UiError
from .reactive import Computed, Reaction, Signal, current_scheduler, untracked

T = TypeVar("T")

__all__ = [
    "app", "state", "computed", "effect", "batch", "untracked", "text", "heading", "caption", "badge", "button",
    "input", "password", "textarea", "number", "checkbox", "switch", "radio", "select", "slider", "row", "column",
    "stack", "card", "grid", "scroll", "spacer", "divider", "shell", "sidebar", "content", "split", "tabs",
    "navigation", "navigate", "when", "each", "notify", "dialog", "confirm", "alert", "empty", "loading",
    "error_state", "spinner", "progress", "html", "css", "theme", "markdown", "code", "table", "form", "log",
    "chat", "image", "component", "sleep", "stylesheet", "stylesheet_file", "current_app", "Signal", "Computed", "NativeMenuItem", "surface", "paper", "toolbar", "header", "footer", "statusbar", "section",
    "center", "sticky", "container", "aspect", "kbd", "inline_code", "mark", "avatar", "link", "icon",
    "icon_names", "icon_button", "breadcrumbs", "disclosure", "accordion", "drawer", "segmented", "tree",
    "TreeNode", "slot", "date", "time", "datetime", "month", "week", "color", "email", "url", "search",
    "telephone", "density", "theme_preset", "combobox", "command_palette", "path", "file_input", "query_table", "PageResult", "menu", "MenuItem", "progress_ring", "sparkline",
]


# ---- application and state -----------------------------------------------------------------

def app(title: str = "UI4ME", *, width: int = 960, height: int = 680, theme: str = "system",
        backend: str | None = None, app_id: str | None = None, css: str | None = None,
        assets: Any = None, on_error: Callable | None = None) -> UiApp:
    """Create an application. Use as ``with ui.app('Title') as app: ...`` then ``app.run()``.

    ``assets`` is a directory for local images/fonts/stylesheets referenced by relative URLs.
    """
    return UiApp(title, width=width, height=height, theme=theme, backend=backend, app_id=app_id, css=css,
                 assets=assets, on_error=on_error)


def image(src: str, *, alt: str = "", width: str | None = None, height: str | None = None, **kw: Any):
    """Local image relative to ``ui.app(assets=...)`` (no remote fetches). ``src`` may be reactive."""
    from .components.basic import Image
    return Image(src, alt=alt, width=width, height=height, **kw)


def state(initial: T, *, name: str | None = None, equals: Callable[[Any, Any], bool] | None = None) -> Signal[T]:
    """Observable value: read ``.value``, write ``.set(v)`` / ``.update(fn)``."""
    return Signal(initial, name=name, equals=equals)


def computed(fn: Callable[[], T], *, name: str | None = None) -> Computed[T]:
    """Derived value recomputed when the state it reads changes (cached)."""
    return Computed(fn, name=name)


def _scheduler():
    frame = current_frame(required=False)
    return frame.app.scheduler if frame is not None else current_scheduler()


def effect(fn: Callable[[], Any]) -> Reaction:
    """Run ``fn`` now and again whenever the state it reads changes. ``fn`` may return a cleanup.

    Inside a component (or app) build, the effect is disposed with that component.
    """
    frame = current_frame(required=False)
    reaction = Reaction(fn, _scheduler(), priority=Reaction.EFFECT, name=getattr(fn, "__name__", "effect"))
    if frame is not None and frame.owner is not None:
        frame.owner._reactions.append(reaction)
    return reaction


@contextlib.contextmanager
def batch() -> Iterator[None]:
    """Group several state writes into one UI update."""
    with _scheduler().batch():
        yield


# ---- text ----------------------------------------------------------------------------------

def text(content: Any = "", *, tone: str = "default", classes: str | None = None, style: Any = None,
         visible: Any = True) -> Text:
    """Literal text (escaped; never parsed as HTML). ``content`` may be reactive."""
    return Text(content, tone=tone, classes=classes, style=style, visible=visible)


def heading(content: Any, *, level: int = 2, classes: str | None = None, style: Any = None,
            visible: Any = True) -> Heading:
    return Heading(content, level=level, classes=classes, style=style, visible=visible)


def caption(content: Any, **kw: Any) -> Text:
    """Small secondary text."""
    return Text(content, cls="u4-caption", **kw)


def badge(content: Any, *, tone: str = "default", **kw: Any) -> Badge:
    return Badge(content, tone=tone, **kw)


# ---- controls ----------------------------------------------------------------------------------

def button(label: Any = "", *, on_click: Callable | None = None, variant: str = "primary", size: str = "md",
           disabled: Any = False, loading: Any = False, tooltip: str | None = None, **kw: Any) -> Button:
    """Push button. ``on_click`` may take the event and may be ``async def`` (shows loading)."""
    return Button(label, on_click=on_click, variant=variant, size=size, disabled=disabled, loading=loading,
                  tooltip=tooltip, **kw)


def input(label: Any = "", *, value: str = "", bind: Signal | None = None, placeholder: str = "",
          on_change: Callable | None = None, on_submit: Callable | None = None, description: Any = None,
          error: Any = None, required: bool = False, disabled: Any = False, autofocus: bool = False,
          max_length: int | None = None, **kw: Any) -> TextField:
    """Text input. ``.value`` is tracked; ``bind=`` shares an existing ``ui.state``."""
    return TextField(label, value=value, bind=bind, placeholder=placeholder, on_change=on_change,
                     on_submit=on_submit, description=description, error=error, required=required,
                     disabled=disabled, autofocus=autofocus, max_length=max_length, **kw)


def password(label: Any = "Password", **kw: Any) -> PasswordField:
    return PasswordField(label, **kw)


def textarea(label: Any = "", *, rows: int = 3, **kw: Any) -> TextArea:
    """Multi-line text. ``on_submit`` fires on Ctrl+Enter."""
    return TextArea(label, rows=rows, **kw)


def number(label: Any = "", *, value: float | int | None = None, min: float | None = None,
           max: float | None = None, step: float | None = None, **kw: Any) -> NumberField:
    """Numeric input; ``.value`` is int/float (or None when empty). Invalid text shows an error."""
    return NumberField(label, value=value, min=min, max=max, step=step, **kw)


def checkbox(label: Any = "", *, value: bool = False, bind: Signal | None = None,
             on_change: Callable | None = None, disabled: Any = False, **kw: Any) -> Checkbox:
    return Checkbox(label, value=value, bind=bind, on_change=on_change, disabled=disabled, **kw)


def switch(label: Any = "", **kw: Any) -> Checkbox:
    """Alias of checkbox with ``role=switch`` semantics."""
    box = Checkbox(label, **kw)
    box.control.set_attr("role", "switch")
    return box


def radio(label: Any = "", *, options: Any, value: Any = None, bind: Signal | None = None,
          on_change: Callable | None = None, horizontal: bool = False, **kw: Any) -> RadioGroup:
    return RadioGroup(label, options=options, value=value, bind=bind, on_change=on_change,
                      horizontal=horizontal, **kw)


def select(label: Any = "", *, options: Any, value: Any = None, bind: Signal | None = None,
           on_change: Callable | None = None, placeholder: str | None = None, **kw: Any) -> Select:
    """Drop-down. ``options``: strings, ``(value, label)`` pairs, a dict, an Enum, or reactive."""
    return Select(label, options=options, value=value, bind=bind, on_change=on_change, placeholder=placeholder,
                  **kw)


def slider(label: Any = "", *, value: float = 0, min: float = 0, max: float = 100, step: float = 1,
           **kw: Any) -> Slider:
    return Slider(label, value=value, min=min, max=max, step=step, **kw)


# ---- layout ------------------------------------------------------------------------------------

def row(*, gap: str = "md", align: str | None = "center", justify: str | None = None, wrap: bool = False,
        grow: bool = False, **kw: Any) -> Row:
    """Horizontal flex container: ``with ui.row(): ...``."""
    return Row(gap=gap, align=align, justify=justify, wrap=wrap, grow=grow, **kw)


def column(*, gap: str = "md", align: str | None = None, justify: str | None = None, grow: bool = False,
           **kw: Any) -> Column:
    """Vertical flex container."""
    return Column(gap=gap, align=align, justify=justify, grow=grow, **kw)


def stack(*, direction: str | Mapping[str, str] = "column", gap: str = "md", align: str | None = None,
          justify: str | None = None, wrap: bool = False, **kw: Any) -> Stack:
    """Responsive direction, e.g. ``direction={'base': 'column', 'md': 'row'}`` (sm=600, md=900, lg=1200px)."""
    return Stack(direction=direction, gap=gap, align=align, justify=justify, wrap=wrap, **kw)


def card(*, padding: str = "lg", variant: str = "outlined", gap: str = "md", **kw: Any) -> Card:
    return Card(padding=padding, variant=variant, gap=gap, **kw)


def grid(columns: int | None = 2, *, min_width: str | None = None, gap: str = "md", **kw: Any) -> Grid:
    """CSS grid; ``min_width='220px'`` gives as many columns as fit."""
    return Grid(columns, min_width=min_width, gap=gap, **kw)


def scroll(*, height: str | None = None, gap: str = "sm", **kw: Any) -> Scroll:
    return Scroll(height=height, gap=gap, **kw)


def spacer() -> Spacer:
    """Flexible space that pushes siblings apart in a row/column."""
    return Spacer()


def divider(*, vertical: bool = False) -> Divider:
    return Divider(vertical=vertical)


def shell(**kw: Any) -> Shell:
    """Full-window app layout with ``ui.sidebar()`` and ``ui.content()`` inside."""
    return Shell(**kw)


def sidebar(title: str | None = None, **kw: Any) -> Sidebar:
    return Sidebar(title, **kw)


def content(**kw: Any) -> Content:
    return Content(**kw)


def split(*, side: str = "40%", **kw: Any) -> Split:
    """Two panes: ``with s.side: ...`` and ``with s.main: ...``; stacked on narrow windows."""
    return Split(side=side, **kw)


def tabs(tabs: Mapping[str, Callable[[], Any]], *, selected: Any = None, on_change: Callable | None = None,
         **kw: Any) -> Tabs:
    """Tabbed views: ``ui.tabs({'General': general, 'Advanced': advanced})``."""
    return Tabs(tabs, selected=selected, on_change=on_change, **kw)


def navigation(pages: Mapping[str, Callable[[], Any]], *, title: str | None = None, selected: str | None = None,
               **kw: Any) -> Navigation:
    """Sidebar navigation between pages (local view state; no web routing)."""
    return Navigation(pages, title=title, selected=selected, **kw)


def navigate(page: str, *, controller: Navigation | Signal | None = None) -> None:
    """Navigate a view. In multi-navigation apps pass its ref or state explicitly.

    In a single-navigation app the matching view is found automatically. Passing
    app.navigation remains supported for applications that deliberately share state.
    """
    if isinstance(controller, Signal):
        controller.set(page)
    elif controller is not None:
        controller.select(page)
    else:
        current_app().navigate(page)


# ---- broader desktop component catalogue --------------------------------------------------

def surface(*, role: str = "paper", padding: str = "md", **kw: Any):
    """Composable surface: paper, toolbar, header, footer, section, statusbar, center, sticky, container."""
    from .components.kit import Surface
    return Surface(role=role, padding=padding, **kw)


def paper(**kw: Any):
    return surface(role="paper", **kw)


def toolbar(**kw: Any):
    return surface(role="toolbar", **kw)


def header(**kw: Any):
    return surface(role="header", **kw)


def footer(**kw: Any):
    return surface(role="footer", **kw)


def statusbar(**kw: Any):
    return surface(role="statusbar", **kw)


def section(**kw: Any):
    return surface(role="section", **kw)


def center(**kw: Any):
    return surface(role="center", **kw)


def sticky(**kw: Any):
    return surface(role="sticky", **kw)


def container(**kw: Any):
    return surface(role="container", **kw)


def aspect(ratio: float = 16 / 9, **kw: Any):
    """Constraint container for media and previews, e.g. with ui.aspect(16/9)."""
    from .components.kit import AspectRatio
    return AspectRatio(ratio, **kw)


def kbd(content: Any, **kw: Any):
    from .components.kit import LabelText
    return LabelText(content, kind="kbd", **kw)


def inline_code(content: Any, **kw: Any):
    from .components.kit import LabelText
    return LabelText(content, kind="inline-code", **kw)


def mark(content: Any, **kw: Any):
    from .components.kit import LabelText
    return LabelText(content, kind="mark", **kw)


def avatar(content: Any, **kw: Any):
    """Avatar initials/fallback text; for photos use ui.image and a custom CSS class."""
    from .components.kit import LabelText
    return LabelText(content, kind="avatar", **kw)


def link(label: Any, *, href: str | None = None, on_click: Callable | None = None,
         external: bool = False, **kw: Any):
    from .components.kit import Link
    return Link(label, href=href, on_click=on_click, external=external, **kw)


def icon(name: str, *, size: int = 18, label: str | None = None, **kw: Any):
    from .components.kit import Icon
    return Icon(name, size=size, label=label, **kw)


def icon_names() -> tuple[str, ...]:
    from .components.kit import icon_names as available
    return available()


def icon_button(name: str, *, label: str, on_click: Callable | None = None,
                variant: str = "ghost", **kw: Any):
    from .components.kit import IconButton
    return IconButton(name, label=label, on_click=on_click, variant=variant, **kw)


def breadcrumbs(items: Sequence[tuple[str, Any]], **kw: Any):
    """Last breadcrumb is current page; previous targets are callbacks or local/HTTP URLs."""
    from .components.kit import Breadcrumbs
    return Breadcrumbs(items, **kw)


def disclosure(label: Any, *, open: Any = False, **kw: Any):
    from .components.kit import Disclosure
    return Disclosure(label, open=open, **kw)


def accordion(sections: Mapping[str, Callable[[], Any]], **kw: Any):
    from .components.kit import Accordion
    return Accordion(sections, **kw)


def drawer(title: str | None = None, *, side: str = "right", **kw: Any):
    from .components.kit import Drawer
    return Drawer(title, side=side, **kw)


def segmented(options: Mapping[str, str] | Sequence[str], *, selected: str | None = None,
              bind: Signal | None = None, on_change: Callable | None = None, **kw: Any):
    from .components.kit import Segmented
    return Segmented(options, selected=selected, bind=bind, on_change=on_change, **kw)


def tree(nodes: Sequence[Any], *, selected: str | None = None,
         on_select: Callable | None = None, **kw: Any):
    """Local tree view. Pass ui.TreeNode(id, label, children=tuple(...))."""
    from .components.kit import TreeView
    return TreeView(nodes, selected=selected, on_select=on_select, **kw)


def slot(name: str, **kw: Any):
    """Customizable named component part, addressable as .u4-slot-{name} in CSS."""
    from .components.kit import EmptyDiv
    return EmptyDiv(name, **kw)


def combobox(options: Mapping[str, str] | Sequence[str], *, label: str = "Choose",
             selected: str | None = None, bind: Signal | None = None,
             on_change: Callable | None = None, **kw: Any):
    """Local filterable combobox with keyboard selection and reactive value."""
    from .components.kit import ComboBox
    return ComboBox(options, label=label, selected=selected, bind=bind, on_change=on_change, **kw)


def command_palette(*, shortcut: str | None = "Ctrl+K", title: str = "Commands"):
    """Create a searchable palette over app.commands and optionally bind a shortcut.

    Declare commands before constructing the palette. For commands registered later,
    recreate the palette or use a custom data-driven command view.
    """
    current = current_app()
    commands = tuple(current.commands)
    dlg = dialog(title)
    with dlg:
        combo = combobox({cmd.name: f"{cmd.name}  {cmd.shortcut or ''}" for cmd in commands},
                         label="Find command", on_change=lambda name: (dlg.close(), current.commands.run(name)))
        if not commands:
            text("No commands registered", tone="muted")
    if shortcut is not None:
        current.commands.add("Open command palette", dlg.open, shortcut=shortcut)
    dlg.search = combo
    return dlg


def path(label: str = "Path", *, mode: str = "open", value: str = "", bind: Signal | None = None,
         on_change: Callable | None = None, **kw: Any):
    """Editable path with a native open/save/folder dialog. No file operations performed."""
    from .components.kit import PathPicker
    return PathPicker(label, mode=mode, value=value, bind=bind, on_change=on_change, **kw)


def file_input(label: str = "Choose file", *, multiple: bool = False, accept: str | None = None,
               on_change: Callable | None = None, **kw: Any):
    """Core native file input; selected paths available at ref.value."""
    from .components.kit import FileField
    return FileField(label, multiple=multiple, accept=accept, on_change=on_change, **kw)


def _typed_input(type: str, label: str, **kw: Any):
    from .components.kit import InputType
    return InputType(label, type=type, **kw)


def date(label: str = "Date", **kw: Any):
    """Date field (``YYYY-MM-DD``) with an in-window calendar; value is ``datetime.date`` or None."""
    from .components.pickers import DateField
    return DateField(label, **kw)


def time(label: str = "Time", **kw: Any):
    """24-hour time field; value is ``datetime.time`` or None."""
    from .components.pickers import TimeField
    return TimeField(label, **kw)


def datetime(label: str = "Date and time", **kw: Any):
    """``YYYY-MM-DD HH:MM`` field; value is ``datetime.datetime`` or None."""
    from .components.pickers import DateTimeField
    return DateTimeField(label, **kw)


def month(label: str = "Month", **kw: Any):
    """``YYYY-MM`` field; value is the first day of the month or None."""
    from .components.pickers import MonthField
    return MonthField(label, **kw)


def week(label: str = "Week", **kw: Any):
    """ISO week ``YYYY-Www`` field; value is that week's Monday or None."""
    from .components.pickers import WeekField
    return WeekField(label, **kw)


def color(label: str = "Color", *, value: str | None = "#2563eb", **kw: Any):
    """Hex colour field with swatch preview and in-window palette; value ``'#rrggbb'`` or None."""
    from .components.pickers import ColorField
    return ColorField(label, value=value, **kw)


def email(label: str = "Email", **kw: Any):
    return _typed_input("email", label, **kw)


def url(label: str = "URL", **kw: Any):
    return _typed_input("url", label, **kw)


def search(label: str = "Search", **kw: Any):
    return _typed_input("search", label, **kw)


def telephone(label: str = "Phone", **kw: Any):
    return _typed_input("tel", label, **kw)


from .components.kit import TreeNode
def menu(label: str, items: Sequence[Any], **kw: Any):
    """In-window accessible menu. Pass ui.MenuItem(label, action), with optional disabled/shortcut."""
    from .components.kit import Menu
    return Menu(label, items, **kw)


def progress_ring(value: Any = 0, *, size: int = 48, thickness: int = 5, **kw: Any):
    from .components.kit import ProgressRing
    return ProgressRing(value, size=size, thickness=thickness, **kw)


def sparkline(values: Any, *, width: int = 160, height: int = 48, **kw: Any):
    from .components.kit import Sparkline
    return Sparkline(values, width=width, height=height, **kw)


from .components.kit import MenuItem




# ---- dynamic regions -----------------------------------------------------------------------------

def when(condition: Any, *, then: Callable[[], Any], otherwise: Callable[[], Any] | None = None) -> When:
    """Show ``then()`` while ``condition`` is true (else ``otherwise()``); content is rebuilt on change."""
    return When(condition, then=then, otherwise=otherwise)


def each(items: Any, *, key: Any, render: Callable[..., Any], empty: Callable[[], Any] | None = None,
         preserve: bool = False) -> Each:
    """Keyed list: ``ui.each(todos, key='id', render=lambda todo: ui.text(todo.title))``.

    Reorders always preserve DOM. ``preserve=True`` also retains item components on
    record changes: render receives a reactive ItemRef, so use reactive lambdas
    such as `ui.text(lambda: item.title)` to update text without reconstruction.
    The default preserves 0.4 backwards compatibility for ordinary record values.
    """
    return Each(items, key=key, render=render, empty=empty, preserve=preserve)


# ---- feedback ------------------------------------------------------------------------------------

def dialog(title: Any = None, *, modal: bool = True, dismissible: bool = True,
           on_close: Callable | None = None) -> Dialog:
    """``with ui.dialog('Edit') as dlg: ...`` then ``dlg.open()`` / ``await dlg.open()``."""
    return Dialog(title, modal=modal, dismissible=dismissible, on_close=on_close)


def alert(message: Any, *, kind: str = "info", title: Any = None, **kw: Any) -> Alert:
    return Alert(message, kind=kind, title=title, **kw)


def empty(title: Any = "Nothing here yet", description: Any = None, *, action: tuple[str, Callable] | None = None,
          **kw: Any) -> StateView:
    return StateView(title, description, variant="empty", action=action, **kw)


def loading(title: Any = "Loading…", description: Any = None, **kw: Any) -> StateView:
    return StateView(title, description, variant="loading", **kw)


def error_state(title: Any = "Something went wrong", description: Any = None, *,
                retry: Callable | None = None, **kw: Any) -> StateView:
    return StateView(title, description, variant="error", action=("Try again", retry) if retry else None, **kw)


def spinner() -> Spinner:
    return Spinner()


def progress(value: Any = 0.0, **kw: Any) -> Progress:
    """Progress bar for a fraction 0..1 (reactive)."""
    return Progress(value, **kw)


# ---- styling and escape hatches ------------------------------------------------------------------

def html(trusted_html: str, *, css: str | None = None, mount: str = "island", **kw: Any) -> Html:
    """Trusted raw HTML island; use ``.core_window`` / ``.core_element()`` for direct Core calls inside."""
    return Html(trusted_html, css=css, mount=mount, **kw)


def css(trusted_css: str) -> None:
    """Add trusted CSS to the current app (all windows)."""
    current_app().css(trusted_css)


def theme(name: str | None = None, **tokens: str) -> str:
    """Set ``'light'``, ``'dark'`` or ``'system'`` and/or override tokens; returns the current name."""
    application = current_app()
    if name is not None:
        application.theme.set(name)
    if tokens:
        application.theme.tokens(**tokens)
    return application.theme.name


def density(value: str) -> str:
    """Apply comfortable, compact or dense layout tokens to all application windows."""
    return current_app().density(value)


def theme_preset(name: str) -> None:
    """Use bundled visual CSS (default, ocean, sage, violet, graphite)."""
    current_app().theme.preset(name)


def stylesheet(css: str, *, mode: str = "replace") -> None:
    """Apply full custom theme CSS or append app CSS, without replacing Core functional CSS."""
    current_app().theme.load(css, mode=mode)


def stylesheet_file(path: str, *, mode: str = "replace") -> None:
    """Apply CSS from a local path. Files are read synchronously by the caller."""
    current_app().theme.load_file(path, mode=mode)


def markdown(source: Any, **kw: Any):
    """Safe Markdown subset (headings, emphasis, code, lists, links, quotes, tables). Raw HTML is escaped."""
    from .components.markdown import Markdown
    return Markdown(source, **kw)


def code(source: Any, *, language: str | None = None, **kw: Any):
    """Monospace code block (literal text)."""
    from .components.markdown import CodeBlock
    return CodeBlock(source, language=language, **kw)


def table(rows: Any, *, columns: Any = None, key: Any = None, search: bool = False, sort: bool = False,
          page_size: int | None = 50, on_select: Callable | None = None, selected: Signal | None = None,
          empty: str = "No rows", **kw: Any):
    """Data table with optional search, sorting, pagination and row selection."""
    from .components.table import Table
    return Table(rows, columns=columns, key=key, search=search, sort=sort, page_size=page_size,
                 on_select=on_select, selected=selected, empty=empty, **kw)


def form(model: Any, *, value: Any = None, on_submit: Callable | None = None, exclude: Sequence[str] = (),
         submit_label: str = "Save", on_cancel: Callable | None = None, cancel_label: str = "Cancel",
         validate: Callable | None = None, columns: int = 1, reset_on_submit: bool = False, **kw: Any):
    """Generate a validated form from a dataclass type."""
    from .components.forms import Form
    return Form(model, value=value, on_submit=on_submit, exclude=exclude, submit_label=submit_label,
                on_cancel=on_cancel, cancel_label=cancel_label, validate=validate, columns=columns,
                reset_on_submit=reset_on_submit, **kw)


def query_table(loader: Callable, *, key: Any, columns: Any, page_size: int = 50,
                search: bool = True, on_select: Callable | None = None, **kw: Any):
    """Paged table where loader(page, size, query) runs in a background worker.

    Return ui.PageResult(rows, total) or a (rows, total) tuple. The loader may
    access files, SQLite or remote APIs, but cannot touch UI state from its thread.
    """
    from .components.query_table import QueryTable
    return QueryTable(loader, key=key, columns=columns, page_size=page_size,
                      search=search, on_select=on_select, **kw)


from .components.query_table import PageResult


def log(*, max_lines: int = 5000, follow: str | bool = "smart", height: str | None = None, **kw: Any):
    """Streaming log view with bounded retention and smart scroll-follow."""
    from .components.data import LogView
    return LogView(max_lines=max_lines, follow=follow, height=height, **kw)


def chat(messages: Any = None, *, on_send: Callable | None = None, markdown: bool = True,
         placeholder: str = "Write a message…", **kw: Any):
    """Local chat presentation (messages + composer). No networking or model client."""
    from .components.data import ChatView
    return ChatView(messages, on_send=on_send, markdown=markdown, placeholder=placeholder, **kw)


def sleep(seconds: float) -> UiFuture:
    """``await ui.sleep(0.5)`` inside an ``async def`` callback."""
    return current_app().sleep(seconds)


def component(fn: Callable[..., Any]) -> Callable[..., Component]:
    """Decorator turning a builder function into a reusable component.

    The function builds UI inside an invisible container; effects/state created inside are
    owned by (and disposed with) that component. Returns the container ref.
    """
    from .components.regions import Scope

    @functools.wraps(fn)
    def make(*args: Any, **kwargs: Any) -> Component:
        scope = Scope()
        scope.kind = fn.__name__
        frame = push(Frame(scope.app, scope, scope.slot, scope.window))
        try:
            fn(*args, **kwargs)
        finally:
            pop(frame)
        return scope
    return make
