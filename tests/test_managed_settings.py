"""The Claude Code managed-settings template for regulated organizations, and the doctor check that looks for it."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import repo

TEMPLATE = ROOT / "templates" / "claude" / "managed-settings.json"

# Every key the template sets, each checked against the Claude Code settings reference (code.claude.com/docs/en/
# settings-reference, and code.claude.com/docs/en/plugins/org for the plugin keys, 2026-09-28). A key that cannot be
# verified stays out of the template.
VERIFIED_TOP_LEVEL = {
    "requiredMinimumVersion",
    "permissions",
    "allowManagedPermissionRulesOnly",
    "sandbox",
    "allowManagedHooksOnly",
    "env",
    "allowManagedMcpServersOnly",
    "allowedMcpServers",
    "strictKnownMarketplaces",
    "extraKnownMarketplaces",
    "enabledPlugins",
    "pluginSuggestionMarketplaces",
    "disableSideloadFlags",
}
VERIFIED_SANDBOX = {"enabled", "failIfUnavailable", "allowUnsandboxedCommands", "network", "filesystem", "credentials"}


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def test_only_verified_keys(self):
        self.assertEqual(set(self.data), VERIFIED_TOP_LEVEL)
        self.assertEqual(set(self.data["sandbox"]), VERIFIED_SANDBOX)
        self.assertEqual(set(self.data["permissions"]), {"allow", "deny", "disableBypassPermissionsMode"})
        self.assertEqual(set(self.data["sandbox"]["network"]), {"allowedDomains", "allowManagedDomainsOnly"})

    def test_locks_the_session_down(self):
        d = self.data
        self.assertEqual(d["permissions"]["disableBypassPermissionsMode"], "disable")
        for key in ("allowManagedPermissionRulesOnly", "allowManagedHooksOnly", "allowManagedMcpServersOnly"):
            self.assertIs(d[key], True, key)
        self.assertEqual((d["sandbox"]["enabled"], d["sandbox"]["failIfUnavailable"], d["sandbox"]["allowUnsandboxedCommands"]), (True, True, False))
        self.assertRegex(d["requiredMinimumVersion"], r"^\d+\.\d+\.\d+$")

    def test_denies_secrets_and_arbitrary_egress(self):
        deny = self.data["permissions"]["deny"]
        for rule in ("Read(~/.ssh/**)", "Read(~/.aws/credentials)", "Read(./.env)", "Bash(curl *)", "Bash(wget *)", "WebFetch"):
            self.assertIn(rule, deny)
        creds = self.data["sandbox"]["credentials"]
        self.assertIn({"path": "~/.aws/credentials", "mode": "deny"}, creds["files"])
        self.assertIn({"name": "GITHUB_TOKEN", "mode": "deny"}, creds["envVars"])
        self.assertIn("~/.ssh", self.data["sandbox"]["filesystem"]["denyRead"])
        self.assertTrue(any("REPLACE" in d for d in self.data["sandbox"]["network"]["allowedDomains"]), "the allowlist needs a placeholder")

    def test_allows_the_safe_inner_loop(self):
        allow = self.data["permissions"]["allow"]
        for cmd in ("test", "gate", "validate"):
            self.assertIn(f"Bash(aidd {cmd})", allow)
            self.assertIn(f"Bash(aidd {cmd} *)", allow)
        self.assertFalse(set(allow) & set(self.data["permissions"]["deny"]))

    def test_the_guard_runs_once_from_the_force_enabled_plugin_and_fails_closed(self):
        # A force-enabled plugin's hooks are exempt from allowManagedHooksOnly: a managed copy of the same hook would
        # run the guard twice on every tool call. The plugin's hook blocks when it cannot run (see the tests below).
        self.assertIs(self.data["enabledPlugins"].get(f"aidd@{repo.MARKETPLACE}"), True)
        self.assertNotIn("hooks", self.data)
        self.assertEqual(self.data["env"], {"AIDD_HOOK_FAIL_CLOSED": "1"})
        (entry,) = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(entry["matcher"], repo.HOOK_MATCHER)

    def test_the_aidd_mcp_server_and_marketplace_match_what_aidd_ships(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["mcpServers"]["aidd"]
        commands = [s["serverCommand"] for s in self.data["allowedMcpServers"]]
        self.assertIn([plugin["command"], *plugin["args"]], commands)  # the plugin's server
        self.assertIn(["aidd", "mcp"], commands)  # the server `aidd init --agent-hooks` writes to .mcp.json
        self.assertEqual(self.data["strictKnownMarketplaces"], [{"source": "github", "repo": repo.MARKETPLACE_REPO}])

    def test_every_machine_gets_the_aidd_plugin_from_the_allowed_marketplace_only(self):
        name = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["name"]
        known = self.data["extraKnownMarketplaces"][name]
        self.assertIn(known["source"], self.data["strictKnownMarketplaces"])  # a managed marketplace must pass the allowlist
        self.assertIs(known["autoUpdate"], False)  # the organization decides when a new version reaches machines
        self.assertEqual(self.data["enabledPlugins"], {f"aidd@{name}": True})
        self.assertEqual(self.data["pluginSuggestionMarketplaces"], [name])
        self.assertIs(self.data["disableSideloadFlags"], True)  # no --plugin-dir or --agents around the policy


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "the hook command runs under a POSIX shell")
class PluginHookFailClosedTests(unittest.TestCase):
    """Claude Code blocks a tool call only on exit 2. The plugin's guard fails open by default (the gate still decides);
    under the regulated managed settings (AIDD_HOOK_FAIL_CLOSED=1) a guard that cannot run blocks instead."""

    def setUp(self):
        self.command = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        # A PATH with the shell and the basic utilities but no python3.
        sh_dir = str(Path(shutil.which("sh") or "/bin/sh").parent)
        self.path = os.pathsep.join(dict.fromkeys([sh_dir, "/usr/bin", "/bin"]))
        if shutil.which("python3", path=self.path):
            self.path = os.pathsep.join([str(self.bin / "empty")])  # only our fakes, and sh by absolute path
        self.sh = shutil.which("sh") or "/bin/sh"

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, path: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.sh, "-c", self.command],
            input='{"tool_name": "Edit"}',
            env={"PATH": path, "CLAUDE_PLUGIN_ROOT": str(ROOT), **env},
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
        )

    def fake_python(self, exit_for_module: int) -> str:
        fake = self.bin / "python3"
        fake.write_text(
            f'#!{self.sh}\nif [ "$1" = "-m" ]; then echo "$@"; IFS= read -r line; echo "$line"; exit {exit_for_module}; fi\nexit 0\n', encoding="utf-8"
        )
        fake.chmod(0o755)
        return os.pathsep.join([str(self.bin), self.path])

    def test_without_python_it_allows_by_default_and_blocks_when_fail_closed(self):
        self.assertEqual(self.run_hook(self.path).returncode, 0)
        r = self.run_hook(self.path, AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("blocking", r.stderr)

    def test_a_guard_that_cannot_run_blocks_when_fail_closed(self):
        path = self.fake_python(1)
        self.assertEqual(self.run_hook(path).returncode, 0)
        self.assertEqual(self.run_hook(path, AIDD_HOOK_FAIL_CLOSED="1").returncode, 2)

    def test_runs_the_aidd_hook_and_passes_its_input_through(self):
        r = self.run_hook(self.fake_python(0), AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "-m aidd hook pre-edit")
        self.assertIn('"tool_name": "Edit"', r.stdout)  # the hook's input reaches aidd on stdin


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.system = self.root / "system"
        self.home.mkdir()
        self.system.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def sources(self):
        with mock.patch.dict(repo.MANAGED_SETTINGS_DIRS, {"linux": str(self.system)}):
            return repo.managed_settings_sources(platform="linux", home=self.home)

    def test_finds_each_kind_of_source(self):
        self.assertEqual(self.sources(), [])
        (self.system / "managed-settings.d").mkdir()
        self.assertEqual(self.sources(), [])  # an empty drop-in directory delivers nothing
        (self.system / "managed-settings.d" / "10-aidd.json").write_text("{}", encoding="utf-8")
        (self.system / "managed-settings.json").write_text("{}", encoding="utf-8")
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "remote-settings.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(self.sources()), 3)

    def doctor(self, profile, managed):
        project = self.root / "project"
        project.mkdir()
        repo.init(project, profile=profile, ci="none", links=[], skill=False, approvers=["@a", "@b"], reviewers={"security": ["@s"]}, harnesses=[])
        (project / ".claude").mkdir(exist_ok=True)  # Claude Code in use here
        with mock.patch.object(repo, "managed_settings_sources", return_value=managed):
            return repo.doctor(project)

    def test_regulated_warns_without_managed_settings(self):
        report = self.doctor("regulated", [])
        (msg,) = [m for lvl, m in report if "managed settings" in m]
        self.assertIn(("warn", msg), report)
        self.assertIn("templates/claude/managed-settings.json", msg)

    def test_regulated_with_managed_settings_is_ok(self):
        report = self.doctor("regulated", ["/etc/claude-code/managed-settings.json"])
        self.assertIn(("ok", next(m for lvl, m in report if "managed settings" in m)), report)

    def test_other_profiles_do_not_ask_for_them(self):
        self.assertFalse([m for _, m in self.doctor("team", []) if "managed settings" in m])


if __name__ == "__main__":
    unittest.main()
