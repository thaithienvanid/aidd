"""The advisory toolkit's setup, end to end in throwaway repositories: `aidd init` writes each agent's ask rules,
`aidd upgrade` removes an older aidd's guard wiring and keeps a person's own, `aidd status` names each next step and
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

    def test_upgrade_removes_the_old_guard_and_keeps_a_persons_hooks(self):
        helpers.make_repo(self.root, "solo", harnesses=["claude-code"])
        settings = self.root / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        data["hooks"] = {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": '"$HOME"/.aidd/bin/aidd hook pre-tool || exit 2'}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "./scripts/notify.sh"}]}],
        }
        settings.write_text(json.dumps(data))
        (self.root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (self.root / ".github" / "workflows" / "aidd-gate.yml").write_text("name: aidd-gate\n")
        code, out = helpers.run_cli("doctor", str(self.root))
        self.assertIn("`aidd upgrade --yes` removes it", out)
        code, out = helpers.run_cli("upgrade", str(self.root), "--yes")
        self.assertEqual(code, 0, out)
        hooks = json.loads(settings.read_text())["hooks"]
        self.assertEqual(list(hooks), ["Stop"])
        self.assertFalse((self.root / ".github" / "workflows" / "aidd-gate.yml").exists())

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

        for profile, reviews in (("solo", 0), ("team", 1)):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
                adoption.init(root, adoption.InitOptions(profile=profile, ci="github", links=[], approvers=["@lead"], harnesses=[]))
                ruleset = root / ".github" / "rulesets" / "main.json"
                rules = {r["type"]: r for r in json.loads(ruleset.read_text())["rules"]}
                self.assertEqual(rules["pull_request"]["parameters"]["required_approving_review_count"], reviews)
                uninstalling.uninstall(root, yes=True)
                self.assertFalse(ruleset.exists())


class OldWiringAndTheMcpServer(unittest.TestCase):
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

    def test_old_hooks_go_and_a_persons_stay(self):
        from aidd.setup import mcp_wiring

        aidd_only = self.write(".codex/hooks.json", {"hooks": {"PreToolUse": [{"hooks": [{"command": "aidd hook pre-tool"}]}]}})
        mixed = self.write(
            ".claude/settings.local.json",
            {
                "model": "x",
                "hooks": {"SessionStart": [{"hooks": [{"command": "aidd.cmd hook session-start"}, {"command": "./mine.sh"}]}]},
            },
        )
        untouched = self.write(".agents/hooks.json", {"hooks": {"Stop": [{"hooks": [{"command": "my-aidd hook stop-ish"}]}]}})
        broken = self.write(".claude/settings.json", "{not json")
        self.write(".opencode/plugins/aidd-tui/index.ts", "x")
        self.write(".opencode/plugins/aidd.js", "x")
        before = {p: p.read_text() for p in (aidd_only, mixed, untouched, broken)}
        said: list[str] = []
        mcp_wiring.remove_old_wiring(self.root, said, yes=False)  # a dry run says it and writes nothing
        self.assertEqual(len(said), 4, said)
        self.assertTrue(all(s.startswith("would remove") for s in said), said)
        self.assertEqual({p: p.read_text() for p in before}, before)
        mcp_wiring.remove_old_wiring(self.root, [], yes=True)
        self.assertFalse(aidd_only.exists())  # it held only aidd's hooks
        self.assertEqual(json.loads(mixed.read_text()), {"model": "x", "hooks": {"SessionStart": [{"hooks": [{"command": "./mine.sh"}]}]}})
        self.assertEqual(untouched.read_text(), before[untouched])  # a look-alike command is not aidd's
        self.assertEqual(broken.read_text(), before[broken])  # a file that does not parse is left alone
        self.assertFalse((self.root / ".opencode/plugins/aidd-tui").exists())
        self.assertFalse((self.root / ".opencode/plugins/aidd.js").exists())

    def test_uninstall_keeps_a_settings_file_that_holds_a_persons_false(self):
        from aidd.setup import uninstalling

        path = self.write(".claude/settings.json", {"includeCoAuthoredBy": False, "permissions": {}})
        uninstalling.drop_empty_settings(path)
        self.assertTrue(path.exists())  # `false` is a setting a person wrote
        empty = self.write("opencode.json", {"permission": {"bash": {}}})
        uninstalling.drop_empty_settings(empty)
        self.assertFalse(empty.exists())

    def test_a_persons_hook_event_that_is_not_a_list_stays(self):
        from aidd.setup import mcp_wiring

        odd = [{"hooks": {"not": "a list"}}, "a string", {"type": "command", "command": "./mine.sh"}]
        path = self.write(".codex/hooks.json", {"hooks": {"Custom": {"command": "./mine.sh"}, "Stop": [{"hooks": [{"command": "aidd hook stop"}]}, *odd]}})
        mcp_wiring.remove_old_wiring(self.root, [], yes=True)
        self.assertEqual(json.loads(path.read_text()), {"hooks": {"Custom": {"command": "./mine.sh"}, "Stop": odd}})

    def test_antigravitys_named_aidd_hook_goes(self):
        """The shape an older aidd wrote in `.agents/hooks.json`: one `aidd` entry of events, beside a person's own."""
        from aidd.setup import mcp_wiring

        launcher = '"$HOME"/.aidd/bin/aidd'
        old = {
            "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": f"{launcher} hook pre-tool || {{ echo x; }}", "timeout": 20}]}],
            "SessionStart": [{"type": "command", "command": f"{launcher} hook session-start || echo '{{}}'"}],
        }
        mine = {"Stop": [{"type": "command", "command": "./notify.sh"}]}
        path = self.write(".agents/hooks.json", {"aidd": old, "mine": mine})
        said: list[str] = []
        mcp_wiring.remove_old_wiring(self.root, said, yes=True)
        self.assertEqual(json.loads(path.read_text()), {"mine": mine})
        self.assertIn("removed 2 aidd hooks from .agents/hooks.json", said[0])

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
