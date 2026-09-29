"""The shell and MCP guard against the ways around it: commands shlex cannot read, Windows program names and
PowerShell escapes, MCP tool names in any casing style, and a crash of the hook under AIDD_HOOK_FAIL_CLOSED=1."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo

from aidd import guard


def _fail_closed(on: bool):
    env = {k: v for k, v in os.environ.items() if k != guard.FAIL_CLOSED_ENV}
    if on:
        env[guard.FAIL_CLOSED_ENV] = "1"
    return mock.patch.dict(os.environ, env, clear=True)


class UnparseableShellTests(unittest.TestCase):
    """bash runs each of these, so the check must not take "shlex cannot read it" for "nothing to deny"."""

    def test_ansi_c_strings_and_here_documents_do_not_hide_a_merge_or_an_approval(self):
        for cmd in (
            "echo $'it\\'s'; gh pr merge 3 --squash",
            "cat <<EOF\nit's done\nEOF\ngh pr merge 3",
            "echo $'don\\'t' && gh pr review 3 --approve",
            "echo $'x\\'' ; python3 -m aidd approve merge",
            "bash -c $'gh pr merge 3 \\'x\\''",
            "bash <<EOF\nit's\ngh pr merge 3\nEOF",
            "echo 'x ; gh pr merge 3",
            'echo "x ; aidd approve merge',
            "echo 'x ; gh api -X PUT repos/o/r/pulls/3/merge",
            "echo 'x ; git push --force origin main",
            "echo 'x ; glab mr merge 3",
        ):
            with self.subTest(cmd=cmd), _fail_closed(False):
                why = guard.forbidden_action(cmd)
                self.assertIsNotNone(why, cmd)
                self.assertNotEqual(guard.reason_code(why or ""), "other", cmd)

    def test_an_unparseable_command_with_nothing_to_deny_is_allowed_unless_fail_closed(self):
        for cmd in ("echo 'unbalanced", 'printf "%s x'):
            with self.subTest(cmd=cmd):
                with _fail_closed(False):
                    self.assertIsNone(guard.forbidden_action(cmd))
                with _fail_closed(True):
                    why = guard.forbidden_action(cmd)
                    self.assertIsNotNone(why)
                    self.assertEqual(guard.reason_code(why or ""), "shell_unparsed")

    def test_readable_ansi_c_strings_and_here_documents_stay_allowed_even_fail_closed(self):
        for cmd in (
            "echo $'it\\'s'; ls",
            "git commit -F - <<EOF\ndon't run gh pr merge 3 yourself\nEOF",
            "cat <<'EOF' > notes.txt\nit's fine\nEOF\necho ok",
            "cat <<-EOF\n\tit's fine\n\tEOF",
        ):
            with self.subTest(cmd=cmd), _fail_closed(True):
                self.assertIsNone(guard.forbidden_action(cmd), cmd)


@unittest.skipUnless(shutil.which("git"), "git is required")
class FailClosedHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve() / "repo"
        make_repo(cls.root, "team")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hook(self, payload: str) -> tuple[int, str]:
        out = io.StringIO()
        code = guard.pre_edit_hook(io.StringIO(payload), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else "allow"
        return code, decision

    def bash(self, command: str) -> str:
        return json.dumps({"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}})

    def test_the_hook_denies_the_repro_commands(self):
        for cmd in ("echo $'it\\'s'; gh pr merge 3 --squash", "cat <<EOF\nit's done\nEOF\ngh pr merge 3", "echo $'x\\'' ; python3 -m aidd approve merge"):
            with self.subTest(cmd=cmd), _fail_closed(False):
                self.assertEqual(self.hook(self.bash(cmd)), (0, "deny"))

    def test_a_crash_of_the_guard_denies_under_fail_closed_and_allows_otherwise(self):
        with mock.patch.object(guard, "_pre_edit", side_effect=RuntimeError("boom")):
            with _fail_closed(False):
                self.assertEqual(self.hook(self.bash("ls")), (0, "allow"))
            with _fail_closed(True):
                self.assertEqual(self.hook(self.bash("ls")), (0, "deny"))

    def test_an_unreadable_event_denies_under_fail_closed(self):
        for payload in ("{not json", "[1, 2]"):
            with self.subTest(payload=payload):
                with _fail_closed(False):
                    self.assertEqual(self.hook(payload), (0, "allow"))
                with _fail_closed(True):
                    self.assertEqual(self.hook(payload), (0, "deny"))

    def test_powershell_backtick_escapes_are_undone(self):
        for cmd in ("gh pr mer`ge 3", "gh pr review 3 --app`rove", "g`h pr merge 3"):
            with self.subTest(cmd=cmd), _fail_closed(False):
                ps = json.dumps({"tool_name": "PowerShell", "cwd": str(self.root), "tool_input": {"command": cmd}})
                self.assertEqual(self.hook(ps), (0, "deny"))


class WindowsProgramNameTests(unittest.TestCase):
    def test_exe_names_in_any_case_are_the_program(self):
        for cmd in (
            "gh.exe pr merge 3",
            "GH.EXE pr merge 3",
            "Gh pr merge 3",
            "aidd.exe approve merge",
            "aidd.cmd ship",
            "glab.exe mr merge 3",
            "git.exe push --force origin main",
            "GIT.EXE push -f origin HEAD:main",
            "gh.exe api -X PUT repos/o/r/pulls/3/merge",
            "gh.exe pr review 3 --approve",
            "'C:\\Program Files\\GitHub CLI\\gh.exe' pr merge 3",
            "bash.exe -c 'gh pr merge 3'",
            "pwsh -Command gh pr merge 3",
        ):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(guard.forbidden_action(cmd), cmd)

    def test_powershell_backticks_through_forbidden_action(self):
        self.assertIsNone(guard.forbidden_action("gh pr mer`ge 3"))
        self.assertIsNotNone(guard.forbidden_action("gh pr mer`ge 3", powershell=True))
        self.assertIsNotNone(guard.forbidden_action("gh pr merge `\n 3", powershell=True))

    def test_ordinary_windows_commands_stay_allowed(self):
        for cmd in ("gh.exe pr view 3", "git.exe push origin feature", "aidd.exe next", "GH.EXE api repos/o/r/pulls/3/merge"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(guard.forbidden_action(cmd), cmd)


class McpToolNameTests(unittest.TestCase):
    def verdict(self, name: str, tool_input: dict | None = None) -> str:
        return guard.check_mcp_tool(name, tool_input or {})[0]

    def test_merging_or_approving_in_any_naming_style_is_denied(self):
        for name, tool_input in (
            ("mcp__bb__bitbucket_merge_pull_request", {}),
            ("mcp__gl__gitlab_merge_merge_request", {}),
            ("mcp__gh__github_merge_pull_request", {}),
            ("mcp__gl__gitlab_approve_merge_request", {}),
            ("mcp__ado__repo_complete_pull_request", {}),
            ("mcp__gh__pull_request_merge", {}),
            ("mcp__x__squash_merge_pull_request", {}),
            ("mcp__x__mergePullRequest", {}),
            ("mcp__x__merge-pull-request", {}),
            ("mcp__x__approvePullRequest", {}),
            ("mcp__x__acceptMergeRequest", {}),
            ("mcp__x__enableAutoMerge", {}),
            ("mcp__x__createPullRequestReview", {"event": "APPROVE"}),
            ("mcp__x__create-pull-request-review", {"event": "APPROVE"}),
            ("mcp__x__createCommitStatus", {"state": "success", "context": "aidd/gate"}),
            ("mcp__gh__create_commit_status", {}),
            ("mcp__gh__github_create_status", {}),
            ("mcp__gh__commitStatusCreate", {}),
        ):
            with self.subTest(name=name):
                self.assertEqual(self.verdict(name, tool_input), "deny")

    def test_reading_and_creating_pull_or_merge_requests_is_allowed(self):
        for name, tool_input in (
            ("mcp__github__get_pull_request", {}),
            ("mcp__gitlab__list_merge_requests", {}),
            ("mcp__gitlab__getMergeRequestApprovals", {}),
            ("mcp__gitlab__get-merge-request", {}),
            ("mcp__gitlab__create_merge_request", {"title": "x"}),
            ("mcp__gitlab__update_merge_request", {"title": "x"}),
            ("mcp__gitlab__createMergeRequestNote", {"body": "see line 3"}),
            ("mcp__github__create_pull_request", {"title": "x"}),
            ("mcp__github__createPullRequestReview", {"event": "COMMENT"}),
            ("mcp__github__getCommitStatus", {}),
            ("mcp__github__check_mergeability", {}),
            ("mcp__github__is_merged", {}),
            ("mcp__todo__complete_task", {}),
        ):
            with self.subTest(name=name):
                self.assertEqual(self.verdict(name, tool_input), "allow")


if __name__ == "__main__":
    unittest.main()
