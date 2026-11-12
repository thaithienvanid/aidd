"""A harness whose ask rules aidd wrote stays known through aidd's own ledger (`.aidd/harness-rules.json`), so its rules never go
stale: after `aidd init --harness <h>`, `aidd doctor` compares them and `aidd upgrade` keeps them current, for every harness
with a format, including GitHub Copilot, whose rules sit in `.vscode/settings.json` where no folder shows Copilot."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd import config
from aidd.config import harness_settings
from aidd.setup import adoption, doctor_checks, upgrading

KEYS = [key for key, h in config.HARNESSES.items() if h.ask_rules]
LOWER = "risks:\n  rules:\n    - {action: git.tag.create, level: allow}\n"


class TheLedgerKeepsAHarnessKnown(unittest.TestCase):
    def repo(self, key: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[key]))
        return root

    def doctor(self, root: Path) -> list[tuple[str, str]]:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(harness_settings, "user_plugins_enabled", return_value=set()):
            return doctor_checks.doctor(root)

    def test_every_harness_with_a_format_is_wired_after_init_and_stays_current(self):
        for key in KEYS:
            with self.subTest(harness=key):
                label, root = config.HARNESSES[key].label, self.repo(key)
                self.assertIn(key, adoption.wired_harnesses(root))
                self.assertIn(("ok", f"{label}: its ask rules match the risk rules"), self.doctor(root))
                self.assertFalse([m for lv, m in self.doctor(root) if m.startswith("no ask rules")], "doctor never says no agent takes ask rules")
                cfg = root / ".aidd" / "config.yaml"
                cfg.write_text(cfg.read_text(encoding="utf-8") + LOWER, encoding="utf-8")
                stale = [m for lv, m in self.doctor(root) if lv == "warn" and m.startswith(f"{label}: its ask rules are not current")]
                self.assertEqual(len(stale), 1, (key, stale))
                self.assertTrue(
                    [a for a in upgrading.upgrade(root, ref="v1.0.0") if a.startswith("would write ask rules into")], "a dry run says what it writes"
                )
                upgrading.upgrade(root, ref="v1.0.0", yes=True)
                self.assertIn(("ok", f"{label}: its ask rules match the risk rules"), self.doctor(root))

    def test_only_an_agent_whose_rules_file_is_still_there_stays_known(self):
        root = self.repo("copilot")
        self.assertEqual(adoption.wired_harnesses(root), ["copilot"])
        (root / ".vscode" / "settings.json").unlink()
        self.assertEqual(adoption.wired_harnesses(root), [], "a person who removed the rules is not given them again")

    def test_a_ledger_that_cannot_be_read_adds_no_agent_and_raises_nothing(self):
        root = self.repo("copilot")
        (root / config.HARNESS_RULES_FILE).write_text("[not an object]", encoding="utf-8")
        self.assertEqual(adoption.wired_harnesses(root), [])


if __name__ == "__main__":
    unittest.main()
