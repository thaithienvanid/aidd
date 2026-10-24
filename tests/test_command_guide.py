"""Which command when: the top-level help lists the everyday commands (`aidd help --all` lists every one, and `aidd
help <command>` one in full), the "Which command when" table and the work-items diagram are generated, every command the parser defines is in
the table, and a doc never names a flag its command does not have."""

import argparse
import contextlib
import io
import json
import re
import unittest

from helpers import ROOT

from aidd.cli import app
from aidd.cli import parser as cli_parser
from aidd.docsgen import generate
from aidd.docsgen import cli_reference
from aidd.docsgen import team_reference
from aidd.docsgen import diagrams

HIDDEN = ("eval", "gen-docs", "mcp", "hook", "hash")


def top_help(*argv: str) -> str:
    """What `aidd <argv>` prints for a help request, which exits 0."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            app.main(list(argv))
    except SystemExit as stop:
        assert stop.code == 0, (argv, stop.code)
    return out.getvalue()


def listed(text: str) -> list[str]:
    """The command names a help page lists: the first word of each two-space-indented row."""
    return [line.split()[0] for line in text.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.split()]


def commands() -> dict:
    return dict(next(a for a in cli_parser.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def schema(name: str) -> dict:
    return json.loads(read(f"schemas/{name}.schema.json"))


EDGE = re.compile(r"\s*(-->|-\.->)(?:\|\"([^\"]*)\"\|)?\s*")


def diagram() -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    """The work-items diagram: each node's label, and each arrow as (from, arrow, label, to)."""
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str, str, str]] = []
    for line in team_reference.WORK_ITEMS[1:]:
        node = re.fullmatch(r"\s+(\w+)(?:\[\"|\{\{\")(.*?)(?:\"\]|\"\}\})", line)
        if node:
            nodes[node.group(1)] = node.group(2)
            continue
        parts = EDGE.split(line.strip())
        for i in range(0, len(parts) - 3, 3):
            edges.append((parts[i], parts[i + 1], parts[i + 2] or "", parts[i + 3]))
    return nodes, edges


class HelpTests(unittest.TestCase):
    def test_the_default_help_lists_the_everyday_commands_of_the_readme_and_where_the_rest_are(self):
        everyday = [re.search(r"`aidd ([\w-]+)", form).group(1) for form in cli_parser.README_FORMS]
        self.assertEqual(list(cli_parser.EVERYDAY_COMMANDS), everyday)  # one list: the README's everyday table
        for argv in (("--help",), ("-h",), ("help",)):
            text = top_help(*argv)
            self.assertEqual(listed(text), everyday, argv)
            self.assertIn("More commands, such as `aidd init`: `aidd help --all`.", text)
            self.assertIn("`aidd help <command>`", text)
            self.assertLessEqual(len(text.splitlines()), 20, argv)
        err = io.StringIO()
        with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(err):
            app.main([])  # no command: the same short help, on stderr, and exit 2
        self.assertEqual(stop.exception.code, 2)
        self.assertEqual(listed(err.getvalue()), everyday)

    def test_help_all_lists_every_command_by_group(self):
        for argv in (("--help", "--all"), ("--all", "--help"), ("-h", "--all"), ("help", "--all")):
            text = top_help(*argv)
            self.assertEqual(sorted(listed(text.split("\noptions:", 1)[0])), sorted(commands()), argv)
            self.assertIn("Maintainers and harnesses:", text, argv)
            section = text.split("Maintainers and harnesses:", 1)[1]
            for name in HIDDEN:
                self.assertIn(name, listed(section), (argv, name))

    def test_help_with_a_command_is_that_commands_help(self):
        self.assertEqual(top_help("help", "gate"), top_help("gate", "--help"))
        self.assertEqual(top_help("help", "record", "verify"), top_help("record", "verify", "--help"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = app.main(["help", "gat"])
        self.assertEqual(code, 2)
        self.assertIn("Did you mean `aidd gate`?", err.getvalue())

    def test_an_abbreviated_top_level_option_is_an_error_not_a_help_without_all(self):
        # `--al` once stood for `--all` to argparse, while the help looked for `--all` itself and hid the commands.
        for argv in (["--al", "--help"], ["--help", "--al"], ["--al", "list"]):
            err = io.StringIO()
            with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                app.main(argv)
            self.assertEqual(stop.exception.code, 2, argv)
            self.assertIn("--al", err.getvalue(), argv)

    def test_a_command_takes_its_options_only_in_full(self):
        # An abbreviation once let `--confirm HEAD` stand for `--confirmed HEAD`, past the guard: no command takes one.
        parser = cli_parser.build_parser()
        self.assertEqual(parser.parse_args(["gate", "--paths", "a.py"]).paths, ["a.py"])
        self.assertEqual(parser.parse_args(["owners", "--changed", "a.py"]).changed, ["a.py"])
        self.assertTrue(parser.parse_args(["gen-docs", "--check"]).check)
        for argv in (["gate", "--pat", "a.py"], ["owners", "--chan", "a.py"], ["gen-docs", "--che"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(argv)

    def test_the_hidden_commands_keep_working(self):
        parser = cli_parser.build_parser()
        for argv in (["eval", "examples"], ["gen-docs", "--check"], ["mcp"], ["hook", "pre-compact"]):
            self.assertEqual(parser.parse_args(argv).func.__name__, "cmd_" + argv[0].replace("-", "_"), argv)
        for name in HIDDEN:
            self.assertIn(f"{name} [-h]", top_help(name, "--help").replace("\n", " "), name)

    def test_cli_md_still_documents_them(self):
        table = cli_reference.cli_table(cli_parser.cli_facts())
        for name in HIDDEN:
            self.assertIn(f"| `{name}`", table, name)
        self.assertIn("`aidd help --all`", read("docs/CLI.md"))


class WhenTableTests(unittest.TestCase):
    def test_every_command_the_parser_defines_is_in_the_table(self):
        table = cli_reference.when_table(cli_parser.cli_facts())
        for name in commands():
            self.assertRegex(table, rf"`aidd {re.escape(name)}\b", name)

    def test_the_everyday_commands_come_first_in_loop_order(self):
        rows = [line for line in cli_reference.when_table(cli_parser.cli_facts()).splitlines() if line.startswith("| ") and "---" not in line][1:]
        everyday = ["aidd gate --paths", "aidd new spec", "aidd approve spec", "aidd test", "aidd gate", "aidd land", "aidd publish", "aidd list"]
        for row, name in zip(rows, everyday, strict=False):
            self.assertIn(f"`{name}", row, name)
        self.assertIn("`aidd approve spec`", rows[2])
        self.assertTrue(rows[0].startswith("| Every day |"), rows[0])
        self.assertTrue(rows[len(everyday)].startswith("| Now and then |"), rows[len(everyday)])
        tail = rows[-len(HIDDEN) :]
        self.assertTrue(tail[0].startswith("| Maintainers and harnesses |"), tail[0])
        self.assertEqual(sorted(re.search(r"`aidd ([\w-]+)", r).group(1) for r in tail), sorted(HIDDEN))

    def test_every_command_has_a_when_phrase(self):
        named = {n for _, names, _ in cli_parser.EVERYDAY for n in names} | set(cli_parser.WHEN)
        self.assertEqual(sorted(set(commands()) - named), [])

    def test_cli_md_holds_the_generated_table_and_the_readme_links_it(self):
        self.assertIn("## Which command when\n", read("docs/CLI.md"))
        self.assertIn("<!-- aidd:gen cli:when -->\n" + cli_reference.when_table(cli_parser.cli_facts()) + "\n<!-- aidd:end -->", read("docs/CLI.md"))
        self.assertIn("(docs/CLI.md#which-command-when)", read("README.md"))

    def test_the_readme_holds_only_the_everyday_commands(self):
        readme = read("README.md")
        self.assertIn("<!-- aidd:gen cli:everyday -->\n" + cli_reference.everyday_table(cli_parser.cli_facts()) + "\n<!-- aidd:end -->", readme)
        table = cli_reference.everyday_table(cli_parser.cli_facts())
        # Only what a person types: an agent runs `aidd gate --paths`, `aidd new spec`, and `aidd test`.
        self.assertEqual(table.count("\n| `aidd "), len(cli_parser.README_FORMS))
        self.assertLessEqual(set(cli_parser.README_FORMS), {form for form, _, _ in cli_parser.EVERYDAY})
        for agents in ("`aidd gate --paths`", "`aidd new spec`", "`aidd test`"):
            self.assertNotIn(agents, table)
        self.assertNotIn("<!-- aidd:gen cli:when -->", readme)


class WorkItemsDiagramTests(unittest.TestCase):
    def test_method_holds_the_generated_diagram_and_the_readme_links_it(self):
        block = "<!-- aidd:gen workitems -->\n" + generate.render("workitems") + "\n<!-- aidd:end -->"
        method = read("docs/METHOD.md")
        self.assertIn(block, method)
        self.assertLess(method.index("## 4. Objects"), method.index(block))
        self.assertIn("(docs/METHOD.md#4-objects)", read("README.md"))

    def test_the_diagram_holds_one_idea_in_at_most_eight_boxes(self):
        nodes, _ = diagram()
        self.assertLessEqual(len(nodes), 8, sorted(nodes))
        self.assertIn(diagrams.HUMAN_CLASS, generate.render("workitems"))

    def test_the_pick_goes_exactly_to_the_record_places_the_exploration_schema_names(self):
        # "the owner role writes the person's pick and reason in the Spec's Design section, DESIGN.md, or an ADR"
        text = schema("exploration")["description"]
        named = re.search(r"pick and reason in (.+?)\.(?:\s|$)", text).group(1)
        places = {re.sub(r"^(?:the|an|a) ", "", p.strip()) for p in re.split(r",\s*(?:or\s+)?|\s+or\s+", named) if p.strip()}
        nodes, edges = diagram()
        drawn = set()
        for src, arrow, label, dst in edges:
            if src != "Pick" or dst == "Pick":
                continue
            self.assertEqual(arrow, "-->", (src, dst))
            for name in nodes[dst].split("<br/>")[0].split(" or "):
                drawn.add(f"{name}'s {label}" if label else name)
        self.assertEqual(drawn, places)

    def test_the_containment_arrows_follow_the_parent_rules_in_the_schemas(self):
        # A Spec's parent is an Epic and an Epic's an Initiative (each schema's `parent`); Tasks live inside the Spec.
        want = {("Spec", "Task")} if "tasks" in schema("spec")["properties"] else set()
        for kind in ("spec", "epic"):
            parent = re.fullmatch(r"Optional (\w+) id\.", schema(kind)["properties"]["parent"]["description"]).group(1)
            want.add((parent, kind.capitalize()))
        kinds = {k for edge in want for k in edge}
        _, edges = diagram()
        drawn = {(src, dst) for src, arrow, _, dst in edges if src in kinds and dst in kinds}
        self.assertEqual(drawn, want)
        self.assertEqual({arrow for src, arrow, _, dst in edges if (src, dst) in want}, {"-->"})

    def test_it_says_what_a_proposal_and_an_exploration_are_for(self):
        nodes, _ = diagram()
        text = generate.render("workitems").split("```", 2)[2]
        for node, article in (("Proposal", "A"), ("Exploration", "An")):
            what = re.search(r"<i>(.+?)</i>", nodes[node]).group(1)
            self.assertIn(f"{article} {node.lower()} is about {what}", text)
        self.assertIn("Skip it when nobody outside the team must say yes.", text)
        self.assertNotIn("Skip it for your own product", text)
        self.assertIn("Skip it when the answer is obvious", text)

    def test_the_caption_says_the_containers_are_optional_and_points_to_the_method(self):
        text = generate.render("workitems").split("```", 2)[2]
        self.assertIn("Proposal, Initiative, and Epic are optional.", text)
        self.assertIn("A team may start with a Spec (§4.7).", text)
        self.assertIn("this section lists all the object kinds.", text)
        method = read("docs/METHOD.md")
        section = method.split("### 4.7 Proposal", 1)[1].split("\n## ", 1)[0]
        self.assertIn("go straight to a Spec", section)

    def test_the_parent_flag_names_the_parent_kind_the_schemas_allow(self):
        # `aidd validate` accepts any id as a parent; the schemas say which kind belongs there.
        help_text = next(a for a in commands()["new"]._actions if "--parent" in a.option_strings).help
        for kind in ("spec", "epic"):
            parent = re.fullmatch(r"Optional (\w+) id\.", schema(kind)["properties"]["parent"]["description"]).group(1)
            self.assertIn(f"an {parent} for {'a' if kind == 'spec' else 'an'} {kind.capitalize()}", help_text)


class MetricsByAuthorTests(unittest.TestCase):
    SENTENCE = "serves agent autonomy and a person's self-review, never ranking or appraising people"

    def test_the_help_and_the_metrics_docs_say_what_by_author_is_for(self):
        by = next(a for a in commands()["metrics"]._actions if "--by" in a.option_strings)
        self.assertIn(self.SENTENCE, by.help)
        self.assertIn(f"`aidd metrics --by author` {self.SENTENCE}.", read("docs/ADOPTION.md"))


class DocFlagTests(unittest.TestCase):
    """A doc that names `aidd <command> --flag` names a flag the command has: the team's explore command once told the
    owner to start an exploration with `aidd explore --question`, which does not exist (`aidd new exploration` does)."""

    def test_every_flag_a_doc_names_exists_on_its_command(self):
        top = commands()
        files = sorted(
            [*ROOT.glob("plugins/aidd-team/**/*.md"), *ROOT.glob(".agents/skills/aidd/**/*.md"), *ROOT.glob("docs/*.md")]
            + [ROOT / "README.md", ROOT / "llms-install.md"]
        )
        bad = []
        for path in files:
            for m in re.finditer(r"`aidd ([a-z][^`]*)`", path.read_text(encoding="utf-8")):
                words = m.group(1).split()
                if words[0] not in top:
                    bad.append((path.relative_to(ROOT).as_posix(), m.group(1), "no such command"))
                    continue
                sub = top[words[0]]
                nested = [a for a in sub._actions if isinstance(a, argparse._SubParsersAction)]
                if nested and len(words) > 1 and words[1] in nested[0].choices:
                    sub = nested[0].choices[words[1]]
                for word in words[1:]:
                    flag = word.split("=")[0].rstrip(",;:.)")
                    if flag.startswith("--") and flag not in sub._option_string_actions:
                        bad.append((path.relative_to(ROOT).as_posix(), m.group(1), flag))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
