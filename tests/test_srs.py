"""The generated SRS (`aidd new srs <INTENT-ID>`): ISO/IEC/IEEE 29148's outline filled from an Intent, its phases, and
the Specs at or past Spec approval, each requirement linking its test and its commit. Derived, never hand-kept."""

import os
import re
import unittest

from helpers import SAMPLE_SPEC, RepoTemplateCase, git, make_repo, run_cli

from aidd.workitems import srs

# Two phases, in order; SPEC-6 is a slice with no Spec file yet.
PHASES = (
    "phases:\n"
    "  - id: P1\n    name: Cart\n    slices: [{id: SPEC-1, title: Totals}, {id: SPEC-2, title: Codes}]\n"
    "  - id: P2\n    name: Payment\n    slices: [{id: SPEC-3, title: Pay}, {id: SPEC-6, title: Refunds}]\n"
)
INTENT = (
    "---\ntype: intent\nid: INTENT-1\ntitle: Faster checkout\ngoal: Checkout takes under 60 seconds\nowner_team: shop\n"
    + PHASES
    + "---\n\n## Out of scope\n\nGift cards.\n"
)
ONE_PHASE = "---\ntype: intent\nid: INTENT-2\ntitle: Receipts\ngoal: g\nslices: [{id: SPEC-5, title: Email it}]\n---\n"
VIEW = ".aidd/views/srs-{name}.md"


def spec_text(sid: str, parent: str, status: str, acceptance: str = "", covers: str = "[A1]") -> str:
    text = SAMPLE_SPEC.replace("SPEC-220", sid).replace("\nroute: ", f'\nstatus: "{status}"\nparent: {parent}\nroute: ', 1)
    text = text.replace("covers: [A1]", f"covers: {covers}")
    if acceptance:
        text = text.replace("- A1: Given a cart of 100.00 and a 10% code, when the shopper applies it, then the total is 90.00.", acceptance)
    return text


class SrsCase(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def build(self) -> None:
        """INTENT-1 holds phase P1 (SPEC-1 approved with a covered and an uncovered item, SPEC-2 a draft) and phase P2
        (SPEC-3 done, SPEC-6 a slice with no Spec file); INTENT-2 lists one phase's slices directly (SPEC-5)."""
        self.write("specs/INTENT-1.md", INTENT)
        self.write("specs/INTENT-2.md", ONE_PHASE)
        two = "- A1: Given a cart of two items, when I view it, then the total is the sum.\n- A2: Given a code | a cart, then the pipe stays in its cell."
        self.write("specs/SPEC-1.md", spec_text("SPEC-1", "INTENT-1", "approved", two))
        self.write("specs/SPEC-2.md", spec_text("SPEC-2", "INTENT-1", "draft"))
        self.write("specs/SPEC-3.md", spec_text("SPEC-3", "INTENT-1", "done"))
        self.write("specs/SPEC-4.md", spec_text("SPEC-4", "INTENT-9", "approved"))  # under no Intent in the repository
        self.write("specs/SPEC-5.md", spec_text("SPEC-5", "INTENT-2", "approved"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: SPEC-1 totals")

    def generate(self, target: str) -> str:
        code, out = run_cli("new", "srs", target)
        self.assertEqual(code, 0, out)
        return (self.root / VIEW.format(name=target.lower())).read_text(encoding="utf-8")


class SrsContentTests(SrsCase):
    def setUp(self):
        super().setUp()
        self.build()
        self.head = git(self.root, "rev-parse", "HEAD")[:10]

    def rows(self, text: str) -> dict[str, list[str]]:
        return {
            cells[1]: cells[2:-1]
            for line in text.splitlines()
            if line.startswith("| ") and "/A" in line
            for cells in [[c.strip() for c in line.replace("\\|", "\0").split("|")]]
        }

    def test_the_outline_and_each_requirement(self):
        text = self.generate("INTENT-1")
        for heading in ("## 1. Introduction", "### 1.1 Purpose", "### 1.2 Scope", "## 2. References", "### 3.2 Functional requirements", "## 4. Verification"):
            self.assertIn(heading, text)
        self.assertIn("Checkout takes under 60 seconds", text)  # the purpose is the Intent's goal
        self.assertIn("Gift cards.", text)
        rows = self.rows(text)
        self.assertEqual(sorted(rows), ["SPEC-1/A1", "SPEC-1/A2", "SPEC-3/A1"])
        a1, a2, third = rows["SPEC-1/A1"], rows["SPEC-1/A2"], rows["SPEC-3/A1"]
        self.assertIn("python3 -m unittest tests.test_discount", a1[2])  # the test that covers it
        self.assertIn(self.head, a1[3])  # the newest commit that names SPEC-1
        self.assertEqual(a1[1], "approved")
        self.assertIn("no test command covers it", a2[2])  # a gap is shown, never hidden
        self.assertEqual(third[3], "none yet")  # no commit names SPEC-3

    def test_a_pipe_in_a_statement_stays_in_its_cell(self):
        row = next(line for line in self.generate("INTENT-1").splitlines() if line.startswith("| SPEC-1/A2"))
        self.assertEqual(row.replace("\\|", "").count("|"), 6)

    def test_the_verification_counts_and_names_the_gaps(self):
        text = self.generate("INTENT-1")
        self.assertIn("3 requirements from 2 Specs. 2 have a test command that covers them, and 2 link a commit.", text)
        self.assertIn("No test command covers SPEC-1/A2.", text)
        self.assertIn("not evidence", text)

    def test_work_not_yet_approved_is_listed_and_not_counted(self):
        text = self.generate("INTENT-1")
        appendix = text.split("## Appendix A.")[1]
        self.assertIn("SPEC-2", appendix)
        self.assertIn("(draft)", appendix)
        self.assertNotIn("SPEC-2/A", text)

    def test_the_scope_is_the_target_and_what_is_below_it(self):
        cases = [
            # (target, the Specs whose requirements it holds)
            ("INTENT-1", {"SPEC-1", "SPEC-3"}),
            ("INTENT-2", {"SPEC-5"}),
            ("intent-2", {"SPEC-5"}),  # an id in any case
            ("product", {"SPEC-1", "SPEC-3", "SPEC-4", "SPEC-5"}),  # every Spec, even one under no Intent here
        ]
        for target, expected in cases:
            with self.subTest(target=target):
                self.assertEqual({r.split("/")[0] for r in self.rows(self.generate(target))}, expected)

    def test_a_spec_and_an_unknown_id_are_refused(self):
        for target in ("SPEC-1", "INTENT-99", "P1"):  # a phase id is not a work item
            with self.subTest(target=target):
                code, out = run_cli("new", "srs", target)
                self.assertEqual(code, 2, out)
                self.assertIn(target, out)

    def test_requirements_are_grouped_by_phase_in_the_intents_order(self):
        text = self.generate("INTENT-1")
        requirements = text.split("### 3.2 Functional requirements")[1].split("## 4.")[0]
        groups = [line for line in requirements.splitlines() if line.startswith("#### ")]
        self.assertEqual(len(groups), 2, groups)
        self.assertEqual(groups, ["#### Phase 1 · Cart", "#### Phase 2 · Payment"], "a phase reads by its place, never its id")
        self.assertLess(requirements.index("SPEC-1/A1"), requirements.index(groups[1]))
        self.assertGreater(requirements.index("SPEC-3/A1"), requirements.index(groups[1]))
        # The perspective table names each phase with the count of its Specs in this document.
        perspective = {
            cells[1]: cells[2] for line in text.splitlines() if re.match(r"\| Phase [0-9] ", line) for cells in [[c.strip() for c in line.split("|")]]
        }
        self.assertEqual(perspective, {"Phase 1 · Cart": "1", "Phase 2 · Payment": "1"})
        # A Spec whose Intent lists no phase of it sits in no phase.
        product = self.generate("product").split("### 3.2 Functional requirements")[1].split("## 4.")[0]
        last = [line for line in product.splitlines() if line.startswith("#### ")][-1]
        self.assertGreater(product.index("SPEC-4/A1"), product.index(last))
        self.assertFalse(any(p in last for p in ("P1", "P2", "INTENT-2")), last)

    def test_it_is_derived_so_generating_again_follows_the_work_items(self):
        before = self.generate("INTENT-1")
        self.write("specs/SPEC-2.md", spec_text("SPEC-2", "INTENT-1", "in_progress"))
        after = self.generate("INTENT-1")
        self.assertNotIn("SPEC-2/A", before)
        self.assertIn("SPEC-2/A1", after)
        self.assertEqual(after, self.generate("INTENT-1"), "the same work items give the same document")

    def test_it_lives_where_git_ignores_it(self):
        self.generate("INTENT-1")
        self.assertEqual(git(self.root, "status", "--porcelain", "--", ".aidd"), "")


class SrsPartsTests(unittest.TestCase):
    def test_acceptance_items_by_id_once_each(self):
        text = "## Acceptance\n\n- A1: first\n- **A2**: second\n* A1: again\n\n## Design\n\nA4: not here\n"
        self.assertEqual(srs.acceptance_items(text), [("A1", "first"), ("A2", "second")])

    def test_a_table_row_loses_its_cell_delimiters(self):
        self.assertEqual(srs.acceptance_items("## Acceptance\n\n| A1 | Given a cart | Then it totals |\n"), [("A1", "Given a cart; Then it totals")])

    def test_badly_shaped_commands_cover_nothing(self):
        cases = [
            ({"tests": {"commands": [{"name": "t", "covers": "A10", "command": ["pytest"]}]}}, "no test command covers it"),
            ({"tests": {"commands": "pytest"}}, "no test command covers it"),
            ({"tests": {"commands": [{"name": "t", "covers": ["A1"], "command": "pytest -q"}]}}, "`t`: `pytest -q`"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(srs._tests(data, "A1"), expected)

    def test_a_template_placeholder_is_not_a_fact(self):
        self.assertEqual(srs._real("TODO: a team", "", None, "shop"), ["shop"])


if __name__ == "__main__":
    unittest.main()
