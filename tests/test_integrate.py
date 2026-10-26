"""`aidd integrate`, `aidd goal`, and `aidd sync`, end to end in a real repository: the team's own merge into a goal
branch, which asks no person, lands only a verified Spec whose tests pass on the merged tree, and can be taken out.

A small shop under the solo profile, where a normal Spec needs no Spec approval, so each case reaches the merge itself.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, aidd_subprocess, git
from test_flows import _commit, run_cli, shop
from test_local_first import SPEC_FIELDS

from aidd import workitems

GOAL = "goal/EPIC-1"
EPIC = "---\nkind: epic\nid: EPIC-1\ntitle: Discounts\nreaches: batched\nspecs: [SPEC-1, SPEC-2]\n---\n\nTwo discounts, released together.\n"
TEST = "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n"
IMPL = "def discount(total, pct):\n    return total - total * pct // 100\n"


def spec_on_goal(root: Path, sid: str = "SPEC-1") -> None:
    """A Spec's branch cut from the goal: the Spec (`base: goal/EPIC-1`) and its failing test, committed."""
    git(root, "switch", "-qc", f"spec/{sid}", GOAL)
    run = aidd_subprocess("new", "spec", sid, "--title", "Apply a percentage discount", "--type", "feat", "--parent", "EPIC-1", cwd=root)
    assert run.returncode == 0, run.stdout + run.stderr
    spec = Path(root, f"specs/{sid}.md")
    text = spec.read_text(encoding="utf-8")
    for old, new in SPEC_FIELDS.items():
        text = text.replace(old, new)
    assert f"base: {GOAL}" in text, text
    spec.write_text(text, encoding="utf-8")
    _commit(root, f"spec: {sid} and its test\n\nAssisted-by: claude-code/claude-opus-5-5", {"tests/test_discount.py": TEST})


@unittest.skipUnless(shutil.which("git"), "git is required")
class IntegrateTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root)
        _commit(root, "plan: EPIC-1, agreed\n\nAssisted-by: claude-code/claude-opus-5-5", {"specs/EPIC-1.md": EPIC})
        code, out = run_cli(root, "goal", "open", "EPIC-1")
        assert code == 0, out
        spec_on_goal(root)

    def implement(self) -> str:
        return _commit(self.root, "feat: discount\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/discount.py": IMPL})

    def test_goal_open_cuts_the_goal_once_and_says_where(self):
        self.assertTrue(git(self.root, "rev-parse", "--verify", GOAL))
        code, out = run_cli(self.root, "goal", "open", "EPIC-1")
        self.assertEqual(code, 0, out)
        self.assertIn(f"{GOAL} is open at", out)  # nothing changes the second time
        code, out = run_cli(self.root, "goal", "open")
        self.assertEqual(code, 2, out)
        self.assertIn("name the Epic", out)

    def test_a_verified_spec_lands_as_a_merge_commit_with_nobody_asked(self):
        head = self.implement()
        before = git(self.root, "rev-parse", GOAL)
        code, out = run_cli(self.root, "integrate")
        self.assertEqual(code, 0, out)
        self.assertIn(f"integrated SPEC-1 (spec/SPEC-1 at {head[:12]}) into {GOAL}", out)
        tip = git(self.root, "rev-parse", GOAL)
        self.assertEqual(git(self.root, "rev-list", "--parents", "-n", "1", tip).split()[1:], [before, head])
        self.assertIn(workitems.integrate_trailer("SPEC-1"), git(self.root, "log", "-1", "--format=%B", tip))
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head, "the Spec's own branch stays where it was")
        self.assertIn("SPEC-1", workitems.integrated(str(self.root), GOAL))
        code, out = run_cli(self.root, "integrate")  # again: it says so, and changes nothing
        self.assertEqual((code, git(self.root, "rev-parse", GOAL)), (0, tip), out)
        self.assertIn("is already in", out)

    def test_a_spec_whose_tests_fail_on_the_merge_never_lands(self):
        before = git(self.root, "rev-parse", GOAL)
        code, out = run_cli(self.root, "integrate")  # the test is red: nothing implements it yet
        self.assertEqual(code, 1, out)
        self.assertIn("Not integrated", out)
        self.assertEqual(git(self.root, "rev-parse", GOAL), before)

    def test_undo_takes_it_out_with_one_revert_commit(self):
        self.implement()
        self.assertEqual(run_cli(self.root, "integrate")[0], 0)
        merged = git(self.root, "rev-parse", GOAL)
        code, out = run_cli(self.root, "integrate", "--undo", "SPEC-1")
        self.assertEqual(code, 0, out)
        self.assertIn(f"took SPEC-1 out of {GOAL}", out)
        tip = git(self.root, "rev-parse", GOAL)
        self.assertEqual(git(self.root, "rev-parse", f"{tip}^"), merged)
        self.assertIn(workitems.undo_trailer("SPEC-1"), git(self.root, "log", "-1", "--format=%B", tip))
        self.assertEqual(git(self.root, "diff", "--name-only", f"{merged}^1", tip), "", "the goal's tree is as before the Spec")
        self.assertNotIn("SPEC-1", workitems.integrated(str(self.root), GOAL))
        code, out = run_cli(self.root, "integrate", "--undo", "SPEC-9")
        self.assertEqual(code, 2, out)
        self.assertIn("no goal branch holds SPEC-9", out)

    def test_it_refuses_off_a_spec_branch_on_a_explore_branch_and_with_uncommitted_work(self):
        self.implement()
        git(self.root, "switch", "-q", "main")
        code, out = run_cli(self.root, "integrate")
        self.assertEqual(code, 2, out)
        self.assertIn("integrate runs on a Spec's branch cut from its goal branch", out)
        git(self.root, "switch", "-q", "spec/SPEC-1")
        Path(self.root, "app/discount.py").write_text(IMPL + "# draft\n", encoding="utf-8")
        code, out = run_cli(self.root, "integrate")
        self.assertEqual(code, 1, out)
        self.assertIn("uncommitted changes", out)
        git(self.root, "checkout", "--", "app/discount.py")
        git(self.root, "switch", "-qc", "explore/discount")
        code, out = run_cli(self.root, "integrate", "--goal", GOAL)
        self.assertEqual(code, 2, out)
        self.assertIn("is an explore branch", out)

    def test_sync_merges_the_goal_in_and_never_rebases(self):
        self.implement()
        self.assertEqual(run_cli(self.root, "integrate")[0], 0)
        # A sibling Spec's branch, cut before SPEC-1 landed, takes the goal in as a merge commit.
        git(self.root, "switch", "-qc", "spec/SPEC-2", f"{GOAL}^1")
        _commit(self.root, "spec: SPEC-2 draft", {"NOTES.md": "SPEC-2\n"})
        own = git(self.root, "rev-parse", "HEAD")
        code, out = run_cli(self.root, "sync", "--from", GOAL)
        self.assertEqual(code, 0, out)
        parents = git(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
        self.assertEqual(parents, [own, git(self.root, "rev-parse", GOAL)])
        code, out = run_cli(self.root, "sync", "--from", GOAL)
        self.assertEqual(code, 0, out)
        self.assertIn("already holds", out)

    def test_sync_onto_a_goal_takes_only_the_default_branch(self):
        git(self.root, "switch", "-q", GOAL)
        code, out = run_cli(self.root, "sync", "--from", "spec/SPEC-1")
        self.assertEqual(code, 2, out)
        self.assertIn("A Spec lands with `aidd integrate`", out)

    def test_goal_list_names_the_goal_and_what_it_holds(self):
        self.implement()
        self.assertEqual(run_cli(self.root, "integrate")[0], 0)
        code, out = run_cli(self.root, "goal", "list")
        self.assertEqual(code, 0, out)
        self.assertIn(f"{GOAL}: 1 integrated", out)


if __name__ == "__main__":
    unittest.main()
