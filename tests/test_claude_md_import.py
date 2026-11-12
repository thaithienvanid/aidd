"""Claude Code reads a CLAUDE.md, a .claude/CLAUDE.md, or a CLAUDE.local.md in place of AGENTS.md, so aidd's section in the person's
file is one line that imports AGENTS.md. In each layout real files take, a person's file keeps its own bytes through a dry run,
init, a second init, and uninstall, and the block reaches Claude Code once (tests/engagement.py holds the layouts; upgrade is in
tests/test_claude_md_upgrade.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from engagement import FIRST_COMMAND, FILES, lay_out, options, read_at_start

from aidd import config
from aidd.setup import adoption, init_plan, instruction_imports, uninstalling


class ClaudeCodeReadsTheGuideAndTheBlockOnce(unittest.TestCase):
    def test_each_layout_through_dry_run_init_a_second_init_and_uninstall(self):
        claude = config.HARNESSES["claude-code"]
        for name, files in FILES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                lay_out(root, files)
                plan = init_plan.plan_init(root, options("claude-code"))
                self.assertTrue(all((root / rel).read_bytes() == text.encode() for rel, text in files.items()), "a dry run wrote")
                adoption.init(root, options("claude-code"))
                for rel in ("CLAUDE.md", ".claude/CLAUDE.md", "AGENTS.md"):
                    if rel in plan.writes:  # the dry run and the run are one computation: the same text, whatever the line endings
                        self.assertEqual(plan.writes[rel].replace("\r\n", "\n"), (root / rel).read_bytes().decode().replace("\r\n", "\n"), rel)
                text = read_at_start(root, claude)
                self.assertEqual(text.count(FIRST_COMMAND), 1, "the block reaches Claude Code once")
                self.assertIsNone(instruction_imports.problem(root, claude))
                for rel, before in files.items():  # a person's file keeps its own bytes first, and aidd never writes the local file
                    self.assertTrue((root / rel).read_bytes().startswith(before.encode()), rel)
                self.assertEqual("CLAUDE.local.md" in files, (root / "CLAUDE.local.md").exists())
                if "CLAUDE.md" in files and ".claude/CLAUDE.md" in files:
                    self.assertEqual((root / ".claude/CLAUDE.md").read_bytes(), files[".claude/CLAUDE.md"].encode(), "only the first project file is written")
                after = {rel: (root / rel).read_bytes() for rel in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", "AGENTS.md") if (root / rel).exists()}
                adoption.init(root, options("claude-code"))
                self.assertEqual(after, {rel: (root / rel).read_bytes() for rel in after}, "a second run changes nothing")
                uninstalling.uninstall(root, yes=True)
                for rel, before in files.items():  # a final newline is the one thing it may add to a file that had none
                    self.assertEqual((root / rel).read_bytes().decode().rstrip("\r\n"), before.rstrip("\r\n"), rel)
                self.assertEqual((root / "CLAUDE.md").exists(), "CLAUDE.md" in files, "uninstall removes a CLAUDE.md that init made")

    def test_a_link_to_agents_md_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (root / "CLAUDE.md").symlink_to("AGENTS.md")
            actions = adoption.init(root, options("claude-code"))
            self.assertTrue((root / "CLAUDE.md").is_symlink())
            self.assertTrue(any("CLAUDE.md (a link to AGENTS.md" in a for a in actions), actions)
            self.assertIsNone(instruction_imports.problem(root, config.HARNESSES["claude-code"]))


if __name__ == "__main__":
    unittest.main()
