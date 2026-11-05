"""The advisory toolkit's setup, end to end in throwaway repositories: `aidd init` writes each agent's ask rules,
`aidd upgrade` and `aidd uninstall` keep a person's own settings, `aidd status` names each next step and
who takes it, and the MCP `risk` tool answers as `aidd risk` does."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers
from aidd.cli import mcp_server


class InitAndUpgrade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "repo"

    def test_init_writes_the_ask_rules_for_each_agent(self):
        helpers.make_repo(self.root, "solo", harnesses=["claude-code", "opencode", "codex"])
        ask = json.loads((self.root / ".claude" / "settings.json").read_text())["permissions"]["ask"]
        self.assertIn("Bash(git push --force*)", ask)
        self.assertIn("git push --force*", json.loads((self.root / "opencode.json").read_text())["permission"]["bash"])
        self.assertTrue((self.root / ".codex" / "rules" / "aidd.rules").is_file())
        self.assertIn("aidd", json.loads((self.root / ".mcp.json").read_text())["mcpServers"])
        code, out = helpers.run_cli("doctor", str(self.root))
        self.assertNotIn("[fail]", out)
        self.assertIn("its ask rules match the risk rules", out)

    def test_aidds_own_mcp_tools_run_with_no_prompt_in_each_harness_and_uninstall_takes_only_them(self):
        """A headless run approves nothing, so aidd's four tools are approved by name: Codex per tool, Claude Code in
        `permissions.allow`. Uninstall takes exactly those names out, never a person's own entry."""
        import tomllib

        from aidd.cli import mcp_server
        from aidd.setup import mcp_wiring, uninstalling, upgrading

        self.assertEqual(set(mcp_wiring.OWN_MCP_TOOLS), set(mcp_server.TOOL_NAMES))
        helpers.make_repo(self.root, "solo", harnesses=["claude-code", "codex"])
        codex = tomllib.loads((self.root / ".codex" / "config.toml").read_text())["mcp_servers"]["aidd"]["tools"]
        self.assertEqual({t: v["approval_mode"] for t, v in codex.items()}, dict.fromkeys(mcp_wiring.OWN_MCP_TOOLS, "approve"))
        settings = self.root / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        self.assertEqual(data["permissions"]["allow"], [f"mcp__aidd__{t}" for t in mcp_wiring.OWN_MCP_TOOLS])
        data["permissions"]["allow"].remove("mcp__aidd__record")  # the person takes one out: no upgrade puts it back
        data["permissions"]["allow"].append("Bash(make test)")  # a person's own
        settings.write_text(json.dumps(data))
        # An older init's block, with no approvals: `aidd upgrade` brings it up to this aidd.
        config_toml = self.root / ".codex" / "config.toml"
        config_toml.write_text(config_toml.read_text().replace(mcp_wiring._CODEX_TOOLS, ""))
        self.assertTrue(any(".codex/config.toml" in a for a in upgrading.upgrade(self.root, yes=True)))
        self.assertIn(mcp_wiring.CODEX_BLOCK, config_toml.read_text())
        self.assertNotIn("mcp__aidd__record", json.loads(settings.read_text())["permissions"]["allow"])
        said: list[str] = []
        mcp_wiring.allow_claude_tools(self.root, said, "mcp__aidd__", write=False)
        self.assertIn("you took mcp__aidd__record out of `permissions.allow`, so it still asks", said[0])
        uninstalling.uninstall(self.root, yes=True)
        left = json.loads(settings.read_text()) if settings.exists() else {}
        self.assertEqual((left.get("permissions") or {}).get("allow"), ["Bash(make test)"])

    def test_a_name_the_person_listed_first_stays_theirs(self):
        from aidd.setup import mcp_wiring

        self.root.mkdir(parents=True)
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["mcp__aidd__risk"]}}))
        mcp_wiring.allow_claude_tools(self.root, [], "mcp__aidd__")
        self.assertEqual(json.loads(settings.read_text())["permissions"]["allow"], [f"mcp__aidd__{t}" for t in mcp_wiring.OWN_MCP_TOOLS])
        mcp_wiring.remove_mcp(self.root, [], yes=True)
        self.assertEqual(json.loads(settings.read_text())["permissions"]["allow"], ["mcp__aidd__risk"])
        self.assertFalse((self.root / mcp_wiring.APPROVALS_FILE).exists())
        for odd in ("[]", "null", '{"permissions": []}'):  # never a crash on a file that is not the shape aidd reads
            with self.subTest(settings=odd):
                settings.write_text(odd)
                mcp_wiring.remove_mcp(self.root, [], yes=False)
                mcp_wiring.allow_claude_tools(self.root, [], "mcp__aidd__", write=False)

    def test_uninstall_takes_out_only_aidds_ask_rules(self):
        helpers.make_repo(self.root, "solo", harnesses=["claude-code"])
        settings = self.root / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        data["permissions"]["ask"].insert(0, "Bash(./deploy.sh*)")
        settings.write_text(json.dumps(data))
        code, out = helpers.run_cli("uninstall", str(self.root), "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(settings.read_text())["permissions"]["ask"], ["Bash(./deploy.sh*)"])


class TheBranchRuleset(unittest.TestCase):
    def test_team_requires_a_review_and_solo_none_and_uninstall_takes_either(self):
        import subprocess

        from aidd.setup import adoption, uninstalling

        for profile, reviews, last_push in (("solo", 0, False), ("team", 1, True)):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
                adoption.init(root, adoption.InitOptions(profile=profile, ci="github", links=[], approvers=["@lead"], harnesses=[]))
                ruleset = root / ".github" / "rulesets" / "main.json"
                rules = {r["type"]: r for r in json.loads(ruleset.read_text())["rules"]}
                self.assertEqual(rules["pull_request"]["parameters"]["required_approving_review_count"], reviews)
                # GitHub never lets a person approve their own push, so a solo project never asks for it.
                self.assertIs(rules["pull_request"]["parameters"]["require_last_push_approval"], last_push)
                uninstalling.uninstall(root, yes=True)
                self.assertFalse(ruleset.exists())


class TheMcpServerWiring(unittest.TestCase):
    """What `aidd upgrade` and `aidd uninstall` take out of a person's settings: only what aidd wrote there."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, rel: str, data) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def test_uninstall_keeps_a_settings_file_that_holds_a_persons_false(self):
        from aidd.setup import uninstalling

        path = self.write(".claude/settings.json", {"includeCoAuthoredBy": False, "permissions": {}})
        uninstalling.drop_empty_settings(path)
        self.assertTrue(path.exists())  # `false` is a setting a person wrote
        empty = self.write("opencode.json", {"permission": {"bash": {}}})
        uninstalling.drop_empty_settings(empty)
        self.assertFalse(empty.exists())

    def test_the_mcp_server_round_trip_keeps_a_persons_servers(self):
        import os

        from aidd.setup import mcp_wiring

        mcp = self.write(".mcp.json", {"mcpServers": {"docs": {"command": "docs-server"}}})
        codex = self.write(".codex/config.toml", 'model = "x"\n')
        said: list[str] = []
        mcp_wiring.install_claude_mcp(self.root, said)
        mcp_wiring.install_claude_mcp(self.root, said)  # a second run keeps it
        self.assertIn("aidd", json.loads(mcp.read_text())["mcpServers"])
        self.assertTrue(said[-1].startswith("kept"), said)
        if os.name != "nt":
            mcp_wiring.install_codex_mcp(self.root, said)
            mcp_wiring.install_codex_mcp(self.root, said)
            self.assertEqual(codex.read_text().count("[mcp_servers.aidd]"), 1)
        dry: list[str] = []
        mcp_wiring.remove_mcp(self.root, dry, yes=False)
        self.assertIn("aidd", json.loads(mcp.read_text())["mcpServers"])
        mcp_wiring.remove_mcp(self.root, [], yes=True)
        self.assertEqual(json.loads(mcp.read_text()), {"mcpServers": {"docs": {"command": "docs-server"}}})
        self.assertEqual(codex.read_text(), 'model = "x"\n')
        bad = self.write(".mcp.json", "{not json")
        mcp_wiring.install_claude_mcp(self.root, said)
        self.assertEqual(bad.read_text(), "{not json")  # never overwrites a file it cannot read
        self.assertIn("not valid JSON", said[-1])


class StatusAndRisk(unittest.TestCase):
    def test_each_spec_status_has_its_next_step(self):
        cases = [
            ("draft", "spec.draft", "agent"),
            ("ready", "spec.approval", "person"),
            ("approved", "spec.approved", "agent"),
            ("in_review", "spec.merge", "person"),
        ]
        for state, code, who in cases:
            with self.subTest(status=state), helpers.adopted_repo("team", spec="specs/SPEC-220.md", status=state) as root:
                (item,) = helpers.open_work(root)
                self.assertEqual((item["status"], item["next"]["code"], item["next"]["who"]), (state, code, who))

    def test_a_done_spec_leaves_the_open_work(self):
        with helpers.adopted_repo("team", spec="specs/SPEC-220.md", status="done") as root:
            self.assertEqual(helpers.open_work(root), [])
            self.assertEqual(len(helpers.open_work(root, include_done=True)), 1)

    def test_the_mcp_risk_tool_answers_as_the_cli(self):
        with helpers.adopted_repo("solo") as root:
            is_error, text = mcp_server.call("risk", {"command": "git push --force origin feat"}, str(root))
            self.assertFalse(is_error, text)
            self.assertEqual(json.loads(text)["level"], "ask")
            is_error, text = mcp_server.call("risk", {"paths": ["src/payments/charge.py"]}, str(root))
            self.assertEqual(json.loads(text)["route"], "major")
            is_error, text = mcp_server.call("risk", {"paths": ["../outside"]}, str(root))
            self.assertTrue(is_error)


if __name__ == "__main__":
    unittest.main()
