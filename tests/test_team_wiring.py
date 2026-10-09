"""The aidd-team roles as the harness runs them: the tools and skills each agent file gets, what each role reads and
hands on, and the gate status an implementer checks before it builds."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import docs, repo, resources

TEAM = ROOT / "plugins" / "aidd-team"


class SpecApprovalPreconditionTests(unittest.TestCase):
    """Spec approval is a recorded decision the gate reads, never a sentence in chat."""

    FILES = (TEAM / "commands" / "implement.md", TEAM / "agents" / "developer.md")

    def test_a_chat_statement_is_not_spec_approval(self):
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("the author confirms it", text)
                self.assertIn("If you cannot read the gate status, stop and ask the author to run `aidd gate`; a statement in chat is not Spec approval", text)
                self.assertNotIn("paste the check status", text)
                self.assertIn("a statement in chat is not Spec approval", text)


def front_matter(text: str) -> tuple[dict[str, str], list[str]]:
    """(scalar fields, the `skills:` list) of an agent file's front matter."""
    head = text.split("---")[1]
    fields = dict(re.findall(r"^(\w+): (.+)$", head, re.M))
    skills = re.findall(r"^  - (.+)$", head.split("\nskills:\n", 1)[1], re.M) if "\nskills:\n" in head else []
    return fields, skills


def helper_rule() -> str:
    return next(x for x in resources.roles()["loop"]["contract"] if x.startswith("Use AI as a delivery team does"))


class AgentToolsTests(unittest.TestCase):
    """Per the Claude Code subagent docs (checked 2026-09-28): a `tools:` allowlist hides every tool it does not name,
    `skills:` preloads a skill's whole text at startup, and `Agent(a, b)` limits which helper types a subagent spawns."""

    def roles(self):
        for key in resources.roles()["order"]:
            yield key, *front_matter((TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8"))

    def test_every_role_can_load_skills_delegate_and_research(self):
        for key, front, _ in self.roles():
            tools = docs.split_tools(front["tools"])
            with self.subTest(role=key):
                self.assertIn("Skill", tools)
                self.assertIn("WebFetch", tools)
                self.assertIn("WebSearch", tools)
                # Contract: helpers of the role's own type or read-only ones. A read-only role works alone: Claude Code
                # ignores the type list in a subagent, so only leaving `Agent` out keeps its helpers from writing.
                agent = [t for t in tools if t.startswith(("Agent", "Task"))]
                if resources.roles()["roles"][key]["writes"]:
                    self.assertEqual(agent, [f"Agent(aidd-team:{key}, Explore)"])
                    self.assertIn(helper_rule(), resources.contract_for(key))
                else:
                    # A read-only role works alone, so the helper rule is not in its contract either.
                    self.assertEqual(agent, [])
                    self.assertNotIn(helper_rule(), resources.contract_for(key))

    def test_the_read_only_roles_stay_read_only(self):
        for key in ("reviewer", "verifier"):
            tools = set(docs.split_tools(front_matter((TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8"))[0]["tools"]))
            self.assertFalse(tools & {"Write", "Edit", "NotebookEdit"}, key)

    def test_every_role_preloads_its_usual_skills_and_a_spec_or_test_writer_the_aidd_skill(self):
        slugs = {d["slug"] for d in resources.roles()["domains"]}
        for key, _, skills in self.roles():
            role = resources.roles()["roles"][key]
            with self.subTest(role=key):
                core = ["aidd:aidd"] if docs.preloads_core(key) else []
                self.assertEqual(skills, [*core, *(f"aidd-team:{x}" for x in role["preload"])])
                self.assertLessEqual(len(role["preload"]), 2)
                for x in role["preload"]:
                    self.assertTrue(x in role["practices"] or x in slugs, x)
                    text = (TEAM / "skills" / x / "SKILL.md").read_text(encoding="utf-8")
                    # A skill only its user may run cannot be preloaded.
                    self.assertNotIn("disable-model-invocation: true", text.split("---")[1], x)

    def test_the_rules_bind_only_roles_that_have_the_tools(self):
        helper = next(x for x in resources.roles()["loop"]["contract"] if x.startswith("A helper's 'done' is a claim"))
        research = next(x for x in resources.roles()["loop"]["contract"] if x.startswith("Research first"))
        self.assertIn("(WebFetch, WebSearch)", research)
        for key, front, _ in self.roles():
            tools = set(docs.split_tools(front["tools"]))
            if research in resources.contract_for(key):
                self.assertLessEqual({"WebFetch", "WebSearch"}, tools, key)
        # Every role has a shell: `aidd new --no-link`, `aidd test`, and a fresh test run need one; the hook bounds its writes.
        no_shell = {key for key, front, _ in self.roles() if "Bash" not in docs.split_tools(front["tools"])}
        self.assertEqual(no_shell, set())
        self.assertIn("a fresh test run", helper)

    def test_a_project_install_names_the_vendored_skill_and_the_prefixed_role(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, team=True, harnesses=[], approvers=["@me"])
            front, skills = front_matter((root / ".claude/agents/aidd-developer.md").read_text(encoding="utf-8"))
            self.assertEqual(skills, ["aidd", "aidd-secure-coding"])
            self.assertIn("Agent(aidd-developer, Explore)", docs.split_tools(front["tools"]))

    def test_split_tools_keeps_an_agent_allowlist_whole(self):
        self.assertEqual(docs.split_tools("Read, Agent(a, b), mcp__x__*"), ["Read", "Agent(a, b)", "mcp__x__*"])


class PackDescriptionTests(unittest.TestCase):
    def test_a_pack_description_leads_with_its_trigger_nouns(self):
        for d in resources.roles()["domains"]:
            text = (TEAM / "skills" / d["slug"] / "SKILL.md").read_text(encoding="utf-8")
            description = json.loads(re.search(r"^description: (.+)$", text, re.M).group(1))
            with self.subTest(pack=d["slug"]):
                self.assertTrue(description.startswith(f"{docs.PACK_TRIGGER}{d['triggers'][0]}, "), description[:80])
                self.assertLessEqual(len(description), 200)  # every session lists every description
        health = next(d for d in resources.roles()["domains"] if d["slug"] == "health")
        self.assertLessEqual({"FHIR", "HL7", "PHI", "patient records", "medical devices", "HIPAA"}, set(health["triggers"]))


class ExtensionRegistryTests(unittest.TestCase):
    """Every extension names what a team may do with it (license) and exactly what it installs (pin)."""

    def extensions(self):
        for key in resources.roles()["order"]:
            for x in resources.roles()["roles"][key]["extends"]:
                yield key, x

    def test_every_extension_has_a_license_and_a_pin(self):
        for key, x in self.extensions():
            with self.subTest(role=key, name=x["name"]):
                self.assertTrue(x.get("license"))
                self.assertTrue(x.get("pin"))
                if x["pin"].startswith("vendor-hosted"):
                    # Only a server its vendor runs is pinned by its endpoint, never a tool, plugin, or skill.
                    self.assertEqual(x["kind"], "mcp")
                    self.assertRegex(x["pin"], r"^vendor-hosted https://\S+$")

    # Licenses a team adopts without reading further: OSI-approved, permissive or weak copyleft on a tool it runs.
    PERMISSIVE = {"MIT", "Apache-2.0", "ISC", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0"}

    def test_the_licenses_a_team_must_read_before_installing(self):
        """Invariants, so a registry refresh that changes a license keeps the tests meaningful: every license is an SPDX
        identifier or names itself proprietary; a license that restricts use (source-available, a proprietary one
        the team installs rather than calls as a hosted service, or a component under other terms) carries a note;
        and the extensions table shows the license with its note on that extension's row."""
        rendered = docs.render("roles:extends").splitlines()
        noted = restricted_seen = 0
        for key, x in self.extensions():
            with self.subTest(role=key, name=x["name"]):
                lic, note = x["license"], x.get("license_note", "")
                self.assertRegex(lic, r"^(Proprietary( \([a-z -]+\))?|[A-Za-z0-9][A-Za-z0-9.+-]*)$")
                hosted = x["pin"].startswith("vendor-hosted")
                if "source-available" in lic or lic.startswith(("FSL-", "BUSL-")) or (lic.startswith("Proprietary") and not hosted):
                    restricted_seen += 1
                    self.assertTrue(note, "a restricted license says what it restricts")
                if note:
                    noted += 1
                    self.assertNotIn(lic, self.PERMISSIVE, "a note on a permissive license belongs in adds")
                row = next(ln for ln in rendered if ln.startswith(f"| `{key}` | {x['name']} |"))
                self.assertIn(f"| {lic} ({note}) |" if note else f"| {lic} |", row)
        self.assertGreater(restricted_seen, 0)
        self.assertGreaterEqual(noted, restricted_seen)

    def test_plane_is_a_pinned_community_server_for_the_product_manager(self):
        maturities = resources.load_json("roles.schema.json")["$defs"]["maturity"]["enum"]
        plane = next(x for x in resources.roles()["roles"]["product-manager"]["extends"] if x["name"] == "Plane MCP")
        self.assertEqual((plane["kind"], plane["tier"]), ("mcp", "community"))
        self.assertIn(plane["maturity"], maturities)
        self.assertIn(plane["license"], self.PERMISSIVE)
        self.assertEqual(plane["capabilities"], ["network", "reads_secrets"])
        # A community server is pinned by its release tag and the commit that tag names (`git ls-remote`).
        self.assertRegex(plane["pin"], r"^v\d+\.\d+\.\d+ \([0-9a-f]{40}\)$")
        # The server is MIT; Plane itself is not, and the entry says so.
        self.assertIn("AGPL-3.0", plane["adds"])

    def test_the_standards_check_fails_on_an_unpinned_tool_plugin_or_skill(self):
        from unittest import mock

        from aidd import evals

        self.assertEqual(evals.unpinned_extensions(), [])
        data = json.loads(json.dumps(resources.roles()))
        data["roles"]["developer"]["extends"].append({"name": "x", "kind": "tool", "license": "MIT"})
        data["roles"]["developer"]["extends"].append({"name": "y", "kind": "mcp"})
        with mock.patch("aidd.resources.roles", lambda: data):
            self.assertEqual([(x["name"], x["missing"]) for x in evals.unpinned_extensions()], [("x", ["pin"])])


class StandardsDatesTests(unittest.TestCase):
    """A `checked` date names what was read and where; a practice with nothing to check against is `reviewed`."""

    def setUp(self):
        self.data = resources.load_json("roles.json")
        self.table = self.data["standards"]

    def test_every_checked_entry_names_its_source_and_evidence(self):
        from aidd import evals

        self.assertEqual([s["id"] for s in evals.unevidenced_standards()], [])
        for sid, s in self.table.items():
            self.assertNotEqual("checked" in s, "reviewed" in s, sid)
            if "reviewed" in s:
                self.assertNotIn("edition", s, sid)
        self.assertGreater(sum("reviewed" in s for s in self.table.values()), 20, "the unversioned practices")

    def test_the_eval_and_the_schema_reject_a_bare_checked_date(self):
        from unittest import mock

        from aidd import evals, schema

        table = {"x": {"name": "X", "checked": "2026-09-28"}, "y": {"name": "Y", "reviewed": "2026-09-28"}}
        with mock.patch("aidd.resources.load_json", lambda name: {"standards": table}):
            self.assertEqual([s["id"] for s in evals.unevidenced_standards()], ["x"])
        for edit in (
            lambda s: s.pop("evidence"),
            lambda s: s.pop("source"),
            lambda s: s.update(reviewed="2026-09-28"),
            lambda s: [s.pop(k) for k in ("checked", "checked_by", "evidence")],
        ):
            broken = json.loads(json.dumps(self.data))
            edit(broken["standards"]["blameless-postmortems"])
            self.assertTrue(schema.validate(broken, "roles.schema.json"))
        broken = json.loads(json.dumps(self.data))
        broken["standards"]["jobs-to-be-done"]["edition"] = "2016"
        self.assertTrue(schema.validate(broken, "roles.schema.json"), "a reviewed practice has no edition to check")

    def test_the_editions_checked_today(self):
        """Invariants a currency refresh keeps: two entries citing the same deadlines agree, a release edition names
        the commit its tag points at, and an entry with no release says what to record instead."""
        # The model cards entry repeats the AI Act's Article 50 dates; every date it cites is in the AI Act entry.
        ai, cards = self.table["eu-ai-act"], self.table["model-cards-and-system-cards-for"]
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", cards["notes"])
        self.assertTrue(dates)
        for d in dates:
            self.assertIn(d, ai["notes"], d)
        # A semantic-versioned edition names its release tag and the commit the tag points at.
        otel = self.table["opentelemetry-for-traces-metrics-and-logs"]
        self.assertRegex(otel["edition"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(otel["notes"], rf"\bv{re.escape(otel['edition'])} is commit [0-9a-f]{{40}}\b")
        # With no tagged release there is no edition and no sample commit to copy: the Spec records the one tested.
        genai = self.table["opentelemetry-genai-semconv"]
        self.assertNotIn("edition", genai)
        self.assertIn(genai["maturity"], resources.load_json("roles.schema.json")["$defs"]["maturity"]["enum"])
        self.assertTrue(genai["notes"].startswith("no tagged release"))
        self.assertIn("record the commit you tested in the Spec", genai["notes"])
        self.assertNotRegex(json.dumps(genai), r"\b[0-9a-f]{40}\b")


class ArtifactFlowTests(unittest.TestCase):
    """What each role reads is written by another role or comes from a person or the platform, and every handoff's
    artifact has a reader: nothing a role needs is re-derived, and nothing a role writes is lost (MetaGPT's shared
    message pool, as named artifacts instead of chat)."""

    EXTERNAL = {"human", "platform"}

    def setUp(self):
        self.data = resources.roles()
        self.arts = self.data["loop"]["artifacts"]
        self.handoffs = self.data["loop"]["handoffs"]

    def test_every_artifact_id_resolves_and_is_used(self):
        used = set()
        for key in self.data["order"]:
            self.assertTrue(set(self.data["roles"][key]["reads"]) <= set(self.arts), key)
            used |= set(self.data["roles"][key]["reads"])
        for h in self.handoffs:
            self.assertTrue(set(h["artifact"]) <= set(self.arts), h["through"])
            used |= set(h["artifact"])
        self.assertEqual(set(self.arts) - used, set(), "an artifact nobody writes or reads")
        for aid in self.arts:
            self.assertRegex(aid, r"^[a-z][a-z-]*$")

    def test_every_read_is_handed_over_or_comes_from_a_person_or_the_platform(self):
        for key in self.data["order"]:
            for aid in self.data["roles"][key]["reads"]:
                if self.arts[aid]["kind"] in self.EXTERNAL:
                    continue
                writers = {r for h in self.handoffs if aid in h["artifact"] for r in h["from"]}
                with self.subTest(role=key, artifact=aid):
                    self.assertTrue(writers, "no role hands it over")
                    self.assertTrue(writers - {key}, "only the reader itself writes it")

    def test_every_handoff_artifact_is_read_by_each_role_it_goes_to(self):
        roles = set(self.data["roles"])
        for h in self.handoffs:
            readers = [t for t in h["to"] if t in roles]
            self.assertTrue(readers or any(t.startswith("the author") for t in h["to"]), h["through"])
            for r in readers:
                for aid in h["artifact"]:
                    self.assertIn(aid, self.data["roles"][r]["reads"], (h["through"], r))
            # A person or the platform is a source, never something a role hands on.
            self.assertFalse({self.arts[a]["kind"] for a in h["artifact"]} & self.EXTERNAL, h["through"])

    def test_no_handoff_is_text_returned_in_chat(self):
        for h in self.handoffs:
            self.assertNotIn("returned as text", h["through"])
        for key in self.data["order"]:
            self.assertNotIn("returned as text", self.data["roles"][key]["hands_off"], key)
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn(f"- **Reads:**\n{docs.role_reads(self.data['roles'][key])}\n", text, key)

    def test_the_specialists_return_fixed_templates(self):
        ref = (ROOT / ".agents" / "skills" / "aidd" / "references" / "spec.md").read_text(encoding="utf-8")
        section = ref.split("## Specialist returns (fixed templates)", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Mitigation | Acceptance id | Owner |", section)
        self.assertIn(
            "| SLI (golden signal, RED or USE) | SLO | Observe signal (dashboard, query, or `observe.command`) | Window | Rollback trigger |", section
        )
        self.assertIn("| Obligation (law or standard, article) | Control | Evidence (test, file, or gate record) | Owner |", section)
        for role, target in (("security-engineer", "### Security and privacy"), ("compliance-analyst", "### Compliance"), ("sre", "### Observability")):
            text = (TEAM / "agents" / f"{role}.md").read_text(encoding="utf-8")
            self.assertIn("return template (the aidd skill's Spec reference, Specialist returns)", text, role)
            self.assertIn(target, text, role)
            self.assertIn(target, section, role)
        self.assertIn("### Compliance", (ROOT / ".agents" / "skills" / "aidd" / "assets" / "tech-spec.md").read_text(encoding="utf-8"))


class PerRoleModelTests(unittest.TestCase):
    """`[agents.models]` reaches each harness's own agent model field, in the format its docs give (checked 2026-09-28)."""

    MODELS = {
        "reasoning": "anthropic/claude-opus-5-5",
        "execution": "anthropic/claude-sonnet-5",
        "reviewer": "openai/gpt-6-astra",
    }

    def test_a_role_entry_wins_over_its_tier(self):
        from aidd import agentmodels

        self.assertEqual(agentmodels.resolve(self.MODELS, "reviewer"), "openai/gpt-6-astra")
        self.assertEqual(agentmodels.resolve(self.MODELS, "architect"), "anthropic/claude-opus-5-5")
        self.assertEqual(agentmodels.resolve(self.MODELS, "developer"), "anthropic/claude-sonnet-5")
        self.assertIsNone(agentmodels.resolve({}, "developer"))
        self.assertEqual(agentmodels.family("anthropic/claude-opus-5-5"), agentmodels.family("anthropic/claude-sonnet-5"))
        self.assertNotEqual(agentmodels.family("anthropic/claude-opus-5-5"), agentmodels.family("openai/gpt-6-astra"))
        with self.assertRaises(ValueError):
            agentmodels.split("claude-opus-5-5")

    def test_each_harness_gets_the_value_it_can_run(self):
        from aidd import agentmodels

        m = "anthropic/claude-opus-5-5"
        self.assertEqual(agentmodels.harness_model("claude-code", m), "claude-opus-5-5")
        self.assertIsNone(agentmodels.harness_model("codex", m))
        self.assertEqual(agentmodels.harness_model("opencode", m), m)
        self.assertEqual(agentmodels.harness_model("kiro", m), "claude-opus-5-5")
        self.assertEqual(agentmodels.harness_model("copilot", m), "claude-opus-5-5")
        self.assertEqual(agentmodels.harness_model("codex", "openai/gpt-6-astra"), "gpt-6-astra")
        self.assertIsNone(agentmodels.harness_model("claude-code", "openai/gpt-6-astra"))

    def test_init_and_uninstall_write_and_recognize_the_model_fields(self):
        import tomllib

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"])
            cfg = root / ".aidd" / "config.toml"
            cfg.write_text(
                cfg.read_text(encoding="utf-8") + "\n[agents.models]\n" + "".join(f'{k} = "{v}"\n' for k, v in self.MODELS.items()),
                encoding="utf-8",
            )
            actions: list[str] = []
            repo.install_team(root, actions, harnesses=list(repo.NATIVE_AGENT_HARNESSES))
            claude = lambda k: (root / f".claude/agents/aidd-{k}.md").read_text(encoding="utf-8").split("---")[1]  # noqa: E731
            self.assertIn("\nmodel: claude-opus-5-5\n", claude("architect"))
            self.assertIn("\nmodel: claude-sonnet-5\n", claude("developer"))
            # Claude Code cannot run the reviewer's OpenAI model: the tier's alias stays, and the file says why.
            self.assertIn("\nmodel: opus\n# [agents.models] names openai/gpt-6-astra, which this harness's agent model field cannot select", claude("reviewer"))
            codex = tomllib.loads((root / ".codex/agents/aidd-reviewer.toml").read_text(encoding="utf-8"))
            self.assertEqual(codex["model"], "gpt-6-astra")
            self.assertNotIn("model", tomllib.loads((root / ".codex/agents/aidd-developer.toml").read_text(encoding="utf-8")))
            self.assertIn("cannot select", (root / ".codex/agents/aidd-developer.toml").read_text(encoding="utf-8"))
            self.assertIn("\nmodel: anthropic/claude-sonnet-5\n", (root / ".opencode/agents/aidd-developer.md").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((root / ".kiro/agents/aidd-architect.json").read_text(encoding="utf-8"))["model"], "claude-opus-5-5")
            self.assertIn("\nmodel: gpt-6-astra\n", (root / ".github/agents/aidd-reviewer.agent.md").read_text(encoding="utf-8"))
            # Uninstall compares against what init wrote with the same models, so it removes every file.
            repo.uninstall(root, yes=True)
            for rel in repo.team_files(list(repo.NATIVE_AGENT_HARNESSES), True, self.MODELS):
                self.assertFalse((root / rel).exists(), rel)

    def test_a_models_key_that_names_no_tier_and_no_role_is_a_warning(self):
        """A stale or misspelt `[agents.models]` key selects nothing, so it must not pass in silence."""
        from aidd import agentmodels

        good = {"reasoning": "anthropic/claude-opus-5-5", "execution": "anthropic/claude-sonnet-5-5", "verifier": "openai/gpt-6-sol"}
        self.assertEqual(agentmodels.unknown_key_warnings(good), [])
        warnings = agentmodels.unknown_key_warnings({**good, "mechanical": "x/y", "revewer": "x/y"})
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("'mechanical'" in w for w in warnings) and any("'revewer'" in w for w in warnings))
        self.assertTrue(all("selects nothing" in w for w in warnings))

    def test_independent_review_warns_on_one_model_family(self):
        from aidd import agentmodels

        self.assertEqual(agentmodels.independent_review_warnings(self.MODELS, False), [])
        warnings = agentmodels.independent_review_warnings(self.MODELS, True)
        # The reviewer is on OpenAI; the verifier takes the execution entry, Claude like the developer.
        self.assertEqual(len(warnings), 1)
        self.assertIn("the verifier (anthropic/claude-sonnet-5) and the developer (anthropic/claude-sonnet-5) are one model family", warnings[0])
        self.assertTrue(all("sets no model" in w for w in agentmodels.independent_review_warnings({}, True)))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"])
            cfg = root / ".aidd" / "config.toml"
            # `aidd init` writes no [agents] table, so the test adds its own.
            cfg.write_text(
                cfg.read_text(encoding="utf-8") + '\n[agents]\nindependent_review = true\n\n[agents.models]\nexecution = "anthropic/claude-sonnet-5"\n',
                encoding="utf-8",
            )
            report = repo.doctor(root)
            self.assertTrue(any(level == "warn" and "independent_review is on" in m and "the reviewer" in m for level, m in report), report)

    def test_the_config_schema_holds_the_model_strings(self):
        from aidd import schema

        base = {"aidd_version": "1.0.0", "profile": "solo"}
        self.assertEqual(schema.validate(dict(base, agents={"models": self.MODELS, "independent_review": True}), "config.schema.json"), [])
        self.assertTrue(schema.validate(dict(base, agents={"models": {"reasoning": "opus"}}), "config.schema.json"))
        self.assertTrue(schema.validate(dict(base, agents={"independent_review": "yes"}), "config.schema.json"))


class DomainExpertTests(unittest.TestCase):
    """The product manager interviews a person from a named specialist pool and quotes them in the Spec's Intent."""

    def test_the_product_manager_quotes_the_expert_from_a_named_pool(self):
        text = (TEAM / "agents" / "product-manager.md").read_text(encoding="utf-8")
        playbook = text.split("\n## Playbook\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("**Interview the domain expert.**", playbook)
        for must in ("`[owners.specialists] clinical = [...]`", "`[[risk_rules]]`", "`## Intent`", "ask the author who the expert is, and stop"):
            self.assertIn(must, playbook)
        steps = [int(ln.split(".", 1)[0]) for ln in playbook.splitlines() if ln[:1].isdigit()]
        self.assertEqual(steps, list(range(1, len(steps) + 1)))

    def test_the_readme_example_is_a_valid_config(self):
        import tomllib

        from aidd import schema

        readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
        example = readme.split("## Domain experts", 1)[1].split("```toml\n", 1)[1].split("```", 1)[0]
        data = {"aidd_version": "1.0.0", "profile": "team", **tomllib.loads(example)}
        data["owners"]["approvers"] = ["@org/leads"]
        self.assertEqual(schema.validate(data, "config.schema.json"), [])
        self.assertEqual(data["risk_rules"][0]["specialists"], list(data["owners"]["specialists"]))


class LivingArchitectureTests(unittest.TestCase):
    """After the merge, an optional follow-up folds the Spec's Design into docs/architecture/; the Spec stays as merged."""

    def test_the_follow_up_is_offered_and_owned(self):
        ship = (TEAM / "commands" / "ship.md").read_text(encoding="utf-8")
        self.assertIn("4. Optional, after a clean window:", ship)
        self.assertIn("`docs/architecture/`", ship)
        self.assertIn("Open it only if the author agrees.", ship)
        for role, how in (("architect", "architecture-document Task in the next Spec"), ("tech-writer", "docs-only change on the fast lane")):
            text = (TEAM / "agents" / f"{role}.md").read_text(encoding="utf-8")
            self.assertIn("**Living architecture (optional", text, role)
            self.assertIn("`docs/architecture/`", text, role)
            self.assertIn(how, text, role)
        # Both roles may write there: the architect by its own area, the tech writer through `docs/**`.
        for role in ("architect", "tech-writer"):
            self.assertTrue(any(w in ("docs/architecture/**", "docs/**") for w in resources.roles()["roles"][role]["writes"]), role)
        self.assertIn("## Living architecture docs", (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))


class ConsistencyTests(unittest.TestCase):
    """The contract, the skills, the agent files, and the commands say one thing."""

    FILES = (
        TEAM / "skills" / "aidd-team" / "SKILL.md",
        TEAM / "commands" / "implement.md",
        ROOT / "docs" / "TEAM.md",
        ROOT / ".agents" / "skills" / "aidd" / "references" / "loop.md",
    )

    def test_parallel_tasks_wait_for_the_first_to_land_green(self):
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("after the first Task lands green", text)
                self.assertNotIn("landed green", text)

    def test_no_role_is_asked_to_run_what_it_has_no_tool_for(self):
        skill = (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8")
        # The reviewer has no shell; the red run on base is `aidd test`'s evidence.
        self.assertNotIn("the reviewer checks that it fails without it", skill)
        self.assertIn("`aidd test` shows it red on base", skill)
        self.assertIn("A read-only role works alone.", skill)
        # The developer cannot write the Spec once it is approved, so its findings go on the handoff note.
        developer = (TEAM / "agents" / "developer.md").read_text(encoding="utf-8")
        self.assertNotIn("name what you found in the Spec's Context", developer)


if __name__ == "__main__":
    unittest.main()
