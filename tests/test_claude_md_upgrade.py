"""`aidd upgrade` turns a copy of the block that an older aidd wrote into a person's CLAUDE.md into the one line that imports
AGENTS.md, keeps the person's text and line endings, and a second upgrade changes nothing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from engagement import OURS, options

from aidd.setup import adoption, upgrading


class UpgradeTurnsACopyIntoTheImport(unittest.TestCase):
    def test_upgrade_turns_an_old_copy_into_the_import_and_a_second_upgrade_changes_nothing(self):
        old = "<!-- aidd -->\n## Change control\n\nThis repository uses aidd. Old words.\n\n### Verification\n\nRun `aidd test`.\n<!-- /aidd -->\n"
        for name, text in {
            "a copy after the person's text": OURS + "\n" + old + "\n## After\n\nMore.\n",
            "a copy in CRLF": (OURS + "\n" + old).replace("\n", "\r\n"),
            "a copy and the person's own import": "@AGENTS.md\n\n" + old,
        }.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                adoption.init(root, options("claude-code"))
                (root / "CLAUDE.md").write_bytes(text.encode())
                upgrading.upgrade(root, yes=True)
                after = (root / "CLAUDE.md").read_bytes()
                self.assertNotIn(b"Old words", after)
                self.assertEqual(after.count(b"@AGENTS.md"), 1)
                self.assertTrue(after.startswith(text.split("<!-- aidd -->")[0].rstrip().encode()), "the person's text above stays")
                if "After" in text:
                    self.assertTrue(after.endswith(b"\n## After\n\nMore.\n"))
                upgrading.upgrade(root, yes=True)
                self.assertEqual((root / "CLAUDE.md").read_bytes(), after)


if __name__ == "__main__":
    unittest.main()
