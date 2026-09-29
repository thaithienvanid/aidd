"""First contact: coding-agent detection, per-agent wiring, the plugin path, `aidd uninstall`, and the installer script."""

import io
import json
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

from aidd import cli, repo


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
        case.assertEqual((link.parent / os.readlink(link)).resolve(), (root / repo.SKILL_REL).resolve())
    else:
        case.assertTrue(link.is_dir(), link)
        case.assertEqual(repo._tree_diff(root / repo.SKILL_REL, link), [])


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
        return repo.detect_harnesses(self.root)

    def installed(self):
        return repo.installed_harnesses(home=self.home, path=str(self.bin))

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
        with mock.patch.object(repo, "installed_harnesses", return_value=self.installed()):
            actions = repo.init(self.root, profile="solo", ci="none", links=[], approvers=["@me"])
        self.assertIn("detected no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them", actions)
        self.assertIn("next     this machine has Claude Code: wire it with --harness claude-code", actions)
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
            self.assertEqual(repo.detect_harnesses(root), [])

    def test_copilot_by_its_instructions_file(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Copilot\n", encoding="utf-8")
        self.assertEqual(self.detect(), ["copilot"])

    def test_doctor_collapses_the_agents_that_only_read_agents_md(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for signal in (".cursor", ".clinerules", ".junie"):
            (self.root / signal).mkdir()
        repo.init(self.root, profile="solo", ci="none", links=[], approvers=["@me"])
        report = repo.doctor(self.root)
        self.assertIn(("ok", "3 agents read AGENTS.md: Cursor, Cline, JetBrains Junie"), report)
        self.assertFalse([m for _, m in report if m.endswith(": reads AGENTS.md")])
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            repo.init(Path(d), profile="solo", ci="none", links=[], approvers=["@me"])
            messages = [m for lvl, m in repo.doctor(Path(d)) if "coding agent" in m]
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
        actions = repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code", "codex"])
        self.assertTrue(any(a.startswith("detected Claude Code, Codex") for a in actions))
        self.assertIn(repo.HOOK_COMMAND, (self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("aidd", json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"])
        assert_skill_linked(self, self.root)
        self.assertFalse((self.root / "GEMINI.md").exists())

    def test_without_symlinks_the_skill_is_copied(self):
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("symlinks need a privilege here")):
            actions = repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code"])
        link = self.root / ".claude" / "skills" / "aidd"
        self.assertFalse(link.is_symlink())
        assert_skill_linked(self, self.root)
        self.assertTrue(any(a.startswith(f"copied   {link}") for a in actions), actions)
        # Run again: the copy is kept, not replaced or duplicated.
        with mock.patch.object(Path, "symlink_to", side_effect=OSError("symlinks need a privilege here")):
            again = repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code"])
        self.assertTrue(any(a.startswith(f"kept     {link}") for a in again), again)

    def test_no_agent_means_agents_md_only(self):
        repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=[])
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
        self.assertFalse((self.root / ".mcp.json").exists())
        self.assertIn(repo.AGENTS_MARK, (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_agent_hooks_false_overrides_detection(self):
        repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code"], agent_hooks=False)
        self.assertFalse((self.root / ".claude" / "settings.json").exists())

    def test_gemini_and_copilot_pointers(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Copilot\n\nBe brief.\n", encoding="utf-8")
        repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["gemini", "copilot"])
        gemini = (self.root / "GEMINI.md").read_text(encoding="utf-8")
        self.assertTrue(gemini.startswith("# Gemini\n"))
        self.assertIn(repo.AGENTS_MARK, gemini)
        copilot = (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        self.assertTrue(copilot.startswith("# Copilot\n\nBe brief.\n"))
        self.assertIn(repo.AGENTS_MARK, copilot)
        # Idempotent.
        actions = repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["gemini", "copilot"])
        self.assertEqual(copilot, (self.root / ".github" / "copilot-instructions.md").read_text(encoding="utf-8"))
        self.assertTrue(any("kept" in a and "GEMINI.md" in a for a in actions))

    def test_pointers_for_claude_md_warp_conventions_and_continue(self):
        (self.root / "CLAUDE.md").write_text("# Project\n\nBe brief.\n", encoding="utf-8")
        (self.root / "WARP.md").write_text("# Warp\n", encoding="utf-8")
        actions = repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["claude-code", "warp", "continue", "aider"], agent_hooks=False)
        for name in ("CLAUDE.md", "WARP.md"):
            text = (self.root / name).read_text(encoding="utf-8")
            self.assertIn(repo.AGENTS_MARK, text, name)
            self.assertTrue(text.startswith("# "), name)
        self.assertFalse((self.root / "CONVENTIONS.md").exists())  # Aider's file is appended to, never created
        rule = (self.root / ".continue" / "rules" / "aidd.md").read_text(encoding="utf-8")
        self.assertTrue(rule.startswith("# aidd\n"))
        self.assertIn(repo.AGENTS_MARK, rule)
        self.assertTrue(any(a.startswith("detected Claude Code, Warp, Continue, Aider") for a in actions))
        repo.uninstall(self.root, yes=True)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# Project\n\nBe brief.\n")
        self.assertEqual((self.root / "WARP.md").read_text(encoding="utf-8"), "# Warp\n")
        self.assertFalse((self.root / ".continue").exists())

    def test_plugins_path_uses_the_claude_cli_and_skips_repository_wiring(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        real_which, real_runner = repo.shutil.which, repo.PLUGIN_RUNNER
        repo.shutil.which = lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)
        repo.PLUGIN_RUNNER = fake_run
        try:
            actions = repo.init(self.root, profile="solo", ci="none", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code"], team=True, claude_plugins=True)
        finally:
            repo.shutil.which, repo.PLUGIN_RUNNER = real_which, real_runner
        self.assertEqual([c[-1] for c in calls], [repo.MARKETPLACE_REPO, "aidd@aidd", "aidd-team@aidd"])
        self.assertFalse((self.root / ".claude" / "skills" / "aidd").exists())
        self.assertFalse((self.root / ".claude" / "settings.json").exists())
        self.assertFalse((self.root / ".claude" / "agents").exists())
        self.assertTrue((self.root / ".agents" / "skills" / "aidd" / "SKILL.md").is_file())  # other harnesses still need it
        self.assertIn(repo.TEAM_MARK, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue(any(a.startswith("skipped  .claude/skills/aidd") for a in actions))

    def test_plugins_path_without_the_cli_says_what_to_run(self):
        real_which = repo.shutil.which
        repo.shutil.which = lambda name, path=None: None if name == "claude" else real_which(name, path=path)
        try:
            actions = repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=True)
        finally:
            repo.shutil.which = real_which
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
        repo.init(
            self.root,
            profile="team",
            ci="github",
            links=list(repo.DEFAULT_LINKS),
            approvers=["@x"],
            harnesses=["claude-code", "gemini", "continue", "aider"],
            team=True,
        )
        self.assertNotEqual(tree(self.root), before)
        dry = repo.uninstall(self.root)
        self.assertTrue(any(a.startswith("would remove") for a in dry))
        self.assertTrue(any("dry run" in a for a in dry))
        self.assertNotEqual(tree(self.root), before)
        done = repo.uninstall(self.root, yes=True)
        self.assertTrue(any(a.startswith("removed ") for a in done))
        self.assertEqual(tree(self.root), before)

    def test_user_edits_are_kept(self):
        repo.init(self.root, profile="solo", ci="github", links=list(repo.DEFAULT_LINKS), harnesses=["claude-code"], team=True)
        agent = self.root / ".claude" / "agents" / "aidd-developer.md"
        agent.write_text(agent.read_text(encoding="utf-8").replace("model: inherit", "model: opus"), encoding="utf-8")
        (self.root / ".github" / "pull_request_template.md").write_text("mine\n", encoding="utf-8")
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n# user comment\napprovers = ["@me"]\n', encoding="utf-8")
        gate = self.root / ".github" / "workflows" / "aidd-gate.yml"
        gate.write_text(gate.read_text(encoding="utf-8") + "# edited gate\n", encoding="utf-8")
        tests = self.root / ".github" / "workflows" / "aidd-tests.yml"
        tests.write_text(tests.read_text(encoding="utf-8") + "# edited tests\n", encoding="utf-8")
        relay = self.root / ".github" / "workflows" / "aidd-relay.yml"
        relay.write_text(relay.read_text(encoding="utf-8") + "# edited relay\n", encoding="utf-8")

        actions = repo.uninstall(self.root, yes=True)
        self.assertTrue(agent.is_file())
        self.assertEqual((self.root / ".github" / "pull_request_template.md").read_text(encoding="utf-8"), "mine\n")
        self.assertTrue(cfg.is_file())
        self.assertTrue(gate.is_file())
        self.assertTrue(tests.is_file())
        self.assertTrue(relay.is_file())
        self.assertTrue(any("kept" in a and "developer.md" in a for a in actions))
        self.assertTrue(any("kept" in a and "config.toml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-gate.yml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-tests.yml" in a for a in actions))
        self.assertTrue(any("kept" in a and "aidd-relay.yml" in a for a in actions))
        self.assertFalse((self.root / ".claude" / "agents" / "tester.md").exists())

    def test_user_edits_are_kept_gitlab(self):
        repo.init(self.root, profile="solo", ci="gitlab", links=[], harnesses=[])
        gl = self.root / ".gitlab" / "aidd.gitlab-ci.yml"
        gl.write_text(gl.read_text(encoding="utf-8") + "# user customized gitlab ci\n", encoding="utf-8")
        actions = repo.uninstall(self.root, yes=True)
        self.assertTrue(gl.is_file())
        self.assertTrue(any("kept" in a and "aidd.gitlab-ci.yml" in a for a in actions))

    def test_marked_sections_are_stripped_and_a_bare_file_is_removed(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n<!-- aidd-team -->\n## Team roles (aidd-team)\n\nroles\n"
        self.assertEqual(repo.strip_marked_section(repo.strip_marked_section(text, repo.TEAM_MARK), repo.AGENTS_MARK), "# Agents\n")
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n## Ours\n\nkeep\n"
        self.assertEqual(repo.strip_marked_section(text, repo.AGENTS_MARK), "# Agents\n\n## Ours\n\nkeep\n")


class InstallerAndCliTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sh"), "sh is required")
    def test_installer_parses(self):
        subprocess.run(["sh", "-n", str(ROOT / "install.sh")], check=True)
        self.assertTrue(os.access(ROOT / "install.sh", os.X_OK))

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
        parser = cli.build_parser()
        init_flags = set(parser._subparsers._group_actions[0].choices["init"]._option_string_actions)
        other_commands = {"--version", "--help", "--yes", "--force", "--context", "--user"}  # aidd, uninstall, gate, pip
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
                self.assertEqual(cli.main(["init", str(root), "--profile", "solo", "--ci", "none", "--harness", "none"]), 0)
                self.assertEqual(cli.main(["uninstall", str(root)]), 0)
            self.assertIn("dry run", out.getvalue())
            self.assertTrue((root / ".aidd" / "config.toml").is_file())
            self.assertIn("detected no coding agent", out.getvalue())


class AuditRegressionTests(unittest.TestCase):
    """Each test reproduces a defect the code audit found in init, uninstall, and the marked sections."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_harness_none_mixed_with_a_name_drops_none(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["init", str(self.root), "--profile", "solo", "--ci", "none", "--harness", "gemini", "--harness", "none"]), 0)
        self.assertIn("detected Gemini CLI", out.getvalue())

    def test_marked_section_stops_at_a_top_level_heading_and_a_bare_mark_loses_only_its_line(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nbody\n\n# Other\n\nkeep me\n"
        self.assertEqual(repo.strip_marked_section(text, repo.AGENTS_MARK), "# Agents\n\n# Other\n\nkeep me\n")
        text = "# Agents\n\n<!-- aidd -->\n\n## Ours\n\nkeep\n"
        self.assertEqual(repo.strip_marked_section(text, repo.AGENTS_MARK), "# Agents\n\n\n## Ours\n\nkeep\n")

    def test_uninstall_keeps_user_files_inside_team_folders(self):
        repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["claude-code"], team=True)
        note = self.root / ".claude" / "skills" / "aidd-web-front-end" / "NOTES.md"
        note.write_text("mine\n", encoding="utf-8")
        mine = self.root / ".claude" / "commands" / "my-command.md"
        mine.write_text("mine\n", encoding="utf-8")
        edited = self.root / ".claude" / "commands" / "aidd-implement.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8")
        repo.uninstall(self.root, yes=True)
        self.assertTrue(note.is_file())
        self.assertTrue(mine.is_file())
        self.assertTrue(edited.is_file())
        self.assertFalse((self.root / ".claude" / "commands" / "aidd-review.md").exists())
        self.assertFalse((self.root / ".claude" / "skills" / "aidd-health").exists())

    def test_malformed_settings_do_not_abort_init_or_uninstall(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
        actions = repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["claude-code"])
        self.assertTrue((self.root / ".aidd" / "config.toml").is_file())
        self.assertTrue(any("not valid JSON" in a for a in actions))
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{not json")
        actions = repo.uninstall(self.root, yes=True)
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{not json")
        self.assertTrue(any("not valid JSON" in a for a in actions))

    def test_a_failed_plugin_install_falls_back_to_repository_wiring(self):
        real_which = repo.shutil.which
        with (
            mock.patch.object(repo.shutil, "which", lambda name, path=None: "/usr/bin/claude" if name == "claude" else real_which(name, path=path)),
            mock.patch.object(repo, "PLUGIN_RUNNER", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")),
        ):
            actions = repo.init(self.root, profile="solo", ci="none", links=[], harnesses=["claude-code"], claude_plugins=True)
        self.assertTrue(any(a.startswith("failed   claude plugin marketplace add") and "wiring the repository instead" in a for a in actions))
        self.assertTrue((self.root / ".claude" / "settings.json").is_file())
        assert_skill_linked(self, self.root)


if __name__ == "__main__":
    unittest.main()
