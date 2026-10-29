"""aidd-team's prototype tool: a design shown in the prototype viewer, checked, and turned into a component contract.

One standard-library file, so it runs wherever Python 3.11 does, with aidd or without it (`aidd prototype` runs it).
Three parts, each with one owner:

- the viewer, `viewer.html` beside this file: the framework, aidd-team's. A project never keeps it: the tool writes each
  page to `.aidd/views/` from the viewer as it stands, so every design gets every fix to the viewer;
- a design: a Spec's prototype file (`design.html` is where one starts; `aidd new design-spec --prototype` writes it),
  or the product prototype in `<docs>/design/app/`: `sitemap.json` (the navigation, defined once, and the example
  data), `shell.html` (the tokens, the styles, and the chrome), and `flows/<flow>.html` (one flow's screens);
- the component contract, read from the design: every `data-component` and `data-variant` the screens name, which
  the built UI's stories match by name (`stories` checks Storybook's `index.json` against it).

Every check is on the design as a browser reads it: no script, no handler, nothing that reaches past the design's
<template id="product">, every link and screen resolved, every screen with a state. A design file also gets the checks in
`design_checks.py`, beside this file: each link, parent, and first state names something, every control has a test id and a
name, and the prototype lint rules hold, each problem with its line. Nothing here calls a model or the network. Run
`python3 prototype.py --help` for the commands.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import importlib.util
import json
import re
import stat
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent


def _sibling(name: str) -> ModuleType:
    """A module beside this file, loaded by its path, so the tool runs the same from aidd, from `python3 -I`, and from any
    folder: the tool is one folder, and the folder needs no install."""
    key = f"aidd_team_tools.{HERE / name}"  # keyed by the file's path, so a module cached from another folder is never reused
    if key in sys.modules:
        return sys.modules[key]
    if not (HERE / f"{name}.py").is_file():
        raise FileNotFoundError(f"the prototype tool's {name}.py is missing beside {Path(__file__).name}: reinstall aidd-team")
    spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"the prototype tool's {name}.py cannot be loaded beside {Path(__file__).name}: reinstall aidd-team")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module


try:
    design_checks = _sibling("design_checks")
except FileNotFoundError as missing:
    if __name__ != "__main__":
        raise
    print(missing, file=sys.stderr)  # run directly, a missing part is a plain message and exit 2, `--help` included
    raise SystemExit(2) from None
# The design format this tool reads: a design names it on its <html> (`data-aidd-prototype`), the product's sitemap as
# `format`. A design newer than the tool asks for a newer tool, never a guess.
FORMAT = 1
# How a message names the build: `aidd prototype` by default; the command line names this file when run directly.
BUILD = "aidd prototype"

APP = "design/app"
SITEMAP = "sitemap.json"
SHELL = "shell.html"
FLOWS = "flows"
VIEW = ".aidd/views/prototype.html"
MARKERS = {"navigation": "<!-- aidd:navigation -->", "screens": "<!-- aidd:screens -->"}
FLOW_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
# The template's parts: the product (which the shell holds), and in it the navigation and the screens aidd fills; and
# the viewer's own data blocks, its subtitle, its comment for a Spec's prototype, and its title.
_PRODUCT = re.compile(r'(<template id="product">\n)(.*)(</template>\n<script type="application/json" id="fixtures">)', re.S)
_TABS = re.compile(r'(<nav class="tabs" aria-label="Main">)(.*?)(</nav>)', re.S)
_MAIN = re.compile(r'(<main id="main" tabindex="-1">)(.*?)(</main>)', re.S)
_FIXTURES = re.compile(r'(<script type="application/json" id="fixtures">)(.*?)(</script>)', re.S)
_CONFIG = re.compile(r'(<script type="application/json" id="viewer-config">)(.*?)(</script>)', re.S)
_TITLE = re.compile(r"<title>.*?</title>", re.S | re.I)
# The Spec a design names in its head. The viewer shows it, and the words to type to approve it, so it must read as an id,
# as `approve SPEC-24` does. That keeps a sketch's "a sketch", the showcase's "the showcase", and aidd's decision words out.
_SPEC_META = re.compile(r'<meta\s+name="aidd-spec"\s+content="([^"]*)"', re.I)
_SPEC_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")  # aidd's own id rule (typed_words._ID), matched whole: "all" and "merge" are no id
# The Spec a design's path names: specs/<ID>/design/prototype.html. The head's name counts only when it is this one.
_SPEC_IN_PATH = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9]*-[0-9]+)/design/")
_DESIGN_FORMAT = re.compile(r"""<html\b[^>]*\bdata-aidd-prototype\s*=\s*["']?([^"'\s>]*)""", re.I)
# The eight screen states the viewer gives a key, 1 to 8. A screen may add its own, such as no-results or submitting.
CORE_STATES = ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")
# A component's or a variant's name: lowercase words joined by hyphens, as code and its stories name it.
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# The attributes that name a screen or link to one, which the assembled view qualifies by the flow. The runtime copies
# data-item-go onto each item of a list as its data-go.
_TARGETS = ("data-screen", "data-go", "data-parent", "data-item-go")
# What the assembled view also qualifies by the flow: a list's item template, so two flows may each name a `card`.
_QUALIFIED = (*_TARGETS, "data-item-template")
# A screen id: what a link and a deep link can name, so no `:` (the flow's) and no `/` (the state's).
SCREEN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_q = design_checks.quoted  # every value from a flow, the shell, or the sitemap is quoted in a message
_VOID = design_checks.VOID  # the HTML standard's void elements, which never open a level


def product_prototype_dir(root: Path, docs_dir: str = "docs") -> Path:
    return root / docs_dir / APP


def new_product_prototype(root: Path, *, docs_dir: str = "docs", product: str = "", today: dt.date | None = None) -> list[Path]:
    """Write the product prototype's sources once: the sitemap, the shell from the flow prototype's template, and a first
    flow to replace. Refuses when the folder holds any of them, so a person's work is never overwritten."""
    folder = product_prototype_dir(root, docs_dir)
    targets = [folder / SITEMAP, folder / SHELL, folder / FLOWS / "start.html"]
    if found := [p for p in targets if p.exists()]:
        raise FileExistsError(f"{found[0]} exists: the product prototype is started already; open it with `{BUILD}`")
    name = product or "Your product"
    sitemap = json.loads((HERE / "sitemap.json").read_text(encoding="utf-8").replace("{{product}}", json.dumps(name)[1:-1]))
    template = with_project_tokens((HERE / "design.html").read_text(encoding="utf-8"), root)
    shell = _shell_from(template, name, today or dt.date.today())
    start = (
        '<section data-screen="start" data-title="Start" data-initial="success">\n'
        '  <div data-state="success" data-testid="start-success">\n'
        '    <h2>Welcome to <span data-text="product"></span></h2>\n'
        "    <p>Replace this flow with the product's first one, and add a file per flow beside it.</p>\n"
        "  </div>\n"
        "</section>\n"
    )
    folder.joinpath(FLOWS).mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(sitemap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    targets[1].write_text(shell, encoding="utf-8")
    targets[2].write_text(start, encoding="utf-8")
    return targets


def _shell_from(template: str, product: str, today: dt.date) -> str:
    """The product's part of the flow prototype's template: its tokens, its styles, and its chrome, with the example
    navigation and screens replaced by the markers aidd fills. `product` names it in the note at its top."""
    found = _PRODUCT.search(template)
    if not found:
        raise ValueError('the starting design no longer has its <template id="product">: the tool\'s files changed')
    text = found.group(2)
    for pattern, marker in ((_TABS, MARKERS["navigation"]), (_MAIN, MARKERS["screens"])):
        text, n = pattern.subn(_keep_ends(marker), text, count=1)
        if n != 1:
            raise ValueError(f"the starting design no longer has the part {marker} replaces: the tool's files changed")
    note = (
        f"<!--\n  The shell of {product}'s product prototype, started {today.isoformat()}: the design system's tokens (the style\n"
        "  block with the id tokens), the product's styles, and its chrome. It is product-level work, kept current by\n"
        "  each change, and nothing freezes it. The prototype tool fills the two aidd markers from sitemap.json and\n"
        "  flows/, so keep them, and puts the shell in the viewer. Change the tokens and the styles here as the design\n"
        "  system changes, and draw screens in flows/.\n-->\n"
    )
    return note + text


def project_tokens(root: Path) -> str | None:
    """The project's design-system tokens as CSS, the build's output (`design/tokens.css`, then its themes, light and
    dark first), or None when it keeps none. A stylesheet that could end its style block is never taken."""
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
    return re.sub(r'(<style id="tokens">\n).*?(</style>)', lambda m: m.group(1) + css + m.group(2), design, count=1, flags=re.S)


def _fixed(text: str) -> Callable[[re.Match[str]], str]:
    """A replacement that puts `text` in place of the whole match, read literally (no group references)."""

    def replace(_match: re.Match[str]) -> str:
        return text

    return replace


def _keep_ends(marker: str) -> Callable[[re.Match[str]], str]:
    """A replacement that keeps a part's opening and closing tags and puts `marker` between them."""

    def replace(match: re.Match[str]) -> str:
        return match.group(1) + "\n" + marker + "\n" + match.group(3)

    return replace


@dataclass
class Flow:
    id: str
    title: str
    text: str = ""  # the flow as assembled: its screen ids and links qualified by the flow
    screens: list[tuple[str, str]] = field(default_factory=list)  # (screen id, its title), in order
    links: list[str] = field(default_factory=list)  # every data-go, data-parent, and data-item-go target, as written
    forbidden: bool = False  # holds markup a flow may not hold, so no page is written
    item_defs: list[str] = field(default_factory=list)  # the item templates it defines, as written
    item_uses: list[str] = field(default_factory=list)  # the item templates its lists repeat, as written


class _Sections(HTMLParser):
    """The screens a flow file holds, the links in it, and the markup a flow may not hold, read as a browser reads them;
    and the flow as assembled, from the same reading, so what the check passes is what the page links."""

    def __init__(self, flow: str, text: str, *, shell: bool = False, label: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.flow = flow
        self.label = label or f"flows/{flow}.html"  # the file the messages name
        self.shell = shell  # the shell holds the navigation and the aidd markers; a flow holds neither
        self.screens: list[tuple[str, str]] = []
        self.links: list[str] = []
        self.forbidden: list[str] = []
        self.problems: list[str] = []
        self.templates = [0, 0]  # the real <template> start and end tags the parser read
        self.item_defs: list[str] = []  # the item templates this file defines
        self.item_uses: list[str] = []  # the item templates its lists repeat
        self._text = text
        self._starts = [0, *(i + 1 for i, c in enumerate(text) if c == "\n")]  # each line's offset, for getpos()
        self._edits: list[tuple[int, int, str]] = []  # (offset, length, the start tag with its targets qualified)
        self._open: list[list] = []  # [tag, the screen a <section> opens or "", its data-state children], outermost first

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
        for _, screen, _states in self._open:
            if screen:
                self.problems.append(f"screen `{self._id(screen)}` has no </section>: close it, so the next screen is not drawn inside it")
        for entry in reversed(self._open):
            self._closed(entry)
        text = self._text
        for offset, length, tag in reversed(self._edits):
            text = text[:offset] + tag + text[offset + length :]
        return text

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a: dict[str, str] = {}
        for name, value in attrs:
            a.setdefault(name, value or "")  # a browser keeps an attribute's first value
        if "data-state" in a and self._open and self._open[-1][1]:
            self._open[-1][2] += 1
            self.problems += _state_problems(self.label, self._id(self._open[-1][1]), a["data-state"])
        screen = a.get("data-screen", "") if "data-screen" in a else ""
        if "data-screen" in a and tag != "section":
            self.problems.append(
                f'{self.label} holds a <{design_checks.quoted(tag)} data-screen="{design_checks.quoted(screen)}">: only a <section data-screen> is a screen'
            )
            screen = ""
        elif "data-screen" in a and not SCREEN_ID.match(screen):
            self.problems.append(f"{self.label} names a screen {_q(repr(screen))}: use letters, digits, hyphens, and underscores, so a link can name it")
            screen = ""
        elif screen:
            self.screens.append((screen, a.get("data-title") or screen))
        self.links += [a[k] for k in _TARGETS[1:] if a.get(k)]
        # A test id, like a component and a variant, is a name in lowercase words joined by hyphens. The viewer copies it into
        # a prompt, so a design cannot make it a sentence or a line break.
        for key, what in (("data-component", "component"), ("data-variant", "variant"), ("data-testid", "test id")):
            if key in a and not KEBAB.match(a[key]):
                self.problems.append(f"{self.label} names a {what} {_q(repr(a[key]))}: use lowercase words joined by hyphens, as code and its stories name it")
        if a.get("data-item-template"):
            (self.item_defs if tag == "template" else self.item_uses).append(a["data-item-template"])
        if tag in _FORBIDDEN_TAGS and not (self.shell and tag == "nav"):
            self.forbidden.append(f"a <{tag}>: {_FORBIDDEN_TAGS[tag]}")
        elif tag == "style" and any(entry[0] in ("svg", "math") for entry in self._open):
            # A browser reads markup inside SVG's or MathML's <style>, where this parser reads only text.
            self.forbidden.append("a <style> inside <svg> or <math>: the styles go in the shell's style blocks")
        for name, value in attrs:
            if name.startswith("on"):
                self.forbidden.append(f"an event handler ({design_checks.quoted(name)}): aidd's viewer holds the one runtime, and the design is markup only")
            elif (value or "").strip().lower().startswith("javascript:"):
                self.forbidden.append(f"a javascript: link ({design_checks.quoted(name)}): a flow links with data-go")
        if any(name in _QUALIFIED for name, _ in attrs):
            self._qualify(tag, attrs)
        if tag == "template":
            self.templates[0] += 1
        if tag not in _VOID:
            self._open.append([tag, screen, 0])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # HTML ignores `/>` except inside SVG and MathML, where it closes the element.
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and any(entry[0] in ("svg", "math") for entry in self._open):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        # An end tag closes its element and every element still open inside it; one with no open element is ignored,
        # except </template>, which would close the page's <template id="product"> and put the rest in the viewer.
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
        if data.strip().startswith("aidd:") and not self.shell:
            self.forbidden.append("an aidd marker: only the shell holds them")

    def _id(self, screen: str) -> str:
        return _q(f"{self.flow}:{screen}" if self.flow else screen)

    def _closed(self, entry: list) -> None:
        if entry[1] and not entry[2]:
            self.problems.append(f'screen `{self._id(entry[1])}` has no state: wrap its content in <div data-state="success"> (or empty, loading, error, ...)')

    def _qualify(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Write this start tag again, with each screen id and link qualified by the flow and every value escaped once."""
        raw = self.get_starttag_text() or ""
        line, column = self.getpos()
        written = [tag] + [
            name if value is None else f'{name}="{html.escape(_qualified(self.flow, value) if name in _QUALIFIED else value)}"' for name, value in attrs
        ]
        self._edits.append((self._starts[line - 1] + column, len(raw), "<" + " ".join(written) + ("/>" if raw.endswith("/>") else ">")))


# What the design may not hold, and why: it is markup only, so aidd's viewer keeps the one runtime and the page's policy,
# and nothing the design holds can reach past its <template id="product">.
_FORBIDDEN_TAGS = {
    "script": "aidd's viewer holds the one runtime",
    "nav": "the shell draws the navigation from sitemap.json",
    "iframe": "the design embeds nothing",
    "object": "the design embeds nothing",
    "embed": "the design embeds nothing",
    "base": "aidd's viewer sets the page's base",
    "meta": "aidd's viewer sets the page's policy",
    "link": "the styles go in the shell's style blocks",
    "form": "the design submits nothing; a button links with data-go",
    "title": "aidd sets the page's title",
    "plaintext": "it would read the rest of the page as text",
    "xmp": "it would read the rest of the page as text",
    "noembed": "it would read the rest of the page as text",
    "noframes": "it would read the rest of the page as text",
    "noscript": "it would read the rest of the page as text",
}
_UNCLOSED = "a browser would take the rest of the page into it"
# Comment forms a browser ends early, where an older parser reads on: a design never needs them, so none is accepted.
_COMMENT_TRICKS = re.compile(r"--!>|<!--->|<!-->|--!|<!\[|<\?|<!(?!--)", re.I)
_TEMPLATE_TAG = re.compile(r"<(/?)template\b", re.I)
# A path aidd writes into a page: plain characters only, so it can close no comment and open no tag.
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
# An element a browser reads to its own end tag whatever comes between: left open, it takes the rest of the page.
_SWALLOWS = ("template", "textarea", "title", "style", "script", "iframe", "noembed", "noframes", "noscript", "xmp", "plaintext")
# The template's Content-Security-Policy (no remote load, no form, no base), the page's only one: the shell and the flows
# sit in a <template>, so neither can add a policy of its own.
_POLICY = re.compile(r'<meta http-equiv="Content-Security-Policy" content="[^"]*">')


# Raw text that reads as an event handler in a tag, whatever a parser makes of it: a second check beside the parser's.
_HANDLER = re.compile(r"<[^>]*?[\s/\"']on[a-z]+\s*=", re.I)
# The viewer's own inline scripts, which the page's policy names by hash, so no other script or event handler can run. It
# reads aidd-team's viewer.html only, never a design; any letter case and a loose end tag (`</script >`) count.
_SCRIPT = re.compile(r"<script>(.*?)</script\s*>", re.S | re.I)
# Every script element's start, and the JSON data blocks among them, which run nothing: the rest must all be hashed.
_ANY_SCRIPT = re.compile(r"<script\b", re.I)
_DATA_SCRIPT = re.compile(r'<script type="application/json"', re.I)
_SCRIPT_SRC = re.compile(r"script-src [^;]*")


def _page_policy(template: str) -> str:
    """The template's Content-Security-Policy, with its inline scripts narrowed to the viewer's own, by hash, read from
    aidd's template, never from the page: an event handler or a script that reached a flow or the shell cannot run,
    whatever the parser missed."""
    found = _POLICY.search(template)
    if not found or not _SCRIPT_SRC.search(found.group(0)):
        raise ValueError("the viewer's Content-Security-Policy changed: the tool's files changed")
    return _SCRIPT_SRC.sub("script-src " + script_hashes(template), found.group(0), count=1)


def _state_problems(label: str, screen: str, state: str) -> list[str]:
    """A state name a deep link cannot carry, or one a letter or two from a core state, which reads like a typo."""
    if not KEBAB.match(state):
        return [f"{label}: screen `{_q(screen)}` names a state {_q(repr(state))}: use lowercase words joined by hyphens, so a deep link can name it"]
    near = [core for core in CORE_STATES if state != core and _distance(state, core) <= 2]
    return (
        [f"{label}: screen `{_q(screen)}` names a state `{_q(state)}`: did you mean `{near[0]}`? A screen's own state is fine; this one reads like a typo"]
        if near
        else []
    )


def _distance(a: str, b: str) -> int:
    """How many single-letter edits turn `a` into `b` (Levenshtein)."""
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def _raw_text_problems(text: str) -> list[str]:
    """What the raw text holds that could reach past <template id="product">, read with no parser, so no difference
    between this parser and a browser's can hide it: a comment form a browser ends early, and a </template> that
    outnumbers the <template> before it, wherever it sits, even in a comment or an attribute."""
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


def script_hashes(template: str) -> str:
    """The template's own inline scripts, as Content-Security-Policy hash sources: the only scripts its pages run. A
    script element that is neither one of them nor a JSON data block stops the build, so none is left unhashed or
    hashed by mistake."""
    scripts = _SCRIPT.findall(template)
    if len(_ANY_SCRIPT.findall(template)) != len(scripts) + len(_DATA_SCRIPT.findall(template)):
        raise ValueError("the viewer holds a script element the page's policy cannot name: the tool's files changed")
    hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(s.encode('utf-8')).digest()).decode('ascii')}'" for s in scripts]
    return " ".join(hashes) or "'none'"


def _qualified(flow: str, target: str) -> str:
    """A link as the assembled view names it: `<flow>:<screen>`, keeping a `/<state>` after it."""
    screen, sep, state = target.partition("/")
    return (screen if ":" in screen else f"{flow}:{screen}") + sep + state


def load(root: Path, docs_dir: str = "docs") -> tuple[dict, str, list[Flow], list[str]]:
    """The sitemap, the shell, and each flow, as written, and what makes them unreadable. Fails closed: a sitemap or a
    flow aidd cannot read is a problem, never an empty prototype."""
    folder = product_prototype_dir(root, docs_dir)
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
    if newer := _newer(sitemap.get("format", 1)):
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
        fid, title = (str(item.get("id", "")), str(item.get("title") or item.get("id", ""))) if isinstance(item, dict) else ("", "")
        if not FLOW_ID.match(fid) or fid in seen:
            problems.append(f"a flow id must be unique, and lowercase letters, digits, and hyphens: {_q(repr(fid))}")
            continue
        seen.add(fid)
        path = folder / FLOWS / f"{fid}.html"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            problems.append(f"flow `{_q(fid)}` has no file: write {where}/{FLOWS}/{_q(fid)}.html, or take it out of {SITEMAP}")
            continue
        except ValueError as exc:
            problems.append(f"{where}/{FLOWS}/{fid}.html is not UTF-8 text ({exc}): save it as UTF-8")
            continue
        parser = _Sections(fid, text)
        assembled = parser.read()
        if _HANDLER.search(text) and not any(w.startswith("an event handler") for w in parser.forbidden):
            parser.forbidden.append("an event handler: the shell holds the one runtime, and a flow is markup only")
        problems += [f"flows/{fid}.html holds {what}" for what in dict.fromkeys(parser.forbidden)]
        problems += list(dict.fromkeys(parser.problems))
        if not parser.screens:
            problems.append(f'flows/{fid}.html holds no screen: each is a <section data-screen="<id>" data-title="...">')
        flows.append(Flow(fid, title, assembled, parser.screens, parser.links, bool(parser.forbidden), parser.item_defs, parser.item_uses))
    problems += [
        f"flows/{_q(p.name)} is in no flow of {SITEMAP}, so the page leaves it out: add it to `flows`, or delete it"
        for p in sorted((folder / FLOWS).glob("*.html"))
        if p.stem not in seen
    ]
    return sitemap, shell, flows, problems


def product_name_problem(name: object) -> str:
    """Why a product's name cannot head the viewer: it is one short line of at most 60 characters, or nothing."""
    if isinstance(name, str) and (len(name) > 60 or "\n" in name or "\r" in name):
        return f"the product's name {_q(repr(name))} is more than one short line: hold it to one line of 60 characters or fewer, because the viewer shows it in its header"
    return ""


def check(sitemap: dict, flows: list[Flow]) -> list[str]:
    """What breaks the product's consistency: a screen twice, a link or a navigation item that opens no screen, and a
    flow nobody reaches but through the sitemap."""
    problems: list[str] = [p for p in (product_name_problem(sitemap.get("product")),) if p]
    screens: dict[str, str] = {}
    for f in flows:
        for sid, _ in f.screens:
            q = f"{f.id}:{sid}"
            if q in screens:
                problems.append(f"screen `{_q(q)}` is drawn twice in flows/{_q(f.id)}.html: give each screen its own id")
            screens[q] = f.id
    for f in flows:
        for link in f.links:
            target = _qualified(f.id, link).partition("/")[0]
            if target not in screens:
                problems.append(f"flows/{_q(f.id)}.html links to `{_q(link)}`, which no flow draws")
    items = {_qualified(f.id, d) for f in flows for d in f.item_defs}
    problems += [
        f'flows/{_q(f.id)}.html lists `{_q(u)}`, an item template no flow defines: add <template data-item-template="{_q(u)}">, or name another flow\'s as `<flow>:<name>`'
        for f in flows
        for u in dict.fromkeys(f.item_uses)
        if _qualified(f.id, u) not in items
    ]
    reached: set[str] = set()
    for item in sitemap.get("navigation", []):
        go = str(item.get("go", "")) if isinstance(item, dict) else ""
        if not isinstance(item, dict) or not item.get("label"):
            problems.append(f"each navigation item in {SITEMAP} needs a `label` and a `go`: {_q(repr(item))}")
        elif go.partition("/")[0] not in screens:
            problems.append(f"navigation item `{_q(str(item['label']))}` opens `{_q(go)}`, which no flow draws")
        reached.add(go.partition(":")[0])
    # A flow counts as reached only through a chain of links from the navigation, so two flows that link only each
    # other are both unreached.
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


def product_body(sitemap: dict, shell: str, flows: list[Flow]) -> str:
    """The product part as assembled: the shell, with the navigation the sitemap draws and every flow's screens. Each
    marker is filled once, from the shell's own text, so a flow can never hold one that captures another part."""
    nav, ids = [], set()
    for i in (i for i in sitemap.get("navigation", []) if isinstance(i, dict)):
        testid = base = f"app-nav-{_slug(str(i.get('label', '')))}"
        n = 1
        while testid in ids:  # two labels that read alike still get a test id each
            n += 1
            testid = f"{base}-{n}"
        ids.add(testid)
        nav.append(
            f'<button type="button" data-go="{html.escape(str(i.get("go", "")))}" data-component="tab" data-testid="{testid}"><span>{html.escape(str(i.get("label", "")))}</span></button>'
        )
    parts = {"navigation": "\n".join(nav), "screens": "\n".join(f.text for f in flows)}
    pattern = re.compile("|".join(re.escape(m) for m in MARKERS.values()))
    names = {m: k for k, m in MARKERS.items()}
    return pattern.sub(lambda m: parts[names[m.group(0)]], shell)


# What a feedback item asks: the kinds the viewer offers, and the one an older item without a kind reads as.
FEEDBACK_KINDS = ("change", "remove", "add", "question")
_ROUND_FILE = re.compile(r"^feedback-round-([0-9]{1,4})\.json$")
_ROUND_DIR = re.compile(r"^[0-9]{1,4}$")
# What a page carries, so a large folder never makes a large page: the newest rounds, each item's fields cut, and a
# total across every round.
MAX_ROUNDS, MAX_ITEMS, MAX_TEXT, MAX_TOTAL = 20, 200, 500, 200_000
MAX_FILE_BYTES = 1_000_000  # a feedback or changes file read at most this far: larger is left out, never read whole


def _plain(value: object) -> str:
    """A field's text: a string or a number as it reads, anything else (a list, an object, nesting) as nothing."""
    return str(value) if isinstance(value, str | int | float) and not isinstance(value, bool) else ""


def feedback_rounds(folder: Path) -> tuple[list[dict], list[str]]:
    """The earlier feedback rounds beside a design, for the viewer, and what could not be read: each
    `feedback-round-<N>.json` item (`{"round": N, "items": [{"id", "kind", "screen", "state", "testid", "note"}]}`), done
    once a later round's `rounds/<M>/changes.json` answers it (`{"changes": [{"answers": ["<item id>"]}]}`). A file of
    another shape is reported and skipped, never a crash; the newest rounds are kept."""
    problems: list[str] = []

    top = folder.resolve()

    def read(path: Path) -> dict:
        # Only a regular file inside the design folder, never through a link, and never larger than the cap.
        shown = path.relative_to(folder).as_posix()
        try:
            st = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(st.st_mode) or not path.resolve().is_relative_to(top):
                problems.append(f"{shown}: not a plain file in the design folder, so it is left out")
                return {}
            if st.st_size > MAX_FILE_BYTES:
                problems.append(f"{shown}: larger than {MAX_FILE_BYTES} bytes, so it is left out")
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            problems.append(f"{path.relative_to(folder).as_posix()}: not JSON ({type(exc).__name__}), so it is left out")
            return {}
        if not isinstance(data, dict):
            problems.append(f"{path.relative_to(folder).as_posix()}: not a JSON object, so it is left out")
            return {}
        return data

    def listed(data: dict, key: str, where: Path) -> list:
        value = data.get(key) or []
        if isinstance(value, list):
            return value
        problems.append(f"{where.relative_to(folder).as_posix()}: `{key}` is not a list, so it is left out")
        return []

    answered: dict[int, set[str]] = {}
    rounds_dir = folder / "rounds"
    found_dirs = [d for d in rounds_dir.iterdir() if _ROUND_DIR.match(d.name)] if rounds_dir.is_dir() and not rounds_dir.is_symlink() else []
    # The newest round folders only, so a folder of thousands is never read whole.
    for changes in [d / "changes.json" for d in sorted(found_dirs, key=lambda d: int(d.name))[-(MAX_ROUNDS + 1) :]]:
        if not changes.exists() and not changes.is_symlink():
            continue
        ids: set[str] = set()
        for c in listed(read(changes), "changes", changes):
            answers = c.get("answers") if isinstance(c, dict) else None
            if isinstance(answers, list):
                ids |= {str(a) for a in answers if isinstance(a, str | int)}
            else:
                problems.append(f"{changes.relative_to(folder).as_posix()}: a change's `answers` is not a list of item ids")
        answered[int(changes.parent.name)] = ids
    files: dict[int, Path] = {}
    for path in sorted(folder.glob("feedback-round-*.json")):
        if m := _ROUND_FILE.match(path.name):
            n = int(m.group(1))
            if n in files:
                problems.append(f"{path.name}: round {n} has another file, {files[n].name}, so this one is left out")
            else:
                files[n] = path
    found: list[dict] = []
    total = 0
    for n in sorted(files)[-MAX_ROUNDS:]:
        later = set().union(*(ids for r, ids in answered.items() if r > n))
        items = []
        for it in listed(read(files[n]), "items", files[n])[:MAX_ITEMS]:
            if not isinstance(it, dict) or not _plain(it.get("id")):
                continue
            kind = _plain(it.get("kind")) or "change"
            item = {
                **{k: _plain(it.get(k))[:MAX_TEXT] for k in ("id", "screen", "state", "testid", "note")},
                "kind": kind if kind in FEEDBACK_KINDS else "change",
                "done": _plain(it["id"]) in later,
            }
            total += sum(len(v) for v in item.values() if isinstance(v, str))
            if total > MAX_TOTAL:
                problems.append(f"the rounds hold more than {MAX_TOTAL} characters, so the rest is left out")
                break
            items.append(item)
        found.append({"round": n, "items": items})
        if total > MAX_TOTAL:
            break
    return found, problems


def assemble(sitemap: dict, shell: str, flows: list[Flow], rounds: tuple[list[dict], list[str]] = ([], [])) -> str:
    """The one clickable view: aidd's viewer, from the template, around the product: the shell, with the navigation
    drawn from the sitemap and every flow's screens, their ids and links qualified by the flow; the sitemap's example
    data; and the flows, for the review column and the Board."""
    product = str(sitemap.get("product") or "The product")
    data = sitemap.get("fixtures")
    fixtures = json.dumps({**(data if isinstance(data, dict) else {}), "product": product}, ensure_ascii=False, indent=2)
    config = json.dumps({"flows": [{"id": f.id, "title": f.title} for f in flows], "rounds": rounds[0], "round_problems": rounds[1]}, ensure_ascii=False)
    body = product_body(sitemap, shell, flows)
    return _in_viewer(
        _Page(
            body,
            fixtures,
            config,
            subtitle="The product prototype: every flow, kept current by each change",
            note="The product prototype, assembled by `aidd prototype` from docs/design/app/: change the sources, never this page.",
            title=f"{product}: product prototype",
        )
    )


@dataclass(frozen=True)
class _Page:
    """What one viewer page shows: the product part, its example data and flows (JSON), and its words."""

    body: str
    fixtures: str
    config: str
    subtitle: str
    note: str
    title: str


def _in_viewer(page_parts: _Page) -> str:
    """The viewer, as it stands beside this file, around a design, with its example data and its flows. The page's
    policy names the viewer's own script by hash, so nothing in the design can run."""
    template = (HERE / "viewer.html").read_text(encoding="utf-8")
    note = page_parts.note.replace("--", "- -")  # a comment holds no `--`
    values = {"title": html.escape(page_parts.title), "subtitle": html.escape(page_parts.subtitle), "note": html.escape(note)}
    for key in values:
        if template.count("{{" + key + "}}") != 1:
            raise ValueError(f"the viewer no longer has its {{{{{key}}}}}: the tool's files changed")
    template = re.sub(r"\{\{(title|subtitle|note)\}\}", lambda m: values[m.group(1)], template)
    steps = (
        (_FIXTURES, lambda m: m.group(1) + "\n" + _script_safe(page_parts.fixtures) + "\n" + m.group(3)),
        (_CONFIG, lambda m: m.group(1) + "\n" + _script_safe(page_parts.config) + "\n" + m.group(3)),
        (_POLICY, _fixed(_page_policy(template))),  # the viewer's own script, by hash, recomputed so it is never stale
        (_PRODUCT, lambda m: m.group(1) + page_parts.body + m.group(3)),  # last: nothing edits the page after the design is in it
    )
    page = template
    for found, replacement in steps:
        page, n = found.subn(replacement, page, count=1)
        if n != 1:
            raise ValueError(f"the viewer no longer has the part `{found.pattern[:40]}` the tool fills: the tool's files changed")
    return page


def view_prototype_file(root: Path, rel: str, write: bool = True) -> tuple[Path | None, list[str]]:
    """A Spec's or a flow's prototype file in the current viewer: (the view written, or None; the problems). The file is
    read, never changed, so one Spec approval froze stays as approved and still gets every fix to the viewer. The view
    goes only to `.aidd/views/`, under a name made from the file's path."""
    shown, text, problems = _design_source(root, rel)
    if problems:
        return None, problems
    # The rounds go only into a page written: a check never fails on a feedback file.
    page, problems = _design_page(text, shown, f"`aidd prototype {shown}`", feedback_rounds((root / rel).resolve().parent) if write else ([], []))
    if problems or page is None or not write:
        return None, problems
    target = _views(root) / f"prototype-{_slug(shown.removesuffix('.html'))}.html"
    target.write_text(page, encoding="utf-8")
    return target, []


def _design_source(root: Path, rel: str) -> tuple[str, str, list[str]]:
    """A prototype file read: (its path as shown, its text, and what keeps it from being read). It must be an .html file
    inside the repository, with a plain path."""
    base = root.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(base) or path.suffix != ".html" or not path.is_file():
        return rel, "", [f"{rel} is no prototype file in this repository: name one, such as specs/<ID>/design/prototype.html"]
    shown = path.relative_to(base).as_posix()
    if not _SAFE_PATH.match(shown):
        return shown, "", [f"{shown!r}: a prototype file's path takes letters, digits, `.`, `_`, `-`, and `/` only, so aidd can name it in the page"]
    try:
        return shown, path.read_text(encoding="utf-8"), []
    except (OSError, ValueError) as exc:
        return shown, "", [f"{shown} cannot be read ({exc}): save it as UTF-8 text"]


# What the safety reading says of a screen with no state: the design checks say it again, with its line.
_STATELESS = re.compile(r"^screen `[^`]*` has no state:")


def check_design_file(root: Path, rel: str) -> tuple[list[str], str]:
    """Everything wrong with a prototype file, and the line that says it is sound: (the problems, the ok line). It is the
    safety reading the page gets, then the design checks: links, states, test ids, names, and the prototype lint. A
    design the checks cannot read gets the safety reading's problems alone."""
    shown, text, problems = _design_source(root, rel)
    if problems:
        return problems, ""
    _, problems = _design_page(text, shown, f"`{BUILD} {shown}`")
    if spec_problem := _spec_of(shown, text)[1]:
        problems.append(spec_problem)
    if (data := _FIXTURES.search(text)) is not None:
        try:
            fixtures = json.loads(data.group(2))
        except ValueError:
            fixtures = {}
        if isinstance(fixtures, dict) and (product_problem := product_name_problem(fixtures.get("product"))):
            problems.append(product_problem)
    product = _PRODUCT.search(text)
    format_found = _DESIGN_FORMAT.search(text)
    if product is None or _newer(format_found.group(1) if format_found else 1):
        return problems, ""
    named = format_found.group(1) if format_found else "1"
    found, ok = design_checks.check(text, product.group(2), text.count("\n", 0, product.start(2)) + 1, shown, int(named) if named.isdigit() else 1)
    return [p for p in problems if not _STATELESS.match(p)] + found, ok


def screens_of(root: Path, rel: str | None, docs_dir: str = "docs") -> tuple[dict | None, list[str]]:
    """The screens of a prototype file, or of the product prototype, as data: (`{"format", "screens"}`, or None; the
    problems). Each screen has its id, title, parent, the state it opens in, and its states in order. A product screen's
    id is `<flow>:<screen>`, as its links name it."""
    if rel:
        shown, text, problems = _design_source(root, rel)
        product = _PRODUCT.search(text)
        if not problems and product is None:
            problems = [f'{shown} has no <template id="product">: it predates the prototype viewer, so read its screens by hand']
        if not problems and product is not None:
            _, problems = _design_page(text, shown, f"`{BUILD} screens {shown}`")  # the safety and format reading `check` gives
            problems = [p for p in problems if not _STATELESS.match(p)]  # a screen with no state is still listed, with no state
        if problems or product is None:
            return None, problems
        part = product.group(2)
    else:
        sitemap, shell, flows, problems = load(root, docs_dir)
        if not sitemap or not shell or problems:
            return None, [*problems, f"fix {docs_dir}/{APP}/ first: the screens are read only from a design that loads"]
        part = product_body(sitemap, shell, flows)
    return {"format": FORMAT, "screens": design_checks.screens_of(design_checks.read_design(part, rel or APP))}, []


def view_example(root: Path) -> Path:
    """The tool's showcase, a complete design to learn the format from, written to `.aidd/views/prototype-example.html`.
    It is shown, never copied into the project, so no design starts from its look."""
    page, problems = _design_page((HERE / "examples" / "showcase.html").read_text(encoding="utf-8"), "the showcase", "`aidd prototype --example`")
    if page is None:
        raise ValueError(f"the showcase has problems ({'; '.join(problems)}): the tool's files changed")
    target = _views(root) / "prototype-example.html"
    target.write_text(page, encoding="utf-8")
    return target


def _design_page(text: str, shown: str, command: str, rounds: tuple[list[dict], list[str]] = ([], [])) -> tuple[str | None, list[str]]:
    """A design's page in the viewer, or None with the problems that keep it from one."""
    format_found = _DESIGN_FORMAT.search(text)
    if newer := _newer(format_found.group(1) if format_found else 1):
        return None, [f"{shown} {newer}"]
    product = _PRODUCT.search(text)
    data = _FIXTURES.search(text)
    if not product or not data:
        return None, [f'{shown} has no <template id="product"> and fixtures block: it predates the prototype viewer, so open it as it is']
    try:
        json.loads(data.group(2))
    except ValueError as exc:
        return None, [f"{shown}: its fixtures block is not JSON ({exc})"]
    check_part = _Sections("", product.group(2), shell=True, label=shown)
    check_part.read()
    if _HANDLER.search(product.group(2)) and not any(w.startswith("an event handler") for w in check_part.forbidden):
        check_part.forbidden.append("an event handler: the viewer holds the one runtime")
    problems = [f"{shown} holds {what}" for what in dict.fromkeys(check_part.forbidden)] + list(dict.fromkeys(check_part.problems))
    named = _TITLE.search(text)
    title = html.unescape(re.sub(r"</?title>", "", named.group(0), flags=re.I)) if named else shown
    if problems:
        return None, problems
    spec = _spec_of(shown, text)[0]
    page = _in_viewer(
        _Page(
            product.group(2),
            data.group(2).strip(),
            json.dumps(
                {"flows": [], "spec": spec, "design": shown if _SAFE_PATH.match(shown) else "", "rounds": rounds[0], "round_problems": rounds[1]},
                ensure_ascii=False,
            ),
            subtitle=shown,
            note=f"A view of {shown} in the current viewer, written by {command}: change the design, never this page.",
            title=title,
        )
    )
    return page, []


def _spec_of(shown: str, text: str) -> tuple[str, str]:
    """The Spec a design is for, and what is wrong with the way it says so: (the id, or "" when none; the problem, or ""). Only
    the head names it, before the product's template, and only an id the design's own folder shows. A name that is no id, such
    as a sketch's, is no Spec and no problem; an id the folder does not show is neither used nor let pass in `check`."""
    found = _SPEC_META.search(text.split('<template id="product">', 1)[0])
    named = html.unescape(found.group(1)) if found else ""
    if not _SPEC_ID.fullmatch(named):
        return "", ""
    in_path = _SPEC_IN_PATH.search(shown)
    if in_path and in_path.group(1).upper() == named.upper():
        return named.upper(), ""
    where = f"the folder names {in_path.group(1)}" if in_path else "the path names no Spec"
    return "", f"{_q(shown)} says it is the design of {_q(named)}, but {where}: put it in specs/{named.upper()}/design/, or name its own Spec"


def _newer(found: object) -> str:
    """Why a design's format is one this tool cannot read, or nothing."""
    try:
        number = int(str(found))
    except ValueError:
        return f"names the design format {found!r}, which is no number: write {FORMAT}"
    return f"is design format {number}, newer than this tool's {FORMAT}: update aidd-team" if number > FORMAT else ""


def _views(root: Path) -> Path:
    """`.aidd/views/`, where every page goes. The folder ignores itself in git, so a page is never committed, with or
    without aidd, and nothing else under `.aidd/` (aidd's config, once a project adopts it) is hidden."""
    folder = root / ".aidd" / "views"
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".gitignore").exists():
        (folder / ".gitignore").write_text("*\n", encoding="utf-8")
    return folder


def _script_safe(text: str) -> str:
    """JSON for a script block: no `<`, `>`, or `&` reaches the HTML parser, so no value can close the block."""
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def build_product_prototype(root: Path, docs_dir: str = "docs", write: bool = True) -> tuple[Path | None, list[str]]:
    """Assemble the product prototype and check it: (the view written, or None when a source cannot be read, the shell is
    not the template's, or `write` is off; the problems). The view goes only to `.aidd/views/prototype.html`, aidd's
    output folder, so no source decides where a file is written."""
    sitemap, shell, flows, problems = load(root, docs_dir)
    if not sitemap or not shell:
        if write:
            (root / VIEW).unlink(missing_ok=True)
        return None, problems
    problems += check(sitemap, flows)
    if not write or any(p.startswith(SHELL) for p in problems) or any(f.forbidden for f in flows):
        if write:
            (root / VIEW).unlink(missing_ok=True)  # an old page would show what the sources no longer say
        return None, problems
    target = _views(root) / Path(VIEW).name
    target.write_text(assemble(sitemap, shell, flows, feedback_rounds(root / docs_dir / APP)), encoding="utf-8")
    return target, problems


# The component contract: every part the design names, so the built UI's components and stories match it by name.


class _Parts(HTMLParser):
    """Each `data-component` a design names: its variant, the screen it sits on, and its test id."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str, str, str]] = []  # (component, variant, screen, test id)
        self._screens: list[tuple[int, str]] = []  # (depth, screen), while inside one
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in reversed(attrs)}
        if tag not in _VOID:
            self._depth += 1
        if tag == "section" and a.get("data-screen"):
            self._screens.append((self._depth, a["data-screen"]))
        if a.get("data-component"):
            screen = self._screens[-1][1] if self._screens else ""
            self.found.append((a["data-component"], a.get("data-variant") or "default", screen, a.get("data-testid", "")))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if self._screens and self._screens[-1][0] == self._depth and tag == "section":
            self._screens.pop()
        self._depth = max(0, self._depth - 1)


def component_contract(parts: list[str]) -> dict:
    """The contract of the design `parts` (markup, as assembled): each component's variants, the screens that use it
    (none: the chrome, on every screen), and its test ids, sorted, so the same design always gives the same file."""
    found: dict[str, dict[str, set[str]]] = {}
    for part in parts:
        reader = _Parts()
        reader.feed(part)
        reader.close()
        for name, variant, screen, testid in reader.found:
            entry = found.setdefault(name, {"variants": set(), "screens": set(), "testids": set()})
            entry["variants"].add(variant)
            if screen:
                entry["screens"].add(screen)
            if testid:
                entry["testids"].add(testid)
    return {"format": FORMAT, "components": [{"name": name, **{k: sorted(v) for k, v in entry.items()}} for name, entry in sorted(found.items())]}


def contract_of(root: Path, rel: str | None, docs_dir: str = "docs") -> tuple[dict | None, list[str]]:
    """The contract of a prototype file, or of the product prototype: (the contract, or None; the problems)."""
    if rel:
        _, problems = view_prototype_file(root, rel, write=False)  # the same checks the page gets
        if problems:
            return None, [*problems, f"fix {rel} first: a contract is read only from a design with no problem"]
        found = _PRODUCT.search((root / rel).read_text(encoding="utf-8"))
        assert found is not None  # view_prototype_file found it
        return component_contract([found.group(2)]), []
    sitemap, shell, flows, problems = load(root, docs_dir)
    if not sitemap or not shell or problems:
        return None, [*problems, f"fix {docs_dir}/{APP}/ first: a contract is read only from a design with no problem"]
    return component_contract([product_body(sitemap, shell, flows)]), []


def kebab(text: str) -> str:
    """A name as the contract writes it: `NoteCard` and `Note card` are `note-card`."""
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", text).lower()).strip("-")


def stories_of(index: object) -> set[tuple[str, str]]:
    """Each story in Storybook's `index.json` (version 4 and later: `entries`; version 3: `stories`) as (component,
    variant): the last part of its title and its name, kebab-cased, so `Components/NoteCard` / `Compact` is
    (`note-card`, `compact`). A story with no title or name falls back to its id, `<title>--<name>`."""
    if not isinstance(index, dict):
        raise ValueError("it holds no JSON object")
    entries = index["entries"] if "entries" in index else index.get("stories", {})
    if not isinstance(entries, dict):
        raise ValueError("its entries are no JSON object")
    found = set()
    for key, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("type", "story") != "story":
            continue
        title, _, name = str(entry.get("id", key)).partition("--")
        found.add((kebab(str(entry.get("title") or title).split("/")[-1]), kebab(str(entry.get("name") or name))))
    return found


def missing_stories(contract: dict, stories: set[tuple[str, str]]) -> list[str]:
    """Each component variant with no story of its own: a story whose title ends with the component's name and whose
    name is the variant (`Components/NoteCard`, `Compact` for `note-card` / `compact`)."""
    return [
        f"component `{c['name']}` has no story for its `{variant}` variant: add one titled `.../{c['name']}` (or set the CSF `title` so it ends so) and named `{variant}`"
        for c in contract["components"]
        for variant in c["variants"]
        if (c["name"], variant) not in stories
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prototype.py", description="aidd-team's prototype tool: show a design in the viewer, check it, and read its component contract."
    )
    parser.add_argument("--docs", default="docs", help="the documentation folder that holds design/app/ (default: docs)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, what in (
        ("build", "write the design's page in the viewer to .aidd/views/, and print its problems"),
        ("check", "check the design and write nothing: report every problem with its line, and exit 1 on any"),
        ("components", "print the design's component contract as JSON"),
        ("screens", "print the design's screens as JSON: each one's id, title, parent, first state, and states in order"),
    ):
        command = commands.add_parser(name, help=what)
        command.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
        if name == "build":
            command.add_argument("--open", action="store_true", help="open the written page in your browser")
    stories = commands.add_parser("stories", help="check Storybook's index.json against the component contract: exit 1 on a missing story")
    stories.add_argument("index", help="Storybook's index.json, from `storybook build` (storybook-static/index.json)")
    stories.add_argument("file", nargs="?", help="a prototype file; the product prototype when absent")
    new = commands.add_parser("new-product", help="start the product prototype in <docs>/design/app/")
    new.add_argument("--name", default="", help="the product's name")
    example = commands.add_parser("example", help="write the tool's showcase, a complete design to learn from, to .aidd/views/")
    example.add_argument("--open", action="store_true", help="open the written page in your browser")
    design = commands.add_parser("new-design", help="start a design file, such as an exploration's sketch, from the starting design")
    design.add_argument("file", help="where to write it, such as directions/a.html")
    design.add_argument("--title", default="A direction", help="what it shows")
    return parser


def new_design(root: Path, rel: str, title: str, today: dt.date | None = None) -> Path:
    """A design file from the starting design, with its placeholders filled. Refuses a file that exists."""
    path = root / rel
    if path.exists():
        raise FileExistsError(f"{rel} exists: open it with `{BUILD} {rel}`")
    text = with_project_tokens((HERE / "design.html").read_text(encoding="utf-8"), root)
    values = {"spec": "a sketch", "title": html.escape(title), "spec_link": "#", "today": (today or dt.date.today()).isoformat(), "path": rel}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(re.sub(r"\{\{(spec|title|spec_link|today|path)\}\}", lambda m: values[m.group(1)], text), encoding="utf-8")
    return path


def _contract_command(root: Path, args: argparse.Namespace) -> int:
    """`components` prints the contract; `stories` checks Storybook's index.json against it."""
    contract, problems = contract_of(root, args.file, args.docs)
    if contract is None:
        for problem in problems:
            print(f"problem: {problem}")
        return 1
    if args.command == "components":
        print(json.dumps(contract, indent=2))
        return 0
    try:
        stories = stories_of(json.loads(Path(args.index).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"problem: {args.index} cannot be read ({exc}): run `storybook build`, then name its index.json")
        return 1
    missing = missing_stories(contract, stories)
    print("\n".join(f"problem: {m}" for m in missing) or f"every component variant has a story ({len(stories)} stories read)")
    return 1 if missing else 0


def problems_line(count: int, where: str) -> str:
    """The line that closes a check with problems: how many, and the file or folder to fix them in."""
    return f"{count} problem(s); fix them in {where}"


def file_url(path: Path) -> str:
    """The address a browser opens a written page at: its `file://` URL."""
    return path.resolve().as_uri()


def open_page(path: Path) -> str:
    """Open a written page in the person's browser, and the line to print: where no browser can open, such as a
    headless session, the line names the address printed above instead."""
    try:
        opened = webbrowser.open(file_url(path))
    except webbrowser.Error:
        opened = False
    return "opened it in your browser" if opened else "no browser opened here: open the address above"


def _screens_command(root: Path, args: argparse.Namespace) -> int:
    """`screens` prints the design's screens as JSON, for the screenshot loop and agents to read instead of the HTML."""
    found, problems = screens_of(root, args.file, args.docs)
    for problem in problems:
        print(f"problem: {problem}")
    if found is not None:
        print(json.dumps(found, indent=2))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    """The command line: `build`, `check`, `components`, `screens`, `stories`, `example`, `new-design`, and `new-product`,
    on a prototype file or the product prototype."""
    args = _parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "example":
        page = view_example(root)
        print(f"wrote {page.relative_to(root).as_posix()}: open it in a browser\n{file_url(page)}")
        if args.open:
            print(open_page(page))
        return 0
    if args.command == "new-design":
        shown = new_design(root, args.file, args.title).relative_to(root).as_posix()
        print(f"{shown}\nnext: sketch the direction in it, then `{BUILD} {shown}` to see it")
        return 0
    if args.command == "new-product":
        for path in new_product_prototype(root, docs_dir=args.docs, product=args.name):
            print(path.relative_to(root).as_posix())
        return 0
    if args.command in ("components", "stories"):
        return _contract_command(root, args)
    if args.command == "screens":
        return _screens_command(root, args)
    if args.command == "check" and args.file:
        problems, ok = check_design_file(root, args.file)
        print("\n".join(f"problem: {problem}" for problem in problems) or ok)
        if problems:
            print(problems_line(len(problems), args.file))
        return 1 if problems else 0
    write = args.command == "build"
    out, problems = view_prototype_file(root, args.file, write=write) if args.file else build_product_prototype(root, args.docs, write=write)
    for problem in problems:
        print(f"problem: {problem}")
    if out:
        print(f"wrote {out.relative_to(root).as_posix()}: open it in a browser\n{file_url(out)}")
        if getattr(args, "open", False):
            print(open_page(out))
    return 1 if problems else 0


if __name__ == "__main__":
    BUILD = f"python3 {Path(__file__).as_posix()} build"  # run directly: messages name this file, never `aidd prototype`
    raise SystemExit(main())
