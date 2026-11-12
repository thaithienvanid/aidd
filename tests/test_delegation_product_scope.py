"""A delegated push, merge, or Spec approval through `aidd delegate check`: the files of the product scope and what an Intent's
approval covers defer, whatever approval the change writes itself, and the honest work beside them still passes. The checks
themselves are in test_delegation_approvals."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from helpers import git
from test_delegation_approvals import APPROVED_BY, INTENT, INTENTS, OTHER, PERSON, SHA, YES, ApprovalCase, intent
from test_delegation_check import FakeGitHub, Repo, codes, note
from test_delegation_spec import SpecCase

from aidd import risk
from aidd.delegation import diff_signals, policy


# A BRD that records a result against an objective: a person's measurement, never a delegate's to land.
BRD_WITH_A_RESULT = (
    "---\ntype: brd\nobjectives:\n"
    "  - id: Objective-1\n    title: Recover failed payments\n"
    "    metric: {name: Recovered in 7 days, source: provider report, baseline: 25%, target: 60%}\n"
    "    results:\n      - {on: 2027-01-11, actual: 45%, source: provider report, decision: continue}\n---\n\n## Why this product\n"
)


def merged_line(sha: str) -> str:
    """A slice line's `merged_in`, quoted as a merge writes it, since a hex id may read as a number."""
    return f', merged_in: "{sha}"'


class ThroughTheCheckTests(ApprovalCase):
    def folded(self, repo: Repo, edits: dict[str, str], *trailers: str) -> str:
        """The change that writes `edits` in one commit, whose message carries the `trailers`, then the note on it: the head."""
        for path, text in edits.items():
            repo.write(path, text)
        code = repo.commit("The change", *(arg for line in trailers for arg in ("-m", line)))
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def push(self, repo: Repo, path: str, text: str) -> list[str]:
        """The reasons of a delegated push of the change that writes `text` to `path`, from the default branch's tip."""
        return self.push_head(repo, repo.change(path, text))

    def push_head(self, repo: Repo, head: str) -> list[str]:
        """The reasons of a delegated push of the commit `head`, from the default branch's tip."""
        tip = git(self.root, "rev-parse", "main")
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        pull = {"base": "main", "head_sha": head, "state": "open"}
        return codes(repo.check(head, f"git push origin {head}:refs/heads/feature", action="git.push", github=FakeGitHub(tip, open_pull_for=pull)))

    def test_a_push_defers_on_what_an_approval_covers_and_on_a_file_of_the_product_scope(self):
        cases = {
            "the goal edited": (INTENT, intent(OTHER), ["intent_approval_changed"]),
            "the approval rewritten": (INTENT, intent(at="2026-11-12T09:12:00Z"), ["intent_approval_changed"]),
            "a slice start": (INTENT, intent(planned_spec_extra=f", drafted_in: {SHA}"), []),
            "an ordinary file": ("src/app.py", "print('hi')\n", []),
            "the PRD": ("product/prd.md", "# A\n", ["reserved_path"]),
            "the order of the Intents": ("product/intents/order.md", "# A\n", ["reserved_path"]),
            "a result added to the BRD": ("product/brd.md", BRD_WITH_A_RESULT, ["reserved_path"]),
            "a nested product folder": ("packages/web/product/brd.md", "# A\n", ["reserved_path"]),
            "an Intent file in the product folder": ("product/intents/INTENT-5.md", "# A\n", []),
        }
        for name, (path, text, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved()
                self.assertEqual(self.push(repo, path, text), expected)

    def test_an_approval_the_change_writes_itself_lifts_no_defer(self):
        """The branch's own commit may carry `Approved-by:` and `Approves:` lines, and its files their own `approved_by`,
        `approved_at`, and `approval`: a line is text and a file says what its author wrote. Only the default branch's tip, where a
        person's merge put it, holds an approval, so each row defers as it did with none."""
        who = f"{APPROVED_BY}\nApproves: product/prd.md"
        approved = f'---\ntype: prd\napproved_by: "{PERSON}"\napproved_at: "2026-11-13T09:00:00Z"\n---\n\n## Users\n'
        cases = {
            # name: (the files the one commit writes, its trailers, the reasons)
            "the PRD, with its two lines": ({"product/prd.md": "# A\n"}, (who,), ["reserved_path"]),
            "the PRD, approved in its own front matter and by its two lines in the same commit": ({"product/prd.md": approved}, (who,), ["reserved_path"]),
            "the PRD, approved in its own front matter alone": ({"product/prd.md": approved}, (), ["reserved_path"]),
            "the BRD, with a delegate's trailers beside it": (
                {"product/brd.md": approved},
                (who, "Decided-by: agent:claude-code/aidd-team:delegate", f"On-behalf-of: {PERSON}"),
                ["reserved_path"],
            ),
            "the order of the Intents, with its two lines": ({"product/intents/order.md": approved}, (who,), ["reserved_path"]),
            "an approved Intent's goal and approval time rewritten in a commit with the approval's two lines": (
                {INTENT: intent(OTHER, at="2026-11-12T09:12:00Z")},
                (YES,),
                ["intent_approval_changed"],
            ),
            "a new Intent approved in a commit with the approval's two lines": (
                {f"{INTENTS}/INTENT-2.md": intent(ident="INTENT-2")},
                (f"{APPROVED_BY}\nApproves: INTENT-2",),
                ["intent_approval_changed"],
            ),
            "an ordinary change with its two lines": ({"src/app.py": "print('hi')\n"}, (who,), []),
        }
        for name, (edits, trailers, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved()
                self.assertEqual(self.push_head(repo, self.folded(repo, edits, *trailers)), expected)
        self.fresh()
        repo = self.approved()
        result = repo.check(self.folded(repo, {"product/prd.md": approved}, who))
        self.assertEqual((result["outcome"], codes(result)), ("defer", ["reserved_path"]), "a local merge reads the same")

    def after_the_approval(self, text: str | Callable[[str], str] | None = None) -> tuple[Repo, str, str, str]:
        """main holds the setup commit, the person's approval, and one commit after it; feature starts there. Returns the repository
        and the three commits, oldest first, the second being the commit that changes only the `approval`."""
        self.fresh()
        repo = self.repo()
        first = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-q", "main")
        approved = self.commit_approval(repo, text(first) if callable(text) else text or intent())
        repo.write("src/later.py", "x = 1\n")
        later = repo.commit("A later commit on main")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        return repo, first, approved, later

    def test_a_merged_in_is_kept_only_for_a_commit_of_the_default_branch_after_the_approval(self):
        """A merge writes `merged_in`, which makes a slice done. A first one passes for a commit of the tip after the approval. An id
        that names no commit, a short id, a commit only the branch holds, an old commit, the approval's own commit, and a change or a
        removal of one the approved version holds defer."""
        repo, first, approved, later = self.after_the_approval()
        self.assertEqual(self.push(repo, INTENT, intent(planned_spec_extra=merged_line(later))), [], "a commit after the approval")
        cases = {  # each names a commit of the repository the row makes, by the position in (first, approved, later)
            "an id that names no commit": lambda commits: "c" * 40,
            "a short id": lambda commits: commits[2][:12],
            "an old commit, the first of the repository": lambda commits: commits[0],
            "the approval's own commit": lambda commits: commits[1],
        }
        for name, pick in cases.items():
            with self.subTest(name):
                repo, *commits = self.after_the_approval()
                self.assertEqual(self.push(repo, INTENT, intent(planned_spec_extra=merged_line(pick(commits)))), ["intent_approval_changed"])
        with self.subTest("a commit only the branch holds"):
            repo, *_ = self.after_the_approval()
            repo.write("src/branch.py", "x = 1\n")
            only = repo.commit("only on the branch")
            self.assertEqual(self.push(repo, INTENT, intent(planned_spec_extra=merged_line(only))), ["intent_approval_changed"])
        for name, after in (("a change", intent(planned_spec_extra=merged_line("d" * 40))), ("a removal", intent())):
            with self.subTest(name):
                repo, *_ = self.after_the_approval(lambda first: intent(planned_spec_extra=merged_line(first)))
                self.assertEqual(self.push(repo, INTENT, after), ["intent_approval_changed"])

    def test_a_slice_delivered_in_another_repository_keeps_its_merged_in_unchecked(self):
        """The commit lies in a repository aidd reads none of, so the tip cannot hold it: a push and a merge pass, where the same id
        on a slice of this repository defers."""
        elsewhere = intent(planned_spec_extra=", repo: acme/other")
        repo, *_ = self.after_the_approval(elsewhere)
        self.assertEqual(self.push(repo, INTENT, intent(planned_spec_extra=", repo: acme/other" + merged_line("c" * 40))), [], "a push")
        repo, *_ = self.after_the_approval(elsewhere)
        result = repo.check(repo.change(INTENT, intent(planned_spec_extra=", repo: acme/other" + merged_line("c" * 40))))
        self.assertEqual((result["outcome"], codes(result)), ("eligible", []), "a merge")
        repo, *_ = self.after_the_approval()
        self.assertEqual(self.push(repo, INTENT, intent(planned_spec_extra=merged_line("c" * 40))), ["intent_approval_changed"], "the same id, this repository")

    def test_a_local_merge_defers_the_same_way_and_the_check_says_what_and_what_next(self):
        repo = self.approved()
        result = repo.check(repo.change(INTENT, intent(OTHER, specs=("SPEC-220", "SPEC-221"))))
        self.assertEqual((result["outcome"], result["reserved"], codes(result)), ("defer", True, ["intent_approval_changed"]))
        self.assertIn(f"{INTENT} (INTENT-1): outcome, specs changed", result["reasons"][0]["detail"])
        self.assertEqual(result["next"]["what"], policy.reasons()["intent_approval_changed"]["next"]["what"])

    def test_a_local_merge_of_a_slice_start_is_as_eligible_as_before(self):
        repo = self.approved(intent(planned_spec_extra=", blocked_by: [SPEC-1]"))
        result = repo.check(repo.change(INTENT, intent()))
        self.assertEqual((result["outcome"], codes(result)), ("eligible", []))

    def test_a_product_dir_the_config_names_is_held_too(self):
        cases = {
            # name: (the config's top-level lines, the path, the reasons)
            "the named folder": ("product_dir: plans\n", "plans/prd.md", ["reserved_path"]),
            "an Intent in the named folder": ("product_dir: plans\n", "plans/intents/INTENT-1.md", []),
            "the default folder stays held": ("product_dir: plans\n", "product/prd.md", ["reserved_path"]),
        }
        for name, (top, path, expected) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo = self.approved(top=top)
                self.assertEqual(self.push(repo, path, "# A\n"), expected)


class ATaskScopeTests(SpecCase):
    def test_a_scope_that_names_a_file_of_the_product_scope_defers_the_approval(self):
        repo, head = self.spec_repo('["src/checkout/", "product/intents/order.md"]')
        result = self.approve(repo, head)
        self.assertEqual((codes(result), result["reserved"]), (["reserved_path"], True))
        self.assertIn("product/intents/order.md (product_scope)", result["reasons"][0]["detail"])

    def test_which_scopes_reach_the_product_scope_before_any_file_changes(self):
        """A folder holds files its scope may never touch, so a scope naming only the folder waits for the diff, where a change to
        one of the files is a reserved path (as for a CODEOWNERS file under `docs/`)."""
        rs = risk.rule_set(None)
        cases = {
            "product/prd.md": True,
            "product/intents/order.md": True,
            "**/product/brd.md": True,
            "product/": False,
            "product/intents/INTENT-1.md": False,
            "src/": False,
        }
        for scope, reaches in cases.items():
            with self.subTest(scope):
                self.assertEqual(bool(diff_signals.reserved_scopes(rs, [scope])), reaches)


if __name__ == "__main__":
    unittest.main()
