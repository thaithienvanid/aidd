"""The held-out cases: a case's `tier` says it is held out, evals/held-out.lock.json locks its content, and its text is quoted nowhere else."""

import copy
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT
from helpers import run_cli as run

from aidd import evals
from aidd.cli.commands import maintain
from aidd.evals import held_out, suites
from aidd.kernel import json_schema

# With the tier in the file, s5 is held out and s1 and s2 are not.
SCENARIOS = """
scenario:
  - id: s1
    situation: ROUTE=minor a typo
    expected: {route: minor}
  - id: s5
    tier: held-out
    situation: ROUTE=major an auth change
    expected: {route: major}
  - id: s2
    situation: ROUTE=normal a new endpoint
    expected: {route: stop}
"""
AGENT = """
import json, re, sys
print(json.dumps({"route": re.search(r"ROUTE=(\\w+)", sys.stdin.read()).group(1), "reason": "x"}))
"""
LOCK = json.loads((ROOT / "evals" / "held-out.lock.json").read_text(encoding="utf-8"))


class TierTests(unittest.TestCase):
    def test_a_case_is_held_out_by_its_stated_tier_and_not_by_its_id(self):
        cases = [{"id": "s1"}, {"id": "s5", "tier": "held-out"}, {"id": "s2", "tier": "full"}]
        self.assertEqual(suites.held_out_ids(cases), {"s5"})
        self.assertEqual(suites.held_out_ids([dict(c, id="renamed-" + c["id"]) for c in cases]), {"renamed-s5"}, "a rename carries the tier with it")
        self.assertFalse(any(hasattr(suites, name) for name in ("is_held_out", "HELD_OUT_SEED", "MOVED_TO_DEVELOPMENT")), "no hash picks the set")

    def test_the_held_out_cases_are_the_ones_the_lock_lists(self):
        shipped = {(r["suite"], r["id"]) for r in evals.suite_cases(ROOT) if r["tier"] == "held-out"}
        self.assertEqual(shipped, {(e["suite"], e["case"]) for e in LOCK["cases"]})
        self.assertEqual({s: sum(e["suite"] == s for e in LOCK["cases"]) for s in ("routing", "roles", "team")}, {"routing": 12, "roles": 14, "team": 10})

    def test_about_a_fifth_of_each_shipped_suite_is_held_out(self):
        for suite in ("routing", "roles"):
            scenarios = evals.load_scenarios(ROOT / "evals" / suite)
            share = len(suites.held_out_ids(scenarios)) / len(scenarios)
            self.assertTrue(0.10 <= share <= 0.30, f"{share:.0%} of the {suite} cases are held out")


class LockTests(unittest.TestCase):
    def test_the_lock_follows_its_schema_and_matches_the_cases(self):
        self.assertEqual(json_schema.validate(LOCK, "eval-held-out.schema.json"), [])
        self.assertEqual(held_out.lock_problems(ROOT), [])

    def test_the_lock_names_each_way_it_and_the_cases_disagree(self):
        first = LOCK["cases"][0]

        def edited(read: str | None, **change) -> dict:
            lock = copy.deepcopy(LOCK)
            lock["cases"][0].update(first_read_on=read, **change)
            return lock

        wrong = "0" * 64
        cases = {
            "the lock as shipped": (LOCK, []),
            "a held-out case with no entry": ({"cases": LOCK["cases"][1:]}, ["has no entry"]),
            "an entry with no held-out case": (
                {"cases": sorted([*LOCK["cases"], dict(first, case="r99-nothing")], key=lambda e: (e["suite"], e["case"]))},
                ["no case with that id"],
            ),
            "an edit before the first read": (edited(None, content_sha256=wrong), ["edited before its first read"]),
            "an edit after the first read": (edited("2026-12-01", content_sha256=wrong), ["edited after its score was read on 2026-12-01"]),
            "a read with no edit": (edited("2026-12-01"), []),
            "entries out of order": ({"cases": list(reversed(LOCK["cases"]))}, ["out of order"]),
        }
        for name, (lock, want) in cases.items():
            with self.subTest(name):
                got = held_out.lock_problems(ROOT, lock)
                self.assertEqual(len(got), len(want), got)
                for fragment, line in zip(want, got, strict=False):
                    self.assertIn(fragment, line)

    def test_a_first_read_is_dated_once_and_never_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evals").mkdir()
            lock = copy.deepcopy(LOCK)
            lock["cases"] = lock["cases"][:2]
            lock["cases"][1]["first_read_on"] = "2026-01-01"
            (root / "evals" / "held-out.lock.json").write_text(json.dumps(lock), encoding="utf-8")
            ids = [e["case"] for e in lock["cases"]]
            suite = lock["cases"][0]["suite"]
            self.assertEqual(held_out.mark_held_out_read(root, suite, ids, "2026-11-11"), [ids[0]])
            self.assertEqual(held_out.mark_held_out_read(root, suite, ids, "2026-12-12"), [], "a second run moves nothing")
            read = {e["case"]: e["first_read_on"] for e in held_out.read_lock(root)["cases"]}
            self.assertEqual(read, {ids[0]: "2026-11-11", ids[1]: "2026-01-01"})
            self.assertEqual(held_out.mark_held_out_read(root, "plugin", ids, "2026-12-12"), [], "another suite's case is not this one")


class LeakTests(unittest.TestCase):
    def test_no_file_outside_the_cases_quotes_a_held_out_case(self):
        self.assertEqual(held_out.leaks(ROOT), [])

    @staticmethod
    def found(guarded: str, development: str = "fix a typo in the readme") -> list[str]:
        held = "rename the quarterly invoices export column so the finance team sees totals in cents"
        files = {
            "evals/routing/scenarios.yaml": "scenario:\n"
            f"  - id: c1-held\n    claim: x\n    tier: held-out\n    situation: {held}\n"
            f"  - id: c2-dev\n    claim: x\n    tier: full\n    situation: {development}\n",
            "evals/roles/scenarios.yaml": "scenario: []\n",
            "evals/team/triggers.json": json.dumps({"skills": {}}),
            "docs/guide.md": guarded,
        }
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in files.items():
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / rel).write_text(text, encoding="utf-8")
            for suite in ("plugin",):
                (Path(tmp) / "evals" / suite).mkdir(parents=True, exist_ok=True)
            with mock.patch.object(held_out, "GUARDED", ("docs",)):
                return held_out.leaks(Path(tmp))

    def test_a_copied_sentence_is_a_leak_and_a_shared_phrase_is_not(self):
        quote = "Rename the quarterly invoices export column so the finance team sees totals in cents."
        cases = {
            "the sentence in a guide": ((f"A worked example. {quote} Then check the report.",), ["docs/guide.md quotes routing/c1-held"]),
            "the sentence in another case": (("nothing", quote.lower()), ["routing/c2-dev quotes routing/c1-held"]),
            "the first words in another case": (("nothing", "rename the quarterly invoices export column"), []),
            "a short shared phrase": (("Rename the quarterly invoices. The finance team sees totals.",), []),
            "no text near it": (("A page about something else entirely.",), []),
        }
        for name, (args, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.found(*args), want)


class ScoreTests(unittest.TestCase):
    def test_the_two_sets_are_scored_apart(self):
        def row(pass_at_1, held_out):
            return {"id": "x", "pass_at_1": pass_at_1, "pass_all": pass_at_1 == 1, "held_out": held_out}

        cases = {
            "both sets": ([row(1.0, False), row(0.0, False), row(1.0, True)], (2, 0.5, 0.5), (1, 1.0, 1.0)),
            "only development": ([row(1.0, False)], (1, 1.0, 1.0), None),
            "only held out": ([row(0.5, True)], None, (1, 0.5, 0.0)),
            "nothing": ([], None, None),
        }
        for name, (results, dev, held) in cases.items():
            with self.subTest(name):
                got = suites.split_summary(results)
                for key, want in (("development", dev), ("held_out", held)):
                    self.assertEqual(None if got[key] is None else (got[key]["scenarios"], got[key]["mean_pass_at_1"], got[key]["pass_k_share"]), want)

    def test_measure_marks_each_result_by_the_ids_it_is_given(self):
        results = suites.measure(lambda: [{"id": "s1", "ok": True}, {"id": "s5", "ok": True}], 1, frozenset({"s5"}))
        self.assertEqual([(r["id"], r["held_out"]) for r in results], [("s1", False), ("s5", True)])
        results = suites.measure(lambda: [{"id": "s1", "ok": True}], 1)
        self.assertEqual([r["held_out"] for r in results], [False], "with no held-out ids nothing is held out")


class SetsLineTests(unittest.TestCase):
    def test_a_held_out_set_under_the_compare_minimum_says_it_is_too_few(self):
        for n, too_few in ((1, True), (9, True), (10, False), (12, False)):
            with self.subTest(n):
                sets = {"development": None, "held_out": {"scenarios": n, "mean_pass_at_1": 1.0, "pass_k_share": 1.0}}
                self.assertEqual("too few to compare" in maintain._sets_line(sets, "pass@1"), too_few)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "routing").mkdir()
        (base / "routing" / "scenarios.yaml").write_text(SCENARIOS, encoding="utf-8")
        (base / "agent.py").write_text(AGENT, encoding="utf-8")
        self.cmd = shlex.join([sys.executable, str(base / "agent.py")])
        self.record = base / "runs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def routing(self, *extra: str) -> tuple[str, dict]:
        self.record.unlink(missing_ok=True)
        argv = [
            "routing",
            "--scenarios",
            str(Path(self.tmp.name) / "routing"),
            "--agent-command",
            self.cmd,
            "--min-accuracy",
            "0",
            "--record",
            str(self.record),
            "--model-label",
            "test-model",
        ]
        code, out = run("eval", *argv, *extra)
        self.assertEqual(code, 0, out)
        (line,) = [json.loads(x) for x in self.record.read_text(encoding="utf-8").splitlines()]
        return out, line

    def test_the_run_prints_and_records_both_sets(self):
        out, line = self.routing()
        self.assertIn("development: pass@1 50.0% over 2; held-out: pass@1 100.0% over 1 (too few to compare: under 10 cases)", out)
        self.assertEqual(line["sets"]["development"]["mean_pass_at_1"], 0.5)
        self.assertEqual(line["sets"]["held_out"], {"scenarios": 1, "mean_pass_at_1": 1.0, "pass_k_share": 1.0})
        self.assertEqual({s["id"]: s.get("held_out", False) for s in line["scenarios"]}, {"s1": False, "s5": True, "s2": False})

    def test_a_set_with_no_case_in_the_run_says_so(self):
        out, line = self.routing("--case", "s5")
        self.assertIn("development: no case; held-out: pass@1 100.0% over 1", out)
        self.assertIsNone(line["sets"]["development"])
        out, _ = self.routing("--case", "s1", "--repeat", "2")
        self.assertIn("development: mean pass@1 100.0% over 1; held-out: no case", out)

    def test_a_recorded_run_names_its_model_or_does_not_start(self):
        argv = ["routing", "--scenarios", str(Path(self.tmp.name) / "routing"), "--agent-command", self.cmd, "--record", str(self.record)]
        with mock.patch.object(suites, "run_routing", side_effect=AssertionError("the agent must not start")):
            code, out = run("eval", *argv)
        self.assertEqual(code, 2)
        self.assertIn("--record needs --model-label", out)
        self.assertFalse(self.record.exists())


if __name__ == "__main__":
    unittest.main()


class RecordBlockersTests(unittest.TestCase):
    """A recorded run is refused when the eval data disagrees with itself. Both directions: this repository's data is clean,
    a folder with no eval data blocks nothing, and one broken lock entry is a blocker."""

    def test_clean_data_and_no_data_block_nothing_and_a_broken_lock_blocks(self):
        self.assertEqual(held_out.record_blockers(ROOT), [])
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(held_out.record_blockers(Path(empty)), [])
        lock = held_out.read_lock(ROOT)
        broken = dict(lock, cases=lock["cases"][1:])
        with mock.patch("aidd.evals.held_out.read_lock", return_value=broken):
            self.assertEqual(len(held_out.record_blockers(ROOT)), 1)


class OnlyARecordedRunReadsAHeldOutCaseTests(unittest.TestCase):
    """A held-out case counts as read when a recorded run scores it. A run with no `--record` leaves the lock as it is, so a
    test that runs a stub agent over aidd's own cases never dates a read. Both directions, on the real lock, with the write patched."""

    def test_a_run_with_no_record_writes_nothing_and_a_recorded_run_marks(self):
        import argparse

        from aidd.cli.commands import maintain

        cases = ROOT / "evals" / "routing"
        ids = [case for (suite, case) in held_out.held_out_cases(ROOT) if suite == "routing"][:1]
        self.assertTrue(ids)
        for record, calls in ((None, 0), ("out.jsonl", 1)):
            with self.subTest(record=record), mock.patch("aidd.evals.held_out.mark_held_out_read", return_value=[]) as mark:
                maintain._mark_held_out_read(argparse.Namespace(record=record, suite="routing"), cases, ROOT, ids)
                self.assertEqual(mark.call_count, calls)
