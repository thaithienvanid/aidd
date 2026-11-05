"""tools/sync_pins.py copies the pins Dependabot moves into templates/github/, so a bump's follow-up is one command."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

_spec = importlib.util.spec_from_file_location("sync_pins", ROOT / "tools" / "sync_pins.py")
assert _spec and _spec.loader
sync_pins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_pins)

OLD, NEW = "a" * 40, "b" * 40
OTHER = f"""steps:
  - uses: actions/checkout@{OLD} # v6.0.0
  - uses: some/only-here@{OLD}
"""


class SyncPinsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / "templates" / "github").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text(f"steps:\n  - uses: actions/checkout@{NEW} # v7.0.1\n", encoding="utf-8")
        (self.root / "action.yml").write_text(f"runs:\n  steps:\n    - uses: actions/checkout@{NEW} # v7.0.1\n", encoding="utf-8")
        self.other = self.root / "templates" / "github" / "aidd-other.yml"
        self.other.write_text(OTHER, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = sync_pins.main(["--root", str(self.root), *args])
        return code, out.getvalue()

    def test_check_lists_what_differs_and_writes_nothing(self):
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("differs: templates/github/aidd-other.yml", out)
        self.assertEqual(self.other.read_text(encoding="utf-8"), OTHER)

    def test_a_run_copies_the_sha_and_its_tag(self):
        code, _ = self.run_tool()
        self.assertEqual(code, 0)
        other = self.other.read_text(encoding="utf-8")
        self.assertIn(f"uses: actions/checkout@{NEW} # v7.0.1", other)
        self.assertIn(f"uses: some/only-here@{OLD}", other, "an action only the templates use keeps its pin")
        self.assertEqual(self.run_tool("--check")[0], 0, "a second run finds nothing to change")

    def test_the_workflows_disagreeing_with_each_other_stops_it(self):
        (self.root / ".github" / "workflows" / "other.yml").write_text(f"steps:\n  - uses: actions/checkout@{OLD} # v6.0.0\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            self.run_tool()
        self.assertIn("several SHAs", str(cm.exception.code))
        self.assertEqual(self.other.read_text(encoding="utf-8"), OTHER)

    def test_a_wrong_folder_stops_it_instead_of_reading_as_in_sync(self):
        for name in ("empty", "no-templates"):
            root = self.root / name
            if name == "no-templates":
                (root / ".github" / "workflows").mkdir(parents=True)
                (root / ".github" / "workflows" / "ci.yml").write_text(f"- uses: actions/checkout@{NEW} # v7.0.1\n", encoding="utf-8")
            root.mkdir(exist_ok=True)
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
                sync_pins.main(["--root", str(root), "--check"])
            self.assertIn("is --root right?", str(cm.exception.code), name)

    def test_two_tags_for_one_action_stop_it(self):
        (self.root / ".github" / "workflows" / "other.yml").write_text(f"steps:\n  - uses: actions/checkout@{NEW} # v7\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            self.run_tool()
        self.assertIn("several SHAs or tags", str(cm.exception.code))

    def test_a_path_action_and_a_missing_tag(self):
        (self.root / ".github" / "workflows" / "scan.yml").write_text(
            f"steps:\n  - uses: github/codeql-action/upload-sarif@{NEW} # v4.38.3\n", encoding="utf-8"
        )
        self.other.write_text(f"steps:\n  - uses: github/codeql-action/upload-sarif@{OLD}\n", encoding="utf-8")
        self.run_tool()
        self.assertIn(f"uses: github/codeql-action/upload-sarif@{NEW} # v4.38.3", self.other.read_text(encoding="utf-8"))

    def test_this_repository_is_in_sync(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sync_pins.main(["--root", str(ROOT), "--check"]), 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
