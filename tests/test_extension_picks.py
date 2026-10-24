"""Ecosystem extensions on demand (B11): the registry curates installable plugins for each role, pinned with evidence,
and `aidd extensions suggest` names the ones that fit a repository's stacks with the line a person runs. aidd itself
never installs one."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git

from aidd import knowledge
from aidd.knowledge import extension_picks, team_registry


def installable() -> list[tuple[str, dict]]:
    return [(role, e) for role, r in team_registry.roles()["roles"].items() for e in r.get("extends", []) if e.get("install")]


class RegistryTests(unittest.TestCase):
    def test_every_install_line_names_a_known_marketplace_and_a_pin(self):
        for role, e in installable():
            with self.subTest(role=role, name=e["name"]):
                self.assertIn(e["install"].rsplit("@", 1)[1], extension_picks.MARKETPLACES)
                self.assertTrue(e.get("pin"))
                self.assertEqual(e["kind"], "plugin")

    def test_an_official_tier_is_anthropics_own_source(self):
        for role, e in installable():
            if e["tier"] == "official":
                with self.subTest(role=role, name=e["name"]):
                    self.assertTrue(e["source"].startswith("https://github.com/anthropics/"), e["source"])

    def test_the_roles_get_their_ecosystem(self):
        named = {(role, e["name"]) for role, e in installable()}
        for pair in [
            ("developer", "pyright-lsp"),
            ("reviewer", "typescript-lsp"),
            ("security-engineer", "claude-security"),
            ("product-manager", "product-management"),
            ("product-designer", "design"),
            ("developer", "data"),
            ("compliance-analyst", "legal"),
        ]:
            self.assertIn(pair, named)


class SuggestTests(unittest.TestCase):
    def test_a_language_server_fits_only_its_stack(self):
        rows = {r["name"]: r for r in knowledge.suggestions({"Python"})}
        self.assertEqual(set(rows["pyright-lsp"]["roles"]), {"developer", "reviewer"})  # one line for both roles
        self.assertNotIn("gopls-lsp", rows)
        self.assertIn("claude-security", rows)  # names no stack: fits any repository
        self.assertNotIn("pyright-lsp", {r["name"] for r in knowledge.suggestions(set())})

    def test_one_role(self):
        self.assertEqual({r for row in knowledge.suggestions({"Go"}, "reviewer") for r in row["roles"]}, {"reviewer"})

    def test_the_text_says_aidd_installs_none_and_adds_each_marketplace_once(self):
        rows = knowledge.suggestions({"Go"})
        text = knowledge.suggestions_text(rows, {"Go"})
        self.assertIn("aidd installs none of them", text)
        self.assertEqual(text.count("claude plugin marketplace add anthropics/knowledge-work-plugins"), 1)
        self.assertNotIn("marketplace add anthropics/claude-plugins-official", text)
        self.assertIn("claude plugin install gopls-lsp@claude-plugins-official", text)


@unittest.skipUnless(shutil.which("git"), "git is required")
class CommandTests(unittest.TestCase):
    def test_suggest_reads_the_repository_and_prints_json(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        git(root, "init", "-q", "-b", "main")
        (root / "go.mod").write_text("module example.com/x\n\ngo 1.24\n", encoding="utf-8")
        run = aidd_subprocess("extensions", "suggest", "--json", cwd=root)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        self.assertEqual(out["stacks"], ["Go"])
        self.assertIn("claude plugin install gopls-lsp@claude-plugins-official", [r["install"] for r in out["suggestions"]])
        self.assertNotEqual(aidd_subprocess("extensions", "suggest", "--role", "nobody", cwd=root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
