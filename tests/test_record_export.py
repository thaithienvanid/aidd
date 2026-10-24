"""`aidd record export`: gate records and events as JSON or CSV, the same bytes for the same inputs."""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import decide, example, run_cli

from aidd.tracking import record_export
from aidd.gate import decision_report
from aidd.kernel import json_schema, resources


def ev(change, ts, **kw):
    return {
        "repo": "o/r",
        "change": change,
        "ts": ts,
        "head_sha": "a" * 40,
        "decision": "pass",
        "profile": "team",
        "failed_rules": [],
        "pending_rules": [],
    } | kw


class ExportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        runs = self.root / "runs"
        (runs / "b").mkdir(parents=True)
        (runs / "a").mkdir(parents=True)
        # Two artifacts, one event in both (an overlapping download), out of time order, and a line that is not an event.
        (runs / "b" / "aidd-events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in [ev("2", "2026-09-02T00:00:00+02:00", failed_rules=["scope", "tests"]), ev("1", "2026-09-01T09:00:00Z")])
            + "\nnot json\n",
            encoding="utf-8",
        )
        (runs / "a" / "aidd-events.jsonl").write_text(json.dumps(ev("1", "2026-09-01T09:00:00Z")) + "\n" + json.dumps({"note": "x"}) + "\n", encoding="utf-8")
        d1 = decide(example("02-normal-feature"))
        d2 = decide(example("03-normal-waiting"))
        (runs / "a" / "aidd-record.json").write_text(json.dumps(d2.record, indent=2), encoding="utf-8")
        (runs / "b" / "aidd-record.json").write_text(json.dumps(d1.record, indent=2), encoding="utf-8")
        (runs / "b" / "evidence.json").write_text(json.dumps({"results": []}), encoding="utf-8")
        self.runs = runs
        self.event_line = decision_report.decision_event(d1, "acme/shop")

    def export(self, *args):
        with contextlib.chdir(self.root):
            return run_cli("record", "export", *args)

    def test_events_are_deduplicated_and_ordered_by_time(self):
        items = record_export.collect_records("events", [str(self.runs)])
        self.assertEqual([(e["change"], e["ts"]) for e in items], [("1", "2026-09-01T09:00:00Z"), ("2", "2026-09-02T00:00:00+02:00")])

    def test_the_output_is_the_same_bytes_whatever_the_argument_order(self):
        one = self.export("events", str(self.runs / "a"), str(self.runs / "b"), "--format", "csv")
        two = self.export("events", str(self.runs / "b"), str(self.runs / "a"), "--format", "csv")
        self.assertEqual(one, two)
        self.assertEqual(one[0], 0)
        self.assertEqual(self.export("records", str(self.runs / "b"), str(self.runs / "a")), self.export("records", str(self.runs)))

    def test_csv_columns_are_the_schemas_fields_in_order(self):
        code, out = self.export("events", str(self.runs), "--format", "csv")
        rows = list(csv.reader(io.StringIO(out)))
        self.assertEqual(rows[0], list(resources.load_json("event.schema.json")["properties"]))
        self.assertEqual(rows[0], record_export.columns("events"))
        header = rows[0]
        second = dict(zip(header, rows[2], strict=True))
        self.assertEqual(second["failed_rules"], "scope;tests")
        self.assertEqual(second["spec"], "")
        self.assertEqual(len(rows), 3)

    def test_a_real_event_round_trips_and_nested_values_are_compact_json(self):
        path = self.root / "real.jsonl"
        path.write_text(json.dumps(self.event_line) + "\n", encoding="utf-8")
        code, out = self.export("events", str(path), "--format", "csv")
        row = dict(zip(*list(csv.reader(io.StringIO(out))), strict=True))
        self.assertEqual(json.loads(row["tests"]), json.loads(json.dumps(self.event_line["tests"])))
        code, out = self.export("events", str(path))
        self.assertEqual(json.loads(out), {"schema_version": "1", "kind": "events", "items": [self.event_line]})
        self.assertEqual(json_schema.validate(json.loads(out), "export.schema.json"), [])

    def test_records_skip_other_json_and_since_is_for_events_only(self):
        items = record_export.collect_records("records", [str(self.runs)])
        self.assertEqual(len(items), 2)
        self.assertTrue(all("decision" in r for r in items))
        code, out = self.export("records", str(self.runs), "--since", "2026-09-01")
        self.assertEqual(code, 2)
        self.assertIn("records carry no time", out)
        code, out = self.export("records", str(self.runs), "--format", "csv")
        self.assertEqual(next(csv.reader(io.StringIO(out))), list(resources.load_json("record.schema.json")["properties"]))

    def test_since_and_out(self):
        code, out = self.export("events", str(self.runs), "--since", "2026-09-01T12:00:00Z", "--out", "exported")
        self.assertEqual(code, 0, out)
        self.assertIn("1 events", out)
        written = json.loads((self.root / "exported" / "events.json").read_text(encoding="utf-8"))
        self.assertEqual((written["schema_version"], written["kind"]), ("1", "events"))
        self.assertEqual([e["change"] for e in written["items"]], ["2"])

    def test_a_missing_path_or_an_unknown_format_is_an_error(self):
        self.assertEqual(self.export("events", str(self.root / "none"))[0], 2)
        code, out = self.export("events", str(self.runs), "--format", "xml")
        self.assertEqual(code, 2)
        self.assertIn("no exporter 'xml'", out)


if __name__ == "__main__":
    unittest.main()
