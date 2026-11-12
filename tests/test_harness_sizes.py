"""The sizes a coding agent's vendor documents (`config.SIZES`), and aidd's text under each one it imposes.

A harness limit is the one kind of size that is not aidd's to set: text past it is cut, skipped, dropped, or refused, or the
vendor documents it as a maximum. Each row carries its page and the date aidd read it. The text aidd writes stays under every
such row, and a vendor's advice (`guidance`) fails nothing. The listing of all descriptions is a report: its budget scales with
the person's window and is shared with their other plugins (`aidd eval packs`, `aidd doctor`).
"""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import budgets
import helpers
from helpers import ROOT

from aidd import config, knowledge
from aidd.cli import mcp_server
from aidd.docsgen import pack_budget
from aidd.kernel import documents
from aidd.setup import doctor_checks, doctor_listing, team_install

SKILLS = ROOT / ".agents" / "skills"
TEAM = ROOT / "plugins" / "aidd-team"
PAST = {"cut", "skipped", "dropped", "guidance", "not stated"}
UNITS = {"characters", "bytes", "lines", "tokens"}

# What aidd measures against each row that bounds text it writes: the row's `what`, with the size of each text, by name.
_SNIPPET = (ROOT / "templates" / "AGENTS.snippet.md").read_text(encoding="utf-8")


def _skill_names() -> dict[str, int]:
    folders = [p.parent for p in [*SKILLS.glob("*/SKILL.md"), *(TEAM / "skills").glob("*/SKILL.md")]]
    return {f.name: len(f.name) for f in folders}


def _descriptions() -> dict[str, int]:
    return {f"{d['type']} {d['name']}": d["chars"] for d in pack_budget.pack_descriptions()}


def _instruction_files() -> dict[str, int]:
    return {"AGENTS.md": len((ROOT / "AGENTS.md").read_bytes()), "the block aidd writes into AGENTS.md": len(_SNIPPET.encode())}


def _role_prompts() -> dict[str, int]:
    return {p.name: len(p.read_text(encoding="utf-8")) for p in (TEAM / "agents").glob("*.md")}


MEASURED = {
    ("agent-skills", "a skill's name", "characters"): _skill_names,
    ("agent-skills", "a skill's description", "characters"): _descriptions,
    ("claude-code", "a skill's or command's description, with its `when_to_use`, in the skill listing", "characters"): _descriptions,
    ("claude-code", "an MCP server's instructions", "characters"): lambda: {"mcp_server.INSTRUCTIONS": len(mcp_server.INSTRUCTIONS)},
    ("claude-code", "a CLAUDE.md file", "bytes"): _instruction_files,
    ("codex", "all the AGENTS.md files together", "bytes"): lambda: {"AGENTS.md": _instruction_files()["AGENTS.md"]},
    ("copilot", "a custom agent's prompt", "characters"): _role_prompts,
    ("antigravity", "one rule file, such as AGENTS.md", "bytes"): _instruction_files,
    ("kiro", "a skill's name", "characters"): _skill_names,
    ("kiro", "a skill's description", "characters"): _descriptions,
    ("vibe", "a skill's description", "characters"): _descriptions,
}
# Rows no test fails on, each with its reason: the listing is a report, and the rest are vendor advice.
REPORTED = {
    ("claude-code", "the descriptions of all skills in the skill listing, at a 200,000-token context window", "characters"),
    ("codex", "the descriptions of all skills in the skill list", "characters"),
}


def key(size) -> tuple[str, str, str]:
    return size.harness, size.what, size.unit


class TheRowsAreFacts(unittest.TestCase):
    def test_each_row_names_a_harness_a_page_a_date_and_what_the_page_says_happens(self):
        seen = set()
        for size in config.SIZES:
            with self.subTest(size=key(size)):
                self.assertIn(size.harness, {*config.HARNESSES, "agent-skills"})
                self.assertRegex(size.source, r"^https://\S+$")
                self.assertLessEqual(dt.date.fromisoformat(size.read), dt.date.today())
                self.assertIn(size.past, PAST)
                self.assertIn(size.unit, UNITS)
                self.assertGreater(size.number, 0)
                self.assertNotIn(key(size), seen, "a harness's size is stated once")
                seen.add(key(size))

    def test_a_row_whose_page_gives_no_effect_never_claims_one(self):
        for size in config.SIZES:
            if size.past == "not stated":
                with self.subTest(size=key(size)):
                    self.assertNotRegex(size.note, r"\bcuts?\b|truncat|rejects?|refuses?")

    def test_the_two_sizes_the_report_asked_to_hold_are_here_with_their_pages(self):
        by = {key(s): s for s in config.SIZES}
        self.assertEqual(by[("claude-code", "an MCP server's instructions", "characters")].number, 4096)
        self.assertEqual(by[("claude-code", "an MCP server's instructions", "characters")].past, "cut")
        self.assertEqual(by[("agent-skills", "a skill's description", "characters")].number, 1024)
        # The page says `max 1024 chars`, not that Kiro cuts at it.
        self.assertEqual(by[("kiro", "a skill's description", "characters")].past, "not stated")


class TheTextAiddWritesKeepsToEachLimit(unittest.TestCase):
    def test_every_row_is_held_by_a_measure_reported_or_guidance(self):
        for size in config.SIZES:
            with self.subTest(size=key(size)):
                self.assertTrue(size.past == "guidance" or key(size) in MEASURED or key(size) in REPORTED, "a limit of a coding agent has a test or a report")
        self.assertEqual(set(MEASURED) | REPORTED, {key(s) for s in config.SIZES if s.past != "guidance"})

    def test_each_text_of_aidd_is_within_each_documented_maximum(self):
        for size in config.SIZES:
            if key(size) not in MEASURED:
                continue
            for name, measured in MEASURED[key(size)]().items():
                with self.subTest(size=key(size), text=name):
                    self.assertEqual(budgets.past_a_harness_limit(name, measured, size), "")

    def test_a_text_at_the_limit_passes_and_one_unit_past_it_fails_with_the_next_step(self):
        for size in config.SIZES:
            with self.subTest(size=key(size)):
                self.assertEqual(budgets.past_a_harness_limit("a text", size.number, size), "")
                message = budgets.past_a_harness_limit("a text", size.number + 1, size)
                self.assertIn(size.source, message)
                self.assertIn(size.read, message)
                self.assertIn("say less", message)

    def test_the_doctors_page_length_is_the_vendors_guidance_for_a_claude_md(self):
        (lines,) = (s for s in config.SIZES if s.harness == "claude-code" and s.what == "a CLAUDE.md file" and s.unit == "lines")
        self.assertEqual(lines.past, "guidance")
        self.assertEqual(doctor_checks.INSTRUCTION_MAX_LINES, lines.number)
        (cut,) = (s for s in config.SIZES if s.harness == "antigravity")
        self.assertLess(doctor_checks.INSTRUCTION_MAX_BYTES, cut.number)

    def test_the_skill_body_is_under_the_agent_skills_line_guidance(self):
        # Guidance, so the text still loads past it; aidd's skill keeps well under it.
        (limit,) = (s for s in config.SIZES if s.harness == "agent-skills" and s.what == "a skill's body")
        lines = len((SKILLS / "aidd" / "SKILL.md").read_text(encoding="utf-8").splitlines())
        self.assertLess(lines, limit.number)


class TheListingOfDescriptionsIsReportedNotFailed(unittest.TestCase):
    def test_the_note_gives_the_total_the_budget_and_what_is_dropped_when_it_is_over(self):
        over = config.listing_note(13416, "The aidd-team plugin lists", "Do this.", by_name=4216)
        self.assertIn("13,416 characters", over)
        self.assertIn("8,000 characters at 200,000 tokens", over)
        self.assertIn("5,416 over", over)
        self.assertIn("4,216 of the characters belong to skills a role or the lead loads by name", over)
        self.assertIn("the other 9,200 belong to skills a model finds from the description", over)
        self.assertIn("drops the descriptions of the least-used skills", over)
        self.assertTrue(over.endswith("Do this."))

    def test_the_note_at_the_budget_fits_and_one_character_past_it_is_over(self):
        self.assertIn("That fits at 200,000 tokens.", config.listing_note(8000, "x", "Do this."))
        self.assertNotIn("Do this.", config.listing_note(8000, "x", "Do this."))
        self.assertIn("1 over", config.listing_note(8001, "x", "Do this."))

    def test_the_team_with_every_pack_is_over_the_budget_at_200k_and_no_test_fails_on_it(self):
        total = sum(d["chars"] for d in pack_budget.pack_descriptions() if d["listed"])
        self.assertGreater(total, config.listing_budget().number, "if every pack fits too, the report can say it fits, and the packs plugin needs no care")

    def test_doctor_reports_the_descriptions_of_the_team_files_it_finds_and_is_quiet_without_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(doctor_listing.listing_lines(root), [])
            for rel, text in team_install.team_files(["claude-code"], True).items():
                if doctor_listing.LISTED.match(rel):
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text, encoding="utf-8")
            helpers.git(root, "init", "-q")
            ((level, line),) = doctor_listing.listing_lines(root)
            self.assertEqual(level, "")
            self.assertRegex(line, r"^The team files here list [\d,]+ characters of skill descriptions\.")

    def test_with_the_plugin_on_doctor_counts_every_description_the_plugin_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {f"aidd-team@{config.MARKETPLACE}": True}}), encoding="utf-8")
            ((level, line),) = doctor_listing.listing_lines(root)
        listed = pack_budget.pack_descriptions()
        plugin = sum(d["chars"] for d in listed if d["plugin"] == "aidd-team" and d["listed"])  # the aidd skill is the other plugin's
        self.assertEqual(level, "")
        self.assertTrue(line.startswith(f"The aidd-team plugin lists {plugin:,} characters of skill descriptions."), line[:120])
        self.assertIn("That fits at 200,000 tokens.", line)

    def test_with_the_packs_plugin_on_too_doctor_adds_the_packs_and_says_they_are_found_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"enabledPlugins": {f"aidd-team@{config.MARKETPLACE}": True, f"{config.PACKS_PLUGIN}@{config.MARKETPLACE}": True}}), encoding="utf-8"
            )
            ((level, line),) = doctor_listing.listing_lines(root)
        listed = [d for d in pack_budget.pack_descriptions() if d["plugin"] != "aidd" and d["listed"]]
        self.assertTrue(
            line.startswith(f"The aidd-team and aidd-packs plugins list {sum(d['chars'] for d in listed):,} characters of skill descriptions."), line[:120]
        )
        by_name = sum(d["chars"] for d in listed if d["found"] == "name")
        self.assertIn(f"{by_name:,} of the characters belong to skills a role or the lead loads by name", line)

    def test_a_description_is_read_from_the_front_matter_and_an_unreadable_one_is_empty(self):
        self.assertEqual(doctor_listing.description("---\nname: x\ndescription: Use it when y.\n---\nBody\n"), "Use it when y.")
        for bad in ("no front matter", "---\nname: x\n---\nBody", "---\ndescription: [a\n---\n"):
            self.assertEqual(doctor_listing.description(bad), "", bad)
        self.assertTrue(doctor_listing.LISTED.match(".claude/skills/aidd-x/SKILL.md"))
        self.assertIsNone(doctor_listing.LISTED.match(".claude/skills/aidd-x/references/a.md"))


NEXT_STEP = (
    "say less in a description that is too long for what it triggers, or move a skill that no model finds alone, such as a domain, to the "
    "aidd-packs plugin, which a person adds where a project calls for a pack"
)


def _preloaded() -> set[str]:
    """Every skill an agent file of the team preloads (`skills:` in its front matter), by its folder name, but the aidd skill."""
    names: set[str] = set()
    for path in (TEAM / "agents").glob("*.md"):
        front = documents.split_front_matter(path.read_text(encoding="utf-8"))[0]
        names |= {str(s).partition(":")[2] for s in front.get("skills", []) if str(s).startswith("aidd-team:")}
    return names


class TheDefaultPluginsListWhatAModelMustFindAlone(unittest.TestCase):
    """Claude Code lists every skill's name and, within a budget its window sets, every description. A skill a model finds alone needs
    its description there. A skill a role or the lead names does not, but no setting keeps one both loadable by a model and out of the
    listing (`config.LISTING_FACTS`): a domain pack is a skill of the aidd-packs plugin, which a person adds."""

    def listed(self, plugins: tuple[str, ...] = ("aidd", "aidd-team")) -> list[dict]:
        return [d for d in pack_budget.pack_descriptions() if d["listed"] and d["plugin"] in plugins]

    def test_the_listed_descriptions_of_the_aidd_and_aidd_team_plugins_fit_the_budget_of_the_smallest_window(self):
        total = sum(d["chars"] for d in self.listed())
        self.assertEqual(budgets.past_a_harness_limit("the descriptions the aidd and aidd-team plugins list", total, config.listing_budget()), "", NEXT_STEP)

    def test_one_character_past_the_budget_fails_with_the_next_step(self):
        budget = config.listing_budget()
        total = sum(d["chars"] for d in self.listed())
        self.assertEqual(budgets.past_a_harness_limit("x", budget.number, budget), "")
        past = budgets.past_a_harness_limit("x", budget.number + 1, budget)
        self.assertIn("say less", past)
        self.assertIn(budget.source, past)
        self.assertLessEqual(total, budget.number)

    def test_every_pack_is_a_skill_of_the_packs_plugin_that_a_role_or_the_lead_names(self):
        by_slug = {d["slug"] for d in knowledge.roles()["domains"]}
        rows = {d["name"]: d for d in pack_budget.pack_descriptions() if d["name"] in by_slug}
        self.assertEqual(set(rows), by_slug)
        for name, row in rows.items():
            with self.subTest(name):
                self.assertEqual((row["plugin"], row["found"], row["listed"]), (config.PACKS_PLUGIN, "name", True))
                self.assertFalse((TEAM / "skills" / name).exists(), "the aidd-team plugin carries no pack")

    def test_a_skill_is_found_by_name_when_a_role_preloads_it_or_a_file_names_it_and_else_by_description(self):
        data = knowledge.roles()
        preloaded = {p for r in data["roles"].values() for p in r.get("preload", [])} - {"aidd"}
        named_for_files = {p for f in data["graph"]["file_skills"] for p in f["skills"]}
        cases = [(slug, "name") for slug in sorted(preloaded | named_for_files)]
        cases += [(d["slug"], "name") for d in data["domains"]]
        cases += [(p, "description") for p in sorted(set(data["skills"]) - preloaded - named_for_files)]
        cases += [("aidd-team", "description"), ("aidd", "description"), ("a-skill-no-registry-names", "description")]
        self.assertGreater(len(preloaded) + len(named_for_files), 10)
        for slug, found in cases:
            with self.subTest(slug):
                self.assertEqual(knowledge.found_by(slug), found)

    def test_a_skill_an_agent_file_preloads_stays_listed_since_a_preload_needs_the_model_to_be_able_to_load_it(self):
        self.assertTrue(_preloaded(), "the agent files preload practice skills")
        listed = {d["name"] for d in self.listed()}
        for name in sorted(_preloaded()):
            with self.subTest(name):
                self.assertIn(name, listed)
                self.assertTrue(knowledge.lists_description((TEAM / "skills" / name / "SKILL.md").read_text(encoding="utf-8")))

    def test_a_command_is_run_by_a_person_so_its_description_stays_out_of_the_listing(self):
        for path in sorted((TEAM / "commands").glob("*.md")):
            with self.subTest(path.stem):
                self.assertFalse(knowledge.lists_description(path.read_text(encoding="utf-8")))
        rows = [d for d in pack_budget.pack_descriptions() if d["type"] == "command"]
        self.assertEqual({d["name"] for d in rows}, {p.stem for p in (TEAM / "commands").glob("*.md")})
        self.assertEqual({(d["listed"], d["found"]) for d in rows}, {(False, "person")})

    def test_a_front_matter_lists_its_description_unless_it_sets_model_invocation_off(self):
        cases = [
            ("---\nname: x\ndescription: d\n---\n", True),
            ("---\nname: x\ndescription: d\ndisable-model-invocation: true\n---\n", False),
            ("---\nname: x\ndescription: d\ndisable-model-invocation: false\n---\n", True),
            ('---\nname: x\ndescription: d\nargument-hint: "<x>"\ndisable-model-invocation: true\n---\nBody\n', False),
            ("no front matter", True),
            ("---\ndescription: [a\n---\n", True),
            ("", True),
        ]
        for text, listed in cases:
            with self.subTest(text=text[:50]):
                self.assertEqual(knowledge.lists_description(text), listed)

    def test_the_name_aidd_gives_a_skill_is_the_name_its_plugin_gives_it(self):
        """A role loads a skill with the Skill tool by its plugin's name and its folder (`aidd-packs:health`), so the name `aidd risk`
        and the lead say is, for every skill of both plugins, `<plugin.json name>:<folder>`. Only a live session shows the call itself."""
        for plugin in ("aidd-team", "aidd-packs"):
            name = json.loads((ROOT / "plugins" / plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]
            folders = sorted(p.parent for p in (ROOT / "plugins" / plugin / "skills").glob("*/SKILL.md"))
            self.assertGreater(len(folders), 20)
            for folder in folders:
                with self.subTest(plugin=plugin, skill=folder.name):
                    self.assertEqual(knowledge.skill_ref(folder.name), f"{name}:{folder.name}")
                    front = documents.split_front_matter((folder / "SKILL.md").read_text(encoding="utf-8"))[0]
                    self.assertEqual(front["name"], folder.name)
                    self.assertNotIn("disable-model-invocation", front, "a skill a model loads by name must be one it may load")
                    for val in (front.get("metadata") or {}).values():
                        self.assertIsInstance(val, str)

    def test_each_listing_fact_names_a_harness_a_page_what_it_says_and_the_date_aidd_read_it(self):
        self.assertGreaterEqual(len(config.LISTING_FACTS), 5)
        for fact in config.LISTING_FACTS:
            with self.subTest(fact=fact.what):
                self.assertIn(fact.harness, config.HARNESSES)
                self.assertRegex(fact.source, r"^https://\S+$")
                self.assertLessEqual(dt.date.fromisoformat(fact.read), dt.date.today())
                self.assertTrue(fact.what and fact.says)


if __name__ == "__main__":
    unittest.main()
