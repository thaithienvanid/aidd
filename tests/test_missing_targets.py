"""Missing file or work-item id errors say what is missing and name a next step that works."""

from __future__ import annotations

import tempfile
import unittest

from helpers import adopted_repo, run_cli


class TestMissingTargets(unittest.TestCase):
    def test_test_spec_path_checks_file_existence_before_commit_check(self):
        with adopted_repo() as root:
            code, out = run_cli("test", "--spec", "specs/SPEC-99.md")
            self.assertEqual(code, 2, out)
            self.assertIn("specs/SPEC-99.md does not exist", out)
            self.assertIn("aidd status", out)
            self.assertIn("aidd new spec", out)
            self.assertNotIn("not in the head commit", out)

            uncommitted = root / "specs" / "SPEC-99.md"
            uncommitted.parent.mkdir(exist_ok=True)
            uncommitted.write_text("---\ntype: spec\nid: SPEC-99\n---\n", encoding="utf-8")
            code2, out2 = run_cli("test", "--spec", "specs/SPEC-99.md")
            self.assertEqual(code2, 2, out2)
            self.assertIn("not in the head commit", out2)

    def test_prototype_missing_file_says_it_does_not_exist(self):
        with adopted_repo():
            code, out = run_cli("prototype", "nonexistent")
            self.assertNotEqual(code, 0, out)
            self.assertIn("nonexistent does not exist", out)
            self.assertIn("aidd new design-spec", out)
            self.assertNotIn("fix the problems", out)

    def test_validate_missing_file_names_next_step_instead_of_fix_each_file(self):
        with adopted_repo():
            code, out = run_cli("validate", "nonexistent.md")
            self.assertNotEqual(code, 0, out)
            self.assertIn("nonexistent.md does not exist", out)
            self.assertIn("aidd validate", out)
            self.assertIn("aidd status", out)
            self.assertNotIn("fix each file", out)

    def test_status_missing_id_names_next_step(self):
        with adopted_repo():
            code, out = run_cli("status", "SPEC-999")
            self.assertEqual(code, 2, out)
            self.assertIn("SPEC-999", out)
            self.assertIn("aidd status", out)
            self.assertIn("aidd new", out)

    def test_test_spec_outside_repo_and_directory_name_cause(self):
        with adopted_repo() as root, tempfile.NamedTemporaryFile(suffix=".md") as outside:
            code_out, out_msg = run_cli("test", "--spec", outside.name)
            self.assertEqual(code_out, 2, out_msg)
            self.assertIn("outside the repository", out_msg)
            self.assertIn("aidd status", out_msg)

            (root / "specs").mkdir(exist_ok=True)
            code_dir, dir_msg = run_cli("test", "--spec", "specs")
            self.assertEqual(code_dir, 2, dir_msg)
            self.assertIn("is a directory", dir_msg)
            self.assertIn("aidd status", dir_msg)

    def test_validate_and_prototype_reject_directories_with_next_step(self):
        with adopted_repo() as root:
            (root / "specs").mkdir(exist_ok=True)
            code_val, out_val = run_cli("validate", "specs")
            self.assertEqual(code_val, 2, out_val)
            self.assertIn("is a directory", out_val)
            self.assertIn("aidd validate", out_val)

            code_proto, out_proto = run_cli("prototype", "specs")
            self.assertNotEqual(code_proto, 0, out_proto)
            self.assertIn("is a directory", out_proto)
            self.assertNotIn("does not exist", out_proto)


if __name__ == "__main__":
    unittest.main()
