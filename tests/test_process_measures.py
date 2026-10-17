"""Process measures: `aidd test` keeps one test line per run, and `aidd metrics` reports the duplicate work (suite runs
per head) and the broken handoffs (handoff notes a reader cannot use)."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo, run_cli

from aidd import gate, tracking, workitems
from aidd.cli import local_events
from aidd.kernel import json_schema


def test_line(head: str, *, red: bool = True, partial: bool = False, result: str = "pass") -> dict:
    test = {"head_sha": head, "base_sha": "b" * 40, "result": result, "red": red, "partial": partial, "commands": 1, "duration_seconds": 1.5}
    return gate.event_header() | {"kind": "test", "repo": "repo", "change": "fix", "test": test}


def evidence(head: str, *, partial: bool = False) -> dict:
    results = [
        {"name": "unit", "red_green": "red", "status": "failed", "duration_seconds": 0.5},
        {"name": "unit", "red_green": "green", "status": "passed", "duration_seconds": 1.0},
    ]
    return {"head_sha": head, "base_sha": "b" * 40, "results": results, "partial": partial}


class SuiteRunsTests(unittest.TestCase):
    def test_full_runs_are_counted_per_head(self):  # A1: three readers ran the suite on one head, one on the next
        a, b = "a" * 40, "c" * 40
        lines = [test_line(a), test_line(a), test_line(a), test_line(a, red=False), test_line(a, partial=True), test_line(b)]
        got = tracking.suite_runs(lines)
        self.assertEqual((got["heads"], got["runs"], got["full_runs"]), (2, 6, 4))
        self.assertEqual(got["per_head"], {"p50": 2.0, "p90": 3.0, "samples": 2})

    def test_no_test_line_is_no_measure(self):
        self.assertIsNone(tracking.suite_runs([]))

    def test_the_line_is_a_valid_event_and_never_a_gate_decision(self):
        line = test_line("a" * 40)
        self.assertEqual(json_schema.validate(line, "event.schema.json"), [])
        self.assertEqual(tracking.gate_events([line]), [])
        broken = {**line, "test": {**line["test"], "result": "maybe"}}
        self.assertNotEqual(json_schema.validate(broken, "event.schema.json"), [])


class RecordTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "solo")
        self.events = self.root / ".git" / "aidd" / "events.jsonl"

    def test_a_run_keeps_one_test_line_that_metrics_counts(self):
        head = "d" * 40
        with contextlib.chdir(self.root):
            local_events.record_test(evidence(head), True)
            local_events.record_test(evidence(head, partial=True), True)
            code, out = run_cli("metrics", "--json")
        lines = [json.loads(x) for x in self.events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["kind"] for x in lines], ["test", "test"])
        self.assertEqual(
            lines[0]["test"], {"head_sha": head, "base_sha": "b" * 40, "result": "pass", "red": True, "partial": False, "commands": 1, "duration_seconds": 1.5}
        )
        self.assertEqual(lines[0]["change"], "feat")
        self.assertEqual(code, 0, out)
        runs = json.loads(out)["suite_runs"]
        self.assertEqual((runs["heads"], runs["runs"], runs["full_runs"]), (1, 2, 1))
        self.assertEqual(json_schema.validate(json.loads(out), "metrics.schema.json"), [])

    def test_a_store_that_cannot_take_the_line_costs_one_warning(self):
        self.events.parent.mkdir(mode=0o700, exist_ok=True)
        self.events.write_bytes(b"\xff\n")
        err = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stderr(err):
            local_events.record_test(evidence("e" * 40), False)
        self.assertEqual(err.getvalue().count("the test event was not kept"), 1, err.getvalue())
        self.assertEqual(self.events.read_bytes(), b"\xff\n")


class HandoffTests(unittest.TestCase):
    NOTES = (
        "```aidd-handoff\ndone: built it\nnext: reviewer\nneeds: none\nstopped_at: review\n```\n"
        "```aidd-handoff\ndone: half\nnext: reviewer\n```\n"  # no needs, no stopped_at
        "```aidd-handoff\ndone: x\nnext: the merge\nneeds: none\nstopped_at: y\n```\n"  # next is no role
        "```aidd-handoff\n: not yaml [\n```\n"
    )

    def test_each_broken_note_is_counted_once(self):  # A3
        self.assertEqual(workitems.handoff_counts("# Spec\n\n" + self.NOTES), (4, 3))

    def test_metrics_with_the_specs_folder_reports_the_handoffs(self):
        with tempfile.TemporaryDirectory() as d:
            specs = Path(d)
            (specs / "SPEC-1.md").write_text("---\nkind: spec\n---\n\n" + self.NOTES, encoding="utf-8")
            self.assertEqual(tracking.handoff_health(specs), {"notes": 4, "broken": 3})


if __name__ == "__main__":
    unittest.main()
