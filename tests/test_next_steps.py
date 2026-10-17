"""The forecast and `aidd list`: one plain answer per open piece of work, the step and who takes it, for anyone on the
team: this change's steps, and all open work."""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, example, git  # noqa: F401

from aidd.tracking import next_steps
from aidd.setup import adoption
from aidd.setup import doctor_checks
from aidd.workitems import derived_status
from aidd.workitems import steps as workitems_steps
from aidd.kernel import resources

PROPOSAL = """---
aidd_version: "1.0.0"
kind: proposal
id: "{id}"
title: t
audience: internal
addressee: the board
goal: g
status: {status}
{extra}---
"""
DECIDED = 'go_no_go: {decision: go, by: "@lead", decided_on: "2026-09-01"}\nsign_off: {by: "@lead", decided_on: "2026-09-02"}\n'
ACCEPTED = DECIDED + 'outcome: {decision: accepted, by: "@lead", decided_on: "2026-09-05"}\n'
SUBMITTED = DECIDED + 'outcome: {decision: submitted, by: "@lead", decided_on: "2026-09-03"}\n'
NEED = '\nneeds:\n  - id: N-1\n    need: "n"\n    answer: met\n'


@unittest.skipUnless(shutil.which("git"), "git is required")
class NextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "a@example.com"), ("user.name", "A"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)

    def tearDown(self):
        self.tmp.cleanup()

    def setup_repo(self):
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@lead"], harnesses=[]))
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "day 0")
        git(self.root, "checkout", "-qb", "feat")

    def proposal(self, pid, status, extra=""):
        folder = self.root / "proposals" / pid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "proposal.md").write_text(PROPOSAL.format(id=pid, status=status, extra=extra), encoding="utf-8")

    def test_an_unset_repository_says_how_to_start(self):
        (step,) = next_steps.plan(self.root)
        self.assertEqual(step["code"], "setup.missing")
        self.assertIn("not set up", step["what"])
        self.assertIn("aidd init", step["how"])

    def test_each_open_piece_of_work_gets_its_step_and_owner(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        self.proposal("PROP-2", "accepted", ACCEPTED + NEED)
        (self.root / "specs" / "SPEC-220.md").write_text(
            example("02-normal-feature")["head_files"]["specs/SPEC-220.md"].replace("kind: spec\n", "kind: spec\nstatus: in_review\n", 1),
            encoding="utf-8",
        )
        # The branch changes the Task's scope, so the Spec is past ready; with no evidence here, the stored status says in review.
        (self.root / "src" / "checkout" / "rate_limit").mkdir(parents=True)
        (self.root / "src" / "checkout" / "rate_limit" / "limit.py").write_text("LIMIT = 60\n", encoding="utf-8")
        # This change: the Spec the branch changes carries it, so there is no lane step.
        steps = next_steps.plan(self.root)
        self.assertEqual([s["code"] for s in steps], ["spec.in_review"])
        self.assertTrue(steps[0]["what"].startswith("SPEC-220 waits for Merge approval"), steps)
        self.assertIn("who: Approver", next_steps.next_steps_markdown(steps))
        # All open work: the proposals, a decision maker's decision before the author's step.
        listed = helpers.open_work(self.root)
        self.assertEqual([(s["code"], s["who"]) for s in listed], [("proposal.exploring", "decision maker"), ("proposal.accepted", "author")])
        whats = [s["what"] for s in listed]
        self.assertIn("PROP-1 waits for a go/no-go decision", whats)
        self.assertIn("PROP-2 was accepted: turn it into delivery work", whats)
        self.assertIn("aidd proposal convert", listed[1]["how"])

    def test_a_converted_proposal_is_no_longer_open(self):
        self.setup_repo()
        self.proposal("PROP-2", "accepted", ACCEPTED + NEED)
        self.assertEqual([s["code"] for s in helpers.open_work(self.root)], ["proposal.accepted"])
        (self.root / "specs" / "INIT-PROP-2.md").write_text(
            '---\naidd_version: "1.0.0"\nkind: initiative\nid: INIT-PROP-2\ntitle: t\ngoal: g\nstatus: draft\nproposal: PROP-2\n---\n',
            encoding="utf-8",
        )
        self.assertEqual([s["code"] for s in helpers.open_work(self.root)], ["nothing_open"])
        # This change is the branch's own diff: the lane's step, never the proposal.
        self.assertEqual([s["code"] for s in next_steps.plan(self.root)], ["lane"])
        git(self.root, "switch", "-q", "main")
        for f in ("specs/INIT-PROP-2.md", "proposals/PROP-2/proposal.md"):
            (self.root / f).unlink()
        self.assertEqual([s["code"] for s in next_steps.plan(self.root)], ["nothing_open"])

    def test_the_branch_diff_gets_its_route_and_lane(self):
        """The forecast for a branch: the route, its lane, and the reasons, for the branch's diff, then the lane's step."""
        self.setup_repo()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        answer = next_steps.forecast(self.root)
        (step,) = answer["steps"]
        self.assertEqual((step["code"], step["route"], step["lane"], step["who"]), ("lane", "minor", "fast", "agent"))
        self.assertEqual(answer["route"]["header"], "Route: minor (fast lane), needed by this branch's diff against main (1 path)")
        self.assertIn("aidd describe", step["how"])
        (self.root / "db" / "migrations").mkdir(parents=True)
        (self.root / "db" / "migrations" / "1.sql").write_text("select 1;\n", encoding="utf-8")
        answer = next_steps.forecast(self.root)
        (step,) = answer["steps"]
        self.assertEqual((step["route"], step["lane"]), ("major", "spec"))
        self.assertTrue(any("db/migrations/1.sql" in r for r in answer["route"]["reasons"]), answer)
        self.assertIn("aidd new spec", step["how"])
        text = next_steps.forecast_markdown(answer)
        self.assertTrue(text.startswith("Route: major (spec lane), needed by this branch's diff against main (2 paths)\n  - "), text)

    def test_a_project_in_several_repositories_answers_per_repository(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        with tempfile.TemporaryDirectory() as other:
            git(other, "init", "-q")
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            run = subprocess.run(
                [sys.executable, "-m", "aidd", "list", str(self.root), other, "missing-repo", "--json"],
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            found = json.loads(run.stdout)["repos"]
            self.assertEqual(found[str(self.root)][0]["what"], "PROP-1 waits for a go/no-go decision")
            self.assertIn("not set up", found[other][0]["what"])
            self.assertIn("not a git repository", found["missing-repo"][0]["what"])

    def branch_with_spec(self, name, author, sid, scope):
        git(self.root, "switch", "-qc", name, "main")
        (self.root / "specs" / f"{sid}.md").write_text(
            f'---\naidd_version: "1.0.0"\nkind: spec\nid: "{sid}"\nstatus: ready\n\ntasks:\n  - id: "{sid}-T1"\n    scope: ["{scope}"]\n---\n',
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "-c", f"user.name={author}", "commit", "-qm", f"spec: {sid}")

    def test_two_people_changing_the_same_code_hear_about_it_first(self):
        self.setup_repo()
        git(self.root, "switch", "-q", "main")
        self.branch_with_spec("alice/cart", "Alice", "SPEC-1", "app/cart/**")
        self.branch_with_spec("carol/docs", "Carol", "SPEC-3", "docs/**")
        self.branch_with_spec("bob/checkout", "Bob", "SPEC-2", "app/cart/checkout.py")
        overlaps = [s for s in next_steps.plan(self.root) if s["code"] == "overlap"]
        # The docs change touches nothing of Bob's, so SPEC-3 is not named.
        self.assertEqual([s["what"] for s in overlaps], ["SPEC-2 overlaps SPEC-1 on alice/cart (Alice): the same code, changed twice"])
        self.assertIn("blocked_on: SPEC-1", overlaps[0]["how"])

    def test_the_branch_cap_counts_only_other_branches_and_says_when_it_stops(self):
        self.setup_repo()
        git(self.root, "switch", "-q", "main")
        git(self.root, "branch", "-D", "feat")
        git(self.root, "switch", "-qc", "alice/cart", "main")
        # A Spec file whose name has a space: `diff --name-only` split on whitespace would lose it.
        (self.root / "specs" / "SPEC 1.md").write_text(
            '---\naidd_version: "1.0.0"\nkind: spec\nid: SPEC-1\nstatus: ready\n\ntasks:\n  - id: SPEC-1-T1\n    scope: ["app/cart/**"]\n---\n',
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1")
        self.branch_with_spec("bob/checkout", "Bob", "SPEC-2", "app/cart/checkout.py")
        with mock.patch.object(next_steps, "MAX_BRANCHES", 1):
            whats = [s["what"] for s in next_steps.plan(self.root)]
        # Only alice/cart is another branch (main and bob/checkout itself are filtered before the cap), so it is read.
        self.assertTrue(any(w.startswith("SPEC-2 overlaps SPEC-1 on alice/cart") for w in whats), whats)
        self.assertFalse(any("were checked" in w for w in whats), whats)
        # A branch at main holds no work, so it is never read; one with a commit of its own is, and meets the cap.
        git(self.root, "branch", "zed/empty", "main")
        with mock.patch.object(next_steps, "MAX_BRANCHES", 1):
            whats = [s["what"] for s in next_steps.plan(self.root)]
        self.assertFalse(any("were checked" in w for w in whats), whats)
        git(self.root, "switch", "-qc", "zed/other", "main")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "other work")
        git(self.root, "switch", "-q", "bob/checkout")
        with mock.patch.object(next_steps, "MAX_BRANCHES", 1):
            whats = [s["what"] for s in next_steps.plan(self.root)]
        self.assertIn("only the first 1 of 2 other branches were checked for overlapping Specs", whats)

    def test_finished_specs_and_the_same_spec_elsewhere_are_not_overlaps(self):
        self.setup_repo()
        git(self.root, "switch", "-q", "main")
        self.branch_with_spec("alice/cart", "Alice", "SPEC-1", "app/cart/**")
        spec = self.root / "specs" / "SPEC-1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace("status: ready", "status: done"), encoding="utf-8")
        git(self.root, "commit", "-qam", "SPEC-1 is done")
        self.branch_with_spec("alice/cart-copy", "Alice", "SPEC-2", "app/cart/**")  # Bob's id, on another branch
        self.branch_with_spec("bob/checkout", "Bob", "SPEC-2", "app/cart/checkout.py")
        self.assertEqual([s for s in next_steps.plan(self.root) if s["code"] == "overlap"], [])

    def test_a_failing_setup_is_the_only_step(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        with mock.patch.object(doctor_checks, "doctor", return_value=[("ok", "fine"), ("fail", "the hook is missing"), ("fail", "second")]):
            (step,) = next_steps.plan(self.root)
        self.assertEqual(step["code"], "setup.doctor_fail")
        self.assertIn("the hook is missing", step["what"])

    def test_a_failing_setup_comes_first_and_a_forecast_still_says_the_route(self):
        self.setup_repo()
        with mock.patch.object(doctor_checks, "doctor", return_value=[("fail", "the launcher is missing on this machine")]):
            planned = next_steps.forecast(self.root, paths=["docs/guide.md"])
        self.assertIsNotNone(planned["route"])
        self.assertEqual(planned["steps"][0]["code"], "setup.doctor_fail")

    def test_an_overdue_proposal_says_when_it_was_due(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring", 'due: "2026-09-01"\n')
        self.proposal("PROP-2", "submitted", 'due: "2026-09-01"\n' + SUBMITTED)  # waiting on someone else: no reminder
        steps = {s["code"]: s["what"] for s in helpers.open_work(self.root, today=dt.date(2026, 9, 28))}
        self.assertTrue(steps["proposal.exploring"].endswith(" (it was due 2026-09-01)"), steps)
        self.assertNotIn("was due", steps["proposal.submitted"])
        steps = {s["code"]: s["what"] for s in helpers.open_work(self.root, today=dt.date(2026, 9, 1))}
        self.assertNotIn("was due", steps["proposal.exploring"])  # due today is not late

    def test_json_lists_each_task_for_a_coordinator(self):
        """`aidd list --branch --json` keeps every step's keys and adds `tasks` to a Spec's step, so a script (or Orca) can start
        one agent per ready Task, each in its own worktree."""
        self.setup_repo()
        (self.root / "specs" / "SPEC-9.md").write_text(
            '---\naidd_version: "1.0.0"\nkind: spec\nid: SPEC-9\nstatus: ready\n\n'
            'tasks:\n  - id: SPEC-9-T1\n    title: API\n    scope: ["api/**"]\n    assignee: agent:backend\n    skills: [api-design]\n'
            '  - id: SPEC-9-T2\n    title: Web\n    scope: ["web/**"]\n'
            "  - id: SPEC-9-T3\n    title: Wire up\n    scope: [web/app.ts]\n    depends_on: [SPEC-9-T1, SPEC-9-T2]\n---\n",
            encoding="utf-8",
        )
        env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
        run = subprocess.run(
            [sys.executable, "-m", "aidd", "list", "--branch", "--json"], cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        (step,) = [s for s in json.loads(run.stdout)["steps"] if s["code"].startswith("spec.")]
        self.assertLessEqual({"code", "where", "what", "who", "how"}, set(step))  # the existing keys are all still there
        self.assertEqual(step["where"], "specs/SPEC-9.md")
        by_id = {t["id"]: t for t in step["tasks"]}
        self.assertEqual(list(by_id), ["SPEC-9-T1", "SPEC-9-T2", "SPEC-9-T3"])
        self.assertEqual(
            by_id["SPEC-9-T1"],
            {
                "id": "SPEC-9-T1",
                "title": "API",
                "scope": ["api/**"],
                "depends_on": [],
                "skills": ["api-design"],
                "assignee": "agent:backend",
                "role": "backend",
                "status": "todo",
            },
        )
        self.assertEqual(by_id["SPEC-9-T2"]["status"], "todo")
        self.assertNotIn("skills", by_id["SPEC-9-T2"])  # only what the Spec carries
        self.assertEqual(by_id["SPEC-9-T3"]["status"], "blocked")
        self.assertEqual(by_id["SPEC-9-T3"]["waiting_on"], ["SPEC-9-T1", "SPEC-9-T2"])
        self.assertEqual([t["id"] for t in step["tasks"] if t["status"] == "todo"], ["SPEC-9-T1", "SPEC-9-T2"])
        # Work on T1's scope starts it; T3 unlocks once T1 and T2 are done (a person's `done: true` for T2, here).
        (self.root / "api").mkdir()
        (self.root / "api" / "a.py").write_text("x = 1\n", encoding="utf-8")
        spec = self.root / "specs" / "SPEC-9.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace('scope: ["web/**"]\n', 'scope: ["web/**"]\n    done: true\n'), encoding="utf-8")
        (step,) = [s for s in next_steps.plan(self.root) if s["code"].startswith("spec.")]
        self.assertEqual([t["status"] for t in step["tasks"]], ["in_progress", "done", "blocked"])
        self.assertEqual(step["tasks"][2]["waiting_on"], ["SPEC-9-T1"])
        self.assertEqual(step["code"], "spec.in_progress")


class ForSpecTests(unittest.TestCase):
    OBSERVE = {"window": "1d", "rollback_trigger": "errors"}

    def test_each_status_names_its_step_and_owner(self):
        for status, code, who in (
            ("draft", "spec.draft", workitems_steps.AGENT),
            ("ready", "spec.ready", workitems_steps.AGENT),
            ("in_progress", "spec.in_progress", workitems_steps.AGENT),
            ("in_review", "spec.in_review", workitems_steps.APPROVER),
            ("shipped", "spec.shipped", workitems_steps.AGENT),
            ("rolled_back", "spec.rolled_back", workitems_steps.AGENT),
            ("done", "spec.done", workitems_steps.AUTHOR),
            ("cancelled", "spec.cancelled", workitems_steps.AUTHOR),
        ):
            with self.subTest(status=status):
                step = helpers.for_spec("specs/S-1.md", {"id": "S-1", "status": status, "route": "normal", "observe": self.OBSERVE})
                self.assertEqual((step["code"], step["who"], step["where"]), (code, who, "specs/S-1.md"))
        self.assertIn("aidd observe specs/S-1.md", helpers.for_spec("specs/S-1.md", {"id": "S-1", "status": "shipped", "observe": self.OBSERVE})["how"])
        # Shipped with no observe block, or a passed window, is done; a failed window is a rollback. The runner
        # records only pass or fail: `skipped` is no observe result, so it never ends the window.
        self.assertEqual(helpers.for_spec("r", {"id": "S-1", "status": "shipped"})["code"], "spec.done")
        for result, code in (("pass", "spec.done"), ("skipped", "spec.shipped"), ("fail", "spec.rolled_back")):
            data = {"id": "S-1", "status": "shipped", "observe": self.OBSERVE, "outcome": {"observe_result": result}}
            self.assertEqual(helpers.for_spec("r", data)["code"], code)
        self.assertEqual(helpers.for_spec("r", {"id": "S-1"})["code"], "spec.draft")  # no status is a draft
        # A committed draft waits for an Approver; blocked is a flag with its reason, never a status.
        self.assertEqual(helpers.for_spec("r", {"id": "S-1"}, committed=True)["who"], workitems_steps.APPROVER)
        blocked = helpers.for_spec("r", {"id": "S-1", "status": "ready", "blocked_on": "S-0"})
        self.assertEqual((blocked["code"], blocked["who"]), ("spec.blocked", workitems_steps.AUTHOR))
        self.assertTrue(blocked["what"].endswith("blocked: S-0"))

    def test_an_emergency_restores_service_then_backfills_then_is_gone(self):
        em = {"id": "INC-1", "route": "emergency", "emergency": {"review_due": "2026-09-30"}}
        for status in ("draft", "in_progress", "in_review"):
            step = helpers.for_spec("specs/INC-1.md", em | {"status": status})
            self.assertEqual((step["code"], step["emergency"]), ("spec.emergency", True))
            self.assertIn("restore service", step["what"])
        for status in ("shipped", "done"):
            step = helpers.for_spec("specs/INC-1.md", em | {"status": status})
            self.assertEqual(step["code"], "spec.backfill")
            self.assertIn("by 2026-09-30", step["what"])
        self.assertEqual(helpers.for_spec("specs/INC-1.md", em | {"status": "done", "outcome": {"learn_ref": "https://x"}})["code"], "spec.done")
        self.assertEqual(derived_status.item_priority(em), "urgent")

    def test_task_status_follows_the_spec(self):
        spec = {"id": "S-1", "tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"]}]}
        for status, want in (
            ("draft", "blocked"),
            ("ready", "todo"),
            ("in_progress", "todo"),  # which Task started, only commits in its scope say
            ("in_review", "done"),
            ("shipped", "done"),
            ("done", "done"),
            ("rolled_back", "done"),
            ("cancelled", "blocked"),
        ):
            with self.subTest(status=status):
                (task,) = next_steps.tasks(spec | {"status": status})
                self.assertEqual(task["status"], want)
                self.assertEqual("why" in task, want == "blocked")
        (task,) = next_steps.tasks({"tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"]}]})
        self.assertIn("Spec approval", task["why"])  # no status is a draft: nothing starts before Spec approval
        (task,) = next_steps.tasks(spec | {"status": "ready", "blocked_on": "S-0"}, blockers=["S-0"])
        self.assertEqual(task["status"], "blocked")
        self.assertIn("S-0", task["why"])
        (task,) = next_steps.tasks({"status": "in_progress", "tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"], "retry_count": 3}]})
        self.assertEqual(task["status"], "stopped")
        self.assertIn("retries", task["why"])
        self.assertEqual(next_steps.tasks({"status": "ready"}), [])
        self.assertEqual(helpers.for_spec("r", {"id": "S-1", "status": "ready"})["tasks"], [])

    def test_task_state_from_the_facts(self):
        """Commits in a Task's scope start it; green evidence on head with its scope changed finishes it; a handoff note
        that stopped stops the Task in progress; a Task that depends on another unlocks once that one is done."""
        spec = {
            "id": "S-1",
            "tasks": [
                {"id": "T1", "title": "t", "scope": ["a/**"]},
                {"id": "T2", "title": "t", "scope": ["b/**"], "depends_on": ["T1"]},
            ],
        }
        started = derived_status.Facts(approved=True, changed=("a/x.py",), green=False)
        self.assertEqual([t["status"] for t in derived_status.task_states(spec, "in_progress", started)], ["in_progress", "blocked"])
        stop = {"next": "developer", "stopped_at": "3 retries"}
        self.assertEqual([t["status"] for t in derived_status.task_states(spec, "in_progress", started, note=stop)], ["stopped", "blocked"])
        green = derived_status.Facts(approved=True, changed=("a/x.py",), green=True)
        self.assertEqual([t["status"] for t in derived_status.task_states(spec, "in_progress", green)], ["done", "todo"])


class SpecStatusTests(unittest.TestCase):
    """The derivation itself: each fact git proves moves the Spec, and a fact nobody can observe is read from the store."""

    SPEC = {"id": "S-1", "kind": "spec", "route": "normal", "tasks": [{"id": "T1", "title": "t", "scope": ["src/a/**"]}]}

    def status(self, facts, **extra):
        return derived_status.spec_status(self.SPEC | extra, facts)

    def test_each_fact_moves_the_spec(self):
        F = derived_status.Facts
        self.assertEqual(self.status(F(approved=False, changed=())), "draft")
        self.assertEqual(self.status(F(approved=True, changed=())), "ready")
        self.assertEqual(self.status(F(approved=True, changed=("docs/x.md",))), "ready")  # outside every Task's scope
        self.assertEqual(self.status(F(approved=True, changed=("src/a/x.py",))), "in_progress")
        self.assertEqual(self.status(F(approved=True, changed=("src/a/x.py",), green=True)), "in_review")
        self.assertEqual(self.status(F(approved=True, changed=("src/a/x.py",), green=True, shipped=True)), "done")
        self.assertEqual(self.status(F(shipped=True), observe={"window": "1d", "rollback_trigger": "x"}), "shipped")
        # The approval voided (a new hash): back to draft, whatever the stored status says.
        self.assertEqual(self.status(F(approved=False, changed=("src/a/x.py",), green=True), status="in_review"), "draft")
        # A route that needs no Spec approval skips ready.
        self.assertEqual(derived_status.spec_status(self.SPEC, F(approved=False, changed=("src/a/x.py",)), approval=False), "in_progress")
        self.assertEqual(derived_status.spec_status(self.SPEC, F(approved=False, changed=()), approval=False), "draft")

    def test_the_store_answers_only_what_nobody_can_observe(self):
        F = derived_status.Facts
        everything = F(approved=True, changed=("src/a/x.py",), green=True, shipped=False)
        self.assertEqual(self.status(everything, status="cancelled"), "cancelled")
        self.assertEqual(self.status(everything, triage={"decision": "declined"}), "cancelled")
        self.assertEqual(self.status(everything, outcome={"rolled_back": True}), "rolled_back")
        self.assertEqual(self.status(everything, status="done"), "in_review")  # the merge is observable: it has not happened
        # Unknown facts fall back to the stored status as a cache.
        self.assertEqual(self.status(F(), status="in_review"), "in_review")
        self.assertEqual(self.status(F(changed=()), status="in_review"), "ready")

    def test_blocked_is_a_flag(self):
        self.assertEqual(derived_status.blocked_reasons(self.SPEC | {"blocked_on": "the vendor"}, "ready"), ["the vendor"])
        self.assertEqual(derived_status.blocked_reasons(self.SPEC, "in_progress", ["S-0"]), ["blocked by S-0"])
        retried = self.SPEC | {"tasks": [{"id": "T1", "title": "t", "scope": ["a/**"], "retry_count": 3}]}
        self.assertEqual(derived_status.blocked_reasons(retried, "in_progress"), ["T1 used its 3 retries; a person re-plans it"])
        self.assertEqual(derived_status.blocked_reasons(self.SPEC | {"blocked_on": "x"}, "in_review"), [])  # built work is not blocked
        self.assertNotIn("blocked", resources.load_json("common.schema.json")["$defs"]["status"]["enum"])

    def test_containers_follow_their_children(self):
        epic = {"kind": "epic", "id": "E-1"}
        self.assertEqual(derived_status.container_status(epic, ["draft", "ready"]), "draft")
        self.assertEqual(derived_status.container_status(epic, ["draft", "in_progress"]), "active")
        self.assertEqual(derived_status.container_status(epic | {"status": "done"}, ["in_progress"]), "done")  # a person's decision
        self.assertEqual(derived_status.container_status(epic | {"status": "active"}, []), "active")  # children elsewhere: the cache
        statuses, progress, _ = derived_status.container_statuses(
            [epic, {"kind": "spec", "id": "S-1", "parent": "E-1"}, {"kind": "spec", "id": "S-2", "parent": "E-1"}], {"S-1": "done", "S-2": "shipped"}
        )
        self.assertEqual((statuses["E-1"], progress["E-1"]), ("active", (1, 2)))


if __name__ == "__main__":
    unittest.main()
