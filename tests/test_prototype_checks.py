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

from helpers import PROTOTYPE_TOOL, adopted_repo, run_cli

from aidd.kernel import resources

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


class LintRuleTests(unittest.TestCase):
    """The prototype lint rules of the screenshot reference, over the whole file."""

    def lint(self, text: str) -> list[tuple[int, str]]:
        return checks.lint_problems(text)

    def test_the_tokens_block_may_hold_colors_and_nothing_else_may(self):
        tokens = '<style id="tokens">\n:root { --color-accent: #1d4ed8; }\n</style>\n'
        self.assertEqual(self.lint(tokens + "<style>.a { color: var(--color-accent); }</style>\n"), [])
        for raw in ("color: #fff", "background: rgb(0 0 0 / 0.1)", "box-shadow: 0 1px oklch(0.5 0.1 200)", "border-color: hsl(10 20% 30%)"):
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


class ScreensTests(unittest.TestCase):
    def test_a_file_lists_its_screens_with_their_states_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(SHOWCASE, encoding="utf-8")
            done = tool(root, "screens", "prototype.html")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual(listed["format"], pp.FORMAT)
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
            code, out = run_cli("prototype", "--screens", "prototype.html")
            self.assertEqual(code, 0, out)
            self.assertEqual([s["id"] for s in json.loads(out)["screens"]], ["sign-in", "sitters", "sitter"])
            run_cli("new", "product-prototype")
            code, out = run_cli("prototype", "--screens")
            self.assertEqual(code, 0, out)
            self.assertEqual([s["id"] for s in json.loads(out)["screens"]], ["start:start"])
            code, out = run_cli("prototype", "--screens", "--check")
            self.assertNotEqual(code, 0)
            self.assertIn("give one of them", out)

    def test_a_screen_id_the_check_refuses_is_refused_by_screens_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(swapped(SHOWCASE, 'data-screen="sitter"', 'data-screen="x$(touch PWNED)"'), encoding="utf-8")
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


class HostileDesignTests(unittest.TestCase):
    """A design is data from outside: it must neither stall the check nor write to the terminal as it likes."""

    def timed(self, text: str) -> float:
        start = time.monotonic()
        checks.lint_problems(text)
        return time.monotonic() - start

    def test_a_long_line_takes_time_in_proportion_to_its_length(self):
        for hostile in ("color:" * 34000, "color" * 40000, "a:" * 100000, "background-color:" * 12000, "color: x" + " " * 200000, "{color:" * 30000):
            with self.subTest(shape=hostile[:20]):
                self.assertLess(self.timed(hostile), 1.0, "a 200 KB line")
        self.assertLess(self.timed(("<p style='color:" * 12000) + "'>"), 1.0)

    def test_the_raw_color_rule_still_catches_every_shape_it_caught(self):
        for raw in (
            "color:#fff",
            "color: #FFFFFF80",
            "background-image: linear-gradient(red, #123)",
            "accent-color: #123abc",
            "text-shadow: 0 0 1px rgb(0 0 0)",
            "border-top-color: hsla(1 2% 3% / 0.5)",
            "fill:oklch(0.5 0.1 20)",
            "stroke: color(srgb 1 0 0)",
            "outline: 1px solid lab(50 0 0)",
            ".button-primary { border: 0; background: var(--color-accent); color: var(--color-on-accent); box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }",
            ".btn{border-radius: 4px; color: #fff}",
            "color: var(--c); background: #fff",
        ):
            with self.subTest(raw=raw):
                self.assertEqual([n for n, _ in checks.lint_problems(f'<p style="{raw}">x</p>\n<i>{raw}</i>')], [1, 2])
        for fine in ("color: var(--color-accent)", "padding: 4px; margin: 0", "content: '#fff'", "width: 3px;color: red", "--space-2: 8px"):
            with self.subTest(fine=fine):
                self.assertEqual(checks.lint_problems(f'<p style="{fine}">x</p>'), [])
        self.assertEqual([n for n, _ in checks.lint_problems('<p style="margin: 0; color:#fff">x</p>')], [1], "a later declaration on the line")
        self.assertEqual(checks.lint_problems('<p style="color: red">#fff</p>'), [], "a color outside the declaration is text")

    def test_a_deep_design_is_refused_with_a_plain_message_and_read_in_linear_time(self):
        for hostile in ("<div>x" * 20000, "<div><span><button>" * 8000, "<div>" * 5000 + "</p>" * 20000):
            with self.subTest(shape=hostile[:20]):
                start = time.monotonic()
                found = checks.check(hostile, hostile, 1, "d.html")[0]
                self.assertLess(time.monotonic() - start, 1.0)
                self.assertEqual(len(found), 1)
                self.assertIn("nests elements more than 400 levels deep", found[0])
        shallow = "<div>" * 300 + "x" + "</div>" * 300
        self.assertFalse(checks.read_design(shallow, "d.html").too_deep, "a design under the limit is read")

    def test_a_wide_design_with_many_bad_links_prints_a_bounded_list(self):
        markup = "".join(screen(f"s{n}", state("ok", button(f"b{n}", data_go=f"nowhere{n}"))) for n in range(1200))
        start = time.monotonic()
        found = checks.check(markup, markup, 1, "d.html")[0]
        self.assertLess(time.monotonic() - start, 1.0)
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
        start = time.monotonic()
        huge = checks._choose("screen-1", [f"screen-{n}" for n in range(5000)], "screen")
        self.assertLess(time.monotonic() - start, 0.2)
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
        address = checks.lint_problems('<img src="https://x.test/\x1b[2J\x07a.png">')
        self.assertTrue(address)
        self.assertNotRegex(address[0][1], r"[\x00-\x1f\x7f-\x9f]")
        declaration = checks.lint_problems('<p style="color:#fff\x1b[2J">x</p>')
        self.assertNotRegex(declaration[0][1], r"[\x00-\x1f\x7f-\x9f]")

    def test_the_tool_prints_none_of_them_either(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text(
                swapped(SHOWCASE, 'data-go="sitters/success" data-testid="signin-submit"', 'data-go="x\x1b[2J\x07y" data-testid="signin-submit"'),
                encoding="utf-8",
            )
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
            for args, page in ((("build", "prototype.html"), "prototype-prototype.html"), (("example",), "prototype-example.html")):
                with self.subTest(args=args):
                    out = tool(root, *args).stdout.splitlines()
                    self.assertEqual(out[0], f"wrote .aidd/views/{page}: open it in a browser")
                    self.assertEqual(out[1], (root / ".aidd" / "views" / page).resolve().as_uri())

    def test_aidd_prints_them_too_and_new_design_names_the_next_command(self):
        with adopted_repo() as root:
            (root / "prototype.html").write_text(sound_showcase(), encoding="utf-8")
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
