"""Cost per passing trial: an agent command that emits `stream-json` has its tokens and cost recorded per trial.

The fake agent replays a real recorded run (tests/fixtures/live/stream-json-claude-code-2.1.319.jsonl, $0.2059584 and
14 + 1383 tokens) with the answer swapped for a route. No model runs.
"""

import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from helpers import run_cli as run

from aidd.cli.commands import maintain
from aidd.evals import records, suites, transcripts

FIXTURE = ROOT / "tests" / "fixtures" / "live" / "stream-json-claude-code-2.1.319.jsonl"
COST, INPUT, OUTPUT, CACHE = 0.20595839999999999, 14, 1383, 18522 + 150332

STREAM_AGENT = """
import json, re, sys
prompt = sys.stdin.read()
route = re.search(r"ROUTE=(\\w+)", prompt).group(1)
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
last = json.loads(lines[-1])
last["result"] = "Thinking.\\n" + json.dumps({"route": route, "reason": "replayed"})
print("\\n".join(lines[:-1] + [json.dumps(last)]))
"""
SCENARIOS = """
scenario:
  - id: s1
    situation: ROUTE=minor a typo
    expected: {route: minor}
  - id: s2
    situation: ROUTE=major an auth change
    expected: {route: major}
  - id: s3
    situation: ROUTE=normal a new endpoint
    expected: {route: stop}
"""


def stream(result: dict) -> str:
    return "\n".join(json.dumps(e) for e in [{"type": "system", "subtype": "init"}, {"type": "result", **result}])


class AnswerAndUsageTests(unittest.TestCase):
    def test_each_shape_of_output(self):
        usage = {"input_tokens": 3, "output_tokens": 4}
        cases = {
            "plain text": ("route: minor", ("route: minor", None)),
            "a bare JSON answer": ('{"route": "minor"}', ('{"route": "minor"}', None)),
            "a stream with no result event": ('{"type": "system"}', ('{"type": "system"}', None)),
            "a priced result": (
                stream({"result": "ok", "total_cost_usd": 0.5, "usage": usage}),
                ("ok", dict(transcripts.Usage(3, 4, None, None, 0.5).__dict__)),
            ),
            "a result with a subagent": (  # `usage` is the main loop's; `modelUsage` adds the subagent's model
                stream(
                    {
                        "result": "ok",
                        "total_cost_usd": 0.9,
                        "usage": usage,
                        "modelUsage": {"main": {"inputTokens": 3, "outputTokens": 4}, "sub": {"inputTokens": 5, "outputTokens": 6}},
                    }
                ),
                ("ok", dict(transcripts.Usage(8, 10, None, None, 0.9).__dict__)),
            ),
            "a result with no cost": (stream({"result": "ok", "usage": usage}), ("ok", dict(transcripts.Usage(3, 4).__dict__))),
            "a result with no text": (stream({"total_cost_usd": 0.5}), ("", dict(transcripts.Usage(cost_usd=0.5).__dict__))),
            "a result with nothing to count": (stream({"result": "ok"}), ("ok", None)),
        }
        for name, (output, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(transcripts.answer_and_usage(output), want)

    def test_the_recorded_run_gives_its_answer_and_its_cost(self):
        text, used = transcripts.answer_and_usage(FIXTURE.read_text(encoding="utf-8"))
        self.assertIn("PR #12", text)
        self.assertEqual((used["cost_usd"], used["input_tokens"], used["output_tokens"]), (COST, INPUT, OUTPUT))


class CostSummaryTests(unittest.TestCase):
    def test_cost_per_passing_trial(self):
        u = {"cost_usd": 1.0, "input_tokens": 10, "output_tokens": 5}
        cases = {
            "no usage reported": ([{"trials": 2, "passed": 2}], None),
            "every trial priced": ([{"trials": 2, "passed": 1, "usages": [u, u]}, {"trials": 1, "passed": 1, "usages": [u]}], (3.0, 1.5, 2)),
            "none passed": ([{"trials": 2, "passed": 0, "usages": [u, u]}], (2.0, None, 0)),
            "a trial with no usage": ([{"trials": 2, "passed": 2, "usages": [u, None]}], (None, None, 2)),
            "a trial with no cost": ([{"trials": 2, "passed": 2, "usages": [u, {"input_tokens": 1}]}], (None, None, 2)),
        }
        for name, (results, want) in cases.items():
            with self.subTest(name):
                got = suites.cost_summary(results)
                if want is None:
                    self.assertIsNone(got)
                else:
                    self.assertEqual((got["cost_usd"], got["cost_usd_per_pass"], got["passing_trials"]), want)

    def test_a_token_count_that_misses_a_trial_is_none_not_zero(self):
        full = {"cost_usd": 1.0, "input_tokens": 10, "output_tokens": 5}
        cases = {
            "every trial reports": ([full, full], (20, 10)),
            "a trial reports no usage": ([full, None], (None, None)),
            "a trial misses input tokens": ([full, {"cost_usd": 1.0, "output_tokens": 5}], (None, 10)),
        }
        for name, (usages, want) in cases.items():
            with self.subTest(name):
                got = suites.cost_summary([{"trials": 2, "passed": 2, "usages": usages}])
                self.assertEqual((got["input_tokens"], got["output_tokens"]), want)

    def test_the_cost_line_counts_cache_tokens_as_input_and_marks_a_missing_count(self):
        spent = {"cost_usd": 1.0, "cost_usd_per_pass": 0.5, "trials": 2, "passing_trials": 2, "input_tokens": 10, "cache_creation_input_tokens": 100}
        spent |= {"cache_read_input_tokens": 1000, "output_tokens": 5}
        self.assertIn("1110 input tokens (cache included) and 5 output", maintain._cost_line(spent))
        self.assertIn("tokens not reported by every trial", maintain._cost_line(spent | {"cache_read_input_tokens": None}))

    def test_measure_keeps_each_trials_usage(self):
        used = {"cost_usd": 0.5}
        trials = iter([[{"id": "a", "ok": True, "usage": used}], [{"id": "a", "ok": False}]])
        (r,) = suites.measure(lambda: next(trials), 2)
        self.assertEqual((r["usages"], "usage" in r), ([used, None], False))
        (plain,) = suites.measure(lambda: [{"id": "a", "ok": True}], 1)
        self.assertNotIn("usages", plain)

    def test_the_report_shows_the_cost_per_pass_only_when_the_run_has_one(self):
        base = {"suite": "routing", "date": "2026-11-07T00:00:00Z", "mean_pass_at_1": 1.0, "scenarios": []}
        rows = records.report_markdown([base | {"cost": {"cost_usd_per_pass": 0.25}}, base]).splitlines()
        self.assertIn("$ per pass", rows[0])
        cells = [[c.strip() for c in row.strip("|").split("|")] for row in rows]
        column = cells[0].index("$ per pass")
        self.assertEqual((cells[2][column], cells[3][column]), ("$0.2500", ""))


class StreamRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "routing").mkdir()
        (base / "routing" / "scenarios.yaml").write_text(SCENARIOS, encoding="utf-8")
        (base / "agent.py").write_text(STREAM_AGENT, encoding="utf-8")
        self.cmd = shlex.join([sys.executable, str(base / "agent.py"), str(FIXTURE)])
        self.record = base / "runs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def routing(self, *extra: str) -> tuple[int, str, dict]:
        argv = ["routing", "--scenarios", str(Path(self.tmp.name) / "routing"), "--agent-command", self.cmd, "--record", str(self.record), *extra]
        code, out = run("eval", *argv)
        (line,) = [json.loads(x) for x in self.record.read_text(encoding="utf-8").splitlines()]
        self.record.unlink()
        return code, out, line

    def test_a_stream_run_is_scored_on_its_answer_and_records_tokens_and_cost_per_trial(self):
        code, out, line = self.routing("--min-accuracy", "0")
        self.assertEqual(code, 0, out)
        self.assertEqual([s["pass_all"] for s in line["scenarios"]], [True, True, False])
        usages = [s["usages"] for s in line["scenarios"]]
        self.assertTrue(all(len(u) == 1 and u[0]["cost_usd"] == COST and u[0]["output_tokens"] == OUTPUT for u in usages))
        cost = line["cost"]
        self.assertAlmostEqual(cost["cost_usd"], 3 * COST)
        self.assertAlmostEqual(cost["cost_usd_per_pass"], 3 * COST / 2)
        self.assertEqual((cost["trials"], cost["passing_trials"], cost["input_tokens"], cost["output_tokens"]), (3, 2, 3 * INPUT, 3 * OUTPUT))
        self.assertIn(
            f"cost: ${3 * COST:.4f} over 3 trial(s); ${3 * COST / 2:.4f} per passing trial; {3 * (INPUT + CACHE)} input tokens (cache included) and {3 * OUTPUT} output",
            out,
        )

    def test_repeats_count_every_trial_and_a_run_with_no_pass_has_no_cost_per_pass(self):
        code, out, line = self.routing("--min-accuracy", "0", "--repeat", "2", "--case", "s3")
        self.assertEqual(code, 0, out)
        self.assertEqual((line["cost"]["trials"], line["cost"]["passing_trials"], line["cost"]["cost_usd_per_pass"]), (2, 0, None))
        self.assertAlmostEqual(line["cost"]["cost_usd"], 2 * COST)
        self.assertIn("no trial passed, so no cost per pass", out)

    def test_an_agent_command_that_prints_plain_text_records_no_cost(self):
        base = Path(self.tmp.name)
        (base / "plain.py").write_text('print(\'{"route": "minor", "reason": "x"}\')\n', encoding="utf-8")
        self.cmd = shlex.join([sys.executable, str(base / "plain.py")])
        code, out, line = self.routing("--min-accuracy", "0", "--case", "s1")
        self.assertEqual(code, 0, out)
        self.assertIsNone(line["cost"])
        self.assertNotIn("usages", line["scenarios"][0])
        self.assertNotIn("cost:", out)


if __name__ == "__main__":
    unittest.main()
