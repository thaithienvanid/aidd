"""Control tests for what `aidd test` calls a pass.

Invariants, each about every input:
- A full run outside the Design stage exits 0 only when at least one command ran and passed, and every decider of "the
  suite passed" gives one answer for one piece of evidence.
- A failing green run is expected only while every governing Spec's stored status is before Implement and the changed
  paths are the Specs and the files they freeze.
- A change cannot turn its check green by removing or weakening the `tests` it is checked by.
"""

from __future__ import annotations

import itertools
import random
import unittest
from unittest import mock

from spec_repo_fixtures import FAIL, PASS, RepoCase, config_text, spec_text

from aidd import testing
from aidd.delegation import local_run

GREEN_PASS = {"name": "unit", "red_green": "green", "status": "passed", "exit": 0}
GREEN_FAIL = {"name": "unit", "red_green": "green", "status": "failed", "exit": 1}
RED_FAIL = {"name": "new", "red_green": "red", "status": "failed", "exit": 1}


def evidences():
    """Every shape of evidence: results (none, one pass, one fail, both) with each flag on or off."""
    for results, *flags in itertools.product(([], [GREEN_PASS], [GREEN_FAIL], [GREEN_PASS, RED_FAIL]), *([False, True],) * 4):
        evidence: dict = {"results": results}
        evidence.update({name: True for name, on in zip(("before_implement", "dirty_tree", "partial", "no_red"), flags, strict=True) if on})
        yield evidence


class RunNothingIsNoPassTests(unittest.TestCase):
    """For every full run outside the Design stage, exit 0 means a command ran and passed; the deciders agree."""

    def test_a_full_run_with_no_result_never_passes(self):
        for evidence in evidences():
            if evidence["results"] or evidence.get("partial"):
                continue
            with self.subTest(evidence=evidence):
                self.assertEqual(testing.exit_code(evidence), 1)
                self.assertTrue(testing.ran_nothing(evidence))

    def test_a_quick_check_that_selects_nothing_is_no_failure_and_says_it_is_partial(self):
        """Safe because a quick check (`--changed`) is never the change's evidence: `aidd status` reads it as partial."""
        evidence = {"results": [], "partial": True}
        self.assertEqual((testing.exit_code(evidence), testing.ran_nothing(evidence)), (0, False))

    def test_the_merge_check_and_the_exit_code_decide_alike(self):
        for evidence in evidences():
            if evidence.get("before_implement"):
                continue  # a merge is never in the Design stage, so it stays red where `aidd test` excuses the run
            with self.subTest(evidence=evidence):
                self.assertEqual(bool(testing.exit_code(evidence)), bool(local_run.suite_problem(evidence, "")))

    def test_the_merge_check_says_nothing_ran_rather_than_a_dirty_tree(self):
        self.assertIn("no test ran", local_run.suite_problem({"results": []}, ""))

    def test_a_pass_needs_a_result_that_passed(self):
        for evidence in evidences():
            if testing.exit_code(evidence) == 0 and not evidence.get("partial") and not evidence.get("before_implement"):
                with self.subTest(evidence=evidence):
                    self.assertTrue(any(r["red_green"] == "green" and r["status"] == "passed" for r in evidence["results"]))

    @staticmethod
    def monotone(decide) -> bool:
        """Adding a failing green result never turns 1 into 0, and on a full run dropping every result never does."""
        rng = random.Random(20261111)
        for _ in range(300):
            results = [rng.choice([GREEN_PASS, GREEN_FAIL, RED_FAIL]) for _ in range(rng.randint(0, 4))]
            flags = {name: True for name in ("dirty_tree", "no_red", "partial") if rng.random() < 0.3}
            now = decide({"results": results, **flags})
            if decide({"results": [*results, GREEN_FAIL], **flags}) < now:
                return False
            if not flags.get("partial") and decide({"results": [], **flags}) < now:
                return False
        return True

    def test_the_verdict_is_monotone_and_the_check_can_fail(self):
        self.assertTrue(self.monotone(testing.exit_code))

        def lenient(evidence):  # a verdict that passes an empty run, as `aidd test` once did
            return 0 if not evidence["results"] else testing.exit_code(evidence)

        self.assertFalse(self.monotone(lenient), "the relation must catch a decider that passes an empty run")


class DesignStageNeedsTheStatusTests(unittest.TestCase):
    """A failing green run is expected only while every governing Spec is `draft`, `ready`, or `approved` and the
    paths are the Specs and the files they freeze with some Task scope untouched."""

    SPEC, TEST, CODE = "specs/SPEC-1.md", "checks/t.py", "app/x.py"
    FROZEN = [SPEC, TEST]

    def test_the_table(self):
        from aidd.testing.runner import before_implement

        cases = [
            # (stored statuses, changed paths, Task scopes, in the Design stage)
            (["draft"], [self.SPEC, self.TEST], [["app/"]], True),
            (["ready"], [self.SPEC, self.TEST], [["app/"]], True),
            (["approved"], [self.SPEC, self.TEST], [["app/"]], True),
            (["in_progress"], [self.SPEC, self.TEST], [["app/"]], False),
            (["in_review"], [self.SPEC, self.TEST], [["app/"]], False),
            (["done"], [self.SPEC, self.TEST], [["app/"]], False),
            (["rolled_back"], [self.SPEC, self.TEST], [["app/"]], False),
            (["cancelled"], [self.SPEC, self.TEST], [["app/"]], False),
            (["draft", "in_review"], [self.SPEC, self.TEST], [["app/"]], False),  # one Spec past Implement ends it for the run
            (["draft", "approved"], [self.SPEC, self.TEST], [["app/"], ["lib/"]], True),
            (["draft"], [self.SPEC, self.CODE], [["app/"]], False),  # code changed: Implement began
            (["draft"], [], [["app/"]], False),
            (["draft"], [self.SPEC], [[]], False),  # a Task with no scope is never "untouched"
            (["draft"], [self.SPEC], [], False),
            ([], [self.SPEC], [["app/"]], False),  # no Spec governs
        ]
        for statuses, paths, scopes, expected in cases:
            with self.subTest(statuses=statuses, paths=paths, scopes=scopes):
                self.assertIs(before_implement(paths, self.FROZEN, scopes, statuses), expected)

    def test_a_path_outside_the_frozen_files_never_turns_false_into_true(self):
        from aidd.testing.runner import before_implement

        paths = [[], [self.SPEC], [self.SPEC, self.TEST]]
        for statuses, scopes, base in itertools.product((["draft"], ["in_review"], ["draft", "done"]), ([["app/"]], [[]], []), paths):
            with self.subTest(statuses=statuses, scopes=scopes, base=base):
                if not before_implement(base, self.FROZEN, scopes, statuses):
                    self.assertFalse(before_implement([*base, "other.txt"], self.FROZEN, scopes, statuses))


class NothingRanTests(RepoCase):
    """A full run that selects no command exits 1 and names the step; a quick check that selects none is partial."""

    def change_app(self) -> None:
        self.branch()
        self.put(self.root, "app/x.py", "x = 1\n")
        self.commit(self.root, "change app")

    def test_no_tests_configured_and_no_spec_runs_nothing_and_exits_1(self):
        for text in (config_text(), 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: [bob]\n'):
            with self.subTest(text=text[-30:]):
                self.fresh()
                self.put(self.root, ".aidd/config.yaml", text)
                self.commit(self.root, "no tests")
                self.change_app()
                evidence, notes = self.run_aidd()
                self.assertEqual((evidence["results"], testing.exit_code(evidence)), ([], 1))
                self.assertTrue(any("`tests:`" in n and "Spec" in n for n in notes), notes)

    def test_a_project_whose_commands_all_skip_the_changed_paths_declares_that_no_test_applies(self):
        """The base's own config says no test covers these paths (a docs-only change), so the run exits 0 and says it proved nothing.
        With one unscoped command present, or when a Spec that applies is skipped, or when nothing is configured, it is not that state."""
        docs, unit = ("docs", PASS, ["docs/**"]), ("unit", PASS, [])
        spec_skipped = {"specs/SPEC-1.md": spec_text("SPEC-1", code=PASS, when_changed=("nowhere/",))}
        cases = [
            # (the config's tests, files the change touches, ran, exit, no test applied)
            ((docs,), {"app/x.py": "x = 1\n"}, set(), 0, True),
            ((docs, ("lint", PASS, ["lib/**"])), {"app/x.py": "x = 1\n"}, set(), 0, True),
            ((docs, unit), {"app/x.py": "x = 1\n"}, {("unit", "green")}, 0, False),  # one unscoped command: it runs and counts
            ((docs,), {"docs/guide.md": "guide\n"}, {("docs", "green")}, 0, False),  # a path matches
            ((docs,), {"app/x.py": "x = 1\n", **spec_skipped}, set(), 1, False),  # a Spec applies and every command is skipped
            ((), {"app/x.py": "x = 1\n"}, set(), 1, False),  # nothing is configured
        ]
        for tests, files, ran, code, state in cases:
            with self.subTest(tests=[t[0] for t in tests], files=sorted(files)):
                self.fresh()
                self.put(self.root, ".aidd/config.yaml", config_text(*tests))
                self.commit(self.root, "the config")
                self.branch()
                for rel, text in files.items():
                    self.put(self.root, rel, text)
                self.commit(self.root, "the change")
                evidence, notes = self.run_aidd()
                self.assertEqual((self.ran(evidence), testing.exit_code(evidence), bool(evidence.get("untested"))), (ran, code, state))
                self.assertEqual(any("no test applied" in n and "no `when_changed`" in n for n in notes), state, notes)
                self.assertEqual(testing.tests_apply(str(self.root), "HEAD", "main"), bool(evidence["results"]), "the merge check decides as the run does")

    def test_the_head_cannot_reach_the_state_by_scoping_or_dropping_the_tests_the_base_holds(self):
        """The base holds an unscoped `unit`: a head that scopes it to docs, removes it, or adds a scoped command still has it run."""
        heads = {
            "scopes it": config_text(("unit", PASS, ["docs/**"])),
            "removes it": config_text(),
            "adds a scoped command": config_text(("unit", PASS, []), ("docs", PASS, ["docs/**"])),
        }
        for name, head_config in heads.items():
            with self.subTest(head=name):
                self.fresh()
                self.branch()
                self.put(self.root, ".aidd/config.yaml", head_config)
                self.put(self.root, "app/x.py", "x = 1\n")
                self.commit(self.root, "the head")
                evidence, _ = self.run_aidd()
                self.assertTrue(evidence["results"], "the base's unscoped command runs")
                self.assertFalse(evidence.get("untested"))
                self.assertEqual(testing.exit_code(evidence), 0)

    def test_the_merge_check_and_the_status_never_read_the_state_as_a_pass(self):
        state = {"results": [], "untested": True}
        self.assertEqual(testing.exit_code(state), 0)
        self.assertIn("no test applied", local_run.suite_problem(state, ""))
        self.assertEqual(testing.exit_code({**state, "dirty_tree": True}), 1, "a dirty full run still fails")
        self.assertEqual(testing.exit_code({"results": [GREEN_FAIL], "untested": True}), 1, "the flag excuses nothing that ran")

    def test_a_branch_with_no_common_ancestor_with_the_base_says_why_and_what_to_do(self):
        from helpers import git as run_git

        run_git(self.root, "checkout", "-q", "--orphan", "island")
        self.put(self.root, "island.txt", "x\n")
        self.commit(self.root, "an unrelated history")
        for changed in (False, True):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError) as stop:
                self.run_aidd(changed=changed)
            self.assertIn("share no commit", str(stop.exception))
            self.assertIn("--base", str(stop.exception))

    def test_a_quick_check_that_selects_nothing_is_partial_and_exits_0(self):
        self.branch()
        evidence, _ = self.run_aidd(changed=True)
        self.assertEqual((evidence["results"], evidence["partial"], testing.exit_code(evidence)), ([], True, 0))


class WeakeningTheTestsIsNoWayToPassTests(RepoCase):
    """The base commit's `tests` run beside the head's when the head removes or changes them."""

    def head_config(self, text: str) -> tuple[dict, list[str]]:
        self.branch()
        self.put(self.root, ".aidd/config.yaml", text)
        self.put(self.root, "app/x.py", "x = 1\n")
        self.commit(self.root, "change the tests")
        return self.run_aidd()

    def test_a_head_that_removes_its_tests_still_runs_the_base_tests(self):
        evidence, notes = self.head_config(config_text())
        self.assertEqual((self.ran(evidence), testing.exit_code(evidence)), ({("base.unit", "green")}, 0))
        self.assertTrue(any("base.<name>" in n for n in notes), notes)

    def test_a_head_that_weakens_a_test_fails_on_the_base_test(self):
        self.put(self.root, ".aidd/config.yaml", config_text(("unit", FAIL, [])))
        self.commit(self.root, "a suite that fails")
        evidence, _ = self.head_config(config_text(("unit", PASS, [])))
        self.assertEqual((self.ran(evidence), testing.exit_code(evidence)), ({("unit", "green"), ("base.unit", "green")}, 1))

    def test_no_value_the_head_controls_drops_or_excuses_a_base_test(self):
        """The route, the status, and the frozen list come from the head's Spec: none may drop a `base.*` command or excuse its result."""
        base = config_text(("unit", PASS, []), ("quick", PASS, []), smoke=("quick",))
        failing_base = config_text(("unit", FAIL, []))
        config = ".aidd/config.yaml"
        cases = [
            # (base config, head config, head Spec, what ran, exit)
            # an emergency Spec asks for the smoke subset: the head's own commands honor it, a base command always runs
            (base, base, {"route": "emergency"}, {("quick", "green"), ("check", "green")}, 0),
            (base, config_text(), {"route": "emergency"}, {("base.unit", "green"), ("base.quick", "green"), ("check", "green")}, 0),
            # a Spec before Implement that freezes the config excuses its own failing check in a local run, and never a failing base command
            (config_text(("unit", PASS, [])), config_text(), {"files": (config,), "code": FAIL}, {("base.unit", "green"), ("check", "green")}, 0),
            (failing_base, config_text(), {"files": (config,), "code": FAIL}, {("base.unit", "green"), ("check", "green")}, 1),
            (failing_base, config_text(("unit", PASS, [])), {"files": (config,)}, {("unit", "green"), ("base.unit", "green"), ("check", "green")}, 1),
        ]
        for base_config, head_config, spec, ran, code in cases:
            with self.subTest(spec=spec, head=head_config[-40:], exit=code):
                self.fresh()
                self.put(self.root, config, base_config)
                self.commit(self.root, "the base's tests")
                self.branch()
                self.put(self.root, config, head_config)
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", **spec))
                if spec.get("route"):
                    self.put(self.root, "app/x.py", "x = 1\n")
                self.commit(self.root, "the head's Spec")
                evidence, _ = self.run_aidd()
                self.assertEqual(self.ran(evidence), ran)
                self.assertEqual(testing.exit_code(evidence), code)
                gated, _ = self.run_aidd(require_green=True)  # a gating run excuses nothing: any failing command fails it
                self.assertEqual(testing.exit_code(gated), 1 if FAIL in str(spec.get("code")) or code else 0)

    def test_a_head_that_keeps_the_tests_runs_them_once(self):
        evidence, notes = self.head_config(config_text(("unit", PASS, []), ("lint", PASS, [])))
        self.assertEqual((self.ran(evidence), testing.exit_code(evidence)), ({("unit", "green"), ("lint", "green")}, 0))
        self.assertFalse(any("base.<name>" in n for n in notes), notes)


class OneSpecNeverExcusesAnotherTests(RepoCase):
    """A failing result is excused only for the Spec that owns it, when that Spec itself is before Implement and the diff's
    paths are its own file and frozen files, and only in a local run. Spec A freezes `app/**`, which covers the code of Spec B
    and of the whole change, so a local run excuses A's own failure there. A run with `require_green`, which gates a merge,
    excuses nothing, whatever a Spec freezes."""

    A = {"files": ("app/**",), "scope": "lib/", "code": FAIL}

    def check(self, specs: dict[str, dict], code_path: str | None, landed: dict[str, dict] | None = None, suite: str = PASS, gate: bool = False):
        self.fresh()
        self.put(self.root, ".aidd/config.yaml", config_text(("unit", suite, [])))
        for sid, kwargs in (landed or {}).items():
            self.put(self.root, f"specs/{sid}.md", spec_text(sid, **kwargs))
        self.commit(self.root, "Specs that landed earlier")
        self.branch()
        for sid, kwargs in specs.items():
            self.put(self.root, f"specs/{sid}.md", spec_text(sid, **kwargs))
        if code_path:
            self.put(self.root, code_path, "x = 1\n")
        self.commit(self.root, "the change")
        evidence, _ = self.run_aidd(require_green=gate)
        return {r["name"]: bool(r.get("before_implement")) for r in evidence["results"] if r["status"] != "passed"}, testing.exit_code(evidence)

    def both_modes(self, specs, code_path, landed, failing, code, suite=PASS):
        """A local run excuses what the table says; a run that gates a merge excuses nothing, so every failure fails it."""
        self.assertEqual(self.check(specs, code_path, landed, suite), (failing, code))
        self.assertEqual(self.check(specs, code_path, landed, suite, gate=True), ({n: False for n in failing}, 1 if failing else 0))

    def test_the_table(self):
        b = {"scope": "app/", "code": FAIL}
        cases = [
            # (Specs in the diff, a code path, Specs that landed earlier, failing results and whether each was excused locally, exit locally)
            ({"SPEC-1": self.A, "SPEC-2": b}, "app/x.py", None, {"SPEC-1.check": False, "SPEC-2.check": False}, 1),  # A's `app/**` excuses neither
            ({"SPEC-1": self.A, "SPEC-2": {**b, "status": "in_progress"}}, "app/x.py", None, {"SPEC-1.check": False, "SPEC-2.check": False}, 1),
            ({"SPEC-1": self.A, "SPEC-2": b}, None, None, {"SPEC-1.check": False, "SPEC-2.check": False}, 1),  # B's own file is not A's, nor A's B's
            ({"SPEC-1": {"code": FAIL}}, None, None, {"check": True}, 0),  # one Spec alone, before Implement: its own failure is expected locally
            ({"SPEC-1": {"code": FAIL, "status": "in_review"}}, None, None, {"check": False}, 1),
            # one Spec whose frozen glob covers the whole change excuses its own failure locally, and a gating run still fails
            ({"SPEC-1": self.A}, "app/greet.py", None, {"check": True}, 0),
        ]
        for specs, code_path, landed, failing, code in cases:
            with self.subTest(specs=sorted(specs), code_path=code_path):
                self.both_modes(specs, code_path, landed, failing, code)

    def test_the_repository_suite_is_excused_only_when_every_spec_is(self):
        """The suite sweeps in each Spec's tests, so its failure is expected locally only if no Spec is past Implement or off its own files."""
        cases = [
            ({"SPEC-1": {}}, None, None, {"unit": True}, 0),  # the one Spec is before Implement, and the change holds only its files
            ({"SPEC-1": {"status": "in_review"}}, None, None, {"unit": False}, 1),
            ({"SPEC-1": {"files": ("app/**",), "scope": "lib/"}}, "app/greet.py", None, {"unit": True}, 0),  # a wide frozen glob excuses the suite locally only
        ]
        for specs, code_path, landed, failing, code in cases:
            with self.subTest(specs=sorted(specs), code_path=code_path):
                self.both_modes(specs, code_path, landed, failing, code, suite=FAIL)


class DesignStageEndToEndTests(RepoCase):
    """A Spec-only branch whose acceptance test fails: expected before Implement, a failure after."""

    def test_the_stored_status_decides_whether_a_failing_green_run_is_expected(self):
        for status, code in [("draft", 0), ("ready", 0), ("approved", 0), ("in_progress", 1), ("in_review", 1), ("done", 1), ("cancelled", 1)]:
            with self.subTest(status=status):
                self.fresh()
                self.branch()
                self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status=status, code=FAIL))
                self.commit(self.root, "the Spec")
                evidence, _ = self.run_aidd()
                self.assertEqual(testing.exit_code(evidence), code)
                self.assertEqual(bool(evidence.get("before_implement")), code == 0)


class RequireGreenTests(RepoCase):
    """A run that gates a merge (`--require-green`) excuses nothing, and a local run still tells the author a Spec's own failing test is expected."""

    def design_branch(self, status="draft", suite_fails=False) -> None:
        self.branch()
        self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", status=status, code=FAIL))
        self.commit(self.root, "the Spec")

    def test_a_gating_run_is_red_in_the_design_stage_and_says_why_and_a_local_run_is_not(self):
        for status in ("draft", "ready", "approved"):
            with self.subTest(status=status):
                self.fresh()
                self.design_branch(status)
                local, local_notes = self.run_aidd()
                gate, gate_notes = self.run_aidd(require_green=True)
                self.assertEqual((testing.exit_code(local), bool(local.get("before_implement")), local.get("require_green")), (0, True, None))
                self.assertEqual((testing.exit_code(gate), gate.get("before_implement"), gate["require_green"]), (1, None, True))
                self.assertFalse(any(r.get("before_implement") for r in gate["results"]))
                self.assertTrue(any("expected before Implement" in n and "--require-green" in n and "until Implement" in n for n in gate_notes), gate_notes)
                self.assertFalse(any("--require-green" in n for n in local_notes), local_notes)

    def test_the_command_takes_the_flag_and_a_design_stage_change_exits_1_with_it_and_0_without(self):
        import contextlib
        import io

        from aidd.cli import app

        self.design_branch()
        for argv, code in ((["test", "--base", "main"], 0), (["test", "--base", "main", "--require-green"], 1)):
            with (
                self.subTest(argv=argv),
                contextlib.chdir(self.root),
                contextlib.redirect_stdout(io.StringIO()) as out,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(app.main(argv), code, out.getvalue())

    def test_the_two_flags_that_exclude_each_other_are_refused_before_any_command_runs(self):
        """A quick `--changed` run is never the change's evidence, and a check that gates a merge must be. The pair is a usage error
        (exit 2) that names the next step and runs nothing, so a CI step that writes both cannot turn green on a partial run."""
        import contextlib
        import io

        from aidd.cli import app

        self.design_branch(status="done")
        for flags, code in (
            (["--changed"], 0),
            (["--require-green"], 1),
            (["--changed", "--require-green"], 2),
            (["--watch", "--require-green"], 2),
            (["--no-red", "--require-green"], 2),
        ):
            out = self.root / f"out-{'-'.join(f.strip('-') for f in flags)}"
            watching = mock.patch("aidd.testing.watching.watch_tests", return_value=0) if "--watch" in flags else contextlib.nullcontext()
            with (
                self.subTest(flags=flags),
                watching as watcher,
                contextlib.chdir(self.root),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as err,
            ):
                self.assertEqual(app.main(["test", "--base", "main", "--out", str(out), *flags]), code, err.getvalue())
                self.assertEqual((out / "evidence.json").exists(), code != 2, "a refused pair runs nothing, so it writes no evidence")
                if code == 2:
                    self.assertIn("drop --no-red" if "--no-red" in flags else "drop --changed", err.getvalue())
                    self.assertFalse(watcher and watcher.called, "a refused pair starts no watcher")
        with self.assertRaises(ValueError):
            testing.run_tests(repo=str(self.root), base="main", changed=True, require_green=True)

    def test_evidence_that_says_require_green_is_never_excused_whatever_a_result_claims(self):
        forged = {"results": [{**GREEN_FAIL, "before_implement": True}], "before_implement": True, "require_green": True}
        self.assertEqual(testing.exit_code(forged), 1)
        self.assertEqual(testing.exit_code({**forged, "require_green": False}), 0)

    def test_the_note_that_a_failure_is_expected_is_not_printed_on_a_run_that_still_fails_and_a_merge_says_why_it_refuses(self):
        self.put(self.root, ".aidd/config.yaml", config_text(("unit", FAIL, [])))
        self.commit(self.root, "the base's tests")
        self.branch()
        self.put(self.root, ".aidd/config.yaml", config_text(("unit", PASS, [])))
        self.put(self.root, "specs/SPEC-1.md", spec_text("SPEC-1", code=FAIL, files=(".aidd/config.yaml",)))
        self.commit(self.root, "the head")
        evidence, notes = self.run_aidd()
        self.assertEqual(testing.exit_code(evidence), 1, "the base's command fails, and nothing excuses it")
        self.assertFalse(any("this branch holds only the Spec" in n for n in notes), notes)
        self.assertTrue(any("another result failed too" in n for n in notes), notes)
        excused_pass = {"results": [{**GREEN_PASS, "name": "x"}], "before_implement": True}
        why = local_run.suite_problem(excused_pass, "")
        self.assertIn("excused a failing test", why)
        self.assertNotIn("not clean", why)


if __name__ == "__main__":
    unittest.main()
