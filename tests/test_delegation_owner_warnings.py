"""A delegation that will surprise its owner says so once, in the same words, wherever the config is read.

Invariant: a delegation that decides a merge (`pr.merge` or `git.merge`) and not `spec.approve` warns, because a delegated
merge counts only the delegate's own accept of the Spec's approval, so every merge of a change with a Spec waits for the person.
No other combination warns. `aidd validate`, `aidd doctor`, and `aidd init --delegate` print what `config.delegation_warnings`
returns, and doctor also prints the same-model warning the delegate check prints for the branch checked out.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config, workitems
from aidd.setup import adoption, delegation_wiring, doctor_checks

TODAY = dt.date(2026, 11, 11)
MERGES = ("pr.merge", "git.merge")


def delegation(decides: list[str] | None, reserved: list[str] | None = None) -> dict:
    block = {"by": "me <me@example.com>", "at": "2026-11-01T09:00:00Z", "review_due": "2026-12-01", "default_branch": "main", "digest": "each_session"}
    return {**block, **({"decides": decides} if decides is not None else {}), "reserved": reserved or []}


class TheTableOfCombinations(unittest.TestCase):
    def test_only_a_merge_delegated_without_spec_approve_warns(self):
        cases = {
            # name: (decides, reserved, warns)
            "a merge, and spec.approve": (["pr.merge", "spec.approve"], [], False),
            "git.merge, and spec.approve": (["git.merge", "spec.approve"], [], False),
            "a merge, no spec.approve": (["pr.merge"], [], True),
            "git.merge, no spec.approve": (["git.merge", "git.push"], [], True),
            "both merges, no spec.approve": (["pr.merge", "git.merge"], [], True),
            "no merge, spec.approve": (["spec.approve", "git.push"], [], False),
            "no merge, no spec.approve": (["git.push"], [], False),
            "nothing decided": ([], [], False),
            "a merge decided and reserved, no spec.approve": (["pr.merge"], ["pr.merge"], False),
            "a merge and spec.approve, spec.approve reserved": (["pr.merge", "spec.approve"], ["spec.approve"], True),
            "decides is no list": (None, [], False),
        }
        for name, (decides, reserved, warns) in cases.items():
            with self.subTest(name):
                found = config.delegation_warnings(delegation(decides, reserved), TODAY)
                self.assertEqual(len(found), int(warns), found)
                if warns:
                    self.assertIn("spec.approve", found[0])
                    self.assertIn("waits for you", found[0])
                    self.assertIn("still merges", found[0])
                    self.assertTrue(found[0].endswith("or merge those yourself"), "the next step is last")
                    self.assertLess(len(found[0]), 220)

    def test_no_delegation_is_no_warning_and_the_review_warning_still_comes_with_it(self):
        self.assertEqual(config.delegation_warnings({}, TODAY), [])
        far = {**delegation(["pr.merge"]), "review_due": "2099-01-01"}
        self.assertEqual([w.split()[0] for w in config.delegation_warnings(far, TODAY)], ["delegation.review_due", "delegation.decides"])


class EveryPlacePrintsTheSameWarning(unittest.TestCase):
    def repo(self, decides: list[str] | None = None, extra: str = "", review_due: str | None = None) -> Path:
        """A repository that adopted aidd with a delegation block as `aidd init --delegate` writes it, with `decides` and
        `review_due` changed when given, committed on main."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        lines = delegation_wiring.block("me <me@example.com>", "main", TODAY).splitlines()
        lines = [f"  decides: [{', '.join(decides)}]" if decides is not None and ln.startswith("  decides:") else ln for ln in lines]
        lines = [f'  review_due: "{review_due}"' if review_due and ln.startswith("  review_due:") else ln for ln in lines]
        cfg = root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n" + "\n".join(lines) + "\n" + extra, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "Adopt aidd")
        return root

    def delegation_lines(self, root: Path, which: str) -> list[str]:
        if which == "validate":
            seen = (w.removeprefix("warning: ").removeprefix(".aidd/config.yaml: ") for w in workitems.check_repo(root)[1])
            return [w for w in seen if w.startswith("delegation.")]
        return [m for level, m in doctor_checks.doctor(root, today=dt.date.today()) if level == "warning" and m.startswith("delegation.")]

    def test_doctor_prints_what_validate_prints(self):
        # `decides` less spec.approve, with a review date far ahead: both warnings, in the same order.
        root = self.repo(["pr.merge", "git.push"], review_due="2099-01-01")
        said = self.delegation_lines(root, "validate")
        self.assertEqual([w.split()[0] for w in said], ["delegation.review_due", "delegation.decides"], said)
        self.assertEqual(self.delegation_lines(root, "doctor"), said)

    def test_a_delegation_that_decides_spec_approve_prints_neither_as_init_writes_it(self):
        root = self.repo(review_due=(dt.date.today() + dt.timedelta(days=90)).isoformat())
        self.assertEqual(self.delegation_lines(root, "validate"), [])
        self.assertEqual(self.delegation_lines(root, "doctor"), [])

    def test_init_delegate_previews_the_warning_from_the_same_function(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "Me")
        git(root, "config", "user.email", "me@example.com")
        actions = adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[], delegate=True))
        self.assertFalse([a for a in actions if "waits for you" in a], "init's own block decides spec.approve")
        warned = {"decides": ["pr.merge"], "reserved": []}
        self.assertEqual(len(config.delegation_warnings(warned, TODAY)), 1)

    def test_doctor_prints_the_same_model_warning_for_the_branch_checked_out(self):
        root = self.repo(
            extra="agents:\n  models:\n    delegate: anthropic/claude-opus-5-5\n", review_due=(dt.date.today() + dt.timedelta(days=90)).isoformat()
        )

        def weaker() -> list[str]:
            return [m for _, m in doctor_checks.doctor(root, today=dt.date.today()) if "weaker second look" in m]

        self.assertEqual(weaker(), [], "on the default branch no commit is the change's")
        git(root, "switch", "-q", "-c", "feat")
        (root / "x.txt").write_text("x\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "Change x", "-m", "Assisted-by: claude-code/claude-opus-5-5")
        self.assertEqual(len(weaker()), 1)
        (root / ".aidd" / "config.yaml").write_text(
            (root / ".aidd" / "config.yaml").read_text(encoding="utf-8").replace("claude-opus-5-5", "claude-sonnet-5-5"), encoding="utf-8"
        )
        self.assertEqual(weaker(), [], "another model for the delegate")


if __name__ == "__main__":
    unittest.main()
