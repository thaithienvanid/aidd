"""`aidd validate -- <file>` prints one note when cross-file checks exist for that file type and were skipped."""

from __future__ import annotations

import unittest

from helpers import adopted_repo, run_cli


class ValidateCrossFileNoteTests(unittest.TestCase):
    def test_single_work_item_prints_one_cross_file_note(self):
        with adopted_repo() as root:
            (root / "specs").mkdir(exist_ok=True)
            (root / "specs" / "SPEC-1.md").write_text(
                "---\ntype: spec\nid: SPEC-1\ntitle: T\nstatus: draft\n---\n\n# Spec\n",
                encoding="utf-8",
            )
            _code, out = run_cli("validate", "--", "specs/SPEC-1.md")
            note_lines = [line for line in out.splitlines() if line.startswith("note:") and "cross-file" in line]
            self.assertEqual(len(note_lines), 1, out)
            self.assertIn("aidd validate", note_lines[0])

    def test_config_file_prints_no_cross_file_note(self):
        with adopted_repo():
            _code, out = run_cli("validate", "--", ".aidd/config.yaml")
            self.assertNotIn("cross-file", out)


if __name__ == "__main__":
    unittest.main()
