"""First contact: coding-agent detection, per-agent wiring, the plugin path, `aidd uninstall`, and the installer script."""

import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_subprocess, git, hermetic_environ

from aidd.cli import app as cli_app
from aidd.cli import parser as cli_parser
from aidd.setup import doctor_checks, doctor_harnesses
from aidd.setup import uninstalling
from aidd.setup import upgrading
from aidd.setup import adoption, ask_rules
from aidd.setup import doctor_probes
from aidd.setup import claude_plugins
from aidd.setup import pins
from aidd import risk
from aidd.config import harness_settings
from aidd.kernel import resources


def tree(root: Path) -> dict[str, str]:
    out = {}
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        rel = str(p.relative_to(root))
        out[rel] = os.readlink(p) if p.is_symlink() else (p.read_text(encoding="utf-8") if p.is_file() else "<dir>")
    return out


def allow_the_plugin_install(case: unittest.TestCase) -> None:
    """Lift AIDD_OFFLINE=1 for a test that fakes the `claude` CLI, so `--claude-plugins` reaches it, while the release
    lookup still answers nothing, so no git call leaves the machine."""
    for patch in (mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}), mock.patch.object(pins, "remote_refs", lambda *a, **kw: None)):
        patch.start()
        case.addCleanup(patch.stop)


def assert_skill_linked(case: unittest.TestCase, root: Path, link_dir: str = ".claude/skills") -> None:
    """The skill link: a symlink to .agents/skills/aidd, or, where symlinks are unavailable (Windows without the
    privilege), a copy equal to it, which is what `link_skill` falls back to."""
    link = root / link_dir / "aidd"
    if link.is_symlink():
        case.assertEqual((link.parent / os.readlink(link)).resolve(), (root / adoption.SKILL_REL).resolve())
    else:
        case.assertTrue(link.is_dir(), link)
        case.assertEqual(doctor_probes.tree_diff(root / adoption.SKILL_REL, link), [])


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.home = Path(self.tmp.name) / "home"
        self.bin = Path(self.tmp.name) / "bin"
        for d in (self.root, self.home, self.bin):
            d.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def detect(self):
        return adoption.detect_harnesses(self.root)

    def installed(self):
        return adoption.installed_harnesses(home=self.home, path=str(self.bin))

    def binary(self, name):
        """An installed program as the OS finds it on PATH: `name` on POSIX, `name.cmd` on Windows (PATHEXT)."""
        b = self.bin / (name + (".cmd" if os.name == "nt" else ""))
        b.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
        b.chmod(b.stat().st_mode | stat.S_IEXEC)

    def test_nothing_on_a_bare_machine(self):
        self.assertEqual(self.detect(), [])
        self.assertEqual(self.installed(), [])

    def test_the_repository_decides_never_the_machine(self):
        """init and doctor name the agents the repository shows, so every teammate's machine says the same."""
        (self.home / ".gemini").mkdir()
        (self.home / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")  # Antigravity shares ~/.gemini; the settings file is no kept agent's
        self.binary("codex")
        self.assertEqual(self.detect(), [])
        self.assertEqual(self.installed(), ["codex"])
        (self.root / ".claude").mkdir()
        self.assertEqual(self.detect(), [], "an empty .claude/ shows no wiring")
        (self.root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        (self.root / ".cursorrules").write_text("x", encoding="utf-8")
        self.assertEqual(self.detect(), ["claude-code", "cursor"])

    def test_init_hints_at_an_installed_agent_whose_wiring_matters(self):
        self.binary("claude")
        self.binary("cursor")  # reads AGENTS.md: nothing to wire, so no hint
        with mock.patch.object(adoption, "installed_harnesses", return_value=self.installed()):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
        self.assertIn("detected no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them", actions)
        self.assertIn(adoption.no_ask_rules_hint(["claude-code"]), actions)
        self.assertIn("`aidd init --harness claude-code`", adoption.no_ask_rules_hint(["claude-code", "cursor"]))
        self.assertFalse((self.root / ".claude").exists(), "nothing is wired for an agent the repository does not show")

    def test_new_agents_are_detected_by_their_own_files_never_by_aidd_output(self):
        (self.root / ".agents" / "rules").mkdir(parents=True)  # Antigravity keeps rules there; aidd only ever writes .agents/skills/
        (self.root / "opencode.json").write_text("{}", encoding="utf-8")
        (self.root / ".junie").mkdir()
        self.assertEqual(self.detect(), ["antigravity", "opencode", "junie"])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".agents" / "skills" / "aidd").mkdir(parents=True)
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            self.assertEqual(adoption.detect_harnesses(root), [])
            # The skill link `aidd init --link .claude/skills` writes is aidd's own: init run again finds no new agent.
            (root / ".claude" / "skills").mkdir(parents=True)
            (root / ".claude" / "skills" / "aidd").symlink_to("../../.agents/skills/aidd")
            self.assertEqual(adoption.detect_harnesses(root), [])
            (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")  # anything else of Claude Code's is
            self.assertEqual(adoption.detect_harnesses(root), ["claude-code"])

    def test_copilot_by_its_instructions_file(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Copilot\n", encoding="utf-8")
        self.assertEqual(self.detect(), ["copilot"])

    def test_init_wires_the_session_agent_and_says_so_unless_it_is_left_out(self):
        """`aidd init` in an agent session wires that session's agent from the variable its vendor documents, and says so in one
        line. `--harness` leaves it out. A variable no vendor documents, and no variable at all, change nothing. Doctor warns
        while aidd wrote no ask rules, decided from what it wrote."""
        claude = (".claude/settings.json", "permissions")
        vscode = (".vscode/settings.json", "chat.tools.terminal.autoApprove")
        cases = (
            # (name, repository signal, session environment, --harness, agents wired, a file that holds the ask rules, a line says so)
            ("bare", None, {}, None, [], None, False),
            ("claude code session", None, {"CLAUDECODE": "1"}, None, ["claude-code"], claude, True),
            ("a session variable its vendor does not document", None, {"CODEX_SANDBOX": "seatbelt"}, None, [], None, False),
            ("two sessions, one documented", None, {"CLAUDECODE": "1", "CODEX_SANDBOX": "seatbelt"}, None, ["claude-code"], claude, True),
            ("only an agent with no ask rules", ".cursor", {}, None, ["cursor"], None, False),
            ("the repository and the session", ".cursor", {"CLAUDECODE": "1"}, None, ["cursor", "claude-code"], claude, True),
            ("the repository shows the session's agent", ".claude/agents", {"CLAUDECODE": "1"}, None, ["claude-code"], claude, False),
            ("--harness claude-code in its session", None, {"CLAUDECODE": "1"}, ["claude-code"], ["claude-code"], claude, False),
            ("--harness cursor leaves the session's agent out", None, {"CLAUDECODE": "1"}, ["cursor"], ["cursor"], None, False),
            ("--harness copilot, which leaves no Copilot signal", None, {}, ["copilot"], ["copilot"], vscode, False),
            ("--harness none leaves it out", None, {"CLAUDECODE": "1"}, [], [], None, False),
        )
        for name, signal, env, flag, wired, rules, said in cases:
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                if signal:
                    (root / signal).mkdir(parents=True)
                with mock.patch.dict(os.environ, env), mock.patch.object(adoption, "installed_harnesses", return_value=["claude-code"]):
                    self.assertEqual(adoption.init_harnesses(root) if flag is None else flag, wired)
                    actions = adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"], harnesses=flag))
                    report = doctor_checks.doctor(root)
                hints = [a for a in actions if a == adoption.no_ask_rules_hint(["claude-code"], named=flag is not None)]
                problem = doctor_harnesses.no_ask_rules_problem(next(iter(adoption.session_harnesses(env)), None), adoption.wired_harnesses(root))
                self.assertEqual(len(hints), int(rules is None and flag != []), actions)
                self.assertEqual([lvl for lvl, m in report if m == problem], ["warning"] if rules is None else [], report)
                # With no agent that takes ask rules, the one hint names the agents this machine has: no second hint.
                self.assertEqual([a for a in actions if a.startswith("hint     this machine has")], [], actions)
                line = [a for a in actions if "runs this session" in a]
                self.assertEqual(len(line), int(said), actions)
                if said:
                    self.assertTrue(line[0].startswith("note     Claude Code runs this session (its CLAUDECODE variable is set)"), line)
                    self.assertIn("writes its ask rules into .claude/settings.json", line[0])
                    self.assertIn("--harness none", line[0])
                if rules:
                    self.assertIn(rules[1], json.loads((root / rules[0]).read_text(encoding="utf-8")))
                else:
                    self.assertFalse((root / ".claude" / "settings.json").exists(), "left out, or never named: not written")
                if "codex" in wired:
                    self.assertTrue((root / ".codex" / "rules" / "aidd.rules").is_file())

    def test_a_dry_run_says_the_same_line_the_real_run_does_and_the_flag_leaves_it_out(self):
        """Both come from one run. The line is the dry run's too, and `--harness none` is the way to leave the agent out."""
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        env = {**os.environ, "CLAUDECODE": "1"}
        base = ("--approvers", "@me", "--ci", "none")
        dry = aidd_subprocess("init", "--dry-run", *base, cwd=self.root, env=env)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        said = [line for line in dry.stdout.splitlines() if "runs this session" in line]
        self.assertEqual(len(said), 1, dry.stdout)
        self.assertFalse((self.root / ".claude" / "settings.json").exists(), "a dry run writes nothing")
        left = aidd_subprocess("init", "--harness", "none", *base, cwd=self.root, env=env)
        self.assertEqual(left.returncode, 0, left.stderr)
        self.assertNotIn("runs this session", left.stdout)
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
        real = aidd_subprocess("init", *base, cwd=self.root, env=env)
        self.assertEqual([line for line in real.stdout.splitlines() if "runs this session" in line], said, "the real run says what the dry run said")
        self.assertTrue(json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["ask"])
        self.assertTrue([line for line in real.stdout.splitlines() if line.startswith("Restart ")])

    def test_doctor_warns_once_the_ask_rules_aidd_wrote_are_gone(self):
        """The ledger, `.aidd/harness-rules.json`, says what aidd wrote; only the rules still on disk count."""
        cases = (
            # (--harness, the paths removed after init, so no agent's files are left: folders or files)
            (["claude-code"], (".claude", ".mcp.json")),
            (["copilot"], (".vscode/settings.json",)),
        )
        for flag, removed in cases:
            with self.subTest(flag=flag, removed=removed), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"], harnesses=flag))
                problem = doctor_harnesses.no_ask_rules_problem(None, adoption.detect_harnesses(root))
                self.assertNotIn(("warning", problem), doctor_checks.doctor(root))
                for target in (root / r for r in removed):
                    shutil.rmtree(target) if target.is_dir() else target.unlink()
                self.assertEqual(adoption.detect_harnesses(root), [])
                self.assertTrue((root / ".aidd" / "harness-rules.json").is_file(), "the ledger stays")
                problem = doctor_harnesses.no_ask_rules_problem(None, adoption.detect_harnesses(root))
                self.assertIn(("warning", problem), doctor_checks.doctor(root))

    def test_the_command_names_the_agent_to_restart_once_it_is_wired(self):
        """`aidd init --harness claude-code` run inside Claude Code wires it, so the restart line names it."""
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        done = aidd_subprocess("init", "--harness", "claude-code", "--approvers", "@me", "--ci", "none", cwd=self.root, env={**os.environ, "CLAUDECODE": "1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        restart = [line for line in done.stdout.splitlines() if line.startswith("Restart ")]
        self.assertEqual(len(restart), 1, done.stdout)
        self.assertIn("Claude Code", restart[0])

    def test_the_no_ask_rules_warning_names_the_agents_and_a_step_that_works(self):
        cases = (
            # (the session's agent, the agents detected, what the warning names)
            ("claude-code", [], ["`aidd init --harness claude-code`"]),
            (None, ["cursor", "kiro"], ["Cursor", "Kiro", "`aidd init --harness <key>`", "claude-code"]),
            ("antigravity", [], ["`aidd init --harness <key>`", "codex"]),
        )
        for running, detected, names in cases:
            with self.subTest(running=running, detected=detected):
                message = doctor_harnesses.no_ask_rules_problem(running, detected)
                self.assertEqual([n for n in names if n not in message], [], message)

    def test_doctor_collapses_the_agents_that_only_read_agents_md(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for signal in (".cursor", ".trae", ".junie"):
            (self.root / signal).mkdir()
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
        report = doctor_checks.doctor(self.root)
        self.assertIn(("", "3 agents read AGENTS.md: Cursor, JetBrains Junie, TraeCode"), report)
        self.assertFalse([m for _, m in report if m.endswith(": reads AGENTS.md")])
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            adoption.init(Path(d), adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
            messages = [(lvl, m) for lvl, m in doctor_checks.doctor(Path(d)) if "coding agent" in m]
            self.assertEqual(messages, [("warning", doctor_harnesses.no_ask_rules_problem(None, []))])
            self.assertNotIn("on this machine", messages[0][1])


def _assert_shares_the_plugins(self, plugins: list[str]) -> None:
    """The project's Claude Code settings enable the aidd plugins for everyone who trusts the folder, and copy no hook in."""
    data = json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    self.assertEqual({p for p, on in data["enabledPlugins"].items() if on}, set(plugins))
    self.assertEqual(data["extraKnownMarketplaces"]["aidd"]["source"], {"source": "github", "repo": claude_plugins.MARKETPLACE_REPO})
    self.assertNotIn("hooks", data)


class WiringTests(unittest.TestCase):
    assert_shares_the_plugins = _assert_shares_the_plugins

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_symlinks_the_skill_is_copied(self):
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("symlinks need a privilege here")):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"]))
        link = self.root / ".claude" / "skills" / "aidd"
        self.assertFalse(link.is_symlink())
        assert_skill_linked(self, self.root)
        self.assertTrue(any(a.startswith(f"copied   {link}") for a in actions), actions)
        # Run again: the copy is kept, not replaced or duplicated.
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("symlinks need a privilege here")):
            again = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"]))
        self.assertTrue(any(a.startswith(f"kept     {link}") for a in again), again)

    def test_no_agent_means_agents_md_only(self):
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=[]))
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
        self.assertFalse((self.root / ".mcp.json").exists())
        self.assertIn(adoption.AGENTS_MARK, (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_the_copilot_pointer(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Copilot\n\nBe request.\n", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["copilot"]))
        copilot = (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        self.assertTrue(copilot.startswith("# Copilot\n\nBe request.\n"))
        self.assertIn(adoption.AGENTS_MARK, copilot)
        # Idempotent.
        actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["copilot"]))
        self.assertEqual(copilot, (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"))
        self.assertTrue(any("kept" in a and "copilot-instructions.md" in a for a in actions))

    def test_the_claude_md_pointer_is_appended_and_removed(self):
        (self.root / "CLAUDE.md").write_text("# Project\n\nBe request.\n", encoding="utf-8")
        actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        text = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(adoption.AGENTS_MARK, text)
        self.assertTrue(text.startswith("# Project\n"))
        self.assertTrue(any(a.startswith("detected Claude Code") for a in actions))
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# Project\n\nBe request.\n")

    def test_plugins_path_uses_the_claude_cli_and_skips_repository_wiring(self):
        allow_the_plugin_install(self)
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        real_which, real_runner = shutil.which, claude_plugins.PLUGIN_RUNNER
        shutil.which = lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)
        claude_plugins.PLUGIN_RUNNER = fake_run
        try:
            actions = adoption.init(
                self.root,
                adoption.InitOptions(
                    profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"], aidd_team=True, claude_plugins=True
                ),
            )
        finally:
            shutil.which, claude_plugins.PLUGIN_RUNNER = real_which, real_runner
        self.assertEqual([c[-1] for c in calls], [claude_plugins.MARKETPLACE_REPO, "aidd@aidd", "aidd-team@aidd"])
        self.assertFalse((self.root / ".claude" / "skills" / "aidd").exists())
        self.assert_shares_the_plugins(["aidd@aidd", "aidd-team@aidd"])
        self.assertFalse((self.root / ".claude" / "agents").exists())
        self.assertTrue((self.root / ".agents" / "skills" / "aidd" / "SKILL.md").is_file())  # other harnesses still need it
        self.assertIn(harness_settings.TEAM_MARK, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue(any(a.startswith("skipped  .claude/skills/aidd") for a in actions))

    def test_plugins_path_without_the_cli_says_what_to_run(self):
        real_which = shutil.which
        shutil.which = lambda name, path=None: None if name == "claude" else real_which(name, path=path)
        try:
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=True))
        finally:
            shutil.which = real_which
        self.assertTrue(any("/plugin marketplace add thaithienvanid/aidd" in a for a in actions))


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# My app\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Agents\n\n## House rules\n\nUse pnpm.\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_leaves_the_repository_as_it_was(self):
        before = tree(self.root)
        adoption.init(
            self.root,
            adoption.InitOptions(
                profile="team",
                ci="github",
                links=list(adoption.DEFAULT_LINKS),
                approvers=["@x"],
                harnesses=["claude-code", "qwen-code", "kiro"],
                aidd_team=True,
            ),
        )
        self.assertNotEqual(tree(self.root), before)
        dry = uninstalling.uninstall(self.root)
        self.assertTrue(any(a.startswith("would remove") for a in dry))
        self.assertTrue(any("dry run" in a for a in dry))
        self.assertNotEqual(tree(self.root), before)
        done = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(any(a.startswith("removed ") for a in done))
        self.assertEqual(tree(self.root), before)

    def test_user_edits_are_kept(self):
        adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="github", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"], aidd_team=True)
        )
        agent = self.root / ".claude" / "agents" / "aidd-developer.md"
        agent.write_text(agent.read_text(encoding="utf-8").replace("model: sonnet", "model: opus"), encoding="utf-8")
        (self.root / ".github" / "pull_request_template.md").write_text("mine\n", encoding="utf-8")
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n# user comment\napprovers: ["@me"]\n', encoding="utf-8")
        tests = self.root / ".github" / "workflows" / "aidd-tests.yml"
        tests.write_text(tests.read_text(encoding="utf-8") + "# edited tests\n", encoding="utf-8")

        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(agent.is_file())
        self.assertEqual((self.root / ".github" / "pull_request_template.md").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue(cfg.is_file())
        self.assertTrue(tests.is_file())
        self.assertTrue(any("kept" in a and "developer.md" in a for a in actions))
        self.assertTrue(any("kept" in a and "config.yaml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-tests.yml" in a for a in actions))
        self.assertFalse((self.root / ".claude" / "agents" / "verifier.md").exists())

    def test_user_edits_are_kept_gitlab(self):
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="gitlab", links=[], harnesses=[]))
        gl = self.root / ".gitlab" / "aidd.gitlab-ci.yml"
        gl.write_text(gl.read_text(encoding="utf-8") + "# user customized gitlab ci\n", encoding="utf-8")
        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(gl.is_file())
        self.assertTrue(any("kept" in a and "aidd.gitlab-ci.yml" in a for a in actions))

    def test_marked_sections_are_stripped_and_a_bare_file_is_removed(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n<!-- aidd-team -->\n## Team roles (aidd-team)\n\nroles\n"
        self.assertEqual(upgrading.strip_marked_section(upgrading.strip_marked_section(text, harness_settings.TEAM_MARK), adoption.AGENTS_MARK), "# Agents\n")
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n## Ours\n\nkeep\n"
        self.assertEqual(upgrading.strip_marked_section(text, adoption.AGENTS_MARK), "# Agents\n\n## Ours\n\nkeep\n")


class InstallerAndCliTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sh"), "sh is required")
    def test_installer_parses(self):
        subprocess.run(["sh", "-n", str(ROOT / "install.sh")], check=True)
        self.assertTrue(os.access(ROOT / "install.sh", os.X_OK))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_the_cli_and_the_runbook_give_one_setup_commit_instruction(self):
        """The runbook has the agent commit the setup on `chore/adopt-aidd` with its trailer, then ask before it reaches the base branch
        (a person reviews the PR/MR on a platform); init's last line says to commit the setup as its own change."""
        from helpers import git, run_cli

        step4 = (ROOT / "llms-install.md").read_text(encoding="utf-8").split("## 4. Commit", 1)[1].split("\n## ", 1)[0]
        for phrase in (
            "`chore/adopt-aidd`",
            "Assisted-by:",
            "GitHub or GitLab",
            "A person reviews and merges it",
            "Ask the person before you merge",
            "no commit yet",
        ):
            self.assertIn(phrase, step4, phrase)
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, "--profile", "solo", "--ci", "none", "--test", "true")
        self.assertEqual(code, 0, out)
        self.assertIn("commit the setup as its own change", out)

    def test_init_refuses_a_test_command_whose_program_is_a_variable_and_writes_nothing(self):
        """`--test "PYTHONPATH=src python3 -m pytest"` would store `PYTHONPATH=src` as the program, so `aidd test` could
        never start: init says so, names the `env` form that runs, and writes no file."""
        from helpers import run_cli

        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, "--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "PYTHONPATH=src python3 -m pytest")
            self.assertEqual(code, 2, out)
            self.assertIn("error: the --test command cannot start: `PYTHONPATH=src` is an environment variable", out)
            self.assertIn("start the command with `env`, as in `env PYTHONPATH=src python3 -m pytest`", out)
            self.assertEqual([p.name for p in Path(d).iterdir()], [".git"])
            code, out = run_cli("init", d, "--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "env PYTHONPATH=src python3 -m pytest")
            self.assertEqual(code, 0, out)
            self.assertIn("command: [env, PYTHONPATH=src, python3, -m, pytest]", (Path(d) / ".aidd" / "config.yaml").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_init_says_to_restart_claude_code_only_when_it_wrote_its_files(self):
        from helpers import git, run_cli

        notice = adoption.restart_notice(["Claude Code"])
        args = ("--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "true")
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, *args, "--harness", "claude-code", "--aidd-team")
            self.assertEqual((code, out.count(notice)), (0, 1), out)
            code, out = run_cli("init", d, *args, "--harness", "claude-code", "--aidd-team")  # everything is there: kept
            self.assertEqual((code, out.count(notice)), (0, 0), out)
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, *args, "--harness", "none")
            self.assertEqual((code, out.count(notice)), (0, 0), out)
        with tempfile.TemporaryDirectory() as d:  # a repository that sits under a `.claude` folder, such as a worktree
            app = Path(d) / ".claude" / "worktrees" / "app"
            app.mkdir(parents=True)
            git(app, "init", "-q", "-b", "main")
            code, out = run_cli("init", str(app), *args, "--harness", "none")
            self.assertEqual((code, out.count(notice)), (0, 0), out)

    def test_agent_runbook_and_llms_index_match_the_cli(self):
        runbook = (ROOT / "llms-install.md").read_text(encoding="utf-8")
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        url = "https://raw.githubusercontent.com/thaithienvanid/aidd/main/install.sh"
        self.assertIn(url, installer)
        self.assertIn(url, runbook)
        for needed in (
            "aidd init --profile solo",
            "aidd init --profile team",
            "aidd doctor",
            "aidd validate",
            "aidd uninstall",
            "AIDD_REF",
            "--claude-plugins",
            "--harness",
            "--ci gitlab",
            "Assisted-by:",
            "## Never",
        ):
            self.assertIn(needed, runbook, needed)
        self.assertNotIn("mode: enforce`\n", runbook.split("## Never")[0])
        # Every flag the runbook names is a flag `aidd init` has.
        import re as _re

        flags = {w.strip("`.,:()") for w in runbook.split() if _re.fullmatch(r"`?--[a-z][a-z-]+`?[.,:()]*", w)}
        parser = cli_parser.build_parser()
        init_flags = set(parser._subparsers._group_actions[0].choices["init"]._option_string_actions)
        other_commands = {"--version", "--help", "--yes", "--force", "--context", "--user", "--paths"}  # aidd, uninstall, gate, pip
        self.assertTrue(flags <= init_flags | other_commands, flags - init_flags - other_commands)
        self.assertIn("--claude-plugins", flags)
        index = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("llms-install.md", index)
        for path in ("docs/GUIDE.md", "docs/CLI.md", "docs/TEAM.md", "docs/METHOD.md", "plugins/README.md"):
            self.assertIn(path, index, path)
            self.assertTrue((ROOT / path).is_file(), path)
        # The prompt a person gives their agent: README's first text block under "Install", naming this repository
        # (from pyproject's Source URL), followed by the runbook link, and quoted the same wherever the docs offer it.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        start = readme.split("\n## Install\n", 1)[1].split("\n## ", 1)[0]
        prompt = start.split("```text\n", 1)[1].split("\n```", 1)[0].strip()
        import tomllib

        source = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]["Source"]
        self.assertIn(source.removeprefix("https://github.com/"), prompt)
        self.assertIn("(llms-install.md)", start.split(prompt, 1)[1])
        self.assertIn(prompt, (ROOT / "docs/GUIDE.md").read_text(encoding="utf-8"))
        self.assertIn(f'"{prompt}"', (ROOT / "llms.txt").read_text(encoding="utf-8"))

    def test_cli_uninstall_is_a_dry_run_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli_app.main(["init", str(root), "--profile", "solo", "--ci", "none", "--harness", "none"]), 0)
                self.assertEqual(cli_app.main(["uninstall", str(root)]), 0)
            self.assertIn("dry run", out.getvalue())
            self.assertTrue((root / ".aidd" / "config.yaml").is_file())
            self.assertIn("detected no coding agent", out.getvalue())


class EdgeCaseTests(unittest.TestCase):
    """Edge cases of init, uninstall, and the marked sections."""

    assert_shares_the_plugins = _assert_shares_the_plugins

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_harness_none_beside_a_name_is_an_error_that_names_both(self):
        for order in (("cursor", "none"), ("none", "cursor")):
            out = io.StringIO()  # a fresh buffer for each order, so each order must say it itself
            argv = ["init", str(self.root), "--profile", "solo", "--ci", "none", *(x for h in order for x in ("--harness", h))]
            with redirect_stdout(out), redirect_stderr(out):
                code = cli_app.main(argv)
            self.assertEqual(code, 2, order)
            self.assertIn("--harness none says no coding agent, so give it alone: it cannot stand beside --harness cursor", out.getvalue())
        self.assertFalse((self.root / ".aidd").exists(), "nothing is written when the flags contradict")

    def test_marked_section_stops_at_a_top_level_heading_and_a_bare_mark_loses_only_its_line(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n# Other\n\nkeep me\n"
        self.assertEqual(upgrading.strip_marked_section(text, adoption.AGENTS_MARK), "# Agents\n\n# Other\n\nkeep me\n")
        text = "# Agents\n\n<!-- aidd -->\n\n## Ours\n\nkeep\n"
        self.assertEqual(upgrading.strip_marked_section(text, adoption.AGENTS_MARK), "# Agents\n\n\n## Ours\n\nkeep\n")

    def test_uninstall_keeps_user_files_inside_team_folders(self):
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], aidd_team=True))
        note = self.root / ".claude" / "skills" / "aidd-code-review" / "NOTES.md"
        note.write_text("mine\n", encoding="utf-8")
        mine = self.root / ".claude" / "commands" / "my-command.md"
        mine.write_text("mine\n", encoding="utf-8")
        edited = self.root / ".claude" / "commands" / "aidd-implement.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8")
        uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(note.is_file())
        self.assertTrue(mine.is_file())
        self.assertTrue(edited.is_file())
        self.assertFalse((self.root / ".claude" / "commands" / "aidd-review.md").exists())
        self.assertFalse((self.root / ".claude" / "skills" / "aidd-naming").exists())

    def test_malformed_settings_do_not_abort_init_or_uninstall(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
        actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        self.assertTrue((self.root / ".aidd" / "config.yaml").is_file())
        self.assertTrue(any("not valid JSON" in a for a in actions))
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{not json")
        # init wrote no ask rules, so there is nothing to take out; a file that turns bad after a good init is kept, with the reason.
        settings = self.root / ".claude" / "settings.json"
        settings.write_text("{}", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        settings.write_text("{not json", encoding="utf-8")
        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertEqual(settings.read_text(encoding="utf-8"), "{not json")
        self.assertTrue(any("not valid JSON" in a for a in actions))

    def test_a_local_trunk_of_another_name_keeps_its_push_ask_rules(self):
        """Fail-safe: git cannot tell the default branch of a local-only repository whose trunk is `trunk`, adopted on a
        setup branch. The push ask rules then name every branch that could be it, never only the branch checked out, and
        doctor's ok holds because they do."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "trunk")
        git(root, "commit", "-q", "--allow-empty", "-m", "start")
        git(root, "switch", "-q", "-c", "chore/adopt-aidd")
        actions = adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        candidates = ["chore/adopt-aidd", "main", "master", "trunk"]
        self.assertEqual([a for a in actions if "cannot tell the default branch" in a], [f"hint     {ask_rules.default_branch_note(candidates)}"])
        ask = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["ask"]
        for branch in ("trunk", "chore/adopt-aidd", "main", "master"):
            self.assertIn(f"Bash(git push * {branch})", ask, branch)
            self.assertIn(f"Bash(git push * refs/heads/{branch})", ask, branch)
        checks = doctor_harnesses.harness_checks(root, ["claude-code"])
        self.assertIn(("", "Claude Code: its ask rules match the risk rules"), checks)
        self.assertIn(("note", ask_rules.default_branch_note(candidates)), checks)
        rs = risk.rule_set(None)
        git(root, "switch", "-q", "trunk")
        self.assertEqual(risk.command_level(rs, "git push", cwd=str(root))["level"], "ask")  # as the harness asks
        # Once the repository names its default branch, the rules name it alone, and `aidd risk` reads it the same way.
        git(root, "config", "init.defaultBranch", "trunk")
        self.assertEqual(ask_rules.push_rule_branches(root), ["trunk"])
        self.assertFalse([m for _, m in doctor_harnesses.harness_checks(root, ["claude-code"]) if "cannot tell the default branch" in m])
        self.assertEqual(risk.command_level(rs, "git push", cwd=str(root))["level"], "ask")
        git(root, "switch", "-q", "chore/adopt-aidd")
        self.assertEqual(risk.command_level(rs, "git push origin trunk", cwd=str(root))["level"], "ask")
        self.assertEqual(risk.command_level(rs, "git push", cwd=str(root))["level"], "allow")  # one's own branch

    def test_stale_rules_with_no_readable_default_branch_name_the_way_to_stop_it(self):
        """With no origin/HEAD, main, or master, each new local branch makes the push rules stale again, so the warning names
        `git config init.defaultBranch <branch>` before `aidd upgrade --yes`, the one step that ends it."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "trunk")
        git(root, "commit", "-q", "--allow-empty", "-m", "start")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        git(root, "switch", "-q", "-c", "feature/cart")
        stale = [m for level, m in doctor_harnesses.harness_checks(root, ["claude-code"]) if level == "warning" and "not current" in m]
        self.assertEqual(len(stale), 1, stale)
        self.assertLess(stale[0].index("git config init.defaultBranch <branch>"), stale[0].index("aidd upgrade --yes"))
        git(root, "config", "init.defaultBranch", "trunk")
        stale = [m for level, m in doctor_harnesses.harness_checks(root, ["claude-code"]) if level == "warning" and "not current" in m]
        self.assertEqual(len(stale), 1, stale)
        self.assertNotIn("init.defaultBranch", stale[0])

    def test_a_global_default_branch_name_never_narrows_the_push_ask_rules(self):
        """Fail-safe: a global `init.defaultBranch` is a default for new repositories, so it never replaces the branch
        checked out among the branches that could be this one's default."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root, home = Path(tmp.name) / "repo", Path(tmp.name) / "gitconfig"
        root.mkdir()
        home.write_text(Path(os.environ["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf-8") + "[init]\n\tdefaultBranch = trunk\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(home)}):
            git(root, "init", "-q", "-b", "develop")
            git(root, "commit", "-q", "--allow-empty", "-m", "start")
            git(root, "branch", "trunk")
            self.assertEqual(ask_rules.push_rule_branches(root)[:2], ["develop", "trunk"])

    def test_a_failed_plugin_install_falls_back_to_repository_wiring(self):
        allow_the_plugin_install(self)
        real_which = shutil.which
        with (
            mock.patch.object(shutil, "which", lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)),
            mock.patch.object(claude_plugins, "PLUGIN_RUNNER", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")),
        ):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=True))
        self.assertTrue(any(a.startswith("failed   claude plugin marketplace add") and "wiring the repository instead" in a for a in actions))
        self.assertTrue((self.root / ".claude" / "settings.json").is_file())
        assert_skill_linked(self, self.root)


class PluginFallbackTests(unittest.TestCase):
    """`aidd init --claude-plugins` that cannot install the plugins wires the repository files instead. Those files
    replace the plugins, so its message never tells a person to install the plugins as well: the skill and the roles
    would load twice. `aidd doctor` warns when both are there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.claude_home = Path(self.tmp.name) / "claude-home"
        self.claude_home.mkdir()
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude_home)})
        env.start()
        self.addCleanup(env.stop)
        self.real_which = shutil.which
        allow_the_plugin_install(self)

    def init(self, runner=None, claude: bool = True, harnesses: list[str] | None = ["claude-code"]) -> list[str]:  # noqa: B006
        which = lambda name, path=None: ("/usr/bin/claude" if claude else None) if name == "claude" else self.real_which(name, path=path)  # noqa: E731
        with mock.patch.object(shutil, "which", which), mock.patch.object(claude_plugins, "PLUGIN_RUNNER", runner or (lambda cmd, **kw: None)):
            return adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=harnesses, aidd_team=True, claude_plugins=True))

    def fallback(self, actions: list[str]) -> str:
        lines = [a for a in actions if a.startswith("fallback ")]
        self.assertEqual(len(lines), 1, actions)
        return lines[0]

    def test_no_claude_cli_says_what_it_wrote_and_never_to_install_the_plugins(self):
        actions = self.init(claude=False)
        self.assertFalse([a for a in actions if "/plugin install" in a], actions)  # on top of the repository files: twice
        line = self.fallback(actions)
        for path in (".claude/skills/aidd", ".claude/agents", ".claude/commands", ".mcp.json"):
            self.assertIn(path, line)
        self.assertIn("replace the plugins", line)
        self.assertIn("`aidd uninstall --yes`", line)
        self.assertIn("`--claude-plugins`", line)
        self.assertNotIn("claude plugin uninstall", line)  # nothing was installed

    def test_the_note_tells_a_missing_cli_from_a_failed_install(self):
        missing = self.fallback(self.init(claude=False))
        self.assertIn("the `claude` CLI is missing", missing)
        self.assertIn("install the `claude` CLI", missing)
        failed = self.fallback(self.init(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")))
        self.assertIn("see the `failed` line above", failed)
        self.assertNotIn("install the `claude` CLI", failed)

    def test_offline_never_runs_the_claude_cli_and_wires_the_repository(self):
        """`claude plugin marketplace add` and `install` fetch from github.com, so AIDD_OFFLINE=1 stops them."""
        calls = []
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}):
            actions = self.init(lambda cmd, **kw: calls.append(cmd))
        self.assertEqual(calls, [])
        self.assertIn("AIDD_OFFLINE=1 stopped the install, so unset it", self.fallback(actions))
        assert_skill_linked(self, self.root)

    def test_a_partial_install_names_the_plugins_to_uninstall(self):
        def runner(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1 if cmd[-1] == "aidd-team@aidd" else 0, stdout="", stderr="network down")

        actions = self.init(runner)
        self.assertTrue(any(a.startswith("failed   claude plugin install aidd-team@aidd") for a in actions), actions)
        line = self.fallback(actions)
        self.assertIn("installed or found already installed", line)  # claude exits 0 for a plugin already there
        self.assertIn("`claude plugin uninstall aidd@aidd`", line)
        self.assertNotIn("`claude plugin uninstall aidd-team@aidd`", line)

    def test_a_failed_install_where_claude_code_was_not_detected_adds_it_and_wires_the_repository(self):
        actions = self.init(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down"), harnesses=[])
        self.assertEqual(
            actions[:2],
            [
                "detected no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them",
                "failed   claude plugin marketplace add thaithienvanid/aidd: network down; wiring the repository instead",
            ],
        )
        self.assertTrue(actions[-1].startswith("fallback Claude Code loads aidd from the repository files instead"), actions[-1])
        self.assertNotEqual(claude_plugins.claude_repo_files(self.root), ([], []))  # Claude Code joined the agents to wire

    @unittest.skipUnless(os.name != "nt", "the stub `claude` is a shell script")
    def test_the_same_run_from_the_command_line_exits_0_and_links_the_skill(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        (stub / "claude").write_text("#!/bin/sh\necho boom >&2\nexit 1\n", encoding="utf-8")
        (stub / "claude").chmod(0o755)
        home = Path(self.tmp.name) / "home"
        home.mkdir()
        env = {**hermetic_environ(), "AIDD_OFFLINE": "0", "AIDD_UPDATE": "off", "HOME": str(home), "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"}
        git(self.root, "init", "-q", "-b", "main")
        r = aidd_subprocess("init", "--claude-plugins", "--harness", "none", "--profile", "solo", "--ci", "none", cwd=self.root, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("failed   claude plugin marketplace add thaithienvanid/aidd: boom; wiring the repository instead", r.stdout)
        self.assertIn("fallback Claude Code loads aidd from the repository files instead", r.stdout)
        self.assertIn("linked   .claude/skills/aidd -> ../../.agents/skills/aidd", r.stdout)

    def test_an_install_without_its_templates_fails_before_any_plugin_is_installed(self):
        """`init` finds the templates first, as it always has, so a broken install changes nothing on this machine."""
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout="ok", stderr=""))
        with mock.patch.object(resources, "data_dir", side_effect=FileNotFoundError("aidd data directory not found: templates")):
            with self.assertRaises(FileNotFoundError):
                self.init(runner)
        runner.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_uninstall_then_init_with_the_plugins_leaves_no_repository_files_for_claude_code(self):
        # The way the fallback note gives to switch to the plugins later.
        self.init(claude=False)
        self.assertNotEqual(claude_plugins.claude_repo_files(self.root), ([], []))
        uninstalling.uninstall(self.root, yes=True)
        self.init(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr=""))
        self.assertEqual(claude_plugins.claude_repo_files(self.root), ([], []))

    def test_no_fallback_line_when_the_plugins_install(self):
        actions = self.init(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr=""))
        self.assertFalse([a for a in actions if a.startswith("fallback ")])

    def doubles(self) -> list[str]:
        return [m for level, m in doctor_checks.doctor(self.root) if level == "warning" and "load twice" in m]

    def enable(self, where: Path, plugins: dict) -> None:
        where.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(where.read_text(encoding="utf-8")) if where.is_file() else {}
        data["enabledPlugins"] = plugins
        where.write_text(json.dumps(data), encoding="utf-8")

    def test_doctor_warns_when_a_plugin_and_its_repository_files_are_both_there(self):
        self.init(claude=False)
        self.assertEqual(self.doubles(), [])
        self.enable(self.claude_home / "settings.json", {"aidd@aidd": True, "aidd-team@aidd": True})
        warnings = self.doubles()
        self.assertEqual(len(warnings), 2, warnings)
        skill, team = warnings
        self.assertIn("aidd@aidd", skill)
        self.assertIn(".claude/skills/aidd", skill)
        self.assertIn("aidd-team@aidd", team)
        self.assertIn(".claude/agents", team)
        for m in warnings:
            self.assertIn("`aidd uninstall`", m)

    def test_the_packs_plugin_and_the_packs_in_the_project_skills_load_twice(self):
        pack = self.root / ".claude" / "skills" / "aidd-health" / "SKILL.md"
        pack.parent.mkdir(parents=True)
        pack.write_text("---\nname: aidd-health\n---\n", encoding="utf-8")
        self.enable(self.claude_home / "settings.json", {"aidd-packs@aidd": False})
        self.assertEqual([m for m in self.doubles() if "aidd-packs" in m], [])
        self.enable(self.claude_home / "settings.json", {"aidd-packs@aidd": True})
        (warning,) = [m for m in self.doubles() if "aidd-packs" in m]
        self.assertIn("health", warning)
        self.assertIn("`aidd uninstall`", warning)

    def test_a_teams_own_aidd_named_skill_is_not_a_double_load(self):
        own = self.root / ".claude" / "skills" / "aidd-ledger" / "SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_text("---\nname: aidd-ledger\n---\n", encoding="utf-8")
        self.enable(self.claude_home / "settings.json", {"aidd-team@aidd": True})
        self.assertEqual(claude_plugins.claude_repo_files(self.root), ([], []))
        self.assertEqual(self.doubles(), [])

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX permissions and a non-root user")
    def test_unreadable_settings_warn_instead_of_crashing(self):
        self.init(claude=False)
        for path in (self.root / ".claude" / "settings.json", self.claude_home / "settings.json"):
            path.write_text("{}", encoding="utf-8") if not path.exists() else None
            path.chmod(0)
            self.addCleanup(path.chmod, 0o644)
        claude_plugins.claude_repo_files(self.root)
        harness_settings.plugins_enabled(self.root)
        unreadable = [m for level, m in doctor_probes.plugin_double_load(self.root, "Claude Code") if level == "warning" and "cannot read" in m]
        self.assertEqual(len(unreadable), 2, unreadable)
        self.assertEqual(len([m for level, m in doctor_checks.doctor(self.root) if level == "warning" and "cannot read" in m]), 2)

    def test_the_project_settings_decide_over_the_user_settings(self):
        self.init(claude=False)
        self.enable(self.claude_home / "settings.json", {"aidd@aidd": True, "aidd-team@aidd": True})
        self.enable(self.root / ".claude" / "settings.local.json", {"aidd@aidd": False, "aidd-team@aidd": False})
        self.assertEqual(self.doubles(), [])
        self.enable(self.root / ".claude" / "settings.json", {"aidd-team@aidd": True})
        self.assertEqual(self.doubles(), [])  # settings.local.json turns it off again


if __name__ == "__main__":
    unittest.main()
