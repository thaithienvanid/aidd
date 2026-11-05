"""The merge check decides by the base. Invariant: for every field that decides what a Spec's change may do (its status, route,
Task scope, tests, and frozen files), a head that changes the field gets the base's answer, or the stricter of the two, and
never a looser one than the base gives. A Spec new at the head is the head's own."""

import tempfile
from pathlib import Path

from helpers import SAMPLE_SPEC, git
from test_delegation_check import Repo, codes, note
from test_delegation_spec import SpecCase

EMERGENCY = 'route: emergency\nemergency:\n  severity: sev2\n  type: outage\n  commander: "@x"\n  incident: INC-1\n  backfill_due: "2099-01-01"'


class BaseDecidesTests(SpecCase):
    def landed(self, edit=lambda text: text) -> Repo:
        """SPEC-220 approved on `main` (the delegate's yes on record), edited by `edit`; `feature` starts from `main`."""
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        ready = edit(SAMPLE_SPEC.replace("route: normal", "status: ready\nroute: normal"))
        repo.write("specs/SPEC-220.md", ready)
        repo.write(
            "tests/test_discount.py",
            "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        self.assertTrue(__import__('os').path.exists('src/checkout/discount.py'))\n",
        )
        self.delegate_approved(repo.commit("SPEC-220: the Spec and its tests"))
        repo.write("specs/SPEC-220.md", ready.replace("status: ready", "status: approved"))
        repo.commit(
            "Approve SPEC-220",
            "-m",
            "Decided-by: agent:claude-code/aidd-team:delegate\nOn-behalf-of: Maya Lee <maya@users.noreply.github.com>\nDelegation: " + "b" * 40,
        )
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        return repo

    def head(self, repo: Repo, spec_edit) -> str:
        text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
        repo.write("specs/SPEC-220.md", spec_edit(text))
        repo.write("src/checkout/discount.py", "RATE = 0.1\n")
        code = repo.commit("Implement")
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def codes(self, base_edit, head_edit) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo = self.landed(base_edit)
            result = repo.check(self.head(repo, head_edit))
            self.detail = [r["detail"] for r in result["reasons"]]
            return codes(result)

    def test_a_head_that_changes_a_deciding_field_never_gets_a_looser_answer_than_the_base_gives(self):
        """The Spec is in the diff in every row, so the run and the check both read it. The tests, scope, and frozen-file rows
        are in test_delegation_spec_changes; these are the fields the check read from the head's text before."""
        touch = lambda f: lambda t: f(t) + "\n<!-- touched -->\n"  # noqa: E731
        emergency = lambda t: t.replace("route: normal", EMERGENCY)  # noqa: E731
        cases = {
            "the base is on the emergency route and the head says normal": (
                emergency,
                touch(lambda t: t.replace(EMERGENCY, "route: normal")),
                "emergency_route",
            ),
            "the base is on the emergency route and the head keeps it": (emergency, touch(lambda t: t), "emergency_route"),
            "the base is normal and the head says emergency": (lambda t: t, touch(emergency), "emergency_route"),
            "the head lowers the status to draft": (lambda t: t, touch(lambda t: t.replace("status: approved", "status: draft")), "no_spec"),
            "the head lowers the status to ready": (lambda t: t, touch(lambda t: t.replace("status: approved", "status: ready")), "no_spec"),
        }
        for name, (base_edit, head_edit, expected) in cases.items():
            with self.subTest(name):
                self.assertIn(expected, self.codes(base_edit, head_edit), name)
                if expected == "no_spec":
                    self.assertTrue(any("in the head" in d for d in self.detail), "the head's lowered status is what defers, not another reason")
        with self.subTest("nothing changes: a Spec the base holds and the head touches reaches the approval check"):
            self.assertNotIn("emergency_route", self.codes(lambda t: t, touch(lambda t: t)))

    def test_a_spec_new_at_the_head_is_the_heads_own(self):
        for route, expected in (("normal", ["no_spec"]), ("emergency", ["emergency_route"])):
            with self.subTest(route), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.repo()
                text = SAMPLE_SPEC.replace("route: normal", EMERGENCY if route == "emergency" else "route: normal")
                repo.write("specs/SPEC-220.md", text.replace("route:", "status: approved\nroute:", 1))
                repo.write("src/checkout/discount.py", "RATE = 0.1\n")
                code = repo.commit("A new Spec and its work")
                head = repo.commit("Hand off", "-m", note(code))
                git(self.root, "checkout", "-q", "main")
                self.assertTrue(set(expected) <= set(codes(repo.check(head))))


if __name__ == "__main__":
    import unittest

    unittest.main()
