"""Intents: work bigger than one Spec, with its slices grouped into phases, and the stage each Spec stands in.

`aidd status` derives each slice's status, each Intent's progress and next step (agree, slice, close), and each Spec's
stage, from the files alone. `aidd validate` checks the slices across the repository. The tests read codes, fields, and ids,
never whole sentences."""

import datetime as dt
import json
import os
import unittest

from helpers import SAMPLE_SPEC, RepoTemplateCase, git, make_repo, run_cli
from test_workitems import Base, intent, spec

from aidd.kernel import documents, json_schema
from aidd.workitems import all_branches, intent_checks, intents, validation, work_list

TODAY = dt.date(2026, 9, 28)
AGREED = 'agreed_by: "Dana <dana@example.com>"\nagreed_at: "2026-09-01T09:00:00Z"\n'
TWO_PHASES = (
    "phases:\n"
    '  - id: P1\n    name: Walking skeleton\n    due: "2026-10-15"\n    slices:\n'
    "      - {id: SPEC-1, title: Status endpoint}\n"
    "      - {id: SPEC-2, title: Status panel, blocked_by: [SPEC-1]}\n"
    "  - id: P2\n    name: Adjusters\n    slices:\n"
    "      - {id: SPEC-3, title: Adjusters see it}\n"
    "      - {id: SPEC-4, title: Adjusters filter it}\n"
)
DONE_TASKS = 'tasks:\n  - {id: T1, title: t, scope: ["a/**"], done: true}\n  - {id: T2, title: t, scope: ["b/**"], done: true}\n'
OPEN_TASKS = 'tasks:\n  - {id: T1, title: t, scope: ["a/**"], done: true}\n  - {id: T2, title: t, scope: ["b/**"]}\n'


def valid_spec(sid: str, parent: str, extra: str = "") -> str:
    """A Spec that passes its schema, under `parent`, so `aidd validate` shows only the findings a test is after."""
    return SAMPLE_SPEC.replace("SPEC-220", sid).replace("\nroute: ", f"\nparent: {parent}\n{extra}route: ", 1)


class StageTests(Base):
    """A Spec's stage comes from its stored status, its Tasks, and its observe window, in `loop.stages` order."""

    OBSERVE = 'observe: {window: "7d"}\n'
    CASES = (
        # (what, status, extra front matter, tasks, the stage; "" for none)
        ("a draft", "draft", "", "", "Design"),
        ("a ready Spec", "ready", "", "", "Design"),
        ("an approved Spec", "approved", "", "", "Build"),
        ("in progress with a Task not done", "in_progress", "", OPEN_TASKS, "Build"),
        ("in progress with every Task done", "in_progress", "", DONE_TASKS, "Test"),
        ("in review, waiting at Merge approval", "in_review", "", "", "Test"),
        ("done inside its observe window", "done", OBSERVE + 'outcome: {released_on: "2026-09-25"}\n', "", "Deploy"),
        ("done with its observe window passed", "done", OBSERVE + 'outcome: {released_on: "2026-09-01"}\n', "", "Maintain"),
        ("done with its observe result recorded", "done", OBSERVE + 'outcome: {released_on: "2026-09-25", observe_result: pass}\n', "", "Maintain"),
        ("done with no observe window", "done", "", "", "Maintain"),
        ("rolled back", "rolled_back", "", "", "Maintain"),
        ("cancelled", "cancelled", "", "", ""),
    )

    def test_each_status_stands_in_its_stage(self):
        stage_names = [name for name, _ in intents.stages()]
        for what, state, extra, tasks, want in self.CASES:
            with self.subTest(what):
                self.assertTrue(want == "" or want in stage_names, want)
                self.write("specs/SPEC-1.md", spec("SPEC-1", state, extra, tasks))
                item = self.items(include_done=True).get("SPEC-1", {})
                self.assertEqual(item.get("stage", ""), want)


class SliceStatusTests(Base):
    """A slice is planned until it has a Spec file, which then gives its status, or until its line records `merged_in`."""

    def setUp(self):
        super().setUp()
        self.write(
            "specs/INTENT-1.md", intent("INTENT-1", "g", AGREED + TWO_PHASES.replace("Adjusters filter it}", 'Adjusters filter it, merged_in: "3f2c1a9"}'))
        )
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_review", "parent: INTENT-1"))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "draft", "parent: INTENT-1"))

    def test_each_slice_has_its_status_and_its_stage_in_phase_order(self):
        got = self.items()["INTENT-1"]
        self.assertEqual(
            [(p.get("id"), p.get("name"), p.get("due")) for p in got["phases"]], [("P1", "Walking skeleton", "2026-10-15"), ("P2", "Adjusters", None)]
        )
        slices = [(s["id"], s["status"], s.get("stage")) for p in got["phases"] for s in p["slices"]]
        self.assertEqual(
            slices,
            [("SPEC-1", "in_review", "Test"), ("SPEC-2", "planned", "Plan"), ("SPEC-3", "draft", "Design"), ("SPEC-4", "done", None)],
        )
        self.assertEqual(got["progress"], {"finished": 1, "total": 4}, "the merged slice is finished; a planned one counts as left")
        self.assertEqual(got["status"], "active", "a slice in review has started")

    def test_a_spec_that_names_the_intent_but_is_no_slice_is_still_its_child(self):
        self.write("specs/SPEC-9.md", spec("SPEC-9", "done", "parent: INTENT-1"))
        self.assertEqual(self.items()["INTENT-1"]["progress"], {"finished": 2, "total": 5})

    def test_an_intent_with_one_phase_lists_that_phase(self):
        self.write("specs/INTENT-2.md", intent("INTENT-2", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-7, title: a}, {id: SPEC-8, title: b}]}]\n"))
        (phase,) = self.items()["INTENT-2"]["phases"]
        self.assertEqual((phase.get("id"), [s["status"] for s in phase["slices"]]), ("P1", ["planned", "planned"]))
        self.assertEqual(self.items()["INTENT-2"]["status"], "draft", "no slice has started")

    def test_the_answer_is_valid_under_the_status_schema(self):
        self.assertEqual(json_schema.validate({"schema_version": "1", **self.work()}, "status.schema.json"), [])


class PhaseLineTests(unittest.TestCase):
    """The progress line under an Intent, from the answer's phases alone."""

    def phases(self, *groups):
        return {
            "phases": [
                {"id": f"P{n}", "name": f"N{n}", "slices": [{"id": i, "status": s, **({"stage": g} if g else {})} for i, s, g in slices]}
                for n, slices in enumerate(groups, 1)
            ]
        }

    def test_each_shape_of_phases(self):
        cases = (
            # (what, the phases, fragments the line holds, fragments it never holds)
            (
                "the first phase open",
                self.phases([("S1", "in_progress", "Build"), ("S2", "planned", "Plan")], [("S3", "planned", "Plan")]),
                ("Phase 1 · N1: ", "S1 in Build", "S2 planned", "1 planned in 1 more phase"),
                ("S3", "P1"),
            ),
            (
                "the first phase finished",
                self.phases([("S1", "done", "Maintain")], [("S2", "planned", "Plan"), ("S3", "planned", "Plan")]),
                ("Phase 1 · N1: done", "Phase 2 · N2: ", "S2 planned", "S3 planned"),
                ("S1", "more phase"),
            ),
            ("a finished slice beside an open one", self.phases([("S1", "done", "Maintain"), ("S2", "draft", "Design")]), ("S2 in Design",), ("S1",)),
            (
                "two more phases",
                self.phases([("S1", "approved", "Build")], [("S2", "planned", "Plan")], [("S3", "planned", "Plan")]),
                ("2 planned in 2 more phases",),
                (),
            ),
        )
        for what, item, holds, never in cases:
            with self.subTest(what):
                line = intents.phase_line(item)
                for fragment in holds:
                    self.assertIn(fragment, line)
                for fragment in never:
                    self.assertNotIn(fragment, line)

    def test_a_finished_phase_says_when_and_no_phase_says_nothing(self):
        done = self.phases([("S1", "done", "Maintain"), ("S2", "cancelled", None)], [("S3", "done", "Maintain")])
        done["phases"][1]["finished_on"] = "2026-11-14"
        cases = (
            ("every phase finished", done, "Phase 2 · N2: done 14 Nov"),
            (
                "one phase with no id or name, which a valid Intent has none of",
                {"phases": [{"slices": [{"id": "S1", "status": "planned", "stage": "Plan"}]}]},
                "S1 planned",
            ),
            ("no phase", {"phases": []}, ""),
            ("nothing", {}, ""),
        )
        for what, item, line in cases:
            with self.subTest(what):
                self.assertEqual(intents.phase_line(item), line)


class IntentStepTests(Base):
    """An Intent's next step: a person agrees to it, the agent starts its ready slices, and a person closes it."""

    CASES = (
        # (what, the Intent's extra front matter, the Spec files as {id: status}, the code or None, who, ids the step names)
        ("slices with no agreement", TWO_PHASES, {}, "intent.agree", "person", ()),
        ("agreed, with ready slices", AGREED + TWO_PHASES, {}, "intent.slice", "agent", ("SPEC-1", "SPEC-3", "SPEC-4")),
        ("agreed, a slice waits for one not merged", AGREED + TWO_PHASES, {"SPEC-1": "in_progress", "SPEC-3": "draft", "SPEC-4": "draft"}, None, None, ()),
        (
            "agreed, the slice it waits for is done",
            AGREED + TWO_PHASES,
            {"SPEC-1": "done", "SPEC-3": "draft", "SPEC-4": "draft"},
            "intent.slice",
            "agent",
            ("SPEC-2",),
        ),
        (
            "every slice finished",
            AGREED + TWO_PHASES,
            {"SPEC-1": "done", "SPEC-2": "cancelled", "SPEC-3": "rolled_back", "SPEC-4": "done"},
            "intent.close",
            "person",
            (),
        ),
        (
            "every slice finished, though never agreed",
            TWO_PHASES,
            {"SPEC-1": "done", "SPEC-2": "done", "SPEC-3": "done", "SPEC-4": "done"},
            "intent.close",
            "person",
            (),
        ),
        ("no slices and no Specs", "", {}, None, None, ()),
    )

    def test_each_state_has_its_step(self):
        for what, extra, files, code, who, named in self.CASES:
            with self.subTest(what):
                for p in (self.root / "specs").glob("*.md") if (self.root / "specs").is_dir() else ():
                    p.unlink()
                self.write("specs/INTENT-1.md", intent("INTENT-1", "g", extra).replace("status: active\n", ""))
                for sid, state in files.items():
                    self.write(f"specs/{sid}.md", spec(sid, state, "parent: INTENT-1"))
                self.commit_all()
                step = self.items()["INTENT-1"].get("next")
                self.assertEqual(step and (step["code"], step["who"]), code and (code, who))
                for sid in named:
                    self.assertIn(sid, step["what"])
                if code == "intent.slice":
                    self.assertNotIn("SPEC-2" if "SPEC-2" not in named else "SPEC-1", step["what"])

    def test_a_closed_intent_has_no_step_and_leaves_the_open_work(self):
        for stored in ("done", "cancelled"):
            with self.subTest(stored=stored):
                self.write("specs/INTENT-1.md", intent("INTENT-1", "g", AGREED + TWO_PHASES).replace("status: active", f"status: {stored}"))
                self.assertNotIn("INTENT-1", self.items())
                self.assertNotIn("next", self.items(include_done=True)["INTENT-1"])


class RepoCase(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", branch=None)

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def findings(self) -> tuple[list[str], list[str]]:
        errors, warnings = validation.check_repo(self.root, today=TODAY)
        strip = str(self.root) + "/"
        return [e.replace(strip, "") for e in errors], [w.replace(strip, "") for w in warnings]


class StatusTextTests(RepoCase):
    """`aidd status` as text: a Spec's line names its stage, and an Intent's next line shows its current phase."""

    def test_a_spec_line_names_its_stage_after_its_status(self):
        self.write("specs/SPEC-1.md", spec("SPEC-1", "approved"))
        code, out = run_cli("status")
        self.assertEqual(code, 0, out)
        line = next(ln for ln in out.splitlines() if ln.startswith("SPEC-1 "))
        self.assertIn("approved · Build stage", line)

    def test_an_intent_shows_its_current_phase_and_what_is_planned_after_it(self):
        self.write("specs/INTENT-1.md", intent("INTENT-1", "g", TWO_PHASES))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "in_review", "parent: INTENT-1"))
        code, out = run_cli("status")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        at = next(i for i, ln in enumerate(lines) if ln.startswith("INTENT-1 "))
        progress = lines[at + 1]
        self.assertTrue(progress.startswith("  Phase 1 · Walking skeleton: "), progress)
        for fragment in ("SPEC-1 in Test", "SPEC-2 planned", "2 planned in 1 more phase"):
            self.assertIn(fragment, progress)
        self.assertNotIn("SPEC-3", progress, "a later phase is counted, never listed")


class IntentBranchTests(RepoCase):
    """A `batched` Intent says where each Spec stands on `intent/<ID>`, from git on each run. A Spec's file lives on its own
    branch until it merges, so the scratch repository commits no Spec on main first: SPEC-1 merged into the Intent's branch,
    SPEC-2 on its branch alone, SPEC-3 planned (no file, no branch), SPEC-4 started here with no branch, and SPEC-5 done
    here with no branch."""

    SLICES = "reaches: batched\nphases:\n  - id: P1\n    name: p\n    slices:\n" + "".join(f"      - {{id: SPEC-{n}, title: S{n}}}\n" for n in range(1, 6))

    def branch_with_spec(self, sid: str, state: str = "in_progress") -> None:
        git(self.root, "checkout", "-qb", f"spec/{sid}", "intent/INTENT-1")
        self.write(f"specs/{sid}.md", spec(sid, state, "parent: INTENT-1"))
        git(self.root, "add", "specs")
        git(self.root, "commit", "-qm", f"{sid} work")

    def build(self, slices: str = SLICES) -> None:
        self.write("specs/INTENT-1.md", intent("INTENT-1", "g", AGREED + slices))
        self.write("specs/SPEC-4.md", spec("SPEC-4", "in_progress", "parent: INTENT-1"))
        self.write("specs/SPEC-5.md", spec("SPEC-5", "done", "parent: INTENT-1"))
        git(self.root, "add", "specs")
        git(self.root, "commit", "-qm", "the Intent, SPEC-4, and SPEC-5")
        git(self.root, "branch", "intent/INTENT-1")
        self.branch_with_spec("SPEC-1")
        git(self.root, "checkout", "-q", "intent/INTENT-1")
        git(self.root, "merge", "-q", "--no-ff", "-m", "merge SPEC-1", "spec/SPEC-1")
        self.branch_with_spec("SPEC-2")
        git(self.root, "checkout", "-q", "main")

    def answer(self, *, on: str) -> dict:
        git(self.root, "checkout", "-q", on)
        code, out = run_cli("status", "INTENT-1", "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)["items"][0]

    def places(self, item: dict) -> dict:
        return {s["id"]: s.get("spec_branch_state") for p in item["phases"] for s in p["slices"]}

    def test_each_spec_has_its_place_from_main_the_intent_branch_and_its_own_branch(self):
        self.build()
        want = {"SPEC-1": "merged", "SPEC-2": "unmerged", "SPEC-3": None, "SPEC-4": "missing", "SPEC-5": None}
        for on in ("main", "intent/INTENT-1", "spec/SPEC-2"):
            with self.subTest(on):
                item = self.answer(on=on)
                self.assertEqual(self.places(item), want)
                self.assertEqual(item["intent_branch_state"], "pending")
        code, out = run_cli("status", "INTENT-1")
        for fragment in ("SPEC-1: nothing left to merge into intent/INTENT-1", "SPEC-2: waits to merge into intent/INTENT-1", "SPEC-4: no spec/SPEC-4 branch"):
            self.assertIn(fragment, out)
        self.assertIn("Merge approval pending for intent/INTENT-1", out)
        self.assertNotIn("SPEC-3:", out)

    def test_plain_status_prints_the_same_lines(self):
        self.build()
        code, out = run_cli("status")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-2: waits to merge into intent/INTENT-1", out)

    def test_each_branch_that_is_not_there_is_said_apart(self):
        self.build()
        git(self.root, "update-ref", "refs/remotes/origin/spec/SPEC-4", "HEAD")
        self.write("specs/SPEC-6.md", spec("SPEC-6:x", "in_progress", "parent: INTENT-1"))
        self.assertEqual(self.places(self.answer(on="main"))["SPEC-4"], "remote_only")
        code, out = run_cli("status", "INTENT-1")
        self.assertIn("SPEC-4: no local spec/SPEC-4: check out origin's", out)
        git(self.root, "branch", "-qD", "spec/SPEC-2")
        self.assertIsNone(self.places(self.answer(on="main"))["SPEC-2"], "a Spec with no branch and no file here has not started")
        git(self.root, "update-ref", "-d", "refs/remotes/origin/spec/SPEC-4")
        git(self.root, "branch", "-qD", "intent/INTENT-1")
        item = self.answer(on="main")
        self.assertEqual(
            (item["intent_branch_state"], self.places(item)["SPEC-4"], self.places(item)["SPEC-1"]),
            ("missing", "intent_branch_missing", "intent_branch_missing"),
        )

    def test_an_id_git_refuses_as_a_branch_name_is_said_plainly(self):
        self.build(self.SLICES + '      - {id: "SPEC:9", title: odd}\n')
        self.write("specs/SPEC-9.md", spec("SPEC:9", "in_progress", "parent: INTENT-1"))
        self.assertEqual(self.places(self.answer(on="main"))["SPEC:9"], "invalid_name")
        code, out = run_cli("status", "INTENT-1")
        self.assertIn("cannot be a branch name", out)

    def test_the_landed_intent_has_no_pending_approval(self):
        self.build()
        git(self.root, "merge", "-q", "--no-ff", "-m", "land", "intent/INTENT-1")
        item = self.answer(on="main")
        self.assertEqual(item["intent_branch_state"], "landed")
        code, out = run_cli("status", "INTENT-1")
        self.assertNotIn("pending", out)

    def test_an_incremental_intent_says_nothing_about_branches(self):
        self.build(self.SLICES.replace("batched", "incremental"))
        item = self.answer(on="main")
        self.assertNotIn("intent_branch_state", item)
        self.assertEqual(set(self.places(item).values()), {None})
        code, out = run_cli("status", "INTENT-1")
        self.assertNotIn("intent/INTENT-1", out)

    def test_git_is_read_a_fixed_number_of_times_however_many_specs_there_are(self):
        from unittest import mock

        from aidd.kernel import git as kernel_git
        from aidd.workitems import intent_branches

        for n in range(1, 13):
            git(self.root, "branch", f"spec/SPEC-{n}")
        git(self.root, "branch", "intent/INTENT-1")
        counts = []
        real = kernel_git._git

        def counted(*a, **k):
            calls.append(a[0])
            return real(*a, **k)

        for size in (2, 12):
            slices = [{"id": f"SPEC-{n}", "status": "in_progress"} for n in range(1, size + 1)]
            item = {"id": "INTENT-1", "phases": [{"slices": slices}]}
            calls: list = []
            with mock.patch("aidd.kernel.git._git", side_effect=counted):
                intent_branches.add_to(str(self.root), [item], set())
            counts.append(len(calls))
            self.assertTrue(all(s["spec_branch_state"] in ("merged", "unmerged") for s in slices))
        self.assertEqual(counts[0], counts[1], "the reads do not grow with the Specs")

    def test_the_answer_is_valid_under_the_status_schema(self):
        self.build()
        code, out = run_cli("status", "INTENT-1", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json_schema.validate(json.loads(out), "status.schema.json"), [])


class ValidateSliceTests(RepoCase):
    """`aidd validate` checks the slices across the repository: one owner for each slice, and parents that agree."""

    CASES = (
        # (what, {path: text}, (errors or warnings, the file the finding names, a fragment of it)); None when clean
        (
            "a clean Intent that waits for its agreement",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", TWO_PHASES) + "\n## Request coverage\n\nNo request: the idea was spoken.\n"},
            None,
        ),
        (
            "an agreement no commit records",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", AGREED + TWO_PHASES)},
            ("warnings", "warning: specs/INTENT-1.md", "intent.agree"),
        ),
        (
            "a slice listed twice in one Intent",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}, {id: SPEC-1, title: b}]}]\n")},
            ("errors", "specs/INTENT-1.md", "SPEC-1"),
        ),
        (
            "a slice listed by two Intents",
            {
                "specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n"),
                "specs/INTENT-2.md": intent("INTENT-2", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n"),
            },
            ("errors", "specs/INTENT-2.md", "INTENT-1"),
        ),
        (
            "an agent in agreed_by",
            {
                "specs/INTENT-1.md": intent(
                    "INTENT-1",
                    "g",
                    'agreed_by: "agent:planner"\nagreed_at: "2026-09-01T09:00:00Z"\nphases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n',
                )
            },
            ("errors", "specs/INTENT-1.md", "agent:planner"),
        ),
        (
            "agreed_by with no agreed_at",
            {
                "specs/INTENT-1.md": intent(
                    "INTENT-1", "g", 'agreed_by: "Dana <dana@example.com>"\nphases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n'
                )
            },
            ("errors", "specs/INTENT-1.md", "agreed_at"),
        ),
        (
            "a slices list, which an Intent no longer holds",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", "slices: [{id: SPEC-9, title: a}]\n")},
            ("errors", "specs/INTENT-1.md", "`slices` was retired in 1.0.0"),
        ),
        (
            "a slice blocked by itself",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a, blocked_by: [SPEC-1]}]}]\n")},
            ("errors", "specs/INTENT-1.md", "SPEC-1"),
        ),
        (
            "a slice blocked by an id nothing has",
            {"specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a, blocked_by: [SPEC-77]}]}]\n")},
            ("errors", "specs/INTENT-1.md", "SPEC-77"),
        ),
        (
            "slices whose blocked_by form a cycle",
            {
                "specs/INTENT-1.md": intent(
                    "INTENT-1",
                    "g",
                    "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a, blocked_by: [SPEC-2]}, {id: SPEC-2, title: b, blocked_by: [SPEC-1]}]}]\n",
                )
            },
            ("errors", "specs/INTENT-1.md", "cycle"),
        ),
        (
            "a slice and a Spec's relation that form a cycle",
            {
                "specs/INTENT-1.md": intent(
                    "INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}, {id: SPEC-2, title: b, blocked_by: [SPEC-1]}]}]\n"
                ),
                "specs/SPEC-1.md": valid_spec("SPEC-1", "INTENT-1", "blocked_by: [SPEC-2]\n"),
            },
            ("errors", "", "cycle"),
        ),
        (
            "a relation to a slice with no Spec file",
            {
                "specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}, {id: SPEC-2, title: b}]}]\n"),
                "specs/SPEC-1.md": valid_spec("SPEC-1", "INTENT-1", "blocked_by: [SPEC-2]\n"),
            },
            None,
        ),
        (
            "a Spec whose parent Intent lists no slice of it",
            {
                "specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n"),
                "specs/SPEC-5.md": valid_spec("SPEC-5", "INTENT-1"),
            },
            ("warnings", "specs/SPEC-5.md", "INTENT-1"),
        ),
        (
            "a slice whose Spec names another parent",
            {
                "specs/INTENT-1.md": intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n"),
                "specs/INTENT-2.md": intent("INTENT-2", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-2, title: a}]}]\n"),
                "specs/SPEC-1.md": valid_spec("SPEC-1", "INTENT-2"),
            },
            ("warnings", "specs/SPEC-1.md", "INTENT-1"),
        ),
    )

    def test_each_shape_of_slices(self):
        for what, files, finding in self.CASES:
            with self.subTest(what):
                for p in (self.root / "specs").glob("*.md"):
                    p.unlink()
                for rel, text in files.items():
                    self.write(rel, text)
                errors, warnings = self.findings()
                found = [ln for ln in errors + warnings if ("INTENT-" in ln or "SPEC-" in ln or "cycle" in ln) and "Request coverage" not in ln]
                if finding is None:
                    self.assertEqual(found, [], what)
                    continue
                kind, path, fragment = finding
                hits = [ln for ln in (errors if kind == "errors" else warnings) if ln.startswith(path) and fragment in ln]
                self.assertTrue(hits, (what, errors, warnings))
                if kind == "warnings":
                    self.assertEqual([e for e in errors if "INTENT-" in e or "SPEC-" in e], [], what)


class RequestTests(RepoCase):
    """A request is a person's own words. A root `intent.md` with no front matter, and every file in the saved requests'
    folder, `specs/requests/`, whatever it holds, are no work item for validate, status, the work-items page, or the
    branches' index."""

    REQUEST = "# What I want\n\nCustomers see their claim status in the portal.\n\ntype: intent\n"
    # A request pasted with front matter of its own still reads as the person's words.
    SAVED = '---\ntype: intent\nid: INTENT-9\ntitle: "x"\n---\n\nShow the claim status in the portal.\n'

    def assert_no_work_item(self, rel: str, typed: bool = False) -> None:
        """No reader takes `rel` for a work item. A saved request whose front matter names an aidd type (`typed`) is one
        error of `aidd validate`, so a work item hidden there is loud, and still no work item."""
        code, out = run_cli("status", "--json")
        self.assertEqual(code, 0, out)
        answer = json.loads(out)
        self.assertEqual(answer["items"], [])
        self.assertNotIn(rel, json.dumps(answer.get("unreadable", [])))
        errors, warnings = self.findings()
        found = [ln for ln in errors + warnings if rel in ln]
        self.assertEqual(len(found), 1 if typed else 0, found)
        self.assertTrue(all("never a work item" in ln and ln in errors for ln in found), found)
        code, out = run_cli("validate")
        self.assertEqual(code, 1 if typed else 0, out)
        if "/requests/" in rel:
            code, out = run_cli("validate", rel)
            self.assertEqual(code, 1 if typed else 0, out)
        self.assertEqual(work_list.read_work(self.root, None), ([], []))
        if "/requests/" in rel:
            self.assertFalse(all_branches._is_work_file(rel, "specs", "proposals"))

    def test_status_and_validate_leave_a_request_alone(self):
        for rel, text in (("intent.md", self.REQUEST), ("specs/intent.md", self.REQUEST), ("specs/requests/2026-11-08-claim-status.md", self.SAVED)):
            with self.subTest(rel=rel):
                self.write(rel, text)
                self.assert_no_work_item(rel, typed=text == self.SAVED)
                (self.root / rel).unlink()

    def test_validate_finds_a_credential_in_a_saved_request(self):
        rel = "specs/requests/2026-11-08-deploy.md"
        key = "".join(("AKIA", "ABCDEFGHIJKLMNOP"))  # the shape of an AWS key id, split so no scanner reads it here
        for line, kind in ((f"Deploy with {key} please.", "errors"), ("The password: hunter2hunter2 is old.", "warnings"), ("Show the claim status.", None)):
            with self.subTest(kind=kind):
                self.write(rel, f"# Request\n\n{line}\n")
                errors, warnings = self.findings()
                found = {"errors": [e for e in errors if rel in e], "warnings": [w for w in warnings if rel in w]}
                if kind is None:
                    self.assertEqual(found, {"errors": [], "warnings": []})
                    continue
                self.assertEqual(len(found[kind]), 1, found)
                self.assertIn(f"{rel}:3", found[kind][0])
                self.assertIn("[left out: a credential]", found[kind][0])
                self.assertNotIn(line.split()[-2], found[kind][0], "the finding never repeats the value")


class NewSliceSpecTests(RepoCase):
    """`aidd new spec <slice id>` writes the Spec from its slice line, and the facts the Spec owns leave the line."""

    LINES = (
        "phases:\n  - id: P1\n    name: p\n    slices:\n"
        "      - {id: SPEC-1, title: Status endpoint}\n      - {id: SPEC-2, title: Status panel, delivery_team: portal, blocked_by: [SPEC-1]}\n"
    )

    def test_the_spec_takes_the_slice_and_its_line_keeps_the_rest(self):
        self.write("specs/INTENT-1.md", intent("INTENT-1", "g", AGREED + self.LINES))
        config = self.root / ".aidd" / "config.yaml"
        config.write_text(config.read_text(encoding="utf-8") + 'delivery_teams:\n  portal:\n    approvers: ["@a"]\n', encoding="utf-8")
        code, out = run_cli("new", "spec", "SPEC-2", "--force")
        self.assertEqual(code, 0, out)

        data, _ = documents.split_front_matter((self.root / "specs" / "SPEC-2.md").read_text(encoding="utf-8"), "SPEC-2")
        self.assertEqual((data["title"], data["parent"], data.get("delivery_team")), ("Status panel", "INTENT-1", "portal"))
        self.assertIn("SPEC-1", data.get("blocked_by") or [])
        owner, _ = documents.split_front_matter((self.root / "specs" / "INTENT-1.md").read_text(encoding="utf-8"), "INTENT-1")
        line = next(s for p in owner["phases"] for s in p["slices"] if s["id"] == "SPEC-2")
        self.assertEqual(line, {"id": "SPEC-2", "title": "Status panel"}, "one owner for each fact: the Spec")
        errors, _ = self.findings()
        self.assertEqual([e for e in errors if "SPEC-2" in e and "TODO" not in e], [])


class AgreementTests(RepoCase):
    """A slice added or removed, or a new goal, after the person agreed warns until they agree again; bookkeeping never does."""

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(
            self.root,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            message,
            "--trailer",
            "Agreed-by: Dana <dana@example.com>",
        )

    def test_what_changes_the_agreement(self):
        base = intent(
            "INTENT-1", "Calls fall", AGREED + "phases:\n  - id: P1\n    name: p\n    slices:\n      - {id: SPEC-1, title: a}\n      - {id: SPEC-2, title: b}\n"
        )
        cases = (
            # (what, the Intent's text after agreement, whether validate warns)
            ("nothing changed", base, False),
            ("a slice renamed", base.replace("title: b}", "title: b, renamed}"), False),
            ("a slice added", base.replace("title: b}\n", "title: b}\n      - {id: SPEC-3, title: c}\n"), True),
            ("a slice removed", base.replace("      - {id: SPEC-2, title: b}\n", ""), True),
            ("the goal changed", base.replace("Calls fall", "Calls fall by half"), True),
        )
        self.write("specs/INTENT-1.md", base)
        self.commit("plan: agree INTENT-1")
        for what, text, warns in cases:
            with self.subTest(what):
                self.write("specs/INTENT-1.md", text)
                found = [w for w in validation.validate_file(self.root / "specs" / "INTENT-1.md") if "intent.agree" in w]
                self.assertEqual(bool(found), warns, found)

    def test_an_upgrade_between_the_agreement_and_now_changes_nothing_in_either_direction(self):
        """Invariant: for every agreement and every later file, the file asks for a new agreement exactly when its slices or goal differ
        from the agreed ones, whichever shape (`slices` or `phases`) each side is written in. An upgrade alone is no difference, and
        a revert of an upgrade is none either."""

        def listing(shape: str, ids: list[str]) -> str:
            rows = "".join(f"{'  ' if shape == 'old' else '      '}- {{id: {i}, title: t}}\n" for i in ids)
            head = "slices:" if shape == "old" else "phases:\n  - id: P1\n    name: p\n    slices:"
            return head + (f"\n{rows}" if rows else " []\n")

        agreed_at = {"old": "2026-09-01T09:00:00Z", "new": "2026-09-01T09:00:01Z"}
        files = {shape: f"specs/INTENT-{n}.md" for n, shape in enumerate(("old", "new"), 1)}

        def text(shape_agreed: str, shape_now: str, ids: list[str], goal: str) -> str:
            n = 1 if shape_agreed == "old" else 2
            who = f'agreed_by: "Dana <dana@example.com>"\nagreed_at: "{agreed_at[shape_agreed]}"\n'
            return intent(f"INTENT-{n}", goal, who + listing(shape_now, ids))

        agreed_ids = ["SPEC-1", "SPEC-2"]
        for shape, rel in files.items():
            self.write(rel, text(shape, shape, agreed_ids, "Calls fall"))
        self.commit("plan: agree both")
        for shape, rel in files.items():  # the agreed version comes back in today's shape, whichever it was written in
            then = intent_checks.agreed_version(self.root, rel, documents.split_front_matter((self.root / rel).read_text(encoding="utf-8"), rel)[0])
            self.assertEqual((intents.slice_ids(then or {}), "slices" in (then or {})), (agreed_ids, False), shape)
        changes = {
            "nothing": (agreed_ids, "Calls fall", False),
            "a slice added": ([*agreed_ids, "SPEC-3"], "Calls fall", True),
            "a slice removed": (agreed_ids[:1], "Calls fall", True),
            "a slice swapped": (["SPEC-1", "SPEC-9"], "Calls fall", True),
            "all slices removed": ([], "Calls fall", True),
            "the goal changed": (agreed_ids, "Calls fall by half", True),
        }
        for agreed_shape, rel in files.items():
            for now_shape in ("old", "new"):
                for what, (ids, goal, warns) in changes.items():
                    with self.subTest(agreed=agreed_shape, now=now_shape, change=what):
                        self.write(rel, text(agreed_shape, now_shape, ids, goal))
                        found = [w for w in validation.validate_file(self.root / rel) if "intent.agree" in w]
                        self.assertEqual(bool(found), warns, found)


class ExplainTests(unittest.TestCase):
    """`aidd explain` knows the Intent's words, and points the words it replaced at what replaced them."""

    def test_each_word_has_an_answer(self):
        from aidd.knowledge import explanations

        cases = [("stage", "stage"), ("gate", "gate"), ("phase", "document_type"), ("slice", "document_type"), ("intent", "document_type")]
        for word, kind in cases:
            with self.subTest(word=word):
                self.assertIn(kind, [a["type"] for a in explanations.explain(word)])


if __name__ == "__main__":
    unittest.main()
