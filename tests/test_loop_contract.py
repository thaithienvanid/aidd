"""The loop contract (`loop` in schemas/roles.json), version 1.0.0.

Plan → Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Ship → Learn. Checking the route is
the loop's entry check, not a step; Verify is a step of its own; human feedback edges are drawn in the loop diagram; the
two loops split the steps cleanly; and the contract carries a semantic version that gate events record.
"""

import re
import unittest

from helpers import ROOT, ROUTING, decide, example

from aidd import docs, report, resources, schema

STEPS = ["Plan", "Specify", "Implement", "Verify", "Review", "Ship", "Learn"]


def loop() -> dict:
    return resources.roles()["loop"]


class StepsTests(unittest.TestCase):
    def test_the_steps_in_order(self):
        self.assertEqual(loop()["steps"], STEPS)
        self.assertEqual(resources.load_json("roles.schema.json")["$defs"]["step"]["enum"], STEPS)

    def test_the_route_is_an_entry_check_not_a_step(self):
        data = resources.roles()
        self.assertNotIn("Assess", loop()["steps"])
        for lane, text in loop()["lanes"].items():
            self.assertNotIn("Assess", text, lane)
        for f in loop()["flows"]:
            self.assertNotIn("Assess", f["steps"], f["command"])
        for key, role in data["roles"].items():
            self.assertNotIn("Assess", role["steps"], key)
        for d in data["domains"]:
            self.assertNotIn("Assess", {c["step"] for c in d["checklist"]}, d["slug"])
        entry = loop()["entry"]
        for must in (
            ROUTING,
            "Check the route before the first edit with `aidd assess --paths` (or `aidd assess` on a branch).",
            "Which change to work on is a person's choice; `aidd list` shows the open work and who holds each step.",
            "fast lane is the default",
            "five questions",
            "confidence low",
        ):
            self.assertIn(must, entry)
        for gone in ("aidd next", "picks the lane", "entry rule", "Every change starts"):
            self.assertNotIn(gone, entry)

    def test_every_lane_runs_implement_then_verify(self):
        lanes = loop()["lanes"]
        for lane, text in lanes.items():
            self.assertIn("Implement ⟲ Verify → Review", text, lane)
        self.assertNotIn("Specify", lanes["fast"])
        self.assertIn("Specify → Spec approval →", lanes["spec"])
        self.assertIn("→ Merge approval → Ship", lanes["spec"])

    def test_the_verifier_acts_in_verify_alone(self):
        roles = resources.roles()["roles"]
        self.assertEqual([k for k, r in roles.items() if "Verify" in r["steps"]], ["verifier"])
        self.assertNotIn("Implement", roles["verifier"]["steps"])
        for field in ("done_when", "hands_off"):
            self.assertIn("head SHA", roles["verifier"][field], field)
        self.assertIn("returns to Implement", roles["verifier"]["done_when"])
        self.assertIn("exit codes", roles["verifier"]["does"])  # its text routes work; the runner's exit codes are the evidence

    def test_assess_duties_moved_to_specify_and_implement(self):
        roles = resources.roles()["roles"]
        self.assertIn("`aidd assess`", roles["architect"]["does"])
        self.assertIn("Specify", roles["architect"]["steps"])
        self.assertIn("`aidd assess`", roles["developer"]["starts_when"])
        self.assertEqual(roles["developer"]["steps"], ["Implement"])


class TwoLoopsTests(unittest.TestCase):
    def test_outer_is_human_and_inner_is_the_agent(self):
        lo = loop()["loops"]
        self.assertEqual(lo["outer_steps"], ["Plan", "Ship", "Learn"])
        self.assertEqual(lo["inner_steps"], ["Specify", "Implement", "Verify", "Review"])
        text = docs.render("roles:loops")
        self.assertIn("| Plan, Spec approval, Merge approval, Ship, Learn |", text)
        self.assertIn("| Specify, Implement ⟲ Verify, Review |", text)

    def test_specify_drafts_the_contract_that_spec_approval_freezes(self):
        """The old text had Specify happen "inside a contract the outer loop has frozen", before anything froze it."""
        inner = loop()["loops"]["inner"]
        self.assertNotIn("Inside a contract the outer loop has frozen", inner)
        self.assertIn("drafts the contract", inner)
        self.assertLess(inner.index("Specify"), inner.index("Spec approval then freezes"))

    def test_human_feedback_paths(self):
        edges = [(f["from"], f["to"], f["when"]) for f in loop()["loops"]["feedback"]]
        self.assertEqual(
            edges,
            [
                ("Spec approval", "Specify", "changes requested"),
                ("Merge approval", "Implement", "changes requested"),
                ("Ship", "Learn", "incident, rollback, missed hypothesis"),
                ("Learn", "Plan", "a new change"),
            ],
        )
        notes = " ".join(f["note"] for f in loop()["loops"]["feedback"])
        self.assertIn("review comments", notes)
        self.assertIn("a missed hypothesis is a product decision, taken at Plan", notes)
        text = docs.render("roles:loops")
        self.assertIn("**Human feedback.**", text)
        for a, b, _ in edges:
            self.assertIn(f"**{a} → {b}**", text)


class DiagramTests(unittest.TestCase):
    def setUp(self):
        self.text = docs.loop_diagram()
        self.body = self.text.split("\n", 1)[1].rsplit("```", 1)[0]

    def links(self) -> list[str]:
        """Every link in the order Mermaid numbers them: a chain `a --> b --> c` is two links."""
        out = []
        for line in self.body.splitlines():
            line = line.strip()
            if line.startswith(("classDef", "class ", "linkStyle", "subgraph", "direction", "end")) or not re.search(r"-->|-\.->", line):
                continue
            out += re.findall(r"-\.->|-->", line)
        return out

    def test_human_feedback_edges_are_dashed_and_styled(self):
        for edge in (
            'SpecApproval -.->|"changes requested"| Specify',
            'MergeApproval -.->|"changes requested"| Implement',
            'Ship -.->|"incident, rollback,<br/>missed hypothesis"| Learn',
            'Learn -.->|"a new change"| Plan_again',
        ):
            self.assertIn(edge, self.body)
        self.assertIn('Plan_again(["back to Plan"])', self.body)
        style = re.search(r"^\s*linkStyle ([\d,]+) (.+)$", self.body, re.M)
        self.assertIsNotNone(style)
        assert style is not None
        self.assertIn("stroke-dasharray", style.group(2))
        self.assertIn(docs.FEEDBACK_STYLE, style.group(0))
        dashed = [i for i, kind in enumerate(self.links()) if kind == "-.->"]
        self.assertEqual([int(i) for i in style.group(1).split(",")], dashed)
        self.assertEqual(len(dashed), len(loop()["loops"]["feedback"]))

    def test_the_inner_loop_and_the_approvals(self):
        self.assertIn('Verify -->|"red, or a mismatch"| Implement', self.body)
        self.assertIn(docs.HUMAN_CLASS, self.body)
        self.assertIn("class SpecApproval,MergeApproval human", self.body)
        self.assertNotIn("Ship --> Learn", self.body)  # that path is drawn once, dashed
        self.assertNotIn("Assess", self.body)

    def test_rows_keep_their_direction(self):
        """A link from a node to another row makes Mermaid drop the rows' left-to-right layout."""
        rows: dict[str, str] = {}
        current = None
        for line in self.body.splitlines():
            m = re.match(r"\s*subgraph (\w+)", line)
            if m:
                current = m.group(1)
            elif line.strip() == "end":
                current = None
            else:
                n = re.match(r"\s*(\w+)[\[({]", line)
                if n and current:
                    rows[n.group(1)] = current
        for line in self.body.splitlines():
            ends = re.findall(r"(\w+)\s*(?:-->|-\.->)(?:\|[^|]*\|)?\s*(\w+)", line)
            for a, b in ends:
                if a in rows and b in rows:
                    self.assertEqual(rows[a], rows[b], line)

    def test_every_page_that_draws_the_loop_carries_this_diagram(self):
        for rel in ("docs/TEAM.md", "plugins/aidd-team/skills/aidd-team/SKILL.md"):  # README links it
            self.assertIn(self.text, (ROOT / rel).read_text(encoding="utf-8"), rel)


class VersionTests(unittest.TestCase):
    def test_the_loop_has_a_semantic_version(self):
        version = loop()["version"]
        self.assertEqual(version, "1.0.0")
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn("loop.version", (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8"))
        self.assertIn(f"Loop contract version {version}", docs.render("roles:loops"))
        self.assertTrue(
            schema.validate({**resources.load_json("roles.json"), "loop": {**resources.load_json("roles.json")["loop"], "version": "1.0"}}, "roles.schema.json")
        )

    def test_gate_events_record_it(self):
        ev = report.event(decide(example("03-normal-waiting")), "acme/shop")
        self.assertEqual(ev["loop_version"], loop()["version"])
        self.assertEqual(schema.validate(ev, "event.schema.json"), [])
        self.assertTrue(schema.validate(dict(ev, loop_version="one"), "event.schema.json"))
        self.assertEqual(report.error_event("acme/shop", "1", RuntimeError("x"))["loop_version"], loop()["version"])


class AlwaysLoadedSizeTests(unittest.TestCase):
    """The skill and loop.md load into every session; detail read on a signal lives in its own reference."""

    REFS = ROOT / ".agents" / "skills" / "aidd" / "references"

    def test_loop_md_stays_small_and_points_at_the_signal_references(self):
        loop = (self.REFS / "loop.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(loop.encode()), 10 * 1024)
        skill = (ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8")
        for ref in ("handoff.md", "emergency.md", "containers.md"):
            self.assertTrue((self.REFS / ref).is_file(), ref)
            self.assertIn(f"`references/{ref}`", skill, ref)
        self.assertIn("aidd-handoff", (self.REFS / "handoff.md").read_text(encoding="utf-8"))
        self.assertIn("review_due", (self.REFS / "emergency.md").read_text(encoding="utf-8"))

    def test_each_table_lives_once(self):
        spec = (self.REFS / "spec.md").read_text(encoding="utf-8")
        for block in ("fields:epic", "fields:initiative", "fields:proposal"):
            self.assertNotIn(f"aidd:gen {block} ", spec + " ")
        containers = (self.REFS / "containers.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen fields:initiative~epic -->", containers)
        self.assertEqual(containers.count("| `labels` |"), 1)  # the Initiative's shared rows are not repeated
        routes = (self.REFS / "routes.md").read_text(encoding="utf-8")
        self.assertNotIn("<details><summary>", routes)  # the path lists: `aidd assess --paths` answers for a real path
        self.assertIn("<!-- aidd:gen baseline:summary -->", routes)


class MergeAfterApprovalTests(unittest.TestCase):
    def test_base_is_taken_in_before_merge_approval_not_after(self):
        """The skill said to merge the base branch in often, which contradicted a Merge approval bound to the exact head."""
        text = (ROOT / ".agents" / "skills" / "aidd" / "references" / "loop.md").read_text(encoding="utf-8")
        self.assertNotIn("merge the base branch in often", text)
        self.assertIn("before you ask for Merge approval, not after", text)
        self.assertIn("needs a new Verify and a new approval", text)


if __name__ == "__main__":
    unittest.main()
