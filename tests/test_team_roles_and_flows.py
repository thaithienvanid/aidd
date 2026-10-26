"""A lean aidd-team. Right-sized models per tier, a lead that routes and never authors, a loop contract rendered
once and per role, small agent files, and the quick `fix` and `mvp` flows."""

import io
import json
import re
import shutil
import tempfile
import tomllib
import unittest

import budgets
from pathlib import Path

import helpers
from helpers import ROOT, git

from aidd.guard import pre_tool
from aidd.docsgen import generate
from aidd.docsgen import pack_render
from aidd.setup import adoption
from aidd.setup import team_install
from aidd.knowledge import agent_models, team_registry
from aidd.kernel import json_schema

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
    return next(f for f in team_registry.roles()["loop"]["flows"] if f["command"] == name)


def rule(opening: str) -> str:
    found = [x for x in team_registry.roles()["loop"]["contract"] if x.startswith(opening)]
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
        # Two tiers (owner, 2026-10-02): Sonnet is the smallest model aidd runs an agent on in Claude Code.
        self.assertEqual(team_registry.MODELS_BY_HARNESS["claude-code"], {"reasoning": "opus", "execution": "sonnet"})
        for h, m in team_registry.MODELS_BY_HARNESS.items():
            self.assertEqual(set(m), {"reasoning", "execution"}, h)

    def test_each_role_sits_in_its_tier(self):
        roles = team_registry.roles()["roles"]
        tiers = {k: r["tier"] for k, r in roles.items()}
        self.assertEqual(
            {k for k, t in tiers.items() if t == "reasoning"},
            {"architect", "security-engineer", "reviewer", "compliance-analyst", "domain-expert", "product-manager", "product-designer"},
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
        """Two tiers only (owner, 2026-10-02): no role, harness map, tier meaning, or schema names `mechanical`."""
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
        self.assertFalse(any("mechanical" in x for x in team_registry.roles()["loop"]["lead"]))
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
        self.assertTrue(team_registry.roles()["loop"]["lead"])
        for path in sorted((TEAM / "commands").glob("*.md")):
            self.assertIn("<!-- aidd:gen roles:lead -->", text(path), path.name)

    def test_the_lead_rules_say_it(self):
        lead = generate.render("roles:lead")
        # Role placement (R147): the lead plays a role only for a small step of its own work, and never checks its own work;
        # every role it starts gets its context pack (R149).
        for must in (
            "place each role",
            "--play",
            "Never play a role that checks, tests, or reviews work you wrote",
            "Under autopilot, start every role",
            "else the files by path",
            "context pack",
            "in one message",
            "wait for all",
            "`model`",
            "fresh session",
            "`/clear`",
            "one Edit",
            "handoff note",
        ):
            self.assertIn(must, lead, must)
        for model in team_registry.MODELS_BY_HARNESS["claude-code"].values():
            self.assertIn(f"`{model}`", lead)
        # A command's roles are named only where it runs them, so the shared block names none.
        self.assertNotRegex(lead, r"`aidd-team:[a-z-]+`")
        # A section is changed with one Edit: one Write of a whole file to change a section risks the rest of it.
        self.assertNotIn("one Write, not many Edits", lead)
        self.assertNotIn("one Write, not many Edits", generate.render("roles:contract"))

    def test_the_handoff_note_carries_a_cost_line(self):
        self.assertIn("Spend", rule("End every run with the handoff note"))


class SharedRulesTests(unittest.TestCase):
    """Every agent file carries the aidd skill's hard rules in brief, scoped to the roles and steps they bind."""

    def test_every_role_carries_the_shared_rules(self):
        for key in team_registry.roles()["order"]:
            text = agent(key)
            self.assertIn("- **Hard rules (in brief):**", text, key)
            for rule in team_registry.shared_rules_for(key):
                self.assertIn(rule, text, key)
            self.assertIn("never approve", text.split("- **Loop steps:**", 1)[0], key)

    def test_every_role_that_commits_says_assisted_by(self):
        for key in writers():
            self.assertIn("`Assisted-by: <harness>/<model>`", "\n".join(team_registry.shared_rules_for(key)), key)
        for key in ("tech-writer", "sre"):
            self.assertIn("Assisted-by", agent(key), key)

    def test_each_rule_names_the_step_it_applies_to(self):
        roles = team_registry.roles()["roles"]
        scope = next(x for x in team_registry.roles()["loop"]["shared_rules"] if "`scope`" in x)
        self.assertIn("in Implement or on the fast lane", scope)
        verified = next(x for x in team_registry.roles()["loop"]["shared_rules"] if x.startswith("Done means verified"))
        retries = next(x for x in team_registry.roles()["loop"]["shared_rules"] if "retry_count" in x)
        for key, r in roles.items():
            self.assertEqual(verified in team_registry.shared_rules_for(key), "Implement" in r["steps"], key)  # never the verifier, which fixes nothing
            self.assertEqual(retries in team_registry.shared_rules_for(key), "Implement" in r["steps"], key)
            if verified in team_registry.shared_rules_for(key):
                self.assertIn("Bash", pack_render.split_tools(front(key)[0]["tools"]), key)  # a role told to run the tests has a shell
        skill = text(ROOT / ".agents" / "skills" / "aidd" / "SKILL.md")
        # The hard rules run most critical first (owner, 2026-10-03): the scope rule is 4, and done-means-verified is 9.
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
        self.assertTrue(hard_rules[1].startswith("Never approve") and "for a person" in hard_rules[1], hard_rules[1])
        self.assertIn("protected branch", hard_rules[1])  # the push rule is a sub-rule of rule 1
        self.assertIn("edit only", hard_rules[4])  # the scope rule
        self.assertTrue(hard_rules[9].startswith("Done means verified"), hard_rules[9])
        self.assertTrue(team_registry.roles()["loop"]["contract"][0].startswith("Never skip a step or a human decision"))
        self.assertTrue(team_registry.roles()["loop"]["shared_rules"][0].startswith("Humans decide"))

    def test_a_read_only_role_returns_its_note_for_the_lead_to_post(self):
        """The reviewer and the domain expert have no Write tool, so they cannot put the note in the Spec themselves."""
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
            for absent in ("`tests.commands`", "Use AI as a delivery team does", "a helper's 'done' is a claim", "Research first"):
                self.assertNotIn(absent, joined, (key, absent))

    def test_scoped_rules_bind_who_they_should(self):
        self.assertEqual(binds("Use AI as a delivery team does"), writers())
        self.assertIn("a helper's 'done' is a claim", rule("Use AI as a delivery team does"))
        self.assertEqual(binds("Research first"), {"architect", "security-engineer"})
        research = rule("Research first")
        for must in ("in Plan and Specify only", "no pack", "due for review"):
            self.assertIn(must, research)
        packs = [x for x in team_registry.roles()["loop"]["contract"] if "`tests.commands`" in x]
        self.assertEqual(len(packs), 1)
        self.assertEqual({k for k in team_registry.roles()["order"] if packs[0] in team_registry.contract_for(k)}, {"architect", "verifier"})

    def test_the_whole_contract_is_rendered_once(self):
        roles_ref = text(TEAM / "skills" / "aidd-team" / "references" / "roles.md")
        self.assertIn("<!-- aidd:gen roles:contract -->", roles_ref)
        for r in team_registry.roles()["loop"]["contract"]:
            self.assertEqual(roles_ref.count(r), 1, r[:40])

    def test_agent_files_are_about_one_screen(self):
        for key in team_registry.roles()["order"]:
            t = agent(key)
            self.assertTrue(budgets.within(len(t.encode()), 9 * 1024 + 256), (key, len(t.encode())))  # 9.25 KiB: see test_team.SlimAgentFileTests
            # The hand-written part (the playbook, the definition of done, and the stop rules) fits one screen.
            self.assertLess(len(t.split("<!-- aidd:end -->", 1)[1].encode()), 2560, key)
            self.assertNotIn("**Extend with", t, key)

    def test_the_aidd_skill_is_preloaded_only_where_specs_or_tests_are_written(self):
        for key, r in team_registry.roles()["roles"].items():
            writes_spec_or_tests = (bool({"{spec}", "{specs_dir}", "{tests}"} & set(r["writes"])) or "{tests}" in r.get("writes_unfrozen", [])) and r.get(
                "preload_core"
            ) is not False
            _, skills = front(key)
            self.assertEqual(skills[:1] == ["aidd:aidd"], writes_spec_or_tests, key)
            self.assertEqual([s for s in skills if s != "aidd:aidd"], [f"aidd-team:{x}" for x in r["preload"]], key)
        for key in ("developer", "architect", "product-manager"):
            self.assertEqual(front(key)[1][0], "aidd:aidd", key)
        # The verifier writes tests, but its Verify run needs no 13 KB rulebook, so it loads the skill by name in Specify.
        self.assertEqual(team_registry.roles()["roles"]["verifier"]["preload_core"], False)
        for key in ("verifier", "reviewer", "security-engineer", "sre", "compliance-analyst"):
            self.assertNotIn("aidd:aidd", front(key)[1], key)

    def test_the_fixed_text_per_subagent_shrank(self):
        """The agent body plus its preloaded skills: about 25.5 KB a role on average before the lean team, and 18.0 KB
        before the preloaded skills' dates and sources moved to the roles reference (about 16.2 KB after).
        The cap keeps about 10 percent headroom under the old 18 KB cap: a new feature pays for its own bytes."""

        def skill_bytes(name: str) -> int:
            plugin, _, skill = name.partition(":")
            base = ROOT / ".agents" / "skills" if plugin == "aidd" else TEAM / "skills"
            return len((base / skill / "SKILL.md").read_bytes())

        sizes = [len(body(k).encode()) + sum(skill_bytes(s) for s in front(k)[1]) for k in team_registry.roles()["order"]]
        # The mean stays within 16,700 plus the 3% headroom (17,201): the owner's cap since 1.0.0, from 16,500.
        self.assertTrue(budgets.within(sum(sizes) / len(sizes), 16700), (sum(sizes) / len(sizes), sizes))


class ContradictionTests(unittest.TestCase):
    """The developer's precondition names its lane, and the skill and the team page agree on the fast-lane team."""

    FAST_TEAM = "A small minor fix runs one developer, and the reviewer past 20 changed lines (`/aidd-team:fix`); every other fast-lane change runs the developer, the verifier, and the reviewer."

    def test_the_developer_precondition_names_the_lane(self):
        playbook = body("developer").split("\n## Playbook\n", 1)[1]
        first = next(ln for ln in playbook.splitlines() if ln.startswith("1. "))
        self.assertIn("Spec lane:", first)
        self.assertIn("Fast or emergency lane:", first)

    def test_one_fast_lane_team(self):
        self.assertIn(self.FAST_TEAM, text(SKILL))
        self.assertIn(self.FAST_TEAM, text(TEAM_MD))
        self.assertNotIn("runs one agent and no roles", text(TEAM_MD))


class FixFlowTests(unittest.TestCase):
    """The quick path for a small fix."""

    def test_the_flow(self):
        f = flow("fix")
        self.assertEqual((f["steps"], f["lanes"], f["runs"]), (["Implement", "Verify", "Review"], ["fast"], [["developer"], ["reviewer"]]))
        self.assertIn("Merge approval", f["stops_at"])

    def test_the_command(self):
        t = command("fix")
        for must in ("regression test", "red on base", "`aidd test`", "50 changed lines", "20 changed lines", "risk dimension", "/aidd-team:specify"):
            self.assertIn(must, t, must)

    def test_the_fix_declares_minor_so_a_person_approves_it(self):
        # A standard change needs no Merge approval, and a quick fix always ends at one: with no block the gate takes
        # minor from the diff, never standard, and the command never accepts a standard outcome.
        t = command("fix")
        self.assertIn("`route: minor`", t)
        self.assertNotIn("standard", t)
        block_step = next(ln for ln in t.splitlines() if "Change Request block" in ln and "`aidd describe`" in ln)
        self.assertIn("the gate takes `route: minor` from the diff, so it asks for one Merge approval.", block_step)
        self.assertIn("never declare a lower route.", block_step)

    def test_the_reviewer_report_is_cut_to_the_review_limits(self):
        # As /aidd-team:review step 5 does: the reviewer's findings are cut to REVIEW.md's nit limit before the author sees them.
        review_cut = "Cut it to the REVIEW.md limits: at most five nits by default, and the rest as a count."
        self.assertIn(review_cut, command("review"))
        reviewer_step = next(ln for ln in command("fix").splitlines() if "`aidd-team:reviewer`" in ln)
        self.assertIn("REVIEW.md limits: at most five nits by default, and the rest as a count", reviewer_step)


class InstallLineTests(unittest.TestCase):
    """Each page that names the aidd plugin's install also names the optional team's."""

    def test_the_team_plugin_is_named_next_to_the_aidd_plugin(self):
        for rel in ("README.md", "docs/INSTALL.md", "llms-install.md"):
            lines = [ln for ln in text(ROOT / rel).splitlines() if "`/plugin install aidd@aidd`" in ln]
            self.assertTrue(lines, rel)
            for ln in lines:
                self.assertIn("`/plugin install aidd-team@aidd`", ln, rel)


class FlowWhenTests(unittest.TestCase):
    """Each team command says when a person picks it, and TEAM.md lists them all in one table."""

    def test_every_flow_says_when(self):
        flows = team_registry.roles()["loop"]["flows"]
        required = json.loads(text(ROOT / "schemas" / "roles.schema.json"))["properties"]["loop"]["properties"]["flows"]["items"]["required"]
        self.assertIn("when", required)
        for f in flows:
            when = f.get("when", "")
            self.assertTrue(when.strip(), f["command"])
            self.assertLessEqual(len(when.split()), 25, f["command"])
            self.assertEqual(when.count(". "), 0, f"{f['command']}: one sentence")
            self.assertFalse(when.endswith("."), f"{f['command']}: a table cell, no full stop")

    def test_the_when_agrees_with_the_command_and_the_lead_skill(self):
        self.assertIn("small bug fix on the minor route", flow("fix")["when"])
        self.assertNotIn("minor fix", flow("fix")["when"])
        # A fast-lane change other than a quick fix runs the developer, the verifier, and the reviewer (ContradictionTests).
        self.assertIn("other than a bug fix", flow("implement")["when"], "a bug fix on the fast lane is /fix")
        self.assertIn("Verify and Review", flow("implement")["when"])
        self.assertNotIn("one developer", flow("implement")["when"])
        self.assertIn("more than about 20 open items, and", flow("refine")["when"])
        self.assertIn("more than about 20 open items, and", command("refine"), "the when and the command give one trigger")
        self.assertNotIn("accepts or rejects", flow("refine")["when"], "the Stops at cell says that")

    def test_the_table_lists_every_command_in_team_md(self):
        table = generate.render("roles:flows:when")
        header, rule, *rows = table.splitlines()
        self.assertEqual([c.strip() for c in header.strip("|").split("|")], ["Command", "When", "Stops at"])
        flows = team_registry.roles()["loop"]["flows"]
        autopilot = team_registry.roles()["loop"]["autopilot"]  # the command after the flows: it runs theirs
        self.assertEqual(len(rows), len(flows) + 1)
        for f, row in zip(flows, rows[:-1], strict=True):
            self.assertTrue(row.startswith(f"| `/aidd-team:{f['command']}` | {f['when']} | "), row)
        self.assertTrue(rows[-1].startswith(f"| `/aidd-team:autopilot` | {autopilot['when']} | "), rows[-1])
        self.assertLessEqual(len(autopilot["when"].split()), 25)
        section = text(TEAM_MD).split("## Commands and flows", 1)[1].split("\n## ", 1)[0]
        self.assertIn("<!-- aidd:gen roles:flows:when -->\n" + table + "\n<!-- aidd:end -->", section)
        # Not preloaded: no agent file and no skill carries the table.
        for path in [SKILL, *sorted((TEAM / "agents").glob("*.md"))]:
            self.assertNotIn("roles:flows:when", text(path), path.name)


class MvpFlowTests(unittest.TestCase):
    """From a brief to a launched MVP, skeleton first, with a person at every decision."""

    def test_the_flow(self):
        f = flow("mvp")
        self.assertEqual(
            f["runs"],
            [
                ["product-manager"],
                ["architect", "product-designer"],
                ["sre"],
                ["developer"],
                ["verifier", "reviewer"],  # Verify and Review run side by side on one head
                ["security-engineer", "sre"],
            ],
        )
        self.assertEqual(f["lanes"], ["fast", "spec"])

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
        """The mvp flow runs the gate as it is: no route, profile, or baseline rule names it."""
        for name in ("baseline.json", "profiles.json"):
            self.assertNotIn("mvp", text(ROOT / "schemas" / name), name)


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
        for key, r in team_registry.roles()["roles"].items():
            self.assertIsInstance(r["max_turns"], int, key)
            self.assertTrue(10 <= r["max_turns"] <= 200, key)
            self.assertEqual(front(key)[0]["maxTurns"], str(r["max_turns"]), key)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ReviewerShellTests(unittest.TestCase):
    """The reviewer reads the diff and runs the tests itself; the hook still holds its shell writes."""

    def test_the_reviewer_has_a_shell_and_no_write_tool(self):
        tools = set(pack_render.split_tools(front("reviewer")[0]["tools"]))
        self.assertIn("Bash", tools)
        self.assertFalse(tools & {"Write", "Edit", "NotebookEdit"})
        self.assertIn("`git diff", body("reviewer"))

    def test_the_hook_denies_a_reviewer_shell_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], enforce=True))
            for command_line, expected in (("git diff HEAD~1", "allow"), ("echo x > src/a.py", "deny"), ("sed -i s/a/b/ src/a.py", "deny")):
                out = io.StringIO()
                event = {"tool_name": "Bash", "cwd": str(root), "agent_type": "aidd-team:reviewer", "tool_input": {"command": command_line}}
                pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
                decision = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else "allow"
                self.assertEqual(decision, expected, command_line)

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
            head = text(TEAM / "skills" / d["slug"] / "SKILL.md").split("---")[1]
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
        self.assertLessEqual(len(aidd), 250)
        self.assertTrue(aidd.startswith("Use in a repository with .aidd/config.yaml"), aidd[:60])
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
        for must in ("`developer`", "`verifier`", "`reviewer`", "`aidd gate --paths`", "founder", "`solo`", "/aidd-team:fix", "/aidd-team:mvp"):
            self.assertIn(must, section, must)


if __name__ == "__main__":
    unittest.main()
