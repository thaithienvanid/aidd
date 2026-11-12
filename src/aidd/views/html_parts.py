"""The parts every view is built from: escaped markup (`el`), one self-contained page on the design system under a strict Content-Security-Policy, and the small blocks pages share (facts, tables, code lists, diagrams)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.views.design_tokens import system_css

# Where a page goes unless --out or a PATH says otherwise: aidd's output in .aidd/, which the repository git-ignores.
VIEWS_DIR = Path(config.VIEWS_DIR)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MERMAID_NOTE = "Mermaid source. The page loads nothing from anywhere, so the diagram shows as its source; paste it into any Mermaid viewer to draw it."


class Html(str):
    """Markup that is already safe: built by `el` from escaped parts. Anything else is text and gets escaped."""


def esc(value: object) -> Html:
    return Html(html.escape(str(value), quote=True))


def _children(parts) -> str:
    out = []
    for p in parts:
        if p is None or p is False:
            continue
        if isinstance(p, Html):
            out.append(str(p))
        elif isinstance(p, list | tuple):
            out.append(_children(p))
        else:
            out.append(str(esc(p)))
    return "".join(out)


_VOID = {"meta", "img", "br", "hr"}


def el(tag: str, *children, **attrs) -> Html:
    """<tag attrs>children</tag>. Attribute names come from code (`class_` is `class`, `aria_label` is `aria-label`);
    attribute values and text children are escaped; a child that is `Html` goes in as it is."""
    parts = [tag]
    for key in sorted(attrs):
        value = attrs[key]
        if value is None or value is False:
            continue
        name = key.rstrip("_").replace("_", "-")
        parts.append(name if value is True else f'{name}="{esc(value)}"')
    opening = "<" + " ".join(parts) + ">"
    if tag in _VOID:
        return Html(opening)
    return Html(f"{opening}{_children(children)}</{tag}>")


def join(*parts) -> Html:
    return Html(_children(parts))


@dataclass
class Section:
    id: str
    title: str
    body: Html
    count: int | None = None  # shown beside the title, in the heading and the table of contents


def csp_hash(text: str) -> str:
    """A Content-Security-Policy source for one inline block: its SHA-256, so the policy allows that block and no other."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


def page_style(own: str) -> str:
    """A page's one style block: the design system's CSS, then the page's own layout, which adds no component."""
    style = system_css() + own
    if "</style" in style.lower():
        raise ValueError("the page's style holds </style, which would end its style block: fix tokens.json or the page's CSS")
    return style


def utc_offset(now: dt.datetime) -> str:
    """The offset the page's times are in, said once in each foot: `UTC`, `UTC+9`, or `UTC+5:30`."""
    seconds = int((now.astimezone().utcoffset() or dt.timedelta()).total_seconds())
    if not seconds:
        return "UTC"
    hours, minutes = divmod(abs(seconds) // 60, 60)
    return f"UTC{'+' if seconds > 0 else '-'}{hours}" + (f":{minutes:02d}" if minutes else "")


def written_texts(now: dt.datetime) -> tuple[str, str]:
    """When a page was written, short for the top bar and long for the foot."""
    return f"{now.day} {now:%b}, {now:%H:%M}", f"{now.day} {now:%b %Y} at {now:%H:%M}"


FOOT = "Rendered by aidd from the repository's text. A view for people: it is never evidence, and it never approves."


def page(
    title: str,
    sections: list[Section],
    *,
    lead: object = "",
    flag: Html | None = None,
    note: object = "",
    style: str = "",
    product: str = "aidd",
    page_type: str = "",
    written: dt.datetime | None = None,
    latest: str = "",
    icons: Html | None = None,
) -> str:
    """One page that only reads, on the design system: the top bar with the product, what the page is (`page_type`), and
    when it was written; the title with its flag, lead, and table of contents; each section with its anchor; and the foot,
    which names the command that writes the page again (`latest`). Its one style block is the system's CSS, then `style`,
    the page's own layout; the Content-Security-Policy names that block by hash and runs no script. `icons` is the sprite
    its flags draw from, drawn once."""

    def counted(section: Section) -> Html:
        return join(section.title, " ", el("span", section.count, class_="count")) if section.count is not None else esc(section.title)

    short, long_ = written_texts(written) if written else ("", "")
    toc = el("nav", el("ol", [el("li", el("a", counted(s), href=f"#{s.id}", class_="link")) for s in sections]), class_="toc", aria_label="On this page")
    head = el(
        "header",
        el("p", flag) if flag else "",
        el("h1", title, dir="auto"),
        el("p", lead, class_="lead prose") if lead else "",
        el("p", note, class_="muted prose") if note else "",
        toc,
        class_="page-head",
    )
    sections_html = [
        el("section", el("h2", counted(s), id=f"{s.id}-title"), s.body, id=s.id, class_="section", aria_labelledby=f"{s.id}-title") for s in sections
    ]
    when = el("p", f"Written {long_}. Times are in {utc_offset(written)}. Run ", el("code", latest), " for the latest.") if written and latest else ""
    body = (icons or "") + el(
        "div",
        el("a", "Skip to the content", href="#main", class_="skip"),
        el(
            "header",
            el(
                "p",
                el("b", product, dir="auto"),
                el("span", page_type) if page_type else "",
                el("span", f"Written {short}") if short else "",
                class_="topbar-name",
            ),
            class_="topbar",
        ),
        el("main", head, sections_html, id="main", class_="page page-wide"),
        el("footer", when, el("p", FOOT), class_="foot"),
        class_="shell",
    )
    return document(f"{page_type}: {title}" if page_type else title, page_style(style), body)


def document(title: str, css: str, body: str) -> str:
    """The whole file of a page that runs no script: its one style block, named by hash in its Content-Security-Policy."""
    policy = f"default-src 'none'; style-src {csp_hash(css)}; img-src data:; script-src 'none'; base-uri 'none'; form-action 'none'"
    return (
        "<!doctype html>\n"
        + '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        + f'<meta http-equiv="Content-Security-Policy" content="{esc(policy)}">\n'
        + '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + '<meta name="referrer" content="no-referrer">\n'
        + f"<title>{esc(title)}</title>\n<style>{css}</style>\n</head>\n<body>\n"
        + body
        + "\n</body>\n</html>\n"
    )


def write(path: Path | str, text: str) -> Path:
    """Write a page, never through a link. A committed link at a folder on the way (`.aidd/views` -> elsewhere) is
    refused, and the page goes to a new file renamed over the target, so a link there is replaced, never followed."""
    p = Path(path)
    if not p.is_absolute():
        for i in range(1, len(p.parent.parts) + 1):
            if (step := Path(*p.parent.parts[:i])).is_symlink():
                raise ValueError(f"{step.as_posix()} is a link: aidd writes pages only into a real folder; remove the link and run again")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


def facts(rows: Sequence[tuple[str, object]]) -> Html:
    return el("dl", [join(el("dt", k), el("dd", v)) for k, v in rows if v not in (None, "", [])], class_="facts")


def table(headers: list[str], rows: Sequence[Sequence[object]], *, label: str) -> Html:
    head = el("thead", el("tr", [el("th", h, scope="col") for h in headers]))
    body = el("tbody", [el("tr", [el("td", c) for c in row]) for row in rows])
    return el("div", el("table", el("caption", label), head, body, class_="table"), class_="table-wrap")


def code_list(items: list[str]) -> Html:
    return join([join(el("code", x), ", " if i < len(items) - 1 else "") for i, x in enumerate(items)]) if items else Html("none")


def diagram(source: str) -> Html:
    return el("figure", el("pre", source.rstrip("\n")), el("figcaption", MERMAID_NOTE), class_="diagram")


def default_path(page_type: str, name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "page"
    return VIEWS_DIR / f"{page_type}-{safe}.html"
