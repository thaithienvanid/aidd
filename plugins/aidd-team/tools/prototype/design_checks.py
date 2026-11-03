"""The prototype tool's design checks: what a design file must hold to be sound, each problem with its line.

This file sits beside `prototype.py` and belongs to the same tool. It uses the standard library only, so the tool runs
wherever Python 3.11 does, with aidd or without it. It owns four things:

- the screens a design draws, with their states, parent, and first state (`screens`), which agents read instead of
  parsing the HTML themselves;
- the integrity of those screens: every link, parent, and first state names a thing the design has, every interactive
  element has a test id, no test id repeats in one state, and the first screen reaches every other;
- the names a control needs, so a screen reader and a test can find it;
- the lint rules `skills/prototyping/references/prototype-screenshots.md` lists as shell commands, in Python. The
  reference keeps its commands; these are the same rules for a person who has no Node or grep.

Text from the design is data. Nothing here runs it, and a placeholder such as `{{spec}}` in a starting design is skipped.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Elements with no end tag (the HTML standard's void elements), so they never open a level.
VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())
# A design nested deeper than this is refused, so a hostile one cannot take time in proportion to its depth for each tag.
MAX_DEPTH = 400
INTERACTIVE = frozenset(("button", "a", "input", "select", "textarea"))
# The attributes that name a control. A button or a link is also named by its text.
_NAMES = ("aria-label", "aria-labelledby", "title")
# An input of these types is named by its value.
_BUTTON_INPUTS = ("button", "submit", "reset")
_LINK_ATTRIBUTES = ("data-go", "data-item-go")


@dataclass
class Screen:
    id: str
    title: str
    line: int
    parent: str | None = None  # data-parent, or None when the screen has none
    initial: str | None = None  # data-initial, or None when the screen names none
    states: list[str] = field(default_factory=list)  # in the order the screen draws them

    def opens_in(self) -> str | None:
        """The state the viewer opens first: the declared one when the screen has it, else its first state."""
        if self.initial in self.states:
            return self.initial
        return self.states[0] if self.states else None


@dataclass(frozen=True)
class _Link:
    attribute: str
    value: str
    line: int
    screen: str  # the screen it sits on, or "" in the chrome around the screens


@dataclass(frozen=True)
class _TestId:
    name: str
    line: int
    screen: str  # "" in the chrome, which shows on every screen
    state: str  # "" when it sits on the screen outside any state, which shows in every state
    in_template: bool  # in a list's item template, which the viewer repeats for each item


@dataclass
class _Open:
    """An element the reader has opened and not yet closed."""

    tag: str
    attrs: dict[str, str]
    line: int
    screen: Screen | None = None  # when it is a screen's <section>
    state: str = ""  # when it is a state, directly inside a screen
    interactive: bool = False
    named: bool = False
    # What the element inherits from its parents, kept here so each step of the reading costs the same on a deep design.
    hidden: bool = False  # it or a parent has aria-hidden="true"
    in_template: bool = False
    in_label: bool = False
    context: tuple[str, str] = ("", "")  # the screen it sits on and the state it is in


class DesignReader(HTMLParser):
    """The screens, links, test ids, and unnamed controls of a design's product part, read as a browser reads them."""

    def __init__(self, label: str, first_line: int = 1) -> None:
        super().__init__(convert_charrefs=True)
        self.label = label  # the file the messages name
        self._offset = first_line - 1  # the product part starts on this line of the file
        self.screens: list[Screen] = []
        self.problems: list[tuple[int, str]] = []  # (line, message) for the problems the reading finds alone
        self.links: list[_Link] = []
        self.test_ids: list[_TestId] = []
        self._stack: list[_Open] = []
        self._controls: list[_Open] = []  # the open buttons and links with no name yet
        self.too_deep = False
        self._fields: list[tuple[str, int, str, bool]] = []  # (tag, line, id, named by its own attributes or a wrapping label)
        self._label_targets: set[str] = set()

    def finish(self) -> None:
        """Read to the end, then settle what needed the whole design: the labels that name a field."""
        self.close()
        if self.too_deep:
            return
        for entry in reversed(self._stack):
            self._close(entry)
        self._stack.clear()
        for tag, line, ident, named in self._fields:
            if not named and ident not in self._label_targets:
                self._problem(line, f'<{tag}> has no label; add <label for="..."> with its id, or an aria-label')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.too_deep:
            return
        a: dict[str, str] = {}
        for name, value in attrs:
            a.setdefault(name, value or "")  # a browser keeps an attribute's first value
        line = self.getpos()[0] + self._offset
        if len(self._stack) >= MAX_DEPTH:
            self.too_deep = True
            self.problems.clear()  # what was read so far is a fragment of the design; the depth is the one thing to fix
            self._problem(line, f"the design nests elements more than {MAX_DEPTH} levels deep; flatten the markup, as a person reads no screen that deep")
            return
        entry = _Open(tag, a, line)
        parent = self._stack[-1] if self._stack else None
        if tag == "section" and a.get("data-screen"):
            entry.screen = Screen(a["data-screen"], a.get("data-title") or a["data-screen"], line, a.get("data-parent"), a.get("data-initial"))
            self.screens.append(entry.screen)
        if "data-state" in a and parent is not None and parent.screen is not None:
            parent.screen.states.append(a["data-state"])
            entry.state = a["data-state"]
        entry.hidden = (parent is not None and parent.hidden) or a.get("aria-hidden") == "true"
        entry.in_template = (parent is not None and parent.in_template) or (tag == "template" and bool(a.get("data-item-template")))
        entry.in_label = (parent is not None and parent.in_label) or tag == "label"
        entry.context = self._context(entry, parent)
        screen, state = entry.context
        for attribute in _LINK_ATTRIBUTES:
            if attribute in a:
                self.links.append(_Link(attribute, a[attribute], line, screen))
        if a.get("data-testid", "").strip():
            self.test_ids.append(_TestId(a["data-testid"].strip(), line, screen, state, entry.in_template))
        if tag == "label" and a.get("for"):
            self._label_targets.add(a["for"])
        self._note_control(entry)
        if tag not in VOID:
            self._stack.append(entry)
            if entry.interactive and not entry.named:
                self._controls.append(entry)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.too_deep:
            return
        # HTML ignores `/>` except inside SVG and MathML, where it closes the element.
        self.handle_starttag(tag, attrs)
        if tag not in VOID and any(e.tag in ("svg", "math") for e in self._stack):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.too_deep:
            return
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                for entry in reversed(self._stack[i:]):
                    self._close(entry)
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if self.too_deep or not data.strip() or (self._stack and self._stack[-1].hidden):
            return
        if self._stack and self._stack[-1].tag in ("style", "script"):
            return
        self._name_open_controls(None)

    @staticmethod
    def _context(entry: _Open, parent: _Open | None) -> tuple[str, str]:
        """The screen an element sits on and the state it is in; both empty in the chrome around the screens."""
        if entry.screen is not None:
            return entry.screen.id, ""
        if parent is None:
            return "", ""
        if parent.screen is not None:
            return parent.screen.id, entry.state
        return parent.context

    def _problem(self, line: int, message: str) -> None:
        self.problems.append((line, message))

    def _name_open_controls(self, entry: _Open | None) -> None:
        """Mark every open button and link named: text, a runtime fill, or an image with its alt sits inside it."""
        for e in self._controls:
            e.named = True
        self._controls.clear()
        if entry is not None and entry.interactive:
            entry.named = True

    def _note_control(self, entry: _Open) -> None:
        tag, a, line = entry.tag, entry.attrs, entry.line
        if tag == "img" and "alt" not in a and a.get("role") not in ("presentation", "none"):
            self._problem(line, '<img> has no alt; describe the image, or write alt="" if it only decorates')
        entry.interactive = tag in INTERACTIVE and not (tag == "input" and a.get("type", "").lower() == "hidden")
        if not entry.hidden and ("data-text" in a or "data-field" in a or a.get("alt", "").strip() or any(a.get(k, "").strip() for k in _NAMES[:2])):
            self._name_open_controls(entry)  # a runtime fill, an image's alt, or a label inside the control names it
        if not entry.interactive:
            return
        by_attribute = any(a.get(k, "").strip() for k in _NAMES) or (
            tag == "input" and a.get("type", "").lower() in _BUTTON_INPUTS and bool(a.get("value", "").strip())
        )
        if tag in ("button", "a"):
            entry.named = entry.named or by_attribute
        else:
            self._fields.append((tag, line, a.get("id", ""), by_attribute or entry.in_label))
        if not a.get("data-testid", "").strip():
            self._problem(line, f'<{tag}> has no data-testid; add one a test can select, such as data-testid="<screen>-<what-it-does>"')

    def _close(self, entry: _Open) -> None:
        if self._controls and self._controls[-1] is entry:
            self._controls.pop()
        if entry.interactive and entry.tag in ("button", "a") and not entry.named:
            self._problem(entry.line, f"<{entry.tag}> has no name; put text inside it, or add an aria-label")


def read_design(markup: str, label: str, first_line: int = 1) -> DesignReader:
    """Read a design's product part. `first_line` is the line of the file where `markup` starts."""
    reader = DesignReader(label, first_line)
    reader.feed(markup)
    reader.finish()
    return reader


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


_UNSAFE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_QUOTE_LIMIT = 80
_LIST_LIMIT = 10  # a message lists this many options, then says how many more
_SUGGEST_LIMIT = 300  # past this many options, the closest-name search is skipped, because it costs time for each one
_PROBLEM_LIMIT = 200  # `check` prints this many problems, then says how many more


def quoted(value: str) -> str:
    """A value from the design, as a message may print it: no control character, so a design cannot erase a line of the
    terminal or print a false `ok:`, and no more than 80 characters."""
    clean = _UNSAFE.sub("", value)
    return clean if len(clean) <= _QUOTE_LIMIT else clean[: _QUOTE_LIMIT - 1] + "…"


def _choose(name: str, options: list[str], kind: str) -> str:
    """What to do about a name that matches nothing: the closest option, when one is near, and the list."""
    if not options:
        return f"this design draws no {kind} to name"
    near = difflib.get_close_matches(name, options, n=1) if len(options) <= _SUGGEST_LIMIT else []
    listed = ", ".join(quoted(o) for o in options[:_LIST_LIMIT])
    if len(options) > _LIST_LIMIT:
        listed += f", and {len(options) - _LIST_LIMIT} more"
    return f"did you mean `{quoted(near[0])}`? Name one of {listed}" if near else f"name one of {listed}"


def integrity_problems(reader: DesignReader) -> list[tuple[int, str]]:
    """What breaks a design's own consistency, each as (line, message): a link, a parent, or a first state that names
    nothing, a screen without a state, a test id used twice in a state, and a screen the first one never reaches."""
    found = list(reader.problems)
    if reader.too_deep:
        return found  # the reading stopped at the depth limit, so the screens it holds are not the design's
    by_id: dict[str, Screen] = {}
    for screen in reader.screens:
        if screen.id in by_id:
            found.append((screen.line, f"screen `{quoted(screen.id)}` repeats the screen on line {by_id[screen.id].line}; give each screen its own id"))
        else:
            by_id[screen.id] = screen
        if not screen.states:
            found.append(
                (screen.line, f'screen `{quoted(screen.id)}` has no state; wrap its content in <div data-state="success"> (or empty, loading, error, ...)')
            )
        elif screen.initial is not None and screen.initial not in screen.states:
            found.append(
                (
                    screen.line,
                    f'data-initial="{quoted(screen.initial)}" names no state of `{quoted(screen.id)}`; {_choose(screen.initial, screen.states, "state")}',
                )
            )
    names = list(by_id)
    if not reader.screens:
        found.append((1, 'the design draws no screen; add <section data-screen="<id>" data-title="..."> with a state inside it'))
    for screen in reader.screens:
        if screen.parent is not None and screen.parent not in by_id:
            found.append(
                (
                    screen.line,
                    f'data-parent="{quoted(screen.parent)}" on screen `{quoted(screen.id)}` names no screen; {_choose(screen.parent, names, "screen")}',
                )
            )
    edges: dict[str, set[str]] = {}
    for link in reader.links:
        if "{{" in link.value:
            continue  # a placeholder in a starting design, filled when the design is written
        target, _, state = link.value.partition("/")
        if target not in by_id:
            found.append((link.line, f'{link.attribute}="{quoted(link.value)}" names no screen; {_choose(target, names, "screen")}'))
        elif state and state not in by_id[target].states:
            found.append(
                (link.line, f'{link.attribute}="{quoted(link.value)}" names no state of `{quoted(target)}`; {_choose(state, by_id[target].states, "state")}')
            )
        else:
            edges.setdefault(link.screen, set()).add(target)
    found += _repeats(reader)
    found += _unreached(reader, edges)
    return found


def _repeats(reader: DesignReader) -> list[tuple[int, str]]:
    """A test id used twice in one state, as the person sees that state: the chrome, the screen outside any state, and the
    state itself. A list's item template repeats once for each item, so it is left out."""
    found: dict[tuple[int, str], int] = {}
    for screen in reader.screens:
        for state in screen.states or [""]:
            first: dict[str, _TestId] = {}
            for test_id in reader.test_ids:
                if test_id.in_template or (test_id.screen and (test_id.screen != screen.id or (test_id.state and test_id.state != state))):
                    continue
                earlier = first.setdefault(test_id.name, test_id)
                if earlier is not test_id:
                    found[(test_id.line, test_id.name)] = earlier.line
    return [
        (line, f'data-testid="{quoted(name)}" repeats the one on line {first_line} in the same state; give each element its own test id')
        for (line, name), first_line in found.items()
    ]


def _unreached(reader: DesignReader, edges: dict[str, set[str]]) -> list[tuple[int, str]]:
    """The screens no chain of links from the first screen opens. A link in the chrome, such as a tab, is on every screen."""
    if len(reader.screens) < 2:
        return []
    first = reader.screens[0]
    chrome = edges.get("", set())
    reached, todo = {first.id}, [first.id]
    while todo:
        for nxt in (edges.get(todo.pop(), set()) | chrome) - reached:
            reached.add(nxt)
            todo.append(nxt)
    return [
        (
            s.line,
            f"screen `{quoted(s.id)}` is not reached from the first screen, `{quoted(first.id)}`, by any data-go; link to it from a screen or from the navigation",
        )
        for s in reader.screens
        if s.id not in reached
    ]


def screens_of(reader: DesignReader) -> list[dict]:
    """The screens as data, in the order the design draws them: what an agent reads instead of parsing the HTML."""
    return [{"id": s.id, "title": s.title, "parent": s.parent, "initial": s.opens_in(), "states": s.states} for s in reader.screens]


def summary(reader: DesignReader) -> str:
    """The one line that says a design is sound, with what it holds."""
    states = sum(len(s.states) for s in reader.screens)
    names = {t.name for t in reader.test_ids}
    return f"ok: {_plural(len(reader.screens), 'screen')}, {_plural(states, 'state')}, {_plural(len(names), 'test id')}"


# The prototype lint, the rules `prototype-screenshots.md` lists as shell commands, here as Python over the whole file.
_TOKENS_START = re.compile(r'<style id="tokens">')
_TOKENS_END = re.compile(r"</style>")
# The color rule reads one CSS declaration at a time, so it takes time in proportion to the line: a declaration ends at `;`,
# `"`, or `}`; a property name is a run of lowercase letters and dashes that ends at `:`; a raw color is a hex code or a
# color function after it.
_DECLARATION = re.compile(r'[^;"}]+')
_PROPERTY = re.compile(r"(?<![a-z-])[a-z-]+: *")
_COLOR_PROPERTIES = ("color", "background", "border", "fill", "stroke", "outline", "shadow")
_COLOR_VALUE = re.compile(r"#[0-9a-fA-F]{3,8}\b|(rgb|hsl|hwb|lab|lch|oklab|oklch|color)a?\(")
_HOTLINK = re.compile(r"""(src|href)=["']https?://|url\(["']?https?://|@import +url\(""")
_ADDRESS = re.compile(r"""https?://[^\s"')>]+""")
_PLACEHOLDER = re.compile(r"lorem ipsum|dolor sit amet|\bTODO\b|\bFIXME\b|\bTBD\b|john doe|jane doe|placeholder text", re.I)
# Unicode's Extended_Pictographic, less (c), (r), and (tm), which the lint allows: the ranges of emoji-data.txt.
_PICTOGRAPHS = (
    (0x203C, 0x203C), (0x2049, 0x2049), (0x2139, 0x2139), (0x2194, 0x2199), (0x21A9, 0x21AA), (0x231A, 0x231B), (0x2328, 0x2328),
    (0x2388, 0x2388), (0x23CF, 0x23CF), (0x23E9, 0x23F3), (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25AB), (0x25B6, 0x25B6),
    (0x25C0, 0x25C0), (0x25FB, 0x25FE), (0x2600, 0x2605), (0x2607, 0x2612), (0x2614, 0x2685), (0x2690, 0x2705), (0x2708, 0x2712),
    (0x2714, 0x2714), (0x2716, 0x2716), (0x271D, 0x271D), (0x2721, 0x2721), (0x2728, 0x2728), (0x2733, 0x2734), (0x2744, 0x2744),
    (0x2747, 0x2747), (0x274C, 0x274C), (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757), (0x2763, 0x2767), (0x2795, 0x2797),
    (0x27A1, 0x27A1), (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B07), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55), (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299), (0x1F000, 0x1F0FF), (0x1F10D, 0x1F10F),
    (0x1F12F, 0x1F12F), (0x1F16C, 0x1F171), (0x1F17E, 0x1F17F), (0x1F18E, 0x1F18E), (0x1F191, 0x1F19A), (0x1F1AD, 0x1F1E5),
    (0x1F201, 0x1F20F), (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F), (0x1F232, 0x1F23A), (0x1F23C, 0x1F23F), (0x1F249, 0x1F3FA),
    (0x1F400, 0x1F53D), (0x1F546, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F774, 0x1F77F), (0x1F7D5, 0x1F7FF), (0x1F80C, 0x1F80F),
    (0x1F848, 0x1F84F), (0x1F85A, 0x1F85F), (0x1F888, 0x1F88F), (0x1F8AE, 0x1F8FF), (0x1F90C, 0x1F93A), (0x1F93C, 0x1F945),
    (0x1F947, 0x1FAFF), (0x1FC00, 0x1FFFD),
)  # fmt: skip
_EMOJI = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _PICTOGRAPHS) + "]")


def _raw_color(line: str) -> int | None:
    """Where in the line the property of the first raw color starts, or None when the line has none."""
    for declaration in _DECLARATION.finditer(line):
        text = declaration.group(0)
        for prop in _PROPERTY.finditer(text):
            if any(word in prop.group(0) for word in _COLOR_PROPERTIES):
                # The first color property has the longest rest of the declaration, so no later one in it can match when it does
                # not: one bounded search for each declaration, then the next declaration.
                if _COLOR_VALUE.search(text, prop.end()):
                    return declaration.start() + prop.start()
                break
    return None


def _declaration(line: str, start: int) -> str:
    """The CSS declaration a raw color sits in, from its property name to its `;`, cut short for a message."""
    before = line[:start]
    name = before[len(before.rstrip("abcdefghijklmnopqrstuvwxyz-")) :]
    rest = re.match(r'[^;"}]*', line[start:])
    return (name + (rest.group(0) if rest else "")).strip()[:70]


# The design format each rule family arrived in. Spec approval freezes a design and the command that checks it, so an
# aidd upgrade must never turn an approved design red: `check` applies only the families of the format the design names,
# and shows a newer family's findings as notes. A new rule after 1.0.0 is a new family at a new format, and a design takes
# it through its own change.
RULE_FORMATS = {"integrity": 1, "raw-color": 1, "hotlink": 1, "placeholder": 1, "emoji": 1}


def lint_problems(text: str) -> list[tuple[int, str]]:
    """The prototype lint over the whole design file, each problem as (line, message): a raw color outside the tokens
    block, a hotlinked image or font, placeholder text, and an emoji used as an icon."""
    return [(line, message) for line, message, _ in _lint(text)]


def _lint(text: str) -> list[tuple[int, str, str]]:
    """The lint's problems, each as (line, message, rule family)."""
    found: list[tuple[int, str, str]] = []
    in_tokens = False
    for number, line in enumerate(text.split("\n"), 1):
        # The color rule skips the tokens block, which holds the generated roles; the other rules read every line.
        if not in_tokens and (start := _TOKENS_START.search(line)):
            in_tokens = _TOKENS_END.search(line, start.end()) is None
        elif in_tokens:
            in_tokens = _TOKENS_END.search(line) is None
        elif (color := _raw_color(line)) is not None:
            found.append(
                (
                    number,
                    f'the raw color in "{quoted(_declaration(line, color))}" is outside the tokens block; read a role with var(), such as var(--color-accent)',
                    "raw-color",
                )
            )
        if link := _HOTLINK.search(line):
            address = _ADDRESS.search(line)
            found.append(
                (
                    number,
                    f"{quoted(address.group(0) if address else link.group(0))} loads from the network; keep the image or font in the design, as its Content-Security-Policy requires",
                    "hotlink",
                )
            )
        if word := _PLACEHOLDER.search(line):
            found.append((number, f'placeholder text "{word.group(0)}"; write the real copy a person would read', "placeholder"))
        if emoji := _EMOJI.search(line):
            found.append(
                (number, f'the emoji {emoji.group(0)} is not an icon; draw it from the system\'s icon set, with a name or aria-hidden="true"', "emoji")
            )
    return found


def check(text: str, product: str, first_line: int, label: str, design_format: int = 1) -> tuple[list[str], str]:
    """A design file's problems and its ok line. `product` is the markup of its <template id="product"> and `first_line`
    the file's line where it starts. Each problem names the file and the line, and says what to change. A rule family
    newer than `design_format` reports only as a note under the ok line, so an upgrade never fails an approved design."""
    reader = read_design(product, label, first_line)
    every = sorted([*((line, message, "integrity") for line, message in integrity_problems(reader)), *_lint(text)], key=lambda item: item[0])
    found = [(line, message) for line, message, rule in every if RULE_FORMATS[rule] <= design_format]
    newer = [(line, message, rule) for line, message, rule in every if RULE_FORMATS[rule] > design_format]
    lines = [f"{label}:{line}: {message}" for line, message in found[:_PROBLEM_LIMIT]]
    if len(found) > _PROBLEM_LIMIT:
        lines.append(f"{label}: and {len(found) - _PROBLEM_LIMIT} more problems; fix these, then check again")
    notes = [
        f"note: {label}:{line}: format {RULE_FORMATS[rule]} would flag this, and the design is format {design_format}: {message}"
        for line, message, rule in newer[:_LIST_LIMIT]
    ]
    return lines, "\n".join([summary(reader), *notes])
