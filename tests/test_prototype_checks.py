"""The prototype tool's checks on one design file: every link, state, test id, and name, and the prototype lint, each
problem with its line; the `screens` command; and the lines the commands print."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import copy_showcase_images, PROTOTYPE_TOOL, adopted_repo, run_cli

from aidd.kernel import json_schema, resources

pp = resources.team_tool("prototype")
checks = pp.design_checks
OK = r"\Aok: \d+ screens?, \d+ states?, \d+ test ids?\n\Z"
SHOWCASE = (PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8")


def tool(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """The tool as a person runs it with aidd-team alone: its own file, no aidd on the path (`-I`)."""
    return subprocess.run(
        [sys.executable, "-I", str(PROTOTYPE_TOOL / "prototype.py"), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60
    )


def swapped(text: str, old: str, new: str) -> str:
    """`text` with `old` replaced once. The edit must land, so a test never passes on a design it did not change."""
    assert text.count(old) == 1, f"{old!r} is in the design {text.count(old)} times, not once"
    return text.replace(old, new)


def sound_showcase() -> str:
    """The showcase as the check reads it. Its primary button's shadow is a raw rgb() outside the tokens block, which the
    lint rejects; this reads the design's own token instead, so the rest of the showcase is held to the other rules."""
    return SHOWCASE.replace("box-shadow: 0 1px 2px rgb(0 0 0 / 0.12)", "box-shadow: var(--shadow-raised)")


def lint_problems(text: str) -> list[tuple[int, str]]:
    """The lint over the whole design file, each problem as (line, message)."""
    return [(line, message) for line, message, _ in checks._lint(text)]


def line_of(text: str, needle: str) -> int:
    """The line of `text` that holds `needle`, counted from 1."""
    return next(n for n, line in enumerate(text.split("\n"), 1) if needle in line)


def broken_showcase() -> str:
    """The showcase with one fault for each rule, built here so no broken design is committed."""
    text = sound_showcase()
    text = swapped(text, 'data-go="sitters/success" data-testid="signin-submit"', 'data-go="nowhere" data-testid="signin-submit"')
    text = swapped(text, 'data-go="sitters/offline" data-testid="signin-saved"', 'data-go="sitters/offlin" data-testid="signin-saved"')
    text = swapped(text, 'data-parent="sitters" data-initial="success"', 'data-parent="nowhere" data-initial="sucess"')
    text = swapped(text, ".button-primary { border: 0;", ".button-primary { color: #ff0000; border: 0;")
    text = swapped(text, "Sign in to book a sitter, message them", "Lorem ipsum TODO, message them")
    text = swapped(text, "Signing you in…", "Signing you in 🙂…")
    text = swapped(
        text,
        '      <div data-state="empty" data-testid="signin-empty">\n',
        '      <div data-state="empty" data-testid="signin-empty">\n'
        '        <img src="https://example.com/a.png" alt="">\n'
        '        <button type="button"></button>\n'
        '        <img src="logo.png">\n'
        '        <input type="text" data-testid="signin-extra">\n'
        '        <button type="button" data-testid="signin-submit">Again</button>\n',
    )
    return swapped(
        text,
        "  </main>\n</div>\n</template>",
        '    <section data-screen="orphan" data-title="Orphan"><p>Nothing.</p></section>\n  </main>\n</div>\n</template>',
    )


def problems_of(markup: str) -> list[str]:
    """The problems of a small design's product part, without the file name."""
    found, _ = checks.check(markup, markup, 1, "d.html")
    return [p.removeprefix("d.html:") for p in found]


def screen(ident: str, body: str, **attrs: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<section data-screen="{ident}" data-title="{ident}"{extra}>{body}</section>\n'


def state(name: str, body: str) -> str:
    return f'<div data-state="{name}">{body}</div>'


def button(testid: str, label: str = "Go", **attrs: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<button type="button" data-testid="{testid}"{extra}>{label}</button>'


class BrokenDesignTests(unittest.TestCase):
    """One design with a fault for each rule: the check reports every one, with its line, and exits 1."""

    @classmethod
    def setUpClass(cls):
        cls.text = broken_showcase()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        (cls.root / "prototype.html").write_text(cls.text, encoding="utf-8")
        copy_showcase_images(cls.root)
        cls.done = tool(cls.root, "check", "prototype.html")
        cls.out = cls.done.stdout.splitlines()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def has(self, line: int, what: str) -> None:
        wanted = f"problem: prototype.html:{line}: {what}"
        self.assertTrue(any(o.startswith(wanted) for o in self.out), f"{wanted!r} is not in\n" + "\n".join(self.out))

    def test_it_exits_1_and_reports_every_problem_not_just_the_first(self):
        self.assertEqual(self.done.returncode, 1, self.done.stdout + self.done.stderr)
        self.assertEqual(len(self.out), 16, "\n".join(self.out))
        self.assertEqual(self.out[-1], "15 problem(s); fix them in prototype.html", "the tool counts them as aidd does")
        problems = self.out[:-1]
        self.assertTrue(all(o.startswith("problem: prototype.html:") for o in problems))
        self.assertEqual([int(o.split(":")[2]) for o in problems], sorted(int(o.split(":")[2]) for o in problems), "in the file's order")

    def test_a_link_names_a_screen_and_a_state_it_has(self):
        self.has(line_of(self.text, 'data-go="nowhere"'), 'data-go="nowhere" names no screen; name one of sign-in, sitters, sitter, orphan')
        self.has(line_of(self.text, "sitters/offlin"), 'data-go="sitters/offlin" names no state of `sitters`; did you mean `offline`? Name one of')

    def test_a_first_state_and_a_parent_name_what_they_should(self):
        line = line_of(self.text, 'data-parent="nowhere"')
        self.has(line, 'data-initial="sucess" names no state of `sitter`; did you mean `success`? Name one of loading, error, success')
        self.has(line, 'data-parent="nowhere" on screen `sitter` names no screen; name one of sign-in, sitters, sitter, orphan')

    def test_a_screen_has_a_state_and_the_first_screen_reaches_it(self):
        line = line_of(self.text, 'data-screen="orphan"')
        self.has(line, "screen `orphan` has no state; wrap its content in")
        self.has(line, "screen `orphan` is not reached from the first screen, `sign-in`, by any data-go")
        self.assertEqual(sum("has no state" in o for o in self.out), 1, "the safety reading's own wording is not said twice")

    def test_every_interactive_element_has_a_test_id_that_a_state_never_repeats(self):
        line = line_of(self.text, '<button type="button"></button>')
        self.has(line, "<button> has no data-testid; add one a test can select")
        again = line_of(self.text, '"signin-submit">Again')
        # The form's own button comes later in the file, so it is the one that repeats.
        self.has(line_of(self.text, 'data-go="nowhere"'), f'data-testid="signin-submit" repeats the one on line {again} in the same state')

    def test_a_control_has_a_name(self):
        self.has(line_of(self.text, '<button type="button"></button>'), "<button> has no name; put text inside it, or add an aria-label")
        self.has(line_of(self.text, '<img src="logo.png">'), "<img> has no alt; describe the image")
        self.has(line_of(self.text, 'data-testid="signin-extra"'), "<input> has no label")

    def test_the_prototype_lint_rules_fire(self):
        self.has(line_of(self.text, "color: #ff0000"), 'the raw color in "color: #ff0000" is outside the tokens block')
        self.has(line_of(self.text, "https://example.com/a.png"), "https://example.com/a.png loads from the network")
        self.has(line_of(self.text, "Lorem ipsum TODO"), 'placeholder text "Lorem ipsum"')
        self.has(line_of(self.text, "🙂"), "the emoji 🙂 is not an icon")

    def test_aidd_says_the_same_and_counts_the_problems(self):
        with adopted_repo() as root:
            (root / "prototype.html").write_text(self.text, encoding="utf-8")
            copy_showcase_images(root)
            code, out = run_cli("prototype", "--check", "prototype.html")
        self.assertEqual(code, 1)
        wrong = line_of(self.text, 'data-go="nowhere"')
        self.assertIn(f'problem: prototype.html:{wrong}: data-go="nowhere" names no screen', out)
        self.assertIn("15 problem(s); fix them in prototype.html", out)


class SoundDesignTests(unittest.TestCase):
    def test_the_check_says_ok_and_what_the_design_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(sound_showcase(), encoding="utf-8")
            copy_showcase_images(root)
            done = tool(root, "check", "prototype.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, OK)
        self.assertEqual(done.stdout.count("\n"), 1, "one line")

    def test_the_starting_design_passes_with_its_placeholders_in_place(self):
        """`{{spec}}` and the rest are skipped, never the whole file; a written design has none left."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "design.html").write_text((PROTOTYPE_TOOL / "design.html").read_text(encoding="utf-8"), encoding="utf-8")
            self.assertRegex(tool(root, "check", "design.html").stdout, OK)
            made = tool(root, "new-design", "a.html", "--title", "Cards")
            self.assertIn("next: sketch the direction in it, then `python3 ", made.stdout)
            self.assertIn(" build a.html` to see it", made.stdout)
            self.assertRegex(tool(root, "check", "a.html").stdout, OK)

    def test_aidd_prints_the_ok_line(self):
        with adopted_repo() as root:
            (root / "prototype.html").write_text(sound_showcase(), encoding="utf-8")
            copy_showcase_images(root)
            code, out = run_cli("prototype", "--check", "prototype.html")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, OK)

    def test_a_design_the_safety_reading_refuses_still_gets_its_other_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = swapped(
                sound_showcase(),
                '<button type="button" class="button button-secondary" data-component="button" data-variant="secondary" data-go="sitters/offline"',
                '<button onclick="x()" type="button" class="button button-secondary" data-component="button" data-variant="secondary" data-go="nowhere"',
            )
            (root / "prototype.html").write_text(text, encoding="utf-8")
            copy_showcase_images(root)
            done = tool(root, "check", "prototype.html")
        self.assertEqual(done.returncode, 1)
        self.assertIn("an event handler (onclick)", done.stdout)
        self.assertIn("names no screen", done.stdout)


class IntegrityRuleTests(unittest.TestCase):
    """The rules on small designs: what each allows, and what it flags."""

    def test_a_test_id_may_repeat_across_states_and_screens_and_in_an_item_template(self):
        markup = (
            screen("a", state("one", button("go") + "<ul data-list='x' data-item-template='row'></ul>") + state("two", button("go")), data_initial="one")
            + screen("b", state("one", button("go")))
            + '<template data-item-template="row"><li><button type="button" data-testid="row">Row</button><button type="button" data-testid="row">Row</button></li></template>'
        )
        self.assertEqual([p for p in problems_of(markup) if "repeats" in p], [])

    def test_a_test_id_on_the_chrome_or_outside_a_state_repeats_in_every_state(self):
        markup = button("tab") + screen("a", button("tab") + state("one", button("x")) + state("two", button("y")))
        self.assertEqual(sum('data-testid="tab" repeats' in p for p in problems_of(markup)), 1)

    def test_the_first_screen_reaches_the_others_through_a_screen_or_the_chrome(self):
        chain = screen("a", state("s", button("a1", data_go="b"))) + screen("b", state("s", button("b1", data_go="c"))) + screen("c", state("s", "<p>End</p>"))
        self.assertEqual(problems_of(chain), [])
        cut = chain.replace(' data-go="b"', "")
        self.assertEqual([p.split("`")[1] for p in problems_of(cut) if "not reached" in p], ["b", "c"])
        self.assertEqual([p for p in problems_of(button("tab", data_go="b") + button("tab2", data_go="c") + cut) if "not reached" in p], [])

    def test_a_name_comes_from_text_a_label_an_alt_or_a_runtime_fill(self):
        named = (
            '<button type="button" data-testid="a">Text</button>'
            '<button type="button" data-testid="b" aria-label="Close"></button>'
            '<button type="button" data-testid="c"><svg aria-hidden="true"></svg><span class="sr-only">Hidden text</span></button>'
            '<button type="button" data-testid="d"><img src="x.png" alt="Logo"></button>'
            '<button type="button" data-testid="e"><span data-field="name"></span></button>'
            '<a href="#" data-testid="f" title="Help"></a>'
            '<label for="g">Email</label><input id="g" data-testid="g">'
            '<label>Name <input data-testid="h"></label>'
            '<input type="submit" value="Save" data-testid="i">'
            '<input type="hidden" name="token">'
            '<img src="x.png" alt="">'
        )
        self.assertEqual(problems_of(screen("a", state("s", named))), [])
        unnamed = '<button type="button" data-testid="a"><svg aria-hidden="true"><title>Hidden</title></svg></button><select data-testid="b"></select><textarea data-testid="c"></textarea><a data-testid="d"> </a>'
        self.assertEqual(len(problems_of(screen("a", state("s", unnamed)))), 4)

    def test_the_ok_line_counts_screens_states_and_distinct_test_ids(self):
        markup = screen("a", state("one", button("go") + button("stop")) + state("two", button("go"))) + screen("b", state("one", button("go")))
        self.assertEqual(checks.summary(checks.read_design(markup, "d.html")), "ok: 2 screens, 3 states, 2 test ids")
        self.assertEqual(checks.summary(checks.read_design(screen("a", state("one", button("go"))), "d.html")), "ok: 1 screen, 1 state, 1 test id")

    def test_a_starting_designs_placeholders_are_skipped(self):
        markup = screen("a", state("s", button("a", data_go="{{next}}")))
        self.assertEqual(problems_of(markup), [])

    def test_a_design_with_no_screen_says_so_and_a_link_has_none_to_name(self):
        self.assertEqual(len(problems_of("<p>Nothing</p>")), 1)
        self.assertIn("1: the design draws no screen", problems_of("<p>Nothing</p>")[0])
        self.assertIn("names no screen; this design draws no screen to name", " ".join(problems_of(button("a", data_go="x"))))

    def test_duplicate_ids_and_broken_aria_labelledby_fail_while_valid_ones_pass(self):
        good = screen("a", state("s", '<h2 id="title-a">Title</h2><section aria-labelledby="title-a"><p>Body</p></section>'))
        self.assertEqual(problems_of(good), [])
        dup = screen("a", state("s", '<h2 id="same">One</h2><h2 id="same">Two</h2>'))
        self.assertEqual(len([p for p in problems_of(dup) if 'id="same" repeats' in p]), 1)
        broken = screen("a", state("s", '<div aria-labelledby="title-a missing-id">Hi</div>'))
        self.assertEqual(len([p for p in problems_of(broken) if "aria-labelledby" in p and "`missing-id`" in p]), 1)


class LintRuleTests(unittest.TestCase):
    """The prototype lint rules of the screenshot reference, over the whole file."""

    def lint(self, text: str) -> list[tuple[int, str]]:
        return lint_problems(text)

    def test_the_tokens_block_may_hold_colors_and_nothing_else_may(self):
        tokens = '<style id="tokens">\n:root { --color-accent: #1d4ed8; }\n</style>\n'
        self.assertEqual(self.lint(tokens + "<style>.a { color: var(--color-accent); }</style>\n"), [])
        for raw in ("color: #fff", "background: rgb(0 0 0 / 0.1)", "box-shadow: 0 0 oklch(0.5 0.1 200)", "border-color: hsl(10 20% 30%)"):
            with self.subTest(raw=raw):
                self.assertEqual([n for n, _ in self.lint(tokens + f"<style>.a {{ {raw}; }}</style>\n")], [4])
        self.assertEqual([n for n, _ in self.lint(tokens + '<p style="color:#123456">x</p>\n')], [4], "a style attribute too")
        self.assertEqual(self.lint('<style id="tokens">:root { --c: #fff; }</style>\n<p>Fine</p>\n'), [], "a one-line block")

    def test_a_hotlink_a_placeholder_and_an_emoji(self):
        text = "\n".join(
            [
                '<img src="https://cdn.example.com/a.png">',
                '<link href="http://fonts.example.com/a.css">',
                "<style>@import url(a.css); .a { background: url('https://x.test/a.png'); }</style>",
                "<p>Name: John Doe</p>",
                "<p>Fixme later</p>",
                "<p>Copyright © 2026, ® and ™ are fine; so is → and ✓</p>",
                "<p>Save ✔</p>",
            ]
        )
        self.assertEqual([n for n, _ in self.lint(text)], [1, 2, 3, 4, 5, 7])
        self.assertEqual(self.lint('<img src="a.png" alt="">\n<p>A local image and a todolist</p>\n'), [])

    def test_custom_property_and_svg_raw_colors_and_extended_hotlinks_or_todo(self):
        tokens = '<style id="tokens">\n:root { --color-accent: #1d4ed8; }\n</style>\n'
        self.assertEqual([n for n, _ in self.lint(tokens + "<style>.a { --brand: #123456; }</style>\n")], [4])
        svg_problems = problems_of(screen("a", state("s", '<svg viewBox="0 0 1 1"><path fill="#123456" stroke="rgb(1 2 3)" d="M0 0"/></svg>')))
        self.assertEqual(len([p for p in svg_problems if "raw color in " in p]), 2)
        hotlinks = "\n".join(
            [
                '<img src="//cdn.example.com/a.png">',
                '<img SRC="https://cdn.example.com/upper.png">',
                '<style>@import "theme.css";</style>',
                '<img srcset="a.png 1x, https://cdn.example.com/b.png 2x" alt="">',
                '<video poster="https://cdn.example.com/p.jpg"></video>',
                "<p>TODO later</p>",
                "<p>Track TODO-104</p>",
            ]
        )
        self.assertEqual([n for n, _ in self.lint(hotlinks)], [1, 2, 3, 4, 5, 6])

    def test_a_named_color_is_raw_in_css_and_in_svg_and_a_word_that_is_not_in_a_color_value_is_text(self):
        # CSS Color 4's named colors, case-blind. In a custom property only a value that is one name counts, as it has no type.
        raw = (
            "color: red",
            "background: rebeccapurple",
            "border: 1px solid RED",
            "background: linear-gradient(red, blue)",
            "box-shadow: 0 0 0 1px Black",
            "accent-color: tan",
            "color: var(--x, red)",
            "background: color-mix(in srgb, red 50%, white)",
            "--brand: gold",
        )
        # No color of its own (transparent, currentColor, the CSS-wide keywords, none), a system color, and a word that is no color value.
        fine = (
            *(f"color: {word}" for word in ("transparent", "currentColor", "inherit", "initial", "unset", "revert", "revert-layer")),
            "border: none",
            "outline: none",
            *(f"background: {word}" for word in ("Canvas", "CanvasText", "ButtonFace", "AccentColor")),
            "color: var(--red)",
            "background: url(red.png)",
            "background-image: url('tan red.png')",
            "font-family: Tan",
            "content: 'red'",
            "width: calc(tan(1deg) * 1px)",
            "--font: Tan, serif",
            "--space: 8px",
        )
        for declaration in raw:
            with self.subTest(raw=declaration):
                self.assertEqual([n for n, _ in self.lint(f"<style>.a {{ {declaration}; }}</style>\n")], [1])
                self.assertEqual([n for n, _ in self.lint(f'<p style="{declaration}">x</p>\n')], [1], "a style attribute too")
        for declaration in fine:
            with self.subTest(fine=declaration):
                self.assertEqual(self.lint(f"<style>.a {{ {declaration}; }}</style>\n"), [])
        text = '<style>.red, .orange { margin: 0 }</style>\n<p class="red">Orange and Tan, with a white tan line</p>\n<a href="red.html">Red</a>\n'
        self.assertEqual(self.lint(text), [], "a color's name outside a color value is a class, a link, or text")

        def svg_paint(attribute: str, value: str) -> list[str]:
            body = f'<svg viewBox="0 0 1 1" aria-hidden="true"><path {attribute}="{value}" d="M0 0"/></svg>'
            return [p for p in problems_of(screen("a", state("s", body))) if "raw color in " in p]

        for attribute in ("fill", "stroke"):
            for value in ("red", "Tan", "rebeccapurple", "#123456", "rgb(1 2 3)"):
                with self.subTest(attribute=attribute, raw=value):
                    self.assertEqual(len(svg_paint(attribute, value)), 1)
            for value in (
                "none",
                "currentColor",
                "transparent",
                "inherit",
                "initial",
                "unset",
                "revert",
                "revert-layer",
                "Canvas",
                "CanvasText",
                "var(--c)",
                "url(#g)",
            ):
                with self.subTest(attribute=attribute, fine=value):
                    self.assertEqual(svg_paint(attribute, value), [])


class DepthRuleTests(unittest.TestCase):
    """The depth family: outside the tokens block a shadow is a ring or wholly var(), and a blur is zero or wholly var()."""

    # The tokens block is lines 1 to 3 and the style block opens on line 4, so a rule written by `rule` is on line 5.
    TOKENS = '<style id="tokens">\n:root { --shadow-raised: 0 1px 2px var(--c); --filter-glass: saturate(1.2) blur(8px); }\n</style>\n'
    DRAWS_DEPTH = (
        "box-shadow: 0 4px 12px var(--c)",
        "box-shadow: 0 1px 0 var(--c)",
        "box-shadow: 1px 0 0 var(--c)",
        "box-shadow: 0 0 8px var(--c)",
        "box-shadow: 0 0 0.5px var(--c)",
        "box-shadow: inset 0 2px 4px var(--c)",
        "box-shadow: var(--a), 0 1px 2px var(--c)",
        "box-shadow: 0 0 0 1px var(--c), 0 8px 16px var(--c)",
        "box-shadow: 0 0 var(--b) var(--c)",
        "box-shadow: var(--x, 0 8px 24px var(--c))",
        "box-shadow: var(--x, var(--y, 0 8px 24px var(--c)))",
        "box-shadow: 0 0 0 1px var(--c), var(--x, 0 8px 24px var(--c))",
        "box-shadow: var(--x, 0 0 0 1px var(--c), 0 8px 24px var(--c))",
        "box-shadow: " + "var(--x, " * 9 + "none" + ")" * 9,
        "box-shadow: var(--a) var(--b)",
        "box-shadow: 0 0 0 1px var(--c) 0 0 0 1px var(--c)",
        "BOX-SHADOW: 0 1px 2px var(--c) !important",
        "-webkit-box-shadow: 0 1px 2px var(--c)",
        "text-shadow: 0 1px 0 var(--c)",
        "filter: blur(4px)",
        "filter: blur(0.1px)",
        "filter: saturate(1.2) blur(8px)",
        "filter: drop-shadow(0 1px 2px var(--c))",
        "filter: drop-shadow(1px 0 0 var(--c))",
        "backdrop-filter: saturate(1.2) blur(8px)",
        "-webkit-backdrop-filter: blur(8px)",
        "backdrop-filter: blur(calc(2 * var(--u)))",
    )
    DRAWS_NO_DEPTH = (
        "box-shadow: none",
        "box-shadow: none !important",
        "box-shadow: var(--x, none)",
        "box-shadow: var(--x, var(--shadow-raised))",
        "box-shadow: var(--x, 0 0 0 1px var(--c))",
        "box-shadow: var(--x, var(--y, none))",
        "box-shadow: " + "var(--x, " * 8 + "none" + ")" * 8,
        "box-shadow: inherit",
        "box-shadow: var(--shadow-raised)",
        "box-shadow: 0 0 0 1px var(--c)",
        "box-shadow: 0 0 0 1px var(--c) !important",
        "box-shadow: 0 0 0 calc(2 * var(--u)) var(--c)",
        "box-shadow: inset 0 0 0 1px var(--c)",
        "box-shadow: 0 0 0 1px var(--c) inset",
        "box-shadow: 0px 0px 0px 2px var(--c)",
        "box-shadow: 0em 0rem 0% 1px var(--c)",
        "box-shadow: 0 0 var(--c)",
        "box-shadow: var(--c) 0 0 0 1px",
        "box-shadow: 0 0 0 -1px var(--c)",
        "box-shadow: 0 0 0 1px",
        "box-shadow: 0 0 0 1px rgb(0 0 0 / 0.1)",
        "box-shadow: 0 0 0 var(--w) var(--c)",
        "box-shadow: var(--a), 0 0 0 1px var(--c)",
        "box-shadow: 0 0 0 1px var(--c), inset 0 0 0 2px var(--d)",
        "text-shadow: 0 0 0 var(--c)",
        "filter: none",
        "filter: blur(0)",
        "filter: blur(0px)",
        "filter: var(--filter-glass)",
        "filter: url(#soft)",
        "filter: saturate(1.2) brightness(0.9)",
        "filter: drop-shadow(0 0 0 var(--c))",
        "filter: drop-shadow(var(--ds))",
        "backdrop-filter: none",
        "backdrop-filter: blur(0)",
        "backdrop-filter: blur(var(--blur-glass))",
        "backdrop-filter: saturate(1.2)",
        "background: linear-gradient(90deg, var(--c) 40%, var(--d) 60%) 0 0 / 300% 100%",
    )

    @staticmethod
    def depth(text: str) -> list[int]:
        """The lines the depth family flags in `text`."""
        return [line for line, _, rule in checks._lint(text) if rule == "depth"]

    def rule(self, declaration: str) -> str:
        return self.TOKENS + f"<style>\n.a {{ {declaration}; }}\n</style>\n"

    def test_each_form_that_draws_depth_is_flagged_on_its_line_and_each_ring_or_token_is_not(self):
        for declaration in self.DRAWS_DEPTH:
            with self.subTest(draws=declaration):
                self.assertEqual(self.depth(self.rule(declaration)), [5])
                self.assertEqual(self.depth(f'<p style="{declaration}">x</p>\n'), [1], "a style attribute too")
                self.assertEqual(self.depth(f"<style>\n@media (min-width: 40rem) {{\n  .a {{ {declaration}; }}\n}}\n</style>\n"), [3], "in an @media block")
                self.assertEqual(self.depth(f"<style>.a {{ margin: 0; {declaration} }}</style>\n"), [1], "after another declaration, with no end mark")
        for declaration in self.DRAWS_NO_DEPTH:
            with self.subTest(draws_none=declaration):
                for text in (
                    self.rule(declaration),
                    f'<p style="{declaration}">x</p>\n',
                    f"<style>@media (min-width: 40rem) {{ .a {{ {declaration}; }} }}</style>",
                ):
                    self.assertEqual(self.depth(text), [])

    def test_an_at_rules_condition_is_no_declaration_and_the_block_inside_it_is_read(self):
        for condition in (
            "@supports (backdrop-filter: blur(10px))",
            "@supports not (box-shadow: 0 8px 24px var(--c))",
            "@supports (filter: blur(2px)) and (text-shadow: 0 1px 0 var(--c))",
            "@media (min-width: 40rem)",
        ):
            with self.subTest(condition=condition):
                self.assertEqual(self.depth(f"<style>\n{condition} {{\n  .g {{ margin: 0 }}\n}}\n</style>\n"), [])
                self.assertEqual(self.depth(f"<style>\n{condition} {{\n  .g {{ box-shadow: 0 8px 24px var(--c) }}\n}}\n</style>\n"), [3])
        self.assertEqual(
            self.depth("<style>@supports (box-shadow: 0 8px 24px var(--c)) { .g { margin: 0 } } .h { box-shadow: 0 8px 24px var(--c) }</style>"), [1]
        )

    def test_a_single_quoted_style_attribute_ends_at_its_quote(self):
        self.assertEqual(self.depth("<p style='box-shadow:none'>x</p>\n"), [])
        self.assertEqual(self.depth("<p style='box-shadow: 0 0 0 1px var(--c)'>x</p>\n"), [])
        self.assertEqual(self.depth("<p style='box-shadow:0 8px 24px var(--c)'>x</p>\n"), [1], "a shadow in one is still read")

    def test_the_findings_come_in_line_order_whichever_rule_found_them(self):
        text = "<p>\u2728</p>\n<style>.a { box-shadow: 0 8px 24px var(--c) }</style>\n<p>TODO</p>\n"
        self.assertEqual([(line, rule) for line, _, rule in checks._lint(text)], [(1, "emoji"), (2, "depth"), (3, "placeholder")])

    def test_when_two_tokens_hold_the_same_value_the_first_is_named(self):
        tokens = '<style id="tokens">:root { --first: 0 6px 18px var(--c); --second: 0 6px 18px var(--c); }</style>\n'
        said = next(message for _, message, rule in checks._lint(tokens + "<style>.a { box-shadow: 0 6px 18px var(--c) }</style>\n") if rule == "depth")
        self.assertIn("var(--first)", said)
        self.assertNotIn("--second", said)

    def test_a_value_on_two_lines_is_one_value_on_the_line_of_its_property(self):
        for split in ("box-shadow:\n    0 4px 8px\n    var(--c)", "box-shadow: 0 4px\n  8px var(--c)", "backdrop-filter:\n  blur(\n    8px)"):
            with self.subTest(split=split):
                self.assertEqual(self.depth(self.rule(split)), [5])
        self.assertEqual(self.depth(self.rule("box-shadow:\n    0 0 0 1px\n    var(--c)")), [], "a ring on three lines is a ring")
        self.assertEqual(self.depth(self.rule("margin: 0;\n  box-shadow: 0 4px 8px var(--c);\n  filter: blur(2px)")), [6, 7], "each property on its own line")

    def test_each_layer_is_judged_by_itself(self):
        self.assertEqual(self.depth(self.rule("box-shadow: 0 0 0 1px var(--c), var(--shadow-raised)")), [])
        self.assertEqual(self.depth(self.rule("box-shadow: var(--shadow-raised), 0 0 0 1px var(--c), 0 2px 4px var(--c)")), [5])

    def test_the_words_outside_a_declarations_value_are_no_depth(self):
        for text in (
            "<style>.blur { margin: 0 }\n.box-shadow { margin: 0 }\na.filter:hover { margin: 0 }\n.drop-shadow-note { margin: 0 }</style>",
            "<p>A soft blur or a long shadow reads as depth, and a filter or a drop-shadow is one way to draw it.</p>",
            "<style>/* box-shadow: 0 4px 12px var(--c); backdrop-filter: blur(8px) */ .a { margin: 0 }</style>",
            "<style>\n/*\n  filter: blur(4px);\n*/\n.a { margin: 0 }</style>",
            "<!-- text-shadow: 0 1px 0 var(--c) -->",
            "<style>.a { box-shadow: /* 0 4px 8px red */ 0 0 0 1px var(--c) }</style>",
            "<style>.a { --shadow-note: none }</style>",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.depth(self.TOKENS + text), [])

    def test_the_tokens_block_may_hold_any_depth_and_the_rule_resumes_after_it(self):
        for block in (
            '<style id="tokens">\n:root { --a: 0 4px 12px var(--c); --b: blur(8px); }\n.x { box-shadow: 0 4px 12px red; filter: blur(4px) }\n</style>\n',
            '<style id="tokens">.x { backdrop-filter: blur(8px) }</style>\n',
            '<style id="tokens">\n@media (prefers-reduced-transparency: reduce) { :root { --glass: none } }\n:root { --glass: blur(8px) }\n</style >\n',
        ):
            with self.subTest(block=block[:40]):
                self.assertEqual(self.depth(block), [])
                self.assertEqual(self.depth(block + "<style>\n.a { filter: blur(2px) }</style>"), [block.count("\n") + 2])

    def test_the_message_names_the_property_and_the_token_that_holds_the_value(self):
        def said(declaration: str) -> str:
            return next(message for _, message, rule in checks._lint(self.rule(declaration)) if rule == "depth")

        held = said("box-shadow: 0 1px 2px  var(--c)")
        self.assertIn("box-shadow", held)
        self.assertIn("--shadow-raised", held, "the tokens block already holds this value")
        self.assertIn("--filter-glass", said("backdrop-filter: saturate(1.2) blur(8px)"))
        self.assertIn("--shadow-raised", said("box-shadow: 0 0 0 1px var(--c), 0 1px 2px var(--c)"), "the layer that fails is the value the token holds")
        free = said("box-shadow: 0 6px 18px var(--c)")
        self.assertIn("box-shadow", free)
        self.assertNotIn("--shadow-raised", free)
        self.assertIn("tokens block", free, "it says where the value goes")
        fallback = said("box-shadow: var(--x, 0 6px 18px var(--c))")
        self.assertEqual(fallback, free, "a fallback gives the message its layer gives")
        self.assertIn("--shadow-raised", said("box-shadow: var(--x, 0 1px 2px var(--c))"), "and names the token that holds it")
        self.assertNotRegex(said("box-shadow: 0 6px 18px var(--c)\x1b[2J"), r"[\x00-\x1f\x7f-\x9f]")

    def test_a_design_with_depth_outside_its_tokens_fails_the_check_with_its_line(self):
        text = swapped(format_one_design(), "box-shadow: var(--shadow-raised);", "box-shadow: 0 8px 24px var(--color-text);")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "d.html").write_text(text, encoding="utf-8")
            done = tool(Path(tmp), "check", "d.html")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn(f"d.html:{line_of(text, '0 8px 24px')}:", done.stdout)
        self.assertEqual(len(done.stdout.splitlines()), 2, "the one problem, and the count")

    def test_depth_is_a_format_1_family_and_a_newer_format_only_notes(self):
        self.assertEqual(checks.RULE_FORMATS["depth"], 1)
        design = self.rule("box-shadow: 0 8px 24px var(--c)") + screen("a", state("s", "<p>Hi</p>"))
        self.assertEqual(len(checks.check(design, design, 1, "d.html", 1)[0]), 1)
        original = checks.RULE_FORMATS
        checks.RULE_FORMATS = dict(original, depth=2)
        try:
            problems, ok = checks.check(design, design, 1, "d.html", 1)
        finally:
            checks.RULE_FORMATS = original
        self.assertEqual(problems, [], "a rule newer than the design never fails it")
        self.assertIn("note: d.html:5: format 2 would flag this", ok)

    def test_every_design_source_the_tool_ships_passes_the_depth_family(self):
        examples = PROTOTYPE_TOOL / "examples"
        sources = [PROTOTYPE_TOOL / "design.html", examples / "showcase.html", *sorted((examples / "product").rglob("*.html"))]
        with tempfile.TemporaryDirectory() as tmp:
            sources += [path for path in pp.new_product_prototype(Path(tmp)) if path.suffix == ".html"]
            for path in sources:
                with self.subTest(source=path.name):
                    self.assertEqual(self.depth(path.read_text(encoding="utf-8")), [])
        self.assertGreaterEqual(len(sources), 7, "the starting design, the showcase, the product example, and the product starter")


class DeclarationReaderTests(unittest.TestCase):
    """The raw-color rule reads whole declarations: it answers as it did on each one-line declaration, and now answers on the forms
    a line reader missed."""

    PROPERTIES = (
        "color",
        "background",
        "background-image",
        "border",
        "border-top-color",
        "outline",
        "fill",
        "stroke",
        "accent-color",
        "box-shadow",
        "text-shadow",
        "--brand",
        "--space",
        "margin",
        "font-family",
        "content",
        "width",
    )
    VALUES = (
        "#fff",
        "#FFFFFF80",
        "rgb(0 0 0 / 0.1)",
        "oklch(0.5 0.1 20)",
        "red",
        "Tan",
        "tan",
        "currentColor",
        "transparent",
        "var(--c)",
        "var(--red)",
        "none",
        "0",
        "8px",
        "linear-gradient(red, blue)",
        "linear-gradient(var(--a), var(--b))",
        "url(red.png)",
        "'red'",
        "1px solid #123",
        "0 0 0 1px black",
        "Canvas",
        "inherit",
    )
    FRAMES = (
        "<style>.a {{ {d}; }}</style>",
        ".a {{ {d} }}",
        '<p style="{d}">x</p>',
        "<i>{d}</i>",
        "  {d};",
        "margin: 0; {d};",
        "{d}; margin: 0",
        "a:hover {{ {d}; }}",
        "@media (min-width: 40rem) {{ .a {{ {d}; }} }}",
    )

    @staticmethod
    def raw_lines(text: str) -> list[int]:
        return [line for line, _, rule in checks._lint(text) if rule == "raw-color"]

    def test_every_one_line_declaration_gets_the_answer_the_line_reader_gave(self):
        colors = checks._sibling("design_colors")
        for frame in self.FRAMES:
            lines = [frame.format(d=f"{prop}: {value}") for prop in self.PROPERTIES for value in self.VALUES]
            old = [number for number, line in enumerate(lines, 1) if colors.raw_color(line) is not None]
            self.assertGreater(len(old), 40, "the set holds many raw colors")
            self.assertLess(len(old), len(lines) - 40, "and many that are not")
            new = self.raw_lines("\n".join(lines))
            with self.subTest(frame=frame):
                if frame == "<i>{d}</i>":
                    # A tag ends a declaration, so a custom property set to one color name in text is a whole declaration there.
                    self.assertTrue(set(old) <= set(new) and all("--" in lines[number - 1] for number in set(new) - set(old)))
                else:
                    self.assertEqual(new, old)

    def test_a_color_in_mask_and_in_filter_is_raw(self):
        for raw in (
            "mask: linear-gradient(black, transparent)",
            "-webkit-mask-image: linear-gradient(red, transparent)",
            "mask-image: linear-gradient(#000, transparent)",
            "filter: drop-shadow(black)",
            "filter: drop-shadow(0 0 0 black)",
            "backdrop-filter: drop-shadow(rgb(0 0 0))",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.raw_lines(f"<style>.a {{ {raw}; }}</style>\n"), [1])
        for fine in (
            "mask: none",
            "mask: url(a.svg) no-repeat center",
            "mask: linear-gradient(var(--a), transparent)",
            "mask-composite: exclude",
            "filter: none",
            "filter: blur(0)",
            "filter: saturate(1.2) brightness(0.9) hue-rotate(10deg)",
            "filter: drop-shadow(0 0 0 var(--c))",
        ):
            with self.subTest(fine=fine):
                self.assertEqual(self.raw_lines(f"<style>.a {{ {fine}; }}</style>\n"), [])

    def test_a_value_on_two_lines_is_one_value_and_a_comment_is_no_declaration(self):
        for split in ("background:\n    white", "color:\n#fff", "box-shadow: 0 0 0 1px\n  rgb(0 0 0)", "background: linear-gradient(\n  red,\n  blue)"):
            with self.subTest(split=split):
                self.assertEqual(self.raw_lines(f"<style>\n.a {{ {split}; }}\n</style>\n"), [2], "on the line of its property")
        for comment in (
            "/* color: #fff; background: red */",
            "/*\n  border: 1px solid black;\n*/",
            "color: /* #fff */ var(--c)",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(self.raw_lines(f"<style>.a {{ margin: 0 }} {comment}</style>\n"), [])
        self.assertEqual(self.raw_lines("<style>.a { margin: 0 }</style>\n<!-- fill: rgb(1 2 3) -->\n"), [], "an HTML comment, outside the style")
        self.assertEqual(self.raw_lines('<p style="color: /* #fff */ var(--c)">x</p>\n'), [], "a comment in a style attribute")
        self.assertEqual(self.raw_lines("<style>.a { color: red } /* never closed .b { color: red }</style>\n"), [1, 1], "an unclosed comment is text")

    def test_a_slash_star_that_is_no_comment_hides_no_declaration(self):
        """A `/*` is a comment only in a style's text or a style attribute's value, outside a string and a `url()`, and a `<!--`
        only outside both. A real comment after it must not end it: the declarations between stay read, by both rules."""
        body = ".b{box-shadow:0 8px 24px var(--c);color:#fff}"
        rows = {
            "a string": f'<style>\n.a::before{{content:"/*"}}\n{body}\n/* x */\n</style>\n',
            "a single-quoted string": f"<style>\n.a::before{{content:'/*'}}\n{body}\n/* x */\n</style>\n",
            "a url()": f"<style>\n.a{{background:url(a/*b.png)}}\n{body}\n/* x */\n</style>\n",
            "a quoted url()": f'<style>\n.a{{background:url("a/*b.png")}}\n{body}\n/* x */\n</style>\n',
            "a line that opens a quote and never closes it": f"<style>\n.a::before{{content:'it}}\n{body}\n/* x */\n</style>\n",
            "prose outside a style": f"<p>See docs/*.md</p>\n<style>\n{body}\n/* x */\n</style>\n",
            "a script string": f'<script>var a = "/*";</script>\n<style>\n{body}\n/* x */\n</style>\n',
            "an HTML opener in a style": f"<style>\n.a::before{{content:'<!--'}}\n{body}\n</style>\n<p>a --> b</p>\n",
            "an HTML opener that no comment closes": f"<!--\n<style>\n{body}\n</style>\n",
            "a title attribute": f'<p title="/*">x</p>\n<p style="{body[3:-1]}">y</p>\n<i>*/</i>\n',
        }
        for name, text in rows.items():
            with self.subTest(name):
                at = line_of(text, "box-shadow")
                self.assertEqual(self.raw_lines(text), [at], "the raw color")
                self.assertEqual([n for n, _, rule in checks._lint(text) if rule == "depth"], [at], "the raw shadow")
        hidden = "<style>\n/* it's a note */\n/* box-shadow: 0 8px 24px var(--c); color: #fff */\n</style>\n"
        self.assertEqual(checks._lint(hidden), [], "a comment with a quote in it still ends at its own end")

    def test_an_at_rules_condition_is_no_color_either(self):
        for condition in ("@supports (color: color-mix(in srgb, red, blue))", "@supports not (color: red)", "@media (prefers-color-scheme: dark)"):
            with self.subTest(condition=condition):
                self.assertEqual(self.raw_lines(f"<style>\n{condition} {{\n  .g {{ margin: 0 }}\n}}\n</style>\n"), [])
                self.assertEqual(self.raw_lines(f"<style>\n{condition} {{\n  .g {{ color: red }}\n}}\n</style>\n"), [3])

    def test_a_declaration_written_as_text_is_read_as_one_unless_its_colon_is_written_another_way(self):
        """The README names this false alarm and its way out, so a person is never stuck on a sample."""

        def found(text: str) -> list[str]:
            return [rule for _, _, rule in checks._lint(text)]

        for sample, rule in (("box-shadow: 0 4px 8px var(--c)", "depth"), ("color: #fff", "raw-color")):
            with self.subTest(sample=sample):
                self.assertEqual(found(f"<p><code>{sample}</code></p>\n"), [rule])
                self.assertEqual(found(f"<style>.a::after {{ content: '{sample}' }}</style>\n"), [rule])
                self.assertEqual(found(f"<p><code>{sample.replace(':', '&#58;')}</code></p>\n"), [], "a colon written as an entity")
                self.assertEqual(found(f"<style>.a::after {{ content: '{sample.replace(':', chr(92) + '3a ')}' }}</style>\n"), [], "and as a CSS escape")

    def test_a_declaration_that_runs_into_the_next_tag_stops_at_the_tag(self):
        self.assertEqual(self.raw_lines("<i>Note, color: grey\n</i>\n<p>The Red Fox</p>\n"), [1], "the text up to the tag is read")
        self.assertEqual(self.raw_lines("<i>Note, color:\n</i>\n<p>The Red Fox</p>\n"), [], "and no further")


class ScreensTests(unittest.TestCase):
    def test_a_file_lists_its_screens_with_their_states_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(SHOWCASE, encoding="utf-8")
            copy_showcase_images(root)
            done = tool(root, "screens", "prototype.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual((listed["schema_version"], "format" in listed), (str(pp.FORMAT), False))
        self.assertEqual(json_schema.validate(listed, "design-manifest.schema.json"), [])
        by_id = {s["id"]: s for s in listed["screens"]}
        self.assertEqual(list(by_id), ["sign-in", "sitters", "sitter"])
        self.assertEqual(
            by_id["sign-in"], {"id": "sign-in", "title": "Sign in", "parent": None, "initial": "empty", "states": ["empty", "loading", "error", "offline"]}
        )
        self.assertEqual(by_id["sitter"]["parent"], "sitters")
        self.assertEqual(by_id["sitters"]["states"][:3], ["empty", "loading", "partial"])
        self.assertEqual(by_id["sitters"]["initial"], "success")

    def test_a_screen_opens_in_its_first_state_when_it_names_none_or_a_wrong_one(self):
        markup = f'<template id="product">\n{screen("a", state("x", "<p>X</p>") + state("y", "<p>Y</p>"), data_initial="z")}</template>'
        reader = checks.read_design(markup, "d.html")
        self.assertEqual(checks.screens_of(reader)[0]["initial"], "x")

    def test_aidd_prints_the_same_for_a_file_and_for_the_product_prototype(self):
        with adopted_repo() as root:
            (root / "prototype.html").write_text(SHOWCASE, encoding="utf-8")
            copy_showcase_images(root)
            code, out = run_cli("prototype", "--screens", "prototype.html")
            self.assertEqual(code, 0, out)
            self.assertEqual([s["id"] for s in json.loads(out)["screens"]], ["sign-in", "sitters", "sitter"])
            run_cli("new", "product-prototype")
            code, out = run_cli("prototype", "--screens")
            self.assertEqual(code, 0, out)
            self.assertEqual([s["id"] for s in json.loads(out)["screens"]], ["start:start"])
            self.assertEqual(json_schema.validate(json.loads(out), "design-manifest.schema.json"), [])
            code, out = run_cli("prototype", "--screens", "--check")
            self.assertNotEqual(code, 0)
            self.assertIn("give one of them", out)

    def test_a_screen_id_the_check_refuses_is_refused_by_screens_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(swapped(SHOWCASE, 'data-screen="sitter"', 'data-screen="x$(touch PWNED)"'), encoding="utf-8")
            copy_showcase_images(root)
            checked = tool(root, "check", "prototype.html")
            done = tool(root, "screens", "prototype.html")
        self.assertEqual(checked.returncode, 1)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("names a screen 'x$(touch PWNED)'", done.stdout)
        self.assertNotIn("{", done.stdout, "no screens are printed from a design that is not safe to read")

    def test_screens_refuses_a_design_newer_than_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.html").write_text(swapped(SHOWCASE, "data-aidd-prototype=", 'data-aidd-prototype="9" data-x='), encoding="utf-8")
            copy_showcase_images(root)
            done = tool(root, "screens", "a.html")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("update aidd-team", done.stdout)

    def test_a_file_that_is_no_design_gives_the_problem_and_no_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            done = tool(root, "screens", "absent.html")
        self.assertEqual(done.returncode, 1)
        self.assertIn("absent.html is no prototype file in this repository", done.stdout)
        self.assertNotIn("{", done.stdout)


class ShotsTests(unittest.TestCase):
    """The fidelity pass's views, sized to the change (the prototyping skill's design review): a new screen takes its full
    matrix, a changed component takes the screens it appears on first, then its states, and never more than a screen."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        (cls.root / "prototype.html").write_text(SHOWCASE, encoding="utf-8")
        copy_showcase_images(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def shots(self, **change: list[str]) -> tuple[list[dict], list[str]]:
        found, problems = pp.shots_of(self.root, "prototype.html", **change)
        if found is not None:
            self.assertEqual(json_schema.validate(found, "design-manifest.schema.json"), [])
        return (found or {}).get("shots", []), problems

    def test_a_changed_component_takes_fewer_views_than_a_new_screen_and_never_none(self):
        contract, _ = pp.contract_of(self.root, "prototype.html")
        listed, _ = pp.screens_of(self.root, "prototype.html")
        states = {s["id"]: set(s["states"]) for s in listed["screens"]}
        per_screen = {screen: self.shots(screens=[screen])[0] for screen in states}
        least = min(len(found) for found in per_screen.values())
        self.assertLess(least, len(self.shots()[0]), "a whole design takes more than one screen")
        for screen, found in per_screen.items():
            with self.subTest(screen=screen):
                self.assertEqual(
                    {(s["state"], s["frame"], s["theme"]) for s in found if s["purpose"] == "matrix"},
                    {(st, f, t) for st in states[screen] for f in ("320", "ios", "1024") for t in ("light", "dark")},
                )
                self.assertEqual(sorted(s["purpose"] for s in found if s["purpose"] != "matrix"), ["rtl", "text-200"], "one of each on its fullest state")  # fmt: skip
        for component in contract["components"]:
            with self.subTest(component=component["name"]):
                found, problems = self.shots(components=[component["name"]])
                self.assertEqual(problems, [])
                self.assertTrue(0 < len(found) < least, f"{len(found)} views for one component, {least} for the smallest screen")
                self.assertEqual(found[0]["purpose"], "overview", "the view a person sees comes before any close-up")
                at_states = {(s["variant"], s["theme"]) for s in found if s["purpose"] == "states"}
                self.assertEqual(at_states, {(v, t) for v in component["variants"] for t in ("light", "dark")}, "each variant once, in each theme")
                self.assertIn("text-200", {s["purpose"] for s in found}, "200% text, on the changed component only")
                for shot in found:
                    self.assertIn(shot["state"], states[shot["screen"]], "each view opens a state the design has")

    def test_what_the_design_lacks_is_a_problem_and_no_views(self):
        rows = (
            ("a component no screen shows", {"components": ["nope"]}, "no screen shows the component 'nope': name one of app-bar"),
            ("a screen the design lacks", {"screens": ["nope"]}, "the design has no screen 'nope': name one of sign-in"),
            ("a frame the table lacks", {"frames": ["360"]}, "the frame '360' is not in the device table"),
        )
        for name, change, problem in rows:
            with self.subTest(name):
                found, problems = self.shots(**change)
                self.assertEqual(found, [])
                self.assertEqual(len(problems), 1, problems)
                self.assertTrue(problems[0].startswith(problem), problems[0])

    def test_the_frames_a_product_ships_replace_the_full_passs(self):
        found, _ = self.shots(screens=["sitters"], components=["tab"], frames=["desktop", "desktop-1440"])
        self.assertEqual({s["frame"] for s in found}, {"desktop", "desktop-1440"})
        tab = [s for s in found if s.get("component") == "tab" or s["purpose"] in ("overview", "narrow")]
        self.assertEqual({s["frame"] for s in tab}, {"desktop"}, "with no 1024, the overview is the first frame named, and it is the narrowest")
        self.assertEqual(len({s["file"] for s in found}), len(found), "each view once")

    def test_aidd_and_the_tool_alone_print_the_same_views(self):
        done = tool(self.root, "shots", "prototype.html", "--changed-component", "sitter-card")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with adopted_repo() as root:
            (root / "prototype.html").write_text(SHOWCASE, encoding="utf-8")
            copy_showcase_images(root)
            code, out = run_cli("prototype", "--shots", "prototype.html", "--changed-component", "sitter-card")
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out), json.loads(done.stdout))
            code, out = run_cli("prototype", "--changed-component", "sitter-card", "prototype.html")
            self.assertNotEqual(code, 0)
            self.assertIn("add --shots", out)


class HostileDesignTests(unittest.TestCase):
    """A design is data from outside: it must neither stall the check nor write to the terminal as it likes."""

    # CPU time, not wall time: a stalling pattern burns this process's CPU, while other processes' load
    # only stretches the wall clock, where the 1 s bound failed on a busy machine.
    def timed(self, text: str) -> float:
        start = time.process_time()
        lint_problems(text)
        return time.process_time() - start

    def test_a_long_line_takes_time_in_proportion_to_its_length(self):
        for hostile in (
            "color:" * 34000,
            "color" * 40000,
            "a:" * 100000,
            "background-color:" * 12000,
            "color: x" + " " * 200000,
            "{color:" * 30000,
            "/*" * 100000,
            "<!--" * 60000,
            "<style " * 30000,
            '<style id="tokens">' + "</style " * 25000,
            "<style>" + "</style " * 25000,
            ("<style>" + "</style x") * 15000,
            '<style>"/*' * 20000,
            "<style>url( /*" * 15000,
            "style='/*" * 20000,
            "/* " * 60000 + "*/",
            "box-shadow:" * 20000,
            "filter: " + "blur(" * 50000,
            "box-shadow: " + "var(" * 50000,
            "box-shadow: " + "0 " * 100000,
            "box-shadow: " + "a," * 100000,
            "box-shadow: " + "var(--a," * 30000 + ")" * 30000,
            '<style id="tokens">' * 20000,
            "color:\n" * 100000,
        ):
            with self.subTest(shape=hostile[:20]):
                self.assertLess(self.timed(hostile), 1.0, "a 200 KB line")
        self.assertLess(self.timed(("<p style='color:" * 12000) + "'>"), 1.0)

    def test_a_design_with_thirty_thousand_findings_takes_time_in_proportion_to_its_size(self):
        """Each finding's message once read the whole file for the tokens, so findings times size was 7.7 s for 1 MB. Linear is
        under a second; the bound is 2.5 s, for a slow machine."""
        tokens = '<style id="tokens">:root { --shadow-raised: 0 4px 8px var(--c); }</style>\n'
        for name, rule in (("depth", ".a{box-shadow:0 4px 8px var(--c)}"), ("raw-color", ".a{color:#fff}")):
            with self.subTest(rule=name):
                text = tokens + "<style>" + rule * 30000 + "</style>"
                self.assertGreater(len(text), 400_000)
                start = time.process_time()
                found = checks._lint(text)
                self.assertLess(time.process_time() - start, 2.5)
                self.assertEqual(len(found), 30000)

    def test_the_raw_color_rule_still_catches_every_shape_it_caught(self):
        for raw in (
            "color:#fff",
            "color: #FFFFFF80",
            "background-image: linear-gradient(red, #123)",
            "accent-color: #123abc",
            "text-shadow: 0 0 0 rgb(0 0 0)",
            "border-top-color: hsla(1 2% 3% / 0.5)",
            "fill:oklch(0.5 0.1 20)",
            "stroke: color(srgb 1 0 0)",
            "outline: 1px solid lab(50 0 0)",
            ".button-primary { border: 0; background: var(--color-accent); color: var(--color-on-accent); box-shadow: 0 0 0 1px rgb(0 0 0 / 0.12); }",
            ".btn{border-radius: 4px; color: #fff}",
            "color: var(--c); background: #fff",
        ):
            with self.subTest(raw=raw):
                self.assertEqual([n for n, _ in lint_problems(f'<p style="{raw}">x</p>\n<i>{raw}</i>')], [1, 2])
        for fine in ("color: var(--color-accent)", "padding: 4px; margin: 0", "content: '#fff'", "width: 3px;color: var(--c)", "--space-2: 8px"):
            with self.subTest(fine=fine):
                self.assertEqual(lint_problems(f'<p style="{fine}">x</p>'), [])
        self.assertEqual([n for n, _ in lint_problems('<p style="margin: 0; color:#fff">x</p>')], [1], "a later declaration on the line")
        self.assertEqual(lint_problems('<p style="color: var(--c)">#fff</p>'), [], "a color outside the declaration is text")

    def test_a_deep_design_is_refused_with_a_plain_message_and_read_in_linear_time(self):
        for hostile in ("<div>x" * 20000, "<div><span><button>" * 8000, "<div>" * 5000 + "</p>" * 20000):
            with self.subTest(shape=hostile[:20]):
                start = time.process_time()
                found = checks.check(hostile, hostile, 1, "d.html")[0]
                self.assertLess(time.process_time() - start, 1.0)
                self.assertEqual(len(found), 1)
                self.assertIn("nests elements more than 400 levels deep", found[0])
        shallow = "<div>" * 300 + "x" + "</div>" * 300
        self.assertFalse(checks.read_design(shallow, "d.html").too_deep, "a design under the limit is read")

    def test_a_wide_design_with_many_bad_links_prints_a_bounded_list(self):
        markup = "".join(screen(f"s{n}", state("ok", button(f"b{n}", data_go=f"nowhere{n}"))) for n in range(1200))
        start = time.process_time()
        found = checks.check(markup, markup, 1, "d.html")[0]
        self.assertLess(time.process_time() - start, 1.0)
        self.assertEqual(len(found), 201, "200 problems, then how many more")
        self.assertIn("and ", found[-1])
        self.assertRegex(found[-1], r"and \d{3,} more problems")
        self.assertLess(sum(map(len, found)), 100_000, "bounded output")
        self.assertTrue(all(len(line) < 1500 for line in found))
        self.assertIn("and 1190 more", found[0], "a message lists ten options, then the rest as a count")

    def test_a_message_lists_ten_options_and_skips_the_close_match_search_past_a_few_hundred(self):
        few = [f"opt{n}" for n in range(5)]
        self.assertEqual(checks._choose("opt4x", few, "screen"), "did you mean `opt4`? Name one of opt0, opt1, opt2, opt3, opt4")
        many = [f"screen-{n}" for n in range(12)]
        self.assertTrue(checks._choose("zzz", many, "screen").endswith("screen-9, and 2 more"))
        start = time.process_time()
        huge = checks._choose("screen-1", [f"screen-{n}" for n in range(5000)], "screen")
        self.assertLess(time.process_time() - start, 0.2)
        self.assertNotIn("did you mean", huge, "past a few hundred options the suggestion is skipped")

    def test_a_quoted_value_has_no_control_character_and_is_cut_short(self):
        self.assertEqual(checks.quoted("a\x1b[2Jb\x07c\x85d\x7fe f"), "a[2Jbcde f")
        self.assertEqual(checks.quoted("a\u200eb\u200fc\u061cd"), "abcd", "bidirectional marks reorder a terminal line")
        self.assertEqual(checks.quoted("x" * 200), "x" * 79 + "…")
        self.assertEqual(checks.quoted("plain text"), "plain text")

    def test_no_message_prints_a_control_character_from_the_design(self):
        evil = "go\x1b[2J\x07ok: 99 screens"
        markup = screen("a", state("s", button("a1", data_go=evil, data_item_go=evil)), data_parent=evil, data_initial=evil)
        markup += screen(evil.replace("go", "gp"), state(evil, button(evil)))
        found = checks.check(markup, markup, 1, "d.html")[0]
        self.assertTrue(found)
        for line in found:
            self.assertNotRegex(line, r"[\x00-\x08\x0a-\x1f\x7f-\x9f]", line)
        self.assertTrue(any("[2J" in line for line in found), "the printable part of the value stays")
        self.assertFalse(any(len(line) > 400 for line in found))
        long = checks.check(markup.replace(evil, "q" * 500), markup.replace(evil, "q" * 500), 1, "d.html")[0]
        self.assertTrue(all(len(line) < 400 for line in long))
        address = lint_problems('<img src="https://x.test/\x1b[2J\x07a.png">')
        self.assertTrue(address)
        self.assertNotRegex(address[0][1], r"[\x00-\x1f\x7f-\x9f]")
        declaration = lint_problems('<p style="color:#fff\x1b[2J">x</p>')
        self.assertNotRegex(declaration[0][1], r"[\x00-\x1f\x7f-\x9f]")

    def test_the_tool_prints_none_of_them_either(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(
                swapped(SHOWCASE, 'data-go="sitters/success" data-testid="signin-submit"', 'data-go="x\x1b[2J\x07y" data-testid="signin-submit"'),
                encoding="utf-8",
            )
            copy_showcase_images(root)
            done = tool(root, "check", "prototype.html")
        self.assertEqual(done.returncode, 1)
        self.assertIn("names no screen", done.stdout)
        self.assertNotRegex(done.stdout.replace("\n", ""), r"[\x00-\x1f\x7f-\x9f]")


class MissingPartTests(unittest.TestCase):
    def test_the_tool_alone_without_its_checks_says_to_reinstall_and_exits_2(self):
        for args in (["--help"], ["check", "a.html"]):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp:
                lone = Path(tmp) / "prototype.py"
                lone.write_text((PROTOTYPE_TOOL / "prototype.py").read_text(encoding="utf-8"), encoding="utf-8")
                done = subprocess.run([sys.executable, "-I", str(lone), *args], cwd=tmp, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertIn("design_checks.py is missing beside prototype.py: reinstall aidd-team", done.stderr)
                self.assertNotIn("Traceback", done.stderr)


class PrintedLinesTests(unittest.TestCase):
    def test_build_and_example_print_the_page_path_and_its_file_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(sound_showcase(), encoding="utf-8")
            copy_showcase_images(root)
            for args, page in ((("build", "prototype.html"), "prototype-prototype.html"), (("example",), "prototype-example.html")):
                with self.subTest(args=args):
                    out = tool(root, *args).stdout.splitlines()
                    self.assertEqual(out[0], f"wrote .aidd/views/{page}: open it in a browser")
                    self.assertEqual(out[1], (root / ".aidd" / "views" / page).resolve().as_uri())

    def test_aidd_prints_them_too_and_new_design_names_the_next_command(self):
        with adopted_repo() as root:
            (root / "prototype.html").write_text(sound_showcase(), encoding="utf-8")
            copy_showcase_images(root)
            code, out = run_cli("prototype", "prototype.html")
            self.assertEqual(code, 0, out)
            self.assertIn((root / ".aidd" / "views" / "prototype-prototype.html").resolve().as_uri(), out)
            code, out = run_cli("prototype", "--example")
            self.assertIn("file://", out)
            code, out = run_cli("prototype", "--new-design", "a.html")
            self.assertIn("then `aidd prototype a.html` to see it", out)
        with tempfile.TemporaryDirectory() as tmp:
            made = tool(Path(tmp), "new-design", "a.html")
            self.assertEqual(made.stdout.splitlines()[0], "a.html")


if __name__ == "__main__":
    unittest.main()


class RuleFormatTests(unittest.TestCase):
    """Spec approval freezes a design and the command that checks it, so an aidd upgrade never turns an approved design
    red: each rule family names the design format it arrived in, and a design is held to its own format's families."""

    DESIGN = (
        '<html data-aidd-prototype="1"><template id="product"><main>'
        '<section data-screen="home" data-title="Home"><div data-state="success"><p>Hi \U0001f680</p></div></section>'
        "</main></template></html>"
    )

    def test_every_family_is_at_or_below_the_tools_format(self):
        self.assertTrue(checks.RULE_FORMATS)
        for rule, version in checks.RULE_FORMATS.items():
            self.assertTrue(1 <= version <= pp.FORMAT, rule)

    def test_a_family_newer_than_the_design_only_notes(self):
        product = self.DESIGN.split('<template id="product">', 1)[1].rsplit("</template>", 1)[0]
        problems, _ = checks.check(self.DESIGN, product, 1, "d.html", 1)
        self.assertTrue(any("emoji" in p for p in problems), "today the emoji rule is format 1, so it fails a format-1 design")
        newer = dict(checks.RULE_FORMATS, emoji=2)
        original = checks.RULE_FORMATS
        checks.RULE_FORMATS = newer
        try:
            problems, ok = checks.check(self.DESIGN, product, 1, "d.html", 1)
        finally:
            checks.RULE_FORMATS = original
        self.assertFalse(any("emoji" in p for p in problems), "a rule newer than the design never fails it")
        self.assertIn("note: d.html:1: format 2 would flag this, and the design is format 1", ok)


# A design that uses every form format 1 allows, written once. It is frozen: the rules of format 1 are fixed at 1.0.0, so a
# later aidd must still pass it. Never edit it to make a test pass.
FORMAT_ONE_DESIGN = """<!doctype html>
<html lang="en" data-aidd-prototype="1">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Format 1: every form it allows</title>
</head>
<body>
<template id="product">
<style id="tokens">
:root { --color-surface: #ffffff; --color-text: #1a1a1a; --color-accent: #1d4ed8; --shadow-raised: 0 1px 2px rgb(0 0 0 / 0.12); --filter-glass: saturate(1.6) blur(18px); }
@media (prefers-reduced-transparency: reduce) { :root { --filter-glass: none; } }
</style>
<style>
.card { padding: 8px; background: var(--color-surface); color: var(--color-text); border: 1px solid transparent; outline: none; box-shadow: var(--shadow-raised); }
.card { font-family: system-ui, Tan, serif; border-color: currentColor; accent-color: var(--color-accent); }
.forced { background: Canvas; color: CanvasText; }
.ring { box-shadow: 0 0 0 1px var(--color-accent), inset 0 0 0 calc(2 * var(--space-1, 4px)) var(--color-surface); text-shadow: none; outline: 0 solid var(--color-accent); }
.glass { backdrop-filter: var(--filter-glass); filter: blur(0); background: linear-gradient(90deg, var(--color-surface) 40%, var(--color-accent) 60%) 0 0 / 300% 100%; }
.red { margin: 0; }
.logo { background: var(--color-surface) url(images/logo.png) no-repeat; }
</style>
<div class="device">
  <nav class="tabs" aria-label="Main">
    <button type="button" data-go="home" data-testid="tab-home"><span>Home</span></button>
  </nav>
  <main id="main" tabindex="-1">
    <section data-screen="home" data-title="Home" data-initial="success" aria-labelledby="home-title">
      <div data-state="success" data-testid="home-success">
        <h2 id="home-title">Orange</h2>
        <p class="red">Track TODO-104 before the next round.</p>
        <img src="images/logo.png" srcset="images/logo.png 1x, images/logo@2x.png 2x" alt="The product's logo">
        <svg class="card" viewBox="0 0 8 8" aria-hidden="true" focusable="false"><path d="M0 0h8v8z" fill="currentColor" stroke="none"/><circle cx="4" cy="4" r="2" fill="var(--color-accent)" stroke="Canvas"/></svg>
        <label for="email">Email</label>
        <input id="email" type="email" data-testid="home-email">
        <label>Name <input type="text" data-testid="home-name"></label>
        <input type="search" aria-labelledby="home-title" data-testid="home-search">
        <button type="button" class="forced" data-go="home/success" data-testid="home-again">Again</button>
@@FRAMES@@
      </div>
    </section>
  </main>
</div>
</template>
<script type="application/json" id="fixtures">
{ "product": "Format 1" }
</script>
</body>
</html>
"""


def format_one_design() -> str:
    """The frozen design, with each frame of the device table drawn at its size and linked by its id, since the table is data."""
    frames = []
    for key, frame in checks.device_frames().items():
        style = f"width: {frame['width']}px; height: {frame['height']}px; overflow-y: auto"
        frames.append(
            f'        <div data-device="{key}" style="{style}"><a href="#home/success?frame={key}" data-testid="home-frame-{key}">{frame["name"]}</a></div>'
        )
    frames.append('        <a href="#home/success?frame=fill" data-testid="home-frame-fill">Fill the window</a>')
    return FORMAT_ONE_DESIGN.replace("@@FRAMES@@", "\n".join(frames))


class FrozenFormatTests(unittest.TestCase):
    """The rules of format 1 are fixed at 1.0.0, so a later aidd never fails a design that names it."""

    def test_a_design_with_every_form_format_1_allows_passes_check_with_no_note(self):
        # A rule that tightens format 1 in place fails here. Give the rule a new format in `RULE_FORMATS` instead, so a
        # format-1 design gets a note and keeps passing; never change the design above.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "d.html").write_text(format_one_design(), encoding="utf-8")
            done = tool(Path(tmp), "check", "d.html")
        self.assertEqual((done.returncode, done.stderr), (0, ""), done.stdout)
        self.assertRegex(done.stdout, OK)


class TokenColorHintTests(unittest.TestCase):
    """Raw colors that match a unique token in `<style id="tokens">` suggest its `var(--...)` name."""

    def _design(self, extra_css: str = "", extra_html: str = "", tokens: str = "") -> str:
        tok = tokens or ":root { --color-danger: #b91c1c; --color-accent: #1d4ed8; --color-short: #abc; }"
        return (
            '<html data-aidd-prototype="1"><template id="product">\n'
            f'<style id="tokens">{tok}</style>\n'
            f"<style>{extra_css}</style>\n"
            f'<main><section data-screen="home" data-title="Home"><div data-state="success">{extra_html}</div></section></main>\n'
            "</template></html>"
        )

    def test_raw_css_and_svg_colors_suggest_matching_tokens(self):
        design = self._design(
            extra_css=".err { color: #B91C1C; }\n.muted { background: #aabbcc; }\n.miss { border-color: #123456; }",
            extra_html='<svg viewBox="0 0 8 8" aria-hidden="true"><circle fill="#1d4ed8" cx="4" cy="4" r="2"/></svg>',
        )
        product = design.split('<template id="product">', 1)[1].rsplit("</template>", 1)[0]
        problems, _ = checks.check(design, product, 1, "d.html")
        joined = "\n".join(problems)
        self.assertIn("such as var(--color-danger)", joined)
        self.assertIn("such as var(--color-short)", joined)
        self.assertIn("such as var(--color-accent)", joined)
        miss_lines = [p for p in problems if "#123456" in p]
        self.assertEqual(len(miss_lines), 1)
        self.assertIn("var(--color-accent)", miss_lines[0])

    def test_unmatched_color_uses_generic_example_when_tokens_lack_hex(self):
        design = self._design(
            tokens=":root { --color-surface: #fafafa; }",
            extra_css=".a { color: #1d4ed8; }",
        )
        product = design.split('<template id="product">', 1)[1].rsplit("</template>", 1)[0]
        problems, _ = checks.check(design, product, 1, "d.html")
        self.assertEqual(len(problems), 1)
        self.assertIn("var(--color-accent)", problems[0])
        self.assertNotIn("var(--color-surface)", problems[0])
