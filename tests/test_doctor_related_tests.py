"""`aidd doctor` suggests the narrowed form of a config test command: one note for each command with no
`related_tests` whose runner's documentation gives a related-tests mode, and none for any other, so a person sees the form
`aidd test --changed` can run before a slow full suite costs them on every change."""

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import config
from aidd.setup import doctor_checks, doctor_tests


def cfg(tests: str) -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + tests)


JEST = '  - name: unit\n    command: ["npx", "jest", "--ci"]\n'
NARROWED = '    related_tests: {command: ["npx", "jest", "--findRelatedTests", "{changed_paths}"], sees: ["src/**"]}\n'
PYTEST = '  - name: py\n    command: ["pytest", "-q"]\n'


class RelatedTestsNoteTests(unittest.TestCase):
    def test_one_note_for_each_command_whose_runner_can_narrow_and_has_no_form_yet(self):
        rows = [
            ("no tests", "", 0),
            ("one jest command", "tests:\n" + JEST, 1),
            ("jest with its form", "tests:\n" + JEST + NARROWED, 0),
            ("a runner with no mode", "tests:\n" + PYTEST, 0),
            ("many, one of each", "tests:\n" + JEST + PYTEST + JEST.replace("unit", "unit2"), 2),
        ]
        for label, tests, count in rows:
            with self.subTest(label):
                lines = doctor_tests.related_tests_lines(cfg(tests))
                self.assertEqual(len(lines), count)
                for level, message in lines:
                    self.assertEqual(level, "note", "advice, never a warning")
                    self.assertIn('"--findRelatedTests", "{changed_paths}"', message, "the runner's own form")
                    self.assertIn("related_tests:", message)
                    self.assertIn(config.CONFIG_PATH, message)

    def test_a_command_word_from_the_config_prints_on_one_line(self):
        # A test's name is a plain token by the schema, so the words before the runner are the text a file controls.
        hostile = JEST.replace('["npx", "jest"', '["env\\u001b[2J\\nnext", "npx", "jest"')
        ((_, message),) = doctor_tests.related_tests_lines(cfg("tests:\n" + hostile))
        self.assertNotIn("\n", message)
        self.assertNotIn("\x1b", message)

    def test_aidd_doctor_prints_the_note_and_failures_only_leaves_it_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".aidd").mkdir()
            (root / config.CONFIG_PATH).write_text('aidd_version: "1.0.0"\nprofile: solo\ntests:\n' + JEST + PYTEST, encoding="utf-8")
            notes = [m for level, m in doctor_checks.doctor(root) if level == "note" and "related_tests:" in m]
            self.assertEqual(len(notes), 1, "the jest command only")
            self.assertFalse([m for _, m in doctor_checks.doctor(root, failures_only=True) if "related_tests:" in m])


if __name__ == "__main__":
    unittest.main()
