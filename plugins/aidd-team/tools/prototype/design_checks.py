"""The prototype tool's design checks: what a design file must hold to be sound, each problem with its line.

This file sits beside `prototype.py` and belongs to the same tool. It uses the standard library only, so the tool runs
wherever Python 3.11 does, with aidd or without it. It owns five things:

- the screens a design draws, with their states, parent, and first state (`screens`), which agents read instead of
  parsing the HTML themselves, and the components each state shows, which the fidelity pass's views read
  (`fidelity_shots.py`);
- the integrity of those screens: every link, parent, and first state names a thing the design has, every interactive
  element has a test id, no test id repeats in one state, and the first screen reaches every other;
- the names a control needs, so a screen reader and a test can find it;
- the lint rules `skills/prototyping/references/design-review.md` lists as shell commands, in Python. The
  reference keeps its commands; these are the same rules for a person who has no Node or grep. The color rule is
  `design_colors.py`, and the CSS reader and the depth rule are `design_css.py`, each beside this file;
- the device frames: the table of real device sizes beside this file (`devices.json`, which `aidd gen-docs` writes from the
  design system), and the check that a link names a frame of it and a frame a design draws has its size and a fixed height.

Text from the design is data. Nothing here runs it, and a placeholder such as `{{spec}}` in a starting design is skipped.
"""

from __future__ import annotations

import difflib
import functools
import importlib.util
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from types import ModuleType
from typing import Any

# Elements with no end tag (the HTML standard's void elements), so they never open a level.
VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())
# A design nested deeper than this is refused, so a hostile one cannot take time in proportion to its depth for each tag.
MAX_DEPTH = 400
INTERACTIVE = frozenset(("a", "button", "input", "select", "textarea"))
# The attributes that name a control. A button or a link is also named by its text. The first two name it by reference,
# and `_NAMES[:2]` reads them by position.
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
    in_svg: bool = False
    context: tuple[str, str] = ("", "")  # the screen it sits on and the state it is in


@functools.cache
def _sibling(name: str) -> ModuleType:
    """A rule that sits beside this file (`design_colors.py`, `design_css.py`), loaded when a check first reads it, so this file still loads alone."""
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"aidd_team_tools.{path}", path) if path.is_file() else None
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"the prototype tool's {name}.py is missing beside {Path(__file__).name}: reinstall aidd-team")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.devices: list[tuple[int, str, str]] = []  # (line, data-device, style) of each frame the design draws itself
        # Each `data-component` as (name, variant, screen, state), in the order the design draws them: "" for the chrome or
        # for no state. The fidelity pass's shots read it, and the count of elements in each (screen, state) beside it.
        self.components: list[tuple[str, str, str, str]] = []
        self.state_sizes: dict[tuple[str, str], int] = {}
        self._fields: list[tuple[str, int, str, bool]] = []  # (tag, line, id, named by its own attributes or a wrapping label)
        self._label_targets: set[str] = set()
        self._ids: dict[str, int] = {}  # each id seen and its first line
        self._labelledby: list[tuple[int, str]] = []  # (line, aria-labelledby value)
        self.paints: list[tuple[int, str]] = []  # SVG fill/stroke attributes that hold a raw color

    def finish(self) -> None:
        """Read to the end, then settle what needed the whole design: labels and ARIA references."""
        self.close()
        if self.too_deep:
            return
        for entry in reversed(self._stack):
            self._close(entry)
        self._stack.clear()
        for tag, line, ident, named in self._fields:
            if not named and ident not in self._label_targets:
                self._problem(line, f'<{tag}> has no label; add <label for="..."> with its id, or an aria-label')
        for line, value in self._labelledby:
            for ref in value.split():
                if "{{" not in ref and ref not in self._ids:
                    self._problem(
                        line,
                        f'aria-labelledby="{quoted(value)}" names missing id `{quoted(ref)}`; add an element with id="{quoted(ref)}" or remove it',
                    )

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
        entry.in_svg = (parent is not None and parent.in_svg) or tag == "svg"
        entry.context = self._context(entry, parent)
        self._note_metadata(entry, a)
        if tag not in VOID:
            self._stack.append(entry)
            if entry.interactive and not entry.named:
                self._controls.append(entry)

    def _note_metadata(self, entry: _Open, a: dict[str, str]) -> None:
        """Record links, device frames, test ids, components, ids, ARIA labels, and SVG paint attributes."""
        tag, line, (screen, state) = entry.tag, entry.line, entry.context
        for attribute in _LINK_ATTRIBUTES:
            if attribute in a:
                self.links.append(_Link(attribute, a[attribute], line, screen))
        if "data-device" in a:
            self.devices.append((line, a["data-device"], a.get("style", "")))
        if a.get("data-testid", "").strip():
            self.test_ids.append(_TestId(a["data-testid"].strip(), line, screen, state, entry.in_template))
        if a.get("data-component"):
            self.components.append((a["data-component"], a.get("data-variant") or "default", screen, state))
        if state:
            self.state_sizes[(screen, state)] = self.state_sizes.get((screen, state), 0) + 1
        if tag == "label" and a.get("for"):
            self._label_targets.add(a["for"])
        if (ident := a.get("id", "")) and "{{" not in ident:
            if ident in self._ids:
                self._problem(line, f'id="{quoted(ident)}" repeats the id on line {self._ids[ident]}; give each element its own id')
            else:
                self._ids[ident] = line
        if labelledby := a.get("aria-labelledby", "").strip():
            self._labelledby.append((line, labelledby))
        if entry.in_svg:
            for attr in ("fill", "stroke"):
                val = a.get(attr, "").strip()
                if val and val.lower() not in _sibling("design_colors").SAFE_PAINT and not val.lower().startswith(("var(", "url(")) and "{{" not in val:
                    self.paints.append(
                        (line, f'the raw color in {attr}="{quoted(val)}" is outside the tokens block; use currentColor or var(), such as var(--color-accent)')
                    )
        self._note_control(entry)

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


def _choose(name: str, options: list[str], noun: str) -> str:
    """What to do about a name that matches nothing: the closest option, when one is near, and the list."""
    if not options:
        return f"this design draws no {noun} to name"
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


DEVICES_FILE = "devices.json"
# The viewer's one mode that is no device: it follows the window, so it has no row in the table.
VIEWER_MODES = ("fill",)
_DEVICE_KEYS = (("name", str), ("platform", str), ("width", int), ("height", int))


def _good_frame(frame: object) -> bool:
    """A row the tool can draw: its name, platform, width, and height, and a phone's system bars, when it has them, as whole px."""
    if not (isinstance(frame, dict) and all(isinstance(frame.get(k), t) for k, t in _DEVICE_KEYS)):
        return False
    bars = frame.get("safe_area", {"top": 0, "bottom": 0})
    return isinstance(bars, dict) and all(isinstance(bars.get(side), int) and 0 <= bars[side] < frame["height"] // 2 for side in ("top", "bottom"))


@functools.cache
def device_frames() -> dict[str, dict]:
    """The device table, as the design system owns it: each frame's name, platform, width, and height in CSS px, and a phone's
    system bars (`safe_area`), by the id a deep link names (`?frame=ios`). It is `devices.json` beside this file, which
    `aidd gen-docs` writes from the design system's tokens.json, so no size is typed here."""
    path = Path(__file__).with_name(DEVICES_FILE)
    try:
        frames = json.loads(path.read_text(encoding="utf-8")).get("frames")
    except (OSError, ValueError, AttributeError) as error:
        raise FileNotFoundError(f"the prototype tool's {DEVICES_FILE} is missing or unreadable beside {Path(__file__).name}: reinstall aidd-team") from error
    if not (isinstance(frames, dict) and frames and all(_good_frame(f) for f in frames.values())):
        raise ValueError(f"the prototype tool's {DEVICES_FILE} is not a table of device frames: reinstall aidd-team")
    return frames


def _frame_choices() -> str:
    """The frames a link may name, each with its size, for a message."""
    return ", ".join(f"`{key}` ({f['width']} by {f['height']})" for key, f in device_frames().items())


# A deep link's frame: `?frame=ios` or `&frame=ios`. An empty value is a placeholder in a starting design, and the HTML
# `frame` attribute of a table has no `?` or `&` before it, so neither is read.
_FRAME_LINK = re.compile(r"[?&]frame=([^&\s\"'#<>)]+)")
_PIXELS = re.compile(r"(\d+(?:\.\d+)?)px")


def _frame_link_problem(value: str) -> str | None:
    """What is wrong with a deep link's `frame=` value, with the frame to name instead; None when it names a frame."""
    frames = device_frames()
    if value in frames or value in VIEWER_MODES or "{{" in value:
        return None
    bare = value.isascii() and value.isdigit()
    same_width = [key for key, f in frames.items() if bare and f["width"] == int(value)]
    if bare:
        # A width alone is no frame, since a frame has a fixed height too; the ids 320, 768, 1024, and 1440 are names.
        hint = f"; {value} is the width of `{same_width[0]}`, so name frame={same_width[0]}" if same_width else ""
        return f"frame={quoted(value)} is no frame of the device table{hint}. Name one: {_frame_choices()}"
    return f"frame={quoted(value)} is no frame of the device table; {_choose(value, list(frames), 'frame')}. Name one: {_frame_choices()}"


def _style_declarations(style: str) -> dict[str, str]:
    """An inline style as {property: value}, lower case, in the order of each property's last declaration, which wins, as a
    browser reads it."""
    out: dict[str, str] = {}
    for declaration in style.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip():
            out.pop(name.strip().lower(), None)
            out[name.strip().lower()] = value.replace("!important", "").strip().lower()
    return out


def _overflow_y(css: dict[str, str]) -> str:
    """How the element scrolls up and down: the later of `overflow-y` and the `overflow` shorthand, whose last value is y."""
    found = ""
    for name, value in css.items():
        if name == "overflow-y" or (name == "overflow" and value.split()):
            found = value.split()[-1] if name == "overflow" else value
    return found


def device_problems(reader: DesignReader) -> list[tuple[int, str]]:
    """The frames a design draws itself (`data-device="<frame>"`), each measured against the device table: the frame is one of
    its ids, its width and height are that frame's, in px, the height is fixed, and the design scrolls inside. A frame that
    grows with its content, or has a size no device has, is the mistake this table exists to stop."""
    frames, found = device_frames(), []
    for line, ident, style in reader.devices:
        frame = frames.get(ident)
        if frame is None:
            found.append(
                (line, f'data-device="{quoted(ident)}" is no frame of the device table; {_choose(ident, list(frames), "frame")}. Name one: {_frame_choices()}')
            )
            continue
        css = _style_declarations(style)
        # Each message names the frame as a person knows it, and says what to write in the element's style attribute.
        what = f"the frame `{ident}` ({frame['name']}, {frame['width']} by {frame['height']})"
        sizes = {side: _PIXELS.fullmatch(css.get(side, "")) for side in ("width", "height")}
        if sizes["height"] is None:
            found.append((line, f"{what} has no fixed height, so it grows with its content; add height: {frame['height']}px; overflow-y: auto to its style"))
        if sizes["width"] is None:
            found.append((line, f"{what} has no width in px; add width: {frame['width']}px to its style"))
        if sizes["width"] and sizes["height"]:
            drawn = (float(sizes["width"].group(1)), float(sizes["height"].group(1)))
            if drawn != (frame["width"], frame["height"]):
                found.append(
                    (
                        line,
                        f"{what} is drawn {drawn[0]:g} by {drawn[1]:g} px, a size the device table lacks; set width: {frame['width']}px; height: {frame['height']}px in its style",
                    )
                )
        if sizes["height"] is not None and _overflow_y(css) not in ("auto", "scroll"):
            found.append((line, f"{what} does not scroll inside, so a long design is cut off or spills out; add overflow-y: auto to its style"))
    return found


# The prototype lint, the rules `design-review.md` lists as shell commands, here as Python over the whole file.
_HOTLINK = re.compile(
    r"""(?:srcset\s*=\s*["'][^"']*(?:https?:)?//|(?:src|href|poster)\s*=\s*["'](?:https?:)?//|url\(\s*["']?(?:https?:)?//|@import\s+(?:url\(|["']))""",
    re.I,
)
_ADDRESS = re.compile(r"""(?:https?:)?//[^\s"')>]+""")
_PLACEHOLDER = re.compile(r"lorem ipsum|dolor sit amet|\bTODO\b(?!-\d+)|\bFIXME\b|\bTBD\b|john doe|jane doe|placeholder text", re.I)
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


# The design format each rule family arrived in. Spec approval freezes a design and the command that checks it, so an
# aidd upgrade must never turn an approved design red: `check` applies only the families of the format the design names,
# and shows a newer family's findings as notes. A new rule after 1.0.0 is a new family at a new format, and a design takes
# it through its own change.
RULE_FORMATS = {"integrity": 1, "raw-color": 1, "hotlink": 1, "placeholder": 1, "emoji": 1, "device-frame": 1, "depth": 1}


_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{3,8})\b")
_FUNC_COLOR = re.compile(r"(?:rgb|hsl|hwb|lab|lch|oklab|oklch|color)a?\([^)]+\)", re.I)


def _norm_color(value: str) -> str:
    raw = value.strip().lower()
    if m := _HEX_COLOR.fullmatch(raw):
        h = m.group(1)
        return "#" + ("".join(c * 2 for c in h) if len(h) in (3, 4) else h)
    return re.sub(r"\s+", " ", raw)


def token_colors(text: str) -> dict[str, str]:
    """Map normalized colors inside `<style id="tokens">` to custom property names."""
    by_color: dict[str, str] = {}
    for block in _sibling("design_css").token_blocks(text):
        for name, val in _sibling("design_css").custom_properties(block):
            if _HEX_COLOR.fullmatch(val) or _FUNC_COLOR.fullmatch(val):
                by_color.setdefault(_norm_color(val), name)
    return by_color


def suggest_var(value: str, tokens: dict[str, str]) -> str:
    """Return the token custom property matching a raw color value, if defined."""
    m = (_HEX_COLOR.search(value) or _FUNC_COLOR.search(value)) if tokens else None
    return tokens.get(_norm_color(m.group(0)), "") if m else ""


def _token_names(text: str) -> dict[str, str]:
    """Each value the tokens block sets, as `design_css.normal` reads it, with the name of the first custom property that holds it."""
    css = _sibling("design_css")
    return {css.normal(v): name for block in css.token_blocks(text) for name, v in reversed(css.custom_properties(block))}


def _depth_message(finding: Any, named: dict[str, str]) -> str:
    """What a depth finding says to do: read the token that already holds the value, or move the value into the tokens block."""
    css = _sibling("design_css")
    token = named.get(css.normal(finding.layer)) or named.get(css.normal(finding.value))
    what = f'the depth in "{quoted(finding.prop + ": " + finding.layer)}" is outside the tokens block'
    if token:
        return f"{what}; the tokens block already holds {token} with this value, so read it with var({token})"
    return f"{what}; move the value into the tokens block as a custom property, and read it with var()"


def _lint(text: str, tokens: dict[str, str] | None = None) -> list[tuple[int, str, str]]:
    """Run prototype lint rules over the file: raw colors, depth, hotlinks, bad frames, placeholder text, and emoji icons.
    Colors and depth are read from whole declarations (`design_css.py`), the rest line by line."""
    found: list[tuple[int, str, str]] = []
    token_map = token_colors(text) if tokens is None else tokens
    colors, css = _sibling("design_colors"), _sibling("design_css")
    named = _token_names(text)  # once for the file, so a design with many findings is read in time linear in its size
    for declaration in css.declarations(text):
        if (color := colors.raw_color(declaration.text)) is not None:
            decl = colors.declaration(declaration.text, color)
            var = suggest_var(decl, token_map)
            msg = f'the raw color in "{quoted(decl)}" is outside the tokens block; read a role with var(), such as var({var or "--color-accent"})'
            found.append((declaration.line_at(color), msg, "raw-color"))
        if (depth := css.depth_finding(declaration.text)) is not None:
            found.append((declaration.line_at(depth.start), _depth_message(depth, named), "depth"))
    for number, line in enumerate(text.split("\n"), 1):
        if link := _HOTLINK.search(line):
            address = _ADDRESS.search(line)
            msg = f"{quoted(address.group(0) if address else link.group(0))} loads from the network; keep the image or font in the design, as its Content-Security-Policy requires"
            found.append((number, msg, "hotlink"))
        for link in _FRAME_LINK.finditer(line):
            if problem := _frame_link_problem(link.group(1)):
                found.append((number, problem, "device-frame"))
        if word := _PLACEHOLDER.search(line):
            found.append((number, f'placeholder text "{word.group(0)}"; write the real copy a person would read', "placeholder"))
        if emoji := _EMOJI.search(line):
            found.append(
                (number, f'the emoji {emoji.group(0)} is not an icon; draw it from the system\'s icon set, with a name or aria-hidden="true"', "emoji")
            )
    return sorted(found, key=lambda item: item[0])


def hint_paint(message: str, tokens: dict[str, str]) -> str:
    """Replace the generic token hint on an SVG paint finding when `tokens` defines that color."""
    if not tokens or '="' not in message:
        return message
    var = suggest_var(message.split('="', 1)[1].split('"', 1)[0], tokens)
    return message.replace("such as var(--color-accent)", f"such as var({var})", 1) if var else message


def check(text: str, product: str, first_line: int, label: str, design_format: int = 1) -> tuple[list[str], str]:
    """A design file's problems and its ok line. `product` is the markup of its <template id="product"> and `first_line`
    the file's line where it starts. Each problem names the file and the line, and says what to change. A rule family
    newer than `design_format` reports only as a note under the ok line, so an upgrade never fails an approved design."""
    reader = read_design(product, label, first_line)
    tokens = token_colors(text)
    every = sorted(
        [
            *((line, message, "integrity") for line, message in integrity_problems(reader)),
            *((line, hint_paint(message, tokens), "raw-color") for line, message in reader.paints),
            *((line, message, "device-frame") for line, message in device_problems(reader)),
            *_lint(text, tokens),
        ],
        key=lambda item: item[0],
    )
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
