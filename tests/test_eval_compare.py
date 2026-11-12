"""`aidd eval compare`: two recorded variants, the difference with a 95% interval, and a verdict that never over-reads a small K."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import run_cli as run

from aidd.evals import compare


def run_of(scores: dict[str, float], *, suite="routing", repeat=3, date="2026-11-07T00:00:00Z", model="m") -> dict:
    return {
        "suite": suite,
        "date": date,
        "mean_pass_at_1": sum(scores.values()) / max(len(scores), 1),
        "repeat": repeat,
        "model": model,
        "scenarios": [{"id": i, "pass_at_1": v} for i, v in scores.items()],
    }


def cases(n: int, value: float, *, flip: int = 0, to: float = 1.0) -> dict[str, float]:
    """n cases at `value`, the first `flip` of them at `to`."""
    return {f"c{i:02d}": (to if i < flip else value) for i in range(n)}


class IntervalTests(unittest.TestCase):
    def test_the_interval_is_fixed_for_the_same_input_and_holds_the_mean(self):
        diffs = [1.0] * 10 + [0.0] * 10
        self.assertEqual(compare.paired_interval(diffs), compare.paired_interval(diffs))
        low, high = compare.paired_interval(diffs)
        self.assertTrue(0.25 < low < 0.5 < high < 0.75, (low, high))

    def test_no_spread_gives_a_point(self):
        for value in (0.0, 1.0, -0.5):
            with self.subTest(value):
                self.assertEqual(compare.paired_interval([value] * 12), (value, value))

    def test_fewer_cases_make_a_wider_interval(self):
        wide = compare.paired_interval([1.0, 0.0] * 5)
        narrow = compare.paired_interval([1.0, 0.0] * 50)
        self.assertGreater(wide[1] - wide[0], narrow[1] - narrow[0])


class VerdictTests(unittest.TestCase):
    def test_each_reading_of_the_interval(self):
        cases_ = {
            "too few cases, even with a clear gain": ((9, 0.2, 0.4, 5, (9, 0)), "Too few shared cases"),
            "a gain at K=1 is a lead": ((30, 0.1, 0.3, 1, (20, 2)), "treat it as a lead"),
            "a gain at K=2 is a lead": ((30, 0.1, 0.3, 2, (20, 2)), "treat it as a lead"),
            "a loss at K=1 is a lead": ((30, -0.3, -0.1, 1, (2, 20)), "hints that B is worse than A"),
            "a gain at K=3": ((30, 0.1, 0.3, 3, (20, 2)), "B is better than A: the interval stays"),
            "a loss at K=3": ((30, -0.3, -0.1, 3, (2, 20)), "B is worse than A: the interval stays"),
            "an interval holding 0": ((30, -0.1, 0.2, 5, (10, 8)), "No difference the data can show"),
            "an interval touching 0 is not a gain": ((30, 0.0, 0.2, 5, (10, 8)), "No difference the data can show"),
        }
        for name, (args, want) in cases_.items():
            with self.subTest(name):
                self.assertIn(want.lower(), compare.verdict(*args).lower())
        self.assertNotIn("firm", compare.verdict(30, 0.1, 0.3, 1, (20, 2)))

    def test_a_lopsided_split_is_firm_only_when_a_sign_test_agrees(self):
        """4 better and 0 worse is p=0.125 at any number of cases: the interval leaves 0, and luck still explains it."""
        table = {
            "4-0 of 10 cases": (10, (4, 0), False),
            "4-0 of 15 cases": (15, (4, 0), False),
            "4-0 of 20 cases": (20, (4, 0), False),
            "5-0, p=0.0625": (20, (5, 0), False),
            "6-0, p=0.031": (20, (6, 0), True),
            "7-1, p=0.070": (20, (7, 1), False),
            "8-1, p=0.039": (20, (8, 1), True),
            "0-6, a firm loss": (20, (0, 6), True),
            "0-4, a loss luck explains": (20, (0, 4), False),
        }
        for name, (cases_, signs, firm) in table.items():
            with self.subTest(name):
                low, high = (0.05, 0.2) if signs[0] > signs[1] else (-0.2, -0.05)
                text = compare.verdict(cases_, low, high, 3, signs)
                self.assertEqual(" than A: the interval stays" in text, firm, text)
                if not firm:
                    self.assertIn("sign test", text)

    def test_the_sign_test_is_exact(self):
        table = {(4, 0): 0.125, (0, 4): 0.125, (5, 0): 0.0625, (6, 0): 0.03125, (3, 3): 1.0, (0, 0): 1.0, (8, 1): 0.0390625}
        for (better, worse), want in table.items():
            with self.subTest((better, worse)):
                self.assertAlmostEqual(compare.sign_test_p(better, worse), want)


class CompareFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, *runs: dict) -> Path:
        path = self.base / name
        path.write_text("\n".join(json.dumps(r) for r in runs) + "\n", encoding="utf-8")
        return path

    def compare(self, a: dict, b: dict) -> str:
        return compare.compare_runs(self.write("a.jsonl", a), self.write("b.jsonl", b))

    def test_the_verdict_follows_the_difference_the_cases_and_the_repeats(self):
        base = cases(20, 0.5)
        table = {
            "a clear gain at K=3": (run_of(base), run_of(cases(20, 1.0)), "B is better than A"),
            "the same gain at K=1": (run_of(base, repeat=1), run_of(cases(20, 1.0), repeat=1), "treat it as a lead"),
            "a clear loss at K=3": (run_of(cases(20, 1.0)), run_of(base), "B is worse than A"),
            "the same scores": (run_of(base), run_of(base), "No difference the data can show"),
            "a gain on five cases": (run_of(cases(5, 0.0)), run_of(cases(5, 1.0)), "Too few shared cases"),
            "one case in four better": (run_of(cases(20, 0.5)), run_of(cases(20, 0.5, flip=5)), "difference B - A: +12.5 points"),
        }
        for name, (a, b, want) in table.items():
            with self.subTest(name):
                self.assertIn(want.lower(), self.compare(a, b).lower())

    def test_the_text_names_both_variants_and_the_interval(self):
        text = self.compare(run_of(cases(20, 0.5), model="old"), run_of(cases(20, 1.0), model="new"))
        self.assertIn("A: routing, model old, 2026-11-07T00:00:00Z, K=3, 20 cases", text)
        self.assertIn("B: routing, model new", text)
        self.assertIn("mean pass@1 on the shared cases: A 50.0%, B 100.0%", text)
        self.assertIn("difference B - A: +50.0 points (95% interval +50.0 to +50.0), paired over 20 cases", text)

    def test_only_the_shared_cases_count_and_the_text_says_so(self):
        text = self.compare(run_of(cases(20, 0.0)), run_of({**cases(18, 1.0), "extra": 1.0}))
        self.assertIn("Only 18 case ids are in both runs", text)
        self.assertIn("paired over 18 cases", text)

    def test_four_better_and_none_worse_is_not_called_firm(self):
        text = self.compare(run_of(cases(20, 0.5)), run_of(cases(20, 0.5, flip=4)))
        self.assertNotIn("B is better than A:", text)

    def test_naming_one_file_twice_is_refused_with_the_next_step(self):
        path = self.write("a.jsonl", run_of(cases(12, 0.5)))
        for other in (path, self.base / "." / "a.jsonl"):
            with self.subTest(other=str(other)):
                with self.assertRaisesRegex(ValueError, "named twice.*each variant to its own file with --record"):
                    compare.compare_runs(path, other)

    def test_the_latest_run_in_a_file_is_the_one_compared(self):
        old, new = run_of(cases(20, 0.0), date="2026-11-01T00:00:00Z"), run_of(cases(20, 1.0), date="2026-11-07T00:00:00Z")
        text = compare.compare_runs(self.write("a.jsonl", new, old), self.write("b.jsonl", run_of(cases(20, 1.0))))
        self.assertIn("A 100.0%, B 100.0%", text)

    def test_input_it_cannot_compare_is_an_error_that_says_what_to_do(self):
        empty = self.base / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        good = self.write("good.jsonl", run_of(cases(12, 0.5)))
        table = {
            "another suite": (good, self.write("roles.jsonl", run_of(cases(12, 0.5), suite="roles")), "one suite"),
            "no shared case": (good, self.write("other.jsonl", run_of({"x": 1.0})), "share no case id"),
            "a file with no run": (good, empty, "holds no recorded run"),
        }
        for name, (a, b, want) in table.items():
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, want):
                    compare.compare_runs(a, b)


class CommandTests(unittest.TestCase):
    def test_the_command_prints_the_comparison_and_takes_exactly_two_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a.jsonl"), Path(tmp, "b.jsonl")
            a.write_text(json.dumps(run_of(cases(20, 0.5))) + "\n", encoding="utf-8")
            b.write_text(json.dumps(run_of(cases(20, 1.0))) + "\n", encoding="utf-8")
            code, out = run("eval", "compare", str(a), str(b))
            self.assertEqual(code, 0, out)
            self.assertIn("verdict: B is better than A", out)
            for argv in ((), (str(a),), (str(a), str(b), str(b))):
                with self.subTest(argv=argv):
                    code, out = run("eval", "compare", *argv)
                    self.assertEqual(code, 2, out)
                    self.assertIn("two files of recorded runs", out)

    def test_other_suites_still_refuse_files(self):
        code, out = run("eval", "standards", "x.jsonl")
        self.assertEqual(code, 2, out)
        self.assertIn("`compare` take files", out)


if __name__ == "__main__":
    unittest.main()
