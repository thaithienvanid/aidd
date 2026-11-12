"""The design system of aidd's built-in pages, built from its one source: `design/tokens.json` and
`design/components.css`, beside this file.

`tokens_css` writes the tokens as CSS custom properties, Tailwind v4's names for the scale and shadcn/ui's for the
colors. `system_css` is the tokens, then the components with their comments stripped: the style the status page reads,
and the `system.css` that `aidd gen-docs` writes beside the prototype tool. `design_front_matter` is DESIGN.md's token
front matter, which `with_design_front_matter` writes into the file's text. `devices_json` is the device table, the
`devices.json` that `aidd gen-docs` writes beside the prototype tool. Each reads the file once, and fails on an
alias that does not resolve, a color whose components and hex disagree, a contrast pair that names a role a theme lacks,
a device frame with no source, or a value outside the file's grammar, so no value can end a CSS rule or a style block.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import math
import re

from aidd.kernel import resources

DESIGN_TOKENS_PACKAGE = ("aidd.views", "design")
GENERATED = "/* Generated from src/aidd/views/design/tokens.json by `aidd gen-docs`: never edit by hand. */\n"
_ALIAS = re.compile(r"\{([\w.-]+)\}")
# The grammar every value keeps, so none can end a CSS rule, a style block, or a quoted family name. Each is matched in
# full (fullmatch), so a trailing newline fails too.
_HEX = re.compile(r"#[0-9a-f]{6}")
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
_FAMILY = re.compile(r"[\w -]+")
_UNITS = ("rem", "px", "ms")
_SCALE = (("spacing", "spacing"), ("size", "size"), ("container", "container"), ("radius", "radius"), ("breakpoint", "breakpoint"))
THEMES = ("light", "dark")
PLATFORMS = ("web", "ios", "android", "desktop")
# A device frame's words, matched in full: plain text with no markup, so the viewer and the tool print them as they are.
_DEVICE_TEXT = re.compile(r"[\w ,.()'/+-]+")
MAX_VIEWPORT = 10000


def _num(value: float) -> str:
    return f"{value:g}"


def _length(value: dict) -> str:
    return _num(value["value"]) + value["unit"]


def _lookup(data: dict, path: str) -> dict:
    node: object = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"tokens.json: the alias {{{path}}} names no token")
        node = node[part]
    if not isinstance(node, dict) or "$value" not in node:
        raise ValueError(f"tokens.json: the alias {{{path}}} names a group, not a token")
    return node


def _entries(group: dict) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in group.items() if not k.startswith("$")]


def _alias(value: object, where: str = "a value") -> str:
    """The token path an alias such as `{color.light.ring}` names."""
    found = _ALIAS.fullmatch(value) if isinstance(value, str) else None
    if not found:
        raise ValueError(f"tokens.json: {where} is {value!r}, not an alias such as {{color.light.ring}}")
    return found.group(1)


def _role(value: object, where: str = "a value") -> str:
    """The role an alias names, its last part: `{color.light.ring}` is `ring`."""
    return _alias(value, where).rsplit(".", 1)[-1]


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"tokens.json: {where} is {value!r}, not a finite number")
    return value


def _dimension(value: object, where: str) -> None:
    if not isinstance(value, dict) or value.get("unit") not in _UNITS:
        raise ValueError(f"tokens.json: {where} needs a unit from {', '.join(_UNITS)}")
    _number(value.get("value"), where)


def _check_color(value: dict, where: str) -> None:
    if not isinstance(value.get("hex"), str) or not _HEX.fullmatch(value["hex"]):
        raise ValueError(f"tokens.json: {where}'s hex is {value.get('hex')!r}, not # and six lower-case hex digits")
    parts = value.get("components")
    if not isinstance(parts, list) or len(parts) != 3 or not all(0 <= _number(c, where) <= 1 for c in parts):
        raise ValueError(f"tokens.json: {where} needs three components from 0 to 1")
    if "alpha" in value and not 0 <= _number(value["alpha"], where) <= 1:
        raise ValueError(f"tokens.json: {where}'s alpha is not from 0 to 1")


def _check_grammar(data: dict) -> None:
    """Every name and value tokens.json holds keeps the grammar above: names in lower-case words, lengths in rem, px, or
    ms, finite numbers, six-digit hex colors, and plain family names."""
    groups = [("color." + theme, data["color"][theme]) for theme in THEMES]
    groups += [(g, data[g]) for g, _ in _SCALE] + [("duration", data["duration"]), ("ease", data["ease"]), ("focus", data["focus"])]
    groups += [("border.width", data["border"]["width"]), ("shadow", data.get("shadow", {})), ("typography", data["typography"])]
    groups += [("font." + g, data["font"][g]) for g in ("family", "weight", "size", "line-height")]
    for group, tokens_ in groups:
        for name, token in _entries(tokens_):
            where, value = f"{group}.{name}", token["$value"]
            if not _NAME.fullmatch(name):
                raise ValueError(f"tokens.json: the name {where} is not lower-case letters, digits, _ and -")
            if group in ("spacing", "size", "container", "radius", "breakpoint", "duration", "focus", "border.width", "font.size"):
                _dimension(value, where)
            elif group in ("font.weight", "font.line-height"):
                _number(value, where)
            elif group == "ease":
                if not isinstance(value, list) or len(value) != 4:
                    raise ValueError(f"tokens.json: {where} needs four numbers")
                for number in value:
                    _number(number, where)
            elif group == "font.family" and not (isinstance(value, list) and value and all(isinstance(f, str) and _FAMILY.fullmatch(f) for f in value)):
                raise ValueError(f"tokens.json: {where} needs family names of letters, digits, spaces, and -")
            elif group == "typography":
                for key in ("fontFamily", "fontSize", "fontWeight"):
                    _lookup(data, _alias(value.get(key), f"{where}.{key}"))
                _number(value.get("lineHeight"), f"{where}.lineHeight")
                _dimension(value.get("letterSpacing"), f"{where}.letterSpacing")
            elif group == "shadow":
                for layer in value:
                    for key in ("offsetX", "offsetY", "blur", "spread"):
                        _dimension(layer.get(key), f"{where}.{key}")
            elif group.startswith("color.") and isinstance(value, dict):
                _check_color(value, where)


def _check_devices(data: dict) -> None:
    """The device table: each frame has a name, a platform, a fixed width and height in CSS px, the devices it stands for, and
    the source it was read from on a day, so no size is one nobody confirmed."""
    frames = data["$extensions"]["aidd"]["device"]["frames"]
    if not frames:
        raise ValueError("tokens.json: the device table has no frame")
    for key, frame in frames.items():
        where = f"device.frames.{key}"
        if not _NAME.fullmatch(key):
            raise ValueError(f"tokens.json: the name {where} is not lower-case letters, digits, _ and -")
        if frame.get("platform") not in PLATFORMS:
            raise ValueError(f"tokens.json: {where}'s platform is {frame.get('platform')!r}, not one of {', '.join(PLATFORMS)}")
        for side in ("width", "height"):
            size = frame.get(side)
            if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_VIEWPORT:
                raise ValueError(f"tokens.json: {where}'s {side} is {size!r}, not a whole number of CSS px from 1 to {MAX_VIEWPORT}")
        names = [frame.get("name"), *(frame.get("devices") or [])]
        if not frame.get("devices") or not all(isinstance(n, str) and _DEVICE_TEXT.fullmatch(n) for n in names):
            raise ValueError(f"tokens.json: {where} needs a name and the devices it stands for, in plain words")
        citation = frame.get("citation") or {}
        if not (str(citation.get("url", "")).startswith("https://") and isinstance(citation.get("quote"), str) and citation["quote"].strip()):
            raise ValueError(f"tokens.json: {where} needs the source it was read from: a citation with an https url and a quote")
        try:
            dt.date.fromisoformat(str(frame.get("checked")))
        except ValueError:
            raise ValueError(f"tokens.json: {where}'s checked is {frame.get('checked')!r}, not the day the source was read (YYYY-MM-DD)") from None


def design_text(name: str) -> str:
    """A file of the design folder, `tokens.json` or `components.css`, read from the package, so the zipapp reads it too."""
    package, folder = DESIGN_TOKENS_PACKAGE
    return resources.package_text(package, folder, name)


@functools.cache
def tokens() -> dict:
    """tokens.json, checked: each alias resolves, each color's components match its hex within 1/255, and each contrast
    pair names a role both themes hold."""
    data = json.loads(design_text("tokens.json"))
    _check_grammar(data)
    _check_devices(data)
    for theme in THEMES:
        for role, token in _entries(data["color"][theme]):
            value = token["$value"]
            if isinstance(value, str):
                _lookup(data, _alias(value, f"color.{theme}.{role}"))
                continue
            if mix := _mix(token):
                mixed = _lookup(data, _alias(mix[0], f"color.{theme}.{role}'s mix"))["$value"]
                if mixed.get("components") != value["components"] or abs(value.get("alpha", 1) - mix[1] / 100) > 1e-9:
                    raise ValueError(f"tokens.json: color.{theme}.{role} is not {mix[0]} at {mix[1]}%, as its mix says")
            hex_ = value["hex"].lstrip("#")  # six digits, by the grammar
            for i, part in enumerate(value["components"]):
                if abs(int(hex_[2 * i : 2 * i + 2], 16) / 255 - part) > 1 / 255:
                    raise ValueError(f"tokens.json: color.{theme}.{role}'s components and hex {value['hex']} disagree")
    for name, t in _entries(data.get("shadow", {})):
        for layer in t["$value"]:
            _lookup(data, _alias(layer.get("color"), f"shadow.{name}'s color"))
    for fg, bg, least, _ in data["$extensions"]["aidd"]["contrast"]["pairs"]:
        _number(least, f"the contrast pair {fg} on {bg}'s least ratio")
        for theme in THEMES:
            for role in (fg, bg):
                if role not in data["color"][theme]:
                    raise ValueError(f"tokens.json: the contrast pair {fg} on {bg} names {role}, which the {theme} theme lacks")
    return data


def color(theme: str, role: str) -> tuple[float, float, float]:
    """A role's sRGB components in a theme, its aliases followed, as a page draws it: a role with alpha, such as the
    `border` hairline, is composited over the theme's `background`, so a contrast check measures the color on screen."""
    data = tokens()
    value = data["color"][theme][role]["$value"]
    while isinstance(value, str):
        value = _lookup(data, _alias(value))["$value"]
    r, g, b = value["components"]
    alpha = value.get("alpha", 1)
    if alpha >= 1 or role == "background":
        return r, g, b
    page = color(theme, "background")
    blended = [alpha * c + (1 - alpha) * p for c, p in zip((r, g, b), page, strict=True)]
    return blended[0], blended[1], blended[2]


def _shadow(layers: list[dict]) -> str:
    """A DTCG shadow as CSS: each layer's offsets, blur, and spread (a zero spread left out), then its color as the role,
    so each theme's shadow-color applies."""

    def _size(dimension: dict) -> str:
        return "0" if dimension["value"] == 0 else _length(dimension)

    out = []
    for layer in layers:
        role = _role(layer["color"])
        parts = [_size(layer["offsetX"]), _size(layer["offsetY"]), _size(layer["blur"])] + ([_size(layer["spread"])] if layer["spread"]["value"] else [])
        out.append(" ".join([*parts, f"var(--{role})"]))
    return ", ".join(out)


def _family(names: list[str]) -> str:
    return ", ".join(f'"{n}"' if " " in n else n for n in names)


def _color_value(value: object) -> str:
    if isinstance(value, str):
        return f"var(--{_role(value)})"
    assert isinstance(value, dict)
    if "alpha" in value:
        r, g, b = (round(c * 255) for c in value["components"])
        return f"rgb({r} {g} {b} / {_num(value['alpha'])})"
    return str(value["hex"])


def _mix(token: dict) -> list | None:
    """A color's `$extensions.aidd.mix`, [the role it mixes, its percent], when the CSS writes it as a color-mix."""
    return token.get("$extensions", {}).get("aidd", {}).get("mix")


def _token_css(token: dict) -> str:
    if mix := _mix(token):
        return f"color-mix(in srgb, var(--{_role(mix[0])}) {_num(mix[1])}%, transparent)"
    return _color_value(token["$value"])


def _colors(theme: str, indent: str) -> list[str]:
    lines = [f"{indent}color-scheme: {theme};"]
    lines += [f"{indent}--{role}: {_token_css(t)};" for role, t in _entries(tokens()["color"][theme])]
    return lines


@functools.cache
def tokens_css() -> str:
    """The tokens as CSS: the scale on :root, durations at 0ms under reduced motion, then the light colors, and the dark
    ones by `data-theme` and by the system's preference."""
    data = tokens()
    lines = [GENERATED.rstrip("\n"), ":root {"]
    for group, prefix in _SCALE:
        lines += [f"  --{prefix}-{name}: {_length(t['$value'])};" for name, t in _entries(data[group])]
    font = data["font"]
    lines += [f"  --font-{name}: {_family(t['$value'])};" for name, t in _entries(font["family"])]
    lines += [f"  --font-weight-{name}: {t['$value']};" for name, t in _entries(font["weight"])]
    for name, t in _entries(font["size"]):
        lines += [f"  --text-{name}: {_length(t['$value'])};", f"  --text-{name}--line-height: {_num(font['line-height'][name]['$value'])};"]
    lines += [f"  --border-width-{name}: {_length(t['$value'])};" for name, t in _entries(data["border"]["width"])]
    lines += [f"  --focus-{name}: {_length(t['$value'])};" for name, t in _entries(data["focus"])]
    lines += [f"  --duration-{name}: {_length(t['$value'])};" for name, t in _entries(data["duration"])]
    lines += [f"  --ease-{name}: cubic-bezier({', '.join(_num(v) for v in t['$value'])});" for name, t in _entries(data["ease"])]
    lines += [f"  --shadow-{name}: {_shadow(t['$value'])};" for name, t in _entries(data.get("shadow", {}))]
    lines.append("}")
    reduced = " ".join(f"--duration-{name}: 0ms;" for name, _ in _entries(data["duration"]))
    lines += ["@media (prefers-reduced-motion: reduce) {", f"  :root {{ {reduced} }}", "}"]
    lines += [':root, [data-theme="light"] {', *_colors("light", "  "), "}"]
    lines += ['[data-theme="dark"] {', *_colors("dark", "  "), "}"]
    lines += ["@media (prefers-color-scheme: dark) {", '  :root:not([data-theme="light"]) {', *_colors("dark", "    "), "  }", "}"]
    return "\n".join(lines) + "\n"


def components_css() -> str:
    """components.css with its comments and blank lines stripped."""
    text = re.sub(r"/\*.*?\*/", "", design_text("components.css"), flags=re.S)
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip()) + "\n"


@functools.cache
def system_css() -> str:
    """The tokens, then the components: the style every built-in page starts from."""
    return tokens_css() + components_css()


def devices_json() -> str:
    """The device table as the prototype tool reads it, `devices.json` beside `prototype.py`: the frames of
    `$extensions.aidd.device`, each with its source and the day it was read."""
    block = tokens()["$extensions"]["aidd"]["device"]
    note = "Generated from src/aidd/views/design/tokens.json by `aidd gen-docs`: never edit by hand."
    return json.dumps({"$generated": note, **block}, indent=2, ensure_ascii=False) + "\n"


def _hex(value: object) -> str:
    if isinstance(value, str):
        return value
    assert isinstance(value, dict)
    alpha = f"{round(value['alpha'] * 255):02x}" if "alpha" in value else ""
    return str(value["hex"]) + alpha


@functools.cache
def design_front_matter() -> str:
    """DESIGN.md's token front matter, between its `# generated` and `# end generated` lines: the colors by role (a dark
    one as `<role>-dark`), the typography, rounded, and spacing groups, and a `components` entry per text pair in both
    themes, so a DESIGN.md linter checks the pairs too."""
    data = tokens()
    lines = ["colors:"]
    for theme in THEMES:
        end = "" if theme == "light" else "-dark"
        for role, t in _entries(data["color"][theme]):
            value = t["$value"]
            if isinstance(value, str):
                lines.append(f'  {role}{end}: "{{colors.{_role(value)}{end}}}"')
            else:
                lines.append(f'  {role}{end}: "{_hex(value)}"')
    lines.append("typography:")
    for name, t in _entries(data["typography"]):
        v = t["$value"]
        family, size, weight = (_lookup(data, _alias(v[key]))["$value"] for key in ("fontFamily", "fontSize", "fontWeight"))
        lines += [
            f"  {name}:",
            f'    fontFamily: "{", ".join(family)}"',
            f"    fontSize: {_length(size)}",
            f"    fontWeight: {weight}",
            f"    lineHeight: {_num(v['lineHeight'])}",
            f"    letterSpacing: {_length(v['letterSpacing'])}",
        ]
    lines.append("rounded:")
    lines += [f"  {name}: {_length(t['$value'])}" for name, t in _entries(data["radius"])]
    lines.append("spacing:")
    lines += [f'  "{name}": {_length(t["$value"])}' for name, t in _entries(data["spacing"])]
    lines.append("components:")
    for fg, bg, least, _ in data["$extensions"]["aidd"]["contrast"]["pairs"]:
        if least < 4.5:
            continue
        for end in ("", "-dark"):
            lines += [f"  {fg}-on-{bg}{end}:", f'    backgroundColor: "{{colors.{bg}{end}}}"', f'    textColor: "{{colors.{fg}{end}}}"']
    return "\n".join(lines) + "\n"


FRONT_MATTER = re.compile(r"(^# generated[^\n]*\n)(.*?)(^# end generated$)", re.S | re.M)


def with_design_front_matter(text: str) -> str:
    """`text`, a DESIGN.md, with its generated token front matter rewritten from tokens.json."""
    if not FRONT_MATTER.search(text):
        raise ValueError("DESIGN.md has no `# generated` ... `# end generated` lines for its token front matter")
    return FRONT_MATTER.sub(lambda m: m.group(1) + design_front_matter() + m.group(3), text, count=1)
