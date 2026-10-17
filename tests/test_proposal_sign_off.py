"""A proposal's sign-off binds its text by hash, and a proposal being drafted names who answers for each open dependency.

`aidd hash <proposal>` prints the proposal hash. It covers the body, handoff blocks included, and the front matter. It
leaves out the decisions (`sign_off`, `outcome`, `status`) and the living fields (model.PROPOSAL_LIVING_FIELDS). A
person records it as `sign_off.hash`. `aidd validate` fails once the text no longer matches, unless a change order in
the proposal's `change-orders/` folder names the new hash on its `Proposal hash after this change:` line. It reads
only regular files named `CO-<n>.md`, and warns about a file it cannot read. While the proposal is drafted, it warns
when an open dependency has no owner, due date, or mitigation.
"""

import os
import tempfile
import unittest
from pathlib import Path

from helpers import adopted_repo, git, run_cli

from aidd.workitems import validation
from aidd.workitems import spec_file
from aidd.kernel import documents

PROPOSAL = """---
aidd_version: "1.0.0"
kind: proposal
id: PROP-3
title: Dealer portal
audience: client
addressee: Acme Corp
goal: Dealers track their orders
go_no_go: {decision: go, by: "@lead", decided_on: "2026-09-01"}
{sign_off}{outcome}
needs:
  - id: N-1
    need: Track orders
    answer: met

dependencies:
  - id: D-1
    text: Read access to the ERP export
    owner: Acme IT
    status: open
    due: "2026-10-15"
    mitigation: Start on a fixture export
---

## Summary

We build the dealer portal.
"""
SUBMITTED = 'outcome: {decision: submitted, by: "@lead", decided_on: "2026-09-21"}\n'


def text(sign_off: str = "", outcome: str = "") -> str:
    return PROPOSAL.replace("{sign_off}", sign_off).replace("{outcome}", outcome)


def signed(h: str) -> str:
    return f'sign_off: {{by: "@lead", decided_on: "2026-09-20", hash: "{h}"}}\n'


UNSIGNED_HASH = spec_file.proposal_hash(text())

# The proposal with an estimate, an exclusion, a price, a question, and a risk.
RICH = (
    text()
    .replace(
        "go_no_go: {",
        "exclusions: [Hosting]\nestimate: {unit: person-days, low: 20, likely: 30, high: 45, basis: Two past portals}\ngo_no_go: {",
    )
    .replace(
        "---\n\n## Summary",
        '\nrisks:\n  - id: R-1\n    text: The ERP export is late\n    owner: "@lead"\n    status: open\n    likelihood: medium\n    impact: high\n'
        '\nquestions:\n  - id: Q-1\n    question: "Which ERP?"\n    answer: SAP\n'
        '\nmilestones:\n  - id: M-1\n    name: Order tracking live\n    due: "2026-12-01"\n    trigger: {event: go-live}\n    currency: EUR\n    amount: 5000\n'
        "---\n\n## Summary",
    )
)


class HashTests(unittest.TestCase):
    def test_the_hash_covers_the_promise_and_not_the_decisions_after_it(self):
        h = spec_file.proposal_hash(text())
        self.assertRegex(h, r"^[0-9a-f]{32}$")
        # Recording the sign-off itself, the outcome, or a status cache never changes what was signed off.
        self.assertEqual(spec_file.proposal_hash(text(signed(h), SUBMITTED)), h)
        self.assertEqual(spec_file.proposal_hash(text().replace("\ngoal: ", "\nstatus: drafting\ngoal: ")), h)
        # Comments change nothing either.
        self.assertEqual(spec_file.proposal_hash(text().replace("title: Dealer portal\n", "# a note\ntitle: Dealer portal\n")), h)
        # The needs, the RAID log, and the body are the promise: any change to them changes the hash.
        self.assertNotEqual(spec_file.proposal_hash(text().replace("answer: met", "answer: partly_met")), h)
        self.assertNotEqual(spec_file.proposal_hash(text().replace('due: "2026-10-15"', 'due: "2026-11-15"')), h)
        self.assertNotEqual(spec_file.proposal_hash(text().replace("We build the dealer portal.", "We build a dealer portal.")), h)

    def test_line_endings_and_key_order_change_nothing(self):
        h = spec_file.proposal_hash(RICH)
        self.assertEqual(spec_file.proposal_hash(RICH.replace("\n", "\r\n")), h)
        multiline = RICH.replace(
            "estimate: {unit: person-days, low: 20, likely: 30, high: 45, basis: Two past portals}",
            "estimate:\n  unit: person-days\n  low: 20\n  likely: 30\n  high: 45\n  basis: |-\n    Two past\n    portals",
        )
        self.assertNotEqual(multiline, RICH)
        self.assertEqual(spec_file.proposal_hash(multiline.replace("\n", "\r\n")), spec_file.proposal_hash(multiline))
        reordered = RICH.replace("title: Dealer portal\n", "").replace(
            "goal: Dealers track their orders\n", "goal: Dealers track their orders\ntitle: Dealer portal\n"
        )
        reordered = reordered.replace("  - id: D-1\n    text: Read access to the ERP export\n", "  - text: Read access to the ERP export\n    id: D-1\n")
        self.assertNotEqual(reordered, RICH)
        self.assertEqual(spec_file.proposal_hash(reordered), h)

    def test_a_handoff_block_in_a_proposal_counts(self):
        """A proposal's handoff block is part of its text: the hash keeps it, unlike the Spec hash."""
        h = spec_file.proposal_hash(text())
        self.assertNotEqual(spec_file.proposal_hash(text() + "\n```aidd-handoff\ndone: drafted\n```\n"), h)
        hidden = text().replace("## Summary\n", "## Summary\n\n```aidd-handoff\nPrice: 10k\n```\n")
        self.assertNotEqual(spec_file.proposal_hash(hidden), h)
        self.assertNotEqual(spec_file.proposal_hash(hidden), spec_file.proposal_hash(hidden.replace("10k", "20k")))

    def test_the_promise_changes_it(self):
        h = spec_file.proposal_hash(RICH)
        self.assertEqual(spec_file.load_object(RICH, "p.md")[2], [])
        for old, new in (
            ("likely: 30", "likely: 35"),  # the estimate
            ("exclusions: [Hosting]", "exclusions: [Hosting, Support]"),
            ("[Hosting]", "[Hosting after go-live]"),  # an exclusion
            ("amount: 5000", "amount: 6000"),  # the price
            ("need: Track orders", "need: Track and cancel orders"),
            ("text: The ERP export is late", "text: The ERP export is late or partial"),  # RAID text
            ("text: Read access to the ERP export", "text: Write access to the ERP export"),
            ('question: "Which ERP?"', 'question: "Which ERP version?"'),
        ):
            with self.subTest(old=old):
                self.assertIn(old, RICH)
                self.assertNotEqual(spec_file.proposal_hash(RICH.replace(old, new, 1)), h)

    def test_the_living_fields_change_nothing(self):
        """Fields people fill in over time, after sign-off too: a question's answer, a RAID item's status, a milestone's
        reached_on and invoice_ref, and a need's epic."""
        h = spec_file.proposal_hash(RICH)
        for old, new in (
            ("answer: SAP\n", ""),
            ("answer: SAP", 'answer: "SAP S/4HANA, cloud edition"'),
            ("status: open\n    likelihood", "status: resolved\n    likelihood"),  # close a risk
            ("status: open\n    due", "status: resolved\n    due"),  # close a dependency
            ("amount: 5000", 'amount: 5000\n    reached_on: "2026-12-01"\n    invoice_ref: INV-7'),
            ("answer: met", "answer: met\n    epic: EPIC-1"),
        ):
            with self.subTest(old=old):
                self.assertIn(old, RICH)
                changed = RICH.replace(old, new, 1)
                self.assertEqual(spec_file.load_object(changed, "p.md")[2], [])
                self.assertEqual(spec_file.proposal_hash(changed), h)
        self.assertEqual(
            {k: set(v) for k, v in spec_file.PROPOSAL_LIVING_FIELDS.items()},
            {
                "questions": {"answer"},
                "risks": {"status"},
                "assumptions": {"status"},
                "issues": {"status"},
                "dependencies": {"status"},
                "milestones": {"reached_on", "invoice_ref"},
                "needs": {"epic"},
            },
        )

    def test_method_lists_what_the_hash_leaves_out(self):
        method = (Path(__file__).resolve().parent.parent / "docs" / "METHOD.md").read_text(encoding="utf-8")
        start = method.index("The sign-off records the proposal hash")
        section = method[start : method.index("\n\n", start)]
        for key in sorted(spec_file.PROPOSAL_UNSIGNED_KEYS | {f for fields in spec_file.PROPOSAL_LIVING_FIELDS.values() for f in fields}):
            self.assertIn(f"`{key}`", section, key)

    def test_the_schema_takes_a_hash_of_32_hex_characters(self):
        self.assertEqual(spec_file.load_object(text(signed(UNSIGNED_HASH)), "p.md")[2], [])
        self.assertTrue(spec_file.load_object(text(signed("not-a-hash")), "p.md")[2])
        self.assertTrue(spec_file.load_object(text(signed(UNSIGNED_HASH.upper())), "p.md")[2])


class ValidateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "proposals" / "PROP-3"
        self.folder.mkdir(parents=True)
        self.path = self.folder / "proposal.md"

    def findings(self, body: str, needle: str) -> list[str]:
        self.path.write_text(body, encoding="utf-8")
        return [f.replace(str(self.path), "proposal.md") for f in validation.validate_file(self.path) if needle in f]

    def change_order(self, n: int, body: str) -> None:
        (self.folder / "change-orders").mkdir(exist_ok=True)
        (self.folder / "change-orders" / f"CO-{n}.md").write_text(body, encoding="utf-8")

    def test_a_matching_hash_passes(self):
        self.assertEqual(self.findings(text(signed(UNSIGNED_HASH)), "hash"), [])
        self.assertEqual(self.findings(text(signed(UNSIGNED_HASH), SUBMITTED), "hash"), [])

    def test_a_change_after_sign_off_fails(self):
        changed = text(signed(UNSIGNED_HASH)).replace("answer: met", "answer: partly_met")
        now = spec_file.proposal_hash(changed)
        (error,) = self.findings(changed, "hash")
        self.assertFalse(error.startswith("warning: "), error)
        self.assertTrue(error.startswith(f"proposal.md: the proposal changed after sign-off: its hash is {now}, and sign_off.hash is {UNSIGNED_HASH}"), error)
        self.assertIn("change-orders/", error)

    def test_a_change_order_that_names_the_new_hash_records_the_change(self):
        changed = text(signed(UNSIGNED_HASH)).replace("answer: met", "answer: partly_met")
        now = spec_file.proposal_hash(changed)
        self.change_order(1, f"# Change order CO-1: PROP-3\n\nProposal hash after this change: `{UNSIGNED_HASH[:31]}0`\n")
        self.assertEqual(len(self.findings(changed, "hash")), 1, "a change order that names another hash records nothing")
        self.change_order(2, f"# Change order CO-2: PROP-3\n\nProposal hash after this change: `{now}`\n")
        self.assertEqual(self.findings(changed, "hash"), [])
        (self.folder / "change-orders" / "CO-2.md").write_text(f"Proposal hash after this change: {now}\n", encoding="utf-8")
        self.assertEqual(self.findings(changed, "hash"), [], "the backticks are optional")

    def changed(self) -> tuple[str, str]:
        changed = text(signed(UNSIGNED_HASH)).replace("answer: met", "answer: partly_met")
        return changed, spec_file.proposal_hash(changed)

    def test_only_the_hash_line_of_a_change_order_named_co_n_counts(self):
        """The reviewer's cases: none of these records the change, and the error stays."""
        changed, now = self.changed()
        proper = f"Proposal hash after this change: `{now}`\n"
        cases = {
            "CO-zzz.md": f"<!-- {now} -->\nnot a real change order\n",
            "CO-1.txt": proper,
            "co-1.md": proper,
            "CO-1a.md": proper,
            "CO-.md": proper,
            "CO-1.md": f"# Change order CO-1: PROP-99\nThis change order does NOT approve {now}.\n",
        }
        cases_in_co_1 = {
            "in an HTML comment": f"<!-- {proper} -->\n",
            "in an unclosed HTML comment": f"<!--\n{proper}",
            "inside a sentence": f"We think the Proposal hash after this change: `{now}` is wrong.\n",
            "another proposal's id, no line": f"# Change order CO-1: PROP-99\n\n{now}\n",
            "the line, another hash": f"Proposal hash after this change: `{UNSIGNED_HASH}`\nThis change order does NOT approve {now}.\n",
        }
        (self.folder / "change-orders").mkdir()
        for name, body in cases.items():
            with self.subTest(name=name):
                (self.folder / "change-orders" / name).write_text(body, encoding="utf-8")
                self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
                (self.folder / "change-orders" / name).unlink()
        for why, body in cases_in_co_1.items():
            with self.subTest(why=why):
                self.change_order(1, body)
                self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        nested = self.folder / "change-orders" / "old"
        nested.mkdir()
        (nested / "CO-1.md").write_text(proper, encoding="utf-8")
        (self.folder / "CO-1.md").write_text(proper, encoding="utf-8")
        self.change_order(1, "nothing yet\n")
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1, "only files directly in change-orders/ count")
        self.change_order(1, f"# Change order CO-1: PROP-3\n\n<!-- Filled by a person. -->\n\n{proper}")
        self.assertEqual(self.findings(changed, "changed after sign-off"), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_a_symlinked_change_order_or_folder_counts_for_nothing(self):
        changed, now = self.changed()
        outside = self.folder.parent.parent / "outside"
        outside.mkdir()
        (outside / "CO-1.md").write_text(f"Proposal hash after this change: `{now}`\n", encoding="utf-8")
        (self.folder / "change-orders").mkdir()
        os.symlink(outside / "CO-1.md", self.folder / "change-orders" / "CO-1.md")
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        self.assertEqual(self.findings(changed, "CO-1.md"), ["warning: proposal.md: change order change-orders/CO-1.md is not read: it is a symlink"])
        (self.folder / "change-orders" / "CO-1.md").unlink()
        (self.folder / "change-orders").rmdir()
        os.symlink(outside, self.folder / "change-orders")
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        self.assertEqual(self.findings(changed, "is not read"), ["warning: proposal.md: change-orders/ is not read: it is a symlink"])

    def test_an_unreadable_change_order_is_a_warning_and_validate_goes_on(self):
        changed, now = self.changed()
        orders = self.folder / "change-orders"
        orders.mkdir()
        (orders / "CO-1.md").mkdir()
        self.assertEqual(self.findings(changed, "CO-1.md"), ["warning: proposal.md: change order change-orders/CO-1.md is not read: it is not a regular file"])
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        (orders / "CO-1.md").rmdir()
        if hasattr(os, "symlink"):
            os.symlink(orders / "missing.md", orders / "CO-2.md")
            self.assertEqual(self.findings(changed, "CO-2.md"), ["warning: proposal.md: change order change-orders/CO-2.md is not read: it is a symlink"])
            (orders / "CO-2.md").unlink()
        big = f"Proposal hash after this change: `{now}`\n" + "x" * documents.MAX_DOCUMENT_BYTES
        (orders / "CO-3.md").write_text(big, encoding="utf-8")
        self.assertEqual(
            self.findings(changed, "CO-3.md"),
            [f"warning: proposal.md: change order change-orders/CO-3.md is not read: it is over {documents.MAX_DOCUMENT_BYTES} bytes"],
        )
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        (orders / "CO-3.md").unlink()
        if os.name == "posix" and os.geteuid() != 0:
            locked = orders / "CO-4.md"
            locked.write_text(f"Proposal hash after this change: `{now}`\n", encoding="utf-8")
            locked.chmod(0)
            self.addCleanup(locked.chmod, 0o644)
            (warning,) = self.findings(changed, "CO-4.md")
            self.assertTrue(warning.startswith("warning: proposal.md: change order change-orders/CO-4.md is not read: "), warning)
            self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)

    def test_a_new_sign_off_clears_the_error(self):
        changed, now = self.changed()
        self.assertEqual(len(self.findings(changed, "changed after sign-off")), 1)
        resigned = changed.replace(f'hash: "{UNSIGNED_HASH}"', f'hash: "{now}"').replace('decided_on: "2026-09-20"', 'decided_on: "2026-09-24"')
        self.assertEqual(spec_file.proposal_hash(resigned), now)
        self.assertEqual(self.findings(resigned, "hash"), [])

    def test_living_fields_recorded_after_sign_off_need_no_new_sign_off(self):
        h = spec_file.proposal_hash(RICH)
        sent = RICH.replace("go_no_go: {", signed(h) + SUBMITTED + "go_no_go: {")
        self.assertEqual(self.findings(sent, "proposal.md"), [])
        later = sent.replace("status: open\nlikelihood", "status: resolved\nlikelihood").replace("answer: SAP", "answer: SAP S/4HANA")
        self.assertEqual(self.findings(later, "proposal.md"), [])
        self.assertEqual(len(self.findings(later.replace("likely: 30", "likely: 40"), "changed after sign-off")), 1)

    def test_a_sign_off_without_a_hash_is_a_warning(self):
        bare = 'sign_off: {by: "@lead", decided_on: "2026-09-20"}\n'
        (warning,) = self.findings(text(bare), "hash")
        self.assertTrue(warning.startswith("warning: proposal.md: sign_off records no hash, so it binds no text"), warning)
        self.assertIn("aidd hash", warning)
        self.assertEqual(self.findings(text(), "hash"), [], "an unsigned proposal needs no hash")

    def test_an_open_dependency_names_its_owner_due_and_mitigation_while_the_proposal_is_drafted(self):
        """The warning fires while a person can still act on it without a new sign-off: after go, before sign-off."""

        def warnings(old: str, new: str = "", sign: bool = False, outcome: str = "", go: bool = True) -> list[str]:
            base = text(signed(UNSIGNED_HASH) if sign else "", outcome)
            self.assertIn(old, base + "unused")
            base = base.replace(old, new)
            base = base.replace(f'hash: "{UNSIGNED_HASH}"', f'hash: "{spec_file.proposal_hash(base)}"')
            if not go:
                base = base.replace('go_no_go: {decision: go, by: "@lead", decided_on: "2026-09-01"}\n', "")
            return self.findings(base, "dependency D-1")

        self.assertEqual(warnings("unused"), [])
        (w,) = warnings('    due: "2026-10-15"\n')
        self.assertEqual(w, "warning: proposal.md: dependency D-1 is open and has no due date; a person sets it before the sign-off")
        (w,) = warnings('    due: "2026-10-15"\n    mitigation: Start on a fixture export\n')
        self.assertIn("has no due date and no mitigation; a person sets them before the sign-off", w)
        (w,) = warnings("owner: Acme IT", 'owner: " "')
        self.assertIn("has no owner", w)
        self.assertEqual(warnings('    status: open\n    due: "2026-10-15"\n', "    status: resolved\n"), [], "a closed dependency owes nothing")
        self.assertEqual(warnings('    due: "2026-10-15"\n', go=False), [], "before go, nobody drafts")
        self.assertEqual(warnings('    due: "2026-10-15"\n', sign=True), [], "after sign-off, following it would change the signed text")
        self.assertEqual(warnings('    due: "2026-10-15"\n', sign=True, outcome=SUBMITTED), [])

    def test_following_the_dependency_warning_then_signing_off_leaves_no_finding(self):
        draft = text().replace('    due: "2026-10-15"\n', "")
        self.assertEqual(len(self.findings(draft, "dependency D-1")), 1)
        fixed = text()
        self.assertEqual(self.findings(fixed, "proposal.md"), [])
        self.assertEqual(self.findings(text(signed(spec_file.proposal_hash(fixed)), SUBMITTED), "proposal.md"), [])


class HashCommandTests(unittest.TestCase):
    def test_aidd_hash_prints_a_proposal_hash_and_its_sign_off_line(self):
        with adopted_repo() as root:
            path = root / "proposals" / "PROP-3" / "proposal.md"
            path.parent.mkdir(parents=True)
            path.write_text(text(), encoding="utf-8")
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md", "--worktree")
            self.assertEqual((code, out.strip()), (0, UNSIGNED_HASH))
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md", "--worktree", "--line")
            self.assertEqual(code, 0, out)
            self.assertRegex(out.strip(), rf'^sign_off: {{by: "@you", decided_on: "\d{{4}}-\d{{2}}-\d{{2}}", hash: "{UNSIGNED_HASH}"}}$')
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md", "--worktree", "--summary")
            self.assertEqual(code, 2, out)
            self.assertIn("a Spec", out)

    def test_the_default_ref_is_head(self):
        with adopted_repo() as root:
            path = root / "proposals" / "PROP-3" / "proposal.md"
            path.parent.mkdir(parents=True)
            path.write_text(text(), encoding="utf-8")
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md")
            self.assertEqual(code, 2, out)
            self.assertIn("proposals/PROP-3/proposal.md is not in HEAD; commit it first, or pass --worktree", out)
            git(root, "add", "-A")
            git(root, "commit", "-qm", "proposal")
            self.assertEqual(run_cli("hash", "proposals/PROP-3/proposal.md"), (0, UNSIGNED_HASH + "\n"))
            path.write_text(text().replace("We build the dealer portal.", "We build a dealer portal."), encoding="utf-8")
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md")
            self.assertEqual(code, 0, out)
            self.assertEqual(out.splitlines(), ["warning: uncommitted changes to the proposal; this hash is for HEAD", UNSIGNED_HASH])

    def test_a_spec_only_flag_refuses_before_any_warning(self):
        with adopted_repo() as root:
            path = root / "proposals" / "PROP-3" / "proposal.md"
            path.parent.mkdir(parents=True)
            path.write_text(text(), encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "proposal")
            path.write_text(text() + "\nMore.\n", encoding="utf-8")
            for flag in ("--html", "--summary"):
                with self.subTest(flag=flag):
                    code, out = run_cli("hash", "proposals/PROP-3/proposal.md", flag)
                    self.assertEqual(code, 2, out)
                    self.assertNotIn("warning", out)
                    self.assertIn("on a proposal, use --line or no flag", out)

    def test_a_proposal_id_finds_the_proposal(self):
        with adopted_repo() as root:
            path = root / "proposals" / "PROP-3" / "proposal.md"
            path.parent.mkdir(parents=True)
            path.write_text(text(), encoding="utf-8")
            self.assertEqual(run_cli("hash", "PROP-3", "--worktree"), (0, UNSIGNED_HASH + "\n"))
            other = root / "proposals" / "dealer-portal" / "proposal.md"
            other.parent.mkdir(parents=True)
            other.write_text(text().replace("id: PROP-3", "id: PROP-4"), encoding="utf-8")
            code, out = run_cli("hash", "PROP-4", "--worktree")
            self.assertEqual(code, 0, out)
            git(root, "add", "-A")
            git(root, "commit", "-qm", "proposals")
            self.assertEqual(run_cli("hash", "PROP-3"), (0, UNSIGNED_HASH + "\n"))
            code, out = run_cli("hash", "PROP-404", "--worktree")
            self.assertEqual(code, 2, out)
            self.assertIn("no Spec has the id PROP-404 in specs/, and no proposal has it in proposals/", out)


class NewParentTests(unittest.TestCase):
    """`aidd new` refuses a parent that is here and of the wrong kind, as `aidd validate` would."""

    def test_new_refuses_a_parent_of_the_wrong_kind(self):
        with adopted_repo() as root:
            self.assertEqual(run_cli("new", "initiative", "INIT-1", "--title", "Dealers")[0], 0)
            code, out = run_cli("new", "spec", "SPEC-1", "--title", "t", "--parent", "INIT-1")
            self.assertEqual(code, 2, out)
            self.assertIn("parent INIT-1 is an Initiative; a Spec's parent is an Epic", out)
            self.assertFalse((root / "specs" / "SPEC-1.md").exists())
            code, out = run_cli("new", "epic", "EPIC-1", "--title", "t", "--parent", "INIT-1")
            self.assertEqual(code, 0, out)
            code, out = run_cli("new", "epic", "EPIC-2", "--title", "t", "--parent", "EPIC-1")
            self.assertEqual(code, 2, out)
            self.assertIn("parent EPIC-1 is an Epic; an Epic's parent is an Initiative", out)
            code, out = run_cli("new", "spec", "SPEC-1", "--title", "t", "--parent", "EPIC-1")
            self.assertEqual(code, 0, out)
            code, out = run_cli("new", "spec", "SPEC-2", "--title", "t", "--parent", "EPIC-404")
            self.assertEqual(code, 0, "a parent that is not here may live elsewhere: validate warns, new writes")


if __name__ == "__main__":
    unittest.main()
