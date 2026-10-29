"""The shell and MCP guard against the ways around it: commands shlex cannot read, Windows program names and
PowerShell escapes, MCP tool names in any casing style, and a crash of the hook under AIDD_HOOK_FAIL_CLOSED=1."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo

from aidd.guard import pre_tool
from aidd.guard import command_check
from aidd.guard import denial_log
from aidd.guard import approval_commands
from aidd.guard import mcp_tools
from aidd.guard import shell_parser
from aidd.guard import edit_check
from aidd.guard import git_commands


def _fail_closed(on: bool):
    env = {k: v for k, v in os.environ.items() if k != approval_commands.FAIL_CLOSED_ENV}
    if on:
        env[approval_commands.FAIL_CLOSED_ENV] = "1"
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
                why = approval_commands.forbidden_action(cmd)
                self.assertIsNotNone(why, cmd)
                self.assertNotEqual(denial_log.reason_code(why or ""), "other", cmd)

    def test_an_unparseable_command_with_nothing_to_deny_is_allowed_unless_fail_closed(self):
        for cmd in ("echo 'unbalanced", 'printf "%s x'):
            with self.subTest(cmd=cmd):
                with _fail_closed(False):
                    self.assertIsNone(approval_commands.forbidden_action(cmd))
                with _fail_closed(True):
                    why = approval_commands.forbidden_action(cmd)
                    self.assertIsNotNone(why)
                    self.assertEqual(denial_log.reason_code(why or ""), "shell_unparsed")

    def test_readable_ansi_c_strings_and_here_documents_stay_allowed_even_fail_closed(self):
        for cmd in (
            "echo $'it\\'s'; ls",
            "git commit -F - <<EOF\ndon't run gh pr merge 3 yourself\nEOF",
            "cat <<'EOF' > notes.txt\nit's fine\nEOF\necho ok",
            "cat <<-EOF\n\tit's fine\n\tEOF",
        ):
            with self.subTest(cmd=cmd), _fail_closed(True):
                self.assertIsNone(approval_commands.forbidden_action(cmd), cmd)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ReadOnlyFormsTests(unittest.TestCase):
    """What only reads is allowed (help, a preview, listing the decision records), and so is a mention where the gate never
    reads an approval; what records or posts one stays denied (loop friction review, T5)."""

    def test_reading_and_mentioning_are_allowed(self):
        for command in (
            "aidd approve --help",
            "aidd approve spec --help",
            "aidd land -h",
            "aidd approve spec SPEC-1 --show",
            "aidd approve merge --show",
            "aidd land --show",
            "git for-each-ref refs/aidd/decisions",
            "git rev-parse --verify refs/aidd/decisions",
            'git commit -m "docs: say how Approvers post /aidd approve-spec"',
            'git commit -m "the loop switch is a record on refs/aidd/decisions"',  # it names the ref, and writes no record
            'gh pr create --title "Approvals" --body "an Approver posts /aidd approve-spec on this PR"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command))

    def test_the_persons_typed_words_are_never_typed_for_them(self):
        for command in (
            'tmux send-keys -t 0 "approve SPEC-1" Enter',
            'xdotool type "ship it"',
            'orca terminal send --text "approve all"',
            # Fail closed: a terminal edits what it receives, so a decision word anywhere in typed text is denied.
            'tmux send-keys -t 0 "xapprove SPEC-1" Home Delete Enter',
            'tmux send-keys -t 0 "please approve the plan" Enter',
            # Key codes hide the text: hex, and key-name sequences.
            "tmux send-keys -t 0 -H 61 70 70 72 6f 76 65",
            "xdotool key a p p r o v e space S P E C minus 1 Return",
            # A message one agent hands another passes for a decision when the whole of it reads as one.
            'orca orchestration send --to lead --text "approve SPEC-1"',
            'orca orchestration send --to lead --text "I approve SPEC-1 and SPEC-4, please"',  # the prompt hook's own reading
            # Any tmux key name but Enter, Space, and Tab edits what the terminal receives.
            "tmux send-keys -t 0 xship ^A Delete Enter",
            "tmux send-keys -t 0 F1",
            "tmux send-keys -t 0 S-Left",
            "tmux send-keys -t 0 xship home delete enter",  # tmux reads key names in any case
            'orca orchestration send --to lead --text="approve SPEC-1"',
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command))
        for command in (
            'tmux send-keys -t 0 "run the tests again" Enter',
            "tmux send-keys -t 0 make Space test C-m",
            'xdotool type "the build is green"',
            'orca orchestration send --to lead --text "loop on"',  # an ordinary message: no switch reads it
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command))

    def test_text_the_guard_cannot_read_is_never_typed_into_another_terminal(self):
        """Text a sender takes from a file, a buffer, stdin, or an expansion: the guard sees `$(cat f)`, never the words
        the receiver gets, so it fails closed on every such sender (security review of the branch, 2026-10-16)."""
        for command in (
            'tmux send-keys -t 0 "$(cat /tmp/p)" Enter',
            "tmux send-keys -t 0 `cat /tmp/p` Enter",
            'tmux send-keys -t 0 "$WORDS" Enter',
            'tmux send-keys -t 0 "${WORDS}" Enter',
            "tmux load-buffer /tmp/p",
            "tmux paste-buffer -t 0",
            "tmux pasteb -t 0",
            "xdotool type --file /tmp/p",
            "xdotool type --file -",
            'xdotool type "$(cat /tmp/p)"',
            "cat /tmp/p | xargs tmux send-keys -t 0",
            'orca orchestration send --to lead --text "$(cat /tmp/p)"',
            'orca terminal send --text "$(cat /tmp/p)"',
            # Globs and braces put file names into the text (`cd /tmp && ... appro*`).
            "tmux send-keys -t 0 appro* Enter",
            "tmux send-keys -t 0 appro? Enter",
            "tmux send-keys -t 0 {ap,}prove Enter",
            "xdotool type appro[v]e",
            # Options that read a file, in any spelling.
            "xdotool type -f /tmp/p",
            "xdotool type --fi /tmp/p",
            "ydotool type --file /tmp/p",
            # tmux takes any unambiguous prefix of a command.
            'tmux send-ke -t 0 "approve SPEC-1" Enter',
            "tmux paste -t 0",
            "tmux load /tmp/p",
            "tmux source-file /tmp/p",
            "tmux source /tmp/p",
            "tmux pipe-pane -t 0 -I 'cat /tmp/p'",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command))
        # Plain text still goes, and an expansion outside a sender is none of this rule's business.
        for command in ('tmux send-keys -t 0 "make test" Enter', 'echo "$HOME"', 'git commit -m "$(cat msg.txt)"'):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command))

    def test_tmux_is_an_allowlist_read_only_commands_and_plain_send_keys(self):
        for command in (
            "tmux if-shell true 'send-keys -t 0 x'",
            "tmux set-hook -g pane-focus-in 'send-keys -t 0 x'",
            "tmux bind-key x send-keys -t 0 y",
            "tmux command-prompt -I x",
            "tmux confirm-before 'send-keys -t 0 x'",
            "tmux display-menu -T x",
            "tmux display-message -I -t 0",
            "tmux new-session -d 'cat /tmp/p | tmux load-buffer -'",  # the command it runs, read by the same rules
            "tmux run-shell 'tmux paste-buffer -t 0'",
            "tmux new-window 'aidd approve all'",
            "tmux -f /tmp/conf ls",
            "tmux -c 'echo hi'",
            "tmux send-keys -t 0 hello \\; if-shell true 'send-keys -t 0 x'",
            "tmux send-keys -t 0 hello ';' if-shell true 'send-keys -t 0 x'",  # a quoted `;` is tmux's separator too
            "tmux new-window aidd approve all",  # tmux joins the words into the command it runs
            "tmux new-window -n w aidd approve all",
            "tmux new-window git push --force origin main",  # the words it joins, read as the agent's own command
            "tmux new-window -n w gh pr merge 7",
            "tmux send-keys -X copy-pipe 'aidd approve all'",  # copy-mode commands
            "tmux send-keys -K -t 0 x",
            "tmux send-keys -M -t 0",
            "tmux sen -t 0 hello",  # an ambiguous prefix (send-keys, send-prefix): fail closed
            "tmux zzz",  # an unknown command
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command))
        for command in (
            "tmux ls",
            "tmux list-panes -a",
            "tmux capture-pane -p -t 0",
            "tmux show-options -g",
            "tmux has -t build",
            "tmux send-keys -t 0 'make test' Enter",
            "tmux new-session -d -s build 'make test'",  # it runs a command the guard reads, and finds nothing
            "tmux run-shell 'echo hi'",
            "find . -name '*.pyc' -exec rm {} \\;",  # `\;` is a word, as bash reads it
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command))

    def test_what_xargs_parallel_and_find_run_is_read_as_the_agents_own_command(self):
        """A merge, an approval, or typed text that xargs, parallel, or find -exec runs is the agent's own, for every
        session (indirect_runs). The words they fill in are read as names only the shell resolves."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = str(make_repo(Path(tmp.name) / "repo", "team"))
        for command in (
            "echo 12 | xargs gh pr merge",
            "echo 12 | xargs -n1 gh pr review --approve",
            "find . -maxdepth 0 -exec gh pr merge 12 \\;",
            "find . -maxdepth 0 -execdir glab mr merge 12 \\;",
            "find . -maxdepth 0 -exec tmux send-keys -t 0 'approve SPEC-1' Enter \\;",
            "echo spec | xargs -I S sh -c 'aidd approve S'",
            "echo approve spec | xargs aidd",
            "find . -maxdepth 0 -exec aidd land \\;",
            "echo 12 | parallel gh pr merge {}",
            "echo merge | xargs -I V gh pr V 12",
            "echo main | xargs git push --force origin",
            "echo x | xargs git branch -D",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, root))
        for command in (
            "git ls-files | xargs wc -l",
            "git ls-files | xargs git add",
            "find . -name '*.orig' -exec git rm -q {} \\;",
            "git ls-files | xargs git log --oneline -1 --",
            # A folder named aidd is where find starts, never a program: find runs one only after -exec and its kin.
            'find /home/me/.local/share/uv/tools/aidd -path "*skills/aidd/SKILL.md"',
            "find /opt/aidd -name '*.md' -print",
            "find . -name aidd -type d",
            'aidd eval hooks --harness antigravity --agent-command "agy -p"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command, root))
        for command in (
            "find /opt/aidd -maxdepth 0 -exec aidd approve spec S-1 \\;",
            "find ~/tools/aidd -okdir aidd land \\;",
            "find /opt/aidd -name $X aidd approve spec S-1",  # a word the shell may turn into an action
            "fd -Hx aidd approve spec S-1",  # fd's actions come in option clusters: the backstop reads them
            # A quoted expansion does not split, but may be `-exec`: the words from it on are read as a command.
            'A=-exec; find . -maxdepth 0 "$A" aidd approve spec S-1 \\;',
            'find . -maxdepth 0 "$(printf %s -exec)" aidd land \\;',
            'A=-exec; find . -maxdepth 0 "$A" git push --force origin main \\;',
            # The command `aidd eval` starts is the agent's own.
            'aidd eval hooks --harness claude-code --agent-command "gh pr merge 12"',
            "aidd eval roles --agent-command='aidd approve spec S-1'",
            'aidd eval hooks --agent-command "agy -p" --agent-command "gh pr merge 12"',  # argparse takes the last
            'aidd eval hooks --agent-comm "gh pr merge 12"',  # and an abbreviation
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, root))

    def test_the_parsers_own_marker_in_a_command_fails_closed(self):
        # A command that holds the character the parser marks escaped punctuation with: never a separator hidden in a word.
        command = "echo ; aidd approve all"
        self.assertIsNotNone(approval_commands.forbidden_action(command))
        with self.assertRaises(ValueError):
            shell_parser.shell_tokens(command)

    def test_a_message_may_name_the_approvals_ref_and_nothing_else_may(self):
        self.assertIsNone(approval_commands.forbidden_action('git commit -m "records on refs/aidd/decisions"'))
        for command in (
            "git -c core.editor=\"sh -c 'git update-ref refs/aidd/decisions 0123'\" commit",
            "GIT_EDITOR='git update-ref refs/aidd/decisions 0123' git commit",
            'git commit --author="refs/aidd/decisions <a@b.c>" -m x',
            'env X=refs/aidd/decisions git commit -m "a message"',  # an assignment is never the message
            'git commit -b "refs/aidd/decisions"',  # -b is not git's message flag
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command))

    def test_recording_or_posting_an_approval_stays_denied(self):
        for command in (
            "aidd approve spec SPEC-1",
            "aidd approve spec SPEC-1 --confirmed 0123",
            "aidd approve spec SPEC-1 --show --confirmed 0123",
            "aidd approve merge --confirmed 0123",
            "aidd land",
            "aidd land --confirmed 0123",
            'gh pr comment 7 --body "/aidd approve-spec SPEC-1 0123 abc"',
            'gh pr create --body "/aidd approve-spec SPEC-1 0123 abc"',  # a line that reads as an approval, anywhere
            'git commit -m "/aidd approve SPEC-220 abc"',
            'git commit -m x && gh pr comment 7 --body "see /aidd approve"',
            "git update-ref refs/aidd/decisions 0123",
            'git commit -m "Aidd-Merge-Approval: 0123"',  # text that reads as a record
            'git commit -m "see refs/aidd/decisions" && git update-ref refs/aidd/decisions 0123',
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command))


class IndirectCommandsAndReservedWordsTests(unittest.TestCase):
    """What a reserved word, xargs or find, a variable, or the input hides from the checks (the defensive review of the
    guard, 2026-10-22): each is read, and what the guard cannot read fails closed, for every session."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = str(make_repo(Path(tmp.name) / "repo", "team"))

    def test_runners_reserved_words_and_input_options_fail_closed(self):
        root = self.root
        for command in (
            "if true; then gh pr merge 3; fi",
            "{ gh pr merge 3; }",
            "for f in a; do git checkout explore/topic; done",
            "gfind . -maxdepth 0 -exec gh pr merge 3 \\;",
            "bfs . -exec gh pr merge 3 \\;",
            "fd -x gh pr merge 3",
            "echo 3 | busybox xargs gh pr merge",
            "echo 3 | gxargs gh pr merge",
            "echo 3 | sem gh pr merge",
            "X=xargs; echo 3 | $X gh pr merge",
            "X=gh; $X pr merge 3",
            "echo gh | xargs -I C C pr merge 3",
            "echo gh | parallel {} pr merge 3",
            "parallel ::: 'gh pr merge 3'",
            "echo gh pr merge 3 | xargs env",
            "echo --approve | xargs gh pr review 3",
            "echo --confirmed=abc | xargs aidd approve merge --show",
            "echo -f | xargs git branch main feat",
            "echo -m | xargs git branch explore/new",
            "git branch -qf main feat",
            "git switch -- explore/topic",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, root))
        main, role = {"tool_name": "Bash"}, {"tool_name": "Bash", "agent_type": "aidd-team:developer"}
        for event in (main, role):
            for command in (
                "find . -delete",
                "find .git/refs -delete",
                "find . -fprint .aidd/config.yaml",
                "if true; then rm .aidd/config.yaml; fi",
                "gfind .aidd -exec rm {} \\;",
                "echo .aidd/config.yaml | busybox xargs rm",
            ):
                with self.subTest(command=command, event=event):
                    self.assertEqual(command_check.check_command(root, root, command, event)[0], "deny")
        for command in ("echo .aidd/config.yaml | xargs rm", "find . -maxdepth 0 -exec tee .aidd/config.yaml \\;"):
            self.assertEqual(command_check.check_command(root, root, command, main)[0], "deny", command)

    def test_more_forms_of_each_fail_closed(self):
        for command in (
            "! gh pr merge 3",
            "coproc gh pr merge 3",
            "function f { gh pr merge 3; }",
            "while gh pr merge 3; do :; done",
            "G=git; $G checkout explore/topic",
            "echo gh | xargs -i{} {} pr merge 3",
            "echo gh | xargs -J % % pr merge 3",
            "echo gh | xargs --replace {} pr merge 3",
            *(f"echo gh pr merge 3 | xargs {w}" for w in ("nice", "timeout 5", "nohup", "sudo", "command", "xargs")),
            "echo '-c gh' | xargs sh",
            "X=echo; for i in 1 2; do $X pr merge 3; X=gh; done",  # a later value reaches the next pass
            "X=echo; false && X=gh; $X pr merge 3",  # an assignment that may not run
            "X=echo; read X; $X pr merge 3",  # a value only the input gives
            "git branch --forc main feat",
            "git branch --mov explore/x",
            "git branch -m main x",
            "script -qc 'gh pr merge 3' /dev/null",
            "script -q /dev/null gh pr merge 3",
            "watch -n1 gh pr merge 3",
            "flock /tmp/l gh pr merge 3",
            "flock /tmp/l -c 'gh pr merge 3'",
            "ssh host gh pr merge 3",
            "fdfind -X git checkout explore/topic",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, self.root))

    def test_what_the_guard_reads_whole_stays_allowed(self):
        for command in (
            "git ls-files | xargs wc -l",
            'grep -r "gh pr merge" docs/',
            'echo "git push"',
            "echo git push",
            "brew install tmux git",  # tmux refuses a command it lacks, so it runs nothing
            "parallel gzip {} ::: a b",
            'for f in *.py; do git add "$f"; done',
            "aidd approve merge --show",
            "gh pr review 3 --comment -b 'looks good'",
            "git branch --list 'feat*'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command, self.root))
        main = {"tool_name": "Bash"}
        for command in (
            "find . -name cache.db -exec rm {} \\;",
            "find . -name cache.db -delete",
            'git add "$f"',
            'git restore --staged -- "$f"',  # after `--` a word is a path, never an option
            "git ls-files | xargs wc -l",
        ):
            with self.subTest(command=command):
                self.assertEqual(command_check.check_command(self.root, self.root, command, main)[0], "allow")

    def test_the_documented_over_denials_of_failing_closed(self):
        """SECURITY.md's known limits: the guard resolves no variable for a program, so this is denied though it writes
        nothing protected. It has a plain form the guard reads."""
        self.assertIsNotNone(approval_commands.forbidden_action("G=git; $G status", self.root))

    def test_quoting_read_exactly_frees_the_plain_forms(self):
        """The reader keeps each word's quoting (shell_words): a quoted find pattern is find's own, a quoted text is
        one value, and a loop over literal words is judged per value."""
        main, role = {"tool_name": "Bash"}, {"tool_name": "Bash", "agent_type": "aidd-team:developer"}
        for command in ("gh pr review 3 --comment -b 'why?'", 'gh pr review 3 --comment --body "$MSG"', "gh pr review 3 -c --body='a b?'"):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command, self.root))
        for command, event in (
            ("find . -name '*.pyc' -exec rm {} \\;", main),
            ("find . -name '*.pyc' -delete", main),
            ('for f in a b; do git checkout --ours -- "$f"; done', main),
            ("find src -name '*.py' -exec grep -n x {} +", role),
        ):
            with self.subTest(command=command):
                self.assertEqual(command_check.check_command(self.root, self.root, command, event)[0], "allow")

    def test_find_bounds_its_input_only_to_names_no_protected_file_has(self):
        main = {"tool_name": "Bash"}
        for command in (
            "find . -name config.yaml -exec rm {} \\;",
            "find .aidd/config.yaml -name config.yaml -exec rm {} \\;",
            "find . -name HEAD -exec cp /tmp/x {} \\;",
            "find . -name lease.json -exec rm {} \\;",  # aidd's lease in the git directory
            "find . -name cache.db -o -name config.yaml -exec rm {} \\;",
            "find -L . -name cache.db -exec rm {} \\;",
            "find . -name cache.db -execdir rm {} \\;",
            "find .git -name cache.db -delete",
            "echo x | xargs sh -c 'cd .aidd && rm config.yaml'",
            "X=rm; $X .aidd/config.yaml",
            'git restore --staged --worktree "$f"',
            "for f in a; do sh -c 'for f in .aidd/config.yaml; do rm $f; done'; done",
            'for f in a; do f=.aidd/config.yaml; rm "$f"; done',
            'for f in "a .aidd/config.yaml"; do rm $f; done',
            'for f in .aidd/*.yaml; do rm "$f"; done',
            "for f in .aidd/config.yaml; do rm $f; done",
        ):
            with self.subTest(command=command):
                self.assertEqual(command_check.check_command(self.root, self.root, command, main)[0], "deny")


class ReviewOfTheReadingTests(unittest.TestCase):
    """Fail-open readings the security reviews of the reading above found (2026-10-22): each case passed once. The
    remedy is to fail closed: no loop is unrolled, no variable resolved, and no quoting proven."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = str(make_repo(Path(tmp.name) / "repo", "team"))
        self.main = {"tool_name": "Bash"}

    def denied(self, command: str, event: dict | None = None) -> bool:
        return command_check.check_command(self.root, self.root, command, event or self.main)[0] == "deny"

    def test_a_program_a_variable_names_is_never_resolved(self):
        eight = "; ".join(f"X=a{i}" for i in range(1, 9))
        for command in (f"{eight}; X=gh; $X pr merge 3", "X=gh; $X pr merge 3", "printf -v X gh; $X pr merge 3", "X=git; $X status"):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, self.root))

    def test_a_loop_variable_is_put_in_only_where_nothing_else_sets_it(self):
        for command in (
            "for f in a; do git checkout explore/topic; done",
            "trap 'f=explore/topic' DEBUG; for f in main; do git checkout \"$f\"; done",
            'g() { f=explore/topic; }; for f in main; do g; git checkout "$f"; done',
            "sh -c 'for B in main; do git branch -f \"$B\" feat; done'",
            "eval 'for B in main; do git branch -f \"$B\" feat; done'",
            "declare -x B=main; git branch -f $B x",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, self.root))
        for command in (
            'for f in a .aidd/config.yaml; do git checkout --ours -- "$f"; done',
            'g() { f=.aidd/config.yaml; }; for f in a; do g; rm "$f"; done',
            'for f in a; do printf -v f %s .aidd/config.yaml; rm "$f"; done',
        ):
            with self.subTest(command=command):
                self.assertTrue(self.denied(command))

    def test_a_branch_word_only_the_shell_names_may_split_into_an_option_and_a_name(self):
        command = 'B="-f main"; git branch $B feat'
        self.assertIsNotNone(git_commands.base_branch_denial(shell_parser.simple_commands(command), self.root), command)
        self.assertIsNotNone(approval_commands.forbidden_action(command, self.root))

    def test_restore_is_index_only_only_when_its_options_read_exactly(self):
        for command in (
            "git restore --staged --no-staged -- .aidd/config.yaml",
            "git restore -S --wo -- .aidd/config.yaml",
            "git restore --staged --work -- .aidd/config.yaml",
            "git restore --no-worktree --staged --worktree -- .aidd/config.yaml",
            "git restore --staged $OPTS -- .aidd/config.yaml",
            "git restore --staged --s -- .aidd/config.yaml",  # ambiguous: --staged, --source
            "git restore --staged --bogus -- .aidd/config.yaml",
            'git restore --staged "$f"',  # before `--`, the word may be `--worktree`
            "git restore --staged -SW -- .aidd/config.yaml",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.denied(command))
        for command in ("git restore --staged -- .aidd/config.yaml", "git restore --worktree --no-worktree -S -- x", "git restore -qS -s HEAD -- x"):
            with self.subTest(command=command):
                self.assertFalse(self.denied(command))

    def test_a_find_pattern_with_a_glob_is_never_one_word(self):
        role = {"tool_name": "Bash", "agent_type": "aidd-team:developer"}
        for command in (
            "touch -- -delete; find . -name * -exec cat {} +",
            "find . -name * -exec cat {} +",
            "echo '*'; find . -name * -exec cat {} +",  # a quoted copy elsewhere vouches for nothing
        ):
            with self.subTest(command=command):
                self.assertTrue(self.denied(command, role))
                self.assertTrue(self.denied(command), "the main session too: it may be -delete")

    def test_a_review_word_with_a_glob_or_an_expansion_counts_quoted_or_not(self):
        for command in (
            "gh pr review 3 -b *",
            "gh pr review 3 --body $MSG",
            "gh pr review 3 -R {a,--approve}",
            "echo '*'; gh pr review 3 -b *",  # a quoted copy elsewhere vouches for nothing
            "X=x; gh pr review 3 -b $X",  # a word only a variable names
            "sh -c \"gh pr review 3 -b '*'\"",  # the command a child shell parses again
            "echo x | xargs gh pr review 3 -b",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, self.root))


class GuardLogTests(unittest.TestCase):
    """The guard log: owner-only, one session's denials together, and a long command still told apart (review J11)."""

    def test_the_log_is_owner_only_and_names_the_session_and_a_long_commands_length_and_hash(self):
        from aidd import config

        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "repo")
            long = "echo " + "x" * 300
            denial_log.log_denial(str(root), {"tool_name": "Bash", "tool_input": {"command": long}, "session_id": "s-1"}, "no")
            log = config.guard_log(str(root))
            (entry,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)
            self.assertEqual((entry["session"], entry["command_len"], len(entry["command"])), ("s-1", len(long), 200))
            self.assertEqual(len(entry["command_sha256"]), 16)

    def test_metrics_read_past_a_bad_byte_and_count_what_they_skip(self):
        from aidd.tracking import metrics

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "events.jsonl"
            p.write_bytes(b'{"ts": "2026-10-15T00:00:00Z", "rule": "a"}\n{"ts": "\xff"}\nnot json\n{"ts": "2026-10-15T00:00:01Z"}\n')
            skipped: list[str] = []
            events = metrics.load_events([str(p)], skipped_lines=skipped)
            self.assertEqual(len(events), 2)
            self.assertEqual(skipped, [f"{p}: skipped 2 lines that are not a JSON event"])


class ReasonCodeTests(unittest.TestCase):
    def test_a_shell_write_to_a_decision_file_is_logged_as_unreadable(self):
        reason = (
            "specs/INIT-1.md: this file holds an Initiative's go_no_go, which only a person records; use the Edit or Write tool so the change can be checked"
        )
        self.assertEqual(denial_log.reason_code(reason), "decision_unreadable")


class FailClosedHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve() / "repo"
        make_repo(cls.root, "team", enforce=False)  # an advising team repository; `mode: enforce` fails closed by itself

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hook(self, payload: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.chdir(self.root):  # an event that names no folder is judged in the guard's own, an adopted one here
            code = pre_tool.pre_tool_hook(io.StringIO(payload), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else "allow"
        return code, decision

    def bash(self, command: str) -> str:
        return json.dumps({"tool_name": "Bash", "cwd": str(self.root), "tool_input": {"command": command}})

    def test_the_hook_denies_the_repro_commands(self):
        for cmd in ("echo $'it\\'s'; gh pr merge 3 --squash", "cat <<EOF\nit's done\nEOF\ngh pr merge 3", "echo $'x\\'' ; python3 -m aidd approve merge"):
            with self.subTest(cmd=cmd), _fail_closed(False):
                self.assertEqual(self.hook(self.bash(cmd)), (0, "deny"))

    def test_a_crash_of_the_guard_denies_under_fail_closed_and_allows_otherwise(self):
        with mock.patch.object(pre_tool, "_pre_tool", side_effect=RuntimeError("boom")):
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


class UnloadedConfigTests(unittest.TestCase):
    """A config that is there and valid but did not load on one read: a role, or a fail-closed repository, is denied."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve() / "repo"
        make_repo(cls.root, "team", enforce=False)  # advising: `mode: enforce` is a fail-closed repository (repo_config)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def check(self, role: str | None = None) -> tuple[str, str]:
        from aidd.config import loading

        real, calls = loading.load_file, []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise RuntimeError("busy")
            return real(*args, **kwargs)

        with mock.patch.object(loading, "load_file", side_effect=flaky):
            return edit_check.check_edit(str(self.root), "src/app.py", role)

    def test_an_edit_without_a_role_goes_through_and_says_why(self):
        with _fail_closed(False):
            decision, reason = self.check()
        self.assertEqual(decision, "allow", reason)
        self.assertIn("did not load this time", reason)

    def test_a_role_is_denied_and_told_to_try_again(self):
        with _fail_closed(False):
            decision, reason = self.check("developer")
        self.assertEqual(decision, "deny", reason)
        self.assertIn("Try the edit again", reason)
        self.assertIn("`aidd doctor`", reason)

    def test_a_fail_closed_repository_denies(self):
        with _fail_closed(True):
            decision, reason = self.check()
        self.assertEqual(decision, "deny", reason)


class WindowsProgramNameTests(unittest.TestCase):
    def test_exe_names_in_any_case_are_the_program(self):
        for cmd in (
            "gh.exe pr merge 3",
            "GH.EXE pr merge 3",
            "Gh pr merge 3",
            "aidd.exe approve merge",
            "aidd.cmd land",
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
                self.assertIsNotNone(approval_commands.forbidden_action(cmd), cmd)

    def test_powershell_backticks_through_forbidden_action(self):
        # In bash the backtick starts a substitution the guard cannot read where gh's command goes, so it fails closed too.
        self.assertIsNotNone(approval_commands.forbidden_action("gh pr mer`ge 3"))
        self.assertIsNotNone(approval_commands.forbidden_action("gh pr mer`ge 3", powershell=True))
        self.assertIsNotNone(approval_commands.forbidden_action("gh pr merge `\n 3", powershell=True))

    def test_ordinary_windows_commands_stay_allowed(self):
        for cmd in ("gh.exe pr view 3", "git.exe push origin feature", "aidd.exe next", "GH.EXE api repos/o/r/pulls/3/merge"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(approval_commands.forbidden_action(cmd), cmd)


class McpToolNameTests(unittest.TestCase):
    def verdict(self, name: str, tool_input: dict | None = None) -> str:
        return mcp_tools.check_mcp_tool(name, tool_input or {})[0]

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
