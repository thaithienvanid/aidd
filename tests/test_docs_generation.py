"""The doc generator: tables follow $ref, an empty generated table is an error, and the CLI, environment,
config, and count blocks are derived from the code and data they describe."""

import argparse
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import config
from aidd.cli import parser as cli_parser
from aidd.docsgen import generate
from aidd.docsgen import cli_reference
from aidd.docsgen import counts
from aidd.docsgen import schema_tables
from aidd.docsgen import team_reference
from aidd.docsgen import blocks
from aidd.kernel import resources
from aidd.knowledge import team_registry


class FieldsTableTests(unittest.TestCase):
    def test_a_table_whose_node_is_a_ref_lists_the_referenced_fields(self):
        # config.extends.items is {"$ref": "#/$defs/extends"}; the table was empty before $ref was followed.
        table = schema_tables.fields_table("config-extends")
        for field in ("path", "url", "sha256"):
            self.assertIn(f"| `{field}` |", table)
        self.assertEqual(generate.empty_tables(table), 0)

    def test_every_fields_block_has_rows(self):
        for key in schema_tables.FIELD_SCHEMAS:
            with self.subTest(key=key):
                self.assertEqual(generate.empty_tables(schema_tables.fields_table(key)), 0)


class EmptyTableTests(unittest.TestCase):
    def test_empty_tables_counts_header_only_tables(self):
        self.assertEqual(generate.empty_tables("| a |\n| --- |\n"), 1)
        self.assertEqual(generate.empty_tables("| a |\n| --- |\n| 1 |\n"), 0)
        self.assertEqual(generate.empty_tables("| a |\n| --- |\n\ntext\n\n| b |\n| --- |\n| 2 |"), 1)
        self.assertEqual(generate.empty_tables("no table here"), 0)

    def test_a_block_that_renders_an_empty_table_fails_regeneration(self):
        # agents.models is an object with no fixed properties, so its table has only a header.
        with mock.patch.dict(schema_tables.FIELD_SCHEMAS, {"no-rows": ("config.schema.json", ["properties", "agents", "properties", "models"])}):
            with self.assertRaisesRegex(ValueError, "no rows"):
                generate.regenerate("<!-- aidd:gen fields:no-rows -->\n<!-- aidd:end -->\n")

    def test_gen_docs_check_fails_on_an_empty_generated_table(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch.dict(schema_tables.FIELD_SCHEMAS, {"no-rows": ("config.schema.json", ["properties", "agents", "properties", "models"])}),
        ):
            (Path(d) / "X.md").write_text("<!-- aidd:gen fields:no-rows -->\n| Field |\n| --- |\n<!-- aidd:end -->\n", encoding="utf-8")
            with mock.patch.object(team_registry, "roles", return_value={"domains": [], "order": [], "roles": {}}):
                with self.assertRaises(ValueError):
                    generate.gen_docs(Path(d), check=True)


class CliTableTests(unittest.TestCase):
    def test_every_command_and_flag_of_the_parser_is_in_the_table(self):
        table = cli_reference.cli_table(cli_parser.cli_facts())
        for name, sub in cli_reference._subcommands(cli_parser.cli_facts()).items():
            self.assertIn(f"| `{name}`", table)
            for action in sub._actions:
                for flag in action.option_strings:
                    if flag.startswith("--") and flag != "--help" and action.help != argparse.SUPPRESS:
                        self.assertIn(f"`{flag}", table, f"{name} {flag}")
                    elif action.help == argparse.SUPPRESS:  # an old spelling, kept for one release: in no table
                        self.assertNotIn(f"`{flag}`", table, f"{name} {flag}")

    def test_required_and_positional_arguments_are_marked(self):
        table = cli_reference.cli_table(cli_parser.cli_facts())
        # No listed command has a required flag since `aidd new --title` became optional for linked docs.
        import argparse

        self.assertEqual(cli_reference._arg_text(argparse.ArgumentParser().add_argument("--title", required=True)), "`--title TITLE` (required)")
        self.assertRegex(table, r"\| `validate` `\[PATH \.\.\.\]` \|")
        # `aidd new` writes the work items and the documents a Spec links, each by its type, and takes an optional id.
        new_row = next(line for line in table.splitlines() if line.startswith("| `new` "))
        cell = new_row.split(" | ")[0]
        types = re.search(r"`new` `([^`]+)`", cell).group(1).split("\\|")
        for item_type in ("spec", "intent", "proposal", "exploration", "product-prototype", "tech-spec", "threat-model", "runbook"):
            self.assertIn(item_type, types)
        self.assertTrue(cell.endswith("`[id]`"), cell)

    def test_a_flag_whose_value_is_optional_shows_it_in_brackets(self):
        parser = argparse.ArgumentParser()
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--explain", nargs="?", metavar="RULE")), "`--explain [RULE]`")
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--format", nargs="?", choices=["a", "b"])), "`--format [a\\|b]`")
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--title")), "`--title TITLE`")

    def test_cli_md_holds_the_generated_table(self):
        text = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen cli:commands -->\n" + cli_reference.cli_table(cli_parser.cli_facts()) + "\n<!-- aidd:end -->", text)

    def test_one_generated_list_names_every_mcp_tool(self):
        """The MCP tools are listed once, from the tools `aidd mcp` serves; no page names a hand-typed subset of them."""
        from aidd.cli import mcp_tools

        names = [tool["name"] for tool in mcp_tools.TOOLS]
        listed = generate.render("mcp:tools", cli_parser.cli_facts())
        self.assertEqual(re.findall(r"`([a-z_]+)`", listed), names)
        text = (ROOT / "docs" / "architecture" / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"<!-- aidd:gen mcp:tools -->{listed}<!-- aidd:end -->", text)
        mcp_row = next(line for line in cli_reference.cli_table(cli_parser.cli_facts()).splitlines() if line.startswith("| `mcp` |"))
        self.assertFalse([n for n in names if "_" in n and n in mcp_row], mcp_row)  # `gate` and `validate` are words too


class ConfigReferenceTests(unittest.TestCase):
    def test_config_md_covers_every_top_level_key(self):
        text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen fields:config -->", text)
        schema = resources.load_json("config.schema.json")
        for key, prop in schema["properties"].items():
            self.assertIn(f"`{key}`", text, key)
            if prop.get("type") == "object" and prop.get("properties"):
                self.assertIn(f"<!-- aidd:gen fields:config-{key} -->", text, key)


class RiskAreasTableTests(unittest.TestCase):
    def test_the_short_table_lists_every_area_of_the_full_table_without_its_paths(self):
        full = generate.render("risks:areas").splitlines()
        short = generate.render("risks:areas:short").splitlines()
        self.assertEqual(len(short), len(full))
        self.assertTrue(full[0].endswith("| Paths, such as |"))
        self.assertNotIn("Paths", short[0])
        for f, s in zip(full[2:], short[2:], strict=True):
            self.assertTrue(f.startswith(s[:-2]), s)


class CountTests(unittest.TestCase):
    def test_counts_come_from_the_data(self):
        self.assertEqual(counts.count("roles"), len(team_registry.roles()["order"]))
        with self.assertRaises(KeyError):
            counts.count("nothing")

    def test_an_inline_count_is_regenerated_in_place(self):
        text = "We ship <!-- aidd:gen count:roles -->99<!-- aidd:end --> roles.\n"
        self.assertEqual(generate.regenerate(text), f"We ship <!-- aidd:gen count:roles -->{counts.count('roles')}<!-- aidd:end --> roles.\n")

    def test_an_inline_list_of_team_commands_names_every_flow(self):
        text = "Commands: <!-- aidd:gen list:team-commands -->old<!-- aidd:end -->.\n"
        out = generate.regenerate(text)
        commands = [f["command"] for f in team_registry.roles()["graph"]["flows"]]
        self.assertIn(f"`/aidd-team:{commands[0]}`", out)
        for command in commands[1:]:
            self.assertIn(f"`{command}`", out)
        self.assertNotIn("old", out)
        team = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        plugin_row = next(ln for ln in team.splitlines() if ln.startswith("| Claude Code, plugin |"))
        self.assertIn(f"<!-- aidd:gen list:team-commands -->{generate.render('list:team-commands')}<!-- aidd:end -->", plugin_row)

    def test_the_agents_with_ask_rules_and_those_without_are_exactly_the_supported_agents(self):
        every = {h.label for h in config.HARNESSES.values()}
        named = {}
        for part in ("ask-rule-harnesses", "no-ask-rule-harnesses"):
            named[part] = set(re.split(r", and |, | and ", generate.render(f"list:{part}")))
        self.assertEqual(named["ask-rule-harnesses"] & named["no-ask-rule-harnesses"], set())
        self.assertEqual(named["ask-rule-harnesses"] | named["no-ask-rule-harnesses"], every)
        self.assertEqual(counts.count("ask-rule-harnesses") + counts.count("no-ask-rule-harnesses"), counts.count("harnesses"))
        method = (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8")
        self.assertIn(f"<!-- aidd:gen list:no-ask-rule-harnesses -->{generate.render('list:no-ask-rule-harnesses')}<!-- aidd:end -->", method)

    def test_the_readme_names_only_real_team_commands_and_its_team_section_links_the_team_page(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("\n## The development team\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("(docs/TEAM.md)", section)
        named = re.findall(r"`/aidd-team:([a-z-]+)`", readme)
        self.assertTrue(named)
        self.assertLessEqual(set(named), set(team_reference.team_commands()))

    def test_prose_states_no_hand_typed_count_of_generated_facts(self):
        pattern = re.compile(
            r"\b(\d+|fourteen|thirteen|sixteen|twenty-six) (coding agents|agent roles|domain packs|practice skills|mutations|tampered variants)\b", re.I
        )
        for path in [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "llms.txt", *sorted((ROOT / "docs").glob("*.md"))]:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = blocks.INLINE.sub("", line)
                self.assertIsNone(pattern.search(stripped), f"{path.relative_to(ROOT)}: {line[:100]}")


class RoleBlockTests(unittest.TestCase):
    """The generated role block: the contract rules that bind the role, each edition once, and each extension's tier."""

    def fake_roles(self):
        data = team_registry.roles()
        fake = json.loads(json.dumps(data))
        fake["graph"]["contract"] = ["Everyone.", "Builders only.", "Review only."]
        fake["graph"]["contract_applies_to"] = [None, ["developer"], ["Review"]]
        fake["graph"]["contract_needs"] = [None, None, None]
        fake["graph"]["contract_in_core_skill"] = [None, None, None]
        fake["graph"]["contract_reviewed_as"] = [None, None, None]
        return fake

    def test_a_scoped_rule_renders_only_where_it_applies(self):
        fake = self.fake_roles()
        self.assertEqual(team_registry.contract_for("developer", fake), ["Everyone.", "Builders only."])
        self.assertEqual(team_registry.contract_for("reviewer", fake), ["Everyone.", "Review only."])
        with mock.patch.object(team_registry, "roles", return_value=fake):
            block = generate.render("role:developer")
            self.assertIn("  1. Everyone.\n  2. Builders only.\n", block)
            self.assertNotIn("Review only.", block)
            loop = generate.render("roles:graph")
            self.assertIn("2. Builders only. *(applies to: developer)*", loop)
            self.assertIn("1. Everyone.\n", loop)

    def test_a_rule_a_role_checks_shows_its_own_text_and_the_verdict_in_that_roles_block_only(self):
        fake = self.fake_roles()
        fake["graph"]["contract"] = ["Everyone.", "Builders keep this rule.", "Builders keep another rule."]
        fake["graph"]["contract_applies_to"] = [None, ["developer"], ["developer"]]
        fake["graph"]["contract_needs"] = [None, None, None]
        fake["graph"]["contract_in_core_skill"] = [None, None, None]
        fake["graph"]["contract_reviewed_as"] = [None, {"roles": ["reviewer"], "as": "A new part breaks it: a finding."}, None]
        self.assertEqual(team_registry.reviewed_rules_for("reviewer", fake), [("Builders keep this rule.", "A new part breaks it: a finding.")])
        self.assertEqual(team_registry.reviewed_rules_for("developer", fake), [])
        with mock.patch.object(team_registry, "roles", return_value=fake):
            reviewer = generate.render("role:reviewer")
            self.assertIn("Builders keep this rule.\n     *You apply it so:* A new part breaks it: a finding.", reviewer)
            self.assertNotIn("Builders keep another rule.", reviewer)
            self.assertNotIn("A new part breaks it", generate.render("role:developer"))
            fake["graph"]["contract_reviewed_as"] = [None, None, None]
            self.assertNotIn("Rules the authors keep", generate.render("role:reviewer"))

    def test_the_extensions_table_carries_the_publisher_and_the_role_block_none(self):
        # An extension is used only when the project already has it, so the list lives in the reference only.
        block = generate.render("role:developer")
        self.assertNotIn("Superpowers", block)
        self.assertNotIn("CodeGraph", block)
        table = generate.render("roles:extensions")
        self.assertIn("| Role | Extension | Type | Publisher | Access | Adds | Source | License | Pin |", table)
        self.assertIn("| `developer` | CodeGraph | mcp, emerging | community |", table)


class StagesOutlineTests(unittest.TestCase):
    def test_the_outline_names_every_stage_step_and_gate_of_the_loop_once_in_order(self):
        loop = resources.load_json("roles.json")["graph"]
        out = generate.render("roles:stages:outline")
        self.assertEqual([line.split()[0] for line in out.splitlines()[1:-1]], [s["name"] for s in loop["stages"]])
        for word in [*(g["name"] for g in loop["gates"]), *(a for g in loop["gates"] for a in g["actions"])]:
            with self.subTest(word=word):
                self.assertEqual(out.count(word), 1)
        steps = re.sub(r"\[gate[^\]]*\]", "", out)
        positions = [steps.index(step) for step in loop["steps"]]
        self.assertEqual(positions, sorted(positions))

    def test_a_gate_stands_before_the_step_it_names(self):
        out = generate.render("roles:stages:outline")
        self.assertIn("Merge → [gate: Production release, deploy.run] → Roll out", out)
        self.assertRegex(out, r"Verify, Review → \[gate: Merge approval, pr\.merge or git\.merge\]\n")


class MermaidTests(unittest.TestCase):
    """Every generated diagram names its nodes with single-word ids: Mermaid ends an id at a space, and GitHub then renders
    nothing but an error. CI also parses every Mermaid block with Mermaid itself (tools/mermaid/check-mermaid.mjs)."""

    NODE = re.compile(r"^\s+([^\s\[\{\(]+)\s*[\[\{\(]")
    ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_every_opaque_fill_sets_its_text_color(self):
        """GitHub draws a diagram in the viewer's light or dark theme; an opaque fill without a text color puts light text
        on a light fill in dark mode. So every opaque fill in the repository's diagrams sets `color` too. A tint, a fill
        with an alpha, shows the page through it, so it sets none and the theme's text keeps its color on its own page;
        tests/test_diagram_rules.py measures that text on each tint."""
        import subprocess

        for rel in subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split():
            for block in re.findall(r"```mermaid\n(.*?)```", (ROOT / rel).read_text(encoding="utf-8"), re.S):
                for line in block.splitlines():
                    if re.search(r"fill:#[0-9a-fA-F]{6}(?![0-9a-fA-F])", line):
                        self.assertIn("color:", line, f"{rel}: {line.strip()}")
                    elif re.search(r"fill:#[0-9a-fA-F]{8}\b", line):
                        self.assertNotIn("color:", line, f"{rel}: a tint keeps the theme's text: {line.strip()}")

    def test_node_and_style_ids_are_single_words(self):
        for key in ("roles:graph:diagram", "workitems"):
            for line in generate.render(key).splitlines():
                if line.lstrip().startswith("style "):
                    self.assertRegex(line, r"^\s+style [A-Za-z_][A-Za-z0-9_]* (fill|stroke|color):", f"{key}: {line}")
                elif "-->" not in line and "-." not in line and (m := self.NODE.match(line)):
                    self.assertRegex(m.group(1), self.ID, f"{key}: {line}")


if __name__ == "__main__":
    unittest.main()
