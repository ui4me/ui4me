"""Text, buttons, value controls and the raw HTML island."""
from __future__ import annotations

import enum
import math
from typing import Any, Callable, Iterable, Sequence

from ..aio import UiFuture
from ..component import Component, adapt
from ..dom import Element, check_css
from ..errors import InvalidComponentProps, UiError
from ..reactive import Computed, Signal, is_reactive, read, untracked

TONES = ("default", "success", "warning", "danger", "info", "muted")
VARIANTS = ("primary", "secondary", "outline", "ghost", "danger")
SIZES = ("sm", "md", "lg")


def _choice(value: str, allowed: Sequence[str], what: str) -> str:
    if value not in allowed:
        raise InvalidComponentProps(f"{what} must be one of {', '.join(allowed)}; got {value!r}")
    return value


def _tone_class(tone: str) -> str | None:
    _choice(tone, TONES, "tone")
    if tone == "default":
        return None
    return "u4-muted" if tone == "muted" else f"u4-tone-{tone}"


# ---- text -------------------------------------------------------------------------------

class Text(Component):
    """Literal text (never markup). ``content`` may be a str, Signal, Computed or lambda."""

    kind = "Text"

    def __init__(self, content: Any = "", *, tone: str = "default", tag: str = "div", cls: str = "u4-text",
                 **kw: Any):
        self._tag, self._cls, self._tone = tag, cls, tone
        super().__init__(**kw)
        self._bind(content, lambda v: self.root.set_text("" if v is None else str(v)), "text")

    def _build(self) -> Element:
        return Element(self._tag, self, cls=[self._cls, _tone_class(self._tone) or ""])

    @property
    def text(self) -> str:
        return self.root.text or ""

    def set(self, content: Any) -> None:
        """Replace the content (a value, or a new reactive source)."""
        self._live_check()
        for reaction in [r for r in self._reactions if r.context and r.context.endswith(".text")]:
            reaction.dispose()
            self._reactions.remove(reaction)
        self._bind(content, lambda v: self.root.set_text("" if v is None else str(v)), "text")
        self._touch()


class Heading(Text):
    kind = "Heading"

    def __init__(self, content: Any, *, level: int = 2, **kw: Any):
        if level not in (1, 2, 3, 4):
            raise InvalidComponentProps("heading level must be 1-4")
        super().__init__(content, tag=f"h{level}", cls=f"u4-heading u4-h{level}", **kw)


class Badge(Text):
    kind = "Badge"

    def __init__(self, content: Any, *, tone: str = "default", **kw: Any):
        super().__init__(content, tag="span", cls="u4-badge", tone=tone, **kw)


# ---- button ---------------------------------------------------------------------------------

class Button(Component):
    """A push button. ``on_click`` may be ``async def``: the button shows loading meanwhile."""

    kind = "Button"

    def __init__(self, label: Any = "", *, on_click: Callable | None = None, variant: str = "primary",
                 size: str = "md", disabled: Any = False, loading: Any = False, tooltip: str | None = None,
                 **kw: Any):
        self._variant = _choice(variant, VARIANTS, "variant")
        self._size = _choice(size, SIZES, "size")
        self._busy = Signal(False, name="button busy")
        super().__init__(**kw)
        if tooltip:
            self.root.set_attr("title", tooltip)
        self._bind(label, lambda v: self.root.set_text("" if v is None else str(v)), "label")
        self._disabled_src, self._loading_src = disabled, loading
        self._bind(lambda: bool(read(self._disabled_src)) or bool(read(self._loading_src)) or self._busy.value,
                   lambda v: self.root.set_attr("disabled", bool(v)), "disabled")
        self._bind(lambda: bool(read(self._loading_src)) or self._busy.value,
                   lambda v: self.root.toggle_class("u4-loading", bool(v)), "loading")
        self._on_click = adapt(on_click, None)
        self._listen(self.root.id, "click", self._clicked)

    def _build(self) -> Element:
        cls = ["u4-btn", f"u4-btn-{self._variant}"]
        if self._size != "md":
            cls.append(f"u4-btn-{self._size}")
        return Element("button", self, cls=cls, attrs={"type": "button"})

    def _clicked(self, event: Any) -> None:
        if self._on_click is None or "disabled" in self.root.attrs:
            return
        result = self._emit(self._on_click, event)
        if isinstance(result, UiFuture) and not result.done:
            self._busy.set(True)
            result.add_done_callback(lambda _f: None if self.disposed else self._busy.set(False))

    @property
    def disabled(self) -> bool:
        return "disabled" in self.root.attrs

    def click(self) -> None:
        """Invoke the click handler programmatically (as if the user clicked)."""
        self.app._call(self._clicked, {"type": "click", "element": self.root.id}, context=f"{self.path()} click",
                       owner=self)


# ---- value fields ------------------------------------------------------------------------------

class Field(Component):
    """Shared label / description / error chrome for form controls."""

    kind = "Field"
    control_tag = "input"
    inline = False

    def __init__(self, label: Any = "", *, description: Any = None, error: Any = None, required: bool = False,
                 disabled: Any = False, name: str | None = None, **kw: Any):
        self._label_value, self._description, self._required, self._name = label, description, required, name
        super().__init__(**kw)
        if required:
            self.root.add_class("u4-required")
            self.control.set_attr("aria-required", "true")
        if label is not None:
            self._bind(label, lambda v: self.label_el.set_text(v), "label")
        if description is not None:
            self._bind(description, lambda v: self.help_el.set_text(v or ""), "description")
        self.error_signal: Signal[str | None] = Signal(None, name="field error")
        self._error_src = error
        self._bind(lambda: read(self._error_src) if self._error_src is not None else self.error_signal.value,
                   self._show_error, "error")
        self._bind(disabled, lambda v: self.control.set_attr("disabled", bool(v)), "disabled")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-field u4-field-inline" if self.inline else "u4-field")
        self.control = self._build_control()
        self.label_el = Element("label", self, cls="u4-label", attrs={"for": self.control.id})
        self.help_el = Element("p", self, cls="u4-help", attrs={"hidden": self._description is None})
        self.error_el = Element("p", self, cls="u4-error", attrs={"hidden": True, "role": "alert"})
        root.add(self.label_el, self.control, self.help_el, self.error_el)
        if self._description is not None:
            self.control.set_attr("aria-describedby", self.help_el.id)
        if self._name:
            self.control.set_attr("name", self._name)
        return root

    def _build_control(self) -> Element:  # pragma: no cover - overridden
        raise NotImplementedError

    def _show_error(self, message: Any) -> None:
        text = "" if not message else str(message)
        self.error_el.set_text(text)
        self.error_el.set_attr("hidden", not text)
        self.root.toggle_class("u4-invalid", bool(text))
        self.control.set_attr("aria-invalid", "true" if text else None)
        self.control.set_attr("aria-errormessage", self.error_el.id if text else None)

    def set_error(self, message: str | None) -> None:
        """Show (or clear with ``None``) a validation message under the control."""
        self.error_signal.set(message or None)

    @property
    def error(self) -> str | None:
        return self.error_signal.peek()

    def _focus_target(self) -> Element:
        return self.control


# Core 1.x rejects documents containing these input types (no native picker popups).
CORE_REFUSED_INPUT_TYPES = frozenset({"date", "time", "datetime-local", "month", "week", "color"})


class TextField(Field):
    """Single-line text input bound to a ``Signal[str]``."""

    kind = "Input"

    def __init__(self, label: Any = "", *, value: str = "", bind: Signal | None = None, placeholder: str = "",
                 on_change: Callable | None = None, on_submit: Callable | None = None, type: str = "text",
                 autofocus: bool = False, max_length: int | None = None, **kw: Any):
        if bind is not None and not isinstance(bind, Signal):
            raise InvalidComponentProps("bind= expects a ui.state(...) Signal")
        if type in CORE_REFUSED_INPUT_TYPES:
            raise InvalidComponentProps(
                f"input type {type!r} needs a native picker that UI4ME Core 1.x does not provide; "
                "use ui.date, ui.time, ui.datetime, ui.month, ui.week or ui.color")
        self.state: Signal = bind if bind is not None else Signal(value, name="input value")
        self._type, self._placeholder, self._autofocus, self._max = type, placeholder, autofocus, max_length
        self._shadow: str | None = None
        self._composing = False
        self._deferred: Any = None
        super().__init__(label, **kw)
        self._on_change = adapt(on_change, None)
        self._on_submit = adapt(on_submit, None)
        self._bind(lambda: self._to_text(self.state.value), self._write, "value")
        self._listen(self.control.id, "input", self._on_input)
        self._listen(self.control.id, "compositionstart", self._on_composition_start)
        self._listen(self.control.id, "compositionend", self._on_composition_end)
        if on_submit is not None:
            self._listen(self.control.id, "keydown", self._on_key)

    def _build_control(self) -> Element:
        attrs: dict[str, Any] = {"type": self._type}
        if self._placeholder:
            attrs["placeholder"] = self._placeholder
        if self._autofocus:
            attrs["autofocus"] = True
        if self._max:
            attrs["maxlength"] = int(self._max)
        return Element(self.control_tag, self, cls="u4-input", attrs=attrs)

    # conversions (overridden by numeric fields)
    def _to_text(self, value: Any) -> str:
        return "" if value is None else str(value)

    def _from_text(self, text: str) -> Any:
        return text

    def _write(self, text: str) -> None:
        if text == self._shadow:
            return
        if self._composing and self.mounted:
            self._deferred = text  # never clobber an in-progress IME composition
            return
        self._shadow = text
        if self.mounted:
            self.window._queue({"op": "set_value", "element": self.control.id, "value": text})
        else:
            self._initial(text)

    def _initial(self, text: str) -> None:
        self.control.set_attr("value", text) if text else self.control.remove_attr("value")

    def _on_input(self, event: dict) -> None:
        text = event.get("value")
        if text is None or text == self._shadow:
            return
        self._shadow = text
        try:
            parsed = self._from_text(text)
        except ValueError as error:
            self.error_signal.set(str(error))
            return
        if self.error_signal.peek() and self._error_src is None:
            self.error_signal.set(None)
        self.state.set(parsed)
        self._emit(self._on_change, parsed)

    def _on_composition_start(self, _event: dict) -> None:
        self._composing = True

    def _on_composition_end(self, event: dict) -> None:
        self._composing = False
        if self._deferred is not None:
            text, self._deferred = self._deferred, None
            self._write(text)

    def _on_key(self, event: dict) -> None:
        if event.get("key") == "Enter" and not event.get("shift") and not self._composing:
            self._emit(self._on_submit, self.state.peek())

    @property
    def value(self) -> Any:
        return self.state.value

    def set_value(self, value: Any) -> None:
        """Set the value programmatically (does not fire ``on_change``)."""
        self.state.set(value)

    def clear(self) -> None:
        self.set_value(self._from_text("") if not isinstance(self, NumberField) else None)


class PasswordField(TextField):
    kind = "Password"

    def __init__(self, label: Any = "Password", **kw: Any):
        super().__init__(label, type="password", **kw)

    def __repr__(self) -> str:
        return f"<Password {self.root.id} {self._state}>"


class TextArea(TextField):
    """Multi-line text."""

    kind = "Textarea"
    control_tag = "textarea"

    def __init__(self, label: Any = "", *, rows: int = 3, **kw: Any):
        self._rows = rows
        super().__init__(label, **kw)

    def _build_control(self) -> Element:
        attrs: dict[str, Any] = {"rows": int(self._rows)}
        if self._placeholder:
            attrs["placeholder"] = self._placeholder
        if self._autofocus:
            attrs["autofocus"] = True
        if self._max:
            attrs["maxlength"] = int(self._max)
        return Element("textarea", self, cls="u4-textarea", attrs=attrs)

    def _initial(self, text: str) -> None:
        self.control.text = text

    def _on_key(self, event: dict) -> None:
        if event.get("key") == "Enter" and (event.get("ctrl") or event.get("meta")) and not self._composing:
            self._emit(self._on_submit, self.state.peek())


class NumberField(TextField):
    """Numeric input with strict parsing; ``value`` is an int/float or None when empty."""

    kind = "Number"

    def __init__(self, label: Any = "", *, value: float | int | None = None, min: float | None = None,
                 max: float | None = None, step: float | None = None, integer: bool | None = None, **kw: Any):
        self._min, self._max_value, self._step = min, max, step
        self._integer = integer if integer is not None else (isinstance(value, int) and not isinstance(value, bool)
                                                             and (step is None or float(step).is_integer()))
        super().__init__(label, value=value, type="number", **kw)
        for attr, v in (("min", min), ("max", max), ("step", step)):
            if v is not None:
                self.control.set_attr(attr, v)

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer() and self._integer:
            value = int(value)
        return str(value)

    def _from_text(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        try:
            number: float | int = int(text) if self._integer else float(text)
        except ValueError:
            raise ValueError("Enter a whole number" if self._integer else "Enter a number") from None
        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError("Enter a finite number")
        if self._min is not None and number < self._min:
            raise ValueError(f"Must be at least {self._min}")
        if self._max_value is not None and number > self._max_value:
            raise ValueError(f"Must be at most {self._max_value}")
        return number


class Checkbox(Component):
    """A labelled checkbox bound to a ``Signal[bool]``. ``switch=True`` uses a toggle style."""

    kind = "Checkbox"

    def __init__(self, label: Any = "", *, value: bool = False, bind: Signal | None = None,
                 on_change: Callable | None = None, disabled: Any = False, **kw: Any):
        if bind is not None and not isinstance(bind, Signal):
            raise InvalidComponentProps("bind= expects a ui.state(...) Signal")
        self.state: Signal = bind if bind is not None else Signal(bool(value), name="checkbox")
        self._shadow: bool | None = None
        super().__init__(**kw)
        self._bind(label, lambda v: self.label_el.set_text(v), "label")
        self._bind(lambda: bool(self.state.value), self._write, "checked")
        self._bind(disabled, lambda v: self.control.set_attr("disabled", bool(v)), "disabled")
        self._on_change = adapt(on_change, None)
        for event in ("input", "change"):
            self._listen(self.control.id, event, self._on_toggle)

    def _build(self) -> Element:
        root = Element("label", self, cls="u4-check")
        self.control = Element("input", self, attrs={"type": "checkbox"})
        self.label_el = Element("span", self)
        root.add(self.control, self.label_el)
        return root

    def _write(self, checked: bool) -> None:
        if checked == self._shadow:
            return
        self._shadow = checked
        if self.mounted:
            self.window._queue({"op": "set_checked", "element": self.control.id, "checked": checked})
        else:
            self.control.set_attr("checked", checked)

    def _on_toggle(self, event: dict) -> None:
        checked = event.get("checked")
        if checked is None or bool(checked) == self._shadow:
            return
        self._shadow = bool(checked)
        self.state.set(bool(checked))
        self._emit(self._on_change, bool(checked))

    @property
    def value(self) -> bool:
        return self.state.value

    def set_value(self, value: bool) -> None:
        self.state.set(bool(value))

    def _focus_target(self) -> Element:
        return self.control


def normalize_options(options: Any) -> list[tuple[str, str, Any]]:
    """-> [(wire value, label, python value)] from strings, pairs, dicts, Enums or mappings."""
    if isinstance(options, type) and issubclass(options, enum.Enum):
        options = list(options)
    if isinstance(options, dict):
        options = list(options.items())
    result: list[tuple[str, str, Any]] = []
    for option in options:
        if isinstance(option, enum.Enum):
            label = str(option.value) if isinstance(option.value, str) else option.name.replace("_", " ").title()
            result.append((option.name, label, option))
        elif isinstance(option, (tuple, list)) and len(option) == 2:
            value, label = option
            result.append((str(value), str(label), value))
        elif isinstance(option, dict):
            result.append((str(option["value"]), str(option.get("label", option["value"])), option["value"]))
        else:
            result.append((str(option), str(option), option))
    wires = [w for w, _, _ in result]
    if len(set(wires)) != len(wires):
        raise InvalidComponentProps("option values must be unique")
    return result


class Select(Field):
    """Drop-down choice bound to a Signal holding the *python value* of the selected option."""

    kind = "Select"

    def __init__(self, label: Any = "", *, options: Any = (), value: Any = None, bind: Signal | None = None,
                 on_change: Callable | None = None, placeholder: str | None = None, **kw: Any):
        if bind is not None and not isinstance(bind, Signal):
            raise InvalidComponentProps("bind= expects a ui.state(...) Signal")
        self._options_src = options
        self._placeholder = placeholder
        self._options = normalize_options(untracked(lambda: read(options)))
        if bind is None and value is None and self._options and placeholder is None:
            value = self._options[0][2]
        self.state: Signal = bind if bind is not None else Signal(value, name="select value")
        self._shadow: str | None = None
        super().__init__(label, **kw)
        if is_reactive(options):
            self._bind(options, self._set_options, "options")
        self._bind(lambda: self._wire(self.state.value), self._write, "value")
        self._on_change = adapt(on_change, None)
        for event in ("input", "change"):
            self._listen(self.control.id, event, self._on_pick)

    def _build_control(self) -> Element:
        control = Element("select", self, cls="u4-select")
        self._render_options(control)
        return control

    def _render_options(self, control: Element) -> None:
        control.children = []
        if self._placeholder is not None:
            control.add(Element("option", None, attrs={"value": ""}, text=self._placeholder))
        for wire, label, _ in self._options:
            control.add(Element("option", None, attrs={"value": wire}, text=label))

    def _set_options(self, options: Any) -> None:
        new = normalize_options(options)
        if new == self._options:
            return
        self._options = new
        self._render_options(self.control)
        if self.mounted:
            inner = "".join(child.html() for child in self.control.children)
            self.control._op("replace_children_html", html=inner)
            self._shadow = None
            self.window._queue({"op": "set_value", "element": self.control.id,
                                "value": self._wire(self.state.peek())})

    def _wire(self, value: Any) -> str:
        for wire, _, python in self._options:
            if python == value or wire == value:
                return wire
        return ""

    def _write(self, wire: str) -> None:
        if wire == self._shadow:
            return
        self._shadow = wire
        if self.mounted:
            self.window._queue({"op": "set_value", "element": self.control.id, "value": wire})
        else:
            for child in self.control.children:
                child.attrs.pop("selected", None)
                if child.attrs.get("value") == wire:
                    child.attrs["selected"] = True

    def _on_pick(self, event: dict) -> None:
        wire = event.get("value")
        if wire is None or wire == self._shadow:
            return
        self._shadow = wire
        value = next((python for w, _, python in self._options if w == wire), None)
        self.state.set(value)
        self._emit(self._on_change, value)

    @property
    def value(self) -> Any:
        return self.state.value

    def set_value(self, value: Any) -> None:
        self.state.set(value)

    @property
    def options(self) -> list[tuple[str, str, Any]]:
        return list(self._options)


class RadioGroup(Field):
    """One-of-many choice rendered as radio buttons."""

    kind = "Radio"

    def __init__(self, label: Any = "", *, options: Any = (), value: Any = None, bind: Signal | None = None,
                 on_change: Callable | None = None, horizontal: bool = False, **kw: Any):
        self._options = normalize_options(options)
        self._horizontal = horizontal
        if bind is None and value is None and self._options:
            value = self._options[0][2]
        self.state: Signal = bind if bind is not None else Signal(value, name="radio value")
        self._shadow: str | None = None
        super().__init__(label, **kw)
        self._bind(lambda: self._wire(self.state.value), self._write, "value")
        self._on_change = adapt(on_change, None)
        for radio in self._radios:
            for event in ("input", "change"):
                self._listen(radio.id, event, self._on_pick)

    def _build_control(self) -> Element:
        group = Element("div", self, cls="u4-radio-group u4-horizontal" if self._horizontal else "u4-radio-group",
                        attrs={"role": "radiogroup"})
        name = group.id
        self._radios: list[Element] = []
        for wire, label, _ in self._options:
            row = Element("label", self, cls="u4-check")
            radio = Element("input", self, attrs={"type": "radio", "name": name, "value": wire})
            row.add(radio, Element("span", self, text=label))
            group.add(row)
            self._radios.append(radio)
        return group

    def _build(self) -> Element:
        root = super()._build()
        self.label_el.tag = "span"
        self.label_el.attrs.pop("for", None)
        return root

    def _wire(self, value: Any) -> str:
        for wire, _, python in self._options:
            if python == value or wire == value:
                return wire
        return ""

    def _write(self, wire: str) -> None:
        if wire == self._shadow:
            return
        self._shadow = wire
        for radio in self._radios:
            checked = radio.attrs.get("value") == wire
            if self.mounted:
                if checked:
                    self.window._queue({"op": "set_checked", "element": radio.id, "checked": True})
            else:
                radio.set_attr("checked", checked)

    def _on_pick(self, event: dict) -> None:
        if event.get("checked") is False:
            return
        element = event.get("element")
        radio = next((r for r in self._radios if r.id == element), None)
        if radio is None:
            return
        wire = radio.attrs.get("value")
        if wire == self._shadow:
            return
        self._shadow = wire
        value = next((python for w, _, python in self._options if w == wire), None)
        self.state.set(value)
        self._emit(self._on_change, value)

    @property
    def value(self) -> Any:
        return self.state.value

    def set_value(self, value: Any) -> None:
        self.state.set(value)

    def _focus_target(self) -> Element:
        wire = self._shadow
        return next((r for r in self._radios if r.attrs.get("value") == wire), self._radios[0] if self._radios
                    else self.control)


class Slider(TextField):
    """Range slider bound to a numeric Signal."""

    kind = "Slider"

    def __init__(self, label: Any = "", *, value: float = 0, min: float = 0, max: float = 100, step: float = 1,
                 **kw: Any):
        self._integer = all(float(x).is_integer() for x in (min, max, step))
        self._range = (min, max, step)
        super().__init__(label, value=value, type="range", **kw)
        self.control.classes = ["u4-slider"]
        for attr, v in zip(("min", "max", "step"), self._range):
            self.control.set_attr(attr, v)

    def _to_text(self, value: Any) -> str:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)

    def _from_text(self, text: str) -> Any:
        number = float(text)
        return int(number) if self._integer else number


# ---- simple visual components -----------------------------------------------------------

class Divider(Component):
    kind = "Divider"

    def __init__(self, *, vertical: bool = False, **kw: Any):
        self._vertical = vertical
        super().__init__(**kw)

    def _build(self) -> Element:
        return Element("hr", self, cls="u4-divider-vertical" if self._vertical else "u4-divider")


class Spacer(Component):
    kind = "Spacer"

    def _build(self) -> Element:
        return Element("div", self, cls="u4-spacer", attrs={"aria-hidden": "true"})


class Spinner(Component):
    kind = "Spinner"

    def _build(self) -> Element:
        return Element("span", self, cls="u4-spinner", attrs={"role": "status", "aria-label": "Loading"})


class Progress(Component):
    """Determinate progress bar; ``value`` 0..1 (reactive)."""

    kind = "Progress"

    def __init__(self, value: Any = 0.0, **kw: Any):
        super().__init__(**kw)
        self._bind(value, self._apply, "value")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-progress", attrs={"role": "progressbar", "aria-valuemin": "0",
                                                              "aria-valuemax": "100"})
        self.bar = Element("div", self, cls="u4-progress-bar")
        root.add(self.bar)
        return root

    def _apply(self, value: Any) -> None:
        fraction = min(1.0, max(0.0, float(value or 0)))
        percent = f"{fraction * 100:.1f}%"
        self.bar.set_style("width", percent)
        self.root.set_attr("aria-valuenow", str(round(fraction * 100)))


class Html(Component):
    """Raw island of *trusted* HTML handed to the developer; UI4ME UI never reconciles inside it."""

    kind = "Html"

    def __init__(self, trusted_html: str, *, css: str | None = None, mount: str = "island", **kw: Any):
        if mount != "island":
            raise InvalidComponentProps("ui.html only supports mount='island'")
        if not isinstance(trusted_html, str):
            raise InvalidComponentProps("ui.html needs trusted HTML as a string")
        self._trusted = trusted_html
        super().__init__(**kw)
        if css:
            self.app.css(css)

    def _build(self) -> Element:
        return Element("div", self, cls="u4-island")

    def _html(self) -> str:
        return self.root.open_tag() + self._trusted + "</div>"

    def set_html(self, trusted_html: str) -> None:
        """Replace the island's content with new trusted HTML."""
        self._live_check()
        self._trusted = trusted_html
        if self.mounted:
            self.root._op("replace_children_html", html=trusted_html)
            self._touch()

    @property
    def element_id(self) -> str:
        return self.root.id


class Image(Component):
    """Image from the app's ``assets`` directory (relative path) — Core blocks other local files."""

    kind = "Image"

    def __init__(self, src: Any, *, alt: str = "", width: str | None = None, height: str | None = None, **kw: Any):
        self._alt = alt
        super().__init__(**kw)
        if self.app.assets is None:
            raise InvalidComponentProps("ui.image needs ui.app(assets='folder') so Core may load local files")
        self._bind(src, self._set_src, "src")
        if width:
            self.root.set_style("width", width)
        if height:
            self.root.set_style("height", height)

    def _build(self) -> Element:
        return Element("img", self, cls="u4-image", attrs={"alt": self._alt})

    def _set_src(self, src: Any) -> None:
        text = str(src or "")
        if ":" in text.split("/")[0] or text.startswith(("/", "\\")) or ".." in text.replace("\\", "/").split("/"):
            raise InvalidComponentProps("ui.image src must be a relative path inside the assets directory")
        self.root.set_attr("src", text)
