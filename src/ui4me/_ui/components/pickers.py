"""Date, time, month, week and colour fields built from controls UI4ME Core supports.

UI4ME Core 1.x refuses ``<input type=date|time|datetime-local|month|week|color>``
(they need OS picker popups it does not provide). These fields use a validated text
input instead, plus in-window helpers: a keyboard-accessible calendar for dates and
a swatch palette for colours. Values are Python objects (``datetime.date``,
``datetime.time``, ``datetime.datetime`` or ``'#rrggbb'``), ``None`` when empty.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from typing import Any

from ..dom import Element, escape_attr, escape_text
from ..errors import InvalidComponentProps
from .basic import TextField

_HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_WEEK = re.compile(r"(\d{4})-?W(\d{2})")
PALETTE = ("#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c", "#ca8a04", "#16a34a", "#0d9488", "#475569", "#111827")


class ParsedField(TextField):
    """A text input whose text is parsed into a typed value (errors show under the field)."""

    kind = "ParsedField"
    placeholder = ""
    inputmode = "text"

    def __init__(self, label: Any = "", *, value: Any = None, placeholder: str | None = None, **kw: Any):
        kw.pop("type", None)
        super().__init__(label, value=value, placeholder=placeholder if placeholder is not None else self.placeholder,
                         type="text", **kw)
        self.control.set_attr("inputmode", self.inputmode)
        self.control.set_attr("autocomplete", "off")
        self.control.set_attr("spellcheck", "false")


class DateField(ParsedField):
    """``YYYY-MM-DD`` date with an in-window calendar; value is ``datetime.date`` or None."""

    kind = "Date"
    placeholder = "YYYY-MM-DD"
    inputmode = "numeric"

    def __init__(self, label: Any = "Date", *, value: dt.date | str | None = None, min: dt.date | None = None,
                 max: dt.date | None = None, calendar: bool = True, **kw: Any):
        # A datetime bound would compare badly with dates (and keep a time of day).
        self._min = min.date() if isinstance(min, dt.datetime) else min
        self._max = max.date() if isinstance(max, dt.datetime) else max
        self._calendar = calendar
        if isinstance(value, str):
            value = self._parse(value)
        today = dt.date.today()
        self._shown = (value or today).replace(day=1)
        super().__init__(label, value=value, **kw)
        if calendar:
            self._listen(self.toggle_el.id, "click", lambda _e: self.toggle_calendar())
            self._listen(self.panel.id, "click", self._panel_click)
            self._listen(self.panel.id, "keydown", self._panel_key)
            self._listen(self.control.id, "keydown", self._control_key)

    def _build(self) -> Element:
        root = super()._build()
        if not self._calendar:
            return root
        self.toggle_el = Element("button", self, cls="u4-btn u4-btn-ghost u4-btn-sm u4-picker-toggle",
                                 attrs={"type": "button", "aria-label": "Choose date from calendar",
                                        "aria-expanded": "false", "aria-haspopup": "dialog"}, text="Calendar")
        self.panel = Element("div", self, cls="u4-calendar", attrs={"role": "dialog", "aria-label": "Calendar",
                                                                    "hidden": True})
        # Order: label, input, calendar button, panel, help, error.
        root.children = [root.children[0], root.children[1], self.toggle_el, self.panel, *root.children[2:]]
        return root

    # text <-> value
    def _parse(self, text: str) -> dt.date | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = dt.date.fromisoformat(text.replace("/", "-"))
        except ValueError:
            raise ValueError("Enter a date as YYYY-MM-DD") from None
        if self._min is not None and value < self._min:
            raise ValueError(f"Must be on or after {self._min.isoformat()}")
        if self._max is not None and value > self._max:
            raise ValueError(f"Must be on or before {self._max.isoformat()}")
        return value

    def _from_text(self, text: str) -> Any:
        return self._parse(text)

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            value = self._parse(value)
        return value.isoformat()

    # calendar
    @property
    def calendar_open(self) -> bool:
        return self._calendar and "hidden" not in self.panel.attrs

    def toggle_calendar(self, open: bool | None = None) -> None:
        self._live_check()
        if not self._calendar:
            return
        open = not self.calendar_open if open is None else open
        if open:
            current = self.state.peek()
            if isinstance(current, dt.date):
                self._shown = current.replace(day=1)
            self._render()
        self.panel.set_attr("hidden", not open)
        self.toggle_el.set_attr("aria-expanded", "true" if open else "false")
        if open and self.window is not None:
            target = self._day_id(self._focus_day())
            self.window._queue({"op": "focus", "element": target})
        self._touch()

    def _focus_day(self) -> dt.date:
        current = self.state.peek()
        if isinstance(current, dt.date) and current.replace(day=1) == self._shown:
            return current
        today = dt.date.today()
        return today if today.replace(day=1) == self._shown else self._shown

    def _day_id(self, day: dt.date) -> str:
        return f"{self.panel.id}-d{day.strftime('%Y%m%d')}"

    def _render(self) -> None:
        pid = self.panel.id
        year, month = self._shown.year, self._shown.month
        selected = self.state.peek()
        today = dt.date.today()
        cells = []
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
            for day in week:
                classes = ["u4-calendar-day"]
                if day.month != month:
                    classes.append("u4-muted")
                if day == today:
                    classes.append("u4-today")
                attrs = ""
                if day == selected:
                    classes.append("u4-selected")
                    attrs += ' aria-pressed="true"'
                if (self._min and day < self._min) or (self._max and day > self._max):
                    attrs += " disabled"
                cells.append(f'<button type="button" id="{self._day_id(day)}" class="{" ".join(classes)}"'
                             f' aria-label="{escape_attr(day.strftime("%A %d %B %Y"))}"{attrs}>{day.day}</button>')
        heads = "".join(f'<span class="u4-calendar-head" aria-hidden="true">{escape_text(n)}</span>'
                        for n in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))
        title = escape_text(f"{calendar.month_name[month]} {year}")
        html = (f'<div class="u4-calendar-nav"><button type="button" id="{pid}-prev" class="u4-btn u4-btn-ghost u4-btn-sm"'
                f' aria-label="Previous month">&#8249;</button><strong id="{pid}-title" aria-live="polite">{title}</strong>'
                f'<button type="button" id="{pid}-next" class="u4-btn u4-btn-ghost u4-btn-sm" aria-label="Next month">&#8250;'
                f'</button></div><div class="u4-calendar-grid" role="grid">{heads}{"".join(cells)}</div>'
                f'<div class="u4-calendar-foot"><button type="button" id="{pid}-today" class="u4-btn u4-btn-ghost u4-btn-sm">'
                f'Today</button><button type="button" id="{pid}-clear" class="u4-btn u4-btn-ghost u4-btn-sm">Clear</button></div>')
        self.panel.set_html(html)

    def _move_month(self, delta: int) -> None:
        month = self._shown.month - 1 + delta
        self._shown = dt.date(self._shown.year + month // 12, month % 12 + 1, 1)
        self._render()
        self._touch()

    def _pick(self, day: dt.date | None) -> None:
        self.error_signal.set(None)
        self.state.set(day)
        self._emit(self._on_change, day)
        self.toggle_calendar(False)
        self.focus()

    def _panel_click(self, event: dict) -> None:
        target = str(event.get("element") or "")
        pid = self.panel.id
        if target == f"{pid}-prev":
            self._move_month(-1)
        elif target == f"{pid}-next":
            self._move_month(1)
        elif target == f"{pid}-today":
            self._pick(dt.date.today())
        elif target == f"{pid}-clear":
            self._pick(None)
        elif target.startswith(f"{pid}-d"):
            day = dt.datetime.strptime(target[len(pid) + 2:], "%Y%m%d").date()
            if not ((self._min and day < self._min) or (self._max and day > self._max)):
                self._pick(day)

    def _panel_key(self, event: dict) -> None:
        key = event.get("key")
        if key == "Escape":
            self.toggle_calendar(False)
            self.focus()
            return
        target = str(event.get("element") or "")
        prefix = f"{self.panel.id}-d"
        steps = {"ArrowLeft": -1, "ArrowRight": 1, "ArrowUp": -7, "ArrowDown": 7}
        if key in steps and target.startswith(prefix):
            day = dt.datetime.strptime(target[len(prefix):], "%Y%m%d").date() + dt.timedelta(days=steps[key])
            if day.replace(day=1) != self._shown:
                self._shown = day.replace(day=1)
                self._render()
            self.window._queue({"op": "focus", "element": self._day_id(day)})
            self._touch()

    def _control_key(self, event: dict) -> None:
        if event.get("key") == "ArrowDown" and event.get("alt"):
            self.toggle_calendar(True)


class TimeField(ParsedField):
    """``HH:MM`` (24-hour, optional ``:SS``); value is ``datetime.time`` or None."""

    kind = "Time"
    placeholder = "HH:MM"
    inputmode = "numeric"

    def __init__(self, label: Any = "Time", *, value: dt.time | str | None = None, seconds: bool = False, **kw: Any):
        self._seconds = seconds
        if isinstance(value, str):
            value = self._from_text(value)
        super().__init__(label, value=value, placeholder="HH:MM:SS" if seconds else "HH:MM", **kw)

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if not match:
            raise ValueError("Enter a time as HH:MM" + (":SS" if self._seconds else ""))
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
        if h > 23 or m > 59 or s > 59:
            raise ValueError("Enter a valid 24-hour time")
        return dt.time(h, m, s if self._seconds else 0)

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            value = self._from_text(value)
        return value.strftime("%H:%M:%S" if self._seconds else "%H:%M")


class DateTimeField(ParsedField):
    """``YYYY-MM-DD HH:MM``; value is a naive ``datetime.datetime`` or None."""

    kind = "DateTime"
    placeholder = "YYYY-MM-DD HH:MM"

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        try:
            return dt.datetime.strptime(text.replace("T", " "), "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Enter date and time as YYYY-MM-DD HH:MM") from None

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            value = self._from_text(value)
        return value.strftime("%Y-%m-%d %H:%M")


class MonthField(ParsedField):
    """``YYYY-MM``; value is the first day of that month (``datetime.date``) or None."""

    kind = "Month"
    placeholder = "YYYY-MM"
    inputmode = "numeric"

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
        if not match or not 1 <= int(match.group(2)) <= 12:
            raise ValueError("Enter a month as YYYY-MM")
        return dt.date(int(match.group(1)), int(match.group(2)), 1)

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            value = self._from_text(value)
        return value.strftime("%Y-%m")


class WeekField(ParsedField):
    """ISO week ``YYYY-Www``; value is the Monday of that week (``datetime.date``) or None."""

    kind = "Week"
    placeholder = "YYYY-Www"

    def _from_text(self, text: str) -> Any:
        text = text.strip().upper()
        if not text:
            return None
        match = _WEEK.fullmatch(text)
        try:
            if not match:
                raise ValueError
            return dt.date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            raise ValueError("Enter an ISO week as YYYY-Www, e.g. 2026-W07") from None

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            value = self._from_text(value)
        year, week, _ = value.isocalendar()
        return f"{year}-W{week:02d}"


class ColorField(ParsedField):
    """Hex colour ``#rrggbb`` with a live swatch and an in-window palette; value is a str or None."""

    kind = "Color"
    placeholder = "#rrggbb"

    def __init__(self, label: Any = "Color", *, value: str | None = "#2563eb", palette: tuple[str, ...] = PALETTE,
                 **kw: Any):
        self._palette = tuple(self._normalize(c) for c in palette)
        if value is not None:
            value = self._normalize(value)
        super().__init__(label, value=value, **kw)
        self._listen(self.swatches.id, "click", self._swatch_click)
        self._bind(lambda: self.state.value, self._show_preview, "preview")

    @staticmethod
    def _normalize(text: str) -> str:
        match = _HEX.fullmatch(str(text).strip())
        if not match:
            raise InvalidComponentProps(f"not a hex colour: {text!r}")
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return "#" + digits.lower()

    def _build(self) -> Element:
        root = super()._build()
        self.preview = Element("span", self, cls="u4-swatch u4-swatch-preview", attrs={"aria-hidden": "true"})
        self.swatches = Element("div", self, cls="u4-swatches", attrs={"role": "group", "aria-label": "Colour presets"})
        for index, colour in enumerate(self._palette):
            swatch = Element("button", self, cls="u4-swatch", id=f"{self.swatches.id}-{index}",
                             attrs={"type": "button", "aria-label": colour, "title": colour})
            swatch.set_style("background", colour)
            self.swatches.add(swatch)
        root.children = [root.children[0], root.children[1], self.preview, self.swatches, *root.children[2:]]
        return root

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        try:
            return self._normalize(text)
        except InvalidComponentProps:
            raise ValueError("Enter a colour as #rrggbb") from None

    def _to_text(self, value: Any) -> str:
        return "" if value is None else self._normalize(value)

    def _show_preview(self, value: Any) -> None:
        self.preview.set_style("background", value or "transparent")

    def _swatch_click(self, event: dict) -> None:
        target = str(event.get("element") or "")
        prefix = f"{self.swatches.id}-"
        if target.startswith(prefix) and target[len(prefix):].isdigit():
            colour = self._palette[int(target[len(prefix):])]
            self.error_signal.set(None)
            self.state.set(colour)
            self._emit(self._on_change, colour)
