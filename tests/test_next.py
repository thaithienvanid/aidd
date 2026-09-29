"""`aidd next`: one plain answer per open piece of work, the step and who takes it, for anyone on the team."""

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

from helpers import ROOT, example, git  # noqa: F401

from aidd import nextstep, repo

PROPOSAL = """+++
aidd_version = "1.0.0"
kind = "proposal"
id = "{id}"
title = "t"
audience = "internal"
addressee = "the board"
goal = "g"
status = "{status}"
{extra}+++
"""
DECIDED = 'go_no_go = { decision = "go", by = "@lead", on = "2026-09-01" }\nsign_off = { by = "@lead", on = "2026-09-02" }\n'
NEED = '\n[[needs]]\nid = "N-1"\nneed = "n"\nanswer = "met"\n'


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
        repo.init(self.root, profile="team", ci="none", links=[], approvers=["@lead"], harnesses=[])
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "day 0")
        git(self.root, "checkout", "-qb", "feat")

    def proposal(self, pid, status, extra=""):
        folder = self.root / "proposals" / pid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "proposal.md").write_text(PROPOSAL.format(id=pid, status=status, extra=extra), encoding="utf-8")

    def test_an_unset_repository_says_how_to_start(self):
        (step,) = nextstep.plan(self.root)
        self.assertEqual(step["code"], "setup.missing")
        self.assertIn("not set up", step["what"])
        self.assertIn("aidd init", step["how"])

    def test_each_open_piece_of_work_gets_its_step_and_owner(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        self.proposal("PROP-2", "accepted", DECIDED + NEED)
        (self.root / "specs" / "SPEC-220.md").write_text(
            example("02-normal-feature")["head_files"]["specs/SPEC-220.md"].replace('kind = "spec"\n', 'kind = "spec"\nstatus = "in_review"\n', 1),
            encoding="utf-8",
        )
        steps = nextstep.plan(self.root)
        # A person's decision first; the branch's diff (the new Spec and proposals) gets its route last.
        self.assertEqual([s["code"] for s in steps], ["spec.in_review", "proposal.exploring", "proposal.accepted", "route"])
        whats = [s["what"] for s in steps]
        self.assertTrue(whats[0].startswith("SPEC-220 waits for Merge approval"), whats)
        self.assertIn("PROP-1 waits for a go/no-go decision", whats)
        self.assertIn("PROP-2 was accepted: turn it into delivery work", whats)
        self.assertIn("aidd proposal convert", next(s for s in steps if s["what"].startswith("PROP-2"))["how"])
        text = nextstep.markdown(steps)
        self.assertIn("who: an approver", text)

    def test_a_converted_proposal_is_no_longer_open(self):
        self.setup_repo()
        self.proposal("PROP-2", "accepted", DECIDED + NEED)
        (self.root / "specs" / "INIT-PROP-2.md").write_text(
            '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-PROP-2"\ntitle = "t"\ngoal = "g"\nstatus = "draft"\nproposal = "PROP-2"\n+++\n',
            encoding="utf-8",
        )
        self.assertEqual([s["code"] for s in nextstep.plan(self.root)], ["route"])  # only the branch's own diff is left
        git(self.root, "switch", "-q", "main")
        for f in ("specs/INIT-PROP-2.md", "proposals/PROP-2/proposal.md"):
            (self.root / f).unlink()
        self.assertEqual([s["code"] for s in nextstep.plan(self.root)], ["nothing_open"])

    def test_the_branch_diff_gets_its_route_and_lane(self):
        """The entry rule in `aidd next`: the computed route, its lane, and the reasons, for the branch's diff."""
        self.setup_repo()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        (step,) = nextstep.plan(self.root)
        self.assertEqual((step["code"], step["route"], step["lane"]), ("route", "minor", "fast"))
        self.assertIn("needs route minor (fast lane)", step["what"])
        self.assertIn("aidd change", step["how"])
        (self.root / "db" / "migrations").mkdir(parents=True)
        (self.root / "db" / "migrations" / "1.sql").write_text("select 1;\n", encoding="utf-8")
        (step,) = nextstep.plan(self.root)
        self.assertEqual((step["route"], step["lane"]), ("major", "spec"))
        self.assertTrue(any("db/migrations/1.sql" in r for r in step["reasons"]), step)
        self.assertIn("aidd new spec", step["how"])
        self.assertIn(step["reasons"][0], step["what"])

    def test_a_project_in_several_repositories_answers_per_repository(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        with tempfile.TemporaryDirectory() as other:
            git(other, "init", "-q")
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            run = subprocess.run(
                [sys.executable, "-m", "aidd", "next", str(self.root), other, "missing-repo", "--json"],
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            found = json.loads(run.stdout)
            self.assertEqual(found[str(self.root)][0]["what"], "PROP-1 waits for a go/no-go decision")
            self.assertIn("not set up", found[other][0]["what"])
            self.assertIn("not a git repository", found["missing-repo"][0]["what"])

    def branch_with_spec(self, name, author, sid, scope):
        git(self.root, "switch", "-qc", name, "main")
        (self.root / "specs" / f"{sid}.md").write_text(
            f'+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "{sid}"\nstatus = "ready"\n\n[[tasks]]\nid = "{sid}-T1"\nscope = ["{scope}"]\n+++\n',
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
        overlaps = [s for s in nextstep.plan(self.root) if s["code"] == "overlap"]
        # The docs change touches nothing of Bob's, so SPEC-3 is not named.
        self.assertEqual([s["what"] for s in overlaps], ["SPEC-2 overlaps SPEC-1 on alice/cart (Alice): the same code, changed twice"])
        self.assertIn('blocked_on = "SPEC-1"', overlaps[0]["how"])

    def test_the_branch_cap_counts_only_other_branches_and_says_when_it_stops(self):
        self.setup_repo()
        git(self.root, "switch", "-q", "main")
        git(self.root, "branch", "-D", "feat")
        git(self.root, "switch", "-qc", "alice/cart", "main")
        # A Spec file whose name has a space: `diff --name-only` split on whitespace would lose it.
        (self.root / "specs" / "SPEC 1.md").write_text(
            '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "SPEC-1"\nstatus = "ready"\n\n[[tasks]]\nid = "SPEC-1-T1"\nscope = ["app/cart/**"]\n+++\n',
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1")
        self.branch_with_spec("bob/checkout", "Bob", "SPEC-2", "app/cart/checkout.py")
        with mock.patch.object(nextstep, "MAX_BRANCHES", 1):
            whats = [s["what"] for s in nextstep.plan(self.root)]
        # Only alice/cart is another branch (main and bob/checkout itself are filtered before the cap), so it is read.
        self.assertTrue(any(w.startswith("SPEC-2 overlaps SPEC-1 on alice/cart") for w in whats), whats)
        self.assertFalse(any("were checked" in w for w in whats), whats)
        git(self.root, "branch", "zed/other", "main")
        with mock.patch.object(nextstep, "MAX_BRANCHES", 1):
            whats = [s["what"] for s in nextstep.plan(self.root)]
        self.assertIn("only the first 1 of 2 other branches were checked for overlapping Specs", whats)

    def test_finished_specs_and_the_same_spec_elsewhere_are_not_overlaps(self):
        self.setup_repo()
        git(self.root, "switch", "-q", "main")
        self.branch_with_spec("alice/cart", "Alice", "SPEC-1", "app/cart/**")
        spec = self.root / "specs" / "SPEC-1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace('status = "ready"', 'status = "done"'), encoding="utf-8")
        git(self.root, "commit", "-qam", "SPEC-1 is done")
        self.branch_with_spec("alice/cart-copy", "Alice", "SPEC-2", "app/cart/**")  # Bob's id, on another branch
        self.branch_with_spec("bob/checkout", "Bob", "SPEC-2", "app/cart/checkout.py")
        self.assertEqual([s for s in nextstep.plan(self.root) if s["code"] == "overlap"], [])

    def test_a_failing_setup_is_the_only_step(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring")
        with mock.patch.object(nextstep.repo, "doctor", return_value=[("ok", "fine"), ("fail", "the hook is missing"), ("fail", "second")]):
            (step,) = nextstep.plan(self.root)
        self.assertEqual(step["code"], "setup.doctor_fail")
        self.assertIn("the hook is missing", step["what"])

    def test_an_overdue_proposal_says_when_it_was_due(self):
        self.setup_repo()
        self.proposal("PROP-1", "exploring", 'due = "2026-09-01"\n')
        self.proposal("PROP-2", "submitted", 'due = "2026-09-01"\n' + DECIDED)  # waiting on someone else: no reminder
        steps = {s["code"]: s["what"] for s in nextstep.plan(self.root, today=dt.date(2026, 9, 28))}
        self.assertTrue(steps["proposal.exploring"].endswith(" (it was due 2026-09-01)"), steps)
        self.assertNotIn("was due", steps["proposal.submitted"])
        steps = {s["code"]: s["what"] for s in nextstep.plan(self.root, today=dt.date(2026, 9, 1))}
        self.assertNotIn("was due", steps["proposal.exploring"])  # due today is not late

    def test_json_lists_each_task_for_a_coordinator(self):
        """`aidd next --json` keeps every step's keys and adds `tasks` to a Spec's step, so a script (or Orca) can start
        one agent per ready Task, each in its own worktree."""
        self.setup_repo()
        (self.root / "specs" / "SPEC-9.md").write_text(
            '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "SPEC-9"\nstatus = "ready"\n\n'
            '[[tasks]]\nid = "SPEC-9-T1"\ntitle = "API"\nscope = ["api/**"]\nassignee = "agent:backend"\nskills = ["api-design"]\n\n'
            '[[tasks]]\nid = "SPEC-9-T2"\ntitle = "Web"\nscope = ["web/**"]\n\n'
            '[[tasks]]\nid = "SPEC-9-T3"\ntitle = "Wire up"\nscope = ["web/app.ts"]\ndepends_on = ["SPEC-9-T1", "SPEC-9-T2"]\n+++\n',
            encoding="utf-8",
        )
        env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
        run = subprocess.run([sys.executable, "-m", "aidd", "next", "--json"], cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        (step,) = [s for s in json.loads(run.stdout) if s["code"].startswith("spec.")]
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
                "status": "ready",
            },
        )
        self.assertEqual(by_id["SPEC-9-T2"]["status"], "ready")
        self.assertNotIn("skills", by_id["SPEC-9-T2"])  # only what the Spec carries
        self.assertEqual(by_id["SPEC-9-T3"]["status"], "blocked")
        self.assertEqual(by_id["SPEC-9-T3"]["waiting_on"], ["SPEC-9-T1", "SPEC-9-T2"])
        self.assertEqual([t["id"] for t in step["tasks"] if t["status"] == "ready"], ["SPEC-9-T1", "SPEC-9-T2"])


class ForSpecTests(unittest.TestCase):
    def test_each_status_names_its_step_and_owner(self):
        for status, code, who in (
            ("draft", "spec.draft", nextstep.AGENT),
            ("ready", "spec.ready", nextstep.AGENT),
            ("in_progress", "spec.in_progress", nextstep.AGENT),
            ("in_review", "spec.in_review", nextstep.APPROVER),
            ("released", "spec.released", nextstep.AGENT),
            ("rolled_back", "spec.rolled_back", nextstep.AGENT),
            ("blocked", "spec.blocked", nextstep.YOU),
            ("done", "spec.done", nextstep.YOU),
        ):
            with self.subTest(status=status):
                step = nextstep.for_spec("specs/S-1.md", {"id": "S-1", "status": status, "route": "normal", "blocked_on": "S-0"})
                self.assertEqual((step["code"], step["who"], step["where"]), (code, who, "specs/S-1.md"))
        self.assertIn("aidd observe specs/S-1.md", nextstep.for_spec("specs/S-1.md", {"id": "S-1", "status": "released"})["how"])
        self.assertTrue(nextstep.for_spec("r", {"id": "S-1", "status": "blocked", "blocked_on": "S-0"})["what"].endswith("blocked: S-0"))
        self.assertEqual(nextstep.for_spec("r", {"id": "S-1"})["code"], "spec.draft")  # no status is a draft

    def test_an_open_emergency_comes_before_its_status(self):
        em = {"id": "INC-1", "route": "emergency", "emergency": {"review_due": "2026-09-30"}}
        for status in ("draft", "ready", "released"):
            step = nextstep.for_spec("specs/INC-1.md", em | {"status": status})
            self.assertEqual(step["code"], "spec.emergency")
            self.assertIn("before 2026-09-30", step["what"])
        self.assertEqual(nextstep.for_spec("specs/INC-1.md", em | {"status": "done"})["code"], "spec.done")

    def test_task_status_follows_the_spec(self):
        spec = {"id": "S-1", "blocked_on": "S-0", "tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"]}]}
        for status, want in (
            ("draft", "blocked"),
            ("ready", "ready"),
            ("in_progress", "ready"),
            ("in_review", "done"),
            ("released", "done"),
            ("done", "done"),
            ("rolled_back", "done"),
            ("blocked", "blocked"),
            ("cancelled", "blocked"),
        ):
            with self.subTest(status=status):
                (task,) = nextstep.tasks(spec | {"status": status})
                self.assertEqual(task["status"], want)
                self.assertEqual("why" in task, want == "blocked")
        (task,) = nextstep.tasks({"tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"]}]})
        self.assertIn("Spec approval", task["why"])  # no status is a draft: nothing starts before Spec approval
        (task,) = nextstep.tasks(spec | {"status": "blocked"})
        self.assertIn("S-0", task["why"])
        (task,) = nextstep.tasks({"status": "in_progress", "tasks": [{"id": "S-1-T1", "title": "t", "scope": ["a/**"], "retry_count": 3}]})
        self.assertEqual(task["status"], "blocked")
        self.assertIn("retries", task["why"])
        self.assertEqual(nextstep.tasks({"status": "ready"}), [])
        self.assertEqual(nextstep.for_spec("r", {"id": "S-1", "status": "ready"})["tasks"], [])


if __name__ == "__main__":
    unittest.main()
