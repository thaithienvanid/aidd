"""Work items a team steers by, from the repository alone: mission and goal, the why chain, the backlog and its filters,
status groups, triage, typed relations, labels, the Spec log, the handoff note, and the human queue.

None of it is evidence: the gate never reads relations, labels, triage, handoff notes, or the queue limits, and the
Spec hash ignores them, so the last tests pin the gate's decision as unchanged."""

import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, decide, example, git, run_cli

from aidd import config, docs, gitutil, hooks, local, model, nextstep, repo, resources, schema, speclog, workitems

TODAY = dt.date(2026, 9, 28)
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def spec(sid: str, status: str = "draft", extra: str = "", tasks: str = "", body: str = "") -> str:
    """A small Spec front matter; enough for `aidd assess` and `aidd list`, which read the fields they need and never validate."""
    tasks = tasks or f'[[tasks]]\nid = "{sid}-T1"\ntitle = "t"\nscope = ["src/{sid.lower()}/**"]\n'
    return f'+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "{sid}"\ntitle = "{sid}"\nstatus = "{status}"\n{extra}\n{tasks}+++\n{body}'


def container(kind: str, cid: str, goal: str, extra: str = "") -> str:
    return f'+++\naidd_version = "1.0.0"\nkind = "{kind}"\nid = "{cid}"\ntitle = "{cid}"\ngoal = "{goal}"\nstatus = "active"\n{extra}+++\n'


def handoff(nxt: str, needs: str = "none", done: str = "T1 built") -> str:
    return f'\n```aidd-handoff\ndone = "{done}"\nnext = "{nxt}"\nneeds = "{needs}"\nstopped_at = "none"\n```\n'


class Base(unittest.TestCase):
    """A repository that adopted aidd (team profile, @lead approves) on main, then a branch `feat` off it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "a@example.com"), ("user.name", "A"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        repo.init(self.root, profile="team", ci="none", links=[], approvers=["@lead"], harnesses=[])
        self.cfg_path = self.root / ".aidd" / "config.toml"
        self.login = mock.patch("aidd.repo.operator_login", return_value=None)
        self.login.start()
        self.addCleanup(self.login.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, top: str = "", owners: str = "", gates: str = "") -> None:
        text = self.cfg_path.read_text(encoding="utf-8")
        text = text.replace('aidd_version = "1.0.0"\n', f'aidd_version = "1.0.0"\n{top}', 1)
        text = text.replace('approvers = ["@lead"]\n', f'approvers = ["@lead"]\n{owners}', 1)
        self.cfg_path.write_text(text + (f"\n[gates]\n{gates}" if gates else ""), encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg: str = "work", when: str | None = None, author: str | None = None) -> None:
        env = dict(os.environ)
        if when:
            env |= {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        if author:
            env |= {"GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": f"{author.lower()}@example.com"}
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", msg, env=env)

    def plan(self, **filters) -> list[dict]:
        return nextstep.plan(self.root, today=TODAY, filters=nextstep.Filters(**filters), now=NOW)

    def codes(self, **filters) -> list[tuple[str, str]]:
        return [(s["code"], s["where"]) for s in self.plan(**filters)]


@unittest.skipUnless(shutil.which("git"), "git is required")
class MissionAndWhyTests(Base):
    def test_mission_is_a_top_level_key_a_child_may_replace(self):
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\nmission = "shops get paid"\ngoal = "onboard first try"\n')
        self.assertEqual((cfg.get("mission"), cfg.get("goal")), ("shops get paid", "onboard first try"))
        self.assertTrue(schema.validate({"aidd_version": "1.0.0", "profile": "team", "mission": ""}, "config.schema.json"))
        parent = 'aidd_version = "1.0.0"\nprofile = "team"\nmission = "old"\n'
        child = config.load_text(
            'aidd_version = "1.0.0"\nprofile = "team"\nmission = "new"\nextends = [{ path = "p.toml" }]\n', read=lambda p: parent if p == "p.toml" else None
        )
        self.assertEqual(child.get("mission"), "new")

    def test_the_session_briefing_has_one_mission_and_goal_line_within_the_cap(self):
        self.config(top='mission = "shops get paid on time"\ngoal = "onboarding succeeds first try"\n')
        cfg = hooks._config(str(self.root))
        self.assertEqual(hooks.purpose(cfg), "Mission: shops get paid on time / Goal: onboarding succeeds first try")
        steps = [nextstep._step(f"step {i}", nextstep.AGENT, "do it") for i in range(20)]
        with mock.patch.object(nextstep, "assess", return_value={"route": None, "steps": steps, "overlaps": []}):
            text = hooks.summary(self.root, "LANE", cfg)
        lines = text.splitlines()
        self.assertLessEqual(len(lines), hooks.MAX_SUMMARY_LINES)
        self.assertEqual(lines[1:3], ["LANE", "Mission: shops get paid on time / Goal: onboarding succeeds first try"])
        self.assertIn("more", lines[-1])
        self.assertIsNone(hooks.purpose(config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n')))
        self.assertEqual(hooks.purpose(config.load_text('aidd_version = "1.0.0"\nprofile = "team"\ngoal = "g"\n')), "Goal: g")

    def test_each_spec_step_says_why_from_mission_to_hypothesis(self):
        self.config(top='mission = "shops get paid"\ngoal = "fewer failed payouts"\n')
        self.write("specs/INIT-1.md", container("initiative", "INIT-1", "payouts never stall"))
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "retry failed payouts", 'parent = "INIT-1"\n'))
        self.commit("day 0")
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", 'parent = "EPIC-1"\nhypothesis = "failed payouts drop from 3% to 1% by November"'))
        (step,) = [s for s in self.plan() if s["code"].startswith("spec.")]
        self.assertEqual(
            [(w["kind"], w.get("id")) for w in step["why"]],
            [("mission", None), ("goal", None), ("initiative", "INIT-1"), ("epic", "EPIC-1"), ("spec", "SPEC-1")],
        )
        self.assertEqual(step["why"][-1]["text"], "failed payouts drop from 3% to 1% by November")
        text = nextstep.markdown([step])
        # Each container's link says how many of its children are finished (none of one, here).
        self.assertIn(
            "why: mission: shops get paid → goal: fewer failed payouts → INIT-1 (0/1): payouts never stall → EPIC-1 (0/1): retry failed payouts", text
        )
        # A measured outcome joins the hypothesis; a Spec with nothing to say has no why line.
        chain = workitems.why({"id": "S", "hypothesis": "h", "outcome": {"result": "met: 0.9%"}}, {}, None)
        self.assertEqual(chain, [{"kind": "spec", "id": "S", "text": "h (outcome: met: 0.9%)"}])
        self.assertNotIn("why:", nextstep.markdown([nextstep._step("w", nextstep.AUTHOR, "h")]))
        # A parent outside the Specs folder is named, and the walk stops there.
        self.assertEqual(workitems.why({"id": "S", "parent": "EPIC-9"}, {}, None), [{"kind": "parent", "id": "EPIC-9", "text": "not in the Specs folder"}])


@unittest.skipUnless(shutil.which("git"), "git is required")
class BacklogTests(Base):
    """The backlog reads the base branch and every open branch: a Spec on the base branch is merged work, and a Spec
    still being built lives on its own branch until it merges."""

    def branch(self, name: str, rel: str, text: str, author: str | None = None, code: str | None = None, when: str | None = None) -> None:
        git(self.root, "checkout", "-q", "-b", name, "main")
        self.write(rel, text)
        if code:
            self.write(code, "x = 1\n")
        self.commit(f"work on {rel}", author=author, when=when)
        git(self.root, "checkout", "-q", "main")

    def setUp(self):
        super().setUp()
        self.commit("day 0")
        self.write("specs/SPEC-3.md", spec("SPEC-3", "in_review"))  # merged: on the base branch, and done
        self.commit("SPEC-3 merged")
        self.branch(
            "a/spec-1",
            "specs/SPEC-1.md",
            spec("SPEC-1", "ready", 'labels = ["area:billing"]', '[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["a/**"]\nassignee = "agent:developer"\n'),
        )
        self.branch("a/spec-2", "specs/SPEC-2.md", spec("SPEC-2", "ready", 'blocked_on = "the vendor"\nlabels = ["customer-ask"]'))
        self.branch("a/spec-4", "specs/SPEC-4.md", spec("SPEC-4", "in_review"), code="src/spec-4/x.py", when="2026-09-26T12:00:00Z")
        self.branch(
            "bea/spec-5",
            "specs/SPEC-5.md",
            spec("SPEC-5", "ready", tasks='[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["b/**"]\nassignee = "agent:tester"\n'),
            author="Bea",
        )
        git(self.root, "checkout", "-qb", "feat")

    def test_default_next_is_this_branch_and_all_reads_the_base_and_every_open_branch(self):
        self.assertEqual(self.codes(), [("nothing_open", "")])  # this branch changes no Spec
        codes = {w: c for c, w in self.codes(all=True)}
        self.assertEqual(
            codes,
            {"specs/SPEC-4.md": "spec.in_review", "specs/SPEC-2.md": "spec.blocked", "specs/SPEC-1.md": "spec.ready", "specs/SPEC-5.md": "spec.ready"},
        )  # SPEC-3 merged, and nothing watches it: done, so not in the backlog
        by = {s["where"]: s for s in self.plan(all=True)}
        self.assertEqual((by["specs/SPEC-4.md"]["branch"], by["specs/SPEC-4.md"]["status"]), ("a/spec-4", "in_review"))
        # An uncommitted Spec on the branch is not in the backlog until it is committed.
        self.write("specs/SPEC-6.md", spec("SPEC-6"))
        self.assertNotIn("specs/SPEC-6.md", [w for _, w in self.codes(all=True)])
        self.assertIn(("spec.draft", "specs/SPEC-6.md"), self.codes())
        self.commit("SPEC-6")
        self.assertIn(("spec.spec_approval", "specs/SPEC-6.md"), self.codes(all=True))  # committed: an Approver's turn

    def test_merged_work_leaves_the_backlog_and_the_approver_inbox(self):
        """No zombies: once a branch merges, its Spec is the base branch's, shipped, whatever its stored status says."""
        with mock.patch("aidd.repo.operator_login", return_value="lead"):
            self.assertEqual(self.codes(all=True, waiting_on_me=True), [("spec.in_review", "specs/SPEC-4.md")])
            git(self.root, "checkout", "-q", "main")
            git(self.root, "merge", "-q", "--no-ff", "a/spec-4", "-m", "merge SPEC-4")
            self.assertEqual(self.codes(all=True, waiting_on_me=True), [("nothing_matches", "")])
        self.assertNotIn("specs/SPEC-4.md", [w for _, w in self.codes(all=True)])
        # Watching after release: with an observe block and no result yet, it stays open as shipped.
        self.write("specs/SPEC-4.md", spec("SPEC-4", "in_review", 'observe = { window = "1d", rollback_trigger = "errors" }'))
        self.commit("observe it")
        self.assertIn(("spec.shipped", "specs/SPEC-4.md"), self.codes(all=True))

    def test_every_step_carries_its_group(self):
        groups = {s["where"]: s["group"] for s in self.plan(all=True)}
        self.assertEqual(groups["specs/SPEC-4.md"], "started")
        self.assertEqual(groups["specs/SPEC-1.md"], "unstarted")
        here = os.getcwd()
        os.chdir(self.root)
        try:
            code, out = run_cli("list", "--json", "--label", "area:billing")
        finally:
            os.chdir(here)
        self.assertEqual(code, 0, out)
        (step,) = json.loads(out)["steps"]
        self.assertEqual((step["where"], step["group"], step["labels"]), ("specs/SPEC-1.md", "unstarted", ["area:billing"]))

    def test_filters(self):
        self.assertEqual([w for _, w in self.codes(all=True, label="area:billing")], ["specs/SPEC-1.md"])
        self.assertEqual([w for _, w in self.codes(all=True, blocked=True)], ["specs/SPEC-2.md"])
        self.assertEqual(sorted(w for _, w in self.codes(all=True, agent="")), ["specs/SPEC-1.md", "specs/SPEC-5.md"])
        (step,) = self.plan(all=True, agent="tester")
        self.assertEqual((step["where"], [t["id"] for t in step["tasks"]]), ("specs/SPEC-5.md", ["T1"]))
        # Mine: the Specs I added (git user.email), not Bea's.
        self.assertEqual(sorted(w for _, w in self.codes(all=True, mine=True)), ["specs/SPEC-1.md", "specs/SPEC-2.md", "specs/SPEC-4.md"])
        self.assertEqual(self.codes(all=True, label="nope"), [("nothing_matches", "")])

    def test_a_filter_keeps_the_proposals_it_applies_to(self):
        folder = self.root / "proposals" / "PROP-1"
        folder.mkdir(parents=True)
        (folder / "proposal.md").write_text(
            '+++\naidd_version = "1.0.0"\nkind = "proposal"\nid = "PROP-1"\ntitle = "t"\naudience = "internal"\naddressee = "the board"\ngoal = "g"\n+++\n',
            encoding="utf-8",
        )
        self.assertIn("proposal.exploring", [c for c, _ in self.codes(all=True, mine=True)])  # uncommitted: mine
        self.assertIn("proposal.exploring", [c for c, _ in self.codes(all=True, priority="medium")])  # a proposal is medium
        self.assertNotIn("proposal.exploring", [c for c, _ in self.codes(all=True, priority="high")])
        for f in ({"label": "area:billing"}, {"blocked": True}, {"agent": ""}):
            self.assertNotIn("proposal.exploring", [c for c, _ in self.codes(all=True, **f)], f)

    def test_mine_includes_a_task_assigned_to_me_and_work_i_own(self):
        self.branch(
            "bea/spec-7",
            "specs/SPEC-7.md",
            spec("SPEC-7", "ready", tasks='[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["c/**"]\nassignee = "@a-login"\n'),
            author="Bea",
        )
        with mock.patch("aidd.repo.operator_login", return_value="a-login"):
            self.assertIn("specs/SPEC-7.md", [w for _, w in self.codes(all=True, mine=True)])
        self.assertNotIn("specs/SPEC-7.md", [w for _, w in self.codes(all=True, mine=True)])
        # An owner decides it: Bea owns SPEC-8, which I added, so it is hers, and the backlog names her as who acts.
        self.branch("a/spec-8", "specs/SPEC-8.md", spec("SPEC-8", "ready", 'owner = "@bea"'))
        self.assertNotIn("specs/SPEC-8.md", [w for _, w in self.codes(all=True, mine=True)])
        with mock.patch("aidd.repo.operator_login", return_value="bea"):
            self.assertIn("specs/SPEC-8.md", [w for _, w in self.codes(all=True, mine=True)])
        step = next(s for s in self.plan(all=True) if s["where"] == "specs/SPEC-8.md")
        self.assertEqual((step["owner"], step["who"]), ("@bea", "@bea's agent"))

    def test_priority_sorts_and_filters(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g", 'priority = "high"\n'))
        self.commit("an epic that matters")
        self.branch("a/spec-9", "specs/SPEC-9.md", spec("SPEC-9", "ready", 'parent = "EPIC-1"'))  # inherits high
        self.branch("a/spec-10", "specs/SPEC-10.md", spec("SPEC-10", "ready", 'priority = "urgent"'))
        self.branch("a/spec-11", "specs/SPEC-11.md", spec("SPEC-11", "ready", 'priority = "low"'))
        order = [s["where"] for s in self.plan(all=True) if s["code"] == "spec.ready"]
        self.assertEqual(order[:2], ["specs/SPEC-10.md", "specs/SPEC-9.md"])
        self.assertEqual(order[-1], "specs/SPEC-11.md")
        self.assertEqual(sorted(w for _, w in self.codes(all=True, priority="high")), ["specs/SPEC-10.md", "specs/SPEC-9.md"])
        self.assertEqual([w for _, w in self.codes(all=True, priority="urgent")], ["specs/SPEC-10.md"])
        self.assertEqual(len(self.codes(all=True, priority="low")), len([s for s in self.plan(all=True) if s["code"].startswith("spec.")]))

    def test_the_approver_inbox_and_its_queue_limit(self):
        with mock.patch("aidd.repo.operator_login", return_value="lead"):
            self.assertEqual(self.codes(all=True, waiting_on_me=True), [("spec.in_review", "specs/SPEC-4.md")])
            for i in range(10, 13):
                self.branch(f"a/spec-{i}", f"specs/SPEC-{i}.md", spec(f"SPEC-{i}", "in_review"), code=f"src/spec-{i}/x.py")
            steps = self.plan(all=True, waiting_on_me=True)
        self.assertEqual(len([s for s in steps if s["code"] == "spec.in_review"]), 4)
        (warn,) = [s for s in steps if s["code"] == "queue.over_limit"]
        self.assertIn("you hold 4 open approval waits, more than gates.max_open_per_approver = 3", warn["what"])
        self.assertEqual(warn["approver"], "@lead")
        # Someone who is not an Approver has an empty inbox, and --all names the Approver over the limit.
        self.assertEqual(self.codes(all=True, waiting_on_me=True), [("nothing_matches", "")])
        (warn,) = [s for s in self.plan(all=True) if s["code"] == "queue.over_limit"]
        self.assertTrue(warn["what"].startswith("@lead holds 4"))
        # Off under solo (0), and a child may lower a limit but not raise or clear it.
        self.assertEqual(config.load_text('aidd_version = "1.0.0"\nprofile = "solo"\n').gates["max_open_per_approver"], 0)
        team = 'aidd_version = "1.0.0"\nprofile = "team"\n[gates]\nmax_open_per_approver = {}\n'
        self.assertEqual(config.load_text(team.format(2)).gates["max_open_per_approver"], 2)
        for looser in (5, 0):
            loose = config.load_text(team.format(looser))
            self.assertEqual(loose.gates["max_open_per_approver"], 3)
            self.assertTrue(any("max_open_per_approver" in w for w in loose.warnings))
        self.assertEqual(config.load_text('aidd_version = "1.0.0"\nprofile = "solo"\n[gates]\nmax_open_per_approver = 4\n').gates["max_open_per_approver"], 4)

    def test_a_wip_limit_per_owner_warns_and_is_off_by_default(self):
        for i in (12, 13):
            self.branch(f"bea/spec-{i}", f"specs/SPEC-{i}.md", spec(f"SPEC-{i}", "in_progress", 'owner = "@bea"'), code=f"src/spec-{i}/x.py")
        self.assertEqual([s for s in self.plan(all=True) if s["code"] == "wip.over_limit"], [])  # unset: no limit
        git(self.root, "checkout", "-q", "main")
        self.config(gates="max_in_progress_per_owner = 1\n")
        self.commit("one Spec in progress per person")
        git(self.root, "checkout", "-q", "feat")
        git(self.root, "merge", "-q", "main")
        (warn,) = [s for s in self.plan(all=True) if s["code"] == "wip.over_limit"]
        self.assertIn("@bea holds 2 Specs in progress, more than gates.max_in_progress_per_owner = 1", warn["what"])
        self.assertEqual((warn["owner"], warn["specs"]), ("@bea", ["specs/SPEC-12.md", "specs/SPEC-13.md"]))
        # A queue limit like max_open_per_approver: 0 is off, and a child may lower it but not raise or clear it.
        base = 'aidd_version = "1.0.0"\nprofile = "team"\n[gates]\nmax_in_progress_per_owner = {}\n'
        self.assertIsNone(config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n').gates.get("max_in_progress_per_owner"))
        parent = base.format(2)
        for looser in (5, 0):
            text = base.format(looser).replace("[gates]", 'extends = [{ path = "p.toml" }]\n[gates]')
            child = config.load_text(text, read=lambda p: parent if p == "p.toml" else None)
            self.assertEqual(child.gates["max_in_progress_per_owner"], 2)

    def age_step(self, rel: str) -> dict:
        (step,) = [s for s in self.plan(all=True) if s["where"] == rel and s["code"].startswith("spec.")]
        return step

    def test_a_spec_in_progress_shows_its_age_from_its_first_commit_in_scope(self):
        """Work item age: days since the Spec entered in progress. On a branch, that is the first commit that changed a
        Task's scope, the fact that makes the derived status in_progress."""
        git(self.root, "checkout", "-q", "-b", "a/spec-20", "main")
        self.write("specs/SPEC-20.md", spec("SPEC-20", "in_progress"))
        self.commit("SPEC-20, approved", when="2026-09-01T12:00:00Z")
        self.write("src/spec-20/x.py", "x = 1\n")
        self.commit("first code", when="2026-09-20T12:00:00Z")
        self.write("src/spec-20/y.py", "y = 1\n")
        self.commit("more code", when="2026-09-27T12:00:00Z")
        git(self.root, "checkout", "-q", "feat")
        step = self.age_step("specs/SPEC-20.md")
        self.assertEqual((step["status"], step["age_days"], step["aged"]), ("in_progress", 8, False))
        self.assertIn("1. [age 8d] SPEC-20 is being built", nextstep.markdown([step]))
        # Only work in progress has an age.
        self.assertEqual([s["where"] for s in self.plan(all=True) if "age_days" in s], ["specs/SPEC-20.md"])
        self.assertNotIn("[age", nextstep.markdown([s for s in self.plan(all=True) if "age_days" not in s]))
        # The list's JSON schema names the new keys; a consumer that does not know them ignores them.
        props = resources.load_json("list.schema.json")["$defs"]["step"]["properties"]
        self.assertEqual((props["age_days"]["type"], props["aged"]["type"]), ("integer", "boolean"))
        self.assertEqual(schema.validate({"schema_version": "1", "steps": [step]}, "list.schema.json"), [])

    def test_an_item_older_than_the_limit_is_flagged(self):
        self.branch("a/spec-21", "specs/SPEC-21.md", spec("SPEC-21", "in_progress"), code="src/spec-21/x.py", when="2026-09-10T12:00:00Z")
        step = self.age_step("specs/SPEC-21.md")
        self.assertEqual((step["age_days"], step["aged"]), (18, True))
        self.assertIn(f"past gates.max_in_progress_days = {nextstep.MAX_IN_PROGRESS_DAYS}", step["how"])
        self.assertIn("1. [age 18d, aging] SPEC-21", nextstep.markdown([step]))
        self.assertEqual(step["who"], nextstep.AGENT)  # a signal for people: nothing else about the step changes

    def test_the_age_limit_is_a_queue_limit_that_only_tightens(self):
        self.branch("a/spec-23", "specs/SPEC-23.md", spec("SPEC-23", "in_progress"), code="src/spec-23/x.py", when="2026-09-21T12:00:00Z")
        self.assertEqual(nextstep.MAX_IN_PROGRESS_DAYS, 10)
        self.assertFalse(self.age_step("specs/SPEC-23.md")["aged"])  # 7 days, under the default
        original = self.cfg_path.read_text(encoding="utf-8")
        self.config(gates="max_in_progress_days = 5\n")
        step = self.age_step("specs/SPEC-23.md")
        self.assertEqual((step["age_days"], step["aged"]), (7, True))
        self.assertIn("past gates.max_in_progress_days = 5", step["how"])
        self.cfg_path.write_text(original, encoding="utf-8")
        self.config(gates="max_in_progress_days = 0\n")  # off: the age shows, and nothing is flagged
        step = self.age_step("specs/SPEC-23.md")
        self.assertEqual(step["age_days"], 7)
        self.assertNotIn("aged", step)
        base = 'aidd_version = "1.0.0"\nprofile = "team"\n[gates]\nmax_in_progress_days = {}\n'
        parent = base.format(5)
        for looser in (8, 0):
            text = base.format(looser).replace("[gates]", 'extends = [{ path = "p.toml" }]\n[gates]')
            child = config.load_text(text, read=lambda p: parent if p == "p.toml" else None)
            self.assertEqual(child.gates["max_in_progress_days"], 5)
            self.assertTrue(any("max_in_progress_days" in w for w in child.warnings))

    def test_where_the_stored_status_answers_the_age_is_when_it_was_set(self):
        """A minor Spec needs no Spec approval. With no commit in its scope, its base-branch copy is in progress by its
        stored status, so its age starts at the commit that set that status, as `aidd log` reads it."""
        git(self.root, "checkout", "-q", "main")
        self.write("specs/SPEC-22.md", spec("SPEC-22", "ready", 'route = "minor"'))
        self.commit("SPEC-22", when="2026-09-01T12:00:00Z")
        self.write("specs/SPEC-22.md", spec("SPEC-22", "in_progress", 'route = "minor"'))
        self.commit("SPEC-22 started", when="2026-09-16T12:00:00Z")
        git(self.root, "checkout", "-q", "feat")
        step = self.age_step("specs/SPEC-22.md")
        self.assertEqual((step["status"], step["age_days"], step["aged"]), ("in_progress", 12, True))

    def test_the_age_is_the_earliest_author_date_whatever_the_commit_order(self):
        """A cherry-pick or a reordered rebase can put an older author date after a newer one: the age reads every
        commit in scope and takes the earliest, not the first in topological order."""
        git(self.root, "checkout", "-q", "-b", "a/spec-24", "main")
        self.write("specs/SPEC-24.md", spec("SPEC-24", "in_progress"))
        self.write("src/spec-24/x.py", "x = 1\n")
        self.commit("later work, committed first", when="2026-09-20T12:00:00Z")
        self.write("src/spec-24/y.py", "y = 1\n")
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-10T12:00:00Z", GIT_COMMITTER_DATE="2026-09-25T12:00:00Z")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "cherry-picked: authored earlier", env=env)
        git(self.root, "checkout", "-q", "feat")
        step = self.age_step("specs/SPEC-24.md")
        self.assertEqual((step["age_days"], step["aged"]), (18, True))

    def test_a_shallow_clone_shows_no_age(self):
        """A shallow clone cuts the history: its oldest commit is a graft that seems to add every file, so the commit
        that set the status (or the first commit in scope) may be missing. No age beats a wrong one."""
        git(self.root, "checkout", "-q", "main")
        self.write("specs/SPEC-26.md", spec("SPEC-26", "in_progress", 'route = "minor"'))
        self.commit("SPEC-26 started", when="2026-09-12T12:00:00Z")
        self.write("README-later.md", "later\n")
        self.commit("later on main", when="2026-09-27T12:00:00Z")
        self.assertEqual(self.age_step("specs/SPEC-26.md")["age_days"], 16)
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        clone = Path(other.name).resolve() / "shallow"
        git(other.name, "clone", "-q", "--depth", "1", "--branch", "main", self.root.as_uri(), str(clone))
        self.assertEqual(git(clone, "rev-parse", "--is-shallow-repository"), "true")
        steps = nextstep.plan(clone, today=TODAY, filters=nextstep.Filters(all=True), now=NOW)
        (step,) = [s for s in steps if s["where"] == "specs/SPEC-26.md" and s["code"].startswith("spec.")]
        self.assertEqual(step["status"], "in_progress")  # still listed, in progress
        self.assertNotIn("age_days", step)  # the graft says 1 day: wrong, so none
        self.assertNotIn("aged", step)
        self.assertNotIn("[age", nextstep.markdown([step]))

    def test_debt_is_a_suggested_spec_labelled_debt(self):
        """No ledger: an agent in proactive_roles suggests the debt as a draft Spec with the label, a person triages it,
        and `aidd list --label debt` is the debt list."""
        self.branch("sre/spec-14", "specs/SPEC-14.md", spec("SPEC-14", "draft", 'suggested_by = "agent:sre"\nlabels = ["debt", "area:billing"]'))
        (step,) = self.plan(all=True, label="debt")
        self.assertEqual((step["code"], step["where"], step["labels"]), ("spec.triage", "specs/SPEC-14.md", ["debt", "area:billing"]))
        self.assertNotIn("specs/SPEC-14.md", [w for _, w in self.codes(all=True, label="area:checkout")])

    def test_a_wait_past_the_limit_is_escalated_to_the_backup_pool(self):
        git(self.root, "checkout", "-q", "main")
        self.config(owners='backup_approvers = ["@backup"]\n', gates="escalate_after_minutes = 60\n")
        self.commit("escalate after an hour", when="2026-09-20T12:00:00Z")
        git(self.root, "branch", "-qD", "a/spec-4")
        # The wait for Merge approval starts at the head commit the evidence (here, the stored status) is green on.
        self.branch("a/spec-4", "specs/SPEC-4.md", spec("SPEC-4", "in_review"), code="src/spec-4/x.py", when="2026-09-26T12:00:00Z")
        (step,) = [s for s in self.plan(all=True) if s["where"] == "specs/SPEC-4.md"]
        self.assertTrue(step["escalated"])
        self.assertEqual(step["waiting_minutes"], 2 * 24 * 60)
        self.assertEqual(step["backup_approvers"], ["@backup"])
        self.assertIn("waiting 2 days, past gates.escalate_after_minutes = 60", step["what"])
        self.assertIn("ask a backup approver (@backup)", step["how"])
        self.assertEqual(step["who"], nextstep.APPROVER)  # still a wait for an Approver: nothing is approved
        fresh = nextstep.plan(self.root, today=TODAY, filters=nextstep.Filters(all=True), now=dt.datetime(2026, 9, 26, 12, 30, tzinfo=dt.UTC))
        (step,) = [s for s in fresh if s["where"] == "specs/SPEC-4.md"]
        self.assertNotIn("escalated", step)
        self.assertEqual(step["waiting_minutes"], 30)

    def test_the_list_schema_names_every_queue_key_and_how_it_grows(self):
        """`aidd list --json` readers learn every key the queue signals add, and that a new optional key comes in a minor
        release with no version bump."""
        sch = resources.load_json("list.schema.json")
        self.assertIn("A new optional key may be added in a minor release without a version bump", sch["description"])
        self.assertIn("a consumer ignores keys it does not know", sch["description"])
        props = sch["$defs"]["step"]["properties"]
        self.assertEqual(props["waiting_minutes"], props["waiting_minutes"] | {"type": "integer", "minimum": 0})
        self.assertEqual(props["escalated"]["type"], "boolean")
        self.assertEqual((props["backup_approvers"]["type"], props["backup_approvers"]["items"]["type"]), ("array", "string"))
        for key in ("waiting_minutes", "escalated", "backup_approvers"):
            self.assertIn("escalate_after_minutes", props[key]["description"], key)
        self.assertIn("false", props["aged"]["description"])
        step = {"code": "spec.in_review", "where": "s", "what": "w", "who": "Approver", "how": "h"}
        good = step | {"waiting_minutes": 90, "escalated": True, "backup_approvers": ["@backup"], "age_days": 3, "aged": False}
        self.assertEqual(schema.validate({"schema_version": "1", "steps": [good]}, "list.schema.json"), [])
        self.assertTrue(schema.validate({"schema_version": "1", "steps": [step | {"escalated": "yes"}]}, "list.schema.json"))
        self.assertTrue(schema.validate({"schema_version": "1", "steps": [step | {"waiting_minutes": -1}]}, "list.schema.json"))

    def test_the_docs_list_the_queue_limits_one_by_one(self):
        """The four queue limits read as a list, each with its default, and the profiles table shows all four. An org
        preset that wants the age limit enforced sets it: unset is 10, yet a child may then set any value."""
        text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        section = text.split("## `[gates]`", 1)[1].split("<!-- aidd:gen", 1)[0]
        for key in config._QUEUE_LIMITS:
            self.assertRegex(section, rf"(?m)^- `{key}`", key)
        self.assertRegex(section, r"org preset that wants `max_in_progress_days` enforced must set it")
        for sentence in re.split(r"(?<=\.)\s+|\n+", section.strip()):
            self.assertLessEqual(len(sentence.split()), 25, sentence)
        table = docs.profiles_table()
        owner = next(ln for ln in table.splitlines() if "Specs in progress per owner" in ln)
        days = next(ln for ln in table.splitlines() if "Days in progress" in ln)
        self.assertEqual(owner.split("|")[2:6], [" unset (off) "] * 4)
        self.assertEqual(days.split("|")[2:6], [" unset (10) "] * 4)

    def test_an_epic_is_derived_from_its_children_and_a_person_closes_it(self):
        git(self.root, "checkout", "-q", "main")
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "retry payouts").replace('status = "active"\n', ""))
        self.write("specs/SPEC-20.md", spec("SPEC-20", "in_review", 'parent = "EPIC-1"'))  # merged
        self.commit("EPIC-1 and a merged child")
        self.branch("a/spec-21", "specs/SPEC-21.md", spec("SPEC-21", "ready", 'parent = "EPIC-1"'))
        steps = self.plan(all=True)
        (child,) = [s for s in steps if s["where"] == "specs/SPEC-21.md"]
        self.assertEqual(child["why"][-1], {"kind": "epic", "id": "EPIC-1", "text": "retry payouts", "progress": "1/2"})
        self.assertIn("EPIC-1 (1/2): retry payouts", nextstep.markdown([child]))
        self.assertNotIn("epic.close", [s["code"] for s in steps])
        # Once every child is finished, `aidd list` suggests closing it; a person records done.
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", "a/spec-21", "-m", "merge SPEC-21")
        (close,) = [s for s in self.plan(all=True) if s["code"] == "epic.close"]
        self.assertEqual((close["what"], close["who"], close["status"]), ("close EPIC-1: 2/2 children finished", nextstep.AUTHOR, "active"))
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "retry payouts").replace('"active"', '"done"'))
        self.commit("close EPIC-1")
        self.assertNotIn("epic.close", [s["code"] for s in self.plan(all=True)])


@unittest.skipUnless(shutil.which("git"), "git is required")
class DerivedStatusTests(Base):
    """Local-first, end to end: a Spec moves from draft to done with nobody editing its status, because every step is
    something git proves. `aidd validate` warns when a stored status, a cache, says otherwise."""

    def status(self) -> str:
        (step,) = [s for s in self.plan() if s["where"] == "specs/SPEC-1.md"]
        return step["status"]

    def warnings(self) -> list[str]:
        return [w for w in repo.check_repo(self.root, today=TODAY)[1] if "stored status" in w or "not finished" in w]

    def test_a_spec_moves_by_what_git_proves(self):
        self.commit("day 0")
        git(self.root, "checkout", "-qb", "feat")
        text = spec(
            "SPEC-1",
            "draft",
            tasks='[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["src/one/**"]\n\n[tests]\nfiles = ["tests/test_one.py"]\n\n[[tests.commands]]\nname = "one"\ncommand = ["true"]\n',
        ).replace('status = "draft"\n', "")
        self.write("specs/SPEC-1.md", text)
        self.write("tests/test_one.py", "assert True\n")
        self.assertEqual(self.status(), "draft")
        self.commit("SPEC-1 and its tests")
        self.assertEqual([s["code"] for s in self.plan() if s["where"] == "specs/SPEC-1.md"], ["spec.spec_approval"])
        # `aidd approve spec`, as a person records it: the derived status is ready, and no file changed.
        head = git(self.root, "rev-parse", "HEAD")
        h = model.spec_hash(text, gitutil.ls_tree("HEAD", str(self.root)))
        local.record(local.approve_spec_line("SPEC-1", h, head), str(self.root))
        self.assertEqual(self.status(), "ready")
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        # Work in the Task's scope starts it; green evidence on the head puts it in review.
        self.write("src/one/a.py", "x = 1\n")
        self.commit("T1")
        self.assertEqual(self.status(), "in_progress")
        head = git(self.root, "rev-parse", "HEAD")
        results = [{"name": "one", "red_green": "green", "status": "passed"}]
        self.write("aidd-evidence/evidence.json", json.dumps({"head_sha": head, "results": results}))
        self.assertEqual(self.status(), "in_review")
        (step,) = [s for s in self.plan() if s["where"] == "specs/SPEC-1.md"]
        self.assertEqual([t["status"] for t in step["tasks"]], ["done"])
        # A changed test voids the approval: back to draft, whatever the stored status says.
        self.write("specs/SPEC-1.md", text.replace('kind = "spec"\n', 'kind = "spec"\nstatus = "in_review"\n', 1))
        self.write("tests/test_one.py", "assert 1\n")
        self.assertEqual(self.status(), "draft")
        self.assertIn(
            "specs/SPEC-1.md: the stored status in_review disagrees with the derived status draft; aidd assess and aidd list show draft. Update the status or remove it",
            self.warnings(),
        )
        self.write("tests/test_one.py", "assert True\n")
        self.assertEqual(self.warnings(), [])  # the cache agrees again
        # The merge ships it; with nothing to watch, it is done and leaves the backlog.
        git(self.root, "checkout", "-q", "--", ".")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", "feat", "-m", "ship SPEC-1")
        self.assertNotIn("specs/SPEC-1.md", [s["where"] for s in self.plan(all=True)])
        log = speclog.build(self.root, "SPEC-1")
        self.assertEqual(log["status"], "done")

    def test_validate_warns_about_a_done_epic_with_an_open_child_and_refuses_an_unknown_status(self):
        self.commit("day 0")
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g").replace('"active"', '"done"'))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", 'parent = "EPIC-1"'))
        self.assertIn("specs/EPIC-1.md: status done, but SPEC-1 is not finished; reopen it or finish them", self.warnings())
        self.write("specs/SPEC-2.md", spec("SPEC-2", "released"))
        found = repo.validate_file(self.root / "specs/SPEC-2.md")
        self.assertTrue(any("status" in e and not e.startswith("warning:") for e in found), found)
        self.write("specs/SPEC-3.md", spec("SPEC-3", "blocked"))
        found = repo.validate_file(self.root / "specs/SPEC-3.md")
        self.assertTrue(any("status" in e and not e.startswith("warning:") for e in found), found)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GroupTests(unittest.TestCase):
    def test_every_status_has_a_group(self):
        common = resources.load_json("common.schema.json")["$defs"]
        proposal = resources.load_json("proposal.schema.json")["properties"]["status"]
        groups = set(common["status_group"]["enum"])
        self.assertEqual(groups, set(workitems.GROUPS))
        for vocab in (common["status"], common["container_status"], proposal):
            self.assertEqual(set(vocab["x-groups"]), set(vocab["enum"]))
            self.assertLessEqual(set(vocab["x-groups"].values()), groups)
        self.assertEqual(workitems.group({"kind": "spec"}), "backlog")  # no status is a draft
        self.assertEqual(workitems.group({"kind": "epic", "status": "active"}), "started")
        self.assertEqual(workitems.group({"kind": "proposal", "status": "no_go"}), "cancelled")
        self.assertEqual(workitems.group({"kind": "proposal"}, "signed_off"), "started")  # the derived status, given
        self.assertEqual(workitems.group({"kind": "spec", "status": "draft"}, "shipped"), "started")
        self.assertIsNone(workitems.group({"kind": "runbook"}))

    def test_the_method_carries_the_generated_table(self):
        text = (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen status:groups -->\n" + docs.groups_table() + "\n<!-- aidd:end -->", text)
        self.assertIn("| `completed` |", docs.groups_table())


@unittest.skipUnless(shutil.which("git"), "git is required")
class TriageTests(Base):
    def valid(self, extra: str, status: str = "draft") -> str:
        text = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        return text.replace('kind = "spec"\n', f'kind = "spec"\nstatus = "{status}"\n{extra}', 1)

    def errors(self, text: str) -> list[str]:
        self.write("specs/SPEC-220.md", text)
        return [e for e in repo.validate_file(self.root / "specs/SPEC-220.md") if not e.startswith("warning: ")]

    def test_agent_proposed_work_needs_a_persons_triage_before_it_moves(self):
        proposed = 'suggested_by = "agent:sre"\n'
        self.assertEqual(self.errors(self.valid(proposed)), [])  # a draft waits for triage
        (err,) = self.errors(self.valid(proposed, "ready"))
        self.assertIn("status ready needs triage: agent:sre suggested this work", err)
        accepted = proposed + 'triage = { decision = "accepted", by = "@lead", on = 2026-09-20 }\n'
        self.assertEqual(self.errors(self.valid(accepted, "ready")), [])
        (err,) = self.errors(self.valid(accepted.replace("@lead", "agent:product-manager"), "ready"))
        self.assertIn("triage.by agent:product-manager is an agent account", err)
        # A configured agent account is an agent too.
        self.config(owners="")
        text = self.cfg_path.read_text(encoding="utf-8").replace("bots = []", 'bots = ["helper-bot"]')
        self.cfg_path.write_text(text, encoding="utf-8")
        (err,) = self.errors(self.valid(accepted.replace("@lead", "helper-bot"), "ready"))
        self.assertIn("triage.by helper-bot is an agent account", err)
        declined = proposed + 'triage = { decision = "declined", by = "@lead", on = 2026-09-20 }\n'
        (err,) = self.errors(self.valid(declined, "in_progress"))
        self.assertIn('needs triage.decision = "accepted"', err)
        self.assertEqual(self.errors(self.valid(declined, "cancelled")), [])
        # Declined cancels the work: a stored draft contradicts it; no stored status at all is fine.
        (err,) = self.errors(self.valid(declined, "draft"))
        self.assertIn('contradicts triage.decision = "declined"', err)
        self.assertEqual(self.errors(self.valid(declined, "draft").replace('status = "draft"\n', "", 1)), [])
        # A person's own Spec needs no triage.
        self.assertEqual(self.errors(self.valid("", "ready")), [])

    def test_a_declined_triage_records_its_reason(self):
        """A later triage reads why an idea was declined before it decides the same idea again: `triage.reason` is
        optional bookkeeping, outside the Spec hash like the rest of `triage`, and `aidd validate` warns when a decline
        has none."""
        proposed = 'suggested_by = "agent:sre"\n'
        declined = proposed + 'triage = { decision = "declined", by = "@lead", on = 2026-09-20 }\n'
        self.write("specs/SPEC-220.md", self.valid(declined, "cancelled"))
        found = repo.validate_file(self.root / "specs/SPEC-220.md")
        self.assertTrue(any(e.startswith("warning: ") and "triage.reason" in e for e in found), found)
        with_reason = declined.replace("on = 2026-09-20 }", 'on = 2026-09-20, reason = "the support load is too small to pay for it" }')
        self.write("specs/SPEC-220.md", self.valid(with_reason, "cancelled"))
        found = repo.validate_file(self.root / "specs/SPEC-220.md")
        self.assertFalse([e for e in found if "triage" in e], found)
        # An accepted or snoozed triage may say why too, and needs no reason.
        accepted = proposed + 'triage = { decision = "accepted", by = "@lead", on = 2026-09-20 }\n'
        self.write("specs/SPEC-220.md", self.valid(accepted, "ready"))
        self.assertFalse([e for e in repo.validate_file(self.root / "specs/SPEC-220.md") if "triage" in e])
        self.assertEqual(self.errors(self.valid(accepted.replace(" }", ', reason = "a customer asked twice" }', 1), "ready")), [])
        # An empty reason is no reason.
        errs = self.errors(self.valid(with_reason.replace("the support load is too small to pay for it", ""), "cancelled"))
        self.assertTrue(any("reason" in e for e in errs), errs)
        # Bookkeeping: a reason never voids Spec approval.
        text = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        tree = {"tests/checkout/test_rate_limit.py": "a" * 40}
        reasoned = text.replace('kind = "spec"\n', 'kind = "spec"\ntriage = { decision = "accepted", by = "@lead", on = 2026-09-20, reason = "x" }\n', 1)
        self.assertEqual(model.spec_hash(text, tree), model.spec_hash(reasoned, tree))

    def test_only_a_proactive_role_proposes_work(self):
        # The default roles: product-manager, agile-coach, and sre.
        (err,) = self.errors(self.valid('suggested_by = "agent:developer"\n'))
        self.assertIn("agent:developer may not suggest work: [agents] proactive_roles names product-manager, agile-coach, sre", err)
        self.assertEqual(self.errors(self.valid('suggested_by = "agent:sre"\n')), [])
        text = self.cfg_path.read_text(encoding="utf-8")
        self.cfg_path.write_text(text + '\n[agents]\nproactive_roles = ["developer"]\n', encoding="utf-8")
        self.assertEqual(self.errors(self.valid('suggested_by = "agent:developer"\n')), [])
        (err,) = self.errors(self.valid('suggested_by = "agent:sre"\n'))
        self.assertIn("agent:sre may not suggest work", err)

    def test_an_owner_is_a_person(self):
        self.assertEqual(self.errors(self.valid('owner = "@lead"\n')), [])
        (err,) = self.errors(self.valid('owner = "agent:developer"\n'))
        self.assertIn("owner agent:developer is an agent account", err)
        (err,) = self.errors(self.valid('owner = "renovate[bot]"\n'))
        self.assertIn("is an agent account", err)

    def test_the_schema_requires_until_for_a_snooze_and_a_duplicate_is_a_relation(self):
        base = self.valid('suggested_by = "agent:sre"\n')
        for triage, needed in (
            ('{ decision = "snoozed", by = "@lead", on = 2026-09-20 }', "until"),
            ('{ decision = "duplicate", by = "@lead", on = 2026-09-20 }', "decision"),  # a relation now: `duplicates`
        ):
            errs = self.errors(base.replace('suggested_by = "agent:sre"\n', f'suggested_by = "agent:sre"\ntriage = {triage}\n'))
            self.assertTrue(any(needed in e for e in errs), errs)

    def test_next_asks_a_person_to_triage_first_and_hides_snoozed_work_until_its_date(self):
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='suggested_by = "agent:sre"'))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "ready"))
        steps = self.plan()
        self.assertEqual([s["code"] for s in steps], ["spec.triage", "spec.ready"])
        self.assertEqual(steps[0]["who"], nextstep.PERSON)
        self.assertIn("SPEC-1 was suggested by agent:sre", steps[0]["what"])
        snooze = 'suggested_by = "agent:sre"\ntriage = {{ decision = "snoozed", by = "@lead", on = 2026-09-01, until = {} }}'
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra=snooze.format("2026-10-15")))
        self.assertEqual([s["code"] for s in self.plan()], ["spec.ready"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra=snooze.format("2026-09-20")))
        (step,) = [s for s in self.plan() if s["where"] == "specs/SPEC-1.md"]
        self.assertEqual(step["code"], "spec.triage")
        self.assertIn("snooze ended on 2026-09-20", step["what"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='suggested_by = "agent:sre"\ntriage = { decision = "declined", by = "@lead", on = 2026-09-01 }'))
        self.assertEqual([s["code"] for s in self.plan()], ["spec.ready"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='suggested_by = "agent:sre"\nrelations = [{ type = "duplicates", id = "SPEC-2" }]'))
        self.assertEqual([s["code"] for s in self.plan()], ["spec.ready"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='suggested_by = "agent:sre"\ntriage = { decision = "accepted", by = "@lead", on = 2026-09-01 }'))
        self.assertIn("spec.draft", [s["code"] for s in self.plan()])


@unittest.skipUnless(shutil.which("git"), "git is required")
class RelationTests(Base):
    def test_validate_checks_targets_self_links_and_cycles(self):
        self.write("specs/EPIC-1.md", container("epic", "EPIC-1", "g", 'relations = [{ type = "relates_to", id = "SPEC-9" }]\n'))
        self.write("specs/INIT-1.md", container("initiative", "INIT-1", "g", 'relations = [{ type = "blocks", id = "INIT-1" }]\n'))
        errors = workitems.relation_errors(
            [
                ("specs/EPIC-1.md", {"kind": "epic", "id": "EPIC-1", "relations": [{"type": "relates_to", "id": "SPEC-9"}]}),
                ("specs/INIT-1.md", {"kind": "initiative", "id": "INIT-1", "relations": [{"type": "blocks", "id": "INIT-1"}]}),
                ("specs/A.md", {"kind": "spec", "id": "A", "relations": [{"type": "blocks", "id": "B"}]}),
                ("specs/B.md", {"kind": "spec", "id": "B", "relations": [{"type": "blocked_by", "id": "C"}]}),
                ("specs/C.md", {"kind": "spec", "id": "C", "relations": [{"type": "blocked_by", "id": "B"}]}),
                ("specs/D.md", {"kind": "spec", "id": "D", "relations": [{"type": "duplicates", "id": "Z"}]}),
            ]
        )
        self.assertEqual(len(errors), 4, errors)
        self.assertTrue(any("relates_to SPEC-9: no Spec, Epic, or Initiative" in e for e in errors))
        self.assertTrue(any("blocks INIT-1 points at itself" in e for e in errors))
        self.assertTrue(any("duplicates Z: no Spec, Epic, or Initiative" in e for e in errors))
        (cycle,) = [e for e in errors if "cycle" in e]
        self.assertIn("B -> C -> B", cycle)
        # A blocks B with B blocked_by A is one edge, not a cycle.
        ok = [
            ("a", {"kind": "spec", "id": "A", "relations": [{"type": "blocks", "id": "B"}]}),
            ("b", {"kind": "spec", "id": "B", "relations": [{"type": "blocked_by", "id": "A"}]}),
        ]
        self.assertEqual(workitems.relation_errors(ok), [])
        # `aidd validate` on the repository reports them.
        errors, _ = repo.check_repo(self.root, today=TODAY)
        self.assertTrue(any("relates_to SPEC-9" in e for e in errors), errors)
        self.assertTrue(any("points at itself" in e for e in errors), errors)

    def test_labels_and_relations_are_schema_checked(self):
        bad = {"labels": ["Upper"]}, {"labels": [f"l{i}" for i in range(9)]}, {"relations": [{"type": "parent_of", "id": "X"}]}
        base = json.loads(json.dumps({"aidd_version": "1.0.0", "kind": "epic", "id": "E", "title": "t", "goal": "g", "status": "active"}))
        self.assertEqual(
            schema.validate(base | {"labels": ["area:billing", "customer-ask"], "relations": [{"type": "implements", "id": "I-1"}]}, "epic.schema.json"), []
        )
        for extra in bad:
            self.assertTrue(schema.validate(base | extra, "epic.schema.json"), extra)

    def test_next_shows_work_blocked_by_unfinished_items_and_drops_duplicates(self):
        self.commit("day 0")
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "ready", 'relations = [{ type = "blocked_by", id = "SPEC-1" }]'))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "ready", 'relations = [{ type = "duplicates", id = "SPEC-1" }]'))
        by = {s["where"]: s for s in self.plan()}
        self.assertNotIn("specs/SPEC-3.md", by)
        blocked = by["specs/SPEC-2.md"]
        self.assertEqual((blocked["code"], blocked["waiting_on"], blocked["blocked"]), ("spec.blocked_by", ["SPEC-1"], True))
        self.assertEqual(blocked["tasks"][0]["status"], "blocked")
        self.assertIn("blocked by SPEC-1", blocked["tasks"][0]["why"])
        # The other side says it: SPEC-1 blocks SPEC-4.
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress", 'relations = [{ type = "blocks", id = "SPEC-4" }]'))
        self.write("specs/SPEC-4.md", spec("SPEC-4", "draft"))
        self.assertEqual({s["where"]: s["code"] for s in self.plan()}["specs/SPEC-4.md"], "spec.blocked_by")
        # A stored "done" is only a cache: SPEC-1 is not merged, so both still wait.
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", 'relations = [{ type = "blocks", id = "SPEC-4" }]'))
        self.assertEqual({s["where"]: s["code"] for s in self.plan()}["specs/SPEC-2.md"], "spec.blocked_by")
        # Once SPEC-1 merges (it is on the base branch, approved), both go ahead.
        (self.root / "specs" / "SPEC-1.md").unlink()
        git(self.root, "stash", "push", "-q", "-u", "-m", "the other Specs")
        git(self.root, "checkout", "-q", "main")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_review", 'relations = [{ type = "blocks", id = "SPEC-4" }]'))
        self.commit("SPEC-1 merged")
        git(self.root, "checkout", "-q", "feat")
        git(self.root, "merge", "-q", "main")
        git(self.root, "stash", "pop", "-q")
        codes = {s["where"]: s["code"] for s in self.plan()}
        self.assertEqual((codes["specs/SPEC-2.md"], codes["specs/SPEC-4.md"]), ("spec.ready", "spec.draft"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class HandoffTests(Base):
    def test_the_latest_note_names_the_role_and_a_need_becomes_a_persons_step(self):
        git(self.root, "checkout", "-qb", "feat")
        body = "\n## Context\n" + handoff("developer", done="old") + handoff("tester", needs="pick the retry limit: 3 or 5")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress", body=body))
        self.write("src/spec-1/x.py", "x = 1\n")  # the work started in the Task's scope
        steps = self.plan()
        (main,) = [s for s in steps if s["code"] == "spec.in_progress"]
        self.assertEqual(main["who"], "agent (tester)")
        self.assertEqual(main["handoff"]["next"], "tester")
        (need,) = [s for s in steps if s["code"] == "spec.needs"]
        self.assertEqual((need["who"], need["what"]), (nextstep.AUTHOR, "SPEC-1 needs a person: pick the retry limit: 3 or 5"))
        self.assertLess(steps.index(need), steps.index(main))  # a person's step before the agent's

    def test_the_approver_inbox_follows_the_derived_status_not_the_note(self):
        self.commit("day 0")
        git(self.root, "checkout", "-qb", "feat")
        # A committed draft waits for Spec approval; a Spec green in review waits for Merge approval.
        self.write("specs/SPEC-1.md", spec("SPEC-1", "draft", body=handoff("tester")))
        self.commit("SPEC-1 for Spec approval")
        self.write("specs/SPEC-2.md", spec("SPEC-2", "in_review"))
        self.write("src/spec-2/x.py", "x = 1\n")
        # A note that still names an approval, on work that is not waiting for one, puts nothing in the inbox.
        self.write("specs/SPEC-3.md", spec("SPEC-3", "ready", body=handoff("merge-approval")))
        by = {s["where"]: s for s in self.plan()}
        self.assertEqual((by["specs/SPEC-1.md"]["code"], by["specs/SPEC-1.md"]["who"]), ("spec.spec_approval", nextstep.APPROVER))
        self.assertEqual((by["specs/SPEC-2.md"]["code"], by["specs/SPEC-2.md"]["who"]), ("spec.in_review", nextstep.APPROVER))
        self.assertEqual(by["specs/SPEC-3.md"]["code"], "spec.ready")
        with mock.patch("aidd.repo.operator_login", return_value="lead"):
            self.assertEqual(sorted(c for c, _ in self.codes(waiting_on_me=True)), ["spec.in_review", "spec.spec_approval"])

    def test_a_need_asked_in_another_status_is_stale(self):
        git(self.root, "checkout", "-qb", "feat")
        note = handoff("tester", needs="pick the limit").replace('stopped_at = "none"', 'stopped_at = "none"\nstatus = "draft"')
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", body=note))
        self.assertNotIn("spec.needs", [s["code"] for s in self.plan()])  # asked while a draft; the Spec is ready now
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready", body=note.replace('status = "draft"', 'status = "ready"')))
        self.assertIn("spec.needs", [s["code"] for s in self.plan()])

    def test_parsing_and_validate_warnings(self):
        text = (
            handoff("tester")
            + "```aidd-handoff\nnext = \n```\n"
            + handoff("nobody")
            + '```aidd-handoff\ndone = "x"\nnext = "reviewer"\nneeds = ["a", "none"]\nstopped_at = "none"\nspend = 3\nmood = "ok"\n```\n'
        )
        self.assertEqual(workitems.latest_handoff(text)["next"], "reviewer")
        self.assertEqual(workitems.needs(workitems.latest_handoff(text)), ["a"])
        warnings = workitems.handoff_warnings("s.md", text + handoff("spec-approval").replace('stopped_at = "none"', 'stopped_at = "none"\nstatus = "waiting"'))
        self.assertEqual(len(warnings), 5, warnings)
        self.assertTrue(any("handoff note 2 is not TOML" in w for w in warnings))
        self.assertTrue(any("next 'nobody' is not a role" in w for w in warnings))
        self.assertTrue(any("keys aidd does not read: mood" in w for w in warnings))
        self.assertTrue(any("next 'spec-approval' is an approval, not a role" in w for w in warnings))
        self.assertTrue(any("status 'waiting' is not a Spec status" in w for w in warnings))
        self.assertIsNone(workitems.latest_handoff('```aidd-handoffx\nnext = "tester"\n```\n'))
        self.assertIn("aidd-handoff", hooks.HANDOFF_REMINDER)

    def test_the_skill_names_the_same_bookkeeping_keys_the_hash_leaves_out(self):
        skill = ROOT / ".agents" / "skills" / "aidd"
        keys = sorted(model.VOLATILE_SPEC_KEYS | model.VOLATILE_TASK_KEYS)
        for doc in (skill / "SKILL.md", skill / "references" / "loop.md"):
            text = doc.read_text(encoding="utf-8")
            (line,) = [ln for ln in text.splitlines() if "voids" in ln and "`retry_count`" in ln]
            self.assertEqual(sorted(re.findall(r"`([a-z_]+)`", line.split("except", 1)[1].split(")", 1)[0].split(";", 1)[0])), keys, doc)

    def test_a_handoff_note_labels_relations_and_triage_never_void_spec_approval(self):
        text = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        tree = {"tests/checkout/test_rate_limit.py": "a" * 40}
        before = model.spec_hash(text, tree)
        bookkeeping = text.replace(
            'kind = "spec"\n',
            'kind = "spec"\nlabels = ["area:checkout"]\nrelations = [{ type = "relates_to", id = "SPEC-1" }]\n'
            'triage = { decision = "accepted", by = "@lead", on = 2026-09-01 }\npriority = "urgent"\nowner = "@lead"\nstatus = "shipped"\n',
            1,
        ).replace('assignee = "agent:claude-code"\n', 'assignee = "agent:claude-code"\nretry_count = 2\ndone = true\n', 1)
        self.assertEqual(model.spec_hash(bookkeeping + handoff("tester", needs="a decision"), tree), before)
        self.assertNotEqual(model.spec_hash(text + "\nOne more Acceptance line.\n", tree), before)
        self.assertNotEqual(model.spec_hash(text + "\n```aidd-handoffx\nnext = 1\n```\n", tree), before)  # only the exact fence
        self.assertNotEqual(model.spec_hash(text.replace('kind = "spec"\n', 'kind = "spec"\nsuggested_by = "agent:sre"\n', 1), tree), before)


@unittest.skipUnless(shutil.which("git"), "git is required")
class SpecLogTests(Base):
    def test_transitions_time_in_state_approvals_and_assisted_by(self):
        self.commit("day 0", when="2026-09-01T09:00:00Z")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "draft"))
        self.commit("specify", when="2026-09-02T09:00:00Z")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "ready"))
        self.commit("approved\n\nAssisted-by: claude-code/claude-opus-5-5", when="2026-09-03T09:00:00Z")
        self.write("src/spec-1/x.py", "x = 1\n")
        self.commit("build\n\nAssisted-by: codex/gpt-5", when="2026-09-03T10:00:00Z")
        self.write("src/other.py", "y = 1\n")
        self.commit("unrelated\n\nAssisted-by: someone/else", when="2026-09-03T11:00:00Z")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_review"))
        self.commit("review", when="2026-09-04T09:00:00Z")
        head = git(self.root, "rev-parse", "HEAD")
        local.record(local.approve_spec_line("SPEC-1", "0" * 32, head), str(self.root))
        local.record(local.approve_spec_line("SPEC-99", "0" * 32, head), str(self.root))
        local.record(local.approve_merge_line(head), str(self.root))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "shipped"))  # uncommitted
        log = speclog.build(self.root, "specs/SPEC-1.md", now=dt.datetime(2026, 9, 5, 9, 0, tzinfo=dt.UTC))
        self.assertEqual([t["status"] for t in log["transitions"]], ["draft", "ready", "in_review", "shipped"])
        # The status now is derived: the one Spec approval recorded names another hash, so the Spec is a draft.
        self.assertEqual((log["status"], log["stored_status"]), ("draft", "shipped"))
        self.assertEqual([t.get("minutes") for t in log["transitions"]], [1440, 1440, 1440, None])
        self.assertTrue(log["transitions"][-1]["uncommitted"])
        self.assertEqual(log["assisted_by"], ["claude-code/claude-opus-5-5", "codex/gpt-5"])
        kinds = sorted(a["kind"] for a in log["approvals"])
        self.assertEqual(kinds, ["merge_approval", "spec_approval"])  # not SPEC-99's
        record = self.root / "aidd-evidence" / "record.json"
        record.parent.mkdir()
        record.write_text(json.dumps({"decision": "pending", "spec_id": "SPEC-1", "head_sha": head, "approved_by": ["@lead"]}), encoding="utf-8")
        code, out = self.cli("log", "SPEC-1", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["id"], "SPEC-1")
        self.assertIn(
            {
                "kind": "gate_record",
                "decision": "pending",
                "head_sha": head,
                "spec_approved_by": [],
                "approved_by": ["@lead"],
                "source": speclog.DEFAULT_RECORD,
            },
            data["approvals"],
        )
        code, out = self.cli("log", "specs/SPEC-1.md")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"\| `ready` \| 2026-09-03T09:00:00\S* \| 24 h \|")
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5, codex/gpt-5.", out)

    def cli(self, *argv: str) -> tuple[int, str]:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            return run_cli(*argv)
        finally:
            os.chdir(here)


class GateNeverReadsTests(unittest.TestCase):
    """Relations, labels, triage, handoff notes, and the queue limits are for people; the gate's decision is the same
    with or without them."""

    def outcome(self, ctx: dict) -> tuple:
        d = decide(ctx)
        return d.decision, d.rules_at("fail"), d.rules_at("pending"), d.rules_at("warn"), d.record.get("spec_hash"), d.record.get("route")

    def test_work_item_fields_and_queue_limits_leave_the_decision_unchanged(self):
        for name in ("02-normal-feature", "03-normal-waiting"):
            with self.subTest(example=name):
                ctx = example(name)
                before = self.outcome(ctx)
                rel = "specs/SPEC-220.md"
                ctx["head_files"][rel] = ctx["head_files"][rel].replace(
                    'kind = "spec"\n',
                    'kind = "spec"\nlabels = ["area:checkout"]\nrelations = [{ type = "blocked_by", id = "SPEC-1" }]\n'
                    'triage = { decision = "accepted", by = "@checkout-lead", on = 2026-09-01 }\npriority = "urgent"\nowner = "@checkout-lead"\n'
                    'status = "shipped"\n',
                    1,
                ) + handoff("merge-approval", needs="decide the limit")
                ctx["base_config"] = (
                    ctx["base_config"]
                    .replace('approvers = ["@checkout-lead"', 'backup_approvers = ["@backup"]\napprovers = ["@checkout-lead"', 1)
                    .replace('profile = "team"\n', 'profile = "team"\nmission = "m"\n', 1)
                    + "\n[gates]\nmax_open_per_approver = 1\nescalate_after_minutes = 1\n"
                )
                self.assertEqual(self.outcome(ctx), before)

    def test_the_gate_modules_never_name_the_work_item_fields(self):
        for module in ("gates.py", "verify.py", "rules.py", "policy.py"):
            text = (ROOT / "src" / "aidd" / module).read_text(encoding="utf-8")
            for word in (
                "relations",
                "labels",
                "triage",
                "priority",
                "aidd-handoff",
                "workitems",
                "max_open_per_approver",
                "escalate_after_minutes",
                "max_in_progress_days",
                "backup_approvers",
            ):
                self.assertIsNone(re.search(rf"\b{re.escape(word)}\b", text), f"{module} reads {word}")
            # Nor the derived status: the gate derives its own verdict from the platform.
            self.assertIsNone(re.search(r"^from \. import .*\b(state|nextstep)\b|^from \.(state|nextstep) import", text, re.M), f"{module} imports the status")


if __name__ == "__main__":
    unittest.main()
