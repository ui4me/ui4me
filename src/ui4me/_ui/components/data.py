"""Long-lived views: LogView (bounded streaming lines) and ChatView (local message list)."""
from __future__ import annotations

import dataclasses
import itertools
import threading
import time
from collections import deque
from typing import Any, Callable, Iterable, Sequence

from ..component import Component, Container, Frame, adapt, pop, push
from ..dom import Element, escape_text
from ..errors import InvalidComponentProps, UiBusyError
from ..reactive import Signal, read, untracked

LEVELS = ("debug", "info", "warning", "error")
MAX_LINE = 8 * 1024


class LogView(Component):
    """Append-only log with bounded retention and scroll-follow.

    ``append``/``extend``/``clear`` run on the owner thread and are coalesced into one Core
    batch per update (``insert_html`` + ``trim_children``). From worker threads use
    :meth:`post` (thread-safe, coalesced into a single owner post at a time).

    ``follow='smart'``: stay at the end while the reader is at the end; scrolling up pauses,
    returning to the end resumes (Core ``set_scroll_follow``). ``True``: always jump to the
    end. ``False``: never.
    """

    kind = "Log"

    def __init__(self, *, max_lines: int = 5000, follow: str | bool = "smart", height: str | None = None,
                 **kw: Any):
        if max_lines < 1 or max_lines > 20000:
            raise InvalidComponentProps("max_lines must be between 1 and 20000")
        if follow not in ("smart", True, False):
            raise InvalidComponentProps("follow must be 'smart', True or False")
        self.max_lines = max_lines
        self.follow = follow
        self._lines: deque[tuple[str, str]] = deque(maxlen=max_lines)
        self._pending: list[tuple[str, str]] = []
        self._cleared = False
        self._ingress: list[tuple[str, str]] = []
        self._ingress_lock = threading.Lock()
        self._ingress_posted = False
        self._ingress_dropped = 0
        self.count = Signal(0, name="log lines")
        self.total = 0
        super().__init__(**kw)
        if height:
            self.root.set_style("height", height)
            self.root.set_style("flex", "0 0 auto")

    def _build(self) -> Element:
        return Element("div", self, cls="u4-log", attrs={"role": "log", "tabindex": "0", "aria-live": "off"})

    def _html(self) -> str:
        lines = "".join(self._line_html(t, l) for t, l in self._lines)
        return self.root.open_tag() + lines + "</div>"

    @staticmethod
    def _line_html(text: str, level: str) -> str:
        cls = "u4-log-line" if level == "info" else f"u4-log-line u4-level-{level}"
        return f'<div class="{cls}">{escape_text(text)}</div>'

    def _on_mount(self) -> None:
        if self.follow == "smart":
            self.window._queue({"op": "set_scroll_follow", "element": self.root.id, "follow": True})
            self.window._queue({"op": "scroll_to", "element": self.root.id, "y": 1e9})
        self.app._request_commit()

    # -- owner-thread API ----------------------------------------------------------------------
    def append(self, line: Any, level: str = "info") -> None:
        self.extend([line], level)

    def extend(self, lines: Iterable[Any], level: str = "info") -> None:
        self._live_check()
        if level not in LEVELS:
            raise InvalidComponentProps(f"level must be one of {', '.join(LEVELS)}")
        items = []
        for line in lines:
            if isinstance(line, tuple) and len(line) == 2 and line[1] in LEVELS:
                text, lvl = line
            else:
                text, lvl = line, level
            text = str(text)
            if len(text) > MAX_LINE:
                text = text[:MAX_LINE] + "…"
            items.append((text, lvl))
        if not items:
            return
        self._lines.extend(items)
        self.total += len(items)
        if self.mounted:
            self._pending.extend(items)
            if len(self._pending) > self.max_lines:
                del self._pending[:-self.max_lines]
                self._cleared = True
            if len(self._pending) == len(items):
                self.window.call(self._flush)  # one flush per commit, however many appends
        self.count.set(len(self._lines))

    def _flush(self, core) -> None:
        pending, self._pending = self._pending, []
        cleared, self._cleared = self._cleared, False
        if not pending or self.disposed:
            return
        html = "".join(self._line_html(t, l) for t, l in pending)
        ops = []
        if cleared:
            ops.append({"op": "replace_children_html", "element": self.root.id, "html": ""})
        ops.append({"op": "insert_html", "element": self.root.id, "position": "beforeend", "html": html})
        ops.append({"op": "trim_children", "element": self.root.id, "keep": self.max_lines, "from": "start"})
        core.batch(ops)
        if self.follow is True:
            core.scroll_to(self.root.id, y=1e9)

    def clear(self) -> None:
        self._live_check()
        self._lines.clear()
        self._pending.clear()
        if self.mounted:
            self.root._op("replace_children_html", html="")
            self._touch()
        self.count.set(0)

    def set_follow(self, follow: str | bool) -> None:
        self._live_check()
        self.follow = follow
        if self.mounted:
            self.window._queue({"op": "set_scroll_follow", "element": self.root.id, "follow": follow == "smart"})
            if follow:
                self.window._queue({"op": "scroll_to", "element": self.root.id, "y": 1e9})
            self._touch()

    def lines(self) -> list[str]:
        """Retained lines (oldest first)."""
        return [t for t, _ in self._lines]

    # -- thread-safe ingress ---------------------------------------------------------------------
    def post(self, lines: Any, level: str = "info") -> None:
        """Thread-safe append. Lines are buffered and delivered in one owner post at a time."""
        batch = [lines] if isinstance(lines, str) else list(lines)
        with self._ingress_lock:
            self._ingress.extend((str(x), level) if not isinstance(x, tuple) else x for x in batch)
            if len(self._ingress) > self.max_lines:
                self._ingress_dropped += len(self._ingress) - self.max_lines
                del self._ingress[:-self.max_lines]
            if self._ingress_posted:
                return
            self._ingress_posted = True
        try:
            self.app.post(self._drain)
        except Exception:
            with self._ingress_lock:
                self._ingress_posted = False
            raise

    def _drain(self) -> None:
        with self._ingress_lock:
            items, self._ingress = self._ingress, []
            dropped, self._ingress_dropped = self._ingress_dropped, 0
            self._ingress_posted = False
        self.total += dropped
        if items and not self.disposed:
            self.extend(items)


@dataclasses.dataclass
class ChatMessage:
    role: str
    text: str
    id: int = 0
    time: float = dataclasses.field(default_factory=time.time)
    name: str | None = None


_message_ids = itertools.count(1)


class MessageView(Component):
    kind = "Message"

    def __init__(self, chat: "ChatView", message: ChatMessage):
        self._chat, self.message = chat, message
        self._streamed = False
        super().__init__(place=False)
        self._render_body()

    def _build(self) -> Element:
        m = self.message
        root = Element("div", self, cls=f"u4-msg u4-msg-{m.role if m.role in ('user', 'assistant', 'system') else 'other'}")
        meta = Element("div", self, cls="u4-msg-meta")
        meta.add(Element("span", self, cls="u4-strong", text=m.name or m.role.capitalize()))
        meta.add(Element("span", self, text=time.strftime("%H:%M", time.localtime(m.time))))
        self.body = Element("div", self, cls="u4-msg-body u4-md" if self._chat._markdown else "u4-msg-body")
        root.add(meta, self.body)
        return root

    def _render_body(self) -> None:
        from .markdown import render_markdown
        if self._chat._markdown:
            self.body.set_html(render_markdown(self.message.text))
        else:
            self.body.set_text(self.message.text)

    def stream(self, chunk: str) -> None:
        """Append text to this message (patches only this message's body)."""
        self._live_check()
        self.message.text += chunk
        if not self._chat._markdown and self.mounted:
            self.body.text = self.message.text
            for start in range(0, len(chunk), 8000):
                self.body._op("append_text", text=chunk[start:start + 8000])
            self._touch()
            return
        self._render_body()
        self._touch()

    def set_text(self, text: str) -> None:
        self._live_check()
        self.message.text = text
        self._render_body()
        self._touch()


class ChatView(Container):
    """Local chat presentation: message list + composer. No networking or model client.

    ``chat.add('assistant', 'Hi')`` returns a message ref with ``.stream(chunk)``. The composer
    sends on Enter (Shift+Enter for a newline) and calls ``on_send(text)``.
    """

    kind = "Chat"

    def __init__(self, messages: Any = None, *, on_send: Callable | None = None, markdown: bool = True,
                 placeholder: str = "Write a message…", max_messages: int = 500, composer: bool = True, **kw: Any):
        self._markdown = markdown
        self._on_send = adapt(on_send, None)
        self._placeholder = placeholder
        self.max_messages = max_messages
        self._has_composer = composer
        self.messages: Signal[list[ChatMessage]] = messages if isinstance(messages, Signal) else Signal(
            [self._coerce(m) for m in (messages or [])], name="chat messages")
        super().__init__(**kw)
        from .regions import KeyedChildren
        self._list = KeyedChildren(self, self._messages_el, lambda m: m.id, self._make, lambda c, m: self._update(c, m))
        self._bind(lambda: list(self.messages.value), self._list.reconcile, "messages")
        if composer:
            self._build_composer()

    @staticmethod
    def _coerce(message: Any) -> ChatMessage:
        if isinstance(message, ChatMessage):
            if not message.id:
                message.id = next(_message_ids)
            return message
        if isinstance(message, dict):
            data = dict(message)
            data.setdefault("id", next(_message_ids))
            return ChatMessage(**data)
        role, text = message
        return ChatMessage(role, text, next(_message_ids))

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-chat")
        self._messages_el = Element("div", self, cls="u4-chat-messages", attrs={"role": "log", "tabindex": "0"})
        self._composer_el = Element("div", self, cls="u4-chat-composer")
        root.add(self._messages_el, self._composer_el)
        return root

    @property
    def slot(self) -> Element:
        return self._composer_el

    def _build_composer(self) -> None:
        from .basic import Button, TextArea
        frame = push(Frame(self.app, self, self._composer_el, self.window))
        try:
            self.input = TextArea(None, rows=2, placeholder=self._placeholder, classes="u4-grow")
            self.input.label_el.set_attr("hidden", True)
            self.input.control.set_attr("aria-label", "Message")
            self.send_button = Button("Send", on_click=self.send)
        finally:
            pop(frame)
        self._listen(self.input.control.id, "keydown", self._key)

    def _on_mount(self) -> None:
        self.window._queue({"op": "set_scroll_follow", "element": self._messages_el.id, "follow": True})
        if self._has_composer:
            self.window._queue({"op": "set_default_action", "element": self.input.control.id, "event": "keydown",
                                "options": {"key": "Enter", "shift": False}})
        self.app._request_commit()

    def _key(self, event: dict) -> None:
        if event.get("key") == "Enter" and not event.get("shift") and not self.input._composing:
            self.send()

    def _make(self, message: ChatMessage, _index: int) -> MessageView:
        frame = push(Frame(self.app, self, None, self.window))
        try:
            return MessageView(self, message)
        finally:
            pop(frame)

    def _update(self, component: MessageView, message: ChatMessage) -> bool:
        component.message = message
        component._render_body()
        return True

    def add(self, role: str, text: str = "", *, name: str | None = None) -> MessageView:
        """Append a message; returns its view (``.stream(chunk)`` to extend it)."""
        message = ChatMessage(role, text, next(_message_ids), name=name)
        items = list(self.messages.peek()) + [message]
        if len(items) > self.max_messages:
            items = items[-self.max_messages:]
        self.messages.set(items)
        self.app.scheduler.flush() if not self.app.scheduler._flushing else None
        return self._list.component(message.id)  # type: ignore[return-value]

    def send(self) -> None:
        """Send the composer text (as the user) and clear the composer."""
        if not self._has_composer:
            return
        text = self.input.state.peek()
        if not text or not text.strip():
            return
        self.input.set_value("")
        self.add("user", text.rstrip())
        self._emit(self._on_send, text.rstrip())

    def clear(self) -> None:
        self.messages.set([])
