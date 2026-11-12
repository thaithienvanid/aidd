"""Revising an approved Spec's tests, end to end, as CI runs it (`aidd test --require-green`) and as a delegated merge reads it.

The base holds SPEC-1 approved, with one command (`check`), its frozen test file, and code that passes it. Each shape is one change
holding the Spec, its tests, and the code, built as the loop's `spec.revise` says (the Spec goes back to `draft` with a `revisions`
entry, then is approved again). The table records what a person sees: the exit code, the results, whether a note names the next
step, and what the delegate's merge check answers. Invariant: the base's commands still run, so a revision goes green in one change
exactly when every command the base holds still passes on the head; a retired or renamed command whose old test cannot pass stays
red by design, and the note names who acts. No head-written text is read as a person's yes.
"""

from __future__ import annotations

import json
import unittest

from spec_repo_fixtures import PASS, PY, RepoCase, config_text
from test_delegation_check import ENV, NAME, note

from aidd import config, delegation, records, testing
from helpers import git

CONFIG = ".aidd/config.yaml"
SPEC = "specs/SPEC-1.md"
WHO = "Maya Lee <maya@users.noreply.github.com>"
DELEGATION = f'delegation:\n  default_branch: main\n  by: "{WHO}"\n  at: "2026-11-01T09:00:00Z"\n  decides: [spec.approve, git.merge]\n  review_due: "2099-01-01"\nenvironments: []\n'

CHECK = {"name": "check", "command": [PY, "checks/test_greet.py"], "new_behavior": True, "covers": ["A1"]}
LOUD = {"name": "check_loud", "command": [PY, "checks/test_loud.py"], "new_behavior": False, "covers": ["A2"]}
RENAMED = {**CHECK, "command": [PY, "checks/test_greeting.py"]}
RENAMED_NEW = {**RENAMED, "name": "check_v2", "new_behavior": False}
QUIET = {**RENAMED, "new_behavior": False}


def greet_test(expected: str) -> str:
    return f"import sys\nsys.path.insert(0, '.')\nfrom app.greet import greet\nassert greet() == {expected!r}, greet()\n"


def greet_code(value: str) -> str:
    return f"def greet():\n    return {value!r}\n"


LOUD_TEST = "import sys\nsys.path.insert(0, '.')\nfrom app.loud import loud\nassert loud() == 'HELLO'\n"
LOUD_CODE = "def loud():\n    return 'HELLO'\n"


def spec_doc(status: str, commands: list[dict], files: list[str], revised: int = 0) -> str:
    """SPEC-1 with these commands and frozen files, in `status`; `revised` is how many `revisions` entries it holds, one for each
    `spec.revise` the loop records."""
    ids = sorted({i for c in commands for i in c["covers"]})
    lines = [
        "---",
        "type: spec",
        "id: SPEC-1",
        "title: Greeting says hello",
        f"status: {status}",
        "change_type: feat",
        "route: normal",
        "confidence: high",
        "rollback: Revert the PR.",
        "risk:",
        "  summary: Changes a greeting.",
        "  dimensions: []",
        "  irreversible: false",
        "tasks:",
        "  - id: T1",
        "    title: Implement greet",
        "    scope: [app/]",
        "    risk: low",
        "    proof: test check",
        "tests:",
        f"  files: {json.dumps(files)}",
        "  commands:",
    ]
    for c in commands:
        lines += [
            f"    - name: {c['name']}",
            f"      command: {json.dumps(c['command'])}",
            f"      new_behavior: {str(c['new_behavior']).lower()}",
            f"      covers: {json.dumps(c['covers'])}",
        ]
    if status in ("approved", "in_progress", "done"):
        lines += [f'approved_by: "{WHO}"', 'approved_at: "2026-11-01T10:00:00Z"']
    if revised:
        lines += ["revisions:"]
        for n in range(revised):
            lines += [f'  - why: "The greeting changes, revision {n + 1}."', '    at: "2026-11-11T09:00:00Z"', f'    by: "{WHO}"']
    body = "\n".join(f"- {i}: Given a call, then it answers as the test says." for i in ids)
    return (
        "\n".join(lines)
        + f'\n---\n\n## Request\n\n"Change the greeting."\n\n## Context\n\nA tiny example.\n\n## Acceptance\n\n{body}\n\n## Policy conflicts\n\nnone\n'
    )


class RevisionCase(RepoCase):
    """`main` holds SPEC-1 with `check`, its frozen file, and passing code, under a solo delegation of `git.merge` and `spec.approve`.
    The Spec is `done` (merged), as a later revision finds it; `Approved` holds it `approved`, as the brief describes."""

    BASE_STATUS = "done"

    @classmethod
    def build_template(cls, root):
        super().build_template(root)
        cls.put(root, CONFIG, config_text(("unit", PASS, []), extra=DELEGATION).replace("profile: team", "profile: solo"))
        cls.put(root, "app/greet.py", greet_code("hello"))
        cls.put(root, "checks/test_greet.py", greet_test("hello"))
        cls.put(root, SPEC, spec_doc(cls.BASE_STATUS, [CHECK], ["checks/test_greet.py"]))
        cls.commit(root, "SPEC-1 built")

    def write(self, files: dict[str, str | None]) -> None:
        for path, text in files.items():
            if text is None:
                (self.root / path).unlink()
            else:
                self.put(self.root, path, text)

    def land_on_main(self, files: dict[str, str | None]) -> None:
        self.write(files)
        self.commit(self.root, "main moves")

    def accept(self, spec_head: str) -> None:
        """The delegate's accept of SPEC-1's approval on `spec_head`: the one record a delegated merge counts."""
        data = {
            "action": "spec.approve",
            "covers": {"spec": "SPEC-1", "head": spec_head, "tree": git(self.root, "rev-parse", f"{spec_head}^{{tree}}")},
            "outcome": "accept",
            "reason": "ready",
            "check": "20261111T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by=config.DECIDED_BY, cwd=str(self.root))

    def revise(self, revised_spec: str, tests: dict[str, str | None], code: dict[str, str | None], *, approve: bool = True, with_code: bool = True) -> str:
        """The loop's flow on a branch from `main`: the revised Spec as `ready` with its tests, the delegate's accept of that commit,
        `approved` again (or left `draft` when `approve` is False, the pending case), then the code and a handoff note. The head."""
        self.steps = getattr(self, "steps", 0) + 1
        self.branch(f"feat{self.steps}")
        status = "ready" if approve else "draft"
        self.write({SPEC: revised_spec.replace("status: approved", f"status: {status}"), **tests})
        spec_head = self.commit_and_id("Revise SPEC-1: the Spec and its tests")
        if approve:
            self.accept(spec_head)
            self.write({SPEC: revised_spec})
            self.commit(self.root, "Approve SPEC-1 again")
        return self.finish(code if with_code else {})

    def finish(self, code: dict[str, str | None]) -> str:
        """The code (none is an empty commit), then a handoff note that names it: the head. Back on `main`."""
        self.write(code)
        git(self.root, "add", "-A")
        git(self.root, *NAME, "commit", "-q", "--allow-empty", "-m", "Implement")
        built = git(self.root, "rev-parse", "HEAD")
        git(self.root, *NAME, "commit", "-q", "--allow-empty", "-m", "Hand off", "-m", note(built))
        head = git(self.root, "rev-parse", "HEAD")
        git(self.root, "switch", "-q", "main")
        return head

    def merge(self, head: str, status: str = "in_review") -> None:
        """What a merge into `main` leaves: `main` at the head, whose Spec has reached `status` by then (`in_review`: Verify is clean)."""
        git(self.root, "switch", "-q", "main")
        git(self.root, "reset", "-q", "--hard", head)
        if status != "approved":
            self.write({SPEC: (self.root / SPEC).read_text(encoding="utf-8").replace("status: approved", f"status: {status}")})
            self.commit(self.root, f"SPEC-1 {status}")

    def commit_and_id(self, message: str) -> str:
        self.commit(self.root, message)
        return git(self.root, "rev-parse", "HEAD")

    def ci(self, head: str) -> tuple[dict, list[str]]:
        """`aidd test --require-green` as CI runs it, on `head`."""
        git(self.root, "switch", "-q", "--detach", head)
        try:
            return self.run_aidd(require_green=True)
        finally:
            git(self.root, "switch", "-q", "main")

    def delegate_detail(self, head: str):
        result = delegation.run_check(delegation.Request(action="git.merge", command=f"git merge --no-ff {head}", head=head, cwd=str(self.root), env=ENV))
        return [(r["code"], r["detail"][:150]) for r in result["reasons"]]

    def shown(self, head: str):
        evidence, notes = self.ci(head)
        return testing.exit_code(evidence), sorted((r["name"], r["red_green"], r["status"]) for r in evidence["results"]), notes


SPEC_A = spec_doc("approved", [CHECK], ["checks/test_greet.py"], revised=1)


MORE = {"name": "check_more", "command": [PY, "checks/test_more.py"], "new_behavior": False, "covers": ["A3"]}
MORE_TEST = "import sys\nsys.path.insert(0, '.')\nfrom app.greet import greet\nassert greet().startswith('h')\n"
BOTH = ["checks/test_greet.py", "checks/test_loud.py"]
OLD, NEW = ["checks/test_greet.py"], ["checks/test_greeting.py"]


class Shapes(RevisionCase):
    """The six shapes of a revision, each as one change from `main`: `shape(name)` builds it and returns the head."""

    def spec(self, commands, files, revised=True):
        """The revised Spec of the next change: one `revisions` entry more than any change before it recorded."""
        return spec_doc("approved", commands, files, getattr(self, "steps", 0) + 1 if revised else 0)

    def land_loud(self):
        self.land_on_main({"app/loud.py": LOUD_CODE, "checks/test_loud.py": LOUD_TEST, SPEC: spec_doc(self.BASE_STATUS, [CHECK, LOUD], BOTH)})

    def shape(self, name: str) -> str:
        new_test, new_code = {"checks/test_greet.py": greet_test("hello, world")}, {"app/greet.py": greet_code("hello, world")}
        if name == "a":  # new expectation in the same file, the command unchanged, the code follows
            return self.revise(self.spec([CHECK], OLD), new_test, new_code)
        if name == "b":  # as (a), the Spec left draft: approval is still pending
            return self.revise(self.spec([CHECK], OLD), new_test, new_code, approve=False)
        if name == "c":  # the file is renamed, the command changes with it, and the expectation is new
            return self.revise(self.spec([RENAMED], NEW), {"checks/test_greet.py": None, "checks/test_greeting.py": greet_test("hello, world")}, new_code)
        if name == "d":  # behavior retired: its command, its test file, and its code go
            self.land_loud()
            return self.revise(self.spec([CHECK], OLD), {"checks/test_loud.py": None}, {"app/loud.py": None})
        if name == "e":  # a command added, nothing else changed
            return self.revise(self.spec([CHECK, MORE], [*OLD, "checks/test_more.py"]), {"checks/test_more.py": MORE_TEST}, {})
        if name == "f":  # the Spec and its test alone, no code
            return self.revise(self.spec([CHECK], OLD), new_test, {}, with_code=False)
        raise KeyError(name)


class ShapesTests(Shapes):
    """`aidd test --require-green` and the delegate's merge check on each shape, with the Spec `done` on `main`."""

    # shape: (CI's exit code, the results, whether the base's copy ran, the delegate's reasons)
    TABLE = {
        "a": (0, {("check", "green", "passed")}, False, ["no_spec"]),
        "b": (0, {("check", "green", "passed")}, False, ["no_spec", "no_spec"]),
        "c": (1, {("check", "green", "passed"), ("base.check", "green", "failed")}, True, ["no_spec"]),
        "d": (1, {("check", "green", "passed"), ("base.check_loud", "green", "failed")}, True, ["no_spec"]),
        "e": (0, {("check", "green", "passed"), ("check_more", "green", "passed")}, False, ["no_spec"]),
        "f": (1, {("check", "green", "failed")}, False, ["no_spec"]),
    }

    def test_each_shape(self):
        for name, (exit_code, results, copied, reasons) in self.TABLE.items():
            with self.subTest(shape=name):
                self.fresh()
                head = self.shape(name)
                code, ran, notes = self.shown(head)
                self.assertEqual((code, {r for r in ran if r[0] != "unit"}), (exit_code, results))
                said = [n for n in notes if n.startswith("SPEC-1:")]
                self.assertEqual(any("base.<name>" in n for n in said), copied, notes)
                self.assertTrue(all("approves the Spec again" in n for n in said), "every note names who acts")
                self.assertEqual(all("later change" in n for n in said), copied and bool(said), "a failing base copy gets the step that works")
                self.assertEqual(codes_of(self.delegate_detail(head)), reasons)

    def test_the_delegate_cannot_approve_a_revision_it_did_not_see_red(self):
        """With the Spec `done`, no new-behavior test runs on the base, so the delegate's re-check of the approval defers to a person."""
        self.fresh()
        head = self.shape("a")
        detail = self.delegate_detail(head)
        self.assertIn("not_red_on_base", detail[0][1])


class ApprovedBaseTests(Shapes):
    """The same shapes with the Spec held `approved` beside code that passes it, as the brief describes."""

    BASE_STATUS = "approved"

    def test_a_revision_in_place_is_green_and_the_delegate_accepts_the_recorded_re_approval(self):
        self.fresh()
        head = self.shape("a")
        code, ran, notes = self.shown(head)
        self.assertEqual((code, self.delegate_detail(head)), (0, []))
        self.assertEqual(len(notes), 1, notes)
        self.assertTrue(notes[0].startswith("SPEC-1:") and "checks/test_greet.py" in notes[0] and "approves the Spec again" in notes[0], notes)
        self.assertIn(("check", "red", "failed"), ran, "the new expectation fails on the old code")

    def test_the_same_edit_with_no_recorded_revision_stops_the_gate(self):
        """Holding the Spec is no revision: on a branch named for it, the frozen test and the code change as in shape (a), the Spec does
        not, and `--require-green` stops with the step, because nothing records the person's `spec.revise`."""
        self.fresh()
        self.branch("spec/SPEC-1")
        self.write({"checks/test_greet.py": greet_test("hello, world")})
        head = self.finish({"app/greet.py": greet_code("hello, world")})
        with self.assertRaises(RuntimeError) as stopped:
            self.ci(head)
        self.assertIn("revise SPEC-1 in this change", str(stopped.exception))

    def test_a_command_added_beside_an_unchanged_new_behavior_command_is_red_for_that_command_alone(self):
        """Red before green: the unchanged `check` still says it is new behavior and already passes on the base's built code. Not a
        revision problem: a Spec held `approved` beside its built code is the cause, and `done` clears it."""
        self.fresh()
        head = self.shape("e")
        code, ran, _ = self.shown(head)
        self.assertEqual(code, 1)
        self.assertIn(("check", "red", "passed"), ran)


def codes_of(detail: list[tuple[str, str]]) -> list[str]:
    return [code for code, _ in detail]


if __name__ == "__main__":
    unittest.main()
