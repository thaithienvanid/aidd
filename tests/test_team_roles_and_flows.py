"""A lean aidd-team. Right-sized models per tier, a lead that routes and never authors, a loop contract rendered
once and per role, small agent files, and the quick `fix` and `mvp` flows."""

import json
import re
import shutil
import tempfile
import tomllib
import unittest

import budget_shares
import budgets
from pathlib import Path

import helpers
from helpers import ROOT

from aidd.docsgen import generate
from aidd.docsgen import pack_render
from aidd.setup import adoption
from aidd.setup import team_install
from aidd.knowledge import agent_models, team_registry
from aidd.kernel import json_schema, resources

TEAM = ROOT / "plugins" / "aidd-team"
SKILL = TEAM / "skills" / "aidd-team" / "SKILL.md"
TEAM_MD = ROOT / "docs" / "TEAM.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def agent(key: str) -> str:
    return text(TEAM / "agents" / f"{key}.md")


def front(key: str) -> tuple[dict[str, str], list[str]]:
    head = agent(key).split("---")[1]
    fields = dict(re.findall(r"^(\w+): (.+)$", head, re.M))
    skills = re.findall(r"^  - (.+)$", head.split("\nskills:\n", 1)[1], re.M) if "\nskills:\n" in head else []
    return fields, skills


def body(key: str) -> str:
    t = agent(key)
    return t[t.index("\n---", 4) + 4 :]


def command(name: str) -> str:
    return text(TEAM / "commands" / f"{name}.md")


def flow(name: str) -> dict:
    return next(f for f in team_registry.roles()["graph"]["flows"] if f["command"] == name)


def rule(opening: str) -> str:
    found = [x for x in team_registry.roles()["graph"]["contract"] if x.startswith(opening)]
    assert len(found) == 1, opening
    return found[0]


def binds(opening: str) -> set[str]:
    r = rule(opening)
    return {k for k in team_registry.roles()["order"] if r in team_registry.contract_for(k)}


def writers() -> set[str]:
    return {k for k, r in team_registry.roles()["roles"].items() if r["writes"]}


class TierTests(unittest.TestCase):
    """The cheap roles run on a mid-size model, not the session's (often the strongest) one."""

    def test_the_claude_code_mapping(self):
        # Two tiers: Sonnet is the smallest model aidd runs an agent on in Claude Code.
        self.assertEqual(team_registry.MODELS_BY_HARNESS["claude-code"], {"reasoning": "opus", "execution": "sonnet"})
        for h, m in team_registry.MODELS_BY_HARNESS.items():
            self.assertEqual(set(m), {"reasoning", "execution"}, h)

    def test_each_role_sits_in_its_tier(self):
        roles = team_registry.roles()["roles"]
        tiers = {k: r["tier"] for k, r in roles.items()}
        self.assertEqual(
            {k for k, t in tiers.items() if t == "reasoning"},
            {"architect", "security-engineer", "reviewer", "delegate", "compliance-analyst", "product-manager", "product-designer"},
        )
        self.assertEqual(set(tiers.values()), {"reasoning", "execution"})
        self.assertEqual(tiers["verifier"], "execution")
        for k, r in roles.items():
            fields, _ = front(k)
            self.assertEqual(fields["model"], team_registry.tier_model(r["tier"]), k)
            self.assertNotEqual(fields["model"], "inherit", k)
            self.assertNotIn("inherits the session's model", r["tier_reason"], k)

    def test_a_role_takes_its_own_entry_else_its_tiers(self):
        self.assertEqual(agent_models.resolve_agent_model({"execution": "anthropic/claude-sonnet-5"}, "verifier"), "anthropic/claude-sonnet-5")
        self.assertEqual(agent_models.resolve_agent_model({"execution": "x/a", "verifier": "x/b"}, "verifier"), "x/b")
        self.assertIsNone(agent_models.resolve_agent_model({"reasoning": "x/a"}, "verifier"))
        # A stale `mechanical` key names no tier and no role, so it selects nothing.
        self.assertIsNone(agent_models.resolve_agent_model({"mechanical": "x/b"}, "verifier"))

    def test_no_mechanical_tier(self):
        """Two tiers only: no role, harness map, tier meaning, or schema names `mechanical`."""
        roles = team_registry.roles()["roles"]
        self.assertEqual(list(team_registry.TIER_MEANING), ["reasoning", "execution"])
        self.assertEqual(set(helpers.TIER_MEANING), set(team_registry.TIER_MEANING))
        for k, r in roles.items():
            self.assertIn(r["tier"], team_registry.TIER_MEANING, k)
            self.assertNotIn("mechanical", r["tier_reason"], k)
        for h, m in team_registry.MODELS_BY_HARNESS.items():
            self.assertNotIn("mechanical", m, h)
        enum = json.loads(text(ROOT / "schemas" / "roles.schema.json"))["properties"]["roles"]["additionalProperties"]["properties"]["tier"]["enum"]
        self.assertEqual(enum, ["reasoning", "execution"])
        self.assertFalse(any("mechanical" in x for x in team_registry.roles()["graph"]["lead"]))
        # No generated agent file runs on Haiku: the verifier, the cheapest role, runs on Sonnet.
        for path in sorted((TEAM / "agents").glob("*.md")):
            self.assertNotIn("\nmodel: haiku\n", text(path), path.name)
        self.assertEqual(front("verifier")[0]["model"], "sonnet")

    def test_inherit_is_an_opt_in_override(self):
        base = {"aidd_version": "1.0.0", "profile": "solo"}
        self.assertEqual(json_schema.validate(dict(base, agents={"models": {"execution": "inherit", "reviewer": "inherit"}}), "config.schema.json"), [])
        self.assertEqual(agent_models.harness_model("claude-code", "inherit"), "inherit")
        for h in ("codex", "opencode", "kiro", "copilot"):
            self.assertIsNone(agent_models.harness_model(h, "inherit"), h)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"]))
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(text(cfg) + "\nagents:\n  models:\n    execution: inherit\n", encoding="utf-8")
            team_install.install_team(root, [], harnesses=["codex"])
            self.assertIn("\nmodel: inherit\n", text(root / ".claude/agents/aidd-developer.md"))
            self.assertIn("\nmodel: opus\n", text(root / ".claude/agents/aidd-architect.md"))
            codex = text(root / ".codex/agents/aidd-developer.toml")
            self.assertNotIn("model", tomllib.loads(codex))
            self.assertNotIn("cannot select", codex)

    def test_the_docs_say_the_same(self):
        skill = text(SKILL)
        for word in ("`reasoning`", "`execution`", "`inherit`", "`agents.models`"):
            self.assertIn(word, skill, word)
        cost = text(TEAM_MD).split("## What it costs", 1)[1].split("\n## ", 1)[0]
        self.assertIn("<!-- aidd:gen roles:tiers -->", cost)
        for word in ("`inherit`", "`agents.models`"):
            self.assertIn(word, cost, word)
        for page in (skill, cost):
            self.assertNotIn("`mechanical`", page)
        self.assertNotIn("It inherits the session's model (`inherit`), so you choose the model once", text(TEAM_MD))
        tiers = generate.render("roles:tiers")
        for tier, model in team_registry.MODELS_BY_HARNESS["claude-code"].items():
            self.assertIn(f"`{tier}`", tiers)
            self.assertIn(f"`{model}`", tiers)


class LeadTests(unittest.TestCase):
    """The session that runs a command routes; it never authors, re-pastes, or waits one completion at a time."""

    def test_every_command_carries_the_lead_rules(self):
        self.assertTrue(team_registry.roles()["graph"]["lead"])
        for path in sorted((TEAM / "commands").glob("*.md")):
            self.assertIn("<!-- aidd:gen roles:lead -->", text(path), path.name)

    def test_the_lead_rules_say_it(self):
        lead = generate.render("roles:lead")
        # Role placement: the lead plays a role only for a small step of its own work, and never checks its own work;
        # every role it starts gets its context pack.
        for must in (
            "place each role",
            "Never play a role that checks, tests, or reviews work you wrote",
            "always start",
            "never pasted facts",
            "files by path",
            "in one message",
            "wait for all",
            "`model`",
            "fresh session",
            "`/clear`",
            "one Edit",
            "handoff note",
            "`aidd validate`",  # Each flow ends with a note it passes, its `stopped_at` starting with a stop code
            "`stopped_at`",
        ):
            self.assertIn(must, lead, must)
        # The model comes from the role's agent file, so the lead never carries a literal that the config could not change.
        self.assertIn("full model id or `inherit`, pass none", lead)
        for model in team_registry.MODELS_BY_HARNESS["claude-code"].values():
            self.assertNotIn(f"`{model}`", lead)
        # A command's roles are named only where it runs them, so the shared block names none.
        self.assertNotRegex(lead, r"`aidd-team:[a-z-]+`")
        # A section is changed with one Edit: one Write of a whole file to change a section risks the rest of it.
        self.assertNotIn("one Write, not many Edits", lead)
        self.assertNotIn("one Write, not many Edits", generate.render("roles:contract"))

    def test_the_lead_rules_that_the_build_taught_stay(self):
        """Each rule is one a real mistake taught, and each stays in the lead's rules: a lost one fails here, by the fact it holds."""
        from aidd.workitems import handoff_notes

        lead = generate.render("roles:lead")
        rules = {n: x for n, x in enumerate(team_registry.roles()["graph"]["lead"], 1)}
        rule_with = lambda word: [n for n, x in rules.items() if word in x]  # noqa: E731
        facts = {  # the fact, the words that hold it, in one rule
            "bring work over one commit at a time and run the changed-files checks between": ("one commit at a time", "`aidd test --changed`"),
            "regenerate a generated file's conflict, never pick a side": ("generates", "generator", "never pick a side by hand"),
            "take a role's files by its folder, never by a word in the path": ("folder the role owns", "never by a word in the path"),
            "run the whole suite once for each batch, then read the tree's state": ("whole suite once for each batch", "`git status`"),
            "commit named paths": ("named paths, never everything",),
            "never end the turn while a role runs, and stop with `waiting` past the session": ("Never end your turn", "`waiting`"),
            "answer each open decision before the merge": ("`open_decisions`", "`decided`", "`needs`"),
            "under autopilot the lead keeps the session": ("`/aidd-team:autopilot`", "keep the session"),
        }
        for fact, words in facts.items():
            with self.subTest(fact):
                self.assertEqual(len([n for n in rule_with(words[0])]), 1, f"one rule holds {words[0]!r}")
                (n,) = rule_with(words[0])
                for word in words:
                    self.assertIn(word, rules[n], f"rule {n}: {word}")
        # A code the lead names is a code the schema owns.
        for code in re.findall(r"`(waiting|retries|blocked|quota|harness)`", lead):
            self.assertIn(code, handoff_notes.stop_codes())
        # The lead's rules name no product, framework, or domain: they hold for any project.
        self.assertNotRegex(lead, r"(?i)\b(orca|stripe|postgres|django|react)\b")

    def test_the_three_cases_of_merge_approval_are_one_block_in_each_flow_that_ends_there(self):
        cases = team_registry.roles()["graph"]["merge_approval"]
        self.assertEqual(len(cases), 3, "a local trunk, a platform under team, a platform under solo")
        for where in ("local trunk", "platform under `team`", "platform under `solo`"):
            self.assertEqual(len([c for c in cases if where in c.split(",")[0]]), 1, where)
        pages = [ROOT / ".agents" / "skills" / "aidd" / "references" / "graph.md", TEAM / "commands" / "autopilot.md", TEAM / "commands" / "fix.md"]
        block = generate.render("roles:merge-approval")
        for page in pages:
            with self.subTest(page=page.name):
                self.assertIn(f"<!-- aidd:gen roles:merge-approval -->\n{block}\n<!-- aidd:end -->", text(page))

    def test_the_handoff_note_carries_a_cost_line(self):
        self.assertIn("`spend`", rule("End every run with the handoff note"))


class SharedRulesTests(unittest.TestCase):
    """Every agent file carries the aidd skill's hard rules in short, scoped to the roles and steps they bind."""

    def test_every_role_carries_the_shared_rules(self):
        for key in team_registry.roles()["order"]:
            text = agent(key)
            self.assertIn("- **Hard rules (in short):**", text, key)
            for rule in team_registry.shared_rules_carried_for(key):  # less the ones its preloaded aidd skill gives (CoreSkillCoverageTests)
                self.assertIn(rule, text, key)
            self.assertIn("never approve", text.split("- **Loop steps:**", 1)[0], key)

    def test_every_role_that_commits_says_assisted_by(self):
        for key in writers():
            self.assertIn("`Assisted-by: <harness>/<model>`", "\n".join(team_registry.shared_rules_for(key)), key)
        for key in ("tech-writer", "sre"):
            self.assertIn("Assisted-by", agent(key), key)

    def test_each_rule_names_the_step_it_applies_to(self):
        roles = team_registry.roles()["roles"]
        scope = next(x for x in team_registry.roles()["graph"]["shared_rules"] if "`scope`" in x)
        self.assertIn("in Implement or with no Spec", scope)
        verified = next(x for x in team_registry.roles()["graph"]["shared_rules"] if x.startswith("Done means verified"))
        retries = next(x for x in team_registry.roles()["graph"]["shared_rules"] if "retry_count" in x)
        for key, r in roles.items():
            self.assertEqual(verified in team_registry.shared_rules_for(key), "Implement" in r["steps"], key)  # never the verifier, which fixes nothing
            self.assertEqual(retries in team_registry.shared_rules_for(key), "Implement" in r["steps"], key)
            if verified in team_registry.shared_rules_for(key):
                self.assertIn("Bash", pack_render.split_tools(front(key)[0]["tools"]), key)  # a role told to run the tests has a shell
        skill = text(ROOT / ".agents" / "skills" / "aidd" / "SKILL.md")
        # The hard rules run most critical first: the scope rule is 4, and done-means-verified is 8.
        hard_rules: dict[int, str] = {}  # the first numbered list, each rule with its indented sub-rules
        for line in skill[skill.index("\n1. ") + 1 :].splitlines():
            number, dot, rest = line.partition(". ")
            if dot and number.isdigit():
                if int(number) != len(hard_rules) + 1:
                    break
                hard_rules[int(number)] = rest
            elif hard_rules and line.startswith("   "):
                hard_rules[len(hard_rules)] += "\n" + line
            elif hard_rules and line.strip():
                break
        self.assertTrue(hard_rules[1].startswith("Ask before every `ask`") and "the person's yes" in hard_rules[1], hard_rules[1])
        self.assertIn("edit only", hard_rules[4])  # the scope rule
        self.assertTrue(hard_rules[8].startswith("Done means verified"), hard_rules[8])
        self.assertTrue(team_registry.roles()["graph"]["contract"][0].startswith("Never skip a step or a human decision"))
        self.assertTrue(team_registry.roles()["graph"]["shared_rules"][0].startswith("Humans decide"))

    def test_a_read_only_role_returns_its_note_for_the_lead_to_post(self):
        """The reviewer has no Write tool, so they cannot put the note in the Spec themselves."""
        post = rule("End every run with the handoff note")
        ret = rule("Return the handoff note")
        for key in team_registry.roles()["order"]:
            tools = set(pack_render.split_tools(front(key)[0]["tools"]))
            can_write = bool(tools & {"Write", "Edit"})
            self.assertEqual(post in team_registry.contract_for(key), can_write, key)
            self.assertEqual(ret in team_registry.contract_for(key), not can_write, key)
        self.assertIn("final message", ret)
        self.assertIn("the lead", ret)


class ProposeTests(unittest.TestCase):
    """The delivery manager, not the lead, records the client's answers in `questions`; the product manager writes
    the goal, needs, and options before the go/no-go."""

    def test_the_delivery_manager_records_the_answers(self):
        runs = flow("propose")["runs"]
        self.assertEqual(runs[:2], [["delivery-manager"], ["product-manager"]])
        self.assertIn("delivery-manager", runs[2])
        self.assertEqual(runs[-1], ["tech-writer"])
        t = command("propose")
        self.assertIn("records them in `questions`", t)
        self.assertIn("the lead never writes them", t)
        self.assertIn("on the execution tier's model", t)


class ContractTests(unittest.TestCase):
    """The contract is rendered once in full, and each agent file carries only the rules that bind it."""

    def test_readers_carry_no_builder_rules(self):
        for key in ("reviewer",):
            joined = "\n".join(team_registry.contract_for(key))
            for absent in ("`tests.commands`", "Use AI as a development team does", "a helper's 'done' is a claim", "Research first"):
                self.assertNotIn(absent, joined, (key, absent))

    def test_scoped_rules_bind_who_they_should(self):
        self.assertEqual(binds("Use AI as a development team does"), writers())
        self.assertIn("their 'done' is a claim", rule("Use AI as a development team does"))
        self.assertEqual(binds("Research first"), {"architect", "security-engineer"})
        research = rule("Research first")
        for must in ("in Plan and Specify only", "no pack", "due for review"):
            self.assertIn(must, research)
        packs = [x for x in team_registry.roles()["graph"]["contract"] if "`tests.commands`" in x]
        self.assertEqual(len(packs), 1)
        self.assertEqual({k for k in team_registry.roles()["order"] if packs[0] in team_registry.contract_for(k)}, {"architect", "verifier"})

    def test_the_whole_contract_is_rendered_once(self):
        roles_ref = text(TEAM / "skills" / "aidd-team" / "references" / "roles.md")
        self.assertIn("<!-- aidd:gen roles:contract -->", roles_ref)
        for r in team_registry.roles()["graph"]["contract"]:
            self.assertEqual(roles_ref.count(r), 1, r[:40])

    def test_agent_files_are_about_one_screen(self):
        for key in team_registry.roles()["order"]:
            t = agent(key)
            self.assertTrue(
                budgets.within(len(t.encode()), budgets.ROLE_FILE_BYTES),
                budgets.make_room(f"{key}.md", len(t.encode()), budgets.ROLE_FILE_BYTES, cost=budgets.cost_of("role file")),
            )
            self.assertNotIn("**Extend with", t, key)

    def test_the_aidd_skill_is_preloaded_only_where_specs_or_tests_are_written(self):
        # The verifier writes tests, but its Verify run needs no 13 KB rulebook, so it loads the skill by name in Specify.
        by_name = {"verifier"}
        for key, r in team_registry.roles()["roles"].items():
            writes_spec_or_tests = bool({"{spec}", "{specs_dir}", "{tests}"} & set(r["writes"])) or "{tests}" in r.get("writes_unfrozen", [])
            _, skills = front(key)
            self.assertEqual("aidd" in r["preload"], writes_spec_or_tests and key not in by_name, key)
            self.assertEqual(r["preload"][:1] == ["aidd"], skills[:1] == ["aidd:aidd"], key)
            self.assertEqual([s for s in skills if s != "aidd:aidd"], [f"aidd-team:{x}" for x in r["preload"] if x != "aidd"], key)
        for key in ("developer", "architect", "product-manager"):
            self.assertEqual(front(key)[1][0], "aidd:aidd", key)
        for key in ("verifier", "reviewer", "security-engineer", "sre", "compliance-analyst"):
            self.assertNotIn("aidd:aidd", front(key)[1], key)

    def test_each_role_lists_the_practice_skills_its_files_call_for(self):
        # A role that writes code, a UI, or docs lists that type's practice skills, and the lead names them in each role's prompt,
        # so they load by name and cost no agent file a byte (a preload would cost every run its whole text).
        data = team_registry.roles()
        by_files = {x["files"]: x["skills"] for x in data["graph"]["file_skills"]}
        code = {"{scope}", "{scope:assigned}", "{skeleton}", "{tests}"}

        def writes(role: dict) -> set[str]:
            out, paths = set(), role["writes"] + role.get("writes_unfrozen", [])
            if code & set(paths):
                out.add("code")
            if "{design}" in paths:
                out.add("a UI")
            if any(p.startswith(("{docs:", "docs/", "{spec", "{proposals_dir}", "{living}", "{explorations}")) or p.endswith(".md") for p in paths):
                out.add("docs")
            return out

        for key, role in data["roles"].items():
            for files in writes(role):
                self.assertLessEqual(set(by_files[files]), set(role["skills"]), (key, files))
        self.assertEqual(writes(data["roles"]["sre"]), {"code", "docs"})
        for flow in ("implement", "mvp"):
            self.assertIn("for code, `maintainable-code` and `secure-coding`", command(flow), flow)
            self.assertNotIn("FILE_SKILLS", command(flow), flow)

    def test_each_roles_start_total_keeps_to_its_budget(self):
        """The agent body plus its preloaded skills, and graph.md where it preloads the aidd skill, for each role. It was 25.5 KB a
        role on average before the lean team and 18.0 KB before the preloaded skills' dates and sources moved to the roles
        reference. One heavy role can no longer grow behind a mean: each role keeps to budgets.ROLE_START_BYTES."""
        for key, size in budget_shares.role_start_text().items():
            with self.subTest(role=key):
                self.assertTrue(
                    budgets.within(size, budgets.ROLE_START_BYTES),
                    budgets.make_room(f"{key}'s start total", size, budgets.ROLE_START_BYTES, cost=budgets.cost_of("role start")),
                )

    def test_a_role_that_preloads_the_aidd_skill_pays_for_loop_md_and_one_that_does_not_does_not(self):
        loop = len((ROOT / ".agents" / "skills" / "aidd" / "references" / "graph.md").read_bytes())
        sizes = budget_shares.role_start_text()
        for key in team_registry.roles()["order"]:
            skills = front(key)[1]
            plain = len(body(key).encode())
            for name in skills:
                plugin, _, skill = name.partition(":")
                base = ROOT / ".agents" / "skills" if plugin == "aidd" else TEAM / "skills"
                plain += len((base / skill / "SKILL.md").read_bytes())
            with self.subTest(role=key):
                self.assertEqual(sizes[key], plain + (loop if "aidd:aidd" in skills else 0))


class CoreSkillCoverageTests(unittest.TestCase):
    """A role reaches every rule that binds it through its own file or through the aidd skill it preloads, never through
    neither, and its file does not repeat what that skill gives it (the fixed text per subagent is a cost every run pays)."""

    CORE = ROOT / ".agents" / "skills" / "aidd" / "SKILL.md"
    NAMES = ("shared_rules", "contract")

    def phrases(self) -> dict[str, list[str] | None]:
        loop = team_registry.roles()["graph"]
        return {rule: found for name in self.NAMES for rule, found in zip(loop[name], loop[f"{name}_in_core_skill"], strict=True)}

    def binding(self, key: str, data: dict | None = None) -> list[str]:
        return [*team_registry.shared_rules_for(key, data), *team_registry.contract_for(key, data)]

    def test_each_rule_reaches_each_role_exactly_once(self):
        skill, found = text(self.CORE), self.phrases()
        for key in team_registry.roles()["order"]:
            preloads = "aidd:aidd" in front(key)[1]
            for rule in self.binding(key):
                with self.subTest(role=key, rule=rule[:50]):
                    in_file = rule in agent(key)
                    given = bool(found[rule]) and preloads and all(x in skill for x in found[rule])
                    self.assertTrue(in_file or given, "neither the file nor the preloaded skill gives the rule")
                    self.assertNotEqual(in_file, given, "the file repeats what the preloaded skill gives")

    def test_every_phrase_that_proves_a_rule_is_in_the_skill(self):
        skill = text(self.CORE)
        for rule, found in self.phrases().items():
            for phrase in found or []:
                with self.subTest(rule=rule[:50], phrase=phrase[:50]):
                    self.assertIn(phrase, skill)
            self.assertNotEqual(found, [], rule[:50])  # a rule names its proof or none; never an empty list

    def test_a_role_that_stops_preloading_the_skill_carries_every_rule_itself(self):
        fake = json.loads(json.dumps(team_registry.roles()))
        for r in fake["roles"].values():
            r["preload"] = [x for x in r.get("preload", []) if x != "aidd"]
        for key in fake["order"]:
            self.assertEqual(team_registry.shared_rules_carried_for(key, fake), team_registry.shared_rules_for(key, fake), key)
            self.assertEqual(team_registry.contract_carried_for(key, fake), team_registry.contract_for(key, fake), key)
        real = team_registry.roles()
        preloading = [k for k in real["order"] if "aidd" in real["roles"][k].get("preload", [])]
        self.assertTrue(preloading)
        for key in real["order"]:
            carried = team_registry.shared_rules_carried_for(key) + team_registry.contract_carried_for(key)
            self.assertEqual(len(carried) < len(self.binding(key)), key in preloading, key)


class ContradictionTests(unittest.TestCase):
    """The developer's precondition names its route, and the skill and the team page agree on the team of a change with no Spec."""

    FAST_TEAM = "A small minor change of any type runs one builder, and the reviewer past 20 changed lines (`/aidd-team:fix`); every other change with no Spec runs the builder, the verifier, and the reviewer."

    def test_the_developer_precondition_names_the_route(self):
        playbook = body("developer").split("\n## Playbook\n", 1)[1]
        first = next(ln for ln in playbook.splitlines() if ln.startswith("1. "))
        self.assertIn("Spec first:", first)
        self.assertIn("No Spec, or the emergency route:", first)

    def test_one_team_for_a_change_with_no_spec(self):
        self.assertIn(self.FAST_TEAM, text(SKILL))
        self.assertIn(self.FAST_TEAM, text(TEAM_MD))
        self.assertNotIn("runs one agent and no roles", text(TEAM_MD))


class RoleTextMatchesToolsTests(unittest.TestCase):
    """B2: a role file never tells a role to use a tool it was not given, and the delegate's rules never contradict its job."""

    HARNESS_TOOLS = ("Skill", "Agent", "WebFetch", "WebSearch", "Bash", "Read", "Grep", "Glob", "Write", "Edit")

    def named_tools(self, key: str) -> set[str]:
        """The tools a role file names: a harness tool in code marks, the `one Edit` rule, an aidd-team skill (loaded
        with `Skill`)."""
        t = body(key)
        found = set(re.findall(r"`(" + "|".join(self.HARNESS_TOOLS) + r")`", t))
        found |= {"Edit"} if re.search(r"\bone Edit\b", t) else set()
        found |= {"Skill"} if re.search(r"`aidd(?:-team)?:[a-z-]+`", t) else set()
        return found

    def given_tools(self, key: str) -> set[str]:
        entries = pack_render.split_tools(front(key)[0]["tools"])
        return {e.split("(", 1)[0].rsplit("__", 1)[-1] for e in entries}

    def test_every_tool_and_skill_a_role_file_names_is_in_its_tools_line(self):
        for key in team_registry.roles()["order"]:
            with self.subTest(key):
                self.assertEqual(self.named_tools(key) - self.given_tools(key), set())

    def test_a_role_with_only_its_own_tools_carries_no_rule_that_needs_more(self):
        roles = team_registry.roles()["roles"]
        for key, r in roles.items():
            for rules in (team_registry.shared_rules_for(key), team_registry.contract_for(key)):
                for x in rules:
                    with self.subTest(key=key, rule=x[:40]):
                        if r.get("mcp_tools"):
                            self.assertNotRegex(x, r"\baidd risk\b|domain pack|AGENTS\.md|one Edit|subagents|no `\.aidd/config\.yaml`")
                        if not r["writes"]:
                            self.assertNotIn("one Edit", x)

    def test_the_delegate_accepts_on_an_eligible_check_and_never_approves_anything_else(self):
        first = team_registry.shared_rules_for("delegate")[0]
        self.assertTrue(first.startswith("Accept only on an eligible check"), first)
        self.assertIn("never approve or merge anything else", first)
        self.assertNotIn("Humans decide", "\n".join(team_registry.shared_rules_for("delegate")))
        everyone_else = [k for k in team_registry.roles()["order"] if k != "delegate"]
        for key in everyone_else:
            self.assertTrue(team_registry.shared_rules_for(key)[0].startswith("Humans decide"), key)
            self.assertFalse(any(x.startswith("Accept only on an eligible check") for x in team_registry.shared_rules_for(key)), key)

    def test_the_delegate_does_not_run_anything_and_the_verifier_does_not_claim_to_write_no_file(self):
        self.assertNotIn("it runs the exact command", body("delegate"))
        self.assertNotIn("it writes no file", body("verifier"))
        self.assertIn("Write", self.given_tools("verifier"))


class FixFlowTests(unittest.TestCase):
    """The quick path for a small fix."""

    def test_the_flow(self):
        f = flow("fix")
        self.assertEqual((f["steps"], f["routes"], f["runs"]), (["Implement", "Verify", "Review"], ["minor"], [["developer", "tech-writer"], ["reviewer"]]))
        self.assertIn("Merge approval", f["stops_when"])

    def test_the_command(self):
        t = command("fix")
        for must in ("regression test", "red on base", "`aidd test`", "50 changed lines", "20 changed lines", "/aidd-team:specify"):
            self.assertIn(must, t, must)

    def test_the_fix_stops_when_the_route_is_above_minor(self):
        # A quick fix stays on the minor route: the command checks the route with `aidd risk` twice and sends a grown fix to Specify.
        t = command("fix")
        self.assertIn("aidd risk --paths", t)
        self.assertIn("--change-type <its type>", t)
        self.assertIn("is no longer minor", t)
        self.assertNotIn("standard", t)

    def test_the_reviewer_report_is_cut_to_the_review_limits(self):
        # As /aidd-team:review step 5 does: the reviewer's findings are cut to REVIEW.md's nit limit before the author sees them.
        review_cut = "Cut it to the REVIEW.md limits: at most five nits by default, and the rest as a count."
        self.assertIn(review_cut, command("review"))
        reviewer_step = next(ln for ln in command("fix").splitlines() if "`aidd-team:reviewer`" in ln)
        self.assertIn("REVIEW.md limits: at most five nits by default, and the rest as a count", reviewer_step)


class InstallLineTests(unittest.TestCase):
    """Each page that names the aidd plugin's install also names the optional team's."""

    def test_the_team_plugin_is_named_next_to_the_aidd_plugin(self):
        for rel in ("README.md", "docs/GUIDE.md", "llms-install.md"):
            t = text(ROOT / rel)
            self.assertIn("/plugin install aidd@aidd", t, rel)
            self.assertIn("/plugin install aidd-team@aidd", t, rel)


class FlowWhenTests(unittest.TestCase):
    """Each team command says when a person picks it, and TEAM.md lists them all in one table."""

    def test_every_flow_says_when(self):
        flows = team_registry.roles()["graph"]["flows"]
        required = json.loads(text(ROOT / "schemas" / "roles.schema.json"))["properties"]["graph"]["properties"]["flows"]["items"]["required"]
        self.assertIn("when", required)
        modes = [m | {"command": f"{x['command']} {m['name']}"} for x in flows for m in x.get("modes", [])]
        for f in [*flows, *modes]:
            when = f.get("when", "")
            self.assertTrue(when.strip(), f["command"])
            self.assertLessEqual(len(when.split()), 25, f["command"])
            self.assertEqual(when.count(". "), 0, f"{f['command']}: one sentence")
            self.assertFalse(when.endswith("."), f"{f['command']}: a table cell, no full stop")

    def test_the_when_agrees_with_the_command_and_the_lead_skill(self):
        self.assertIn("Any small change, of any type, on the minor route", flow("fix")["when"])
        self.assertNotIn("minor fix", flow("fix")["when"])
        # A change with no Spec that the quick path does not take runs the builder, the verifier, and the reviewer (ContradictionTests).
        self.assertIn("that the quick path does not take", flow("implement")["when"], "a small minor change is /fix")
        self.assertIn("Verify and Review", flow("implement")["when"])
        self.assertNotIn("one developer", flow("implement")["when"])
        # Refine is a mode of the plan: one trigger in the when and in the command.
        (refine,) = flow("plan")["modes"]
        self.assertIn("more than about 20 open items, and", refine["when"])
        self.assertIn("more than about 20 open items, and", command("plan"), "the when and the command give one trigger")
        self.assertNotIn("accepts or rejects", refine["when"], "the Stops when cell says that")

    def test_the_table_lists_every_command_in_team_md(self):
        table = generate.render("roles:flows:when")
        header, rule, *rows = table.splitlines()
        self.assertEqual([c.strip() for c in header.strip("|").split("|")], ["Command", "When", "Stops when"])
        flows = team_registry.roles()["graph"]["flows"]
        autopilot = team_registry.roles()["graph"]["autopilot"]  # the command after the flows: it runs theirs
        # Each flow, then each of its modes, then autopilot.
        entries = [(name, x) for f in flows for name, x in [(f["command"], f), *((f"{f['command']} {m['name']}", m) for m in f.get("modes", []))]]
        self.assertEqual(len(rows), len(entries) + 1)
        for (name, x), row in zip(entries, rows[:-1], strict=True):
            self.assertTrue(row.startswith(f"| `/aidd-team:{name}` | {x['when']} | "), row)
        self.assertTrue(rows[-1].startswith(f"| `/aidd-team:autopilot` | {autopilot['when']} | "), rows[-1])
        self.assertLessEqual(len(autopilot["when"].split()), 25)
        section = text(TEAM_MD).split("## Commands and flows", 1)[1].split("\n## ", 1)[0]
        self.assertIn("<!-- aidd:gen roles:flows:when -->\n" + table + "\n<!-- aidd:end -->", section)
        # Not preloaded: no agent file and no skill carries the table.
        for path in [SKILL, *sorted((TEAM / "agents").glob("*.md"))]:
            self.assertNotIn("roles:flows:when", text(path), path.name)


class MvpFlowTests(unittest.TestCase):
    """From a request to a launched MVP, skeleton first, with a person at every decision."""

    def test_the_flow(self):
        f = flow("mvp")
        self.assertEqual(
            f["runs"],
            [
                ["product-manager"],
                ["architect", "product-designer"],
                ["sre"],
                ["verifier", "reviewer"],  # the Day-0 baseline, before the person's yes to merge it
                ["developer"],
                ["verifier", "reviewer"],  # Verify and Review run side by side on one head
                ["security-engineer", "sre"],
            ],
        )
        self.assertEqual(f["routes"], ["minor", "normal", "major"])

    def test_the_command(self):
        t = command("mvp")
        for must in (
            "riskiest assumption",
            "non-goals",
            "vertical slices",
            "Day 0",
            "walking skeleton",
            'isolation: "worktree"',
            "two or three at a time",
            "the launch",
            "rollback",
            "/aidd-team:specify",
        ):
            self.assertIn(must, t, must)

    def test_the_routing_rules_are_untouched(self):
        """The mvp flow uses the risk rules as they are: no route, profile, or risk rule names it."""
        for name in ("risks.json", "profiles.json"):
            self.assertNotIn("mvp", text(ROOT / "schemas" / name), name)


class AutopilotWaitsTests(unittest.TestCase):
    """When only a person can go on and nothing changed, autopilot stops once, with no new handoff commit (BT1, F7)."""

    def test_a_wait_on_a_person_that_changed_nothing_writes_no_second_handoff_commit(self):
        end = command("autopilot").split("5. **End.**", 1)[1]
        rule = next((ln for ln in end.splitlines() if "same head" in ln), "")
        for must in ("person's", "same next step", "last handoff note", "without a new handoff commit", "once"):
            self.assertIn(must, rule, must)


class SpecifyTests(unittest.TestCase):
    """A small Spec takes fewer passes, and whoever writes the tests still never implements."""

    def test_the_small_spec_path(self):
        t = command("specify")
        for must in ("**Small Spec.**", "one Task", "in parallel", "second pass", "on every route", "never makes them pass"):
            self.assertIn(must, t, must)


class WorktreeTests(unittest.TestCase):
    """Parallel Tasks run in their own worktrees and the lead merges them back one at a time."""

    def test_implement_names_the_isolation_and_the_merge(self):
        t = command("implement")
        for must in ('isolation: "worktree"', "one at a time", "`aidd test --spec"):
            self.assertIn(must, t, must)


class ProductManagerSoloTests(unittest.TestCase):
    """Under solo, the founder is the domain expert, recorded as an assumption."""

    def test_solo_records_the_founder(self):
        playbook = body("product-manager").split("\n## Playbook\n", 1)[1].split("\n## ", 1)[0]
        for must in ("under the `solo` profile", "founder", "assumption", "ask the author who the expert is, and stop"):
            self.assertIn(must, playbook, must)


class PlanKeepsTheRequestTests(unittest.TestCase):
    """The plan keeps the decisions it records, and leaves every slice one line until its work starts."""

    def test_the_playbook_and_the_plan_flow_say_it_once_each(self):
        playbook = body("product-manager").split("\n## Playbook\n", 1)[1].split("\n## ", 1)[0]
        for name, text in (("the playbook", playbook), ("the plan flow", command("plan"))):
            for must in ("its own question", "soften"):
                self.assertEqual(text.count(must), 1, (name, must))
            self.assertIn("acceptance in its own file when its work starts", text, name)
            for gone in ("2 to 5 acceptance lines", "order of work", "first slice carries"):
                self.assertNotIn(gone, text.lower(), name)
            self.assertRegex(text, r"(?i)never re-asks? what (the request|it) settled")

    def test_a_proposed_cut_is_asked_apart(self):
        """A proposed cut is asked apart from the agreement, never stated as done."""
        playbook = body("product-manager").split("\n## Playbook\n", 1)[1].split("\n## ", 1)[0]
        for name, text in (("the playbook", playbook), ("the plan flow", command("plan"))):
            self.assertEqual(text.count("never stated"), 1, name)


class ReviewTriggerTests(unittest.TestCase):
    """The security reader runs for risky dependencies, not every lockfile bump."""

    def test_the_security_trigger(self):
        t = command("review")
        for must in ("install scripts", "native code", "auth, secrets, or AI"):
            self.assertIn(must, t, must)
        self.assertNotIn("auth, secrets, dependencies, or AI", t)


class TurnCapTests(unittest.TestCase):
    """Every agent file caps its turns (Claude Code's `maxTurns`, a positive integer), from the registry."""

    def test_max_turns(self):
        # The schema owns the bound, so the test reads it there.
        bound = resources.load_json("roles.schema.json")["$defs"]["max_turns"]  # a role's `max_turns` refers to it
        max_turns = bound["maximum"]
        for key, r in team_registry.roles()["roles"].items():
            self.assertIsInstance(r["max_turns"], int, key)
            self.assertTrue(10 <= r["max_turns"] <= max_turns, key)
            self.assertEqual(front(key)[0]["maxTurns"], str(r["max_turns"]), key)

    def test_a_cap_leaves_room_and_never_ends_a_run_silently(self):
        """A run that stopped at 50 turns returned nothing, so every role gets 100 or more, and the Stop rule hands back
        before the cap."""
        for key, r in team_registry.roles()["roles"].items():
            self.assertGreaterEqual(r["max_turns"], 100, key)
        # The developer reads the rule in the preloaded aidd skill, not in its file (CoreSkillCoverageTests proves it reaches the role).
        stop = next(x for x in team_registry.shared_rules_for("developer") if x.startswith("Stop, and hand back"))
        self.assertIn("few turns left", stop)


class ToolsetToolTests(unittest.TestCase):
    """A toolset grants the MCP tools of the extensions it names, so a role can use a server once a person enables it;
    an extension no toolset names grants nothing."""

    def test_the_browser_toolset_grants_playwright_to_the_roles_that_name_it(self):
        for key in ("product-designer", "verifier"):
            tools = front(key)[0]["tools"]
            self.assertIn("mcp__plugin_playwright_playwright__*", tools, key)
            self.assertIn("mcp__playwright__*", tools, key)
        self.assertNotIn("playwright", front("developer")[0]["tools"], "the developer lists Playwright MCP in no toolset")

    def test_an_extension_no_toolset_names_grants_nothing(self):
        from aidd.docsgen import pack_render

        role = {
            "toolsets": {"kit": {"uses": "a kit", "extensions": ["Named"]}},
            "extensions": [
                {"name": "Named", "type": "mcp", "tool_patterns": ["mcp__named__*"]},
                {"name": "Unnamed", "type": "mcp", "tool_patterns": ["mcp__unnamed__*"]},
            ],
        }
        self.assertEqual(pack_render.toolset_tools(role), ["mcp__named__*"])
        self.assertEqual(pack_render.toolset_tools({"extensions": role["extensions"]}), [], "no toolset, no MCP grant")

    def test_tool_patterns_are_tight_and_only_on_an_mcp_server(self):
        from aidd.kernel import json_schema

        schema = json_schema.bundled("roles.schema.json")
        item = schema["properties"]["roles"]["additionalProperties"]["properties"]["extensions"]["items"]
        pattern = item["properties"]["tool_patterns"]["items"]["pattern"]
        for good in ("mcp__playwright__*", "mcp__plugin_playwright_playwright__*"):
            self.assertRegex(good, pattern)
        for bad in ("mcp______*", "mcp__-__*", "mcp__a__b__*", "mcp__x__tool", "Bash"):
            self.assertNotRegex(bad, pattern)
        tool = {"name": "T", "type": "tool", "tool_patterns": ["mcp__t__*"]}
        rule = next(r for r in item["allOf"] if r.get("if", {}).get("required") == ["tool_patterns"])
        self.assertFalse(json_schema._ok(tool, rule, schema), "a tool that is no MCP server grants no MCP tools")
        self.assertTrue(json_schema._ok(dict(tool, type="mcp"), rule, schema))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ReviewerShellTests(unittest.TestCase):
    """The reviewer reads the diff and runs the tests itself; the hook still holds its shell writes."""

    def test_the_reviewer_has_a_shell_and_no_write_tool(self):
        tools = set(pack_render.split_tools(front("reviewer")[0]["tools"]))
        self.assertIn("Bash", tools)
        self.assertFalse(tools & {"Write", "Edit", "NotebookEdit"})
        self.assertIn("`git diff", body("reviewer"))

    def test_reports_name_the_model_actually_used(self):
        for path in (TEAM / "agents").glob("*.md"):
            self.assertNotIn("claude-code/claude-opus-5-5", text(path), path.name)
        for key in ("verifier", "reviewer"):
            self.assertIn("`<harness>/<model actually used>`", agent(key), key)


class PackDescriptionTests(unittest.TestCase):
    """Every session lists every skill's description, so a pack's says only when to load it."""

    def test_pack_descriptions_are_short(self):
        total = 0
        for d in team_registry.roles()["domains"]:
            head = text(TEAM.parent / "aidd-packs" / "skills" / d["slug"] / "SKILL.md").split("---")[1]
            description = json.loads(re.search(r"^description: (.+)$", head, re.M).group(1))
            self.assertNotIn("loaded on top of your aidd-team role", description, d["slug"])
            self.assertLessEqual(len(description), 200, d["slug"])
            self.assertTrue(description.startswith("In an aidd repository, "), d["slug"])
            self.assertNotIn("(.aidd/config.yaml)", description, d["slug"])
            total += len(description.encode())
        # The budget is per pack (it grows with the number of packs), so a new pack pays its own way.
        self.assertLess(total, 175 * len(team_registry.roles()["domains"]))

    def test_every_listed_description_is_short_and_scoped(self):
        """Every session lists the aidd skill, every team skill, and every command that the model may start."""
        aidd = json.loads(re.search(r"^description: (.+)$", text(ROOT / ".agents/skills/aidd/SKILL.md").split("---")[1], re.M).group(1))
        # It names the plain first requests (a fix, a feature), so a model that was never told "aidd" still matches.
        self.assertLessEqual(len(aidd), 250)
        self.assertTrue(aidd.startswith("Use before any change in a repository with .aidd/config.yaml"), aidd[:70])
        for plain in ("bug fix", "feature", "refactor", "commit"):
            self.assertIn(plain, aidd)
        for path in sorted((TEAM / "skills").glob("*/SKILL.md")):
            head = text(path).split("---")[1]
            description = json.loads(re.search(r"^description: (.+)$", head, re.M).group(1))
            # The aidd skill names the config file once; a team skill says only "aidd repository".
            self.assertIn("aidd repository", description, path.parent.name)
            self.assertNotIn("(.aidd/config.yaml)", description, path.parent.name)
            if path.parent.name != "aidd-team":  # the router also lists every role by name
                self.assertLessEqual(len(description), 200, path.parent.name)
            else:
                self.assertLessEqual(len(description), 460, path.parent.name)
        for path in sorted((TEAM / "commands").glob("*.md")):
            self.assertIn("\ndisable-model-invocation: true\n", text(path).split("---")[1] + "\n", path.name)


class StartupTeamTests(unittest.TestCase):
    """The default team for a startup, in one place."""

    def test_the_section(self):
        section = text(TEAM_MD).split("## Startup default team", 1)[1].split("\n## ", 1)[0]
        for must in ("`developer`", "`verifier`", "`reviewer`", "`aidd risk --paths`", "founder", "`solo`", "/aidd-team:fix", "/aidd-team:mvp"):
            self.assertIn(must, section, must)


class ChecksSizedToTheChangeTests(unittest.TestCase):
    """One rule of the loop contract sizes every role's checks to the change, and names what never scales down. It
    binds every role that has the harness's tools, the reviewer included, which reports a check the change dropped."""

    RULE = "Spend in proportion to risk"

    def test_every_role_with_tools_carries_the_one_rule(self):
        r = rule(self.RULE)
        roles = team_registry.roles()["roles"]
        for key in team_registry.roles()["order"]:
            with self.subTest(key):
                self.assertEqual(r in body(key), not roles[key].get("mcp_tools"), "every role but one with only aidd's tools")
        self.assertIn(r, body("reviewer"))

    def test_the_rule_keeps_each_check_on_and_names_what_never_scales_down(self):
        r = rule(self.RULE)
        for must in (
            "a required check stays on",
            # its five behaviors
            "cheapest check that could stop you",
            "what reads it, once",
            "only for something new",
            "already proven on this head",
            "only what only a person can judge",
            "two or three options",
            "a step that needs no judgment",
            # what never scales down
            "red before green",
            "the person's yes",
            "a reviewer who is not the author",
            "evidence bound to the head",
            # and who checks it
            "A reviewer reports",
        ):
            self.assertIn(must, r, must)
        # An independent check is never a repeat, so the verifier's own run stays.
        self.assertIn("a check by a role that did not write the work is no repeat", r)

    def test_the_rule_restates_no_hard_rule_it_points_to(self):
        r = rule(self.RULE).lower()
        hard = text(ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").split("## Hard rules", 1)[1].split("\n## ", 1)[0]
        items = dict(re.findall(r"^(\d+)\. (.+)$", hard, re.M))
        for number in ("6", "7", "8", "10"):
            for sentence in re.split(r"(?<=[.:])\s+", items[number]):
                words = sentence.strip().rstrip(".:").lower()
                if len(words.split()) >= 4:
                    with self.subTest(rule=number, sentence=words[:40]):
                        self.assertNotIn(words, r)
        self.assertIn("as the hard rules on evidence and on done say", r, "it points to them, by subject, never by a number")


class TestsOncePerBatchTests(unittest.TestCase):
    """A merge runs `aidd test --changed` once after a batch, and between its commits only on a conflict, and
    the fix path runs a narrowed check between attempts. What never scales down: each flow that ends in a merge ask keeps one
    full `aidd test` on the final head, with each new test red on base, and the lead's whole-suite run for each merged batch."""

    # Each flow that ends in a merge ask, and the command that holds its one full run on the final head.
    FULL_RUN_IN = {"fix": "fix", "review": "review", "autopilot": "review"}

    def test_a_merge_runs_the_changed_tests_once_per_batch_and_on_a_conflict(self):
        (lead,) = [x for x in team_registry.roles()["graph"]["lead"] if x.startswith("Bring a role's work over")]
        for must in ("once after the role's last commit", "between its commits only when one conflicts", "Run the whole suite once for each batch"):
            self.assertIn(must, lead, must)
        for name in ("implement", "autopilot"):
            with self.subTest(name):
                own = command(name).split("<!-- aidd:end -->", 1)[1]
                self.assertIn("`aidd test --changed` once after the last Task merges, and after a merge only when it conflicted", own)
                self.assertNotIn("after each merge", own)

    def test_the_fix_path_runs_a_narrowed_check_between_attempts(self):
        own = command("fix").split("<!-- aidd:end -->", 1)[1]
        self.assertIn("runs `aidd test --changed` or the one test file between attempts", own)
        self.assertNotIn("the repository's tests and `aidd test` until green", own, "the suite twice per attempt")

    def test_every_flow_that_ends_in_a_merge_ask_keeps_one_full_run_red_on_base_on_the_final_head(self):
        asks = {f["command"] for f in team_registry.roles()["graph"]["flows"] if f["stops_when"].startswith("Merge approval")}
        asks |= {p.stem for p in (TEAM / "commands").glob("*.md") if "<!-- aidd:gen roles:merge-approval -->" in text(p)}
        self.assertEqual(asks, set(self.FULL_RUN_IN), "a new flow that asks for the merge names where its full run is")
        full = {
            "fix": ("one full `aidd test` on the final head", "red on base"),
            "review": ("`aidd test --spec specs/<ID>.md` once on a clean tree", "the head's one full run", "red on base"),
        }
        for name, holder in self.FULL_RUN_IN.items():
            for must in full[holder]:
                with self.subTest(flow=name, must=must):
                    self.assertIn(must, command(holder).split("<!-- aidd:end -->", 1)[1])
        # Autopilot asks for the merge only on a clean report, which /aidd-team:review gives.
        (ask,) = [s for s in command("autopilot").split(". ") if "Merge approval ask (step 3)" in s and "comes only after" in s]
        for must in ("`/aidd-team:review`", "clean report on the head"):
            self.assertIn(must, ask, must)

    def test_the_config_reference_says_what_the_narrowed_form_never_narrows(self):
        ref = text(ROOT / ".agents" / "skills" / "aidd" / "references" / "config.md")
        self.assertIn("`related_tests`", ref)
        self.assertIn("a full run and `--require-green` always run the full command", ref)


class QuickPathTests(unittest.TestCase):
    """The quick path takes a small minor change of any change type, under the same limits, and each type names its
    proof. What must not be lost: the route and line stops, a test red on base for any change in behavior, the reviewer past the
    line threshold, and the person's Merge approval."""

    def test_every_change_type_names_its_proof(self):
        own = command("fix").split("<!-- aidd:end -->", 1)[1]
        proofs = own.split("1. proves the change by its type", 1)[1].split("\n   2. ", 1)[0]
        # Every change type the schema's vocabulary has, so a new type gets its proof before it takes the path.
        for token in resources.load_json("common.schema.json")["$defs"]["change_type"]["enum"]:
            with self.subTest(token):
                self.assertIn(f"`{token}`", proofs)
        for behavior in ("- a `fix`:", "- a `feat` or `perf`:"):
            line = next(ln for ln in proofs.splitlines() if ln.strip().startswith(behavior))
            self.assertIn("red on base", line, behavior)
        # A change that alters no behavior proves itself by the check that reads it, red on base where it finds the defect.
        no_behavior = next(ln for ln in proofs.splitlines() if "`docs`" in ln)
        for must in ("the check that reads the changed files", "red on base"):
            self.assertIn(must, no_behavior)
        # The type follows the diff, so a behavior change never escapes its red test by its label.
        self.assertIn("A diff that changes behavior is a `fix`, `feat`, or `perf`, whatever type it was given", own)

    def test_the_limits_and_the_approval_hold_for_every_type(self):
        own = command("fix").split("<!-- aidd:end -->", 1)[1]
        for must in ("is no longer minor", "more than 50 changed lines", "more than 20 changed lines", "in no area that raises the route", "Merge approval"):
            self.assertIn(must, own, must)
        self.assertNotIn("--change-type fix", own, "every type takes the path, so the route is checked with its own type")


class ReworkSizedByWhatChangedTests(unittest.TestCase):
    """A rework, a merge of the base after the yes, and a security challenge are sized by what changed, and
    each keeps its control: a new head gets a new Verify with one full run and a new ask, a reworked head's report says which
    Acceptance lines it judged unaffected, and no security finding is dropped, only left unchallenged when every one is Low."""

    def own_step(self, number: int) -> str:
        own = command("review").split("<!-- aidd:end -->", 1)[1]
        return re.split(r"\n(?=\d+\. )", own.split(f"\n{number}. ", 1)[1], maxsplit=1)[0]

    def test_a_base_merge_after_the_yes_gets_a_new_verify_and_a_new_ask_that_says_what_changed(self):
        loop = text(ROOT / ".agents" / "skills" / "aidd" / "references" / "graph.md")
        self.assertIn("A new head after the yes needs a new Verify and a new ask.", loop)
        self.assertIn("`git show --remerge-diff <merge>` prints nothing", loop)
        self.assertIn("runs the full `aidd test` once on the new head", loop)
        merge = self.own_step(8)
        for must in (
            "new Verify and a new Merge approval",
            "`git show --remerge-diff <merge>` prints nothing",
            "full `aidd test --spec` once on the new head",
            "The new ask says what changed since the yes",
            "A merge that resolved a conflict is a rework",
        ):
            self.assertIn(must, merge, must)

    def test_a_rework_runs_the_full_test_once_and_names_the_acceptance_lines_it_left(self):
        rework = self.own_step(7)
        for must in (
            "full `aidd test --spec` once on it, as on every head",
            "each Acceptance line the rework can affect",
            "names each line it judged unaffected, and why",
            "every line again in the reviewer's three cases",
        ):
            self.assertIn(must, rework, must)
        self.assertNotIn("the verifier runs in full, as on every head", rework)

    def test_the_security_challenge_follows_the_findings_and_never_drops_one(self):
        challenge = self.own_step(4).split("**Challenge", 1)[1]
        for must in ("Medium or above", "needs validation", "the change is major", "edit level is `ask`", "all Low or Nit"):
            self.assertIn(must, challenge, must)
        for must in ("stays in the main list, marked not challenged", "You never drop a finding", "The person who reviews security decides"):
            self.assertIn(must, challenge, must)


class MechanicalStepTests(unittest.TestCase):
    """The lead runs a step that needs no judgment as a command or on the execution tier, and no role's own tier
    changes. The word is not `mechanical`, which TierTests keeps for no tier and no lead rule."""

    def test_the_lead_places_a_step_that_needs_no_judgment_on_a_command_or_the_cheaper_tier(self):
        first = team_registry.roles()["graph"]["lead"][0]
        for must in (
            "A step that needs no judgment",
            "runs as its command in your session",
            "an execution-tier role",
            "Each role's judgment stays on its own tier",
        ):
            self.assertIn(must, first, must)
        # The judging roles stay where their tier_reason puts them.
        roles = team_registry.roles()["roles"]
        for key in ("architect", "reviewer", "security-engineer"):
            self.assertEqual(roles[key]["tier"], "reasoning", key)


class TeamDataTests(unittest.TestCase):
    """What each key of the team's data (`schemas/roles.json`) holds is read by a reader, so none claims what nothing does."""

    def test_each_flow_starts_on_agent_step_codes_and_each_agent_step_code_starts_one_flow(self):
        from aidd import workitems

        agent_codes = {code for code, who in workitems.STEP_CODES.items() if who == "agent"}
        starts = [(f["command"], code) for f in team_registry.roles()["graph"]["flows"] for code in f["starts_on"]]
        for command_name, code in starts:
            with self.subTest(flow=command_name, code=code):
                self.assertIn(code, agent_codes, "a step code of the common schema that an agent takes")
        codes = [code for _, code in starts]
        self.assertEqual(len(codes), len(set(codes)), "no code starts two flows")
        self.assertEqual(set(codes), agent_codes, "each agent step code starts a flow, and a person's step starts none")

    def test_the_autopilot_command_lists_each_step_code_that_starts_a_flow(self):
        listed = command("autopilot").split("<!-- aidd:gen roles:flows:starts -->\n", 1)[1].split("<!-- aidd:end -->", 1)[0]
        for f in team_registry.roles()["graph"]["flows"]:
            for code in f["starts_on"]:
                with self.subTest(code=code):
                    self.assertIn(f"| `{code}` | `/aidd-team:{f['command']}` |", listed)

    def test_an_artifact_says_who_it_comes_from_and_where_it_lives_once(self):
        for name, artifact in team_registry.roles()["graph"]["artifacts"].items():
            with self.subTest(artifact=name):
                self.assertIn(artifact["from"], ("human", "platform", "agent"))
                self.assertTrue(artifact["where"])
                self.assertEqual(set(artifact), {"name", "where", "from"})

    def test_the_documents_table_shows_the_roles_a_document_is_handed_to_and_the_command_that_opens_it(self):
        from aidd.docsgen import team_reference

        table = team_reference.documents_table()
        documents = team_registry.roles()["graph"]["documents"]
        rows = {line.split("|")[1].strip(" `"): [c.strip() for c in line.split("|")[2:-1]] for line in table.splitlines()[2:]}
        self.assertEqual(set(rows), set(documents))
        for name, d in documents.items():
            with self.subTest(document=name):
                self.assertEqual(rows[name][0], f"`{d['written_by']}`")
                self.assertEqual(rows[name][4], ", ".join(f"`{r}`" for r in d.get("read_by", [])))
                self.assertEqual(rows[name][5], f"`{d['opened_by']}`" if d.get("opened_by") else "")
        self.assertTrue(any(d.get("read_by") for d in documents.values()) and any(d.get("opened_by") for d in documents.values()))

    def test_a_role_that_writes_where_nothing_is_frozen_is_told_so_in_its_write_area(self):
        from aidd import knowledge

        found = []
        for key, role in team_registry.roles()["roles"].items():
            area = knowledge.role_area(role)
            with self.subTest(role=key):
                if role.get("writes_unfrozen"):
                    found.append(key)
                    self.assertIn(f"{knowledge.role_writes(role['writes_unfrozen'])} on a change with no Spec or on the emergency route", area)
                    self.assertIn(f"- **May write:** {area}", agent(key))
                else:
                    self.assertNotIn("where nothing is frozen", area)
        self.assertEqual(found, ["developer"])

    def test_an_extension_with_a_key_nothing_reads_fails_the_schema(self):
        import copy

        data = copy.deepcopy(resources.load_json("roles.json"))
        self.assertEqual(json_schema.validate(data, "roles.schema.json"), [])
        extension = next(x for r in data["roles"].values() for x in r.get("extensions", []))
        extension["suggest_when"] = {"stacks": ["Python"]}
        self.assertNotEqual(json_schema.validate(data, "roles.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
