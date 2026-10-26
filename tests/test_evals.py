"""The evals: the role scenarios and their scorer, the standards registry check, the evals workflow, and your own agent tasks."""

import contextlib
import datetime as dt
import io
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.evals import suites
from aidd.evals import standards_audit
from aidd.knowledge import standards_evidence, team_registry
from aidd.kernel import resources


def echo_agent(directory) -> tuple[str, Path]:
    """An agent that answers with its prompt (what `cat` does, on any OS) and counts its runs in a file: (command, counter)."""
    counter = Path(directory) / "echo-runs"
    script = Path(directory) / "echo_agent.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\nwith open(sys.argv[1], 'a', encoding='utf-8') as fh:\n    fh.write('ran\\n')\n",
        encoding="utf-8",
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} {shlex.quote(str(counter))}", counter


def runs(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8").splitlines()) if counter.exists() else 0


class RoleEvalTests(unittest.TestCase):
    def test_scenarios_name_real_roles_and_score_shapes(self):
        scenarios = suites.load_scenarios(ROOT / "evals" / "roles")
        self.assertGreaterEqual(len(scenarios), 6)
        roles = set(team_registry.roles()["roles"])
        for sc in scenarios:
            self.assertIn(sc["role"], roles, sc["id"])
            self.assertTrue(sc["prompt"] and sc["fixture"], sc["id"])
            self.assertTrue(set(sc["expected"]) <= {"require", "require_any", "forbid"}, sc["id"])
            for line in ("Stopped at", "Spend"):
                self.assertIn(line, sc["expected"].get("require", []), sc["id"])
        self.assertEqual(len({sc["id"] for sc in scenarios}), len(scenarios))

    def test_scorer(self):
        expected = {"require": ["Done"], "require_any": [["injection", "parameterized"]], "forbid": ["-def keep_me"]}
        self.assertEqual(suites.score_role("SQL injection at line 2.\nDone: report", expected), (True, []))
        ok, misses = suites.score_role("looks fine\n-def keep_me", expected)
        self.assertFalse(ok)
        self.assertEqual(len(misses), 3)

    def test_prompt_carries_the_playbook_and_a_fake_agent_is_scored(self):
        text = suites.role_playbook("reviewer")
        self.assertNotIn("\nname: reviewer", text)
        self.assertIn("## Playbook", text)
        with tempfile.TemporaryDirectory() as d:
            agent, counter = echo_agent(d)
            results = suites.run_roles(ROOT / "evals" / "roles", agent)
            self.assertEqual(runs(counter), len(results))  # the agent really ran, once per scenario
        self.assertEqual([r["id"] for r in results], [sc["id"] for sc in suites.load_scenarios(ROOT / "evals" / "roles")])
        # An agent that only echoes the prompt back scores nothing: copied lines do not count.
        self.assertFalse(any(r["ok"] for r in results))
        self.assertEqual(suites.own_words("kept\ncopied line\n", "copied line\nother"), "kept")


class RoutingLabelTests(unittest.TestCase):
    def test_every_path_scenario_expects_the_route_the_gate_requires(self):
        """A label must agree with the rules, or the eval would reward the agent for a wrong route."""
        from aidd import config
        from aidd.gate import routing

        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')
        checked = 0
        for sc in suites.load_scenarios(ROOT / "evals" / "routing"):
            if "paths" not in sc or sc.get("judgment"):
                continue
            got = routing.assess_route(
                paths=sc["paths"],
                cfg=cfg,
                ctype=sc["type"],
                risk={"dimensions": [], "reversible": True},
                confidence="high",
                task_count=1,
                changed_lines=sc["lines"],
                # A dependency the change adds to a manifest (`manifest:name`), which a rule may name.
                dependencies=[dict(zip(("file", "name"), d.split(":", 1), strict=True)) for d in sc.get("dependencies", [])],
            ).required_route
            self.assertEqual(got, sc["expected"]["route"], sc["id"])
            self.assertEqual(suites.gate_route(sc), got, sc["id"])  # the library function the eval and `aidd gate --paths` use
            checked += 1
        self.assertGreaterEqual(checked, 15)


class StandardsProvenanceTests(unittest.TestCase):
    def test_an_entry_shared_by_roles_counts_once_and_evidence_is_not_bulk(self):
        from unittest import mock

        entries = [dict(id="asvs", checked="2026-09-25", where=f"role r{i}") for i in range(30)]
        quote = "Use human-in-the-loop control to require a human to approve high-impact actions before they are taken."
        evidence = {"url": "https://genai.owasp.org/download/56857/", "quote": quote}
        entries += [dict(id=f"s{i}", checked="2026-09-25", where="role x", evidence=evidence) for i in range(30)]
        with mock.patch.object(standards_evidence, "dated_entries", lambda: entries):
            self.assertEqual(standards_audit.bulk_checked_dates(threshold=1), [])

    def test_a_versioned_entry_without_a_source_is_reported(self):
        from unittest import mock

        table = {"x": {"name": "X", "edition": "2.0", "checked": "2026-09-25"}, "y": {"name": "Y", "notes": "a practice", "checked": "2026-09-25"}}
        with mock.patch("aidd.kernel.resources.load_json", lambda name: {"standards": table}):
            self.assertEqual([s["id"] for s in standards_audit.unsourced_standards()], ["x"])

    def test_the_registry_has_no_unsourced_edition(self):
        self.assertEqual(standards_audit.unsourced_standards(), [])


class EvalsWorkflowTests(unittest.TestCase):
    """The agent evals run on a schedule and by hand, and their pass rates decide the check; a pull request that changes
    what the agents read triggers the workflow, which measures nothing, since its code must never run with the key."""

    def setUp(self):
        self.text = (ROOT / ".github" / "workflows" / "evals.yml").read_text(encoding="utf-8")

    def test_agent_configuration_changes_trigger_the_evals(self):
        on = self.text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        for trigger in ("schedule:", "workflow_dispatch:", "pull_request:"):
            self.assertIn(trigger, on)
        self.assertNotIn("pull_request_target", self.text)
        for path in (".agents/**", "plugins/**", "schemas/roles.json", "evals/**", "AGENTS.md"):
            self.assertIn(f'- "{path}"', on, path)

    def test_the_key_stays_in_the_environment_and_no_pull_request_reads_it(self):
        self.assertIn("'evals'", self.text.split("environment:", 1)[1].splitlines()[0])
        # Neither a fork's pull request nor this repository's own gets the environment or the key: its code would run
        # with it (tests/test_release_surface.py pins every step that names the secret).
        self.assertIn("environment: ${{ github.event_name != 'pull_request' && 'evals' || '' }}", self.text)
        self.assertIn("HAS_KEY: ${{ github.event_name != 'pull_request' && secrets.ANTHROPIC_API_KEY != '' }}", self.text)
        self.assertIn("if: env.HAS_KEY != 'true'", self.text)
        # The thresholds are the merge check: both agent suites fail below their floor.
        self.assertIn('aidd eval routing --agent-command "claude -p" --min-accuracy', self.text)
        self.assertIn('aidd eval roles --agent-command "claude -p" --min-accuracy', self.text)
        # The calendar check never turns an unrelated pull request red.
        currency = self.text.split("name: Standards currency", 1)[1].split("- ", 1)[0]
        self.assertIn("github.event_name != 'pull_request'", currency)

    def test_the_schedule_measures_and_keeps_every_run(self):
        for suite in ("Routing eval", "Role evals"):
            step = self.text.split(f"name: {suite}", 1)[1].split("\n      - ", 1)[0]
            self.assertIn("measure=(--repeat 3 --without-aidd --record evals-results.jsonl)", step, suite)
            # A pull request runs no live agent, so nothing measures it by a cheaper trial.
            self.assertNotIn("GITHUB_EVENT_NAME", step, suite)
            self.assertIn('"${measure[@]}"', step, suite)
        keep = self.text.split("name: Keep the recorded runs", 1)[1]
        self.assertIn("actions/upload-artifact@", keep)
        self.assertIn("path: evals-results.jsonl", keep)
        self.assertIn("always()", keep.split("\n", 2)[1])


class StandardsEvalTests(unittest.TestCase):
    def test_every_entry_is_dated_and_none_is_stale(self):
        entries = standards_evidence.dated_entries()
        self.assertTrue(all(standards_evidence.dated_on(s) for s in entries))
        # Measured from the newest check, not today: a unit test must not turn red on a calendar date.
        # Currency against today's date runs weekly in .github/workflows/evals.yml.
        newest = max(dt.date.fromisoformat(standards_evidence.dated_on(s)) for s in entries)
        self.assertEqual(standards_evidence.stale_standards(newest), [])
        self.assertEqual({s["where"].split()[0] for s in entries}, {"role", "domain", "extension", "practice"})


FAKE_AGENT = """
import pathlib, sys
sys.stdin.read()
calc = pathlib.Path("eval-fixture/calc.py")
if calc.exists():
    calc.write_text("def add(a, b):\\n    return a + b\\n")
print("That change is major: a specialist approver from the security pool must approve it, and Merge approval is a human decision.")
"""


@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git and sh are required")
class TaskEvalTests(unittest.TestCase):
    """`aidd eval tasks`: an adopter's own tasks, each in a scratch worktree, graded by commands."""

    TEMPLATE = resources.data_dir("templates") / "evals"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        for args in (
            ["init", "-q", "-b", "main"],
            ["config", "user.email", "a@example.com"],
            ["config", "user.name", "A"],
            ["config", "commit.gpgsign", "false"],
        ):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        (self.repo / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "day 0"], cwd=self.repo, check=True, capture_output=True)
        shutil.copytree(self.TEMPLATE / "tasks", self.repo / "evals" / "tasks")
        self.agent = Path(self.tmp.name) / "agent.py"
        self.agent.write_text(FAKE_AGENT, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_template_is_valid_and_documents_incidents(self):
        tasks = suites.load_scenarios(self.TEMPLATE / "tasks")
        self.assertGreaterEqual(len(tasks), 2)
        self.assertEqual([p for t in tasks for p in suites.task_problems(t)], [])
        self.assertTrue(all(t.get("source") for t in tasks))
        readme = (self.TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("Every incident becomes an eval", readme)
        self.assertIn("20 to 50 real tasks", readme)

    def test_a_good_agent_passes_and_the_checkout_is_untouched(self):
        results = suites.run_tasks(self.repo / "evals" / "tasks", f"{sys.executable} {self.agent}", repo=self.repo)
        self.assertEqual([(r["id"], r["misses"]) for r in results if not r["ok"]], [])
        self.assertFalse((self.repo / "eval-fixture").exists(), "the agent must work in a scratch worktree")
        listed = subprocess.run(["git", "worktree", "list"], cwd=self.repo, capture_output=True, text=True, encoding="utf-8").stdout
        self.assertEqual(len(listed.strip().splitlines()), 1, "the scratch worktree must be removed")

    def test_an_echoing_agent_fails_every_task(self):
        agent, counter = echo_agent(self.tmp.name)
        results = suites.run_tasks(self.repo / "evals" / "tasks", agent, repo=self.repo)
        self.assertEqual(runs(counter), len(results))
        self.assertFalse(any(r["ok"] for r in results))
        weakened = next(r for r in results if r["id"].startswith("t03"))
        self.assertTrue(any("the bug is fixed" in m for m in weakened["misses"]))

    def test_uncommitted_changes_to_tracked_files_are_evaluated(self):
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        task = "scenario:\n  - id: sees-the-change\n    prompt: x\n    checks: [{run: [grep, -q, changed, README.md]}]\n"
        (self.repo / "evals" / "tasks" / "examples.yaml").write_text(task, encoding="utf-8")
        agent, counter = echo_agent(self.tmp.name)
        self.assertTrue(suites.run_tasks(self.repo / "evals" / "tasks", agent, repo=self.repo)[0]["ok"])
        self.assertEqual(runs(counter), 1)

    def test_a_task_without_a_grade_or_with_a_shell_string_is_rejected(self):
        self.assertTrue(suites.task_problems({"id": "a", "prompt": "p"}))
        self.assertTrue(suites.task_problems({"id": "a", "prompt": "p", "checks": [{"run": "npm test"}]}))
        self.assertTrue(suites.task_problems({"id": "a", "prompt": "p", "checks": [{"run": ["true"]}], "bogus": 1}))
        self.assertEqual(suites.task_problems({"id": "a", "prompt": "p", "checks": [{"run": ["true"]}]}), [])

    def test_the_cli_points_at_the_template_when_there_are_no_tasks(self):
        from aidd.cli import app

        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        agent, counter = echo_agent(self.tmp.name)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(app.main(["eval", "tasks", "--agent-command", agent, "--root", str(empty)]), 2)
        self.assertIn(str(self.TEMPLATE), err.getvalue())
        self.assertEqual(runs(counter), 0)  # no tasks: the agent never ran
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(["eval", "tasks", "--agent-command", agent, "--root", str(self.repo)]), 1)
        self.assertGreater(runs(counter), 0)

    def test_tasks_repeat_and_say_the_control_does_not_apply(self):
        from aidd.cli import app

        out = io.StringIO()
        good = f"{sys.executable} {self.agent}"
        with contextlib.redirect_stdout(out):
            code = app.main(["eval", "tasks", "--agent-command", good, "--root", str(self.repo), "--repeat", "2", "--without-aidd", "--min-accuracy", "1"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("(passed 2/2)", out.getvalue())
        self.assertIn("pass^2 100.0%", out.getvalue())
        self.assertIn("control: not applicable to tasks", out.getvalue())

    def test_a_record_names_the_measured_repository_and_whether_it_was_dirty(self):
        from aidd.cli import app

        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "tasks"], cwd=self.repo, check=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()
        record = self.repo / "evals" / "runs.jsonl"
        good = f"{sys.executable} {self.agent}"
        argv = ["eval", "tasks", "--agent-command", good, "--root", str(self.repo), "--record", str(record)]
        with contextlib.redirect_stdout(io.StringIO()):
            app.main(argv)
            task = sorted((self.repo / "evals" / "tasks").glob("*.yaml"))[0]
            with task.open("a", encoding="utf-8") as f:
                f.write("# edited after the commit\n")
            app.main(argv)
            subprocess.run(["git", "checkout", "-q", "--", str(task)], cwd=self.repo, check=True, capture_output=True)
            (self.repo / "README.md").write_text("an uncommitted change to the configuration measured\n", encoding="utf-8")
            app.main(argv)
        clean, dirty, config = [json.loads(x) for x in record.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((config["head"], config["dirty"]), (head, True), "for tasks, any uncommitted tracked change is measured")
        self.assertEqual((clean["head"], clean["dirty"], clean["cases"]), (head, False, "evals/tasks"))
        self.assertEqual((dirty["head"], dirty["dirty"]), (head, True), "the head no longer shows the task files measured")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(app.main(["eval", "report", str(record)]), 0)
        self.assertEqual([ln.rsplit("|", 2)[1].strip() for ln in out.getvalue().splitlines() if ln.startswith("| 2")], ["fresh", "stale", "fresh"])


if __name__ == "__main__":
    unittest.main()
