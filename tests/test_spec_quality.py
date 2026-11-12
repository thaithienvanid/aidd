"""Spec quality: what `aidd validate` and the team's commands ask of a Spec and an Intent."""

import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import AGENT_APPROVERS, PEOPLE_APPROVERS, ROOT, git

from aidd.workitems import validation
from aidd.workitems import spec_warnings
from aidd.workitems import authoring
from aidd import config
from aidd.workitems import spec_file
from aidd.kernel import documents, json_schema, resources

SKILL = ROOT / ".agents" / "skills" / "aidd"
TEAM = ROOT / "plugins" / "aidd-team"


def spec(body: str) -> str:
    """A minimal normal Spec that validates, with `body` after its front matter."""
    return (
        "---\ntype: spec\nid: S\ntitle: t\nchange_type: feat\n"
        "route: normal\nconfidence: high\nrollback: Revert.\n"
        "risk:\n  summary: s\n  dimensions: []\n  irreversible: false\n"
        "tasks:\n  - id: S-T1\n    title: t\n    scope: [src/a.py]\n"
        "tests:\n  files: [tests/t.py]\n  commands:\n    - name: a\n      command: [pytest]\n      new_behavior: true\n"
        f"---\n\n## Request\n\nProblem: checkout times out.\n\n## Context\n\nc\n{body}"
    )


def findings(text: str, name: str = "S.md") -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_text(text, encoding="utf-8")
        return validation.validate_file(p)


class PerformanceBudgetTests(unittest.TestCase):
    """risk naming `performance` warns until an Acceptance item states a budget and a test command covers it."""

    def budget(self, body: str, dims: str = "[performance]", covers: str = "") -> list[str]:
        text = spec(body).replace("  dimensions: []", f"  dimensions: {dims}").replace("      new_behavior: true\n", f"      new_behavior: true\n{covers}")
        out = findings(text)
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [], "a budget is a warning, never an error")
        return [w for w in out if "performance budget" in w or "states a budget" in w]

    def test_no_budget_warns(self):
        out = self.budget("\n## Acceptance\n\n- A1: orders list for the buyer.\n")
        self.assertEqual(len(out), 1, out)
        self.assertIn("states a budget", out[0])

    def test_a_percentile_without_a_number_is_no_budget(self):
        for line in ("- A1: p95 stays low under load.", "- A1: LCP stays good.", "- A1: the cls helper returns 2 rows.", "- A1: p95 of `cache_v2` is fine."):
            out = self.budget(f"\n## Acceptance\n\n{line}\n", covers="      covers: [A1]\n")
            self.assertEqual(len(out), 1, line)
            self.assertIn("states a budget", out[0], line)

    def test_a_decimal_percentile_counts(self):
        self.assertEqual(self.budget("\n## Acceptance\n\n- A1: the 99.9th percentile under 2 s at 20 requests a second.\n", covers="      covers: [A1]\n"), [])

    def test_an_uncovered_budget_warns_and_a_covered_one_does_not(self):
        body = "\n## Acceptance\n\n- A1: orders list.\n- A2: p95 of GET /orders under 200 ms at 50 requests a second on staging.\n"
        out = self.budget(body)
        self.assertEqual(len(out), 1, out)
        self.assertIn("A2", out[0])
        self.assertEqual(self.budget(body, covers="      covers: [A1, A2]\n"), [])
        once = [
            w
            for w in findings(
                spec(body)
                .replace("  dimensions: []", "  dimensions: [performance]")
                .replace("      new_behavior: true\n", "      new_behavior: true\n      covers: [A1]\n")
            )
            if "A2" in w
        ]
        self.assertEqual(len(once), 1, "coverage_warnings names it once, with no second budget warning")

    def test_a_web_vital_counts_as_a_budget(self):
        self.assertEqual(self.budget("\n## Acceptance\n\n- A1: LCP at or under 2.5 s at p75 on the product page.\n", covers="      covers: [A1]\n"), [])

    def test_without_the_dimension_it_stays_quiet(self):
        self.assertEqual(self.budget("\n## Acceptance\n\n- A1: orders list.\n", dims="[]"), [])


class OpenQuestionTests(unittest.TestCase):
    """Spec Kit's checklist passes only once no `[NEEDS CLARIFICATION]` is left; aidd names each open question a Spec
    still lists once it asks for approval. The schema already refuses a high confidence with questions listed."""

    @staticmethod
    def with_(status: str, confidence: str = "medium") -> str:
        head = f'confidence: {confidence}\nopen_questions:\n  - "Which currency does a refund use?"\nstatus: {status}\n'
        return spec("\n## Acceptance\n\n- A1: a refund of 10 EUR returns 10 EUR.\n").replace("confidence: high\n", head)

    def test_each_open_question_warns_while_the_spec_asks_for_approval(self):
        for status, warns in (("draft", False), ("ready", True), ("approved", False), ("done", False)):
            with self.subTest(status=status):
                found = [f for f in findings(self.with_(status)) if "open question" in f]
                self.assertEqual(len(found), int(warns), found)
                if warns:
                    self.assertIn("Which currency does a refund use?", found[0])
                    self.assertTrue(found[0].startswith("warning: "))


class ApprovedByTests(unittest.TestCase):
    """`approved_by`, like its `Approved-by` trailer, holds only who said yes: `Name <email>`, or an Approver's
    `@handle`, `@org/team`, or `email:<address>`. Another value, or an agent, is a warning, never an error."""

    CASES = [
        ("Van Hoang <van@example.com>", None),
        ("José García <jose@example.com>", None),
        ("Nguyễn Văn An <an@example.com>", None),
        ("Zoë O'Brien-Smith <zoe+aidd@example.com>", None),
        ("Devin Lee <devin@example.com>", None),  # a part of a name is never an agent's name
        ("Jos\u00e9 Garc\u00eda <jose@example.com>", None),  # an accent on a Latin letter is a name
        ("<noreply@anthropic.com>", "agent"),
        ("Patsy Cline <patsy@example.com>", None),
        ("Junie Moon <junie@example.com>", None),
        ("@maya", None),
        ("@org/leads", None),
        ("email:maya@example.com", None),
        ("maya", "form"),
        ("@maya.", "form"),
        ("acme:@alice", "form"),
        ("van@example.com", "form"),
        ("Van Hoang <van@example.com> (head f8ff731)", "form"),
        ("Van, as the owner's delegate (record of 2026-11-07) <van@example.com>", "form"),
        ("A" * 81 + " <a@example.com>", "form"),
        ("the person in the chat, as the owner's delegate (record of 2026-11-07, pr.merge, head f8ff731)", "form"),
        ("Maya <maya@example.com>, Pat <pat@example.com>", "form"),
        ("@claude", "agent"),
        ("Claude <noreply@anthropic.com>", "agent"),
        ("github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>", "agent"),
        ("Pat Lee <49699333+dependabot[bot]@users.noreply.github.com>", "agent"),
    ]

    @staticmethod
    def with_(by: str, revised_by: str = "@maya") -> str:
        head = f'status: approved\napproved_by: {json.dumps(by)}\napproved_at: "2026-11-07T10:00:00Z"\n'
        head += f"revisions:\n  - why: w\n    by: {json.dumps(revised_by)}\n"
        return spec("\n## Acceptance\n\n- A1: a refund of 10 EUR returns 10 EUR.\n").replace("rollback: Revert.\n", head + "rollback: Revert.\n")

    def test_every_place_that_asks_who_is_an_agent_gives_one_answer_for_every_form(self):
        """`approved_by_kind` is the one rule. The Spec's `approved_by` and `revisions[].by` (validate), an Intent's agreement
        (status and validate), a waiver, and `--approvers` all agree with it, for every agent form any check once refused and
        for people whose names carry accents or an agent's word."""
        import datetime as dt

        from aidd.cli import arguments
        from aidd.config import project
        from aidd.workitems import intent_checks, work_list

        head = 'aidd_version: "1.0.0"\nprofile: team\nowners: {approvers: ["@org/leads"]}\n'
        rule = 'project:\n  rules:\n    - id: r1\n      requirement_level: must\n      statement: s\n      why: w\n      owner: "@a"\n'
        for is_agent, values in ((True, AGENT_APPROVERS), (False, PEOPLE_APPROVERS)):
            for value in values:
                with self.subTest(value=value, agent=is_agent):
                    self.assertEqual(config.approver_is_agent(value), is_agent)
                    self.assertEqual(config.approved_by_kind(value) == "agent", is_agent)
                    self.assertEqual(config.approved_by_problem(value) is not None, is_agent)
                    agreed = {"agreed_by": value, "agreed_at": "2026-11-10T09:12:00Z"}
                    self.assertEqual(work_list.person_agreed(agreed), not is_agent, "status")
                    self.assertEqual(any(not f.startswith("warning") for f in intent_checks.agreement_problems("I.md", {"type": "intent", **agreed})), is_agent)
                    for field in (self.with_(value), self.with_("@maya", value)):
                        self.assertEqual(any("names an agent or a bot" in f for f in findings(field)), is_agent, "validate")
                    waiver = f'  waivers:\n    - rule: r1\n      reason: r\n      granted_by: {json.dumps(value)}\n      until: "2027-01-01"\n'
                    errors, _ = project.project_findings(config.load_text(head + rule + waiver), dt.date(2026, 9, 30))
                    self.assertEqual(any("a person approves a waiver" in e and "@handle" in e for e in errors), is_agent, "waiver")
                    try:
                        arguments.approvers([value])
                        refused = False
                    except ValueError as exc:
                        refused = "@handle" in str(exc)
                    if is_agent or value.startswith(("@", "email:")):
                        self.assertEqual(refused, is_agent, "--approvers")

    def test_a_name_wholly_in_another_script_that_only_looks_like_an_agents_reads_as_a_person(self):
        """The known limit (SECURITY.md): the agent-identity check is a tripwire for honest mistakes and plain agent names. A
        name of Cyrillic letters only, `\u0441\u043e\u0501\u0435\u0445` for `codex`, is a person's name in that script, and an
        agent that wants to pass could write a real person's name as well."""
        self.assertIsNone(config.approved_by_kind("\u0441\u043e\u0501\u0435\u0445 <x@example.com>"))

    def test_each_value_is_a_person_in_the_form_or_names_what_is_wrong(self):
        for value, kind in self.CASES:
            with self.subTest(value=value):
                self.assertEqual(config.approved_by_kind(value), kind)
                self.assertEqual(config.approved_by_problem(value) is None, kind is None)

    def test_validate_warns_once_per_field_and_never_fails(self):
        quiet = findings(self.with_("@maya"))
        for by, revised_by in (("maya", "@maya"), ("@maya", "maya")):
            with self.subTest(by=by, revised_by=revised_by):
                found = findings(self.with_(by, revised_by))
                self.assertEqual([f for f in found if not f.startswith("warning: ")], [])
                self.assertEqual(len(found), len(quiet) + 1, found)

    def test_a_page_for_a_client_names_the_person_and_copies_no_address(self):
        for value, shown in (("Zoë O'Brien-Smith <zoe@example.com>", "Zoë O'Brien-Smith"), ("email:maya@example.com", "maya"), ("@maya", "@maya")):
            with self.subTest(value=value):
                self.assertEqual(config.display_name(value), shown)


GLOSSARY = """# Glossary: Shop

| Term | Meaning | Avoid | Owning module |
| --- | --- | --- | --- |
| Customer | A person who pays. | user, `client` | billing |
| Order | What a customer pays for. | none | |
| Seller | Who lists an item. | vendor; merchant account, customer, a person who sells things here | |
| Workspace | A team's own space. | Workspace, user | |
| TODO | TODO: what it means | TODO: the words | |
"""


class GlossaryAvoidTests(unittest.TestCase):
    """a Spec's Goals, Acceptance, or Design line that uses a word from the glossary's Avoid column warns; Intent never does."""

    def glossary(self, body: str, glossary: str | None = GLOSSARY, docs: str = "docs", config: str = "") -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            if config:
                (root / ".aidd").mkdir()
                (root / ".aidd" / "config.yaml").write_text(config, encoding="utf-8")
            if glossary is not None:
                (root / docs).mkdir(parents=True)
                (root / docs / "GLOSSARY.md").write_text(glossary, encoding="utf-8")
            (root / "specs").mkdir()
            p = root / "specs" / "S.md"
            p.write_text(spec(body), encoding="utf-8")
            out = validation.validate_file(p)
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [], "an Avoid word is a warning, never an error")
        return [w for w in out if "lists under Avoid" in w]

    def test_an_avoid_word_warns_and_names_the_term_and_the_glossary(self):
        out = self.glossary("\n## Acceptance\n\n- A1 The user downloads the order as CSV.\n")
        self.assertEqual(len(out), 1, out)
        self.assertIn("Acceptance A1 uses 'user' (the glossary's term is 'Customer')", out[0])
        self.assertIn("docs/GLOSSARY.md", out[0])
        self.assertIn("write the glossary's term", out[0])

    def test_goals_and_design_are_checked_and_intent_is_not(self):
        body = "\n## Goals\n\n- Every client sees the total.\n\n## Acceptance\n\n- A1 returns 429\n\n## Design\n\nThe vendor list moves.\n"
        self.assertEqual(len(self.glossary(body)), 2)
        body = "\n## Request\n\nProblem: the user cannot export.\n\n## Non-goals\n\n- No user import.\n\n## Acceptance\n\n- A1 returns 429\n"
        self.assertEqual(self.glossary(body), [])

    def test_whole_words_phrases_and_any_case(self):
        out = self.glossary("\n## Acceptance\n\n- A1 A Merchant  Account is listed, and a USER sees it.\n")
        self.assertEqual(len(out), 1, out)
        self.assertIn("'merchant account' (the glossary's term is 'Seller')", out[0])
        self.assertIn("'user'", out[0])
        for line in ("- A1 The users page loads.", "- A1 The user-id is kept.", "- A1 Each customer pays."):
            self.assertEqual(self.glossary(f"\n## Acceptance\n\n{line}\n"), [], line)

    def test_code_is_not_prose(self):
        body = "\n## Acceptance\n\n- A1 returns 429\n\n## Design\n\nThe `user` table keeps its name.\n\n```sql\nSELECT * FROM user;\n```\n"
        self.assertEqual(self.glossary(body), [])

    def test_placeholders_none_explanations_and_terms_are_not_avoid_words(self):
        avoid = spec_warnings.glossary_avoid(GLOSSARY)
        self.assertEqual(avoid, {"user": "Customer", "client": "Customer", "vendor": "Seller", "merchant account": "Seller"})

    def test_no_glossary_or_no_avoid_column_says_nothing(self):
        self.assertEqual(self.glossary("\n## Acceptance\n\n- A1 The user downloads it.\n", glossary=None), [])
        self.assertEqual(
            self.glossary("\n## Acceptance\n\n- A1 The user downloads it.\n", glossary="| Term | Meaning |\n| --- | --- |\n| Customer | pays |\n"), []
        )
        self.assertEqual(spec_warnings.glossary_lines(spec("\n## Acceptance\n\n- A1 The user.\n"), {}), [])

    def test_the_glossary_is_read_from_the_configured_docs_folder(self):
        out = self.glossary(
            "\n## Acceptance\n\n- A1 The user downloads it.\n", docs="handbook", config='aidd_version: "1.0.0"\nprofile: team\ndocs:\n  dir: handbook\n'
        )
        self.assertEqual(len(out), 1, out)
        self.assertIn("handbook/GLOSSARY.md", out[0])

    def test_the_template_holds_only_words_and_stays_quiet(self):
        template = (SKILL / "assets" / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("list only the words", template)
        self.assertEqual(spec_warnings.glossary_avoid(template), {})


class DecisionTableTests(unittest.TestCase):
    """a business rule with three or more conditions is a decision table with a hit policy, one Acceptance id per row."""

    REF = TEAM / "skills" / "product-discovery" / "references" / "job-stories-and-ears.md"

    def test_the_reference_holds_rules_hit_policies_gaps_and_example_mapping(self):
        ref = self.REF.read_text(encoding="utf-8")
        self.assertIn("## Rules and decision tables", ref)
        for words in (
            "`Rule:`",
            "three or more conditions",
            "**Unique** (U)",
            "**First** (F)",
            "gap",
            "overlap",
            "DMN 1.6",
            "Example mapping (Matt Wynne, Cucumber, 2015)",
        ):
            self.assertIn(words, ref, words)
        table = documents.raw_section(ref, "Rules and decision tables")
        ids = [ln.split("|")[1].strip() for ln in table.splitlines() if ln.startswith("| A")]
        self.assertEqual(ids, ["A1", "A2", "A3", "A4"], "each row of the example has its own Acceptance id")

    def test_the_spec_template_and_the_tester_point_at_it(self):
        self.assertIn('"Rules and decision tables"', (SKILL / "assets" / "spec.md").read_text(encoding="utf-8"))
        self.assertIn("decision table", (TEAM / "skills" / "product-discovery" / "SKILL.md").read_text(encoding="utf-8"))

    def test_dmn_is_a_dated_registry_standard_of_the_practice(self):
        entry = resources.load_json("industry-standards.json")["dmn-decision-tables"]
        self.assertEqual((entry["edition"], entry["source"]), ("DMN 1.6", "https://www.omg.org/spec/DMN/1.6"))
        self.assertIn("dmn-decision-tables", resources.load_json("roles.json")["practices"]["product-discovery"]["standards"])


class ExemplarTests(helpers.RepoTemplateCase):
    """`docs.exemplars` names the project's best Specs, which the Specify step reads first."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        helpers.make_repo(root, branch="feat", approvers=["@lead"])
        cfg = root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\ndocs:\n  exemplars: [specs/SPEC-12.md]\n", encoding="utf-8")
        (root / "specs").mkdir(exist_ok=True)
        (root / "specs" / "SPEC-12.md").write_text(spec("\n## Acceptance\n\n- A1 returns 429\n").replace("id: S", "id: SPEC-12"), encoding="utf-8")
        (root / "specs" / "SPEC-1.md").write_text(spec("\n## Acceptance\n\n- A1 returns 429\n").replace("id: S", "id: SPEC-1"), encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "specs")

    def test_the_config_takes_a_list_of_spec_paths(self):
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertEqual(cfg.get("docs", "exemplars"), ["specs/SPEC-12.md"])
        for bad in ('"specs/SPEC-12.md"', '["/etc/passwd.md"]', '["../x.md"]', '[""]', '["specs/*.md"]'):
            text = (self.root / config.CONFIG_PATH).read_text(encoding="utf-8").replace("[specs/SPEC-12.md]", bad)
            self.assertIn(bad, text)
            with self.assertRaises((config.ConfigError, documents.DocumentError), msg=bad):
                config.load_text(text, where="config.yaml")


class ExemplarWordingTests(unittest.TestCase):
    def test_the_specify_command_and_the_spec_reference_say_to_read_them(self):
        specify = (TEAM / "commands" / "specify.md").read_text(encoding="utf-8")
        self.assertIn("exemplars", specify)
        self.assertIn("read them first", specify)
        ref = (SKILL / "references" / "spec.md").read_text(encoding="utf-8")
        self.assertIn("`docs.exemplars`", ref)

    def test_no_preloaded_text_mentions_them(self):
        """Zero preloaded bytes: no agent file and no preloaded skill carries the exemplar rule."""
        preloaded = [SKILL / "SKILL.md", *sorted((TEAM / "agents").glob("*.md")), *sorted((TEAM / "skills").glob("*/SKILL.md"))]
        for p in preloaded:
            self.assertNotIn("exemplar", p.read_text(encoding="utf-8").lower(), p)


class AmbiguityPassTests(unittest.TestCase):
    """before the first edit, list what the Spec leaves unclear, and settle it in the Spec, never only in chat."""

    def test_implement_lists_what_is_unclear_before_the_first_edit(self):
        text = (TEAM / "commands" / "implement.md").read_text(encoding="utf-8")
        for must in ("before the first edit", "unclear", "returns to Specify", "assumption", "Verify report", "only in chat"):
            self.assertIn(must, text, must)
        self.assertLess(text.index("unclear"), text.index("Take the Tasks in `depends_on` order"))


INTENT = (
    '---\ntype: intent\nid: INTENT-1\ntitle: t\ngoal: "checkout conversion from 2% to 3% by 2026-12-31"\n'
    "{extra}---\n\n## {section}\n\n- Problem: {problem}\n- Appetite: two weeks.\n\n### Journey\n\n"
    "Persona or segment: buyers. Scenario: checkout. Evidence: {evidence}\n"
)

# The Intent's evidence lives in `## Problem`, the template's section.
SECTIONS = ("Problem",)


def intent(problem: str = "(assumed) buyers give up at checkout.", evidence: str = "(assumed)", extra: str = "", section: str = "Problem") -> str:
    return INTENT.format(problem=problem, evidence=evidence, extra=extra, section=section)


class IntentEvidenceTests(unittest.TestCase):
    """an Intent's Problem line and its journey's Evidence cite a source, or say they are assumed."""

    def unsourced(self, text: str) -> list[str]:
        out = findings(text, "INTENT-1.md")
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [])
        return [w for w in out if "cites no source" in w]

    def test_a_problem_with_no_source_warns(self):
        for section in SECTIONS:
            with self.subTest(section=section):
                out = self.unsourced(intent(problem="buyers give up at checkout.", section=section))
                self.assertEqual(len(out), 1, out)
                self.assertIn("Problem", out[0])
                self.assertIn("(assumed)", out[0])

    def test_a_source_or_an_assumed_mark_is_enough(self):
        for problem in (
            "buyers give up at checkout (assumed).",
            "buyers give up at checkout, per [the funnel](https://example.com/funnel).",
            "buyers give up at checkout: docs/research/interviews.md.",
            'buyers give up at checkout: "I could not find the pay button" (support ticket).',
            "buyers give up at checkout; support call notes, 2026-09-30.",
        ):
            self.assertEqual(self.unsourced(intent(problem=problem)), [], problem)

    def test_the_problem_may_wrap_onto_the_next_line(self):
        self.assertEqual(self.unsourced(intent(problem="buyers give up at checkout,\n  as the 2026-09 funnel shows.")), [])

    def test_journey_evidence_with_no_source_warns(self):
        for section in SECTIONS:
            with self.subTest(section=section):
                out = self.unsourced(intent(evidence="interviews with buyers.", section=section))
                self.assertEqual(len(out), 1, out)
                self.assertIn("Evidence", out[0])
                self.assertEqual(self.unsourced(intent(evidence="five interviews, 2026-09-12 to 2026-09-19.", section=section)), [])
        table = intent() + "\n| Stage | Browse | Pay |\n| --- | --- | --- |\n| Evidence | session recordings | (assumed) |\n"
        out = self.unsourced(table)
        self.assertEqual(len(out), 1, out)

    def test_the_template_stays_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            p = authoring.new_object(Path(d), authoring.NewObject(item_type="intent", id="INTENT-9", title="Example", today=dt.date(2026, 10, 9)))
            self.assertEqual([w for w in validation.validate_file(p) if "cites no source" in w], [])


GO = 'go_no_go:\n  decision: {decision}\n  by: "{by}"\n  decided_on: "2026-10-01"\n'


class IntentGoNoGoTests(unittest.TestCase):
    """an optional go/no-go on an Intent, the proposal's shape, a person's decision."""

    def test_the_schema_takes_the_proposal_shape(self):
        data, _, errs = spec_file.load_object(intent(extra=GO.format(decision="go", by="@lead")), "INTENT-1.md")
        self.assertEqual(errs, [])
        self.assertEqual(data["go_no_go"]["decision"], "go")
        for bad in (GO.format(decision="maybe", by="@lead"), "go_no_go:\n  decision: go\n"):
            data = documents.parse_yaml(intent(extra=bad).split("---")[1], "INTENT-1.md")
            self.assertTrue(json_schema.validate(data, "intent.schema.json"), bad)
        self.assertEqual(
            resources.load_json("intent.schema.json")["properties"]["go_no_go"]["$ref"],
            "urn:aidd:1:proposal#/properties/go_no_go",
        )

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_an_agent_never_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_repo(Path(d) / "r", branch=None)
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs" / "INTENT-1.md").write_text(intent(extra=GO.format(decision="go", by="agent:claude-code")), encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertTrue(any("go_no_go.by agent:claude-code" in e for e in errors), errors)
            (root / "specs" / "INTENT-1.md").write_text(intent(extra=GO.format(decision="go", by="@lead")), encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertFalse(any("go_no_go" in e for e in errors), errors)

    def test_intents_reference_says_so(self):
        text = (SKILL / "references" / "intents.md").read_text(encoding="utf-8")
        self.assertIn("`go_no_go`", text)
        self.assertIn("(assumed)", text)


if __name__ == "__main__":
    unittest.main()
