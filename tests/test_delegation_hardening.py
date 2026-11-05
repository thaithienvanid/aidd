"""The delegate check's answers to the full security review: a Spec edit behind a verified head, a test file changed on
the fast lane, an area a config narrows, the triggers and steps that deploy, a test workflow that only mentions
`aidd test`, a person's own ask rule, and a repository with no Claude Code."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ
from test_delegation_check import Case, Repo, codes, note

from aidd import risk
from aidd.delegation import action_gates, diff_signals
from aidd.delegation.check import Check, Request
from aidd.setup import delegation_wiring


class FastLaneTests(Case):
    def test_a_test_file_the_base_holds_must_stay_byte_equal(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        repo.write("tests/test_cart.py", "def test_total():\n    assert 1 + 1 == 2\n")
        repo.commit("a test")
        git(self.root, "checkout", "-q", "-B", "feature")
        repo.write("tests/test_cart.py", "def test_total():\n    assert 1 + 1 == 2\n    return\n")  # a line added, none taken out
        head = repo.change()
        self.assertIn("tests-changed", codes(repo.check(head)))
        self.assertEqual(diff_signals.changed_test_files("main", head, str(self.root)), ["tests/test_cart.py"])

    def test_a_new_test_file_is_fine(self):
        repo = self.repo()
        repo.write("tests/test_new.py", "def test_new():\n    assert True\n")
        self.assertEqual(codes(repo.check(repo.change())), [])


class ReservedAreaTests(Case):
    def test_a_config_that_redefines_an_area_only_adds_to_what_is_reserved(self):
        narrowed = '  reserved: []\nrisks:\n  areas:\n    ci: {paths: ["nothing/**"]}\n'
        repo = Repo(self.root, extra=narrowed)
        result = repo.check(repo.change(".github/workflows/release.yml", "name: release\n"))
        self.assertIn("reserved-path", codes(result))


class ProjectConfigTests(unittest.TestCase):
    def test_each_test_runner_file_is_reserved(self):
        rs = risk.rule_set(None)
        for path in ("pytest.toml", ".pytest.toml", ".pytest.ini", "vitest.workspace.ts", ".mocharc.yml", "babel.config.js", ".babelrc", "jest.setup.js"):
            with self.subTest(path):
                self.assertTrue(diff_signals.reserved_paths(rs, [path]))


class WorkflowTests(unittest.TestCase):
    def test_a_trigger_the_scan_cannot_rule_out_reaches_the_branch(self):
        rs = risk.rule_set(None)
        cases = {
            "on:\n  workflow_run:\n    workflows: [tests]\njobs:\n  a:\n    environment: prod\n": True,
            "on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  a:\n    environment: prod\n": True,
            "name: no trigger\njobs:\n  a:\n    environment: prod\n": True,
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: npx vercel deploy --prod\n": True,
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: npm run deploy\n": True,
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: make deploy\n": True,
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: ./scripts/deploy-site.sh\n": True,
            "on:\n  workflow_dispatch:\njobs:\n  a:\n    environment: prod\n": False,
        }
        for text, deploys in cases.items():
            with self.subTest(text):
                self.assertEqual(diff_signals.push_reaches(text, "main") and diff_signals.deploy_line(text, rs) is not None, deploys)

    def test_a_test_workflow_runs_aidd_test_and_never_only_mentions_it(self):
        self.assertTrue(action_gates.RUNS_AIDD_TEST.search("jobs:\n  t:\n    steps:\n      - uses: thaithienvanid/aidd@v1.0.0\n"))
        self.assertTrue(action_gates.RUNS_AIDD_TEST.search("    steps:\n      - run: aidd test\n"))
        for text in ("      # uses: thaithienvanid/aidd@v1\n", "      - run: echo aidd test\n", "      - run: echo 'skip aidd test'\n"):
            with self.subTest(text):
                self.assertIsNone(action_gates.RUNS_AIDD_TEST.search(text))


class SetupTests(unittest.TestCase):
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

    def test_taking_the_delegation_out_keeps_a_persons_own_ask_rule(self):
        own = {"permissions": {"ask": ["Bash(git merge --no-ff *)"]}}
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text(json.dumps(own), encoding="utf-8")
        cfg = type("Cfg", (), {"get": lambda self, k, default=None: {"to": "delegate"} if k == "delegation" else default})()
        delegation_wiring.apply(self.root, cfg)
        delegation_wiring.apply(self.root, None)
        after = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(after["permissions"]["ask"], ["Bash(git merge --no-ff *)"], "aidd claims only the rules it added")
        self.assertNotIn("hooks", after)

    def test_a_codex_only_delegation_says_claude_code_alone_answers(self):
        (self.root / ".codex").mkdir()
        done = aidd_subprocess("init", ".", "--profile", "solo", "--ci", "none", "--harness", "codex", "--delegate", cwd=self.root, env=hermetic_environ())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("only Claude Code answers a delegated ask", done.stdout)
        from aidd import config

        lines = delegation_wiring.doctor_lines(self.root, config.load_file(config.CONFIG_PATH, str(self.root)))
        self.assertFalse(any("disableAllHooks" in m or "Claude Code mod" in m for _, m in lines), "no Claude Code advice where it is not set up")


class SpecEditTests(Case):
    def test_a_spec_edit_behind_the_verified_head_is_another_head(self):
        repo = self.repo()
        repo.write("specs/SPEC-1.md", "# The plan\n")
        code = repo.commit("Change")
        repo.write("specs/SPEC-1.md", "# The plan\n\n" + note(code))
        noted = repo.commit("Hand off in the Spec")
        repo.write("specs/SPEC-1.md", "# The plan, widened after the note\n\n" + note(code))
        edited = repo.commit("Edit the Spec")
        for head, holds in ((noted, True), (edited, False)):
            with self.subTest(head=head):
                check = Check(Request(action="git.merge", head=head, cwd=str(self.root)))
                check.open_repository()
                self.assertEqual(action_gates.names_the_head(check, code, "specs/SPEC-1.md"), holds)


if __name__ == "__main__":
    unittest.main()
