"""Twenty-three types of document, each with one home.

`aidd new` writes the twenty-three types below, and nothing else: the cut types live as sections of the documents that already
held them (flows and a usability test in the design spec, a component in DESIGN.md, a brief's problem and its evidence
in the Intent, the support terms in the contract, a change order beside the contract in the proposal's folder, a decision
card as an exploration with no visuals). The data map, the vendor register, the glossary, the vulnerability policy, and AGENTS.md are the repository's own, at fixed paths;
the contract and its change orders are the engagement's, in the proposal's folder. An exploration's front matter has a
schema, `aidd new exploration` writes it, and `aidd explore` only renders.
"""

import contextlib
import datetime as dt
import io
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, make_repo, run_cli

from aidd import config
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.views import exploration_page
from aidd.kernel import documents, json_schema, resources
from aidd.kernel import text as kernel_text

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TYPES = {
    "product-brief",
    "metrics-dictionary",
    "service-card",
    "control-register",
    "improvement-log",
    "srs",
    "tech-spec",
    "test-plan",
    "design-spec",
    "adr",
    "threat-model",
    "authz",
    "api",
    "runbook",
    "slo",
    "compliance",
    "analytics",
    "migration",
    "acceptance",
    "design-system",
    "architecture",
    "data-map",
    "vendors",
    "glossary",
    "vulnerability-policy",
    "agents",
    "feedback",
    "contract",
    "exploration",
}
CUT = ("flows", "journey", "usability", "component", "brief", "sla", "change-order", "decision-card", "ui", "authz-matrix")
LINKED = (
    "tech-spec",
    "test-plan",
    "design-spec",
    "adr",
    "threat-model",
    "authz",
    "api",
    "runbook",
    "slo",
    "compliance",
    "analytics",
    "migration",
    "acceptance",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


class TheKinds(unittest.TestCase):
    def test_twenty_three_types_and_no_other(self):
        self.assertEqual(set(authoring.DOC_TYPES_NEW), TYPES)
        self.assertEqual(len(authoring.DOC_TYPES_NEW), 29)
        for doc_type in CUT:
            with self.subTest(doc_type=doc_type), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_cli("new", doc_type, "x")

    def test_the_help_names_the_common_types_and_list_names_every_one(self):
        # The help's first screen names the work items and the six documents a Spec links most; `--list` the rest.
        from aidd.cli import grammar

        code, out = run_cli("help", "new")
        self.assertEqual(code, 0)
        usage = out.split("\n\n", 1)[0]
        self.assertNotIn("vulnerability-policy", usage)
        positional = out.split("positional arguments:", 1)[1].split("options:", 1)[0]
        for name in (*grammar.NEW_WORK_ITEMS, *grammar.NEW_COMMON_DOCS):
            self.assertIn(name, " ".join(positional.split()).replace("- ", "-"), name)
        self.assertNotIn("metrics-dictionary", positional)
        from aidd.cli import parser as cli_parser

        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as done:
            cli_parser.build_parser().parse_args(["new", "--list"])
        self.assertEqual(done.exception.code, 0)
        listed = [t for line in out.getvalue().splitlines() if ": " in line for t in line.split(": ", 1)[1].split(", ")]
        self.assertEqual(sorted(listed), sorted(grammar.new_types()), "each type once")
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            cli_parser.build_parser().parse_args(["new"])
        self.assertIn("aidd new --list", err.getvalue())

    def test_what_a_spec_links(self):
        self.assertEqual(config.DOC_TYPES, (*LINKED, "data-map", "vendors", "other"))
        spec_types = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["type"]["enum"]
        self.assertEqual(tuple(spec_types), config.DOC_TYPES)
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"]
        self.assertEqual(set(required), set(config.default_docs_required()))  # a type aidd has a rule for

    def test_the_cut_templates_are_gone(self):
        for name in ("journey-map.md", "user-flows.md", "usability-test.md", "component-spec.md", "support-sla.md", "brief.md", "decision-card.md"):
            self.assertFalse((ASSETS / name).exists(), name)


class TheirNewHomes(unittest.TestCase):
    def test_the_design_spec_holds_flows_and_the_usability_test(self):
        ds = read(ASSETS / "design-spec.md")
        self.assertIn("```mermaid", section(ds, "## Flows"))
        usability = section(ds, "## Usability test")
        for word in ("Participants", "Tasks", "Findings", "feedback"):
            self.assertIn(word, usability, word)

    def test_design_md_holds_the_components(self):
        comp = section(read(ASSETS / "DESIGN.md"), "\n## Components\n")
        for word in ("Anatomy", "Props", "states", "Accessibility"):
            self.assertIn(word, comp, word)

    def test_the_intent_holds_the_problem_and_the_map(self):
        intent = read(ASSETS / "intent.md")
        self.assertIn("the brief", section(intent, "## Problem"))
        for word in ("Persona", "Pain points", "Service blueprint"):
            self.assertIn(word, section(intent, "## Map"), word)
        self.assertIn("brief", resources.load_json("intent.schema.json")["properties"])  # the Intent may name its brief

    def test_the_contract_holds_the_support_terms_and_points_at_the_proposal(self):
        text = read(ASSETS / "contract.md")
        support = section(text, "## Support and service levels")
        for word in ("S1", "S2", "S3", "S4", "Escalation", "Maintenance", "Response", "Resolution"):
            self.assertIn(word, support, word)
        for heading in ("## Phases", "## Assumptions and exclusions"):
            body = section(text, heading)
            self.assertIn("proposal", body, heading)
            self.assertNotIn("| M-1 |", body, heading)
        self.assertIn("change-orders/CO-", section(text, "## Change control"))

    def test_the_test_plan_points_to_the_acceptance_record(self):
        text = read(ASSETS / "test-plan.md")
        self.assertNotIn("## User acceptance", text)
        self.assertIn("aidd new acceptance", text)


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewWritesEachHome(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def new(self, *args: str) -> str:
        code, out = run_cli("new", *args)
        self.assertEqual(code, 0, out)
        return out

    def links(self) -> dict[str, dict]:
        data, _ = documents.split_front_matter(read(self.root / "specs" / "SPEC-220.md"))
        return {d["path"]: d for d in data.get("docs") or []}

    def test_ui_is_the_design_spec_and_prototype_is_its_html(self):
        self.new("design-spec", "cart", "--spec", "SPEC-220")
        self.assertIn("# Design spec", read(self.root / "specs/SPEC-220/design-spec-cart.md"))
        self.new("design-spec", "cart", "--spec", "SPEC-220", "--prototype")
        self.assertIn("<html", read(self.root / "specs/SPEC-220/design/prototype.html").lower())
        links = self.links()
        self.assertEqual({links[p]["type"] for p in ("specs/SPEC-220/design-spec-cart.md", "specs/SPEC-220/design/prototype.html")}, {"design-spec"})

    def test_a_team_writes_the_full_design_spec(self):
        self.new("design-spec", "cart", "--spec", "SPEC-220")
        self.assertIn("## Platforms", read(self.root / "specs/SPEC-220/design-spec-cart.md"))

    def test_authz_is_the_authorization_matrix(self):
        self.new("authz", "admin", "--spec", "SPEC-220")
        self.assertIn("SPEC-220", read(self.root / "specs/SPEC-220/authz-admin.md"))
        self.assertEqual(self.links()["specs/SPEC-220/authz-admin.md"]["type"], "authz")

    def test_the_data_map_and_the_vendor_register_are_the_repositorys(self):
        self.new("data-map")
        self.new("vendors")
        self.assertTrue((self.root / "docs/data-map.md").is_file())
        self.assertTrue((self.root / "docs/vendors.md").is_file())
        code, out = run_cli("new", "vendors")
        self.assertNotEqual(code, 0, "one per repository")
        self.assertIn("exists", out)

    def test_the_glossary_is_the_repositorys_living_list_of_terms(self):
        """One word, one meaning: the plain-language and technical-writing skills use the project's GLOSSARY.md, and
        Clarify records each term the author settles there."""
        self.new("glossary")
        path = self.root / "docs/GLOSSARY.md"
        self.assertTrue(path.is_file())
        text = read(path)
        self.assertNotIn("{{", text)
        self.assertIn("| Term | Meaning | Avoid |", text)
        self.assertIn("aidd new glossary", text)
        code, out = run_cli("new", "glossary")
        self.assertNotEqual(code, 0, "one per repository")
        self.assertIn("exists", out)
        code, out = run_cli("new", "glossary", "--spec", "SPEC-220")
        self.assertNotEqual(code, 0, "the repository's, not a Spec's")

    def test_the_renewal_check_finds_the_register_without_a_spec_link(self):
        self.new("vendors")
        path = self.root / "docs/vendors.md"
        path.write_text(read(path) + "| Mailer Inc | email | none | n/a | 99.9% | 2026-10-10 | @ops |\n", encoding="utf-8")
        _, warnings = validation.check_repo(self.root, today=dt.date(2026, 9, 30))
        self.assertTrue(any("Mailer Inc" in w and "docs/vendors.md" in w for w in warnings), warnings)

    def test_a_vendors_path_outside_the_repository_is_never_read(self):
        import tempfile

        from aidd.workitems import due_dates

        row = "| Mailer Inc | email | none | n/a | 99.9% | 2026-10-10 | @ops |\n"
        with tempfile.TemporaryDirectory() as d:
            root, outside = Path(d) / "repo", Path(d) / "vendors.md"
            root.mkdir()
            text = (Path(__file__).resolve().parents[1] / ".agents/skills/aidd/assets/vendors.md").read_text(encoding="utf-8") + row
            outside.write_text(text, encoding="utf-8")
            (root / "inside.md").write_text(text, encoding="utf-8")
            inside = {"type": "spec", "docs": [{"type": "vendors", "path": "inside.md"}]}
            self.assertTrue(due_dates.renewal_warnings(root, [("specs/SPEC-1.md", inside)], dt.date(2026, 9, 30)))  # the same file inside is read
            for rel in ("../vendors.md", str(outside)):
                with self.subTest(rel=rel):
                    spec = {"type": "spec", "docs": [{"type": "vendors", "path": rel}]}
                    self.assertEqual(due_dates.renewal_warnings(root, [("specs/SPEC-1.md", spec)], dt.date(2026, 9, 30)), [])

    def test_the_contract_then_each_change_order_in_the_proposals_folder(self):
        self.new("proposal", "PROP-7", "--title", "Portal", "--addressee", "Acme")
        self.new("contract", "PROP-7")
        folder = self.root / "proposals/PROP-7"
        self.assertIn("PROP-7", read(folder / "contract.md"))
        self.new("contract", "PROP-7")
        self.new("contract", "PROP-7")
        self.assertIn("# Change order", read(folder / "change-orders/CO-1.md"))
        self.assertTrue((folder / "change-orders/CO-2.md").is_file())
        code, out = run_cli("new", "contract", "PROP-404")
        self.assertNotEqual(code, 0)
        self.assertIn("PROP-404", out)

    def test_the_intent_is_the_solo_founders_brief(self):
        self.new("intent", "INTENT-1", "--title", "Pet sitter MVP")
        text = read(self.root / "specs/INTENT-1.md")
        self.assertIn("type: intent\n", text)
        self.assertIn("## Problem", text)
        self.assertEqual([e for e in validation.validate_file(self.root / "specs/INTENT-1.md") if not e.startswith("warning: ")], [])

    def test_new_exploration_writes_it_and_explore_only_renders(self):
        out = self.new("exploration", "specs/SPEC-9/explore/refund-button", "--title", "Where does the refund button go?", "--timebox", "30 minutes")
        self.assertIn("exploration.md", out)
        text = read(self.root / "specs/SPEC-9/explore/refund-button/exploration.md")
        self.assertIn("Where does the refund button go?", text)
        self.assertIn("30 minutes", text)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_cli("explore", "specs/SPEC-10/explore/x", "--question", "x")
        code, out = run_cli("explore", "specs/SPEC-10/explore/x")
        self.assertNotEqual(code, 0)
        self.assertIn("aidd new exploration", out)
        code, out = run_cli("explore", "specs/SPEC-9/explore/refund-button")
        self.assertEqual(code, 0, out)

    def test_an_exploration_outside_its_home_is_refused_with_the_right_folder(self):
        # The exploration lives in the folder of the work item it informs; the old homes name the folder it moved to.
        for given, home in (
            ("specs/INIT-1/refund-limit", "specs/INIT-1/explore/refund-limit"),
            ("docs/specs/SPEC-7/refund-limit", "specs/SPEC-7/explore/refund-limit"),
            ("docs/design/SPEC-12", "specs/SPEC-12/explore/<slug>"),
        ):
            with self.subTest(given):
                code, out = run_cli("new", "exploration", given, "--title", "Q?")
                self.assertNotEqual(code, 0, out)
                self.assertIn(f"aidd new exploration {home}", out)
                self.assertFalse((self.root / given).exists())
        self.assertIn("exploration.md", self.new("exploration", "specs/explore/queues", "--title", "Which queue?"))


class ExplorationSchema(unittest.TestCase):
    def test_the_template_front_matter_validates(self):
        text = kernel_text.fill_template(
            read(ASSETS / "exploration.md"), title="Q", question="Q", owner="product-designer", timebox="45 minutes", today="2026-09-30"
        )
        data, _ = documents.split_front_matter(text)
        self.assertEqual(json_schema.validate(data, "exploration.schema.json"), [])
        self.assertTrue(json_schema.validate(dict(data, status="maybe"), "exploration.schema.json"))
        self.assertTrue(json_schema.validate(dict(data, owner="nobody at all"), "exploration.schema.json"))

    def test_a_bad_front_matter_is_refused_on_render(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "exploration.md").write_text("---\ntype: exploration\nquestion: Q\nowner: architect\nstatus: maybe\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "status"):
                exploration_page.comparison_page(folder)

    def test_a_decision_card_is_an_exploration_without_visuals(self):
        text = read(ASSETS / "exploration.md")
        self.assertIn("decision card", text.lower())
        self.assertIn("exploration", read(ROOT / ".agents" / "skills" / "aidd" / "references" / "handoff.md"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class SoloWritesTheShortSet(RepoTemplateCase):
    """The profile and the route pick the template together: solo writes the short Spec and the design spec's light
    variant, and every document the risk triggers is still expected."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo")

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def new(self, *args: str) -> str:
        code, out = run_cli("new", *args)
        self.assertEqual(code, 0, out)
        return out

    def test_a_major_spec_is_the_short_one_and_still_asks_for_its_docs(self):
        out = self.new("spec", "SPEC-9", "--title", "Sign-in", "--route", "major", "--dimension", "security", "--paths", "src/web/login.tsx")
        text = read(self.root / "specs/SPEC-9.md")
        self.assertNotIn("## Problem", text)
        self.assertIn("\nobserve:", text)
        for doc in ("tech-spec", "runbook", "threat-model", "design-spec"):
            self.assertIn(f"{doc} (expected", out, doc)  # the matrix `aidd validate` warns from, as the route gives it
        self.new("spec", "SPEC-10", "--title", "t", "--route", "major", "--full")
        self.assertIn("## Problem", read(self.root / "specs/SPEC-10.md"))

    def test_a_bare_tests_folder_stays_out_of_the_scope(self):
        # It would hold the acceptance tests Spec approval freezes, so the note names the unit-test folder instead.
        out = self.new("spec", "SPEC-9", "--title", "t", "--paths", "src/web/login.tsx", "tests/", "tests/unit/test_login.py")
        scope = re.search(r"(?m)^ +scope: (\[[^\]]*\])", read(self.root / "specs/SPEC-9.md")).group(1)
        self.assertEqual(scope.strip("[]").split(", ")[1:], ["tests/unit/test_login.py"])
        self.assertIn("left out tests/", out)
        self.assertIn("tests/unit/", out.split("left out tests/", 1)[1])

    def test_the_design_spec_is_the_light_variant_and_full_writes_every_section(self):
        self.new("spec", "SPEC-9", "--title", "Sign-in")
        self.new("design-spec", "login", "--spec", "SPEC-9")
        light = read(self.root / "specs/SPEC-9/design-spec-login.md")
        headings = [line[3:] for line in light.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["Flows", "Screen inventory", "Content and copy", "Test hooks"])
        self.assertIn("[spec]: ", light)
        self.new("design-spec", "signup", "--spec", "SPEC-9", "--full")
        self.assertIn("## Platforms", read(self.root / "specs/SPEC-9/design-spec-signup.md"))


if __name__ == "__main__":
    unittest.main()
