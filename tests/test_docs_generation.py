"""The doc generator: tables follow $ref, an empty generated table is an error, and the CLI, environment,
config, and count blocks are derived from the code and data they describe."""

import argparse
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, package_source, source_of

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
        # rule_exclusions is an object with no fixed properties, so its table has only a header.
        with mock.patch.dict(schema_tables.FIELD_SCHEMAS, {"no-rows": ("config.schema.json", ["properties", "rule_exclusions"])}):
            with self.assertRaisesRegex(ValueError, "no rows"):
                generate.regenerate("<!-- aidd:gen fields:no-rows -->\n<!-- aidd:end -->\n")

    def test_gen_docs_check_fails_on_an_empty_generated_table(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch.dict(schema_tables.FIELD_SCHEMAS, {"no-rows": ("config.schema.json", ["properties", "rule_exclusions"])}),
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
        self.assertRegex(table, r"\| `validate` `\[paths \.\.\.\]` \|")
        # `aidd new` also writes the documents a Spec links, which take a topic and no title, the repository's own
        # documents, which take no id, a proposal's contract, and an exploration.
        self.assertIn(
            "`new` `spec\\|epic\\|initiative\\|proposal\\|runbook\\|postmortem\\|tech-spec\\|test-plan\\|adr\\|threat-model\\|authz\\|design-spec\\|api\\|slo\\|compliance\\|analytics\\|migration\\|acceptance\\|feedback\\|design-system\\|architecture\\|data-map\\|vendors\\|glossary\\|agents\\|contract\\|exploration` `[id]`",
            table,
        )

    def test_a_flag_whose_value_is_optional_shows_it_in_brackets(self):
        parser = argparse.ArgumentParser()
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--explain", nargs="?", metavar="RULE")), "`--explain [RULE]`")
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--format", nargs="?", choices=["a", "b"])), "`--format [a\\|b]`")
        self.assertEqual(cli_reference._arg_text(parser.add_argument("--title")), "`--title TITLE`")

    def test_cli_md_holds_the_generated_table(self):
        text = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen cli:commands -->\n" + cli_reference.cli_table(cli_parser.cli_facts()) + "\n<!-- aidd:end -->", text)


class EnvTableTests(unittest.TestCase):
    def test_every_aidd_variable_the_code_names_is_documented(self):
        named = set()
        for path in (ROOT / "src" / "aidd").rglob("*.py"):
            if path.resolve() == Path(counts.__file__).resolve():  # the table itself names them
                continue
            named |= set(re.findall(r"\b(AIDD_[A-Z_]+[A-Z])\b", path.read_text(encoding="utf-8")))
        from aidd.kernel.processes import SECRET_ENV

        documented = {name for name, _, _ in counts.ENV_VARS} | set(SECRET_ENV)
        self.assertEqual(sorted(named - documented), [])

    def test_the_policy_and_observe_variables_are_the_ones_the_code_sets(self):
        policy = source_of("aidd.gate.policy")
        observe = package_source("aidd.cli")
        for name, who, _ in counts.ENV_VARS:
            if "Policy command" in who:
                self.assertIn(f'"{name}"', policy, name)
            if "Observe command" in who:
                self.assertIn(f'"{name}"', observe, name)


class ConfigReferenceTests(unittest.TestCase):
    def test_config_md_covers_every_top_level_key(self):
        text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen fields:config -->", text)
        schema = resources.load_json("config.schema.json")
        for key, prop in schema["properties"].items():
            self.assertIn(f"`{key}`", text, key)
            if prop.get("type") == "object" and prop.get("properties"):
                self.assertIn(f"<!-- aidd:gen fields:config-{key} -->", text, key)


class CountTests(unittest.TestCase):
    def test_counts_come_from_the_data(self):
        self.assertEqual(counts.count("roles"), len(team_registry.roles()["order"]))
        self.assertEqual(counts.count("mutations"), len(list((ROOT / "examples").glob("*/mutations/*.json"))))
        with self.assertRaises(KeyError):
            counts.count("nothing")

    def test_an_inline_count_is_regenerated_in_place(self):
        text = "We ship <!-- aidd:gen count:roles -->99<!-- aidd:end --> roles.\n"
        self.assertEqual(generate.regenerate(text), f"We ship <!-- aidd:gen count:roles -->{counts.count('roles')}<!-- aidd:end --> roles.\n")

    def test_an_inline_list_of_team_commands_names_every_flow(self):
        text = "Commands: <!-- aidd:gen list:team-commands -->old<!-- aidd:end -->.\n"
        out = generate.regenerate(text)
        commands = [f["command"] for f in team_registry.roles()["loop"]["flows"]]
        self.assertIn(f"`/aidd-team:{commands[0]}`", out)
        for command in commands[1:]:
            self.assertIn(f"`{command}`", out)
        self.assertNotIn("old", out)
        team = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        plugin_row = next(ln for ln in team.splitlines() if ln.startswith("| Claude Code, plugin |"))
        self.assertIn(f"<!-- aidd:gen list:team-commands -->{generate.render('list:team-commands')}<!-- aidd:end -->", plugin_row)

    def test_the_readme_team_table_names_every_team_command_once(self):
        # The README groups the commands by the job a person has; the grouping is written by hand, so this keeps it whole.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("\n## The delivery team\n", 1)[1].split("\n## ", 1)[0]
        rows = [ln.split(" | ", 1)[1] for ln in section.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
        named = re.findall(r"`([a-z-]+)`", " ".join(rows))
        self.assertEqual(sorted(named), sorted(team_reference.team_commands()))

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
        fake["loop"]["contract"] = ["Everyone.", "Builders only.", "Review only."]
        fake["loop"]["contract_applies_to"] = [None, ["developer"], ["Review"]]
        return fake

    def test_a_scoped_rule_renders_only_where_it_applies(self):
        fake = self.fake_roles()
        self.assertEqual(team_registry.contract_for("developer", fake), ["Everyone.", "Builders only."])
        self.assertEqual(team_registry.contract_for("reviewer", fake), ["Everyone.", "Review only."])
        with mock.patch.object(team_registry, "roles", return_value=fake):
            block = generate.render("role:developer")
            self.assertIn("  1. Everyone.\n  2. Builders only.\n", block)
            self.assertNotIn("Review only.", block)
            loop = generate.render("roles:loop")
            self.assertIn("2. Builders only. *(applies to: developer)*", loop)
            self.assertIn("1. Everyone.\n", loop)

    def test_the_extensions_table_carries_the_tier_and_the_role_block_none(self):
        # An extension is used only when the project already has it, so the list lives in the reference only.
        block = generate.render("role:developer")
        self.assertNotIn("Superpowers", block)
        self.assertNotIn("CodeGraph", block)
        table = generate.render("roles:extends")
        self.assertIn("| Role | Extension | Kind | Tier | Can | Adds | Source | License | Pin |", table)
        self.assertIn("| `developer` | CodeGraph | mcp, emerging | community |", table)


class MermaidTests(unittest.TestCase):
    """Every generated diagram names its nodes with single-word ids: Mermaid ends an id at a space, and GitHub then renders
    nothing but an error. CI also parses every Mermaid block with Mermaid itself (tools/mermaid/check-mermaid.mjs)."""

    NODE = re.compile(r"^\s+([^\s\[\{\(]+)\s*[\[\{\(]")
    ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_every_fill_sets_its_text_color(self):
        """GitHub draws a diagram in the viewer's light or dark theme; a fill without a text color puts light text on a
        light fill in dark mode. Every fill in the repository's diagrams sets `color` too."""
        import subprocess

        for rel in subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.split():
            for block in re.findall(r"```mermaid\n(.*?)```", (ROOT / rel).read_text(encoding="utf-8"), re.S):
                for line in block.splitlines():
                    if "fill:" in line:
                        self.assertIn("color:", line, f"{rel}: {line.strip()}")

    def test_node_and_style_ids_are_single_words(self):
        for key in ("roles:loop:diagram", "roles:flows:diagram", "roles:handoffs:diagram"):
            for line in generate.render(key).splitlines():
                if line.lstrip().startswith("style "):
                    self.assertRegex(line, r"^\s+style [A-Za-z_][A-Za-z0-9_]* (fill|stroke|color):", f"{key}: {line}")
                elif "-->" not in line and "-." not in line and (m := self.NODE.match(line)):
                    self.assertRegex(m.group(1), self.ID, f"{key}: {line}")


if __name__ == "__main__":
    unittest.main()
