"""The loop contract (`loop` in schemas/roles.json), version 1.0.0.

Plan → Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Merge → Roll out → Learn. Checking the route is
the loop's entry check, not a step; Verify is a step of its own; human feedback edges are drawn in the loop diagram; the
two loops split the steps cleanly; and the contract carries a semantic version.
"""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

import budgets

from helpers import ROOT, ROUTING, git, mermaid_arrows

from aidd import records

from aidd.docsgen import generate
from aidd.docsgen import diagrams
from aidd.kernel import json_schema, resources
from aidd.knowledge import team_registry
from aidd.risk import rules, suggestions

STEPS = ["Plan", "Specify", "Implement", "Verify", "Review", "Merge", "Roll out", "Learn"]


def loop() -> dict:
    return team_registry.roles()["loop"]


class StepsTests(unittest.TestCase):
    def test_the_steps_in_order(self):
        self.assertEqual(loop()["steps"], STEPS)
        self.assertEqual(resources.load_json("roles.schema.json")["$defs"]["step"]["enum"], STEPS)

    def test_the_route_is_an_entry_check_not_a_step(self):
        data = team_registry.roles()
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
            "Before the first edit, get the route: `aidd risk --paths <planned paths>` gives the route",
            "Which change to work on is a person's choice; `aidd status` shows the open work and each item's next step.",
            "No Spec is the default",
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
        self.assertIn("→ Merge approval → Merge → Roll out", lanes["spec"])

    def test_the_verifier_acts_in_verify_alone(self):
        roles = team_registry.roles()["roles"]
        self.assertEqual([k for k, r in roles.items() if "Verify" in r["steps"]], ["verifier"])
        self.assertNotIn("Implement", roles["verifier"]["steps"])
        for field in ("done_when", "hands_off"):
            self.assertIn("head SHA", roles["verifier"][field], field)
        self.assertIn("returns to Implement", roles["verifier"]["done_when"])
        self.assertIn("exit codes", roles["verifier"]["does"])  # its text routes work; the runner's exit codes are the evidence

    def test_route_duties_moved_to_specify_and_implement(self):
        roles = team_registry.roles()["roles"]
        self.assertIn("`aidd risk --paths`", roles["architect"]["does"])
        self.assertIn("Specify", roles["architect"]["steps"])
        self.assertIn("`aidd risk --paths` gave minor", roles["developer"]["starts_when"])
        self.assertEqual(roles["developer"]["steps"], ["Implement"])


class StagesAndGatesTests(unittest.TestCase):
    """`loop.stages` group the steps for people, and `loop.gates` are the fixed points where a person decides."""

    def test_every_step_sits_in_exactly_one_stage_in_the_steps_order(self):
        stages = loop()["stages"]
        self.assertEqual([s["name"] for s in stages], ["Plan", "Design", "Build", "Test", "Deploy", "Maintain"])
        self.assertEqual([step for s in stages for step in s["steps"]], loop()["steps"])
        for s in stages:
            self.assertTrue(s["steps"], s["name"])

    def test_every_gate_names_a_stage_a_step_and_built_in_ask_actions(self):
        steps, stages = loop()["steps"], {s["name"]: s["steps"] for s in loop()["stages"]}
        risks = resources.load_json("risks.json")
        asks = {r["action"] for r in risks["rules"] if r["level"] == "ask" and not r.keys() - {"action", "level", "reason"}}
        gates = loop()["gates"]
        for gate in gates:
            with self.subTest(gate=gate["name"]):
                self.assertIn(gate["stage"], stages)
                self.assertIn(gate["before"], steps)
                previous = steps[steps.index(gate["before"]) - 1]
                self.assertIn(previous, stages[gate["stage"]], "a gate ends the stage of the step before it")
                for action in gate["actions"]:
                    self.assertIn(action, risks["actions"])
                    self.assertIn(action, asks, "a gate's action is a built-in ask rule")
        befores = [steps.index(g["before"]) for g in gates]
        self.assertEqual(befores, sorted(befores), "the gates in the loop's order")
        self.assertEqual([g["name"] for g in gates], ["Intent agreement", "Spec approval", "Merge approval", "Production release"])

    def test_the_loop_diagram_and_the_loop_text_draw_every_gate(self):
        from aidd.docsgen import diagrams, team_reference

        names = [g["name"] for g in loop()["gates"]]
        diagram = diagrams.loop_diagram()
        points = team_reference.loop_points(loop(), loop()["steps"], gates=True)
        for name in names:
            with self.subTest(gate=name):
                self.assertIn(name, diagram)
                self.assertIn(name, points)
        self.assertEqual([p for p in points if p in names], names, "each gate in the loop's order")

    def test_no_gate_action_is_ever_suggested_lower(self):
        points = {action for action, _, _ in suggestions.DECISION_POINTS}
        actions = resources.load_json("risks.json")["actions"]
        for gate in loop()["gates"]:
            for action in gate["actions"]:
                with self.subTest(action=action):
                    self.assertTrue(action in points or actions[action].get("irreversible"), "a decision point, or an action no one can undo")

    def test_intent_agreement_is_an_ask_a_decision_point_and_a_gate(self):
        risks = resources.load_json("risks.json")
        self.assertIn(("intent.agree", "ask"), [(r["action"], r["level"]) for r in risks["rules"] if not r.keys() - {"action", "level", "reason"}])
        order = list(risks["actions"])
        self.assertLess(order.index("intent.agree"), order.index("spec.approve"))
        self.assertIn(("intent.agree", None, None), suggestions.DECISION_POINTS)
        self.assertEqual([g["actions"] for g in loop()["gates"] if "intent.agree" in g["actions"]], [["intent.agree"]])

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_intent_agreement_is_never_suggested_however_many_yeses(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "Ada")
            git(root, "config", "user.email", "ada@example.com")
            git(root, "commit", "-q", "--allow-empty", "-m", "init")
            data = {"action": "intent.agree", "question": {"type": "approval", "text": "Agree?"}, "answer": {"outcome": "accept", "words": "yes", "by": "Ada"}}
            for _ in range(suggestions.MIN_ASKS + 2):
                records.add_record("decision", data, by="agent:claude-code/claude-opus-5-5", cwd=str(root))
            found = suggestions.rule_suggestions(rules.rule_set(None), str(root))["suggestions"]
            self.assertEqual([s for s in found if s["action"] == "intent.agree"], [])


class TwoLoopsTests(unittest.TestCase):
    def test_outer_is_human_and_inner_is_the_agent(self):
        lo = loop()["loops"]
        self.assertEqual(lo["outer_steps"], ["Plan", "Merge", "Roll out", "Learn"])
        self.assertEqual(lo["inner_steps"], ["Specify", "Implement", "Verify", "Review"])
        text = generate.render("roles:loops")
        self.assertIn("| Plan, Intent agreement, Spec approval, Merge approval, Merge, Production release, Roll out, Learn |", text)
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
                ("Roll out", "Learn", "incident, rollback, missed hypothesis"),
                ("Learn", "Plan", "a new change"),
            ],
        )
        notes = " ".join(f["note"] for f in loop()["loops"]["feedback"])
        self.assertIn("review comments", notes)
        self.assertIn("a missed hypothesis is a product decision, taken at Plan", notes)
        text = generate.render("roles:loops")
        self.assertIn("**Human feedback.**", text)
        for a, b, _ in edges:
            self.assertIn(f"**{a} → {b}**", text)


class DiagramTests(unittest.TestCase):
    def setUp(self):
        self.text = diagrams.loop_diagram()
        self.body = self.text.split("\n", 1)[1].rsplit("```", 1)[0]

    def links(self) -> list[str]:
        """Every link in the order Mermaid numbers them: a chain `a --> b --> c` is two links."""
        out = []
        for line in self.body.splitlines():
            line = line.strip()
            if line.startswith(("classDef", "class ", "linkStyle", "subgraph", "direction", "end")) or not mermaid_arrows(line):
                continue
            out += mermaid_arrows(line)
        return out

    def test_human_feedback_edges_are_dashed_and_styled(self):
        for edge in (
            'SA -.->|"changes requested"| Specify',
            'MA -.->|"changes requested"| Implement',
            'Roll_out -.->|"incident, rollback,<br/>missed hypothesis"| Learn',
            'Learn -.->|"a new change"| Plan_again',
        ):
            self.assertIn(edge, self.body)
        self.assertIn('Plan_again(["back to Plan"])', self.body)
        style = re.search(r"^\s*linkStyle ([\d,]+) (.+)$", self.body, re.M)
        self.assertIsNotNone(style)
        assert style is not None
        self.assertIn("stroke-dasharray", style.group(2))
        self.assertIn(diagrams.FEEDBACK_STYLE, style.group(0))
        dashed = [i for i, arrow in enumerate(self.links()) if arrow == "-.->"]
        self.assertEqual([int(i) for i in style.group(1).split(",")], dashed)
        self.assertEqual(len(dashed), len(loop()["loops"]["feedback"]))

    def test_the_inner_loop_and_the_approvals(self):
        self.assertIn('Verify -->|"red, or a mismatch"| Implement', self.body)
        self.assertIn(diagrams.HUMAN_CLASS, self.body)
        self.assertIn("class IA,SA,MA,PR human", self.body)
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
        self.assertIn(f"Loop contract version {version}", generate.render("roles:loops"))
        self.assertTrue(
            json_schema.validate(
                {**resources.load_json("roles.json"), "loop": {**resources.load_json("roles.json")["loop"], "version": "1.0"}}, "roles.schema.json"
            )
        )


class AlwaysLoadedSizeTests(unittest.TestCase):
    """The skill and loop.md load into every session; detail read on a signal lives in its own reference."""

    REFS = ROOT / ".agents" / "skills" / "aidd" / "references"

    def test_loop_md_stays_small_and_points_at_the_signal_references(self):
        loop = (self.REFS / "loop.md").read_text(encoding="utf-8")
        self.assertTrue(budgets.within(len(loop.encode()), 10 * 1024), len(loop.encode()))
        skill = (ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8")
        for ref in ("handoff.md", "emergency.md", "intents.md"):
            self.assertTrue((self.REFS / ref).is_file(), ref)
            self.assertIn(f"`references/{ref}`", skill, ref)
        self.assertIn("aidd-handoff", (self.REFS / "handoff.md").read_text(encoding="utf-8"))
        self.assertIn("review_due", (self.REFS / "emergency.md").read_text(encoding="utf-8"))

    def test_the_skill_stays_small(self):
        # SKILL.md loads into every session and is preloaded into the developer, verifier, architect, and product manager.
        # 13.5 KiB, at 13,618 bytes on 2026-10-20: the role average in test_team_roles_and_flows.py only caps its sum.
        size = len((ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_bytes())
        self.assertTrue(budgets.within(size, 13.5 * 1024), size)

    REFERENCE_KIB = budgets.REFERENCE_KIB  # each reference's cap, with the others in tests/budgets.py

    def test_each_reference_keeps_its_budget(self):
        # loop.md keeps its own cap, in test_loop_md_stays_small_and_points_at_the_signal_references.
        found = sorted(p.name for p in self.REFS.glob("*.md") if p.name != "loop.md")
        self.assertEqual(found, sorted(self.REFERENCE_KIB), "a new reference names its cap in REFERENCE_KIB")
        for name, kib in self.REFERENCE_KIB.items():
            with self.subTest(reference=name):
                size = len((self.REFS / name).read_bytes())
                self.assertTrue(budgets.within(size, kib * 1024), f"{name}: {size} bytes, cap {kib} KiB")

    def test_each_table_lives_once(self):
        spec = (self.REFS / "spec.md").read_text(encoding="utf-8")
        self.assertNotIn("aidd:gen fields:proposal ", spec + " ")
        intents = (self.REFS / "intents.md").read_text(encoding="utf-8")
        for block in ("fields:intent~spec", "fields:proposal~intent"):  # each table once, past the rows another one shows
            self.assertEqual(intents.count(f"<!-- aidd:gen {block} -->"), 1, block)
        routes = (self.REFS / "routes.md").read_text(encoding="utf-8")
        self.assertNotIn("<details><summary>", routes)  # the path lists: `aidd risk --paths` answers for a real path
        self.assertIn("`aidd risk --paths", routes)


class MergeAfterApprovalTests(unittest.TestCase):
    def test_base_is_taken_in_before_merge_approval_not_after(self):
        """The skill said to merge the base branch in often, which contradicted a Merge approval bound to the exact head."""
        text = (ROOT / ".agents" / "skills" / "aidd" / "references" / "loop.md").read_text(encoding="utf-8")
        self.assertNotIn("merge the base branch in often", text)


class ReferencePastCapTests(unittest.TestCase):
    """P8: a reference past its cap is a note in the test report, never a failure, and a reference within it is not named."""

    def test_the_note_names_each_reference_past_its_cap_and_only_those(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "emergency.md").write_bytes(b"x" * int(2 * 1024 * 1.02))  # cap 2 KiB: past it, within the headroom
            (Path(folder) / "handoff.md").write_bytes(b"x" * int(4.5 * 1024 * 0.99))  # just under its cap
            (Path(folder) / "security.md").write_bytes(b"x" * 1024)
            self.assertEqual(budgets.references_past_cap(Path(folder)), ["emergency.md (2.0 of 2 KiB)"])

    def test_the_test_report_carries_the_note_only_when_a_reference_is_past_its_cap(self):
        import run

        refs = ROOT / ".agents" / "skills" / "aidd" / "references"
        past = budgets.references_past_cap(refs)
        note = run.references_note()
        self.assertEqual(bool(note), bool(past))
        for name in past:
            self.assertIn(name, note)
        self.assertLess(len(past), len(budgets.REFERENCE_KIB), "a note that names every reference is ignored")


if __name__ == "__main__":
    unittest.main()
