"""`aidd risk --paths` gives one next step: a new feature with no test gets its test first inside the step of a change with no
Spec, never a second step that names another route, and the step of a change with a Spec names the command as it runs."""

import contextlib
import subprocess
import tempfile
import unittest

from helpers import run_cli

from aidd import risk


class OneNextStepTests(unittest.TestCase):
    def test_one_step_by_the_route_and_whether_the_new_code_has_a_test(self):
        cases = [
            # (planned paths, tracked files, the change type, the route, whether the step writes the new code's test first)
            (["src/orders.py"], [], "feat", "minor", True),
            (["src/orders.py", "tests/test_orders.py"], [], "feat", "minor", False),
            (["src/orders.py"], ["src/orders.py"], "feat", "minor", False),
            (["src/orders.py"], [], "fix", "minor", False),
            (["src/payments/charge.py"], [], "feat", "major", False),
        ]
        for paths, tracked, change_type, route, test_first in cases:
            answer = risk.advice(None, paths, change_type=change_type, tracked=tracked)
            self.assertEqual((answer["route"], answer["hints"]), (route, []), paths)
            self.assertEqual("write a test for the new code" in answer["next"]["what"].casefold(), test_first, (paths, answer["next"]["what"]))
            self.assertNotIn("<ID>", answer["next"]["what"], "`aidd new spec` picks the id itself")

    def test_the_text_has_one_next_line_and_no_hint(self):
        # Inside a repository, as an agent runs it: outside one, aidd adds a true hint that a glob names no tracked file.
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d):
            subprocess.run(["git", "init", "-q"], check=True, stdin=subprocess.DEVNULL)
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
