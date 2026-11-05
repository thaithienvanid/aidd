"""The arguments a person types: `--approvers`, `--specialist`, and a Spec or proposal named by its id."""

import contextlib
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd.cli import arguments


class ArgumentTests(unittest.TestCase):
    def test_approvers_split_on_commas_and_are_checked(self):
        self.assertEqual(arguments.approvers(["@a,@org/team", "email:me@example.com", "@a"]), ["@a", "@org/team", "email:me@example.com"])
        for bad in (["agent:claude"], ["@a b"], ["email:nobody"], ["@org/team/sub"], ["deploy[bot]"]):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "is not a person"):
                arguments.approvers(bad)

    def test_specialists_name_a_pool_and_its_people(self):
        self.assertEqual(
            arguments.specialists(["security=@org/sec, @alice", "privacy=@bob", "security=@carol"]),
            {"security": ["@org/sec", "@alice", "@carol"], "privacy": ["@bob"]},
        )
        for bad in ("security", "=@a", "security= "):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "POOL=WHO"):
                arguments.specialists([bad])

    def test_an_id_finds_its_one_spec_or_proposal(self):
        def item(rel: str, item_type: str, oid: str) -> None:
            path = Path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"---\ntype: {item_type}\nid: {oid}\ntitle: t\n---\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d):
            item("specs/SPEC-1.md", "spec", "SPEC-1")
            item("specs/checkout-limits.md", "spec", "SPEC-2")  # named for its topic, not its id
            item("proposals/PROP-3/proposal.md", "proposal", "PROP-3")
            item("specs/a.md", "spec", "SPEC-9")
            item("specs/b.md", "spec", "SPEC-9")
            self.assertEqual(arguments.spec_by_id("SPEC-1"), "specs/SPEC-1.md")
            self.assertEqual(arguments.spec_by_id("SPEC-2"), "specs/checkout-limits.md")
            self.assertEqual(arguments.spec_by_id("PROP-3"), "proposals/PROP-3/proposal.md")
            self.assertEqual(arguments.spec_by_id("specs/SPEC-1.md"), "specs/SPEC-1.md")  # a path stays a path
            with self.assertRaisesRegex(ValueError, "2 files have the id SPEC-9"):
                arguments.spec_by_id("SPEC-9")
            with self.assertRaisesRegex(ValueError, "no Spec has the id SPEC-4"):
                arguments.spec_by_id("SPEC-4")


if __name__ == "__main__":
    unittest.main()
