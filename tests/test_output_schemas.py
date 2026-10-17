"""The JSON output contracts: what `aidd metrics`, `aidd owners`, `aidd gate --paths`, and `aidd list` print with --json, and the
gate event, validated as printed against schemas/metrics.schema.json, owners.schema.json, forecast.schema.json,
list.schema.json, and event.schema.json."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT, adopted_repo, decide, example, run_cli

from aidd.cli.commands import understand
from aidd.cli import arguments
from aidd.tracking import metrics
from aidd.gate import decision_report
from aidd.setup import adoption
from aidd.kernel import json_schema


def ev(change, ts, decision="pass", **kw):
    return {
        "repo": "o/r",
        "change": change,
        "ts": ts,
        "head_sha": f"{int(change):040x}",
        "decision": decision,
        "pending_rules": [],
        "failed_rules": [],
        "route": "normal",
        "assisted_by": ["claude-code/claude-opus-5-5"],
        "type": "deps",
        "author": "renovate[bot]",
    } | kw


EVENTS = [
    ev(
        "1",
        "2026-09-01T09:00:00Z",
        "pending",
        pending_rules=["tests", "spec_approval"],
        opened_at="2026-09-01T08:50:00Z",
        head_pushed_at="2026-09-01T08:55:00Z",
    ),
    ev("1", "2026-09-01T09:30:00Z", "pending", pending_rules=["merge_approval"], spec_hash="x", spec_id="SPEC-1", failed_rules=[]),
    ev("1", "2026-09-01T10:00:00Z", spec_hash="x", spec_id="SPEC-1"),
    *[ev(str(i), f"2026-09-02T09:{i:02d}:00Z") for i in range(2, 28)],
]


class OutputSchemaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = self.root / "events.jsonl"
        self.events.write_text("".join(json.dumps(e) + "\n" for e in EVENTS), encoding="utf-8")
        specs = self.root / "specs"
        specs.mkdir()

    def json_of(self, *argv, cwd=None):
        with contextlib.chdir(cwd or self.root):
            code, out = run_cli(*argv)
        self.assertIn(code, (0, 1), out)
        return json.loads(out)

    def valid(self, data, ref):
        self.assertEqual(json_schema.validate(data, ref), [], json.dumps(data)[:400])

    def test_every_metrics_json_output_matches_its_schema(self):
        ledger = self.root / "cost.jsonl"
        ledger.write_text(json.dumps({"ts": "2026-09-01T09:00:00Z", "amount": 1.5, "currency": "USD", "spec": "SPEC-1", "agent": "a"}) + "\n", encoding="utf-8")
        e = str(self.events)
        summary = self.json_of("metrics", e, "--json", "--specs", "specs", "--cost", str(ledger))
        self.assertEqual(summary["schema_version"], metrics.METRICS_SCHEMA_VERSION)
        self.assertIn("cost", summary)
        self.assertIn("released_specs", summary)
        self.valid(summary, "metrics.schema.json#/$defs/summary")
        self.valid(self.json_of("metrics", e, "--json"), "metrics.schema.json#/$defs/summary")
        grouped = self.json_of("metrics", e, "--json", "--by", "author")
        self.assertEqual((set(grouped), grouped["schema_version"], grouped["by"]), ({"schema_version", "by", "groups"}, "1", "author"))
        self.valid(grouped, "metrics.schema.json#/$defs/grouped")
        tables = []
        for flag, ref in (("--dora", "dora"), ("--autonomy", "autonomy")):
            table = self.json_of("metrics", e, "--json", flag)
            self.assertEqual((set(table), table["schema_version"]), ({"schema_version", "rows"}, "1"), flag)
            self.assertTrue(table["rows"])
            self.valid(table, f"metrics.schema.json#/$defs/{ref}")
            self.assertTrue(json_schema.validate(table["rows"], f"metrics.schema.json#/$defs/{ref}"), "a bare array is no longer the shape")
            tables.append(table)
        proposals = self.json_of("metrics", e, "--json", "--autonomy", "--suggest-standard-changes")
        self.assertTrue(proposals["proposals"])
        self.valid(proposals, "metrics.schema.json#/$defs/proposals")
        guard = self.root / "guard.jsonl"
        guard.write_text(json.dumps({"decision": "deny", "reason": "out_of_scope", "role": "developer", "tool": "Edit"}) + "\n", encoding="utf-8")
        self.valid(self.json_of("metrics", "--guard", str(guard), "--json"), "metrics.schema.json#/$defs/guard")
        # And each one against the schema's root, which accepts any of them.
        for data in (summary, proposals, grouped, *tables):
            self.valid(data, "metrics.schema.json")

    def test_the_summary_schema_names_every_key_and_catches_drift(self):
        s = metrics.summarize_events(EVENTS)
        self.valid(s, "metrics.schema.json#/$defs/summary")
        self.assertTrue(json_schema.validate(s | {"new_key": 1}, "metrics.schema.json#/$defs/summary"))
        self.assertTrue(json_schema.validate({k: v for k, v in s.items() if k != "schema_version"}, "metrics.schema.json#/$defs/summary"))

    def test_owners_json_matches_its_schema(self):
        with adopted_repo() as adopted:
            data = self.json_of("owners", "--json", cwd=adopted)
        self.assertEqual(data["schema_version"], understand.OWNERS_SCHEMA_VERSION)
        self.assertIn("@x", json.dumps(data["humans"]))
        self.valid(data, "owners.schema.json")
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[]))
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(
            cfg.read_text(encoding="utf-8") + '\nstandards:\n  - name: api\n    path: docs/api.md\n    roles: [developer]\n    when_changed: ["api/**"]\n',
            encoding="utf-8",
        )
        with contextlib.chdir(self.root):
            import subprocess

            subprocess.run(["git", "init", "-q"], check=True)
        data = self.json_of("owners", "--json", "--changed", "api/x.py")
        self.assertEqual([s["name"] for s in data["standards"]], ["api"])
        self.valid(data, "owners.schema.json")

    def test_list_json_matches_its_schema_in_both_shapes(self):
        with adopted_repo(spec="02-normal-feature:specs/SPEC-220.md") as adopted:
            one = self.json_of("list", "--json", cwd=adopted)
            many = self.json_of("list", str(adopted), str(self.root / "missing"), "--json", cwd=adopted)
        self.assertEqual(set(one), {"schema_version", "steps"})
        self.assertEqual(one["schema_version"], arguments.JSON_SCHEMA_VERSION)
        self.assertTrue(one["steps"])
        self.valid(one, "list.schema.json")
        self.assertEqual(set(many), {"schema_version", "repos"})
        self.valid(many, "list.schema.json")
        self.assertTrue(json_schema.validate({"schema_version": "1", "steps": [{"code": "x"}]}, "list.schema.json"))
        self.assertTrue(json_schema.validate(one["steps"], "list.schema.json"), "a bare array is no longer the shape")

    def test_the_forecast_json_matches_its_schema(self):
        from aidd import tracking

        with adopted_repo(spec="02-normal-feature:specs/SPEC-220.md") as adopted, contextlib.chdir(adopted):
            answer = {"schema_version": arguments.JSON_SCHEMA_VERSION} | tracking.forecast(Path("."))  # a branch's, as the hooks read it
            planned = self.json_of("gate", "--paths", "db/migrations/1.sql", "--json", cwd=adopted)
        self.assertEqual(set(answer), {"schema_version", "route", "steps", "overlaps"})
        self.assertEqual(planned["schema_version"], arguments.JSON_SCHEMA_VERSION)
        self.valid(answer, "forecast.schema.json")
        self.assertEqual((planned["route"]["route"], planned["route"]["required"], planned["route"]["declared"]), ("major", "major", None))
        self.assertNotIn("computed", planned["route"])
        self.valid(planned, "forecast.schema.json")
        self.assertTrue(json_schema.validate({"route": None, "steps": [{"code": "x"}], "overlaps": []}, "forecast.schema.json"))
        self.assertTrue(json_schema.validate({"route": None, "steps": [], "overlaps": []}, "forecast.schema.json"))  # no schema_version

    def test_validate_and_doctor_json_match_their_schemas(self):
        with adopted_repo(spec="02-normal-feature:specs/SPEC-220.md") as adopted:
            checked = self.json_of("validate", "--json", cwd=adopted)
            wired = self.json_of("doctor", "--json", cwd=adopted)
            autopilot = self.json_of("doctor", "--autopilot", "--json", cwd=adopted)
        self.valid(checked, "validate.schema.json")
        self.assertEqual(checked["passed"], not checked["errors"])
        self.valid(wired, "doctor.schema.json")
        self.assertTrue(wired["checks"])
        self.valid(autopilot, "doctor.schema.json")
        self.assertIn("check_yourself", autopilot)

    def test_gate_json_prints_the_decision_record_with_its_version(self):
        ctx = self.root / "ctx.json"
        ctx.write_text(json.dumps(example("02-normal-feature")), encoding="utf-8")
        with contextlib.chdir(self.root):
            code, out = run_cli("gate", "--context", str(ctx), "--json")
        record = json.loads(out)  # nothing but the record on stdout
        self.assertEqual(record["schema_version"], arguments.JSON_SCHEMA_VERSION)
        self.assertEqual({k: v for k, v in record.items() if k != "schema_version"}, decide(example("02-normal-feature")).record)
        self.assertEqual(code, arguments.EXIT[record["decision"]])
        self.valid(record, "record.schema.json")

    def test_log_json_is_versioned(self):
        helpers.git(self.root, "init", "-q")
        (self.root / "specs" / "S-1.md").write_text("---\nkind: spec\nid: S-1\ntitle: t\n---\n", encoding="utf-8")
        data = self.json_of("log", "specs/S-1.md", "--json")
        self.assertEqual(data["schema_version"], arguments.JSON_SCHEMA_VERSION)

    def test_the_gate_event_is_versioned_and_valid(self):
        line = decision_report.decision_event(decide(example("02-normal-feature")), "acme/shop")
        self.assertEqual(line["schema_version"], "1")
        self.valid(line, "event.schema.json")
        # The record is versioned by its verifier release and the schema's $id (urn:aidd:1:record).
        self.assertIn("aidd_version", decide(example("02-normal-feature")).record)


def undescribed(node, path=""):
    """The JSON pointers of properties without a description (a `$ref` carries its target's). The properties an
    `if`, `then`, `else`, or `not` names are conditions on properties declared elsewhere, not declarations."""
    if isinstance(node, dict):
        for key, value in (node.get("properties") or {}).items():
            if isinstance(value, dict) and "$ref" not in value and not value.get("description"):
                yield f"{path}/properties/{key}"
        for key, value in node.items():
            if key not in ("if", "then", "else", "not"):
                yield from undescribed(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from undescribed(value, f"{path}/{i}")


# What aidd writes and a consumer reads without the code.
OUTPUT_SCHEMAS = (
    "event",
    "export",
    "packs",
    "upkeep",
    "standard-list",
    "stack-list",
    "evidence",
    "artifacts",
    "change-record",
    "record",
    "list",
    "goal-list",
    "forecast",
    "owners",
    "metrics",
    "control-evidence",
    "digest",
    "release-notes",
    "knowledge",
    "autopilot-next",
    "autopilot-status",
    "context-pack",
    "validate",
    "doctor",
)
# What a person or an agent writes: the config, the change's block, and the planning and delivery artifacts.
AUTHOR_SCHEMAS = ("config", "change-request", "spec", "proposal", "initiative", "epic", "postmortem", "runbook", "exploration", "common", "standard", "stack")


class SchemaDescriptionTests(unittest.TestCase):
    def test_every_property_of_the_output_schemas_says_what_it_holds(self):
        """A consumer reads these files without the code: each property carries a description."""
        for name in OUTPUT_SCHEMAS:
            with self.subTest(schema=name):
                data = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
                self.assertEqual(list(undescribed(data)), [])

    def test_every_property_an_author_writes_says_what_it_holds(self):
        """An author fills these in from the schema or an editor's hover text: each property carries a description."""
        for name in AUTHOR_SCHEMAS:
            with self.subTest(schema=name):
                data = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
                self.assertEqual(list(undescribed(data)), [])

    def test_the_walk_finds_an_undescribed_property_and_skips_a_condition(self):
        schema_ = {"properties": {"a": {"type": "string"}, "b": {"$ref": "#/x"}}, "allOf": [{"if": {"properties": {"a": {"const": "x"}}}}]}
        self.assertEqual(list(undescribed(schema_)), ["/properties/a"])
        self.assertEqual(
            sorted(set(OUTPUT_SCHEMAS) | set(AUTHOR_SCHEMAS)),
            sorted(
                p.name.removesuffix(".schema.json")
                for p in (ROOT / "schemas").glob("*.schema.json")
                if p.name not in ("context.schema.json", "conformance.schema.json", "roles.schema.json")
            ),
        )


if __name__ == "__main__":
    unittest.main()
