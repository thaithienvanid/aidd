"""Small goals: how an Epic ships (`incremental`, `flagged`, `batched`), the checks that keep its Specs consistent with it, the
launch that stays a person's, and the goal steps `aidd list` gives."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import git, make_repo

from aidd import workitems
from aidd.tracking import goal_status, next_steps
from aidd.workitems import authoring

EPIC = {"kind": "epic", "id": "EPIC-1", "ships": "batched", "specs": ["SPEC-1", "SPEC-2"]}


def spec(**kw) -> dict:
    return {"kind": "spec", "id": "SPEC-1", "parent": "EPIC-1"} | kw


class SmallGoalCheckTests(unittest.TestCase):
    def check(self, *objects: dict) -> tuple[list[str], list[str]]:
        return workitems.small_goal_checks([(f"specs/{d['id']}.md", d) for d in objects])

    def test_a_batched_spec_ships_into_its_goal_branch(self):
        self.assertEqual(workitems.goal_branch("EPIC-1"), "goal/EPIC-1")
        self.assertEqual(workitems.goal_branch("team:EPIC-1"), "goal/team-EPIC-1")
        (err,) = self.check(EPIC, spec())[0]
        self.assertIn("set `base: goal/EPIC-1`", err)
        self.assertEqual(self.check(EPIC, spec(base="goal/EPIC-1")), ([], []))
        (err,) = self.check(EPIC, spec(base="goal/EPIC-9"))[0]
        self.assertIn("goal/EPIC-1", err)

    def test_an_incremental_or_flagged_spec_merges_to_the_default_branch(self):
        for mode in ("incremental", "flagged"):
            (err,) = self.check(EPIC | {"ships": mode}, spec(base="goal/EPIC-1", flags=[{"name": "x"}]))[0]
            self.assertIn("merges to the default branch", err)
        self.assertEqual(self.check({"kind": "epic", "id": "EPIC-1"}, spec()), ([], []))  # incremental by default

    def test_a_flagged_spec_ships_behind_a_flag_and_the_launch_turns_it_on(self):
        flagged = EPIC | {"ships": "flagged", "launch": "SPEC-2"}
        (warning,) = self.check(flagged, spec())[1]
        self.assertIn("feature flag", warning)
        self.assertEqual(self.check(flagged, spec(flags=[{"name": "booking"}]), spec(id="SPEC-2")), ([], []))
        (err,) = self.check(EPIC | {"launch": "SPEC-2"}, spec(base="goal/EPIC-1"))[0]
        self.assertIn("set `ships: flagged`", err)
        (warning,) = self.check(flagged | {"launch": "SPEC-9"}, spec(flags=[{"name": "b"}]))[1]
        self.assertIn("plan it last", warning)

    def test_one_spec_needs_no_goal_branch(self):
        (warning,) = self.check(EPIC | {"specs": ["SPEC-1"]})[1]
        self.assertIn("ships: incremental", warning)

    def test_the_launch_is_the_epics_named_spec(self):
        idx = {"EPIC-1": EPIC | {"ships": "flagged", "launch": "SPEC-2"}}
        self.assertTrue(workitems.is_launch(spec(id="SPEC-2"), idx))
        self.assertFalse(workitems.is_launch(spec(), idx))
        self.assertFalse(workitems.is_launch(spec(id="SPEC-2", parent="EPIC-9"), idx))


class SmallGoalStepTests(unittest.TestCase):
    def ready(self, **kw) -> dict:
        return {"branch": "goal/EPIC-1", "integrated": ["SPEC-1", "SPEC-2"], "release_ready": True} | kw

    def test_a_ready_goal_waits_for_the_person_or_ships_under_their_standing_approval(self):
        (s,) = goal_status.goal_steps([self.ready()], None, set())
        self.assertEqual((s["code"], s["who"], s["id"]), ("goal.release", workitems.APPROVER, "goal/EPIC-1"))
        (s,) = goal_status.goal_steps([self.ready()], {"scope": "all"}, set())
        self.assertEqual((s["code"], s["who"]), ("goal.ship_ready", workitems.AGENT))
        (s,) = goal_status.goal_steps([self.ready()], {"scope": "all-but-major"}, {"SPEC-2"})
        self.assertEqual(s["code"], "goal.release")  # a major Spec inside keeps the release the person's
        self.assertEqual(goal_status.goal_steps([self.ready(release_ready=False)], None, set()), [])

    def test_the_launch_spec_is_written_once_the_rest_shipped(self):
        flagged = SimpleNamespace(
            data={"kind": "epic", "id": "EPIC-1", "ships": "flagged", "specs": ["SPEC-1", "SPEC-2"], "launch": "SPEC-2"},
            id="EPIC-1",
            rel="specs/EPIC-1.md",
            status="active",
        )
        one = SimpleNamespace(data={"id": "SPEC-1", "flags": [{"name": "booking"}]})
        ctx = SimpleNamespace(items={"SPEC-1": one}, status={"SPEC-1": "in_review"}, team=True)
        self.assertEqual(next_steps._launch_step(flagged, ctx), [])  # SPEC-1 still in review
        ctx.status["SPEC-1"] = "shipped"
        (s,) = next_steps._launch_step(flagged, ctx)
        self.assertEqual((s["code"], s["who"]), ("epic.launch_spec", workitems.AGENT))
        self.assertIn("booking", s["what"])
        ctx.items["SPEC-2"] = SimpleNamespace(data={"id": "SPEC-2"})
        self.assertEqual(next_steps._launch_step(flagged, ctx), [])  # written: its own steps go on

    def test_a_small_goal_waits_for_the_one_it_is_blocked_by(self):
        idx = {"EPIC-1": {"kind": "epic", "id": "EPIC-1", "relations": [{"type": "blocked_by", "id": "EPIC-0"}]}, "EPIC-0": {"kind": "epic", "id": "EPIC-0"}}
        self.assertEqual(workitems.waiting_on(spec(), idx, lambda i: False), ["EPIC-0"])
        self.assertEqual(workitems.waiting_on(spec(), idx, lambda i: True), [])


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewSpecTests(unittest.TestCase):
    def test_a_spec_of_a_together_epic_takes_its_goal_as_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team")
            (root / "specs" / "EPIC-1.md").write_text("---\nkind: epic\nid: EPIC-1\ntitle: Rename\nships: batched\n---\n", encoding="utf-8")
            path = authoring.new_object(root, authoring.NewObject(kind="spec", id="SPEC-1", title="Rename the core", parent="EPIC-1"))
            self.assertIn("base: goal/EPIC-1", path.read_text(encoding="utf-8"))
            (root / "specs" / "EPIC-2.md").write_text("---\nkind: epic\nid: EPIC-2\ntitle: Export\n---\n", encoding="utf-8")
            path = authoring.new_object(root, authoring.NewObject(kind="spec", id="SPEC-2", title="Export CSV", parent="EPIC-2"))
            self.assertNotIn("base:", path.read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class CatchUpTests(unittest.TestCase):
    """A goal another machine integrated into: the local goal fast-forwards to its upstream, and one that went two ways
    is a person's to bring together."""

    def test_the_goal_catches_up_with_its_upstream(self):
        import contextlib

        from aidd.cli.commands import goals

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            git(base, "init", "-q", "--bare", "-b", "main", "origin.git")
            here, there = base / "here", base / "there"
            for clone in (here, there):
                git(base, "clone", "-q", str(base / "origin.git"), clone.name)
                for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
                    git(clone, "config", k, v)
            git(here, "commit", "-q", "--allow-empty", "-m", "day 0")
            git(here, "push", "-q", "origin", "HEAD:main")
            git(here, "switch", "-qc", "goal/EPIC-1")
            git(here, "push", "-q", "-u", "origin", "goal/EPIC-1")
            git(here, "switch", "-q", "main")
            git(there, "fetch", "-q")
            git(there, "switch", "-q", "goal/EPIC-1")
            git(there, "commit", "-q", "--allow-empty", "-m", "integrated elsewhere")
            git(there, "push", "-q")
            with contextlib.chdir(here):
                self.assertIsNone(goals._catch_up("goal/EPIC-1"))
            self.assertEqual(git(here, "rev-parse", "goal/EPIC-1"), git(there, "rev-parse", "HEAD"))
            git(here, "update-ref", "refs/heads/goal/EPIC-1", git(here, "commit-tree", "-p", "goal/EPIC-1", "-m", "local", "goal/EPIC-1^{tree}"))
            git(there, "commit", "-q", "--allow-empty", "-m", "and again")
            git(there, "push", "-q")
            with contextlib.chdir(here):
                self.assertIn("went two ways", goals._catch_up("goal/EPIC-1") or "")


@unittest.skipUnless(shutil.which("git"), "git is required")
class LaunchTests(unittest.TestCase):
    def test_a_branch_carrying_the_launch_is_never_covered_by_a_standing_approval(self):
        import contextlib

        from aidd import config
        from aidd.cli.commands import standing

        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team", branch=None)
            epic = "---\nkind: epic\nid: EPIC-1\ntitle: Booking\nships: flagged\nspecs: [SPEC-1, SPEC-2]\nlaunch: SPEC-2\n---\n"
            (root / "specs" / "EPIC-1.md").write_text(epic, encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "plan")
            git(root, "switch", "-qc", "spec/SPEC-2")
            (root / "specs" / "SPEC-2.md").write_text("---\nkind: spec\nid: SPEC-2\ntitle: Turn booking on\nparent: EPIC-1\n---\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "spec: SPEC-2")
            with contextlib.chdir(root):
                cfg = config.load_file(config.CONFIG_PATH, str(root))
                self.assertEqual(standing.launching(cfg), "SPEC-2 of EPIC-1")
                git(root, "switch", "-qc", "spec/SPEC-1", "main")
                self.assertIsNone(standing.launching(cfg))
                # A branch named for another Spec that carries the launch too is still a launch.
                (root / "specs" / "SPEC-1.md").write_text("---\nkind: spec\nid: SPEC-1\ntitle: Book\nparent: EPIC-1\n---\n", encoding="utf-8")
                git(root, "add", "-A")
                git(root, "commit", "-qm", "spec: SPEC-1")
                git(root, "merge", "-q", "--no-edit", "spec/SPEC-2")
                self.assertEqual(standing.launching(cfg), "SPEC-2 of EPIC-1")

    def test_a_subject_never_forges_an_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team", branch=None)
            git(root, "switch", "-qc", "goal/EPIC-1")
            git(root, "switch", "-qc", "spec/SPEC-1")
            git(root, "commit", "-q", "--allow-empty", "-m", "work")
            git(root, "switch", "-q", "goal/EPIC-1")
            git(root, "merge", "-q", "--no-ff", "-m", "Aidd-Integrate: SPEC-9", "spec/SPEC-1")
            self.assertEqual(workitems.integrated(str(root), "goal/EPIC-1"), {})
            git(root, "commit", "-q", "--allow-empty", "-m", "a later one")
            git(root, "switch", "-q", "spec/SPEC-1")
            git(root, "commit", "-q", "--allow-empty", "-m", "more")
            git(root, "switch", "-q", "goal/EPIC-1")
            git(root, "merge", "-q", "--no-ff", "-m", "feat: x (SPEC-1)\n\nAidd-Integrate: SPEC-1", "spec/SPEC-1")
            self.assertEqual(list(workitems.integrated(str(root), "goal/EPIC-1")), ["SPEC-1"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class TrunkFlowTests(unittest.TestCase):
    """Trunk-based work (DORA): three or fewer branches with unmerged work, each landed within days; `aidd sync`
    keeps a branch current with the default branch."""

    def test_old_and_many_branches_are_flagged_and_sync_takes_the_default_branch(self):
        import os
        import subprocess

        from aidd import config
        from helpers import aidd_subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team", branch=None)
            old = {**os.environ, "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00"}
            for n in range(4):
                git(root, "switch", "-qc", f"feat/{n}", "main")
                subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", f"work {n}"], cwd=root, check=True, env=old if n == 0 else None)
            branches = workitems.work_branches(str(root))
            self.assertEqual([b["branch"] for b in branches][0], "feat/0")  # oldest first
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            warnings = workitems.flow_warnings(branches, cfg)
            self.assertTrue(any("past gates.max_open_branches = 3" in w for w in warnings), warnings)
            self.assertTrue(any(w.startswith("feat/0 is ") and "max_branch_days = 2" in w for w in warnings), warnings)
            git(root, "switch", "-q", "main")
            git(root, "commit", "-q", "--allow-empty", "-m", "moved")
            git(root, "switch", "-q", "feat/1")
            run = aidd_subprocess("sync", cwd=root)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("synced main", run.stdout)
            behind = {b["branch"]: b["behind"] for b in workitems.work_branches(str(root))}
            self.assertEqual((behind["feat/1"], behind["feat/2"]), (0, 1))


@unittest.skipUnless(shutil.which("git"), "git is required")
class LadderTests(unittest.TestCase):
    """The decision ladder of each small goal: D1 the plan, D2 Spec approval, D3 the release, D4 the launch."""

    def test_each_small_goal_says_where_each_decision_stands(self):
        from aidd.kernel import json_schema

        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team", branch=None)
            plan = {
                "INIT-1": "---\nkind: initiative\nid: INIT-1\ntitle: Booking\n---\n",
                "EPIC-1": "---\nkind: epic\nid: EPIC-1\ntitle: Search\nparent: INIT-1\nspecs: [SPEC-1, SPEC-2]\n---\n",
                "EPIC-2": "---\nkind: epic\nid: EPIC-2\ntitle: Reserve\nparent: INIT-1\nships: batched\nspecs: [SPEC-3, SPEC-4]\n---\n",
                "EPIC-3": "---\nkind: epic\nid: EPIC-3\ntitle: Notify\nships: flagged\nspecs: [SPEC-5, SPEC-6]\nlaunch: SPEC-6\n---\n",
            }
            for name, text in plan.items():
                (root / "specs" / f"{name}.md").write_text(text, encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "plan")
            item = lambda i, status, parent: SimpleNamespace(id=i, status=status, data={"parent": parent})  # noqa: E731
            specs = [
                item("SPEC-1", "shipped", "EPIC-1"),
                item("SPEC-2", "in_review", "EPIC-1"),
                item("SPEC-3", "in_review", "EPIC-2"),
                item("SPEC-5", "shipped", "EPIC-3"),
                item("SPEC-6", "in_review", "EPIC-3"),
            ]
            steps = [
                {"id": "SPEC-2", "code": "spec.in_review", "who": workitems.APPROVER},
                {"id": "SPEC-6", "code": "spec.in_review", "who": workitems.APPROVER},
                {"id": "SPEC-4", "code": "spec.spec_approval", "who": workitems.APPROVER},
            ]
            goals = [{"branch": "goal/EPIC-2", "integrated": ["SPEC-3"], "release_ready": False}]
            shaped = goal_status.small_goal_ladders(str(root), None, steps, specs, goals)
            by = {g["id"]: g for g in shaped["small_goals"]}
            self.assertEqual(shaped["initiatives"], [{"id": "INIT-1", "title": "Booking", "small_goals": ["EPIC-1", "EPIC-2"]}])
            self.assertEqual((by["EPIC-1"]["release"], by["EPIC-1"]["launch"]), ({"done": 1, "total": 2, "waits": ["SPEC-2"]}, None))
            self.assertEqual(by["EPIC-2"]["branch"], "goal/EPIC-2")
            self.assertEqual(by["EPIC-2"]["specs"], [{"id": "SPEC-3", "status": "integrated"}, {"id": "SPEC-4", "status": "planned"}])
            self.assertEqual(by["EPIC-2"]["spec_approval"], {"done": 1, "total": 2, "waits": ["SPEC-4"]})
            self.assertEqual(by["EPIC-2"]["release"], {"done": 0, "total": 1, "waits": []})
            self.assertEqual(by["EPIC-3"]["release"], {"done": 1, "total": 1, "waits": []})  # the launch is its own rung
            self.assertEqual(by["EPIC-3"]["launch"], {"spec": "SPEC-6", "state": "waits"})
            shown = {"schema_version": "1", "goals": [], "flow": {"branches": [], "warnings": []}} | shaped
            self.assertEqual(json_schema.validate(shown, "goal-list.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
