"""The public contracts of CONTRIBUTING.md hold against the code.

- every file of `schemas/` belongs to one surface of the table, or says why it belongs to none, so a schema added with no row fails;
- the table has one row per surface, in the order below, each with what a minor release may do and what only a major may;
- what aidd writes is closed: each `--json` output follows its schema, and a key the schema lacks is an error for the writer's check;
- what a program reads from aidd is open: the same output with one more key in every object and a code its family does not list
  is no error when read as a reader of a newer aidd reads it (`open_set`), and the output a reader cannot use is still one;
- a reader opens only the `enum` that is marked `"x-open": true`, a family of codes a minor release may grow, and the marked enums
  are the families the table promises; any other `enum` stays closed to a reader, so an unknown `level` is an error;
- the handoff block is read the same way: a key or a stop code it does not know is a warning, and the rest of the note still counts;
- the lists the code holds, the environment variables, the Action's inputs, the commit trailers, and the headings aidd reads, are
  each derived from the code and must match their row, so a new one with no row fails.

The other readers of a newer file have their tests beside them: the records (`test_records_reading.py`) and the summary of the
last test run (`test_last_run.py`)."""

from __future__ import annotations

import ast
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # puts src/ on the path and makes the run hermetic
import test_cli_contract
from helpers import aidd_here, git, make_repo

from aidd import config
from aidd.cli import arguments, mcp_tools
from aidd.config import layout
from aidd.delegation import parts
from aidd.docsgen import counts
from aidd.kernel import json_schema
from aidd.kernel.processes import SECRET_ENV
from aidd.testing import runner
from aidd.workitems import doc_checks, handoff_notes, spec_warnings

ROOT = helpers.ROOT

# The rows of CONTRIBUTING.md's public contracts, in order: the word each row's first cell starts with, then the files of `schemas/`
# that carry the surface. A row with no file is a surface the code holds by other means.
SURFACES: dict[str, tuple[str, tuple[str, ...]]] = {
    "cli": ("CLI commands", ()),
    "exit": ("Exit codes", ()),
    "output": (
        "`--json` outputs",
        (
            "common.schema.json",
            "delegate-check.schema.json",
            "design-manifest.schema.json",
            "doctor.schema.json",
            "explain.schema.json",
            "knowledge.schema.json",
            "orca-payload.schema.json",
            "packs.schema.json",
            "recall.schema.json",
            "risk.schema.json",
            "stack-list.schema.json",
            "standard-list.schema.json",
            "status.schema.json",
            "trace.schema.json",
            "validate.schema.json",
        ),
    ),
    "mcp": ("MCP tool names", ()),
    "env": ("The environment variables", ()),
    "action": ("The GitHub Action's inputs", ()),
    "records": ("Records", ("records.json", "records.schema.json")),
    "evidence": ("The evidence file", ("evidence.schema.json",)),
    "handoff": ("The handoff block", ("handoff.schema.json",)),
    "config": ("The config", ("config.schema.json",)),
    "front_matter": (
        "A Spec's front matter",
        (
            "exploration.schema.json",
            "intent.schema.json",
            "postmortem.schema.json",
            "proposal.schema.json",
            "round-changes.schema.json",
            "round-comments.schema.json",
            "runbook.schema.json",
            "spec.schema.json",
        ),
    ),
    "headings": ("The `##` headings", ()),
    "trailers": ("The commit trailers", ()),
    "ids": (
        "The ids an adopter names",
        (
            "agents.json",
            "findings.json",
            "findings.schema.json",
            "industry-standards.json",
            "item-types.json",
            "item-types.schema.json",
            "languages.json",
            "languages.schema.json",
            "lifecycles.json",
            "lifecycles.schema.json",
            "packs.json",
            "profiles.json",
            "risks.json",
            "risks.schema.json",
            "roles.json",
            "roles.schema.json",
            "stack.schema.json",
            "standard.schema.json",
            "test-runners.json",
            "test-runners.schema.json",
        ),
    ),
    "plugins": ("The plugins' names", ()),
    "retired": ("The retired-names table", ("retired-names.json", "retired-names.schema.json")),
    "ledgers": ("The ledgers aidd keeps", ()),
    "generated": ("The files aidd writes and rewrites", ()),
}
# Files of `schemas/` that no adopter reads or writes, each with why.
INTERNAL = {
    "eval-claims.schema.json": "the claims `aidd eval` checks, written and run by the maintainers",
    "eval-grader-library.schema.json": "the graders of `aidd eval`, the maintainers' own",
    "eval-held-out.schema.json": "the lock of the held-out tasks of `aidd eval`, the maintainers' own",
    "eval-worlds.schema.json": "the worlds of `aidd eval`, the maintainers' own",
    "product.json": "what aidd says about itself, which `aidd gen-docs` copies into its own files",
}


def contract_rows() -> list[list[str]]:
    """The cells of each row of CONTRIBUTING.md's public contracts table, below its header."""
    lines = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| Surface |"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return rows


class TableTests(unittest.TestCase):
    def test_every_schema_file_belongs_to_one_surface_or_says_why_it_belongs_to_none(self):
        held = [name for _, files in SURFACES.values() for name in files]
        self.assertEqual(len(held), len(set(held)), "a file is on one row")
        self.assertEqual(sorted(set(held) & set(INTERNAL)), [], "a file is on a row or internal, not both")
        on_disk = sorted(p.name for p in (ROOT / "schemas").glob("*.json"))
        self.assertEqual(
            sorted(set(on_disk) - set(held) - set(INTERNAL)),
            [],
            "a new file of schemas/ is a public surface, so add its row to CONTRIBUTING.md's public contracts and to SURFACES, or it is internal, so say why in INTERNAL",
        )
        self.assertEqual(sorted((set(held) | set(INTERNAL)) - set(on_disk)), [], "a file this test names is gone")

    def test_the_table_has_one_row_per_surface_in_order_and_each_says_what_a_minor_and_a_major_release_may_do(self):
        rows = contract_rows()
        self.assertEqual(len(rows), len(SURFACES), [r[0] for r in rows])
        for row, (key, (label, _)) in zip(rows, SURFACES.items(), strict=True):
            with self.subTest(key):
                self.assertEqual(len(row), 5, "surface, versioned by, a minor release may, only a major release may, a reader of a newer file")
                self.assertTrue(row[0].startswith(label), f"{row[0]!r} is not the row of {label!r}")
                self.assertTrue(all(cell for cell in row), "no empty cell")

    def test_the_surfaces_the_code_holds_by_other_means_exist(self):
        """A row with no schema file stands on something in the code, so the row is for a surface that exists."""
        self.assertGreater(len(test_cli_contract.commands()), 8)
        self.assertTrue(arguments.EXIT_CODES)
        self.assertTrue(mcp_tools.TOOLS and all(tool["name"] and tool["inputSchema"]["properties"] for tool in mcp_tools.TOOLS))
        ledgers = contract_rows()[list(SURFACES).index("ledgers")][0]
        for path in (layout.HARNESS_RULES_FILE, layout.TEAM_FILES_FILE):
            self.assertIn(f"`{path}`", ledgers, "the row names each ledger aidd keeps in .aidd/")
        for folder in ("commands", "agents", "skills"):
            self.assertTrue(list((ROOT / "plugins" / "aidd-team" / folder).iterdir()), f"the plugin has {folder}")
        self.assertTrue(list((ROOT / "plugins" / "aidd-packs" / "skills").iterdir()), "the packs plugin has skills")


KEY = "added_by_a_newer_aidd"


def with_an_unknown_key_in_every_closed_object(node, schema: dict, base: str):
    """A copy of `node` with one more key in every object its schema closes: the places a newer aidd may add one. A schema
    reached through a combinator is left as it is, and a map of names to values takes no key of its own."""
    schema, base = json_schema.deref(schema, base)
    if isinstance(node, dict) and "oneOf" in schema:  # the one shape the answer fits, such as risk's answer for paths or for a command
        for branch in schema["oneOf"]:
            shape, where = json_schema.deref(branch, base)
            both = {**schema.get("properties", {}), **shape.get("properties", {})}
            if set(shape.get("required", [])) <= set(node) and set(node) <= set(both):
                schema, base = {**{k: v for k, v in schema.items() if k != "oneOf"}, **shape, "properties": both}, where
                break
    if isinstance(node, list) and isinstance(schema.get("items"), dict):
        return [with_an_unknown_key_in_every_closed_object(item, schema["items"], base) for item in node]
    if not isinstance(node, dict):
        return node
    props, extra = schema.get("properties", {}), schema.get("additionalProperties")
    grown = {
        k: with_an_unknown_key_in_every_closed_object(v, props[k] if k in props else extra, base) if k in props or isinstance(extra, dict) else v
        for k, v in node.items()
    }
    return {**grown, KEY: 1} if extra is False else grown


def set_at(node, pointer: tuple, value) -> None:
    for step in pointer[:-1]:
        node = node[step]
    node[pointer[-1]] = value


class OutputTests(unittest.TestCase):
    """Each call is a `--json` command with the schema its output follows, and where a code family sits in it, if it does there."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = make_repo(Path(tmp.name) / "repo", "team", spec="specs/SPEC-220.md")
        (cls.root / "app.py").write_text("print(1)\n", encoding="utf-8")
        head = git(cls.root, "rev-parse", "HEAD")
        cls.CALLS = (
            (("status",), "status.schema.json", ("items", 0, "next", "code"), "spec.state_a_newer_aidd_adds"),
            (("status", "SPEC-220"), "status.schema.json", ("items", 0, "next", "code"), "spec.state_a_newer_aidd_adds"),
            (("explain", "pr.merge"), "explain.schema.json", ("matches", 0, "type"), "type_a_newer_aidd_adds"),
            (
                ("delegate", "check", "--action", "pr.merge", "--command", "gh pr merge 1", "--head", head),
                "delegate-check.schema.json",
                ("reasons", 0, "code"),
                "reason_a_newer_aidd_adds",
            ),
            *((argv, schema, None, None) for argv, schema in test_cli_contract.JsonOutputTests.CALLS if argv[0] not in ("status", "explain")),
        )

    def output(self, argv: tuple) -> dict:
        done = aidd_here(*argv, "--json", cwd=self.root)
        self.assertIn(done.returncode, (0, 1), done.stdout + done.stderr)
        return json.loads(done.stdout)

    def test_what_aidd_writes_is_closed_and_what_a_reader_of_a_newer_aidd_reads_is_open(self):
        for argv, schema, pointer, newer in self.CALLS:
            with self.subTest(argv=argv):
                written = self.output(argv)
                self.assertEqual(json_schema.validate(written, schema), [], "aidd emits no key its schema lacks, and no code it does not list")
                root, base = json_schema.resolve_ref(schema, "")
                grown = with_an_unknown_key_in_every_closed_object(written, root, base)
                self.assertIn(KEY, json.dumps(grown), "the schema closes the output, so a key was added")
                if pointer:
                    grown = copy.deepcopy(grown)
                    set_at(grown, pointer, newer)
                self.assertTrue(json_schema.validate(grown, schema), "the writer's check stays closed")
                self.assertEqual(json_schema.validate(grown, schema, open_set=True), [], "a reader ignores a key and a code it does not know")
                broken = copy.deepcopy(grown)
                del broken["schema_version"]
                self.assertTrue(json_schema.validate(broken, schema, open_set=True), "a reader still needs what the output must hold")

    def test_the_calls_cover_every_output_a_command_prints_that_a_fixture_can_print(self):
        shown = {schema for _, schema, _, _ in self.CALLS}
        self.assertEqual(shown - {s for _, s in test_cli_contract.JsonOutputTests.CALLS}, {"delegate-check.schema.json"})


class HandoffTests(unittest.TestCase):
    NOTE = "done: T1 built\nnext_role: reviewer\nneeds: none\nstopped_at: none\n"

    def warnings(self, extra: str) -> list[str]:
        return handoff_notes.handoff_warnings("specs/SPEC-1.md", f"text\n\n```aidd-handoff\n{self.NOTE}{extra}```\n")

    def test_a_key_and_a_stop_code_a_newer_aidd_adds_are_warnings_and_never_errors(self):
        self.assertEqual(self.warnings(""), [], "the note without either is clean")
        for what, extra, named in (
            ("a key it does not know", f"{KEY}: x\n", KEY),
            ("a stop code it does not know", None, "newer_stop"),
        ):
            with self.subTest(what):
                if extra is None:
                    note = self.NOTE.replace("stopped_at: none", 'stopped_at: "newer_stop: a detail"')
                    found = handoff_notes.handoff_warnings("specs/SPEC-1.md", f"text\n\n```aidd-handoff\n{note}```\n")
                else:
                    found = self.warnings(extra)
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith("warning: ") and named in found[0], found)

    def test_the_rest_of_the_note_still_counts_beside_a_key_it_does_not_know(self):
        decision = "open_decisions:\n  - id: pick-one\n    what: which one\n    options:\n      - choice: a\n      - choice: b\n"
        with_key = handoff_notes.handoff_blocks(f"```aidd-handoff\n{self.NOTE}{decision}{KEY}: x\n```\n")
        without = handoff_notes.handoff_blocks(f"```aidd-handoff\n{self.NOTE}{decision}```\n")
        self.assertEqual(handoff_notes.decision_states(with_key), handoff_notes.decision_states(without))
        self.assertEqual([s["status"] for s in handoff_notes.decision_states(with_key)[0]], ["open"])


def row_text(key: str) -> str:
    """One row of the table, as one string."""
    return " ".join(contract_rows()[list(SURFACES).index(key)])


def words_in_code_marks(key: str) -> list[str]:
    """What the row's first cell puts in code marks after its first colon, in the row's order: the list it states."""
    return re.findall(r"`([^`]+)`", contract_rows()[list(SURFACES).index(key)][0].partition(": ")[2])


SOURCE = ROOT / "src" / "aidd"
# Modules that read aidd's own skills and packs, which no adopter writes, so their headings belong to no row.
OWN_FILE_READERS = ("docsgen/pack_budget.py", "knowledge/library_checks.py", "knowledge/standards.py")
HEADING_READERS = ("markdown_section", "raw_section")
# A call that takes its heading from a variable the walk below cannot resolve, with the headings that variable holds.
HEADINGS_BY_VARIABLE = {
    "delegation/parts.py": [heading for _, heading in parts.SECTIONS],
    "workitems/doc_checks.py": [heading for headings in doc_checks.INLINE_DOC_SECTIONS.values() for heading in headings],
    "workitems/spec_warnings.py": list(spec_warnings.GLOSSARY_SECTIONS),
    "workitems/validation.py": ["Alternatives considered", "Pre-mortem"],
}
TRAILER = re.compile(r"\b(?:[A-Z][a-z]+(?:-[a-z]+)*-by|On-behalf-of|Delegation(?=:))")


def headings_aidd_reads(source: Path = SOURCE) -> set[str]:
    """Every `## <heading>` a reader of a document's body looks for: the literal, or the module constant, that a call of
    `markdown_section` or `raw_section` gives, and the headings a call that takes a variable gets from `HEADINGS_BY_VARIABLE`.
    A call of that kind in a module the table does not name fails the test, so a new reader cannot go unseen."""
    found, unresolved = set(), []
    for path in sorted(source.rglob("*.py")):
        rel = path.relative_to(source).as_posix()
        if rel in OWN_FILE_READERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.targets[0], ast.Name)
        }
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call) and len(n.args) >= 2):
            name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
            if name not in HEADING_READERS:
                continue
            heading = call.args[1]
            if isinstance(heading, ast.Constant):
                found.add(str(heading.value))
            elif isinstance(heading, ast.Name) and heading.id in constants:
                found.add(str(constants[heading.id]))
            elif rel in HEADINGS_BY_VARIABLE:
                found.update(HEADINGS_BY_VARIABLE[rel])
            else:
                unresolved.append(f"{rel}: {ast.unparse(call)}")
    assert not unresolved, f"a reader of a heading the test cannot resolve; name its headings in HEADINGS_BY_VARIABLE: {unresolved}"
    return found


# A name the code looks up in a loop over a table, by the file that does it: the table holds the names.
NAMES_FROM_TABLES = {
    "cli/commands/setup.py": lambda: config.AGENT_ENV,
    "setup/adoption.py": lambda: tuple(config.SESSION_ENV),
    "setup/self_updating.py": lambda: config.AGENT_ENV,
    "testing/runner.py": lambda: runner.CI_RUNNER_ENV,
}
READ_METHODS = ("get", "pop", "setdefault", "getenv")


def _is_environ(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "environ" or isinstance(node, ast.Name) and node.id == "environ"


def _holds_environ(node: ast.AST) -> bool:
    return any(_is_environ(n) for n in ast.walk(node))


def _is_environment(node: ast.AST, aliases: set[str]) -> bool:
    """Whether `node` is the process environment: `os.environ`, a name assigned from it in the same function, or a choice
    between it and a mapping the caller passes (`os.environ if environ is None else environ`)."""
    if _is_environ(node) or isinstance(node, ast.Name) and node.id in aliases:
        return True
    if isinstance(node, ast.IfExp):
        return _is_environment(node.body, aliases) or _is_environment(node.orelse, aliases)
    return isinstance(node, ast.BoolOp) and any(_is_environment(v, aliases) for v in node.values)


def environment_reads(source: Path = SOURCE) -> tuple[set[str], list[str]]:
    """Every environment variable the code looks up by name, and the lookups whose name the walk cannot resolve. A lookup is
    `os.environ[name]`, `.get`, `.pop`, or `.setdefault` on the environment, `os.getenv(name)`, or `name in os.environ`, where
    the environment may be a name assigned from it in the same function. A name is a string, or a constant of the module. A
    lookup in a file `NAMES_FROM_TABLES` names takes the names of its table. A write (`os.environ[name] = value`) and a copy of the
    whole environment name no variable."""
    found: set[str] = set()
    unresolved: list[str] = []
    for path in sorted(source.rglob("*.py")):
        rel = path.relative_to(source).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and isinstance(node.targets[0], ast.Name)
        }
        for scope in (tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))):
            aliases = {
                target.id
                for n in ast.walk(scope)
                if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None and _holds_environ(n.value)
                for target in (n.targets if isinstance(n, ast.Assign) else [n.target])
                if isinstance(target, ast.Name)
            }
            for n in ast.walk(scope):
                key: ast.expr | None = None
                if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load) and _is_environment(n.value, aliases):
                    key = n.slice
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in READ_METHODS and n.args:
                    if _is_environment(n.func.value, aliases) or n.func.attr == "getenv" and isinstance(n.func.value, ast.Name) and n.func.value.id == "os":
                        key = n.args[0]
                elif (
                    isinstance(n, ast.Compare)
                    and any(isinstance(op, (ast.In, ast.NotIn)) for op in n.ops)
                    and any(_is_environment(c, aliases) for c in n.comparators)
                ):
                    key = n.left
                if key is None:
                    continue
                if isinstance(key, ast.Name) and key.id in constants:
                    found.add(constants[key.id])
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.add(key.value)
                elif rel in NAMES_FROM_TABLES:
                    found.update(NAMES_FROM_TABLES[rel]())
                else:
                    unresolved.append(f"{rel}:{n.lineno}: {ast.unparse(n)[:80]}")
    return found, sorted(set(unresolved))


def aidd_variables_in_code() -> set[str]:
    """Every `AIDD_` name any file of the code spells, even where it only sets or describes the variable. A name may end in a digit."""
    named: set[str] = set()
    for path in SOURCE.rglob("*.py"):
        if path.resolve() != Path(counts.__file__).resolve():  # the table that lists them names them too
            named |= set(re.findall(r"\b(AIDD_[A-Z0-9_]*[A-Z0-9])\b", path.read_text(encoding="utf-8")))
    return named


def action_inputs() -> list[str]:
    lines = (ROOT / "action.yml").read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    for line in lines[lines.index("inputs:") + 1 :]:
        if line and not line.startswith(" "):
            break
        if found := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line):
            names.append(found[1])
    return names


def trailers_in_code() -> set[str]:
    """The trailers the code names, and the `Aidd-` ones that the skill and the team's files tell an agent to write."""
    found = set()
    for path in SOURCE.rglob("*.py"):
        found |= set(TRAILER.findall(path.read_text(encoding="utf-8")))
    for folder in (ROOT / ".agents" / "skills" / "aidd", ROOT / "plugins" / "aidd-team" / "commands", ROOT / "plugins" / "aidd-team" / "agents"):
        for path in folder.rglob("*.md"):
            found |= set(re.findall(r"\bAidd-[A-Z][A-Za-z]+", path.read_text(encoding="utf-8")))
    return found


class ListedSurfaceTests(unittest.TestCase):
    """The lists the code holds, each derived from the code and compared with its row."""

    def test_every_variable_the_code_reads_is_in_one_of_the_three_kinds_the_page_lists(self):
        """The variables aidd defines (`AIDD_*`) are promised. The variables of another tool or the platform that it reads, and the
        ones it reads only to tell where it runs, are listed with no promise about their values. A variable of none of the three,
        or of two, fails."""
        defined = {name for name, _, _ in counts.ENV_VARS}
        other = {name for name, _, _ in counts.OTHER_ENV_VARS}
        where = set(counts.where_it_runs_env())
        read, unresolved = environment_reads()
        self.assertEqual(unresolved, [], "a lookup the walk cannot resolve: name its table in NAMES_FROM_TABLES")
        self.assertGreater(len(read), 20)
        kinds = {"defined": defined, "other": other, "where": where}
        for name in sorted(read | aidd_variables_in_code()):
            with self.subTest(name=name):
                listed = [kind for kind, names in kinds.items() if name in names]
                if name.startswith("AIDD_"):
                    self.assertTrue(listed == ["defined"] or name in SECRET_ENV, f"{name} is aidd's, so it has a row in the first kind")
                else:
                    self.assertEqual(len(listed), 1, f"{name} is in {listed or 'none'} of the three kinds")
        self.assertEqual(sorted(name for name in other | where if name.startswith("AIDD_")), [], "a variable of aidd's is never listed as another tool's")
        self.assertTrue(set(runner.CI_RUNNER_ENV) <= where, "the CI platform's variables the evidence records")
        self.assertTrue(set(config.AGENT_ENV) - {"AIDD_AGENT"} <= where, "a coding agent's variables")

    def test_the_page_the_row_names_lists_every_variable_in_all_three_kinds(self):
        self.assertIn("docs/CLI.md", row_text("env"))
        self.assertIn("`AIDD_*`", row_text("env"), "the row says which variables it promises")
        page = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
        listed = {name for name, _, _ in counts.ENV_VARS} | {name for name, _, _ in counts.OTHER_ENV_VARS} | set(counts.where_it_runs_env())
        self.assertEqual(sorted(name for name in listed if f"`{name}`" not in page), [], "a variable with no entry on the page the row names")

    def test_the_walk_finds_each_way_the_code_reads_a_variable_and_none_it_only_writes(self):
        cases = {
            "a subscript": ('import os\nx = os.environ["A_ONE"]\n', {"A_ONE"}),
            "get": ('import os\nx = os.environ.get("A_TWO", "")\n', {"A_TWO"}),
            "getenv": ('import os\nx = os.getenv("A_THREE")\n', {"A_THREE"}),
            "pop and setdefault": ('import os\nos.environ.pop("A_FOUR", None)\nos.environ.setdefault("A_FIVE", "x")\n', {"A_FOUR", "A_FIVE"}),
            "in": ('import os\nx = "A_SIX" in os.environ\n', {"A_SIX"}),
            "a name ending in a digit": ('import os\nx = os.environ.get("AIDD_TIMEOUT2")\n', {"AIDD_TIMEOUT2"}),
            "a module constant": ('import os\nKEY = "A_SEVEN"\nx = os.environ.get(KEY)\n', {"A_SEVEN"}),
            "a name assigned from the environment": ('import os\ndef f():\n    env = dict(os.environ)\n    return env.get("A_EIGHT")\n', {"A_EIGHT"}),
            "a choice between it and a passed mapping": (
                'import os\ndef f(environ=None):\n    return (os.environ if environ is None else environ).get("A_NINE")\n',
                {"A_NINE"},
            ),
            "a write": ('import os\nos.environ["A_TEN"] = "1"\n', set()),
            "a copy of the whole environment": ("import os\nenv = dict(os.environ)\nenv2 = {**os.environ}\n", set()),
            "another mapping": ('settings = {}\nx = settings.get("A_ELEVEN")\n', set()),
        }
        for name, (source, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                (Path(folder) / "reader.py").write_text(source, encoding="utf-8")
                self.assertEqual(environment_reads(Path(folder)), (expected, []))

    def test_a_lookup_by_a_name_the_walk_cannot_resolve_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "reader.py").write_text("import os\ndef f(name):\n    return os.environ.get(name)\n", encoding="utf-8")
            self.assertEqual(environment_reads(Path(folder)), (set(), ["reader.py:3: os.environ.get(name)"]))

    def test_the_action_inputs_are_the_ones_its_row_lists_in_order(self):
        inputs = action_inputs()
        self.assertGreater(len(inputs), 3)
        self.assertEqual(words_in_code_marks("action"), sorted(inputs), "an input with no row, or a row for one the Action lacks")

    def test_the_trailers_the_code_names_are_the_ones_its_row_lists_in_order(self):
        named = trailers_in_code()
        self.assertTrue({"Assisted-by", "Approved-by", "Agreed-by", "Decided-by", "On-behalf-of", "Delegation", "Aidd-Skipped"} <= named, named)
        listed = words_in_code_marks("trailers")
        self.assertEqual(listed, sorted(named, key=str.lower), "a trailer with no row, or a row for one the code lacks")

    def test_the_headings_the_code_reads_are_the_ones_its_row_lists_in_order(self):
        read = headings_aidd_reads()
        self.assertGreater(len(read), 15)
        listed = words_in_code_marks("headings")
        self.assertEqual(listed, sorted(read, key=str.lower), "a heading with no row, or a row for one no code reads")

    def test_a_reader_that_takes_a_heading_from_a_variable_is_named_or_the_walk_fails(self):
        source = "from aidd.kernel import documents\n\ndef read(text, name):\n    return documents.markdown_section(text, name)\n"
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "reader.py").write_text(source, encoding="utf-8")
            with self.assertRaises(AssertionError) as caught:
                headings_aidd_reads(Path(folder))
        self.assertIn("reader.py", str(caught.exception))


def enums_marked_open() -> list[str]:
    """`<file>#<pointer>` of each `enum` with `"x-open": true`, in every file of `schemas/`."""
    found: list[str] = []

    def walk(node, pointer: str, name: str) -> None:
        if isinstance(node, dict):
            if node.get("x-open") is True:
                found.append(f"{name}#{pointer}" + ("" if "enum" in node else " (no enum)"))
            for key, value in node.items():
                walk(value, f"{pointer}/{key}", name)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{pointer}/{i}", name)

    for path in sorted((ROOT / "schemas").glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")), "", path.name)
    return found


class OpenFamilyTests(unittest.TestCase):
    """A reader opens the families of codes that the table promises may grow, and no other `enum`."""

    FAMILIES = [
        "common.schema.json#/$defs/step_code",
        "delegate-check.schema.json#/$defs/reason_code",
        "explain.schema.json#/$defs/type",
        "records.json#/types/decision/data/properties/answer/properties/outcome",
        "records.json#/types/decision/data/properties/question/properties/type",
        "records.json#/types/delegate_answer/data/properties/outcome",
        "records.json#/types/delegate_check/data/properties/outcome",
        "records.schema.json#/$defs/record/properties/written_with",
    ]

    def test_the_marked_enums_are_the_families_of_codes_and_nothing_else(self):
        self.assertEqual(sorted(enums_marked_open()), sorted(self.FAMILIES))
        row = row_text("output")
        for word in ("step", "reason codes", "`aidd explain`", "`x-open: true`"):
            self.assertIn(word, row)

    def test_every_enum_of_a_record_is_a_family_an_older_aidd_keeps_reading(self):
        """The records table promises a record with a value of a code it does not know is kept and shown, so none of the
        enums in the record schemas may be closed to a reader."""

        def enums(node, pointer=""):
            if isinstance(node, dict):
                if "enum" in node:
                    yield pointer, node.get("x-open") is True
                for key, value in node.items():
                    yield from enums(value, f"{pointer}/{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    yield from enums(value, f"{pointer}/{i}")

        for name in ("records.json", "records.schema.json"):
            found = list(enums(json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))))
            self.assertTrue(found, name)
            self.assertEqual([pointer for pointer, marked in found if not marked], [], f"{name}: an enum closed to a reader")

    def test_a_reader_opens_a_marked_enum_and_keeps_every_other_closed(self):
        marked, plain = "common.schema.json#/$defs/step_code", "common.schema.json#/$defs/route"
        cases = [
            ("a marked enum, a value it lists", marked, "spec.draft", 0, 0),
            ("a marked enum, a value it does not list", marked, "spec.a_newer_aidd_adds", 1, 0),
            ("a marked enum, a value of another type", marked, 7, 1, 1),
            ("a marked enum, no value", marked, None, 1, 1),
            ("another enum, a value it lists", plain, "major", 0, 0),
            ("another enum, a value it does not list", plain, "a_newer_aidd_adds", 1, 1),
        ]
        for name, schema, value, closed, opened in cases:
            with self.subTest(name):
                self.assertEqual((len(json_schema.validate(value, schema)), len(json_schema.validate(value, schema, open_set=True))), (closed, opened))

    def test_an_unknown_level_and_an_unknown_route_are_errors_to_a_reader_beside_a_code_it_does_not_know(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "repo", "team")
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            shown = json.loads(aidd_here("risk", "--paths", "app.py", "--json", cwd=root).stdout)
        for key, newer in (("spec_approval", "level_a_newer_aidd_adds"), ("route", "route_a_newer_aidd_adds")):
            with self.subTest(key=key):
                grown = {**shown, key: newer}
                self.assertTrue(json_schema.validate(grown, "risk.schema.json"))
                self.assertTrue(json_schema.validate(grown, "risk.schema.json", open_set=True), "a value of a closed enum is no pass")


if __name__ == "__main__":
    unittest.main()
