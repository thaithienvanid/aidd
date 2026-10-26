"""The "Use all of aidd" recipe in docs/INSTALL.md: every `aidd` command and flag it names exists, its `/plugin` lines
install the plugins the marketplace lists, its settings block uses the keys and the marketplace source the managed
settings template already carries, and the README's install section links to it."""

import argparse
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, says

from aidd import config
from aidd.cli import parser
from aidd.setup import upgrading
from aidd.setup import claude_plugins
from aidd.setup import team_install
from aidd.config import harness_settings

ANCHOR = "use-all-of-aidd"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def recipe() -> str:
    text = read("docs/INSTALL.md")
    m = re.search(r"^### Use all of aidd\n(.*?)(?=^#{2,3} )", text, re.S | re.M)
    assert m, "docs/INSTALL.md has no '### Use all of aidd' section"
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


class UseAllRecipeTests(unittest.TestCase):
    def test_every_command_and_flag_the_recipe_names_exists(self):
        top = commands()
        named = aidd_commands(recipe())
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

    def test_init_uses_the_team_profile_the_team_and_the_plugin_path(self):
        init = next(c for c in aidd_commands(recipe()) if c.startswith("init "))
        args = parser.build_parser().parse_args(init.split())
        self.assertEqual(args.profile, "team")
        self.assertTrue(args.team)
        self.assertTrue(args.claude_plugins)  # the plugins carry Claude Code's part, so init writes no .claude/ files
        self.assertTrue(all(a.startswith("email:") for a in args.approvers))

    def test_the_plugin_lines_install_both_plugins_the_marketplace_lists(self):
        market = json.loads(read(".claude-plugin/marketplace.json"))
        lines = [line.strip() for b in blocks(recipe(), "text") for line in b.splitlines() if line.strip()]
        expected = [f"/plugin marketplace add {claude_plugins.MARKETPLACE_REPO}"]
        expected += [f"/plugin install {p['name']}@{market['name']}" for p in market["plugins"]]
        self.assertEqual(lines, [*expected, "/reload-plugins"])

    def test_the_strict_hook_level_is_one_the_config_accepts(self):
        yaml = blocks(recipe(), "yaml")
        self.assertEqual(len(yaml), 1)
        self.assertIn("level: strict", yaml[0])
        self.assertIn("strict", config.HOOK_LEVELS)

    def test_the_team_settings_use_the_documented_keys_and_source(self):
        settings = json.loads(blocks(recipe(), "json")[0])
        source = {"source": "github", "repo": claude_plugins.MARKETPLACE_REPO}
        managed = json.loads(read("templates/claude/managed-settings.json"))
        self.assertEqual(set(settings), {"extraKnownMarketplaces", "enabledPlugins"})
        self.assertEqual(managed["extraKnownMarketplaces"][harness_settings.MARKETPLACE]["source"], source)
        self.assertEqual(settings["extraKnownMarketplaces"], {harness_settings.MARKETPLACE: {"source": source}})
        self.assertEqual(settings["enabledPlugins"], {"aidd@aidd": True, "aidd-team@aidd": True})

    def test_the_fallback_note_tells_a_missing_cli_from_a_failed_install(self):
        text = recipe()
        self.assertIn("If the `claude` CLI is missing, install it.", text)
        self.assertIn("If an install failed, see the `failed` line above it.", text)

    def test_team_settings_make_claude_code_prompt_not_install(self):
        # Trusting the folder makes Claude Code ask each contributor to install the plugins; it installs nothing by itself.
        text = recipe()
        self.assertIn("Claude Code prompts each contributor who trusts the folder to install the two plugins", text)
        self.assertNotIn("then gets both plugins", text)

    def test_the_readme_install_section_links_to_the_recipe(self):
        readme = read("README.md")
        start = readme.index("## Get started")
        section = readme[start : readme.index("\n## ", start + 1)]
        self.assertIn(f"(docs/INSTALL.md#{ANCHOR})", section)


class OwnPracticeSkillTests(unittest.TestCase):
    """docs/HOW-TO.md's "add our own practice skill": the `aidd-` prefix warning holds only where `aidd upgrade` looks,
    `.claude/skills/` with the team's repository files installed."""

    def test_the_how_to_scopes_the_prefix_warning(self):
        text = read("docs/HOW-TO.md").split("**…add our own practice skill?**", 1)[1].split("\n**…", 1)[0]
        self.assertTrue(says(text, "`.claude/skills/`", "`aidd-`", "`aidd init --team`"), "the prefix warning holds only where the team's files are")

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
