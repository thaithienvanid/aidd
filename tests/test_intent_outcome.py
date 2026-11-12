"""An Intent states its `outcome`, in a body of five sections, and a person's agreement covers the whole body.

The invariants: an Intent holds `outcome`, never `goal`; a proposal keeps its own `goal`; `aidd new intent` writes the five sections with
only the two optional ones beside them; and every line of an agreed Intent's body is covered, so text added under any heading,
`## Learn` too, reads as a change. Each table is the input space, with its boundary rows."""

import contextlib
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import git

from test_intents import RepoCase
from test_workitems import intent, spec

from aidd.cli import app
from aidd.setup import adoption
from aidd.workitems import intents, spec_file

PATH = "product/intents/INTENT-1.md"
FRONT = "---\ntype: intent\nid: INTENT-1\ntitle: Book a table\n{key}: A guest books a table in under a minute.\n---\n\nbody\n"
FIVE = ("## Problem", "## Proposed outcome", "## Affected users and systems", "## Constraints", "## Open questions")
OPTIONAL = ("## Plan", "## Out of scope")


def new_intent_text() -> str:
    """The file `aidd new intent` writes in a repository that adopted aidd, read back from the disk."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
        with contextlib.chdir(root), contextlib.redirect_stdout(io.StringIO()):
            code = app.main(["new", "intent", "Book a table"])
        assert code == 0, code
        return (root / PATH).read_text(encoding="utf-8")


class TheKey(unittest.TestCase):
    def test_an_intent_holds_outcome_and_no_longer_takes_goal(self):
        _, _, errors = spec_file.load_object(FRONT.format(key="outcome"), PATH)
        self.assertEqual(errors, [])
        _, _, errors = spec_file.load_object(FRONT.format(key="goal"), PATH)
        self.assertTrue(errors, "a file that says `goal` is no Intent")


@unittest.skipUnless(shutil.which("git"), "git is required")
class TheTemplate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = new_intent_text()
        cls.front, cls.body, cls.errors = spec_file.load_object(cls.text, PATH)
        cls.headings = re.findall(r"(?m)^## .+?$", cls.body)

    def test_the_file_is_a_valid_intent_with_an_outcome_and_no_goal(self):
        self.assertEqual(self.errors, [])
        self.assertIn("outcome", self.front)
        self.assertNotIn("goal", self.front)

    def test_it_opens_with_the_five_sections_in_order_and_adds_only_the_optional_ones(self):
        self.assertEqual(tuple(self.headings[:5]), FIVE)
        self.assertLessEqual(set(self.headings[5:]), set(OPTIONAL), self.headings)


class TheBody(unittest.TestCase):
    """The agreed body is compared whole: no section is one an agent keeps writing."""

    DATA = {"type": "intent", "id": "INTENT-1", "title": "t", "outcome": "o"}
    BASE = "## Problem\n\nA.\n\n## Constraints\n\nNo invoices.\n"

    def changed(self, now: str, then: str | None = None) -> bool:
        return "body" in intents.approved_changes(self.DATA, self.DATA, self.BASE if then is None else then, now)

    def test_text_under_any_heading_is_a_change_the_old_learn_section_too(self):
        cases = {
            "nothing": (self.BASE, False),
            "the line endings converted": (self.BASE.replace("\n", "\r\n"), False),
            "a Learn section written at the end": (self.BASE + "\n## Learn\n\nIt held.\n", True),
            "a Problem line added": (self.BASE.replace("A.", "A. B."), True),
            "an Open questions section written at the end": (self.BASE + "\n## Open questions\n\n- [ ] When?\n", True),
            "the body emptied": ("", True),
        }
        for name, (now, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.changed(now), want)
        self.assertTrue(self.changed(self.BASE + "\n## Learn\n\nNew.\n", then=self.BASE + "\n## Learn\n\nOld.\n"))


class TheOutcomeSentenceAndTheOutcomeBlock(RepoCase):
    """A Spec's `outcome` is a block and an Intent's is a sentence, so a check of the whole repository reads the block only where it is one."""

    def test_validate_runs_over_an_intent_beside_a_spec_with_a_release_block(self):
        self.write("product/intents/INTENT-1.md", intent("INTENT-1", "Calls fall by half by 2027-01-01"))
        self.write("specs/SPEC-1.md", spec("SPEC-1", "done", extra='route: major\noutcome: {released_on: "2026-11-01"}\n'))
        _, warnings = self.findings()
        self.assertTrue(any("SPEC-1.md: released major change has no outcome.observe_result" in w for w in warnings), warnings)
        self.assertFalse(any("INTENT-1.md" in w and "outcome." in w for w in warnings), warnings)
