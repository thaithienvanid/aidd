"""The error catalog, docs/ERRORS.md, and the codes Troubleshooting cites.

- every finding code, step code, guard reason code, and exit code has exactly one anchor on the page, and no two
  anchors or headings share a name;
- each source of meanings covers its codes exactly: the guard's GUARD_REASONS its REASON_CODES, the step meanings the
  step-code contract, and the exit codes the gate's exit map;
- each finding code or step code that Troubleshooting cites in backticks exists, and so does each guard reason code
  its guard section names.
"""

import re
import unittest

from helpers import ROOT

from aidd import autopilot, gate
from aidd.cli import arguments
from aidd.docsgen import error_catalog, generate
from aidd.guard import denial_log, denial_reasons
from aidd.kernel import text as kernel_text

ERRORS = ROOT / "docs" / "ERRORS.md"
TROUBLESHOOTING = ROOT / "docs" / "TROUBLESHOOTING.md"
FINDING_CODES = {code for r in gate.RULES for code in r.codes}
GUARD_CODES = {code for _, code in denial_log.REASON_CODES} | {"other"}


def anchors(text: str) -> list[str]:
    return re.findall(r'<a id="([^"]+)"></a>', text)


class CatalogTests(unittest.TestCase):
    def test_every_code_has_exactly_one_anchor(self):
        found = anchors(ERRORS.read_text(encoding="utf-8"))
        want = (
            [kernel_text.code_anchor(c) for c in FINDING_CODES]
            + [error_catalog.STEP_PREFIX + kernel_text.code_anchor(c) for c in autopilot.contract()]
            + [error_catalog.GUARD_PREFIX + kernel_text.code_anchor(c) for c in GUARD_CODES]
            + [f"{error_catalog.EXIT_PREFIX}{n}" for n in range(4)]
        )
        self.assertEqual(sorted(found), sorted(want))

    def test_no_two_anchors_or_headings_share_a_name(self):
        text = ERRORS.read_text(encoding="utf-8")
        names = anchors(text) + [generate._slug(h) for h in re.findall(r"^#{2,3} +(.+?) *$", text, re.M)]
        self.assertEqual(sorted({n for n in names if names.count(n) > 1}), [])

    def test_a_code_anchor_is_the_code_in_lowercase_with_hyphens(self):
        self.assertEqual(kernel_text.code_anchor("scope.outside"), "scope-outside")
        self.assertEqual(kernel_text.code_anchor("change_request.several_specs"), "change-request-several-specs")
        self.assertEqual(kernel_text.code_anchor("policy:<rule>"), "policy-rule")

    def test_the_guard_meanings_cover_its_reason_codes_exactly(self):
        self.assertEqual(sorted(denial_reasons.GUARD_REASONS), sorted(GUARD_CODES))

    def test_the_step_meanings_cover_the_step_code_contract_exactly(self):
        self.assertEqual(sorted(autopilot.step_meanings()), sorted(autopilot.contract()))

    def test_the_gate_exit_codes_match_its_exit_map(self):
        command, means = arguments.EXIT_CODES[0]
        self.assertIn("`gate`", command)
        self.assertEqual({word: means[n] for word, n in arguments.EXIT.items()}, {word: word for word in arguments.EXIT})


class TroubleshootingTests(unittest.TestCase):
    def test_each_finding_or_step_code_it_cites_exists(self):
        text = TROUBLESHOOTING.read_text(encoding="utf-8")
        rules = {r.name for r in gate.RULES}
        cited = {c for c in re.findall(r"`([a-z_]+\.[a-z_]+)`", text) if c.split(".")[0] in rules}
        self.assertTrue({"scope.outside", "change_request.several_specs", "config.newer_version"} <= cited)
        self.assertEqual(sorted(cited - FINDING_CODES - set(autopilot.contract())), [])

    def test_each_guard_reason_code_its_guard_section_names_exists(self):
        text = TROUBLESHOOTING.read_text(encoding="utf-8")
        section = text.split("## The guard denied a step", 1)[1].split("\n## ", 1)[0]
        cited = {c for heading in re.findall(r"^### .+$", section, re.M) for c in re.findall(r"`([a-z_]+)`", heading)}
        self.assertTrue({"role_area", "out_of_scope", "shell_opaque", "frozen_file", "decision_typed"} <= cited)
        self.assertEqual(sorted(cited - GUARD_CODES), [])


if __name__ == "__main__":
    unittest.main()
