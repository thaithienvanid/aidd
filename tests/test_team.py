"""aidd-team: roles as data, the role-aware edit guard, the plugin wiring, and `aidd init --team`."""

import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import ROOT, RepoTemplateCase, git, make_repo, repo_files

from aidd import guard, repo, resources

TEAM = ROOT / "plugins" / "aidd-team"


@unittest.skipUnless(shutil.which("git"), "git is required")
class RoleGuardTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def decide(self, role, path):
        return guard.check_edit(str(self.root), path, role)[0]

    def test_each_role_writes_only_its_own_files(self):
        code, tests, spec = "src/checkout/rate_limit/limiter.py", "tests/checkout/test_rate_limit.py", "specs/SPEC-220.md"
        self.assertEqual([self.decide("developer", p) for p in (code, tests, spec)], ["allow", "deny", "deny"])
        # The tester writes the tests while specifying; no prompt stops it mid-build.
        self.assertEqual([self.decide("tester", p) for p in (code, tests, spec)], ["deny", "allow", "allow"])
        self.assertEqual([self.decide("architect", p) for p in (code, tests, spec)], ["deny", "deny", "allow"])
        self.assertEqual([self.decide("reviewer", p) for p in (code, tests, spec)], ["deny", "deny", "deny"])
        self.assertEqual(self.decide("product-manager", "specs/EPIC-1.md"), "allow")
        self.assertEqual(self.decide("product-manager", code), "deny")
        # A threat model or runbook file is a documentation Task: outside the scope it would fail the gate's scope rule.
        # Specialists return their Spec sections as text; the architect folds them in.
        self.assertEqual([self.decide("security-engineer", p) for p in (code, "docs/security/tm.md", spec)], ["deny", "deny", "deny"])
        self.assertEqual([self.decide(r, spec) for r in ("compliance-analyst", "sre")], ["deny", "deny"])
        self.assertEqual([self.decide("sre", p) for p in (code, "docs/runbooks/checkout.md")], ["deny", "deny"])
        # The tech-writer's edits ship in the change, so they must also sit inside the Spec's scope.
        self.assertEqual([self.decide("tech-writer", p) for p in ("docs/guide.md", code, spec)], ["deny", "deny", "deny"])

    def add_scope(self, *paths):
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                'scope = ["src/checkout/rate_limit/"]', f"scope = {['src/checkout/rate_limit/', *paths]!r}".replace("'", '"')
            ),
            encoding="utf-8",
        )

    def test_documentation_tasks_open_the_role_areas(self):
        self.add_scope("docs/**")
        self.assertEqual(
            [
                self.decide(r, p)
                for r, p in (
                    ("architect", "docs/adr/0001-limits.md"),
                    ("security-engineer", "docs/security/tm.md"),
                    ("sre", "docs/runbooks/checkout.md"),
                    ("tech-writer", "docs/guide.md"),
                )
            ],
            ["allow"] * 4,
        )
        self.assertEqual(self.decide("architect", "docs/guide.md"), "deny")

    def test_several_specs_on_a_branch_cover_each_other(self):
        other = (
            (self.root / "specs" / "SPEC-220.md")
            .read_text(encoding="utf-8")
            .replace("SPEC-220", "SPEC-221")
            .replace("src/checkout/rate_limit/", "src/billing/")
        )
        (self.root / "specs" / "SPEC-221.md").write_text(other, encoding="utf-8")
        self.assertEqual([self.decide("developer", p) for p in ("src/checkout/rate_limit/a.py", "src/billing/b.py", "src/c.py")], ["allow", "allow", "deny"])
        self.assertEqual([self.decide("architect", f"specs/SPEC-22{i}.md") for i in (0, 1)], ["allow", "allow"])

    def test_without_a_spec_only_planning_roles_write(self):
        (self.root / "specs" / "SPEC-220.md").unlink()
        # No Spec: the developer may be on the fast lane, which the gate checks; a Spec role has nothing to write yet.
        self.assertEqual(self.decide("developer", "src/a.py"), "allow")
        # A protected path waits for an approved scope, on any lane.
        self.assertEqual(self.decide("developer", ".github/workflows/ci.yml"), "deny")
        self.assertEqual(self.decide("tester", "tests/t.py"), "deny")
        self.assertEqual(self.decide("product-manager", "specs/SPEC-9.md"), "allow")
        self.assertEqual(self.decide(None, "src/a.py"), "allow")

    def test_each_task_goes_to_the_role_it_names(self):
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(p.read_text(encoding="utf-8").replace('assignee = "agent:claude-code"', 'assignee = "agent:ml-engineer"'), encoding="utf-8")
        code = "src/checkout/rate_limit/limiter.py"
        self.assertEqual([self.decide(r, code) for r in ("ml-engineer", "developer", "data-engineer")], ["allow", "deny", "deny"])

    def test_the_designer_writes_frozen_design_files(self):
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(p.read_text(encoding="utf-8").replace("[tests]", '[design]\nfiles = ["docs/design/SPEC-220/**"]\n\n[tests]', 1), encoding="utf-8")
        self.assertEqual(
            [self.decide("product-designer", x) for x in ("docs/design/SPEC-220/flow.md", "specs/SPEC-220.md", "src/a.py")], ["allow", "allow", "deny"]
        )
        self.assertEqual(self.decide("developer", "docs/design/SPEC-220/flow.md"), "deny")

    def set_status(self, status):
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(p.read_text(encoding="utf-8").replace('route = "normal"', f'route = "normal"\nstatus = "{status}"', 1), encoding="utf-8")

    def test_g1_freezes_the_tests_and_design_by_the_spec_status(self):
        """Allow or deny from local facts only: the Spec's status says whether Spec approval has happened."""
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(p.read_text(encoding="utf-8").replace("[tests]", '[design]\nfiles = ["docs/design/SPEC-220/**"]\n\n[tests]', 1), encoding="utf-8")
        tests, design = "tests/checkout/test_rate_limit.py", "docs/design/SPEC-220/flow.md"
        self.set_status("draft")
        self.assertEqual([self.decide(r, tests) for r in ("tester", None, "developer", "architect")], ["allow", "allow", "deny", "deny"])
        self.assertEqual([self.decide(r, design) for r in ("product-designer", None, "tester")], ["allow", "allow", "deny"])
        for status in sorted(guard.FROZEN_STATUSES):
            p.write_text(re.sub(r'status = "\w+"', f'status = "{status}"', p.read_text(encoding="utf-8"), count=1), encoding="utf-8")
            for role, path in (("tester", tests), (None, tests), ("product-designer", design), (None, design)):
                decision, reason = guard.check_edit(str(self.root), path, role)
                self.assertEqual(decision, "deny", (status, role, path))
                self.assertIn("ask for Spec approval again", reason)
        # Blocked or cancelled can come from either side of Spec approval: the owner still writes, nobody else.
        p.write_text(re.sub(r'status = "\w+"', 'status = "blocked"', p.read_text(encoding="utf-8"), count=1), encoding="utf-8")
        self.assertEqual([self.decide(r, tests) for r in ("tester", "developer")], ["allow", "deny"])

    def test_a_draft_spec_says_change_the_spec_not_approve_it_again(self):
        """Before Spec approval the Spec and its tests are open: the guard allows them with guidance, and a path the
        Spec misses means "add it to the Spec", never "get it approved again"."""
        spec, tests, new_test, other = "specs/SPEC-220.md", "tests/checkout/test_rate_limit.py", "tests/checkout/test_burst.py", "src/other/y.py"
        for status in ("draft", None):  # no status is a draft
            if status:
                self.set_status(status)
            for role in (None, "architect"):
                decision, reason = guard.check_edit(str(self.root), spec, role)
                self.assertEqual(decision, "allow", (status, role))
            decision, reason = guard.check_edit(str(self.root), spec)
            self.assertIn("before Spec approval", reason)
            self.assertIn("aidd validate", reason)
            for role in (None, "tester"):
                decision, reason = guard.check_edit(str(self.root), tests, role)
                self.assertEqual((decision, "before Spec approval" in reason), ("allow", True), (status, role, reason))
                decision, reason = guard.check_edit(str(self.root), new_test, role)
                self.assertEqual(decision, "deny", (status, role))
                self.assertIn("add it to tests.files in the Spec (it isn't approved yet)", reason)
                self.assertNotIn("approved again", reason)
                self.assertEqual(guard.reason_code(reason), "out_of_scope")
            decision, reason = guard.check_edit(str(self.root), other)
            self.assertEqual(decision, "deny")
            self.assertIn("add it to a Task's scope in the Spec (it isn't approved yet)", reason)
            self.assertNotIn("approved again", reason)
            p = self.root / "specs" / "SPEC-220.md"
            p.write_text(re.sub(r'\nstatus = "\w+"', "", p.read_text(encoding="utf-8"), count=1), encoding="utf-8")

    def test_an_approved_spec_says_get_it_approved_again(self):
        self.set_status("ready")
        decision, reason = guard.check_edit(str(self.root), "tests/checkout/test_burst.py")
        self.assertEqual(decision, "deny")
        self.assertIn("get it approved again", reason)
        self.assertNotIn("isn't approved yet", reason)
        self.assertEqual(guard.check_edit(str(self.root), "specs/SPEC-220.md"), ("allow", "the active Spec"))
        decision, reason = guard.check_edit(str(self.root), "tests/checkout/test_rate_limit.py", "tester")
        self.assertEqual(decision, "deny")
        self.assertIn("frozen by Spec approval", reason)

    def test_the_frozen_statuses_are_the_approved_ones(self):
        meanings = resources.load_json("common.schema.json")["$defs"]["status"]["x-meanings"]
        self.assertLessEqual(guard.FROZEN_STATUSES, set(meanings))
        self.assertNotIn("draft", guard.FROZEN_STATUSES)
        self.assertIn("Spec approval", meanings["ready"])

    def test_a_protected_path_is_allowed_only_inside_an_approved_scope(self):
        workflow, owners = ".github/workflows/deploy.yml", ".github/CODEOWNERS"
        self.assertEqual(self.decide("developer", workflow), "deny")  # outside its Tasks' scope, so outside its area
        decision, reason = guard.check_edit(str(self.root), workflow)
        self.assertEqual(decision, "deny")
        self.assertIn("protected path", reason)
        self.assertIn("major", reason)
        self.assertIn("scope in the Spec and get Spec approval", reason)
        self.add_scope(".github/workflows/**")
        for role in ("developer", "platform-engineer", None):
            decision, reason = guard.check_edit(str(self.root), workflow, role)
            self.assertEqual(decision, "allow", role)
            self.assertIn("major", reason)
        self.assertEqual([self.decide(r, owners) for r in ("developer", None)], ["deny", "deny"])
        (self.root / "specs" / "SPEC-220.md").unlink()
        self.assertEqual([self.decide(r, workflow) for r in ("developer", None)], ["deny", "deny"])
        self.assertEqual(self.decide(None, "src/a.py"), "allow")

    def test_the_guard_never_asks(self):
        """A prompt mid-build puts a person on the critical path of every parallel session.

        guard.Decision is Literal["allow", "deny"], so mypy holds every branch of check_edit to it; this pins what the
        hook prints for each: nothing on allow, a deny on deny, never an "ask"."""
        self.set_status("ready")
        for role, path, expected in (
            ("developer", "src/checkout/rate_limit/limiter.py", None),  # inside the scope
            ("developer", "tests/checkout/test_rate_limit.py", "deny"),  # another role's file
            ("tester", "tests/checkout/test_rate_limit.py", "deny"),  # frozen by Spec approval
            (None, ".github/workflows/ci.yml", "deny"),  # a protected path outside the scope
            ("reviewer", "specs/SPEC-220.md", "deny"),
        ):
            with self.subTest(role=role, path=path):
                event = {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / path), "content": "x"}}
                if role:
                    event["agent_type"] = f"aidd-team:{role}"
                out = io.StringIO()
                self.assertEqual(guard.pre_edit_hook(io.StringIO(json.dumps(event)), out), 0)
                printed = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else None
                self.assertEqual(printed, expected)

    def test_the_coach_proposes_but_never_adopts(self):
        # Improvement Specs and RFC drafts yes; the process files themselves only through a Spec and a human.
        self.assertEqual(self.decide("agile-coach", "specs/IMP-1.md"), "allow")
        self.assertEqual([self.decide("agile-coach", p) for p in (".aidd/config.toml", ".claude/agents/developer.md", "src/a.py")], ["deny", "deny", "deny"])
        (self.root / "specs" / "SPEC-220.md").unlink()
        self.assertEqual(self.decide("agile-coach", "docs/retros/2026-09-25.md"), "allow")

    def test_an_unknown_role_is_named(self):
        decision, reason = guard.check_edit(str(self.root), "src/a.py", "qa")
        self.assertEqual(decision, "deny")
        self.assertIn("security-engineer", reason)

    def test_the_hook_reads_the_subagent_type(self):
        out = io.StringIO()
        event = {
            "tool_name": "Edit",
            "cwd": str(self.root),
            "agent_type": "aidd-team:developer",
            "tool_input": {"file_path": str(self.root / "tests/checkout/test_rate_limit.py")},
        }
        guard.pre_edit_hook(io.StringIO(json.dumps(event)), out)
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(guard.role_of({"agent_type": "Explore"}))
        # Another plugin's agent, or a project's own agent, with a role's name is not an aidd-team role:
        # only the plugin's `aidd-team:<role>` and the `aidd-<role>` that `aidd init --team` installs are.
        self.assertEqual(
            [guard.role_of({"agent_type": a}) for a in ("aidd-team:architect", "aidd-architect", "architect", "ecc:architect", "sdd:developer", "aidd-qa")],
            ["architect", "architect", None, None, None, None],
        )

    def test_the_developer_writes_the_regression_test_on_an_emergency(self):
        """Nothing is frozen on the emergency lane and no tester runs there."""
        p = self.root / "specs" / "SPEC-220.md"
        tests = "tests/checkout/test_rate_limit.py"
        self.assertEqual(self.decide("developer", tests), "deny")
        p.write_text(p.read_text(encoding="utf-8").replace('route = "normal"', 'route = "emergency"', 1), encoding="utf-8")
        self.assertEqual(self.decide("developer", tests), "allow")
        p.write_text(p.read_text(encoding="utf-8").replace('route = "emergency"', 'route = "emergency"\nstatus = "in_progress"', 1), encoding="utf-8")
        self.assertEqual(self.decide("developer", tests), "allow")  # a backfill: nothing is frozen, whatever the status
        (self.root / "specs" / "SPEC-220.md").unlink()
        self.assertEqual(self.decide("developer", tests), "allow")  # fast lane: no Spec, the Change Request's scope decides

    def test_the_tech_writer_writes_documentation_only(self):
        """A write area of `**/*.md` would let the tech writer rewrite AGENTS.md or a Spec."""
        self.add_scope("docs/**", "AGENTS.md", "src/**")
        self.assertEqual([self.decide("tech-writer", p) for p in ("docs/guide.md", "AGENTS.md", "src/checkout/README.md")], ["allow", "deny", "deny"])

    def test_deny_messages_name_areas_in_words(self):
        reason = guard.check_edit(str(self.root), "docs/x.md", "developer")[1]
        self.assertNotIn("{", reason)


class PluginTests(unittest.TestCase):
    def test_agents_match_the_roles(self):
        roles = resources.roles()
        for key in roles["order"]:
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            front = dict(re.findall(r"^(\w+): (.+)$", text.split("---")[1], re.M))
            self.assertEqual((front["name"], front["model"]), (key, resources.tier_model(roles["roles"][key]["tier"])), key)
            self.assertIn(f"<!-- aidd:gen role:{key} -->", text)
        self.assertNotIn("Write", (TEAM / "agents" / "reviewer.md").read_text(encoding="utf-8").split("---")[1])

    def test_the_router_skill_stays_small_and_links_its_references(self):
        """The aidd-team SKILL.md loads on every trigger, so it stays short; the tables live in references/."""
        skill_dir = TEAM / "skills" / "aidd-team"
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 150)
        self.assertLess(len(text.encode()), 8192, "the router skill loads on every trigger; move tables to references/")
        # Only the loop diagram is generated into the router itself; the role, flow, and handoff tables are references.
        self.assertEqual(re.findall(r"<!-- aidd:gen (\S+) -->", text), ["roles:loop:diagram"])
        links = re.findall(r"\]\((references/[^)]+)\)", text)
        for link in links:
            self.assertTrue((skill_dir / link).is_file(), link)
        refs = {"roles.md", "flows.md", "domain-packs.md", "practice-skills.md", "extensions.md"}
        self.assertEqual({p.name for p in (skill_dir / "references").glob("*.md")}, refs)
        self.assertEqual({link.removeprefix("references/") for link in links}, refs, "every reference is linked from the router")
        self.assertIn("<!-- aidd:gen roles -->", (skill_dir / "references" / "roles.md").read_text(encoding="utf-8"))
        flows = (skill_dir / "references" / "flows.md").read_text(encoding="utf-8")
        for block in ("roles:flows", "roles:flows:diagram", "roles:handoffs", "roles:handoffs:diagram"):
            self.assertIn(f"<!-- aidd:gen {block} -->", flows)

    def test_every_role_has_a_seeded_defect_eval(self):
        """Every role has an eval scenario, so every tier choice has a check."""
        from aidd import evals

        scenarios = evals.load_scenarios(ROOT / "evals" / "roles")
        self.assertEqual({s["role"] for s in scenarios}, set(resources.roles()["order"]))
        for s in scenarios:
            self.assertTrue(s["fixture"].strip() and s["expected"].get("require_any"), s["id"])
            self.assertLessEqual({"Needs", "Stopped at"}, set(s["expected"]["require"]), s["id"])

    def test_agent_models_are_values_claude_code_accepts(self):
        """Every agent file names a model Claude Code accepts: an alias, `inherit`, or a full model ID."""
        for path in sorted((TEAM / "agents").glob("*.md")):
            front = dict(re.findall(r"^(\w+): (.+)$", path.read_text(encoding="utf-8").split("---")[1], re.M))
            self.assertTrue(helpers.is_claude_code_model(front["model"]), f"{path.name}: model {front['model']!r}")
        for tier in helpers.TIER_MEANING:
            self.assertTrue(helpers.is_claude_code_model(resources.tier_model(tier)), tier)
        for bad in ("opus-5.5", "sonnet-5", "gpt-6-sol", "", "claude"):
            self.assertFalse(helpers.is_claude_code_model(bad), bad)
        for good in ("opus", "sonnet", "haiku", "fable", "inherit", "claude-opus-5-5", "claude-sonnet-4-5-20250929"):
            self.assertTrue(helpers.is_claude_code_model(good), good)

    def test_every_role_follows_the_loop(self):
        data = resources.roles()
        loop = data["loop"]
        covered = set()
        for key in data["order"]:
            r = data["roles"][key]
            self.assertTrue(r["steps"] and set(r["steps"]) <= set(loop["steps"]), key)
            self.assertTrue(r["lanes"] and set(r["lanes"]) <= set(loop["lanes"]), key)
            self.assertTrue(r["starts_when"] and r["done_when"], key)
            covered |= set(r["steps"])
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            binding = resources.contract_for(key)
            for item in binding:
                self.assertIn(item, text, key)
            # An agent file carries only the rules that bind its role.
            for item in set(loop["contract"]) - set(binding):
                self.assertNotIn(item, text, key)
        # Ship's merge is a human's; every other step has a role.
        self.assertEqual(set(loop["steps"]) - covered, set())
        for cmd in (TEAM / "commands").glob("*.md"):
            step = re.search(r"Loop steps?: (.+)", cmd.read_text(encoding="utf-8"))
            self.assertTrue(step and any(f"**{s}**" in step.group(1) for s in loop["steps"]), cmd.name)

    def test_domain_packs_are_generated_skills(self):
        from aidd import docs

        data = resources.roles()
        for d in data["domains"]:
            path = docs.pack_path(ROOT, d)
            self.assertTrue(path.is_file(), d["slug"])
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text, docs.render_pack(d), d["slug"])
            self.assertIn(f"name: {d['slug']}\n", text)
            for section in ("## Standards", "## Checklist by loop step", "## Test commands", "## Keep it current"):
                self.assertIn(section, text, (d["slug"], section))
            self.assertTrue({c["step"] for c in d["checklist"]} >= {"Specify", "Implement"}, d["slug"])
        self.assertTrue(any("Research first" in x for x in data["loop"]["contract"]))

    def test_commands_follow_their_flows(self):
        import re as _re

        data = resources.roles()
        flows = {f["command"]: f for f in data["loop"]["flows"]}
        self.assertEqual(sorted(flows), sorted(p.stem for p in (TEAM / "commands").glob("*.md")))
        for name, f in flows.items():
            text = (TEAM / "commands" / f"{name}.md").read_text(encoding="utf-8")
            named = set(_re.findall(r"`aidd-team:([a-z-]+)`", text))
            expected = {r for g in f["runs"] for r in g}
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
            self.assertEqual(role["practices"], sorted(role["practices"]), key)

    def test_extensions_are_in_one_explainable_order(self):
        """Established before emerging (proven methods first), then by kind in the order a role reaches for one (its
        harness, a command-line tool that produces evidence, an MCP server for data, a plugin, a skill), then by name."""
        kinds = ["harness", "tool", "mcp", "plugin", "skill"]
        for key, role in resources.roles()["roles"].items():
            ext = role.get("extends", [])
            order = [(e.get("maturity", "established") != "established", kinds.index(e["kind"]), e["name"].lower()) for e in ext]
            self.assertEqual(order, sorted(order), key)

    def test_extensions_are_dated_and_sourced(self):
        data = resources.roles()
        kinds = {"skill", "plugin", "mcp", "tool", "harness"}
        for key in data["order"]:
            for x in data["roles"][key]["extends"]:
                self.assertIn(x["kind"], kinds, key)
                self.assertTrue(x["source"].startswith("https://"), key)
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn("**Extend with", text, key)

    def test_flow_lanes_agree_with_role_lanes(self):
        """A command and its flow name the same lanes.

        Every lane a flow runs on has a role for it, every role in a flow works on one of its lanes, the command
        states the flow's lanes, and a command whose roles do not all work on every lane says it filters them.
        """
        data = resources.roles()
        for f in data["loop"]["flows"]:
            roles = [r for g in f["runs"] for r in g]
            for lane in f["lanes"]:
                self.assertTrue(any(lane in data["roles"][r]["lanes"] for r in roles), (f["command"], lane))
            for r in roles:
                self.assertTrue(set(data["roles"][r]["lanes"]) & set(f["lanes"]), (f["command"], r))
            text = (TEAM / "commands" / f"{f['command']}.md").read_text(encoding="utf-8")
            m = re.search(r"^Lanes: ([a-z, ]+)\.", text, re.M)
            self.assertIsNotNone(m, f["command"])
            self.assertEqual([x.strip() for x in m.group(1).split(",")], f["lanes"], f["command"])
            if any(not set(f["lanes"]) <= set(data["roles"][r]["lanes"]) for r in roles):
                self.assertIn("run only the roles whose lanes include it", text, f["command"])
            for lane in ("fast", "spec", "emergency"):
                if lane not in f["lanes"]:
                    self.assertNotRegex(text.split("\n## ")[0], rf"on (?:the|every) [a-z ,]*\b{lane}\b[a-z ,]* lanes?", (f["command"], lane))

    def test_flows_run_roles_in_their_own_steps(self):
        data = resources.roles()
        for f in data["loop"]["flows"]:
            for role in (r for g in f["runs"] for r in g):
                self.assertTrue(set(f["steps"]) & set(data["roles"][role]["steps"]), (f["command"], role))

    def test_handoffs_link_every_role(self):
        data = resources.roles()
        senders: set[str] = set()
        for h in data["loop"]["handoffs"]:
            self.assertTrue(set(h["from"]) <= set(data["roles"]), h["from"])
            for party in h["to"]:
                self.assertTrue(party in data["roles"] or party.startswith("the author"), party)
            senders |= set(h["from"])
        self.assertEqual(senders, set(data["roles"]))
        self.assertTrue(any("handoff note" in x for x in data["loop"]["contract"]))
        handoffs = (TEAM / "skills" / "aidd-team" / "references" / "flows.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen roles:handoffs -->", handoffs)
        self.assertIn("references/flows.md", (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8"))

    def test_roles_validate_against_their_schema(self):
        from aidd import schema

        data = resources.load_json("roles.json")  # the file itself; resources.roles() is the resolved view
        self.assertEqual(schema.validate(data, "roles.schema.json"), [])
        self.assertEqual(set(data["order"]), set(data["roles"]))
        self.assertEqual(len(data["order"]), len(set(data["order"])))
        # A data file names the schema it validates against, not the metaschema.
        self.assertEqual(data.get("$schema"), "./roles.schema.json")
        self.assertTrue((ROOT / "schemas" / data["$schema"]).is_file())
        for h in data["loop"]["handoffs"]:
            for sender in h["from"]:
                self.assertIn(sender, data["roles"])
        for f in data["loop"]["flows"]:
            for group in f["runs"]:
                for role in group:
                    self.assertIn(role, data["roles"])
        skills_dir = TEAM / "skills"
        for d in data["domains"]:
            self.assertTrue((skills_dir / d["slug"]).is_dir(), f"missing skill dir for domain {d['slug']}")
        for r, rdata in data["roles"].items():
            for p in rdata.get("practices", []):
                self.assertTrue((skills_dir / p).is_dir(), f"missing skill dir for practice {p} in role {r}")
        loop_steps = set(data["loop"]["steps"])
        for r, rdata in data["roles"].items():
            self.assertTrue(set(rdata["steps"]) <= loop_steps, f"role {r} steps outside loop.steps")
        broken = json.loads(json.dumps(data))
        broken["roles"]["developer"]["steps"] = ["Deploy"]
        self.assertTrue(schema.validate(broken, "roles.schema.json"))

    def test_domains_cover_the_ai_era(self):
        domains = {d["name"]: d for d in resources.roles()["domains"]}
        self.assertGreaterEqual(len(domains), 10)
        self.assertTrue(any("Agentic" in s["name"] for s in domains["AI agents and tools"]["standards"]))
        skill = (TEAM / "skills" / "aidd-team" / "references" / "domain-packs.md").read_text(encoding="utf-8")
        for name in domains:
            self.assertIn(f"| {name} |", skill)

    def test_standards_registry_is_current(self):
        import datetime as dt

        from aidd import evals

        # The clock is pinned to the newest `checked` date, so this test never turns red because time passed: real
        # currency is a calendar check, which `aidd eval standards` runs on the evals workflow's schedule.
        entries = evals.standards()
        self.assertGreater(len(entries), 100)
        checked = [dt.date.fromisoformat(evals.dated(s)) for s in entries]
        newest = max(checked)
        # Nothing is checked in the future. Against the wall clock, this can only go from red to green as time passes.
        self.assertLessEqual(newest, dt.date.today())
        # Every entry was checked within a year of the newest one, and a year and a month later every one is stale.
        self.assertEqual(evals.stale_standards(newest), [])
        later = evals.stale_standards(newest + dt.timedelta(days=400))
        self.assertEqual(len(later), len(entries))
        self.assertEqual(sorted(s["age_days"] for s in later), sorted((newest + dt.timedelta(days=400) - d).days for d in checked))
        self.assertGreater(later[0]["age_days"], 365)

    def test_every_role_names_its_standards_and_done(self):
        for key in resources.roles()["order"]:
            self.assertGreaterEqual(len(resources.roles()["roles"][key]["standards"]), 5, key)
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            for section in ("## Playbook", "## Definition of Done", "## Stop and hand back"):
                self.assertIn(section, text, (key, section))

    def test_practice_skills_are_dated_playbooks(self):
        import datetime as dt

        from aidd import docs

        data = resources.roles()
        listed = {x for k in data["order"] for x in data["roles"][k]["practices"]}
        packs = {d["slug"] for d in data["domains"]}
        on_disk = {p.parent.name for p in (TEAM / "skills").glob("*/SKILL.md")} - packs - {"aidd-team"}
        # Every practice skill on disk has a role that loads it, and every listed practice exists.
        self.assertEqual(on_disk, listed)
        self.assertGreaterEqual(len(listed), 10)
        self.assertEqual(set(docs.practice_names()), listed)
        for name in sorted(listed):
            text = (TEAM / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            front = docs.practice_front(name)
            self.assertEqual(front["name"], name)
            self.assertTrue(front["description"].startswith("Practice skill: "), name)
            self.assertIn(". Use ", front["description"], name)
            self.assertLessEqual(dt.date.fromisoformat(front["checked"]), dt.date.today(), name)
            for section in ("## Standards", "## Hand off"):
                self.assertIn(section, text, (name, section))
            self.assertNotIn("<!-- aidd:gen", text, name)
        for role in ("developer", "tester", "reviewer", "security-engineer", "architect"):
            self.assertTrue(data["roles"][role]["practices"], role)

    def test_practices_reach_the_agents_and_the_currency_check(self):
        from aidd import docs, evals

        data = resources.roles()
        for key in data["order"]:
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn("**Practice skills", text, key)
            for name in data["roles"][key]["practices"]:
                self.assertIn(f"`aidd-team:{name}`", text, (key, name))
        table = docs.render("roles:practices")
        for name in docs.practice_names():
            self.assertIn(f"| `aidd-team:{name}` |", table)
        for path in (TEAM / "skills" / "aidd-team" / "references" / "practice-skills.md", ROOT / "docs" / "TEAM-REFERENCE.md"):
            self.assertIn("<!-- aidd:gen roles:practices -->", path.read_text(encoding="utf-8"), path.name)
        where = {s["where"] for s in evals.standards()}
        self.assertTrue({f"practice {x}" for x in docs.practice_names()} <= where)
        self.assertTrue(any("practice skill" in x for x in data["loop"]["contract"]))

    def test_tiers_are_priced_to_value(self):
        """The tier is harness-neutral; only the Claude Code plugin's frontmatter carries a vendor SKU."""
        data = resources.roles()
        # The tier follows the cost of a mistake: only the builders whose errors the tests catch, and whose
        # change is reversible, run in the execution tier.
        # `execution` (inherit the session's model) is the default; `reasoning` is kept only for the roles
        # whose judgment no test or later human check catches, each with its reason.
        reasoning = {k for k in data["order"] if data["roles"][k]["tier"] == "reasoning"}
        self.assertEqual(reasoning, {"architect", "security-engineer", "reviewer"})
        self.assertGreater(len(data["order"]) - len(reasoning), len(reasoning))
        for k in data["order"]:
            tier = data["roles"][k]["tier"]
            self.assertTrue(data["roles"][k]["tier_reason"].endswith("."), k)
            text = (TEAM / "agents" / f"{k}.md").read_text(encoding="utf-8")
            self.assertIn(f"- **Model tier:** `{tier}`", text, k)
            # the plugin frontmatter is the one place a vendor model name appears, and it is derived
            self.assertIn(f"model: {resources.tier_model(tier)}", text.split("---")[1], k)
        # Every mapped harness answers both tiers, and the plugin's harness is one of them.
        self.assertIn(resources.PLUGIN_HARNESS, resources.MODELS_BY_HARNESS)
        for h, m in resources.MODELS_BY_HARNESS.items():
            self.assertEqual(set(m), set(helpers.TIER_MEANING), h)
            self.assertTrue(all(isinstance(v, str) and v for v in m.values()), h)
        # A harness the registry has no mapping for gets no model: it reads the tier and picks its own.
        self.assertIsNone(resources.tier_model("reasoning", "cursor"))
        self.assertIsNone(resources.tier_model("execution", "no-such-harness"))
        self.assertIn("<!-- aidd:gen roles:models -->", (ROOT / "docs" / "TEAM-REFERENCE.md").read_text(encoding="utf-8"))
        self.assertTrue(any(x.startswith("Spend in proportion to risk") for x in data["loop"]["contract"]))

    def test_emerging_entries_are_marked_and_the_rule_is_in_the_contract(self):
        from aidd import docs, evals

        data = resources.roles()
        self.assertTrue(any(x.startswith("Proven methods first") for x in data["loop"]["contract"]))
        entries = evals.standards()
        emerging = [s for s in entries if s.get("maturity") == "emerging"]
        self.assertTrue(emerging)
        self.assertLess(len(emerging), len(entries) // 4, "most of the registry must be established")
        for s in emerging:
            self.assertIn("emerging", docs.standard_text(s), s["name"])
        for key in data["order"]:
            for s in data["roles"][key]["standards"] + data["roles"][key]["extends"]:
                self.assertIn(s.get("maturity", "established"), {"established", "emerging"}, s["name"])
                self.assertNotIn("Karpathy", s.get("edition", ""), s["name"])
        packs = [docs.render_pack(x) for x in data["domains"]]
        self.assertTrue(any("(emerging)" in t for t in packs))
        self.assertIn("emerging", docs.render("roles:extends"))

    def test_diagrams_are_generated_from_the_registry(self):
        from aidd import docs

        data = resources.roles()
        loop = docs.render("roles:loop:diagram")
        self.assertTrue(loop.startswith("```mermaid\nflowchart"))
        for key in data["order"]:
            self.assertIn(key, loop, key)
        self.assertIn("Spec approval", loop)
        self.assertIn("Merge approval", loop)
        flows = docs.render("roles:flows:diagram")
        for f in data["loop"]["flows"]:
            self.assertIn(f"/aidd-team:{f['command']}", flows)
            self.assertIn(docs._label(f["stops_at"], 26), flows)
        handoffs = docs.render("roles:handoffs:diagram")
        for h in data["loop"]["handoffs"]:
            self.assertIn(docs._label(h["through"], 26), handoffs)
        for text in (loop, flows, handoffs):
            self.assertNotIn('"`', text, "a quoted Mermaid label must not start with a backtick")
        for path in (ROOT / "README.md", ROOT / "docs" / "TEAM.md", TEAM / "skills" / "aidd-team" / "SKILL.md"):
            self.assertIn("<!-- aidd:gen roles:loop:diagram -->", path.read_text(encoding="utf-8"), path.name)
        self.assertTrue(any(x.startswith("Explain visually") for x in data["loop"]["contract"]))

    def test_marketplace_lists_both_plugins(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual([p["name"] for p in market["plugins"]], ["aidd", "aidd-team"])
        # Without the aidd plugin there is no hook, so the team declares it.
        self.assertEqual(market["plugins"][1]["dependencies"], ["aidd"])
        self.assertEqual(json.loads((TEAM / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["dependencies"], ["aidd"])
        for cmd in ("plan", "specify", "implement", "verify", "review", "secure", "sweep", "ship", "postmortem", "retro"):
            self.assertTrue((TEAM / "commands" / f"{cmd}.md").is_file(), cmd)

    def test_manifests_state_no_stale_count_and_name_every_command(self):
        """The manifests said nine commands and sixteen practice skills after propose, onboard, estimation, and proposal landed.

        JSON cannot carry a generated block, so a manifest either states no count or states the registry's.
        """
        from aidd import docs

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
                self.assertEqual(value, docs.count(counts[noun.lower()]), f"a manifest says {number} {noun}")
        for f in resources.roles()["loop"]["flows"]:
            self.assertRegex(team["description"], rf"\b{f['command']}\b", f"plugin.json does not name the {f['command']} command")

    def test_agents_can_call_the_aidd_mcp_tools(self):
        """Every role's prompt says to use the aidd MCP tools, and a `tools:` allowlist hides any tool it does not name.

        The reviewer has no shell, so the MCP `gate` tool is its only view of the gate.
        """
        from aidd import docs, mcp

        names = {t["name"] for t in mcp.TOOLS}
        self.assertEqual(names, {"next", "check_edit", "validate", "hash", "change", "gate"})
        for key in resources.roles()["order"]:
            front = dict(re.findall(r"^(\w+): (.+)$", (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8").split("---")[1], re.M))
            tools = set(docs.split_tools(front["tools"]))

            def granted(tool: str, tools: set[str] = tools) -> bool:
                # By its name, or by its server's `mcp__<server>__*` entry, which grants every tool of that server.
                return tool in tools or tool.rsplit("__", 1)[0] + "__*" in tools

            for prefix in ("mcp__plugin_aidd_aidd__", "mcp__aidd__"):  # the plugin's server, and the one `aidd init` wires
                self.assertTrue(all(granted(prefix + n) for n in names), key)
            self.assertTrue(all(granted(t) for t in docs.role_mcp_tools()), key)

    def test_the_loop_contract_needs_no_third_party_service(self):
        """Not every project has a forge, a tracker, a design tool, or an observability service; git and files suffice."""
        contract = resources.roles()["loop"]["contract"]
        rule = next((x for x in contract if x.startswith("Work with what the project has.")), None)
        self.assertIsNotNone(rule, "the loop contract has no work-with-what-the-project-has rule")
        self.assertIn("never ask the team to adopt one", rule)
        self.assertIn("in the repository instead", rule)

    def test_every_platform_command_in_a_command_file_has_a_local_alternative(self):
        """A step that runs `gh` or `glab` also says what to do without a platform, in the same step (one line)."""
        for path in sorted((TEAM / "commands").glob("*.md")):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"`(?:gh|glab) ", line):
                    self.assertTrue("without a platform" in line or "`git " in line, f"{path.name}:{i} names gh or glab with no local path")

    def test_init_team_installs_agents_and_agents_md(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, team=True, harnesses=[], approvers=["@me"])
            # Installed names carry the `aidd-` prefix, so `code-review` or `developer` never collides with a
            # built-in or the project's own agent, and the guard knows them as roles.
            tester = (root / ".claude/agents/aidd-tester.md").read_text(encoding="utf-8")
            self.assertIn("\nname: aidd-tester\n", tester)
            self.assertEqual(guard.role_of({"agent_type": "aidd-tester"}), "tester")
            self.assertFalse((root / ".claude/agents/tester.md").exists())
            self.assertTrue((root / ".claude/skills/aidd-web-front-end/SKILL.md").is_file())
            api = (root / ".claude/skills/aidd-api-design/SKILL.md").read_text(encoding="utf-8")
            self.assertIn("\nname: aidd-api-design\n", api)
            self.assertNotIn("aidd-team:", api)
            implement = (root / ".claude/commands/aidd-implement.md").read_text(encoding="utf-8")
            self.assertNotIn("aidd-team:", implement)
            self.assertIn("`aidd-developer`", implement)
            for path in (root / ".claude/agents").glob("*.md"):
                front = dict(re.findall(r"^(\w+): (.+)$", path.read_text(encoding="utf-8").split("---")[1], re.M))
                self.assertTrue(front["name"].startswith("aidd-"), path.name)
                self.assertTrue(helpers.is_claude_code_model(front["model"]), path.name)
            text = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("| `aidd-tester` |", text)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, team=True, harnesses=[], approvers=["@me"])
            self.assertEqual((root / "AGENTS.md").read_text(encoding="utf-8").count(repo.TEAM_MARK), 1)

    def test_other_harnesses_get_a_short_pointer_and_native_agent_files(self):
        """AGENTS.md loads every session on most harnesses, so its team section is a short pointer, not the team."""
        import tomllib

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, team=True, harnesses=["codex", "copilot", "opencode", "kiro", "cursor"])
            section = (root / "AGENTS.md").read_text(encoding="utf-8").split(repo.TEAM_MARK, 1)[1]
            self.assertLess(len(section.encode()), 4096, "the AGENTS.md team section should point, not copy")
            self.assertIn("advisory", section)
            for key in resources.roles()["order"]:
                self.assertIn(f"`aidd-{key}`", section)
                codex = tomllib.loads((root / f".codex/agents/aidd-{key}.toml").read_text(encoding="utf-8"))
                self.assertEqual(codex["name"], f"aidd-{key}")
                self.assertTrue(codex["description"] and "advisory" in codex["developer_instructions"])
                copilot = (root / f".github/agents/aidd-{key}.agent.md").read_text(encoding="utf-8")
                self.assertTrue(copilot.startswith(f"---\nname: aidd-{key}\ndescription: "))
                opencode = (root / f".opencode/agents/aidd-{key}.md").read_text(encoding="utf-8")
                self.assertIn("\nmode: subagent\n", opencode)
                kiro = json.loads((root / f".kiro/agents/aidd-{key}.json").read_text(encoding="utf-8"))
                self.assertEqual(kiro["name"], f"aidd-{key}")
                self.assertIn("read", kiro["tools"])
            reviewer = tomllib.loads((root / ".codex/agents/aidd-reviewer.toml").read_text(encoding="utf-8"))
            self.assertEqual(reviewer.get("sandbox_mode"), "read-only")
            self.assertIn("  edit: deny\n  bash: deny\n", (root / ".opencode/agents/aidd-reviewer.md").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((root / ".kiro/agents/aidd-reviewer.json").read_text(encoding="utf-8"))["tools"], ["read"])
            # Every file init wrote is a protected path: an agent cannot rewrite its own role in a minor change.
            from aidd import globs

            protected = resources.baseline()["protected_paths"]
            for rel in repo.team_files(list(repo.NATIVE_AGENT_HARNESSES)):
                self.assertTrue(globs.match_any(protected, rel), rel)
            # Uninstall removes exactly what init wrote.
            repo.uninstall(root, yes=True)
            for rel in repo.team_files(list(repo.NATIVE_AGENT_HARNESSES)):
                self.assertFalse((root / rel).exists(), rel)


class ExtensionTierTests(unittest.TestCase):
    """Every extension says who stands behind it; a community one is emerging, licensed for commercial use, and pinned."""

    TIERS = {"official", "vendor", "maintainer", "community"}
    # Licenses compatible with shipping beside an Apache-2.0 project and with commercial use.
    COMMUNITY_LICENSES = {"0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT"}
    OFFICIAL_DIRECTORY = "https://github.com/anthropics/claude-plugins-official"
    OFFICIAL_SOURCES = ("https://github.com/anthropics/", "https://code.claude.com/")

    def extensions(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            for x in role["extends"]:
                yield key, x

    def test_every_extension_has_a_tier(self):
        for key, x in self.extensions():
            self.assertIn(x.get("tier"), self.TIERS, (key, x["name"]))

    def test_a_community_extension_is_emerging_licensed_and_pinned(self):
        seen = 0
        for key, x in self.extensions():
            if x["tier"] != "community":
                continue
            seen += 1
            self.assertEqual(x.get("maturity"), "emerging", (key, x["name"]))
            self.assertIn(x.get("license"), self.COMMUNITY_LICENSES, (key, x["name"]))
            self.assertTrue(x.get("pin", "").strip(), (key, x["name"]))
        self.assertGreater(seen, 0, "no community extension left to check")

    def test_an_official_extension_is_made_by_the_harness_vendor(self):
        """`official` means the harness vendor made it; a third-party entry its directory lists keeps its maker's tier."""
        for key, x in self.extensions():
            if x["tier"] == "official":
                self.assertTrue(x["source"].startswith(self.OFFICIAL_SOURCES), (key, x["name"]))
            if x.get("listed_in"):
                self.assertEqual(x["listed_in"], self.OFFICIAL_DIRECTORY, (key, x["name"]))
                self.assertTrue(x.get("pin"), (key, x["name"]))
                self.assertNotEqual(x["tier"], "official", (key, x["name"]))

    def test_the_schema_enforces_the_tier_rules(self):
        from aidd import schema

        data = resources.load_json("roles.json")
        self.assertEqual(schema.validate(data, "roles.schema.json"), [])
        for field, value in (("license", "GPL-3.0"), ("maturity", "established"), ("pin", None), ("tier", None)):
            broken = json.loads(json.dumps(data))
            entry = next(x for x in broken["roles"]["developer"]["extends"] if x["name"] == "CodeGraph")
            if value is None:
                del entry[field]
            else:
                entry[field] = value
            self.assertTrue(schema.validate(broken, "roles.schema.json"), field)
        broken = json.loads(json.dumps(data))
        entry = next(x for x in broken["roles"]["developer"]["extends"] if x["name"] == "Superpowers")
        entry["tier"] = "official"
        self.assertTrue(schema.validate(broken, "roles.schema.json"), "a listing in the official directory does not make it official")
        broken = json.loads(json.dumps(data))
        entry = next(x for x in broken["roles"]["developer"]["extends"] if x["name"] == "Superpowers")
        del entry["pin"]
        self.assertTrue(schema.validate(broken, "roles.schema.json"), "a listed entry names the directory's pinned commit")
        for kind in ("tool", "plugin", "skill"):
            for field in ("license", "pin"):
                broken = json.loads(json.dumps(data))
                entry = next(x for r in broken["roles"].values() for x in r["extends"] if x["kind"] == kind)
                del entry[field]
                self.assertTrue(schema.validate(broken, "roles.schema.json"), f"a {kind} without its {field}")

    def test_the_curated_entries(self):
        ext = {(k, x["name"]): x for k, x in self.extensions()}
        names = {x["name"] for x in ext.values()}
        self.assertNotIn("Product Manager Skills", names, "CC BY-NC-SA is non-commercial")
        sp = ext[("developer", "Superpowers")]
        # Made by its author, Jesse Vincent, and listed in (not made by) the official directory.
        self.assertEqual((sp["tier"], sp["maturity"], sp["listed_in"]), ("community", "emerging", self.OFFICIAL_DIRECTORY))
        for skill in ("systematic debugging", "test-driven development", "verification before completion", "receiving code review"):
            self.assertIn(skill, sp["adds"])
        self.assertIn("superseded by the aidd loop", sp["adds"])
        self.assertIn("never merge", sp["adds"])
        for key, name, lic in (("product-designer", "Impeccable", "Apache-2.0"), ("developer", "CodeGraph", "MIT")):
            self.assertEqual((ext[(key, name)]["tier"], ext[(key, name)]["license"]), ("community", lic))
        for key, name in (("reviewer", "pr-review-toolkit"), ("developer", "code-simplifier"), ("security-engineer", "security-guidance")):
            x = ext[(key, name)]
            self.assertEqual((x["kind"], x["tier"]), ("plugin", "official"), name)
            self.assertTrue(x["source"].startswith(self.OFFICIAL_DIRECTORY + "/tree/main/plugins/"), name)
        for key, name in (
            ("platform-engineer", "Renovate"),
            ("platform-engineer", "Dependabot"),
            ("platform-engineer", "OSV-Scanner"),
            ("security-engineer", "OSV-Scanner"),
            ("developer", "knip"),
            ("reviewer", "knip"),
            ("developer", "vulture"),
            ("reviewer", "vulture"),
        ):
            self.assertEqual(ext[(key, name)]["tier"], "maintainer", (key, name))

    def test_the_tier_reaches_the_agent_files_and_the_tables(self):
        from aidd import docs

        table = docs.render("roles:extends")
        self.assertIn("| Tier |", table)
        for key, role in resources.roles()["roles"].items():
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn("**Extend with (optional, only when the project already uses it", text, key)
            for x in role["extends"]:
                self.assertIn(f"{x['name']} ({docs.maturity_text(x)})", text, (key, x["name"]))
                self.assertIn(f"| `{key}` | {x['name']} | ", table)


class ExtensionCapabilityTests(unittest.TestCase):
    """Every extension says what it can touch, so a team sees it before installing, and the security review knows where to look."""

    CAPABILITIES = {"network", "writes_repo", "runs_commands", "reads_secrets", "telemetry"}
    RISKY = {"writes_repo", "runs_commands"}

    def extensions(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            for x in role["extends"]:
                yield key, x

    def test_every_extension_declares_its_capabilities(self):
        for key, x in self.extensions():
            caps = x.get("capabilities")
            self.assertIsInstance(caps, list, (key, x["name"]))
            self.assertLessEqual(set(caps), self.CAPABILITIES, (key, x["name"]))
            self.assertEqual(len(caps), len(set(caps)), (key, x["name"]))

    def test_one_extension_declares_the_same_capabilities_in_every_role(self):
        seen: dict[str, tuple] = {}
        for key, x in self.extensions():
            caps = (sorted(x["capabilities"]), x.get("telemetry_opt_out"))
            self.assertEqual(seen.setdefault(x["name"], caps), caps, (key, x["name"]))

    def test_telemetry_states_whether_it_can_be_turned_off(self):
        for key, x in self.extensions():
            if "telemetry" in x["capabilities"]:
                self.assertIsInstance(x.get("telemetry_opt_out"), bool, (key, x["name"]))
            else:
                self.assertNotIn("telemetry_opt_out", x, (key, x["name"]))

    def test_a_community_extension_that_writes_or_runs_is_pinned(self):
        risky = [(k, x) for k, x in self.extensions() if x["tier"] == "community" and self.RISKY & set(x["capabilities"])]
        self.assertTrue(risky, "no community extension that writes or runs left to check")
        for key, x in risky:
            self.assertTrue(x.get("pin", "").strip(), (key, x["name"]))

    def test_the_schema_enforces_the_capability_rules(self):
        from aidd import schema

        data = resources.load_json("roles.json")
        self.assertEqual(schema.validate(data, "roles.schema.json"), [])

        def broken(edit):
            copy = json.loads(json.dumps(data))
            edit(next(x for x in copy["roles"]["developer"]["extends"] if x["name"] == "CodeGraph"))
            return schema.validate(copy, "roles.schema.json")

        self.assertTrue(broken(lambda x: x.pop("capabilities")), "capabilities is required")
        self.assertTrue(broken(lambda x: x.update(capabilities=["filesystem"])), "an unknown capability")
        self.assertTrue(broken(lambda x: x.update(capabilities=["network", "network"])), "a repeated capability")
        self.assertTrue(broken(lambda x: x.pop("telemetry_opt_out")), "telemetry without its opt-out")
        self.assertTrue(broken(lambda x: x.update(capabilities=["network"], telemetry_opt_out=True)), "an opt-out without telemetry")
        self.assertEqual(broken(lambda x: x.update(capabilities=["telemetry"], telemetry_opt_out=False)), [])
        self.assertEqual(broken(lambda x: (x.update(capabilities=[]), x.pop("telemetry_opt_out"))), [], "empty is read-only")
        self.assertTrue(broken(lambda x: (x.update(capabilities=["runs_commands"]), x.pop("pin"))), "a community extension that runs is pinned")

    def test_the_capabilities_reach_the_reference_table(self):
        from aidd import docs

        table = docs.render("roles:extends")
        self.assertIn("| Tier | Can | Adds |", table)
        for key, x in self.extensions():
            self.assertIn(f"| `{key}` | {x['name']} | ", table)
            row = next(r for r in table.splitlines() if r.startswith(f"| `{key}` | {x['name']} | "))
            self.assertIn(f" | {docs.capabilities_text(x)} | {x['adds']} |", row, (key, x["name"]))
        self.assertEqual(docs.capabilities_text({"capabilities": []}), "read-only")
        self.assertEqual(
            docs.capabilities_text({"capabilities": ["network", "runs_commands", "telemetry"], "telemetry_opt_out": True}),
            "network, runs commands, telemetry (can be turned off)",
        )
        # The reference explains why before the table: what an extension can touch is read before it is installed.
        text = (TEAM / "skills" / "aidd-team" / "references" / "extensions.md").read_text(encoding="utf-8")
        self.assertIn("**Can**", text.split("<!-- aidd:gen roles:extends -->")[0])


class SlimAgentFileTests(unittest.TestCase):
    """An agent file loads into every run of its role, so it carries what changes what the role does, and no more."""

    # Bytes (10 KiB). The files were 11,911 to 18,229 bytes before the slimming and 8,081 to 9,734 after it.
    BUDGET = 10 * 1024
    MAX_STANDARDS = 12

    def test_every_agent_file_is_under_the_budget(self):
        for key in resources.roles()["order"]:
            size = len((TEAM / "agents" / f"{key}.md").read_bytes())
            self.assertLess(size, self.BUDGET, f"{key}.md is {size} bytes; move narrow standards into a domain pack, not more text in")

    def test_every_role_applies_at_most_twelve_standards(self):
        for key, role in resources.load_json("roles.json")["roles"].items():
            self.assertLessEqual(len(role["standards"]), self.MAX_STANDARDS, key)

    def test_a_scoped_contract_rule_names_real_roles_or_steps(self):
        data = resources.load_json("roles.json")
        names = set(data["roles"]) | set(data["loop"]["steps"])
        scoped = [x for x in data["loop"]["contract"] if isinstance(x, dict)]
        self.assertTrue(scoped)
        for x in scoped:
            self.assertLessEqual(set(x["applies_to"]), names, x["rule"][:40])
            # A rule scoped to everyone is a rule without a scope.
            self.assertTrue(any(x["rule"] not in resources.contract_for(k) for k in data["roles"]), x["rule"][:40])

    def test_the_debugging_and_helper_rules_are_in_the_contract(self):
        # Each rule is found in the registry by its opening words, then checked by where it binds and where it renders;
        # rewording the rest of a rule leaves this test alone.
        data = resources.load_json("roles.json")
        items = data["loop"]["contract"]

        def rule(opening: str):
            found = [x for x in items if (x if isinstance(x, str) else x["rule"]).startswith(opening)]
            self.assertEqual(len(found), 1, opening)
            return found[0]

        repro, helper = rule("No fix without a reproduction"), rule("A helper's 'done' is a claim")
        # The reproduction rule binds only the roles and steps that fix code; the helper rule binds everyone.
        self.assertIsInstance(repro, dict)
        self.assertIsInstance(helper, str)
        for key in data["order"]:
            binds = resources.contract_for(key)
            agent = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn(helper, binds, key)
            self.assertIn(helper, agent, key)
            self.assertEqual(repro["rule"] in binds, repro["rule"] in agent, key)
        self.assertIn(repro["rule"], resources.contract_for("developer"))
        self.assertNotIn(repro["rule"], resources.contract_for("reviewer"))

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
        self.assertIn("on the handoff note, where the reviewer reads it", steps[search])

    def test_an_edition_is_printed_once_per_agent_file(self):
        from aidd import docs

        stds = [{"id": "x", "name": "X for A", "release": "1.0", "edition": "1.0 (published 2020-01-01); notes"}, {"id": "x", "name": "X for B"}]
        self.assertEqual(docs.role_standards_text(stds, full=False), ["X for A (1.0)", "X for B"])
        self.assertEqual(docs.role_standards_text(stds), ["X for A (1.0 (published 2020-01-01); notes)", "X for B"])


class VerifierTests(unittest.TestCase):
    """The runtime verifier runs the change, reports, and never writes."""

    def test_the_verifier_runs_the_change_but_writes_nothing(self):
        data = resources.roles()
        v = data["roles"]["verifier"]
        self.assertEqual((v["writes"], v["in_scope"], v["tier"]), ([], False, "execution"))
        self.assertEqual(v["steps"], ["Verify"])
        self.assertIn("Acceptance", v["done_when"])
        # Its report is about one commit: it starts with the head SHA, and a new push makes it stale.
        self.assertIn("head SHA", v["done_when"])
        self.assertIn("stale", v["done_when"])
        front = dict(re.findall(r"^(\w+): (.+)$", (TEAM / "agents" / "verifier.md").read_text(encoding="utf-8").split("---")[1], re.M))
        tools = {t.strip() for t in front["tools"].split(",")}
        self.assertIn("Bash", tools)
        self.assertFalse(tools & {"Write", "Edit", "NotebookEdit"})
        # It sits after the builders and before Review, in a step of its own: the verify flow runs it alone, right
        # after the implement flow, and it hands to the readers.
        flows = [f["command"] for f in data["loop"]["flows"]]
        verify = next(f for f in data["loop"]["flows"] if f["command"] == "verify")
        self.assertEqual((verify["steps"], verify["runs"]), (["Verify"], [["verifier"]]))
        self.assertEqual(flows.index("verify"), flows.index("implement") + 1)
        implement = next(f for f in data["loop"]["flows"] if f["command"] == "implement")
        self.assertNotIn(["verifier"], implement["runs"])
        self.assertIn("Verify", implement["stops_at"])
        steps = data["loop"]["steps"]
        self.assertEqual(steps.index("Verify"), steps.index("Implement") + 1)
        handoff = next(h for h in data["loop"]["handoffs"] if h["from"] == ["verifier"])
        self.assertIn("reviewer", handoff["to"])
        self.assertTrue(any("verifier's mismatch" in x for x in data["loop"]["contract"]))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_the_guard_denies_every_verifier_edit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            repo.init(root, profile="team", ci="none", links=[], skill=False, approvers=["@x"])
            for path in ("src/app.py", "tests/test_app.py", "specs/SPEC-1.md", "REVIEW.md"):
                self.assertEqual(guard.check_edit(str(root), path, "verifier")[0], "deny", path)


class SweepTests(unittest.TestCase):
    def test_the_sweep_stops_at_g2_and_never_widens_scope(self):
        data = resources.roles()
        sweep = next(f for f in data["loop"]["flows"] if f["command"] == "sweep")
        self.assertIn("Merge approval", sweep["stops_at"])
        text = (TEAM / "commands" / "sweep.md").read_text(encoding="utf-8")
        for must in ("One fix per comment", "aidd test", "aidd gate", "Specify", "Never approve, never merge", "frozen"):
            self.assertIn(must, text, must)
        self.assertNotIn("--force", text)


class RaciTests(unittest.TestCase):
    """The RACI table in docs/TEAM.md is hand-written prose about generated data.

    The audit found it giving the product-manager a Learn responsibility while the registry gives
    that role only Plan, which contradicts loop contract rule 1 ("work only in your loop steps").
    A table nobody checks against its source drifts, so this holds it to the registry.
    """

    def test_a_role_is_responsible_only_in_the_steps_it_has(self):
        import re

        data = resources.roles()
        text = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        block = text.split("## Who is responsible (RACI)", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in block.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
        self.assertGreaterEqual(len(rows), 10, "the RACI table lost its rows")
        step_of = lambda label: label.split(":")[0].strip()  # noqa: E731
        for ln in rows:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            step, responsible = step_of(cells[0]), cells[1]
            self.assertIn(step, data["loop"]["steps"], f"RACI names a step the loop does not have: {step!r}")
            for role in re.findall(r"[a-z]+-[a-z-]+", responsible):
                self.assertIn(role, data["roles"], f"RACI names a role the registry does not have: {role!r}")
                self.assertIn(
                    step, data["roles"][role]["steps"], f"RACI makes `{role}` responsible for {step}, but the registry gives it {data['roles'][role]['steps']}"
                )

    def test_the_router_skill_names_every_role_by_its_current_key(self):
        """Its description is hand-written frontmatter and lists all fourteen roles by name.

        A rename silently leaves a router trigger pointing at a role that no longer exists, and
        nothing else would notice: the description is above the first generated block.
        """
        text = (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        for key in resources.roles()["order"]:
            self.assertIn(key, text, f"`{key}` is a role but is not a router trigger in the aidd-team skill")
        inner = text.split("names a role (", 1)[1].split(")", 1)[0]
        listed = {x.strip().strip("`") for x in inner.split(",") if x.strip()}
        self.assertEqual(listed, set(resources.roles()["order"]), "the router trigger list and the registry disagree")

    def test_every_role_appears_in_the_raci_table(self):
        text = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8").split("## Who is responsible (RACI)", 1)[1].split("\n## ", 1)[0]
        for key in resources.roles()["order"]:
            self.assertIn(key, text, f"`{key}` is in the registry but nowhere in the RACI table")


class CapabilityTests(unittest.TestCase):
    """The team covers every software life cycle process an engineering firm is measured against, and says who acts."""

    def test_every_12207_process_is_mapped_to_something_real(self):
        from aidd import cli

        caps = resources.roles()["loop"]["capabilities"]
        processes = caps["processes"]
        self.assertIn("12207", caps["standard"])
        self.assertEqual(len(processes), 30)  # ISO/IEC/IEEE 12207:2017 defines thirty processes
        self.assertEqual(len({c["process"] for c in processes}), 30)
        roles = set(resources.roles()["roles"])
        commands = {p.stem for p in (TEAM / "commands").glob("*.md")}
        subcommands = set(cli.build_parser()._subparsers._group_actions[0].choices)
        for c in processes:
            self.assertEqual(c["coverage"] == "people", not c["by"], c["process"])
            for by in c["by"]:
                if by.startswith("/aidd-team:"):
                    self.assertIn(by.removeprefix("/aidd-team:"), commands, (c["process"], by))
                elif by.startswith("aidd "):
                    self.assertIn(by.split()[1], subcommands, (c["process"], by))
                elif by != "standard changes":
                    self.assertIn(by, roles, (c["process"], by))

    def test_the_map_reaches_the_team_page(self):
        text = (ROOT / "docs" / "TEAM-REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen roles:capabilities -->", text)
        for c in resources.roles()["loop"]["capabilities"]["processes"]:
            self.assertIn(f"| {c['process']} |", text)


if __name__ == "__main__":
    unittest.main()
