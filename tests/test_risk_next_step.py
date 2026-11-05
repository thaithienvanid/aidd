"""`aidd risk --paths` gives one next step: a new feature with no test gets its test first inside the fast lane's step,
never a second step that names another lane, and the spec lane's step names the command as it runs."""

import unittest

from helpers import run_cli

from aidd import risk


class OneNextStepTests(unittest.TestCase):
    def test_one_step_by_the_lane_and_whether_the_new_code_has_a_test(self):
        cases = [
            # (planned paths, tracked files, the change type, the lane, whether the step writes the new code's test first)
            (["src/orders.py"], [], "feat", "fast", True),
            (["src/orders.py", "tests/test_orders.py"], [], "feat", "fast", False),
            (["src/orders.py"], ["src/orders.py"], "feat", "fast", False),
            (["src/orders.py"], [], "fix", "fast", False),
            (["src/payments/charge.py"], [], "feat", "spec", False),
        ]
        for paths, tracked, change_type, lane, test_first in cases:
            answer = risk.advice(None, paths, change_type=change_type, tracked=tracked)
            self.assertEqual((answer["lane"], answer["hints"]), (lane, []), paths)
            self.assertEqual("write a test for the new code" in answer["step"].casefold(), test_first, (paths, answer["step"]))
            self.assertNotIn("<ID>", answer["step"], "`aidd new spec` picks the id itself")

    def test_the_text_has_one_next_line_and_no_hint(self):
        code, out = run_cli("risk", "--paths", "src/orders.py")
        self.assertEqual(code, 0, out)
        self.assertEqual(sum(line.startswith("next:") for line in out.splitlines()), 1, out)
        self.assertFalse([line for line in out.splitlines() if line.startswith("hint:")], out)


if __name__ == "__main__":
    unittest.main()


class FromASubfolderTests(unittest.TestCase):
    """A relative path typed in a subfolder is read from there, as git reads it, never from the repository's top: from
    src/billing/, `charge.py` is a billing file, which the built-in payments area routes major."""

    def test_a_relative_path_is_read_from_the_folder_it_was_typed_in(self):
        import contextlib
        import json
        import tempfile
        from pathlib import Path

        from helpers import make_repo

        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "shop", branch=None)
            (root / "src" / "billing").mkdir(parents=True)
            with contextlib.chdir(root / "src" / "billing"):
                code, out = run_cli("risk", "--paths", "charge.py", "--json")
            self.assertEqual(code, 0, out)
            answer = json.loads(out)
            self.assertEqual(answer["route"], "major", answer)
            self.assertIn("payments", [a["area"] for a in answer["areas"]])
