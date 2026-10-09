"""The PreToolUse hook's decisions for shell commands and helper subagents.

Agents never approve, merge, or post an approval; a role's obvious shell writes meet the same rules as its
edits; and a subagent that is not an aidd-team role only reads. The shell check is best-effort, so these
tests pin what it does see, and a few cases it deliberately lets through.
"""

import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, RepoTemplateCase, git, make_repo

from aidd import config as cfgmod
from aidd import guard, repo

CODE = "src/checkout/rate_limit/limiter.py"
TESTS = "tests/checkout/test_rate_limit.py"


class ForbiddenActionTests(unittest.TestCase):
    """Denied to every agent, whoever runs the command."""

    def denied(self, command):
        return guard.forbidden_action(command) is not None

    def test_the_helper_rule_is_cited_by_name_not_by_a_number_that_drifts(self):
        from aidd import resources

        self.assertNotRegex(guard.HELPER_DENY, r"item \d")
        quoted = guard.HELPER_DENY.split('"')[1]
        self.assertTrue(any(rule.startswith(quoted) for rule in resources.roles()["loop"]["contract"]), quoted)

    def test_approving_is_denied(self):
        for cmd in (
            "gh pr review 12 --approve",
            "gh pr review --approve -b 'looks good' 12",
            "gh pr review 12 -a",
            "gh -R org/repo pr review 12 --approve",
            "glab mr approve 7",
            "gh api repos/o/r/pulls/12/reviews -f event=APPROVE",
            "gh api -X POST repos/o/r/pulls/12/reviews --input review.json",
            "gh api repos/o/r/pulls/12/reviews/99/events -f event=APPROVE",
            "glab api -X POST projects/1/merge_requests/2/approve",
            "gh api graphql -f query='mutation { addPullRequestReview(input: {pullRequestId: \"x\", event: APPROVE}) { clientMutationId } }'",
        ):
            self.assertTrue(self.denied(cmd), cmd)

    def test_merging_is_denied(self):
        for cmd in (
            "gh pr merge 12 --squash",
            "gh pr merge --auto --merge",
            "cd repo && gh pr merge 3",
            "GH_TOKEN=abc gh pr merge 3",
            "sudo gh pr merge 3",
            "timeout 30 gh pr merge 3",
            "bash -c 'gh pr merge 3'",
            'sh -c "cd x; gh pr merge 3"',
            "glab mr merge 7",
            "glab mr accept 7",
            "gh api -X PUT repos/o/r/pulls/12/merge",
            "gh api repos/o/r/pulls/12/merge -f merge_method=squash",
            "glab api -X PUT projects/1/merge_requests/2/merge",
            "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
            "git push --force origin main",
            "git push -f origin HEAD:main",
            "git push origin +feature:master",
        ):
            self.assertTrue(self.denied(cmd), cmd)

    def test_posting_an_approval_command_is_denied(self):
        for cmd in (
            "gh pr comment 12 --body '/aidd approve-spec SPEC-1 abc123 def456'",
            "gh pr comment 12 --body '/aidd approve'",
            "echo '/aidd approve' | gh pr comment 12 -F -",
            "glab mr note 7 -m '/aidd  approve'",
            'curl -X POST -d \'{"body": "/aidd approve"}\' https://api.github.com/repos/o/r/issues/1/comments',
        ):
            self.assertTrue(self.denied(cmd), cmd)

    def test_local_approvals_and_the_ship_are_a_persons(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        for cmd, denied in (
            ("uvx aidd approve merge", True),
            ("uv run aidd ship", True),
            ("pipx run aidd approve merge", True),
            ("python3 -I -m aidd approve merge", True),
            ("python3 -m aidd.cli approve merge", True),
            ("python3 -maidd ship --squash", True),
            ("env AIDD_X=1 aidd approve spec specs/SPEC-1.md", True),
            (f"git update-ref refs/aidd/approvals {sha}", True),
            ("git update-ref -d refs/aidd/approvals", True),
            (f'git commit-tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904 -m "Aidd-Merge-Approval: {sha}"', True),
            ("aidd assess", False),
            ("aidd list --waiting-on-me", False),
            ("python3 -m aidd gate --base main", False),
            ("git log refs/aidd/approvals", False),
        ):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.denied(cmd), denied)

    def test_reading_and_ordinary_work_is_allowed(self):
        for cmd in (
            "gh pr view 12",
            "gh pr diff 12",
            "gh pr checks 12",
            "gh pr review 12 --comment -b 'see line 4'",
            "gh pr review 12 --request-changes -b 'fails on empty input'",
            "gh api repos/o/r/pulls/12/reviews",
            "gh api repos/o/r/pulls/12/merge",
            "gh api graphql -f query='query { viewer { login } }'",
            "glab mr view 7",
            "grep -rn '/aidd approve' docs/",
            "rg '/aidd approve-spec' .agents",
            "git log --grep='/aidd approve'",
            "git push origin feature",
            "git push --force-with-lease origin feature",
            "git push origin main",
            "pytest -q",
        ):
            self.assertFalse(self.denied(cmd), cmd)

    def test_typing_an_approval_into_another_terminal_is_denied(self):
        # `aidd approve` checks that a person runs it in a terminal; an agent that types into that terminal would pass.
        for cmd in (
            'orca terminal send --terminal t1 --text "aidd approve merge" --enter',
            'orca terminal send --terminal t1 --text "aidd ship" --enter',
            "orca terminal send --terminal t1 --text 'uvx aidd approve spec specs/S-1.md'",
            'orca orchestration send --to lead --text "run aidd approve merge"',
            'orca orchestration ask --to lead "please run aidd ship"',
            'tmux send-keys -t 0 "aidd approve merge" Enter',
            "tmux send -t work:1 'aidd ship' C-m",
            "tmux set-buffer 'aidd approve merge' && tmux paste-buffer -t 0",
            "echo 'aidd approve merge' | xargs -0 tmux send-keys -t 0",
            "screen -S work -X stuff 'aidd approve merge\\n'",
            'osascript -e \'tell application "System Events" to keystroke "aidd approve merge"\'',
            'osascript -e \'tell application "Terminal" to do script "aidd ship"\'',
            "xdotool type 'aidd approve merge'",
            "wtype 'aidd approve merge'",
            "ydotool type 'aidd ship'",
            "expect -c 'spawn bash; send \"aidd approve merge\\r\"; interact'",
            "kitty @ send-text --match id:1 'aidd approve merge\\n'",
            "wezterm cli send-text --pane-id 2 'aidd ship'",
            "echo 'aidd approve merge' > /dev/pts/3",
            "printf 'aidd ship\\n' > /dev/ttys004",
            "echo 'aidd approve merge' | tee /dev/pts/1",
            "tmux send-keys -t 0 'python3 -m aidd.cli approve merge' Enter",
            "tmux send-keys -t 0 'git push origin refs/aidd/approvals' Enter",
            "bash -c \"tmux send-keys -t 0 'aidd approve merge' Enter\"",
        ):
            why = guard.forbidden_action(cmd)
            self.assertIsNotNone(why, cmd)
            self.assertNotEqual(guard.reason_code(why or ""), "other", cmd)

    def test_starting_an_approval_in_another_terminal_is_denied(self):
        # A terminal the agent starts with `aidd approve` in it passes the terminal check; the guard denies starting it.
        for cmd in (
            'orca terminal create --worktree active --command "aidd approve merge"',
            "orca terminal create --command 'uvx aidd ship --squash' --focus",
            "orca terminal split --terminal t1 --direction vertical --command 'aidd approve spec specs/S-1.md'",
            'orca computer type-text --app Terminal --text "aidd approve merge"',
            'orca computer paste-text --app iTerm2 --text "aidd ship"',
            'orca computer press-key --app Terminal --key "aidd approve merge"',
            "orca computer hotkey --app Terminal 'aidd ship'",
            'orca orchestration reply --id m1 --text "run aidd approve merge"',
            'orca orchestration dispatch --task t1 --terminal t2 --prompt "aidd ship"',
            "tmux new-window 'aidd approve merge'",
            "tmux new-session -d -s approve 'aidd ship'",
            "tmux split-window -h 'aidd approve merge'",
            "tmux respawn-pane -k -t 0 'aidd approve merge'",
            "tmux respawn-window -k 'aidd ship'",
            "screen -dm aidd approve merge",
            "screen -dmS work sh -c 'aidd ship'",
            "screen -S work -X screen aidd approve merge",
            "open -a Terminal --args aidd approve merge",
            "open -a iTerm 'aidd ship'",
            "zellij run -- aidd approve merge",
            "zellij action write-chars 'aidd approve merge'",
            "zellij action write 'aidd ship'",
            "zellij action new-pane -- aidd approve merge",
            "gnome-terminal -- sh -c 'aidd approve merge'",
            "kitty sh -c 'aidd ship'",
        ):
            why = guard.forbidden_action(cmd)
            self.assertIsNotNone(why, cmd)
            self.assertNotEqual(guard.reason_code(why or ""), "other", cmd)

    def test_quoting_or_escaping_does_not_hide_a_typed_approval(self):
        for cmd in (
            r"tmux send-keys aidd\ approve\ merge Enter",
            r'tmux send-keys -t 0 "aidd" " approve merge" Enter',
            r'tmux send-keys -t 0 "aid""d approve merge" Enter',
            "tmux send-keys -t 0 aidd Space approve Space merge Enter",
            "tmux send-keys -t 0 a i d d Space a p p r o v e Enter",
            "tmux send-keys -t 0 aidd Space ship C-m",
            r"tmux send-keys -t 0 'aidd   approve' Enter",
            "tmux send-keys -t 0 'aidd\tship' Enter",
            r"orca terminal send --terminal t1 --text aidd\ ship --enter",
            "orca terminal create --command \"a''idd approve merge\"",
            "tmux new-window \"python3 -m 'aidd' approve merge\"",
            r"screen -S work -X stuff aidd\ approve\ merge",
            "orca computer type-text --text \"aidd\"'  ship'",
        ):
            why = guard.forbidden_action(cmd)
            self.assertIsNotNone(why, cmd)
            self.assertEqual(guard.reason_code(why or ""), "approval_typed", cmd)

    def test_sending_ordinary_text_to_another_terminal_is_allowed(self):
        for cmd in (
            'tmux send-keys -t 0 "aidd assess" Enter',
            "tmux send-keys -t 0 aidd Space next Enter",
            r"tmux send-keys -t 0 aidd\ test Enter",
            "tmux new-window 'aidd list'",
            'orca terminal create --worktree active --command "claude"',
            'orca orchestration send --to lead --text "aidd shipped the fix in v2; the approval step is next"',
            'orca computer type-text --app Terminal --text "npm test"',
            "zellij run -- pytest -q",
            "open -a Terminal .",
            "screen -dmS build make",
            'tmux send-keys -t 0 "aidd assess" Enter',
            'tmux send-keys -t 0 "aidd test" Enter',
            'orca terminal send --terminal t1 --text "npm test" --enter',
            'orca orchestration send --to lead --text "tests are green; please review"',
            "screen -S work -X stuff 'make build\\n'",
            "xdotool type 'hello'",
            "echo done > /dev/tty",
            "osascript -e 'display notification \"build done\"'",
            "tmux list-panes",
            "orca terminal list",
        ):
            self.assertFalse(self.denied(cmd), cmd)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShellWriteTests(RepoTemplateCase):
    """A role's obvious shell writes meet its edit rules; a helper subagent writes nothing."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")
        (root / "tests" / "checkout").mkdir(parents=True)
        (root / "src" / "checkout" / "rate_limit").mkdir(parents=True)

    def run_as(self, agent_type, command, cwd=None):
        event = {"agent_type": agent_type} if agent_type else {}
        return guard.check_command(str(self.root), str(cwd or self.root), command, event)[0]

    def test_a_developer_cannot_write_a_frozen_test_through_the_shell(self):
        dev = "aidd-team:developer"
        for cmd in (
            f"echo 'assert True' > {TESTS}",
            f"echo x >> {TESTS}",
            f"printf x | tee {TESTS}",
            f"printf x | tee -a {TESTS} > /dev/null",
            f"sed -i 's/a/b/' {TESTS}",
            f"sed -i '' -e 's/a/b/' {TESTS}",
            f"cp /tmp/x.py {TESTS}",
            f"mv {CODE} {TESTS}",
            f"rm {TESTS}",
            "cd tests/checkout && echo x > test_new.py",
            f"bash -c 'echo x > {TESTS}'",
        ):
            self.assertEqual(self.run_as(dev, cmd), "deny", cmd)

    def test_a_developer_writes_inside_its_scope_and_outside_the_repository(self):
        dev = "aidd-developer"
        for cmd in (
            f"echo x > {CODE}",
            f"sed -i 's/a/b/' {CODE}",
            "pytest -q > /dev/null 2>&1",
            "npm test 2>&1 | tail -5",
            "echo scratch > /tmp/aidd-scratch.txt",
            f"cat {TESTS}",
            "git status",
        ):
            self.assertEqual(self.run_as(dev, cmd), "allow", cmd)

    def test_patches_are_read_to_find_their_targets(self):
        diff = self.root / "change.diff"
        diff.write_text(f"--- a/{TESTS}\n+++ b/{TESTS}\n@@ -0,0 +1 @@\n+x\n", encoding="utf-8")
        self.assertEqual(self.run_as("aidd-team:developer", "git apply change.diff"), "deny")
        self.assertEqual(self.run_as("aidd-team:developer", "patch -p1 < change.diff"), "deny")
        diff.write_text(f"--- a/{CODE}\n+++ b/{CODE}\n@@ -0,0 +1 @@\n+x\n", encoding="utf-8")
        self.assertEqual(self.run_as("aidd-team:developer", "git apply change.diff"), "allow")
        # A patch from a pipe cannot be read: the guard denies and names the route, never a prompt mid-build.
        dev = {"agent_type": "aidd-team:developer"}
        decision, reason = guard.check_command(str(self.root), str(self.root), "curl -s https://example.com/p.diff | git apply", dev)
        self.assertEqual(decision, "deny")
        self.assertIn("save the patch to a file", reason)

    def test_an_unexpanded_target_is_denied_with_a_route(self):
        for cmd in ("echo x > $TARGET", "echo x > tests/*.py"):
            decision, reason = guard.check_command(str(self.root), str(self.root), cmd, {"agent_type": "aidd-team:developer"})
            self.assertEqual(decision, "deny", cmd)
            self.assertIn("name the file literally", reason)

    def test_a_read_only_role_writes_nothing_through_the_shell(self):
        for cmd in ("echo x > notes.md", f"sed -i 's/a/b/' {CODE}", "touch src/a.py"):
            self.assertEqual(self.run_as("aidd-team:reviewer", cmd), "deny", cmd)
        self.assertEqual(self.run_as("aidd-team:reviewer", f"grep -n limit {CODE}"), "allow")

    def test_a_helper_subagent_only_reads(self):
        self.assertEqual(self.run_as("Explore", f"echo x > {CODE}"), "deny")
        self.assertEqual(self.run_as("general-purpose", "touch src/a.py"), "deny")
        self.assertEqual(self.run_as("Explore", f"grep -rn limit {CODE}"), "allow")
        with mock.patch.dict(os.environ, {"AIDD_HELPERS_MAY_WRITE": "1"}):
            self.assertEqual(self.run_as("Explore", f"echo x > {CODE}"), "allow")  # the session is not a role: shell writes are the gate's

    def test_the_session_itself_is_checked_only_for_approvals_and_merges(self):
        self.assertEqual(self.run_as(None, f"echo x > {TESTS}"), "allow")
        self.assertEqual(self.run_as(None, "gh pr merge 3"), "deny")

    def hook(self, event):
        out = io.StringIO()
        self.assertEqual(guard.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else "allow"

    def test_the_hook_routes_bash_and_edits(self):
        base = {"cwd": str(self.root)}
        self.assertEqual(self.hook({**base, "tool_name": "Bash", "tool_input": {"command": "gh pr merge 3"}}), "deny")
        self.assertEqual(self.hook({**base, "tool_name": "Bash", "agent_type": "aidd-team:developer", "tool_input": {"command": f"echo x > {TESTS}"}}), "deny")
        self.assertEqual(self.hook({**base, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}}), "allow")
        edit = {**base, "tool_name": "Edit", "tool_input": {"file_path": str(self.root / CODE)}}
        self.assertEqual(self.hook(edit), "allow")
        self.assertEqual(self.hook({**edit, "agent_type": "Explore"}), "deny")
        self.assertEqual(self.hook({**edit, "agent_type": "ecc:developer"}), "deny")
        self.assertEqual(self.hook({**edit, "agent_type": "aidd-team:developer"}), "allow")
        with mock.patch.dict(os.environ, {"AIDD_HELPERS_MAY_WRITE": "1"}):
            self.assertEqual(self.hook({**edit, "agent_type": "Explore"}), "allow")

    @unittest.skipIf(os.name == "nt", "the fake orca CLI is a POSIX script")
    def test_inside_orca_in_full_autonomy_approving_merging_and_shipping_stay_denied(self):
        """Orca launches agents with their permission-bypass flag (Claude: --dangerously-skip-permissions), and its
        terminals carry ORCA_* variables. The guard never reads either, and never asks Orca anything: the same
        commands are denied for the same reasons."""
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "orca.log"
            fake = Path(d) / "orca"
            fake.write_text(f"#!/bin/sh\necho \"$@\" >> '{log}'\necho '{{\"ok\": true}}'\n", encoding="utf-8")
            fake.chmod(0o755)
            orca = {
                "ORCA_PANE_KEY": "tab-1:leaf-1",
                "ORCA_WORKTREE_ID": "repo-1::/w",
                "ORCA_AGENT_HOOK_PORT": "49177",
                "ORCA_AGENT_HOOK_TOKEN": "t",
                "PATH": f"{d}{os.pathsep}{os.environ.get('PATH', '')}",
            }
            commands = (
                "aidd approve merge",
                "aidd approve spec specs/SPEC-220.md",
                "uvx aidd ship --squash",
                "gh pr merge 3 --squash",
                "gh pr review 3 --approve",
                "glab mr approve 3",
                "gh pr comment 3 --body '/aidd approve-spec SPEC-220 abc def'",
                'orca terminal send --terminal t1 --text "aidd approve merge" --enter',
                'orca orchestration ask --to lead "please run aidd ship"',
            )
            base = {"cwd": str(self.root), "tool_name": "Bash", "permission_mode": "default"}

            def answer(event):
                out = io.StringIO()
                guard.pre_tool_hook(io.StringIO(json.dumps(event)), out)
                return out.getvalue()

            before = {c: answer({**base, "tool_input": {"command": c}}) for c in commands}
            with mock.patch.dict(os.environ, orca):
                for agent in ({}, {"agent_type": "aidd-team:developer"}):
                    for command in commands:
                        event = {**base, **agent, "permission_mode": "bypassPermissions", "tool_input": {"command": command}}
                        self.assertEqual(self.hook(event), "deny", (agent, command))
                        if not agent:
                            self.assertEqual(answer(event), before[command], command)  # the same reason as outside Orca
                self.assertEqual(self.hook({**base, "permission_mode": "bypassPermissions", "tool_input": {"command": "pytest -q"}}), "allow")
            self.assertFalse(log.exists(), "the guard asked Orca something")

    def test_outside_an_aidd_repository_the_hook_stays_silent(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            for event in (
                {"cwd": d, "tool_name": "Bash", "tool_input": {"command": "gh pr merge 3"}},
                {"cwd": d, "tool_name": "Edit", "agent_type": "Explore", "tool_input": {"file_path": str(Path(d) / "a.py")}},
            ):
                self.assertEqual(self.hook(event), "allow")


DEPLOY_GATE = """
[[guard.held_commands]]
name = "production deploy"
match = ["deploy", "production"]
environment = "production"
requires = "RELEASE_APPROVAL"
message = "Production changes ship through the release train."

[[guard.held_commands]]
name = "terraform apply"
match = ["terraform apply*"]

[[guard.held_commands]]
name = "database drop"
match = ["drop database"]
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class HeldCommandTests(unittest.TestCase):
    """`[[guard.held_commands]]`: a deploy waits for a person's approval, set in the environment the session started with."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        repo.init(self.root, profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[])
        self.config = self.root / ".aidd" / "config.toml"
        self.config.write_text(self.config.read_text(encoding="utf-8") + DEPLOY_GATE, encoding="utf-8")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("RELEASE_APPROVAL", None)

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self, command, approval=None, agent_type=None):
        if approval is not None:
            os.environ["RELEASE_APPROVAL"] = approval
        event = {"agent_type": agent_type} if agent_type else {}
        return guard.check_command(str(self.root), str(self.root), command, event)

    def test_the_config_validates(self):
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(self.root))
        self.assertEqual([g["name"] for g in cfg.get("guard", "held_commands")], ["production deploy", "terraform apply", "database drop"])
        self.config.write_text(
            self.config.read_text(encoding="utf-8").replace('requires = "RELEASE_APPROVAL"', 'requires = "not a variable"'), encoding="utf-8"
        )
        with self.assertRaises(cfgmod.ConfigError):
            cfgmod.load_file(cfgmod.CONFIG_PATH, str(self.root))

    def test_a_matching_command_is_denied_until_approved(self):
        for cmd in (
            "make deploy ENV=production",
            "./scripts/deploy.sh --env Production",
            "cd infra && kubectl rollout restart deploy/api --context production",
            "bash -c 'npm run deploy -- --target production'",
        ):
            decision, reason = self.decide(cmd)
            self.assertEqual(decision, "deny", cmd)
            self.assertIn("`production deploy` is a held command for production", reason)
            self.assertIn("RELEASE_APPROVAL", reason)
            self.assertIn("release train", reason)
        # Every agent: the session, a role, and a helper.
        for agent in ("aidd-team:platform-engineer", "Explore"):
            self.assertEqual(self.decide("make deploy ENV=production", agent_type=agent)[0], "deny", agent)

    def test_every_pattern_must_match_one_command(self):
        for cmd in ("make deploy ENV=staging", "echo production", "pytest -q", "echo deploy; ls production"):
            self.assertEqual(self.decide(cmd)[0], "allow", cmd)

    def test_the_approval_variable_lets_it_run(self):
        self.assertEqual(self.decide("make deploy ENV=production", approval="CHG-1234")[0], "allow")
        self.assertEqual(self.decide("make deploy ENV=production", approval="  ")[0], "deny")

    def test_the_command_cannot_approve_itself(self):
        for cmd in ("RELEASE_APPROVAL=1 make deploy ENV=production", "export RELEASE_APPROVAL=yes; make deploy ENV=production"):
            decision, reason = self.decide(cmd)
            self.assertEqual(decision, "deny", cmd)
            self.assertIn("never from the command itself", reason)
            # Even with a real approval, a command that sets the variable is not trusted.
            self.assertEqual(self.decide(cmd, approval="CHG-1")[0], "deny", cmd)

    def test_globs_and_gates_without_an_approval_variable(self):
        decision, reason = self.decide("terraform apply -auto-approve")
        self.assertEqual(decision, "deny")
        self.assertIn("agents never run it", reason)
        self.assertEqual(self.decide("terraform plan")[0], "allow")
        self.assertEqual(self.decide("psql -c 'DROP DATABASE app'")[0], "deny")

    def test_the_hook_denies_a_held_command(self):
        out = io.StringIO()
        event = {"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": "make deploy ENV=production"}}
        guard.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("RELEASE_APPROVAL", decision["permissionDecisionReason"])

    def test_no_gates_by_default(self):
        self.config.write_text(self.config.read_text(encoding="utf-8").replace(DEPLOY_GATE, ""), encoding="utf-8")
        self.assertNotIn("guard", self.config.read_text(encoding="utf-8"))
        self.assertEqual(self.decide("make deploy ENV=production")[0], "allow")


class HookWiringTests(unittest.TestCase):
    def test_the_plugin_hook_matches_bash_and_every_edit_tool(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(repo.HOOK_MATCHER, hooks[0]["matcher"])
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "PowerShell"):
            self.assertTrue(self.matches(tool), tool)

    @staticmethod
    def matches(tool: str) -> bool:
        """Claude Code tests a tool name against the matcher as a case-sensitive regular expression; the matcher must
        hold whether it is anchored or not."""
        full, anywhere = re.fullmatch(repo.HOOK_MATCHER, tool) is not None, re.search(repo.HOOK_MATCHER, tool) is not None
        assert full == anywhere or not full, tool
        return full

    def test_every_mcp_tool_the_guard_denies_by_name_reaches_it(self):
        """The matcher leaves out MCP tools that cannot approve or merge (a browser, a docs search), so a busy session
        does not start the guard on each call; every name the guard denies still reaches it, in any naming style."""
        verbs = ["merge", "approve", "accept", "complete", "enable", "set", "create", "post", "update", "add", "submit", "write", "get"]
        nouns = ["pull_request", "merge_request", "pr", "mr", "auto_merge", "commit_status", "status", "review", "request", "issue_comment"]
        styles = (
            lambda ws: "_".join(ws),
            lambda ws: "-".join(ws),
            lambda ws: ws[0] + "".join(w.title() for w in ws[1:]),
            lambda ws: "".join(w.title() for w in ws),
            lambda ws: "_".join(ws).upper(),
        )
        denied = 0
        for verb in verbs:
            for noun in nouns:
                words = [verb, *noun.split("_")]
                for style in styles:
                    name = f"mcp__forge__{style(words)}"
                    decision, _ = guard.check_mcp_tool(name, {"event": "APPROVE"})
                    if decision == "deny":
                        denied += 1
                        self.assertTrue(self.matches(name), name)
        self.assertGreater(denied, 100)

    def test_the_tools_that_carry_a_comment_a_body_or_a_commit_reach_the_guard(self):
        for tool in (
            "mcp__github__add_issue_comment",
            "mcp__github__add_comment_to_pending_review",
            "mcp__github__create_pull_request",
            "mcp__github__update_pull_request",
            "mcp__github__create_or_update_file",
            "mcp__github__push_files",
            "mcp__gitlab__create_note",
            "mcp__gitlab__create_merge_request_note",
            "mcp__gitlab__create_merge_request_discussion_note",
            "mcp__gitlab__create_merge_request_thread",
            "mcp__gitlab__update_merge_request",
            "mcp__forge__update_pr",
            "mcp__forge__updatePr",
            "mcp__forge__reply_to_thread",
        ):
            self.assertTrue(self.matches(tool), tool)

    def test_tools_that_cannot_approve_or_merge_skip_the_guard(self):
        for tool in (
            "mcp__plugin_playwright_playwright__browser_click",
            "mcp__plugin_playwright_playwright__browser_press_key",
            "mcp__plugin_ecc_chrome-devtools__take_screenshot",
            "mcp__plugin_mintlify_Mintlify__search_mintlify",
            "mcp__context7__query-docs",
            "mcp__think-strategies__think-strategies",
        ):
            self.assertFalse(self.matches(tool), tool)

    def test_each_hook_starts_one_interpreter(self):
        """A second `python3 -c` just to check the version doubled the cost of every matched tool call."""
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event, entries in hooks.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    self.assertEqual(hook["command"].count("python3"), 1, event)
                    self.assertIn("3.11", hook["command"], event)  # a failure still names what it needs

    def test_the_loader_exits_3_on_an_old_python_before_it_reads_stdin(self):
        """macOS ships python3 3.9: the loader stops it with exit 3, and the plugin's hooks then try a Python uv finds."""
        import sys

        with mock.patch.object(sys, "version_info", (3, 9, 6)), mock.patch.object(sys, "stdin") as stdin:
            with self.assertRaises(SystemExit) as caught:
                exec(repo.LOADER, {})
        self.assertEqual(caught.exception.code, 3)
        stdin.read.assert_not_called()

    def test_init_wires_the_same_matcher_and_upgrades_an_old_one(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            settings = root / ".claude" / "settings.json"
            settings.parent.mkdir()
            old = {"hooks": {"PreToolUse": [{"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": repo.HOOK_COMMAND}]}]}}
            settings.write_text(json.dumps(old), encoding="utf-8")
            actions: list[str] = []
            repo.install_agent_hooks(root, actions)
            entries = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
            self.assertEqual([e["matcher"] for e in entries], [repo.HOOK_MATCHER])
            repo.install_agent_hooks(root, actions)
            self.assertEqual(len(json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]), 1)
            self.assertTrue(any("kept" in a and "settings.json" in a for a in actions))


if __name__ == "__main__":
    unittest.main()
