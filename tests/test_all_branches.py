"""`aidd status --all-branches`: the open work in every worktree and every local and fetched branch, read through the
index in the clone's git folder. The index reads a place again exactly when the place changed, and answers as reading
every place directly does."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, src_pythonpath

from aidd import workitems
from aidd.kernel import index
from aidd.workitems import all_branches


def spec(sid: str, title: str, status: str = "draft") -> str:
    return f'---\ntype: spec\nid: {sid}\ntitle: "{title}"\nstatus: {status}\n---\n# {title}\n'


class IndexTests(unittest.TestCase):
    """The generic index: a place is loaded once, again only when its stamp changes, and dropped when it is gone."""

    def test_a_place_is_read_again_exactly_when_its_stamp_changes(self):
        loads: list[str] = []

        def place(name: str, stamp: str, title: str):
            return stamp, lambda: loads.append(name) or [index.Entry("spec", f"{name}.md", None, None, {"title": title})]

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "index.sqlite"
            first = {"a": place("a", "1", "A"), "b": place("b", "1", "B")}
            self.assertEqual(index.read_through(path, first)["a"][0].data, {"title": "A"})
            self.assertEqual(index.read_through(path, first)["b"][0].data, {"title": "B"})
            self.assertEqual(sorted(loads), ["a", "b"], "a warm index reads no place again")
            changed = {"a": place("a", "2", "A2"), "c": place("c", "1", "C")}
            rows = index.read_through(path, changed)
            self.assertEqual(sorted(loads), ["a", "a", "b", "c"])
            self.assertEqual({name: [e.data["title"] for e in r] for name, r in rows.items()}, {"a": ["A2"], "c": ["C"]})

    def test_a_junk_file_is_rebuilt_and_a_locked_one_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "index.sqlite"
            path.write_bytes(b"not a database" * 100)
            with index.opened(path) as conn:
                self.assertIsNotNone(conn)
            self.assertTrue(path.read_bytes().startswith(b"SQLite format 3"))
            with index.opened(path) as holder:
                assert holder is not None
                holder.execute("BEGIN EXCLUSIVE")
                with mock.patch.object(index, "BUSY_TIMEOUT_SECONDS", 0.05), index.opened(path) as other:
                    self.assertIsNone(other, "a locked index is skipped, so the caller reads the places directly")
                holder.execute("COMMIT")
            self.assertTrue(path.is_file(), "a locked index is never removed")


class AllBranchesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        (self.root / "specs").mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Ada")
        git(self.root, "config", "user.email", "ada@example.com")
        (self.root / "specs" / "SPEC-1.md").write_text(spec("SPEC-1", "Refunds"), encoding="utf-8")
        (self.root / "specs" / "README.md").write_text("---\ntype: spec\n---\nnot a work item\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "SPEC-1")
        git(self.root, "branch", "other")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.feat = self.root.parent / "feat"
        git(self.root, "worktree", "add", "-q", "-b", "feat", str(self.feat))

    def answer(self, cfg=None, **kw) -> dict:
        return all_branches.all_branches_work(self.root, cfg, **kw)

    def summary(self, answer: dict) -> list[tuple]:
        return [(i["id"], i["title"], tuple(i["places"])) for i in answer["items"]]

    def commit_on(self, branch: str, name: str, text: str, *trailer: str) -> None:
        git(self.root, "checkout", "-q", branch)
        (self.root / "specs" / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / "specs" / name).write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", name, *(a for t in trailer for a in ("--trailer", t)))
        git(self.root, "checkout", "-q", "main")

    def test_a_branch_whose_spec_file_is_missing_here_is_named_never_dropped(self):
        """A partial clone leaves blobs out; reading one as empty would drop the Spec from every list without a word."""
        self.commit_on("other", "SPEC-2.md", spec("SPEC-2", "Receipts"))
        sha = git(self.root, "rev-parse", "other:specs/SPEC-2.md")
        for use_index in (False, True):
            with self.subTest(use_index=use_index), mock.patch.object(all_branches.git, "raw_objects", return_value={}):
                answer = self.answer(use_index=use_index)
                self.assertNotIn("SPEC-2", [i["id"] for i in answer["items"]], "the file could not be read")
                [gone, *_] = [u for u in answer["unreadable"] if u["place"] == "branch:other" and u["path"] == "specs/SPEC-2.md"]
                self.assertIn(f"git -C {self.root} cat-file -p {sha}", gone["error"])
                self.assertIn("not in this clone", gone["error"])

    def test_the_command_that_fetches_a_missing_file_is_safe_to_paste_from_a_folder_with_a_space(self):
        spaced = self.root.parent / "my repo"
        spaced.mkdir()
        git(spaced, "init", "-q", "-b", "main")
        git(spaced, "config", "user.name", "Ada")
        git(spaced, "config", "user.email", "ada@example.com")
        (spaced / "specs").mkdir()
        (spaced / "specs" / "SPEC-3.md").write_text(spec("SPEC-3", "Gifts"), encoding="utf-8")
        git(spaced, "add", "-A")
        git(spaced, "commit", "-q", "-m", "SPEC-3")
        with mock.patch.object(all_branches.git, "raw_objects", return_value={}):
            rows = all_branches._branch_rows(str(spaced), git(spaced, "rev-parse", "HEAD"), None)
        [gone] = [r for r in rows if r.type == "unreadable"]
        self.assertIn(f"git -C '{spaced}' cat-file -p ", gone.data["error"])

    def test_a_partial_clone_reads_its_branches_again_so_a_fetched_file_shows_at_once(self):
        git(self.root, "config", "extensions.partialclone", "origin")
        stamps = [all_branches.places(self.root, None)["branch:other"][0] for _ in range(2)]
        self.assertNotEqual(stamps[0], stamps[1], "a partial clone's place is never kept")
        git(self.root, "config", "--unset", "extensions.partialclone")
        again = [all_branches.places(self.root, None)["branch:other"][0] for _ in range(2)]
        self.assertEqual(again[0], again[1], "a whole clone's place is kept until its tip moves")

    def test_each_version_of_a_work_item_names_the_places_that_hold_it(self):
        (self.feat / "specs" / "SPEC-1.md").write_text(spec("SPEC-1", "Refunds in 30 days"), encoding="utf-8")  # not committed
        self.commit_on("other", "SPEC-2.md", spec("SPEC-2", "Receipts"))
        git(self.root, "branch", "origin/x")  # a local branch named like a fetched one stays its own place
        main, feat = f"worktree:{self.root}", f"worktree:{self.feat}"
        self.assertEqual(
            self.summary(self.answer()),
            [
                ("SPEC-1", "Refunds", ("branch:origin/x", "branch:other", "remote:origin/main", main)),
                ("SPEC-1", "Refunds in 30 days", (feat,)),
                ("SPEC-2", "Receipts", ("branch:other",)),
            ],
        )

    def test_the_same_spec_on_a_branch_and_in_the_worktree_is_one_item_held_by_both_places(self):
        """Invariant: the same Spec, on a branch and in the worktree, is one item held by both places, and `--all-branches` shows the
        Intent's planned Specs and the Spec's `blocked_by` from the branch tip. An Intent is a row at the file it is in: the branch
        holds it in `specs/`, the worktree in `product/intents/`, and each place keeps its own row."""
        old_intent = new_intent = (
            "---\ntype: intent\nid: INTENT-1\ntitle: Plan\noutcome: g\nphases: [{id: P1, name: Plan, specs: [{id: SPEC-1, title: Refunds}]}]\n---\n"
        )
        old_spec = new_spec = "---\ntype: spec\nid: SPEC-2\ntitle: Receipts\nstatus: draft\nblocked_by: [SPEC-1]\n---\n"
        self.commit_on("other", "INTENT-1.md", old_intent)
        self.commit_on("other", "SPEC-2.md", old_spec)
        (self.root / "product" / "intents").mkdir(parents=True)
        (self.root / "product" / "intents" / "INTENT-1.md").write_text(new_intent, encoding="utf-8")
        (self.root / "specs" / "SPEC-2.md").write_text(new_spec, encoding="utf-8")
        for use_index in (False, True):
            with self.subTest(use_index=use_index):
                items = self.answer(use_index=use_index)["items"]
                found = {i["id"]: i for i in items}
                intents = [i for i in items if i["id"] == "INTENT-1"]
                self.assertEqual(
                    sorted((i["path"], i["places"]) for i in intents),
                    [("product/intents/INTENT-1.md", [f"worktree:{self.root}"]), ("specs/INTENT-1.md", ["branch:other"])],
                    "each place's Intent shows at the file it is in",
                )
                self.assertEqual([[s["id"] for p in i["phases"] for s in p["specs"]] for i in intents], [["SPEC-1"], ["SPEC-1"]])
                self.assertEqual(found["SPEC-2"]["places"], ["branch:other", f"worktree:{self.root}"])
                self.assertEqual(found["SPEC-2"]["blocked_by"], ["SPEC-1"])
        # Part upgraded: a branch the upgrade has not reached holds an approved Intent in a subfolder of the specs folder, and this
        # worktree still holds another approved one at the old place. Each shows at the file it is in, and each keeps its approval.
        # Each approval is its own commit, which changes only `approval`, with the person's two lines.
        plan = (
            "---\ntype: intent\nid: INTENT-{n}\ntitle: Plan\noutcome: g\n{approval}"
            "phases: [{{id: P1, name: Plan, specs: [{{id: SPEC-{n}0, title: One}}]}}]\n---\n"
        )
        approval = 'approval: {by: "J <j@example.com>", at: "2026-11-10T09:12:00Z"}\n'
        lines = ("Approved-by: J <j@example.com>", "Approves: INTENT-{n}")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "the upgrade, here")
        self.commit_on("other", "old/INTENT-3.md", plan.format(n=3, approval=""))
        self.commit_on("other", "old/INTENT-3.md", plan.format(n=3, approval=approval), *(line.format(n=3) for line in lines))
        (self.root / "specs" / "INTENT-4.md").write_text(plan.format(n=4, approval=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "INTENT-4: plan")
        (self.root / "specs" / "INTENT-4.md").write_text(plan.format(n=4, approval=approval), encoding="utf-8")
        git(self.root, "commit", "-q", "-a", "-m", "INTENT-4: approved", *(a for line in lines for a in ("--trailer", line.format(n=4))))
        for use_index in (False, True):
            with self.subTest("part upgraded", use_index=use_index):
                found = {i["id"]: i for i in self.answer(use_index=use_index)["items"]}
                self.assertEqual((found["INTENT-3"]["path"], found["INTENT-3"]["places"]), ("specs/old/INTENT-3.md", ["branch:other"]))
                self.assertEqual((found["INTENT-4"]["path"], found["INTENT-4"]["places"]), ("specs/INTENT-4.md", [f"worktree:{self.root}"]))
                self.assertEqual([found[i]["next"]["code"] for i in ("INTENT-3", "INTENT-4")], ["intent.slice", "intent.slice"], "their approvals stand")

    def test_the_warm_index_follows_each_kind_of_change_as_a_direct_read_does(self):
        reads = mock.patch.object(all_branches, "_branch_rows", wraps=all_branches._branch_rows)
        changes = {
            "a worktree file rewritten": lambda: (self.feat / "specs" / "SPEC-1.md").write_text(spec("SPEC-1", "Refunds", "cancelled"), encoding="utf-8"),
            "a worktree file added": lambda: (self.feat / "specs" / "SPEC-3.md").write_text(spec("SPEC-3", "Exports"), encoding="utf-8"),
            "a branch moved": lambda: self.commit_on("other", "SPEC-2.md", spec("SPEC-2", "Receipts")),
            "a branch deleted": lambda: git(self.root, "branch", "-D", "other"),
            "a worktree removed": lambda: git(self.root, "worktree", "remove", "--force", str(self.feat)),
        }
        for what, change in changes.items():
            with self.subTest(what), reads as branch_rows:
                self.answer()
                warm = branch_rows.call_count
                self.answer()
                self.assertEqual(branch_rows.call_count, warm, "a warm index reads no branch again")
                change()
                self.assertEqual(self.answer(), self.answer(use_index=False))
                self.assertEqual(self.answer(include_done=True), self.answer(include_done=True, use_index=False))

    def test_another_config_never_reads_rows_the_first_one_wrote(self):
        self.commit_on("other", "SPEC-2.md", spec("SPEC-2", "Receipts"))
        git(self.root, "checkout", "-q", "other")
        (self.root / "work").mkdir()
        (self.root / "work" / "SPEC-9.md").write_text(spec("SPEC-9", "Elsewhere"), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "SPEC-9")
        git(self.root, "checkout", "-q", "main")
        self.answer()
        cfg = mock.Mock(specs_dir="work", product_dir="product", proposals_dir="proposals", approvers=[])
        self.assertEqual(self.answer(cfg), self.answer(cfg, use_index=False))
        self.assertEqual([i["id"] for i in self.answer(cfg)["items"]], ["SPEC-9"])

    def test_a_worktree_whose_folder_is_gone_leaves_its_branch_read_from_its_tip(self):
        self.commit_on("other", "SPEC-2.md", spec("SPEC-2", "Receipts"))
        gone = self.root.parent / "gone"
        git(self.root, "worktree", "add", "-q", str(gone), "other")
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        self.assertIn(("SPEC-2", "Receipts", ("branch:other",)), self.summary(self.answer()))

    def test_parallel_processes_on_a_fresh_index_all_answer_alike(self):
        want = json.dumps(self.answer(use_index=False), sort_keys=True)
        code = "import json, pathlib, sys; from aidd.workitems import all_branches as a; print(json.dumps(a.all_branches_work(pathlib.Path(sys.argv[1]), None), sort_keys=True))"
        env = {**os.environ, "PYTHONPATH": src_pythonpath()}
        runs = [
            subprocess.Popen([sys.executable, "-c", code, str(self.root)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)
        ]
        outs = [(r.communicate(timeout=60), r.returncode) for r in runs]
        self.assertEqual([(rc, err) for (_, err), rc in outs], [(0, "")] * 8)
        self.assertEqual({out.strip() for (out, _), _ in outs}, {want})
        self.assertTrue(all_branches.index_path(self.root).read_bytes().startswith(b"SQLite format 3"))

    def test_a_branchs_text_never_drives_the_terminal(self):
        (self.feat / "specs" / "SPEC-7.md").write_text(
            '---\ntype: spec\nid: SPEC-7\ntitle: "x\\u001b]0;owned\\u0007"\nstatus: draft\nroute: "normal\\u001b[2J"\n---\n',
            encoding="utf-8",
        )
        text = workitems.status_text(self.answer())
        self.assertIn("SPEC-7 x ]0;owned ", text)
        self.assertFalse(any(ord(c) < 32 and c != "\n" for c in text), text)

    def test_a_file_that_does_not_parse_is_named_with_its_place(self):
        (self.feat / "specs" / "SPEC-9.md").write_text("---\ntype: spec\nid: SPEC-9\ntitle: [unclosed\n---\n", encoding="utf-8")
        unreadable = self.answer()["unreadable"]
        self.assertEqual([(u["place"], u["path"]) for u in unreadable], [(f"worktree:{self.feat}", "specs/SPEC-9.md")])


def approved_intent(approved_at: str = "2026-11-10T09:12:00Z", approved: bool = True) -> str:
    """INTENT-1 with its `approval`, or without it (`approved=False`), as it stands before the person's yes."""
    approval = f'approval: {{by: "J <j@example.com>", at: "{approved_at}"}}\n' if approved else ""
    return (
        '---\ntype: intent\nid: INTENT-1\ntitle: "Plan"\noutcome: "g by 2027-01-01"\n'
        f"{approval}phases: [{{id: P1, name: p, specs: [{{id: SPEC-1, title: one}}]}}]\n---\n\n## Problem\n"
    )


class AnApprovalNeedsItsLinesInEveryPlaceTests(unittest.TestCase):
    """The file's text says who approved; a commit with the person's `Approved-by` and `Approves` lines, which changes only the
    approval, proves it. `aidd status` checks that,
    and `--all-branches` checks it in each place with that place's own history, never trusting the text."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        (self.root / "product" / "intents").mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Ada")
        git(self.root, "config", "user.email", "ada@example.com")

    def commit(self, message: str, text: str = "", *, approves: bool = False) -> None:
        """A commit of the Intent (`text`, else with its approval); `approves` adds the person's two lines."""
        (self.root / "product" / "intents" / "INTENT-1.md").write_text(text or approved_intent(), encoding="utf-8")
        git(self.root, "add", "-A")
        lines = ["--trailer", "Approved-by: J <j@example.com>", "--trailer", "Approves: INTENT-1"] if approves else []
        git(self.root, "commit", "-q", "-m", message, *lines)

    def approve(self, text: str = "") -> None:
        """The person's yes: the Intent as it stands, then a commit that changes only its approval, with their two lines."""
        self.commit("plan", approved_intent(approved=False))
        self.commit("Approve INTENT-1", text, approves=True)

    def test_a_file_that_says_approved_with_no_lines_asks_for_the_approval_in_every_place(self):
        self.commit("plan: the agent wrote the approval itself")
        git(self.root, "branch", "elsewhere")  # a branch place, read from its tip
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")  # and a fetched one
        plain = next(i for i in workitems.open_work(self.root, None)["items"] if i["id"] == "INTENT-1")
        self.assertEqual(plain["next"]["code"], "intent.approve")
        every = [i for i in all_branches.all_branches_work(self.root, None, use_index=False)["items"] if i["id"] == "INTENT-1"]
        self.assertEqual([(i["next"]["code"], len(i["places"])) for i in every], [("intent.approve", 3)], "one version, in three places")

    def test_the_persons_lines_keep_the_approval_in_every_place(self):
        self.approve()
        git(self.root, "branch", "elsewhere")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        every = [i for i in all_branches.all_branches_work(self.root, None, use_index=False)["items"] if i["id"] == "INTENT-1"]
        self.assertEqual([(i["next"]["code"], len(i["places"])) for i in every], [("intent.slice", 3)])

    def test_each_place_is_checked_against_its_own_history(self):
        self.commit("plan: no approval lines")
        git(self.root, "branch", "without-lines")
        self.commit("Approve again", approved_intent("2026-11-11T09:12:00Z"), approves=True)
        git(self.root, "branch", "with-lines")
        found = {i["next"]["code"]: i["places"] for i in all_branches.all_branches_work(self.root, None, use_index=False)["items"] if i["id"] == "INTENT-1"}
        self.assertIn("branch:without-lines", found["intent.approve"])
        self.assertNotIn("branch:with-lines", found["intent.approve"])
        self.assertIn("branch:with-lines", found["intent.slice"])

    def test_a_branch_tip_whose_approved_intent_has_a_body_change_asks_for_the_approval_again(self):
        """`approved_version` marks the body of the place it is asked about, so `--all-branches` reads a branch tip's body as the
        working tree's: a change asks again, a Learn section written at the end included."""
        self.approve()
        base = approved_intent()
        git(self.root, "checkout", "-q", "-b", "edited")
        self.commit("Rewrite the Problem", base + "\nMore about the problem.\n")
        git(self.root, "checkout", "-q", "-b", "learned", "main")
        self.commit("Write the Learn section", base + "\n## Learn\n\nIt held.\n")
        git(self.root, "checkout", "-q", "main")
        found = {i["next"]["code"]: i["places"] for i in all_branches.all_branches_work(self.root, None, use_index=False)["items"] if i["id"] == "INTENT-1"}
        self.assertEqual(sorted(found["intent.approve"]), ["branch:edited", "branch:learned"])
        self.assertNotIn("branch:learned", found["intent.slice"])
        self.assertNotIn("branch:edited", found["intent.slice"])


if __name__ == "__main__":
    unittest.main()
