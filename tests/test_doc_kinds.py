"""Twenty-one kinds of document, each with one home.

`aidd new` writes the twenty-one kinds below, and nothing else: the cut kinds live as sections of the documents that already
held them (flows and a usability test in the design spec, a component in DESIGN.md, a brief and a journey in the
Initiative, the support terms in the contract, a change order beside the contract in the proposal's folder, a decision
card as an exploration with no visuals). The data map, the vendor register, and the glossary are the repository's own, at fixed paths;
the contract and its change orders are the engagement's, in the proposal's folder. An exploration's front matter has a
schema, `aidd new exploration` writes it, and `aidd explore` only renders.
"""

import contextlib
import datetime as dt
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, make_repo, run_cli

from aidd import explore, model, repo, resources, schema

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
KINDS = {
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
    def test_twenty_one_kinds_and_no_other(self):
        self.assertEqual(set(repo.DOC_KINDS_NEW), KINDS)
        self.assertEqual(len(repo.DOC_KINDS_NEW), 21)
        for kind in CUT:
            with self.subTest(kind=kind), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run_cli("new", kind, "x")

    def test_what_a_spec_links(self):
        self.assertEqual(model.DOC_KINDS, (*LINKED, "data-map", "vendors", "other"))
        spec_kinds = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["kind"]["enum"]
        self.assertEqual(tuple(spec_kinds), model.DOC_KINDS)
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"]
        self.assertEqual(set(required), set(model.DOC_KINDS) - {"other"})

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

    def test_the_initiative_holds_the_brief_and_the_journey(self):
        brief = section(read(ASSETS / "initiative.md"), "## Brief")
        for word in ("Problem", "Appetite", "Solution sketch", "Rabbit holes", "No-gos", "Success metric", "### Journey", "Service blueprint"):
            self.assertIn(word, brief, word)

    def test_the_contract_holds_the_support_terms_and_points_at_the_proposal(self):
        text = read(ASSETS / "contract.md")
        support = section(text, "## Support and service levels")
        for word in ("S1", "S2", "S3", "S4", "Escalation", "Maintenance", "Response", "Resolution"):
            self.assertIn(word, support, word)
        for heading in ("## Milestones", "## Assumptions and exclusions"):
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
        data, _ = model.split_front_matter(read(self.root / "specs" / "SPEC-220.md"))
        return {d["path"]: d for d in data.get("docs") or []}

    def test_ui_is_the_design_spec_and_prototype_is_its_html(self):
        self.new("design-spec", "cart", "--spec", "SPEC-220")
        self.assertIn("# Design spec", read(self.root / "docs/specs/SPEC-220/design-spec-cart.md"))
        self.new("design-spec", "cart", "--spec", "SPEC-220", "--prototype")
        self.assertIn("<html", read(self.root / "docs/design/SPEC-220/prototype.html").lower())
        links = self.links()
        self.assertEqual({links[p]["kind"] for p in ("docs/specs/SPEC-220/design-spec-cart.md", "docs/design/SPEC-220/prototype.html")}, {"design-spec"})

    def test_authz_is_the_authorization_matrix(self):
        self.new("authz", "admin", "--spec", "SPEC-220")
        self.assertIn("SPEC-220", read(self.root / "docs/specs/SPEC-220/authz-admin.md"))
        self.assertEqual(self.links()["docs/specs/SPEC-220/authz-admin.md"]["kind"], "authz")

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
        _, warnings = repo.check_repo(self.root, today=dt.date(2026, 9, 30))
        self.assertTrue(any("Mailer Inc" in w and "docs/vendors.md" in w for w in warnings), warnings)

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

    def test_the_initiative_is_the_solo_founders_brief(self):
        self.new("initiative", "INIT-1", "--title", "Pet sitter MVP")
        self.assertIn("## Brief", read(self.root / "specs/INIT-1.md"))

    def test_new_exploration_writes_it_and_explore_only_renders(self):
        out = self.new("exploration", "docs/design/SPEC-9", "--title", "Where does the refund button go?", "--timebox", "30 minutes")
        self.assertIn("exploration.md", out)
        text = read(self.root / "docs/design/SPEC-9/exploration.md")
        self.assertIn("Where does the refund button go?", text)
        self.assertIn("30 minutes", text)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_cli("explore", "docs/design/SPEC-10", "--question", "x")
        code, out = run_cli("explore", "docs/design/SPEC-10")
        self.assertNotEqual(code, 0)
        self.assertIn("aidd new exploration", out)
        code, out = run_cli("explore", "docs/design/SPEC-9")
        self.assertEqual(code, 0, out)


class ExplorationSchema(unittest.TestCase):
    def test_the_template_front_matter_validates(self):
        text = repo.fill(read(ASSETS / "exploration.md"), title="Q", question="Q", owner="product-designer", timebox="45 minutes", today="2026-09-30")
        data, _ = model.split_front_matter(text)
        self.assertEqual(schema.validate(data, "exploration.schema.json"), [])
        self.assertTrue(schema.validate(dict(data, status="maybe"), "exploration.schema.json"))
        self.assertTrue(schema.validate(dict(data, owner="nobody at all"), "exploration.schema.json"))

    def test_a_bad_front_matter_is_refused_on_render(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "exploration.md").write_text('+++\nkind = "exploration"\nquestion = "Q"\nowner = "architect"\nstatus = "maybe"\n+++\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "status"):
                explore.comparison_page(folder)

    def test_a_decision_card_is_an_exploration_without_visuals(self):
        text = read(ASSETS / "exploration.md")
        self.assertIn("decision card", text.lower())
        self.assertIn("exploration", read(ROOT / ".agents" / "skills" / "aidd" / "references" / "handoff.md"))


if __name__ == "__main__":
    unittest.main()
