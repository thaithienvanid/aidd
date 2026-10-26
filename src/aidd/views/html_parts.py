"""The parts every view is built from: escaped markup (`el`), one self-contained page under a strict Content-Security-Policy, and the small blocks pages share (facts, tables, badges, diffs)."""

from __future__ import annotations

import base64
import hashlib
import html
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from aidd import config

# Where a page goes unless --out or a PATH says otherwise: aidd's output in .aidd/, which the repository git-ignores.
VIEWS_DIR = Path(config.VIEWS_DIR)

MAX_DIFF_LINES = 2000  # per file
MAX_DIFF_CHARS = 1_000_000  # per page
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


# The only script: it reveals the copy buttons and copies the text a button names. Without it (or with scripts off),
# the buttons stay hidden and the text stays selectable. Its hash is pinned in the page's CSP.
COPY_SCRIPT = (
    'document.querySelectorAll("button[data-copy]").forEach(function(b){b.hidden=false;'
    'b.addEventListener("click",function(){var t=document.getElementById(b.getAttribute("data-copy"));'
    "if(!t||!navigator.clipboard){return;}navigator.clipboard.writeText(t.textContent).then(function(){"
    'b.textContent="Copied";setTimeout(function(){b.textContent="Copy";},1500);});});});'
)
SCRIPT_HASH = "sha256-" + base64.b64encode(hashlib.sha256(COPY_SCRIPT.encode("utf-8")).digest()).decode("ascii")
CSP = f"default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src '{SCRIPT_HASH}'; base-uri 'none'; form-action 'none'"

# Light and dark from the system setting; every pair meets WCAG AA contrast (4.5:1 for text) in both.
STYLE = """
:root{color-scheme:light dark;--bg:#ffffff;--fg:#1f2328;--muted:#57606a;--border:#d0d7de;--panel:#f6f8fa;--accent:#0a58c2;
--pass-bg:#dafbe1;--pass-fg:#0f5323;--fail-bg:#ffebe9;--fail-fg:#82071e;--pending-bg:#fff8c5;--pending-fg:#5c4200;
--warn-bg:#fff1e5;--warn-fg:#7a3300;--add-bg:#e6ffec;--del-bg:#ffebe9;--hunk:#0a58c2}
@media (prefers-color-scheme: dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9da7b3;--border:#3d444d;--panel:#161b22;--accent:#79b8ff;
--pass-bg:#0f2e1a;--pass-fg:#7ee2a8;--fail-bg:#3d1214;--fail-fg:#ffb3ae;--pending-bg:#2e2600;--pending-fg:#f2cc60;
--warn-bg:#331c00;--warn-fg:#ffb77a;--add-bg:#12261e;--del-bg:#2d1214;--hunk:#79b8ff}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:72rem;margin:0 auto;padding:1rem}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.skip{position:absolute;left:-999px}.skip:focus{left:1rem;top:1rem;background:var(--bg);padding:.5rem;z-index:1}
header{border-bottom:1px solid var(--border);margin-bottom:1rem}
h1{font-size:1.6rem;line-height:1.25;margin:.5rem 0;overflow-wrap:anywhere}
h2{font-size:1.25rem;margin:2rem 0 .5rem;padding-bottom:.25rem;border-bottom:1px solid var(--border)}
h3{font-size:1.05rem;margin:1.25rem 0 .5rem}
h4,h5,h6{font-size:1rem;margin:1rem 0 .25rem}
p,li,dd{overflow-wrap:anywhere}td,th{overflow-wrap:break-word}
.lead{color:var(--muted);margin:.25rem 0 1rem}
nav ol{display:flex;flex-wrap:wrap;gap:.25rem 1rem;padding:0;margin:0 0 1rem;list-style:none}
.badge{display:inline-block;white-space:nowrap;padding:.1rem .5rem;border-radius:1rem;font-weight:600;font-size:.9rem;border:1px solid currentColor}
.pass{background:var(--pass-bg);color:var(--pass-fg)}.fail{background:var(--fail-bg);color:var(--fail-fg)}
.pending{background:var(--pending-bg);color:var(--pending-fg)}.warn{background:var(--warn-bg);color:var(--warn-fg)}
.box{background:var(--panel);border:1px solid var(--border);border-radius:.5rem;padding:.75rem 1rem;margin:.75rem 0}
.muted{color:var(--muted)}
dl.facts{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1rem;margin:.5rem 0}
dl.facts dt{font-weight:600}dl.facts dd{margin:0;min-width:0}
@media (max-width:40rem){dl.facts{grid-template-columns:1fr;gap:0}dl.facts dd{margin-bottom:.5rem}}
.scroll{overflow-x:auto;max-width:100%}.scroll>table{min-width:36rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{border:1px solid var(--border);padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:var(--panel)}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.875rem}
pre{background:var(--panel);border:1px solid var(--border);border-radius:.375rem;padding:.75rem;overflow-x:auto;white-space:pre;margin:.5rem 0}
.diff span{display:block}.diff .add{background:var(--add-bg)}.diff .del{background:var(--del-bg)}.diff .hunk{color:var(--hunk)}
details{border:1px solid var(--border);border-radius:.375rem;padding:.25rem .75rem;margin:.5rem 0}
summary{cursor:pointer;font-weight:600;padding:.25rem 0;overflow-wrap:anywhere}
.diagram figcaption{color:var(--muted);font-size:.875rem}
figure{margin:.5rem 0}
img{max-width:100%;height:auto;border:1px solid var(--border)}
.copyline{display:flex;gap:.5rem;align-items:flex-start;flex-wrap:wrap}.copyline pre{flex:1 1 20rem;margin:0;user-select:all}
button{font:inherit;padding:.35rem .75rem;border:1px solid var(--border);border-radius:.375rem;background:var(--panel);color:var(--fg);cursor:pointer}
ul.findings{padding-left:1.25rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));gap:1rem;align-items:start}
.cards>article{background:var(--panel);border:1px solid var(--border);border-radius:.5rem;padding:.25rem 1rem .75rem;min-width:0}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr));gap:.75rem}
footer{border-top:1px solid var(--border);margin-top:2rem;padding-top:.5rem;color:var(--muted);font-size:.875rem}
@media print{nav,.skip,button{display:none!important}body{font-size:11pt}.wrap{max-width:none}
details>*{display:block!important}details::details-content{content-visibility:visible;display:contents}
pre{white-space:pre-wrap}a{color:inherit}h2{break-after:avoid}tr,img{break-inside:avoid}}
""".strip()


def page(title: str, sections: list[Section], *, lead: object = "", badge: Html | None = None, footer: str = "") -> str:
    """One whole page: the title, a table of contents, and each section with its anchor."""
    toc = el("nav", el("ol", [el("li", el("a", s.title, href=f"#{s.id}")) for s in sections]), aria_label="On this page")
    body = el(
        "div",
        el("a", "Skip to the content", href="#main", class_="skip"),
        el("header", el("h1", title), badge or "", el("p", lead, class_="lead") if lead else "", toc),
        el("main", [el("section", el("h2", s.title), s.body, id=s.id, aria_labelledby=None) for s in sections], id="main"),
        el("footer", el("p", footer or "Rendered by aidd from the repository's text. A view for people: it is never evidence, and it never approves.")),
        class_="wrap",
    )
    return (
        "<!DOCTYPE html>\n"
        + '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        + f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">\n'
        + '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + '<meta name="referrer" content="no-referrer">\n'
        + f"<title>{esc(title)}</title>\n<style>\n{STYLE}\n</style>\n</head>\n<body>\n"
        + body
        + f"\n<script>{COPY_SCRIPT}</script>\n</body>\n</html>\n"
    )


def write(path: Path | str, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def copyable(ident: str, text: str) -> Html:
    """Text to copy, always visible and selectable; the Copy button appears only when the pinned script runs."""
    return el("div", el("pre", text, id=ident), el("button", "Copy", type="button", class_="copy", data_copy=ident, hidden=True), class_="copyline")


def facts(rows: Sequence[tuple[str, object]]) -> Html:
    return el("dl", [join(el("dt", k), el("dd", v)) for k, v in rows if v not in (None, "", [])], class_="facts")


def table(headers: list[str], rows: Sequence[Sequence[object]], *, label: str) -> Html:
    head = el("thead", el("tr", [el("th", h, scope="col") for h in headers]))
    body = el("tbody", [el("tr", [el("td", c) for c in row]) for row in rows])
    return el("div", el("table", el("caption", label, class_="muted"), head, body), class_="scroll")


def badge(level: str, text: str | None = None) -> Html:
    return el("span", text or level.upper(), class_=f"badge {level}")


def code_list(items: list[str]) -> Html:
    return join([join(el("code", x), ", " if i < len(items) - 1 else "") for i, x in enumerate(items)]) if items else Html("none")


def diagram(source: str) -> Html:
    return el("figure", el("pre", source.rstrip("\n")), el("figcaption", MERMAID_NOTE), class_="diagram")


def diff_block(text: str, *, max_lines: int = MAX_DIFF_LINES) -> Html:
    lines = text.splitlines()
    shown = lines[:max_lines]
    spans = []
    for ln in shown:
        kind = (
            "meta"
            if ln.startswith(("+++", "---", "diff ", "index "))
            else "add"
            if ln.startswith("+")
            else "del"
            if ln.startswith("-")
            else "hunk"
            if ln.startswith("@@")
            else None
        )
        spans.append(el("span", ln or " ", class_=kind))
    more = el("p", f"… {len(lines) - max_lines} more line(s); see the full diff with git", class_="muted") if len(lines) > max_lines else ""
    return join(el("pre", spans, class_="diff"), more)


def default_path(kind: str, name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "page"
    return VIEWS_DIR / f"{kind}-{safe}.html"
