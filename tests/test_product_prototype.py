"""The product designer's living work: the whole-product prototype (L1), the same-change check that keeps each role's
product-level work in line with the changes that shape it (L0), and the roles `aidd context` hands it to (L2)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import adopted_repo, git, run_cli

from aidd.kernel import resources
from aidd.knowledge import team_registry
from aidd.workitems import living_work

APP = Path("docs") / "design" / "app"

pp = resources.team_tool("prototype")  # aidd-team's prototype tool, as `aidd prototype` runs it


def write_flow(root: Path, flow: str, body: str) -> None:
    (root / APP / "flows" / f"{flow}.html").write_text(body, encoding="utf-8")


def screen(sid: str, title: str, inside: str = "", parent: str = "") -> str:
    parent_attr = f' data-parent="{parent}"' if parent else ""
    return f'<section data-screen="{sid}" data-title="{title}"{parent_attr}><div data-state="success">{inside}</div></section>\n'


class ProductPrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        pp.new_product_prototype(self.root, product="Field Notes")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def sitemap(self, **changes) -> None:
        path = self.root / APP / "sitemap.json"
        data = json.loads(path.read_text(encoding="utf-8")) | changes
        path.write_text(json.dumps(data), encoding="utf-8")

    def two_flows(self) -> None:
        self.sitemap(
            flows=[{"id": "start", "title": "Start"}, {"id": "notes", "title": "Notes"}],
            navigation=[{"label": "Start", "go": "start:start"}, {"label": "Notes", "go": "notes:list"}],
        )
        write_flow(
            self.root,
            "notes",
            screen("list", "All notes", '<button data-go="detail" data-testid="notes-open">Open</button>')
            + screen("detail", "A note", '<button data-go="start:start" data-testid="notes-home">Home</button>', "list"),
        )

    def test_a_new_product_prototype_is_consistent_and_never_overwritten(self):
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(problems, [])
        text = out.read_text(encoding="utf-8")
        self.assertEqual(out, self.root / pp.VIEW)  # beside the decision page, never in the repository's tracked files
        self.assertNotIn("{{", text)
        for spec_words in ("frozen at spec approval", "aidd-spec", "the three here"):  # living work, not a Spec's prototype
            self.assertNotIn(spec_words, text.lower())
        self.assertIn("<title>Field Notes: product prototype</title>", text)
        self.assertIn("The product prototype: every flow, kept current by each change", text)
        self.assertIn("Content-Security-Policy", text)  # loads nothing, as a flow prototype
        with self.assertRaises(FileExistsError):
            pp.new_product_prototype(self.root, product="Again")

    def test_a_name_that_could_break_out_of_the_shell_or_the_header_is_refused_or_kept_as_text(self):
        # `new-product --name` reaches the shell's opening comment and the sitemap, so the name is held to the header's own rule first.
        for label, name in (("a long name", "n" * 61), ("a line break", "Field\nNotes"), ("a carriage return", "Field\rNotes")):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError, "one short line"):
                    pp.new_product_prototype(Path(tmp), product=name)
                self.assertEqual(list(Path(tmp).iterdir()), [], "nothing is written for a name the viewer would refuse")
        plain = (self.root / APP / "shell.html").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            pp.new_product_prototype(Path(tmp), product="x --> <script>alert(1)</script>")
            shell = (Path(tmp) / APP / "shell.html").read_text(encoding="utf-8")
            self.assertEqual(shell.count("-->"), plain.count("-->"), "the opening comment ends where the tool ends it")
            self.assertEqual(shell.count("<script"), plain.count("<script"), "the name adds no element")
            self.assertEqual(json.loads((Path(tmp) / APP / "sitemap.json").read_text(encoding="utf-8"))["product"], "x --> <script>alert(1)</script>")

    def test_the_product_is_named_once_in_the_sitemap(self):
        self.sitemap(product="Field Journal", fixtures={"product": "An old name"})
        text = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        self.assertIn("<title>Field Journal: product prototype</title>", text)
        self.assertIn('"product": "Field Journal"', text)
        self.assertNotIn("An old name", text)

    def test_the_navigation_is_drawn_once_from_the_sitemap_and_links_cross_flows(self):
        self.two_flows()
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(problems, [])
        text = out.read_text(encoding="utf-8")
        self.assertIn('data-go="notes:list" data-component="tab" data-testid="app-nav-notes"', text)
        self.assertIn('data-screen="notes:detail"', text)
        self.assertIn('data-go="notes:detail"', text)  # a link inside the flow, qualified by it
        self.assertIn('data-go="start:start"', text)  # a link to another flow, as written
        self.assertIn('data-parent="notes:list"', text)
        self.assertEqual(text.count('<nav class="tabs"'), 1)  # one navigation, the shell's
        config = json.loads(text.split('<script type="application/json" id="viewer-config">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(config["flows"], [{"id": "start", "title": "Start"}, {"id": "notes", "title": "Notes"}])  # the navigator's groups

    def test_the_check_names_each_way_the_product_falls_apart(self):
        self.two_flows()
        self.sitemap(
            flows=[{"id": "start", "title": "Start"}, {"id": "notes", "title": "Notes"}, {"id": "lonely", "title": "Lonely"}, {"id": "gone", "title": "Gone"}],
            navigation=[{"label": "Start", "go": "start:start"}, {"label": "Notes", "go": "notes:list"}, {"label": "Broken", "go": "notes:nowhere"}],
        )
        write_flow(self.root, "lonely", screen("a", "A", '<button data-go="missing">x</button>') + '<nav class="tabs"></nav><script>1</script>\n')
        write_flow(self.root, "notes", screen("list", "All notes") + '<section data-screen="bare" data-title="Bare"><p>no state</p></section>\n')
        _, problems = pp.build_product_prototype(self.root, write=False)
        text = "\n".join(problems)
        for expected in (
            "flows/lonely.html holds a <nav>",
            "flows/lonely.html holds a <script>",
            "flow `gone` has no file",
            "screen `notes:bare` has no state",
            "flows/lonely.html links to `missing`",
            "navigation item `Broken` opens `notes:nowhere`",
            "flow `lonely` is reached only from the sitemap",
        ):
            self.assertIn(expected, text)
        self.assertFalse((self.root / pp.VIEW).exists())  # --check writes nothing

    def test_a_lost_marker_or_an_unreadable_sitemap_fails_closed(self):
        shell = self.root / APP / "shell.html"
        shell.write_text(shell.read_text(encoding="utf-8").replace(pp.MARKERS["screens"], ""), encoding="utf-8")
        _, problems = pp.build_product_prototype(self.root, write=False)
        self.assertTrue(any("lost its marker" in p for p in problems), problems)
        (self.root / APP / "sitemap.json").write_text("{not json", encoding="utf-8")
        out, problems = pp.build_product_prototype(self.root)
        self.assertIsNone(out)
        self.assertTrue(problems)

    def test_a_sitemap_names_its_version_as_schema_version_and_one_from_before_1_0_0_as_format(self):
        cases = (
            # (what the sitemap names, the keys it holds, a piece of the problem, or None when it loads)
            ("a new marker", {"schema_version": "1"}, None),
            ("the old marker", {"format": 1}, None),
            ("no marker, which is version 1", {}, None),
            ("a newer new marker", {"schema_version": "2"}, "newer than this tool's"),
            ("a newer old marker", {"format": 2}, "newer than this tool's"),
            ("the new marker wins over an older old one", {"schema_version": "1", "format": 2}, None),
            ("the new marker wins over a newer old one's reading", {"schema_version": "2", "format": 1}, "newer than this tool's"),
            ("a marker that is no number", {"schema_version": "one"}, "no number"),
        )
        path = self.root / APP / "sitemap.json"
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["schema_version"], "1", "the template names its version as every versioned file does")
        self.assertNotIn("format", written)
        for what, marker, problem in cases:
            with self.subTest(what):
                path.write_text(json.dumps({k: v for k, v in written.items() if k != "schema_version"} | marker), encoding="utf-8")
                problems = pp.load(self.root)[3]
                if problem is None:
                    self.assertEqual(problems, [])
                else:
                    self.assertEqual(len(problems), 1, problems)
                    self.assertIn(problem, problems[0])

    def test_text_from_the_sources_is_escaped(self):
        self.sitemap(product="A <b>bold</b> name", navigation=[{"label": "<img src=x>", "go": "start:start"}])
        text = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        self.assertNotIn("<img src=x>", text)
        self.assertNotIn("<b>bold</b>", text.split("<body", 1)[1].split('<script type="application/json"', 1)[0])


class FlowMarkupTests(unittest.TestCase):
    """A flow is agent-written markup, assembled into a page a person opens: it may not run code, change the page's
    policy, or capture another part of the page."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        pp.new_product_prototype(self.root, product="Field Notes")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def problems(self, flow: str) -> str:
        write_flow(self.root, "start", screen("start", "Start", flow))
        return "\n".join(pp.build_product_prototype(self.root, write=False)[1])

    def test_a_flow_runs_no_code_and_embeds_nothing(self):
        for markup, expected in (
            ('<img src="x" onerror="alert(1)">', "an event handler (onerror)"),
            ('<button onclick="go()">x</button>', "an event handler (onclick)"),
            ('<a href="javascript:alert(1)">x</a>', "a javascript: link"),
            ('<iframe src="x"></iframe>', "a <iframe>"),
            ('<meta http-equiv="refresh" content="0;url=x">', "a <meta>"),
            ('<base href="x">', "a <base>"),
            ('<form action="x"></form>', "a <form>"),
            ("<!-- aidd:fixtures -->", "an aidd marker"),
        ):
            with self.subTest(markup=markup):
                self.assertIn(expected, self.problems(markup))

    def test_markup_a_browser_runs_but_a_parser_reads_as_text_is_caught_and_writes_nothing(self):
        old = pp.build_product_prototype(self.root)[0]
        self.assertTrue(old.exists())
        for markup in ('<svg><style><img src="x" onerror="alert(1)"></style></svg>', '<p title="x" data-a="<b onclick=alert(1)>">x</p>'):
            with self.subTest(markup=markup):
                write_flow(self.root, "start", screen("start", "Start", markup))
                out, problems = pp.build_product_prototype(self.root)
                self.assertIsNone(out)
                self.assertTrue(any("holds a" in p for p in problems), problems)
                self.assertFalse(old.exists())

    def test_only_the_shells_own_scripts_can_run(self):
        page = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        policies = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)
        self.assertEqual(len(policies), 1)  # the shell and the flows sit in a <template>, so they add none
        policy = policies[0]
        self.assertNotIn("'unsafe-inline'", policy.split("script-src", 1)[1].split(";", 1)[0])
        runtime = page.split("<script>", 1)[1].split("</script>", 1)[0]
        digest = base64.b64encode(hashlib.sha256(runtime.encode("utf-8")).digest()).decode("ascii")
        self.assertIn(f"'sha256-{digest}'", policy)

    def test_the_policy_names_each_style_block_by_hash_and_keeps_inline_only_for_style_attributes(self):
        page = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        policy = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page).group(1)  # type: ignore[union-attr]
        directives = dict(d.strip().split(" ", 1) for d in policy.split(";") if d.strip())
        blocks = re.findall(r"<style\b[^>]*>(.*?)</style(?:[\s/][^>]*)?>", page, re.S)
        hashes = {f"'sha256-{base64.b64encode(hashlib.sha256(b.encode('utf-8')).digest()).decode('ascii')}'" for b in blocks}
        self.assertEqual(set(directives["style-src-elem"].split()), hashes, "every style block, the design's too, and nothing else")
        self.assertEqual(directives["style-src-attr"], "'unsafe-inline'", "a design's style attributes, which no hash can name")
        self.assertEqual(directives["style-src"], "'unsafe-inline'", "only for a browser that knows neither of the two")

    def test_the_tool_refuses_a_system_css_that_would_end_the_viewers_style_block(self):
        with tempfile.TemporaryDirectory() as d:
            tool = Path(d) / "prototype"
            shutil.copytree(Path(pp.__file__).parent, tool, ignore=shutil.ignore_patterns("__pycache__"))
            (tool / "system.css").write_text(":root { --x: 1; }</Style><b>\n", encoding="utf-8")
            with mock.patch.object(pp, "HERE", tool), self.assertRaisesRegex(ValueError, "</style"):
                pp.build_product_prototype(self.root)

    def test_nothing_reaches_past_the_product_template_and_nothing_swallows_the_page(self):
        for markup, expected in (
            ("</template><p>loose in the viewer</p>", "a </template> with no <template>"),
            ('<template data-item-template="card"><li>open', "an unclosed <template>"),
            ("<textarea>", "an unclosed <textarea>"),
            ("<style>", "an unclosed <style>"),
            ("<!-- open", "an unclosed comment"),
            ("<plaintext>", "a <plaintext>"),
            ("<noscript>x</noscript>", "a <noscript>"),
        ):
            with self.subTest(markup=markup):
                write_flow(self.root, "start", screen("start", "Start") + markup)
                out, problems = pp.build_product_prototype(self.root)
                self.assertIsNone(out)
                self.assertTrue(any(expected in p for p in problems), problems)
        for markup, expected in (
            ("<!-- a --!> </template><p>x</p> -->", "the form `--!>`"),
            ("<!--> </template> -->", "the form `<!-->`"),
            ('<p title="<template">x</p><![CDATA[> </template> ]]>', "the form `<![`"),
            ('<p title="<template">x</p><p>y</p>', "outside a real tag"),
            ('<p title="</template>">x</p>', "a </template> with no <template>"),  # any parser, any place
        ):
            with self.subTest(markup=markup):
                write_flow(self.root, "start", screen("start", "Start") + markup)
                self.assertIn(expected, self.problems_of())
        write_flow(self.root, "start", screen("start", "Start"))
        shell = self.root / APP / "shell.html"
        shell.write_text(shell.read_text(encoding="utf-8") + "</template>", encoding="utf-8")
        self.assertIn("shell.html holds a </template> with no <template>", self.problems_of())

    def test_the_design_goes_in_last_so_it_cannot_move_the_pages_own_parts(self):
        fake = '<!-- <script type="application/json" id="fixtures">{"product": "Not this"}</script> -->'
        write_flow(self.root, "start", screen("start", "Start") + fake)
        page = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        real = page.rsplit("</template>", 1)[1].split('<script type="application/json" id="fixtures">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(real)["product"], "Field Notes")
        self.assertIn(fake, page.rsplit("</template>", 1)[0])  # the comment stays inert, inside the product part

    def test_each_flow_names_its_own_item_templates(self):
        path = self.root / APP / "sitemap.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["flows"] = [{"id": "start", "title": "Start"}, {"id": "notes", "title": "Notes"}]
        data["navigation"] = [{"label": "Start", "go": "start:start"}, {"label": "Notes", "go": "notes:list"}]
        path.write_text(json.dumps(data), encoding="utf-8")
        card = '<template data-item-template="card"><li><button type="button" data-testid="{0}-card">{0}</button></li></template>'
        write_flow(self.root, "start", screen("start", "Start", '<ul data-list="items" data-item-template="card"></ul>' + card.format("start")))
        write_flow(
            self.root,
            "notes",
            screen(
                "list",
                "Notes",
                '<ul data-list="items" data-item-template="start:card"></ul><ul data-list="items" data-item-template="gone"></ul>' + card.format("notes"),
            ),
        )
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(
            problems,
            [
                'flows/notes.html lists `gone`, an item template no flow defines: add <template data-item-template="gone">, or name another flow\'s as `<flow>:<name>`'
            ],
        )
        page = out.read_text(encoding="utf-8")
        for name in ('data-item-template="start:card"', 'data-item-template="notes:card"', 'data-item-template="notes:gone"'):
            self.assertIn(name, page)

    def test_the_page_follows_every_link_the_check_passes(self):
        # A browser reads any quoting and any case, so the page qualifies each link from the same reading as the check.
        write_flow(
            self.root,
            "start",
            screen(
                "start",
                "Start",
                '<button data-go=\'detail\' data-testid="a">a</button><button DATA-GO=detail data-testid="b">b</button><ul data-list="notes" data-item-go="detail"></ul>',
            )
            + screen("detail", "Detail", '<button data-go="a&amp;b" x-data-go="keep" data-testid="c">c</button>'),
        )
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(problems, ["flows/start.html links to `a&b`, which no flow draws"])
        page = out.read_text(encoding="utf-8")
        for label in "ab":
            self.assertIn(f'<button data-go="start:detail" data-testid="{label}">{label}</button>', page)
        self.assertIn('data-item-go="start:detail"', page)
        self.assertIn('data-go="start:a&amp;b"', page)  # escaped once
        self.assertIn('x-data-go="keep"', page)  # another attribute, left as written
        write_flow(self.root, "start", screen("start", "Start", '<ul data-item-go="nowhere"></ul>'))
        self.assertIn("flows/start.html links to `nowhere`, which no flow draws", self.problems_of())

    def problems_of(self) -> str:
        return "\n".join(pp.build_product_prototype(self.root, write=False)[1])

    def test_depth_in_the_shell_and_in_a_flow_is_found_in_its_own_file_and_line(self):
        shell = self.root / APP / "shell.html"
        text = shell.read_text(encoding="utf-8")
        shell.write_text(
            text + "<style>\n.ring { box-shadow: 0 0 0 1px var(--color-border); }\n.bad { backdrop-filter: blur(8px); }\n</style>\n", encoding="utf-8"
        )
        write_flow(
            self.root,
            "start",
            '<section data-screen="start" data-title="Start">\n<div data-state="success">\n'
            '<p style="box-shadow: 0 6px 12px var(--color-border)">Raised</p>\n<p style="box-shadow: 0 0 0 1px var(--color-border)">Ringed</p>\n</div></section>',
        )
        found = [line.split(": ", 1)[0] for line in pp.build_product_prototype(self.root, write=False)[1]]
        self.assertEqual(found, [f"shell.html:{text.count(chr(10)) + 3}", "flows/start.html:3"])

    def test_each_screen_needs_a_state_whatever_its_markup_holds(self):
        for inside, stateless in (
            ('<p>Sign in</p><input name="email"><br><img alt="" src="data:,"><div data-state="success">ok</div>', False),
            ('</p><div data-state="success">ok</div>', False),  # a stray end tag closes nothing
            ('<svg viewBox="0 0 1 1"><path d="M0 0"/></svg><div data-state="success">ok</div>', False),
            ('<p>no state</p><input name="q">', True),
            ('<div><div data-state="success">not a direct child</div></div>', True),
        ):
            with self.subTest(inside=inside):
                write_flow(self.root, "start", f'<section data-screen="start" data-title="Start">{inside}</section>')
                self.assertEqual("screen `start:start` has no state" in self.problems_of(), stateless)
        write_flow(self.root, "start", '<section data-screen="start" data-title="Start"><div data-state="success">open')
        self.assertIn("screen `start:start` has no </section>", self.problems_of())

    def test_product_design_checks_map_shell_and_flow_faults_and_empty_flows(self):
        shell = self.root / APP / "shell.html"
        shell_text = shell.read_text(encoding="utf-8").replace("<!-- aidd:screens -->", "    <!-- aidd:screens -->")
        shell.write_text(shell_text + '<style>.bad { color: #123456; }</style><div id="main"></div>', encoding="utf-8")
        write_flow(
            self.root,
            "start",
            '<section data-screen="start" data-title="Start" data-initial="nowhere">\n'
            '<div data-state="success"><button type="button" data-go="start/missing">Go</button>'
            '<button type="button" data-testid="dup">A</button><button type="button" data-testid="dup">B</button>'
            '<span id="main"></span><p aria-labelledby="no-such-id">Body</p></div></section>',
        )
        out, problems = pp.build_product_prototype(self.root)
        self.assertIsNotNone(out)
        joined = "\n".join(problems)
        for want in (
            "shell.html:",
            'id="main" repeats',
            'the raw color in "color: #123456"',
            "flows/start.html:1:",
            "data-testid",
            'data-initial="nowhere"',
            'data-go="start:start/missing" names no state',
            'aria-labelledby="no-such-id" names missing id `no-such-id`',
            'id="main" repeats the id on shell.html:',
            'data-testid="dup" repeats the one on line 2',
        ):
            self.assertIn(want, joined)
        self.assertFalse(any(p.startswith("shell.html:") and ("data-testid" in p or "no-such-id" in p) for p in problems), joined)
        # A forbidden tag or empty flow list refuses the build and writes no page.
        write_flow(self.root, "start", '<section data-screen="start" data-title="Start"><div data-state="success"><script>1</script></div></section>')
        self.assertIsNone(pp.build_product_prototype(self.root)[0])
        sitemap_path = self.root / APP / "sitemap.json"
        sitemap = json.loads(sitemap_path.read_text(encoding="utf-8"))
        sitemap["flows"] = []
        sitemap["navigation"] = []
        sitemap_path.write_text(json.dumps(sitemap), encoding="utf-8")
        out_empty, empty_problems = pp.build_product_prototype(self.root)
        self.assertIsNotNone(out_empty)
        self.assertTrue(any("flows/start.html is in no flow" in p for p in empty_problems), empty_problems)
        self.assertFalse(any("draws no screen" in p for p in empty_problems), "the line that says why is the only one")
        self.assertIsNone(pp.contract_of(self.root, None)[0])

    def test_a_product_with_no_screen_says_so_once_and_names_where_screens_go(self):
        # Each way a product ends with no screen is one cause, so it is one problem line that names flows/, never the shell's line 1.
        def no_flow_listed(root: Path) -> None:
            sitemap = root / APP / "sitemap.json"
            sitemap.write_text(json.dumps(json.loads(sitemap.read_text(encoding="utf-8")) | {"flows": [], "navigation": []}), encoding="utf-8")

        def no_flow_file_either(root: Path) -> None:
            no_flow_listed(root)
            (root / APP / "flows" / "start.html").unlink()

        for label, change in (
            ("a flow file with no section", lambda root: write_flow(root, "start", "")),
            ("a flow file that no flow lists", no_flow_listed),
            ("no flow and no flow file", no_flow_file_either),
        ):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pp.new_product_prototype(root, product="Field Notes")
                change(root)
                problems = pp.check_product_prototype(root)[0]
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("flows/", problems[0])
                self.assertFalse(problems[0].startswith("shell.html:"), problems)

    def test_a_screen_is_a_section_with_an_id_a_link_can_name(self):
        for markup, expected in (
            ('<div data-screen="start"><div data-state="success">x</div></div>', 'a <div data-screen="start">'),
            ('<section data-screen="a:b"><div data-state="success">x</div></section>', "names a screen 'a:b'"),
            ('<section data-screen="a/b"><div data-state="success">x</div></section>', "names a screen 'a/b'"),
        ):
            with self.subTest(markup=markup):
                write_flow(self.root, "start", markup)
                self.assertIn(expected, self.problems_of())

    def test_two_flows_that_link_only_each_other_are_both_unreached(self):
        path = self.root / APP / "sitemap.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["flows"] += [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
        data["navigation"] += [{"label": "Start", "go": "start:start"}]  # a label twice: each gets a test id
        path.write_text(json.dumps(data), encoding="utf-8")
        write_flow(self.root, "a", screen("one", "One", '<button data-go="b:two">B</button>'))
        write_flow(self.root, "b", screen("two", "Two", '<button data-go="a:one">A</button>'))
        found = self.problems_of()
        for flow in ("a", "b"):
            self.assertIn(f"flow `{flow}` is reached only from the sitemap", found)
        page = pp.assemble(json.loads(path.read_text(encoding="utf-8")), (self.root / APP / "shell.html").read_text(encoding="utf-8"), [])
        self.assertIn('data-testid="app-nav-start-2"', page)

    def test_a_flow_file_the_sitemap_leaves_out_and_a_file_aidd_cannot_read_are_problems(self):
        write_flow(self.root, "billing", screen("invoice", "Invoice"))
        self.assertIn("flows/billing.html is in no flow of sitemap.json", self.problems_of())
        (self.root / APP / "flows" / "billing.html").unlink()
        (self.root / APP / "flows" / "start.html").write_bytes(b"\xff\xfe<section>")
        self.assertIn("start.html is not UTF-8 text", self.problems_of())

    def test_the_shell_runs_nothing_and_a_lost_marker_writes_nothing(self):
        shell = self.root / APP / "shell.html"
        text = shell.read_text(encoding="utf-8")
        self.assertNotIn("<script", text)  # the viewer's runtime is aidd's, taken from the template on every build
        for markup, expected in (
            ("<script>alert(1)</script>", "a <script>"),
            ('<meta http-equiv="Content-Security-Policy" content="default-src *">', "a <meta>"),
            ('<p onclick="alert(1)">x</p>', "an event handler"),
        ):
            with self.subTest(markup=markup):
                shell.write_text(text + markup, encoding="utf-8")
                out, problems = pp.build_product_prototype(self.root)
                self.assertIsNone(out)
                self.assertTrue(any(p.startswith("shell.html holds " + expected) for p in problems), problems)
        shell.write_text(text.replace(pp.MARKERS["navigation"], pp.MARKERS["navigation"] * 2), encoding="utf-8")
        out, problems = pp.build_product_prototype(self.root)
        self.assertIsNone(out)
        self.assertTrue(any("lost its marker" in p for p in problems), problems)
        self.assertFalse((self.root / pp.VIEW).exists())

    def test_a_page_aidd_cannot_build_removes_the_old_one(self):
        self.assertTrue(pp.build_product_prototype(self.root)[0])
        (self.root / APP / "sitemap.json").write_text("{", encoding="utf-8")
        out, problems = pp.build_product_prototype(self.root)
        self.assertIsNone(out)
        self.assertIn("line 1 column 2", problems[0])
        self.assertNotIn("aidd new product-prototype", problems[0])  # it refuses here, so it is no next step
        self.assertFalse((self.root / pp.VIEW).exists())

    def test_example_data_never_reaches_the_parser_as_markup(self):
        path = self.root / APP / "sitemap.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fixtures"] = {"note": "<!--<script></script>&amp;"}
        path.write_text(json.dumps(data), encoding="utf-8")
        text = pp.build_product_prototype(self.root)[0].read_text(encoding="utf-8")
        block = text.split('<script type="application/json" id="fixtures">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", block)
        self.assertIn("\\u003c!--\\u003cscript", block)
        self.assertEqual(json.loads(block)["note"], "<!--<script></script>&amp;")


class CommandTests(unittest.TestCase):
    def test_new_then_prototype_then_check(self):
        with adopted_repo() as root:
            code, out = run_cli("new", "product-prototype", "--title", "Field Notes")
            self.assertEqual(code, 0, out)
            self.assertIn("docs/design/app/sitemap.json", out)
            code, out = run_cli("prototype", "--check")
            self.assertEqual(code, 0, out)
            self.assertIn("consistent", out)
            code, out = run_cli("prototype")
            self.assertEqual(code, 0, out)
            self.assertTrue((root / pp.VIEW).is_file())
            write_flow(root, "start", '<section data-screen="start" data-title="Start"><p>no state</p></section>')
            code, out = run_cli("prototype", "--check")
            self.assertEqual(code, 1, out)
            self.assertIn("problem: screen `start:start` has no state", out)
            (root / APP / "sitemap.json").write_text("{", encoding="utf-8")
            code, out = run_cli("prototype")
            self.assertEqual(code, 1, out)  # fails closed: no page, and it says so
            self.assertIn("wrote no page", out)

    def test_the_page_is_written_only_to_aidds_output_folder(self):
        with adopted_repo():
            run_cli("new", "product-prototype")
            with self.assertRaises(SystemExit):
                run_cli("prototype", "--output", ".claude/settings.json")  # no such flag: no source decides where a file goes

    def test_a_frozen_spec_prototype_opens_in_the_current_viewer_and_stays_as_approved(self):
        with adopted_repo(spec="02-normal-feature:specs/SPEC-220.md") as root:
            code, out = run_cli("new", "design-spec", "checkout", "--spec", "SPEC-220", "--prototype")
            self.assertEqual(code, 0, out)
            rel = "specs/SPEC-220/design/prototype.html"
            before = (root / rel).read_bytes()
            code, out = run_cli("prototype", rel)
            self.assertEqual(code, 0, out)
            view = root / ".aidd" / "views" / "prototype-specs-spec-220-design-prototype.html"
            self.assertEqual((root / rel).read_bytes(), before)  # the approved file is never rewritten
            page = view.read_text(encoding="utf-8")
            self.assertIn("in the current viewer", page)
            self.assertIn('data-screen="start"', page)  # the skeleton's one screen
            self.assertNotIn("script-src 'unsafe-inline'", page)  # only the viewer's own script, by hash
            (root / rel).write_text(
                before.decode("utf-8").replace('<div class="device">', '<div class="device"><script>alert(1)</script>', 1), encoding="utf-8"
            )
            code, out = run_cli("prototype", rel)
            self.assertEqual(code, 1, out)
            self.assertIn("holds a <script>", out)
            odd = root / "specs" / "SPEC-220" / "design" / "a-->b.html"
            odd.write_bytes(before)
            code, out = run_cli("prototype", "specs/SPEC-220/design/a-->b.html")
            self.assertEqual(code, 1, out)
            self.assertIn("takes letters, digits", out)  # a path aidd names in the page closes no comment
            (root / "-x.html").write_bytes(before)
            code, out = run_cli("prototype", "./-x.html")  # a path that starts with `-` is no command word: `aidd prototype -x.html` is an option
            self.assertEqual(code, 1, out)
            self.assertIn("takes letters, digits", out)
            code, out = run_cli("prototype", "../outside.html")
            self.assertEqual(code, 1, out)
            self.assertIn("no prototype file in this repository", out)

    def test_force_never_overwrites_the_product_prototype(self):
        with adopted_repo():
            run_cli("new", "product-prototype")
            code, out = run_cli("new", "product-prototype", "--force")
            self.assertNotEqual(code, 0)
            self.assertIn("never overwrites", out)

    def test_no_product_prototype_names_the_command_that_starts_one(self):
        with adopted_repo():
            code, out = run_cli("prototype")
            self.assertNotEqual(code, 0)
            self.assertIn("aidd new product-prototype", out)


class SameChangeTests(unittest.TestCase):
    """A change that alters a Spec's design leaves the product prototype as it was: `aidd validate` warns."""

    def spec(self, root: Path, route: str = "normal") -> tuple[Path, dict]:
        path = root / "specs" / "SPEC-90.md"
        return path, {"type": "spec", "id": "SPEC-90", "route": route}

    def test_a_design_change_without_the_product_prototype_warns_and_with_it_does_not(self):
        with adopted_repo() as root:
            git(root, "switch", "-q", "main")  # the product prototype is the base branch's already
            pp.new_product_prototype(root, product="Field Notes")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "the product prototype")
            git(root, "switch", "-qc", "spec/SPEC-90")
            (root / "specs" / "SPEC-90" / "design").mkdir(parents=True)
            (root / "specs" / "SPEC-90" / "design" / "prototype.html").write_text("<p>a new flow</p>", encoding="utf-8")
            path, data = self.spec(root)
            warnings = living_work.same_change_warnings(path, data, root)
            self.assertEqual(len(warnings), 1, warnings)
            self.assertIn("design-spec", warnings[0])
            self.assertIn("docs/design/app/**", warnings[0])
            self.assertEqual(living_work.same_change_warnings(path, {**data, "route": "minor"}, root), [])  # not a route with a Spec
            write_flow(root, "start", screen("start", "Start, now with the new flow"))
            self.assertEqual(living_work.same_change_warnings(path, data, root), [])

    def test_only_the_prototype_or_the_design_spec_feeds_it_and_only_while_the_spec_is_open(self):
        with adopted_repo() as root:
            git(root, "switch", "-q", "main")
            pp.new_product_prototype(root, product="Field Notes")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "the product prototype")
            git(root, "switch", "-qc", "spec/SPEC-90")
            (root / "specs" / "SPEC-90" / "design").mkdir(parents=True)
            (root / "specs" / "SPEC-90" / "design" / "accessibility-notes.md").write_text("Focus order.", encoding="utf-8")
            path, data = self.spec(root)
            self.assertEqual(living_work.same_change_warnings(path, data, root), [])  # notes feed no screen
            (root / "specs" / "SPEC-90" / "design-spec-search.md").write_text("# Search", encoding="utf-8")
            warnings = living_work.same_change_warnings(path, data, root)
            self.assertIn("the product-designer may write it while the Spec is a draft", warnings[0])
            planned = {**data, "tasks": [{"id": "T1", "scope": ["docs/design/app/**"]}]}
            self.assertEqual(living_work.same_change_warnings(path, planned, root), [])  # a Task plans it: answered
            self.assertEqual(living_work.same_change_warnings(path, {**data, "status": "cancelled"}, root), [])
            self.assertEqual(len(living_work.same_change_warnings(path, {**data, "base": "main"}, root)), 1)  # the Spec's own base
            gone = living_work.same_change_warnings(path, {**data, "base": "no-such-branch"}, root)
            self.assertEqual(len(gone), 1)
            self.assertIn("found no base branch", gone[0])  # a word, never a silent pass

    def test_aidd_validate_gives_the_warning(self):
        with adopted_repo(spec="02-normal-feature:specs/SPEC-220.md") as root:
            git(root, "switch", "-q", "main")
            pp.new_product_prototype(root, product="Field Notes")
            git(root, "add", "docs")
            git(root, "commit", "-qm", "the product prototype")
            git(root, "switch", "-qC", "feat")  # the branch starts after it, and the Spec stays in the working tree
            (root / "specs" / "SPEC-220" / "design").mkdir(parents=True, exist_ok=True)
            (root / "specs" / "SPEC-220" / "design" / "prototype.html").write_text("<p>search</p>", encoding="utf-8")
            out = run_cli("validate", "specs/SPEC-220.md")[1]
            self.assertIn("leaves the product's product-prototype", out)

    def test_a_repository_that_keeps_no_product_prototype_hears_nothing(self):
        with adopted_repo() as root:
            git(root, "switch", "-qc", "spec/SPEC-90")
            (root / "specs" / "SPEC-90" / "design").mkdir(parents=True)
            (root / "specs" / "SPEC-90" / "design" / "prototype.html").write_text("<p>a flow</p>", encoding="utf-8")
            self.assertEqual(living_work.same_change_warnings(*self.spec(root), root), [])

    def test_every_feeding_type_names_a_product_type_with_files(self):
        docs = team_registry.roles()["graph"]["documents"]
        feeding = {k: d["feeds"] for k, d in docs.items() if d.get("feeds")}
        self.assertEqual(
            feeding,
            {
                "tech-spec": "architecture",
                "design-spec": "product-prototype",
                "tracking-plan": "metrics-dictionary",
                "slo": "service-card",
                "compliance-record": "control-register",
            },
        )
        for doc_type, target in feeding.items():
            self.assertEqual(docs[doc_type]["belongs_to"], "change", doc_type)
            self.assertEqual(docs[target]["belongs_to"], "product", target)
            self.assertTrue(docs[doc_type].get("files") and docs[target].get("files"), doc_type)


class PartialsAndTypoHintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        pp.new_product_prototype(self.root, product="Field Notes")
        sitemap = json.loads((self.root / APP / "sitemap.json").read_text(encoding="utf-8"))
        sitemap["flows"] = [{"id": "start", "title": "Start"}, {"id": "notes", "title": "Notes"}]
        sitemap["navigation"] = [{"label": "Start", "go": "start:start"}, {"label": "Notes", "go": "notes:list"}]
        (self.root / APP / "sitemap.json").write_text(json.dumps(sitemap), encoding="utf-8")
        write_flow(self.root, "notes", screen("list", "All notes", '<p data-testid="n">Notes</p>'))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cross_flow_typo_links_and_navigation_suggest_nearest_target(self):
        write_flow(self.root, "start", screen("start", "Start", '<button type="button" data-go="notse:list" data-testid="go-notes">Go</button>'))
        problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("did you mean `notes:list`?" in p for p in problems), problems)

        sitemap = json.loads((self.root / APP / "sitemap.json").read_text(encoding="utf-8"))
        sitemap["navigation"][1]["go"] = "notes:lst"
        (self.root / APP / "sitemap.json").write_text(json.dumps(sitemap), encoding="utf-8")
        write_flow(self.root, "start", screen("start", "Start"))
        problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("did you mean `notes:list`?" in p for p in problems), problems)

    def test_component_partial_expands_parameters_maps_errors_and_rejects_bad_includes(self):
        comps = self.root / APP / "components"
        comps.mkdir(parents=True, exist_ok=True)
        (comps / "note-card.html").write_text(
            '<article data-component="note-card" data-variant="{{variant}}">\n'
            '  <button type="button" data-go="notes:list" data-testid="{{testid}}">{{title}}</button>\n'
            "</article>\n",
            encoding="utf-8",
        )
        write_flow(
            self.root,
            "start",
            screen("start", "Start", '<!-- aidd:use note-card variant="compact" testid="open-note" title="Field <1>" -->'),
        )
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(problems, [])
        built = out.read_text(encoding="utf-8")
        self.assertIn('data-component="note-card" data-variant="compact"', built)
        self.assertIn("Field &lt;1&gt;", built)
        contract, contract_problems = pp.contract_of(self.root, None)
        self.assertEqual(contract_problems, [])
        self.assertIn("note-card", [c["name"] for c in contract["components"]])

        # Line-accurate error mapping back to components/note-card.html
        (comps / "note-card.html").write_text(
            '<article data-component="note-card">\n  <p style="color:#123456">Bad</p>\n</article>\n',
            encoding="utf-8",
        )
        write_flow(self.root, "start", screen("start", "Start", "<!-- aidd:use note-card -->"))
        err_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("components/note-card.html:2:" in p for p in err_problems), err_problems)

        # Missing parameter reports caller line
        (comps / "note-card.html").write_text("<p>{{missing_key}}</p>\n", encoding="utf-8")
        missing_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("missing `missing_key=...`" in p for p in missing_problems), missing_problems)

        # Nested cycle reports cycle clearly
        (comps / "a.html").write_text("<!-- aidd:use b -->\n", encoding="utf-8")
        (comps / "b.html").write_text("<!-- aidd:use a -->\n", encoding="utf-8")
        write_flow(self.root, "start", screen("start", "Start", "<!-- aidd:use a -->"))
        cycle_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("loops back to itself" in p for p in cycle_problems), cycle_problems)

        # <section inside partial refused
        (comps / "bad-sec.html").write_text('<section data-screen="x">No</section>\n', encoding="utf-8")
        write_flow(self.root, "start", screen("start", "Start", "<!-- aidd:use bad-sec -->"))
        sec_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("holds a <section>" in p for p in sec_problems), sec_problems)

        # Multi-line partial expands cleanly, nested partial avoids double-escape, and unclosed directive errors
        (comps / "inner.html").write_text('<span data-testid="tag">{{title}}</span>\n', encoding="utf-8")
        (comps / "outer.html").write_text('<!-- aidd:use inner title="{{title}}" -->\n', encoding="utf-8")
        write_flow(
            self.root,
            "start",
            screen("start", "Start", '<!-- aidd:use outer\n  title="R&amp;D <1>" -->'),
        )
        ok_problems = pp.check_product_prototype(self.root)[0]
        self.assertEqual(ok_problems, [])
        built_path, _ = pp.build_product_prototype(self.root)
        built_text = built_path.read_text(encoding="utf-8")
        self.assertIn("R&amp;D &lt;1&gt;", built_text)
        self.assertNotIn("&amp;amp;", built_text)

        write_flow(self.root, "start", screen("start", "Start", '<!-- aidd:use inner\n  title="Missing end"'))
        unclosed_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("unclosed <!-- aidd:use" in p for p in unclosed_problems), unclosed_problems)

        # Attribute-injected raw color through partial parameter is caught with exact component line
        (comps / "badge.html").write_text('<span style="color:{{ink}}">{{text}}</span>\n', encoding="utf-8")
        write_flow(self.root, "start", screen("start", "Start", '<!-- aidd:use badge ink="#1d4ed8" text="OK" -->'))
        attr_problems = pp.check_product_prototype(self.root)[0]
        self.assertTrue(any("components/badge.html:1:" in p and "var(--color-accent)" in p for p in attr_problems), attr_problems)

    def test_bundled_product_example_builds_with_zero_problems(self) -> None:
        example_root = Path(__file__).resolve().parents[1] / "plugins" / "aidd-team" / "tools" / "prototype" / "examples" / "product"
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            app_dir = temp_root / "docs" / "design" / "app"
            app_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(example_root, app_dir)
            problems, checked = pp.check_product_prototype(temp_root)
            self.assertEqual(problems, [])
            self.assertEqual(checked, "ok: 3 screens, 7 states, 23 test ids")
            out_path, built_problems = pp.build_product_prototype(temp_root)
            self.assertEqual(built_problems, [])
            page = out_path.read_text(encoding="utf-8")
            self.assertIn('data-component="note-card"', page)
            self.assertIn('data-toggle="note-history"', page)


if __name__ == "__main__":
    unittest.main()
