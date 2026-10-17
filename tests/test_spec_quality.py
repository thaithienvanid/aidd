"""Spec quality: what `aidd validate`, `aidd context`, and the team's commands ask of a Spec and an Initiative."""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT, git

from aidd.autopilot import context_pack
from aidd.workitems import validation
from aidd.workitems import spec_warnings
from aidd.workitems import authoring
from aidd import config
from aidd.workitems import derived_status, spec_file
from aidd.kernel import documents, json_schema, resources

SKILL = ROOT / ".agents" / "skills" / "aidd"
TEAM = ROOT / "plugins" / "aidd-team"


def spec(body: str) -> str:
    """A minimal normal Spec that validates, with `body` after its front matter."""
    return (
        '---\naidd_version: "1.0.0"\nkind: spec\nid: S\ntitle: t\nowner_team: core\ntype: feat\n'
        "route: normal\nconfidence: high\nassisted_by: []\nrollback: Revert.\n"
        "risk:\n  summary: s\n  dimensions: []\n  reversible: true\n"
        "tasks:\n  - id: S-T1\n    title: t\n    scope: [src/a.py]\n"
        "tests:\n  files: [tests/t.py]\n  commands:\n    - name: a\n      command: [pytest]\n      new_behavior: true\n"
        f"---\n\n## Intent\n\nProblem: checkout times out.\n\n## Context\n\nc\n{body}"
    )


def findings(text: str, name: str = "S.md") -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_text(text, encoding="utf-8")
        return validation.validate_file(p)


class VagueWordTests(unittest.TestCase):
    """an Acceptance or non-functional line with a vague word and no number, unit, threshold, or test reference warns."""

    def vague(self, body: str) -> list[str]:
        out = findings(spec(body))
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [], "a vague word is a warning, never an error")
        return [w for w in out if "measurable target" in w]

    def test_a_vague_acceptance_line_warns_and_names_the_word(self):
        out = self.vague("\n## Acceptance\n\n- A1 Search is fast for every caller.\n")
        self.assertEqual(len(out), 1, out)
        self.assertIn("A1", out[0])
        self.assertIn("'fast'", out[0])

    def test_a_number_a_unit_or_a_test_reference_makes_it_measurable(self):
        for line in (
            "- A1 Search is fast: p95 under 300 ms.",
            "- A1 Search is fast enough for `test_search_budget`.",
            "- A1 Search is fast, as [the SLO](docs/slo.md) defines it.",
            "- A1 Search is fast, as tests/perf/search_test.py checks.",
        ):
            self.assertEqual(self.vague(f"\n## Acceptance\n\n{line}\n"), [], line)

    def test_the_item_id_is_not_a_number(self):
        self.assertTrue(self.vague("\n## Acceptance\n\n| A12 | the page is intuitive |\n"))

    def test_gherkin_steps_are_checked_and_scenario_names_are_not(self):
        body = "\n## Acceptance\n\n```gherkin\nScenario: A1 Fast search\n  Given a caller\n  Then results appear within 200 ms\n\n"
        body += "Scenario: A2 Easy checkout\n  When the buyer pays\n  Then the flow feels intuitive and seamless\n```\n"
        out = self.vague(body)
        self.assertEqual(len(out), 1, out)
        self.assertIn("A2", out[0])
        self.assertIn("'intuitive'", out[0])
        self.assertIn("'seamless'", out[0])

    def test_whole_words_only(self):
        for line in ("- A1 a fast-forward merge keeps the history", "- A1 the breakfast menu loads", "- A1 a securely-signed token"):
            self.assertEqual(self.vague(f"\n## Acceptance\n\n{line}\n"), [], line)

    def test_a_non_functional_section_is_checked_too(self):
        out = self.vague("\n## Acceptance\n\n- A1 returns 429 on request 61\n\n## Non-functional requirements\n\n- The API is scalable and reliable.\n")
        self.assertEqual(len(out), 1, out)
        self.assertIn("Non-functional", out[0])
        self.assertIn("'scalable'", out[0])
        self.assertIn("'reliable'", out[0])

    def test_other_sections_are_not_checked(self):
        self.assertEqual(self.vague("\n## Design\n\nA simple, fast, robust design.\n\n## Acceptance\n\n- A1 returns 429\n"), [])

    def test_the_word_list_is_data_short_and_conservative(self):
        data = resources.load_json("vague-words.json")
        words = data["words"]
        self.assertTrue(data["description"])
        self.assertLessEqual(len(words), 40)
        self.assertEqual(len(words), len(set(words)))
        for w in ("fast", "intuitive", "user-friendly", "user friendly", "securely", "performant", "gracefully", "adequate", "adequately", "as needed"):
            self.assertIn(w, words)
        self.assertNotIn("clean", words, "a clean working tree is a precise term in a repository's own Specs")
        for w in ("secure", "slow", "simple"):
            self.assertNotIn(w, words, f"{w!r} names a real attribute, precondition, or feature")
        self.assertEqual(words, sorted(words))

    def test_attribute_precondition_and_feature_words_stay_quiet(self):
        for line in ("- A1 the secure cookie flag is set", "- A1 Given a slow network, the page shows a retry button", "- A1 the simple search box shows"):
            self.assertEqual(self.vague(f"\n## Acceptance\n\n{line}\n"), [], line)

    def test_the_added_words_warn(self):
        for line in ("- A1 the token is stored securely", "- A1 errors are handled gracefully", "- A1 the form is user friendly", "- A1 logging is adequate"):
            self.assertEqual(len(self.vague(f"\n## Acceptance\n\n{line}\n")), 1, line)

    def test_numbering_and_ids_are_not_a_target(self):
        for line in ("AC-1 the API is fast", "1. The API is fast", "- A1 the API is fast (see SPEC-4)", "- the API is fast, as EPIC-2 asks"):
            self.assertEqual(len(self.vague(f"\n## Acceptance\n\n{line}\n")), 1, line)
        for line in ("1. The API is fast: p95 under 300 ms.", "AC-1 the API is fast: 200 requests/s"):
            self.assertEqual(self.vague(f"\n## Acceptance\n\n{line}\n"), [], line)

    def test_the_templates_and_the_worked_example_stay_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            for route in ("normal", "major"):
                p = authoring.new_object(
                    Path(d), authoring.NewObject(kind="spec", id=f"X-{route}", title="Example", route=route, owner_team="core", today=dt.date(2026, 10, 9))
                )
                self.assertFalse([w for w in validation.validate_file(p) if "measurable target" in w], route)
        example = (SKILL / "references" / "example.md").read_text(encoding="utf-8")
        self.assertEqual(spec_warnings.vague_lines(example), [])


class ExemplarTests(helpers.RepoTemplateCase):
    """`docs.exemplars` names the project's best Specs; `aidd context` lists them for the Specify step."""

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

    def exemplars(self, **kw) -> list[dict]:
        pack = context_pack.build_context_pack(self.root, "SPEC-1", **kw)
        self.assertEqual(json_schema.validate(pack, "context-pack.schema.json"), [])
        return [i for i in pack["items"] if i["kind"] == "exemplar"]

    def test_the_config_takes_a_list_of_spec_paths(self):
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertEqual(cfg.get("docs", "exemplars"), ["specs/SPEC-12.md"])
        for bad in ('"specs/SPEC-12.md"', '["/etc/passwd.md"]', '["../x.md"]', '[""]', '["specs/*.md"]'):
            text = (self.root / config.CONFIG_PATH).read_text(encoding="utf-8").replace("[specs/SPEC-12.md]", bad)
            self.assertIn(bad, text)
            with self.assertRaises((config.ConfigError, documents.DocumentError), msg=bad):
                config.load_text(text, where="config.yaml")

    def test_the_specify_step_lists_them_with_the_reason(self):
        for kw in ({"step": "spec.draft"}, {"step": "lane.spec"}, {}, {"role": "architect"}, {"role": "tester"}):
            got = self.exemplars(**kw)
            self.assertEqual([i["path"] for i in got], ["specs/SPEC-12.md"], kw)
            self.assertEqual(got[0]["reason"], "an exemplar a person chose")
            self.assertGreater(got[0]["tokens"], 0)

    def test_other_steps_and_builders_do_not_read_them(self):
        for kw in ({"step": "spec.in_progress"}, {"role": "developer"}, {"role": "verifier"}):
            self.assertEqual(self.exemplars(**kw), [], kw)

    def test_validate_warns_on_an_exemplar_that_does_not_exist(self):
        cfg = self.root / config.CONFIG_PATH
        self.assertFalse([w for w in validation.validate_file(cfg) if "exemplar" in w])
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("SPEC-12.md", "SPEC-404.md"), encoding="utf-8")
        out = validation.validate_file(cfg)
        found = [w for w in out if "exemplar" in w]
        self.assertEqual(len(found), 1, out)
        self.assertTrue(found[0].startswith("warning: "))
        self.assertIn("specs/SPEC-404.md", found[0])
        self.assertIn("missing", context_pack.context_pack_markdown(context_pack.build_context_pack(self.root, "SPEC-1", step="spec.draft")))


class ExemplarWordingTests(unittest.TestCase):
    def test_the_specify_command_and_the_spec_reference_say_to_read_them(self):
        specify = (TEAM / "commands" / "specify.md").read_text(encoding="utf-8")
        self.assertIn("exemplars", specify)
        self.assertIn("aidd context", specify)
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


INITIATIVE = (
    '---\naidd_version: "1.0.0"\nkind: initiative\nid: INIT-1\ntitle: t\ngoal: "checkout conversion from 2% to 3% by 2026-12-31"\n'
    "owner_team: core\n{extra}---\n\n## Brief\n\n- Problem: {problem}\n- Appetite: two weeks.\n\n### Journey\n\n"
    "Persona or segment: buyers. Scenario: checkout. Evidence: {evidence}\n"
)


def initiative(problem: str = "(assumed) buyers give up at checkout.", evidence: str = "(assumed)", extra: str = "") -> str:
    return INITIATIVE.format(problem=problem, evidence=evidence, extra=extra)


class InitiativeEvidenceTests(unittest.TestCase):
    """an Initiative's Problem and its journey's Evidence cite a source, or say they are assumed."""

    def unsourced(self, text: str) -> list[str]:
        out = findings(text, "INIT-1.md")
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [])
        return [w for w in out if "cites no source" in w]

    def test_a_problem_with_no_source_warns(self):
        out = self.unsourced(initiative(problem="buyers give up at checkout."))
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
            self.assertEqual(self.unsourced(initiative(problem=problem)), [], problem)

    def test_the_problem_may_wrap_onto_the_next_line(self):
        self.assertEqual(self.unsourced(initiative(problem="buyers give up at checkout,\n  as the 2026-09 funnel shows.")), [])

    def test_journey_evidence_with_no_source_warns(self):
        out = self.unsourced(initiative(evidence="interviews with buyers."))
        self.assertEqual(len(out), 1, out)
        self.assertIn("Evidence", out[0])
        self.assertEqual(self.unsourced(initiative(evidence="five interviews, 2026-09-12 to 2026-09-19.")), [])
        table = initiative() + "\n| Stage | Browse | Pay |\n| --- | --- | --- |\n| Evidence | session recordings | (assumed) |\n"
        out = self.unsourced(table)
        self.assertEqual(len(out), 1, out)

    def test_the_template_stays_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            p = authoring.new_object(
                Path(d), authoring.NewObject(kind="initiative", id="INIT-9", title="Example", owner_team="core", today=dt.date(2026, 10, 9))
            )
            self.assertEqual([w for w in validation.validate_file(p) if "cites no source" in w], [])


GO = 'go_no_go:\n  decision: {decision}\n  by: "{by}"\n  decided_on: "2026-10-01"\n'


class InitiativeGoNoGoTests(unittest.TestCase):
    """an optional go/no-go on an Initiative, the proposal's shape, a person's decision."""

    def test_the_schema_takes_the_proposal_shape(self):
        data, _, errs = spec_file.load_object(initiative(extra=GO.format(decision="go", by="@lead")), "INIT-1.md")
        self.assertEqual(errs, [])
        self.assertEqual(data["go_no_go"]["decision"], "go")
        for bad in (GO.format(decision="maybe", by="@lead"), "go_no_go:\n  decision: go\n"):
            data = documents.parse_yaml(initiative(extra=bad).split("---")[1], "INIT-1.md")
            self.assertTrue(json_schema.validate(data, "initiative.schema.json"), bad)
        self.assertEqual(
            resources.load_json("initiative.schema.json")["properties"]["go_no_go"]["$ref"],
            "urn:aidd:1:proposal#/properties/go_no_go",
        )

    def test_no_go_derives_cancelled(self):
        data = documents.parse_yaml(initiative(extra=GO.format(decision="no_go", by="@lead")).split("---")[1], "INIT-1.md")
        self.assertEqual(derived_status.container_status(data, ["in_progress"]), "cancelled")
        data["go_no_go"]["decision"] = "go"
        self.assertEqual(derived_status.container_status(data, ["in_progress"]), "active")
        self.assertEqual(derived_status.container_status({"kind": "initiative"}, []), "draft")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_an_agent_never_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_repo(Path(d) / "r", branch=None)
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs" / "INIT-1.md").write_text(initiative(extra=GO.format(decision="go", by="agent:claude-code")), encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertTrue(any("go_no_go.by agent:claude-code" in e for e in errors), errors)
            (root / "specs" / "INIT-1.md").write_text(initiative(extra=GO.format(decision="go", by="@lead")), encoding="utf-8")
            errors, _ = validation.check_repo(root)
            self.assertFalse(any("go_no_go" in e for e in errors), errors)

    def test_containers_reference_says_so(self):
        text = (SKILL / "references" / "containers.md").read_text(encoding="utf-8")
        self.assertIn("| `go_no_go` |", text)
        self.assertIn("(assumed)", text)


if __name__ == "__main__":
    unittest.main()
