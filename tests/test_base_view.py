"""Control tests for the base's view of what decides an `aidd test` run.

Invariant: every value that decides what must run or what is excused is read from the base commit when the base has it, and
the head's value applies only to what is new in the head. A head that changes such a value for something the base has gets the
base's value, or both, and a note. A legitimate change of the value (a team that really moves `specs_dir`, or edits a draft
Spec's commands before approval) still works, with its note.
"""

from __future__ import annotations

import itertools
import unittest

from helpers import git, made_up_row, only_rows
from spec_repo_fixtures import FAIL, PASS, PY, RepoCase, config_text, spec_text

from aidd import config, testing, workitems
from aidd.kernel import retired_names
from aidd.testing import base_view, runner

COMMAND = {"name": "check", "command": ["python", "-c", "pass"], "new_behavior": True}


def spec(status="approved", route="normal", commands=None, files=("t.py",), scope="app/") -> dict:
    return {
        "id": "SPEC-1",
        "type": "spec",
        "status": status,
        "route": route,
        "tasks": [{"id": "T1", "scope": [scope]}],
        "tests": {"files": list(files), "commands": [COMMAND] if commands is None else commands},
    }


class SpecViewTable(unittest.TestCase):
    """`spec_view(head, base)` over the value changed (none, status lowered, route, a command changed, a command removed, a
    command added, files widened, scope moved) and whether the base holds the Spec (not at all, as a draft, as approved)."""

    CHANGES = {
        "none": {},
        "status lowered": {"status": "draft"},
        "status raised": {"status": "in_review"},
        "route": {"route": "emergency"},
        "command changed": {"commands": [{**COMMAND, "new_behavior": False}]},
        "command removed": {"commands": []},
        "command moved to another folder": {"commands": [{**COMMAND, "runs_in": "packages/web"}]},
        "command added": {"commands": [COMMAND, {**COMMAND, "name": "more"}]},
        "files widened": {"files": ("t.py", "app/**")},
        "scope moved": {"scope": "lib/"},
    }

    def test_the_base_decides_for_a_spec_it_holds_approved_and_the_head_decides_for_what_is_new(self):
        for held, (change, delta) in itertools.product((None, "draft", "approved", "in_progress"), self.CHANGES.items()):
            head = spec(**{"status": held or "approved", **delta})
            base = None if held is None else spec(status=held)
            with self.subTest(base=held, change=change):
                view, notes = base_view.spec_view(head, base)
                if held in (None, "draft"):
                    self.assertEqual((view, notes), (head, []), "what is new, or a draft, is the head's own")
                    continue
                self.assertEqual(view["status"], held, "the base's status decides, whatever the head sets")
                self.assertEqual(view["route"], "normal", "the base's route decides")
                self.assertTrue(set(base["tests"]["files"]) <= set(view["tests"]["files"]), "the base's frozen files stay frozen")
                names = [c["name"] for c in view["tests"]["commands"]]
                if change in ("command changed", "command removed", "command moved to another folder"):
                    self.assertIn("base.check", names, "a base command the head changes or removes runs as base.<name>")
                else:
                    self.assertFalse(any(n.startswith("base.") for n in names), names)
                moved = change not in ("none", "status raised", "command added")
                self.assertEqual(bool(notes), moved, (change, notes))

    def test_the_status_of_the_view_is_the_status_of_the_base_whatever_the_head_writes(self):
        """Invariant: for a Spec the base holds past approval, `spec_status(view) == spec_status(base)`. The status reads `status`
        and a declined `triage`, so the head's edit of either, or both, or neither, changes nothing in the view."""
        declined = {"decision": "declined"}
        edits = {
            "neither": {},
            "triage declined": {"triage": declined},
            "status changed": {"status": "draft"},
            "status raised": {"status": "done"},
            "both": {"status": "draft", "triage": declined},
        }
        for held, (edit, delta) in itertools.product(("approved", "in_progress", "done"), edits.items()):
            base = spec(status=held)
            with self.subTest(base=held, head_edit=edit):
                view, notes = base_view.spec_view({**spec(status=held), **delta}, base)
                self.assertEqual(workitems.spec_status(view), workitems.spec_status(base))
                if delta.get("triage"):
                    self.assertTrue(notes, "a head that changes the triage of a Spec the base holds approved says so")

    def test_the_status_reads_no_field_the_view_leaves_to_the_head(self):
        """`spec_view` takes `status` and `triage` from the base because `spec_status` reads them. A new field it reads must be
        taken from the base too, so this fails until `spec_view` does."""

        class Recording(dict):
            reads: set = set()

            def get(self, key, default=None):
                self.reads.add(key)
                return super().get(key, default)

            def __getitem__(self, key):
                self.reads.add(key)
                return super().__getitem__(key)

        record = Recording(spec())
        workitems.spec_status(record)
        self.assertLessEqual(Recording.reads, {"status", "triage"})

    def test_the_note_for_a_changed_approved_spec_names_who_acts_and_the_step_that_works(self):
        """aidd cannot see a person's yes, so the note names who approves the revision. When a base command is lost it also names the
        step that needs no bypass: keep the old command working in this change, and remove it in a later one
        (`test_spec_revision_steps` runs that sequence as CI does)."""
        for name, head, lost in (("a command removed", spec(commands=[]), True), ("the route", spec(route="emergency"), False)):
            with self.subTest(change=name):
                _, notes = base_view.spec_view(head, spec())
                self.assertEqual(len(notes), 1)
                self.assertIn("approves the Spec again", notes[0])
                self.assertEqual("later change" in notes[0], lost)

    def test_a_route_the_base_never_gave_is_not_taken_from_the_head(self):
        """An approved Spec with no `route` at the base gets none from the head, so a head cannot add `route: emergency` to cut
        the run to the smoke commands. A head that adds no route is unchanged."""
        base = spec()
        del base["route"]
        for added in ("emergency", None):
            head = spec()
            del head["route"]
            if added:
                head["route"] = added
            with self.subTest(head_route=added):
                view, notes = base_view.spec_view(head, base)
                self.assertNotIn("route", view)
                self.assertEqual(bool(notes), bool(added))


class ConfigViewTable(unittest.TestCase):
    """The config's `tests` and their `smoke` markers over: no base config (a first adoption), a head that keeps, changes, or
    removes a base command, and one that adds a command."""

    def tests(self, *names, smoke=()):
        return [{"name": n, "command": ["x", n], **({"smoke": True} if n in smoke else {})} for n in names]

    def test_the_base_tests_run_beside_the_head_s_and_a_first_adoption_has_none(self):
        base_cfg = config.load_text(config_text(("unit", PASS, []), ("quick", PASS, []), smoke=("quick",)))
        held = base_cfg.tests
        cases = {
            "keeps": (held, []),
            "removes one": (held[:1], ["quick"]),
            "removes all": ([], ["unit", "quick"]),
            "changes one": ([{**held[0], "command": ["other"]}, held[1]], ["unit"]),
            "adds one": ([*held, {"name": "lint", "command": ["lint"]}], []),
        }
        for name, (head, lost) in cases.items():
            with self.subTest(head=name):
                tests, notes = base_view.base_tests(base_cfg, head)
                self.assertEqual([c["name"] for c in tests.copies] if tests else [], [f"base.{n}" for n in lost])
                self.assertEqual(bool(notes), bool(lost))
        self.assertEqual(base_view.base_tests(None, held), (None, []), "a first adoption has no base config, so the head's tests are all there is")

    def test_a_head_that_changes_the_folder_of_a_base_command_runs_the_base_s_copy_too(self):
        """`runs_in` is part of the command, so moving it is a changed command, as for any key: the base's copy keeps the base's folder."""
        base_cfg = config.load_text(config_text(("api", PASS, [], "packages/api"), ("web", PASS, [])))
        api, web = base_cfg.tests
        cases = {
            "keeps both": ([api, web], []),
            "moves one to another folder": ([{**api, "runs_in": "packages/web"}, web], ["api"]),
            "drops the folder": ([{k: v for k, v in api.items() if k != "runs_in"}, web], ["api"]),
            "gives a command with none a folder": ([api, {**web, "runs_in": "packages/web"}], ["web"]),
            "removes the command": ([web], ["api"]),
            "moves both": ([{**api, "runs_in": "x"}, {**web, "runs_in": "x"}], ["api", "web"]),
        }
        for name, (head, lost) in cases.items():
            with self.subTest(head=name):
                tests, notes = base_view.base_tests(base_cfg, head)
                self.assertEqual([c["name"] for c in tests.copies], [f"base.{n}" for n in lost])
                self.assertEqual(bool(notes), bool(lost))
                for copy in tests.copies:  # the copy is the base's command whole, folder included
                    self.assertEqual(
                        {**copy, "name": copy["name"].removeprefix("base.")}, next(c for c in base_cfg.tests if c["name"] == copy["name"].removeprefix("base."))
                    )
                ran = [c["name"] for c, _ in runner.required_tests(head, [], ["packages/web/x.py"], base=tests)[0]]
                self.assertEqual(ran, [c["name"] for c in head] + [f"base.{n}" for n in lost])

    def test_the_base_decides_which_commands_are_smoke_and_whether_there_is_a_smoke_set(self):
        held = self.tests("unit", "quick", smoke=("quick",))
        none_marked = self.tests("unit", "lint")
        cases = [
            # (the base's tests, the head's tests, the commands an emergency change runs of the suite)
            (held, held, ["quick"]),
            (held, [*held, *self.tests("fast", smoke=("fast",))], ["quick", "fast"]),  # new in the head, so it carries its own marker
            (held, self.tests("unit", "quick"), ["quick"]),  # the head unmarks it: the base's marker stands
            (
                held,
                self.tests("unit", "quick", smoke=("unit", "quick")),
                ["quick"],
            ),  # the head marks a command the base holds unmarked: that is a change, and the base copy runs too
            (none_marked, [*none_marked, *self.tests("fast", smoke=("fast",))], ["unit", "lint", "fast"]),  # the head cannot create a smoke set
            (none_marked, none_marked, ["unit", "lint"]),
        ]
        for base_tests, head_tests, expected in cases:
            with self.subTest(base=[c["name"] for c in base_tests], head=[c["name"] for c in head_tests]):
                cfg = base_view.BaseTests(base_tests, [])
                self.assertEqual([c["name"] for c in base_view.emergency_subset(head_tests, cfg)], expected)
        self.assertEqual([c["name"] for c in base_view.emergency_subset(held, None)], ["quick"], "with no base config the head's markers decide")

    def test_the_folders_come_from_the_base_and_the_head_s_is_read_too(self):
        base_cfg = config.load_text(config_text(extra="specs_dir: old/\ndocs:\n  dir: olddocs/\n"))
        head_cfg = config.load_text(config_text(extra="specs_dir: nowhere/\ndocs:\n  dir: elsewhere/\n"))
        self.assertEqual(base_view.spec_dirs(head_cfg.specs_dir, base_cfg), ["old", "nowhere"])
        self.assertEqual(base_view.spec_dirs(head_cfg.specs_dir, None), ["nowhere"])
        self.assertEqual((base_view.docs_dir(head_cfg, base_cfg), base_view.docs_dir(head_cfg, None)), ("olddocs", "elsewhere"))
        self.assertEqual(len(base_view.config_notes(head_cfg, base_cfg)), 2)
        self.assertEqual(base_view.config_notes(head_cfg, head_cfg), [])
        self.assertEqual(base_view.config_notes(head_cfg, None), [])


class HeadCannotDecideTests(RepoCase):
    """The reviewer's four inputs, end to end, and the legitimate change beside each."""

    CONFIG = ".aidd/config.yaml"

    def land(self, **specs) -> None:
        """Specs on `main` as the base holds them, then a branch for the head."""
        for sid, kwargs in specs.items():
            self.put(self.root, f"specs/{sid}.md", spec_text(sid, **kwargs))
        self.commit(self.root, "the Specs landed")
        self.branch()

    def head(self, files: dict[str, str]) -> tuple[dict, list[str]]:
        for path, body in files.items():
            self.put(self.root, path, body)
        self.commit(self.root, "the head")
        return self.run_aidd()

    def test_the_head_sets_specs_dir_somewhere_else(self):
        """The head weakens the approved Spec and points `specs_dir` where no Spec is: the base's folder is read too."""
        cases = [
            # (what the head does, what ran, exit)
            (
                "weakens and hides",
                {
                    "specs/SPEC-1.md": spec_text("SPEC-1", status="approved", code=PASS),
                    self.CONFIG: config_text(("unit", PASS, []), extra="specs_dir: nowhere/\n"),
                },
                {"unit", "check", "base.check"},
                1,
            ),
            ("moves the folder unchanged", None, {"unit", "check"}, 0),  # a team that really moves it: the same Spec, found in the new folder
        ]
        for name, files, ran, code in cases:
            with self.subTest(head=name):
                self.fresh()
                self.land(**{"SPEC-1": {"status": "approved", "code": FAIL if code else PASS}})
                if files is None:
                    (self.root / "specs/SPEC-1.md").rename(self.root / "docs-specs.md")
                    (self.root / "specs").rmdir()
                    files = {
                        "moved/SPEC-1.md": spec_text("SPEC-1", status="approved"),
                        self.CONFIG: config_text(("unit", PASS, []), extra="specs_dir: moved/\n"),
                    }
                    (self.root / "docs-specs.md").unlink()
                evidence, notes = self.head(files)
                self.assertEqual({n for n, _ in self.ran(evidence)}, ran)
                self.assertEqual(testing.exit_code(evidence), code)
                self.assertTrue(any("specs_dir" in n for n in notes), notes)

    def test_the_head_rewrites_an_approved_specs_command(self):
        base = {"status": "approved", "code": FAIL, "new_behavior": True}
        cases = [
            # (the head's Spec, names that ran, exit)
            ("a passing command", {"code": PASS, "new_behavior": True}, {"check", "base.check"}, 1),
            ("a path no change matches", {"code": FAIL, "new_behavior": True, "when_changed": ("nowhere/",)}, {"base.check"}, 1),
            ("no new behavior", {"code": FAIL, "new_behavior": False}, {"check", "base.check"}, 1),
            ("untouched", None, {"check"}, 1),
        ]
        for name, delta, names, code in cases:
            with self.subTest(head=name):
                self.fresh()
                self.land(**{"SPEC-1": base})
                files = {} if delta is None else {"specs/SPEC-1.md": spec_text("SPEC-1", status="approved", **delta)}
                files["app/x.py"] = "x = 1\n"
                evidence, notes = self.head(files)
                ran = {n for n, _ in self.ran(evidence)} - {"unit"}
                self.assertEqual(ran, names if delta is not None else set())
                self.assertEqual(testing.exit_code(evidence), code if delta is not None else 0)
                if delta is not None:
                    self.assertTrue(any("decided by the base's" in n for n in notes), notes)
        self.fresh()
        self.land(**{"SPEC-1": {"status": "approved", "code": FAIL, "new_behavior": True}})
        red = self.head({"specs/SPEC-1.md": spec_text("SPEC-1", status="approved", code=FAIL, new_behavior=False)})[0]
        self.assertIn(("base.check", "green"), self.ran(red), "the base's command runs green")

    def test_a_draft_spec_is_edited_freely_and_an_approved_one_is_not(self):
        for status, expected in (("draft", {"check"}), ("ready", {"check"}), ("approved", {"check", "base.check"})):
            with self.subTest(base=status):
                self.fresh()
                self.land(**{"SPEC-1": {"status": status, "code": FAIL}})
                evidence, notes = self.head({"specs/SPEC-1.md": spec_text("SPEC-1", status=status, code=PASS), "app/x.py": "x = 1\n"})
                self.assertEqual({n for n, _ in self.ran(evidence)} - {"unit"}, expected)
                self.assertEqual(any("decided by the base's" in n for n in notes), status == "approved")

    def test_the_head_lowers_an_in_progress_spec_and_widens_its_frozen_files(self):
        self.land(**{"SPEC-1": {"status": "in_progress", "code": FAIL}})
        evidence, _ = self.head({"specs/SPEC-1.md": spec_text("SPEC-1", status="draft", code=FAIL, files=("app/**",), scope="lib/"), "app/x.py": "x = 1\n"})
        self.assertEqual(testing.exit_code(evidence), 1, "the base's in_progress status keeps the failure unexcused, even in a local run")
        self.assertFalse(any(r.get("before_implement") for r in evidence["results"]))

    def test_the_head_adds_a_smoke_command_and_an_emergency_spec(self):
        smoke_head = config_text(("unit", PASS, []), ("fast", PASS, []), smoke=("fast",))
        cases = [
            # (the base's config, ran of the suite)
            (config_text(("unit", PASS, [])), {"unit", "fast"}),  # the base has no smoke set, which the head cannot create
            (config_text(("unit", PASS, []), ("quick", PASS, []), smoke=("quick",)), {"quick"}),  # the base has one, so the subset stands
        ]
        for base_config, suite in cases:
            with self.subTest(base=base_config[-50:]):
                self.fresh()
                self.put(self.root, self.CONFIG, base_config)
                self.commit(self.root, "the base's tests")
                self.branch()
                head_config = (
                    smoke_head
                    if "quick" not in base_config
                    else config_text(("unit", PASS, []), ("quick", PASS, []), ("fast", PASS, []), smoke=("quick", "fast"))
                )
                evidence, _ = self.head({self.CONFIG: head_config, "specs/SPEC-1.md": spec_text("SPEC-1", route="emergency"), "app/x.py": "x = 1\n"})
                ran = {n for n, _ in self.ran(evidence)} - {"check"}
                self.assertEqual(ran, suite | ({"fast"} if "quick" in base_config else set()))

    def test_the_evidence_says_when_the_repository_suite_ran_as_its_smoke_set_for_an_emergency_spec(self):
        """Invariant: when a governing Spec's route is emergency and that drops a command of the repository suite, the evidence holds
        `emergency_subset: true`, so a person reading a green `tests` check knows the suite was cut. A run that cut nothing leaves it out."""
        two = config_text(("unit", PASS, []), ("quick", PASS, []), smoke=("quick",))
        cases = {  # the config, the Spec's route -> whether the suite was narrowed
            "emergency, the suite marks a smoke set": (two, "emergency", True),
            "normal, the suite marks a smoke set": (two, "normal", False),
            "emergency, the suite marks none": (config_text(("unit", PASS, []), ("quick", PASS, [])), "emergency", False),
            "emergency, every command is smoke": (config_text(("unit", PASS, []), ("quick", PASS, []), smoke=("unit", "quick")), "emergency", False),
        }
        for name, (base_config, route, narrowed) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.put(self.root, self.CONFIG, base_config)
                self.commit(self.root, "the base's tests")
                self.branch()
                evidence, _ = self.head({"specs/SPEC-1.md": spec_text("SPEC-1", route=route), "app/x.py": "x = 1\n"})
                self.assertEqual(evidence.get("emergency_subset"), True if narrowed else None, name)
                self.assertEqual("unit" in {n for n, _ in self.ran(evidence)}, not narrowed, name)

    def test_a_first_adoption_has_no_base_config_and_the_head_decides(self):
        """The base holds no `.aidd/config.yaml`: every value is the head's, and nothing is run twice."""
        self.fresh()
        git_dir = self.root
        (git_dir / self.CONFIG).unlink()
        self.commit(self.root, "base without aidd")
        self.branch()
        evidence, notes = self.head(
            {self.CONFIG: config_text(("unit", PASS, [])), "specs/SPEC-1.md": spec_text("SPEC-1", status="approved"), "app/x.py": "x = 1\n"}
        )
        self.assertEqual(({n for n, _ in self.ran(evidence)}, testing.exit_code(evidence)), ({"unit", "check"}, 0))
        self.assertFalse(any("base" in n for n in notes), notes)
        _, gated = self.run_aidd(require_green=True)
        self.assertFalse(any("does not load" in n for n in gated), "a first adoption stays the head's own at the gate too")

    def test_a_base_config_that_does_not_load_stops_the_gate_and_is_said_otherwise(self):
        """The base decides, so a base config that exists and does not load lets no head value decide a run that gates a merge; a
        quick run of the author's is told, with the step. The base with a key this aidd does not read is one."""
        for name, broken in {
            "a line aidd cannot parse": "tests: [unclosed\n",
            "a key this aidd does not read": config_text(("unit", PASS, [])) + "bogus_key: 1\n",
        }.items():
            with self.subTest(name):
                self.fresh()
                self.put(self.root, self.CONFIG, broken)
                self.commit(self.root, "a base config that does not load")
                self.branch()
                _, notes = self.head({self.CONFIG: config_text(("unit", PASS, [])), "app/x.py": "x = 1\n"})
                said = [n for n in notes if "does not load" in n]
                self.assertTrue(said and "--require-green" in said[0] and "then run `aidd test` again" in said[0], notes)
                with self.assertRaises(RuntimeError) as stopped:  # a quick check never gates (`--changed` with `--require-green` is refused)
                    self.run_aidd(require_green=True)
                self.assertIn("The base decides what a run holds the change to", str(stopped.exception))


ROWS = (
    made_up_row("spec-test-retries", "spec", "tests.commands[].retries_old", "tests.commands[].reruns", "rename"),
    made_up_row("spec-hunch", "spec", "hunch", None, "cut"),
    made_up_row("spec-waits", "spec", "waits_for", "waiting_on", "rename"),
    made_up_row("config-test-retries", "config", "tests[].retries_old", "tests[].reruns", "rename"),
    made_up_row("config-lines", "config", "limits.fix_lines_old", None, "cut"),
    made_up_row("config-retries", "config", "limits.max_retries_old", "limits.max_task_retries", "rename"),
)


class WithMadeUpRows(unittest.TestCase):
    """The base is read in today's shape by the rows of schemas/retired-names.json, which are none at the first release, so a test of
    the reading uses rows made for it."""

    def setUp(self):
        super().setUp()
        rows = only_rows(*ROWS)
        rows.__enter__()
        self.addCleanup(rows.__exit__, None, None, None)


class SpecInTheOldShapeTable(WithMadeUpRows):
    """An upgrade that only moves retired names is no change of an approved Spec, and anything else still is. The base is read in
    today's shape first (`workitems.todays_shape`), so the table runs each row both ways: the migrated head equals the base, and a
    head that also changes a value that decides differs."""

    OLD = {
        "tests.commands[].retries_old": {"tests": {"files": ["t.py"], "commands": [{**COMMAND, "retries_old": 2}]}},
        "hunch": {"hunch": "low"},
        "waits_for": {"waits_for": "legal"},
    }

    def migrated(self, base: dict) -> dict:
        """What `aidd upgrade` leaves, written out by hand."""
        head = {k: v for k, v in base.items() if k not in ("hunch", "waits_for")}
        head["tests"] = {
            **head["tests"],
            "commands": [
                {k: v for k, v in c.items() if k != "retries_old"} | ({"reruns": c["retries_old"]} if "retries_old" in c else {})
                for c in head["tests"]["commands"]
            ],
        }
        if "waits_for" in base:
            head["waiting_on"] = base["waits_for"]
        return head

    def test_a_pure_migration_is_no_change_and_a_migration_that_weakens_the_spec_still_is(self):
        weakenings = {
            "status lowered": {"status": "draft"},
            "route": {"route": "emergency"},
            "scope moved": {"tasks": [{"id": "T1", "scope": ["lib/"]}]},
            "files dropped from the frozen set": {"tests": {"files": [], "commands": []}},
        }
        for row, extra in self.OLD.items():
            base = {**spec(), **extra}
            if "tests" in extra:
                base["tests"] = extra["tests"]
            seen = workitems.todays_shape(base)
            head = self.migrated(base)
            with self.subTest(row=row, kind="pure migration"):
                self.assertEqual(base_view.spec_view(head, seen)[1], [], "the rows alone are no revision")
            for name, delta in weakenings.items():
                with self.subTest(row=row, kind=name):
                    _, notes = base_view.spec_view({**head, **delta}, seen)
                    self.assertTrue(notes, "a weakened head still gets the base's copy and a note")

    def test_a_base_with_design_files_and_a_head_that_frees_one_differs(self):
        paths = ("d/a.md", "d/**")
        kept = [{"type": "design-files", "path": p, "frozen": True} for p in paths]
        seen = {**spec(), "docs": kept}
        cases = {
            "the same entries": (kept, False),
            "the entries without `frozen`": ([{"type": "design-files", "path": p} for p in paths], False),
            "the entries that say `frozen: false`, which a design file ignores": ([{**e, "frozen": False} for e in kept], False),
            "one path dropped": (kept[:1], True),
            "every path dropped": ([], True),
            "a path swapped for another": ([kept[0], {**kept[1], "path": "e/**"}], True),
            "the paths as living docs of another type": ([{"type": "other", "path": p, "frozen": False} for p in paths], True),
        }
        for name, (docs, differs) in cases.items():
            with self.subTest(name):
                _, notes = base_view.spec_view({**spec(), **({"docs": docs} if docs else {})}, seen)
                self.assertEqual(any("frozen files" in n for n in notes), differs, notes)

    def test_a_rename_with_a_changed_value_differs(self):
        base = {**spec(), "tests": self.OLD["tests.commands[].retries_old"]["tests"]}
        seen = workitems.todays_shape(base)
        self.assertEqual(seen["tests"]["commands"][0]["reruns"], 2)
        for reruns, differs in ((2, False), (0, True), (3, True)):
            head = {**spec(), "tests": {"files": ["t.py"], "commands": [{**COMMAND, "reruns": reruns}]}}
            with self.subTest(reruns=reruns):
                view, notes = base_view.spec_view(head, seen)
                self.assertEqual(bool(notes), differs)
                self.assertEqual(any(c["name"] == "base.check" for c in view["tests"]["commands"]), differs)

    def test_a_name_beside_its_replacement_is_refused_as_the_upgrade_refuses_it_and_a_non_spec_comes_back_as_it_is(self):
        both = {**spec(), "waits_for": "old", "waiting_on": "new"}
        with self.assertRaises(retired_names.Refused):
            workitems.todays_shape(both)
        for other in ({"type": "proposal", "hunch": "x"}, {"hunch": "x"}):
            self.assertEqual(workitems.todays_shape(other), other)


class ApprovedSpecInTheOldShapeOnTheBase(WithMadeUpRows, RepoCase):
    """The base commit holds an approved Spec with retired names, as a branch forked before `aidd upgrade` does. The run reads it in
    today's shape, so the upgrade on the head is no revision, and a head that also drops a command still runs the base's."""

    def old(self) -> str:
        text = spec_text("SPEC-1", status="approved", new_behavior=False)
        return text.replace("rollback:", "hunch: low\nrollback:", 1).replace("      new_behavior: false\n", "      new_behavior: false\n      retries_old: 1\n")

    def migrated(self, *, keep_command: bool = True) -> str:
        text = spec_text("SPEC-1", status="approved", new_behavior=False).replace("      new_behavior: false\n", "      new_behavior: false\n      reruns: 1\n")
        return text if keep_command else text.replace("check", "other")

    def land_base(self) -> None:
        self.put(self.root, "specs/SPEC-1.md", self.old())
        self.put(self.root, "checks/SPEC-1.py", "")
        self.commit(self.root, "the approved Spec, in the old shape")
        self.branch()

    def noted(self, notes: list[str]) -> list[str]:
        return [n for n in notes if "the head changes" in n and "approved" in n]

    def test_an_upgrade_that_only_moves_names_is_no_revision_and_one_that_also_drops_a_command_is(self):
        self.land_base()
        self.put(self.root, "specs/SPEC-1.md", self.migrated())
        self.commit(self.root, "aidd upgrade")
        evidence, notes = self.run_aidd()
        self.assertEqual(self.noted(notes), [], notes)
        self.assertFalse(any(n.startswith("base.") for n, _ in self.ran(evidence)), "the Spec's command runs as itself")
        self.put(self.root, "specs/SPEC-1.md", self.migrated(keep_command=False))
        self.commit(self.root, "and drops the command")
        evidence, notes = self.run_aidd()
        self.assertTrue(self.noted(notes), notes)
        self.assertIn("base.check", {n for n, _ in self.ran(evidence)}, "the base's copy of the command still runs")

    def test_the_approved_copy_of_a_spec_in_the_old_shape_reads_as_the_upgraded_head_for_the_run_and_for_the_delegate(self):
        """An approved Spec on the base reads as the upgraded head says, for the run (`governing.specs_at`) and for the copy the
        delegate compares (`delegation.local_run.spec_by_id`), so the upgrade alone is no revision for either."""
        from aidd.delegation import local_run
        from aidd.setup import migrating
        from aidd.testing import governing

        text = spec_text("SPEC-1", status="approved").replace("rollback:", "waits_for: legal\nrollback:", 1)
        self.put(self.root, "specs/SPEC-1.md", text)
        self.put(self.root, "checks/SPEC-1.py", "")
        self.commit(self.root, "approved before the upgrade")
        approval = git(self.root, "rev-parse", "HEAD")
        self.branch()
        migrating.apply(self.root, migrating.plan(self.root))
        self.commit(self.root, "aidd upgrade")
        head = git(self.root, "rev-parse", "HEAD")
        upgraded, _, errors = workitems.load_object((self.root / "specs/SPEC-1.md").read_text(encoding="utf-8"), "specs/SPEC-1.md")
        self.assertEqual((errors, upgraded["waiting_on"], "waits_for" in upgraded), ([], "legal", False))
        self.assertEqual(governing.specs_at(str(self.root), approval, ["specs"])["specs/SPEC-1.md"], upgraded)
        found = local_run.spec_by_id(str(self.root), approval, "specs", "SPEC-1")
        self.assertIsNotNone(found)
        self.assertEqual((found[1], found[3]), (upgraded, []), "the approved copy reads as the head")
        self.assertEqual(local_run.frozen_problem(str(self.root), head, "specs", ("specs/SPEC-1.md", upgraded), approval), "")
        _, notes = self.run_aidd()
        self.assertEqual(self.noted(notes), [], notes)


class OldShapeBaseTests(WithMadeUpRows, RepoCase):
    """A branch forked before an upgrade has the old names on its base commit. The base still decides, because the retired names
    read as their replacements there: the head is not checked by its own `tests`, and the upgrade itself is no change of them."""

    CONFIG = ".aidd/config.yaml"
    TESTS = 'tests:\n  - name: unit\n    command: [{py}, -c, "{code}"]\n{extra}'
    HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: [bob]\n'

    def old(self, code: str = PASS) -> str:
        """The base: `tests[].retries_old`, a cut `limits.fix_lines_old`, and `limits.max_retries_old`."""
        tests = self.TESTS.format(py=PY, code=code, extra="    retries_old: 1\n")
        return self.HEAD + tests + "limits:\n  fix_lines_old: 9\n  max_retries_old: 2\n"

    def new(self, code: str = PASS) -> str:
        """The same config in today's shape, as `aidd upgrade` leaves it."""
        return self.HEAD + self.TESTS.format(py=PY, code=code, extra="    reruns: 1\n") + "limits:\n  max_task_retries: 2\n"

    def land_old_base(self) -> None:
        self.put(self.root, self.CONFIG, self.old())
        self.commit(self.root, "the base, in the old shape")
        self.branch()

    def test_the_base_config_in_the_old_shape_loads_as_today_s(self):
        self.land_old_base()
        sha = git(self.root, "rev-parse", "main")
        base, notes = base_view.load_config(str(self.root), sha)
        self.assertEqual(notes, [])
        self.assertIsNotNone(base, "an old-shape base is read, not dropped for the head's own values")
        self.assertEqual([(t["name"], t.get("reruns")) for t in base.tests], [("unit", 1)])
        with self.assertRaises(config.ConfigError):
            config.load_text(self.old())  # the head's loader still stops at the old names

    def test_an_upgrade_that_only_renames_is_no_change_of_the_tests_and_a_weakened_one_still_is(self):
        self.land_old_base()
        evidence, notes = self.head({self.CONFIG: self.new()})
        self.assertEqual({n for n, _ in self.ran(evidence)}, {"unit"})
        self.assertFalse(any("changes or removes" in n for n in notes), notes)
        self.commit(self.root, "the upgrade")
        self.put(self.root, self.CONFIG, self.new(code=FAIL))
        self.commit(self.root, "and weakens nothing, but breaks the suite")
        evidence, notes = self.run_aidd()
        self.assertTrue({"unit", "base.unit"} <= {n for n, _ in self.ran(evidence)}, "the base's command still runs beside the head's changed one")
        self.assertTrue(any("changes or removes" in n for n in notes), notes)

    def head(self, files: dict[str, str]) -> tuple[dict, list[str]]:
        for path, body in files.items():
            self.put(self.root, path, body)
        self.commit(self.root, "the head")
        return self.run_aidd()


if __name__ == "__main__":
    unittest.main()
