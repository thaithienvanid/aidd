"""The arguments a person types: `--approvers`, `--specialist`, and a Spec or proposal named by its id."""

import contextlib
import tempfile
import unittest
from pathlib import Path

from helpers import AGENT_APPROVERS, ROOT  # noqa: F401  (puts src on the path)

from aidd.cli import arguments


class ArgumentTests(unittest.TestCase):
    def test_approvers_split_on_commas_and_are_checked(self):
        self.assertEqual(arguments.approvers(["@a,@org/team", "email:me@example.com", "@a"]), ["@a", "@org/team", "email:me@example.com"])
        for bad in (["agent:claude"], ["@a b"], ["email:nobody"], ["@org/team/sub"], ["deploy[bot]"]):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "is not a person"):
                arguments.approvers(bad)

    def test_an_approver_the_waivers_refuse_as_an_agent_is_refused_here_too(self):
        for bad in ([v] for v in AGENT_APPROVERS):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "is not a person"):
                arguments.approvers(bad)

    def test_a_whole_agent_name_is_no_approver_and_a_login_that_only_holds_a_word_is(self):
        """`--approvers` takes no `Name <email>`, so the whole-name rule reaches it through a bare login or a handle."""
        for bad in ("bot", "agent", "@bot", "@agent", "Bot", "traecode", "@claude"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "is not a person"):
                arguments.approvers([bad])
        for good in ("@cody", "@maya", "abbot", "agent-smith", "@bot-hansen"):
            with self.subTest(good=good):
                self.assertEqual(arguments.approvers([good]), [good])

    def test_the_refusal_says_a_login_is_a_way_out_only_where_a_login_is_taken(self):
        """A login or a handle that names an agent is refused, so a login is no way out for it; a value of no shape is told a login works, and one passes."""
        for refused, way, says_login in (
            ("claude", "email:you@example.com", False),
            ("@devin", "email:you@example.com", False),
            ("a b", "ab", True),
        ):
            with self.subTest(refused=refused), self.assertRaises(ValueError) as caught:
                arguments.approvers([refused])
            self.assertEqual("or a login" in str(caught.exception), says_login, str(caught.exception))
            self.assertEqual(arguments.approvers([way]), [way], "the way the message names passes")
            self.assertIn("`@handle`", str(caught.exception))

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
