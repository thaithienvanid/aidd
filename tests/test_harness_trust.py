"""`aidd doctor` names each harness that holds back the project's rules until a person trusts the folder: whether its
ask rules wait, how to check, and the words to type. The trust lives in the person's own files, which doctor never
reads, so it says plainly that it cannot see it."""

import sys
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config
from aidd.setup import doctor_checks

# Every real file open in this process while `_OPENS` is a list (the `open` audit event: io.open, os.open, Path.open).
_OPENS: list[str] | None = None


def _audit(event: str, args: tuple) -> None:
    # A `.py` file opened is the interpreter or a coverage tracer reading code, never the trust check reading data.
    if event == "open" and _OPENS is not None and not str(args[0]).endswith(".py"):
        _OPENS.append(str(args[0]))


sys.addaudithook(_audit)


class TrustLineTests(unittest.TestCase):
    def test_each_harness_with_a_trust_step_gets_one_line_from_its_data(self):
        cases = [("codex", True), ("grok-build", True), ("qwen-code", True), ("claude-code", False), ("copilot", False), ("opencode", None), ("cursor", None)]
        for harness, holds_ask_rules in cases:
            with self.subTest(harness=harness):
                trust = config.HARNESSES[harness].trust
                lines = doctor_checks.trust_checks([harness])
                if holds_ask_rules is None:
                    self.assertEqual((trust, lines), (None, []))
                    continue
                self.assertEqual(trust.holds_ask_rules, holds_ask_rules)
                ((level, line),) = lines
                self.assertEqual(level, "info")
                for part in (trust.when, trust.holds, trust.how):
                    self.assertIn(part, line)
                # The way to check is said only when it is not the trust step again, so the line never says one thing twice.
                self.assertEqual(trust.check in line, not doctor_checks.repeats_trust_step(trust.how, trust.check), harness)
                self.assertEqual(line.count(trust.how.split(" and ")[0]), 1, line)

    def test_a_rule_the_harness_cannot_hold_is_named_by_its_action_never_its_pattern(self):
        for harness in ("claude-code", "codex"):
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as d:
                git(Path(d), "init", "-q")
                lines = [line for level, line in doctor_checks.harness_checks(Path(d), [harness]) if "miss a few forms" in line]
                self.assertEqual(len(lines), 1, harness)
                self.assertIn("`git.branch.delete` (Delete a branch", lines[0])
                self.assertNotIn(":*", lines[0])

    def test_doctor_opens_no_file_for_the_trust(self):
        """The trust check opens no file at all, and doctor gives the line for a repository that wires Codex."""
        global _OPENS
        _OPENS = []
        try:
            lines = doctor_checks.trust_checks(list(config.HARNESSES))
            opened = _OPENS
        finally:
            _OPENS = None
        self.assertEqual(opened, [])
        self.assertEqual(len(lines), sum(h.trust is not None for h in config.HARNESSES.values()))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            (root / ".codex").mkdir()
            lines = [text for _, text in doctor_checks.doctor(root)]
        self.assertEqual(len([t for t in lines if t.startswith("Codex: ") and config.HARNESSES["codex"].trust.how in t]), 1, lines)


class TrustDataTests(unittest.TestCase):
    def test_a_trust_step_belongs_to_a_harness_aidd_writes_ask_rules_for(self):
        self.assertTrue(all(h.trust is None or h.ask_rules for h in config.HARNESSES.values()))


if __name__ == "__main__":
    unittest.main()
