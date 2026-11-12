"""Product-prototype sources, flow parser, consistency checks, and line-mapped assembly."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

APP = "design/app"
SITEMAP = "sitemap.json"
SHELL = "shell.html"
FLOWS = "flows"
VIEW = ".aidd/views/prototype.html"
MARKERS = {"navigation": "<!-- aidd:navigation -->", "screens": "<!-- aidd:screens -->"}
FLOW_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
CORE_STATES = ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCREEN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TARGETS = ("data-screen", "data-go", "data-parent", "data-item-go")
_QUALIFIED = (*_TARGETS, "data-item-template")
_PRODUCT = re.compile(r'(<template id="product">\n)(.*)(</template>\n<script type="application/json" id="fixtures">)', re.S)
_TABS = re.compile(r'(<nav class="tabs" aria-label="Main">)(.*?)(</nav>)', re.S)
_MAIN = re.compile(r'(<main id="main" tabindex="-1">)(.*?)(</main>)', re.S)

_FORBIDDEN_TAGS = {
    "script": "aidd's viewer holds the one runtime",
    "nav": "the shell draws the navigation from sitemap.json",
    "iframe": "the design embeds nothing",
    "object": "the design embeds nothing",
    "embed": "the design embeds nothing",
    "base": "aidd's viewer sets the page's base",
    "meta": "aidd's viewer sets the page's policy",
    "link": "the styles go in the shell's style blocks",
    "form": 'the design submits nothing; group fields in <fieldset> and link with <button type="button" data-go="...">',
    "title": "aidd sets the page's title",
    "plaintext": "it would read the rest of the page as text",
    "xmp": "it would read the rest of the page as text",
    "noembed": "it would read the rest of the page as text",
    "noframes": "it would read the rest of the page as text",
    "noscript": "it would read the rest of the page as text",
}
_UNCLOSED = "a browser would take the rest of the page into it"
_COMMENT_TRICKS = re.compile(r"--!>|<!--->|<!-->|--!|<!\[|<\?|<!(?!--)", re.I)
_TEMPLATE_TAG = re.compile(r"<(/?)template\b", re.I)
_SWALLOWS = ("textarea", "title", "style", "xmp", "iframe", "noembed", "noframes", "noscript", "script", "plaintext", "template")
_HANDLER = re.compile(r"<[^>]*?[\s/\"']on[a-z]+\s*=", re.I)
_VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())
_UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _q(value: str) -> str:
    clean = _UNSAFE.sub("", value)
    return clean if len(clean) <= 80 else clean[:79] + "…"


@dataclass
class Flow:
    id: str
    title: str
    text: str = ""
    screens: list[tuple[str, str]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    forbidden: bool = False
    item_defs: list[str] = field(default_factory=list)
    item_uses: list[str] = field(default_factory=list)
    raw_text: str = ""
    line_owners: list[tuple[str, int]] = field(default_factory=list)
    partials: dict[str, str] = field(default_factory=dict)


class _Sections(HTMLParser):
    """The screens a flow file holds, the links in it, and the markup a flow may not hold, read as a browser reads them."""

    def __init__(self, flow: str, text: str, *, shell: bool = False, label: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.flow = flow
        self.label = label or f"flows/{flow}.html"
        self.shell = shell
        self.screens: list[tuple[str, str]] = []
        self.links: list[str] = []
        self.forbidden: list[str] = []
        self.problems: list[str] = []
        self.templates = [0, 0]
        self.item_defs: list[str] = []
        self.item_uses: list[str] = []
        self._text = text
        self._starts = [0, *(i + 1 for i, c in enumerate(text) if c == "\n")]
        self._edits: list[tuple[int, int, str]] = []
        self._open: list[list] = []

    def read(self) -> str:
        """Read the whole flow, and return it as assembled."""
        self.feed(self._text)
        self.close()
        self.forbidden += [f"an unclosed <{tag}>: {_UNCLOSED}" for tag, _, _ in self._open if tag in _SWALLOWS]
        self.forbidden += _raw_text_problems(self._text)
        raw = [len(_TEMPLATE_TAG.findall(self._text)) - len(re.findall(r"</template\b", self._text, re.I)), len(re.findall(r"</template\b", self._text, re.I))]
        if raw != self.templates:
            self.forbidden.append("a `<template` or `</template` outside a real tag, in a comment or an attribute: write it only as a tag")
        start = 0
        while (opened := self._text.find("<!--", start)) >= 0:
            start = self._text.find("-->", opened + 4)
            if start < 0:
                self.forbidden.append(f"an unclosed comment: {_UNCLOSED}")
                break
        for _, screen, _ in self._open:
            if screen:
                self.problems.append(f"screen `{self._id(screen)}` has no </section>: close it, so the next screen is not drawn inside it")
        for entry in reversed(self._open):
            self._closed(entry)
        text = self._text
        for offset, length, tag in reversed(self._edits):
            text = text[:offset] + tag + text[offset + length :]
        return text

    def _note_attributes(self, tag: str, a: dict[str, str], attrs: list[tuple[str, str | None]]) -> str:
        if "data-state" in a and self._open and self._open[-1][1]:
            self._open[-1][2] += 1
            self.problems += _state_problems(self.label, self._id(self._open[-1][1]), a["data-state"])
        screen = a.get("data-screen", "") if "data-screen" in a else ""
        if "data-screen" in a and tag != "section":
            self.problems.append(f'{self.label} holds a <{_q(tag)} data-screen="{_q(screen)}">: only a <section data-screen> is a screen')
            screen = ""
        elif "data-screen" in a and not SCREEN_ID.match(screen):
            self.problems.append(f"{self.label} names a screen {_q(repr(screen))}: use letters, digits, hyphens, and underscores, so a link can name it")
            screen = ""
        elif screen:
            self.screens.append((screen, a.get("data-title") or screen))
        self.links += [a[k] for k in _TARGETS[1:] if a.get(k)]
        for key, what in (("data-component", "component"), ("data-variant", "variant"), ("data-testid", "test id")):
            if key in a and not KEBAB.match(a[key]):
                self.problems.append(f"{self.label} names a {what} {_q(repr(a[key]))}: use lowercase words joined by hyphens, as code and its stories name it")
        if a.get("data-item-template"):
            (self.item_defs if tag == "template" else self.item_uses).append(a["data-item-template"])
        return screen

    def _note_forbidden(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _FORBIDDEN_TAGS and not (self.shell and tag == "nav"):
            self.forbidden.append(f"a <{tag}>: {_FORBIDDEN_TAGS[tag]}")
        elif tag == "style" and any(entry[0] in ("svg", "math") for entry in self._open):
            self.forbidden.append("a <style> inside <svg> or <math>: the styles go in the shell's style blocks")
        for name, value in attrs:
            if name.startswith("on"):
                self.forbidden.append(f"an event handler ({_q(name)}): aidd's viewer holds the one runtime, and the design is markup only")
            elif (value or "").strip().lower().startswith("javascript:"):
                self.forbidden.append(f'a javascript: link ({_q(name)}): a flow links with <button type="button" data-go="...">')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a: dict[str, str] = {}
        for name, value in attrs:
            a.setdefault(name, value or "")
        screen = self._note_attributes(tag, a, attrs)
        self._note_forbidden(tag, attrs)
        if any(name in _QUALIFIED for name, _ in attrs):
            self._qualify(tag, attrs)
        if tag == "template":
            self.templates[0] += 1
        if tag not in _VOID:
            self._open.append([tag, screen, 0])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and any(entry[0] in ("svg", "math") for entry in self._open):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "template":
            self.templates[1] += 1
        if tag == "template" and not any(entry[0] == "template" for entry in self._open):
            self.forbidden.append("a </template> with no <template> before it: it would end the page's product part")
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                for entry in reversed(self._open[i:]):
                    self._closed(entry)
                del self._open[i:]
                return

    def handle_comment(self, data: str) -> None:
        stripped = data.strip()
        if stripped.startswith("aidd:") and not self.shell and not (stripped == "aidd:use" or stripped.startswith(("aidd:use ", "aidd:use\t", "aidd:use\n"))):
            self.forbidden.append("an aidd marker: only the shell holds them")

    def _id(self, screen: str) -> str:
        return _q(f"{self.flow}:{screen}" if self.flow else screen)

    def _closed(self, entry: list) -> None:
        if entry[1] and not entry[2]:
            self.problems.append(f'screen `{self._id(entry[1])}` has no state: wrap its content in <div data-state="success"> (or empty, loading, error, ...)')

    def _qualify(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Write this start tag again, keeping its line count so checks report original line numbers."""
        raw = self.get_starttag_text() or ""
        line, column = self.getpos()
        written = [tag] + [
            name if value is None else f'{name}="{html.escape(_qualified(self.flow, value) if name in _QUALIFIED else value)}"' for name, value in attrs
        ]
        newlines = "\n" * raw.count("\n")
        suffix = f"{newlines}/>" if raw.endswith("/>") else f"{newlines}>"
        self._edits.append((self._starts[line - 1] + column, len(raw), "<" + " ".join(written) + suffix))


def _keep_ends(marker: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return match.group(1) + "\n" + marker + "\n" + match.group(3)

    return replace


def project_tokens(root: Path) -> str | None:
    """The project's design-system tokens as CSS, or None when it keeps none."""
    base = root / "design" / "tokens.css"
    if not base.is_file():
        return None
    themes = root / "design" / "themes"
    order = [themes / "light.css", themes / "dark.css"]
    rest = sorted(p for p in themes.glob("*.css") if p not in order) if themes.is_dir() else []
    css = "".join(p.read_text(encoding="utf-8") for p in [base, *order, *rest] if p.is_file())
    return None if "</style" in css.lower() or "<!--" in css else css


def with_project_tokens(design: str, root: Path) -> str:
    """A starting design with the tokens block holding the project's own, when it keeps a design system."""
    css = project_tokens(root)
    if css is None:
        return design
    return re.sub(r'(<style id="tokens">\n).*?(</style(?:[\s/][^>]*)?>)', lambda m: m.group(1) + css + m.group(2), design, count=1, flags=re.S)


def _shell_from(template: str, product: str, today: dt.date) -> str:
    found = _PRODUCT.search(template)
    if not found:
        raise ValueError('the starting design no longer has its <template id="product">: the tool\'s files changed')
    text = found.group(2)
    for pattern, marker in ((_TABS, MARKERS["navigation"]), (_MAIN, MARKERS["screens"])):
        text, n = pattern.subn(_keep_ends(marker), text, count=1)
        if n != 1:
            raise ValueError(f"the starting design no longer has the part {marker} replaces: the tool's files changed")
    note = (
        f"<!--\n  The shell of {html.escape(product)}'s product prototype, started {today.isoformat()}: the design system's tokens (the style\n"
        "  block with the id tokens), the product's styles, and its chrome. It is product-level work, kept current by\n"
        "  each change, and nothing freezes it. The prototype tool fills the two aidd markers from sitemap.json and\n"
        "  flows/, so keep them, and puts the shell in the viewer. Change the tokens and the styles here as the design\n"
        "  system changes, and draw screens in flows/.\n-->\n"
    )
    return note + text


def new_product_prototype(
    here: Path, root: Path, *, docs_dir: str = "docs", product: str = "", today: dt.date | None = None, build_cmd: str = "aidd prototype"
) -> list[Path]:
    """Write the product prototype's sources once: sitemap, shell, and starting flow."""
    folder = root / docs_dir / APP
    targets = [folder / SITEMAP, folder / SHELL, folder / FLOWS / "start.html"]
    if found := [p for p in targets if p.exists()]:
        raise FileExistsError(f"{found[0]} exists: the product prototype is started already; open it with `{build_cmd}`")
    name = product or "Your product"
    if problem := product_name_problem(name):
        raise ValueError(problem)
    sitemap = json.loads((here / "sitemap.json").read_text(encoding="utf-8").replace("{{product}}", json.dumps(name)[1:-1]))
    template = with_project_tokens((here / "design.html").read_text(encoding="utf-8"), root)
    shell = _shell_from(template, name, today or dt.date.today())
    start = (
        '<section data-screen="start" data-title="Start" data-initial="success">\n'
        '  <div data-state="success" data-testid="start-success">\n'
        '    <h2>Welcome to <span data-text="product"></span></h2>\n'
        "    <p>Replace this flow with the product's first one, and add a file per flow beside it.</p>\n"
        '    <!-- Link to another screen with <button type="button" data-go="flow:screen/state" data-testid="start-next">Next</button> -->\n'
        "  </div>\n"
        "</section>\n"
    )
    folder.joinpath(FLOWS).mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(sitemap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    targets[1].write_text(shell, encoding="utf-8")
    targets[2].write_text(start, encoding="utf-8")
    return targets


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def _state_problems(label: str, screen: str, state: str) -> list[str]:
    if not KEBAB.match(state):
        return [f"{label}: screen `{_q(screen)}` names a state {_q(repr(state))}: use lowercase words joined by hyphens, so a deep link can name it"]
    near = [core for core in CORE_STATES if state != core and _distance(state, core) <= 2]
    return (
        [f"{label}: screen `{_q(screen)}` names a state `{_q(state)}`: did you mean `{near[0]}`? A screen's own state is fine; this one reads like a typo"]
        if near
        else []
    )


def _raw_text_problems(text: str) -> list[str]:
    problems = []
    if found := _COMMENT_TRICKS.search(text):
        problems.append(f"the form `{_q(found.group(0))}`: a browser reads it differently; write comments as <!-- ... -->, and no declaration")
    depth = 0
    for tag in _TEMPLATE_TAG.finditer(text):
        depth += -1 if tag.group(1) else 1
        if depth < 0:
            problems.append("a </template> with no <template> before it: it would end the page's product part")
            break
    return problems


def _qualified(flow: str, target: str) -> str:
    screen, sep, state = target.partition("/")
    return (screen if ":" in screen else f"{flow}:{screen}") + sep + state


def product_name_problem(name: object) -> str:
    if isinstance(name, str) and (len(name) > 60 or "\n" in name or "\r" in name):
        return f"the product's name {_q(repr(name))} is more than one short line: hold it to one line of 60 characters or fewer, because the viewer shows it in its header"
    return ""


def _read_flow(folder: Path, where: str, item: object, seen: set[str], problems: list[str], tool: Any = None) -> Flow | None:
    fid, title = (str(item.get("id", "")), str(item.get("title") or item.get("id", ""))) if isinstance(item, dict) else ("", "")
    if not FLOW_ID.match(fid) or fid in seen:
        problems.append(f"a flow id must be unique, and lowercase letters, digits, and hyphens: {_q(repr(fid))}")
        return None
    seen.add(fid)
    try:
        raw_text = (folder / FLOWS / f"{fid}.html").read_text(encoding="utf-8")
    except OSError:
        problems.append(f"flow `{_q(fid)}` has no file: write {where}/{FLOWS}/{_q(fid)}.html, or take it out of {SITEMAP}")
        return None
    except ValueError as exc:
        problems.append(f"{where}/{FLOWS}/{fid}.html is not UTF-8 text ({exc}): save it as UTF-8")
        return None
    partials: dict[str, str] = {}
    expanded, owners = (
        tool._sibling("prototype_partials").expand_flow(folder, fid, raw_text, problems, partials)
        if tool is not None and "aidd:use" in raw_text
        else (raw_text, [(f"flows/{fid}.html", n) for n in range(1, raw_text.count("\n") + 2)])
    )
    parser = _Sections(fid, expanded)
    assembled = parser.read()
    if _HANDLER.search(expanded) and not any(w.startswith("an event handler") for w in parser.forbidden):
        parser.forbidden.append("an event handler: the shell holds the one runtime, and a flow is markup only")
    for p_label, p_raw in partials.items():
        comp_parser = _Sections(fid, p_raw, label=p_label)
        comp_parser.read()
        problems += [f"{p_label} holds {what}" for what in dict.fromkeys(comp_parser.forbidden)]
    problems += [f"flows/{fid}.html holds {what}" for what in dict.fromkeys(parser.forbidden)]
    problems += list(dict.fromkeys(parser.problems))
    if not parser.screens:
        problems.append(
            f'flows/{fid}.html holds no screen: each is a <section data-screen="<id>" data-title="...">; link between them with <button type="button" data-go="...">'
        )
    return Flow(fid, title, assembled, parser.screens, parser.links, bool(parser.forbidden), parser.item_defs, parser.item_uses, raw_text, owners, partials)


def load(
    root: Path, docs_dir: str = "docs", *, format_version: int = 1, newer_fn: Callable[[object], str] | None = None, tool: Any = None
) -> tuple[dict, str, list[Flow], list[str]]:
    """The sitemap, the shell, and each flow, as written, and what makes them unreadable."""
    folder = root / docs_dir / APP
    problems: list[str] = []
    where = f"{docs_dir}/{APP}"
    try:
        sitemap = json.loads((folder / SITEMAP).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "", [], [f"{where}/{SITEMAP} is missing: restore it from git, or start one with `aidd new product-prototype` (the tool's `new-product`)"]
    except (OSError, ValueError) as exc:
        return {}, "", [], [f"{where}/{SITEMAP} cannot be read ({exc}): fix it there, at the line and column named"]
    if not isinstance(sitemap, dict) or not isinstance(sitemap.get("flows"), list) or not isinstance(sitemap.get("navigation"), list):
        return {}, "", [], [f"{docs_dir}/{APP}/{SITEMAP} needs `flows` and `navigation` lists"]
    if newer_fn and (newer := newer_fn(sitemap.get("schema_version", sitemap.get("format", format_version)))):
        return {}, "", [], [f"{where}/{SITEMAP} {newer}"]
    try:
        shell = (folder / SHELL).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return sitemap, "", [], [f"{where}/{SHELL} cannot be read ({exc}): restore it from git, or save it as UTF-8 text"]
    problems += [f"{SHELL} lost its marker {m}: restore it, so aidd can fill it" for m in MARKERS.values() if shell.count(m) != 1]
    if 'class="device"' not in shell:
        problems.append(f'{SHELL} lost its <div class="device">, the chrome every screen sits in: restore it from the template')
    check_shell = _Sections("shell", shell, shell=True)
    check_shell.read()
    if _HANDLER.search(shell) and not any(w.startswith("an event handler") for w in check_shell.forbidden):
        check_shell.forbidden.append("an event handler: the viewer holds the one runtime")
    problems += [f"{SHELL} holds {what}" for what in dict.fromkeys(check_shell.forbidden)]
    flows: list[Flow] = []
    seen: set[str] = set()
    for item in sitemap["flows"]:
        if flow := _read_flow(folder, where, item, seen, problems, tool=tool):
            flows.append(flow)
    problems += [
        f"flows/{_q(p.name)} is in no flow of {SITEMAP}, so the page leaves it out: add it to `flows`, or delete it"
        for p in sorted((folder / FLOWS).glob("*.html"))
        if p.stem not in seen
    ]
    return sitemap, shell, flows, problems


def _suggest(target: str, choices: dict[str, str]) -> str:
    near = [c for c in choices if c != target and _distance(target, c) <= 2]
    return f" (did you mean `{_q(min(near, key=lambda c: _distance(target, c)))}`?)" if near else ""


def check(sitemap: dict, flows: list[Flow], explained: bool = False) -> list[str]:
    """What breaks the product's consistency. `explained` says a problem already names why no flow draws a screen."""
    problems: list[str] = [p for p in (product_name_problem(sitemap.get("product")),) if p]
    screens: dict[str, str] = {}
    for f in flows:
        for sid, _ in f.screens:
            q = f"{f.id}:{sid}"
            if q in screens:
                problems.append(f"screen `{_q(q)}` is drawn twice in flows/{_q(f.id)}.html: give each screen its own id")
            screens[q] = f.id
    if not screens and not explained:
        problems.append(f"{SITEMAP} lists no flow that draws a screen: add a flow to `flows`, and write its <section data-screen> in flows/<flow>.html")
    for f in flows:
        for link in f.links:
            target = _qualified(f.id, link).partition("/")[0]
            if target not in screens:
                problems.append(f"flows/{_q(f.id)}.html links to `{_q(link)}`, which no flow draws{_suggest(target, screens)}")
    items = {_qualified(f.id, d) for f in flows for d in f.item_defs}
    problems += [
        f'flows/{_q(f.id)}.html lists `{_q(u)}`, an item template no flow defines: add <template data-item-template="{_q(u)}">, or name another flow\'s as `<flow>:<name>`'
        for f in flows
        for u in dict.fromkeys(f.item_uses)
        if _qualified(f.id, u) not in items
    ]
    reached = _check_navigation(sitemap, screens, problems)
    links = {f.id: {_qualified(f.id, link).partition(":")[0] for link in f.links} for f in flows}
    todo = list(reached)
    while todo:
        for nxt in links.get(todo.pop(), set()) - reached:
            reached.add(nxt)
            todo.append(nxt)
    problems += [
        f"flow `{_q(f.id)}` is reached only from the sitemap: add it to the navigation, or link it from another flow"
        for f in flows
        if f.screens and f.id not in reached
    ]
    return problems


def _check_navigation(sitemap: dict, screens: dict[str, str], problems: list[str]) -> set[str]:
    reached: set[str] = set()
    for item in sitemap.get("navigation", []):
        go = str(item.get("go", "")) if isinstance(item, dict) else ""
        target = go.partition("/")[0]
        if not isinstance(item, dict) or not item.get("label"):
            problems.append(f"each navigation item in {SITEMAP} needs a `label` and a `go`: {_q(repr(item))}")
        elif screens and target not in screens:  # with no screen at all, the one problem that says so covers each item
            problems.append(f"navigation item `{_q(str(item['label']))}` opens `{_q(go)}`, which no flow draws{_suggest(target, screens)}")
        reached.add(go.partition(":")[0])
    return reached


def _nav_buttons(sitemap: dict) -> list[str]:
    nav, ids = [], set()
    for item in (i for i in sitemap.get("navigation", []) if isinstance(i, dict)):
        base = f"app-nav-{re.sub(r'[^a-z0-9]+', '-', str(item.get('label', '')).lower()).strip('-') or 'item'}"
        testid, n = base, 1
        while testid in ids:
            n += 1
            testid = f"{base}-{n}"
        ids.add(testid)
        nav.append(
            f'<button type="button" data-go="{html.escape(str(item.get("go", "")))}" data-component="tab" data-testid="{testid}"><span>{html.escape(str(item.get("label", "")))}</span></button>'
        )
    return nav


def product_body(sitemap: dict, shell: str, flows: list[Flow]) -> str:
    """The product part as assembled: the shell, with the navigation the sitemap draws and every flow's screens."""
    parts = {"navigation": "\n".join(_nav_buttons(sitemap)), "screens": "\n".join(f.text for f in flows)}
    pattern = re.compile("|".join(re.escape(m) for m in MARKERS.values()))
    names = {m: k for k, m in MARKERS.items()}
    return pattern.sub(lambda m: parts[names[m.group(0)]], shell)


def _segment_lines(chunks: list[tuple[list[tuple[str, int]], str]]) -> list[tuple[str, int]]:
    """Build a 1-based line lookup table across concatenated text chunks."""
    out: list[tuple[str, int]] = []
    texts: list[str] = []
    for owners, text in chunks:
        if not text:
            continue
        if not out:
            out.extend(owners)
            texts.append(text)
            continue
        prev = texts[-1]
        if prev.endswith("\n") or (not text.startswith("\n") and prev.rsplit("\n", 1)[-1].strip() == ""):
            out[-1] = owners[0]
        out.extend(owners[1:])
        texts.append(text)
    return out


_REF_LINE = re.compile(r"(repeats (?:the id|the one) on )line (\d+)")


def _product_duplicate(message: str) -> bool:
    if message.startswith("screen ") and ("repeats the screen" in message or "has no state" in message or "is not reached from the first screen" in message):
        return True
    return message.startswith("the design draws no screen") or (
        "names no screen;" in message and message.startswith(("data-go=", "data-item-go=", "data-parent="))
    )


def _remap_ref(message: str, line_map: list[tuple[str, int]], where: str) -> str:
    if not line_map or not (m := _REF_LINE.search(message)):
        return message
    rf, rl = line_map[max(0, min(int(m.group(2)) - 1, len(line_map) - 1))]
    return f"{message[: m.start()]}{m.group(1)}{f'line {rl}' if rf == where else f'{rf}:{rl}'}{message[m.end() :]}"


def _flow_line_owners(flows: list[Flow], shell: str) -> list[tuple[str, int]]:
    """Per-line `(file, line)` pairs for concatenated flow blocks."""
    owners: list[tuple[str, int]] = []
    for f in flows:
        owners.extend(f.line_owners or [(f"flows/{f.id}.html", n) for n in range(1, f.text.count("\n") + 2)])
    return owners or [(SHELL, shell[: shell.find(MARKERS["screens"])].count("\n") + 1)]


def mapped_product_body(sitemap: dict, shell: str, flows: list[Flow]) -> tuple[str, list[tuple[str, str]], list[tuple[str, int]]]:
    """Assembled product body plus raw source pairs and line mapping back to shell, flows, and component partials."""
    nav_buttons = _nav_buttons(sitemap)
    nav_text = "\n".join(nav_buttons)
    screens_text = "\n".join(f.text for f in flows)
    pattern = re.compile("|".join(re.escape(m) for m in MARKERS.values()))
    names = {m: k for k, m in MARKERS.items()}
    seen_partials: dict[str, str] = {}
    for f in flows:
        seen_partials.update(f.partials)
    raw_files: list[tuple[str, str]] = [(SHELL, shell), *((f"flows/{f.id}.html", f.raw_text or f.text) for f in flows), *seen_partials.items()]
    nav_owners = [(SITEMAP, 1) for btn in nav_buttons for _ in range(btn.count("\n") + 1)] or [
        (SHELL, shell[: shell.find(MARKERS["navigation"])].count("\n") + 1)
    ]
    flow_owners = _flow_line_owners(flows, shell)
    chunks: list[tuple[list[tuple[str, int]], str]] = []
    texts: list[str] = []
    pos = 0
    for match in pattern.finditer(shell):
        before = shell[pos : match.start()]
        first_line = shell[:pos].count("\n") + 1
        texts.append(before)
        chunks.append(([(SHELL, first_line + n) for n in range(before.count("\n") + 1)], before))
        kind = names[match.group(0)]
        sub_text = nav_text if kind == "navigation" else screens_text
        texts.append(sub_text)
        chunks.append((nav_owners if kind == "navigation" else flow_owners, sub_text))
        pos = match.end()
    tail = shell[pos:]
    tail_first = shell[:pos].count("\n") + 1
    texts.append(tail)
    chunks.append(([(SHELL, tail_first + n) for n in range(tail.count("\n") + 1)], tail))
    return "".join(texts), raw_files, _segment_lines(chunks)


def _collect_product_checks(
    dc: Any, body: str, reader: Any, tokens: dict[str, str], raw_files: list[tuple[str, str]], line_map: list[tuple[str, int]], design_format: int
) -> tuple[list[str], str]:
    mapped: list[tuple[str, int, str]] = []
    for line, raw_msg in [*dc.integrity_problems(reader), *[(ln, dc.hint_paint(msg, tokens)) for ln, msg in reader.paints], *dc.device_problems(reader)]:
        if _product_duplicate(raw_msg):
            continue
        idx = max(0, min(line - 1, len(line_map) - 1)) if line_map else -1
        where, orig_line = line_map[idx] if idx >= 0 else (SHELL, line)
        mapped.append((where, orig_line, _remap_ref(raw_msg, line_map, where)))
    for line, message, rule in dc._lint(body, tokens):
        if dc.RULE_FORMATS[rule] <= design_format:
            idx = max(0, min(line - 1, len(line_map) - 1)) if line_map else -1
            where, orig_line = line_map[idx] if idx >= 0 else (SHELL, line)
            mapped.append((where, orig_line, message))
    order = {name: i for i, (name, _) in enumerate(raw_files)}
    mapped.sort(key=lambda item: (order.get(item[0], len(order)), item[1]))
    lines = list(dict.fromkeys(f"{where}:{line}: {message}" for where, line, message in mapped))
    if len(lines) > dc._PROBLEM_LIMIT:
        lines = lines[: dc._PROBLEM_LIMIT] + [
            f"{raw_files[0][0] if raw_files else SHELL}: and {len(lines) - dc._PROBLEM_LIMIT} more problems; fix these, then check again"
        ]
    return lines, dc.summary(reader)


def product_design_problems(tool: Any, sitemap: dict, shell: str, flows: list[Flow], folder: Path) -> tuple[list[str], str]:
    """Run product consistency, image, and design checks, returning `(problems, summary)`."""
    unlisted = any(f.stem not in {fl.id for fl in flows} for f in (folder / FLOWS).glob("*.html"))
    problems = check(sitemap, flows, explained=unlisted or (bool(flows) and not any(f.screens for f in flows)))
    body, raw_files, line_map = mapped_product_body(sitemap, shell, flows)
    design_problems, ok = _collect_product_checks(
        tool.design_checks,
        body,
        tool.design_checks.read_design(body, raw_files[0][0] if raw_files else SHELL, 1),
        tool.design_checks.token_colors(shell),
        raw_files,
        line_map,
        tool.FORMAT,
    )
    problems += design_problems
    problems += [f"{SITEMAP}: {p}" for p in tool.with_images(sitemap.get("fixtures"), tool.image_fields(body), folder)[1]]
    return problems, ok


def check_product_prototype(tool: Any, root: Path, docs_dir: str = "docs") -> tuple[list[str], str]:
    """Check the product prototype and return `(problems, summary)`."""
    sitemap, shell, flows, problems = load(root, docs_dir, format_version=tool.FORMAT, newer_fn=tool._newer, tool=tool)
    if not sitemap or not shell:
        return problems, ""
    extra, ok = product_design_problems(tool, sitemap, shell, flows, root / docs_dir / APP)
    return problems + extra, ok


def build_product_prototype(tool: Any, root: Path, docs_dir: str = "docs", write: bool = True) -> tuple[Path | None, list[str]]:
    """Assemble the product prototype, check it, and write `.aidd/views/prototype.html` when sound enough to inspect."""
    sitemap, shell, flows, problems = load(root, docs_dir, format_version=tool.FORMAT, newer_fn=tool._newer, tool=tool)
    if not sitemap or not shell:
        if write:
            (root / VIEW).unlink(missing_ok=True)
        return None, problems
    folder = root / docs_dir / APP
    problems += product_design_problems(tool, sitemap, shell, flows, folder)[0]
    if not write or any(p.startswith(f"{SHELL} ") for p in problems) or any(f.forbidden for f in flows):
        if write:
            (root / VIEW).unlink(missing_ok=True)
        return None, problems
    target = tool._views(root) / Path(VIEW).name
    tool._write_page(target, tool.assemble(sitemap, shell, flows, tool.round_comments(folder), problems, folder))
    return target, problems
