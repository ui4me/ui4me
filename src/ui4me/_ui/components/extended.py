"""Reusable desktop component primitives built solely on the UI4ME Core DOM.

These deliberately avoid a JavaScript runtime, synthetic browser events and native
services not advertised by Core. Controls are keyboard-usable using native HTML
inputs, and all state belongs to the creating component/window.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..component import Component, Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps
from ..reactive import Signal, read
from .basic import Checkbox, normalize_options
from .layout import _Pane


class Fieldset(Container):
    """A semantic ``<fieldset>`` with an accessible legend and managed content."""

    kind = "Fieldset"

    def __init__(self, legend: str, *, description: str | None = None, **kw: Any):
        if not legend.strip():
            raise InvalidComponentProps("fieldset requires a meaningful legend")
        self._legend = legend
        self._description = description
        super().__init__(**kw)

    def _build(self) -> Element:
        root = Element("fieldset", self, cls="u4-fieldset")
        root.add(Element("legend", self, cls="u4-fieldset-legend", text=self._legend))
        if self._description:
            hint = Element("p", self, cls="u4-fieldset-description", text=self._description)
            root.add(hint)
            root.set_attr("aria-describedby", hint.id)
        self._slot = Element("div", self, cls="u4-fieldset-content u4-column u4-gap-sm")
        root.add(self._slot)
        return root

    @property
    def slot(self) -> Element:
        return self._slot


class MultiSelect(Container):
    """Multi-option selection using native, labelled checkboxes.

    ``value`` is a tuple of Python values. UI4ME owns no native picker, so this
    is intentionally a fieldset (visible options), not an unqualified ARIA
    combobox claiming browser listbox behavior. Checked values survive renders.
    """

    kind = "MultiSelect"

    def __init__(self, label: str, *, options: Any, value: Sequence[Any] = (),
                 bind: Signal | None = None, on_change: Callable | None = None,
                 disabled: Any = False, **kw: Any):
        if not label.strip():
            raise InvalidComponentProps("multi-select needs an accessible label")
        self.label = label
        self._options = normalize_options(options)
        self.selected: Signal = bind if bind is not None else Signal(tuple(value), name="multi selected")
        if not isinstance(self.selected, Signal):
            raise InvalidComponentProps("bind must be a ui.state Signal")
        self._on_change = adapt(on_change, None)
        self._disabled = disabled
        self.items: dict[str, Checkbox] = {}
        super().__init__(**kw)
        frame = push(Frame(self.app, self, self._slot, self.window))
        try:
            for wire, text, python_value in self._options:
                def changed(checked: bool, option=python_value) -> None:
                    self._toggle(option, checked)
                checkbox = Checkbox(text, value=python_value in self.selected.peek(),
                                    on_change=changed, disabled=disabled)
                self.items[wire] = checkbox
        finally:
            pop(frame)
        self._bind(lambda: tuple(self.selected.value), self._sync, "selection")

    def _build(self) -> Element:
        root = Element("fieldset", self, cls="u4-fieldset u4-multiselect")
        root.add(Element("legend", self, cls="u4-fieldset-legend", text=self.label))
        self._slot = Element("div", self, cls="u4-multiselect-options")
        root.add(self._slot)
        return root

    @property
    def slot(self) -> Element:
        return self._slot

    @property
    def value(self) -> tuple[Any, ...]:
        return tuple(self.selected.value)

    def set_value(self, values: Sequence[Any]) -> None:
        allowed = [entry[2] for entry in self._options]
        unknown = [v for v in values if v not in allowed]
        if unknown:
            raise InvalidComponentProps(f"unknown multi-select option(s): {unknown!r}")
        self.selected.set(tuple(dict.fromkeys(values)))

    def _toggle(self, option: Any, checked: bool) -> None:
        current = [x for x in self.selected.peek() if x != option]
        if checked:
            current.append(option)
        value = tuple(current)
        if value != tuple(self.selected.peek()):
            self.selected.set(value)
            self._emit(self._on_change, value)

    def _sync(self, values: Sequence[Any]) -> None:
        for wire, _label, option in self._options:
            self.items[wire].set_value(option in values)


class ResizableSplit(Container):
    """Two adjustable panes with a native keyboard-operable range control.

    Uses an ordinary ``input type=range`` above the panes. This is robust on
    Core's supported DOM, including keyboard adjustment and accessibility,
    without requiring unqualified pointer capture or JavaScript.
    """

    kind = "ResizableSplit"

    def __init__(self, *, percent: int = 35, minimum: int = 15,
                 maximum: int = 85, label: str = "Resize panels", **kw: Any):
        if not (1 <= minimum < maximum <= 99 and minimum <= percent <= maximum):
            raise InvalidComponentProps("resizable split needs 1 <= min < max <= 99 and percent in range")
        self._initial = percent
        self._min, self._max = minimum, maximum
        self.label = label
        self.position = Signal(percent, name="split percentage")
        super().__init__(**kw)
        self.side = _Pane(self, self._left, "side")
        self.main = _Pane(self, self._right, "main")
        self._listen(self._control.id, "input", self._on_input)
        self._bind(lambda: self.position.value, self._adjust, "split")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-adjustable")
        controls = Element("div", self, cls="u4-adjustable-controls")
        label = Element("label", self, text=self.label)
        self._control = Element("input", self, cls="u4-slider", attrs={
            "type": "range", "min": self._min, "max": self._max,
            "value": self._initial, "aria-label": self.label,
        })
        label.add(self._control)
        controls.add(label)
        self._panes = Element("div", self, cls="u4-resizable-panes")
        self._left = Element("div", self, cls="u4-resizable-side")
        self._right = Element("div", self, cls="u4-resizable-main")
        self._panes.add(self._left, self._right)
        root.add(controls, self._panes)
        return root

    @property
    def slot(self) -> Element:
        return self._left

    def _adjust(self, value: int) -> None:
        value = max(self._min, min(self._max, int(value)))
        self._panes.set_style("--u4-split", str(value) + "%")
        if not self.mounted:
            self._control.set_attr("value", value)

    def _on_input(self, event: dict) -> None:
        try:
            position = int(float(event.get("value", self.position.peek())))
        except (TypeError, ValueError):
            return
        self.position.set(max(self._min, min(self._max, position)))

    def resize(self, percent: int) -> None:
        if not self._min <= percent <= self._max:
            raise InvalidComponentProps("split percentage outside configured range")
        self.position.set(percent)
        if self.mounted:
            self.window._queue({"op": "set_value", "element": self._control.id, "value": str(percent)})


class Metric(Component):
    """Dashboard statistic with accessible label, current value and optional trend."""

    kind = "Metric"

    def __init__(self, label: str, value: Any, *, detail: Any = None, tone: str = "default", **kw: Any):
        self._label = label
        self._tone = tone
        self._value = value
        self._detail = detail
        super().__init__(**kw)
        self._bind(value, self._value_el.set_text, "value")
        self._bind(detail, self._detail_el.set_text, "detail")

    def _build(self) -> Element:
        root = Element("section", self, cls="u4-metric", attrs={"aria-label": self._label})
        root.add(Element("span", self, cls="u4-metric-label", text=self._label))
        self._value_el = Element("strong", self, cls="u4-metric-value")
        self._detail_el = Element("small", self, cls="u4-metric-detail")
        root.add(self._value_el, self._detail_el)
        if self._tone != "default":
            root.add_class("u4-tone-" + self._tone)
        return root


class Tooltip(Container):
    """Tooltip using CSS hover/focus; no unsupported pointer-capture API."""

    kind = "Tooltip"

    def __init__(self, text: str, **kw: Any):
        if not text.strip():
            raise InvalidComponentProps("tooltip text must not be empty")
        self._tooltip_text = text
        super().__init__(**kw)

    def _build(self) -> Element:
        root = Element("span", self, cls="u4-tooltip-root")
        self._slot = Element("span", self, cls="u4-tooltip-trigger")
        tip = Element("span", self, cls="u4-tooltip-text", attrs={"role": "tooltip"}, text=self._tooltip_text)
        # Assistive technology announces the tip as the trigger region's description.
        self._slot.set_attr("aria-describedby", tip.id)
        root.add(self._slot, tip)
        return root

    @property
    def slot(self) -> Element:
        return self._slot


class CopyButton(Component):
    """Copy plain text to the Core clipboard, reporting failures via the app."""

    kind = "CopyButton"

    def __init__(self, text: Any, *, label: str = "Copy", on_copy: Callable | None = None, **kw: Any):
        self._text, self._label = text, label
        self._on_copy = adapt(on_copy, None)
        super().__init__(**kw)
        self._listen(self.root.id, "click", self._clicked)

    def _build(self) -> Element:
        return Element("button", self, cls="u4-btn u4-btn-secondary", attrs={"type": "button"}, text=self._label)

    def _clicked(self, event: dict) -> None:
        try:
            value = str(read(self._text))
            self.app.clipboard.copy(value)
        except Exception as error:
            self.app._report(error, f"copy clipboard {self.path()}")
        else:
            self._emit(self._on_copy, value)
