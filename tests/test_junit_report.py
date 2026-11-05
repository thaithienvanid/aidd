"""A test command's JUnit XML report: what `aidd test` records from it, and what it refuses to read."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd.kernel import json_schema
from aidd.testing import junit
from aidd.testing import runner as test_runner

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "junit"
PY = sys.executable


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ParseTests(unittest.TestCase):
    def test_counts_by_case(self):
        failed = junit.parse_report(fixture("failed.xml"))
        self.assertEqual((failed["tests"], failed["failed"], failed["skipped"]), (4, 2, 1))
        self.assertEqual(failed["failed_tests"], ["tests.test_greeting.test_says_goodbye", "tests.test_greeting.test_crashes"])
        passed = junit.parse_report(fixture("passed.xml"))
        self.assertEqual((passed["tests"], passed["failed"], passed["failed_tests"]), (2, 0, []))
        self.assertEqual(junit.parse_report(fixture("empty.xml"))["tests"], 0)

    def test_a_case_with_a_failure_and_an_error_counts_once(self):
        data = b"<testsuite><testcase name='a'><failure/><error/></testcase></testsuite>"
        self.assertEqual(junit.parse_report(data)["failed"], 1)

    def test_the_failed_names_are_capped(self):
        cases = "".join(f"<testcase name='t{i}'><failure/></testcase>" for i in range(junit.MAX_FAILED_NAMES + 5))
        got = junit.parse_report(f"<testsuite>{cases}</testsuite>".encode())
        self.assertEqual((got["failed"], len(got["failed_tests"])), (junit.MAX_FAILED_NAMES + 5, junit.MAX_FAILED_NAMES))

    def test_input_it_refuses(self):
        deep = b"<testsuites>" + b"<testsuite>" * (junit.MAX_DEPTH + 1) + b"</testsuite>" * (junit.MAX_DEPTH + 1) + b"</testsuites>"
        table = {
            "a DOCTYPE with entities": fixture("doctype.xml"),
            "a DOCTYPE alone, in UTF-16": '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE testsuite><testsuite/>'.encode("utf-16"),
            "a root that is not a report": fixture("not_junit.xml"),
            "text that is not XML": b"FAILED tests/test_greeting.py::test_says_hello",
            "an empty file": b"",
            "a document cut short": b"<testsuite><testcase name='a'>",
            "elements nested too deep": deep,
        }
        for label, data in table.items():
            with self.subTest(label), self.assertRaises(ValueError):
                junit.parse_report(data)


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def write(self, rel: str, data: bytes) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_bytes(data)

    def test_a_report_the_run_wrote_is_read(self):
        before = junit.stamp(self.root, "out/report.xml")
        self.assertIsNone(before)
        self.write("out/report.xml", fixture("failed.xml"))
        got = junit.read_report(self.root, "out/report.xml", before)
        self.assertEqual((got["path"], got["tests"], got["failed"]), ("out/report.xml", 4, 2))
        self.assertNotIn("finding", got)

    def test_a_report_that_cannot_be_trusted_is_a_finding_and_not_a_crash(self):
        self.write("stale.xml", fixture("passed.xml"))
        self.write("big.xml", b"<testsuite>" + b" " * junit.MAX_REPORT_BYTES + b"</testsuite>")
        self.write("bad.xml", fixture("doctype.xml"))
        outside = Path(self.tmp.name).resolve().parent / "outside-report.xml"
        outside.write_bytes(fixture("passed.xml"))
        self.addCleanup(outside.unlink)
        os.symlink(outside, self.root / "link.xml")
        (self.root / "dir.xml").mkdir()
        self.write("encoding.xml", b'<?xml version="1.0" encoding="x-nope"?><testsuite/>')
        os.symlink(self.root / "loop-b.xml", self.root / "loop-a.xml")
        os.symlink(self.root / "loop-a.xml", self.root / "loop-b.xml")
        table = {
            "an encoding Python lacks": ("encoding.xml", None),
            "a symlink loop": ("loop-a.xml", None),
            "a NUL in the path": ("out\x00.xml", None),
            "missing": ("none.xml", None),
            "stale": ("stale.xml", junit.stamp(self.root, "stale.xml")),
            "too large": ("big.xml", None),
            "refused XML": ("bad.xml", None),
            "a symlink out of the repository": ("link.xml", None),
            "a folder": ("dir.xml", None),
        }
        for label, (rel, before) in table.items():
            with self.subTest(label):
                got = junit.read_report(self.root, rel, before)
                self.assertEqual(got["path"], rel)
                self.assertIn("finding", got)
                self.assertNotIn("tests", got)


class RunTests(unittest.TestCase):
    """The report in a result: the exit code stays the evidence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.logs = self.root / "evidence" / "logs"

    def run_command(self, code: int, write: str | None, **extra) -> dict:
        writing = "pathlib.Path('report.xml').write_text(" + repr(write) + ")" if write else "pass"
        body = f"import pathlib, sys; {writing}; sys.exit({code})"
        c = {"name": "unit", "command": [PY, "-c", body], **extra}
        return test_runner._run(c, "green", "config", str(self.root), self.logs, ())

    def test_the_exit_code_decides_and_the_report_adds_detail(self):
        failed, passed = fixture("failed.xml").decode(), fixture("passed.xml").decode()
        empty = fixture("empty.xml").decode()
        table = {
            # label: (exit, report text, status, failed cases, a finding)
            "red with failed cases": (1, failed, "failed", 2, False),
            "red with no test run": (1, empty, "failed", 0, False),
            "green with a clean report": (0, passed, "passed", 0, False),
            "red with no report written": (1, None, "failed", None, True),
            "green with a report that is not XML": (0, "not xml", "passed", None, True),
        }
        for label, (code, text, status, failed_cases, finding) in table.items():
            with self.subTest(label):
                (self.root / "report.xml").unlink(missing_ok=True)
                r = self.run_command(code, text, report="report.xml")
                self.assertEqual((r["exit"], r["status"]), (code, status))
                self.assertEqual("finding" in r["report"], finding)
                self.assertEqual(r["report"].get("failed"), failed_cases)

    def test_a_command_without_a_report_has_none(self):
        self.assertNotIn("report", self.run_command(1, None))

    def test_a_report_left_by_an_earlier_run_is_not_this_runs(self):
        (self.root / "report.xml").write_text(fixture("failed.xml").decode())
        r = self.run_command(1, None, report="report.xml")
        self.assertIn("finding", r["report"])
        self.assertEqual(r["status"], "failed")

    def test_each_attempt_keeps_its_report(self):
        body = "import pathlib, sys; p = pathlib.Path('n'); n = int(p.read_text()) + 1 if p.exists() else 1; p.write_text(str(n)); sys.exit(0 if n > 1 else 1)"
        c = {"name": "flaky", "command": [PY, "-c", body], "retries": 1, "report": "report.xml"}
        r = test_runner._run(c, "green", "config", str(self.root), self.logs, ())
        self.assertTrue(r["flaky"])
        self.assertEqual([a["report"]["path"] for a in r["attempts"]], ["report.xml", "report.xml"])
        self.assertEqual(r["report"], r["attempts"][-1]["report"])


class NotesTests(unittest.TestCase):
    def test_notes_name_a_report_that_disagrees_with_the_exit(self):
        def result(status, report):
            return {"name": "unit", "red_green": "red", "status": status, "exit": 1 if status == "failed" else 0, "report": report}

        table = {
            "red, no failed case": (result("failed", {"path": "r.xml", "tests": 0, "failed": 0}), "no failed test case"),
            "green, a failed case": (result("passed", {"path": "r.xml", "tests": 3, "failed": 1}), "failed test case"),
            "a finding": (result("failed", {"path": "r.xml", "finding": "report r.xml: missing"}), "missing"),
        }
        for label, (r, text) in table.items():
            with self.subTest(label):
                (note,) = junit.report_notes([r])
                self.assertIn(text, note)
        agreeing = [result("failed", {"path": "r.xml", "tests": 3, "failed": 1}), result("passed", {"path": "r.xml", "tests": 3, "failed": 0})]
        self.assertEqual(junit.report_notes(agreeing + [{"name": "x", "red_green": "red", "status": "failed", "exit": 1}]), [])


class SchemaTests(unittest.TestCase):
    def test_a_command_may_name_a_report_and_evidence_may_hold_one(self):
        config = {"aidd_version": "1.0.0", "profile": "team", "owners": {"approvers": ["bob"]}}
        ok = {**config, "tests": [{"name": "unit", "command": ["pytest"], "report": "out/junit.xml"}]}
        self.assertEqual(json_schema.validate(ok, "config.schema.json"), [])
        for bad in ("/tmp/junit.xml", "../junit.xml", "out/", ""):
            with self.subTest(bad):
                self.assertTrue(json_schema.validate({**config, "tests": [{"name": "unit", "command": ["pytest"], "report": bad}]}, "config.schema.json"))
        sha = "a" * 40
        result = {
            "name": "unit",
            "command": ["pytest"],
            "red_green": "green",
            "status": "passed",
            "exit": 0,
            "report": {"path": "r.xml", "tests": 2, "failed": 0, "failed_tests": []},
        }
        evidence = {"aidd_version": "1.0.0", "head_sha": sha, "base_sha": sha, "results": [result]}
        self.assertEqual(json_schema.validate(evidence, "evidence.schema.json"), [])
        result["report"] = {"path": "r.xml", "finding": "report r.xml: missing"}
        self.assertEqual(json_schema.validate(json.loads(json.dumps(evidence)), "evidence.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
