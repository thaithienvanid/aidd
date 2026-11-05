"""What `aidd init` tells a person and where it wires each agent: a restart line that names every agent it set up,
the files that showed each agent, the aidd plugin shared with the project instead of copied into it, a user launcher
that never points at a plugin's moving folder, the commit a git install recorded, the plugin's own `aidd`, and a run
again where aidd is already set up."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git, ROOT

from aidd import __version__
from aidd.kernel import documents
from aidd.setup import adoption, pins

POSIX = os.name != "nt" and shutil.which("sh") is not None


class RestartNoticeTests(unittest.TestCase):
    def test_it_names_each_agent_whose_files_init_wrote_and_none_it_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            actions = [
                "wrote    opencode.json (the ask rules)",
                "updated  .claude/settings.json (enables aidd@aidd)",
                "wrote    .agents/mcp_config.json (the aidd MCP server)",
                "kept     .grok/aidd.json (exists; --force replaces it)",
                "vendored .agents/skills/aidd (aidd 1.0.0)",
            ]
            agents = adoption.agents_to_restart(actions, root)
        self.assertEqual(agents, ["Claude Code", "Google Antigravity", "OpenCode v2"])
        self.assertEqual(
            adoption.restart_notice(agents),
            "Restart Claude Code, Google Antigravity, and OpenCode v2 in this folder: each loads aidd's skill, MCP server, and ask rules only when a session starts.",
        )

    def test_it_names_each_question_the_restart_brings_from_what_init_did(self):
        plugins = "updated  .claude/settings.json (enables aidd@aidd: Claude Code offers it to everyone who trusts this folder)"
        server = "wrote    .mcp.json (the aidd MCP server)"
        tools = "updated  .claude/settings.json (aidd's MCP tools risk, status run with no prompt)"
        cases = [
            # (the agents, what init did, the questions asked, in order: trust, plugins, the server, the tools' note)
            (["Claude Code"], [plugins, tools], ["trust", "plugins", "tools"]),
            (["Claude Code"], [server], ["trust", "server"]),
            (["Codex"], ["updated  .codex/rules/aidd.rules (the ask rules)"], ["trust"]),
            (["Cursor"], ["wrote    .cursor/x"], []),
        ]
        marks = {"trust": "trust this folder?", "plugins": "install the plugins", "server": "`aidd` MCP server in `.mcp.json`", "tools": "own MCP tools"}
        for agents, actions, asked in cases:
            lines = adoption.restart_notice(agents, actions).splitlines()
            self.assertTrue(lines[0].startswith("Restart "), lines)
            found = [k for line in lines[2:] for k, mark in marks.items() if mark in line]
            self.assertEqual(found, asked, (agents, lines))

    def test_a_plugin_install_is_claude_codes(self):
        self.assertEqual(adoption.agents_to_restart(["ran      claude plugin install aidd@aidd"], Path(".")), ["Claude Code"])
        self.assertEqual(adoption.agents_to_restart(["ran      claude plugin install aidd@aidd"], Path("."), ["codex"]), ["Claude Code"])

    def test_only_the_agents_init_wired_are_named_never_the_team_files_it_wrote_for_every_agent(self):
        """`init --aidd-team --harness codex` writes the domain packs into `.claude/skills/`, which no Claude Code needs to
        load: only Codex is named."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            actions = [
                "updated  .codex/rules/aidd.rules (the ask rules)",
                "wrote    .claude/skills/aidd-payments/SKILL.md (the delivery team)",
                "wrote    .claude/agents/aidd-developer.md (the delivery team)",
            ]
            self.assertEqual(adoption.agents_to_restart(actions, root, ["codex"]), ["Codex"])
            self.assertEqual(adoption.agents_to_restart(actions, root, ["codex", "claude-code"]), ["Claude Code", "Codex"])
            self.assertEqual(
                adoption.restart_notice(["Codex"]), "Restart Codex in this folder: it loads aidd's skill, MCP server, and ask rules only when a session starts."
            )

    def test_init_team_for_codex_alone_names_codex(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            r = aidd_subprocess(
                "init", "--aidd-team", "--harness", "codex", "--profile", "solo", "--ci", "none", "--approvers", "email:me@example.com", cwd=root
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((root / ".claude" / "skills").is_dir(), r.stdout)  # the packs, written for every agent
            self.assertIn("Restart Codex in this folder", r.stdout)
            self.assertNotIn("Restart Claude Code", r.stdout)

    def test_init_names_the_file_that_showed_each_agent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            (root / ".opencode").mkdir()
            (root / "opencode.json").write_text("{}\n", encoding="utf-8")
            actions = adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["email:me@example.com"]))
        self.assertIn("detected OpenCode v2 (found opencode.json)", actions)


class NoRemoteTests(unittest.TestCase):
    """With no git remote, `aidd init` writes no CI files unless `--ci` asks, and its dry run shows the config it writes."""

    def repo(self, d: str, remote: bool) -> Path:
        root = Path(d)
        git(root, "init", "-q", "-b", "main")
        if remote:
            git(root, "remote", "add", "origin", "https://github.com/example/app.git")
        for rel in ("src/auth/login.js", "src/orders.js"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("x\n", encoding="utf-8")
        return root

    def test_the_ci_files_follow_the_remote_unless_ci_is_named(self):
        cases = [
            # (a git remote, the --ci given, whether init writes the GitHub workflow)
            (False, None, False),
            (True, None, True),
            (False, "github", True),
            (True, "none", False),
        ]
        for remote, ci, workflow in cases:
            with tempfile.TemporaryDirectory() as d:
                root = self.repo(d, remote)
                flags = ["--ci", ci] if ci else []
                r = aidd_subprocess("init", "--profile", "solo", "--harness", "none", "--test", "true", *flags, cwd=root)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual((root / ".github" / "workflows" / "aidd-tests.yml").is_file(), workflow, (remote, ci))
                self.assertEqual("aidd init --ci github" in r.stdout, not remote and ci is None, (remote, ci, r.stdout))

    def test_the_dry_run_shows_the_config_init_writes_and_the_folders_that_ask(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.repo(d, remote=False)
            r = aidd_subprocess("init", "--dry-run", "--profile", "team", cwd=root)
            self.assertEqual(list(p.name for p in root.iterdir() if p.name != ".git"), ["src"], "a dry run writes nothing")
        config = r.stdout.split("```yaml\n", 1)[1].split("```", 1)[0]
        self.assertEqual(documents.parse_yaml(config, "config")["profile"], "team")
        self.assertIn("`src/auth/` (auth)", r.stdout)
        self.assertNotIn("characterization", r.stdout)


class PluginSharingTests(unittest.TestCase):
    """With the aidd plugin enabled, init enables it for the project instead of copying its MCP server and skill."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        user = Path(tmp.name) / "claude"
        user.mkdir()
        (user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(user)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def init(self, **options) -> list[str]:
        return adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["email:me@example.com"], harnesses=["claude-code"], **options)
        )

    def settings(self) -> dict:
        return json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_the_project_enables_the_plugin_and_holds_no_copy_of_it(self):
        actions = self.init()
        data = self.settings()
        self.assertEqual(data["enabledPlugins"], {"aidd@aidd": True})
        self.assertEqual(data["extraKnownMarketplaces"]["aidd"]["source"], {"source": "github", "repo": "thaithienvanid/aidd"})
        self.assertNotIn("hooks", data)
        self.assertFalse((self.root / ".mcp.json").exists())
        self.assertFalse((self.root / ".claude" / "skills" / "aidd").exists())
        self.assertTrue(any(a.startswith("updated  .claude/settings.json (enables aidd@aidd: Claude Code offers it to everyone") for a in actions), actions)
        self.assertEqual(adoption.agents_to_restart(actions, self.root), ["Claude Code"])
        again = self.init()  # nothing to add
        self.assertTrue(any(a.startswith("kept     .claude/settings.json (it enables the aidd plugin") for a in again), again)

    def test_a_plugin_the_project_turned_off_stays_off(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(make:*)"]}, "enabledPlugins": {"aidd-team@aidd": False}}), encoding="utf-8"
        )
        self.init(aidd_team=True)
        data = self.settings()
        self.assertEqual(data["enabledPlugins"], {"aidd-team@aidd": False, "aidd@aidd": True})
        # The person's own rule stays first, and the plugin's own MCP tools run with no prompt (R327).
        from aidd.setup import mcp_wiring

        self.assertEqual(data["permissions"]["allow"], ["Bash(make:*)", *mcp_wiring.claude_tool_names("mcp__plugin_aidd_aidd__")])
        self.assertIn("Bash(git push --force*)", data["permissions"]["ask"])

    def test_a_repository_that_claims_the_plugin_still_gets_the_files(self):
        (Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json").write_text("{}", encoding="utf-8")  # this user has no plugin
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
        self.init()
        self.assertTrue((self.root / ".mcp.json").is_file())  # the repository's own copy of the MCP server and the skill
        self.assertTrue((self.root / ".claude" / "skills" / "aidd").exists())
        self.assertIn("Bash(git push --force*)", self.settings()["permissions"]["ask"])

    def test_a_marketplace_of_another_source_is_never_enabled(self):
        theirs = {"source": {"source": "github", "repo": "someone/aidd"}}
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"extraKnownMarketplaces": {"aidd": theirs}}), encoding="utf-8")
        actions = self.init()
        data = self.settings()
        self.assertEqual(data["extraKnownMarketplaces"]["aidd"], theirs)
        self.assertNotIn("enabledPlugins", data)
        self.assertTrue((self.root / ".mcp.json").is_file())  # the repository's own copy is wired instead
        self.assertTrue(any(a.startswith("warn     .claude/settings.json names another source for the `aidd` marketplace") for a in actions), actions)

    def test_local_settings_that_turn_the_plugin_off_or_move_its_marketplace_get_the_files(self):
        theirs = {"source": {"source": "github", "repo": "someone/aidd"}}
        for local in ({"enabledPlugins": {"aidd@aidd": False}}, {"extraKnownMarketplaces": {"aidd": theirs}}):
            with self.subTest(local=local):
                shutil.rmtree(self.root / ".claude", ignore_errors=True)
                (self.root / ".claude").mkdir()
                (self.root / ".claude" / "settings.local.json").write_text(json.dumps(local), encoding="utf-8")
                self.init()
                self.assertTrue((self.root / ".mcp.json").is_file())

    def test_team_files_are_copied_unless_the_user_enabled_the_team_plugin(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd-team@aidd": True}}), encoding="utf-8")
        self.init(aidd_team=True)
        self.assertTrue(any((self.root / ".claude" / "agents").glob("aidd-*.md")))


class InstalledCommitTests(unittest.TestCase):
    SHA = "8016d71735b729ba4c23c2f0c73a2b990cfa1450"

    def commit(self, direct_url: dict | None, here: bool = True) -> str | None:
        dist = mock.Mock()
        dist.locate_file.return_value = Path(pins.__file__).resolve().parents[2] if here else Path("/nowhere")
        dist.read_text.return_value = json.dumps(direct_url) if direct_url is not None else None
        with mock.patch("importlib.metadata.distribution", return_value=dist):
            return pins.installed_commit()

    def test_a_git_install_of_aidd_pins_ci_to_its_commit(self):
        url = {"url": "https://github.com/thaithienvanid/aidd", "vcs_info": {"vcs": "git", "commit_id": self.SHA}}
        self.assertEqual(self.commit(url), self.SHA)
        self.assertEqual(self.commit({**url, "url": "https://github.com/thaithienvanid/aidd.git"}), self.SHA)

    def test_anything_else_pins_nothing(self):
        url = {"url": "https://github.com/thaithienvanid/aidd", "vcs_info": {"vcs": "git", "commit_id": self.SHA}}
        self.assertIsNone(self.commit({**url, "url": "https://github.com/someone/fork"}))
        self.assertIsNone(self.commit({**url, "vcs_info": {"vcs": "git", "commit_id": "main"}}))
        self.assertIsNone(self.commit(None))  # a wheel: no direct_url.json
        self.assertIsNone(self.commit(url, here=False))  # an installed copy that is not the code running now


@unittest.skipUnless(POSIX and shutil.which("python3"), "the plugin's aidd is an sh script that finds python3")
class PluginExecutableTests(unittest.TestCase):
    """The skill names the plugin's own `aidd` in Claude Code, so it works there with the plugin alone."""

    SCRIPT = ROOT / "scripts" / "aidd"

    def test_it_runs_aidd_from_the_plugins_source(self):
        self.assertTrue(os.access(self.SCRIPT, os.X_OK))
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([str(self.SCRIPT), "--version"], cwd=d, capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": d})
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"aidd {__version__}"), r.stderr)

    def test_it_never_runs_a_source_inside_the_folder_it_runs_in(self):
        r = subprocess.run([str(self.SCRIPT), "--version"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("the plugin's source is inside this folder", r.stderr)


if __name__ == "__main__":
    unittest.main()


class RunAgainTests(unittest.TestCase):
    """Init run again where aidd is set up keeps the config, says only what it did, and offers no Day-0 commit."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        (self.root / "internal" / "ledger").mkdir(parents=True)
        (self.root / "go.mod").write_text("module x\n", encoding="utf-8")
        (self.root / "internal" / "ledger" / "post.go").write_text("package ledger\n", encoding="utf-8")
        git(self.root.parent, "init", "-q", str(self.root))
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=me", "-c", "user.email=me@example.com", "commit", "-qm", "the code")
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        self.user = Path(tmp.name) / "claude"
        self.user.mkdir()
        self.env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.user), "HOME": tmp.name}

    def init(self) -> str:
        done = aidd_subprocess(
            "init", "--approvers", "email:me@example.com", "--ci", "github", "--harness", "none", "--ref", "a" * 40, cwd=self.root, env=self.env
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_it_says_only_what_it_did(self):
        first = self.init()
        self.assertIn("wrote the sensitive areas it found as `risks.areas`", first)
        self.assertIn("import .github/rulesets/main.json", first)
        again = self.init()
        self.assertIn("aidd was already set up here, so init kept your config", again)
        self.assertIn("pinned   the aidd workflow", first)
        for said in ("wrote the sensitive areas", "import .github/rulesets", "chore/adopt-aidd", "A person merges the setup", "pinned"):
            self.assertNotIn(said, again)

    def test_no_claude_code_hint_where_the_aidd_plugin_is_on(self):
        options = adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["email:me@example.com"])
        (self.root / ".codex").mkdir()  # an agent that takes ask rules, so init hints at the other agents this machine has
        with (
            mock.patch.object(adoption, "installed_harnesses", return_value=["claude-code"]),
            mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.user)}),
        ):
            self.assertTrue(any(a.startswith("hint     this machine has Claude Code") for a in adoption.init(self.root, options)))
            (self.user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
            self.assertFalse(any("this machine has Claude Code" in a for a in adoption.init(self.root, options)))

    def test_doctor_names_claude_code_where_only_the_persons_plugin_brings_it(self):
        from aidd.setup import doctor_checks

        self.init()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.user)}):
            said = [m for _, m in doctor_checks.doctor(self.root)]
            self.assertFalse(any(m.startswith("Claude Code: your aidd plugin") for m in said))
            (self.user / "settings.json").write_text(json.dumps({"enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
            said = [m for _, m in doctor_checks.doctor(self.root)]
        self.assertTrue(any(m.startswith("Claude Code: your aidd plugin brings the skill") and "--harness claude-code" in m for m in said), said)
