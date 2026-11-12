"""aidd-team: roles as data, the role-aware guard, the plugin wiring, and `aidd init --aidd-team`."""

import json
import posixpath
import re
import unittest

import budgets
import helpers
from helpers import ROOT, repo_files, says

from aidd import config
from aidd.setup import team_install
from aidd.kernel import documents, resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"


class PluginTests(unittest.TestCase):
    def test_agents_match_the_roles(self):
        roles = team_registry.roles()
        for key in roles["order"]:
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            front = dict(re.findall(r"^(\w+): (.+)$", text.split("---")[1], re.M))
            self.assertEqual((front["name"], front["model"]), (key, team_registry.tier_model(roles["roles"][key]["tier"])), key)
            self.assertIn(f"<!-- aidd:gen role:{key} -->", text)
        self.assertNotIn("Write", (TEAM / "agents" / "reviewer.md").read_text(encoding="utf-8").split("---")[1])

    def test_the_router_skill_stays_small_and_links_its_references(self):
        """The aidd-team SKILL.md loads on every trigger, so it stays short; the tables live in references/."""
        skill_dir = TEAM / "skills" / "aidd-team"
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 150)
        # The generated loop diagram names each role a step runs, and its palette lines tint every box and row so it reads
        # on GitHub's light and dark pages. 9,472 bytes is about 2,368 estimated tokens, 1.2% of a 200,000-token window, once
        # for each session that triggers the team.
        self.assertLess(len(text.encode()), 9472, "the router skill loads on every trigger; move tables to references/")
        # Only the loop diagram is generated into the router itself; the role, flow, and handoff tables are references.
        self.assertEqual(re.findall(r"<!-- aidd:gen (\S+) -->", text), ["roles:graph:diagram"])
        links = re.findall(r"\]\((references/[^)]+)\)", text)
        for link in links:
            self.assertTrue((skill_dir / link).is_file(), link)
        refs = {"roles.md", "flows.md", "domain-packs.md", "practice-skills.md", "extensions.md", "living-work.md", "orca-channel.md"}
        self.assertEqual({p.name for p in (skill_dir / "references").glob("*.md")}, refs)
        self.assertEqual({link.removeprefix("references/") for link in links}, refs, "every reference is linked from the router")
        self.assertIn("<!-- aidd:gen roles -->", (skill_dir / "references" / "roles.md").read_text(encoding="utf-8"))
        flows = (skill_dir / "references" / "flows.md").read_text(encoding="utf-8")
        for block in ("roles:flows", "roles:handoffs"):
            self.assertIn(f"<!-- aidd:gen {block} -->", flows)
        self.assertNotIn("```mermaid", flows, "the flows and the handoffs are tables: a diagram of one row each would repeat them")

    def test_every_role_has_a_seeded_defect_eval(self):
        """Every role has an eval scenario, so every tier choice has a check."""
        from aidd.evals import suites

        scenarios = suites.load_scenarios(ROOT / "evals" / "roles")
        self.assertEqual({s["role"] for s in scenarios}, set(team_registry.roles()["order"]))
        for s in scenarios:
            self.assertTrue(s["fixture"].strip() and (s["expected"].get("decision") or s["expected"].get("answer_is")), s["id"])

    def test_each_role_thinks_as_hard_as_its_tier_asks(self):
        """A reasoning role runs at `xhigh` effort and an execution role at `high`, in the
        levels Claude Code's agent `effort:` takes."""
        self.assertEqual(team_registry.EFFORT_BY_TIER, {"reasoning": "xhigh", "execution": "high"})
        for path in sorted((TEAM / "agents").glob("*.md")):
            front = dict(re.findall(r"^(\w+): (.+)$", path.read_text(encoding="utf-8").split("---")[1], re.M))
            tier = team_registry.roles()["roles"][path.stem]["tier"]
            self.assertEqual(front.get("effort"), team_registry.EFFORT_BY_TIER[tier], path.name)

    def test_agent_models_are_values_claude_code_accepts(self):
        """Every agent file names a model Claude Code accepts: an alias, `inherit`, or a full model ID."""
        for path in sorted((TEAM / "agents").glob("*.md")):
            front = dict(re.findall(r"^(\w+): (.+)$", path.read_text(encoding="utf-8").split("---")[1], re.M))
            self.assertTrue(helpers.is_claude_code_model(front["model"]), f"{path.name}: model {front['model']!r}")
        for tier in helpers.TIER_MEANING:
            self.assertTrue(helpers.is_claude_code_model(team_registry.tier_model(tier)), tier)
        for bad in ("opus-5.5", "sonnet-5", "gpt-6-sol", "", "claude"):
            self.assertFalse(helpers.is_claude_code_model(bad), bad)
        for good in ("opus", "sonnet", "haiku", "fable", "inherit", "claude-opus-5-5", "claude-sonnet-4-5-20250929"):
            self.assertTrue(helpers.is_claude_code_model(good), good)

    def test_every_role_follows_the_loop(self):
        data = team_registry.roles()
        loop = data["graph"]
        covered = set()
        for key in data["order"]:
            r = data["roles"][key]
            self.assertTrue(r["steps"] and set(r["steps"]) <= set(loop["steps"]), key)
            self.assertTrue(r["routes"] and set(r["routes"]) <= set(loop["routes"]), key)
            self.assertTrue(r["starts_when"] and r["done_when"], key)
            covered |= set(r["steps"])
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            carried = team_registry.contract_carried_for(key)  # the rules that bind the role, less the ones its preloaded aidd skill gives
            for item in carried:
                self.assertIn(item, text, key)
            # An agent file carries only the rules that bind its role, and the rules its role checks, which `reviewed_as` gives it.
            checked = {rule for rule, _ in team_registry.reviewed_rules_for(key)}
            for item in set(loop["contract"]) - set(carried) - checked:
                self.assertNotIn(item, text, key)
        # Merge is the person's yes and the lead's action; every other step has a role.
        self.assertEqual(set(loop["steps"]) - covered, {"Merge"})
        for cmd in (TEAM / "commands").glob("*.md"):
            step = re.search(r"Loop steps?: (.+)", cmd.read_text(encoding="utf-8"))
            self.assertTrue(step and any(f"**{s}**" in step.group(1) for s in loop["steps"]), cmd.name)

    def test_domain_packs_are_generated_skills(self):
        from aidd.docsgen import pack_render

        data = team_registry.roles()
        for d in data["domains"]:
            path = pack_render.pack_path(ROOT, d)
            self.assertTrue(path.is_file(), d["slug"])
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text, pack_render.render_pack(d), d["slug"])
            self.assertIn(f"name: {d['slug']}\n", text)
            for section in ("## Standards", "## Checklist by loop step", "## Test commands", "## Keep it current"):
                self.assertIn(section, text, (d["slug"], section))
            self.assertTrue({c["step"] for c in d["checklist"]} >= {"Specify", "Implement"}, d["slug"])
        self.assertTrue(any("Research first" in x for x in data["graph"]["contract"]))

    def test_commands_follow_their_flows(self):
        import re as _re

        data = team_registry.roles()
        flows = {f["command"]: f for f in data["graph"]["flows"]}
        # One file per flow, and autopilot, which runs no roles of its own (tests/test_autopilot_command.py).
        self.assertEqual(sorted([*flows, data["graph"]["autopilot"]["command"]]), sorted(p.stem for p in (TEAM / "commands").glob("*.md")))
        for name, f in flows.items():
            text = (TEAM / "commands" / f"{name}.md").read_text(encoding="utf-8")
            named = set(_re.findall(r"`aidd-team:([a-z-]+)`", text))
            # A command names the roles of its flow and of each of its modes.
            expected = {r for g in [*f["runs"], *(g for m in f.get("modes", []) for g in m["runs"])] for r in g}
            self.assertEqual(named, expected, name)
            self.assertTrue(expected <= set(data["roles"]), name)
            for step in f["steps"]:
                self.assertIn(f"**{step}**", text, (name, step))
            if len(f["runs"]) > 1 or len(f["runs"][0]) > 1:
                self.assertIn("parallel", text, name)

    def test_front_matter_is_strict_yaml(self):
        import re as _re

        indicators = tuple("-?:,[]{}#&*!|>'\"%@`")
        for path in (ROOT / f for f in repo_files() if f.endswith(".md")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                continue
            front = text[4 : text.index("\n---", 4)]
            try:
                documents.parse_yaml(front, str(path))
                continue  # inside aidd's strict subset, which every YAML reader reads the same way (tests/test_strict_yaml.py)
            except documents.DocumentError:
                pass
            for line in front.splitlines():
                m = _re.match(r"^([\w-]+): (.*)$", line)
                if not m or m.group(2).startswith(('"', "'")):
                    continue
                value = m.group(2)
                self.assertFalse(": " in value or " #" in value or value.startswith(indicators), f"{path}: {line}")

    def test_standards_and_practices_are_in_one_explainable_order(self):
        """A role's standards: established before emerging, then by the name a reader sees. Its practice skills: by name."""
        data = resources.load_json("roles.json")  # the file as written, with standards by reference
        reg = data["standards"]
        for key, role in data["roles"].items():
            seen = []
            for s in role["standards"]:
                sid = s["id"] if isinstance(s, dict) else s
                seen.append((reg[sid].get("maturity", "established") != "established", (s["as"] if isinstance(s, dict) else reg[sid]["name"]).lower()))
            self.assertEqual(seen, sorted(seen), key)
            self.assertEqual(role["skills"], sorted(role["skills"]), key)

    def test_extensions_are_in_one_explainable_order(self):
        """Established before emerging (proven methods first), then by type in the order a role reaches for one (its
        harness, a command-line tool that produces evidence, an MCP server for data, a plugin, a skill), then by name."""
        ext_types = ["harness", "tool", "mcp", "plugin", "skill"]
        for key, role in team_registry.roles()["roles"].items():
            ext = role.get("extensions", [])
            order = [(e.get("maturity", "established") != "established", ext_types.index(e["type"]), e["name"].lower()) for e in ext]
            self.assertEqual(order, sorted(order), key)

    def test_extensions_are_dated_and_sourced(self):
        data = team_registry.roles()
        ext_types = {"skill", "plugin", "mcp", "tool", "harness"}
        for key in data["order"]:
            for x in data["roles"][key]["extensions"]:
                self.assertIn(x["type"], ext_types, key)
                self.assertTrue(x["source"].startswith("https://"), key)
            # An extension is used only when the project already has it, so the list lives in the reference, not the agent file.
            self.assertNotIn("**Extend with", (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8"), key)

    def test_flow_routes_agree_with_role_routes(self):
        """A command and its flow name the same routes.

        Every route a flow runs on has a role for it, every role in a flow works on one of its routes, the command
        states the flow's routes, and a command whose roles do not all work on every route says it filters them.
        """
        data = team_registry.roles()
        for f in data["graph"]["flows"]:
            roles = [r for g in f["runs"] for r in g]
            for route in f["routes"]:
                self.assertTrue(any(route in data["roles"][r]["routes"] for r in roles), (f["command"], route))
            for r in roles:
                self.assertTrue(set(data["roles"][r]["routes"]) & set(f["routes"]), (f["command"], r))
            text = (TEAM / "commands" / f"{f['command']}.md").read_text(encoding="utf-8")
            m = re.search(r"^Routes: ([a-z, ]+)\.", text, re.M)
            self.assertIsNotNone(m, f["command"])
            self.assertEqual([x.strip() for x in m.group(1).split(",")], f["routes"], f["command"])
            if any(not set(f["routes"]) <= set(data["roles"][r]["routes"]) for r in roles):
                self.assertTrue(says(text, "only the roles", "routes"), f["command"])
            for route in config.ROUTES:
                if route not in f["routes"]:
                    self.assertNotRegex(text.split("\n## ")[0], rf"on (?:the|every) [a-z ,]*\b{route}\b[a-z ,]* routes?", (f["command"], route))

    def test_flows_run_roles_in_their_own_steps(self):
        data = team_registry.roles()
        for f in data["graph"]["flows"]:
            for role in (r for g in f["runs"] for r in g):
                self.assertTrue(set(f["steps"]) & set(data["roles"][role]["steps"]), (f["command"], role))

    def test_handoffs_link_every_role(self):
        data = team_registry.roles()
        senders: set[str] = set()
        for h in data["graph"]["handoffs"]:
            self.assertTrue(set(h["from"]) <= set(data["roles"]), h["from"])
            for party in h["to"]:
                self.assertTrue(party in data["roles"] or party.startswith("the author"), party)
            senders |= set(h["from"])
        self.assertEqual(senders, set(data["roles"]))
        self.assertTrue(any("handoff note" in x for x in data["graph"]["contract"]))
        handoffs = (TEAM / "skills" / "aidd-team" / "references" / "flows.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen roles:handoffs -->", handoffs)
        self.assertIn("references/flows.md", (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8"))

    def test_roles_validate_against_their_schema(self):
        from aidd.kernel import json_schema

        data = resources.load_json("roles.json")  # the file itself; team_registry.roles() is the resolved view
        self.assertEqual(json_schema.validate(data, "roles.schema.json"), [])
        self.assertEqual(set(data["order"]), set(data["roles"]))
        self.assertEqual(len(data["order"]), len(set(data["order"])))
        # A data file names the schema it validates against, not the metaschema.
        self.assertEqual(data.get("$schema"), "./roles.schema.json")
        self.assertTrue((ROOT / "schemas" / data["$schema"]).is_file())
        for h in data["graph"]["handoffs"]:
            for sender in h["from"]:
                self.assertIn(sender, data["roles"])
        for f in data["graph"]["flows"]:
            for group in f["runs"]:
                for role in group:
                    self.assertIn(role, data["roles"])
        skills_dir = TEAM / "skills"
        for d in data["domains"]:
            self.assertTrue((ROOT / "plugins" / "aidd-packs" / "skills" / d["slug"]).is_dir(), f"missing skill dir for domain {d['slug']}")
            self.assertFalse((skills_dir / d["slug"]).exists(), f"the pack {d['slug']} belongs to aidd-packs, not aidd-team")
        for r, rdata in data["roles"].items():
            for p in rdata.get("skills", []):
                self.assertTrue((skills_dir / p).is_dir(), f"missing skill dir for practice {p} in role {r}")
        loop_steps = set(data["graph"]["steps"])
        for r, rdata in data["roles"].items():
            self.assertTrue(set(rdata["steps"]) <= loop_steps, f"role {r} steps outside graph.steps")
        broken = json.loads(json.dumps(data))
        broken["roles"]["developer"]["steps"] = ["Deploy"]
        self.assertTrue(json_schema.validate(broken, "roles.schema.json"))

    def test_domains_cover_the_ai_era(self):
        domains = {d["name"]: d for d in team_registry.roles()["domains"]}
        self.assertGreaterEqual(len(domains), 10)
        self.assertTrue(any("Agentic" in s["name"] for s in domains["AI agents and tools"]["standards"]))
        skill = (TEAM / "skills" / "aidd-team" / "references" / "domain-packs.md").read_text(encoding="utf-8")
        for name in domains:
            self.assertIn(f"| {name} |", skill)

    def test_standards_registry_is_current(self):
        import datetime as dt

        from aidd.knowledge import standards_evidence

        # The clock is pinned to the newest `checked` date, so this test never turns red because time passed: real
        # currency is a calendar check, which `aidd eval standards` runs in the standards workflow's weekly check.
        entries = standards_evidence.dated_entries()
        self.assertGreater(len(entries), 100)
        checked = [dt.date.fromisoformat(standards_evidence.dated_on(s)) for s in entries]
        newest = max(checked)
        # Nothing is checked in the future. Against the wall clock, this can only go from red to green as time passes.
        self.assertLessEqual(newest, dt.date.today())
        # No entry is past its review cadence as of the newest check, and a year and a month later every one is stale.
        self.assertEqual(standards_evidence.stale_standards(newest), [])
        later = standards_evidence.stale_standards(newest + dt.timedelta(days=400))
        self.assertEqual(len(later), len(entries))
        self.assertEqual(sorted(s["age_days"] for s in later), sorted((newest + dt.timedelta(days=400) - d).days for d in checked))
        self.assertGreater(later[0]["age_days"], 365)

    def test_every_role_names_its_standards_and_done(self):
        for key in team_registry.roles()["order"]:
            self.assertGreaterEqual(len(team_registry.roles()["roles"][key]["standards"]), 5, key)
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            for section in ("## Playbook", "## Definition of Done", "## Stop and hand back"):
                self.assertIn(section, text, (key, section))

    def test_practice_skills_are_dated_playbooks(self):
        import datetime as dt

        from aidd.knowledge import role_text

        data = team_registry.roles()
        listed = {x for k in data["order"] for x in data["roles"][k]["skills"]}
        packs = {d["slug"] for d in data["domains"]}
        on_disk = {p.parent.name for p in (TEAM / "skills").glob("*/SKILL.md")} - packs - {"aidd-team"}
        # Every practice skill on disk has a role that loads it, and every listed practice exists.
        self.assertEqual(on_disk, listed)
        self.assertGreaterEqual(len(listed), 10)
        self.assertEqual(set(role_text.practice_names()), listed)
        for name in sorted(listed):
            text = (TEAM / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            front = role_text.practice_front(name)
            self.assertEqual(front["name"], name)
            self.assertTrue(front["description"].startswith("Practice skill: "), name)
            self.assertIn(". Use ", front["description"], name)
            self.assertLessEqual(dt.date.fromisoformat(front["checked"]), dt.date.today(), name)
            for section in ("## Standards", "## Hand off"):
                self.assertIn(section, text, (name, section))
            # The one generated block is its Standards table, rendered from its registry ids; the rest is hand-written.
            self.assertEqual(re.findall(r"<!-- aidd:gen (\S+) -->", text), [f"practice:{name}"], name)
        for role in ("developer", "verifier", "reviewer", "security-engineer", "architect"):
            self.assertTrue(data["roles"][role]["skills"], role)

    def test_practices_reach_the_agents_and_the_currency_check(self):
        from aidd.docsgen import generate
        from aidd.knowledge import standards_evidence
        from aidd.knowledge import role_text

        data = team_registry.roles()
        for key in data["order"]:
            # The agent file points at its role's section of the roles reference, where the practice skills are listed.
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            if data["roles"][key].get("mcp_tools"):  # a role with only its own tools reads no reference
                self.assertNotIn("section `", text, key)
            else:
                self.assertIn(f"section `{key}`", text, key)
            section = role_section(key)
            self.assertIn("**Practice skills", section, key)
            for name in data["roles"][key]["skills"]:
                self.assertIn(f"`aidd-team:{name}`", section, (key, name))
        table = generate.render("roles:practices")
        for name in role_text.practice_names():
            self.assertIn(f"| `aidd-team:{name}` |", table)
        for path in (TEAM / "skills" / "aidd-team" / "references" / "practice-skills.md", ROOT / "docs" / "TEAM-REFERENCE.md"):
            self.assertIn("<!-- aidd:gen roles:practices -->", path.read_text(encoding="utf-8"), path.name)
        where = {s["where"] for s in standards_evidence.dated_entries()}
        self.assertTrue({f"practice {x}" for x in role_text.practice_names()} <= where)
        self.assertTrue(any("practice skill" in x for x in data["graph"]["contract"]))

    def test_tiers_are_priced_to_value(self):
        """The tier is harness-neutral; only the Claude Code plugin's frontmatter carries a vendor SKU."""
        data = team_registry.roles()
        # The tier follows the cost of a mistake: only the builders whose errors the tests catch, and whose
        # change is reversible, run in the execution tier.
        # `execution` is the default; `reasoning` is kept only for the roles whose judgment no test or later human
        # check catches; each with its reason. There are two tiers only.
        # 2026-10-24, the owner keeps the judgement roles (product, architecture, design, security, compliance, review) on reasoning, and the domain expert folded into the packs; the rest run on execution.
        reasoning = {k for k in data["order"] if data["roles"][k]["tier"] == "reasoning"}
        self.assertEqual(reasoning, {"architect", "security-engineer", "reviewer", "delegate", "compliance-analyst", "product-manager", "product-designer"})
        # The delegate's accept stands in for the person's yes (the standing delegation's design, 2026-11-08), so it is a
        # judgment role on reasoning too; the builders, still at most half the roster, keep the cap's intent.
        self.assertLessEqual(len(reasoning - {"delegate"}), (len(data["order"]) - 1 + 1) // 2)
        for k in data["order"]:
            tier = data["roles"][k]["tier"]
            self.assertTrue(data["roles"][k]["tier_reason"].endswith("."), k)
            text = (TEAM / "agents" / f"{k}.md").read_text(encoding="utf-8")
            self.assertIn(f"- **Model tier:** `{tier}`", text, k)
            # the plugin frontmatter is the one place a vendor model name appears, and it is derived
            self.assertIn(f"model: {team_registry.tier_model(tier)}", text.split("---")[1], k)
        # Every mapped harness answers both tiers, and the plugin's harness is one of them.
        self.assertIn(team_registry.PLUGIN_HARNESS, team_registry.MODELS_BY_HARNESS)
        for h, m in team_registry.MODELS_BY_HARNESS.items():
            self.assertEqual(set(m), set(helpers.TIER_MEANING), h)
            self.assertTrue(all(isinstance(v, str) and v for v in m.values()), h)
        # A harness the registry has no mapping for gets no model: it reads the tier and picks its own.
        self.assertIsNone(team_registry.tier_model("reasoning", "cursor"))
        self.assertIsNone(team_registry.tier_model("execution", "no-such-harness"))
        self.assertIn("<!-- aidd:gen roles:models -->", (ROOT / "docs" / "TEAM-REFERENCE.md").read_text(encoding="utf-8"))
        self.assertTrue(any(x.startswith("Spend in proportion to risk") for x in data["graph"]["contract"]))

    def test_the_rule_for_the_roles_that_design_and_build_binds_those_roles_and_no_other(self):
        """The rule is found by the roles it binds (a scoped rule has no id), and each agent file carries it only for them, and for
        the roles that check it."""
        binds = ["architect", "product-designer", "developer"]
        items = resources.load_json("roles.json")["graph"]["contract"]
        found = [x for x in items if isinstance(x, dict) and sorted(x.get("applies_to") or []) == sorted(binds)]
        self.assertEqual(len(found), 1)
        rule = found[0]["rule"]
        for key in team_registry.roles()["order"]:
            agent = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            with self.subTest(role=key):
                self.assertEqual(rule in team_registry.contract_for(key), key in binds)
                self.assertEqual(rule in agent, key in binds or rule in {r for r, _ in team_registry.reviewed_rules_for(key)})

    def test_the_verdict_of_the_rule_for_the_builders_has_each_case_the_rule_names(self):
        """The reviewer's verdict follows the builders' rule case by case. Each case has a key term in the rule and one in the
        verdict, both read from the data, so a case cut from either side, or a reworded one, fails here until both are read again."""
        binds = ["architect", "developer", "product-designer"]
        item = next(x for x in resources.load_json("roles.json")["graph"]["contract"] if isinstance(x, dict) and sorted(x.get("applies_to") or []) == binds)
        rule, verdict = item["rule"], item["reviewed_as"]["as"]
        cases = (  # the case, its key term in the rule, and its key term in the verdict
            ("a new part is written the current way", "stands alone", "stands alone"),
            ("a changed or added line matches the code around it", "the code around", "the code around"),
            ("a feature outside the supported range has a stated fallback", "fallback", "fallback"),
            ("with no stated range, the assumed one is named", "the range you assumed", "the range the author named"),
            ("an old pattern the builder leaves is debt", "old pattern you leave", "did not write"),
        )
        for case, in_rule, in_verdict in cases:
            with self.subTest(case=case):
                self.assertIn(in_rule, rule)
                self.assertIn(in_verdict, verdict)
        self.assertEqual(
            len(cases) + 1, verdict.count(". ") + 1, "each sentence of the verdict is one case of the table, and one says where the named range is"
        )
        self.assertEqual(rule.count(". ") + 1, 8, "a sentence was added to the rule or cut from it: read the table and the verdict again")
        self.assertIn("`debt`", verdict.split("did not write", 1)[1], "an old pattern the change did not write is a debt finding")

    def test_a_role_that_checks_a_rule_shows_the_rule_and_its_verdict_in_every_harness_and_holds_no_second_copy(self):
        """A contract rule with `reviewed_as` has one text. Each role in `reviewed_as.roles` carries the rule's own words and the verdict in its
        generated block, in the plugin's agent file and in the file of every harness that gets role files, and its hand-written
        part never restates the rule: its opening words, taken from the data, stand nowhere outside the generated block."""
        items = [x for x in resources.load_json("roles.json")["graph"]["contract"] if isinstance(x, dict) and x.get("reviewed_as")]
        self.assertTrue(items, "the data has a rule a role checks")
        for item in items:
            opening = item["rule"].split(". ")[0]
            for role in item["reviewed_as"]["roles"]:
                plugin = (TEAM / "agents" / f"{role}.md").read_text(encoding="utf-8")
                by_hand = plugin.split("<!-- aidd:end -->", 1)[1]
                with self.subTest(role=role, where="the hand-written part"):
                    self.assertNotIn(opening, by_hand)
                    self.assertNotIn(item["reviewed_as"]["as"].split(". ")[0], by_hand)
                files = {"claude-code": plugin}
                for harness in team_install.NATIVE_AGENT_HARNESSES:
                    made = team_install.team_files([harness], claude_files=False)
                    files[harness] = next(text for rel, text in made.items() if re.search(rf"agents/aidd-{role}\.", rel))
                for harness, text in files.items():
                    # Kiro writes its file as JSON, which escapes what a string cannot hold.
                    shown = json.dumps(text)[1:-1] if harness == "kiro" else text
                    with self.subTest(role=role, harness=harness):
                        for words in (item["rule"], item["reviewed_as"]["as"]):
                            self.assertIn(json.dumps(words)[1:-1] if harness == "kiro" else words, shown)
                for other in (r for r in team_registry.roles()["order"] if r not in item["reviewed_as"]["roles"]):
                    with self.subTest(role=other, where="a role that does not check it"):
                        self.assertNotIn(item["reviewed_as"]["as"], (TEAM / "agents" / f"{other}.md").read_text(encoding="utf-8"))

    def test_emerging_entries_are_marked_and_the_rule_is_in_the_contract(self):
        from aidd.docsgen import generate
        from aidd.docsgen import team_reference
        from aidd.docsgen import pack_render
        from aidd.knowledge import standards_evidence

        data = team_registry.roles()
        self.assertTrue(any(x.startswith("Proven methods first") for x in data["graph"]["contract"]))
        entries = standards_evidence.dated_entries()
        emerging = [s for s in entries if s.get("maturity") == "emerging"]
        self.assertTrue(emerging)
        self.assertLess(len(emerging), len(entries) // 4, "most of the registry must be established")
        for s in emerging:
            self.assertIn("emerging", team_reference.standard_text(s), s["name"])
        for key in data["order"]:
            for s in data["roles"][key]["standards"] + data["roles"][key]["extensions"]:
                self.assertIn(s.get("maturity", "established"), {"established", "emerging"}, s["name"])
                self.assertNotIn("Karpathy", s.get("edition", ""), s["name"])
        packs = [pack_render.render_pack(x) for x in data["domains"]]
        self.assertTrue(any("(emerging)" in t for t in packs))
        self.assertIn("emerging", generate.render("roles:extensions"))

    def test_the_loop_diagram_is_generated_from_the_registry(self):
        from aidd.docsgen import generate

        data = team_registry.roles()
        loop = generate.render("roles:graph:diagram")
        self.assertTrue(loop.startswith("```mermaid\nflowchart"))
        for key in data["order"]:
            self.assertIn(key, loop, key)
        self.assertIn("Spec approval", loop)
        self.assertIn("Merge approval", loop)
        self.assertNotIn('"`', loop, "a quoted Mermaid label must not start with a backtick")
        for path in (ROOT / "docs" / "TEAM.md", TEAM / "skills" / "aidd-team" / "SKILL.md"):
            self.assertIn("<!-- aidd:gen roles:graph:diagram -->", path.read_text(encoding="utf-8"), path.name)
        self.assertIn("docs/TEAM.md", (ROOT / "README.md").read_text(encoding="utf-8"))  # README links the team page
        self.assertTrue(any(x.startswith("Explain visually") for x in data["graph"]["contract"]))

    def test_marketplace_lists_the_plugins(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual([p["name"] for p in market["plugins"]], ["aidd", "aidd-cli", "aidd-team", "aidd-packs"])
        # Without the aidd plugin there is no hook, so the team declares it. The packs name the team they extend, since a pack's
        # neighbours and test owners are practice skills.
        self.assertEqual(next(p for p in market["plugins"] if p["name"] == "aidd-team")["dependencies"], ["aidd"])
        self.assertEqual(json.loads((TEAM / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["dependencies"], ["aidd"])
        packs = next(p for p in market["plugins"] if p["name"] == "aidd-packs")
        self.assertEqual((packs["source"], packs["dependencies"]), ("./plugins/aidd-packs", ["aidd-team"]))
        self.assertEqual(
            json.loads((ROOT / "plugins" / "aidd-packs" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["dependencies"], ["aidd-team"]
        )
        for cmd in ("plan", "specify", "implement", "review", "rollout", "postmortem", "retro"):
            self.assertTrue((TEAM / "commands" / f"{cmd}.md").is_file(), cmd)

    def test_every_place_that_describes_aidd_names_the_governance_layer(self):
        """The pages an agent reads first name the governance layer, in the glossary's words. The description itself has one
        owner, schemas/product.json, and tests/test_product.py holds every copy to it."""
        read = lambda *path: (ROOT.joinpath(*path)).read_text(encoding="utf-8")  # noqa: E731
        for page in ("README.md", "llms.txt", "llms-install.md", "AGENTS.md"):
            self.assertIn("governance layer", read(page).lower(), page)

    def test_manifests_state_no_stale_count_and_name_every_command(self):
        """The manifests said nine commands and sixteen practice skills after propose, onboard, estimation, and proposal landed.

        JSON cannot carry a generated block, so a manifest either states no count or states the registry's.
        """
        from aidd.docsgen import counts as docsgen_counts

        words = (
            "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
        )
        counts = {"agent roles": "roles", "roles": "roles", "commands": "commands", "domain packs": "packs", "practice skills": "practices"}
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        team = json.loads((TEAM / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        texts = [p["description"] for p in market["plugins"]] + [market["metadata"]["description"], team["description"]]
        for text in texts:
            for number, noun in re.findall(r"\b(\d+|" + "|".join(words) + r") (agent roles|roles|commands|domain packs|practice skills)\b", text, re.I):
                value = int(number) if number.isdigit() else words.index(number.lower())
                self.assertEqual(value, docsgen_counts.count(counts[noun.lower()]), f"a manifest says {number} {noun}")
        for f in team_registry.roles()["graph"]["flows"]:
            self.assertRegex(team["description"], rf"\b{f['command']}\b", f"plugin.json does not name the {f['command']} command")

    def test_agents_can_call_the_aidd_mcp_tools(self):
        """Every role's prompt says to use the aidd MCP tools, and a `tools:` allowlist hides any tool it does not name.

        The reviewer has no shell, so the MCP `risk` tool is its only view of the risk rules.
        """
        from aidd.cli import mcp_server
        from aidd.docsgen import pack_render

        names = {t["name"] for t in mcp_server.TOOLS}
        self.assertEqual(
            names,
            {"risk", "status", "recall", "record", "validate", "delegate_check", "delegate_packet", "delegate_answer"},
        )
        delegation = {"delegate_check", "delegate_packet", "delegate_answer"}  # the lead's check and the delegate's own two
        for key in team_registry.roles()["order"]:
            front = dict(re.findall(r"^(\w+): (.+)$", (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8").split("---")[1], re.M))
            tools = set(pack_render.split_tools(front["tools"]))

            def granted(tool: str, tools: set[str] = tools) -> bool:
                # By its name, or by its server's `mcp__<server>__*` entry, which grants every tool of that server.
                return tool in tools or tool.rsplit("__", 1)[0] + "__*" in tools

            # A role that writes no file gets every tool that reads, and never `record`, which writes a record of history.
            writes = bool(team_registry.roles()["roles"][key]["writes"])
            for prefix in ("mcp__plugin_aidd_aidd__", "mcp__aidd__"):  # the plugin's server, and the one `aidd init` wires
                if team_registry.roles()["roles"][key].get("mcp_tools"):  # the delegate: its own two tools, nothing else
                    self.assertEqual({t for t in tools if t.startswith(prefix)}, {prefix + n for n in team_registry.roles()["roles"][key]["mcp_tools"]}, key)
                    continue
                self.assertTrue(all(granted(prefix + n) for n in names - {"record"} - delegation), key)
                self.assertEqual(granted(prefix + "record"), writes, key)
            if not team_registry.roles()["roles"][key].get("mcp_tools"):
                self.assertTrue(all(granted(t) for t in helpers.role_mcp_tools()), key)

    def test_the_graph_contract_needs_no_third_party_service(self):
        """Not every project has a forge, a tracker, a design tool, or an observability service; git and files suffice."""
        contract = team_registry.roles()["graph"]["contract"]
        rule = next((x for x in contract if x.startswith("Work with what the project has.")), None)
        self.assertIsNotNone(rule, "the loop contract has no work-with-what-the-project-has rule")
        self.assertIn("Never ask the team to adopt one.", rule)
        self.assertIn("in the repository instead", rule)

    def test_every_platform_command_in_a_command_file_has_a_local_alternative(self):
        """A step that runs `gh` or `glab` also says what to do without a platform, in the same step (one line)."""
        for path in sorted((TEAM / "commands").glob("*.md")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"`(?:gh|glab) ", line):
                    self.assertTrue("without a platform" in line or "`git " in line, f"{path.name}:{i} names gh or glab with no local path")


class ExtensionPublisherTests(unittest.TestCase):
    """Every extension says who stands behind it; a community one is emerging, licensed for commercial use, and pinned."""

    PUBLISHERS = {"official", "vendor", "maintainer", "community"}
    # Licenses compatible with shipping beside an Apache-2.0 project and with commercial use.
    COMMUNITY_LICENSES = {"0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT"}
    OFFICIAL_DIRECTORY = "https://github.com/anthropics/claude-plugins-official"
    OFFICIAL_SOURCES = ("https://github.com/anthropics/", "https://code.claude.com/")

    def extensions(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            for x in role["extensions"]:
                yield key, x

    def test_every_extension_has_a_publisher(self):
        for key, x in self.extensions():
            self.assertIn(x.get("publisher"), self.PUBLISHERS, (key, x["name"]))

    def test_a_community_extension_is_emerging_licensed_and_pinned(self):
        seen = 0
        for key, x in self.extensions():
            if x["publisher"] != "community":
                continue
            seen += 1
            self.assertEqual(x.get("maturity"), "emerging", (key, x["name"]))
            self.assertIn(x.get("license"), self.COMMUNITY_LICENSES, (key, x["name"]))
            self.assertTrue(x.get("pin", "").strip(), (key, x["name"]))
        self.assertGreater(seen, 0, "no community extension left to check")

    def test_an_official_extension_is_made_by_the_harness_vendor(self):
        """`official` means the harness vendor made it; a third-party entry its directory lists keeps its maker as publisher."""
        for key, x in self.extensions():
            if x["publisher"] == "official":
                self.assertTrue(x["source"].startswith(self.OFFICIAL_SOURCES), (key, x["name"]))
            if x.get("listed_in"):
                self.assertEqual(x["listed_in"], self.OFFICIAL_DIRECTORY, (key, x["name"]))
                self.assertTrue(x.get("pin"), (key, x["name"]))
                self.assertNotEqual(x["publisher"], "official", (key, x["name"]))

    def test_the_schema_enforces_the_publisher_rules(self):
        from aidd.kernel import json_schema

        data = resources.load_json("roles.json")
        self.assertEqual(json_schema.validate(data, "roles.schema.json"), [])
        for field, value in (("license", "GPL-3.0"), ("maturity", "established"), ("pin", None), ("publisher", None)):
            broken = json.loads(json.dumps(data))
            entry = next(x for x in broken["roles"]["developer"]["extensions"] if x["name"] == "CodeGraph")
            if value is None:
                del entry[field]
            else:
                entry[field] = value
            self.assertTrue(json_schema.validate(broken, "roles.schema.json"), field)
        broken = json.loads(json.dumps(data))
        entry = next(x for x in broken["roles"]["developer"]["extensions"] if x["name"] == "Superpowers")
        entry["publisher"] = "official"
        self.assertTrue(json_schema.validate(broken, "roles.schema.json"), "a listing in the official directory does not make it official")
        broken = json.loads(json.dumps(data))
        entry = next(x for x in broken["roles"]["developer"]["extensions"] if x["name"] == "Superpowers")
        del entry["pin"]
        self.assertTrue(json_schema.validate(broken, "roles.schema.json"), "a listed entry names the directory's pinned commit")
        for ext_type in ("tool", "plugin", "skill"):
            for field in ("license", "pin"):
                broken = json.loads(json.dumps(data))
                entry = next(x for r in broken["roles"].values() for x in r["extensions"] if x["type"] == ext_type)
                del entry[field]
                self.assertTrue(json_schema.validate(broken, "roles.schema.json"), f"a {ext_type} without its {field}")

    def test_the_curated_entries(self):
        ext = {(k, x["name"]): x for k, x in self.extensions()}
        names = {x["name"] for x in ext.values()}
        self.assertNotIn("Product Manager Skills", names, "CC BY-NC-SA is non-commercial")
        sp = ext[("developer", "Superpowers")]
        # Made by its author, Jesse Vincent, and listed in (not made by) the official directory.
        self.assertEqual((sp["publisher"], sp["maturity"], sp["listed_in"]), ("community", "emerging", self.OFFICIAL_DIRECTORY))
        for skill in ("systematic debugging", "test-driven development", "verification before completion", "receiving code review"):
            self.assertIn(skill, sp["adds"])
        self.assertIn("superseded by the aidd loop", sp["adds"])
        self.assertIn("never merge", sp["adds"])
        # Community entries, whose license test_a_community_extension_is_emerging_licensed_and_pinned checks.
        for key, name in (("product-designer", "Impeccable"), ("developer", "CodeGraph")):
            self.assertEqual(ext[(key, name)]["publisher"], "community", name)
        for key, name in (("reviewer", "pr-review-toolkit"), ("developer", "code-simplifier"), ("security-engineer", "security-guidance")):
            x = ext[(key, name)]
            self.assertEqual((x["type"], x["publisher"]), ("plugin", "official"), name)
            self.assertTrue(x["source"].startswith(self.OFFICIAL_DIRECTORY + "/tree/main/plugins/"), name)
        for key, name in (
            ("sre", "Renovate"),
            ("sre", "Dependabot"),
            ("sre", "OSV-Scanner"),
            ("security-engineer", "OSV-Scanner"),
            ("developer", "knip"),
            ("reviewer", "knip"),
            ("developer", "vulture"),
            ("reviewer", "vulture"),
        ):
            self.assertEqual(ext[(key, name)]["publisher"], "maintainer", (key, name))

    def test_the_publisher_reaches_the_agent_files_and_the_tables(self):
        from aidd.docsgen import generate

        table = generate.render("roles:extensions")
        self.assertIn("| Publisher |", table)
        for key, role in team_registry.roles()["roles"].items():
            for x in role["extensions"]:
                row = next(r for r in table.splitlines() if r.startswith(f"| `{key}` | {x['name']} | "))
                self.assertIn(f" | {x['publisher']} | ", row, (key, x["name"]))


class ExtensionAccessTests(unittest.TestCase):
    """Every extension says what it can touch, so a team sees it before installing, and the security review knows where to look."""

    ACCESS = {"network", "writes_repo", "runs_commands", "reads_secrets", "telemetry"}
    RISKY = {"writes_repo", "runs_commands"}

    def extensions(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            for x in role["extensions"]:
                yield key, x

    def test_every_extension_declares_its_access(self):
        for key, x in self.extensions():
            caps = x.get("access")
            self.assertIsInstance(caps, list, (key, x["name"]))
            self.assertLessEqual(set(caps), self.ACCESS, (key, x["name"]))
            self.assertEqual(len(caps), len(set(caps)), (key, x["name"]))

    def test_one_extension_declares_the_same_access_in_every_role(self):
        seen: dict[str, tuple] = {}
        for key, x in self.extensions():
            caps = (sorted(x["access"]), x.get("telemetry_opt_out"))
            self.assertEqual(seen.setdefault(x["name"], caps), caps, (key, x["name"]))

    def test_telemetry_states_whether_it_can_be_turned_off(self):
        for key, x in self.extensions():
            if "telemetry" in x["access"]:
                self.assertIsInstance(x.get("telemetry_opt_out"), bool, (key, x["name"]))
            else:
                self.assertNotIn("telemetry_opt_out", x, (key, x["name"]))

    def test_a_community_extension_that_writes_or_runs_is_pinned(self):
        risky = [(k, x) for k, x in self.extensions() if x["publisher"] == "community" and self.RISKY & set(x["access"])]
        self.assertTrue(risky, "no community extension that writes or runs left to check")
        for key, x in risky:
            self.assertTrue(x.get("pin", "").strip(), (key, x["name"]))

    def test_the_schema_enforces_the_access_rules(self):
        from aidd.kernel import json_schema

        data = resources.load_json("roles.json")
        self.assertEqual(json_schema.validate(data, "roles.schema.json"), [])

        def broken(edit):
            copy = json.loads(json.dumps(data))
            edit(next(x for x in copy["roles"]["developer"]["extensions"] if x["name"] == "CodeGraph"))
            return json_schema.validate(copy, "roles.schema.json")

        self.assertTrue(broken(lambda x: x.pop("access")), "access is required")
        self.assertTrue(broken(lambda x: x.update(access=["filesystem"])), "an unknown access")
        self.assertTrue(broken(lambda x: x.update(access=["network", "network"])), "a repeated access")
        self.assertTrue(broken(lambda x: x.pop("telemetry_opt_out")), "telemetry without its opt-out")
        self.assertTrue(broken(lambda x: x.update(access=["network"], telemetry_opt_out=True)), "an opt-out without telemetry")
        self.assertEqual(broken(lambda x: x.update(access=["telemetry"], telemetry_opt_out=False)), [])
        self.assertEqual(broken(lambda x: (x.update(access=[]), x.pop("telemetry_opt_out"))), [], "empty is read-only")
        self.assertTrue(broken(lambda x: (x.update(access=["runs_commands"]), x.pop("pin"))), "a community extension that runs is pinned")

    def test_the_access_reaches_the_reference_table(self):
        from aidd.docsgen import generate
        from aidd.docsgen import team_reference

        table = generate.render("roles:extensions")
        self.assertIn("| Publisher | Access | Adds |", table)
        for key, x in self.extensions():
            self.assertIn(f"| `{key}` | {x['name']} | ", table)
            row = next(r for r in table.splitlines() if r.startswith(f"| `{key}` | {x['name']} | "))
            self.assertIn(f" | {team_reference.access_text(x)} | {x['adds']} |", row, (key, x["name"]))
        self.assertEqual(team_reference.access_text({"access": []}), "read-only")
        self.assertEqual(
            team_reference.access_text({"access": ["network", "runs_commands", "telemetry"], "telemetry_opt_out": True}),
            "network, runs commands, telemetry (can be turned off)",
        )
        # The reference explains why before the table: what an extension can touch is read before it is installed.
        text = (TEAM / "skills" / "aidd-team" / "references" / "extensions.md").read_text(encoding="utf-8")
        self.assertIn("**Access**", text.split("<!-- aidd:gen roles:extensions -->")[0])


def role_section(key: str) -> str:
    """Role `key`'s section of the aidd-team roles reference: its standards and practice skills, loaded on demand."""
    ref = (TEAM / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")
    parts = ref.split(f"\n### {key}\n", 1)
    assert len(parts) == 2, f"no section {key} in the roles reference"
    return parts[1].split("\n### ", 1)[0].split("<!-- aidd:end -->", 1)[0]


class SlimAgentFileTests(unittest.TestCase):
    """An agent file loads into every run of its role, so it carries what changes what the role does, and no more."""

    # Bytes. Most of a role file is the registry's own facts for the role (when it starts, when it is done, its contract). The
    # cap and the cost it tracks are in budgets.CAPS.
    BUDGET = budgets.ROLE_FILE_BYTES
    MAX_STANDARDS = 12

    def test_every_agent_file_is_under_the_budget(self):
        for key in team_registry.roles()["order"]:
            size = len((TEAM / "agents" / f"{key}.md").read_bytes())
            self.assertLess(size, self.BUDGET, budgets.make_room(f"{key}.md", size, self.BUDGET, cost=budgets.cost_of("role file")))

    def test_standards_and_practices_live_in_the_role_reference(self):
        from aidd.docsgen import team_reference

        data = team_registry.roles()
        pointer = "- **Standards and skills:** the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `{}`."
        for key in data["order"]:
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            if data["roles"][key].get("mcp_tools"):  # a role with only its own tools reads no reference
                self.assertNotIn("Standards and skills", text, key)
            else:
                self.assertIn(pointer.format(key), text, key)
            for absent in ("**Standards applied:**", "**Practice skills"):
                self.assertNotIn(absent, text, key)
            section = role_section(key)
            # Every standard, with its whole wording and edition, is a row of the role's section, and nowhere is one lost.
            for name, note in team_reference.role_standards_cells(data["roles"][key]["standards"]):
                self.assertIn(f"\n| {name} | {note or '—'} |\n", section, (key, name))
            for x in data["roles"][key].get("extensions", []):
                self.assertIn(x["name"], section, (key, x["name"]))
        self.assertIn("<!-- aidd:gen roles:by-role -->", (TEAM / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8"))

    def test_every_relative_link_in_an_installed_file_resolves_to_an_installed_file(self):
        """B5: a project install ships each skill whole, so a link from a skill, a reference, or a role file lands on a file."""
        files = team_install.team_files([*team_install.NATIVE_AGENT_HARNESSES, "cursor"])
        self.assertTrue(any("/references/" in rel for rel in files))
        broken = []
        for rel, text in files.items():
            if not rel.endswith(".md"):
                continue
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if re.match(r"[a-z][a-z0-9+.-]*:|#", target):
                    continue  # a URL or an anchor
                found = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target.split("#")[0]))
                if found not in files:
                    broken.append((rel, target))
        self.assertEqual(broken, [])

    def test_a_link_to_another_skill_names_the_installed_folder(self):
        for text, want in (
            ("[a](../modular-monolith/references/x.md)", "[a](../aidd-modular-monolith/references/x.md)"),
            ("[a](../aidd-modular-monolith/references/x.md)", "[a](../aidd-modular-monolith/references/x.md)"),
            ("[a](../SKILL.md#implement)", "[a](../SKILL.md#implement)"),
            ("[a](references/x.md)", "[a](references/x.md)"),
            ("[a](https://example.com/../x/y)", "[a](https://example.com/../x/y)"),
            ("", ""),
        ):
            self.assertEqual(team_install._team_text(text), want, text)

    def test_an_installed_agent_file_points_to_an_installed_reference(self):
        # Without the plugin the team skill is not installed, so `aidd init --aidd-team` writes the roles reference too.
        files = team_install.team_files(list(team_install.NATIVE_AGENT_HARNESSES))
        ref = files[team_install.TEAM_ROLES_REF]
        self.assertIn("\n### architect\n", ref)
        self.assertNotIn("aidd-team:", ref)
        own_tools = [k for k, r in team_registry.roles()["roles"].items() if r.get("mcp_tools")]  # these read no reference
        for rel, text in files.items():
            if (
                "/agents/" in rel and "/skills/" not in rel and not any(f"aidd-{k}." in rel for k in own_tools)
            ):  # a role's file; a skill's `agents/` folder holds Codex's metadata
                self.assertIn(f"(`{team_install.TEAM_ROLES_REF}`), section `", text, rel)
                self.assertNotIn("references/roles.md", text, rel)
        self.assertEqual(team_install.team_files([], claude_files=False), {})

    def test_every_role_applies_at_most_twelve_standards(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            self.assertLessEqual(len(role["standards"]), self.MAX_STANDARDS, key)

    def test_a_scoped_contract_rule_names_real_roles_or_steps(self):
        data = resources.load_json("roles.json")
        names = set(data["roles"]) | set(data["graph"]["steps"])
        scoped = [x for x in data["graph"]["contract"] if isinstance(x, dict) and "applies_to" in x]
        self.assertTrue(scoped)
        for x in scoped:
            self.assertLessEqual(set(x["applies_to"]), names, x["rule"][:40])
            # A rule scoped to everyone is a rule without a scope.
            self.assertTrue(any(x["rule"] not in team_registry.contract_for(k) for k in data["roles"]), x["rule"][:40])

    def test_the_debugging_and_helper_rules_are_in_the_contract(self):
        # Each rule is found in the registry by its opening words, then checked by where it binds and where it renders;
        # rewording the rest of a rule leaves this test alone.
        data = resources.load_json("roles.json")
        items = data["graph"]["contract"]

        def rule(opening: str):
            found = [x for x in items if (x if isinstance(x, str) else x["rule"]).startswith(opening)]
            self.assertEqual(len(found), 1, opening)
            return found[0]

        repro, helper = rule("No fix without a reproduction"), rule("Use AI as a development team does")
        # The reproduction rule binds only the roles and steps that fix code; the helper rule binds every role that
        # writes, since only those have helpers.
        self.assertIsInstance(repro, dict)
        self.assertIsInstance(helper, dict)
        for key in data["order"]:
            binds = team_registry.contract_for(key)
            agent = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertEqual(helper["rule"] in binds, bool(data["roles"][key]["writes"]), key)
            self.assertEqual(helper["rule"] in binds, helper["rule"] in agent, key)
            self.assertEqual(repro["rule"] in binds, repro["rule"] in agent, key)
        self.assertIn(repro["rule"], team_registry.contract_for("developer"))
        self.assertNotIn(repro["rule"], team_registry.contract_for("reviewer"))

    def test_the_developer_searches_before_writing_new_code(self):
        text = (TEAM / "agents" / "developer.md").read_text(encoding="utf-8")
        playbook = text.split("\n## Playbook\n", 1)[1].split("\n## ", 1)[0]
        steps = [ln for ln in playbook.splitlines() if ln[:1].isdigit() and ". **" in ln]
        labels = [s.split("**")[1] for s in steps]
        search = labels.index("Search first.")
        # Searching comes before any step that writes code, and its finding goes where a reviewer sees it.
        self.assertLess(search, labels.index("Test-driven."))
        self.assertLess(search, labels.index("Surgical and minimal."))
        self.assertIn("before writing new code", steps[search])
        # After Spec approval the developer cannot write the Spec (the hash covers Context), so the reviewer reads the
        # finding on the handoff note.
        self.assertTrue(says(steps[search], "handoff note", "reviewer"), steps[search])

    def test_an_edition_is_printed_once_per_agent_file(self):
        from aidd.docsgen import team_reference

        stds = [{"id": "x", "name": "X for A", "release": "1.0", "edition": "1.0 (published 2020-01-01); notes"}, {"id": "x", "name": "X for B"}]
        self.assertEqual(team_reference.role_standards_text(stds, full=False), ["X for A (1.0)", "X for B"])
        self.assertEqual(team_reference.role_standards_text(stds), ["X for A (1.0 (published 2020-01-01); notes)", "X for B"])


class BuilderSideRulesTests(unittest.TestCase):
    """The builder's rules against repeat mistakes. Each lives in one place the developer reads when it acts: the
    developer's Done-when for a fix and for a change a person runs, debugging for every site a bug's cause reaches, test-design for
    open-ended inputs. The reviewer's side (test strength, the other paths) is in `REVIEW.md` and `code-review`."""

    def skill(self, name: str) -> str:
        return (TEAM / "skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def test_the_developers_done_when_holds_the_fix_and_the_run_as_a_person_rules(self):
        done = team_registry.roles()["roles"]["developer"]["done_when"]
        self.assertTrue(says(done, "fix", "invariant", "one sentence"))
        self.assertTrue(says(done, "every site", "root cause", "each edit traced", "backfill Spec"))
        self.assertTrue(says(done, "`new_behavior` test", "fails before the fix"))
        self.assertTrue(says(done, "CLI", "config", "scratch copy", "another folder", "typo", "dry run", "for real"))
        self.assertTrue(says(done, "output", "handoff"))
        self.assertIn(done, (TEAM / "agents" / "developer.md").read_text(encoding="utf-8"))

    def test_running_it_as_a_person_is_said_once_in_the_practice_skills_and_the_other_roles(self):
        # The step lives in the developer's Done-when only. A copy in a practice skill, or in another role's text, would drift.
        holders = [f for f in sorted(TEAM.rglob("*.md")) if says(f.read_text(encoding="utf-8"), "another folder", "typo")]
        self.assertEqual([f.name for f in holders], ["developer.md"], holders)
        roles_json = json.dumps(resources.load_json("roles.json"))
        self.assertEqual(roles_json.count("another folder"), 1)

    def test_debugging_fixes_the_cause_everywhere_and_test_design_covers_open_ended_inputs(self):
        debugging = self.skill("debugging")
        self.assertTrue(says(debugging, "cause everywhere", "not only where it showed"))
        self.assertTrue(says(debugging, "git grep", "other sites"))
        self.assertTrue(says(debugging, "Fix each", "same change"))
        test_design = self.skill("test-design")
        self.assertTrue(says(test_design, "open-ended", "order", "paths", "names"))
        self.assertTrue(says(test_design, "invariant", "table", "generated"))


class VerifierTests(unittest.TestCase):
    """The verifier writes the tests in Specify, then runs the change and reports in Verify; it never writes the code."""

    def test_the_verifier_writes_tests_and_a_preview_but_not_the_code(self):
        data = team_registry.roles()
        v = data["roles"]["verifier"]
        self.assertEqual((v["writes"], v["in_scope"], v["tier"]), (["{spec}", "{tests}", "{docs:test-plan}"], False, "execution"))
        self.assertEqual(v["steps"], ["Specify", "Verify"])
        self.assertIn("Acceptance", v["done_when"])
        # Its report is about one commit: it starts with the head SHA, and a new push makes it stale.
        self.assertIn("head SHA", v["done_when"])
        self.assertIn("stale", v["done_when"])
        front = dict(re.findall(r"^(\w+): (.+)$", (TEAM / "agents" / "verifier.md").read_text(encoding="utf-8").split("---")[1], re.M))
        tools = {t.strip() for t in front["tools"].split(",")}
        self.assertIn("Bash", tools)
        self.assertLessEqual({"Write", "Edit"}, tools)
        # It sits after the builders and before Review, in a step of its own, with no command of its own: review runs it
        # beside the readers on every head, a rework's new head too, and it hands to the readers.
        flows = {f["command"]: f for f in data["graph"]["flows"]}
        self.assertNotIn("verify", flows)
        self.assertFalse((TEAM / "commands" / "verify.md").exists())
        self.assertIn("Verify", flows["review"]["steps"])
        self.assertIn("verifier", [r for group in flows["review"]["runs"] for r in group])
        review = (TEAM / "commands" / "review.md").read_text(encoding="utf-8")
        for must in ("head SHA", "aidd test --spec", "each Acceptance line", "never the builder's evidence"):
            self.assertIn(must, review, must)
        implement = next(f for f in data["graph"]["flows"] if f["command"] == "implement")
        self.assertNotIn(["verifier"], implement["runs"])
        self.assertIn("Verify", implement["stops_when"])
        steps = data["graph"]["steps"]
        self.assertEqual(steps.index("Verify"), steps.index("Implement") + 1)
        handoff = next(h for h in data["graph"]["handoffs"] if h["from"] == ["verifier"] and "reviewer" in h["to"])
        self.assertIn("reviewer", handoff["to"])
        self.assertTrue(any("verifier's mismatch" in x for x in data["graph"]["contract"]))


class ReworkTests(unittest.TestCase):
    def test_the_rework_goes_back_to_review_and_never_widens_scope(self):
        # Rework is a mode of Implement: its new head goes to /aidd-team:review, which runs Verify again.
        data = team_registry.roles()
        self.assertNotIn("rework", [f["command"] for f in data["graph"]["flows"]])
        implement = next(f for f in data["graph"]["flows"] if f["command"] == "implement")
        self.assertIn("rework", [m["name"] for m in implement["modes"]], "rework is a mode of the implement command, which a person starts")
        text = (TEAM / "commands" / "implement.md").read_text(encoding="utf-8").split("\n## Rework mode\n", 1)[1]
        self.assertIn("the next step is `/aidd-team:review` on that head", text)
        for must in ("One fix per comment", "aidd test", "Specify", "Never approve", "never merge without the person's yes", "frozen"):
            self.assertIn(must, text, must)
        self.assertNotIn("--force", text)


class RaciTests(unittest.TestCase):
    """The RACI table in docs/TEAM.md is hand-written prose about generated data.

    A role is responsible only in the loop steps the registry gives it ("work only in your loop steps").
    A table nobody checks against its source drifts, so this holds it to the registry.
    """

    def test_a_role_is_responsible_only_in_the_steps_it_has(self):
        import re

        data = team_registry.roles()
        text = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        block = text.split("## Who is responsible (RACI)", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in block.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
        self.assertGreaterEqual(len(rows), 10, "the RACI table lost its rows")
        step_of = lambda label: label.split(":")[0].strip()  # noqa: E731
        for ln in rows:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            step, responsible = step_of(cells[0]), cells[1]
            self.assertIn(step, data["graph"]["steps"], f"RACI names a step the loop does not have: {step!r}")
            for role in re.findall(r"[a-z]+-[a-z-]+", responsible):
                self.assertIn(role, data["roles"], f"RACI names a role the registry does not have: {role!r}")
                self.assertIn(
                    step, data["roles"][role]["steps"], f"RACI makes `{role}` responsible for {step}, but the registry gives it {data['roles'][role]['steps']}"
                )

    def test_the_router_skill_names_every_role_by_its_current_key(self):
        """Its description is hand-written frontmatter and lists every role by name.

        A rename silently leaves a router trigger pointing at a role that no longer exists, and
        nothing else would notice: the description is above the first generated block.
        """
        text = (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        for key in team_registry.roles()["order"]:
            self.assertIn(key, text, f"`{key}` is a role but is not a router trigger in the aidd-team skill")
        inner = text.split("names a role (", 1)[1].split(")", 1)[0]
        listed = {x.strip().strip("`") for x in inner.split(",") if x.strip()}
        self.assertEqual(listed, set(team_registry.roles()["order"]), "the router trigger list and the registry disagree")

    def test_every_role_appears_in_the_raci_table(self):
        text = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8").split("## Who is responsible (RACI)", 1)[1].split("\n## ", 1)[0]
        for key in team_registry.roles()["order"]:
            self.assertIn(key, text, f"`{key}` is in the registry but nowhere in the RACI table")


class CapabilityTests(unittest.TestCase):
    """The team covers every software life cycle process an engineering firm is measured against, and says who acts."""

    def test_every_12207_process_is_mapped_to_something_real(self):
        from aidd.cli import parser

        caps = team_registry.roles()["graph"]["capabilities"]
        processes = caps["processes"]
        self.assertIn("12207", caps["standard"])
        self.assertEqual(len(processes), 30)  # ISO/IEC/IEEE 12207:2017 defines thirty processes
        self.assertEqual(len({c["process"] for c in processes}), 30)
        roles = set(team_registry.roles()["roles"])
        commands = {p.stem for p in (TEAM / "commands").glob("*.md")}
        subcommands = set(parser.build_parser()._subparsers._group_actions[0].choices)
        for c in processes:
            self.assertEqual(c["coverage"] == "humans", not c["by"], c["process"])
            for by in c["by"]:
                if by.startswith("/aidd-team:"):
                    self.assertIn(by.removeprefix("/aidd-team:"), commands, (c["process"], by))
                elif by.startswith("aidd "):
                    self.assertIn(by.split()[1], subcommands, (c["process"], by))
                elif by.startswith("aidd-team:"):
                    self.assertTrue((TEAM / "skills" / by.removeprefix("aidd-team:") / "SKILL.md").is_file(), (c["process"], by))
                else:
                    self.assertIn(by, roles, (c["process"], by))

    def test_the_map_reaches_the_team_page(self):
        text = (ROOT / "docs" / "TEAM-REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen roles:capabilities -->", text)
        for c in team_registry.roles()["graph"]["capabilities"]["processes"]:
            self.assertIn(f"| {c['process']} |", text)


if __name__ == "__main__":
    unittest.main()
