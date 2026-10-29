"""`aidd doctor --autopilot` on what an unattended run holds: Meta's Agents Rule of Two, and long-lived GitHub tokens.

Both are warnings, never failures. The token check reads only a value's prefix, so no test may find any part of a
value in what aidd prints.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import run_cli

from aidd.setup import antigravity_wiring, autopilot_readiness, codex_wiring, grok_wiring, harness_configs, opencode_wiring, team_install

CLASSIC = "ghp_" + "Zq9" * 12
OAUTH = "gho_" + "Wx7" * 12


def settings(root: Path, data: dict) -> None:
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "settings.local.json").write_text(json.dumps(data), encoding="utf-8")


class LongLivedTokenTests(unittest.TestCase):
    """A classic or OAuth app token (`ghp_`, `gho_`) can live until someone revokes it; aidd names its kind only."""

    def test_it_names_the_variable_and_the_kind_and_never_the_value(self):
        env = {"GH_TOKEN": CLASSIC, "GITHUB_TOKEN": OAUTH, "PATH": "/usr/bin"}
        self.assertEqual(
            autopilot_readiness.long_lived_github_tokens(env),
            [("GH_TOKEN", "a classic personal access token"), ("GITHUB_TOKEN", "an OAuth app token")],
        )
        found = autopilot_readiness.token_checks(env)
        self.assertEqual([lvl for lvl, _ in found], ["warn", "warn"])
        text = "\n".join(m for _, m in found)
        for value in (CLASSIC, OAUTH):
            self.assertNotIn(value[4:10], text)  # no part of the secret
        self.assertNotIn("ghp_", text)
        self.assertIn("fine-grained token with an expiry", text)
        self.assertIn("GitHub App user token", text)
        self.assertIn("docs/AUTOPILOT.md, Credentials for a run", text)

    def test_a_token_that_expires_or_another_variable_says_nothing(self):
        for value in ("github_pat_" + "A" * 40, "ghu_" + "B" * 36, "ghs_" + "C" * 36, "", "ghp"):
            with self.subTest(value=value[:6]):
                self.assertEqual(autopilot_readiness.token_checks({"GH_TOKEN": value, "GITHUB_TOKEN": value}), [])
        self.assertEqual(autopilot_readiness.token_checks({"MY_GITHUB_PAT": CLASSIC}), [])  # only the two aidd reads

    def test_the_docs_hold_the_section_the_warning_names(self):
        page = (helpers.ROOT / "docs" / "AUTOPILOT.md").read_text(encoding="utf-8")
        self.assertIn("\n## Credentials for a run\n", page)


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorTokenTests(unittest.TestCase):
    def test_doctor_warns_and_prints_no_part_of_the_value(self):
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            settings(root, {"sandbox": {"enabled": True}, "permissions": {"allow": autopilot_readiness.needed_rules(root), "defaultMode": "dontAsk"}})
            code_without, _ = run_cli("doctor", "--autopilot")
            with mock.patch.dict(os.environ, {"GH_TOKEN": CLASSIC}):
                code, out = run_cli("doctor", "--autopilot")
                json_code, json_out = run_cli("doctor", "--autopilot", "--json")
            self.assertEqual((code, json_code), (code_without, code_without), out)  # a warning, never a failure
            self.assertIn("[warn] `GH_TOKEN` holds a classic personal access token", out)
            for shown in (out, json_out):
                self.assertNotIn(CLASSIC[4:10], shown)
            self.assertIn("a classic personal access token", json_out)
            self.assertFalse(list(root.rglob("*Zq9Zq9*")))
            for path in root.rglob("*"):
                if path.is_file() and ".git" not in path.parts:
                    self.assertNotIn(b"Zq9Zq9", path.read_bytes(), path)


@unittest.skipUnless(shutil.which("git"), "git is required")
class RuleOfTwoTests(unittest.TestCase):
    """Untrusted input, a credential, and egress no allowlist limits: a run should never hold all three."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # Outside aidd's dev container, wherever the suite runs.
        patcher = mock.patch.object(autopilot_readiness, "DEVCONTAINER_EGRESS_LIST", self.tmp / "no-such-list")
        patcher.start()
        self.addCleanup(patcher.stop)

    def check(self, root: Path, env: dict) -> tuple[str, str]:
        return autopilot_readiness.rule_of_two_check(root, env)

    def test_all_three_legs_warn_and_name_the_next_step(self):
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            settings(root, {"permissions": {"allow": ["WebFetch"]}})
            level, message = self.check(root, {"GH_TOKEN": "github_pat_" + "S" * 30})
            self.assertEqual(level, "warn")
            for must in ("Meta's Agents Rule of Two (2025-10-31)", "untrusted input (`WebFetch` allowed)", "credentials", "egress"):
                self.assertIn(must, message)
            self.assertIn("aidd init --devcontainer", message)
            self.assertIn("unset the credentials", message)
            self.assertNotIn("S" * 10, message)
            self.assertIn(("warn", message), autopilot_readiness.autopilot_checks(root, {"GH_TOKEN": "x"}))
            self.assertNotIn("fail", [lvl for lvl, m in autopilot_readiness.autopilot_checks(root, {"GH_TOKEN": "x"}) if "Rule of Two" in m])

    def test_dropping_any_one_leg_holds_the_rule(self):
        creds = {"ANTHROPIC_API_KEY": "k"}
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            settings(root, {"permissions": {"allow": ["WebFetch"]}})
            self.assertEqual(self.check(root, {}), ("ok", "Meta's Agents Rule of Two (2025-10-31) holds: no variable named like a credential"))
            settings(root, {"permissions": {"allow": []}})
            self.assertEqual(self.check(root, creds)[0], "ok")
            settings(root, {"sandbox": {"enabled": True}, "permissions": {"allow": ["WebFetch(domain:docs.python.org)", "WebSearch"]}})
            level, message = self.check(root, creds)
            self.assertEqual(level, "ok", message)
            self.assertIn("the sandbox holds shell commands", message)
            (self.tmp / "allowed-hosts").write_text("github.com\n", encoding="utf-8")
            settings(root, {"permissions": {"allow": ["WebFetch"]}})
            with (
                mock.patch.object(autopilot_readiness, "DEVCONTAINER_EGRESS_LIST", self.tmp / "allowed-hosts"),
                mock.patch.object(autopilot_readiness, "devcontainer_firewall_up", return_value=True),
            ):
                level, message = self.check(root, creds)
            self.assertEqual(level, "ok", message)
            self.assertIn("dev container firewall is up", message)

    def test_a_dev_container_whose_firewall_did_not_start_is_open(self):
        """The image writes the allowlist whether or not the firewall starts; only the firewall's marker says it is up."""
        creds = {"ANTHROPIC_API_KEY": "k"}
        (self.tmp / "allowed-hosts").write_text("github.com\n", encoding="utf-8")
        with (
            helpers.adopted_repo("team", claude_hooks=True) as root,
            mock.patch.object(autopilot_readiness, "DEVCONTAINER_EGRESS_LIST", self.tmp / "allowed-hosts"),
            mock.patch.object(autopilot_readiness, "DEVCONTAINER_FIREWALL_ACTIVE", self.tmp / "run" / "active"),
        ):
            settings(root, {"permissions": {"allow": ["WebFetch"]}})
            level, message = self.check(root, creds)
            self.assertEqual(level, "warn", message)
            self.assertIn("start the dev container's firewall, which did not start here", message)
            self.assertIn("sudo /usr/local/sbin/aidd-init-firewall", message)
            found = autopilot_readiness.autopilot_checks(root, creds)
            self.assertIn("warn", [lvl for lvl, m in found if "its firewall did not start" in m and "rebuild the container" in m])
            # A marker anyone could have written is no proof: it must be root's, in root's folder.
            (self.tmp / "run").mkdir()
            (self.tmp / "run" / "active").write_text("github.com\n", encoding="utf-8")
            if os.name != "nt" and os.geteuid() != 0:
                self.assertFalse(autopilot_readiness.devcontainer_firewall_up())
                self.assertEqual(self.check(root, creds)[0], "warn")

    @unittest.skipIf(os.name == "nt", "file owners are POSIX here")
    def test_the_marker_counts_only_as_roots_own_file(self):
        candidates = [Path(p) for p in ("/etc/hosts", "/private/etc/hosts", "/etc/passwd", "/private/etc/passwd")]
        usable = [
            p for p in candidates if not p.is_symlink() and not p.parent.is_symlink() and p.is_file() and p.stat().st_uid == 0 and p.parent.stat().st_uid == 0
        ]
        usable = [p for p in usable if not (p.stat().st_mode | p.parent.stat().st_mode) & 0o022]
        if not usable:
            self.skipTest("no root-owned file to stand in for the marker")
        first = usable[0].read_text(encoding="ascii", errors="replace").splitlines()[0].strip()
        with mock.patch.object(autopilot_readiness, "DEVCONTAINER_FIREWALL_ACTIVE", usable[0]):
            with mock.patch.object(autopilot_readiness, "current_start", return_value=first):
                self.assertTrue(autopilot_readiness.devcontainer_firewall_up())
            # A marker an earlier start left, or one where /proc cannot say which start this is, proves nothing.
            for now in ("aidd-start another-boot 1", None):
                with mock.patch.object(autopilot_readiness, "current_start", return_value=now):
                    self.assertFalse(autopilot_readiness.devcontainer_firewall_up())
        link = self.tmp / "active"
        link.symlink_to(usable[0])
        with mock.patch.object(autopilot_readiness, "DEVCONTAINER_FIREWALL_ACTIVE", link):
            self.assertFalse(autopilot_readiness.devcontainer_firewall_up())

    def test_the_sandbox_does_not_hold_what_runs_outside_it(self):
        creds = {"GITHUB_TOKEN": "t"}
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            for opens in (
                {"sandbox": {"enabled": True}, "permissions": {"allow": ["WebFetch"]}},
                {"sandbox": {"enabled": True, "network": {"allowedDomains": ["*"]}}, "permissions": {"allow": ["WebSearch"]}},
                {"sandbox": {"enabled": True}, "permissions": {"defaultMode": "bypassPermissions"}},
                # An allow rule also approves a failed command's retry outside the sandbox, with no prompt.
                {"sandbox": {"enabled": True}, "permissions": {"allow": ["WebSearch", "Bash(curl *)"]}},
                {"sandbox": {"enabled": True, "excludedCommands": ["docker *"]}, "permissions": {"allow": ["WebSearch"]}},
            ):
                with self.subTest(settings=opens):
                    settings(root, opens)
                    self.assertEqual(self.check(root, creds)[0], "warn")
            for holds in (
                {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False}, "permissions": {"allow": ["WebSearch", "Bash(curl *)"]}},
                {"sandbox": {"enabled": True}, "permissions": {"allow": ["WebSearch", "Bash(aidd *)"]}},
            ):
                with self.subTest(settings=holds):
                    settings(root, holds)
                    self.assertEqual(self.check(root, creds)[0], "ok")

    def test_a_shell_rule_that_reads_the_outside_is_untrusted_input(self):
        reads = ("Bash", "Bash(*)", "Bash(curl:*)", "Bash(curl *)", "Bash(wget:*)", "Bash(gh issue view:*)", "Bash(gh pr view:*)", "Bash(gh api:*)")
        for rule in (*reads, "Bash(gh:*)", "Bash(gh pr:*)", "Bash(cu*)", "Bash(curl -s https://example.com/x)"):
            with self.subTest(rule=rule):
                self.assertTrue(autopilot_readiness._shell_reads_untrusted(rule))
        for rule in ("Bash(aidd *)", "Bash(gh pr create:*)", "Bash(npm test:*)", "Bash(git status)", "Bash(gh)", "Read(/**)", "Bash(curlie-lint:*)"):
            with self.subTest(rule=rule):
                self.assertFalse(autopilot_readiness._shell_reads_untrusted(rule))
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            settings(root, {"permissions": {"allow": ["Bash(gh issue view:*)"]}})
            level, message = self.check(root, {"GITHUB_TOKEN": "t"})
            self.assertEqual(level, "warn", message)
            self.assertIn("untrusted input (`Bash(gh issue view:*)` allowed)", message)

    def test_a_server_reads_untrusted_text_by_a_whole_word_only(self):
        for name, server in (
            ("slack", {"command": "npx", "args": ["slack-mcp"]}),
            ("team-chat", {"command": "discord-mcp"}),
            ("inbox", {"url": "https://gmail.mcp.example/mcp"}),
            ("docs", {"command": "npx", "args": ["@notionhq/notion-mcp-server"]}),
            ("wiki", {"url": "https://mcp.atlassian.com/v1/sse"}),
            ("errors", {"command": "uvx", "args": ["mcp-server-sentry"]}),
            ("desk", {"command": "zendesk-mcp"}),
            ("tracker", {"url": "https://mcp.linear.app/mcp"}),
            ("tickets", {"command": "jira-mcp"}),
            ("mcpWebSearch", {"command": "node"}),
        ):
            with self.subTest(name=name):
                self.assertTrue(autopilot_readiness._reads_untrusted(name, server))
        for name, server in (
            ("research", {"command": "node", "args": ["notes.js"]}),
            ("vectors", {"command": "uvx", "args": ["chromadb-mcp"]}),
            ("bundler", {"command": "node", "args": ["/srv/webpack/server.js"]}),
            ("site", {"command": "node", "args": ["/home/me/website/mcp.js"]}),
            ("notes", {"command": "node", "env": {"MODE": "web"}}),
        ):
            with self.subTest(name=name):
                self.assertFalse(autopilot_readiness._reads_untrusted(name, server))

    def test_one_run_reads_the_users_record_once(self):
        home = self.tmp / "claude-once"
        home.mkdir()
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        with helpers.adopted_repo("team", claude_hooks=True) as root, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
            real = Path.read_text
            reads = []

            def counted(path, *a, **kw):
                if path.name == ".claude.json":
                    reads.append(path)
                return real(path, *a, **kw)

            with mock.patch.object(Path, "read_text", counted):
                autopilot_readiness.autopilot_checks(root, {"GITHUB_TOKEN": "t"})
            self.assertEqual(len(reads), 1, reads)
            # Outside a run nothing is kept: a change shows at once.
            servers = {"mcpServers": {"pw": {"command": "npx", "args": ["@playwright/mcp"]}}}
            (home / ".claude.json").write_text(json.dumps(servers), encoding="utf-8")
            self.assertIn("the MCP server `pw`", " ".join(autopilot_readiness.untrusted_inputs(root)))

    def test_a_name_from_a_settings_file_prints_safely(self):
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"web\x1b[2J`x": {"command": "x"}}}), encoding="utf-8")
            level, message = self.check(root, {"GITHUB_TOKEN": "t"})
            self.assertEqual(level, "warn")
            self.assertIn("the MCP server `web?[2J?x`", message)
            self.assertNotIn("\x1b", message)

    def test_an_mcp_server_that_reads_the_web_or_issues_is_untrusted_input(self):
        creds = {"GITHUB_TOKEN": "t"}
        home = self.tmp / "claude"
        home.mkdir()
        with helpers.adopted_repo("team", claude_hooks=True) as root, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
            settings(root, {"sandbox": {"enabled": True}})
            self.assertEqual(self.check(root, creds)[0], "ok")  # aidd's own MCP server reads no web
            servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")) if (root / ".mcp.json").exists() else {"mcpServers": {}}
            servers["mcpServers"]["pw"] = {"command": "npx", "args": ["@playwright/mcp@latest"]}
            (root / ".mcp.json").write_text(json.dumps(servers), encoding="utf-8")
            level, message = self.check(root, creds)
            self.assertEqual(level, "warn", message)  # it runs outside the sandbox, so egress is open too
            self.assertIn("the MCP server `pw`", message)
            del servers["mcpServers"]["pw"]
            servers["mcpServers"]["notes"] = {"command": "node", "env": {"MODE": "web"}}  # never read by its environment
            (root / ".mcp.json").write_text(json.dumps(servers), encoding="utf-8")
            self.assertEqual(self.check(root, creds)[0], "ok")
            record = {"mcpServers": {"tracker": {"type": "http", "url": "https://mcp.linear.app/mcp"}}}
            (home / ".claude.json").write_text(json.dumps(record), encoding="utf-8")
            level, message = self.check(root, creds)
            self.assertEqual(level, "warn", message)
            self.assertIn("the MCP server `tracker`", message)
            record = {"projects": {str(root): {"mcpServers": {"search": {"command": "brave-search-mcp"}}}}}
            (home / ".claude.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertIn("the MCP server `search`", self.check(root, creds)[1])
            (home / ".claude.json").write_text("not json", encoding="utf-8")
            self.assertEqual(self.check(root, creds)[0], "ok")


def wire(root: Path, harness: str) -> None:
    """aidd's guard wiring for one harness, as init writes it, without the user launcher init also writes."""
    if harness == "opencode":
        for rel, text in opencode_wiring.files().items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return
    if harness == "antigravity":
        path, data = root / antigravity_wiring.HOOKS_FILE, {antigravity_wiring.HOOK_NAME: antigravity_wiring.hook_spec()}
    else:
        wiring = {"codex": codex_wiring.FILE, "grok-build": grok_wiring.FILE}[harness]
        path, data = root / wiring.path, {"hooks": wiring.hook_spec()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@unittest.skipUnless(shutil.which("git"), "git is required")
class OtherHarnessTests(unittest.TestCase):
    """`doctor --autopilot` outside Claude Code: the guard each harness's own wiring runs counts, the MCP servers aidd
    can read in Codex's and OpenCode's config count toward the Rule of Two, and a harness it cannot read is named,
    never reported clear."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        homes = {"CODEX_HOME": str(self.tmp / "codex"), "XDG_CONFIG_HOME": str(self.tmp / "xdg"), "CLAUDE_CONFIG_DIR": str(self.tmp / "claude")}
        for patcher in (mock.patch.object(autopilot_readiness, "DEVCONTAINER_EGRESS_LIST", self.tmp / "no-such-list"), mock.patch.dict(os.environ, homes)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_guard_counts_as_wired_in_each_harness_that_runs_it(self):
        for harness, label in (("codex", "Codex"), ("grok-build", "Grok Build"), ("antigravity", "Google Antigravity"), ("opencode", "OpenCode V2")):
            with self.subTest(harness), helpers.adopted_repo("team") as root:
                self.assertNotIn(harness, autopilot_readiness.wired_harnesses(root))
                wire(root, harness)
                self.assertIn(harness, autopilot_readiness.wired_harnesses(root))
                results = autopilot_readiness.autopilot_checks(root, {})
                (guard,) = [(lvl, m) for lvl, m in results if m.startswith("the guard ")]
                self.assertEqual(guard[0], "ok", guard)
                self.assertIn(label, guard[1])
                (note,) = [(lvl, m) for lvl, m in results if "Claude Code's settings only, and Claude Code is not wired here" in m]
                self.assertEqual(note[0], "info")
                self.assertIn(f"Check the sandbox and permissions of {label} yourself", note[1])
                claude_lines = [m for lvl, m in results if m.startswith("Claude Code")]
                self.assertEqual(claude_lines, [], "no Claude Code line where Claude Code is not wired")
                path = team_install.flow_command_file(harness, "autopilot")
                self.assertIn(("warn", f"{label} has no autopilot flow ({path}): run `aidd init --team --harness {harness}`"), results)
                self.assertEqual(any(m.startswith("OpenCode: ") and "-f .opencode/commands/aidd-autopilot.md" in m for _, m in results), harness == "opencode")
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text("the flow\n", encoding="utf-8")
                self.assertIn(("ok", f"{label} has the autopilot flow ({path})"), autopilot_readiness.autopilot_checks(root, {}))

    def test_a_codex_run_is_told_to_make_the_git_directory_writable(self):
        """Codex's `workspace-write` sandbox keeps `.git` read-only, so a live run could not write its lease: the doctor
        names `--add-dir` with the git directory, until a Codex config aidd reads lists it in `writable_roots`."""
        with helpers.adopted_repo("team") as root:
            self.assertFalse([m for _, m in autopilot_readiness.autopilot_checks(root, {}) if "writable_roots" in m])
            wire(root, "codex")
            gitdir = (root / ".git").resolve()
            level, message = harness_configs.codex_git_check(root)
            self.assertEqual(level, "warn")
            self.assertIn(f"cannot write its lease in {gitdir / 'aidd'}: start Codex with `--add-dir {gitdir}`", message)
            self.assertIn(("warn", message), autopilot_readiness.autopilot_checks(root, {}))
            (root / ".codex" / "config.toml").write_text(f'[sandbox_workspace_write]\nwritable_roots = ["{root / ".git"}"]\n', encoding="utf-8")
            self.assertEqual(harness_configs.codex_git_check(root)[0], "ok")
            (root / ".codex" / "config.toml").write_text(f'[sandbox_workspace_write]\nwritable_roots = ["{root}"]\n', encoding="utf-8")
            self.assertEqual(harness_configs.codex_git_check(root)[0], "warn")  # the repository's root leaves `.git` read-only
            # An entry no path can be read from names nothing, and never stops the doctor.
            (root / ".codex" / "config.toml").write_text('[sandbox_workspace_write]\nwritable_roots = ["/a\\u0000b", "~nosuchuser_aidd/x"]\n', encoding="utf-8")
            self.assertEqual(harness_configs.codex_git_check(root)[0], "warn")

    def test_codex_and_opencode_mcp_servers_count_toward_the_rule_of_two(self):
        creds = {"GITHUB_TOKEN": "t"}
        with helpers.adopted_repo("team") as root:
            wire(root, "codex")
            self.assertEqual(autopilot_readiness.rule_of_two_check(root, creds)[0], "ok")  # no server yet
            (root / ".codex" / "config.toml").write_text('[mcp_servers.tracker]\ncommand = "npx"\nargs = ["linear-mcp"]\n', encoding="utf-8")
            level, message = autopilot_readiness.rule_of_two_check(root, creds)
            self.assertEqual(level, "warn", message)
            self.assertIn("the MCP server `tracker` (Codex)", message)
            (root / ".codex" / "config.toml").unlink()
            (self.tmp / "codex").mkdir()
            (self.tmp / "codex" / "config.toml").write_text('[mcp_servers.pw]\nurl = "https://example.com/playwright"\n', encoding="utf-8")
            self.assertIn("the MCP server `pw` (Codex)", autopilot_readiness.rule_of_two_check(root, creds)[1])  # the user's config too
        with helpers.adopted_repo("team") as root:
            wire(root, "opencode")
            (root / "opencode.json").write_text(json.dumps({"mcp": {"browser": {"type": "local", "command": ["npx", "@playwright/mcp"]}}}), encoding="utf-8")
            level, message = autopilot_readiness.rule_of_two_check(root, creds)
            self.assertEqual(level, "warn", message)
            self.assertIn("the MCP server `browser` (OpenCode V2)", message)
            note = autopilot_readiness.harness_scope_note(root)
            self.assertIn("also read the MCP servers of OpenCode V2", note[1])

    def test_a_harness_aidd_cannot_read_is_named_and_never_reported_clear(self):
        with helpers.adopted_repo("team") as root:
            wire(root, "grok-build")
            level, message = autopilot_readiness.rule_of_two_check(root, {})
            self.assertEqual(level, "ok")
            self.assertIn("leaves out the MCP servers of Grok Build", message)
            self.assertIn("did not read the MCP servers of Grok Build", autopilot_readiness.harness_scope_note(root)[1])
        with helpers.adopted_repo("team") as root:
            wire(root, "opencode")
            (root / "opencode.jsonc").write_text('{\n  // comments json cannot read\n  "mcp": {}\n}\n', encoding="utf-8")
            self.assertEqual(autopilot_readiness.unread_harnesses(root), ["opencode"])
            (root / ".codex").mkdir()
            wire(root, "codex")
            (root / ".codex" / "config.toml").write_text("mcp_servers = [", encoding="utf-8")
            self.assertEqual(autopilot_readiness.unread_harnesses(root), ["codex", "opencode"])

    def test_a_config_aidd_will_not_read_leaves_the_harness_unread_and_never_raises(self):
        """A file nested past the parser's depth, one past the size cap, a link inside the repository, and a pipe each
        leave the harness unread: none escapes as an error, and none counts as clear."""
        deep = "[" * 200_000 + "]" * 200_000
        cases = {
            "nested JSON": lambda p: p.write_text('{"mcp": ' + deep + "}", encoding="utf-8"),
            "past the cap": lambda p: p.write_text(json.dumps({"mcp": {}, "pad": "x" * harness_configs.HARNESS_CONFIG_MAX_BYTES}), encoding="utf-8"),
            "a link in the repository": lambda p: (p.symlink_to("real.json"), (p.parent / "real.json").write_text('{"mcp": {}}', encoding="utf-8")),
        }
        if hasattr(os, "mkfifo"):
            cases["a pipe"] = lambda p: os.mkfifo(p)
        for name, make in cases.items():
            with self.subTest(name), helpers.adopted_repo("team") as root:
                wire(root, "opencode")
                make(root / "opencode.json")
                self.assertIsNone(autopilot_readiness.harness_mcp_servers(root, "opencode"))
                self.assertEqual(autopilot_readiness.unread_harnesses(root), ["opencode"])
        with helpers.adopted_repo("team") as root:
            wire(root, "codex")
            (root / ".codex" / "config.toml").write_text("x = " + "[" * 200_000 + "]" * 200_000 + "\n", encoding="utf-8")
            self.assertIsNone(autopilot_readiness.harness_mcp_servers(root, "codex"))

    def test_a_linked_dotfile_in_the_home_folder_is_read(self):
        with helpers.adopted_repo("team") as root:
            wire(root, "opencode")
            dotfiles = self.tmp / "dotfiles"
            dotfiles.mkdir()
            (dotfiles / "opencode.json").write_text(json.dumps({"mcp": {"browser": {"command": ["npx", "@playwright/mcp"]}}}), encoding="utf-8")
            home = harness_configs.opencode_home()
            home.mkdir(parents=True, exist_ok=True)
            (home / "opencode.json").symlink_to(dotfiles / "opencode.json")
            self.assertEqual(list(autopilot_readiness.harness_mcp_servers(root, "opencode") or {}), ["browser"])

    def test_claude_code_alone_adds_no_note(self):
        with helpers.adopted_repo("team", claude_hooks=True) as root:
            self.assertIsNone(autopilot_readiness.harness_scope_note(root))
            self.assertNotIn("info", [lvl for lvl, _ in autopilot_readiness.autopilot_checks(root, {})])


if __name__ == "__main__":
    unittest.main()
