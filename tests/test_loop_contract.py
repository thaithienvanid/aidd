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

from aidd import config, records

from aidd.docsgen import generate
from aidd.docsgen import diagrams
from aidd.kernel import json_schema, resources
from aidd.knowledge import team_registry
from aidd.risk import routes, rules, suggestions

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
        for route, text in loop()["routes"].items():
            self.assertNotIn("Assess", text, route)
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

    def test_every_route_runs_implement_then_verify(self):
        routes = loop()["routes"]
        for route, text in routes.items():
            self.assertIn("Implement ⟲ Verify → Review", text, route)
        self.assertNotIn("Specify", routes["minor"])
        for route in ("normal", "major"):
            self.assertIn("Specify → Spec approval →", routes[route])
            self.assertIn("→ Merge approval → Merge → Roll out", routes[route])

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

    def test_each_gate_is_one_decision_right_named_by_the_gate_and_no_right_has_an_id(self):
        """The decision list and the gate list say the same names: a person reads "Merge approval" in both, and no decision
        is called "the release" while a deploy has no right of its own."""
        rights = [d["decision"] for d in loop()["decision_rights"]]
        for gate in loop()["gates"]:
            with self.subTest(gate=gate["name"]):
                named = [d for d in loop()["decision_rights"] if d.get("gate") == gate["name"]]
                self.assertEqual(len(named), 1, rights)
                self.assertEqual(named[0]["loop"], "outer")
                self.assertTrue(named[0]["decision"].startswith(f"{gate['name']}:"), "a person reads the gate's name in both")
                raw = next(d for d in resources.load_json("roles.json")["loop"]["decision_rights"] if d.get("gate") == gate["name"])
                self.assertNotIn(gate["name"], raw["decision"], "the file names the gate once, in `gate`")
        self.assertEqual({d["gate"] for d in loop()["decision_rights"] if "gate" in d} - {g["name"] for g in loop()["gates"]}, set(), "a gate that exists")
        self.assertEqual([r for r in rights if re.match(r"D[0-9]+\b", r)], [], "no D-ids")
        release = next(d for d in loop()["decision_rights"] if d.get("gate") == "Production release")
        self.assertIn("deploy.run", release["decision"])
        self.assertIn("never covers it", release["decided_by"], "a delegation never decides a deploy")
        merge = next(d for d in loop()["decision_rights"] if d.get("gate") == "Merge approval")
        self.assertNotIn("deploy", merge["decision"], "the merge is not the release")

    def test_a_gates_decision_is_found_by_its_gate_key_and_never_by_the_words_of_its_text(self):
        """Reword every gate's decision text: `aidd explain` and the step reasons still find each, and read the same fields."""
        import copy
        from unittest import mock

        from aidd.knowledge import explanations
        from aidd.workitems import step_reasons

        data = copy.deepcopy(team_registry.roles())
        before = {g["name"]: [e for e in explanations.explain(g["name"]) if e["type"] == "decision"] for g in data["loop"]["gates"]}
        for d in data["loop"]["decision_rights"]:
            d["decision"] = "Reworded: " + d["decision"]
        reasons = {code: step_reasons.step_reason(code) for code in ("intent.agree", "spec.approve", "pr.merge")}
        with mock.patch.object(team_registry, "roles", return_value=data), mock.patch.object(step_reasons, "_loop", return_value=data["loop"]):
            for g in data["loop"]["gates"]:
                with self.subTest(gate=g["name"]):
                    found = [e for e in explanations.explain(g["name"]) if e["type"] == "decision"]
                    self.assertEqual([e["why"] for e in found], [e["why"] for e in before[g["name"]]])
            for code, reason in reasons.items():
                with self.subTest(code=code):
                    self.assertEqual(step_reasons.step_reason(code), reason)

    def test_the_explanation_and_the_step_reason_of_each_gate_read_its_decision_right(self):
        from aidd.knowledge import explanations
        from aidd.workitems import step_reasons

        for gate in loop()["gates"]:
            with self.subTest(gate=gate["name"]):
                found = [e for e in explanations.explain(gate["name"]) if e["type"] == "decision"]
                self.assertEqual(len(found), 1)
                right = step_reasons.decision_right(gate["name"])
                self.assertIn(right["decided_by"], found[0]["why"])
        for code, gate in (("intent.agree", "Intent agreement"), ("spec.approve", "Spec approval"), ("pr.merge", "Merge approval")):
            with self.subTest(code=code):
                self.assertIn(f"the loop leaves {gate} to a person", step_reasons.step_reason(code))

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
            data = {"action": "intent.agree", "question": {"type": "yes_no", "text": "Agree?"}, "answer": {"outcome": "accept", "words": "yes", "by": "Ada"}}
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
        self.assertTrue(
            budgets.within(len(loop.encode()), budgets.LOOP_BYTES),
            budgets.make_room("loop.md", len(loop.encode()), budgets.LOOP_BYTES, cost=budgets.cost_of("loop")),
        )
        skill = (ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8")
        for ref in ("handoff.md", "emergency.md", "intents.md"):
            self.assertTrue((self.REFS / ref).is_file(), ref)
            self.assertIn(f"`references/{ref}`", skill, ref)
        self.assertIn("aidd-handoff", (self.REFS / "handoff.md").read_text(encoding="utf-8"))
        self.assertIn("backfill_due", (self.REFS / "emergency.md").read_text(encoding="utf-8"))

    def test_the_skill_stays_small(self):
        # SKILL.md loads into every session and is preloaded into the product manager, architect, product designer, and developer
        # (`preload` in schemas/roles.json). Its cap and the cost it tracks are in budgets.CAPS; each role's start total in
        # test_team_roles_and_flows.py bounds what it adds to a role.
        size = len((ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_bytes())
        self.assertTrue(budgets.within(size, budgets.SKILL_BYTES), budgets.make_room("SKILL.md", size, budgets.SKILL_BYTES, cost=budgets.cost_of("skill")))

    def test_the_init_word_ends_with_running_init(self):
        # After the questions, `/aidd init` runs `aidd init` with the answers.
        skill = (ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8")
        (line,) = (x for x in skill.splitlines() if x.startswith("- `init`:"))
        self.assertTrue(line.endswith("Then run `aidd init` with their flags."), line)

    def test_each_reference_keeps_to_the_limit_for_references(self):
        # loop.md keeps its own cap, in test_loop_md_stays_small_and_points_at_the_signal_references. A reference near the limit is
        # restructured by topic, as spec.md was: a short main file, with each detail in the reference its step loads.
        for path in sorted(self.REFS.glob("*.md")):
            if path.name == "loop.md":
                continue
            with self.subTest(reference=path.name):
                size = len(path.read_bytes())
                self.assertTrue(
                    budgets.within(size, budgets.REFERENCE_BYTES),
                    budgets.make_room(path.name, size, budgets.REFERENCE_BYTES, cost=budgets.cost_of("reference")),
                )

    def test_each_template_keeps_to_the_limit_for_templates(self):
        assets = self.REFS.parent / "assets"
        for path in sorted(assets.glob("*.md")):
            with self.subTest(template=path.name):
                size = len(path.read_bytes())
                self.assertTrue(
                    budgets.within(size, budgets.TEMPLATE_BYTES), budgets.make_room(path.name, size, budgets.TEMPLATE_BYTES, cost=budgets.cost_of("template"))
                )

    def test_each_table_lives_once(self):
        spec = (self.REFS / "spec.md").read_text(encoding="utf-8")
        self.assertNotIn("aidd:gen fields:proposal ", spec + " ")
        for ref, block in (("intents.md", "fields:intent~spec"), ("proposal.md", "fields:proposal~intent")):  # each table once, past the rows another one shows
            self.assertEqual((self.REFS / ref).read_text(encoding="utf-8").count(f"<!-- aidd:gen {block} -->"), 1, block)
        routes = (self.REFS / "routes.md").read_text(encoding="utf-8")
        self.assertNotIn("<details><summary>", routes)  # the path lists: `aidd risk --paths` answers for a real path
        self.assertIn("`aidd risk --paths", routes)


class MergeAfterApprovalTests(unittest.TestCase):
    def test_base_is_taken_in_before_merge_approval_not_after(self):
        """The skill said to merge the base branch in often, which contradicted a Merge approval bound to the exact head."""
        text = (ROOT / ".agents" / "skills" / "aidd" / "references" / "loop.md").read_text(encoding="utf-8")
        self.assertNotIn("merge the base branch in often", text)


class ImplementPreconditionTests(unittest.TestCase):
    """Every way a Spec becomes approved leaves front matter that Implement accepts, so no approval path ends in a stop."""

    SKILL = ROOT / ".agents" / "skills" / "aidd"
    TEAM = ROOT / "plugins" / "aidd-team"
    # What each text states about the front matter of an approved Spec: a delegated approval sets `delegate_answer` with
    # no `approved_by`, and a route whose `spec.approve` does not ask sets `approved_at` alone.
    PRECONDITIONS = {
        "implement flow": TEAM / "commands" / "implement.md",
        "developer role": TEAM / "agents" / "developer.md",
    }
    # Where a reported approval is set, and the words that say its front matter: `approved_at` with no `approved_by`.
    SETTERS = {
        "state table": (SKILL / "references" / "state.md", "approved, with `approved_at` and no `approved_by`", "you say you go on"),
        "loop step 5": (SKILL / "references" / "loop.md", "say you go on and set `status: approved`", "say you go on"),
        "specify step 10": (
            TEAM / "commands" / "specify.md",
            "set `status: approved` and `approved_at` with no `approved_by`",
            "`aidd risk --action spec.approve",
        ),
    }

    def levels_reached(self) -> dict[str, list[tuple[str, str]]]:
        """Each level `spec.approve` can have, with the (profile, route) pairs that give it, read from the rules: the
        profiles' own rules, and a config rule at each level for every route that writes a Spec first."""
        found: dict[str, list[tuple[str, str]]] = {}
        spec_routes = list(config.SPEC_FIRST_ROUTES)
        for profile in ("solo", "team"):
            for level in ("ask", "report", "allow"):
                for route in spec_routes:
                    text = f'aidd_version: "1.0.0"\nprofile: {profile}\nrisks:\n  rules:\n    - {{action: spec.approve, route: {route}, level: {level}}}\n'
                    got = routes.spec_approval_level(config.load_text(text), route)
                    found.setdefault(got, []).append((profile, route))
            for route in spec_routes:
                found.setdefault(routes.spec_approval_level(config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n'), route), []).append(
                    (profile, route)
                )
        return found

    def sentence_with(self, text: str, *terms: str) -> str:
        return next((x for x in re.split(r"(?<=[.:|])\s+", text) if all(t in x for t in terms)), "")

    def test_every_level_a_route_can_have_meets_a_precondition(self):
        """The levels come from the rules, not from the texts: `ask` leaves a person's yes, and every other level a Spec can
        have is named beside `spec.approve` in each text that says which front matter holds."""
        reached = self.levels_reached()
        self.assertEqual(set(reached), {"ask", "report", "allow"})  # each level occurs on a Spec route, in a config or a profile
        for name, path in self.PRECONDITIONS.items():
            with self.subTest(name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("`delegate_answer`", text)
                for level in set(reached) - {"ask"}:
                    self.assertTrue(self.sentence_with(text, "`spec.approve`", f"`{level}`"), level)

    def test_each_setter_of_an_unasked_approval_says_which_front_matter_to_set(self):
        reached = self.levels_reached()
        for name, (path, words, anchor) in self.SETTERS.items():
            with self.subTest(name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(words, text)
                for level in set(reached) - {"ask"}:
                    self.assertTrue(self.sentence_with(text, anchor, f"`{level}`"), (name, level))

    def test_the_loop_starts_implement_only_once_the_spec_is_approved(self):
        self.assertIn("Start Implement only once the Spec is approved.", (self.SKILL / "references" / "loop.md").read_text(encoding="utf-8"))


class RuleStatedOnceTests(unittest.TestCase):
    """B8: a rule lives in one place, and the text beside it points there. `SKILL.md` loads with `loop.md` in every session,
    so a hard rule it states is never stated again in `loop.md` or in a reference, and a table a reference generates is never
    restated in the prose around it. Each row names where the rule stays and the old wording that must not come back."""

    SKILL = ROOT / ".agents" / "skills" / "aidd"
    # (the words that keep the rule in SKILL.md, the files that point to it, the restatement removed from each)
    HARD_RULES = [
        ("A change with no Spec in an `ask` area asks once", ["loop.md", "risk.md"], "a change with no Spec in an `ask` area asks once"),
        ("fix the code, not the test", ["loop.md"], "fix the code, not the test"),
        ("Only the person's own words in this chat are a yes", ["risk.md"], "only the person's own words in this chat are a yes"),
        ("`ask` means stop and hand back with a handoff note", ["risk.md", "handoff.md"], "`ask` means stop"),
        ("`ask` means stop and hand back with a handoff note", ["handoff.md"], "an `ask` is a stop"),
        ("Never edit `.aidd/config.yaml` or the harness's ask rules unless the person asks", ["risk.md"], "edit it only when they ask you to"),
        ("Never edit `.aidd/config.yaml` or the harness's ask rules unless the person asks", ["risk.md"], "change a rule only on their word"),
        ("add a `revisions` entry, and ask for approval again", ["loop.md"], "add a `revisions` entry"),
        # These two keep their owner sentence only: the old restatement was a short fragment, and banning a fragment also
        # bans honest text ("at most 300 words") while a paraphrase passes.
        ("Never re-run a test until it passes", [], ""),
        ("at most 3 per Task", [], ""),
    ]

    def read(self, name: str) -> str:
        return (self.SKILL / "SKILL.md" if name == "SKILL.md" else self.SKILL / "references" / name).read_text(encoding="utf-8").lower()

    def test_a_hard_rule_stays_in_the_skill_and_its_restatement_stays_out_of_the_files_that_point_to_it(self):
        for kept, files, restated in self.HARD_RULES:
            with self.subTest(kept=kept[:40]):
                self.assertIn(kept.lower(), self.read("SKILL.md"), "the whole owner sentence, so deleting the rule fails here")
            for name in files:
                with self.subTest(kept=kept[:40], file=name, restated=restated[:40]):
                    self.assertNotIn(restated.lower(), self.read(name))

    def test_a_reference_does_not_restate_the_table_it_generates(self):
        profiles = (self.SKILL / "references" / "profiles.md").read_text(encoding="utf-8")
        prose, table = profiles.split("<!-- aidd:gen profiles -->")[0], profiles.split("<!-- aidd:gen profiles -->")[1]
        for said in ("One person directs the agents and decides", "Ask for Spec approval on major only", "Ask for Spec approval on normal and major"):
            with self.subTest(said):
                self.assertNotIn(said, prose)
        self.assertIn("One person directs the agents and decides", table)
        docs = (self.SKILL / "references" / "spec-docs.md").read_text(encoding="utf-8")
        table = docs.split("<!-- aidd:gen fields:doc -->")[1].split("<!-- aidd:end -->")[0]
        # The table says what `frozen` means. The two bullets under it hold what the table does not: a frozen document is in no
        # Task's scope, and a living one is checked to exist. A trim once
        # removed both as a restatement of the table, and lost those rules.
        for owner in ("Default true: approved with the Spec", "False for a living document"):
            self.assertIn(owner, table)
        for rule in ("is never in a Task's scope", "`aidd validate` checks it exists"):
            with self.subTest(rule):
                self.assertIn(rule, docs.split("<!-- aidd:end -->", 1)[1] if "<!-- aidd:gen fields:doc -->" in docs else docs)
                self.assertNotIn(rule, table)


class NearClassLimitTests(unittest.TestCase):
    """A file above the headroom line of its class limit is a note in the test report, never a failure, and a file under it is not
    named: the note is the signal to restructure by topic."""

    def test_the_note_names_each_file_above_the_line_of_its_class_limit_and_only_those(self):
        with tempfile.TemporaryDirectory() as refs, tempfile.TemporaryDirectory() as assets:
            (Path(refs) / "spec.md").write_bytes(b"x" * int(budgets.REFERENCE_BYTES * 0.95))  # above the line: named
            (Path(refs) / "risk.md").write_bytes(b"x" * int(budgets.REFERENCE_BYTES * budgets.LINE))  # at the line: not named
            (Path(refs) / "loop.md").write_bytes(b"x" * budgets.REFERENCE_BYTES)  # loop.md keeps its own cap
            (Path(assets) / "DESIGN.md").write_bytes(b"x" * int(budgets.TEMPLATE_BYTES * 0.92))
            (Path(assets) / "tokens.json").write_bytes(b"x" * budgets.TEMPLATE_BYTES)  # not a Markdown template
            self.assertEqual(budgets.near_class_limit(Path(refs), Path(assets)), ["spec.md (95% of 20,000 bytes)", "DESIGN.md (92% of 24,576 bytes)"])

    def test_the_test_report_carries_the_note_only_when_a_file_is_near_its_class_limit(self):
        import run

        skill = ROOT / ".agents" / "skills" / "aidd"
        near = budgets.near_class_limit(skill / "references", skill / "assets")
        note = run.references_note()
        self.assertEqual(bool(note), bool(near))
        for name in near:
            self.assertIn(name, note)


class LongSectionTests(unittest.TestCase):
    """A section past budgets.SECTION_TOKENS is a note in the test report, never a failure: the section, not the file, is what a
    reader holds."""

    def test_a_section_past_the_line_is_named_with_its_size_and_one_at_it_is_not(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            at = "x" * (budgets.SECTION_TOKENS * 4 - 1)  # one line and its newline: exactly SECTION_TOKENS estimated tokens
            (root / "a.md").write_text(f"top\n## At\n{at}\n## Past\n{at}xx\n```\n## not a heading\n```\n## Short\nshort\n", encoding="utf-8")
            notes = budgets.long_sections([root / "a.md"], root)
            self.assertEqual(len(notes), 1, notes)
            self.assertRegex(notes[0], r"^a\.md ## Past \([\d,]+ tokens\)$")

    def test_the_note_is_quiet_for_a_file_with_no_long_section(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "b.md").write_text("## One\nshort\n## Two\nshort\n", encoding="utf-8")
            self.assertEqual(budgets.long_sections([Path(folder) / "b.md"], Path(folder)), [])

    def test_the_test_report_names_the_long_sections_of_the_skills_and_asks_for_a_split_by_topic(self):
        import run

        found = budgets.long_sections(budgets.signal_files(ROOT), ROOT)
        note = run.sections_note()
        self.assertEqual(bool(note), bool(found))
        for one in found:
            self.assertIn(one, note)
        self.assertNotIn("aidd-team/references/roles.md", note, "the router's generated roles reference is not a section to split")


if __name__ == "__main__":
    unittest.main()
