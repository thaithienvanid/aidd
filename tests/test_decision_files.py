"""The files that hold a person's decision (an Initiative's or a proposal's go_no_go, an exploration's outcome, REVIEW.md's
dismissed findings) are checked on the Edit or Write tool's text. Whatever the guard cannot read is denied for a role or
a helper: a shell write, a git checkout or restore of the file, and an MCP tool's write. The kind of a work item is
read by parsing its front matter, so no TOML spelling of `kind` slips past."""

import io
import json
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo

from aidd import guard

DRAFT = '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-1"\ntitle = "t"\ngoal = "g"\n+++\n\n## Why\n'
GO = 'go_no_go = { decision = "go", by = "@lead", on = "2026-09-01" }\n'
PM, DEV, HELPER = "aidd-team:product-manager", "aidd-team:developer", "general-purpose"


@unittest.skipUnless(shutil.which("git"), "git is required")
class DecisionFileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)
        self.initiative = self.root / "specs" / "INIT-1.md"
        self.initiative.parent.mkdir(exist_ok=True)
        self.initiative.write_text(DRAFT, encoding="utf-8")
        self.decided = Path(tmp.name).resolve() / "decided.md"
        self.decided.write_text(DRAFT.replace('goal = "g"\n', 'goal = "g"\n' + GO), encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "work items"], cwd=self.root, check=True)
        self.sibling = Path(tmp.name).resolve() / "sibling"
        subprocess.run(["git", "worktree", "add", "-q", str(self.sibling), "-b", "sibling"], cwd=self.root, check=True)

    def hook(self, tool: str, tool_input: dict, agent: str | None = PM) -> tuple[str, str]:
        event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(self.root), "session_id": "s1", "hook_event_name": "PreToolUse"}
        if agent:
            event["agent_type"] = agent
        out = io.StringIO()
        guard.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        if not out.getvalue():
            return "allow", ""
        answer = json.loads(out.getvalue())["hookSpecificOutput"]
        return answer.get("permissionDecision", "allow"), answer.get("permissionDecisionReason", "")

    def test_every_toml_spelling_of_the_kind_is_an_initiative(self):
        for label, text in (
            ("quoted key", DRAFT.replace("kind = ", '"kind" = ')),
            ("literal key", DRAFT.replace("kind = ", "'kind' = ")),
            ("escaped value", DRAFT.replace('"initiative"', '"\\u0069nitiative"')),
            ("triple quotes", DRAFT.replace('"initiative"', '"""initiative"""')),
            ("spacing", DRAFT.replace("kind = ", "kind    =   ")),
        ):
            decided = text.replace('goal = "g"\n', 'goal = "g"\n' + GO)
            decision, reason = self.hook("Write", {"file_path": str(self.initiative), "content": decided})
            self.assertEqual(decision, "deny", label)
            self.assertEqual(guard.reason_code(reason), "initiative_decision", label)
        # Taking the kind away in the same edit does not hide the decision: the old text is an Initiative.
        renamed = DRAFT.replace('kind = "initiative"', 'kind = "spec"').replace('goal = "g"\n', 'goal = "g"\n' + GO)
        self.initiative.write_text(DRAFT.replace("kind = ", '"kind" = '), encoding="utf-8")
        self.assertEqual(self.hook("Write", {"file_path": str(self.initiative), "content": renamed})[0], "deny")

    def test_a_shell_write_to_a_decision_file_is_denied_for_a_role_and_a_helper(self):
        sibling = self.sibling / "specs" / "INIT-1.md"
        lines = (
            f"cp {shlex.quote(str(self.decided))} specs/INIT-1.md",
            f"cat {shlex.quote(str(self.decided))} > specs/INIT-1.md",
            "printf 'go_no_go = 1\\n' >> specs/INIT-1.md",
            f"cp {shlex.quote(str(self.decided))} {shlex.quote(str(sibling))}",
            f"cp {shlex.quote(str(self.decided))} specs/INIT-9.md",  # a new work item the guard cannot read either
        )
        for line in lines:
            for agent in (PM, HELPER):
                decision, reason = self.hook("Bash", {"command": line}, agent)
                self.assertEqual(decision, "deny", (line, agent))
                if agent == PM:
                    self.assertIn("use the Edit or Write tool so the change can be checked", reason, line)
        # The person's own session is unaffected.
        self.assertEqual(self.hook("Bash", {"command": lines[0]}, None)[0], "allow")

    def test_a_proposal_and_an_exploration_too(self):
        proposal = self.root / "proposals" / "PROP-1" / "proposal.md"
        exploration = self.root / "docs" / "design" / "SPEC-1" / "exploration.md"
        for path in (proposal, exploration):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('+++\nid = "x"\n+++\n', encoding="utf-8")
            rel = path.relative_to(self.root).as_posix()
            for line in (f"echo 'outcome = 1' >> {rel}", f"cp {shlex.quote(str(self.decided))} {rel}"):
                decision, reason = self.hook("Bash", {"command": line}, PM)
                self.assertEqual(decision, "deny", line)
                self.assertIn("use the Edit or Write tool so the change can be checked", reason, line)
            self.assertEqual(self.hook("Bash", {"command": f"echo x >> {rel}"}, None)[0], "allow")

    def test_git_checkout_and_restore_of_a_decision_file_are_writes(self):
        for line in ("git checkout sibling -- REVIEW.md", "git restore --source=sibling REVIEW.md", "git checkout sibling -- specs/INIT-1.md"):
            for agent in (DEV, HELPER):
                self.assertEqual(self.hook("Bash", {"command": line}, agent)[0], "deny", (line, agent))
            self.assertEqual(self.hook("Bash", {"command": line}, None)[0], "allow", line)
        self.assertEqual(self.hook("Bash", {"command": "git checkout sibling"}, DEV)[0], "allow")  # a branch switch names no file

    def test_an_mcp_write_meets_the_same_rules(self):
        review = self.root / "REVIEW.md"
        for tool, tool_input in (
            ("mcp__filesystem__write_file", {"path": str(review), "content": "x"}),
            ("mcp__filesystem__edit_file", {"path": "REVIEW.md", "edits": [{"oldText": "a", "newText": "b"}]}),
            ("mcp__filesystem__write_file", {"path": str(self.initiative), "content": "x"}),
        ):
            for agent in (DEV, PM, HELPER):
                self.assertEqual(self.hook(tool, tool_input, agent)[0], "deny", (tool, agent))
        self.assertEqual(self.hook("mcp__filesystem__write_file", {"path": str(review), "content": "x"}, None)[0], "allow")
        self.assertEqual(self.hook("mcp__filesystem__read_file", {"path": str(review)}, HELPER)[0], "allow")


if __name__ == "__main__":
    unittest.main()
