"""The guard finds the repository of each path a tool writes, from the path itself.

The tests drive `guard.pre_tool_hook` the way the harness does. Each one pins a write that the guard judges as it
judges an Edit of the same file:
- a shell or MCP write is judged in the repository of its target, never of the session's cwd, so a sibling or nested
  worktree, or a cwd outside the repository, meets the same rules (for `delegate` and for a role's area alike);
- a hard link never carries a write from outside the repository into a tracked file;
- a redirect after a subshell group or a command substitution is seen;
- a case variant of a tracked file in an ignored folder is content on a case-insensitive file system;
- an MCP tool's `source`, `file`, and `uri` are paths too;
- an agent starts or stops autopilot only for its own session, never for the person's;
- session-start masks the branch name.
And `delegate` itself: the steer informs, and never tells an agent to refuse; and `always` with no team installed.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, git, make_repo

from aidd import config as cfgmod
from aidd import guard, hooks, repo
from aidd import lease as leasemod

CODE = "src/checkout/rate_limit/limiter.py"
LEAD = "lead-session-1"
OTHER = "person-session-2"


@unittest.skipUnless(shutil.which("git"), "git is required")
class TargetRepositoryTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")
        (root / "src" / "checkout" / "rate_limit").mkdir(parents=True)
        (root / CODE).write_text("x = 1\n", encoding="utf-8")
        (root / "build").mkdir()
        (root / "build" / "keep.txt").write_text("k\n", encoding="utf-8")
        (root / ".gitignore").write_text("build/\n.claude/\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "add", "-f", "build/keep.txt")
        git(root, "commit", "-qm", "the Spec, the code, and a tracked file in an ignored folder")

    def setUp(self):
        super().setUp()
        self.base = self.root.parent
        self.sib = self.base / "sib"
        git(self.root, "worktree", "add", "-q", str(self.sib), "-b", "sib")
        self.nest = self.root / ".claude" / "worktrees" / "nest"
        git(self.root, "worktree", "add", "-q", str(self.nest), "-b", "nest")
        self.outside = self.base / "outside"
        self.outside.mkdir()
        leasemod.take(self.root, work="all", session_id=LEAD)  # the team profile's `auto`: the lead is denied

    def hook(self, event: dict, cwd: Path | None = None) -> dict:
        out = io.StringIO()
        self.assertEqual(guard.pre_tool_hook(io.StringIO(json.dumps({"cwd": str(cwd or self.root), **event})), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}

    def bash(self, command: str, session: str | None = LEAD, cwd: Path | None = None, **extra) -> str | None:
        event: dict = {"tool_name": "Bash", "tool_input": {"command": command}, **extra}
        if session:
            event["session_id"] = session
        return self.hook(event, cwd).get("permissionDecision")

    def tool(self, name: str, tool_input: dict, session: str | None = LEAD, cwd: Path | None = None, **extra) -> str | None:
        event: dict = {"tool_name": name, "tool_input": tool_input, **extra}
        if session:
            event["session_id"] = session
        return self.hook(event, cwd).get("permissionDecision")

    # ---- the repository of the target, not of the cwd ----------------------------------------------------------

    def test_a_shell_write_is_judged_in_the_repository_of_its_target(self):
        self.assertEqual(self.tool("Edit", {"file_path": str(self.sib / CODE), "old_string": "x", "new_string": "y"}), "deny")
        for command, cwd in (
            (f"echo y > {self.sib / CODE}", None),
            (f"echo y > .claude/worktrees/nest/{CODE}", None),
            (f"echo y > {self.root / CODE}", self.sib),
            (f"echo y > {self.root / CODE}", self.outside),
            (f"cd {self.root} && echo y > {CODE}", self.outside),
            (f"sed -i 's/x/y/' {self.sib / CODE}", None),
        ):
            self.assertEqual(self.bash(command, cwd=cwd), "deny", (command, cwd))
        # A new file in a new folder of a sibling worktree belongs to that worktree too.
        self.assertEqual(self.tool("Write", {"file_path": str(self.sib / "src" / "newdir" / "x.py"), "content": "y"}), "deny")
        # Scratch outside every repository stays free, from any cwd.
        for cwd in (None, self.outside):
            self.assertIsNone(self.bash(f"echo y > {self.outside / 'scratch.txt'}", cwd=cwd), cwd)
        # Another session is never denied by `auto`, wherever the file is.
        self.assertIsNone(self.bash(f"echo y > {self.sib / CODE}", session=OTHER))

    def test_an_mcp_write_is_judged_in_the_repository_of_its_path(self):
        edit = {"edits": [{"oldText": "x", "newText": "y"}]}
        self.assertEqual(self.tool("mcp__filesystem__edit_file", {"path": str(self.sib / CODE), **edit}), "deny")
        self.assertEqual(self.tool("mcp__filesystem__write_file", {"path": str(self.nest / CODE), "content": "y"}), "deny")
        self.assertEqual(self.tool("mcp__filesystem__write_file", {"path": str(self.root / CODE), "content": "y"}, cwd=self.outside), "deny")
        self.assertIsNone(self.tool("mcp__filesystem__write_file", {"path": str(self.outside / "s.txt"), "content": "y"}, cwd=self.outside))

    def test_a_roles_shell_write_is_held_to_the_area_in_the_targets_repository(self):
        role = {"agent_type": "aidd-team:developer"}
        self.assertEqual(self.tool("Edit", {"file_path": str(self.sib / "docs" / "notes.md"), "old_string": "", "new_string": "y"}, **role), "deny")
        self.assertEqual(self.bash(f"echo y > {self.sib / 'docs' / 'notes.md'}", **role), "deny")
        self.assertEqual(self.bash(f"echo y > {self.root / 'docs' / 'notes.md'}", cwd=self.sib, **role), "deny")
        self.assertEqual(self.bash("echo y > .claude/worktrees/nest/docs/notes.md", **role), "deny")
        self.assertIsNone(self.bash(f"echo y > {self.sib / CODE}", **role))  # inside its area there too
        self.assertIsNone(self.bash(f"echo y > {self.outside / 'scratch.txt'}", **role))

    def test_an_edit_tool_never_writes_inside_a_git_folder(self):
        for target in (self.root / ".git" / "config", self.root / ".git" / "aidd" / "lease.json", self.sib / ".git"):
            out = self.hook({"tool_name": "Write", "session_id": OTHER, "tool_input": {"file_path": str(target), "content": "y"}})
            self.assertEqual(out.get("permissionDecision"), "deny", target)
            self.assertEqual(guard.reason_code(out["permissionDecisionReason"]), "git_dir", target)

    # ---- hard links --------------------------------------------------------------------------------------------

    def test_a_hard_link_never_carries_a_write_into_the_repository(self):
        link = self.outside / "h"
        self.assertEqual(self.bash(f"ln {CODE} {link} && echo y > {link}"), "deny")
        self.assertEqual(self.bash(f"ln {CODE} {link}"), "deny")
        self.assertEqual(self.bash(f"cp -l {CODE} {link}"), "deny")
        self.assertIsNone(self.bash(f"ln -s {CODE} {self.outside / 's'}"))  # a symbolic link writes nothing
        os.link(self.root / CODE, link)  # a link made some other way
        self.assertEqual(self.bash(f"echo y > {link}"), "deny")
        self.assertEqual(self.bash(f"cd {self.outside} && echo y > h"), "deny")
        self.assertEqual(self.tool("Write", {"file_path": str(link), "content": "y"}), "deny")
        self.assertEqual(self.tool("Edit", {"file_path": str(link), "old_string": "x", "new_string": "y"}), "deny")
        self.assertEqual(self.tool("mcp__filesystem__write_file", {"path": str(link), "content": "y"}), "deny")
        self.assertEqual(self.bash(f"echo y > {link}", agent_type="aidd-team:developer"), "deny")
        self.assertIsNone(self.bash(f"rm {link}"))  # removing a name changes no other link
        self.assertIsNone(self.bash(f"echo y > {link}", session=OTHER))  # a session `auto` does not hold

    # ---- redirects after a group or a substitution -------------------------------------------------------------

    def test_a_redirect_after_a_group_or_a_substitution_is_seen(self):
        for command in (
            f"(echo y) > {CODE}",
            f"echo $(cat /tmp/payload) > {CODE}",
            f"echo `cat /tmp/payload` > {CODE}",
            f"{{ echo y; }} > {CODE}",
            f"(cd src && echo y) >> {CODE}",
        ):
            self.assertEqual(self.bash(command), "deny", command)
        self.assertEqual(self.bash("(echo y) > docs/notes.md", agent_type="aidd-team:developer"), "deny")
        self.assertIsNone(self.bash("(echo y) > /dev/null"))

    # ---- a tracked file in an ignored folder, in any case ------------------------------------------------------

    def test_a_tracked_file_in_an_ignored_folder_is_content_in_any_case(self):
        self.assertTrue(guard.governed(str(self.root), "build/keep.txt"))
        self.assertEqual(self.bash("echo y > build/keep.txt"), "deny")
        self.assertIsNone(self.bash("echo y > build/new.txt"))  # a new file in an ignored folder is scratch
        if not (self.root / "BUILD").exists():
            self.skipTest("a case-sensitive file system: BUILD/KEEP.txt is another file")
        self.assertEqual(self.bash("echo y > BUILD/KEEP.txt"), "deny")
        self.assertEqual(self.tool("Write", {"file_path": str(self.root / "BUILD" / "KEEP.txt"), "content": "y"}), "deny")
        self.assertEqual(self.tool("Write", {"file_path": str(self.root / "SRC" / "checkout" / "rate_limit" / "LIMITER.py"), "content": "y"}), "deny")
        self.assertIsNone(self.bash("echo y > BUILD/new.txt"))

    # ---- an MCP tool's paths -----------------------------------------------------------------------------------

    def test_an_mcp_tool_s_source_file_and_uri_are_paths_too(self):
        moved = str(self.outside / "moved.py")
        self.assertEqual(self.tool("mcp__filesystem__move_file", {"source": str(self.root / CODE), "destination": moved}), "deny")
        self.assertEqual(self.tool("mcp__fs__delete_file", {"file": str(self.root / CODE)}), "deny")
        self.assertEqual(self.tool("mcp__fs__write_file", {"uri": (self.root / CODE).as_uri(), "content": "y"}), "deny")
        self.assertIsNone(self.tool("mcp__fs__write_file", {"uri": "https://example.com/x", "content": "y"}))

    # ---- another session's autopilot lease ---------------------------------------------------------------------

    def test_an_agent_starts_or_stops_autopilot_only_for_its_own_session(self):
        for command in (
            f"aidd autopilot start --work all --session {OTHER}",
            f"aidd autopilot start --work all --session={OTHER}",
            f"uvx aidd autopilot stop --session {OTHER}",
            f"python3 -m aidd autopilot start --session {OTHER} --work all",
            f"sh -c 'aidd autopilot start --session {OTHER}'",
            "aidd autopilot start --session $SOME_ID",
            f"aidd autopilot start --sess {OTHER}",
            f"(aidd autopilot start --session {OTHER})",
        ):
            for session in (LEAD, OTHER + "-x"):
                self.assertEqual(self.bash(command, session=session), "deny", (command, session))
        out = self.hook({"tool_name": "Bash", "session_id": LEAD, "tool_input": {"command": f"aidd autopilot start --session {OTHER}"}})
        self.assertIn("another session", out["permissionDecisionReason"])
        self.assertEqual(guard.reason_code(out["permissionDecisionReason"]), "autopilot_session")
        self.assertEqual(self.bash(f"cd {self.root} && aidd autopilot start --session {OTHER}", cwd=self.outside), "deny")
        self.assertEqual(self.bash(f"aidd autopilot start --session {OTHER}", session=None), "deny")  # no session to compare with
        for command in (
            f"aidd autopilot start --work all --session {LEAD}",
            f"aidd autopilot stop --session {LEAD}",
            "aidd autopilot start --work all",
            f"aidd autopilot next --session {LEAD} --json",
            f"aidd autopilot status --session {OTHER}",
        ):
            self.assertIsNone(self.bash(command), command)

    # ---- symbolic links, nesting, parse failures, `--session` prefixes, and BSD sed ---------------------------

    def test_a_symbolic_link_then_dot_dot_is_read_as_the_kernel_reads_it(self):
        os.symlink(self.root / "src" / "checkout" / "rate_limit", self.outside / "l")
        via = f"{self.outside}/l/../rate_limit/limiter.py"  # the kernel follows l first: this is CODE
        self.assertEqual(self.bash(f"echo y > {via}"), "deny")
        self.assertEqual(self.bash("echo y > l/../rate_limit/limiter.py", cwd=self.outside), "deny")
        self.assertEqual(self.tool("Edit", {"file_path": via, "old_string": "x", "new_string": "y"}), "deny")
        self.assertEqual(self.tool("mcp__fs__write_file", {"path": via, "content": "y"}), "deny")
        # `cd` is logical in bash: `cd out/l/..` lands in out, so the write that follows is scratch.
        self.assertIsNone(self.bash(f"cd {self.outside}/l/.. && echo y > scratch.py"))

    def test_nesting_never_turns_the_check_off(self):
        self.assertEqual(self.bash("eval " * 1200 + f"'echo y > {CODE}'"), "deny")
        self.assertEqual(self.bash(f"bash -c 'echo y > {CODE}'; cat <<EOF\n(((\nEOF"), "deny")
        self.assertEqual(self.bash(f"(((true))); bash -c 'echo y > {CODE}'"), "deny")
        self.assertEqual(self.bash(f"(cd {self.outside}; cat <<EOF\n(\nEOF\n); echo y > {CODE}"), "deny")
        self.assertEqual(self.bash(f"cd {self.outside} && cd - && echo y > {CODE}"), "deny")

    def test_a_failure_while_parsing_a_held_command_is_a_deny(self):
        with mock.patch.object(guard, "_simple_commands", side_effect=RecursionError("deep")):
            out = self.hook({"tool_name": "Bash", "session_id": LEAD, "tool_input": {"command": f"echo y > {CODE}"}})
            self.assertEqual(out.get("permissionDecision"), "deny")
            self.assertEqual(guard.reason_code(out["permissionDecisionReason"]), "guard_failed")
            self.assertIsNone(self.bash(f"echo y > {CODE}", session=OTHER))  # a session the guard does not hold

    def test_every_prefix_argparse_takes_for_session_is_read(self):
        for flag in ("--s", "--se", "--ses", "--sess", "--session"):
            self.assertEqual(self.bash(f"aidd autopilot stop {flag} {OTHER}"), "deny", flag)
            self.assertEqual(self.bash(f"aidd autopilot stop {flag}={OTHER}"), "deny", flag)
        self.assertIsNone(self.bash(f"aidd autopilot stop --s {LEAD}"))

    def test_bsd_sed_in_place_with_an_empty_suffix(self):
        role = {"agent_type": "aidd-team:developer"}
        for command in (f"sed -i '' 's/x/y/' {CODE}", f"sed -i'' 's/x/y/' {CODE}", f"sed -i '' -e 's/x/y/' {CODE}"):
            self.assertIsNone(self.bash(command, **role), command)  # CODE is in the developer's scope
            self.assertEqual(self.bash(command), "deny", command)  # the lead never edits it
        self.assertEqual(self.bash("sed -i '' 's/x/y/' docs/notes.md", **role), "deny")

    # ---- the steer, and `always` without the team --------------------------------------------------------------

    def team_installed(self) -> None:
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "aidd-developer.md").write_text("---\nname: aidd-developer\n---\n", encoding="utf-8")

    def set_config(self, old: str, new: str) -> None:
        cfg = self.root / cfgmod.CONFIG_PATH
        text = cfg.read_text(encoding="utf-8")
        self.assertIn(old, text)
        cfg.write_text(text.replace(old, new, 1), encoding="utf-8")

    def set_always(self) -> None:
        cfg = self.root / cfgmod.CONFIG_PATH
        text = cfg.read_text(encoding="utf-8")
        self.assertNotIn("\n[agents]\n", text)
        cfg.write_text(text + '\n[agents]\ndelegate = "always"\n', encoding="utf-8")

    def test_the_steer_for_a_file_no_role_owns_is_information(self):
        self.team_installed()
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(self.root))
        rel = "Makefile"
        self.assertEqual(guard.owners_of(str(self.root), cfg, rel), [])
        note = guard.delegate_steer(str(self.root), rel, {"session_id": OTHER}, cfg)
        self.assertIsNotNone(note)
        self.assertNotIn("a person edits it", note)
        self.assertIn("not a denial", note)

    def test_always_without_the_team_says_to_install_it(self):
        self.set_always()
        out = self.hook({"tool_name": "Edit", "session_id": OTHER, "tool_input": {"file_path": str(self.root / CODE), "old_string": "x", "new_string": "y"}})
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("aidd init --team", out["permissionDecisionReason"])
        self.assertNotIn("aidd-team:developer", out["permissionDecisionReason"])
        found = [(lvl, m) for lvl, m in repo.doctor(self.root) if "delegate" in m]
        self.assertEqual([lvl for lvl, _ in found], ["fail"], found)
        self.assertIn("aidd init --team", found[0][1])
        self.team_installed()
        self.assertFalse([m for _, m in repo.doctor(self.root) if "delegate" in m])
        out = self.hook({"tool_name": "Edit", "session_id": OTHER, "tool_input": {"file_path": str(self.root / CODE), "old_string": "x", "new_string": "y"}})
        self.assertIn("aidd-team:developer", out["permissionDecisionReason"])

    def test_the_regulated_default_applies_only_with_the_team(self):
        self.set_config('profile = "team"', 'profile = "regulated"')
        cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, str(self.root))  # a config the guard reads: the test is not vacuous
        self.assertEqual(cfgmod.delegate_mode(cfg.raw), "always")
        edit = {"tool_name": "Edit", "session_id": OTHER, "tool_input": {"file_path": str(self.root / CODE), "old_string": "x", "new_string": "y"}}
        self.assertNotEqual(self.hook(edit).get("permissionDecision"), "deny")
        found = [(lvl, m) for lvl, m in repo.doctor(self.root) if "delegate" in m]
        self.assertEqual([lvl for lvl, _ in found], ["info"], found)
        self.team_installed()
        out = self.hook(edit)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("aidd-team:developer", out["permissionDecisionReason"])
        self.assertFalse([m for _, m in repo.doctor(self.root) if "delegate" in m])


@unittest.skipUnless(shutil.which("git"), "git is required")
class SessionStartMaskTests(unittest.TestCase):
    def test_session_start_masks_a_secret_in_the_branch_name(self):
        token = "ghp_" + "A1b2C3d4E5" * 4
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", "team")
            git(root, "checkout", "-qb", f"feat-{token}")
            out = io.StringIO()
            event = {"cwd": str(root), "session_id": OTHER, "hook_event_name": "SessionStart", "source": "startup"}
            self.assertEqual(hooks.run("session-start", io.StringIO(json.dumps(event)), out, io.StringIO()), 0)
            text = out.getvalue()
            self.assertIn("aidd assess on branch", text)
            self.assertNotIn(token, text)
            self.assertIn("feat-***", text)


if __name__ == "__main__":
    unittest.main()
