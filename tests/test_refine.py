"""`/aidd-team:plan refine`: backlog refinement that proposes and never applies a change without a person's yes. It was
`/aidd-team:refine`, which is now a mode of the plan.

It gathers from what aidd already records, runs the product manager, and the delivery manager beside it when the scope has dates or links, shows one
table a person accepts or rejects line by line, and applies only the accepted lines. It adds no schema, and what it
says about what leaves Spec approval standing holds.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT
from test_plugin_evals import case_yaml, front_matter

from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
COMMAND = TEAM / "commands" / "plan.md"
CASE = ROOT / "evals" / "team" / "refine-proposes-never-applies"


def text() -> str:
    """The plan command's Refine mode section."""
    return COMMAND.read_text(encoding="utf-8").split("\n## Refine mode\n", 1)[1].split("\n## ", 1)[0]


def flow() -> dict:
    return next(f for f in team_registry.roles()["graph"]["flows"] if f["command"] == "plan")


class FlowTests(unittest.TestCase):
    def test_the_flow(self):
        f = flow()
        self.assertEqual(f["steps"], ["Plan"])
        (mode,) = [m for m in f["modes"] if m["name"] == "refine"]
        self.assertEqual(mode["runs"], [["product-manager", "delivery-manager"]])
        self.assertNotIn("delivery-manager", {r for g in f["runs"] for r in g}, "the plan's own chain starts no delivery manager")
        self.assertIn("accepts or rejects", mode["stops_when"])
        self.assertIn("commits the accepted lines", mode["stops_when"])

    def test_the_command_front_matter(self):
        whole = COMMAND.read_text(encoding="utf-8")
        head = whole.split("---")[1]
        self.assertIn("\ndisable-model-invocation: true\n", head + "\n")
        self.assertIn("refine [all | INTENT-x | label:x]", head)
        self.assertIn("<!-- aidd:gen roles:lead -->", whole)


class GatherAndCheckTests(unittest.TestCase):
    def test_it_gathers_from_what_aidd_records(self):
        t = text()
        for must in ("`aidd status --json`", "git log --since", "docs/retros/", "postmortem", "snoozed", "`until`"):
            self.assertIn(must, t, must)

    def test_the_checks(self):
        t = " ".join(text().split())
        for must in (
            "age",
            "stale",
            "too large to review",
            "`relates_to`",
            "duplicate",
            "`duplicates`",
            "slices are all merged or cancelled",
            "orphan",
            "untriaged",
            "WSJF",
            "one reason",
            "dates",
            "dependencies",
        ):
            self.assertIn(must, t, must)

    def test_the_last_run_is_found_by_the_commit_subject_only(self):
        # `git log --grep` reads the whole message, so a body that quotes "refine:" would count as a run.
        t = text()
        self.assertNotIn("--grep", t)
        self.assertIn("%s", t)
        self.assertIn("refine:", t)

    def test_with_no_earlier_run_and_no_retro_it_reads_30_days(self):
        t = " ".join(text().split())
        self.assertIn("latest retrospective", t)
        self.assertIn("last 30 days", t)

    def test_when_to_run_and_what_it_measures(self):
        t = " ".join(text().split())
        for must in ("20 open items", "before planning", "untriaged suggestions reach 0", "stale", "suggestion to decision", "finished Intent"):
            self.assertIn(must, t, must)


class PersonDecidesTests(unittest.TestCase):
    def test_one_table_and_only_accepted_lines_are_applied(self):
        t = " ".join(text().split())
        self.assertIn("one table", t)
        self.assertIn("accepts or rejects every line", t)
        self.assertIn("Apply only the accepted lines", t)
        self.assertIn("Never apply a line without a person's yes", t)
        self.assertIn("no new schema", t.lower())

    def test_triage_is_recorded_as_the_person_who_decided(self):
        t = " ".join(text().split())
        self.assertIn("`triage`", t)
        self.assertIn("`by`", t)

    def test_the_person_commits_the_accepted_lines_on_a_named_branch(self):
        # The git author of the `refine:` commit is the person, so the history proves who decided.
        t = " ".join(text().split())
        self.assertIn("`refine/<today's date>`", t)
        self.assertIn("The person commits", t)
        self.assertIn("never commits", t)
        self.assertNotIn("Each role commits", t)


class SpecApprovalTests(unittest.TestCase):
    """The command says which fields a change of leaves Spec approval standing, and that a new parent voids it."""

    def test_the_fields_it_names_leave_spec_approval_standing(self):
        line = next(ln for ln in text().splitlines() if "leaves Spec approval standing" in ln)
        named = re.findall(r"`([a-z_]+)`", line.split("leaves Spec approval standing", 1)[0])
        self.assertEqual(set(named), {"priority", "blocked_by", "owner", "triage"})

    def test_a_new_parent_voids_spec_approval(self):
        t = " ".join(text().split())
        self.assertIn("A new `parent`", t)
        self.assertIn("`spec.revise`", t)
        self.assertIn("goes back to `draft`", t)


class EvalCaseTests(unittest.TestCase):
    """A plugin eval case checks the command proposes and never applies without a person's yes."""

    def test_the_case(self):
        data, body = front_matter(CASE / "prompt.md")
        self.assertIn("/aidd-team:plan refine", body)
        self.assertIn("Write", data["allowed_tools"])
        self.assertIn("Edit", data["allowed_tools"])
        self.assertEqual(case_yaml(CASE / "case.yaml")["name"], CASE.name)
        graders = {g.stem: front_matter(g)[0] for g in (CASE / "graders").glob("*.md")}
        for tool in ("Write", "Edit"):
            g = next(g for g in graders.values() if g.get("tool") == tool)
            self.assertEqual((g["type"], g["max"]), ("tool_used", 0), tool)
        self.assertTrue(any(g.get("type") == "llm" for g in graders.values()))
        self.assertTrue(any(g.get("input_match") == "aidd-team:product-manager" for g in graders.values()))

    def test_the_fixture_seeds_a_backlog_to_refine(self):
        script = (CASE / "fixture.sh").read_text(encoding="utf-8")
        for must in (".aidd/config.yaml", "suggested_by: role:", "type: intent", "specs/"):
            self.assertIn(must, script, must)
        # The Specs are thin drafts on purpose: they fail `aidd validate`, which this eval does not need.
        self.assertIn("thin drafts", script)
        self.assertIn("aidd validate", script)

    def test_the_case_forbids_a_commit(self):
        g = front_matter(CASE / "graders" / "no-commit.md")[0]
        self.assertEqual((g["type"], g["tool"], g["max"]), ("tool_used", "Bash", 0))
        self.assertIn("commit", g["input_match"])


if __name__ == "__main__":
    unittest.main()
