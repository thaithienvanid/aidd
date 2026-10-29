"""The product designer's living work: the whole-product prototype (L1), the same-change check that keeps each role's
product-level work in line with the changes that shape it (L0), and the roles `aidd context` hands it to (L2)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import adopted_repo, git, run_cli

from aidd.autopilot import context_pack
from aidd.guard import frozen_files, role_areas
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
            screen("list", "All notes", '<button data-go="detail">Open</button>')
            + screen("detail", "A note", '<button data-go="start:start">Home</button>', "list"),
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
            screen("start", "Start", '<button data-go=\'detail\'>a</button><button DATA-GO=detail>b</button><ul data-list="notes" data-item-go="detail"></ul>')
            + screen("detail", "Detail", '<button data-go="a&amp;b" x-data-go="keep">c</button>'),
        )
        out, problems = pp.build_product_prototype(self.root)
        self.assertEqual(problems, ["flows/start.html links to `a&b`, which no flow draws"])
        page = out.read_text(encoding="utf-8")
        for label in "ab":
            self.assertIn(f'<button data-go="start:detail">{label}</button>', page)
        self.assertIn('data-item-go="start:detail"', page)
        self.assertIn('data-go="start:a&amp;b"', page)  # escaped once
        self.assertIn('x-data-go="keep"', page)  # another attribute, left as written
        write_flow(self.root, "start", screen("start", "Start", '<ul data-item-go="nowhere"></ul>'))
        self.assertIn("flows/start.html links to `nowhere`, which no flow draws", self.problems_of())

    def problems_of(self) -> str:
        return "\n".join(pp.build_product_prototype(self.root, write=False)[1])

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
            code, out = run_cli("prototype", "../outside.html")
            self.assertEqual(code, 1, out)
            self.assertIn("no prototype file in this repository", out)

    def test_aidd_list_names_the_product_level_work_it_keeps(self):
        with adopted_repo() as root:
            run_cli("new", "product-prototype")
            git(root, "add", "-A")
            living = json.loads(run_cli("list", "--json")[1])["living"]
            self.assertEqual(living, [{"kind": "product-prototype", "home": "docs/design/app/", "files": 3, "opened_by": "aidd prototype"}])
            run_cli("new", "design-system")
            git(root, "add", "-A")
            living = json.loads(run_cli("list", "--json")[1])["living"]
            self.assertIn({"kind": "design-system", "home": "DESIGN.md", "files": 2}, living)

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
        return path, {"kind": "spec", "id": "SPEC-90", "route": route}

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
            self.assertEqual(living_work.same_change_warnings(path, {**data, "route": "minor"}, root), [])  # not the fast lane
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

    def test_every_feeding_kind_names_a_product_kind_with_files(self):
        docs = team_registry.roles()["loop"]["documents"]
        feeding = {k: d["feeds"] for k, d in docs.items() if d.get("feeds")}
        self.assertEqual(feeding, {"tech-spec": "architecture", "design-spec": "product-prototype"})
        for kind, target in feeding.items():
            self.assertEqual(docs[kind]["scope"], "change", kind)
            self.assertEqual(docs[target]["scope"], "product", target)
            self.assertTrue(docs[kind].get("files") and docs[target].get("files"), kind)


class WriteAreaTests(unittest.TestCase):
    def test_each_owner_writes_its_living_work_in_the_configured_docs_folder(self):
        self.assertEqual(role_areas.living_files("architect", "handbook"), ["handbook/architecture/**"])
        self.assertEqual(role_areas.living_files("product-designer", "handbook"), ["handbook/design/app/**"])

    def test_the_design_system_is_the_designers_but_never_its_living_area(self):
        row = team_registry.roles()["loop"]["documents"]["design-system"]
        self.assertEqual((row["owner"], row["scope"], row["changed_only_in_a_task"]), ("product-designer", "product", True))
        self.assertEqual(row["files"], ["DESIGN.md", "design/tokens.json"])
        self.assertNotIn("DESIGN.md", role_areas.living_files("product-designer", "docs"))
        tracked = ["DESIGN.md", "design/tokens.json", "design/build.mjs"]
        self.assertEqual([p for p, _ in context_pack.living_work("developer", tracked, None)], ["DESIGN.md"])  # the entry; the rest by path
        mine = context_pack.living_work("product-designer", tracked, None)
        self.assertEqual([p for p, _ in mine], ["DESIGN.md", "design/tokens.json"])
        self.assertNotIn("in the same change", mine[0][1])  # never as living work; only a Task changes it
        self.assertEqual(context_pack.living_work("sre", tracked, None), [])

    def test_the_designers_living_work_follows_the_configured_docs_folder(self):
        self.assertEqual(role_areas.living_files("product-designer", "handbook"), ["handbook/design/app/**"])
        self.assertEqual(role_areas.living_files("developer", "docs"), [])

    def test_a_draft_never_freezes_the_product_prototype(self):
        """Before Spec approval, the guard's advice for a new file is to link it from the Spec, frozen by default; for the
        product's living work it says to keep it living."""
        advice = frozen_files.living_work_note("handbook/design/app/sitemap.json", "handbook", "product-designer", [])
        self.assertIsNone(frozen_files.living_work_note("handbook/adr/0001.md", "handbook", "product-designer", []))
        self.assertIn("living work", advice or "")
        self.assertIn("never link it", advice or "")
        self.assertIsNone(frozen_files.living_work_note("handbook/design/app/sitemap.json", "handbook", "developer", []))  # not its owner
        frozen = [("specs/SPEC-1.md", {"id": "SPEC-1", "design": {"files": ["handbook/design/app/**"]}})]
        self.assertIsNone(frozen_files.living_work_note("handbook/design/app/sitemap.json", "handbook", "product-designer", frozen))


class ContextTests(unittest.TestCase):
    def test_each_role_gets_the_living_work_it_keeps_or_builds_against(self):
        tracked = ["docs/architecture/README.md", "docs/design/app/sitemap.json", "docs/design/app/flows/start.html", "src/app.py"]
        by_role = {r: [p for p, _ in context_pack.living_work(r, tracked, None)] for r in ("architect", "developer", "product-designer", "verifier", "sre")}
        self.assertEqual(by_role["architect"], ["docs/architecture/README.md"])
        self.assertEqual(by_role["product-designer"], ["docs/design/app/sitemap.json", "docs/design/app/flows/start.html"])
        # A Spec with no design: a reader gets only the top-level files, to read further by path.
        self.assertEqual(by_role["developer"], ["docs/architecture/README.md", "docs/design/app/sitemap.json"])
        self.assertEqual(by_role["verifier"], ["docs/design/app/sitemap.json"])
        self.assertEqual(by_role["sre"], [])
        self.assertEqual(context_pack.living_work(None, tracked, None), [])
        designed = [*tracked, "specs/SPEC-9/design/prototype.html"]
        self.assertEqual(
            [p for p, _ in context_pack.living_work("verifier", designed, None, "SPEC-9")], ["docs/design/app/sitemap.json", "docs/design/app/flows/start.html"]
        )

    def test_the_entry_files_come_first_and_no_picture_is_handed_out(self):
        many = [f"docs/design/app/flows/f{i:02}.html" for i in range(20)] + ["docs/design/app/shell.html", "docs/design/app/sitemap.json"]
        files = [p for p, _ in context_pack.living_work("product-designer", [*many, "docs/design/app/round-1.png"], None)]
        self.assertEqual(len(files), context_pack.LIVING_FILES)
        self.assertEqual(files[:2], ["docs/design/app/shell.html", "docs/design/app/sitemap.json"])
        self.assertNotIn("docs/design/app/round-1.png", files)

    def test_a_pack_for_a_role_carries_its_living_work(self):
        with adopted_repo() as root:
            run_cli("new", "product-prototype")
            git(root, "add", "-A")
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs" / "SPEC-9.md").write_text("---\nkind: spec\nid: SPEC-9\ntitle: A screen\n---\n# SPEC-9\n", encoding="utf-8")
            git(root, "add", "-A")
            pack = context_pack.build_context_pack(root, "SPEC-9", role="verifier")
            self.assertIn("docs/design/app/sitemap.json", [i["path"] for i in pack["items"] if i["kind"] == "living"])


if __name__ == "__main__":
    unittest.main()
