"""`mcp: {approve_own_tools: false}` keeps aidd's own MCP tools asking: `aidd init` and `aidd upgrade` write no approval
(no per-tool tables in Codex's aidd block, no names in Claude Code's `permissions.allow`), and take out the ones aidd
wrote, through the ledger `.aidd/mcp-approvals.json`, never a person's own entry. A config without the key approves."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import helpers
from aidd.setup import adoption, mcp_wiring, uninstalling, upgrading

OPT_OUT = "mcp:\n  approve_own_tools: false\n"


class KeepAiddsToolsAsking(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.settings = self.root / ".claude" / "settings.json"
        self.codex = self.root / ".codex" / "config.toml"
        self.ledger = self.root / mcp_wiring.APPROVALS_FILE

    def allow(self) -> list[str]:
        return json.loads(self.settings.read_text()).get("permissions", {}).get("allow", [])

    def codex_tools(self) -> dict:
        return tomllib.loads(self.codex.read_text())["mcp_servers"]["aidd"].get("tools", {})

    def set_config(self, extra: str) -> None:
        path = self.root / ".aidd" / "config.yaml"
        path.write_text(path.read_text().rstrip("\n") + "\n" + extra)

    def test_init_with_the_opt_out_writes_no_approval(self):
        self.root.mkdir(parents=True)
        helpers.git(self.root, "init", "-q", "-b", "main")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n' + OPT_OUT)
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@x"], harnesses=["claude-code", "codex"], skill=False))
        self.assertIn("aidd", json.loads((self.root / ".mcp.json").read_text())["mcpServers"])  # the server is still wired
        self.assertEqual([n for n in self.allow() if n.startswith("mcp__")], [])
        self.assertEqual(self.codex_tools(), {})
        self.assertFalse(self.ledger.exists())

    def test_upgrade_takes_out_only_what_aidd_wrote_and_an_opt_in_puts_it_back(self):
        helpers.make_repo(self.root, "solo", harnesses=["claude-code", "codex"])
        names = mcp_wiring.claude_tool_names("mcp__aidd__")
        data = json.loads(self.settings.read_text())
        data["permissions"]["allow"].remove("mcp__aidd__record")  # the person took one out
        data["permissions"]["allow"] += ["Bash(make test)", "mcp__other__tool"]  # their own entries
        self.settings.write_text(json.dumps(data))
        self.set_config(OPT_OUT)
        said = upgrading.upgrade(self.root, yes=True)
        self.assertTrue(any("aidd's MCP tool approvals" in a for a in said), said)
        self.assertEqual(self.allow(), ["Bash(make test)", "mcp__other__tool"])
        self.assertEqual(self.codex_tools(), {})
        # The ledger keeps only the name the person took out, so that choice still holds after an opt-in.
        self.assertEqual(json.loads(self.ledger.read_text()), {"claude-code": [], "taken_out": ["mcp__aidd__record"]})
        self.assertEqual([a for a in upgrading.upgrade(self.root, yes=True) if "MCP" in a or "config.toml" in a], [])  # nothing more to do
        backup = self.settings.read_text()
        uninstalling.uninstall(self.root, yes=False)  # a dry run after the opt-out changes nothing
        self.assertEqual(self.settings.read_text(), backup)
        path = self.root / ".aidd" / "config.yaml"
        path.write_text(path.read_text().replace(OPT_OUT, ""))
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual(sorted(n for n in self.allow() if n.startswith("mcp__aidd__")), sorted(n for n in names if n != "mcp__aidd__record"))
        self.assertEqual(set(self.codex_tools()), set(mcp_wiring.OWN_MCP_TOOLS))

    def test_a_name_put_back_by_hand_is_the_persons_own(self):
        """Taken out, then put back by hand: the name is the person's now, so no opt-out or uninstall removes it."""
        helpers.make_repo(self.root, "solo", harnesses=["claude-code"])
        data = json.loads(self.settings.read_text())
        data["permissions"]["allow"].remove("mcp__aidd__record")
        self.settings.write_text(json.dumps(data))
        upgrading.upgrade(self.root, yes=True)  # the ledger learns it was taken out
        data = json.loads(self.settings.read_text())
        data["permissions"]["allow"].append("mcp__aidd__record")  # and the person puts it back
        self.settings.write_text(json.dumps(data))
        upgrading.upgrade(self.root, yes=True)
        self.assertNotIn("mcp__aidd__record", json.loads(self.ledger.read_text())["claude-code"] + json.loads(self.ledger.read_text())["taken_out"])
        self.set_config(OPT_OUT)
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual([n for n in self.allow() if n.startswith("mcp__aidd__")], ["mcp__aidd__record"])
        uninstalling.uninstall(self.root, yes=True)
        left = json.loads(self.settings.read_text()) if self.settings.exists() else {}
        self.assertIn("mcp__aidd__record", (left.get("permissions") or {}).get("allow", []))

    def test_a_crafted_ledger_never_takes_out_a_persons_own_entry(self):
        helpers.make_repo(self.root, "solo", harnesses=["claude-code"])
        data = json.loads(self.settings.read_text())
        data["permissions"]["allow"] += ["Bash(make test)"]
        self.settings.write_text(json.dumps(data))
        self.ledger.write_text(json.dumps({"claude-code": ["Bash(make test)", "mcp__aidd__risk"], "taken_out": []}))
        uninstalling.uninstall(self.root, yes=True)
        self.assertIn("Bash(make test)", json.loads(self.settings.read_text())["permissions"]["allow"])

    def test_a_name_the_person_listed_stays_under_the_opt_out(self):
        self.root.mkdir(parents=True)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n' + OPT_OUT)
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"permissions": {"allow": ["mcp__aidd__risk"]}}))
        said: list[str] = []
        mcp_wiring.allow_claude_tools(self.root, said, "mcp__aidd__")
        self.assertEqual(self.allow(), ["mcp__aidd__risk"])
        self.assertIn("mcp__aidd__risk stay allowed, since you listed them; `mcp.approve_own_tools` is false", said[0])

    def test_a_config_that_does_not_load_adds_no_approval(self):
        self.root.mkdir(parents=True)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd" / "config.yaml").write_text("not: [valid\n")
        said: list[str] = []
        mcp_wiring.allow_claude_tools(self.root, said, "mcp__aidd__")
        mcp_wiring.install_codex_mcp(self.root, said)
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.codex_tools(), {})
        self.assertIn("the config does not load", said[0])

    def test_which_configs_approve(self):
        cases = [
            (None, True),  # no config yet: today's default
            ('aidd_version: "1.0.0"\nprofile: solo\n', True),
            ('aidd_version: "1.0.0"\nprofile: solo\nmcp:\n  approve_own_tools: true\n', True),
            ('aidd_version: "1.0.0"\nprofile: solo\n' + OPT_OUT, False),
            # A config that does not load adds no approval and takes none out: None.
            ('aidd_version: "1.0.0"\nprofile: solo\nmcp:\n  approve_own_tools: "no"\n', None),
            ("not: [valid\n", None),
        ]
        for text, want in cases:
            with self.subTest(config=text), tempfile.TemporaryDirectory() as d:
                if text is not None:
                    (Path(d) / ".aidd").mkdir()
                    (Path(d) / ".aidd" / "config.yaml").write_text(text)
                self.assertIs(mcp_wiring.approves_own_tools(Path(d)), want)


class ServerNamesLeaveWithTheServer(unittest.TestCase):
    """The server's tool names (`mcp__aidd__*`) that aidd wrote leave `permissions.allow` once `.mcp.json` names no `aidd`
    server, as the aidd plugin serves the tools under its own names. `aidd init` and `aidd upgrade` both do it, and a
    name a person listed before aidd did stays."""

    SERVER = mcp_wiring.claude_tool_names("mcp__aidd__")
    PLUGIN = mcp_wiring.claude_tool_names("mcp__plugin_aidd_aidd__")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "repo"
        self.user = base / "claude"
        self.user.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.user)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = self.root / ".claude" / "settings.json"
        self.mcp = self.root / ".mcp.json"
        self.ledger = self.root / mcp_wiring.APPROVALS_FILE
        self.root.mkdir()
        helpers.git(self.root, "init", "-q", "-b", "main")
        self.settings.parent.mkdir()
        # The person listed `risk` before aidd wrote anything, so that name is theirs.
        self.settings.write_text(json.dumps({"permissions": {"allow": ["mcp__aidd__risk", "Bash(make test)"]}}))
        self.init()

    def init(self) -> list[str]:
        options = adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@x"], harnesses=["claude-code"], skill=False)
        return adoption.init(self.root, options)

    def allow(self) -> list[str]:
        return json.loads(self.settings.read_text())["permissions"]["allow"]

    def ledger_names(self) -> list[str]:
        return json.loads(self.ledger.read_text())["claude-code"]

    def move_to_the_plugin(self, *, keep_server: bool = False) -> None:
        """The person enables the plugin, in this project, and drops (or keeps) the `aidd` server in `.mcp.json`."""
        data = json.loads(self.settings.read_text())
        data["enabledPlugins"] = {"aidd@aidd": True}
        self.settings.write_text(json.dumps(data))
        if not keep_server:
            self.mcp.unlink()

    def test_the_first_init_wires_the_server_and_its_names(self):
        self.assertIn("aidd", json.loads(self.mcp.read_text())["mcpServers"])
        self.assertEqual(sorted(self.ledger_names()), sorted(n for n in self.SERVER if n != "mcp__aidd__risk"))  # not the person's own

    def test_init_withdraws_the_servers_names_aidd_wrote_and_keeps_the_persons(self):
        self.move_to_the_plugin()
        (self.user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}))
        said = self.init()
        self.assertTrue(any(a.startswith("removed  aidd's MCP tool approvals from ") for a in said), said)
        self.assertEqual(self.allow(), ["mcp__aidd__risk", "Bash(make test)", *self.PLUGIN])
        self.assertEqual(sorted(self.ledger_names()), sorted(self.PLUGIN))
        self.assertEqual([a for a in self.init() if "MCP tool approvals" in a and "removed" in a], [])  # nothing more to do

    def test_upgrade_says_it_in_a_dry_run_and_withdraws_on_a_yes(self):
        self.move_to_the_plugin()
        before = self.settings.read_text()
        said = upgrading.upgrade(self.root)
        self.assertTrue(any(a.startswith("would remove aidd's MCP tool approvals from ") for a in said), said)
        self.assertEqual(self.settings.read_text(), before)
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual(self.allow(), ["mcp__aidd__risk", "Bash(make test)", *self.PLUGIN])
        self.assertEqual(sorted(self.ledger_names()), sorted(self.PLUGIN))
        self.assertEqual([a for a in upgrading.upgrade(self.root, yes=True) if "MCP tool" in a], [])

    def test_the_names_stay_while_mcp_json_names_the_server(self):
        self.move_to_the_plugin(keep_server=True)
        (self.user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}))
        mine = json.loads(self.mcp.read_text())
        mine["mcpServers"]["aidd"] = {"command": "my-aidd", "args": ["mcp"]}  # a launcher of their own still names the server
        self.mcp.write_text(json.dumps(mine))
        upgrading.upgrade(self.root, yes=True)
        self.assertTrue(set(self.SERVER) <= set(self.allow()), self.allow())

    def test_a_config_that_does_not_load_or_an_unreadable_mcp_json_takes_nothing_out(self):
        self.move_to_the_plugin()
        config = self.root / ".aidd" / "config.yaml"
        good = config.read_text()
        config.write_text("not: [valid\n")
        mcp_wiring.refresh_mcp(self.root, [], yes=True)
        self.assertTrue(set(self.SERVER) <= set(self.allow()), self.allow())
        config.write_text(good)
        self.mcp.write_text("{not json")
        mcp_wiring.refresh_mcp(self.root, [], yes=True)
        self.assertTrue(set(self.SERVER) <= set(self.allow()), self.allow())

    def test_without_the_plugin_the_servers_names_stay(self):
        """A server named `aidd` in Claude Code's local or user scope has the same names, so only the plugin moves them."""
        self.mcp.unlink()  # the server left `.mcp.json`, and no plugin serves aidd here
        upgrading.upgrade(self.root, yes=True)
        self.assertTrue(set(self.SERVER) <= set(self.allow()), self.allow())

    def test_an_mcp_json_aidd_cannot_open_takes_nothing_out_and_raises_nothing(self):
        self.move_to_the_plugin(keep_server=True)
        (self.user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}))
        self.mcp.chmod(0)
        self.addCleanup(self.mcp.chmod, 0o644)
        if os.access(self.mcp, os.R_OK):
            self.skipTest("this user reads any file, such as root")
        self.assertIsNone(mcp_wiring.server_named(self.root))
        mcp_wiring.refresh_mcp(self.root, [], yes=True)
        self.assertTrue(set(self.SERVER) <= set(self.allow()), self.allow())


if __name__ == "__main__":
    unittest.main()
