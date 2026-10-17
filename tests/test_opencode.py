"""The aidd-team files aidd generates for OpenCode V2: native `permissions:` front matter for the role
subagents, the flow commands as `.opencode/commands/*.md`, and the docs that tell an adopter how to wire
the aidd MCP server. The formats are verified against OpenCode V2's documentation: agents
(https://opencode.ai/v2/docs/agents, the native `permissions:` rule list, not the V1 `permission`/`tools`/`prompt`)
and commands (https://opencode.ai/v2/docs/commands, Markdown with `description` front matter)."""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, opencode_effect, opencode_permissions

from aidd import knowledge
from aidd.setup import harness_text, upgrading
from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.setup import team_install
from aidd.config import baseline, harnesses
from aidd.kernel import globs, resources


class OpenCodeAgentFilesTests(unittest.TestCase):
    """`repo.team_files(["opencode"])` emits the role agents in V2-native front matter."""

    def files(self, **models):
        return team_install.team_files(["opencode"], claude_files=False, models=models or {})

    def test_every_role_agent_uses_v2_front_matter(self):
        out = self.files()
        team = resources.data_dir("team")
        for src in sorted((team / "agents").glob("*.md")):
            rel = f".opencode/agents/aidd-{src.stem}.md"
            with self.subTest(rel):
                text = out[rel]
                self.assertRegex(text, r"^---\ndescription: ")
                self.assertIn("\nmode: subagent\n", text)
                for legacy in ("\npermission:\n", "\ntools:\n", "\nprompt:\n"):
                    self.assertNotIn(legacy, text)
                rules = opencode_permissions(text)
                self.assertEqual({"edit", "shell"}, {r["action"] for r in rules})
                for rule in rules:
                    self.assertEqual(set(rule), {"action", "resource", "effect"})

    def test_each_role_gets_the_rules_its_tools_call_for(self):
        """The last matching rule decides (https://opencode.ai/v2/docs/agents): a role without Write or Edit cannot
        edit, a role without Bash cannot run a command, and a role with Bash is asked before each one."""
        out = self.files()
        team = resources.data_dir("team")
        for src in sorted((team / "agents").glob("*.md")):
            front, _ = team_install._front_and_body(src.read_text(encoding="utf-8"))
            tools = {t.strip() for t in front["tools"].split(",")}
            with self.subTest(src.stem):
                rules = opencode_permissions(out[f".opencode/agents/aidd-{src.stem}.md"])
                for rule in rules:
                    self.assertIn(rule["effect"], ("allow", "ask", "deny"))
                writes = bool(tools & {"Write", "Edit"})
                self.assertEqual(opencode_effect(rules, "edit", "src/app.py"), "allow" if writes else "deny")
                self.assertEqual(opencode_effect(rules, "shell", "git push"), "ask" if "Bash" in tools else "deny")

    def test_reviewer_roles_are_read_only(self):
        out = self.files()
        for role in ("reviewer", "verifier"):
            with self.subTest(role):
                rules = opencode_permissions(out[f".opencode/agents/aidd-{role}.md"])
                for path in ("src/app.py", "specs/SPEC-1.md", ".aidd/config.yaml"):
                    self.assertEqual(opencode_effect(rules, "edit", path), "deny")
                self.assertNotEqual(opencode_effect(rules, "shell", "rm -rf src"), "allow")

    def test_a_role_without_bash_is_denied_the_shell(self):
        # No shipped role lacks Bash today, so the rule is checked on a role made for the test.
        _, text = team_install._native_agent("opencode", "aidd-x", {"description": "x", "tools": "Read, Grep, Glob"}, "body")
        rules = opencode_permissions(text)
        self.assertEqual(opencode_effect(rules, "shell", "ls"), "deny")
        self.assertEqual(opencode_effect(rules, "edit", "a.md"), "deny")

    def test_the_bodies_name_opencode_enforcement_not_a_missing_hook(self):
        developer = self.files()[".opencode/agents/aidd-developer.md"]
        body = developer.split("\n---\n\n", 1)[1]
        self.assertNotIn("no hook checks", body)
        self.assertIn("permissions", body)
        # The other harnesses keep the advisory that names the missing hook.
        codex = team_install.team_files(["codex"], claude_files=False)[".codex/agents/aidd-developer.toml"]
        self.assertIn("no hook checks", codex)

    def test_the_configured_model_stays_provider_slash_model(self):
        out = self.files(execution="anthropic/claude-sonnet-5", reviewer="openai/gpt-6-astra")
        developer = out[".opencode/agents/aidd-developer.md"]
        self.assertIn("\nmodel: anthropic/claude-sonnet-5\n", developer)
        # No variant is invented: the front matter keeps the role's provider/model as configured.
        self.assertNotRegex(developer.split("\n---\n", 1)[0], r"model: [^\n]+#")
        self.assertIn("\nmodel: openai/gpt-6-astra\n", out[".opencode/agents/aidd-reviewer.md"])

    def test_inherit_writes_no_model_line(self):
        out = self.files(execution="inherit")
        self.assertNotIn("\nmodel:", out[".opencode/agents/aidd-developer.md"])


class OpenCodeCommandFilesTests(unittest.TestCase):
    """The flow commands as OpenCode commands, generated from the same source as Claude Code's."""

    def commands(self):
        return team_install.team_files(["opencode"], claude_files=False)

    def test_every_flow_command_exists_as_an_opencode_command(self):
        out = self.commands()
        team = resources.data_dir("team")
        srcs = sorted((team / "commands").glob("*.md"))
        self.assertGreaterEqual(len(srcs), 19)
        for src in srcs:
            rel = f".opencode/commands/aidd-{src.stem}.md"
            with self.subTest(rel):
                self.assertIn(rel, out)
                front, body = team_install._front_and_body(out[rel])
                self.assertEqual(list(front), ["description"])
                self.assertNotIn("disable-model-invocation", out[rel])
                self.assertNotIn("argument-hint", out[rel])
                # `_team_text` renames every aidd-team: reference to the OpenCode aidd- names.
                self.assertNotIn("aidd-team:", out[rel])
                self.assertTrue(body.strip())

    def test_no_claude_code_only_text_reaches_opencode(self):
        """OpenCode never expands `${CLAUDE_SESSION_ID}` and has no `Agent` or `Skill` tool and no `.claude/` command
        files (https://opencode.ai/v2/docs/commands, /tools), so none of it may reach a file OpenCode reads."""
        forbidden = ("CLAUDE_", ".claude/", "Agent call", "Skill tool", "`Skill`", "/clear", "/loop", "isolation:", "`opus`", "`sonnet`")
        for models in ({}, {"execution": "anthropic/claude-sonnet-5"}):
            out = team_install.team_files(["opencode"], claude_files=False, models=models)
            files = {rel: text for rel, text in out.items() if rel.startswith(".opencode/")}
            self.assertEqual(len([r for r in files if r.startswith(".opencode/commands/")]), len(list((resources.data_dir("team") / "commands").glob("*.md"))))
            for rel, text in files.items():
                for word in forbidden:
                    with self.subTest(rel=rel, word=word):
                        self.assertNotIn(word, text)

    def test_every_swap_still_matches_its_source(self):
        """A swap whose Claude Code text was reworded in the source would leave that text in the OpenCode file."""
        team = resources.data_dir("team")
        for name, swaps in harness_text.COMMANDS.items():
            text = team_install._team_text((team / "commands" / name).read_text(encoding="utf-8"))
            for old, _ in swaps:
                with self.subTest(command=name, text=old[:40]):
                    self.assertIn(old, text)
        agents = [team_install._team_text(p.read_text(encoding="utf-8")) for p in (team / "agents").glob("*.md")]
        for old, _ in harness_text.VOICES["opencode"].swaps():
            with self.subTest(agent_text=old[:40]):
                self.assertTrue(any(old in a for a in agents))
        lead = knowledge.roles()["loop"]["lead"]
        for old in harness_text.LEAD:
            with self.subTest(lead=old[:40]):
                self.assertTrue(any(old in rule for rule in lead))

    def test_every_command_carries_the_opencode_lead_block(self):
        lead = harness_text.lead_block()
        self.assertEqual(lead.count("\n1. "), 1)
        self.assertIn("`subagent` tool", lead)
        for rel, text in self.commands().items():
            if rel.startswith(".opencode/commands/") and "**You are the lead.**" in text:
                with self.subTest(rel):
                    self.assertIn(lead, text)
                    self.assertNotIn("<!-- aidd:gen roles:lead", text)

    def test_autopilot_binds_its_lease_to_the_session_the_plugin_names(self):
        """No OpenCode variable names the session, so aidd's plugin puts the session's id in place of
        `${AIDD_SESSION_ID}`, and every autopilot command names it; without the plugin, the id start prints."""
        text = self.commands()[".opencode/commands/aidd-autopilot.md"]
        self.assertIn("Run `aidd autopilot start --work <work> --session ${AIDD_SESSION_ID}`.", text)
        self.assertIn(".opencode/plugins/aidd.js", text)
        self.assertIn("`session:` line", text)
        sessions = re.findall(r"--session (\S+?)[`\s]", text)
        self.assertGreaterEqual(len(sessions), 3)
        self.assertEqual(set(sessions), {"${AIDD_SESSION_ID}"})
        self.assertIn(".opencode/commands/aidd-<flow>.md", text)

    def test_the_body_references_the_opencode_names(self):
        specify = self.commands()[".opencode/commands/aidd-specify.md"]
        self.assertIn("`aidd-architect`", specify)  # the roles read as aidd-<role>
        self.assertIn("/aidd-", specify)  # the flow commands read as /aidd-<flow>


class OpenCodeInitTests(unittest.TestCase):
    """`aidd init --team` for an OpenCode adopter, and the docs name the wire-up."""

    def test_init_writes_agents_and_commands_and_uninstall_removes_them(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, team=True, harnesses=["opencode"], approvers=["@me"]))
            specify = root / ".opencode/commands/aidd-specify.md"
            self.assertTrue(specify.is_file())
            self.assertTrue((root / ".opencode/agents/aidd-developer.md").is_file())
            protected = baseline.baseline_data()["protected_paths"]
            for rel in team_install.team_files(["opencode"]):
                self.assertTrue(globs.match_any(protected, rel), rel)
            uninstalling.uninstall(root, yes=True)
            self.assertFalse(specify.exists())
            self.assertFalse((root / ".opencode/agents/aidd-developer.md").exists())

    def test_upgrade_rewrites_a_v1_role_file_in_the_v2_shape(self):
        """The docs promise that `aidd upgrade --yes` rewrites role files an older aidd wrote in OpenCode's V1 shape."""
        if not shutil.which("git"):
            self.skipTest("git is required")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, team=True, harnesses=["opencode"], approvers=["@me"]))
            role = root / ".opencode/agents/aidd-reviewer.md"
            v1 = '---\ndescription: "AIDD reviewer"\nmode: subagent\npermission:\n  edit: deny\n  bash: ask\n---\n\nOld body.\n'
            role.write_text(v1, encoding="utf-8")
            upgrading.upgrade(root, ref="v1.0.0", yes=True)
            text = role.read_text(encoding="utf-8")
            self.assertNotIn("\npermission:\n", text)
            rules = opencode_permissions(text)
            self.assertEqual(opencode_effect(rules, "edit", "src/app.py"), "deny")
            self.assertEqual(text, team_install.team_files(["opencode"], False)[".opencode/agents/aidd-reviewer.md"])

    def test_the_install_snippet_wires_aidd_mcp(self):
        install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        section = install.split("### OpenCode", 1)[1].split("\n### ", 1)[0]
        snippet = re.search(r"```json\n(.*?)```", section, re.S)
        self.assertIsNotNone(snippet)
        data = json.loads(snippet.group(1))
        self.assertEqual(data["mcp"]["servers"]["aidd"]["command"], ["aidd", "mcp"])
        self.assertEqual(data["mcp"]["servers"]["aidd"]["type"], "local")

    def test_the_docs_name_the_opencode_wire_up(self):
        install = (Path(__file__).resolve().parent.parent / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        self.assertIn("### OpenCode", install)
        self.assertIn("opencode mcp add aidd -- aidd mcp", install)
        # aidd requires OpenCode V2; V1 is not supported.
        self.assertIn("OpenCode V2", install)
        self.assertIn("V1 is not supported", install)
        table = harnesses.harnesses_table()
        self.assertIn(".opencode/commands/aidd-<flow>.md", table)
        self.assertIn("opencode mcp add aidd -- aidd mcp", table)
        self.assertIn("OpenCode V2", table)


if __name__ == "__main__":
    unittest.main()
