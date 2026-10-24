"""SPEC-2: four places where the guard or the kernel failed open. An edit whose new text the guard cannot read, a
`git config` command that renames a section into a signing or include key, a failed `git config --list`, and an empty
list given to `series`."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from unittest import mock

from helpers import TEST_APPROVER, RepoTemplateCase, git, make_repo

from aidd.guard import dialects, edit_check, ref_writes
from aidd.kernel import git as kernel_git
from aidd.kernel import text

CONFIG = ".aidd/config.yaml"


@unittest.skipUnless(shutil.which("git"), "git is required")
class UnreadableEditTests(RepoTemplateCase):
    """On an explore branch the guard holds no edit, but an agent never loosens who must approve. That holds for a
    harness whose edit event does not carry the text it writes."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", approvers=[TEST_APPROVER])
        git(root, "branch", "explore/cache")

    def setUp(self):
        super().setUp()
        from aidd import workitems

        workitems.record_local_approval(workitems.explore_said_line("explore/cache"), str(self.root))  # the person started it
        git(self.root, "switch", "-q", "explore/cache")
        self.target = str(self.root / CONFIG)

    def antigravity_event(self):
        raw = {
            "conversationId": "c",
            "workspacePaths": [str(self.root)],
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": self.target, "TargetContent": "profile: team", "ReplacementContent": "profile: solo"},
            },
        }
        return dialects.Antigravity().normalize(raw)

    def test_a_config_edit_with_no_readable_text_is_denied_on_a_explore_branch(self):
        for event in (self.antigravity_event(), {"tool_name": "Edit", "tool_input": {"file_path": self.target}}):
            with self.subTest(event=event["tool_name"]):
                decision, why = edit_check.check_agent_edit(str(self.root), CONFIG, event)
                self.assertEqual(decision, "deny", why)

    def test_a_readable_edit_that_keeps_the_profile_is_still_allowed(self):
        event = {"tool_name": "Edit", "tool_input": {"file_path": self.target, "old_string": "profile: team", "new_string": "profile: team"}}
        self.assertEqual(edit_check.check_agent_edit(str(self.root), CONFIG, event)[0], "allow")

    def test_an_unreadable_edit_of_an_ordinary_file_is_still_allowed_there(self):
        event = {"tool_name": "Edit", "tool_input": {"file_path": str(self.root / "notes.md")}}
        self.assertEqual(edit_check.check_agent_edit(str(self.root), "notes.md", event)[0], "allow")


class SigningConfigTests(unittest.TestCase):
    """A `git config` command never reaches a signing or include key by renaming a section into it."""

    def test_renaming_a_section_into_a_signing_key_is_denied(self):
        for rest in (
            ["--rename-section", "temp", "gpg.ssh"],
            ["rename-section", "temp", "gpg.ssh"],
            ["--rename-section", "gpg.ssh", "temp"],
            ["--rename-section", "temp", "include"],
            ["rename-section", "temp", "include"],
        ):
            with self.subTest(rest=rest):
                self.assertIsNotNone(ref_writes.signing_config_denial(rest))

    def test_turning_signing_off_is_denied(self):
        for key in ("commit.gpgsign", "tag.gpgsign", "push.gpgsign", "Commit.GpgSign"):
            with self.subTest(key=key):
                self.assertIsNotNone(ref_writes.signing_config_denial([key, "false"]))

    def test_other_keys_and_other_renames_stay_allowed(self):
        for rest in (["user.name", "Ada"], ["--rename-section", "old", "new"], ["--get", "commit.gpgsign"], ["commit.template", "msg.txt"]):
            with self.subTest(rest=rest):
                self.assertIsNone(ref_writes.signing_config_denial(rest))


class FailedConfigReadTests(unittest.TestCase):
    """A `git config --list` that fails is an error the guard denies on, never an empty list of overrides."""

    def test_a_non_zero_exit_raises(self):
        failed = subprocess.CompletedProcess(args=["git"], returncode=128, stdout=b"", stderr=b"fatal: bad config line 3 in file .git/config")
        with mock.patch("subprocess.run", return_value=failed):
            with self.assertRaises(kernel_git.GitError):
                kernel_git._system_overrides("git", ".", {})

    def test_a_zero_exit_with_no_entries_keeps_the_hardened_overrides(self):
        ok = subprocess.CompletedProcess(args=["git"], returncode=0, stdout=b"", stderr=b"")
        with mock.patch("subprocess.run", return_value=ok):
            self.assertEqual(kernel_git._system_overrides("git", ".", {}), list(kernel_git._HARDENED))


class SeriesTests(unittest.TestCase):
    def test_an_empty_list_is_an_empty_phrase(self):
        self.assertEqual(text.series([], "and"), "")

    def test_the_other_lengths_read_as_before(self):
        self.assertEqual(text.series(["a"], "and"), "a")
        self.assertEqual(text.series(["a", "b"], "or"), "a or b")
        self.assertEqual(text.series(["a", "b", "c"], "and"), "a, b, and c")


if __name__ == "__main__":
    unittest.main()
