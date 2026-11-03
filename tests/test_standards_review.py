"""A person's review of the registry: `aidd eval standards` says how much of it a person has reviewed, and
`--unreviewed` lists what waits, the laws and regulations first, with how a person records a review."""

from __future__ import annotations

import unittest

from helpers import run_cli

from aidd import knowledge


class StandardsReviewTests(unittest.TestCase):
    def test_the_check_names_the_registrys_trust(self):
        _, out = run_cli("eval", "standards")
        self.assertRegex(out, r"Registry trust: \d+ checked by an agent, \d+ reviewed by a person")

    def test_unreviewed_lists_the_laws_first_and_how_to_record_a_review(self):
        code, out = run_cli("eval", "standards", "--unreviewed")
        self.assertEqual(code, 0, out)
        laws, rest = out.index("Laws and regulations"), out.index("Everything else")
        self.assertLess(laws, rest)
        self.assertIn("- gdpr:", out[laws:rest])
        self.assertIn("set its `checked_by` to your identity", out)

    def test_unreviewed_names_the_file_that_records_each_entry(self):
        _, out = run_cli("eval", "standards", "--unreviewed")
        self.assertRegex(out, r"- gdpr: .*; role \S+.*; in schemas/industry-standards\.json")
        self.assertIn("practice naming; in plugins/aidd-team/skills/naming/SKILL.md (`metadata.checked`)", out)

    def test_unreviewed_lists_each_standard_once_with_every_place_that_applies_it(self):
        _, out = run_cli("eval", "standards", "--unreviewed")
        lines = [line for line in out.splitlines() if line.startswith("- ")]
        self.assertEqual(sum(line.startswith("- gdpr:") for line in lines), 1, out)
        (gdpr,) = [line for line in lines if line.startswith("- gdpr:")]
        self.assertIn("role security-engineer, role compliance-analyst", gdpr)
        self.assertEqual(sum(line.startswith("- GitHub MCP;") for line in lines), 1, out)

    def test_a_reviewed_entry_gets_its_own_instruction(self):
        # The schema allows a `reviewed` entry no `checked_by`, so the listing never tells a person to set one there.
        _, out = run_cli("eval", "standards", "--unreviewed")
        self.assertIn("A registry standard dated `reviewed` has no versioned source to check", out)
        self.assertIn("set its `reviewed` to today", out)
        self.assertRegex(out, r"\d+ registry standards dated `reviewed`, the extensions, and the practice skills have no field")

    def test_the_counts_name_each_kind(self):
        entries = knowledge.dated_entries()
        ids = len({s["id"] for s in entries if s.get("id")})
        extensions = sum(1 for s in entries if not s.get("id") and s["where"].startswith("extension "))
        skills = len(entries) - extensions - sum(1 for s in entries if s.get("id"))
        _, out = run_cli("eval", "standards")
        self.assertIn(f"{len(entries)} dated applications: {ids} registry standards applied ", out)
        self.assertIn(f"times, {extensions} extensions, and {skills} practice skills", out)

    def test_a_persons_identity_moves_an_entry_to_the_reviewed_tier(self):
        self.assertEqual(knowledge.trust_tier({"checked_by": "@maintainer"}), knowledge.TIER_PERSON)
        self.assertEqual(knowledge.trust_tier({"checked_by": "email:me@example.com"}), knowledge.TIER_PERSON)
        self.assertEqual(knowledge.trust_tier({"checked_by": "agent:claude-code/claude-opus-5-5"}), knowledge.TIER_AGENT)


if __name__ == "__main__":
    unittest.main()
