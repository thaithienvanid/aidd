"""`aidd validate` prints an example beside pattern and format failures."""

from __future__ import annotations

import unittest

from helpers import adopted_repo, run_cli

from aidd.kernel import json_schema


class ValidateExamplesTests(unittest.TestCase):
    def test_pattern_and_format_failures_print_schema_examples(self):
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^SPEC-[1-9][0-9]*$", "examples": ["SPEC-1"]},
                "when": {"type": "string", "format": "date", "examples": ["2026-04-01"]},
            },
        }
        errs: list[str] = []
        json_schema._check({"id": "bad id", "when": "2025-02-29"}, schema, "$", "", errs)
        self.assertEqual(len(errs), 2)
        self.assertIn('for example, "SPEC-1"', errs[0])
        self.assertIn('for example, "2026-04-01"', errs[1])

    def test_aidd_validate_prints_item_specific_id_examples_and_date_example(self):
        with adopted_repo() as repo:
            (repo / "product" / "intents").mkdir(parents=True, exist_ok=True)
            (repo / "product" / "intents" / "INTENT-1.md").write_text(
                '---\ntype: intent\nid: bad id\ntitle: T\nstatus: open\nstart_on: "2025-02-29"\n---\n\n# Intent\n',
                encoding="utf-8",
            )
            code, out = run_cli("validate", "product/intents/INTENT-1.md")
            self.assertNotEqual(code, 0, out)
            self.assertIn('for example, "INTENT-1"', out)
            self.assertNotIn('for example, "SPEC-1"', out)
            self.assertIn('for example, "2026-04-01"', out)

            (repo / "specs").mkdir(exist_ok=True)
            (repo / "specs" / "SPEC-1.md").write_text(
                "---\ntype: spec\nid: bad id\nparent: bad parent\ntitle: T\n---\n\n# Spec\n",
                encoding="utf-8",
            )
            code_spec, out_spec = run_cli("validate", "specs/SPEC-1.md")
            self.assertNotEqual(code_spec, 0, out_spec)
            self.assertIn('$.id: "bad id" does not match', out_spec)
            self.assertIn('for example, "SPEC-1"', out_spec)
            parent_line = next(line for line in out_spec.splitlines() if "$.parent:" in line)
            self.assertNotIn("for example,", parent_line)

            (repo / "proposals").mkdir(exist_ok=True)
            (repo / "proposals" / "PROP-1.md").write_text(
                "---\ntype: proposal\nid: bad id\ntitle: T\n---\n\n# Proposal\n",
                encoding="utf-8",
            )
            code_prop, out_prop = run_cli("validate", "proposals/PROP-1.md")
            self.assertNotEqual(code_prop, 0, out_prop)
            self.assertIn('for example, "PROP-1"', out_prop)


if __name__ == "__main__":
    unittest.main()
