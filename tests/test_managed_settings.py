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

from aidd.setup import doctor_checks
from aidd.setup import adoption
from aidd.setup import doctor_probes
from aidd.setup import claude_plugins
from aidd.setup import hook_wiring
from aidd.config import harness_settings
from aidd.knowledge import team_registry

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
        # Every command the loop runs without a person: author, describe, check, and test; approve and ship stay out.
        for cmd in ("new", "describe", "owners", "observe", "list", "test", "gate", "validate", "hash"):
            self.assertIn(f"Bash(aidd {cmd} *)", allow, cmd)
        for cmd in ("describe", "owners", "list", "test", "gate", "validate"):
            self.assertIn(f"Bash(aidd {cmd})", allow, cmd)
        self.assertFalse([r for r in allow if r.startswith(("Bash(aidd approve", "Bash(aidd land", "Bash(aidd init", "Bash(aidd upgrade"))])
        self.assertFalse(set(allow) & set(self.data["permissions"]["deny"]))

    def test_research_has_a_path_when_web_fetch_is_denied(self):
        """The research-first rule names WebFetch; under these settings a role names the source it needs instead."""
        self.assertIn("WebFetch", self.data["permissions"]["deny"])
        research = next(r for r in team_registry.roles()["loop"]["contract"] if r.startswith("Research first"))
        self.assertIn("denied", research)
        self.assertIn("Needs", research)

    def test_the_guard_runs_once_from_the_force_enabled_plugin_and_fails_closed(self):
        # A force-enabled plugin's hooks are exempt from allowManagedHooksOnly: a managed copy of the same hook would
        # run the guard twice on every tool call. The plugin's hook blocks when it cannot run (see the tests below).
        self.assertIs(self.data["enabledPlugins"].get(f"aidd@{harness_settings.MARKETPLACE}"), True)
        self.assertNotIn("hooks", self.data)
        self.assertEqual(self.data["env"], {"AIDD_HOOK_FAIL_CLOSED": "1"})
        (entry,) = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(entry["matcher"], hook_wiring.HOOK_MATCHER)

    def test_the_aidd_mcp_server_and_marketplace_match_what_aidd_ships(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["mcpServers"]["aidd"]
        commands = [s["serverCommand"] for s in self.data["allowedMcpServers"]]
        self.assertIn([plugin["command"], *plugin["args"]], commands)  # the plugin's server
        # Every allowed server names its program by an absolute path: a bare `aidd` is found through PATH, which a
        # project's settings can change.
        self.assertEqual([c for c in commands if not os.path.isabs(c[0])], [])
        self.assertNotIn(["aidd", "mcp"], commands)
        self.assertEqual(self.data["strictKnownMarketplaces"], [{"source": "github", "repo": claude_plugins.MARKETPLACE_REPO}])

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
    under the audited profile's managed settings (AIDD_HOOK_FAIL_CLOSED=1) a guard that cannot run blocks instead."""

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

    def fake_python(self, exit_for_hook: int) -> str:
        """A python3 on PATH that echoes its arguments and the hook's stdin, then exits `exit_for_hook`; 3 is what the
        loader returns on a Python older than 3.11 (repo.LOADER)."""
        fake = self.bin / "python3"
        reads = "" if exit_for_hook == 3 else ' IFS= read -r line; echo "$line";'  # the loader stops an old Python before stdin
        fake.write_text(f'#!{self.sh}\necho "python3 $@";{reads} exit {exit_for_hook}\n', encoding="utf-8")
        fake.chmod(0o755)
        return os.pathsep.join([str(self.bin), self.path])

    def fake_uv(self) -> Path:
        """A uv whose `python find` names a marker script, so the test sees whether the fallback ran and with what."""
        ran = self.bin / "uv-python"
        ran.write_text(f'#!{self.sh}\necho "uv-python $@"; IFS= read -r line; echo "$line"; exit 0\n', encoding="utf-8")
        ran.chmod(0o755)
        fake = self.bin / "uv"
        fake.write_text(f'#!{self.sh}\necho "{ran}"\n', encoding="utf-8")
        fake.chmod(0o755)
        if not shutil.which("env", path=os.pathsep.join([str(self.bin), self.path])):
            (self.bin / "env").symlink_to(shutil.which("env") or "/usr/bin/env")  # the hook runs uv through `env -u VIRTUAL_ENV`
        return ran

    def test_without_python_it_allows_by_default_and_blocks_when_fail_closed(self):
        self.assertEqual(self.run_hook(self.path).returncode, 0)
        r = self.run_hook(self.path, AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("blocking", r.stderr)

    def test_a_guard_that_cannot_run_blocks_when_fail_closed(self):
        path = self.fake_python(1)
        self.assertEqual(self.run_hook(path).returncode, 0)
        self.assertEqual(self.run_hook(path, AIDD_HOOK_FAIL_CLOSED="1").returncode, 2)

    def test_runs_the_plugin_source_isolated_and_passes_its_input_through(self):
        r = self.run_hook(self.fake_python(0), AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        # -I keeps the repository off sys.path, -S skips site-packages; the source folder is named, never searched for.
        self.assertEqual(r.stdout.splitlines()[0], f"python3 -I -S -c {hook_wiring.LOADER} {ROOT}/src aidd hook pre-tool")
        self.assertIn('"tool_name": "Edit"', r.stdout)  # the hook's input reaches aidd on stdin

    def test_an_old_python3_falls_back_to_the_python_uv_finds_with_the_same_input(self):
        path = self.fake_python(3)
        ran = self.fake_uv()
        r = self.run_hook(path, AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{ran.name} -I -S -c {hook_wiring.LOADER} {ROOT}/src aidd hook pre-tool", r.stdout)
        self.assertIn('"tool_name": "Edit"', r.stdout.split(ran.name, 1)[1])

    def test_without_uv_an_old_python3_still_fails_open_or_closed(self):
        path = self.fake_python(3)
        if shutil.which("uv", path=path):
            self.skipTest("uv is on the base PATH")
        self.assertEqual(self.run_hook(path).returncode, 0)
        r = self.run_hook(path, AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("it needs Python 3.11 or later, or uv with a Python outside any virtual environment", r.stderr)

    def test_a_guard_that_crashes_is_not_run_twice(self):
        path = self.fake_python(1)
        ran = self.fake_uv()
        r = self.run_hook(path, AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn(ran.name, r.stdout)


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
        with mock.patch.dict(doctor_probes.MANAGED_SETTINGS_DIRS, {"linux": str(self.system)}):
            return doctor_probes.managed_settings_sources(platform="linux", home=self.home)

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
        adoption.init(
            project,
            adoption.InitOptions(profile=profile, ci="none", links=[], skill=False, approvers=["@a", "@b"], specialists={"security": ["@s"]}, harnesses=[]),
        )
        (project / ".claude").mkdir(exist_ok=True)  # Claude Code in use here
        with mock.patch.object(doctor_probes, "managed_settings_sources", return_value=managed):
            return doctor_checks.doctor(project)

    def test_audited_warns_without_managed_settings(self):
        report = self.doctor("audited", [])
        (msg,) = [m for lvl, m in report if "managed settings" in m]
        self.assertIn(("warn", msg), report)
        self.assertIn("templates/claude/managed-settings.json", msg)

    def test_audited_with_managed_settings_is_ok(self):
        report = self.doctor("audited", ["/etc/claude-code/managed-settings.json"])
        self.assertIn(("ok", next(m for lvl, m in report if "managed settings" in m)), report)

    def test_other_profiles_do_not_ask_for_them(self):
        self.assertFalse([m for _, m in self.doctor("team", []) if "managed settings" in m])


if __name__ == "__main__":
    unittest.main()
