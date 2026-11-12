"""A delegated Spec approval and the Intents it answers to: the Intent the Spec names as its parent, and each Intent on the default
branch's tip that lists it as a slice, must stand approved there, with the Spec among the approved slices, no person having ended it, and
the head holding it as the person approved it. The checks that read a change's own edits are in test_delegation_approvals."""

from __future__ import annotations

import unittest

from helpers import git
from test_delegation_approvals import APPROVED_BY, FORMER, INTENT, INTENTS, OTHER, PERSON, RED, YES, ApprovalCase, intent, spec_text
from test_delegation_check import Repo, codes

from aidd.delegation import policy


class AParentIntentMustStandApprovedTests(ApprovalCase):
    def spec_head(self, repo: Repo, parent: str | None = "INTENT-1", edits: dict[str, str] | None = None, *trailers: str) -> str:
        """SPEC-220 and its red test on feature, with `parent` set when named, and `edits` besides, in one commit whose message
        carries the `trailers`, each in a paragraph of its own."""
        repo.write("specs/SPEC-220.md", spec_text(parent))
        repo.write("tests/test_discount.py", RED)
        for path, text in (edits or {}).items():
            repo.write(path, text)
        return repo.commit("SPEC-220: the Spec and its tests", *(arg for line in trailers for arg in ("-m", line)))

    def test_a_spec_approval_waits_for_the_parent_intent_to_stand_approved_on_the_tip(self):
        cases = {
            # name: (the Intent main holds, whether its commit has the person's two lines, the Spec's parent, the reasons)
            "a draft": (intent(approved=False), True, "INTENT-1", ["intent_not_approved"]),
            "an approval written in the file, with no Approved-by or Approves line": (None, False, "INTENT-1", ["intent_not_approved"]),
            "an Intent the tip does not hold": (None, True, "INTENT-9", ["intent_not_approved"]),
            "approved": (None, True, "INTENT-1", []),
        }
        for name, (text, trailer, parent, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved(text, message=(YES,) if trailer else ())
                result = self.approve(repo, self.spec_head(repo, parent))
                self.assertEqual((codes(result), result["reserved"]), (expected, bool(expected)))

    def test_an_approval_the_branch_writes_itself_is_not_the_tips(self):
        """The check reads the Intent, and the commit that records its approval, from the default branch's tip, never from the
        branch under check or the working tree. Lines or an approval the branch's own commit carries count for nothing."""
        both = ["intent_approval_changed", "intent_not_approved"]
        prd = f"{APPROVED_BY}\nApproves: product/prd.md"
        cases = {
            # name: (the Intent main holds, how it was recorded, the branch's edits, the branch commit's trailers, the reasons)
            "the approval and the Spec in one commit with the two lines": (intent(approved=False), (YES,), {INTENT: intent()}, (YES,), both),
            "the approval and the Spec in one commit with an Approved-by line alone": (
                intent(approved=False),
                (YES,),
                {INTENT: intent()},
                (APPROVED_BY,),
                both,
            ),
            "an Approved-by line alone on the tip's commit, which is no approval": (None, (APPROVED_BY,), {}, (), ["intent_not_approved"]),
            "an Approves line alone on the tip's commit, which is no approval": (None, ("Approves: INTENT-1",), {}, (), ["intent_not_approved"]),
            "the retired Agreed-by line on the tip's commit, which no reader takes": (None, (f"Agreed-by: {PERSON}",), {}, (), ["intent_not_approved"]),
            "an approved Intent's goal edited in the Spec's commit, with the two lines": (
                None,
                (YES,),
                {INTENT: intent(OTHER)},
                (YES,),
                ["intent_approval_changed"],
            ),
            "the PRD edited in the Spec's commit, with its two lines": (None, (YES,), {"product/prd.md": "# A\n"}, (prd,), ["reserved_path"]),
        }
        for name, (text, recorded, edits, trailers, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved(text, message=recorded)
                self.assertEqual(codes(self.approve(repo, self.spec_head(repo, "INTENT-1", edits, *trailers))), expected)
        self.fresh()
        repo = self.approved(intent(approved=False))
        head = self.spec_head(repo)
        repo.write(INTENT, intent())  # in the working tree of the check, not in any commit
        self.assertEqual(codes(self.approve(repo, head)), ["intent_not_approved"], "the working tree is no tip")

    def test_an_intent_outside_the_intents_folder_on_the_tip_is_no_approved_parent(self):
        """The tip holds the Intent only in the specs folder, approved at that path: the delegate reads an Intent in the Intents' folder
        alone, so the Spec approval waits for a person, whether the Spec names the Intent or the Intent lists the Spec."""
        cases = {"the Spec names it": "INTENT-1", "the Spec names no parent and the Intent lists it": None}
        for name, parent in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved(path=f"{FORMER}/INTENT-1.md")
                result = self.approve(repo, self.spec_head(repo, parent))
                self.assertEqual((codes(result), result["reserved"]), (["intent_not_approved"], True))
                self.assertIn("is no Intent the tip of main holds", result["reasons"][0]["detail"])

    def test_an_approval_stands_across_the_move_a_person_makes_with_git_mv(self):
        """A person approved at another place, then moved the file into the Intents' folder with `git mv`, in a commit with no
        approval lines. The approval is found through git's own record of the rename, so the Spec approval is eligible."""
        repo = self.approved(intent(), path=f"{FORMER}/INTENT-1.md")
        git(self.root, "checkout", "-q", "main")
        (self.root / INTENT).parent.mkdir(parents=True, exist_ok=True)
        git(self.root, "mv", f"{FORMER}/INTENT-1.md", INTENT)
        repo.write(INTENT, intent())
        repo.commit("Move the Intent into product/intents")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        result = self.approve(repo, self.spec_head(repo))
        self.assertEqual((result["outcome"], codes(result)), ("eligible", []))

    def test_an_intent_that_lists_the_spec_binds_it_whatever_its_parent_says(self):
        cases = {
            # name: (the Intent main holds, how its commit reads, the Spec's parent, the reasons, a word of the detail)
            "a draft lists it, the Spec names no parent": (intent(approved=False), True, None, ["intent_not_approved"], "no commit on main"),
            "an approved Intent lists it, the Spec names no parent": (None, True, None, [], ""),
            "an approved Intent lists other slices only": (intent(specs=("SPEC-999",)), True, "INTENT-1", ["intent_not_approved"], "add the slice line"),
            "the person cancelled it": (intent(top="status: cancelled"), True, "INTENT-1", ["intent_not_approved"], "reopen it or to drop SPEC-220"),
            "the person marked it done": (intent(top="status: done"), True, "INTENT-1", ["intent_not_approved"], "reopen it or to drop SPEC-220"),
            "the person recorded a no-go": (
                intent(top="go_no_go: {decision: no_go, by: '@maya', decided_on: \"2027-01-02\"}"),
                True,
                "INTENT-1",
                ["intent_not_approved"],
                "reopen it or to drop SPEC-220",
            ),
            "an Intent the Spec borrows, which the tip holds approved without listing it": (
                intent(specs=("SPEC-999",)),
                True,
                "INTENT-1",
                ["intent_not_approved"],
                "lists no slice",
            ),
        }
        for name, (text, trailer, parent, expected, word) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved(text, message=(YES,) if trailer else ())
                result = self.approve(repo, self.spec_head(repo, parent))
                self.assertEqual(codes(result), expected)
                if word:
                    self.assertIn(word, result["reasons"][0]["detail"])

    def test_a_branch_behind_the_approval_cannot_carry_its_own_version_of_the_intent(self):
        """main holds a draft; the person approves on main; the branch forked before that and rewrote or deleted the draft. Against
        the merge base the Intent was a draft, so only the tip's approval shows the branch holds something else."""
        for name, rewrite, word in (("rewrote the outcome", intent(OTHER, approved=False), "outcome"), ("deleted it", None, "is gone from the head")):
            with self.subTest(name):
                self.fresh()
                repo = self.approved(intent(approved=False))
                git(self.root, "checkout", "-q", "main")
                repo.write(INTENT, intent())
                repo.commit("Approve INTENT-1", "-m", YES)
                git(self.root, "checkout", "-q", "-B", "feature", "HEAD~1")
                if rewrite is None:
                    git(self.root, "rm", "-q", INTENT)
                else:
                    repo.write(INTENT, rewrite)
                repo.commit("The branch's own version of the draft")
                result = self.approve(repo, self.spec_head(repo))
                self.assertEqual(codes(result), ["intent_approval_changed"])
                self.assertIn(word, result["reasons"][0]["detail"])
                self.assertIn("update the branch from main", result["reasons"][0]["detail"], "the step that ends the stop")

    def test_an_intent_only_the_head_adds_binds_the_spec_it_lists(self):
        """The branch writes a new draft Intent and its first Spec together, and the Spec names no parent: the tip holds no such Intent,
        so the Spec's slice belongs to an approval no person made."""
        repo = self.repo()
        head = self.spec_head(repo, None, {f"{INTENTS}/INTENT-5.md": intent(approved=False, ident="INTENT-5")})
        result = self.approve(repo, head)
        self.assertEqual((codes(result), result["reserved"]), (["intent_not_approved"], True))
        self.assertIn("INTENT-5 is no Intent the tip of main holds", result["reasons"][0]["detail"])

    def test_a_slice_a_person_recorded_as_merged_in_another_repository_leaves_the_intent_approved(self):
        """A person's commit on main records `merged_in` for a slice delivered elsewhere: the commit lies in no repository of ours, and
        what a person's merge put on the tip is not held to the tip. Every later Spec approval under the Intent stays eligible."""
        for name, repo_part in (("another repository", ", repo: acme/other"), ("this repository, an id no check can find", "")):
            with self.subTest(name):
                self.fresh()
                two = intent(specs=("SPEC-220", "SPEC-221")).replace("title: Slice SPEC-221", "title: Slice SPEC-221" + repo_part)
                repo = self.approved(two)
                git(self.root, "checkout", "-q", "main")
                repo.write(INTENT, two.replace("title: Slice SPEC-221" + repo_part, "title: Slice SPEC-221" + repo_part + ', merged_in: "' + "c" * 40 + '"'))
                repo.commit("A person records SPEC-221 as merged")
                git(self.root, "checkout", "-q", "-B", "feature", "main")
                result = self.approve(repo, self.spec_head(repo))
                self.assertEqual((result["outcome"], codes(result)), ("eligible", []))

    def test_a_delegate_s_trailer_is_no_person_s_approval(self):
        message = (YES, "Decided-by: agent:claude-code/aidd-team:delegate", f"On-behalf-of: {PERSON}")
        repo = self.approved(message=message)
        self.assertEqual(codes(self.approve(repo, self.spec_head(repo))), ["intent_not_approved"])

    def test_an_approved_intent_edited_on_the_tip_without_a_new_approval_is_no_longer_approved(self):
        repo = self.approved()
        git(self.root, "checkout", "-q", "main")
        repo.write(INTENT, intent(OTHER))
        repo.commit("Edit the goal on main, with no new approval")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        result = self.approve(repo, self.spec_head(repo))
        self.assertEqual(codes(result), ["intent_not_approved"])
        self.assertIn("outcome", result["reasons"][0]["detail"])

    def test_an_approval_only_the_change_holds_is_not_the_tips(self):
        """The change approves the Intent itself, in a commit with the person's two lines: the tip does not hold it, so the approval
        waits, and the change's own approval is a deferral too."""
        repo = self.approved(intent(approved=False))
        repo.write(INTENT, intent())
        repo.commit("Approve INTENT-1", "-m", YES)
        self.assertEqual(sorted(codes(self.approve(repo, self.spec_head(repo)))), ["intent_approval_changed", "intent_not_approved"])

    def test_the_change_that_edits_the_approved_intent_defers_though_the_tip_holds_it_approved(self):
        repo = self.approved()
        found = codes(self.approve(repo, self.spec_head(repo, edits={INTENT: intent(OTHER)})))
        self.assertEqual(found, ["intent_approval_changed"])

    def test_a_parent_only_the_head_names_is_held_to_the_tip_as_well(self):
        """The tip's Spec names an Intent that is a draft; the head's Spec names an approved one: both must stand approved."""
        repo = self.approved(intent(approved=False))
        git(self.root, "checkout", "-q", "main")
        self.commit_approval(repo, intent(ident="INTENT-2"), message=(f"{APPROVED_BY}\nApproves: INTENT-2",), path=f"{INTENTS}/INTENT-2.md")
        repo.write("specs/SPEC-220.md", spec_text("INTENT-1"))
        repo.commit("The tip's SPEC-220 names the draft")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        found = self.approve(repo, self.spec_head(repo, "INTENT-2"))
        self.assertEqual(codes(found), ["intent_not_approved"])
        self.assertIn("INTENT-1", found["reasons"][0]["detail"])

    def test_the_check_names_the_intent_and_what_to_do(self):
        repo = self.approved(intent(approved=False))
        result = self.approve(repo, self.spec_head(repo))
        self.assertEqual(result["outcome"], "defer")
        self.assertIn("no commit on main with an Approved-by line of", result["reasons"][0]["detail"])
        self.assertEqual(result["next"]["what"], policy.reasons()["intent_not_approved"]["next"]["what"])


if __name__ == "__main__":
    unittest.main()
