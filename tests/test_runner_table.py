"""The test runners' table (schemas/test-runners.json) decides when a red run proves new behavior, so it is evidence, not a
convenience. Four things hold:

- Moving the facts into data changed no verdict. A copy of the reading as it was before the table (`START`, kept below) and the
  table's reading give the same answer for `red_ok`, `result_good`, and `exit_code`, over every runner row, every status, and every
  exit from 0 to 130, except the exits ADDED names, and each of those is stricter, never looser.
- Every exit a row gives is documented: the row names its sources and the day they were read, and an exit the documentation
  does not give is not in the table, so it stays a real failure.
- Each exit, in both directions: a documented exit is no proof of new behavior for a command that names the runner, and
  every other exit still is, for that command, and for a command that names no runner at all.
- Pytest's exit 2 stays a red: a new feature's missing module fails the same way on the base commit, and that red is legitimate.

A runner row is a change to the evidence rule. It needs a documented source, a row in ADDED, and a line in the change's notes.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
import unittest

import helpers  # noqa: F401  # the hermetic environment
from helpers import ROOT

from aidd import config
from aidd.kernel import json_schema
from aidd.testing import runner, verdict

TABLE = json.loads((ROOT / "schemas" / "test-runners.json").read_text(encoding="utf-8"))["runners"]

# The reading before the table, as it stood at the commit this package started from (5fb351ad): pytest's exits were a tuple in the code.
START_NOT_RED = (3, 4, 5)


def start_runs_pytest(command: object) -> bool:
    if not isinstance(command, list):
        return False
    words = [str(w) for w in command]
    progs = [re.split(r"[\\/]", w)[-1].lower().removesuffix(".exe") for w in words]
    return any(p in ("pytest", "py.test") for p in progs) or any(w == "-m" and progs[i + 1 : i + 2] == ["pytest"] for i, w in enumerate(words))


def start_red_ok(result: dict) -> bool:
    code = result.get("exit")
    if result.get("status") != "failed" or code in (None, 126, 127):
        return False
    return not (code in START_NOT_RED and start_runs_pytest(result.get("command")))


def start_result_good(result: dict) -> bool:
    return (result["red_green"] == "green" and result["status"] == "passed") or (result["red_green"] == "red" and start_red_ok(result))


def start_exit_code(result: dict) -> int:
    """`exit_code` for a run of one result, in a clean tree with no flag: 1 when the result is bad, else 0."""
    return 0 if start_result_good(result) else 1


# What the table adds to the reading before it: a documented exit of a runner, so a red run that ends with it is no proof. Each is
# one row of the table with its sources; all other (runner, exit) pairs answer as they did.
ADDED = {("pytest", 6), ("unittest", 5), ("cargo nextest", 4)}
STATUSES = ("passed", "failed", "timeout", "not_started")
EXITS = [None, *range(0, 131)]


def words_of(runner_key: str) -> list[str]:
    return list(TABLE[runner_key].get("command_words", [])[:1] or runner_key.split())


def commands_of(runner_key: str) -> list[list[str]]:
    """A command that names the runner in the forms a project writes: bare, behind `python -m`, behind a wrapper with arguments."""
    word = words_of(runner_key)
    return [word, ["python3", "-m", *word], ["uv", "run", *word, "-q", "tests/"]]


def result(command: list[str], status: str, code: int | None, phase: str) -> dict:
    return {"name": "c", "command": command, "red_green": phase, "status": status, "exit": code}


class NoVerdictChanged(unittest.TestCase):
    def table(self):
        for key in TABLE:
            for command in commands_of(key):
                for status, code, phase in itertools.product(STATUSES, EXITS, ("red", "green")):
                    yield key, result(command, status, code, phase)

    def test_the_verdicts_are_the_ones_before_the_table_except_the_exits_added(self):
        different, checked = set(), 0
        for key, r in self.table():
            checked += 1
            red = r["red_green"] == "red"
            new = (runner.red_ok(r) if red else None, verdict.result_good(r), verdict.exit_code({"results": [r]}))
            old = (start_red_ok(r) if red else None, start_result_good(r), start_exit_code(r))
            self.assertEqual(new[1], new[0] if red else r["status"] == "passed", (key, r))
            if new != old:
                different.add((key, r["exit"]))
                self.assertEqual((r["red_green"], r["status"]), ("red", "failed"), "only a red run that failed can differ")
        self.assertEqual(different, ADDED)
        self.assertGreater(checked, 40000)

    def test_a_verdict_is_never_looser_than_before(self):
        """What proved new behavior before the table and proves it no longer is allowed; what did not prove it never starts to."""
        for key, r in self.table():
            if not start_red_ok(r):
                self.assertFalse(runner.red_ok(r), (key, r))
            if not start_result_good(r):
                self.assertFalse(verdict.result_good(r), (key, r))
            if start_exit_code(r) == 1:
                self.assertEqual(verdict.exit_code({"results": [r]}), 1, (key, r))

    def test_a_command_that_names_no_runner_and_every_odd_command_answer_as_before(self):
        odd = [
            ["make", "test"],
            [],
            ["echo", "pytest-cov"],
            ["python3", "tests/run.py"],
            "pytest",
            None,
            ["PyTest.EXE", "-q"],
            ["C:\\bin\\py.test"],
            ["a", "-m", "pytest"],
        ]
        for command, status, code in itertools.product(odd, STATUSES, EXITS):
            if code == 6 and start_runs_pytest(command):
                continue  # pytest's exit 6, the one exit ADDED gives a command that names pytest
            r = {"name": "c", "command": command, "red_green": "red", "status": status, "exit": code}
            self.assertEqual(runner.red_ok(r), start_red_ok(r), r)


class EachExitBothWays(unittest.TestCase):
    def test_a_documented_exit_proves_nothing_and_every_other_exit_still_does(self):
        for key, row in TABLE.items():
            documented = {e["exit"] for e in row.get("not_red_exits", [])}
            for command in commands_of(key) if documented else []:
                for code in range(1, 131):
                    if code in (126, 127):
                        continue
                    r = result(command, "failed", code, "red")
                    with self.subTest(runner=key, command=command, exit=code):
                        self.assertEqual(runner.red_ok(r), code not in documented)
                        self.assertEqual(verdict.exit_code({"results": [r]}), 0 if code not in documented else 1)
                other = result(["make", "test"], "failed", min(documented), "red")
                self.assertTrue(runner.red_ok(other), "a command that names no runner keeps every real exit")

    def test_a_command_is_read_by_its_words_in_any_case_and_with_or_without_exe(self):
        for command in (["PYTEST", "-q"], ["C:\\tools\\pytest.exe"], ["/usr/bin/py.test", "x"], ["uv", "run", "pytest"], ["python", "-P", "-m", "pytest"]):
            self.assertFalse(runner.red_ok(result(command, "failed", 5, "red")), command)
        for command in (["pytest-cov"], ["mypytest"], ["pytest.py"], ["tests/pytest/run.sh"]):
            self.assertTrue(runner.red_ok(result(command, "failed", 5, "red")), command)

    def test_pytest_exit_2_is_a_red_because_a_missing_module_fails_that_way_on_the_base(self):
        """The audit's nuance: exit 2 is not in the table, and a test that adds it fails here."""
        self.assertNotIn(2, {e["exit"] for e in TABLE["pytest"]["not_red_exits"]})
        self.assertIn("Exit 2", TABLE["pytest"]["note"])
        for command in commands_of("pytest"):
            self.assertTrue(runner.red_ok(result(command, "failed", 2, "red")), command)

    def test_a_timeout_a_missing_command_and_a_pass_are_never_a_red(self):
        for key in TABLE:
            for command in commands_of(key):
                for status, code in (("timeout", None), ("not_started", None), ("failed", 126), ("failed", 127), ("failed", None), ("passed", 0)):
                    self.assertFalse(runner.red_ok(result(command, status, code, "red")), (command, status, code))


class EveryRowIsDocumented(unittest.TestCase):
    def test_the_table_follows_its_schema(self):
        errors = json_schema.validate(json.loads((ROOT / "schemas" / "test-runners.json").read_text(encoding="utf-8")), "test-runners.schema.json")
        self.assertEqual(errors, [])

    def test_a_row_that_gives_an_exit_names_its_sources_the_day_it_was_read_and_what_it_leaves_out(self):
        today = dt.date.today()
        for key, row in TABLE.items():
            if "not_red_exits" not in row:
                self.assertLessEqual(set(row), {"command_words", "related_tests"}, f"{key} gives no exit, so it holds no other fact of exits")
                continue
            with self.subTest(runner=key):
                self.assertTrue(row["sources"] and all(s.startswith("https://") for s in row["sources"]))
                self.assertLessEqual(dt.date.fromisoformat(row["checked"]), today)
                exits = [e["exit"] for e in row["not_red_exits"]]
                self.assertEqual(exits, sorted(set(exits)), "each exit once, in order")
                self.assertFalse({0, 126, 127} & set(exits), "0 passes, and 126 and 127 mean the command did not start")
                self.assertTrue(row.get("note", "").strip(), "a row says which near exit it leaves a red, so the next reader does not add it")

    def test_a_word_names_one_runner_and_a_row_with_exits_is_found_by_its_key_too(self):
        words = [w for row in TABLE.values() for w in row.get("command_words", [])]
        self.assertEqual(len(words), len(set(words)), "one word names two runners")
        for key, row in TABLE.items():
            if row.get("command_words"):
                self.assertTrue(set(key.split()) & set(row["command_words"]), f"{key}: no command word is its name")

    def test_a_related_tests_fact_names_its_sources_and_the_day_it_was_read(self):
        """A row's `related_tests` is the documentation's word on a mode that runs only related tests: with `arguments` the form
        aidd suggests, which holds `{changed_paths}` as an argument of its own and needs the words that find the runner."""
        today = dt.date.today()
        for key, row in TABLE.items():
            related = row.get("related_tests")
            if related is None:
                continue
            with self.subTest(runner=key):
                self.assertTrue(related["sources"] and all(s.startswith("https://") for s in related["sources"]))
                self.assertLessEqual(dt.date.fromisoformat(related["checked"]), today)
                self.assertTrue(related["means"].strip())
                if "arguments" in related:
                    self.assertIn(config.CHANGED_PATHS, related["arguments"])
                    self.assertTrue(row["command_words"])

    def test_init_lists_the_runners_it_always_did_in_the_same_order(self):
        before = ("pytest", "unittest", "vitest", "jest", "mocha", "playwright", "rspec", "phpunit", "go test", "cargo test", "dotnet test", "flutter test")
        self.assertEqual([n for n in config.test_runner_names() if n in before], list(before))
        self.assertEqual(config.test_runner_names(), tuple(TABLE))

    def test_the_names_the_tests_added_are_the_rows_that_were_added_and_nothing_more(self):
        self.assertEqual({(k, e["exit"]) for k, row in TABLE.items() for e in row.get("not_red_exits", [])}, ADDED | {("pytest", c) for c in START_NOT_RED})


if __name__ == "__main__":
    unittest.main()
