"""The Spec's Intent and Policy conflicts sections, and a Task's risk and proof."""

import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import model, repo, schema

TEMPLATE = ROOT / ".agents" / "skills" / "aidd" / "assets" / "spec.md"
TASK = {"id": "S-T1", "title": "slice", "scope": ["src/a.py"]}


def spec(route: str = "normal", dims: str = "", body: str = "") -> str:
    """A minimal Spec that validates, with the given route, risk dimensions, and body."""
    obs = '\n[observe]\nwindow = "1h"\nsignals = "dash"\nrollback_trigger = "5xx"\n' if route == "major" else ""
    return (
        '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "S"\ntitle = "t"\nowner_team = "core"\ntype = "feat"\n'
        f'route = "{route}"\nconfidence = "high"\nassisted_by = []\nrollback = "Revert."\n'
        f'[risk]\nsummary = "s"\ndimensions = [{dims}]\nreversible = true\n'
        '[[tasks]]\nid = "S-T1"\ntitle = "t"\nscope = ["src/a.py"]\n'
        '[tests]\nfiles = ["tests/t.py"]\n[[tests.commands]]\nname = "a"\ncommand = ["pytest"]\nnew_behavior = true\n'
        f"{obs}+++\n\n## Context\n\nc\n\n## Acceptance\n\na\n{body}"
    )


class TaskRiskAndProofTests(unittest.TestCase):
    def _validate(self, task: dict) -> list[str]:
        data = model.parse_toml(spec().split("+++")[1], "spec")
        data["tasks"] = [task]
        return schema.validate(data, "spec.schema.json")

    def test_the_schema_accepts_risk_and_proof(self):
        self.assertEqual(self._validate({**TASK, "risk": "the cache key changes; a migration test guards it", "proof": "tests.commands a"}), [])

    def test_they_are_optional_but_never_empty(self):
        self.assertEqual(self._validate(TASK), [])
        self.assertTrue(self._validate({**TASK, "risk": ""}))
        self.assertTrue(self._validate({**TASK, "proof": ["a"]}))

    def test_they_are_approved_content_so_the_hash_covers_them(self):
        self.assertEqual(model.VOLATILE_TASK_KEYS, {"retry_count", "done"})  # bookkeeping only: risk and proof are approved content
        base = spec()
        with_risk = base.replace('scope = ["src/a.py"]\n', 'scope = ["src/a.py"]\nrisk = "r"\nproof = "p"\n', 1)
        other = with_risk.replace('proof = "p"', 'proof = "q"')
        hashes = {model.spec_hash(t, {}) for t in (base, with_risk, other)}
        self.assertEqual(len(hashes), 3)

    def test_the_template_shows_both_and_validates(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^risk = "')
        self.assertRegex(text, r'(?m)^proof = "')
        with tempfile.TemporaryDirectory() as d:
            # The full template: `--full`, or any major Spec. The short one keeps a Task to id, title, and scope.
            for route in ("normal", "major"):
                p = repo.new_object(
                    Path(d), kind="spec", id=f"X-{route}", title="Example", route=route, owner_team="core", today=dt.date(2026, 9, 28), full=True
                )
                data, _, errs = model.load_object(p.read_text(encoding="utf-8"), str(p))
                self.assertEqual(errs, [])
                self.assertTrue({"risk", "proof"} <= set(data["tasks"][0]))


class IntentAndPolicyConflictTests(unittest.TestCase):
    def warnings(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S.md"
            p.write_text(text, encoding="utf-8")
            out = repo.validate_file(p)
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [])
        return out

    def has(self, out: list[str], heading: str) -> bool:
        return any(f"'## {heading}'" in w for w in out)

    def test_a_normal_spec_without_intent_warns(self):
        self.assertTrue(self.has(self.warnings(spec()), "Intent"))
        self.assertTrue(self.has(self.warnings(spec(body="\n## Intent\n\n<!-- guidance only -->\n")), "Intent"))
        self.assertFalse(self.has(self.warnings(spec(body="\n## Intent\n\nProblem: checkout times out.\n")), "Intent"))

    def test_policy_conflicts_on_major(self):
        self.assertTrue(self.has(self.warnings(spec("major")), "Policy conflicts"))
        self.assertFalse(self.has(self.warnings(spec("major", body="\n## Policy conflicts\n\nnone\n")), "Policy conflicts"))

    def test_policy_conflicts_when_more_than_one_specialist_pool(self):
        self.assertFalse(self.has(self.warnings(spec()), "Policy conflicts"))
        self.assertFalse(self.has(self.warnings(spec(dims='"availability"')), "Policy conflicts"))
        self.assertTrue(self.has(self.warnings(spec(dims='"security", "privacy"')), "Policy conflicts"))

    def test_warnings_never_errors_and_emergency_is_exempt(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertLess(text.index("## Intent"), text.index("## Problem"))
        self.assertIn("## Policy conflicts", text)
        with tempfile.TemporaryDirectory() as d:
            p = repo.new_object(Path(d), kind="spec", id="INC-1", title="x", route="emergency", owner_team="core", today=dt.date(2026, 9, 28))
            self.assertFalse(any(re.search(r"'## (Intent|Policy conflicts)'", e) for e in repo.validate_file(p)))
            p = repo.new_object(Path(d), kind="spec", id="M-1", title="x", route="major", owner_team="core", today=dt.date(2026, 9, 28))
            out = repo.validate_file(p)
            self.assertTrue(self.has(out, "Intent") and self.has(out, "Policy conflicts"))
            self.assertFalse(any("Intent" in e and not e.startswith("warning: ") for e in out))


class AcceptanceCoverageTests(unittest.TestCase):
    """`[[tests.commands]] covers` maps a command to the Acceptance items it proves; `aidd validate` shows the gaps."""

    ACCEPTANCE = (
        "\n```gherkin\nScenario: A1 requests within the limit complete\n  Given a caller\n  Then it completes\n\n"
        "Scenario: A2 the 61st request is refused\n  Then it returns 429\n```\n\n| Acceptance | Proven by |\n| --- | --- |\n| A3 | a |\n"
    )

    def warnings(self, covers: str | None, acceptance: str = ACCEPTANCE) -> list[str]:
        text = spec(body="\n## Intent\n\nProblem: slow.\n")
        text = text.replace("\n## Acceptance\n\na\n", f"\n## Acceptance\n{acceptance}")
        if covers is not None:
            text = text.replace("new_behavior = true\n", f"new_behavior = true\ncovers = {covers}\n", 1)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "S.md"
            p.write_text(text, encoding="utf-8")
            out = repo.validate_file(p)
        self.assertEqual([e for e in out if not e.startswith("warning: ")], [])
        return [w for w in out if "covers" in w or "covered" in w]

    def test_ids_are_read_from_scenarios_and_table_rows(self):
        self.assertEqual(repo.acceptance_ids("## Acceptance\n" + self.ACCEPTANCE), ["A1", "A2", "A3"])
        self.assertEqual(repo.acceptance_ids("## Acceptance\n\n- **A1** a list item\n- A12: another\n\nAn A4 mid-sentence is no id.\n"), ["A1", "A12"])

    def test_an_uncovered_item_warns_once_any_command_declares_covers(self):
        out = self.warnings('["A1", "A2"]')
        self.assertEqual(len(out), 1, out)
        self.assertIn("Acceptance item A3 is covered by no test command", out[0])
        self.assertEqual(self.warnings('["A1", "A2", "A3"]'), [])

    def test_a_covered_id_the_acceptance_lacks_warns(self):
        out = self.warnings('["A1", "A2", "A3", "A9"]')
        self.assertEqual(len(out), 1, out)
        self.assertIn("covers A9", out[0])
        out = self.warnings('["A1"]', acceptance="\nGiven a caller\nThen it completes\n")
        self.assertTrue(any("names no item ids" in w for w in out), out)

    def test_without_covers_nothing_warns(self):
        """Backward compatible: a Spec written before `covers` existed stays quiet."""
        self.assertEqual(self.warnings(None), [])

    def test_the_schema_takes_only_acceptance_ids(self):
        data = model.parse_toml(spec().split("+++")[1], "spec")
        command = data["tests"]["commands"][0]
        for good in (["A1"], ["A1", "A20"]):
            self.assertEqual(schema.validate({**data, "tests": {**data["tests"], "commands": [{**command, "covers": good}]}}, "spec.schema.json"), [], good)
        for bad in ([], ["a1"], ["A0"], ["B1"], ["A1", "A1"], "A1"):
            self.assertTrue(schema.validate({**data, "tests": {**data["tests"], "commands": [{**command, "covers": bad}]}}, "spec.schema.json"), bad)

    def test_the_template_and_the_example_use_ids_and_covers(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(template, r'(?m)^covers = \["A1"\]')
        self.assertIn("Scenario: A1", template)
        example = (ROOT / ".agents" / "skills" / "aidd" / "references" / "example.md").read_text(encoding="utf-8")
        self.assertIn('covers = ["A1", "A2"]', example)
        self.assertEqual(repo.acceptance_ids(example), ["A1", "A2"])


if __name__ == "__main__":
    unittest.main()
