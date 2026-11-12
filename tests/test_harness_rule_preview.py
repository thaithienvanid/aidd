"""The line `aidd upgrade` and `aidd init` print for a harness's ask rules lists the rules added and removed by action, and the
dry run and the real run print the same one, because both read one computation (`risk.apply_harness_rules`)."""

import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config
from aidd.setup import adoption, upgrading

LOWER = "risks:\n  rules:\n    - {action: git.tag.create, level: allow}\n"
# Two ways to stop asking: an action's own commands, and a family a rule writes only while it asks (a push to the default branch).
LOWERED = (
    (LOWER, "git.tag.create"),
    ("risks:\n  rules:\n    - {action: git.push, branch: default, level: allow}\n    - {action: git.push, branch: shared, level: allow}\n", "git.push"),
)
KEYS = [key for key, h in config.HARNESSES.items() if h.ask_rules]


def ask_lines(actions: list[str]) -> list[str]:
    return [a for a in actions if "ask rules into" in a]


class AskRuleLinesNameTheActions(unittest.TestCase):
    def repo(self, key: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[key]))
        return root

    def test_every_harness_says_which_actions_gained_and_lost_rules(self):
        for key in KEYS:
            with self.subTest(harness=key):
                root = self.repo(key)
                cfg = root / ".aidd" / "config.yaml"
                original = cfg.read_text(encoding="utf-8")
                self.assertEqual(ask_lines(upgrading.upgrade(root, ref="v1.0.0")), [], "a repository init just wrote is current")
                for lowered, action in LOWERED:
                    for text, word in ((original + lowered, "removed"), (original, "added")):
                        cfg.write_text(text, encoding="utf-8")
                        dry = ask_lines(upgrading.upgrade(root, ref="v1.0.0"))
                        real = ask_lines(upgrading.upgrade(root, ref="v1.0.0", yes=True))
                        self.assertEqual(len(dry), 1, dry)
                        self.assertEqual(len(real), 1, real)
                        self.assertTrue(dry[0].startswith("would write ask rules into "), dry)
                        self.assertIn(f"{word} ", dry[0])
                        self.assertIn(f"`{action}`", dry[0])
                        self.assertNotIn("`other`", dry[0], "every rule names its action")
                        self.assertEqual(dry[0].removeprefix("would write "), real[0].split(None, 1)[1], "one computation: the preview is the run")
                        self.assertEqual(ask_lines(upgrading.upgrade(root, ref="v1.0.0")), [], "and it ran")


if __name__ == "__main__":
    unittest.main()
