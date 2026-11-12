"""`aidd risk --suggest`: the ask rules a person always said yes to, at least 10 times, for an action a person can
undo. Never an action that cannot be undone, however many yeses it got."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git

from aidd import records, risk
from aidd.kernel import json_schema
from aidd.cli.commands import work

BY = "agent:claude-code/claude-opus-5-5"


def approval(action: str, outcome: str = "accept", **covers) -> dict:
    data = {"action": action, "question": {"type": "yes_no", "text": f"{action}?"}, "answer": {"outcome": outcome, "words": "yes", "by": "Ada"}}
    return {**data, "covers": covers} if covers else data


class RuleSuggestionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Ada")
        git(self.root, "config", "user.email", "ada@example.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "init")

    def record(self, data: dict, times: int) -> None:
        for _ in range(times):
            records.add_record("decision", data, by=BY, cwd=str(self.root))

    def test_only_an_undoable_ask_with_a_yes_every_time_is_suggested(self):
        self.record(approval("git.push", branch="staging"), 10)  # a shared branch: suggested
        self.record(approval("pr.merge"), 12)  # a person's own decision point: never
        self.record(approval("git.push", branch="main"), 12)  # the default branch: a decision point, never
        self.record(approval("code.edit", paths=["schemas/risks.json"]), 12)  # an edit to the risk rules: never
        self.record(approval("code.edit", paths=["src/auth/login.py"]), 11)  # suggested, and first: more asks
        self.record(approval("git.push.force", branch="feat/x"), 15)  # cannot be undone: never
        self.record(approval("message.send"), 15)  # cannot be undone: never
        self.record(approval("code.edit", paths=["src/payments/charge.py"]), 9)
        self.record(approval("code.edit", "decline", paths=["src/payments/refund.py"]), 1)  # one no in 10: not suggested
        self.record(approval("spec.approve"), 9)  # 9 yeses: not yet
        self.record({"question": {"type": "text", "text": "Name?"}, "answer": {"outcome": "accept", "words": "Refunds", "by": "Ada"}}, 12)
        answer = risk.rule_suggestions(risk.rule_set(None), str(self.root))
        self.assertEqual(answer["min_asks"], 10)
        self.assertEqual(
            [(s["action"], s["branch"], s["area"], s["ask_count"], s["consider"]) for s in answer["suggestions"]],
            [("code.edit", None, "auth", 11, "report"), ("git.push", "shared", None, 10, "report")],
        )
        shown = json.loads(aidd_subprocess("risk", "--suggest", "--json", cwd=self.root).stdout)
        self.assertEqual(json_schema.validate(shown, "risk.schema.json"), [])
        out = aidd_subprocess("risk", "--suggest", cwd=self.root).stdout
        self.assertIn("`{action: git.push, branch: shared, level: report}`", out)
        self.assertNotIn("force", out)

    def test_a_rule_broader_than_a_decision_point_is_never_suggested(self):
        rs = risk.rule_set(None)
        rs.rules = [r for r in rs.rules if r.action != "git.push"] + [risk.Rule("git.push", "ask", source="config")]
        self.record(approval("git.push", branch="staging"), 10)
        self.assertEqual(risk.rule_suggestions(rs, str(self.root))["suggestions"], [], "`git.push` with no branch also covers the default branch")

    def test_a_pulled_record_never_counts(self):
        self.record(approval("git.push", branch="staging"), 10)
        found, _ = records.read_records(str(self.root))
        (records.records_dir(str(self.root)).parent / "records-pulled").write_text(found[0]["id"] + "\n", encoding="utf-8")
        self.assertEqual(risk.rule_suggestions(risk.rule_set(None), str(self.root))["suggestions"], [], "9 of its own: not yet")

    def test_an_mcp_decision_counts_only_with_who_answered(self):
        """The MCP `record` tool runs with no prompt, so its decision counts only when it names who answered."""
        import json

        for by, want in ((None, []), ("Ada", [("git.push", "shared")])):
            with self.subTest(by=by):
                self.setUp()
                self.record(approval("git.push", branch="staging"), 10)
                for path in records.records_dir(str(self.root)).glob("*/*/*.json"):
                    record = json.loads(path.read_text())
                    record["written_with"] = "mcp"
                    record["data"]["answer"].pop("by") if by is None else None
                    path.write_text(json.dumps(record))
                found = risk.rule_suggestions(risk.rule_set(None), str(self.root))["suggestions"]
                self.assertEqual([(s["action"], s["branch"]) for s in found], want)

    def test_a_wildcard_rule_over_an_irreversible_action_is_never_suggested(self):
        rs = risk.rule_set(None)
        rs.actions["db.drop"] = {"description": "Drop a database.", "irreversible": True, "commands": ["db drop*"]}
        rs.actions["db.backup"] = {"description": "Back a database up.", "commands": ["db backup*"]}
        rs.rules.append(risk.Rule("db.*", "ask", source="config"))
        self.record(approval("db.backup"), 10)
        self.assertEqual(risk.rule_suggestions(rs, str(self.root))["suggestions"], [])
        rs.actions.pop("db.drop")
        self.assertEqual([s["action"] for s in risk.rule_suggestions(rs, str(self.root))["suggestions"]], ["db.*"])
        suggestion = risk.rule_suggestions(rs, str(self.root))["suggestions"][0]
        self.assertEqual(work._rule_yaml(suggestion), '`{action: "db.*", level: report}`', "a `*` is quoted, or YAML reads an alias")

    def test_every_built_in_action_that_cannot_be_undone_says_so(self):
        actions = risk.builtin()["actions"]
        never = {a for a, v in actions.items() if v.get("irreversible")}
        for action in ("git.push.force", "git.history.rewrite", "deploy.run", "release.publish", "data.delete", "secret.use", "money.spend", "records.push"):
            self.assertIn(action, never)
        self.assertNotIn("git.push", never)
        self.assertNotIn("pr.merge", never)


if __name__ == "__main__":
    unittest.main()
