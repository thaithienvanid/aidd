"""`aidd doctor` names the agent that runs the session, from the variable that agent sets in its own shell, and says
plainly when the repository does not wire it."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd import config
from aidd.config import harness_settings, harnesses
from aidd.setup import adoption, doctor_checks


class SessionHarnessTests(unittest.TestCase):
    def test_each_agents_own_variable_names_it(self):
        cases = [
            ({"CLAUDECODE": "1"}, "claude-code"),
            ({"CODEX_SANDBOX": "seatbelt"}, "codex"),
            ({"OPENCODE": "1"}, "opencode"),
            ({"ANTIGRAVITY_AGENT": "1"}, "antigravity"),
            ({"CLAUDECODE": ""}, None),
            ({"TERM": "xterm"}, None),
        ]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(harnesses.session_harness(env), want)

    def test_every_named_agent_is_a_harness_aidd_knows(self):
        self.assertLessEqual(set(harnesses.SESSION_ENV.values()), set(config.HARNESSES))


class DoctorLineTests(unittest.TestCase):
    def lines(self, env: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["@lead"], harnesses=["codex"]))
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(harness_settings, "user_plugins_enabled", return_value=set()):
                return [text for _, text in doctor_checks.doctor(root)]

    def test_an_unwired_agent_is_named_with_the_line_that_wires_it(self):
        found = [line for line in self.lines({"OPENCODE": "1"}) if "runs this session" in line]
        self.assertEqual(len(found), 1)
        self.assertIn("aidd init --harness opencode", found[0])

    def test_a_wired_agent_or_no_agent_adds_no_line(self):
        for env in ({"CODEX_SANDBOX": "seatbelt"}, {}):
            with self.subTest(env=env):
                self.assertFalse([line for line in self.lines(env) if "runs this session" in line])


class ClaudeFolderTests(unittest.TestCase):
    """A `.claude/` folder shows Claude Code's wiring only when it holds the agent's own files."""

    def test_only_its_files_show_the_agent(self):
        cases = [
            ((), False),  # an empty folder
            (("worktrees/",), False),  # Claude Code's own worktrees: this machine's state
            (("skills/aidd/",), False),  # the link aidd init writes
            (("skills/aidd/", "worktrees/"), False),
            (("settings.local.json",), False),  # this machine's own settings
            (("settings.json",), True),
            (("agents/",), True),
            (("worktrees/", "settings.json"), True),
        ]
        for entries, wired in cases:
            with self.subTest(entries=entries):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / ".claude").mkdir()
                    for entry in entries:
                        target = root / ".claude" / entry
                        if entry.endswith("/"):
                            target.mkdir(parents=True)
                        else:
                            target.write_text("{}", encoding="utf-8")
                    self.assertEqual("claude-code" in adoption.detect_harnesses(root), wired)

    def test_in_aidds_own_source_the_upgrade_runs_from_its_code(self):
        from aidd.setup import upgrading

        self.assertTrue(upgrading.aidd_source(ROOT))
        self.assertIn(upgrading.SOURCE_UPGRADE, upgrading.older_than_repository(ROOT) or upgrading.SOURCE_UPGRADE)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(upgrading.aidd_source(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
