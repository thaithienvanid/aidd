"""The schema layer cannot silently ignore a constraint.

Covers the validator's boundary: the assertion keywords it does not implement, `$`-anchored patterns
against a trailing newline, typed errors instead of crashes, `format` for dates, and the shared
`$defs` that stop one field name meaning two things in two documents.
"""

from __future__ import annotations

import datetime as dt
import json
import unittest
from unittest.mock import patch

import helpers
from helpers import ROOT

from aidd.knowledge import standards_evidence
from aidd.kernel import json_schema, resources


class AuditSchemaTests(unittest.TestCase):
    def test_unsupported_keywords_over_every_schema(self):
        """Every schemas/*.json must contain zero unsupported assertion keywords."""
        schema_dir = ROOT / "schemas"
        for p in sorted(schema_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            unsupported = helpers.unsupported_keywords(data)
            self.assertEqual(unsupported, set(), f"{p.name} contains unsupported keywords: {unsupported}")

    def test_unsupported_keywords_detects_unimplemented_assertions(self):
        """unsupported_keywords must detect draft 2020-12 assertion keywords not in aidd.schema."""
        for kw in (
            "patternProperties",
            "dependentRequired",
            "dependentSchemas",
            "prefixItems",
            "contains",
            "maxProperties",
            "minProperties",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
            "unevaluatedProperties",
            "unevaluatedItems",
        ):
            sch = {"type": "object", kw: {"foo": "bar"}}
            found = helpers.unsupported_keywords(sch)
            self.assertIn(kw, found, f"failed to detect {kw}")

    def test_pattern_newline_rejection(self):
        """Patterns with $ must not accept trailing newlines."""
        sha_schema = {"type": "string", "pattern": "^[0-9a-f]{40,64}$"}
        version_schema = {"type": "string", "pattern": r"^1\.[0-9]+\.[0-9]+$"}

        # Trailing newline rejected
        errs = helpers.validate_with("a" * 40 + "\n", sha_schema)
        self.assertTrue(errs, "pattern accepted 40 hex digits with trailing newline")

        errs = helpers.validate_with("1.0.0\n", version_schema)
        self.assertTrue(errs, "pattern accepted 1.0.0 with trailing newline")

        # Valid strings accepted
        self.assertEqual(helpers.validate_with("a" * 40, sha_schema), [])
        self.assertEqual(helpers.validate_with("1.0.0", version_schema), [])

    def test_date_format_validation_in_roles_schema(self):
        """Invalid calendar date such as 2026-02-30 must be rejected by roles.schema.json."""
        invalid_standard = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "name": "X",
            "checked": "2026-02-30",
        }
        # In roles.schema.json, standard object requires name and checked
        errs = helpers.validate_with(
            invalid_standard,
            resources.load_json("roles.schema.json")["$defs"]["standard"],
        )
        self.assertTrue(errs, "roles.schema.json accepted impossible date 2026-02-30")

    def test_the_date_pattern_alone_rejects_impossible_months_and_days(self):
        """A stock validator may not assert `format`, so the pattern itself rejects what it can."""
        pattern_only = {"type": "string", "pattern": resources.load_json("common.schema.json")["$defs"]["date"]["pattern"]}
        for ok in ("2026-01-31", "2026-02-28", "2024-02-29", "2026-04-30", "2026-12-31"):
            self.assertEqual(helpers.validate_with(ok, pattern_only), [], ok)
        for bad in ("2026-00-10", "2026-13-01", "2026-01-00", "2026-01-32", "2026-02-30", "2026-04-31", "2026-11-31", "26-01-01"):
            self.assertTrue(helpers.validate_with(bad, pattern_only), bad)
        # A February 29 outside a leap year passes the pattern; `format: date`, which aidd asserts, rejects it.
        self.assertEqual(helpers.validate_with("2026-02-29", pattern_only), [])
        self.assertTrue(json_schema.validate("2026-02-29", "common.schema.json#/$defs/date"))

    def test_stale_standards_future_and_unparsable_dates(self):
        """standards_evidence.stale_standards treats future dates and unparsable dates as stale rather than crashing."""
        today = dt.date(2026, 9, 25)

        # Mock standards() with future date, unparsable date, and normal date
        mock_entries = [
            {"name": "future", "checked": "9999-12-31", "where": "domain test"},
            {"name": "invalid", "checked": "2026-02-30", "where": "domain test"},
            {"name": "fresh", "checked": "2026-09-01", "where": "domain test"},
        ]
        with patch.object(standards_evidence, "dated_entries", return_value=mock_entries):
            stale = standards_evidence.stale_standards(today, max_days=365)
            stale_names = {s["name"] for s in stale}
            self.assertIn("future", stale_names, "future date was treated as fresh instead of stale")
            self.assertIn("invalid", stale_names, "unparsable date was not treated as stale")
            self.assertNotIn("fresh", stale_names, "fresh date was incorrectly marked stale")

    def test_schema_error_recovery_instead_of_crashes(self):
        """Typed errors must be reported rather than unhandled KeyError, RecursionError, or PatternError."""
        # 1. Unknown type reports typed error rather than KeyError
        errs = helpers.validate_with("value", {"type": "foo"})
        self.assertTrue(errs)
        self.assertIn("unknown type 'foo'", errs[0])

        # 2. $ref cycle reports $ref cycle rather than RecursionError
        errs = helpers.validate_with("value", {"$ref": "#"})
        self.assertTrue(errs)
        self.assertIn("$ref cycle", errs[0])

        # 3. Non-dict schema reports error rather than AttributeError
        errs = helpers.validate_with("value", [])
        self.assertTrue(errs)
        self.assertIn("schema must be an object or a boolean", errs[0])

        # 4. Invalid pattern reports error rather than PatternError
        errs = helpers.validate_with("value", {"pattern": "("})
        self.assertTrue(errs)
        self.assertIn("invalid pattern", errs[0])

    def test_shared_definitions_across_schemas(self):
        """trace_id, assisted_by, head_sha, and base_sha must share common.schema.json definitions."""
        spec_sch = resources.load_json("spec.schema.json")
        evi_sch = resources.load_json("evidence.schema.json")

        self.assertIn("urn:aidd:1:common#/$defs/trace_id", spec_sch["properties"]["trace_id"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/assisted_by", spec_sch["properties"]["assisted_by"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/sha", evi_sch["properties"]["head_sha"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/sha", evi_sch["properties"]["base_sha"].get("$ref", ""))

        # trace_id constraint enforcement
        errs = helpers.validate_with("not valid!", spec_sch["properties"]["trace_id"])
        self.assertTrue(errs, "spec.schema.json accepted invalid trace_id")

        # head_sha uppercase rejection in evidence
        errs = helpers.validate_with("A" * 40, evi_sch["properties"]["head_sha"])
        self.assertTrue(errs, "evidence.schema.json accepted uppercase head_sha")

    def test_epic_and_initiative_use_goal(self):
        """Epic and Initiative schemas must use 'goal' (string) instead of 'outcome'."""
        epic_sch = resources.load_json("epic.schema.json")
        init_sch = resources.load_json("initiative.schema.json")

        self.assertIn("goal", epic_sch["required"])
        self.assertNotIn("outcome", epic_sch["required"])
        self.assertIn("goal", epic_sch["properties"])
        self.assertNotIn("outcome", epic_sch["properties"])

        self.assertIn("goal", init_sch["required"])
        self.assertNotIn("outcome", init_sch["required"])
        self.assertIn("goal", init_sch["properties"])
        self.assertNotIn("outcome", init_sch["properties"])


class BundledDataTests(unittest.TestCase):
    """profiles.json and risks.json are implicit inputs to every command; each part meets its schema."""

    def test_every_profiles_rules_validate_against_the_risks_schema(self):
        data = resources.load_json("profiles.json")
        self.assertTrue(data.get("description"))
        self.assertEqual(sorted(data["order"]), sorted(data["profiles"]))
        for name, p in data["profiles"].items():
            self.assertTrue(p.get("description"), name)
            self.assertTrue(set(p["spec_approval_routes"]) <= {"minor", "normal", "major", "emergency"}, name)
            self.assertEqual(json_schema.validate(p.get("rules", []), "risks.schema.json#/$defs/rules"), [], name)
            self.assertEqual(json_schema.validate(name, "common.schema.json#/$defs/profile"), [], name)

    def test_the_built_in_risk_rules_validate_against_the_risks_schema(self):
        data = resources.load_json("risks.json")
        self.assertTrue(data.get("description"))
        self.assertGreater(len(data["rules"]), 5)
        self.assertEqual(json_schema.validate(data, "risks.schema.json"), [])
        for name, area in data["areas"].items():
            for glob in area["paths"]:
                self.assertEqual(json_schema.validate(glob, "common.schema.json#/$defs/glob"), [], f"{name}: {glob}")


if __name__ == "__main__":
    unittest.main()
