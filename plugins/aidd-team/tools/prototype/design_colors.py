"""The prototype tool's color rule: what a raw color is in a design's CSS and SVG, and where in a line the first one starts.

This file sits beside `design_checks.py` and belongs to the same tool. It uses the standard library only. A raw color is
a hex code, a color function, or a named color, written outside the design's `<style id="tokens">` block, where a design
reads a role with `var()` instead. It reads one declaration at a time, as `design_css.py` gives it: a comment is no
declaration and a value on two lines is one value. The CSS Color Module keywords that are no color of their own stay allowed, with the
system colors a forced-colors style needs.
"""

from __future__ import annotations

import re

# CSS Color Module Level 4, section 6.1, "Named Colors" (https://www.w3.org/TR/css-color-4/#named-colors): its 148 names,
# read 2026-11-16. CSS reads a keyword without regard to case, so each name is lowercase here.
NAMED = frozenset(
    """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood
    cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
    darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue
    firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew
    hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue
    lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
    mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab orange
    orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
    powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna
    silver skyblue slateblue slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet
    wheat white whitesmoke yellow yellowgreen
    """.split()
)
# Section 6.2, "System Colors", lowercased: a forced-colors style names them, so they are no raw color.
SYSTEM = frozenset(
    """accentcolor accentcolortext activetext buttonborder buttonface buttontext canvas canvastext field fieldtext graytext
    highlight highlighttext linktext mark marktext selecteditem selecteditemtext visitedtext""".split()
)
# The keywords that name no color of their own, in a CSS color value and in an SVG `fill` or `stroke`.
KEYWORDS = frozenset("transparent currentcolor inherit initial unset revert revert-layer none".split())
SAFE_PAINT = KEYWORDS | SYSTEM | {"", "context-fill", "context-stroke"}

# The color rule reads one CSS declaration at a time, so it takes time in proportion to its text: a declaration ends at `;`,
# `"`, or `}`; a property name is a run of lowercase letters and dashes that ends at `:`; a raw color is a hex code, a color
# function, or a color name after it. A property holds a color when its name holds one of these words: `mask` and `filter`
# take one in a gradient or a `drop-shadow(`.
_DECLARATION = re.compile(r'[^;"}]+')
_PROPERTY = re.compile(r"(?<![a-z-])(?:[a-z-]+|--[a-z0-9-]+): *")
_COLOR_PROPERTIES = ("color", "background", "border", "fill", "stroke", "outline", "shadow", "mask", "filter")
_COLOR_VALUE = re.compile(r"#[0-9a-fA-F]{3,8}\b|(rgb|hsl|hwb|lab|lch|oklab|oklch|color)a?\(")
# A word in a value that is no part of a longer word, a custom property's name (`--red`), a function's name (`tan(`), or a
# hex code. A URL and a string hold no color, so they are cut out first.
_WORD = re.compile(r"(?<![\w#-])[a-z]+(?![\w(-])", re.I)
_QUOTED = re.compile(r"""url\([^)]*\)|'[^']*'""", re.I)
_BARE = re.compile(r"\s*([a-z]+)\s*(?:!important)?\s*", re.I)


def _names_a_color(value: str, custom: bool) -> bool:
    """Whether a CSS value is or holds a named color. A custom property has no type, so `--font: Tan` could be a font: only a
    value that is one color name and nothing else counts there."""
    value = _QUOTED.sub(" ", value)
    if custom:
        bare = _BARE.fullmatch(value)
        return bare is not None and bare.group(1).lower() in NAMED
    return any(word.lower() in NAMED for word in _WORD.findall(value))


def raw_color(line: str) -> int | None:
    """Where in the line the property of the first raw color starts, or None when the line has none."""
    for declaration in _DECLARATION.finditer(line):
        text = declaration.group(0)
        for prop in _PROPERTY.finditer(text):
            name = prop.group(0).rstrip(": ")
            if name.startswith("--") or any(word in name for word in _COLOR_PROPERTIES):
                # The first color property has the longest rest of the declaration, so no later one in it can match when it does
                # not: one bounded search for each declaration, then the next declaration.
                if _COLOR_VALUE.search(text, prop.end()) or _names_a_color(text[prop.end() :], name.startswith("--")):
                    return declaration.start() + prop.start()
                break
    return None


def declaration(line: str, start: int) -> str:
    """The CSS declaration a raw color sits in, from its property name to its `;`, on one line and cut short for a message."""
    before = line[:start]
    name = before[len(before.rstrip("abcdefghijklmnopqrstuvwxyz-")) :]
    rest = re.match(r'[^;"}]*', line[start:])
    return " ".join((name + (rest.group(0) if rest else "")).split())[:70]
