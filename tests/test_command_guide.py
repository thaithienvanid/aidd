"""Which command when: the top-level help keeps the maintainer and harness commands apart (`aidd --help --all` lists
them), the "Which command when" table and the work-items diagram are generated, every command the parser defines is in
the table, and a doc never names a flag its command does not have."""

import argparse
import contextlib
import io
import json
import re
import unittest

from helpers import ROOT

from aidd import cli, docs

HIDDEN = ("eval", "gen-docs", "mcp", "hook")


def top_help(*argv: str) -> str:
    """What `aidd <argv>` prints for a help request, which exits 0."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            cli.main(list(argv))
    except SystemExit as stop:
        assert stop.code == 0, (argv, stop.code)
    return out.getvalue()


def listed(text: str) -> list[str]:
    """The command names a help page lists: the first word of each two-space-indented row."""
    return [line.split()[0] for line in text.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.split()]


def commands() -> dict:
    return dict(next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def schema(name: str) -> dict:
    return json.loads(read(f"schemas/{name}.schema.json"))


EDGE = re.compile(r"\s*(-->|-\.->)(?:\|\"([^\"]*)\"\|)?\s*")


def diagram() -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    """The work-items diagram: each node's label, and each arrow as (from, arrow, label, to)."""
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str, str, str]] = []
    for line in docs.WORK_ITEMS[1:]:
        node = re.fullmatch(r"\s+(\w+)(?:\[\"|\{\{\")(.*?)(?:\"\]|\"\}\})", line)
        if node:
            nodes[node.group(1)] = node.group(2)
            continue
        parts = EDGE.split(line.strip())
        for i in range(0, len(parts) - 3, 3):
            edges.append((parts[i], parts[i + 1], parts[i + 2] or "", parts[i + 3]))
    return nodes, edges


class HelpTests(unittest.TestCase):
    def test_the_default_help_hides_the_maintainer_and_harness_commands(self):
        text = top_help("--help")
        for name in HIDDEN:
            self.assertNotIn(name, listed(text), name)
        for name in ("assess", "new", "test", "gate", "ship", "list"):
            self.assertIn(name, listed(text), name)
        self.assertIn("aidd --help --all", text)

    def test_help_all_lists_them_under_their_own_heading(self):
        for argv in (("--help", "--all"), ("--all", "--help"), ("-h", "--all")):
            text = top_help(*argv)
            self.assertIn("Maintainers and harnesses:", text, argv)
            section = text.split("Maintainers and harnesses:", 1)[1]
            for name in HIDDEN:
                self.assertIn(name, listed(section), (argv, name))

    def test_an_abbreviated_top_level_option_is_an_error_not_a_help_without_all(self):
        # `--al` once stood for `--all` to argparse, while the help looked for `--all` itself and hid the commands.
        for argv in (["--al", "--help"], ["--help", "--al"], ["--al", "list"]):
            err = io.StringIO()
            with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                cli.main(argv)
            self.assertEqual(stop.exception.code, 2, argv)
            self.assertIn("--al", err.getvalue(), argv)

    def test_a_command_still_takes_its_options_abbreviated(self):
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["assess", "--pat", "a.py"]).paths, ["a.py"])
        self.assertEqual(parser.parse_args(["owners", "--chan", "a.py"]).changed, ["a.py"])
        self.assertTrue(parser.parse_args(["gen-docs", "--che"]).check)

    def test_the_hidden_commands_keep_working(self):
        parser = cli.build_parser()
        for argv in (["eval", "examples"], ["gen-docs", "--check"], ["mcp"], ["hook", "pre-compact"]):
            self.assertEqual(parser.parse_args(argv).func.__name__, "cmd_" + argv[0].replace("-", "_"), argv)
        for name in HIDDEN:
            self.assertIn(f"{name} [-h]", top_help(name, "--help").replace("\n", " "), name)

    def test_cli_md_still_documents_them(self):
        table = docs.cli_table()
        for name in HIDDEN:
            self.assertIn(f"| `{name}`", table, name)
        self.assertIn("aidd --help --all", read("docs/CLI.md"))


class WhenTableTests(unittest.TestCase):
    def test_every_command_the_parser_defines_is_in_the_table(self):
        table = docs.when_table()
        for name in commands():
            self.assertRegex(table, rf"`aidd {re.escape(name)}\b", name)

    def test_the_everyday_commands_come_first_in_loop_order(self):
        rows = [line for line in docs.when_table().splitlines() if line.startswith("| ") and "---" not in line][1:]
        everyday = ["aidd assess", "aidd new spec", "aidd hash", "aidd test", "aidd gate", "aidd ship", "aidd list"]
        for row, name in zip(rows, everyday, strict=False):
            self.assertIn(f"`{name}", row, name)
        self.assertIn("`aidd approve spec`", rows[2])
        self.assertTrue(rows[0].startswith("| Every day |"), rows[0])
        self.assertTrue(rows[len(everyday)].startswith("| Now and then |"), rows[len(everyday)])
        tail = rows[-len(HIDDEN) :]
        self.assertTrue(tail[0].startswith("| Maintainers and harnesses |"), tail[0])
        self.assertEqual(sorted(re.search(r"`aidd ([\w-]+)", r).group(1) for r in tail), sorted(HIDDEN))

    def test_every_command_has_a_when_phrase(self):
        named = {n for _, names, _ in cli.EVERYDAY for n in names} | set(cli.WHEN)
        self.assertEqual(sorted(set(commands()) - named), [])

    def test_the_readme_holds_the_generated_table_and_cli_md_links_it(self):
        self.assertIn("<!-- aidd:gen cli:when -->\n" + docs.when_table() + "\n<!-- aidd:end -->", read("README.md"))
        self.assertIn("README.md#which-command-when", read("docs/CLI.md"))


class WorkItemsDiagramTests(unittest.TestCase):
    def test_readme_and_method_hold_the_same_generated_diagram(self):
        block = "<!-- aidd:gen workitems -->\n" + docs.render("workitems") + "\n<!-- aidd:end -->"
        for rel in ("README.md", "docs/METHOD.md"):
            self.assertIn(block, read(rel), rel)

    def test_the_diagram_holds_one_idea_in_at_most_eight_boxes(self):
        nodes, _ = diagram()
        self.assertLessEqual(len(nodes), 8, sorted(nodes))
        self.assertIn(docs.HUMAN_CLASS, docs.render("workitems"))

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
        text = docs.render("workitems").split("```", 2)[2]
        for node, article in (("Proposal", "A"), ("Exploration", "An")):
            what = re.search(r"<i>(.+?)</i>", nodes[node]).group(1)
            self.assertIn(f"{article} {node.lower()} is about {what}", text)
        self.assertIn("Skip it when nobody outside the team must say yes.", text)
        self.assertNotIn("Skip it for your own product", text)
        self.assertIn("Skip it when the answer is obvious", text)

    def test_the_caption_says_the_containers_are_optional_and_points_to_the_method(self):
        text = docs.render("workitems").split("```", 2)[2]
        self.assertIn("Proposal, Initiative, and Epic are optional.", text)
        self.assertIn("A team may start with a Spec (METHOD §4.7).", text)
        self.assertIn("METHOD §4 lists all the object kinds.", text)
        method = read("docs/METHOD.md")
        section = method.split("### 4.7 Proposal", 1)[1].split("\n## ", 1)[0]
        self.assertIn("go straight to a Spec", section)
        self.assertIn("Proposal, Initiative, and Epic are optional.", method.split("## 4. Objects", 1)[1].split("### 4.1", 1)[0])

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

    def test_the_explore_command_starts_an_exploration_with_new(self):
        text = read("plugins/aidd-team/commands/explore.md")
        self.assertIn('`aidd new exploration <folder> --title "<the question>" --owner <role> --timebox "<minutes or cost>"`', text)


if __name__ == "__main__":
    unittest.main()
