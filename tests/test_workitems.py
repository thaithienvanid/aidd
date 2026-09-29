"""Work items a team steers by, from the repository alone: mission and goal, the why chain, the backlog and its filters,
status groups, triage, typed relations, labels, the Spec log, the handoff note, and the human queue.

None of it is evidence: the gate never reads relations, labels, triage, handoff notes, or the queue limits, and the
Spec approval hash ignores them, so the last tests pin the gate's decision as unchanged."""

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

from aidd import config, docs, hooks, local, model, nextstep, repo, resources, schema, speclog, workitems

TODAY = dt.date(2026, 9, 28)
NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


def spec(sid: str, status: str = "draft", extra: str = "", tasks: str = "", body: str = "") -> str:
    """A small Spec front matter; enough for `aidd next`, which reads the fields it needs and never validates."""
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
        with mock.patch.object(nextstep, "plan", return_value=steps):
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
        self.assertIn("why: mission: shops get paid → goal: fewer failed payouts → INIT-1: payouts never stall → EPIC-1: retry failed payouts", text)
        # A measured outcome joins the hypothesis; a Spec with nothing to say has no why line.
        chain = workitems.why({"id": "S", "hypothesis": "h", "outcome": {"result": "met: 0.9%"}}, {}, None)
        self.assertEqual(chain, [{"kind": "spec", "id": "S", "text": "h (outcome: met: 0.9%)"}])
        self.assertNotIn("why:", nextstep.markdown([nextstep._step("w", nextstep.YOU, "h")]))
        # A parent outside the Specs folder is named, and the walk stops there.
        self.assertEqual(workitems.why({"id": "S", "parent": "EPIC-9"}, {}, None), [{"kind": "parent", "id": "EPIC-9", "text": "not in the Specs folder"}])


@unittest.skipUnless(shutil.which("git"), "git is required")
class BacklogTests(Base):
    def setUp(self):
        super().setUp()
        self.write(
            "specs/SPEC-1.md",
            spec("SPEC-1", "ready", 'labels = ["area:billing"]', '[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["a/**"]\nassignee = "agent:developer"\n'),
        )
        self.write("specs/SPEC-2.md", spec("SPEC-2", "blocked", 'blocked_on = "the vendor"\nlabels = ["customer-ask"]'))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "done"))
        self.write("specs/SPEC-4.md", spec("SPEC-4", "in_review"))
        self.commit("specs")
        self.write("specs/SPEC-5.md", spec("SPEC-5", "ready", tasks='[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["b/**"]\nassignee = "agent:tester"\n'))
        self.commit("someone else's spec", author="Bea")
        git(self.root, "checkout", "-qb", "feat")

    def test_default_next_is_unchanged_and_all_reads_every_spec_at_head(self):
        self.assertEqual(self.codes(), [("nothing_open", "")])  # this branch changes no Spec
        codes = dict((w, c) for c, w in self.codes(all=True))
        self.assertEqual(
            codes,
            {"specs/SPEC-4.md": "spec.in_review", "specs/SPEC-2.md": "spec.blocked", "specs/SPEC-1.md": "spec.ready", "specs/SPEC-5.md": "spec.ready"},
        )  # SPEC-3 is done: nothing to do, so not in the backlog
        # An uncommitted Spec on the branch is not at HEAD.
        self.write("specs/SPEC-6.md", spec("SPEC-6"))
        self.assertNotIn("specs/SPEC-6.md", [w for _, w in self.codes(all=True)])
        self.assertIn(("spec.draft", "specs/SPEC-6.md"), self.codes())

    def test_every_step_carries_its_group(self):
        groups = {s["where"]: s["group"] for s in self.plan(all=True)}
        self.assertEqual(groups["specs/SPEC-4.md"], "started")
        self.assertEqual(groups["specs/SPEC-1.md"], "unstarted")
        here = os.getcwd()
        os.chdir(self.root)
        try:
            code, out = run_cli("next", "--all", "--json", "--label", "area:billing")
        finally:
            os.chdir(here)
        self.assertEqual(code, 0, out)
        (step,) = json.loads(out)
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

    def test_mine_includes_a_task_assigned_to_me(self):
        git(self.root, "checkout", "-q", "main")
        self.write("specs/SPEC-7.md", spec("SPEC-7", "ready", tasks='[[tasks]]\nid = "T1"\ntitle = "t"\nscope = ["c/**"]\nassignee = "@a-login"\n'))
        self.commit("bea's", author="Bea")
        with mock.patch("aidd.repo.operator_login", return_value="a-login"):
            self.assertIn("specs/SPEC-7.md", [w for _, w in self.codes(all=True, mine=True)])
        self.assertNotIn("specs/SPEC-7.md", [w for _, w in self.codes(all=True, mine=True)])

    def test_the_approver_inbox_and_its_queue_limit(self):
        with mock.patch("aidd.repo.operator_login", return_value="lead"):
            self.assertEqual(self.codes(all=True, waiting_on_me=True), [("spec.in_review", "specs/SPEC-4.md")])
            git(self.root, "checkout", "-q", "main")
            for i in range(10, 13):
                self.write(f"specs/SPEC-{i}.md", spec(f"SPEC-{i}", "in_review"))
            self.commit("three more")
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

    def test_a_wait_past_the_limit_is_escalated_to_the_backup_pool(self):
        git(self.root, "checkout", "-q", "main")
        self.config(owners='backup_approvers = ["@backup"]\n', gates="escalate_after_minutes = 60\n")
        self.write("specs/SPEC-4.md", spec("SPEC-4", "in_progress"))
        self.commit("back to work", when="2026-09-25T12:00:00Z")
        self.write("specs/SPEC-4.md", spec("SPEC-4", "in_review"))
        self.commit("in review", when="2026-09-26T12:00:00Z")
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
        proposed = 'proposed_by = "agent:sre"\n'
        self.assertEqual(self.errors(self.valid(proposed)), [])  # a draft waits for triage
        (err,) = self.errors(self.valid(proposed, "ready"))
        self.assertIn("status ready needs triage: agent:sre proposed this work", err)
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
        # A person's own Spec needs no triage.
        self.assertEqual(self.errors(self.valid("", "ready")), [])

    def test_the_schema_requires_until_for_a_snooze_and_duplicate_of_for_a_duplicate(self):
        base = self.valid('proposed_by = "agent:sre"\n')
        for triage, needed in (
            ('{ decision = "snoozed", by = "@lead", on = 2026-09-20 }', "until"),
            ('{ decision = "duplicate", by = "@lead", on = 2026-09-20 }', "duplicate_of"),
        ):
            errs = self.errors(base.replace('proposed_by = "agent:sre"\n', f'proposed_by = "agent:sre"\ntriage = {triage}\n'))
            self.assertTrue(any(needed in e for e in errs), errs)

    def test_next_asks_a_person_to_triage_first_and_hides_snoozed_work_until_its_date(self):
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='proposed_by = "agent:sre"'))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "ready"))
        steps = self.plan()
        self.assertEqual([s["code"] for s in steps], ["spec.triage", "spec.ready"])
        self.assertEqual(steps[0]["who"], nextstep.PERSON)
        self.assertIn("SPEC-1 was proposed by agent:sre", steps[0]["what"])
        snooze = 'proposed_by = "agent:sre"\ntriage = {{ decision = "snoozed", by = "@lead", on = 2026-09-01, until = {} }}'
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra=snooze.format("2026-10-15")))
        self.assertEqual([s["code"] for s in self.plan()], ["spec.ready"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra=snooze.format("2026-09-20")))
        (step,) = [s for s in self.plan() if s["where"] == "specs/SPEC-1.md"]
        self.assertEqual(step["code"], "spec.triage")
        self.assertIn("snooze ended on 2026-09-20", step["what"])
        for decision in ('decision = "declined"', 'decision = "duplicate", duplicate_of = "SPEC-2"'):
            self.write("specs/SPEC-1.md", spec("SPEC-1", extra=f'proposed_by = "agent:sre"\ntriage = {{ {decision}, by = "@lead", on = 2026-09-01 }}'))
            self.assertEqual([s["code"] for s in self.plan()], ["spec.ready"])
        self.write("specs/SPEC-1.md", spec("SPEC-1", extra='proposed_by = "agent:sre"\ntriage = { decision = "accepted", by = "@lead", on = 2026-09-01 }'))
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
                ("specs/D.md", {"kind": "spec", "id": "D", "triage": {"decision": "duplicate", "duplicate_of": "Z"}}),
            ]
        )
        self.assertEqual(len(errors), 4, errors)
        self.assertTrue(any("relates_to SPEC-9: no Spec, Epic, or Initiative" in e for e in errors))
        self.assertTrue(any("blocks INIT-1 points at itself" in e for e in errors))
        self.assertTrue(any("triage.duplicate_of Z" in e for e in errors))
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
        # Once SPEC-1 is done, both go ahead.
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", 'relations = [{ type = "blocks", id = "SPEC-4" }]'))
        codes = {s["where"]: s["code"] for s in self.plan()}
        self.assertEqual((codes["specs/SPEC-2.md"], codes["specs/SPEC-4.md"]), ("spec.ready", "spec.draft"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class HandoffTests(Base):
    def test_the_latest_note_names_the_role_and_a_need_becomes_a_persons_step(self):
        git(self.root, "checkout", "-qb", "feat")
        body = "\n## Context\n" + handoff("developer", done="old") + handoff("tester", needs="pick the retry limit: 3 or 5")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_progress", body=body))
        steps = self.plan()
        (main,) = [s for s in steps if s["code"] == "spec.in_progress"]
        self.assertEqual(main["who"], "your agent (tester)")
        self.assertEqual(main["handoff"]["next"], "tester")
        (need,) = [s for s in steps if s["code"] == "spec.needs"]
        self.assertEqual((need["who"], need["what"]), (nextstep.YOU, "SPEC-1 needs a person: pick the retry limit: 3 or 5"))
        self.assertLess(steps.index(need), steps.index(main))  # a person's step before the agent's

    def test_a_note_asking_for_an_approval_puts_it_in_the_approver_inbox(self):
        git(self.root, "checkout", "-qb", "feat")
        self.write("specs/SPEC-1.md", spec("SPEC-1", "draft", body=handoff("spec-approval")))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "in_progress", body=handoff("merge-approval")))
        by = {s["where"]: s for s in self.plan()}
        self.assertEqual((by["specs/SPEC-1.md"]["code"], by["specs/SPEC-1.md"]["who"]), ("spec.spec_approval", nextstep.APPROVER))
        self.assertEqual((by["specs/SPEC-2.md"]["code"], by["specs/SPEC-2.md"]["who"]), ("spec.merge_approval", nextstep.APPROVER))
        with mock.patch("aidd.repo.operator_login", return_value="lead"):
            self.assertEqual(sorted(c for c, _ in self.codes(waiting_on_me=True)), ["spec.merge_approval", "spec.spec_approval"])

    def test_parsing_and_validate_warnings(self):
        text = (
            handoff("tester")
            + "```aidd-handoff\nnext = \n```\n"
            + handoff("nobody")
            + '```aidd-handoff\ndone = "x"\nnext = "reviewer"\nneeds = ["a", "none"]\nstopped_at = "none"\nspend = 3\nmood = "ok"\n```\n'
        )
        self.assertEqual(workitems.latest_handoff(text)["next"], "reviewer")
        self.assertEqual(workitems.needs(workitems.latest_handoff(text)), ["a"])
        warnings = workitems.handoff_warnings("s.md", text)
        self.assertEqual(len(warnings), 3, warnings)
        self.assertTrue(any("handoff note 2 is not TOML" in w for w in warnings))
        self.assertTrue(any("next 'nobody' is neither a role" in w for w in warnings))
        self.assertTrue(any("keys aidd does not read: mood" in w for w in warnings))
        self.assertIsNone(workitems.latest_handoff('```aidd-handoffx\nnext = "tester"\n```\n'))
        self.assertIn("aidd-handoff", hooks.HANDOFF_REMINDER)

    def test_a_handoff_note_labels_relations_and_triage_never_void_spec_approval(self):
        text = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        tree = {"tests/checkout/test_rate_limit.py": "a" * 40}
        before = model.spec_hash(text, tree)
        bookkeeping = text.replace(
            'kind = "spec"\n',
            'kind = "spec"\nlabels = ["area:checkout"]\nrelations = [{ type = "relates_to", id = "SPEC-1" }]\n'
            'triage = { decision = "accepted", by = "@lead", on = 2026-09-01 }\n',
            1,
        )
        self.assertEqual(model.spec_hash(bookkeeping + handoff("tester", needs="a decision"), tree), before)
        self.assertNotEqual(model.spec_hash(text + "\nOne more Acceptance line.\n", tree), before)
        self.assertNotEqual(model.spec_hash(text + "\n```aidd-handoffx\nnext = 1\n```\n", tree), before)  # only the exact fence
        self.assertNotEqual(model.spec_hash(text.replace('kind = "spec"\n', 'kind = "spec"\nproposed_by = "agent:sre"\n', 1), tree), before)


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
        self.write("specs/SPEC-1.md", spec("SPEC-1", "released"))  # uncommitted
        log = speclog.build(self.root, "specs/SPEC-1.md", now=dt.datetime(2026, 9, 5, 9, 0, tzinfo=dt.UTC))
        self.assertEqual([t["status"] for t in log["transitions"]], ["draft", "ready", "in_review", "released"])
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
                    'triage = { decision = "accepted", by = "@checkout-lead", on = 2026-09-01 }\n',
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
            for word in ("relations", "labels", "triage", "aidd-handoff", "workitems", "max_open_per_approver", "escalate_after_minutes", "backup_approvers"):
                self.assertIsNone(re.search(rf"\b{re.escape(word)}\b", text), f"{module} reads {word}")


if __name__ == "__main__":
    unittest.main()
