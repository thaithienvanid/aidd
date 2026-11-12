"""`aidd delegate check` on the merge of an approved Spec's change: it defers when the change moves what the approval
froze, the Spec's tests, its scope, or the Spec's own path. Split from test_delegation_spec to keep each file inside the
test budget."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from helpers import SAMPLE_SPEC, git
from test_delegation_check import Repo, codes, note
from test_delegation_spec import SpecCase

from aidd import config
from aidd.delegation import action_checks, local_run


class ChangedAfterApprovalTests(SpecCase):
    def test_tests_changed_after_approval_defer_the_merge(self):
        loosened = "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        pass\n"
        cases = {
            "a test loosened": {"tests/test_discount.py": loosened},
            "a test renamed away and its copy loosened": {"tests/test_discount.py": None, "tests/test_discount_v2.py": loosened},
        }
        for name, tests in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo, spec_head = self.spec_repo()
                self.delegate_approved(spec_head)
                head = self.built(repo, tests)
                self.assertEqual(codes(repo.check(head)), ["tests_changed"])
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo, spec_head = self.spec_repo()
            self.delegate_approved(spec_head)
            self.assertEqual(codes(repo.check(self.built(repo, {}))), [], "a recorded yes and unchanged tests pass")

    def test_a_change_outside_the_approved_scope_or_spec_defers(self):
        repo, spec_head = self.spec_repo()
        self.delegate_approved(spec_head)
        self.assertEqual(codes(repo.check(self.built(repo, {"src/billing/rates.py": "RATE = 1\n"}))), ["out_of_scope"])
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo, spec_head = self.spec_repo()
            self.delegate_approved(spec_head)
            text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
            repo.write("specs/SPEC-220.md", text.replace("new_behavior: true", "new_behavior: true\n      reruns: 3"))
            self.assertEqual(codes(repo.check(self.built(repo, {}))), ["tests_changed"], "a changed tests block is spec.revise")

    def test_a_spec_moved_after_its_approval_defers(self):
        repo, spec_head = self.spec_repo()
        self.delegate_approved(spec_head)
        text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
        (self.root / "specs/SPEC-220.md").unlink()
        repo.write("specs/done/SPEC-220.md", text)
        self.assertEqual(codes(repo.check(self.built(repo, {}, spec="specs/done/SPEC-220.md"))), ["tests_changed"])


class SpecLandedEarlierTests(SpecCase):
    """The merge check and `aidd test` name the same Spec for a change: the one the diff holds, or an approved one whose
    Task scope the diff touches, even when it landed in an earlier PR. The head cannot drop it by deleting its file."""

    def landed(self, scope: str | None = None) -> Repo:
        """SPEC-220 ready on `main` with the delegate's yes on record, then approved there; `feature` starts from `main`."""
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        spec = SAMPLE_SPEC.replace("route: normal", "status: ready\nroute: normal")
        spec = spec.replace('scope: ["src/checkout/"]', f"scope: {scope}") if scope else spec
        repo.write("specs/SPEC-220.md", spec)
        repo.write(
            "tests/test_discount.py",
            "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        self.assertTrue(__import__('os').path.exists('src/checkout/discount.py'))\n",
        )
        self.delegate_approved(repo.commit("SPEC-220: the Spec and its tests"))
        repo.write("specs/SPEC-220.md", spec.replace("status: ready", "status: approved"))
        trailers = ["Decided-by: agent:claude-code/aidd-team:delegate", "On-behalf-of: Maya Lee <maya@users.noreply.github.com>", "Delegation: " + "b" * 40]
        repo.commit("Approve SPEC-220", "-m", "\n".join(trailers))
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        return repo

    def head(self, repo: Repo, files: dict[str, str | None]) -> str:
        for path, body in files.items():
            if body is None:
                (self.root / path).unlink()
            else:
                repo.write(path, body)
        code = repo.commit("Implement")
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def test_a_change_inside_an_open_specs_scope_is_deferred_by_its_own_route_and_never_by_the_scope_alone(self):
        """Invariant: touching the Task scope of an open Spec the change does not hold is a note, as `aidd test` has it, and the
        change's own paths decide. A non-minor change with no Spec still defers, naming the Spec and the step; a minor one
        merges, so an unrelated fix never waits on a wide scope."""
        repo = self.landed()
        result = repo.check(self.head(repo, {"src/checkout/discount.py": "RATE = 0.1\n"}))
        self.assertEqual(codes(result), [], "a minor change inside the scope")
        self.assertTrue(any("SPEC-220" in w and "spec/SPEC-220" in w for w in result["warnings"]), "the note names the Spec and the step")
        with self.subTest("a non-minor change inside the scope"), tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo = self.landed(scope='["src/auth/"]')
            result = repo.check(self.head(repo, {"src/auth/login.py": "RATE = 0.1\n"}))
            self.assertEqual(codes(result), ["no_spec"])
            self.assertIn("spec/<ID>", str(result["reasons"]), "the step to take")
            self.assertIn("SPEC-220", str(result["reasons"]))

    def test_the_head_cannot_drop_the_spec_by_deleting_it_and_a_second_spec_is_no_one_specs_change(self):
        cases = {
            "the head deleted the Spec": ({"specs/SPEC-220.md": None, "src/checkout/discount.py": "RATE = 0.1\n"}, ["no_spec"]),
            "the head moved the Spec out of the specs folder": (None, ["no_spec"]),
            "a second Spec in the diff": (
                {
                    "specs/SPEC-220.md": SAMPLE_SPEC.replace("route: normal", "status: approved\nroute: normal").replace("Add a percentage", "Add a flat"),
                    "specs/SPEC-221.md": SAMPLE_SPEC.replace("SPEC-220", "SPEC-221"),
                    "src/checkout/discount.py": "RATE = 0.1\n",
                },
                ["no_spec"],
            ),
            "the change leaves the Spec's scope alone": ({"docs/guide.md": "guide\n"}, []),
        }
        for name, (files, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.landed()
                if files is None:
                    text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
                    files = {"specs/SPEC-220.md": None, "docs/SPEC-220.md": text, "src/checkout/discount.py": "RATE = 0.1\n"}
                result = repo.check(self.head(repo, files))
                self.assertTrue(set(expected) <= set(codes(result)), (name, codes(result)))
                if name != "the change leaves the Spec's scope alone" and "no_spec" in expected:
                    self.assertTrue(any(step in str(result["reasons"]) for step in ("or ask the person", "restore it")), "every defer names a step that works")
                if not expected:
                    self.assertEqual(codes(result), [], "no scope touched, no Spec applies, and a minor change passes")


class OneSpecLookupTests(SpecCase):
    """The Spec with an id is found in the config's `specs_dir` and nowhere else, so the checks that read it agree on
    which file it is, whatever order they run in."""

    FOLDER = "docs/specs"

    def with_a_decoy(self, decoy_scope: str) -> tuple[Repo, str]:
        """A Spec in `docs/specs`, and a file in `docs/a-notes` (sorted before it) with the same id, another `tests`
        block, and a `decoy_scope` for its Task."""
        repo, _ = self.spec_repo(specs=self.FOLDER, extra="specs_dir: docs/specs\n")
        real = (self.root / self.FOLDER / "SPEC-220.md").read_text(encoding="utf-8")
        decoy = real.replace('scope: ["src/checkout/"]', f"scope: {decoy_scope}").replace(
            'files: ["tests/test_discount.py"]', 'files: ["tests/test_discount.py", "tests/test_more.py"]'
        )
        repo.write("docs/a-notes/SPEC-220.md", decoy)
        return repo, repo.commit("a design note that reuses the id")

    def test_a_file_outside_the_specs_folder_with_the_same_id_is_never_the_approved_spec(self):
        repo, spec_head = self.with_a_decoy('["src/"]')
        self.delegate_approved(spec_head)
        built = self.built(repo, {}, spec=f"{self.FOLDER}/SPEC-220.md")
        result = repo.check(built)
        self.assertEqual(codes(result), ["out_of_scope"], "the real Spec is the approved one, and the note lies outside its scope")
        self.assertIn("docs/a-notes/SPEC-220.md", str(result["reasons"]), "the note's own broad scope does not excuse it")

    def test_the_scope_check_alone_reads_the_real_spec_so_the_order_of_the_checks_is_free(self):
        repo, spec_head = self.with_a_decoy('["src/"]')
        self.delegate_approved(spec_head)
        self.built(repo, {}, spec=f"{self.FOLDER}/SPEC-220.md")
        deferred: list[str] = []
        check = SimpleNamespace(
            top=str(self.root),
            cfg=config.load_file(config.CONFIG_PATH, str(self.root)),
            covers={"spec": "SPEC-220"},
            defer=lambda code, why: deferred.append(code),
        )
        action_checks.scope_check(check, ["src/billing/rates.py"], f"{self.FOLDER}/SPEC-220.md", spec_head)
        self.assertEqual(deferred, ["out_of_scope"], "the decoy's broad scope is never read")
        self.assertEqual(local_run.spec_by_id(str(self.root), spec_head, self.FOLDER, "SPEC-220")[0], f"{self.FOLDER}/SPEC-220.md")
        self.assertIsNone(local_run.spec_by_id(str(self.root), spec_head, "docs/a-notes/none", "SPEC-220"))


if __name__ == "__main__":
    import unittest

    unittest.main()
