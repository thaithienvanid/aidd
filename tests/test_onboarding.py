"""First contact: coding-agent detection, per-agent wiring, the plugin path, `aidd uninstall`, and the installer script."""

import io
import json
import re
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd.cli import app as cli_app
from aidd.cli import parser as cli_parser
from aidd.setup import doctor_checks
from aidd.setup import uninstalling
from aidd.setup import upgrading
from aidd.setup import adoption
from aidd.setup import doctor_probes
from aidd.setup import claude_plugins
from aidd.setup import hook_wiring
from aidd.config import harness_settings


def tree(root: Path) -> dict[str, str]:
    out = {}
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        rel = str(p.relative_to(root))
        out[rel] = os.readlink(p) if p.is_symlink() else (p.read_text(encoding="utf-8") if p.is_file() else "<dir>")
    return out


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
        (self.home / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")  # Antigravity shares ~/.gemini; the settings file is Gemini CLI's own
        self.binary("codex")
        self.assertEqual(self.detect(), [])
        self.assertEqual(self.installed(), ["codex", "gemini"])
        (self.root / ".claude").mkdir()
        (self.root / ".clinerules").write_text("x", encoding="utf-8")
        self.assertEqual(self.detect(), ["claude-code", "cline"])

    def test_init_hints_at_an_installed_agent_whose_wiring_matters(self):
        self.binary("claude")
        self.binary("cursor")  # reads AGENTS.md: nothing to wire, so no hint
        with mock.patch.object(adoption, "installed_harnesses", return_value=self.installed()):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
        self.assertIn("detected no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them", actions)
        self.assertIn("hint     this machine has Claude Code: wire it with --harness claude-code", actions)
        self.assertFalse((self.root / ".claude").exists(), "nothing is wired for an agent the repository does not show")

    def test_new_agents_are_detected_by_their_own_files_never_by_aidd_output(self):
        (self.root / ".agents" / "rules").mkdir(parents=True)  # Antigravity keeps rules there; aidd only ever writes .agents/skills/
        (self.root / "opencode.json").write_text("{}", encoding="utf-8")
        (self.root / ".goosehints").write_text("x", encoding="utf-8")
        self.assertEqual(self.detect(), ["antigravity", "opencode", "goose"])
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

    def test_doctor_collapses_the_agents_that_only_read_agents_md(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for signal in (".cursor", ".clinerules", ".junie"):
            (self.root / signal).mkdir()
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
        report = doctor_checks.doctor(self.root)
        self.assertIn(("ok", "3 agents read AGENTS.md: Cursor, Cline, JetBrains Junie"), report)
        self.assertFalse([m for _, m in report if m.endswith(": reads AGENTS.md")])
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            adoption.init(Path(d), adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@me"]))
            messages = [m for lvl, m in doctor_checks.doctor(Path(d)) if "coding agent" in m]
            self.assertEqual(len(messages), 1)
            self.assertIn("in this repository", messages[0])
            self.assertNotIn("on this machine", messages[0])


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_code_gets_hook_and_mcp_without_a_flag(self):
        actions = adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code", "codex"])
        )
        self.assertTrue(any(a.startswith("detected Claude Code, Codex") for a in actions))
        self.assertIn(hook_wiring.HOOK_COMMAND, (self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("aidd", json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"])
        assert_skill_linked(self, self.root)
        self.assertFalse((self.root / "GEMINI.md").exists())

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

    def test_agent_hooks_false_overrides_detection(self):
        adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"], agent_hooks=False)
        )
        self.assertFalse((self.root / ".claude" / "settings.json").exists())

    def test_gemini_and_copilot_pointers(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Copilot\n\nBe brief.\n", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["gemini", "copilot"]))
        gemini = (self.root / "GEMINI.md").read_text(encoding="utf-8")
        self.assertTrue(gemini.startswith("# Gemini\n"))
        self.assertIn(adoption.AGENTS_MARK, gemini)
        copilot = (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        self.assertTrue(copilot.startswith("# Copilot\n\nBe brief.\n"))
        self.assertIn(adoption.AGENTS_MARK, copilot)
        # Idempotent.
        actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["gemini", "copilot"]))
        self.assertEqual(copilot, (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"))
        self.assertTrue(any("kept" in a and "GEMINI.md" in a for a in actions))

    def test_pointers_for_claude_md_warp_conventions_and_continue(self):
        (self.root / "CLAUDE.md").write_text("# Project\n\nBe brief.\n", encoding="utf-8")
        (self.root / "WARP.md").write_text("# Warp\n", encoding="utf-8")
        actions = adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code", "warp", "continue", "aider"], agent_hooks=False)
        )
        for name in ("CLAUDE.md", "WARP.md"):
            text = (self.root / name).read_text(encoding="utf-8")
            self.assertIn(adoption.AGENTS_MARK, text, name)
            self.assertTrue(text.startswith("# "), name)
        self.assertFalse((self.root / "CONVENTIONS.md").exists())  # Aider's file is appended to, never created
        rule = (self.root / ".continue" / "rules" / "aidd.md").read_text(encoding="utf-8")
        self.assertTrue(rule.startswith("# aidd\n"))
        self.assertIn(adoption.AGENTS_MARK, rule)
        self.assertTrue(any(a.startswith("detected Claude Code, Warp, Continue, Aider") for a in actions))
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# Project\n\nBe brief.\n")
        self.assertEqual((self.root / "WARP.md").read_text(encoding="utf-8"), "# Warp\n")
        self.assertFalse((self.root / ".continue").exists())

    def test_plugins_path_uses_the_claude_cli_and_skips_repository_wiring(self):
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
                adoption.InitOptions(profile="solo", ci="none", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"], team=True, claude_plugins=True),
            )
        finally:
            shutil.which, claude_plugins.PLUGIN_RUNNER = real_which, real_runner
        self.assertEqual([c[-1] for c in calls], [claude_plugins.MARKETPLACE_REPO, "aidd@aidd", "aidd-team@aidd"])
        self.assertFalse((self.root / ".claude" / "skills" / "aidd").exists())
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
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
                harnesses=["claude-code", "gemini", "continue", "aider"],
                team=True,
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
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="github", links=list(adoption.DEFAULT_LINKS), harnesses=["claude-code"], team=True))
        agent = self.root / ".claude" / "agents" / "aidd-developer.md"
        agent.write_text(agent.read_text(encoding="utf-8").replace("model: sonnet", "model: opus"), encoding="utf-8")
        (self.root / ".github" / "pull_request_template.md").write_text("mine\n", encoding="utf-8")
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n# user comment\napprovers: ["@me"]\n', encoding="utf-8")
        gate = self.root / ".github" / "workflows" / "aidd-gate.yml"
        gate.write_text(gate.read_text(encoding="utf-8") + "# edited gate\n", encoding="utf-8")
        tests = self.root / ".github" / "workflows" / "aidd-tests.yml"
        tests.write_text(tests.read_text(encoding="utf-8") + "# edited tests\n", encoding="utf-8")
        relay = self.root / ".github" / "workflows" / "aidd-relay.yml"
        relay.write_text(relay.read_text(encoding="utf-8") + "# edited relay\n", encoding="utf-8")

        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(agent.is_file())
        self.assertEqual((self.root / ".github" / "pull_request_template.md").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue(cfg.is_file())
        self.assertTrue(gate.is_file())
        self.assertTrue(tests.is_file())
        self.assertTrue(relay.is_file())
        self.assertTrue(any("kept" in a and "developer.md" in a for a in actions))
        self.assertTrue(any("kept" in a and "config.yaml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-gate.yml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-tests.yml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-relay.yml" in a for a in actions))
        self.assertFalse((self.root / ".claude" / "agents" / "tester.md").exists())

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
    def test_the_cli_and_the_runbook_give_one_day_0_commit_instruction(self):
        """The agent commits the setup on `chore/adopt-aidd` with its trailer; a person lands it (local) or merges it (platform)."""
        from helpers import git, run_cli

        branch = "Commit this setup on the branch `chore/adopt-aidd`"
        lands = "A person then lands that Day-0 commit on the base branch"
        merges = "A person merges the setup PR/MR"
        step4 = (ROOT / "llms-install.md").read_text(encoding="utf-8").split("## 4. Commit", 1)[1].split("\n## ", 1)[0]
        for phrase in (branch, "Assisted-by:", lands, merges, "fast-forward"):
            self.assertIn(phrase, step4, phrase)
        printed = {}
        for name, extra in (("local", ["--ci", "none"]), ("platform", [])):
            with tempfile.TemporaryDirectory() as d:
                git(d, "init", "-q", "-b", "main")
                git(d, "-c", "user.email=a@example.com", "-c", "user.name=A", "commit", "-q", "--allow-empty", "-m", "base")
                if name == "platform":
                    git(d, "remote", "add", "origin", "https://github.com/acme/app.git")
                code, out = run_cli("init", d, "--profile", "solo", "--approvers", "@me", "--ref", "a" * 40, "--test", "true", *extra)
                self.assertEqual(code, 0, out)
                printed[name] = out
        self.assertIn(lands, printed["local"])
        self.assertIn("git merge --ff-only chore/adopt-aidd", printed["local"])
        self.assertNotIn(merges, printed["local"])
        self.assertIn(merges, printed["platform"])
        self.assertNotIn(lands, printed["platform"])
        for out in printed.values():
            self.assertIn(branch, out)
            self.assertIn("Assisted-by:", out)
            self.assertNotIn("on the base branch yourself", out)
        # A new repository with no commit: a person makes the Day-0 commit, and the agent stops.
        fresh = "New repository: a person makes the Day-0 commit, this setup and the project scaffold, on the default branch."
        self.assertIn(fresh, step4)
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, "--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "true")
        self.assertEqual(code, 0, out)
        self.assertIn(fresh, out)
        self.assertIn("An agent does not commit it: it stops here and hands back.", out)
        self.assertNotIn("directly to the default branch", out)
        self.assertNotIn(branch, out)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_init_says_to_restart_claude_code_only_when_it_wrote_its_files(self):
        from helpers import git, run_cli

        notice = "Restart Claude Code in this folder to load the roles, commands, and hooks."
        hand_back = (ROOT / "llms-install.md").read_text(encoding="utf-8").split("## 5. Hand back", 1)[1].split("\n## ", 1)[0]
        self.assertIn(notice, hand_back)
        args = ("--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "true")
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            code, out = run_cli("init", d, *args, "--harness", "claude-code", "--team")
            self.assertEqual((code, out.count(notice)), (0, 1), out)
            code, out = run_cli("init", d, *args, "--harness", "claude-code", "--team")  # everything is there: kept
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
        from aidd import __version__

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
            f"@v{__version__}",
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
        for path in ("docs/INSTALL.md", "docs/QUICKSTART.md", "docs/CLI.md", "docs/TEAM.md", "docs/METHOD.md", "plugins/README.md"):
            self.assertIn(path, index, path)
            self.assertTrue((ROOT / path).is_file(), path)
        # The prompt a person gives their agent: README's first text block under "Get started", naming this repository
        # (from pyproject's Source URL), followed by the runbook link, and quoted the same wherever the docs offer it.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        start = readme.split("\n## Get started\n", 1)[1].split("\n## ", 1)[0]
        prompt = start.split("```text\n", 1)[1].split("\n```", 1)[0].strip()
        import tomllib

        source = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]["Source"]
        self.assertIn(source.removeprefix("https://github.com/"), prompt)
        self.assertIn("(llms-install.md)", start.split(prompt, 1)[1])
        for doc in ("docs/INSTALL.md", "docs/HOW-TO.md", "llms.txt"):
            self.assertIn(f'"{prompt}"', (ROOT / doc).read_text(encoding="utf-8"), doc)

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

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_harness_none_mixed_with_a_name_drops_none(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli_app.main(["init", str(self.root), "--profile", "solo", "--ci", "none", "--harness", "gemini", "--harness", "none"]), 0)
        self.assertIn("detected Gemini CLI", out.getvalue())

    def test_marked_section_stops_at_a_top_level_heading_and_a_bare_mark_loses_only_its_line(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n# Other\n\nkeep me\n"
        self.assertEqual(upgrading.strip_marked_section(text, adoption.AGENTS_MARK), "# Agents\n\n# Other\n\nkeep me\n")
        text = "# Agents\n\n<!-- aidd -->\n\n## Ours\n\nkeep\n"
        self.assertEqual(upgrading.strip_marked_section(text, adoption.AGENTS_MARK), "# Agents\n\n\n## Ours\n\nkeep\n")

    def test_uninstall_keeps_user_files_inside_team_folders(self):
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], team=True))
        note = self.root / ".claude" / "skills" / "aidd-web-front-end" / "NOTES.md"
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
        self.assertFalse((self.root / ".claude" / "skills" / "aidd-health").exists())

    def test_malformed_settings_do_not_abort_init_or_uninstall(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
        actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"]))
        self.assertTrue((self.root / ".aidd" / "config.yaml").is_file())
        self.assertTrue(any("not valid JSON" in a for a in actions))
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{not json")
        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{not json")
        self.assertTrue(any("not valid JSON" in a for a in actions))

    def test_a_failed_plugin_install_falls_back_to_repository_wiring(self):
        real_which = shutil.which
        with (
            mock.patch.object(shutil, "which", lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)),
            mock.patch.object(claude_plugins, "PLUGIN_RUNNER", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")),
        ):
            actions = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=True))
        self.assertTrue(any(a.startswith("failed   claude plugin marketplace add") and "wiring the repository instead" in a for a in actions))
        self.assertTrue((self.root / ".claude" / "settings.json").is_file())
        assert_skill_linked(self, self.root)

    def mods_init(self, version: str, *, install_rc: int = 0, plugins: bool = True) -> tuple[list[str], list[list[str]]]:
        """`aidd init --mods` with a fake `claude` that reports `version` and exits `install_rc` for the aidd-mods install."""
        calls: list[list[str]] = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[1:] == ["--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=version, stderr="")
            rc = install_rc if cmd[-1] == "aidd-mods@aidd" else 0
            return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="" if rc == 0 else "plugin not found")

        real_which = shutil.which
        with (
            mock.patch.object(shutil, "which", lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)),
            mock.patch.object(claude_plugins, "PLUGIN_RUNNER", run),
        ):
            options = adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=plugins, mods=True)
            return adoption.init(self.root, options), calls

    def test_mods_installs_the_optional_plugin_after_the_others(self):
        actions, calls = self.mods_init("2.1.300 (Claude Code)\n")
        self.assertEqual([c[-1] for c in calls], [claude_plugins.MARKETPLACE_REPO, "aidd@aidd", "--version", "aidd-mods@aidd"])
        self.assertIn("ran      claude plugin install aidd-mods@aidd", actions)
        self.assertFalse((self.root / ".claude" / "settings.json").exists())  # still the plugins path

    def test_mods_on_a_claude_code_too_old_for_mods_is_skipped_and_the_rest_stands(self):
        actions, calls = self.mods_init("2.1.290 (Claude Code)\n")
        self.assertNotIn("aidd-mods@aidd", [c[-1] for c in calls])
        line = next(a for a in actions if a.startswith("skipped  aidd-mods"))
        self.assertIn("Claude Code 2.1.290 loads no mods; it needs 2.1.295 or later", line)
        self.assertFalse([a for a in actions if a.startswith("fallback ")])
        self.assertFalse((self.root / ".claude" / "settings.json").exists())

    def test_a_failed_mods_install_never_falls_back(self):
        actions, _ = self.mods_init("2.1.300 (Claude Code)\n", install_rc=1)
        self.assertTrue(any(a.startswith("failed   claude plugin install aidd-mods@aidd: plugin not found; the other plugins stand") for a in actions))
        self.assertFalse([a for a in actions if a.startswith("fallback ")])
        self.assertFalse((self.root / ".claude" / "settings.json").exists())

    def test_mods_without_the_plugins_path_says_it_ships_only_as_a_plugin(self):
        actions, calls = self.mods_init("2.1.300 (Claude Code)\n", plugins=False)
        self.assertEqual(calls, [])
        self.assertTrue(any(a.startswith("skipped  aidd-mods: a mod ships only as a plugin; add --claude-plugins") for a in actions))


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

    def init(self, runner=None, claude: bool = True, harnesses: list[str] | None = ["claude-code"]) -> list[str]:  # noqa: B006
        which = lambda name, path=None: ("/usr/bin/claude" if claude else None) if name == "claude" else self.real_which(name, path=path)  # noqa: E731
        with mock.patch.object(shutil, "which", which), mock.patch.object(claude_plugins, "PLUGIN_RUNNER", runner or (lambda cmd, **kw: None)):
            return adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=harnesses, team=True, claude_plugins=True))

    def fallback(self, actions: list[str]) -> str:
        lines = [a for a in actions if a.startswith("fallback ")]
        self.assertEqual(len(lines), 1, actions)
        return lines[0]

    def test_no_claude_cli_says_what_it_wrote_and_never_to_install_the_plugins(self):
        actions = self.init(claude=False)
        self.assertFalse([a for a in actions if "/plugin install" in a], actions)  # on top of the repository files: twice
        line = self.fallback(actions)
        for path in (".claude/skills/aidd", ".claude/agents", ".claude/commands", ".claude/settings.json", ".mcp.json"):
            self.assertIn(path, line)
        self.assertIn("replace the plugins", line)
        self.assertIn("`aidd uninstall --yes`", line)
        self.assertIn("`--claude-plugins`", line)
        self.assertNotIn("claude plugin uninstall", line)  # nothing was installed

    def test_a_repository_with_no_claude_code_files_gets_the_whole_repository_set(self):
        # The recipe's usual fresh repository: nothing shows Claude Code, so detection alone would wire only the team.
        actions = self.init(claude=False, harnesses=None)
        self.assertTrue((self.root / ".claude" / "skills" / "aidd" / "SKILL.md").is_file())
        self.assertIn(hook_wiring.HOOK_COMMAND, (self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("aidd", json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"])
        agent = (self.root / ".claude" / "agents" / "aidd-developer.md").read_text(encoding="utf-8")
        front = agent.split("\n---", 1)[0]
        preloaded = re.findall(r"^  - (\S+)$", front.split("skills:", 1)[1], re.M)
        self.assertIn("aidd", preloaded)
        for name in preloaded:
            self.assertTrue((self.root / ".claude" / "skills" / name / "SKILL.md").is_file(), name)
        line = self.fallback(actions)
        skill, team = claude_plugins.claude_repo_files(self.root)
        self.assertEqual(skill, [".claude/skills/aidd", ".claude/settings.json", ".mcp.json"])
        for path in [*skill, *(f"{d}/aidd-*" for d in team)]:
            self.assertIn(path, line)

    def test_the_note_tells_a_missing_cli_from_a_failed_install(self):
        missing = self.fallback(self.init(claude=False))
        self.assertIn("the `claude` CLI is missing", missing)
        self.assertIn("install the `claude` CLI", missing)
        failed = self.fallback(self.init(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")))
        self.assertIn("see the `failed` line above", failed)
        self.assertNotIn("install the `claude` CLI", failed)

    def test_a_partial_install_names_the_plugins_to_uninstall(self):
        def runner(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1 if cmd[-1] == "aidd-team@aidd" else 0, stdout="", stderr="network down")

        actions = self.init(runner)
        self.assertTrue(any(a.startswith("failed   claude plugin install aidd-team@aidd") for a in actions), actions)
        line = self.fallback(actions)
        self.assertIn("installed or found already installed", line)  # claude exits 0 for a plugin already there
        self.assertIn("`claude plugin uninstall aidd@aidd`", line)
        self.assertNotIn("`claude plugin uninstall aidd-team@aidd`", line)

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
        return [m for level, m in doctor_checks.doctor(self.root) if level == "warn" and "load twice" in m]

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
        unreadable = [m for level, m in doctor_probes.plugin_double_load(self.root, "Claude Code") if level == "warn" and "cannot read" in m]
        self.assertEqual(len(unreadable), 2, unreadable)
        self.assertEqual(len([m for level, m in doctor_checks.doctor(self.root) if level == "warn" and "cannot read" in m]), 2)

    def test_the_project_settings_decide_over_the_user_settings(self):
        self.init(claude=False)
        self.enable(self.claude_home / "settings.json", {"aidd@aidd": True, "aidd-team@aidd": True})
        self.enable(self.root / ".claude" / "settings.local.json", {"aidd@aidd": False, "aidd-team@aidd": False})
        self.assertEqual(self.doubles(), [])
        self.enable(self.root / ".claude" / "settings.json", {"aidd-team@aidd": True})
        self.assertEqual(self.doubles(), [])  # settings.local.json turns it off again


if __name__ == "__main__":
    unittest.main()
