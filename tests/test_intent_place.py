"""An Intent lives in `<product_dir>/intents/` (`workitems.intent_paths`) and nowhere else.

The invariants. (1) An Intent outside that folder is a plain finding that names the folder and the `git mv` that moves it, and no
`aidd upgrade` step, because aidd moves no Intent. (2) A person's approval is found at the Intent's own path and at the names git's
record of renames gives it: an approval recorded at another place, with no rename for git to follow, holds nothing, and a title or
slice changed after a `git mv` asks again. (3) A reader of a commit finds an Intent in the Intents' folder only. (4) Nothing makes a
`product/` folder until an Intent is written.
"""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, git

from aidd import config, workitems
from aidd.delegation import local_run
from aidd.setup import doctor_probes
from aidd.workitems import intent_checks, intent_paths

CONFIG = 'aidd_version: "1.0.0"\nprofile: solo\n'
PERSON = "Maya Lee <maya@users.noreply.github.com>"
APPROVAL = f'approval: {{by: "{PERSON}", at: "2026-11-10T09:12:00Z"}}\n'
NO_HOLD = "its approval has no hold"


def intent(n: int, extra: str = "", outcome: str = "Refunds are capped", specs: str = "") -> str:
    """An Intent with one phase."""
    ids = specs or f"{{id: SPEC-{n}, title: Cap the refund}}"
    return f"---\ntype: intent\nid: INTENT-{n}\ntitle: Refund limits\noutcome: {outcome}\n{extra}phases:\n  - {{id: P1, name: Cap, specs: [{ids}]}}\n---\n"


class Repo(unittest.TestCase):
    config = CONFIG

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        for key, value in (("user.name", "Maya Lee"), ("user.email", "maya@users.noreply.github.com"), ("commit.gpgsign", "false")):
            git(self.root, "config", key, value)
        self.put(".aidd/config.yaml", self.config)
        self.put(".gitignore", config.OUTPUT_IGNORE + "\n")
        self.commit("adopt")

    def put(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str, *, approves: str = "") -> None:
        """A commit of everything. `approves` is the Intent's id when the person's yes rides on it: their two lines."""
        git(self.root, "add", "-A")
        trailer = ["--trailer", f"Approved-by: {PERSON}", "--trailer", f"Approves: {approves}"] if approves else []
        git(self.root, "commit", "-qm", message, "--allow-empty", *trailer)

    def move(self, old: str, new: str) -> None:
        """A person's `git mv`, committed on its own."""
        (self.root / new).parent.mkdir(parents=True, exist_ok=True)
        git(self.root, "mv", old, new)
        self.commit(f"move {old}")

    def status(self) -> dict[str, dict]:
        done = aidd_here("status", "--json", cwd=self.root)
        return {i["id"]: i for i in json.loads(done.stdout)["items"]}


class AnIntentOutsideItsFolderIsAFindingWithNoUpgradeStep(Repo):
    """Invariant (1)."""

    def findings(self, *args: str) -> list[str]:
        done = aidd_here("validate", *args, cwd=self.root)
        return [line for line in done.stdout.splitlines() if line.startswith("error")]

    def test_validate_names_the_folder_and_the_move_for_each_place_outside_it(self):
        cases = {
            "the specs folder": ("", "specs/INTENT-1.md", "product/intents/INTENT-1.md", True),
            "a folder in the specs folder": ("", "specs/old/INTENT-1.md", "product/intents/INTENT-1.md", True),
            "a product folder the config names": ("product_dir: plans\n", "specs/INTENT-1.md", "plans/intents/INTENT-1.md", True),
            "the top of the repository, named to validate": ("", "INTENT-1.md", "product/intents/INTENT-1.md", False),  # the walk reads no file there
        }
        for name, (extra, where, belongs, walked) in cases.items():
            with self.subTest(name):
                self.setUp()
                self.put(".aidd/config.yaml", CONFIG + extra)
                self.put(where, intent(1))
                self.commit("a misplaced Intent")
                self.assertEqual(len(self.findings()), 1 if walked else 0)
                [error] = self.findings(where)
                for part in (where, belongs, f"git mv {where} {belongs}"):
                    self.assertIn(part, error)
                self.assertNotIn("upgrade", error)

    def test_an_intent_in_its_folder_has_no_such_finding(self):
        for where in ("product/intents/INTENT-1.md", "product/intents/old/INTENT-1.md"):
            with self.subTest(where):
                self.setUp()
                self.put(where, intent(1))
                self.commit("in place")
                self.assertEqual(self.findings(), [])

    def test_a_misplaced_intent_is_still_read_so_that_no_intent_goes_unread(self):
        self.put("specs/INTENT-1.md", intent(1))
        self.put("product/intents/INTENT-2.md", intent(2))
        self.commit("one of each")
        self.assertEqual(sorted(self.status()), ["INTENT-1", "INTENT-2"])
        self.assertEqual(aidd_here("validate", cwd=self.root).returncode, 1)

    def test_doctor_names_no_step_for_it(self):
        self.put("specs/INTENT-1.md", intent(1))
        self.commit("a misplaced Intent")
        self.assertEqual(doctor_probes.retired_name_lines(self.root), [])

    def test_a_person_who_moves_it_clears_the_finding(self):
        self.put("specs/INTENT-1.md", intent(1))
        self.commit("a misplaced Intent")
        self.move("specs/INTENT-1.md", "product/intents/INTENT-1.md")
        self.assertEqual(self.findings(), [])


class AnApprovalIsFoundAtTheIntentsOwnPathAndThroughGitsRenames(Repo):
    """Invariant (2). `approved_at` commits the Intent at its first place, then a commit that changes only its approval, with the
    person's two lines."""

    def warns(self, rel: str) -> list[str]:
        path = self.root / rel
        data, _ = workitems.load_object(path.read_text(encoding="utf-8"), path.as_posix())[:2]
        return intent_checks.approval_warnings(path, data, self.root)

    def approved_at(self, where: str, text: str) -> None:
        self.put(where, text)
        self.commit("plan")
        self.put(where, text.replace("outcome:", APPROVAL + "outcome:"))
        self.commit("INTENT-1: approved", approves="INTENT-1")

    def test_a_git_mv_keeps_the_approval_and_a_change_after_it_asks_again(self):
        base = intent(1)
        cases = {
            "moved, nothing else": (base, None, False),
            "moved, then the outcome changed": (base, ("Refunds are capped", "Refunds are capped at 30 days"), True),
            "moved, then a slice added": (base, ("title: Cap the refund}", "title: Cap the refund}, {id: SPEC-9, title: Nine}"), True),
            "moved, then the title renamed": (base, ("title: Refund limits", "title: Refund caps"), True),
        }
        for where in ("specs/INTENT-1.md", "specs/old/INTENT-1.md", "specs/refund-limits.md"):
            for name, (old, after, warned) in cases.items():
                with self.subTest(where=where, case=name):
                    self.setUp()
                    self.approved_at(where, old)
                    self.move(where, f"product/intents/{Path(where).name}")
                    rel = f"product/intents/{Path(where).name}"
                    if after is not None:
                        self.put(rel, (self.root / rel).read_text(encoding="utf-8").replace(*after))
                        self.commit("edit after the move")
                    found = self.warns(rel)
                    self.assertEqual(bool(found), warned, found)
                    self.assertEqual(self.status()["INTENT-1"]["next"]["code"] == "intent.approve", warned)

    def test_an_approval_recorded_at_another_place_holds_nothing_when_git_follows_no_rename(self):
        """Before, the specs folder was searched by the Intent's file name and by its id. Now only the Intent's own path and the
        names git's record of renames gives it are, so each of these asks for the approval again."""
        cases = {
            "deleted in one commit, added in the next": ("specs/INTENT-1.md", "product/intents/INTENT-1.md"),
            "deleted in one commit, added under another name": ("specs/INTENT-1.md", "product/intents/refund-limits.md"),
            "deleted from a folder of the specs folder": ("specs/old/INTENT-1.md", "product/intents/INTENT-1.md"),
        }
        for name, (where, belongs) in cases.items():
            with self.subTest(name):
                self.setUp()
                self.approved_at(where, intent(1))
                git(self.root, "rm", "-q", where)
                self.commit("the old Intent is removed")
                self.put(belongs, intent(1, extra=APPROVAL))
                self.commit("the Intent, in its folder")
                self.assertTrue(any(NO_HOLD in w for w in self.warns(belongs)))
                self.assertEqual(self.status()["INTENT-1"]["next"]["code"], "intent.approve")

    def test_the_approval_stands_at_the_intents_own_path(self):
        self.approved_at("product/intents/INTENT-1.md", intent(1))
        self.assertEqual(self.warns("product/intents/INTENT-1.md"), [])

    def test_an_approval_no_commit_recorded_holds_nothing_after_a_move_either(self):
        self.put("specs/INTENT-1.md", intent(1, extra=APPROVAL))
        self.commit("a commit with no approval lines")
        self.move("specs/INTENT-1.md", "product/intents/INTENT-1.md")
        self.assertTrue(any(NO_HOLD in w for w in self.warns("product/intents/INTENT-1.md")))

    def test_another_intents_approval_is_never_reused_because_a_file_has_the_same_name(self):
        """INTENT-1 was approved at `specs/plan.md` and left. INTENT-2, written at `product/intents/plan.md` with the same words, is no
        approved Intent: a move keeps the id, so a version with another id is no approval."""
        self.approved_at("specs/plan.md", intent(1))
        git(self.root, "rm", "-q", "specs/plan.md")
        self.commit("INTENT-1 is gone")
        self.put("product/intents/plan.md", intent(1, extra=APPROVAL).replace("INTENT-1", "INTENT-2").replace("SPEC-1", "SPEC-2"))
        self.commit("INTENT-2, the same words")
        self.assertTrue(any(NO_HOLD in w for w in self.warns("product/intents/plan.md")))
        self.assertEqual(self.status()["INTENT-2"]["next"]["code"], "intent.approve")


class IntentsLiveInTheIntentsFolder(Repo):
    """Invariant (4), and the readers of the folder."""

    def test_a_new_intent_goes_to_the_intents_folder_and_never_takes_an_id_either_place_holds(self):
        self.put("specs/INTENT-2.md", intent(2))
        self.put("product/intents/INTENT-5.md", intent(5))
        self.commit("old and new")
        done = aidd_here("new", "intent", "Cut repeated work", cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("product/intents/INTENT-6.md", done.stdout)
        self.assertTrue((self.root / "product/intents/INTENT-6.md").is_file())

    def test_no_product_folder_is_made_until_an_intent_is_written(self):
        done = aidd_here("new", "spec", "Apply a discount", "--force", cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse((self.root / "product").exists())
        aidd_here("new", "intent", "Cut repeated work", cwd=self.root)
        self.assertTrue((self.root / "product/intents").is_dir())

    def test_an_open_exploration_in_an_intents_folder_is_a_step_for_a_person(self):
        self.put("product/intents/INTENT-1.md", intent(1))
        workitems.new_exploration(self.root / "product/intents/INTENT-1/explore/langfuse", question="Langfuse in the clock?")
        found = json.loads(aidd_here("status", "--json", cwd=self.root).stdout)["explorations"]
        self.assertEqual([(e["path"], e["item"]) for e in found], [("product/intents/INTENT-1/explore/langfuse/exploration.md", "INTENT-1")])

    def test_a_slice_starts_its_spec_from_an_intent_in_its_folder(self):
        self.put("product/intents/INTENT-1.md", intent(1))
        done = aidd_here("new", "spec", "SPEC-1", cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("parent: INTENT-1", (self.root / "specs/SPEC-1.md").read_text(encoding="utf-8"))

    def test_the_folders_a_walk_reads_are_the_specs_folder_and_the_intents_folder_once_each(self):
        cases = {
            ("specs", "product"): ("specs", "product/intents"),
            ("work", "plans"): ("work", "plans/intents"),
            ("specs", "specs/product"): ("specs",),  # the specs folder holds the Intents' folder: read it once
            ("specs/", "./product/"): ("specs", "product/intents"),
        }
        for (specs, product), want in cases.items():
            with self.subTest(specs=specs, product=product):
                self.assertEqual(intent_paths.work_folders(specs, product), want)

    def test_an_exploration_of_an_intent_belongs_in_the_intents_folder(self):
        cases = {
            "product/intents/INTENT-1/refund-limit": "product/intents/INTENT-1/explore/refund-limit",
            "specs/INTENT-1/refund-limit": "product/intents/INTENT-1/explore/refund-limit",
            "specs/SPEC-1/refund-limit": "specs/SPEC-1/explore/refund-limit",
            "product/intents/INTENT-1/explore/refund-limit": None,
            "specs/SPEC-1/explore/refund-limit": None,
            "specs/explore/topic": None,
            "product/intents/explore/topic": "specs/<ID>/explore/topic",  # no Intent is named, so no Intent folder is meant
        }
        for folder, want in cases.items():
            with self.subTest(folder):
                self.assertEqual(workitems.exploration_misplaced(Path(folder), root=self.root), want)

    def test_the_order_file_lies_where_the_intent_order_row_names_it(self):
        from unittest import mock

        row = {**config.item_type_rows()["intent-order"], "files": [{"path": "{product}/ranking/order.md", "template": "intent-order.md"}]}
        with mock.patch.dict(config.item_type_rows(), {"intent-order": row}):
            self.assertEqual(intent_paths.product_file("intent-order", "plans"), "plans/ranking/order.md")


class AReaderOfACommitFindsAnIntentInItsFolderOnly(Repo):
    """Invariant (3). The delegate reads the parent Intent from the default branch's tip, which `ref` names."""

    def test_the_intent_is_found_in_the_intents_folder_and_never_in_the_specs_folder(self):
        self.put("specs/INTENT-1.md", intent(1))
        self.commit("misplaced")
        before = git(self.root, "rev-parse", "HEAD")
        self.move("specs/INTENT-1.md", "product/intents/INTENT-1.md")
        after = git(self.root, "rev-parse", "HEAD")
        for ref, path in ((before, None), (after, "product/intents/INTENT-1.md")):
            with self.subTest(ref=ref[:7]):
                found = local_run.intent_by_id(str(self.root), ref, "specs", "product", "INTENT-1")
                self.assertEqual(found[0] if found else None, path)
        self.assertIsNone(local_run.spec_by_id(str(self.root), after, "specs", "INTENT-1"), "a Spec lookup never reads the Intents' folder")

    def test_the_list_of_intents_still_names_a_misplaced_one_so_a_listed_spec_is_never_free_of_it(self):
        """`intents_at` only adds holds: an Intent in the specs folder that lists a Spec binds it, and `intent_by_id` then finds
        none, so the approval defers."""
        self.put("specs/INTENT-1.md", intent(1))
        self.commit("misplaced")
        ref = git(self.root, "rev-parse", "HEAD")
        self.assertEqual([p for p, _ in local_run.intents_at(str(self.root), ref, "specs", "product")], ["specs/INTENT-1.md"])


if __name__ == "__main__":
    unittest.main()
