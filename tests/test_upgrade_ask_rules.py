"""`aidd upgrade --only ask-rules` writes each coding agent's ask rules and no other file.

The invariant: with `--only ask-rules`, the files an upgrade would otherwise refresh (the vendored skill, the text between
aidd's marks, the config's `aidd_version`, the CI pins) stay byte for byte, and the ask rules come up to date exactly as a full
upgrade writes them. After a Spec approval the loop runs it to add the `Edit` asks for the Spec's frozen tests.
"""

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import git

from aidd import __version__
from aidd.config import harness_settings
from aidd.setup import adoption, upgrading

LOWER = "risks:\n  rules:\n    - {action: git.tag.create, level: allow}\n"


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and ".git/" not in p.as_posix()}


class UpgradeOnlyTheAskRules(unittest.TestCase):
    def repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code", "copilot"]))
        # Everything a full upgrade would refresh is out of date: the skill and the marked text.
        (root / adoption.SKILL_REL / "SKILL.md").write_text("an older skill\n", encoding="utf-8")
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace("aidd", "AIDD", 1), encoding="utf-8")
        cfg = root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + LOWER, encoding="utf-8")
        return root

    def test_only_the_ask_rules_change_and_a_full_upgrade_would_change_more(self):
        root = self.repo()
        before = tree(root)
        dry = upgrading.upgrade(root, only="ask-rules")
        self.assertEqual(tree(root), before, "a dry run writes nothing")
        self.assertTrue([a for a in dry if a.startswith("would write ask rules into")], dry)
        done = upgrading.upgrade(root, yes=True, only="ask-rules")
        after = tree(root)
        changed = sorted(k for k in after if before.get(k) != after[k])
        self.assertEqual(changed, [".aidd/harness-rules.json", ".claude/settings.json", ".vscode/settings.json"], done)
        self.assertEqual(
            upgrading.upgrade(root, only="ask-rules"),
            [f"nothing to update: this repository's ask rules already match aidd {__version__}"],
        )
        full = upgrading.upgrade(root, ref="v1.0.0")
        self.assertTrue([a for a in full if "the skill" in a or "marks" in a], "a full upgrade still has the rest to do")

    def test_the_rules_are_the_ones_a_full_upgrade_writes(self):
        narrow, whole = self.repo(), self.repo()
        upgrading.upgrade(narrow, yes=True, only="ask-rules")
        upgrading.upgrade(whole, ref="v1.0.0", yes=True)
        for rel in (".claude/settings.json", ".vscode/settings.json", ".aidd/harness-rules.json"):
            self.assertEqual((narrow / rel).read_bytes(), (whole / rel).read_bytes(), rel)

    def test_a_flag_that_means_nothing_beside_it_or_names_no_part_is_refused(self):
        root = self.repo()
        for kwargs in ({"only": "skill"}, {"only": "ask-rules", "ref": "v1.0.0"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                upgrading.upgrade(root, **kwargs)

    def test_the_command_takes_the_flag_as_a_person_types_it(self):
        root = self.repo()
        with (
            contextlib.chdir(root),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(harness_settings, "user_plugins_enabled", return_value=set()),
        ):
            code, dry = helpers.run_cli("upgrade", "--only", "ask-rules")
            self.assertEqual(code, 0, dry)
            self.assertIn("would write ask rules into .claude/settings.json", dry)
            self.assertIn("dry run: nothing changed", dry)
            code, said = helpers.run_cli("upgrade", "--only", "ask-rules", "--yes")
            self.assertEqual(code, 0, said)
            self.assertNotIn("the skill", said)
            self.assertNotIn("self-update", said, "the CLI and the plugins are not the ask rules")
        typo = helpers.aidd_subprocess("upgrade", "--only", "ask-rule", cwd=root)
        self.assertEqual(typo.returncode, 2)
        self.assertIn("Did you mean `ask-rules`", typo.stderr + typo.stdout)
        self.assertIn("ask-rules", typo.stderr + typo.stdout)


if __name__ == "__main__":
    unittest.main()
