"""A proposal's sign-off binds its text by hash, and a proposal being drafted names who answers for each open dependency.

`aidd hash <proposal>` prints the proposal hash. It covers the body, handoff blocks included, and the front matter. It
leaves out the decisions (`sign_off`, `outcome`, `status`) and the living fields (model.PROPOSAL_LIVING_FIELDS). A
person signs it off (they type `sign off PROP-1`), and aidd records it as `sign_off.hash`. `aidd validate` fails once
the text no longer matches, until the person signs it off again, after the client approved the change order. While
the proposal is drafted, it warns when an open dependency has no owner, due date, or mitigation.
"""

import tempfile
import unittest
from pathlib import Path

from helpers import adopted_repo, git, run_cli

from aidd.workitems import validation
from aidd.workitems import spec_file

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

    def changed(self) -> tuple[str, str]:
        """A signed-off proposal whose promise changed after its sign-off, and its hash now."""
        changed = text(signed(UNSIGNED_HASH)).replace("answer: met", "answer: partly_met")
        return changed, spec_file.proposal_hash(changed)

    def test_a_matching_hash_passes(self):
        self.assertEqual(self.findings(text(signed(UNSIGNED_HASH)), "hash"), [])
        self.assertEqual(self.findings(text(signed(UNSIGNED_HASH), SUBMITTED), "hash"), [])

    def test_a_change_after_sign_off_fails(self):
        changed, now = self.changed()
        (error,) = self.findings(changed, "changed after sign-off")
        self.assertFalse(error.startswith("warning: "), error)
        self.assertTrue(error.startswith("proposal.md: the proposal changed after sign-off."), error)
        self.assertIn("they type `sign off PROP-3` at the prompt", error)
        self.assertNotEqual(now, UNSIGNED_HASH)

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
        self.assertIn("sign off", warning)
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
    def test_aidd_hash_prints_a_proposal_hash(self):
        with adopted_repo() as root:
            path = root / "proposals" / "PROP-3" / "proposal.md"
            path.parent.mkdir(parents=True)
            path.write_text(text(), encoding="utf-8")
            code, out = run_cli("hash", "proposals/PROP-3/proposal.md", "--worktree")
            self.assertEqual((code, out.strip()), (0, UNSIGNED_HASH))
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
                    self.assertIn("a proposal takes no flag", out)

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
