"""The tokens-only lint of aidd's built-in pages: a page's CSS names tokens and the shared components, never a raw
value. `raw_values` returns one finding per raw color (a hex, a color function such as `color()`, or a named color such
as `white`), raw length in any CSS unit, raw line height, unknown `var()`, or custom property the CSS defines itself. A
color is a token's `var()`, `currentColor`, `transparent`, `inherit`, or a system color for forced colors. The allowlist
is short and named:

- `1px` and `-1px` in the visually hidden pattern, a rule that holds `clip-path: inset(50%)`;
- a rem length in a layout property of a page's own CSS (`layout=True`), such as a column's width, or in a measure the
  page names once as its own custom property (`defines`), such as a panel's width;
- a share of the window (vw, vh, dvh, and the rest) in a layout property, or anywhere in a page's own CSS;
- a share of the text an element sits in (em, ch, ex, lh, and the rest), such as an icon's 1em or a measure's 56ch,
  because it follows the reader's text size, which no token sets;
- a `--breakpoint-*` value in a media query;
- the viewer's device drawing, between `/* device drawing: raw by design */` and `/* end device drawing */`, which draws
  hardware over foreign pixels.

`depth_values` is the same lint for depth, and aidd's own pages are stricter than the prototype tool's `depth` rule: one
shadow token, `--shadow-raised`; every other `box-shadow` is a ring or `none`; no blur; and no gradient but the viewer's
safe-area hatch (`.pv-safe`). The ring and the layers are read by the tool's own reader (`design_css.py`), so the two share one
grammar.
"""

from __future__ import annotations

import importlib.util
import re

import helpers  # noqa: F401  (puts src on the path)
from helpers import PROTOTYPE_TOOL

from aidd.views import design_tokens

DEVICE = re.compile(r"/\* device drawing: raw by design \*/.*?/\* end device drawing \*/", re.S)
COMMENT = re.compile(r"/\*.*?\*/", re.S)
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\(")
# Every CSS length unit (CSS Values and Units Level 4), read 2026-11-08.
WINDOW_UNITS = ("vw", "vh", "vi", "vb", "vmin", "vmax", "svw", "svh", "lvw", "lvh", "dvw", "dvh", "cqw", "cqh", "cqi", "cqb", "cqmin", "cqmax")
TEXT_UNITS = ("em", "ex", "ch", "cap", "ic", "lh", "rem", "rex", "rch", "rcap", "ric", "rlh")
ABSOLUTE_UNITS = ("px", "cm", "mm", "q", "in", "pt", "pc")
LENGTH = re.compile(r"(?<![\w.#-])-?(?:\d+\.?\d*|\.\d+)(" + "|".join(sorted(WINDOW_UNITS + TEXT_UNITS + ABSOLUTE_UNITS, key=len, reverse=True)) + r")\b", re.I)
# A share of the text an element sits in: rem and the root's units stay raw, because the scale's tokens are in rem.
PROPORTION = tuple(u for u in TEXT_UNITS if not u.startswith("r"))
VAR = re.compile(r"var\(\s*(--[\w-]+)")
WORD = re.compile(r"(?<![\w-])[a-zA-Z]+(?![\w(-])")
STRING = re.compile(r"\"[^\"]*\"|'[^']*'")
# CSS Color Module Level 4's named colors, which the prototype tool's color rule owns (`design_colors.py` beside it), so
# `aidd-team` carries one list. `transparent` and `currentColor` are not in it, and the system colors stay allowed.
_COLORS_SPEC = importlib.util.spec_from_file_location("design_colors", PROTOTYPE_TOOL / "design_colors.py")
assert _COLORS_SPEC is not None and _COLORS_SPEC.loader is not None
_COLORS = importlib.util.module_from_spec(_COLORS_SPEC)
_COLORS_SPEC.loader.exec_module(_COLORS)
NAMED_COLORS = _COLORS.NAMED
_CSS_SPEC = importlib.util.spec_from_file_location("design_css", PROTOTYPE_TOOL / "design_css.py")
assert _CSS_SPEC is not None and _CSS_SPEC.loader is not None
_CSS = importlib.util.module_from_spec(_CSS_SPEC)
_CSS_SPEC.loader.exec_module(_CSS)
# The one shadow aidd's own pages draw, for a layer that floats over content; every other shadow layer is a ring.
SHADOW_TOKEN = "var(--shadow-raised)"
# The one gradient they draw: the viewer's hatch over a phone's system bars.
HATCH = ".pv-safe"
# A line height is a token, such as a --text-*--line-height, or a keyword.
LINE_HEIGHT = re.compile(r"^(?:var\(--[\w-]+\)|normal|inherit)$")
DEFINED = re.compile(r"(?<![\w-])(--[\w-]+)\s*:")
LAYOUT = {
    "width",
    "min-width",
    "max-width",
    "height",
    "min-height",
    "max-height",
    "inline-size",
    "min-inline-size",
    "max-inline-size",
    "block-size",
    "min-block-size",
    "max-block-size",
    "flex",
    "flex-basis",
    "grid-template-columns",
    "grid-template-rows",
    "grid-auto-columns",
    "grid-auto-rows",
    "grid-template",
    "grid",
    "columns",
    "column-width",
}


def tokens_defined() -> set[str]:
    return set(DEFINED.findall(design_tokens.tokens_css()))


def _breakpoints() -> set[str]:
    data = design_tokens.tokens()["breakpoint"]
    return {f"{v['$value']['value']:g}{v['$value']['unit']}" for k, v in data.items() if not k.startswith("$")}


def _blocks(css: str):
    """Each (prelude, declarations) of `css`, at-rule preludes included as their own entries with no declarations."""
    for found in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        yield found.group(1).strip(), found.group(2)
    for found in re.finditer(r"(@[^{;]+)\{", css):
        yield found.group(1).strip(), ""


def _lengths(text: str) -> list[str]:
    return [found.group(0) for found in LENGTH.finditer(text)]


def _unit(length: str) -> str:
    return re.sub(r"^-?[\d.]+", "", length).lower()


def raw_values(css: str, *, layout: bool = False, defines: set[str] | None = None) -> list[str]:
    """Every raw value in `css`, as `selector: what` lines. `layout` allows rem in a layout property, for a page's own
    CSS. `defines` is the custom properties the CSS may set beside the tokens', such as those a script writes."""
    css = COMMENT.sub("", DEVICE.sub("", css))
    known = tokens_defined() | (defines or set())
    breakpoints = _breakpoints()
    found: list[str] = []
    for prelude, body in _blocks(css):
        if prelude.startswith("@"):
            for length in _lengths(prelude):
                if not (prelude.startswith("@media") and length in breakpoints) and _unit(length) not in PROPORTION:
                    found.append(f"{prelude}: {length}")
            continue
        hidden = "clip-path: inset(50%)" in body
        for declaration in body.split(";"):
            name, _, value = declaration.partition(":")
            name = name.strip()
            if not name:
                continue
            if name.startswith("--") and name not in (defines or set()):
                found.append(f"{prelude}: defines {name}")
            for color in COLOR.findall(value):
                found.append(f"{prelude}: {name}: {color}")
            for word in WORD.findall(STRING.sub("", value)):
                if word.lower() in NAMED_COLORS:
                    found.append(f"{prelude}: {name}: {word}")
            if name == "line-height" and not LINE_HEIGHT.match(value.strip().removesuffix("!important").strip()):
                found.append(f"{prelude}: {name}: {value.strip()}")
            for length in _lengths(value):
                unit = _unit(length)
                if hidden and length in ("1px", "-1px"):
                    continue
                if unit in PROPORTION or (unit in WINDOW_UNITS and (layout or name in LAYOUT)):
                    continue
                if layout and length.endswith("rem") and (name in LAYOUT or name in (defines or set())):
                    continue
                found.append(f"{prelude}: {name}: {length}")
            for used in VAR.findall(value):
                if used not in known:
                    found.append(f"{prelude}: {name}: var({used}) names no token")
    return found


def depth_values(css: str) -> list[str]:
    """Every depth in `css` that aidd's own pages never draw, as `selector: property: what` lines: a shadow layer that is not
    a ring, the one shadow token, or a custom property that the same CSS sets to rings; a `blur(` or a `drop-shadow(`; and a
    gradient outside the safe-area hatch."""
    found: list[str] = []
    blocks = list(_blocks(COMMENT.sub("", css)))
    declarations = [(prelude, *(part.strip() for part in declaration.partition(":")[::2])) for prelude, body in blocks for declaration in body.split(";")]
    rings = {name for _, name, value in declarations if name.startswith("--") and all(_CSS.is_ring(layer) for layer in _CSS.shadow_layers(value))}
    for prelude, name, value in declarations:
        value = value.removesuffix("!important").strip()
        if name.endswith("shadow"):
            for layer in _CSS.shadow_layers(value):
                named = re.fullmatch(r"var\((--[\w-]+)\)", layer)
                if layer != SHADOW_TOKEN and not _CSS.is_ring(layer) and not (named and named.group(1) in rings):
                    found.append(f"{prelude}: {name}: {layer}")
        elif re.search(r"(?<![\w-])(?:blur|drop-shadow)\(", value):
            found.append(f"{prelude}: {name}: {value}")
        if "gradient(" in value and prelude != HATCH:
            found.append(f"{prelude}: {name}: {value}")
    return found
