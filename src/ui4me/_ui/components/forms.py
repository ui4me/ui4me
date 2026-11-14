"""Forms generated from dataclasses: fields -> controls -> validation -> typed submit.

Field metadata (``dataclasses.field(metadata={...})``):

``label``, ``description``, ``placeholder``, ``required`` (bool), ``min_length``, ``max_length``,
``pattern`` (``'email'``, ``'url'`` or a regular expression), ``min``, ``max``, ``step``,
``choices`` (sequence/mapping/Enum), ``widget`` (``'radio'``, ``'textarea'``, ``'switch'``),
``multiline`` (bool), ``secret`` (bool, password field, never logged), ``validator``
(callable returning None or an error message), ``rows``.

``on_submit`` receives a validated instance of the model. It may be ``async def``: the form
shows a pending state, prevents duplicate submission and displays errors for retry.
"""
from __future__ import annotations

import dataclasses
import enum
import re
import types
import typing
from typing import Any, Callable, Literal, Sequence, get_args, get_origin, get_type_hints

from ..aio import UiFuture
from ..component import Container, Frame, adapt, pop, push
from ..dom import Element
from ..errors import InvalidComponentProps, ValidationError, ValidationIssue
from ..reactive import Signal

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL = re.compile(r"^(https?|mailto):[^\s]+$", re.I)
NAMED_PATTERNS = {"email": (EMAIL, "Enter a valid email address"), "url": (URL, "Enter a valid URL")}


@dataclasses.dataclass
class FieldSpec:
    name: str
    label: str
    kind: str                 # text | textarea | password | number | bool | choice
    nullable: bool = False
    required: bool = False
    integer: bool = False
    choices: Any = None
    meta: dict = dataclasses.field(default_factory=dict)
    python_type: Any = str


def _unwrap_optional(tp: Any) -> tuple[Any, bool]:
    origin = get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1 and len(get_args(tp)) == 2:
            return args[0], True
    return tp, False


def _label(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def describe(model: type, exclude: Sequence[str] = ()) -> list[FieldSpec]:
    """Field descriptors for a dataclass type."""
    if not (isinstance(model, type) and dataclasses.is_dataclass(model)):
        raise InvalidComponentProps("ui.form needs a dataclass type (e.g. @dataclass class Customer: ...)")
    hints = get_type_hints(model)
    specs: list[FieldSpec] = []
    for f in dataclasses.fields(model):
        if f.name in exclude or not f.init or f.name.startswith("_"):
            continue
        meta = dict(f.metadata)
        tp, nullable = _unwrap_optional(hints.get(f.name, str))
        label = meta.get("label") or _label(f.name)
        required = bool(meta.get("required", False))
        if "choices" in meta:
            specs.append(FieldSpec(f.name, label, "choice", nullable, required, choices=meta["choices"], meta=meta,
                                   python_type=tp))
        elif isinstance(tp, type) and issubclass(tp, enum.Enum):
            specs.append(FieldSpec(f.name, label, "choice", nullable, required, choices=tp, meta=meta, python_type=tp))
        elif get_origin(tp) is Literal:
            specs.append(FieldSpec(f.name, label, "choice", nullable, required, choices=list(get_args(tp)), meta=meta,
                                   python_type=tp))
        elif tp is bool:
            specs.append(FieldSpec(f.name, label, "bool", meta=meta, python_type=bool))
        elif tp in (int, float):
            specs.append(FieldSpec(f.name, label, "number", nullable, required, integer=tp is int, meta=meta,
                                   python_type=tp))
        elif tp is str:
            kind = "password" if meta.get("secret") else (
                "textarea" if meta.get("multiline") or meta.get("widget") == "textarea" else "text")
            specs.append(FieldSpec(f.name, label, kind, nullable, required, meta=meta, python_type=str))
        else:
            raise InvalidComponentProps(
                f"ui.form cannot generate a control for field {f.name!r} of type {tp!r}; exclude it "
                "(exclude=[...]) and edit it with a custom control")
    return specs


def _initial(model: type, value: Any, spec: FieldSpec) -> Any:
    if value is not None:
        return getattr(value, spec.name)
    for f in dataclasses.fields(model):
        if f.name == spec.name:
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
    return None if spec.kind in ("number", "choice") else (False if spec.kind == "bool" else "")


def check(spec: FieldSpec, value: Any) -> str | None:
    """Built-in validation of one value; returns an error message or None."""
    meta = spec.meta
    empty = value is None or (isinstance(value, str) and not value.strip())
    if empty:
        if spec.required or (spec.kind == "number" and not spec.nullable):
            return meta.get("required_message", "This field is required")
        return None
    if isinstance(value, str):
        if "min_length" in meta and len(value) < meta["min_length"]:
            return f"Use at least {meta['min_length']} characters"
        if "max_length" in meta and len(value) > meta["max_length"]:
            return f"Use at most {meta['max_length']} characters"
        pattern = meta.get("pattern")
        if pattern:
            regex, message = NAMED_PATTERNS.get(pattern, (None, None))
            if regex is None:
                regex, message = re.compile(pattern), meta.get("pattern_message", "Invalid format")
            if not regex.fullmatch(value.strip()):
                return message
    if spec.kind == "number" and isinstance(value, (int, float)):
        if "min" in meta and value < meta["min"]:
            return f"Must be at least {meta['min']}"
        if "max" in meta and value > meta["max"]:
            return f"Must be at most {meta['max']}"
    validator = meta.get("validator")
    if validator is not None:
        result = validator(value)
        if isinstance(result, ValidationIssue):
            return result.message
        if result:
            return str(result)
    return None


class Form(Container):
    """Generated, validated form. ``on_submit(instance)`` runs only with valid data."""

    kind = "Form"

    def __init__(self, model: type, *, value: Any = None, on_submit: Callable | None = None,
                 exclude: Sequence[str] = (), submit_label: str = "Save", on_cancel: Callable | None = None,
                 cancel_label: str = "Cancel", validate: Callable | None = None, columns: int = 1,
                 reset_on_submit: bool = False, validation_mode: Literal["submit", "change", "blur"] = "submit",
                 **kw: Any):
        self.model = model
        self.specs = describe(model, exclude)
        self._value = value
        self._on_submit = adapt(on_submit, None)
        self._on_cancel = adapt(on_cancel, None)
        self._validate = validate
        if validation_mode not in ("submit", "change", "blur"):
            raise InvalidComponentProps("validation_mode must be submit, change or blur")
        if not 1 <= columns <= 6:
            raise InvalidComponentProps("form columns must be between 1 and 6")
        self.validation_mode = validation_mode
        self._columns = columns
        self._reset_on_submit = reset_on_submit
        self.dirty = Signal(False, name="form dirty")
        self.touched = Signal(frozenset(), name="form touched fields")
        self.valid = Signal(True, name="form validated")
        self._initial_snapshot: dict[str, Any] = {}
        self.submitting = Signal(False, name="form submitting")
        self.form_error: Signal[str | None] = Signal(None, name="form error")
        self.fields: dict[str, Any] = {}
        self._submit_label, self._cancel_label = submit_label, cancel_label
        super().__init__(**kw)
        self._build_fields()

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-form", attrs={"role": "form"})
        self._body = Element("div", self, cls="u4-grid u4-gap-md" if self._columns > 1 else "u4-column u4-gap-md")
        if self._columns > 1:
            self._body.set_style("--u4-cols", str(int(self._columns)))
        self._error_el = Element("div", self, cls="u4-form-error", attrs={"role": "alert", "hidden": True})
        self._actions = Element("div", self, cls="u4-form-actions")
        root.add(self._body, self._error_el, self._actions)
        return root

    @property
    def slot(self) -> Element:
        return self._body

    def _build_fields(self) -> None:
        from .basic import Button, Checkbox, NumberField, PasswordField, RadioGroup, Select, TextArea, TextField
        frame = push(Frame(self.app, self, self._body, self.window))
        try:
            for spec in self.specs:
                meta, initial = spec.meta, _initial(self.model, self._value, spec)
                common = dict(description=meta.get("description"), required=spec.required, name=spec.name)
                if spec.kind == "bool":
                    control = Checkbox(spec.label, value=bool(initial),
                                       on_change=lambda _v, n=spec.name: self._edited(n))
                    if meta.get("widget") == "switch":
                        control.control.set_attr("role", "switch")
                elif spec.kind == "number":
                    control = NumberField(spec.label, value=initial, min=meta.get("min"), max=meta.get("max"),
                                          step=meta.get("step"), integer=spec.integer,
                                          placeholder=meta.get("placeholder", ""),
                                          on_change=lambda _v, n=spec.name: self._edited(n),
                                          on_submit=lambda _v: self.submit(), **common)
                elif spec.kind == "choice":
                    cls = RadioGroup if meta.get("widget") == "radio" else Select
                    extra = {} if cls is RadioGroup else {"placeholder": "—" if spec.nullable or initial is None else None}
                    control = cls(spec.label, options=spec.choices, value=initial,
                                  on_change=lambda _v, n=spec.name: self._edited(n), **extra, **common)
                elif spec.kind == "textarea":
                    control = TextArea(spec.label, value=initial or "", rows=meta.get("rows", 3),
                                       placeholder=meta.get("placeholder", ""),
                                       on_change=lambda _v, n=spec.name: self._edited(n), **common)
                elif spec.kind == "password":
                    control = PasswordField(spec.label, value=initial or "", placeholder=meta.get("placeholder", ""),
                                            on_change=lambda _v, n=spec.name: self._edited(n),
                                            on_submit=lambda _v: self.submit(), **common)
                else:
                    control = TextField(spec.label, value=initial or "", placeholder=meta.get("placeholder", ""),
                                        max_length=meta.get("max_length"),
                                        on_change=lambda _v, n=spec.name: self._edited(n),
                                        on_submit=lambda _v: self.submit(), **common)
                self.fields[spec.name] = control
                if self.validation_mode == "blur":
                    control._listen(control._focus_target().id, "blur",
                                    lambda _event, field=spec.name: self._validate_field(field))
        finally:
            pop(frame)
        actions = push(Frame(self.app, self, self._actions, self.window))
        try:
            if self._on_cancel is not None:
                Button(self._cancel_label, variant="secondary", on_click=lambda: self._emit(self._on_cancel))
            self.submit_button = Button(self._submit_label, on_click=self.submit, loading=self.submitting)
        finally:
            pop(actions)
        self._bind(lambda: self.form_error.value, self._show_form_error, "form error")
        self._initial_snapshot = self._snapshot()

    def _show_form_error(self, message: Any) -> None:
        self._error_el.set_text(message or "")
        self._error_el.set_attr("hidden", not message)

    def _snapshot(self) -> dict[str, Any]:
        return {name: control.state.peek() for name, control in self.fields.items()}

    def mark_clean(self) -> None:
        """Commit the current form values as the pristine baseline after saving."""
        self._initial_snapshot = self._snapshot()
        self.dirty.set(False)
        self.touched.set(frozenset())

    def _edited(self, name: str) -> None:
        self.touched.set(self.touched.peek() | {name})
        self.dirty.set(self._snapshot() != self._initial_snapshot)
        control = self.fields[name]
        if control.error_signal.peek() if hasattr(control, "error_signal") else False:
            control.set_error(None)
        if self.validation_mode == "change":
            self._validate_field(name)

    def _validate_field(self, name: str) -> str | None:
        spec = next(s for s in self.specs if s.name == name)
        control = self.fields[name]
        message = check(spec, control.state.peek())
        control.set_error(message)
        self.valid.set(all(not self.fields[s.name].error for s in self.specs))
        return message

    # -- values ---------------------------------------------------------------------------------
    @property
    def values(self) -> dict[str, Any]:
        """Current raw field values (tracked)."""
        return {name: control.value for name, control in self.fields.items()}

    def validate(self, *, focus: bool = True) -> list[ValidationIssue]:
        """Validate all fields, show messages, focus the first invalid field. Returns the issues."""
        issues: list[ValidationIssue] = []
        values = {name: control.state.peek() for name, control in self.fields.items()}
        for spec in self.specs:
            control = self.fields[spec.name]
            parse_error = control.error if spec.kind == "number" and control.error else None
            message = parse_error or check(spec, values[spec.name])
            if message:
                issues.append(ValidationIssue(spec.name, message))
        if not issues and self._validate is not None:
            try:
                instance = self._build_instance(values)
            except Exception as error:  # constructor validation (__post_init__) failures
                issues.append(ValidationIssue("__form__", str(error)))
            else:
                result = self._validate(instance)
                if isinstance(result, dict):
                    issues.extend(ValidationIssue(k, str(v)) for k, v in result.items() if v)
                elif result:
                    issues.extend(r if isinstance(r, ValidationIssue) else ValidationIssue("__form__", str(r))
                                  for r in (result if isinstance(result, (list, tuple)) else [result]))
        by_field = {i.field: i.message for i in issues}
        for name, control in self.fields.items():
            if hasattr(control, "set_error"):
                control.set_error(by_field.get(name))
        self.form_error.set(by_field.get("__form__"))
        self.valid.set(not bool(issues))
        if issues and focus:
            first = next((self.fields[i.field] for i in issues if i.field in self.fields), None)
            if first is not None and first.mounted:
                first.focus()
        return issues

    def _build_instance(self, values: dict[str, Any]) -> Any:
        edited = {}
        for spec in self.specs:
            value = values[spec.name]
            if spec.kind == "text" or spec.kind in ("textarea", "password"):
                value = value if value or not spec.nullable else None
            if spec.kind == "number" and value is not None and not spec.integer:
                value = float(value)
            edited[spec.name] = value
        if self._value is not None:
            return dataclasses.replace(self._value, **edited)
        return self.model(**edited)

    @property
    def value(self) -> Any:
        """A validated model instance (raises ``ValidationError`` when invalid)."""
        issues = self.validate(focus=False)
        if issues:
            raise ValidationError(issues)
        return self._build_instance({n: c.state.peek() for n, c in self.fields.items()})

    def submit(self) -> UiFuture | bool:
        """Validate and call ``on_submit``. Returns False when invalid, else True or the pending future."""
        if self.submitting.peek():
            return False  # duplicate submission while pending
        if self.validate():
            return False
        try:
            instance = self._build_instance({n: c.state.peek() for n, c in self.fields.items()})
        except Exception as error:
            self.form_error.set(str(error))
            return False
        self.form_error.set(None)
        if self._on_submit is None:
            return True
        try:
            result = self._emit(self._on_submit, instance)
        except Exception as error:
            self.form_error.set(f"Could not save: {error}")
            self.app._report(error, f"{self.path()} on_submit")
            return False
        if isinstance(result, UiFuture) and not result.done:
            self.submitting.set(True)

            def settled(future: UiFuture) -> None:
                if self.disposed:
                    return
                self.submitting.set(False)
                if future.error is not None:
                    self.form_error.set(f"Could not save: {future.error}")
                elif self._reset_on_submit:
                    self.reset()
                else:
                    self.mark_clean()
            result.add_done_callback(settled)
            return result
        if self._reset_on_submit:
            self.reset()
        else:
            self.mark_clean()
        return True

    def reset(self, value: Any = None) -> None:
        """Restore initial values (or load ``value``) without simulating typing; clears errors."""
        if value is not None:
            self._value = value
        for spec in self.specs:
            control = self.fields[spec.name]
            control.set_value(_initial(self.model, self._value, spec))
            if hasattr(control, "set_error"):
                control.set_error(None)
        self.form_error.set(None)
        self.valid.set(True)
        self.mark_clean()

    def set_value(self, value: Any) -> None:
        """Load a model instance into the form."""
        self.reset(value)
