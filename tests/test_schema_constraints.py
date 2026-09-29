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

from aidd import evals, resources, schema


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
            "propertyNames",
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
        self.assertTrue(schema.validate("2026-02-29", "common.schema.json#/$defs/date"))

    def test_stale_standards_future_and_unparsable_dates(self):
        """evals.stale_standards treats future dates and unparsable dates as stale rather than crashing."""
        today = dt.date(2026, 9, 25)

        # Mock standards() with future date, unparsable date, and normal date
        mock_entries = [
            {"name": "future", "checked": "9999-12-31", "where": "domain test"},
            {"name": "invalid", "checked": "2026-02-30", "where": "domain test"},
            {"name": "fresh", "checked": "2026-09-01", "where": "domain test"},
        ]
        with patch.object(evals, "standards", return_value=mock_entries):
            stale = evals.stale_standards(today, max_days=365)
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
        """trace_id, assisted_by, head_sha, base_sha, decision must share common.schema.json definitions."""
        spec_sch = resources.load_json("spec.schema.json")
        cr_sch = resources.load_json("change-request.schema.json")
        rec_sch = resources.load_json("record.schema.json")
        ev_sch = resources.load_json("event.schema.json")
        ctx_sch = resources.load_json("context.schema.json")
        evi_sch = resources.load_json("evidence.schema.json")

        # trace_id
        self.assertIn("urn:aidd:1:common#/$defs/trace_id", spec_sch["properties"]["trace_id"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/trace_id", cr_sch["properties"]["trace_id"].get("$ref", ""))

        # assisted_by
        self.assertIn("urn:aidd:1:common#/$defs/assisted_by", spec_sch["properties"]["assisted_by"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/assisted_by", cr_sch["properties"]["assisted_by"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/assisted_by", rec_sch["properties"]["assisted_by"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/assisted_by", ev_sch["properties"]["assisted_by"].get("$ref", ""))

        # decision
        self.assertIn("urn:aidd:1:common#/$defs/decision", rec_sch["properties"]["decision"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/decision", ev_sch["properties"]["decision"].get("$ref", ""))

        # sha
        self.assertIn("urn:aidd:1:common#/$defs/sha", evi_sch["properties"]["head_sha"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/sha", evi_sch["properties"]["base_sha"].get("$ref", ""))
        self.assertIn("urn:aidd:1:common#/$defs/sha", ctx_sch["properties"]["base_sha"].get("$ref", ""))

        # trace_id constraint enforcement on change-request
        errs = schema.validate({"trace_id": "not valid!"}, "change-request.schema.json")
        self.assertTrue(errs, "change-request.schema.json accepted invalid trace_id")

        # head_sha uppercase rejection in context and evidence
        upper_sha = "A" * 40
        errs = helpers.validate_with(upper_sha, ctx_sch["properties"]["head_sha"])
        self.assertTrue(errs, "context.schema.json accepted uppercase head_sha")
        errs = helpers.validate_with(upper_sha, evi_sch["properties"]["head_sha"])
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

    def test_context_map_constraints(self):
        """context.schema.json must constrain head_tree, status_checks, and accept evidence invalid shape."""
        from helpers import example

        ctx = example("01-minor-docs")

        # head_tree invalid blob
        bad_ctx = dict(ctx, head_tree={"src/aidd/gates.py": "not-a-blob-id"})
        errs = schema.validate(bad_ctx, "context.schema.json")
        self.assertTrue(any("head_tree" in e for e in errs), f"context accepted non-hex blob id: {errs}")

        # status_checks invalid check state
        bad_checks = dict(ctx, status_checks={"ci/test": "banana"})
        errs = schema.validate(bad_checks, "context.schema.json")
        self.assertTrue(any("status_checks" in e for e in errs), f"context accepted banana check state: {errs}")

        # evidence holding {"invalid": "the artifact was corrupt"}
        valid_ev_ctx = dict(ctx, evidence={"invalid": "the artifact was corrupt"})
        errs = schema.validate(valid_ev_ctx, "context.schema.json")
        self.assertEqual(errs, [], f"context rejected invalid-shape evidence: {errs}")

    def test_context_shas_identities_and_times_are_typed(self):
        from helpers import example

        ctx = example("01-minor-docs")
        self.assertEqual(schema.validate(ctx, "context.schema.json"), [])
        review = {"user": "@lead", "state": "approved", "commit_sha": None, "submitted_at": "2026-09-23T09:00:00Z"}
        for label, bad in (
            ("commit sha", {"commits": [dict(ctx["commits"][0], sha="abc123")]}),
            ("review commit", {"reviews": [dict(review, commit_sha="HEAD")]}),
            ("review time", {"reviews": [dict(review, submitted_at="yesterday")]}),
            ("reviewer", {"reviews": [dict(review, user="two words")]}),
            ("pushed at", {"head_pushed_at": "2026-13-01T00:00:00Z"}),
            ("now", {"now": "noon"}),
        ):
            self.assertTrue(schema.validate(dict(ctx, **bad), "context.schema.json"), label)
        self.assertEqual(schema.validate(dict(ctx, reviews=[review]), "context.schema.json"), [])


class BundledDataTests(unittest.TestCase):
    """profiles.json and baseline.json are implicit inputs to every verifier; each part has a schema to meet."""

    def test_every_profiles_gates_validate_against_the_config_schema(self):
        data = resources.load_json("profiles.json")
        self.assertTrue(data.get("description"))
        self.assertEqual(sorted(data["order"]), sorted(data["profiles"]))
        for name, p in data["profiles"].items():
            gates = {k: v for k, v in p.items() if k != "description"}
            self.assertTrue(p.get("description"), name)
            self.assertEqual(schema.validate(gates, "config.schema.json#/properties/gates"), [], name)
            self.assertEqual(schema.validate(name, "common.schema.json#/$defs/profile"), [], name)

    def test_every_baseline_risk_rule_validates_against_the_config_schema(self):
        data = resources.load_json("baseline.json")
        self.assertTrue(data.get("description"))
        self.assertGreater(len(data["risk_rules"]), 5)
        for r in data["risk_rules"]:
            self.assertEqual(schema.validate(r, "config.schema.json#/properties/risk_rules/items"), [], r["name"])
        for p in data["protected_paths"]:
            self.assertEqual(schema.validate(p, "common.schema.json#/$defs/glob"), [], p)

    def test_the_bundled_baseline_already_holds_every_harness_path(self):
        raw = resources.load_json("baseline.json")
        self.assertEqual(raw["protected_paths"], resources.baseline()["protected_paths"], "run `aidd gen-docs`")

    def test_gen_docs_check_fails_when_baseline_json_lacks_a_harness_path(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from aidd import docs, harnesses

        text = (ROOT / "schemas" / "baseline.json").read_text(encoding="utf-8")
        self.assertEqual(resources.baseline_json_text(text), text)
        dropped = harnesses.protected_paths()[-1]
        data = json.loads(text)
        self.assertIn(dropped, data["protected_paths"])
        data["protected_paths"].remove(dropped)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "schemas").mkdir()
            target = Path(d) / "schemas" / "baseline.json"
            target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            with mock.patch.object(resources, "roles", return_value={"domains": [], "order": [], "roles": {}}):
                self.assertEqual(docs.gen_docs(Path(d), check=True), [target])
                self.assertNotIn(dropped, json.loads(target.read_text(encoding="utf-8"))["protected_paths"])
                docs.gen_docs(Path(d))
            self.assertIn(dropped, json.loads(target.read_text(encoding="utf-8"))["protected_paths"])


if __name__ == "__main__":
    unittest.main()
