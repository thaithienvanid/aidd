"""The hold of a person's approval: an Intent's `approval`, and a product scope file's pair, count only by the commit that brought
them. That commit's last paragraph carries `Approved-by:` for the same person and `Approves:` with the item's exact id, both keys
in exactly that case, and the commit changes nothing in the item but the approval. Everything else holds nothing and fails closed:
a field alone, a trailer alone, `Approved-by:` with no `Approves:`, an amended or folded approval commit, a commit that names
another item, and the old `Agreed-by:` trailer, which no reader takes."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ, open_work

from aidd.kernel import documents, json_schema
from aidd.workitems import approval, approval_commits, intent_checks, product_approval, validation, work_list

PERSON = "Mai Tran <mai@example.com>"
AT = "2026-11-16T10:05:00Z"
FIELD = f'approval: {{by: "{PERSON}", at: "{AT}"}}\n'
PAIR = f"Approved-by: {PERSON}"


def intent(n: int = 1, approval_line: str = "", outcome: str = "Guests book online by 2027-01-01", specs: str = "") -> str:
    lines = specs or f"{{id: SPEC-{n}, title: one}}"
    return (
        f'---\ntype: intent\nid: INTENT-{n}\ntitle: "Let guests book online"\noutcome: "{outcome}"\n{approval_line}'
        f"phases: [{{id: P1, name: p, specs: [{lines}]}}]\n---\n\n## Problem\n\nGuests cannot book online.\n"
    )


class ApprovesMatcherTests(unittest.TestCase):
    """`Approves:` names an id exactly, in the last paragraph, with the key in exactly that case. Each row is read both ways."""

    ROWS = (
        ("Approves: INTENT-1", "INTENT-1", True),
        ("Approves: INTENT-1", "INTENT-1#S1", False),
        ("Approves: INTENT-1#S1", "INTENT-1", False),
        ("Approves: INTENT-1#S1", "INTENT-1#S1", True),
        ("Approves: INTENT-1", "INTENT-10", False),
        ("Approves: INTENT-10", "INTENT-1", False),
        ("Approves: intent-1", "INTENT-1", False),
        ("Approves: INTENT-2, INTENT-1", "INTENT-1", True),
        ("Approves: INTENT-2,INTENT-1", "INTENT-1", True),
        ("Approves: INTENT-2\nApproves: INTENT-1", "INTENT-1", True),
        ("Approves: INTENT-1 and the plan", "INTENT-1", False),
        ("Approves: INTENT-1, INTENT-2 too", "INTENT-1", False),
        ("Approves: INTENT-1,", "INTENT-1", False),
        ("Approves:", "INTENT-1", False),
        ("approves: INTENT-1", "INTENT-1", False),
        ("APPROVES: INTENT-1", "INTENT-1", False),
        (" Approves: INTENT-1", "INTENT-1", False),
        ("Approves: product/prd.md", "product/prd.md", True),
        ("Approves: product/prd.md", "INTENT-1", False),
        ("Approves: INTENT-1", "product/prd.md", False),
        ("Approves: Product Docs/prd.md", "Product Docs/prd.md", True),
        ("Approves: Product Docs/prd.md, INTENT-1", "Product Docs/prd.md", True),
        ("Approves: Product Docs/prd.md, INTENT-1", "INTENT-1", False),
        ("Approves: INTENT-1, see docs/x y", "INTENT-1", False),
        ("Approves: Product  Docs/prd.md", "Product Docs/prd.md", False),
        ("Approves: Product Docs/prd.md too", "Product Docs/prd.md", False),
        ("Approves: INTENT-1 please", "INTENT-1", False),
    )

    def test_each_row_names_exactly_the_ids_it_lists(self):
        for line, ident, held in self.ROWS:
            with self.subTest(line=line, ident=ident):
                self.assertIs(approval_commits.approves(f"approve\n\n{PAIR}\n{line}", ident), held)

    def test_a_line_outside_the_last_paragraph_or_beside_a_delegated_yes_names_nothing(self):
        self.assertFalse(approval_commits.approves(f"approve\n\nApproves: INTENT-1\n\n{PAIR}", "INTENT-1"))
        delegated = f"approve\n\n{PAIR}\nApproves: INTENT-1\nDecided-by: agent:claude-code/x"
        self.assertFalse(approval_commits.approves(delegated, "INTENT-1"))
        self.assertFalse(approval_commits.approves(f"approve\n\n{PAIR}\nApproves: INTENT-1", ""))
        self.assertEqual(approval_commits.approved_ids(f"approve\n\n{PAIR}\nApproves: Product Docs/prd.md"), set())


@unittest.skipUnless(shutil.which("git"), "git is required")
class IntentApprovalHoldTests(unittest.TestCase):
    """Each way a commit can bring an Intent's approval, and what the Intent reads: approved only for the one honest shape."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        (self.root / "product" / "intents").mkdir(parents=True)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Mai Tran")
        git(self.root, "config", "user.email", "mai@example.com")
        git(self.root, "config", "commit.gpgsign", "false")
        for n in (1, 2):
            self.write(n, intent(n))
        self.commit("plan")

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, n: int) -> Path:
        return self.root / "product" / "intents" / f"INTENT-{n}.md"

    def write(self, n: int, text: str) -> None:
        self.path(n).write_text(text, encoding="utf-8")

    def commit(self, subject: str, *trailers: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", subject, *(["-m", "\n".join(trailers)] if trailers else []))

    def status(self, n: int = 1) -> str:
        return {i["id"]: i for i in open_work(self.root)}[f"INTENT-{n}"]["status"]

    def findings(self, n: int = 1) -> list[str]:
        return validation.validate_file(self.path(n))

    def errors(self, n: int = 1) -> list[str]:
        return [f for f in self.findings(n) if validation.is_error(f)]

    def held(self, n: int = 1) -> bool:
        data, _ = documents.split_front_matter(self.path(n).read_text(encoding="utf-8"), "x")
        return intent_checks.approved_version(self.root, f"product/intents/INTENT-{n}.md", data) is not None

    def test_aidd_approve_makes_the_one_commit_that_holds(self):
        sha, who, paths = approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        message = git(self.root, "log", "-1", "--format=%B", sha)
        self.assertIn(f"{PAIR}\nApproves: INTENT-1", message)
        self.assertEqual((who, paths), (PERSON, ["product/intents/INTENT-1.md"]))
        self.assertTrue(self.held())
        self.assertEqual((self.status(), self.errors()), ("approved", []))

    def test_one_command_for_two_intents_holds_both(self):
        approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1", "INTENT-2"], now=AT)
        self.assertIn("Approves: INTENT-1, INTENT-2", git(self.root, "log", "-1", "--format=%B"))
        self.assertEqual((self.status(1), self.status(2)), ("approved", "approved"))

    def test_the_same_commit_amended_to_change_the_outcome_holds_nothing(self):
        approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        self.write(1, intent(1, FIELD, outcome="Guests book and pay online by 2027-01-01"))
        git(self.root, "commit", "-q", "-a", "--amend", "--no-edit")
        self.assertIn(f"{PAIR}\nApproves: INTENT-1", git(self.root, "log", "-1", "--format=%B"), "the amend kept both lines")
        self.assertFalse(self.held())
        self.assertEqual(self.status(), "draft")
        self.assertEqual(len(self.errors()), 1, self.findings())

    def test_a_commit_that_also_changes_another_field_or_the_body_holds_nothing(self):
        for name, text in (
            ("a field", intent(1, FIELD).replace('title: "Let guests book online"', 'title: "Book online"')),
            ("a planned Spec", intent(1, FIELD, specs="{id: SPEC-1, title: one}, {id: SPEC-9, title: nine}")),
            ("the body", intent(1, FIELD) + "\nOne more line.\n"),
        ):
            with self.subTest(name):
                self.write(1, text)
                self.commit("approve", PAIR, "Approves: INTENT-1")
                self.assertEqual((self.held(), self.status()), (False, "draft"))
                git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_a_field_with_no_trailer_reads_draft_with_an_error(self):
        self.write(1, intent(1, FIELD))
        self.commit("approve")
        self.assertEqual((self.held(), self.status()), (False, "draft"))
        self.assertEqual(len(self.errors()), 1, self.findings())
        self.assertIn("aidd approve INTENT-1", self.errors()[0])

    def test_a_field_never_committed_reads_draft_with_an_error(self):
        self.write(1, intent(1, FIELD))
        self.assertEqual((self.held(), self.status()), (False, "draft"))
        self.assertEqual(len(self.errors()), 1, self.findings())

    def test_a_trailer_with_no_field_approves_nothing(self):
        self.write(1, intent(1) + "\n")
        self.commit("approve", PAIR, "Approves: INTENT-1")
        self.assertEqual((self.held(), self.status(), self.errors()), (False, "draft", []))

    def test_approved_by_alone_the_old_trailer_and_a_key_in_another_case_hold_nothing(self):
        for name, trailers in (
            ("Approved-by alone", (PAIR,)),
            ("Approves alone", ("Approves: INTENT-1",)),
            ("the old trailer", (f"Agreed-by: {PERSON}",)),
            ("the old trailer with Approves", (f"Agreed-by: {PERSON}", "Approves: INTENT-1")),
            ("a lowercase key", (f"approved-by: {PERSON}", "Approves: INTENT-1")),
            ("an uppercase key", (PAIR, "APPROVES: INTENT-1")),
            ("another person", ("Approved-by: Lan Vo <lan@example.com>", "Approves: INTENT-1")),
            ("a delegated yes beside it", (PAIR, "Approves: INTENT-1", "Decided-by: agent:claude-code/x")),
        ):
            with self.subTest(name):
                self.write(1, intent(1, FIELD))
                self.commit("approve", *trailers)
                self.assertEqual((self.held(), self.status()), (False, "draft"))
                git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_a_commit_that_names_another_intent_holds_no_approval_of_this_one(self):
        self.write(1, intent(1, FIELD))
        self.write(2, intent(2, FIELD))
        self.commit("approve", PAIR, "Approves: INTENT-2")
        self.assertEqual((self.held(1), self.status(1)), (False, "draft"))
        self.assertEqual((self.held(2), self.status(2)), (True, "approved"))

    def test_a_commit_that_names_a_criterion_or_a_longer_id_holds_no_approval_of_the_intent(self):
        for named in ("INTENT-1#S1", "INTENT-10", "intent-1"):
            with self.subTest(named):
                self.write(1, intent(1, FIELD))
                self.commit("approve", PAIR, f"Approves: {named}")
                self.assertFalse(self.held())
                git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_an_edit_after_the_approval_keeps_it_and_asks_again(self):
        approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        for name, text in (
            ("the front matter", intent(1, FIELD).replace('title: "Let guests book online"', 'title: "Book online"')),
            ("a planned Spec", intent(1, FIELD, specs="{id: SPEC-1, title: one}, {id: SPEC-9, title: nine}")),
            ("the body", intent(1, FIELD) + "\nOne more line.\n"),
        ):
            with self.subTest(name):
                self.write(1, text)
                self.commit("edit")
                item = {i["id"]: i for i in open_work(self.root)}["INTENT-1"]
                self.assertEqual((item["status"], item["next"]["code"]), ("approved", "intent.approve"))
                self.assertTrue([f for f in self.findings() if f.startswith("warning:") and "approve it again" in f], self.findings())
                git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_a_commit_encoding_header_never_hides_or_synthesizes_trailers(self):
        """Hold reads raw commit bytes as UTF-8 only; ASCII Latin-1 trailers still stand verbatim in raw bytes so they hold."""
        msg_file = Path(self.tmp.name) / "msg.bin"
        self.write(1, intent(1, FIELD))
        msg_file.write_bytes(b"approve\n\n+AEE-pproved-by: Mai Tran <mai@example.com>\n+AEE-pproves: INTENT-1\n")
        git(self.root, "add", "-A")
        git(self.root, "-c", "i18n.commitEncoding=UTF-7", "commit", "-q", "-F", str(msg_file))
        self.assertEqual((self.held(), self.status()), (False, "draft"))
        git(self.root, "reset", "-q", "--hard", "HEAD~1")

        who = "José García <jose@example.com>"
        self.write(1, intent(1, f'approval: {{by: "{who}", at: "{AT}"}}\n'))
        self.commit("approve", f"Approved-by: {who}", "Approves: INTENT-1")
        self.assertEqual((self.held(), self.status()), (True, "approved"))
        git(self.root, "reset", "-q", "--hard", "HEAD~1")

        self.write(1, intent(1, FIELD))
        msg_file.write_bytes(b"approve\n\nApproved-by: Mai Tran <mai@example.com>\nApproves: INTENT-1\n")
        git(self.root, "add", "-A")
        git(self.root, "-c", "i18n.commitEncoding=latin-1", "commit", "-q", "-F", str(msg_file))
        self.assertEqual((self.held(), self.status()), (True, "approved"))
        git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_a_shallow_clone_names_git_fetch_unshallow_when_history_cuts_off_the_approval(self):
        approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        (self.root / "notes.txt").write_text("more work\n", encoding="utf-8")
        self.commit("more work")
        shallow = Path(self.tmp.name).resolve() / "shallow"
        git(self.root, "clone", "-q", "--depth=1", f"file://{self.root}", str(shallow))
        self.assertEqual(git(shallow, "rev-parse", "--is-shallow-repository").strip(), "true")
        self.assertEqual({i["id"]: i for i in open_work(shallow)}["INTENT-1"]["status"], "draft")
        errors = [f for f in validation.validate_file(shallow / "product" / "intents" / "INTENT-1.md") if validation.is_error(f)]
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("its approval has no hold, so aidd reads it as draft", errors[0])
        self.assertIn("git fetch --unshallow", errors[0])
        self.assertNotIn("aidd approve", errors[0])

        status = aidd_subprocess("status", cwd=shallow)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("its approval has no hold, so aidd reads it as draft", status.stdout)
        self.assertIn("git fetch --unshallow", status.stdout)
        self.assertNotIn("aidd approve INTENT-1", status.stdout)

        self.write(2, intent(2, FIELD))
        self.commit("field without trailer")
        full_errors = self.errors(2)
        self.assertEqual(len(full_errors), 1, full_errors)
        self.assertIn("aidd approve INTENT-2", full_errors[0])
        self.assertNotIn("git fetch --unshallow", full_errors[0])

    def test_a_multiline_approval_names_the_fix_in_both_status_and_approve(self):
        self.write(1, intent(1, f'approval:\n  by: "{PERSON}"\n  at: "{AT}"\n'))
        self.commit("multiline approval without trailers")
        status = aidd_subprocess("status", cwd=self.root)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("run this in the repository: aidd approve INTENT-1", status.stdout)
        for token in ("one line", "approval: {by:", "Approved-by:", "Approves: INTENT-1", "remove `approval:`", "commit", "aidd approve INTENT-1"):
            self.assertIn(token, status.stdout)

        with self.assertRaises(ValueError) as caught:
            approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        msg = str(caught.exception)
        for token in ("one line", "approval: {by:", "Approved-by:", "Approves: INTENT-1", "remove `approval:`", "commit", "aidd approve INTENT-1"):
            self.assertIn(token, msg)

        # Removing the multiline field, committing that edit, then running `aidd approve` works.
        self.write(1, intent(1))
        self.commit("remove multiline approval")
        sha, who, rels = approval.record_approval(self.root, {"items": open_work(self.root)}, ["INTENT-1"], now=AT)
        self.assertTrue(sha and who and rels == ["product/intents/INTENT-1.md"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class ProductScopeApprovalHoldTests(unittest.TestCase):
    """A product scope file keeps its loose pair until a later change, and its hold is the same: `Approves:` names its path."""

    PRD = "---\ntype: prd\nproduct_outcomes: []\n{pair}---\n\n## Objectives\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Mai Tran")
        git(self.root, "config", "user.email", "mai@example.com")
        git(self.root, "config", "commit.gpgsign", "false")
        (self.root / "product").mkdir()
        (self.root / "product" / "intents").mkdir()
        self.prd = self.root / "product" / "prd.md"
        self.prd.write_text(self.PRD.format(pair=""), encoding="utf-8")
        (self.root / "product" / "intents" / "INTENT-1.md").write_text(intent(1), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "scope")

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self, *trailers: str, with_intent: bool = False) -> bool:
        self.prd.write_text(self.PRD.format(pair=f'approved_by: "{PERSON}"\napproved_at: "{AT}"\n'), encoding="utf-8")
        if with_intent:
            (self.root / "product" / "intents" / "INTENT-1.md").write_text(intent(1, FIELD), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "approve", "-m", "\n".join(trailers))
        data, _ = documents.split_front_matter(self.prd.read_text(encoding="utf-8"), "prd")
        return product_approval.approved_text(self.root, "product/prd.md", data) is not None

    def test_the_file_holds_only_with_approves_naming_its_path(self):
        for name, trailers, held in (
            ("its path", (PAIR, "Approves: product/prd.md"), True),
            ("Approved-by alone", (PAIR,), False),
            ("another file", (PAIR, "Approves: product/brd.md"), False),
            ("a lowercase key", (PAIR, "approves: product/prd.md"), False),
        ):
            with self.subTest(name):
                self.assertIs(self.approve(*trailers), held)
                git(self.root, "reset", "-q", "--hard", "HEAD~1")

    def test_a_commit_that_approves_an_intent_holds_no_approval_of_a_scope_file_it_sets(self):
        self.assertFalse(self.approve(PAIR, "Approves: INTENT-1", with_intent=True))

    def test_a_scope_file_in_a_folder_with_a_space_holds(self):
        spaced = self.root / "Product Docs" / "prd.md"
        spaced.parent.mkdir()
        spaced.write_text(self.PRD.format(pair=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "spaced scope")
        spaced.write_text(self.PRD.format(pair=f'approved_by: "{PERSON}"\napproved_at: "{AT}"\n'), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "approve", "-m", f"{PAIR}\nApproves: Product Docs/prd.md")
        data, _ = documents.split_front_matter(spaced.read_text(encoding="utf-8"), "prd")
        self.assertIsNotNone(product_approval.approved_text(self.root, "Product Docs/prd.md", data))


class TheFileAloneIsNoHoldTests(unittest.TestCase):
    def test_a_view_with_no_reader_of_the_commit_reads_no_approval(self):
        """A view that cannot read git, such as a list of files with no repository, has no hold to read, so a claimed approval reads draft."""
        data, _ = documents.split_front_matter(intent(1, FIELD), "x")
        answer = work_list.open_items([("product/intents/INTENT-1.md", data)], [], None)
        item = {i["id"]: i for i in answer["items"]}["INTENT-1"]
        self.assertEqual((item["status"], item["next"]["code"]), ("draft", "intent.approve"))
        held = work_list.open_items([("product/intents/INTENT-1.md", data)], [], None, approved=lambda rel, d: d)
        self.assertEqual({i["id"]: i for i in held["items"]}["INTENT-1"]["status"], "approved", "a reader that holds it is what moves it")


class OnlyAPersonApprovesTests(unittest.TestCase):
    def test_an_agent_in_the_intents_or_a_results_approval_is_an_error_and_a_person_is_none(self):
        """One check reads who approved, on the Intent and on each criterion's result, so an agent's id is refused in both."""
        for who, errors in (("agent:claude-code/claude-sonnet-4-6", 1), ("role:architect", 1), (PERSON, 0)):
            for where in ("the Intent", "a result"):
                with self.subTest(who=who, where=where):
                    yes = {"by": who, "at": AT}
                    result = {"measured_on": "2027-01-05", "decision": "met", **({"approval": yes} if where == "a result" else {})}
                    data = {
                        "type": "intent",
                        "id": "INTENT-1",
                        **({"approval": yes} if where == "the Intent" else {}),
                        "success_criteria": [{"id": "S1", "measure_after_days": 14, "result": result}],
                    }
                    found = [f for f in intent_checks.approval_problems("I.md", data) if not f.startswith("warning")]
                    self.assertEqual(len(found), errors, found)


class TheOldShapeIsGoneTests(unittest.TestCase):
    def test_an_intent_that_holds_agreed_by_fails_validation_with_the_schemas_error(self):
        data, _ = documents.split_front_matter(intent(1, f'agreed_by: "{PERSON}"\nagreed_at: "{AT}"\n'), "x")
        errors = json_schema.validate(data, "intent.schema.json")
        self.assertTrue(any("agreed_by" in e for e in errors), errors)
        good, _ = documents.split_front_matter(intent(1, FIELD), "x")
        self.assertEqual(json_schema.validate(good, "intent.schema.json"), [])

    def test_an_approval_of_the_wrong_shape_fails_validation(self):
        for name, line in (("no time", f'approval: {{by: "{PERSON}"}}\n'), ("a key more", f'approval: {{by: "{PERSON}", at: "{AT}", for: x}}\n')):
            with self.subTest(name):
                data, _ = documents.split_front_matter(intent(1, line), "x")
                self.assertTrue(json_schema.validate(data, "intent.schema.json"))

    def test_aidd_agree_is_an_unknown_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = aidd_subprocess("agree", "INTENT-1", cwd=Path(tmp), env=hermetic_environ())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("'agree' is not an aidd command", done.stderr)


if __name__ == "__main__":
    unittest.main()
