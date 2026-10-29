"""Merge trains on GitLab: a car's commit is judged by the approvals on the merge request head, its own tests, and a
tree that must be exactly that head merged onto the commit the car was built on. A real git repository with a train
ref, and a fake GitLab API. The counterpart of test_merge_queue.py for GitHub; not yet run against a real instance."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, FakeTransport, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd.cli.commands import author
from aidd.kernel import http
from aidd.platforms import gitlab, merge_results

API = "https://gitlab.test/api/v4"
CONFIG = """aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@lead"]

tests:
  - name: unit
    command: ["{py}", -c, print('ok')]
"""
BODY = """Fix a typo.

```yaml aidd
route: minor
type: docs
confidence: high
scope: [docs/guide.md]
rollback: Revert the MR.
assisted_by: []

risk:
  summary: Fixes a typo.
  dimensions: []
  reversible: true
```
"""


def _commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@unittest.skipUnless(shutil.which("git"), "git is required")
class MergeTrainTests(unittest.TestCase):
    def setUp(self):
        helpers.enforce_by_default(self)  # these test enforce exit codes
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.origin, self.work = t / "origin.git", t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(t, "init", "-q", "-b", "main", str(self.work))
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.work, "config", k, v)
        self.py = sys.executable.replace("\\", "/")
        (self.work / ".aidd").mkdir()
        (self.work / ".aidd/config.yaml").write_text(CONFIG.format(py=self.py), encoding="utf-8")
        (self.work / "docs").mkdir()
        (self.work / "docs/guide.md").write_text("Teh guide.\n", encoding="utf-8")
        (self.work / "README.md").write_text("readme\n", encoding="utf-8")
        self.base = _commit(self.work, "base")
        git(self.work, "remote", "add", "origin", str(self.origin))
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "checkout", "-qb", "fix")
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        self.head = _commit(self.work, "Fix typo")
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/merge-requests/1/head")
        git(self.work, "checkout", "-q", "main")
        self.evidence = t / "evidence.json"

    def tearDown(self):
        self.tmp.cleanup()

    def car(self, extra: str | None = None, onto: str | None = None, squash: bool = False) -> str:
        """Build a car the way GitLab does: the approved head merged onto `onto` (default: the target tip), or, with
        `squash`, its change as one commit on it (a fast-forward train). Push it as the train ref."""
        git(self.work, "checkout", "-q", "--detach", onto or self.base)
        if squash:
            git(self.work, "merge", "-q", "--squash", self.head)
            git(self.work, "commit", "-qm", "Fix typo (squashed)")
        else:
            git(self.work, "merge", "-q", "--no-ff", "-m", "Merge branch 'fix' into 'main'", self.head)
        if extra:
            (self.work / extra).write_text("not approved\n", encoding="utf-8")
            git(self.work, "add", "-A")
            git(self.work, "commit", "-q", "--amend", "--no-edit")
        sha = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", "-f", "origin", f"{sha}:refs/merge-requests/1/train")
        git(self.work, "checkout", "-q", "main")
        return sha

    def ahead(self) -> str:
        """A car ahead in the train: another merge request's change merged onto the target tip."""
        git(self.work, "checkout", "-q", "--detach", self.base)
        (self.work / "README.md").write_text("readme, by merge request !2\n", encoding="utf-8")
        sha = _commit(self.work, "Merge branch 'other' into 'main'")
        git(self.work, "push", "-q", "origin", f"{sha}:refs/merge-requests/2/train")
        git(self.work, "checkout", "-q", "main")
        return sha

    def write_evidence(self, head: str, base: str) -> None:
        result = {"name": "unit", "source": "config", "command": [self.py, "-c", "print('ok')"], "red_green": "green", "exit": 0, "status": "passed"}
        self.evidence.write_text(json.dumps({"aidd_version": "1.0.0", "head_sha": head, "base_sha": base, "results": [result]}), encoding="utf-8")

    def transport(self, approved_at="2026-09-25T10:05:00Z", versions=None, approver="lead", members=None, bots=()):
        versions = [{"head_commit_sha": self.head, "created_at": "2026-09-25T09:50:00Z"}] if versions is None else versions
        ids = {"lead": 1, "release-automation": 4, "group_42_bot_ab12": 5}
        return FakeTransport(
            {
                f"{API}/groups/acme%2Fleads/members/all": ({}, members or []),
                **{f"{API}/users/{ids[name]}": ({}, {"id": ids[name], "bot": True}) for name in bots},
                f"{API}/users/": ({}, {"bot": False}),  # GET /users/:id: anyone else is a person
                f"{API}/projects/7/merge_requests/1/commits": (
                    {},
                    [{"id": self.head, "author_email": "alice@example.com", "committer_email": "alice@example.com", "message": "Fix typo"}],
                ),
                f"{API}/projects/7/merge_requests/1/notes": (
                    {},
                    [{"system": True, "body": "approved this merge request", "author": {"id": ids[approver], "username": approver}, "created_at": approved_at}],
                ),
                f"{API}/projects/7/merge_requests/1/versions": ({}, versions),
                f"{API}/projects/7/merge_requests/1": (
                    {},
                    {"sha": self.head, "target_branch": "main", "description": BODY, "author": {"username": "alice"}, "created_at": "2026-09-25T09:00:00Z"},
                ),
                f"{API}/projects/7/approvals": ({}, {"merge_requests_disable_committers_approval": True, "merge_requests_author_approval": False}),
                f"{API}/projects/7/statuses/": ({}, {}),
            }
        )

    def run_gate(self, transport, car: str, checkout: str | None = None, **env):
        base_env = {
            "CI_MERGE_REQUEST_IID": "1",
            "CI_PROJECT_ID": "7",
            "CI_API_V4_URL": API,
            "AIDD_GITLAB_TOKEN": "t",
            # A train pipeline starts when the car joins the train, after the approval.
            "CI_PIPELINE_CREATED_AT": "2026-09-25T11:00:00Z",
            "CI_MERGE_REQUEST_EVENT_TYPE": "merge_train",
            "CI_COMMIT_SHA": car,
            "CI_MERGE_REQUEST_SOURCE_BRANCH_SHA": self.head,
            "CI_PROJECT_PATH": "acme/app",
            "AIDD_MODE": "",
            "AIDD_ORG_PRESET": "",
        }
        record = Path(self.tmp.name) / "record.json"
        record.unlink(missing_ok=True)
        git(self.work, "checkout", "-q", "--detach", checkout or car)  # the train pipeline's own checkout of the car
        self.printed = io.StringIO()
        with mock.patch.dict(os.environ, {**base_env, **env}), mock.patch.object(http, "request", transport), contextlib.redirect_stdout(self.printed):
            code = gitlab.gitlab_gate(cwd=str(self.work), evidence_path=str(self.evidence), record_out=str(record), post=True)
        return code, json.loads(record.read_text(encoding="utf-8")) if record.exists() else None

    @staticmethod
    def posts(t):
        return [(c[1].split("/statuses/", 1)[1].split("?", 1)[0], "state=success" in c[1]) for c in t.calls if c[0] == "POST"]

    def test_a_car_that_is_exactly_the_approved_head_passes_on_its_own_commit(self):
        car = self.car()
        self.write_evidence(car, self.base)
        t = self.transport()
        code, record = self.run_gate(t, car)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)
        # Approvals bind to the merge request head; the status goes on the car's commit.
        self.assertEqual((record["head_sha"], record["merge_queue_sha"]), (self.head, car))
        self.assertEqual(self.posts(t), [(car, True)])
        self.assertIn(f"merge train entry {car[:12]}", self.printed.getvalue())

    def test_a_fast_forward_car_with_the_same_tree_passes(self):
        car = self.car(squash=True)
        self.assertEqual(merge_results.train_parent(str(self.work), car, self.head, self.base), (self.base, False))
        self.write_evidence(car, self.base)
        code, record = self.run_gate(self.transport(), car)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)

    def test_a_car_holding_an_unapproved_change_fails(self):
        car = self.car(extra="smuggled.txt")
        self.write_evidence(car, self.base)
        t = self.transport()
        code, record = self.run_gate(t, car)
        self.assertEqual((code, record["decision"]), (1, "fail"))
        self.assertIn({"rule": "merge_queue", "level": "fail", "code": "merge_queue.diff_mismatch"}, record["findings"])
        self.assertEqual(self.posts(t), [(car, False)])

    def test_a_head_that_conflicts_with_the_cars_parent_fails(self):
        # A car whose tree no merge of the head gives, onto a target the head conflicts with.
        git(self.work, "checkout", "-q", "main")
        (self.work / "docs/guide.md").write_text("A different guide.\n", encoding="utf-8")
        moved = _commit(self.work, "Edit the guide on main")
        git(self.work, "push", "-q", "origin", "main")
        self.assertIsNone(merge_results.merged_tree(str(self.work), moved, self.head))
        git(self.work, "checkout", "-q", "--detach", moved)
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        car = _commit(self.work, "A car GitLab could not have built")
        git(self.work, "push", "-q", "-f", "origin", f"{car}:refs/merge-requests/1/train")
        git(self.work, "checkout", "-q", "main")
        self.write_evidence(car, moved)
        _, record = self.run_gate(self.transport(), car)
        self.assertEqual(record["decision"], "fail")
        self.assertIn("merge_queue.conflict", [f["code"] for f in record["findings"]])

    def test_evidence_from_the_merge_request_head_does_not_count_in_the_train(self):
        car = self.car()
        self.write_evidence(self.head, self.base)  # tests on the head never prove the car's commit
        _, record = self.run_gate(self.transport(), car)
        self.assertEqual(record["decision"], "pending")
        self.assertIn("tests.evidence_other_head", [f["code"] for f in record["findings"]])

    def test_a_car_built_on_the_car_ahead_passes_with_its_evidence_against_that_car(self):
        ahead = self.ahead()
        car = self.car(onto=ahead)
        self.assertEqual(merge_results.train_parent(str(self.work), car, self.head, self.base), (ahead, True))
        self.write_evidence(car, ahead)
        code, record = self.run_gate(self.transport(), car)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)
        self.write_evidence(car, self.base)  # red against the target alone is not the car's base
        _, record = self.run_gate(self.transport(), car)
        self.assertIn("tests.evidence_other_base", [f["code"] for f in record["findings"]])

    def test_an_approval_of_the_head_before_the_train_binds_one_before_the_head_does_not(self):
        car = self.car()
        self.write_evidence(car, self.base)
        _, record = self.run_gate(self.transport(approved_at="2026-09-25T09:55:00Z"), car)
        self.assertEqual(record["decision"], "pass", record)  # after the head's diff version, before the train pipeline
        code, record = self.run_gate(self.transport(approved_at="2026-09-25T09:40:00Z"), car)
        self.assertEqual((code, record["decision"]), (1, "pending"))  # before the merge request had this head
        code, record = self.run_gate(self.transport(versions=[]), car)
        self.assertEqual((code, record["decision"]), (1, "pending"))  # no diff version names the head: nothing binds

    def test_a_head_pushed_again_binds_only_approvals_after_its_last_push(self):
        # The head, another head approved at 10:05, then the head again: that approval was of the other head.
        car = self.car()
        self.write_evidence(car, self.base)
        versions = [
            {"head_commit_sha": self.head, "created_at": "2026-09-25T09:50:00Z"},
            {"head_commit_sha": "e" * 40, "created_at": "2026-09-25T10:00:00Z"},
            {"head_commit_sha": self.head, "created_at": "2026-09-25T10:10:00Z"},
        ]
        code, record = self.run_gate(self.transport(versions=versions), car)
        self.assertEqual((code, record["decision"]), (1, "pending"))
        self.assertEqual(gitlab._pushed_at(versions, self.head), "2026-09-25T10:10:00Z")
        self.assertIsNone(gitlab._pushed_at(versions[:2], self.head))  # the newest version names another head
        # A version without a time could be the newest: their order is unknown, so no approval binds.
        for undated in ({"head_commit_sha": "e" * 40}, {"head_commit_sha": "e" * 40, "created_at": "yesterday"}):
            with self.subTest(undated=undated):
                self.assertIsNone(gitlab._pushed_at([versions[0], undated], self.head))
                code, record = self.run_gate(self.transport(versions=[versions[0], undated]), car)
                self.assertEqual((code, record["decision"]), (1, "pending"))

    def test_a_train_ref_that_moved_fails_closed(self):
        car = self.car()
        self.write_evidence(car, self.base)
        self.car(extra="rebuilt.txt")  # GitLab rebuilt the train since this pipeline started
        t = self.transport()
        with self.assertRaisesRegex(RuntimeError, "rebuilt the train"):
            self.run_gate(t, car)
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_a_checkout_other_than_the_car_fails_closed(self):
        car = self.car()
        self.write_evidence(car, self.base)
        t = self.transport()
        self.assertEqual(self.run_gate(t, car, checkout=self.head), (1, None))
        self.assertIn(f"the checkout is {self.head[:12]}, not the train's commit {car[:12]}", self.printed.getvalue())
        self.assertEqual(t.calls, [])

    def test_a_group_service_account_never_approves_for_the_group(self):
        # The pool names a group; its members include a service account and a group access token's bot, which GitLab's
        # members API does not mark. GET /users/:id says they are bots, so neither is in the pool, and the approval of
        # either is recorded as `<name>[bot]`, which never counts.
        members = [{"id": 1, "username": "lead"}, {"id": 4, "username": "release-automation"}, {"id": 5, "username": "group_42_bot_ab12"}]
        self.base = self.rewrite_config(CONFIG.replace('approvers: ["@lead"]', 'approvers: ["@acme/leads"]'))
        car = self.car()
        self.write_evidence(car, self.base)
        bots = ["release-automation", "group_42_bot_ab12"]
        for approver in bots:
            with self.subTest(approver=approver):
                code, record = self.run_gate(self.transport(approver=approver, members=members, bots=bots), car)
                self.assertEqual((code, record["decision"]), (1, "pending"), record)
                self.assertIn("merge_approval.agent_approval", [f["code"] for f in record["findings"]])
                self.assertIn("leave out members GitLab did not say are people", self.printed.getvalue())
        code, record = self.run_gate(self.transport(approver="lead", members=members, bots=bots), car)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)

    def test_a_stacked_car_names_the_same_parent_before_and_after_the_car_ahead_merges(self):
        # The car ahead is another merge request's head merged onto the target; this car is built on it. Its MR head is
        # on the car's ancestry too, and its merge with this head gives the same tree, but it is never the parent.
        git(self.work, "checkout", "-q", "--detach", self.base)
        (self.work / "README.md").write_text("readme, by merge request !2\n", encoding="utf-8")
        other_head = _commit(self.work, "Change the readme")
        git(self.work, "checkout", "-q", "--detach", self.base)
        git(self.work, "merge", "-q", "--no-ff", "-m", "Merge branch 'other' into 'main'", other_head)
        ahead = git(self.work, "rev-parse", "HEAD")
        git(self.work, "checkout", "-q", "main")
        car = self.car(onto=ahead)
        before = merge_results.train_parent(str(self.work), car, self.head, self.base)
        after = merge_results.train_parent(str(self.work), car, self.head, ahead)  # the car ahead merged: the target is it
        self.assertEqual((before[0], after[0]), (ahead, ahead))
        self.assertEqual((before[1], after[1]), (True, False))

    def test_a_rebased_copy_of_the_merge_requests_own_commit_is_never_the_parent(self):
        # A fast-forward train rebases the merge request's commits onto the target. The first rebased copy merged with
        # the head gives the car's tree too, but the car was built on the target.
        git(self.work, "checkout", "-q", "fix")
        (self.work / "docs/more.md").write_text("More.\n", encoding="utf-8")
        self.head = _commit(self.work, "Add more")
        git(self.work, "push", "-q", "-f", "origin", f"{self.head}:refs/merge-requests/1/head")
        git(self.work, "checkout", "-q", "main")
        (self.work / "README.md").write_text("readme, moved on\n", encoding="utf-8")
        self.base = _commit(self.work, "Move the target on")
        git(self.work, "checkout", "-q", "--detach", self.base)
        git(self.work, "cherry-pick", f"{self.head}~1", self.head)
        car = git(self.work, "rev-parse", "HEAD")
        git(self.work, "checkout", "-q", "main")
        self.assertEqual(merge_results.train_parent(str(self.work), car, self.head, self.base), (self.base, False))

    def rewrite_config(self, text: str) -> str:
        """Commit `text` as the base branch's config, the one the gate reads; the new tip of main."""
        git(self.work, "checkout", "-q", "main")
        (self.work / ".aidd/config.yaml").write_text(text.format(py=self.py), encoding="utf-8")
        tip = _commit(self.work, "config: a group pool")
        git(self.work, "push", "-q", "origin", "main")
        return tip

    def test_a_train_pipeline_without_its_commits_fails_closed(self):
        car = self.car()
        t = self.transport()
        self.assertEqual(self.run_gate(t, car, CI_MERGE_REQUEST_SOURCE_BRANCH_SHA=""), (1, None))
        self.assertIn("Remove the MR from the train and add it again", self.printed.getvalue())
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_aidd_test_computes_the_cars_base_as_the_gate_does(self):
        ahead = self.ahead()
        car = self.car(onto=ahead)
        git(self.work, "fetch", "-q", "origin", "main")
        git(self.work, "checkout", "-q", "--detach", car)
        env = {
            "CI_MERGE_REQUEST_EVENT_TYPE": "merge_train",
            "CI_COMMIT_SHA": car,
            "CI_MERGE_REQUEST_SOURCE_BRANCH_SHA": self.head,
            "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "main",
            "CI_MERGE_REQUEST_IID": "1",
        }
        with mock.patch.dict(os.environ, env), contextlib.chdir(self.work), contextlib.redirect_stdout(io.StringIO()):
            # One flag, --merge-queue, reads whichever CI it runs in: here GitLab's merge train pipeline.
            self.assertEqual(author._merge_queue_base(None), ahead)
            with mock.patch.dict(os.environ, {"CI_COMMIT_SHA": self.head}), self.assertRaisesRegex(ValueError, "not the train's commit"):
                author._merge_queue_base(None)
            with mock.patch.dict(os.environ, {"CI_MERGE_REQUEST_EVENT_TYPE": "merged_result"}), self.assertRaisesRegex(ValueError, "merge train pipeline"):
                author._merge_queue_base(None)
        bare = {k: v for k, v in os.environ.items() if k not in ("CI_MERGE_REQUEST_EVENT_TYPE", "GITHUB_EVENT_PATH")}
        with mock.patch.dict(os.environ, bare, clear=True), self.assertRaisesRegex(ValueError, "GitHub merge_group run, or a GitLab merge train"):
            author._merge_queue_base(None)


if __name__ == "__main__":
    unittest.main()
