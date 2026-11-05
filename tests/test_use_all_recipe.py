"""The install steps in docs/GUIDE.md and the README: every `aidd` command and flag the Install section names exists, and
the `/plugin` lines install the plugins the marketplace lists."""

import argparse
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.cli import parser
from aidd.setup import claude_plugins
from aidd.setup import team_install
from aidd.setup import upgrading


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def install_section() -> str:
    text = read("docs/GUIDE.md")
    m = re.search(r"^## Install\n(.*?)(?=^## )", text, re.S | re.M)
    assert m, "docs/GUIDE.md has no '## Install' section"
    return m.group(1)


def blocks(text: str, lang: str) -> list[str]:
    return re.findall(rf"^ *```{lang}\n(.*?)^ *```", text, re.S | re.M)


def commands() -> dict:
    return dict(next(a for a in parser.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices)


def aidd_commands(text: str) -> list[str]:
    """Each `aidd ...` the section names: inline code, and each line of its shell blocks."""
    inline = re.findall(r"`aidd ([a-z][^`]*)`", text)
    shell = [line.strip()[len("aidd ") :] for b in blocks(text, "sh") for line in b.splitlines() if line.strip().startswith("aidd ")]
    return inline + shell


def plugin_lines(text: str) -> list[str]:
    """The `/plugin` and `/reload-plugins` lines of the text blocks, without their trailing comments."""
    lines = [line.split("#", 1)[0].strip() for b in blocks(text, "text") for line in b.splitlines()]
    return [line for line in lines if line.startswith("/")]


class InstallStepsTests(unittest.TestCase):
    def test_every_command_and_flag_the_install_section_names_exists(self):
        top = commands()
        named = aidd_commands(install_section())
        self.assertIn("init", [c.split()[0] for c in named])
        self.assertIn("doctor", [c.split()[0] for c in named])
        bad = []
        for command in named:
            words = command.split()
            if words[0] not in top:
                bad.append((command, "no such command"))
                continue
            sub = top[words[0]]
            for word in words[1:]:
                flag = word.split("=")[0].rstrip(",;:.)")
                if flag.startswith("--") and flag not in sub._option_string_actions:
                    bad.append((command, flag))
        self.assertEqual(bad, [])

    def test_the_plugin_lines_install_the_plugins_the_marketplace_lists(self):
        market = json.loads(read(".claude-plugin/marketplace.json"))
        expected = [f"/plugin marketplace add {claude_plugins.MARKETPLACE_REPO}"]
        expected += [f"/plugin install {p['name']}@{market['name']}" for p in market["plugins"]]
        self.assertEqual(plugin_lines(install_section()), [*expected, "/reload-plugins"])
        readme_lines = plugin_lines(read("README.md").split("## Install", 1)[1].split("\n## ", 1)[0])
        self.assertEqual(readme_lines, expected)


class OwnPracticeSkillTests(unittest.TestCase):
    """The `aidd-` prefix warning holds only where `aidd upgrade` looks, `.claude/skills/` with the team's repository
    files installed."""

    def test_upgrade_names_an_aidd_prefixed_skill_only_beside_the_team_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            own = root / ".claude" / "skills" / "aidd-ledger" / "SKILL.md"
            own.parent.mkdir(parents=True)
            own.write_text("---\nname: aidd-ledger\n---\n", encoding="utf-8")
            self.assertFalse([a for a in upgrading.upgrade(root) if "aidd-ledger" in a])
            team_install.install_team(root, [], harnesses=["claude-code"])
            self.assertTrue([a for a in upgrading.upgrade(root) if "no longer shipped" in a and "aidd-ledger" in a])


class ProductDiscoveryTests(unittest.TestCase):
    def test_discovery_reads_five_to_eight_interviews(self):
        # A range a reviewer can check; "a few" said less.
        self.assertIn("Read five to eight interviews,", read("plugins/aidd-team/skills/product-discovery/SKILL.md"))


if __name__ == "__main__":
    unittest.main()


class RetiredFlowFileTests(unittest.TestCase):
    """A flow aidd retired leaves its file in every harness `aidd init --team` wrote it for, not only under `.claude/`:
    `aidd upgrade` names each one, so a person removes it."""

    def test_upgrade_names_a_retired_flow_in_every_harness_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            team_install.install_team(root, [], harnesses=["claude-code", "opencode", "codex", "grok"])
            left = [
                ".claude/commands/aidd-secure.md",
                ".opencode/commands/aidd-verify.md",
                ".agents/skills/aidd-secure/SKILL.md",
                ".grok/skills/aidd-verify/SKILL.md",
            ]
            for rel in left:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("a retired flow\n", encoding="utf-8")
            named = "\n".join(a for a in upgrading.upgrade(root) if "no longer shipped" in a)
            for rel in left:
                self.assertIn(rel.removesuffix("/SKILL.md"), named, rel)
            self.assertNotIn(".agents/skills/aidd ", named + " ", "the vendored skill is aidd's own, never a retired flow")
