"""Typed errors raised by UI4ME UI.

Every error derives from :class:`UiError`. Errors raised while running a component
callback carry the component path in ``component`` so messages name *where* it happened.
"""
from __future__ import annotations


class UiError(Exception):
    """Base class for UI4ME UI errors."""

    def __init__(self, message: str, *, component: str | None = None):
        if component:
            message = f"{message} (component {component})"
        super().__init__(message)
        self.component = component


class CoreCompatibilityError(UiError):
    """The installed UI4ME Core is missing or too old for this UI version."""


class UnsupportedCapability(UiError):
    """The platform or Core reports that a feature is not available here."""

    def __init__(self, feature: str, status: str, reason: str | None = None):
        detail = f": {reason}" if reason else ""
        super().__init__(f"{feature} is {status} on this platform{detail}")
        self.feature, self.status, self.reason = feature, status, reason


class DisposedComponentError(UiError):
    """A component (or its window) was disposed and can no longer be used."""


class WrongThreadError(UiError):
    """UI state and components belong to the UI owner thread."""


class ReactiveCycleError(UiError):
    """A computed value depends on itself or effects keep re-triggering each other."""


class InvalidComponentProps(UiError, ValueError):
    """A component was created or updated with invalid arguments."""


class DuplicateKeyError(UiError, ValueError):
    """Two items of a keyed list or table share the same key."""


class InvalidMarkupError(UiError, ValueError):
    """Markup or CSS was rejected."""


class UiBusyError(UiError):
    """A bounded queue is full; the work was not accepted."""


class AppClosedError(UiError):
    """The application has stopped and no longer accepts UI work."""


class TaskError(UiError):
    """A background task failed."""


class NativeServiceError(UiError):
    """A native OS service (dialog, clipboard, notification) failed."""


class ValidationIssue:
    """One validation problem of a form field. Not an exception: forms collect them."""

    __slots__ = ("field", "message")

    def __init__(self, field: str, message: str):
        self.field, self.message = field, message

    def __repr__(self) -> str:
        return f"ValidationIssue({self.field!r}, {self.message!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ValidationIssue) and (self.field, self.message) == (other.field, other.message)


class ValidationError(UiError, ValueError):
    """Raised by ``FormRef.value`` when the form is invalid; ``issues`` lists the problems."""

    def __init__(self, issues: list[ValidationIssue]):
        super().__init__("; ".join(f"{i.field}: {i.message}" for i in issues) or "invalid")
        self.issues = issues
