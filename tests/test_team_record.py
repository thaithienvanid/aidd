"""`.aidd/team-files.json`: `aidd upgrade` and `aidd uninstall` remove the team files aidd wrote and no longer writes, and
only while they hold what aidd wrote. No role or flow has left the team yet, so the tests retire a sample role and
a sample flow, which the record then names."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, run_cli

from aidd import config
from aidd.setup import team_install, team_record

ARGS = ("--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "true", "--aidd-team")
HARNESSES = ("--harness", "claude-code", "--harness", "codex", "--harness", "opencode")
SAMPLE_ROLE, SAMPLE_FLOW = "sample-role", "sample-flow"


def retire_samples(case: unittest.TestCase) -> None:
    """For this test, a role and a flow have left the team."""
    for name, value in (("RETIRED_ROLES", (SAMPLE_ROLE,)), ("RETIRED_FLOWS", (SAMPLE_FLOW,))):
        patch = mock.patch.object(team_record, name, value)
        patch.start()
        case.addCleanup(patch.stop)


def write_retired(root: Path) -> list[str]:
    """Write each retired role's and flow's file where aidd wrote it, from a live one's text, and record it as aidd does.
    Their paths come from the same per-harness path functions."""
    every = {rel: next(iter(texts)) for rel, texts in team_install.team_file_variants().items()}
    record = team_record.read_record(root)
    written = []
    for live in every:
        if not (root / live).is_file():
            continue  # a harness this repository did not wire
        text = (root / live).read_text(encoding="utf-8")
        for rel in sorted(team_record.retired_paths({live: text})):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
            record[rel] = team_record.digest(text)
            written.append(rel)
    (root / config.TEAM_FILES_FILE).write_text(json.dumps({"files": record}), encoding="utf-8")
    return written


@unittest.skipUnless(shutil.which("git"), "git is required")
class RetiredTeamFilesTests(unittest.TestCase):
    def setUp(self):
        retire_samples(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        env = mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"})
        env.start()
        self.addCleanup(env.stop)
        code, out = run_cli("init", str(self.root), *ARGS, *HARNESSES)
        self.assertEqual(code, 0, out)

    def upgrade(self) -> str:
        code, out = run_cli("upgrade", str(self.root), "--yes")
        self.assertEqual(code, 0, out)
        return out

    def test_init_records_each_team_file_it_wrote(self):
        record = team_record.read_record(self.root)
        self.assertTrue(record)
        for rel, sha in record.items():
            self.assertEqual(team_record.digest((self.root / rel).read_text(encoding="utf-8")), sha, rel)

    def test_an_upgrade_removes_a_retired_file_that_is_unchanged_and_keeps_an_edited_one(self):
        retired = write_retired(self.root)
        self.assertTrue(any(SAMPLE_ROLE in r for r in retired) and any(SAMPLE_FLOW in r for r in retired), retired)
        edited = self.root / ".claude" / "commands" / f"aidd-{SAMPLE_FLOW}.md"
        edited.write_text("aidd wrote it, and I changed it\n", encoding="utf-8")
        out = self.upgrade()
        self.assertEqual([r for r in retired if (self.root / r).exists() and r != edited.relative_to(self.root).as_posix()], [])
        self.assertTrue(edited.is_file())
        self.assertIn(f"kept .claude/commands/aidd-{SAMPLE_FLOW}.md", out)
        self.assertFalse((self.root / ".agents" / "skills" / f"aidd-{SAMPLE_FLOW}").exists(), "an emptied folder goes too")
        self.assertNotIn(f".claude/commands/aidd-{SAMPLE_FLOW}.md", team_record.read_record(self.root))

    def test_uninstall_leaves_no_team_file_and_no_record(self):
        write_retired(self.root)
        code, out = run_cli("uninstall", str(self.root), "--yes")
        self.assertEqual(code, 0, out)
        every = team_install.team_file_variants()
        left = [rel for rel in [*every, *team_record.retired_paths({r: next(iter(t)) for r, t in every.items()})] if (self.root / rel).exists()]
        self.assertEqual(left, [])
        self.assertFalse((self.root / config.TEAM_FILES_FILE).exists())


@unittest.skipUnless(shutil.which("git"), "git is required")
class TheRecordIsDataTests(unittest.TestCase):
    """The record is committed repository text: a path in it counts only when aidd writes it or once did, inside the
    repository, and through no link. Nothing outside the repository and nothing aidd never wrote is ever removed."""

    def setUp(self):
        retire_samples(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.outside = base / "repo", base / "outside"
        self.root.mkdir()
        self.outside.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        env = mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"})
        env.start()
        self.addCleanup(env.stop)
        code, out = run_cli("init", str(self.root), *ARGS, *HARNESSES)
        self.assertEqual(code, 0, out)

    def plant(self, entries: dict[str, str]) -> None:
        record = team_record.read_record(self.root)
        record.update({rel: team_record.digest(text) for rel, text in entries.items()})
        (self.root / config.TEAM_FILES_FILE).write_text(json.dumps({"files": record}), encoding="utf-8")

    def test_a_planted_path_outside_or_unknown_is_ignored_and_nothing_goes(self):
        target = self.outside / "outside.txt"
        target.write_text("keep me\n", encoding="utf-8")
        mine = self.root / "src" / "keep.py"
        mine.parent.mkdir()
        mine.write_text("print('mine')\n", encoding="utf-8")
        self.plant({"../outside/outside.txt": "keep me\n", str(target): "keep me\n", "src/keep.py": "print('mine')\n"})
        for verb in ("upgrade", "uninstall"):
            code, out = run_cli(verb, str(self.root), "--yes")
            self.assertEqual(code, 0, out)
            self.assertTrue(target.is_file(), verb)
            self.assertTrue(mine.is_file(), verb)
            if verb == "upgrade":
                self.assertIn("ignored src/keep.py", out)
                self.plant({"../outside/outside.txt": "keep me\n", str(target): "keep me\n", "src/keep.py": "print('mine')\n"})

    def test_a_link_at_a_team_folder_is_never_followed(self):
        # A retired flow's folder that is a link to a folder outside, holding a file with the hash the record names.
        (self.outside / "SKILL.md").write_text("**You are the lead.**\n", encoding="utf-8")
        folder = self.root / ".agents" / "skills" / f"aidd-{SAMPLE_FLOW}"
        folder.parent.mkdir(parents=True, exist_ok=True)
        folder.symlink_to(self.outside, target_is_directory=True)
        self.plant({f".agents/skills/aidd-{SAMPLE_FLOW}/SKILL.md": "**You are the lead.**\n"})
        for verb in ("upgrade", "uninstall"):
            code, out = run_cli(verb, str(self.root), "--yes")
            self.assertEqual(code, 0, out)
            self.assertTrue((self.outside / "SKILL.md").is_file(), verb)

    def test_the_record_is_never_written_through_a_link(self):
        (self.root / config.TEAM_FILES_FILE).unlink()
        decoy = self.outside / "record.json"
        decoy.write_text("decoy\n", encoding="utf-8")
        (self.root / config.TEAM_FILES_FILE).symlink_to(decoy)
        code, out = run_cli("upgrade", str(self.root), "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(decoy.read_text(encoding="utf-8"), "decoy\n")


if __name__ == "__main__":
    unittest.main()
