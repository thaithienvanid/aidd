"""Human views: what a person reads to decide, as one self-contained HTML page each.

Sources stay text (the Spec, its tests and docs, the config, the evidence); a view is rendered from them by aidd,
deterministically, with no model. Two pages here: the Spec approval page (`aidd hash --html`) and the Merge approval
page (`aidd gate --html`), which holds the verification and what the verifier recorded for the head
(`<evidence>/preview/<head_sha>/artifacts.json`); an exploration's comparison page (`aidd explore`, in explore.py) and
the client status (`aidd digest --client --html`, in rollup.py) are built from the same parts.

A view is never evidence and never approves: it holds no form, its only buttons copy text, and the gate never reads
it (no module the decision is computed in imports this one). Every string from the repository is escaped, because an
agent wrote most of them. The page loads nothing: a strict Content-Security-Policy allows inline styles, `data:`
images, and one hash-pinned inline script that only turns the copy buttons on. Mermaid diagrams show as their source.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import model, schema
from .util import red_ok

# Where a page goes unless --out or a PATH says otherwise: beside the evidence, which the repository git-ignores.
VIEWS_DIR = Path("aidd-evidence") / "views"

MAX_DIFF_LINES = 2000  # per file
MAX_DIFF_CHARS = 1_000_000  # per page
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
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


# ---- building blocks ----


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


# ---- a small, safe Markdown subset: headings, paragraphs, lists, tables, quotes, code; never a link or raw HTML ----

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)")
_MD_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_LIST = re.compile(r"^[ \t]*(?:([-*+])|(\d+)[.)])[ \t]+(.*)$")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)]*)\)")


def inline(text: str) -> Html:
    """Code spans and bold, on escaped text. A link keeps its text and shows its target as text, never as an href."""
    out = []
    pos = 0
    for m in _CODE_SPAN.finditer(text):
        out.append(_plain(text[pos : m.start()]))
        out.append(str(el("code", m.group(2).strip())))
        pos = m.end()
    out.append(_plain(text[pos:]))
    return Html("".join(out))


def _plain(text: str) -> str:
    text = _LINK.sub(lambda m: m.group(1) + (f" ({m.group(2)})" if m.group(2) and m.group(2) != m.group(1) else ""), text)
    return _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", str(esc(text)))


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


def md(text: str, *, top: int = 3) -> Html:
    """Markdown as HTML, escaped: headings start at h`top`; a mermaid fence becomes its source with a note."""
    lines = model._HTML_COMMENT.sub("", text).splitlines()
    out: list[Html] = []
    para: list[str] = []
    items: list[tuple[bool, str]] = []
    rows: list[list[str]] = []
    quote: list[str] = []

    def flush() -> None:
        if para:
            out.append(el("p", inline(" ".join(s.strip() for s in para))))
            para.clear()
        if items:
            tag = "ol" if items[0][0] else "ul"
            out.append(el(tag, [el("li", inline(t)) for _, t in items]))
            items.clear()
        if rows:
            head, *rest = rows
            out.append(
                el(
                    "div",
                    el(
                        "table",
                        el("thead", el("tr", [el("th", inline(c), scope="col") for c in head])),
                        el("tbody", [el("tr", [el("td", inline(c)) for c in r]) for r in rest]),
                    ),
                    class_="scroll",
                )
            )
            rows.clear()
        if quote:
            out.append(el("blockquote", el("p", inline(" ".join(quote)))))
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
            out.append(diagram(body) if lang == "mermaid" else el("pre", el("code", body)))
            i = j + 1
            continue
        stripped = ln.strip()
        if not stripped:
            flush()
        elif h := _MD_HEADING.match(stripped):
            flush()
            out.append(el(f"h{min(len(h.group(1)) + top - 1, 6)}", inline(h.group(2))))
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
    return join(out)


# ---- shared parts ----


def _acceptance(body: str) -> list[tuple[str, str]]:
    from . import digest

    return digest.acceptance(body)


def _cmd(command) -> str:
    return shlex.join(str(c) for c in command) if isinstance(command, list) else str(command or "")


def _result_text(r: dict | None) -> Html:
    if not r:
        return Html("no result")
    exit_code = r.get("exit")
    if r.get("red_green") == "red":
        level = "pass" if red_ok(r) else "fail"
        text = "fails on base, as it should" if red_ok(r) else f"{r.get('status')} on base"
    else:
        level = "pass" if r.get("status") == "passed" else "fail"
        text = str(r.get("status"))
    flaky = " (flaky: passed on a retry)" if r.get("flaky") else ""
    return join(badge(level, text), f" exit {exit_code}{flaky}")


def _safe_artifact(evidence_dir: Path | None, rel: str) -> tuple[Path | None, str]:
    """The artifact's file when it is inside the evidence folder, or why not."""
    if evidence_dir is None:
        return None, "not embedded: the evidence folder is not here"
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts or re.match(r"^[A-Za-z]:", rel):
        return None, "not embedded: the path leaves the evidence folder"
    root = evidence_dir.resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        return None, "not embedded: the path leaves the evidence folder"
    if not p.is_file():
        return None, "not embedded: the file is not in the evidence folder here"
    return p, ""


def artifact_figure(a: dict, evidence_dir: Path | None) -> Html:
    """One recorded artifact: a screenshot embedded as a data: image when it is here and its SHA-256 matches, else its
    path and hash."""
    rel, kind, sha = str(a.get("path", "")), str(a.get("kind", "")), str(a.get("sha256", ""))
    caption = el("figcaption", el("code", rel), f" ({kind}) sha256 {sha[:16]}…")
    p, why = _safe_artifact(evidence_dir, rel)
    img: Html | str = ""
    if p is not None:
        mime = IMAGE_TYPES.get(p.suffix.lower())
        size = p.stat().st_size
        if kind != "screenshot" or mime is None:
            why = "not embedded: only screenshots (PNG, JPEG, GIF, WebP) are"
        elif size > MAX_IMAGE_BYTES:
            why = f"not embedded: larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB"
        else:
            data = p.read_bytes()
            if hashlib.sha256(data).hexdigest() != sha:
                why = "not embedded: its SHA-256 does not match what the verifier recorded"
            else:
                img = el("img", src=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", alt=f"{kind} {rel}", loading="lazy")
    return el("figure", img, caption, el("p", why, class_="muted") if why else "")


def preview_artifacts(evidence_dir: Path | None, head_sha: object) -> list[dict]:
    """What the verifier recorded for this head: `<evidence>/preview/<head_sha>/artifacts.json` (schemas/artifacts.schema.json),
    or nothing when it is missing, unreadable, or not in that shape."""
    if evidence_dir is None or not re.fullmatch(r"[0-9a-f]{7,64}", str(head_sha or "")):
        return []
    try:
        items = json.loads((evidence_dir / "preview" / str(head_sha) / "artifacts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(items) if not schema.validate(items, "artifacts.schema.json") else []


def _artifacts_for(artifacts: list[dict], ident: str) -> list[dict]:
    """The artifacts a verifier named for an Acceptance id: a file name that starts with it, such as a1-checkout.png."""
    pat = re.compile(rf"^{re.escape(ident.lower())}(?:[-_.]|$)")
    return [a for a in artifacts if pat.match(Path(str(a.get("path", ""))).name.lower())]


def _spec_parts(text: str | None, path: str) -> tuple[dict, str]:
    if not text:
        return {}, ""
    try:
        return model.split_front_matter(text, path)
    except model.ModelError:
        return {}, ""


def acceptance_rows(items: list[tuple[str, str]], cmds: list[dict], evidence: dict | None, evidence_dir: Path | None, *, artifacts: bool = True) -> list[list]:
    results = (evidence or {}).get("results") or []
    green = {r.get("name"): r for r in results if r.get("red_green") == "green"}
    red = {r.get("name"): r for r in results if r.get("red_green") == "red"}
    arts = preview_artifacts(evidence_dir, (evidence or {}).get("head_sha")) if artifacts else []
    rows = []
    for ident, text in items:
        by = [c for c in cmds if ident and ident in (c.get("covers") or [])]
        names = [str(c.get("name")) for c in by]
        row: list = [el("strong", ident or "-"), text, code_list(names) if names else badge("fail", "nothing covers it")]
        if evidence is not None:
            row.append(
                join(
                    [
                        join(el("div", el("code", n), " ", _result_text(red.get(n))))
                        for n in names
                        if any(c.get("new_behavior") for c in by if c.get("name") == n)
                    ]
                )
                or "-"
            )
            row.append(join([el("div", el("code", n), " ", _result_text(green.get(n))) for n in names]) or "-")
            if artifacts:
                row.append(join([artifact_figure(a, evidence_dir) for a in _artifacts_for(arts, ident)]) or "-")
        rows.append(row)
    return rows


def results_table(evidence: dict) -> Html:
    rows = []
    for r in evidence.get("results") or []:
        attempts = r.get("attempts") or []
        rows.append(
            [
                r.get("red_green"),
                el("code", r.get("name")),
                r.get("source", ""),
                el("code", _cmd(r.get("command"))),
                _result_text(r),
                "" if r.get("duration_seconds") is None else f"{r['duration_seconds']}",
                f"{len(attempts)} attempt(s)" if attempts else "",
                el("code", r.get("log")) if r.get("log") else "",
            ]
        )
    return table(["Phase", "Command", "Source", "Runs", "Result", "Seconds", "Retries", "Log"], rows, label="Every result, as the runner recorded it")


def verification_section(evidence: dict | None, data: dict, body: str, evidence_dir: Path | None, *, stale: str = "") -> Html:
    if evidence is None:
        return el("p", stale or "No evidence for this head: run `aidd test`.", class_="muted")
    runner = evidence.get("runner") or {}
    flags = [
        ("Head", el("code", evidence.get("head_sha", ""))),
        ("Base", el("code", evidence.get("base_sha", ""))),
        ("Runner", " ".join(f"{k} {runner[k]}" for k in ("ci", "run_id", "url") if runner.get(k))),
        ("Partial", "yes: only the commands the working tree's changes select; the gate never accepts it" if evidence.get("partial") else ""),
        ("Spec phase", "yes: failing green results are expected before Implement" if evidence.get("spec_phase") else ""),
    ]
    parts: list = [facts(flags)]
    items = _acceptance(body) if body else []
    cmds = ((data.get("tests") or {}).get("commands")) or []
    if items and items[0][0]:
        parts.append(el("h3", "Acceptance, command by command"))
        parts.append(
            table(
                ["Id", "Acceptance", "Proven by", "Red on base", "Green on head", "Recorded"],
                acceptance_rows(items, cmds, evidence, evidence_dir),
                label="Each Acceptance item, the commands that cover it, their results, and what the verifier recorded",
            )
        )
    parts.append(el("h3", "Results"))
    parts.append(results_table(evidence))
    arts = preview_artifacts(evidence_dir, evidence.get("head_sha"))
    if arts:
        parts.append(el("h3", "Recorded while verifying"))
        parts.append(
            el("p", "Screenshots, traces, videos, and transcripts the verifier recorded on this head. For people: the gate never reads them.", class_="muted")
        )
        parts.append(join([artifact_figure(a, evidence_dir) for a in sorted(arts, key=lambda a: str(a.get("path")))]))
    return join(parts)


# ---- the Spec approval page ----


def spec_page(
    text: str,
    path: str,
    line: str,
    *,
    files: dict[str, str] | None = None,
    spec_hash: str = "",
    commit: str = "",
    route: dict | None = None,
    since: dict | None = None,
) -> str:
    """What an Approver reads before posting the approval line: the intent, Acceptance against the tests that cover it,
    the route and why, the risk and rollback, each frozen file and doc, the diagrams, what changed since the last
    approval (`since`: commit, stat, diff), and the line itself to copy."""
    files = files or {}
    data, body = model.split_front_matter(text, path)
    risk = data.get("risk") or {}
    tests = data.get("tests") or {}
    cmds = tests.get("commands") or []
    sid = str(data.get("id", ""))
    sections: list[Section] = []

    approve = [
        el("p", "Read this page, then approve by posting this line as a comment on the pull request:"),
        copyable("approval-line", line),
        el("p", "Without a platform, run this at your own terminal instead; it asks you to type back a one-time code:", class_="muted"),
        copyable("approve-local", f"aidd approve spec {path}"),
        el(
            "p",
            "This page never approves: its buttons only copy text. The hash covers the Spec, its test files, its design files, and its frozen docs; "
            "changing any of them voids the approval.",
            class_="muted",
        ),
    ]
    sections.append(
        Section(
            "approve", "What you approve", join(facts([("Spec", el("code", path)), ("Hash", el("code", spec_hash)), ("Commit", el("code", commit))]), approve)
        )
    )

    intent, intent_name = "", "Intent"
    for name in ("Intent", "Problem", "Context"):
        found = _section_raw(body, name)
        if found:
            intent, intent_name = found, name
            break
    sections.append(Section("intent", intent_name, md(intent) if intent else el("p", "The Spec has no Intent, Problem, or Context section.", class_="muted")))

    items = _acceptance(body)
    if items and items[0][0]:
        acc = table(
            ["Id", "Acceptance", "Proven by"],
            acceptance_rows(items, cmds, None, None),
            label="Each Acceptance item and the test commands that list it in covers",
        )
    else:
        acc = join(
            el("p", "The Acceptance items carry no ids (A1, A2, …), so no command can say which it proves.", class_="muted"),
            md(_section_raw(body, "Acceptance")),
        )
    cmd_rows = [
        [
            el("code", c.get("name")),
            el("code", _cmd(c.get("command"))),
            "yes: must fail on base first" if c.get("new_behavior") else "no",
            code_list(list(c.get("covers") or [])),
        ]
        for c in cmds
    ]
    acc = join(
        acc,
        el("h3", "Test commands"),
        table(["Name", "Runs", "New behavior", "Covers"], cmd_rows, label="The Spec's test commands") if cmd_rows else el("p", "none", class_="muted"),
    )
    sections.append(Section("acceptance", "Acceptance and tests", acc))

    route_rows = [
        ("Declared route", el("strong", data.get("route", ""))),
        ("Type", data.get("type")),
        ("Confidence", data.get("confidence")),
        ("Dimensions", ", ".join(risk.get("dimensions") or []) or "none declared"),
    ]
    route_body: list = [facts(route_rows)]
    if route:
        route_body.append(el("p", f"From the Spec's scope, the rules compute at least {route.get('route')} ({route.get('lane')} lane), because:"))
        route_body.append(
            el("ul", [el("li", r) for r in route.get("reasons") or ["no risk rule, protected path, or declared risk raised it: the minimum is minor"]])
        )
        route_body.append(el("p", "The gate computes the route again from the real diff, and can only raise it.", class_="muted"))
    sections.append(Section("route", "Route", join(route_body)))

    task_rows = [
        [el("code", t.get("id")), t.get("title", ""), code_list(list(t.get("scope") or [])), ", ".join(t.get("depends_on") or []) or "-"]
        for t in data.get("tasks") or []
    ]
    sections.append(
        Section(
            "risk",
            "Risk, rollback, and scope",
            join(
                facts(
                    [
                        ("Risk", risk.get("summary", "")),
                        ("Reversible", "yes" if risk.get("reversible", True) else "NO: irreversible"),
                        ("Rollback", data.get("rollback", "")),
                        ("Residual risk", data.get("residual_risk", "")),
                        ("Hypothesis", (data.get("hypothesis") or {}).get("statement", "") if isinstance(data.get("hypothesis"), dict) else ""),
                    ]
                ),
                el("h3", "Tasks and scope"),
                table(["Task", "Title", "Scope", "Depends on"], task_rows, label="What each Task may change") if task_rows else el("p", "none", class_="muted"),
            ),
        )
    )

    docs = model.frozen_docs(data)
    frozen = model.frozen_paths(data)
    frozen_rows = []
    for pattern in frozen:
        matched = sorted(p for p in files if _matches(pattern, p))
        kind = "doc" if pattern in docs else "design" if pattern in (data.get("design") or {}).get("files", []) else "test"
        lines = sum(len(files[p].splitlines()) for p in matched)
        frozen_rows.append([el("code", pattern), kind, f"{len(matched)} file(s), {lines} line(s)" if matched else badge("warn", "missing")])
    frozen_body: list = [
        table(["Pattern", "Kind", "At this commit"], frozen_rows, label="What the hash freezes besides the Spec")
        if frozen_rows
        else el("p", "Nothing but the Spec.", class_="muted")
    ]
    for pattern in docs:
        for p in sorted(p for p in files if _matches(pattern, p)):
            frozen_body.append(el("details", el("summary", p), md(files[p], top=4)))
    sections.append(Section("frozen", "Frozen files and docs", join(frozen_body)))

    diagrams = [(path, src) for src in mermaid_blocks(body)] + [
        (p, src) for pattern in docs for p in sorted(files) if _matches(pattern, p) for src in mermaid_blocks(files[p])
    ]
    if diagrams:
        sections.append(Section("diagrams", "Diagrams", join([join(el("h3", el("code", where)), diagram(src)) for where, src in diagrams])))

    if since:
        sections.append(
            Section(
                "since",
                "Changed since the last approval",
                join(
                    el(
                        "p",
                        "An earlier approval of this Spec named commit ",
                        el("code", str(since.get("commit", ""))[:12]),
                        "; since then the frozen files changed:",
                    ),
                    el("pre", since.get("stat") or "(no change in the frozen files)"),
                    el("details", el("summary", "The diff"), diff_block(since.get("diff") or "")) if since.get("diff") else "",
                ),
            )
        )

    sections.append(Section("spec", "The whole Spec", el("details", el("summary", f"{path}, as written"), md(model.strip_handoffs(body), top=3))))
    lead = f"{data.get('type', '')}, route {data.get('route', '')}, confidence {data.get('confidence', '')}, owner {data.get('owner_team', '')}"
    return page(f"{sid}: {data.get('title', '')}", sections, lead=lead, badge=badge("pending", "Spec approval"))


def _matches(pattern: str, path: str) -> bool:
    from . import globs

    return globs.match_any([pattern], path)


def _section_raw(body: str, heading: str) -> str:
    """A `## heading` section's Markdown, fences kept, HTML comments dropped."""
    return model.section(body, heading, fences=True)


# ---- the Merge approval page ----

_LEVELS = (("fail", "Failing"), ("pending", "Pending"), ("warn", "Warnings"))


def merge_page(
    ctx: dict,
    d,
    *,
    diffs: dict[str, str] | None = None,
    review: tuple[str | None, list[tuple[str, str]]] | None = None,
    evidence_dir: Path | None = None,
    since: str = "",
) -> str:
    """What an Approver reads before a Merge approval: the decision and its findings with their fixes, Acceptance against
    the evidence, the reviewer's findings, the verification evidence and what the verifier recorded, the scope and the
    budget, and the diff, file by file. `d` is the gate's Decision; the page shows it and decides nothing."""
    from . import digest

    r = d.record
    diffs = diffs or {}
    spec_path = r.get("spec") or ""
    data, body = _spec_parts((ctx.get("head_files") or {}).get(spec_path) if spec_path else None, spec_path)
    evidence = ctx.get("evidence") if isinstance(ctx.get("evidence"), dict) and not ctx["evidence"].get("invalid") else None
    tested = (ctx.get("merge_group") or {}).get("sha") or ctx.get("head_sha")
    stale = ""
    if evidence and evidence.get("head_sha") != tested:
        stale = f"The evidence is for {str(evidence.get('head_sha'))[:12]}, not this head: it says nothing about this commit."
        evidence = None
    head = str(r.get("head_sha") or ctx.get("head_sha") or "")
    sections: list[Section] = []

    level = d.decision if d.decision in ("pass", "fail", "pending") else "warn"
    decision_rows = [
        ("Decision", join(badge(level), "" if d.trusted else " (local, untrusted)")),
        ("Change", r.get("change")),
        ("Spec", el("code", spec_path) if spec_path else ""),
        ("Head", el("code", head)),
        ("Base", el("code", r.get("base_sha") or ctx.get("base_sha") or "")),
        ("Profile", r.get("profile")),
        ("Route", f"{r.get('route')} (required: {r.get('required_route')})" if r.get("route") else ""),
        ("Spec approved by", ", ".join(r.get("spec_approved_by") or [])),
        ("Approved by", ", ".join(r.get("approved_by") or [])),
        ("Assisted by", ", ".join(r.get("assisted_by") or [])),
        ("Changed since the last approval", since),
    ]
    grouped: list = []
    for lvl, title in _LEVELS:
        found = [f for f in d.findings if f.level == lvl]
        if not found:
            continue
        grouped.append(el("h3", badge(lvl, title), f" {len(found)}"))
        grouped.append(
            el(
                "ul",
                [
                    el(
                        "li",
                        el("code", f.rule),
                        ": ",
                        f.message,
                        el("div", el("strong", "Fix: "), el("span", f.fix)) if f.fix else "",
                        el("div", el("code", f.code), class_="muted") if f.code else "",
                    )
                    for f in sorted(found, key=lambda f: (f.rule, f.code, f.message))
                ],
                class_="findings",
            )
        )
    if not d.findings:
        grouped.append(el("p", badge("pass", "every gate holds")))
    notes = el("ul", [el("li", n) for n in d.notes]) if d.notes else ""
    reasons = el("details", el("summary", "Why this route"), el("ul", [el("li", x) for x in r.get("route_reasons") or []])) if r.get("route_reasons") else ""
    approve_help = el(
        "p",
        "When every other rule holds, approve the head commit ",
        el("code", head[:12]),
        " with a platform review. Under the solo profile, post the line below; without a platform, run ",
        el("code", "aidd approve merge"),
        " at your own terminal. This page never approves: its buttons only copy text.",
    )
    sections.append(
        Section(
            "decision",
            "Decision",
            join(facts(decision_rows), grouped, notes, reasons, approve_help, copyable("approve-line", f"/aidd approve-merge {head}") if head else ""),
        )
    )

    items = _acceptance(body) if body else []
    cmds = ((data.get("tests") or {}).get("commands")) or []
    if items and items[0][0]:
        sections.append(
            Section(
                "acceptance",
                "Acceptance against the evidence",
                table(
                    ["Id", "Acceptance", "Proven by", "Red on base", "Green on head"],
                    acceptance_rows(items, cmds, evidence or {}, evidence_dir, artifacts=False),
                    label="Each Acceptance item, the commands that cover it, and their results on this head",
                ),
            )
        )

    who, found = review if review is not None else _review_from_comments(ctx.get("comments") or [])
    if found:
        by_sev: dict[str, list[str]] = {}
        for sev, text in found:
            by_sev.setdefault(sev, []).append(text)
        rev = [el("p", f"Reported by {who}. A report, not evidence: weigh it, then decide.", class_="muted")]
        for sev in digest.SEVERITIES:
            if sev in by_sev:
                lvl = "fail" if sev in ("Critical", "High") else "warn" if sev == "Medium" else "pending"
                rev.append(el("h3", badge(lvl, sev), f" {len(by_sev[sev])}"))
                rev.append(el("ul", [el("li", inline(t)) for t in by_sev[sev]], class_="findings"))
        sections.append(Section("review", "Reviewer findings", join(rev)))

    sections.append(Section("verification", "Verification", verification_section(evidence, data, body, evidence_dir, stale=stale)))

    budget = None
    if d.config is not None and r.get("route") not in (None, "standard", "emergency"):
        try:
            budget = d.config.gates["max_changed_lines"].get(r.get("route"))
        except (AttributeError, KeyError, TypeError):
            budget = None
    scope = list(r.get("scope") or [])
    allowed = scope + list((data.get("tests") or {}).get("files") or []) + model.design_paths(data) + ([spec_path] if spec_path else [])
    files = ctx.get("files") or []
    file_rows = []
    for f in sorted(files, key=lambda f: str(f.get("path"))):
        p = str(f.get("path"))
        where = "in scope" if _any(allowed, p) else "outside the scope"
        moved = f" (from {f['previous_path']})" if f.get("previous_path") else ""
        file_rows.append(
            [
                el("a", el("code", p + moved), href=f"#{_anchor(p)}") if p in diffs else el("code", p + moved),
                f"+{f.get('additions', 0)}",
                f"-{f.get('deletions', 0)}",
                badge("pass" if where == "in scope" else "fail", where),
            ]
        )
    lines = r.get("changed_lines", sum(int(f.get("additions") or 0) + int(f.get("deletions") or 0) for f in files))
    sections.append(
        Section(
            "scope",
            "Scope and budget",
            join(
                facts(
                    [
                        ("Scope", code_list(scope)),
                        ("Changed", f"{r.get('changed_files', len(files))} file(s), {lines} line(s) counted against the budget"),
                        ("Budget", f"{budget} lines for the {r.get('route')} route" if budget is not None else "none for this route"),
                    ]
                ),
                table(["File", "Added", "Removed", "Scope"], file_rows, label="The diffstat: every changed file") if file_rows else "",
            ),
        )
    )

    if diffs:
        budget_left = MAX_DIFF_CHARS
        blocks = []
        for p in sorted(diffs):
            text = diffs[p]
            if budget_left <= 0:
                blocks.append(el("p", f"{p}: not shown, the page's diff limit is reached; see it with git", class_="muted"))
                continue
            budget_left -= len(text)
            blocks.append(el("details", el("summary", el("code", p)), diff_block(text), id=_anchor(p)))
        sections.append(Section("diff", "The diff, file by file", join(blocks)))

    title = f"Merge approval: {data.get('id') or r.get('change') or head[:12]}" + (f": {data.get('title')}" if data.get("title") else "")
    return page(title, sections, lead=f"head {head[:12]}, {len(files)} file(s) changed", badge=badge(level, f"gate: {d.decision.upper()}"))


def _any(patterns: list[str], path: str) -> bool:
    from . import globs

    return bool(patterns) and globs.match_any(patterns, path)


def _anchor(path: str) -> str:
    return "file-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def _review_from_comments(comments: list[dict]) -> tuple[str | None, list[tuple[str, str]]]:
    """The newest comment that holds a ranked review report, all its severities."""
    from . import digest

    for c in reversed(comments):
        found = digest.ranked_findings(c.get("body") or "")
        if found:
            return c.get("user"), found
    return None, []


def review_file(path: Path) -> tuple[str | None, list[tuple[str, str]]] | None:
    """A review report saved as a file (`aidd-evidence/review.md`), or None when there is none or it ranks nothing."""
    from . import digest

    if not path.is_file():
        return None
    found = digest.ranked_findings(path.read_text(encoding="utf-8", errors="replace"))
    return (path.name, found) if found else None


def default_path(kind: str, name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "page"
    return VIEWS_DIR / f"{kind}-{safe}.html"


def diffs(ctx: dict, cwd: str) -> dict[str, str]:
    """Each changed file's diff between the context's base and head, read from git in `cwd`; empty when git cannot."""
    from . import gitutil

    base, head = ctx.get("base_sha"), ctx.get("head_sha")
    out: dict[str, str] = {}
    if not base or not head:
        return out
    for f in ctx.get("files") or []:
        p = str(f.get("path") or "")
        if p:
            text = gitutil.run(["diff", "--no-color", "--no-ext-diff", str(base), str(head), "--", p], cwd, check=False)
            if text:
                out[p] = text
    return out


def write_merge_page(ctx: dict, d, path: str, *, cwd: str, evidence_dir: Path | None = None, number: int | None = None) -> None:
    """The Merge approval page from a CI adapter; a failure prints a warning and never touches the decision."""
    from . import digest

    try:
        target = Path(path) if path else default_path("merge", str(ctx.get("head_sha") or "change")[:12])
        if number is not None:
            target = target.with_name(f"{target.stem}-{number}{target.suffix}")
        review = review_file(evidence_dir / "review.md") if evidence_dir else None
        page_text = merge_page(ctx, d, diffs=diffs(ctx, cwd), review=review, evidence_dir=evidence_dir, since=digest._since_last_approval(ctx, cwd))
        write(target, page_text)
        print(f"wrote {target}")
    except Exception as exc:  # a view for people: it must never turn a decision into an error
        print(f"warning: the Merge approval page was not written: {type(exc).__name__}: {exc}")


# ---- the decision page (experimental) ----

# The page each kind of decision has, as the command that writes it; a decision with none is read in its file.
_DECISION_PAGES = {
    "spec.spec_approval": "aidd hash {where} --summary --html",
    "spec.in_review": "aidd gate --spec {where} --html",
}


def _step_card(s: dict, n: int) -> Html:
    rows: list[tuple[str, object]] = [
        ("Who", s.get("who")),
        ("Where", el("code", s["where"]) if s.get("where") else None),
        ("Status", s.get("status")),
        ("Approvers", ", ".join(s.get("approvers") or [])),
        ("Waiting", f"{s['waiting_minutes']} minutes" if s.get("waiting_minutes") is not None else None),
    ]
    page_cmd = _DECISION_PAGES.get(str(s.get("code")))
    return el(
        "article",
        el("h3", s.get("what") or s.get("code")),
        facts(rows),
        el("p", inline(str(s.get("how") or ""))),
        join(el("p", "Its page:", class_="muted"), copyable(f"page-{n}", page_cmd.format(where=shlex.quote(str(s["where"])))))
        if page_cmd and s.get("where")
        else "",
    )


def decision_page(steps: list[dict], title: str = "Decisions waiting on you") -> str:
    """Every step `aidd list` gave, a person's decisions first, each with who decides, how, and the command that writes
    its own page. Like every view, it holds no form and approves nothing: a decision is made where its `how` says."""
    from .nextstep import AGENT, STEP_CODES

    # By the step-code contract, never the `who` text: an owner shows as an email or "@x's agent" there.
    people = [s for s in steps if s.get("code") != "lane" and STEP_CODES.get(str(s.get("code")), "author") != AGENT]
    rest = [s for s in steps if s not in people]
    sections = [
        Section(
            "decisions",
            f"Decisions ({len(people)})",
            el("div", [_step_card(s, i) for i, s in enumerate(people)], class_="cards") if people else el("p", "No decision waits.", class_="muted"),
        )
    ]
    if rest:
        sections.append(
            Section("work", f"Other open work ({len(rest)})", el("div", [_step_card(s, len(people) + i) for i, s in enumerate(rest)], class_="cards"))
        )
    lead = "Each decision says who takes it and how. Decide each one where its how says; the page itself records nothing."
    return page(title, sections, lead=lead, badge=badge("pending", f"{len(people)} waiting") if people else badge("pass", "nothing waits"))
