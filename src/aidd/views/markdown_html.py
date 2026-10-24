"""Markdown as escaped HTML, for the parts of a view that come from a Markdown file: headings, lists, code, links shown as text, and a mermaid fence as its source."""

from __future__ import annotations

import re

from aidd.kernel import documents
from aidd.views import html_parts

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)")
_MD_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LIST = re.compile(r"^[ \t]*(?:([-*+])|(\d+)[.)])[ \t]+(.*)$")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)]*)\)")


def inline(text: str) -> html_parts.Html:
    """Code spans and bold, on escaped text. A link keeps its text and shows its target as text, never as an href."""
    out = []
    pos = 0
    for m in _CODE_SPAN.finditer(text):
        out.append(_plain(text[pos : m.start()]))
        out.append(str(html_parts.el("code", m.group(2).strip())))
        pos = m.end()
    out.append(_plain(text[pos:]))
    return html_parts.Html("".join(out))


def _plain(text: str) -> str:
    text = _LINK.sub(lambda m: m.group(1) + (f" ({m.group(2)})" if m.group(2) and m.group(2) != m.group(1) else ""), text)
    return _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", str(html_parts.esc(text)))


def mermaid_blocks(text: str) -> list[str]:
    """The source of each ```mermaid fence in a Markdown text."""
    found, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        fence, lang, j = m.group(1), m.group(2).lower(), i + 1
        while j < len(lines) and not lines[j].strip().startswith(fence):
            j += 1
        if lang == "mermaid":
            found.append("\n".join(lines[i + 1 : j]))
        i = j + 1
    return found


def md(text: str, *, top: int = 3) -> html_parts.Html:
    """Markdown as HTML, escaped: headings start at h`top`; a mermaid fence becomes its source with a note."""
    lines = documents._HTML_COMMENT.sub("", text).splitlines()
    out: list[html_parts.Html] = []
    para: list[str] = []
    items: list[tuple[bool, str]] = []
    rows: list[list[str]] = []
    quote: list[str] = []

    def flush() -> None:
        if para:
            out.append(html_parts.el("p", inline(" ".join(s.strip() for s in para))))
            para.clear()
        if items:
            tag = "ol" if items[0][0] else "ul"
            out.append(html_parts.el(tag, [html_parts.el("li", inline(t)) for _, t in items]))
            items.clear()
        if rows:
            head, *rest = rows
            out.append(
                html_parts.el(
                    "div",
                    html_parts.el(
                        "table",
                        html_parts.el("thead", html_parts.el("tr", [html_parts.el("th", inline(c), scope="col") for c in head])),
                        html_parts.el("tbody", [html_parts.el("tr", [html_parts.el("td", inline(c)) for c in r]) for r in rest]),
                    ),
                    class_="scroll",
                )
            )
            rows.clear()
        if quote:
            out.append(html_parts.el("blockquote", html_parts.el("p", inline(" ".join(quote)))))
            quote.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _FENCE.match(ln)
        if m:
            flush()
            fence, lang, j = m.group(1), m.group(2).lower(), i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                j += 1
            body = "\n".join(lines[i + 1 : j])
            out.append(html_parts.diagram(body) if lang == "mermaid" else html_parts.el("pre", html_parts.el("code", body)))
            i = j + 1
            continue
        stripped = ln.strip()
        if not stripped:
            flush()
        elif h := _MD_HEADING.match(stripped):
            flush()
            out.append(html_parts.el(f"h{min(len(h.group(1)) + top - 1, 6)}", inline(h.group(2))))
        elif stripped.startswith("|"):
            if para or items or quote:
                flush()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{1,}:?", c) for c in cells if c) or not any(cells):
                rows.append(cells)
        elif stripped.startswith(">"):
            if para or items or rows:
                flush()
            quote.append(stripped.lstrip(">").strip())
        elif lm := _LIST.match(ln):
            if para or rows or quote:
                flush()
            items.append((lm.group(2) is not None, lm.group(3)))
        elif items and ln.startswith((" ", "\t")):
            ordered, t = items[-1]
            items[-1] = (ordered, t + " " + stripped)
        else:
            if items or rows or quote:
                flush()
            para.append(ln)
        i += 1
    flush()
    return html_parts.join(out)
