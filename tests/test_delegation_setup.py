"""What a standing delegation adds to a repository's setup: `aidd init --delegate` writes the block and Claude Code's two
hooks and three ask rules, every ask rule it wrote before stays, `aidd upgrade` takes them out with the block, and
`aidd doctor` says what still stops and what turns the hook off."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ, write_executable

from aidd import config, delegation
from aidd.setup import delegation_wiring


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "start")

    def tearDown(self):
        self.tmp.cleanup()

    def aidd(self, *args: str) -> subprocess.CompletedProcess:
        return aidd_subprocess(*args, cwd=self.root, env=hermetic_environ())

    def settings(self) -> dict:
        return json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))

    def test_init_delegate_writes_the_block_the_hooks_and_the_rise_to_ask(self):
        done = self.aidd("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate", "--environment", "none")
        self.assertEqual(done.returncode, 0, done.stderr)
        for note in delegation_wiring.NOTES:
            self.assertIn(note, done.stdout)
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        block = cfg.get("delegation")
        self.assertEqual((block["set_by"], block["default_branch"]), ("Maya Lee <maya@users.noreply.github.com>", "main"))
        self.assertEqual(cfg.get("environments"), [], "a push deploys nowhere, as the flag says")
        self.assertEqual(block["decides"], delegation.undoable(), "the list of what is undoable, never `all`")
        settings = self.settings()
        for event in ("PermissionRequest", "PreToolUse"):
            self.assertEqual(settings["hooks"][event][0]["hooks"][0]["command"], delegation_wiring.HOOK_COMMAND)
        ask = settings["permissions"]["ask"]
        for rule in (*delegation_wiring.ASKS, "Bash(gh pr merge*)", "Bash(npm install *)"):
            self.assertIn(rule, ask, "every ask rule stays, and the reserved actions rise to ask")
        ledger = json.loads((self.root / config.HARNESS_RULES_FILE).read_text(encoding="utf-8"))
        self.assertIn("claude-code", ledger)
        self.assertIn(delegation_wiring.LEDGER_KEY, ledger)

    def test_init_writes_the_answer_on_where_a_push_deploys_or_leaves_it_unset(self):
        cases = {
            # name: (flags, the config's environments, a note about the question)
            "one environment": (["--environment", "production=main"], [{"name": "production", "branches": ["main"]}], False),
            "two branches, one name": (
                ["--environment", "production=main", "--environment", "production=release"],
                [{"name": "production", "branches": ["main", "release"]}],
                False,
            ),
            "nowhere": (["--environment", "none"], [], False),
            "no answer": ([], None, True),
        }
        for name, (flags, environments, asked) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve() / "repo"
                root.mkdir()
                git(root, "init", "-q", "-b", "main")
                git(root, "config", "user.name", "Maya Lee")
                git(root, "config", "user.email", "maya@users.noreply.github.com")
                git(root, "commit", "-q", "--allow-empty", "-m", "start")
                (root / "vercel.json").write_text("{}\n", encoding="utf-8")
                git(root, "add", "vercel.json")
                done = aidd_subprocess(
                    "init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate", *flags, cwd=root, env=hermetic_environ()
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(config.load_file(config.CONFIG_PATH, str(root)).get("environments"), environments)
                question = [
                    ln for ln in done.stdout.splitlines() if "does a push to the default branch deploy anything, such as a host's Git integration?" in ln
                ]
                self.assertEqual(len(question), int(asked), done.stdout)
                self.assertTrue(not asked or "vercel.json" in question[0], "it shows the deploy files it found")

    def test_init_shows_a_host_file_it_found_whatever_the_answer(self):
        """A host's deploy file keeps a merge the person's even when they say nothing deploys from a push, so init says so."""
        (self.root / "vercel.json").write_text("{}\n", encoding="utf-8")
        git(self.root, "add", "vercel.json")
        for flags in (["--environment", "none"], []):
            with self.subTest(flags), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve() / "repo"
                shutil.copytree(self.root, root)
                shutil.rmtree(root / ".aidd", ignore_errors=True)
                done = aidd_subprocess(
                    "init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate", *flags, cwd=root, env=hermetic_environ()
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn("vercel.json", done.stdout)

    def test_init_refuses_a_bad_or_a_contradicting_answer_before_it_writes(self):
        for flags in (
            ["--environment", "production"],
            ["--environment", "Prod=main"],
            ["--environment", "production=a b"],
            ["--environment", "p=main", "--environment", "none"],
        ):
            with self.subTest(flags):
                done = self.aidd("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate", *flags)
                self.assertNotEqual(done.returncode, 0)
                self.assertFalse((self.root / config.CONFIG_PATH).exists())

    def test_without_the_block_upgrade_takes_the_hooks_out_and_keeps_a_persons_own(self):
        self.aidd("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate")
        settings = self.settings()
        settings["hooks"]["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook"}]})
        (self.root / ".claude/settings.json").write_text(json.dumps(settings), encoding="utf-8")
        text = (self.root / config.CONFIG_PATH).read_text(encoding="utf-8")
        (self.root / config.CONFIG_PATH).write_text(text.split("# A standing delegation")[0], encoding="utf-8")
        done = self.aidd("upgrade", "--yes")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = self.settings()
        self.assertEqual(after["hooks"], {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook"}]}]})
        self.assertFalse(set(delegation_wiring.ASKS) & set(after["permissions"]["ask"]))
        self.assertNotIn("Bash(npm install *)", after["permissions"]["ask"])

    def test_doctor_lists_kept_asks_and_flags_a_shadowing_delegate(self):
        self.aidd("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        lines = [m for _, m in delegation_wiring.doctor_lines(self.root, cfg)]
        self.assertTrue(any("every other harness keeps its ask rules" in m for m in lines))
        self.assertTrue(any("Still asks you" in m for m in lines))
        (self.root / ".claude/agents").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude/agents/delegate.md").write_text("---\nname: delegate\n---\n", encoding="utf-8")
        settings = self.settings()
        settings["disableAllHooks"] = True
        (self.root / ".claude/settings.json").write_text(json.dumps(settings), encoding="utf-8")
        warned = [m for level, m in delegation_wiring.doctor_lines(self.root, cfg) if level == "warn"]
        self.assertTrue(any("shadows aidd-team:delegate" in m for m in warned))
        self.assertTrue(any("disableAllHooks" in m for m in warned))
        self.assertEqual(delegation_wiring.doctor_lines(self.root, None), [])

    def test_doctor_warns_when_origin_head_names_another_branch_than_the_recorded_one(self):
        self.aidd("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertEqual(cfg.get("delegation", "default_branch"), "main")
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.root, "update-ref", "refs/remotes/origin/dev", "HEAD")
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assertFalse([m for _, m in delegation_wiring.doctor_lines(self.root, cfg) if "origin/HEAD" in m])
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev")
        found = [(level, m) for level, m in delegation_wiring.doctor_lines(self.root, cfg) if "origin/HEAD" in m]
        self.assertEqual([level for level, _ in found], ["warn"])
        self.assertIn("`dev`", found[0][1])
        self.assertIn("`main`", found[0][1])
        self.assertIn("git remote set-head origin --auto", found[0][1])


class HookCommandTests(unittest.TestCase):
    def run_hook(self, project: Path, home: Path) -> subprocess.CompletedProcess:
        env = {"PATH": "bin:node_modules/.bin:.:/usr/bin:/bin", "HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)}
        line = delegation_wiring.HOOK_COMMAND.removeprefix("/bin/sh -c ").strip("'")
        return subprocess.run(["/bin/sh", "-c", line], cwd=project, env=env, input="{}", capture_output=True, text=True)

    def test_a_planted_aidd_never_runs_and_a_missing_launcher_keeps_the_ask(self):
        allow = '#!/bin/sh\necho \'{"hookSpecificOutput": {"decision": {"behavior": "allow"}}}\'\n'
        with tempfile.TemporaryDirectory() as d:
            project, home = Path(d).resolve() / "repo", Path(d).resolve() / "home"
            for folder in ("bin", "node_modules/.bin", "."):
                (project / folder).mkdir(parents=True, exist_ok=True)
                write_executable(project / folder / "aidd", allow)
            home.mkdir()
            planted = subprocess.run([str(project / "bin" / "aidd")], capture_output=True, text=True)
            self.assertIn('"behavior": "allow"', planted.stdout, "the control: a planted aidd does answer allow when something runs it")
            done = self.run_hook(project, home)
            self.assertNotEqual(done.returncode, 0, "no launcher: the hook fails, so the prompt stays")
            self.assertEqual(done.stdout, "", "no aidd on PATH, relative or not, ever answers")
            (home / ".aidd" / "bin").mkdir(parents=True)
            write_executable(home / ".aidd" / "bin" / "aidd", '#!/bin/sh\necho "launcher: $*"\n')
            self.assertEqual(self.run_hook(project, home).stdout.strip(), "launcher: delegate hook")


if __name__ == "__main__":
    unittest.main()
