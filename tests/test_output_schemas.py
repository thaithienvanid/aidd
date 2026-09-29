"""The JSON output contracts: what `aidd metrics`, `aidd owners`, and `aidd next` print with --json, and the gate event,
validated as printed against schemas/metrics.schema.json, owners.schema.json, next.schema.json, and event.schema.json."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, decide, example, run_cli

from aidd import cli, metrics, report, schema
from aidd import repo as repomod


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
        self.assertEqual(schema.validate(data, ref), [], json.dumps(data)[:400])

    def test_every_metrics_json_output_matches_its_schema(self):
        ledger = self.root / "cost.jsonl"
        ledger.write_text(json.dumps({"ts": "2026-09-01T09:00:00Z", "amount": 1.5, "currency": "USD", "spec": "SPEC-1", "agent": "a"}) + "\n", encoding="utf-8")
        e = str(self.events)
        summary = self.json_of("metrics", e, "--json", "--specs", "specs", "--cost", str(ledger))
        self.assertEqual(summary["schema_version"], metrics.SCHEMA_VERSION)
        self.assertIn("cost", summary)
        self.assertIn("released_specs", summary)
        self.valid(summary, "metrics.schema.json#/$defs/summary")
        self.valid(self.json_of("metrics", e, "--json"), "metrics.schema.json#/$defs/summary")
        self.valid(self.json_of("metrics", e, "--json", "--by", "author"), "metrics.schema.json#/$defs/grouped")
        for rows, ref in ((self.json_of("metrics", e, "--json", "--dora"), "dora_row"), (self.json_of("metrics", e, "--json", "--autonomy"), "autonomy_row")):
            self.assertTrue(rows)
            for row in rows:
                self.valid(row, f"metrics.schema.json#/$defs/{ref}")
        proposals = self.json_of("metrics", e, "--json", "--autonomy", "--propose")
        self.assertTrue(proposals["proposals"])
        self.valid(proposals, "metrics.schema.json#/$defs/proposals")
        guard = self.root / "guard.jsonl"
        guard.write_text(json.dumps({"decision": "deny", "reason": "out_of_scope", "role": "developer", "tool": "Edit"}) + "\n", encoding="utf-8")
        self.valid(self.json_of("metrics", "--guard", str(guard), "--json"), "metrics.schema.json#/$defs/guard")
        # And each one against the schema's root, which accepts any of them.
        for data in (summary, proposals):
            self.valid(data, "metrics.schema.json")

    def test_the_summary_schema_names_every_key_and_catches_drift(self):
        s = metrics.summarize(EVENTS)
        self.valid(s, "metrics.schema.json#/$defs/summary")
        self.assertTrue(schema.validate(s | {"new_key": 1}, "metrics.schema.json#/$defs/summary"))
        self.assertTrue(schema.validate({k: v for k, v in s.items() if k != "schema_version"}, "metrics.schema.json#/$defs/summary"))

    def test_owners_json_matches_its_schema(self):
        data = self.json_of("owners", "--json", cwd=ROOT)
        self.assertEqual(data["schema_version"], cli.OWNERS_SCHEMA_VERSION)
        self.valid(data, "owners.schema.json")
        repomod.init(self.root, profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[])
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(
            cfg.read_text(encoding="utf-8") + '\n[[standards]]\nname = "api"\npath = "docs/api.md"\nroles = ["developer"]\nwhen_changed = ["api/**"]\n',
            encoding="utf-8",
        )
        with contextlib.chdir(self.root):
            import subprocess

            subprocess.run(["git", "init", "-q"], check=True)
        data = self.json_of("owners", "--json", "--changed", "api/x.py")
        self.assertEqual([s["name"] for s in data["house_standards"]], ["api"])
        self.valid(data, "owners.schema.json")

    def test_next_json_matches_its_schema_in_both_shapes(self):
        one = self.json_of("next", "--json", cwd=ROOT)
        self.assertIsInstance(one, list)
        self.valid(one, "next.schema.json")
        many = self.json_of("next", str(ROOT), str(self.root / "missing"), "--json", cwd=ROOT)
        self.assertIsInstance(many, dict)
        self.valid(many, "next.schema.json")
        self.assertTrue(schema.validate([{"code": "x"}], "next.schema.json"))

    def test_the_gate_event_is_versioned_and_valid(self):
        line = report.event(decide(example("02-normal-feature")), "acme/shop")
        self.assertEqual(line["schema_version"], "1")
        self.valid(line, "event.schema.json")
        # The record is versioned by its verifier release and the schema's $id (urn:aidd:1:record).
        self.assertIn("aidd_version", decide(example("02-normal-feature")).record)


class OutputSchemaDescriptionTests(unittest.TestCase):
    def test_every_property_of_the_output_schemas_says_what_it_holds(self):
        """A consumer reads these files without the code: each property carries a description (a `$ref` carries its target's)."""

        def undescribed(node, path):
            if isinstance(node, dict):
                for key, value in (node.get("properties") or {}).items():
                    if isinstance(value, dict) and "$ref" not in value and not value.get("description"):
                        yield f"{path}/properties/{key}"
                for key, value in node.items():
                    yield from undescribed(value, f"{path}/{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    yield from undescribed(value, f"{path}/{i}")

        for name in ("event", "evidence", "change-record", "record", "next"):
            with self.subTest(schema=name):
                data = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
                self.assertEqual(list(undescribed(data, "")), [])


if __name__ == "__main__":
    unittest.main()
