"""The agent evals as measurements: repeated trials (pass@1, pass^K), a no-skill control (the lift), and recorded runs."""

import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git
from helpers import run_cli as run

from aidd import __version__, evals, gitutil, resources

# Answers the route named in the situation, but only when the prompt carries the skill's reference;
# without it (the control) it always says "normal". A FLAKY scenario fails its first trial only.
ROUTING_AGENT = """
import json, pathlib, re, sys
prompt = sys.stdin.read()
state = pathlib.Path(sys.argv[1])
route = re.search(r"ROUTE=(\\w+)", prompt).group(1) if "Reference:" in prompt else "normal"
if "FLAKY" in prompt and "Reference:" in prompt:
    n = int(state.read_text()) if state.exists() else 0
    state.write_text(str(n + 1))
    if n == 0:
        route = "stop"
print("thinking...")
print(json.dumps({"route": route, "reason": "fake"}))
"""

# Saves each prompt it receives, as bytes, in the directory it is given, and answers a route.
CAPTURE_AGENT = """
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
out.mkdir(exist_ok=True)
(out / f"{len(list(out.iterdir())):03d}.txt").write_bytes(sys.stdin.buffer.read())
print(json.dumps({"route": "minor", "reason": "captured"}))
"""

ROUTING_SCENARIOS = """
[[scenario]]
id = "s1"
situation = "ROUTE=minor a typo"
expected = { route = "minor" }

[[scenario]]
id = "s2"
judgment = "flaky on purpose"
situation = "ROUTE=normal FLAKY a new endpoint"
expected = { route = "normal" }

[[scenario]]
id = "s3"
situation = "ROUTE=major an auth change"
expected = { route = "major" }
"""

# Finds the defect only with its playbook in the prompt; without it (the control) it only signs off.
ROLE_AGENT = """
import sys
prompt = sys.stdin.read()
if "## Playbook" in prompt:
    print("Found an injection in the query.")
print("Done: reviewed\\nNext: fix\\nNeeds: nothing\\nStopped at: review")
"""

ROLE_SCENARIOS = """
[[scenario]]
id = "r1"
role = "reviewer"
prompt = "Review this diff."
fixture = "query = 'SELECT * FROM t WHERE id = ' + user_id"
expected = { require = ["injection", "Stopped at"] }
"""


class MeasureTests(unittest.TestCase):
    def test_trials_fold_into_pass_at_1_and_pass_k(self):
        trials = iter(
            [
                [{"id": "a", "ok": True}, {"id": "b", "ok": False, "misses": ["first"]}],
                [{"id": "a", "ok": True}, {"id": "b", "ok": True}],
                [{"id": "a", "ok": True}, {"id": "b", "ok": False, "misses": ["third"]}],
                [{"id": "a", "ok": True}, {"id": "b", "ok": True}],
            ]
        )
        a, b = evals.measure(lambda: next(trials), 4)
        self.assertEqual((a["passed"], a["pass_at_1"], a["pass_all"], a["ok"]), (4, 1.0, True, True))
        self.assertEqual((b["passed"], b["pass_at_1"], b["pass_all"], b["ok"]), (2, 0.5, False, False))
        self.assertEqual(b["misses"], ["third"], "a result shows its last failing trial")
        self.assertEqual(evals.summary([a, b]), {"mean_pass_at_1": 0.75, "pass_k_share": 0.5})

    def test_one_trial_reads_as_before(self):
        (r,) = evals.measure(lambda: [{"id": "a", "ok": False, "got": "minor"}], 1)
        self.assertEqual((r["ok"], r["pass_at_1"], r["answers"]), (False, 0.0, ["minor"]))
        with self.assertRaises(ValueError):
            evals.measure(lambda: [], 0)

    def test_the_record_is_stamped_in_utc_and_never_guesses_a_model(self):
        results = evals.measure(lambda: [{"id": "a", "ok": True}], 1)
        line = evals.record_line(
            suite="roles",
            cmd="x",
            model=None,
            repeat=1,
            results=results,
            threshold=0.8,
            now=dt.datetime(2026, 9, 28, 14, 0, tzinfo=dt.timezone(dt.timedelta(hours=7))),
        )
        self.assertEqual(line["date"], "2026-09-28T07:00:00Z")
        self.assertIsNone(line["model"])
        self.assertIsNone(line["control"])
        self.assertIsNone(line["lift"])


class AgentSuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.routing, self.roles = base / "routing", base / "roles"
        self.routing.mkdir()
        self.roles.mkdir()
        (self.routing / "scenarios.toml").write_text(ROUTING_SCENARIOS, encoding="utf-8")
        (self.roles / "scenarios.toml").write_text(ROLE_SCENARIOS, encoding="utf-8")
        (base / "routing_agent.py").write_text(ROUTING_AGENT, encoding="utf-8")
        (base / "role_agent.py").write_text(ROLE_AGENT, encoding="utf-8")
        self.state = base / "flaky-count"
        self.routing_cmd = shlex.join([sys.executable, str(base / "routing_agent.py"), str(self.state)])
        self.role_cmd = shlex.join([sys.executable, str(base / "role_agent.py")])
        self.record = base / "out" / "evals-results.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def routing_eval(self, *extra: str) -> tuple[int, str]:
        return run("eval", "routing", "--scenarios", str(self.routing), "--cmd", self.routing_cmd, *extra)

    def recorded(self, suite_args: list[str], *extra: str) -> tuple[int, str, dict]:
        """Run an agent suite with --record into a fresh file: (exit code, output, the recorded run)."""
        record = Path(self.tmp.name) / f"run-{len(list(Path(self.tmp.name).glob('run-*')))}.jsonl"
        code, out = run("eval", *suite_args, "--record", str(record), *extra)
        (line,) = [json.loads(x) for x in record.read_text(encoding="utf-8").splitlines()]
        return code, out, line

    def routing_run(self, *extra: str) -> tuple[int, str, dict]:
        return self.recorded(["routing", "--scenarios", str(self.routing), "--cmd", self.routing_cmd], *extra)

    @staticmethod
    def scenario(line: dict, sid: str) -> dict:
        return next(s for s in line["scenarios"] if s["id"] == sid)

    def test_one_trial_keeps_the_old_accuracy_and_threshold(self):
        code, out, line = self.routing_run("--min-accuracy", "0.6")
        self.assertEqual(code, 0, out)
        self.assertAlmostEqual(line["mean_pass_at_1"], 2 / 3)
        self.assertEqual((line["repeat"], line["threshold"], line["passed"]), (1, 0.6, True))
        self.assertEqual((self.scenario(line, "s2")["passed"], self.scenario(line, "s2")["answers"]), (0, ["stop"]))
        self.assertIn("accuracy 66.7% over 3 scenario(s); threshold 60%", out)  # the one check on the single-trial format
        self.state.unlink()
        self.assertEqual(self.routing_eval("--min-accuracy", "0.9")[0], 1)

    def test_repeats_report_pass_at_1_and_pass_k_and_gate_on_mean_pass_at_1(self):
        code, out, line = self.routing_run("--repeat", "3", "--min-accuracy", "0.85")
        self.assertEqual(code, 0, out)
        self.assertEqual(
            [(s["id"], s["trials"], s["passed"], s["pass_all"]) for s in line["scenarios"]], [("s1", 3, 3, True), ("s2", 3, 2, False), ("s3", 3, 3, True)]
        )
        self.assertAlmostEqual(line["mean_pass_at_1"], 8 / 9)
        self.assertAlmostEqual(line["pass_k_share"], 2 / 3)
        judged = [s for s in line["scenarios"] if s.get("judgment")]
        self.assertEqual([(s["id"], round(s["pass_at_1"], 3)) for s in judged], [("s2", 0.667)])  # the judgment-only mean
        self.assertIn("mean pass@1 88.9% over 3 scenario(s), 3 trials each; pass^3 66.7%", out)  # the one check on the repeat format
        self.state.unlink()
        self.assertEqual(self.routing_eval("--repeat", "3", "--min-accuracy", "0.9")[0], 1, "8/9 is below 0.9")

    def test_the_control_reports_the_lift_and_never_gates(self):
        code, out, line = self.routing_run("--repeat", "3", "--control", "--min-accuracy", "0.85")
        self.assertEqual(code, 0, out)
        # Without the reference the agent says "normal" everywhere: one of three scenarios.
        self.assertAlmostEqual(line["control"]["mean_pass_at_1"], 1 / 3)
        self.assertAlmostEqual(line["lift"], 8 / 9 - 1 / 3)
        self.assertIn("lift +55.6 points", out)  # the one check on the control format
        code, out, line = self.recorded(["roles", "--scenarios", str(self.roles), "--cmd", self.role_cmd, "--control"], "--min-accuracy", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual((line["mean_pass_at_1"], line["control"]["mean_pass_at_1"], line["lift"]), (1.0, 0.0, 1.0))

    def test_the_control_prompts_carry_no_aidd_material(self):
        seen = Path(self.tmp.name) / "prompts"
        spy = Path(self.tmp.name) / "spy.py"
        spy.write_text(f"import sys\nwith open({str(seen)!r}, 'a') as f:\n    f.write(sys.stdin.read() + '\\n=====\\n')\n", encoding="utf-8")
        cmd = shlex.join([sys.executable, str(spy)])
        evals.run_routing(self.routing, cmd, material=False)
        evals.run_roles(self.roles, cmd, material=False)
        text = seen.read_text(encoding="utf-8")
        for marker in ("Reference:", "Use the aidd skill", "## Playbook", "loop contract", evals.reference_text()[:200]):
            self.assertNotIn(marker, text)

    def test_every_run_appends_one_json_line_and_the_report_reads_them(self):
        self.routing_eval("--repeat", "3", "--control", "--record", str(self.record), "--model-label", "fake-model-1", "--min-accuracy", "0.85")
        run("eval", "roles", "--scenarios", str(self.roles), "--cmd", self.role_cmd, "--record", str(self.record))
        lines = [json.loads(x) for x in self.record.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["suite"] for x in lines], ["routing", "roles"])
        routing, roles = lines
        self.assertEqual(routing["aidd_version"], __version__)
        self.assertEqual((routing["cmd"], routing["model"], routing["repeat"]), (self.routing_cmd, "fake-model-1", 3))
        self.assertTrue(routing["date"].endswith("Z"))
        dt.datetime.fromisoformat(routing["date"].replace("Z", "+00:00"))
        self.assertAlmostEqual(routing["mean_pass_at_1"], 8 / 9)
        self.assertAlmostEqual(routing["pass_k_share"], 2 / 3)
        self.assertAlmostEqual(routing["control"]["mean_pass_at_1"], 1 / 3)
        self.assertAlmostEqual(routing["lift"], 8 / 9 - 1 / 3)
        self.assertEqual((routing["threshold"], routing["passed"], routing["options"]), (0.85, True, {"embed": True}))
        s2 = next(s for s in routing["scenarios"] if s["id"] == "s2")
        self.assertEqual((s2["trials"], s2["passed"], s2["pass_all"], s2["answers"], s2["control_pass_at_1"]), (3, 2, False, ["stop", "normal", "normal"], 1.0))
        self.assertIsNone(roles["model"], "a model is recorded only when --model-label names it")
        self.assertIsNone(roles["lift"])

        code, out = run("eval", "report", str(self.record))
        self.assertEqual(code, 0, out)
        table = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in out.strip().splitlines()]
        header, rule, *rows = table
        self.assertEqual(set("".join(rule)), {"-"} | ({":"} if ":" in "".join(rule) else set()))
        self.assertEqual(len(rows), 2)
        by_suite = {row[header.index("Suite")]: dict(zip(header, row, strict=True)) for row in rows}
        self.assertEqual(by_suite["routing"]["Model"], "fake-model-1")
        self.assertEqual(by_suite["roles"]["Model"], "(not given)")
        self.assertIn("88.9%", by_suite["routing"].values())
        self.assertIn("+55.6 pts", by_suite["routing"].values())

    def report_rows(self, *paths: Path) -> tuple[str, list[dict]]:
        """`aidd eval report` on these files: its whole output and each table row as {column: cell}."""
        code, out = run("eval", "report", *map(str, paths))
        self.assertEqual(code, 0, out)
        table = [ln for ln in out.splitlines() if ln.startswith("|")]
        header = [c.strip() for c in table[0].strip("|").split("|")]
        return out, [dict(zip(header, [c.strip() for c in r.strip("|").split("|")], strict=True)) for r in table[2:]]

    def in_directory(self, path: Path) -> None:
        here = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, here)

    def git_repo(self) -> Path:
        """A committed repository with the routing and roles cases under evals/, the fake agents, and a subdirectory."""
        repo = Path(self.tmp.name) / "repo"
        shutil.copytree(self.routing, repo / "evals" / "routing")
        shutil.copytree(self.roles, repo / "evals" / "roles")
        (repo / "sub").mkdir()
        (repo / "sub" / "routing_agent.py").write_text(ROUTING_AGENT, encoding="utf-8")
        (repo / "sub" / "role_agent.py").write_text(ROLE_AGENT, encoding="utf-8")
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "day 0")
        return repo

    @staticmethod
    def records(path: Path) -> list[dict]:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]

    def test_the_stored_material_is_the_hash_of_what_the_agent_received(self):
        prompts = Path(self.tmp.name) / "prompts"
        agent = Path(self.tmp.name) / "capture_agent.py"
        agent.write_text(CAPTURE_AGENT, encoding="utf-8")
        run("eval", "routing", "--scenarios", str(self.routing), "--cmd", shlex.join([sys.executable, str(agent), str(prompts)]), "--record", str(self.record))
        (line,) = self.records(self.record)
        received = [p.read_bytes() for p in sorted(prompts.iterdir())]
        self.assertEqual(len(received), 3, "one prompt per scenario, one trial, no control")
        digest = hashlib.sha256()
        framed = [("case", p.name, p.read_bytes()) for p in sorted(self.routing.glob("*.toml"))] + [("prompt", "", x) for x in received]
        for kind, name, data in framed:
            digest.update(f"{kind}\0{name}\0{len(data)}\0".encode())
            digest.update(data)
        self.assertEqual(line["material_sha256"], digest.hexdigest())

    def test_a_changed_case_file_or_prompt_makes_the_row_stale(self):
        repo = self.git_repo()
        record = repo / "evals" / "runs.jsonl"
        run("eval", "routing", "--scenarios", str(repo / "evals" / "routing"), "--cmd", self.routing_cmd, "--record", str(record))
        run("eval", "roles", "--scenarios", str(repo / "evals" / "roles"), "--cmd", self.role_cmd, "--record", str(record))
        out, rows = self.report_rows(record)
        self.assertEqual([r["Material"] for r in rows], ["fresh", "fresh"])
        self.assertNotIn("stale", out)
        before = evals.material_sha256("roles", repo / "evals" / "roles")
        with mock.patch.object(evals, "ROLE_PROMPT", evals.ROLE_PROMPT + "One more line.\n"):
            self.assertNotEqual(evals.material_sha256("roles", repo / "evals" / "roles"), before, "a changed prompt changes the material")
        with (repo / "evals" / "routing" / "scenarios.toml").open("a", encoding="utf-8") as f:
            f.write("# an edited case file\n")
        out, rows = self.report_rows(record)
        self.assertEqual({r["Suite"]: r["Material"] for r in rows}, {"routing": "stale", "roles": "fresh"})
        self.assertIn("stale", out.split("\n\n", 1)[1], "the output says what a stale row means, below the table")

    def test_no_record_holds_an_absolute_path(self):
        repo = self.git_repo()
        self.in_directory(repo / "sub")
        record = Path("..") / "evals" / "runs.jsonl"
        routing_cmd, role_cmd = "python3 routing_agent.py state", "python3 role_agent.py"
        run("eval", "routing", "--scenarios", str((repo / "evals" / "routing").resolve()), "--cmd", routing_cmd, "--record", str(record))
        run("eval", "routing", "--root", "..", "--cmd", routing_cmd, "--record", str(record))
        run("eval", "roles", "--root", "..", "--cmd", role_cmd, "--record", str(record))
        run("eval", "routing", "--scenarios", str(self.routing), "--cmd", routing_cmd, "--record", str(record))
        lines = self.records(record)
        self.assertEqual([x["cases"] for x in lines], ["evals/routing", "evals/routing", "evals/roles", None], "cases outside git are not recorded")

        def strings(x):
            if isinstance(x, dict):
                return [s for v in x.values() for s in strings(v)]
            if isinstance(x, list):
                return [s for v in x for s in strings(v)]
            return [x] if isinstance(x, str) else []

        for line in lines:
            for value in strings(line):
                self.assertFalse(Path(value).is_absolute(), value)
            for where in {self.tmp.name, str(Path(self.tmp.name).resolve()), str(Path.home())}:
                self.assertNotIn(where, json.dumps(line))
        _, rows = self.report_rows(record)
        self.assertEqual([r["Material"] for r in rows], ["fresh", "fresh", "fresh", "unknown"])

    def test_the_head_names_the_repository_that_holds_the_material(self):
        self.routing_eval("--record", str(self.record))
        with mock.patch.object(resources, "repo_root", return_value=None):  # a wheel or zipapp install: no checkout to name
            self.routing_eval("--record", str(self.record))
        source, wheel = self.records(self.record)
        root = resources.repo_root()
        self.assertEqual(source["head"], git(root, "rev-parse", "HEAD") if root else None)
        self.assertIsNone(source["dirty"], "the cases are outside aidd's checkout, so its head cannot show them")
        self.assertEqual((wheel["head"], wheel["dirty"]), (None, None))
        with mock.patch.object(gitutil, "run", side_effect=OSError("no git")):
            self.assertIsNone(evals.head_sha(Path(".")))

    def test_dirty_says_whether_the_head_holds_the_hashed_files(self):
        repo = self.git_repo()
        case = repo / "evals" / "routing" / "scenarios.toml"
        head = git(repo, "rev-parse", "HEAD")
        self.assertEqual(evals.repo_state(repo, [case]), (head, False))
        with case.open("a", encoding="utf-8") as f:
            f.write("# edited\n")
        self.assertEqual(evals.repo_state(repo, [case]), (head, True))
        git(repo, "checkout", "-q", "--", str(case))
        (repo / "sub" / "role_agent.py").write_text("# the configuration changed\n", encoding="utf-8")
        self.assertEqual(evals.repo_state(repo, [case]), (head, False), "only the hashed files count")
        self.assertEqual(evals.repo_state(repo, [case], all_tracked=True), (head, True), "a tasks run counts every tracked file")
        git(repo, "checkout", "-q", "--", "sub/role_agent.py")
        log = repo / "evals" / "runs.jsonl"
        log.write_text("{}\n", encoding="utf-8")
        git(repo, "add", "evals/runs.jsonl")
        git(repo, "commit", "-qm", "log")
        head = git(repo, "rev-parse", "HEAD")
        with log.open("a", encoding="utf-8") as f:
            f.write("{}\n")
        self.assertEqual(evals.repo_state(repo, [case], all_tracked=True, ignore=log), (head, False), "a new record line is not a change")
        self.assertEqual(evals.repo_state(repo, [case], all_tracked=True), (head, True))
        git(repo, "checkout", "-q", "--", "evals/runs.jsonl")
        git(repo, "checkout", "-q", "--", "sub/role_agent.py")
        new = repo / "evals" / "routing" / "more.toml"
        new.write_text("", encoding="utf-8")
        self.assertEqual(evals.repo_state(repo, [case, new]), (head, True), "an uncommitted case file is not in the head")
        self.assertEqual(evals.repo_state(repo, [case, self.routing / "scenarios.toml"]), (head, None), "a file outside the repository")
        self.assertEqual(evals.repo_state(Path(self.tmp.name), [self.routing / "scenarios.toml"]), (None, None), "outside git")
        self.assertEqual(evals.repo_state(None, [case]), (None, None))

    def test_an_old_record_without_the_fields_is_unknown_never_fresh(self):
        repo = self.git_repo()
        record = repo / "evals" / "runs.jsonl"
        run("eval", "routing", "--scenarios", str(repo / "evals" / "routing"), "--cmd", self.routing_cmd, "--record", str(record))
        (line,) = self.records(record)
        old = {k: v for k, v in line.items() if k not in ("head", "dirty", "material_sha256", "cases")}
        gone = dict(line, cases="evals/no-such-dir")
        escapes = dict(line, cases=os.path.relpath(self.routing, repo))  # the same cases, but outside the repository
        older = record.with_name("older.jsonl")
        older.write_text("".join(json.dumps(x) + "\n" for x in (old, gone, escapes)), encoding="utf-8")
        outside = self.record.with_name("outside.jsonl")
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text(json.dumps(line) + "\n", encoding="utf-8")
        out, rows = self.report_rows(older, outside)
        self.assertEqual([r["Material"] for r in rows], ["unknown"] * 4)
        self.assertNotIn("fresh", out)

    def test_misuse_is_an_error_not_a_decision(self):
        self.record.parent.mkdir()
        self.record.write_text('{"not": "a run"}\n', encoding="utf-8")
        self.assertEqual(run("eval", "report", str(self.record))[0], 2)
        self.assertEqual(run("eval", "report")[0], 2)
        self.assertEqual(self.routing_eval("--repeat", "0")[0], 2)
        self.assertEqual(run("eval", "examples", "--control")[0], 2)
        self.assertEqual(run("eval", "standards", "--record", str(self.record))[0], 2)
        self.assertEqual(run("eval", "routing", "stray.jsonl", "--cmd", self.routing_cmd)[0], 2)


if __name__ == "__main__":
    unittest.main()
