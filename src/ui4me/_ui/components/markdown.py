"""Safe Markdown subset -> HTML, plus a literal code block.

Supported: ATX headings, paragraphs, line breaks (two spaces / backslash), **bold**, *italic*,
~~strike~~, `code`, fenced code blocks, block quotes, ordered/unordered (nested by indent)
lists, horizontal rules, pipe tables, links ``[text](url)`` and autolinks ``<https://...>``.

Safety: every piece of source text is HTML-escaped; raw HTML in the source is shown as text;
only ``http``, ``https`` and ``mailto`` link targets are kept (others become plain text);
images render as their alt text (no remote fetches). The output contains no attributes
except ``href`` on links and ``class`` on code blocks.
"""
from __future__ import annotations

import re
from html import escape
from typing import Any

from ..component import Component
from ..dom import Element

_SAFE_URL = re.compile(r"^(https?://|mailto:)[^\s<>\"']+$", re.I)
_LANG = re.compile(r"^[A-Za-z0-9_+#.-]{1,32}$")
_INLINE = re.compile(
    r"(?P<code>`+)(?P<codetext>.+?)(?P=code)"
    r"|!\[(?P<alt>[^\]]*)\]\((?P<isrc>[^)\s]*)(?:\s+\"[^\"]*\")?\)"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<href>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    r"|<(?P<auto>(?:https?://|mailto:)[^>\s]+)>"
    r"|(?P<strong>\*\*|__)(?P<stext>.+?)(?P=strong)"
    r"|(?P<em>\*|_)(?P<etext>[^*_\s](?:.*?[^*_\s])?)(?P=em)"
    r"|~~(?P<del>.+?)~~"
    r"|(?P<br>  \n|\\\n)",
    re.S,
)
MAX_SOURCE = 512 * 1024


def _inline(text: str, depth: int = 0) -> str:
    if depth > 6:
        return escape(text, quote=False)
    out: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(escape(text[pos:m.start()], quote=False))
        pos = m.end()
        if m.group("code"):
            out.append(f"<code>{escape(m.group('codetext').strip(), quote=False)}</code>")
        elif m.group("alt") is not None and m.group(0).startswith("!"):
            out.append(escape(m.group("alt") or "image", quote=False))
        elif m.group("ltext") is not None:
            href = m.group("href")
            label = _inline(m.group("ltext"), depth + 1)
            if _SAFE_URL.match(href):
                out.append(f'<a href="{escape(href, quote=True)}">{label}</a>')
            else:
                out.append(label)
        elif m.group("auto"):
            url = m.group("auto")
            out.append(f'<a href="{escape(url, quote=True)}">{escape(url, quote=False)}</a>')
        elif m.group("strong"):
            out.append(f"<strong>{_inline(m.group('stext'), depth + 1)}</strong>")
        elif m.group("em"):
            out.append(f"<em>{_inline(m.group('etext'), depth + 1)}</em>")
        elif m.group("del"):
            out.append(f"<del>{_inline(m.group('del'), depth + 1)}</del>")
        elif m.group("br"):
            out.append("<br>")
    out.append(escape(text[pos:], quote=False))
    return "".join(out)


_LIST = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d{1,9}[.)])\s+(?P<text>.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)\s*([^`\s]*)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _render_list(lines: list[str]) -> str:
    """Render consecutive list lines (with nesting by indentation)."""
    html: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for line in lines:
        m = _LIST.match(line)
        if not m:  # continuation line
            if html and html[-1].endswith("</li>"):
                html[-1] = html[-1][:-5] + " " + _inline(line.strip()) + "</li>"
            continue
        indent = len(m.group("indent").expandtabs(4))
        tag = "ol" if m.group("marker")[0].isdigit() else "ul"
        while stack and indent < stack[-1][0]:
            html.append(f"</{stack.pop()[1]}>")
            if html[-2:-1] and html[-2].endswith("</li>") is False:
                pass
        if not stack or indent > stack[-1][0]:
            if stack and html and html[-1].endswith("</li>"):
                html[-1] = html[-1][:-5]  # nest inside the previous item
                stack.append((indent, tag))
                html.append(f"<{tag}>")
            else:
                stack.append((indent, tag))
                html.append(f"<{tag}>")
        html.append(f"<li>{_inline(m.group('text'))}</li>")
    while stack:
        indent, tag = stack.pop()
        html.append(f"</{tag}>")
        if stack:
            html.append("</li>")
    return "".join(html)


def render_markdown(source: str) -> str:
    """Convert the safe Markdown subset to an HTML fragment."""
    text = (source or "")[:MAX_SOURCE].replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(chr(10).join(paragraph))}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            marker, lang = fence.group(1), fence.group(2)
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                body.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{escape(lang)}"' if lang and _LANG.match(lang) else ""
            out.append(f"<pre><code{cls}>{escape(chr(10).join(body), quote=False)}</code></pre>")
            continue
        if not line.strip():
            flush_paragraph()
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if _RULE.match(line):
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            flush_paragraph()
            quoted: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{render_markdown(chr(10).join(quoted))}</blockquote>")
            continue
        if _LIST.match(line) and not paragraph:
            block: list[str] = []
            while i < len(lines) and lines[i].strip() and (_LIST.match(lines[i]) or lines[i].startswith((" ", "\t"))):
                block.append(lines[i])
                i += 1
            out.append(_render_list(block))
            continue
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]) and not paragraph:
            header = _cells(line)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            head = "".join(f"<th>{_inline(c)}</th>" for c in header)
            body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row[:len(header)]) + "</tr>"
                           for row in rows)
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        paragraph.append(line)
        i += 1
    flush_paragraph()
    return "".join(out)


class Markdown(Component):
    """Rendered Markdown (safe subset). ``source`` may be reactive."""

    kind = "Markdown"

    def __init__(self, source: Any, **kw: Any):
        self._html_cache = ""
        super().__init__(**kw)
        self._bind(source, self._set, "source")

    def _build(self) -> Element:
        return Element("div", self, cls="u4-md")

    def _set(self, source: Any) -> None:
        html = render_markdown("" if source is None else str(source))
        if html == self._html_cache:
            return
        self._html_cache = html
        self.root.set_html(html)


class CodeBlock(Component):
    """Literal monospace code."""

    kind = "Code"

    def __init__(self, source: Any, *, language: str | None = None, **kw: Any):
        self._language = language
        super().__init__(**kw)
        self._bind(source, lambda v: self.code.set_text(v), "source")

    def _build(self) -> Element:
        root = Element("div", self, cls="u4-md")
        pre = Element("pre", self)
        cls = f"language-{self._language}" if self._language and _LANG.match(self._language) else None
        self.code = Element("code", self, cls=cls)
        pre.add(self.code)
        root.add(pre)
        return root
