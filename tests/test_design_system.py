"""The design system of aidd's built-in pages: one source, `src/aidd/views/design/tokens.json` with
`components.css`, and everything else generated from it.

The tokens' CSS and DESIGN.md's front matter come from tokens.json, the prototype tool's `system.css` equals
`system_css()` byte for byte, every color pair a page draws passes WCAG 2.2 AA in both themes, the comfort bands above
that floor hold, the components name tokens only, and the system's CSS keeps its byte budget."""

import base64
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import budgets
import design_lint
from helpers import ROOT

from aidd.views import design_tokens

DESIGN = ROOT / "src" / "aidd" / "views" / "design"
SYSTEM = ROOT / "plugins" / "aidd-team" / "tools" / "prototype" / "system.css"


def luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 2.2's relative luminance of an sRGB color."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def apca(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    """APCA-W3 0.0.98G-4g's lightness contrast, |Lc|, of text `fg` on `bg`: the comfort bands' measure."""

    def y(rgb: tuple[float, float, float]) -> float:
        v = sum(k * c**2.4 for k, c in zip((0.2126729, 0.7151522, 0.0721750), rgb, strict=True))
        return v + (0.022 - v) ** 1.414 if v < 0.022 else v

    yt, yb = y(fg), y(bg)
    if abs(yb - yt) < 0.0005:
        return 0.0
    s = (yb**0.56 - yt**0.57) * 1.14 if yb > yt else (yb**0.65 - yt**0.62) * 1.14
    return 0.0 if abs(s) < 0.1 else (abs(s) - 0.027) * 100


def oklch(rgb: tuple[float, float, float]) -> tuple[float, float]:
    """A color's OKLCH lightness and chroma, as CSS Color 4 converts sRGB."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    lms = [(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)]
    lms.append(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    l_, m_, s_ = (v ** (1 / 3) for v in lms)
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b2 = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_, (a * a + b2 * b2) ** 0.5


class ContrastTests(unittest.TestCase):
    def test_every_pair_a_page_draws_passes_wcag_aa_in_both_themes(self):
        pairs = design_tokens.tokens()["$extensions"]["aidd"]["contrast"]["pairs"]
        self.assertGreaterEqual(len(pairs), 31)
        for fg, bg, least, where in pairs:
            self.assertGreaterEqual(least, 3, f"{fg} on {bg}: WCAG 2.2 AA asks at least 3 for a control and 4.5 for text")
            for theme in design_tokens.THEMES:
                with self.subTest(pair=f"{fg} on {bg}", theme=theme):
                    got = ratio(design_tokens.color(theme, fg), design_tokens.color(theme, bg))
                    self.assertGreaterEqual(got, least, f"{fg} on {bg} ({where}) is {got:.2f}:1 in {theme}, below {least}")

    def test_a_role_with_alpha_is_measured_as_drawn_over_the_page(self):
        # A pair names the color a person sees: an alpha role, such as a hairline drawn as the text at a low alpha, is
        # composited over the theme's page before its ratio is taken, never measured as its opaque ink.
        drawn = 0
        for theme in design_tokens.THEMES:
            page = design_tokens.color(theme, "background")
            for role, token in design_tokens.tokens()["color"][theme].items():
                value = token["$value"] if not role.startswith("$") else None
                if not isinstance(value, dict) or "alpha" not in value:
                    continue
                drawn += 1
                want = [value["alpha"] * c + (1 - value["alpha"]) * p for c, p in zip(value["components"], page, strict=True)]
                for got, expected in zip(design_tokens.color(theme, role), want, strict=True):
                    self.assertAlmostEqual(got, expected, places=9, msg=f"{theme} {role}")
        self.assertGreater(drawn, 0)

    def test_a_color_whose_hex_and_components_disagree_fails(self):
        data = json.loads((DESIGN / "tokens.json").read_text(encoding="utf-8"))
        value = data["color"]["light"]["background"]["$value"]
        value["hex"] = "#" + "".join(f"{255 - round(c * 255):02x}" for c in value["components"])  # its opposite
        self._fails_on(data, "components and hex")

    def test_an_alias_that_names_no_token_fails(self):
        data = json.loads((DESIGN / "tokens.json").read_text(encoding="utf-8"))
        data["color"]["dark"]["card"]["$value"] = "{color.dark.nothing}"
        self._fails_on(data, "names no token")

    def test_a_pair_naming_a_role_a_theme_lacks_fails(self):
        data = json.loads((DESIGN / "tokens.json").read_text(encoding="utf-8"))
        del data["color"]["dark"]["comment-subtle"]
        self._fails_on(data, "the dark theme lacks")

    def test_a_value_outside_the_grammar_fails_so_none_can_end_a_rule_or_a_style_block(self):
        cases = (  # (where in tokens.json, the hostile value, the words the error names)
            (("color", "light", "background", "$value", "hex"), "#ffffff;}</style><style>", "six lower-case hex digits"),
            (("color", "light", "foreground", "$value", "hex"), "#1c1b19\n", "six lower-case hex digits"),
            (("color", "dark", "card", "$value"), "{color.dark.background}\n", "not an alias"),
            (("font", "family", "sans", "$value"), ['Inter"; } a { color: red'], "family names"),
            (("spacing", "1", "$value", "unit"), "px;}", "a unit from"),
            (("font", "line-height", "body", "$value"), float("inf"), "finite number"),
            (("color", "dark", "card", "$value"), "not an alias", "not an alias"),
            (("typography", "body", "$value", "fontSize"), "{font.size.nothing}", "names no token"),
        )
        for path, value, words in cases:
            with self.subTest(path=".".join(path)):
                data = json.loads((DESIGN / "tokens.json").read_text(encoding="utf-8"))
                node = data
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                self._fails_on(data, words)
        data = json.loads((DESIGN / "tokens.json").read_text(encoding="utf-8"))
        data["color"]["light"]["ring}</style>"] = data["color"]["light"]["ring"]
        self._fails_on(data, "lower-case letters")

    def test_the_status_page_refuses_a_style_that_would_end_its_style_block(self):
        from aidd import views

        cached = (design_tokens.tokens, design_tokens.tokens_css, design_tokens.system_css)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tokens.json").write_text((DESIGN / "tokens.json").read_text(encoding="utf-8"), encoding="utf-8")
            (Path(d) / "components.css").write_text(".a { color: var(--foreground); }</STYLE><b>\n", encoding="utf-8")
            for f in cached:
                f.cache_clear()
            try:
                with (
                    mock.patch.object(design_tokens, "design_text", lambda name: (Path(d) / name).read_text(encoding="utf-8")),
                    self.assertRaisesRegex(ValueError, "</style"),
                ):
                    views.status_page({"schema_version": "1", "items": [], "due": []})
            finally:
                for f in cached:
                    f.cache_clear()

    def _fails_on(self, data: dict, words: str) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tokens.json").write_text(json.dumps(data), encoding="utf-8")
            design_tokens.tokens.cache_clear()
            try:
                with (
                    mock.patch.object(design_tokens, "design_text", lambda name: (Path(d) / name).read_text(encoding="utf-8")),
                    self.assertRaisesRegex(ValueError, words),
                ):
                    design_tokens.tokens()
            finally:
                design_tokens.tokens.cache_clear()


class GeneratedTests(unittest.TestCase):
    def test_the_prototype_tools_system_css_is_the_one_source_byte_for_byte(self):
        self.assertEqual(SYSTEM.read_text(encoding="utf-8"), design_tokens.system_css(), "run `aidd gen-docs`")

    def test_gen_docs_check_names_a_stale_system_css_and_front_matter(self):
        from aidd.docsgen import generate

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / generate.SYSTEM_CSS).parent.mkdir(parents=True)
            page = design_tokens.tokens()["color"]["light"]["background"]["$value"]["hex"]
            (root / generate.SYSTEM_CSS).write_text(design_tokens.system_css().replace(page, "#123456"), encoding="utf-8")
            (root / generate.DESIGN_DOC).parent.mkdir(parents=True)
            text = (ROOT / generate.DESIGN_DOC).read_text(encoding="utf-8")
            (root / generate.DESIGN_DOC).write_text(text.replace(f'background: "{page}"', 'background: "#123456"'), encoding="utf-8")
            stale = generate.gen_docs(root, check=True)
            self.assertIn(root / generate.SYSTEM_CSS, stale)
            self.assertIn(root / generate.DESIGN_DOC, stale)
            self.assertIn("#123456", (root / generate.SYSTEM_CSS).read_text(encoding="utf-8"), "--check writes nothing")

    def test_the_reference_page_matches_its_source_until_gen_docs_writes_it(self):
        # A person rebuilds docs/design/reference.html by hand, so this holds what a builder would: its one style
        # block is the tokens, the raw components, then its own layout, under a CSP that names its hash.
        text = (ROOT / "docs" / "design" / "reference.html").read_text(encoding="utf-8")
        style = text.split("<style>", 1)[1].split("</style>", 1)[0]
        source = design_tokens.tokens_css() + (DESIGN / "components.css").read_text(encoding="utf-8")
        self.assertTrue(style.startswith(source), "rebuild the reference page's style block from tokens.json and components.css")
        self.assertTrue(style[len(source) :].startswith("/* The reference page's own layout"), "its own layout comes after the system")
        digest = base64.b64encode(hashlib.sha256(style.encode("utf-8")).digest()).decode()
        self.assertIn(f"style-src &#x27;sha256-{digest}&#x27;", text, "the CSP names the style block's hash")
        body = text.split("</head>", 1)[1]
        for name in re.findall(r"^  (--[\w-]+):", design_tokens.tokens_css().split("}", 1)[0], re.M):
            if name.endswith("--line-height"):
                continue  # shown beside its size, as "0.75rem / 1.35"
            self.assertIn(f"<code>{name}</code>", body, f"the reference page lists the token {name}")
        columns = body.split('data-theme="light" aria-labelledby', 1)[1].split('data-theme="dark" aria-labelledby', 1)
        for theme, column in zip(design_tokens.THEMES, columns, strict=True):
            for role, token in design_tokens.tokens()["color"][theme].items():
                if role.startswith("$"):
                    continue
                value, mix = token["$value"], token.get("$extensions", {}).get("aidd", {}).get("mix")
                if isinstance(value, str):
                    shown = "= " + value.strip("{}").rsplit(".", 1)[-1]
                elif mix:
                    shown = f"{mix[0].strip('{}').rsplit('.', 1)[-1]} at {mix[1]:g}%"
                else:
                    shown = value["hex"] + (f" at {value['alpha']:g}" if "alpha" in value else "")
                self.assertIn(f"<code>--{role}</code><small>{shown}", column, f"the {theme} column shows --{role} as {shown}")
        for fg, bg, _, _ in design_tokens.tokens()["$extensions"]["aidd"]["contrast"]["pairs"]:
            got = [f"<td>{ratio(design_tokens.color(t, fg), design_tokens.color(t, bg)):.2f}</td>" for t in design_tokens.THEMES]
            self.assertIn(f"<td><code>{fg}</code> on <code>{bg}</code></td>", body, f"the contrast table lists {fg} on {bg}")
            row = body.split(f"<td><code>{fg}</code> on <code>{bg}</code></td>", 1)[1].split("</tr>", 1)[0]
            self.assertTrue(row.endswith("".join(got)), f"the contrast table's ratios for {fg} on {bg} match tokens.json")

    def test_design_md_front_matter_is_generated_from_tokens_json(self):
        text = (ROOT / "docs" / "design" / "DESIGN.md").read_text(encoding="utf-8")
        self.assertEqual(design_tokens.with_design_front_matter(text), text, "run `aidd gen-docs`")
        dark = design_tokens.tokens()["color"]["dark"]["comment"]["$value"]["hex"]
        self.assertIn(f'  comment-dark: "{dark}"\n', text)
        scrim = design_tokens.tokens()["color"]["light"]["scrim"]["$value"]
        self.assertIn(f'  scrim: "{scrim["hex"]}{round(scrim["alpha"] * 255):02x}"\n', text)  # an alpha color keeps its alpha

    def test_every_token_becomes_a_custom_property_in_tailwind_and_shadcn_names(self):
        css = design_tokens.tokens_css()
        scrim = design_tokens.tokens()["color"]["light"]["scrim"]["$value"]
        self.assertIn("--scrim: rgb({} {} {} / {:g});".format(*(round(c * 255) for c in scrim["components"]), scrim["alpha"]), css)
        data = design_tokens.tokens()

        def length(token: dict) -> str:
            return f"{token['$value']['value']:g}{token['$value']['unit']}"

        sans = data["font"]["family"]["sans"]["$value"]
        for name in (  # one of each kind, named and valued from tokens.json
            f"--spacing-1_5: {length(data['spacing']['1_5'])};",
            f"--text-body: {length(data['font']['size']['body'])};",
            f"--text-body--line-height: {data['font']['line-height']['body']['$value']:g};",
            f"--radius-full: {length(data['radius']['full'])};",
            f"--font-weight-semibold: {data['font']['weight']['semibold']['$value']};",
            "--ease-standard: cubic-bezier({});".format(", ".join(f"{v:g}" for v in data["ease"]["standard"]["$value"])),
            "--popover: var(--card);",  # an alias, as a var()
            "--font-sans: " + ", ".join(f'"{n}"' if " " in n else n for n in sans) + ";",  # a family with a space, quoted
        ):
            self.assertIn(name, css)
        # Dark by data-theme, and by the system's preference unless the page says light.
        self.assertIn('[data-theme="dark"] {\n  color-scheme: dark;', css)
        self.assertIn('@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {', css)
        self.assertIn(":root { --duration-fast: 0ms; --duration-base: 0ms; }", css)

    def test_the_system_css_drops_the_components_comments_and_keeps_its_budget(self):
        css = design_tokens.system_css()
        self.assertNotIn("/* The components", css)
        size = len(css.encode("utf-8"))
        self.assertTrue(budgets.within(size / 1024, budgets.SYSTEM_CSS_KIB), f"system.css is {size} bytes, past {budgets.SYSTEM_CSS_KIB} KiB")


class ComfortTests(unittest.TestCase):
    """Accessible is the floor and comfortable the target: each band in `$extensions.aidd.comfort`, checked in both themes,
    on aidd's own tokens and on the tokens a new project starts from."""

    BANDS = design_tokens.tokens()["$extensions"]["aidd"]["comfort"]
    ADOPTER = ROOT / ".agents" / "skills" / "aidd" / "assets" / "tokens.json"

    def adopter_color(self, theme: str, role: str) -> tuple[float, float, float]:
        tree = json.loads(self.ADOPTER.read_text(encoding="utf-8"))
        value = tree["color"][theme][role]["$value"]
        while isinstance(value, str):
            node = tree
            for part in value.strip("{}").split("."):
                node = node[part]
            value = node["$value"]
        r, g, b = value["components"]
        return r, g, b

    def body_text_sits_in_its_band(self, color, body: str, page: str) -> None:
        for theme in design_tokens.THEMES:
            with self.subTest(theme=theme, role=body):
                fg, bg = color(theme, body), color(theme, page)
                low, high = self.BANDS["body"]["apca"][theme]
                self.assertGreaterEqual(ratio(fg, bg), self.BANDS["body"]["wcag_min"])
                self.assertTrue(low <= apca(fg, bg) <= high, f"{body} on {page} in {theme} is Lc {apca(fg, bg):.1f}, outside {low} to {high}")

    def secondary_text_reads_but_steps_down(self, color, body: str, secondary: str, page: str) -> None:
        for theme in design_tokens.THEMES:
            with self.subTest(theme=theme, role=secondary):
                lc, top = apca(color(theme, secondary), color(theme, page)), apca(color(theme, body), color(theme, page))
                self.assertGreaterEqual(lc, self.BANDS["secondary_apca_min"], f"{secondary} in {theme} is Lc {lc:.1f}")
                self.assertGreaterEqual(top - lc, self.BANDS["emphasis_gap_min"], f"{secondary} in {theme} sits only {top - lc:.1f} below body text")

    def no_page_or_text_is_pure_white_or_black(self, color, roles: tuple[str, ...], page: str) -> None:
        for theme in design_tokens.THEMES:
            for role in roles:
                with self.subTest(theme=theme, role=role):
                    self.assertNotIn(tuple(round(c * 255) for c in color(theme, role)), {(255, 255, 255), (0, 0, 0)})
        lightness = oklch(color("dark", page))[0]
        self.assertGreaterEqual(lightness, self.BANDS["dark_page_oklch_l_min"], f"the dark {page} is OKLCH L {lightness:.3f}: a grey, never black")

    def test_body_text_sits_in_its_band(self):
        self.body_text_sits_in_its_band(design_tokens.color, "foreground", "background")

    def test_secondary_text_reads_but_steps_down(self):
        self.secondary_text_reads_but_steps_down(design_tokens.color, "foreground", "muted-foreground", "background")

    def test_no_page_or_text_role_is_pure_white_or_black(self):
        self.no_page_or_text_is_pure_white_or_black(design_tokens.color, ("background", "foreground", "muted-foreground"), "background")

    def test_fills_stay_calm(self):
        for theme in design_tokens.THEMES:
            for surface in self.BANDS["fill_surfaces"]:
                under = design_tokens.color(theme, surface)
                for role in self.BANDS["fills"]:
                    with self.subTest(theme=theme, fill=role, surface=surface):
                        lc = apca(design_tokens.color(theme, role), under)
                        self.assertLessEqual(lc, self.BANDS["fill_apca_max"], f"a {role} fill in {theme} is Lc {lc:.1f} on {surface}")
                with self.subTest(theme=theme, disabled="input", surface=surface):
                    lc = apca(design_tokens.color(theme, "input"), under)
                    self.assertGreaterEqual(lc, self.BANDS["disabled_apca_min"], f"disabled text in {theme} is Lc {lc:.1f} on {surface}: still visible")
            for role in self.BANDS["wide_fills"]:
                with self.subTest(theme=theme, wide_fill=role):
                    chroma = oklch(design_tokens.color(theme, role))[1]
                    self.assertLessEqual(chroma, self.BANDS["wide_fill_chroma_max"], f"{role} in {theme} has OKLCH chroma {chroma:.3f}")

    def test_text_never_has_opacity_and_prose_reads_easily(self):
        components = (DESIGN / "components.css").read_text(encoding="utf-8")
        colors = [design_tokens.tokens()["color"][t] for t in design_tokens.THEMES]
        alpha_roles = {r for c in colors for r, v in c.items() if isinstance(v, dict) and isinstance(v["$value"], dict) and "alpha" in v["$value"]}
        chrome = (SYSTEM.parent / "viewer.html").read_text(encoding="utf-8").split('<style id="viewer">', 1)[1].split("</style>", 1)[0]
        pages = {name: (ROOT / "src" / "aidd" / "views" / name).read_text(encoding="utf-8") for name in ("work_item_page.css", "exploration_page.css")}
        for case, css, allowed in (  # (where, its CSS, the selectors that may dim a decoration with opacity)
            ("components.css", components, ()),
            *((name, css, ()) for name, css in pages.items()),
            ("the viewer's chrome", chrome, (".pv-thumb-frame", ".pv-home")),
        ):
            for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
                selector, body = rule[0].strip(), rule[1]
                for value in re.findall(r"(?<![-\w])opacity:\s*([\d.]+)", body):
                    with self.subTest(case=case, selector=selector):
                        self.assertTrue(float(value) in (0, 1) or selector.endswith(allowed), f"{selector} draws opacity {value}")
                for value in re.findall(r"(?<![-\w])color:\s*([^;]+)", body):
                    with self.subTest(case=case, selector=selector, color=value):
                        self.assertNotRegex(value, r"color-mix|rgba|/", "text takes a solid role, never an alpha")
                        self.assertNotIn(value.strip().removeprefix("var(--").removesuffix(")"), alpha_roles, "text takes a solid role, never an alpha one")
        data = design_tokens.tokens()
        self.assertGreaterEqual(data["font"]["line-height"]["body"]["$value"], 1.5)
        self.assertGreaterEqual(data["typography"]["body"]["$value"]["lineHeight"], 1.5)
        self.assertLessEqual(data["container"]["prose"]["$value"]["value"], 32, "about 80 characters a line at the body size")
        self.assertIn(".prose { max-inline-size: var(--container-prose); }", components)

    def test_new_projects_start_comfortable(self):
        self.body_text_sits_in_its_band(self.adopter_color, "text", "surface")
        self.secondary_text_reads_but_steps_down(self.adopter_color, "text", "text-muted", "surface")
        self.no_page_or_text_is_pure_white_or_black(self.adopter_color, ("surface", "text", "text-muted"), "surface")
        # The divider is the text at a low alpha: retuning the text without it would leave a hairline of another hue.
        tree = json.loads(self.ADOPTER.read_text(encoding="utf-8"))
        for theme in design_tokens.THEMES:
            with self.subTest(theme=theme, role="divider"):
                divider = tree["color"][theme]["divider"]["$value"]
                self.assertEqual(tuple(divider["components"]), self.adopter_color(theme, "text"), "the divider is the text color")
                self.assertTrue(0.10 <= divider["alpha"] <= 0.14, divider["alpha"])


class TokensOnlyTests(unittest.TestCase):
    def test_the_components_name_tokens_only(self):
        self.assertEqual(design_lint.raw_values((DESIGN / "components.css").read_text(encoding="utf-8")), [])

    def test_the_status_page_lays_out_in_tokens_only_and_keeps_its_budget(self):
        css = (ROOT / "src" / "aidd" / "views" / "work_item_page.css").read_text(encoding="utf-8")
        self.assertEqual(design_lint.raw_values(css, layout=True), [])
        size = len(css.encode("utf-8"))
        self.assertTrue(budgets.within(size / 1024, budgets.WORK_PAGE_CSS_KIB), f"work_item_page.css is {size} bytes, past {budgets.WORK_PAGE_CSS_KIB} KiB")

    def test_the_explore_page_lays_out_in_tokens_only_and_keeps_its_budget(self):
        css = (ROOT / "src" / "aidd" / "views" / "exploration_page.css").read_text(encoding="utf-8")
        self.assertEqual(design_lint.raw_values(css, layout=True), [])
        size = len(css.encode("utf-8"))
        self.assertTrue(
            budgets.within(size / 1024, budgets.EXPLORE_PAGE_CSS_KIB), f"exploration_page.css is {size} bytes, past {budgets.EXPLORE_PAGE_CSS_KIB} KiB"
        )

    def test_the_viewers_chrome_names_tokens_only_and_keeps_its_budget(self):
        viewer = (SYSTEM.parent / "viewer.html").read_text(encoding="utf-8")
        css = viewer.split('<style id="viewer">', 1)[1].split("</style>", 1)[0]
        self.assertTrue(css.startswith("\n{{system}}\n"), "the tool inlines system.css before the chrome")
        # The viewer's own measures: the top bar's height, which a phone's layout changes, the side panels' widths, which its
        # script reads, the scale and zoom its script writes, and a board thumbnail's edge and the state rings drawn from it.
        defines = {"--pv-top-h", "--pv-nav-width", "--pv-inspector-width", "--pv-nav-column", "--pv-inspector-column", "--pv-scale", "--pv-zoom"}
        defines |= {  # in the order the chrome sets them
            "--pv-thumb-edge-width",
            "--pv-thumb-edge-color",
            "--pv-thumb-halo-color",
            "--pv-thumb-ring-gap",
            "--pv-thumb-thin-width",
            "--pv-thumb-thick-width",
            "--pv-thumb-snap-margin",
            "--pv-thumb-ring-offset",
            "--pv-thumb-outer-offset",
            "--pv-thumb-edge-halo",
            "--pv-thumb-outer-ring",
        }
        self.assertEqual(design_lint.raw_values(css, layout=True, defines=defines), [])
        self.assertEqual(css.count("/* device drawing: raw by design */"), 1, "the drawn device is one block")
        # The frame's own marks live in the design's document, where the system's tokens do not reach and rem is the
        # design's root size, so its outlines alone are in px; any other raw value, a color above all, fails.
        frame = viewer.split('<template id="frame-style"><style>', 1)[1].split("</style>", 1)[0]
        self.assertEqual([f for f in design_lint.raw_values(frame) if not re.search(r": outline(-offset)?: \d+px$", f)], [])
        size = len(css.encode("utf-8"))
        self.assertTrue(
            budgets.within(size / 1024, budgets.VIEWER_CHROME_CSS_KIB), f"the viewer's chrome is {size} bytes, past {budgets.VIEWER_CHROME_CSS_KIB} KiB"
        )

    def test_nothing_reads_the_hand_written_tokens_css_the_system_replaced(self):
        self.assertFalse((SYSTEM.parent / "tokens.css").exists())
        readers = [*(ROOT / "src" / "aidd").rglob("*.py"), *SYSTEM.parent.glob("*.*"), ROOT / "docs" / "architecture" / "README.md"]
        # The tool's file by its path or its bare name; a project's own design/tokens.css, its build's output, is another file.
        tool_file = re.compile(r'HERE / "tokens\.css"|prototype/tokens\.css|`tokens\.css`')
        named = [str(p.relative_to(ROOT)) for p in readers if tool_file.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(named, [])

    def test_the_lint_finds_each_kind_of_raw_value(self):
        css = (
            ".a { color: #fff; margin: 3px; padding: var(--nope); --own: 1; background: rgb(0 0 0); border-color: color(srgb 1 0 0);"
            " outline-color: white; gap: 2pt; line-height: 1.2; }\n@media (width < 33rem) { .b { width: 2rem; } }"
        )
        found = design_lint.raw_values(css)
        kinds = ("#fff", "3px", "var(--nope) names no token", "defines --own", "rgb(", "color(", "white", "2pt", "line-height: 1.2")
        for kind in (*kinds, "@media (width < 33rem): 33rem", "width: 2rem"):
            self.assertTrue(any(kind in f for f in found), (kind, found))
        # The allowlist: the visually hidden pattern, rem in a page's layout, a breakpoint, and the device drawing.
        allowed = (
            ".h { width: 1px; margin: -1px; clip-path: inset(50%); }\n.c { max-width: 30rem; }\n@media (width < 48rem) { .d { color: var(--foreground); } }\n"
            "/* device drawing: raw by design */ .e { background: #111214; } /* end device drawing */"
        )
        self.assertEqual(design_lint.raw_values(allowed, layout=True), [])


if __name__ == "__main__":
    unittest.main()
