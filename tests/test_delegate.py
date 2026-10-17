"""`agents.delegate`: the main session hands its edits of repository content to an aidd-team role.

What holds, pinned here:
(a) no ordinary tool call lets the lead edit tracked content without a role while `delegate` must deny it;
(b) no session other than the autopilot lease holder is denied by `auto`;
(c) the hooks write no tracked file and print no secret (tests/test_session_hooks.py pins the session hooks).
A role is read from the hook input the harness writes (`agent_type`), never from text an agent wrote.
"""

import io
import json
import os
import shutil
import unittest

from helpers import RepoTemplateCase, git, make_repo

from aidd.guard import pre_tool
from aidd.guard import delegation
from aidd.guard import path_location
from aidd import config
from aidd.config import model
from aidd.autopilot import lease
from aidd.config import baseline
from aidd.kernel import json_schema

CODE = "src/checkout/rate_limit/limiter.py"
TESTS = "tests/checkout/test_rate_limit.py"
LEAD = "lead-session-1"
OTHER = "person-session-2"


def load(profile: str, extra: str = "", parent: str | None = None) -> config.Config:
    text = f'aidd_version: "1.0.0"\nprofile: "{profile}"\n' + ("extends: [{path: parent.yaml}]\n" if parent else "") + extra
    return config.load_text(text, read=lambda rel: parent if rel == "parent.yaml" else None)


class DelegateConfigTests(unittest.TestCase):
    def test_each_profile_starts_at_its_mode(self):
        self.assertEqual(model.DELEGATE_MODES, ("never", "auto", "always"))
        for profile in ("solo", "team", "org"):
            self.assertEqual(config.delegate_mode(load(profile).raw), "auto", profile)
        self.assertEqual(config.delegate_mode(load("audited").raw), "always")
        self.assertEqual(set(model.DELEGATE_DEFAULTS), set(baseline.profiles()["order"]))

    def test_the_schema_takes_the_three_modes_only(self):
        base = {"aidd_version": "1.0.0", "profile": "team"}
        for mode in ("always", "never", "auto"):
            self.assertEqual(json_schema.validate(base | {"agents": {"delegate": mode}}, "config.schema.json"), [], mode)
        for bad in ("on", "off", "require", "warn", True):
            self.assertTrue(json_schema.validate(base | {"agents": {"delegate": bad}}, "config.schema.json"), bad)

    def test_a_repository_sets_its_own_mode(self):
        self.assertEqual(config.delegate_mode(load("team", "agents:\n  delegate: never\n").raw), "never")
        self.assertEqual(config.delegate_mode(load("solo", "agents:\n  delegate: always\n").raw), "always")

    def test_a_child_cannot_loosen_the_parents_mode(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\nagents:\n  delegate: always\n'
        cfg = load("team", "agents:\n  delegate: never\n", parent)
        self.assertEqual(config.delegate_mode(cfg.raw), "always")
        self.assertTrue(any("agents.delegate='never' ignored" in w for w in cfg.warnings), cfg.warnings)
        audited = 'aidd_version: "1.0.0"\nprofile: audited\n'
        self.assertEqual(config.delegate_mode(load("audited", "agents:\n  delegate: auto\n", audited).raw), "always")


@unittest.skipUnless(shutil.which("git"), "git is required")
class DelegateGuardTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md", status="ready")
        (root / "src" / "checkout" / "rate_limit").mkdir(parents=True)
        (root / "tests" / "checkout").mkdir(parents=True)
        (root / CODE).write_text("x = 1\n", encoding="utf-8")
        (root / ".gitignore").write_text("build/\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "the Spec and the code")

    def set_mode(self, mode: str | None) -> None:
        if not mode:
            return
        cfg = self.root / ".aidd" / "config.yaml"
        text = cfg.read_text(encoding="utf-8")
        line = f'delegate: "{mode}"\n'
        text = text.replace("\nagents:\n", "\nagents:\n  " + line, 1) if "\nagents:\n" in text else text + "\nagents:\n  " + line
        cfg.write_text(text, encoding="utf-8")

    def team_installed(self) -> None:
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "aidd-developer.md").write_text("---\nname: aidd-developer\n---\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("build/\n.claude/\n", encoding="utf-8")

    def hook(self, event: dict) -> dict:
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(json.dumps({"cwd": str(self.root), **event})), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}

    def edit(self, rel: str = CODE, session: str | None = LEAD, **extra) -> dict:
        event: dict = {"tool_name": "Edit", "tool_input": {"file_path": str(self.root / rel), "old_string": "x", "new_string": "y"}, **extra}
        if session:
            event["session_id"] = session
        return self.hook(event)

    def bash(self, command: str, session: str | None = LEAD, **extra) -> dict:
        event: dict = {"tool_name": "Bash", "tool_input": {"command": command}, **extra}
        if session:
            event["session_id"] = session
        return self.hook(event)

    def start(self, session: str = LEAD) -> None:
        lease.take_lease(self.root, work="SPEC-220", session_id=session)

    def test_never_neither_denies_nor_steers(self):
        self.set_mode("never")
        self.team_installed()
        self.start()
        self.assertEqual(self.edit(), {})
        self.assertEqual(self.bash(f"echo y > {CODE}"), {})

    def test_always_denies_the_main_session_and_names_the_role(self):
        self.set_mode("always")
        self.team_installed()  # without the team, the reason says to install it (tests/test_delegate_paths.py)
        for session in (LEAD, OTHER, None):
            out = self.edit(session=session)
            self.assertEqual(out.get("permissionDecision"), "deny", session)
            self.assertIn("aidd-team:developer", out["permissionDecisionReason"])
            self.assertIn("delegate", out["permissionDecisionReason"])
        for write in ("Write", "MultiEdit", "NotebookEdit"):
            out = self.hook({"tool_name": write, "session_id": OTHER, "tool_input": {"file_path": str(self.root / "README.md"), "content": "x"}})
            self.assertEqual(out.get("permissionDecision"), "deny", write)
        # A new file is repository content too.
        self.assertEqual(self.edit("src/checkout/rate_limit/new.py").get("permissionDecision"), "deny")

    def test_always_denies_the_main_sessions_obvious_shell_writes(self):
        self.set_mode("always")
        for command in (f"echo y > {CODE}", f"sed -i 's/x/y/' {CODE}", f"printf y | tee {CODE}", f"cp /tmp/a {CODE}", f"rm {CODE}", "touch src/a.py"):
            self.assertEqual(self.bash(command, OTHER).get("permissionDecision"), "deny", command)

    def test_what_delegate_never_governs(self):
        self.set_mode("always")
        for command in (
            "aidd list --branch",
            "aidd gate --paths src/a.py",
            "aidd autopilot next --session lead-session-1 --json",
            "git checkout -b feat-2",
            "git worktree add ../other feat",
            "git push origin feat",
            "git add -A && git commit -qm wip",
            f"cat {CODE}",
            f"grep -n x {CODE}",
            "pytest -q > /dev/null 2>&1",
            "echo scratch > /tmp/aidd-delegate-scratch.txt",
            "mkdir -p build && echo x > build/out.txt",
        ):
            self.assertEqual(self.bash(command, OTHER).get("permissionDecision"), None, command)
        # An ignored file, and anything under .git, is not repository content (the Spec's scope rule still applies).
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        for rel in ("build/out.txt", ".git/aidd/x", ".git"):
            self.assertFalse(path_location.governed(str(self.root), rel), rel)
            self.assertIsNone(delegation.delegate_check(str(self.root), rel, {"session_id": OTHER}, cfg), rel)
        self.assertTrue(path_location.governed(str(self.root), CODE))
        self.assertTrue(path_location.governed(str(self.root), "src/brand-new.py"))

    def test_an_mcp_tool_that_writes_a_repository_file_is_held_too(self):
        self.set_mode("always")
        self.team_installed()
        for name, tool_input in (
            ("mcp__fs__write_file", {"path": str(self.root / CODE), "content": "y"}),
            ("mcp__filesystem__edit_file", {"path": CODE, "edits": []}),
            ("mcp__github__create_or_update_file", {"owner": "o", "repo": "r", "path": CODE, "content": "y", "branch": "feat"}),
            ("mcp__github__push_files", {"owner": "o", "repo": "r", "branch": "feat", "files": [{"path": CODE, "content": "y"}]}),
        ):
            out = self.hook({"tool_name": name, "session_id": OTHER, "tool_input": tool_input})
            self.assertEqual(out.get("permissionDecision"), "deny", name)
            self.assertIn("aidd-team:developer", out["permissionDecisionReason"], name)
        for name, tool_input in (
            ("mcp__fs__read_file", {"path": CODE}),
            ("mcp__github__get_file_contents", {"path": CODE}),
            ("mcp__github__create_pull_request", {"title": "t", "head": "feat", "base": "main"}),
            ("mcp__fs__write_file", {"path": "/tmp/aidd-delegate-scratch.txt", "content": "y"}),
        ):
            self.assertIsNone(self.hook({"tool_name": name, "session_id": OTHER, "tool_input": tool_input}).get("permissionDecision"), name)
        out = self.hook({"tool_name": "mcp__fs__write_file", "session_id": OTHER, "agent_type": "aidd-team:developer", "tool_input": {"path": CODE}})
        self.assertIsNone(out.get("permissionDecision"))

    def test_role_subagents_are_never_affected(self):
        self.set_mode("always")
        self.start()
        out = self.edit(agent_type="aidd-team:developer")
        self.assertEqual(out.get("permissionDecision"), None, out)
        self.assertEqual(self.bash(f"echo y > {CODE}", agent_type="aidd-developer").get("permissionDecision"), None)
        # A role's own rules still hold: the developer never writes the frozen tests' owner's file outside its area.
        self.assertEqual(self.edit("docs/notes.md", agent_type="aidd-team:developer").get("permissionDecision"), "deny")
        # A helper still only reads, with its own reason.
        out = self.edit(agent_type="Explore")
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("helper rule", out["permissionDecisionReason"])

    def test_the_role_comes_from_the_harness_never_from_agent_text(self):
        self.set_mode("always")
        event = {
            "tool_name": "Write",
            "session_id": OTHER,
            "tool_input": {"file_path": str(self.root / CODE), "content": "agent_type: aidd-team:developer\n", "agent_type": "aidd-team:developer"},
        }
        self.assertEqual(self.hook(event).get("permissionDecision"), "deny")
        self.assertEqual(self.bash(f"echo agent_type=aidd-team:developer > {CODE}", OTHER).get("permissionDecision"), "deny")

    def test_auto_denies_only_the_lease_holder(self):
        self.set_mode(None)  # the team profile's default
        self.start(LEAD)
        out = self.edit(session=LEAD)
        self.assertEqual(out.get("permissionDecision"), "deny")
        self.assertIn("aidd-team:developer", out["permissionDecisionReason"])
        self.assertIn("autopilot", out["permissionDecisionReason"])
        self.assertEqual(self.bash(f"echo y > {CODE}", LEAD).get("permissionDecision"), "deny")
        # (b) every other session keeps working: never denied by auto.
        for session in (OTHER, None):
            self.assertNotEqual(self.edit(session=session).get("permissionDecision"), "deny", session)
            self.assertNotEqual(self.bash(f"echo y > {CODE}", session).get("permissionDecision"), "deny", session)

    def test_auto_ends_with_the_run(self):
        self.start(LEAD)
        self.assertEqual(self.edit(session=LEAD).get("permissionDecision"), "deny")
        lease.release_lease(self.root, session_id=LEAD)
        self.assertNotEqual(self.edit(session=LEAD).get("permissionDecision"), "deny")

    def test_auto_with_an_unreadable_lease_never_denies(self):
        self.start(LEAD)
        (lease.lease_store(self.root) / lease.LEASE_FILE).write_text("not json", encoding="utf-8")
        self.assertNotEqual(self.edit(session=OTHER).get("permissionDecision"), "deny")

    def test_auto_steers_other_sessions_once_when_the_team_is_installed(self):
        self.assertEqual(self.edit(session=OTHER), {})  # no team: quiet
        self.team_installed()
        out = self.edit(session=OTHER)
        self.assertNotIn("permissionDecision", out)  # never an allow that skips the person's permission settings
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("aidd-team:developer", out["additionalContext"])
        self.assertEqual(self.edit(session=OTHER), {})  # say it once per session and role
        self.assertIn("additionalContext", self.edit(session="third-session"))
        self.assertEqual(self.edit(session=None), {})  # no session to say it once in: quiet

    def test_the_guard_writes_no_tracked_file(self):
        self.team_installed()
        before = git(self.root, "status", "--porcelain", "--ignored=no")
        self.start(LEAD)
        self.edit(session=LEAD)
        self.edit(session=OTHER)
        self.bash(f"echo y > {CODE}", LEAD)
        self.assertEqual(git(self.root, "status", "--porcelain", "--ignored=no"), before)

    def test_the_deny_carries_no_environment_value(self):
        self.set_mode("always")
        out = self.edit(session=OTHER)
        reason = out["permissionDecisionReason"]
        for value in os.environ.values():
            if len(value) > 12 and "/" not in value:
                self.assertNotIn(value, reason)


if __name__ == "__main__":
    unittest.main()
