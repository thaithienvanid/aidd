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

    def test_a_persons_identity_moves_an_entry_to_the_reviewed_tier(self):
        self.assertEqual(knowledge.trust_tier({"checked_by": "@maintainer"}), knowledge.TIER_PERSON)
        self.assertEqual(knowledge.trust_tier({"checked_by": "email:me@example.com"}), knowledge.TIER_PERSON)
        self.assertEqual(knowledge.trust_tier({"checked_by": "agent:claude-code/claude-opus-5-5"}), knowledge.TIER_AGENT)


if __name__ == "__main__":
    unittest.main()
