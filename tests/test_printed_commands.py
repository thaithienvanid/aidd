"""A command aidd prints holds no raw file or config text, at any place that prints one. `kernel.command_names` is the one rule
(`quoted`, `NO_COMMAND`) and `test_command_names.py` holds its per-site rows. This test is the general check: it reads the
source with `ast`, finds every string a person may paste as a command, and fails when a value interpolated into it is not
proven safe. A site someone forgot is found here, not by a person who pastes a command that ran `a$(touch X)`.

A printed command is a backtick span that starts with a program aidd suggests (PROGRAMS) and holds an interpolated
expression, in an f-string, a `.format` call, a `%` format, or a `+` join. A shell command that no backtick marks is also one
(SHELL_WORDS), up to the end of its clause. A value is proven safe by one of these rules, and nothing else:

 1. a call to `command_names.quoted` (by that name, or as `quoted` imported from it), `shlex.quote`, or `shlex.join`;
 2. a literal, a length, or a parameter annotated as a number, a bool, or a `Literal`;
 3. a name of the module's constants (CAPITALS) whose literal holds only characters a shell reads as a plain word;
 4. an argparse value the parser limits to a closed set (`choices`, or the subcommand's name);
 5. a name every binding of which, in the same function, is itself safe: each assignment, and each loop over a literal list;
    a name bound by `with`, `except`, a lambda, or an unpacking is never safe; a name assigned from `command_names.quoted`
    also has to be tested in the function, so the None case is handled;
 6. a conditional, a join, or a comprehension of safe parts (`quoted(x) or "<ID>"`, `a if b else c`, `"--" + x`, `" ".join(...)`).

Where no static proof is possible, the site is one row of ACCEPTED, with the reason and the test that holds it. A row
that no longer matches a site fails, so the table cannot rot. The check reads the source and starts no process."""

from __future__ import annotations

import ast
import functools
import re
import string
import unittest
from pathlib import Path

from helpers import ROOT

ROOTS = ("src/aidd", "plugins/aidd-team/tools", "tools")
# The programs a printed command starts with: every program a span in the source suggests, and the ones a hostile name can
# make dangerous (rm, cd, mkdir).
PROGRAMS = frozenset({"aidd", "git", "gh", "glab", "claude", "cd", "rm", "mkdir", "cp", "mv", "uv", "uvx", "make", "pip", "npm", "python", "python3", "chmod"})
SHELL_WORDS = ("mkdir", "cp", "rm", "mv", "cd", "chmod")  # a command in prose, with no backticks: the program names that are no English word
# What a constant's literal may hold: the characters a shell reads as a plain word (a URL, an id, a path).
INERT = re.compile(r"[A-Za-z0-9._/:@=+,%#-]*")
QUOTERS = {"quoted": True, "quote": False, "join": False}  # the call name; True where it may return None
SPAN = re.compile(r"`([^`]*)`")
NUMBER_TYPES = {"int", "bool", "float"}
HOLE = "\x00"


# The sites no rule can prove from the source, each with why it is safe and the test that holds it. The key is the file, the
# printed command with its holes as `{}`, and the expression.
_OWNED = "tests/test_command_names.py::NamesTheCodeOwns"
_SUBCOMMAND = (
    "a subcommand name the parser accepted, or a literal one",
    f"{_OWNED}.test_every_subcommand_and_the_words_of_a_command_aidd_names_are_plain_names",
)
_HARNESS = ("a key of `config.HARNESSES`, which a test holds as plain names", f"{_OWNED}.test_every_harness_id_and_plugin_name_is_a_plain_name")
_TYPE = ("a key of the document and work item types the code owns", f"{_OWNED}.test_every_work_item_type_and_document_type_is_a_plain_name")
ACCEPTED: dict[tuple[str, str, str], tuple[str, str]] = {
    ("plugins/aidd-team/tools/prototype/prototype.py", "aidd prototype {}", "shown"): (
        "`_design_source` returns the problems, and the command never runs, unless the path matches `_SAFE_PATH`, which never starts with `-`",
        "tests/test_product_prototype.py::./-x.html",
    ),
    ("src/aidd/cli/commands/reading.py", "aidd {}", "row['new']"): (
        "what a retired command word became, from schemas/retired-names.json, aidd's own data",
        f"{_OWNED}.test_what_a_retired_command_word_became_is_plain_words",
    ),
    ("src/aidd/docsgen/cli_reference.py", "aidd {}", "name"): _SUBCOMMAND,
    ("src/aidd/docsgen/cli_reference.py", "aidd {}{}", "name"): _SUBCOMMAND,
    ("src/aidd/kernel/git.py", "aidd {}", "command"): _SUBCOMMAND,
    ("src/aidd/risk/routes.py", 'aidd new spec "<title>" --paths {}{}{}', "shown"): (
        "`shown_paths` quotes each path or shows `<path>`",
        f"{_OWNED}.test_the_paths_a_next_step_shows_are_plain_names_or_a_placeholder",
    ),
    ("src/aidd/setup/adoption.py", "aidd init {}", "' '.join((f'--harness {h}' for h in keys))"): _HARNESS,
    ("src/aidd/setup/claude_plugins.py", "claude plugin uninstall {}", "p"): (
        "the plugin names this function built from `config.MARKETPLACE`",
        f"{_OWNED}.test_every_harness_id_and_plugin_name_is_a_plain_name",
    ),
    ("src/aidd/setup/doctor_checks.py", "aidd init --harness {}", "running"): _HARNESS,
    ("src/aidd/setup/doctor_harnesses.py", "aidd init --harness {}", "running"): _HARNESS,
    ("src/aidd/workitems/authoring.py", 'aidd new {} "<title>"', "item.item_type"): _TYPE,
    ("src/aidd/workitems/doc_checks.py", "aidd new {}", "doc_type"): _TYPE,
    ("src/aidd/workitems/doc_checks.py", "aidd new {} <component> --living --spec {}", "doc_type"): _TYPE,
    ("src/aidd/workitems/doc_checks.py", "aidd new {} <topic> --spec {}", "doc_type"): _TYPE,
}


def module_files(roots: tuple[str, ...] = ROOTS) -> list[Path]:
    return [p for r in roots for p in sorted((ROOT / r).rglob("*.py")) if (ROOT / r).is_dir()]


def inert_literal(node: ast.expr, known: dict[str, bool]) -> bool:
    """A literal that holds only plain characters, or a constant that is another such constant (`URL = resources.URL`)."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int)) and bool(INERT.fullmatch(str(node.value)))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(inert_literal(e, known) for e in node.elts)
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return name.isupper() and known.get(name, False)


def module_constants(trees: list[ast.Module], known: dict[str, bool] | None = None) -> dict[str, bool]:
    """Every CAPITALS name the modules assign at their top, and whether all its assignments are inert literals."""
    found: dict[str, bool] = {}
    for tree in trees:
        for stmt in tree.body:
            pairs = (
                [(t, stmt.value) for t in stmt.targets]
                if isinstance(stmt, ast.Assign)
                else [(stmt.target, stmt.value)]
                if isinstance(stmt, ast.AnnAssign) and stmt.value is not None
                else []
            )
            for target, value in pairs:
                if isinstance(target, ast.Name) and target.id.isupper():
                    found[target.id] = found.get(target.id, True) and inert_literal(value, known or {})
    return found


def closed_arguments(trees: list[ast.Module]) -> set[str]:
    """The argparse values the parser limits to a closed set: a positional or option with `choices`, a subcommand's name."""
    seen: dict[str, bool] = {}
    for tree in trees:
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            keys = {k.arg: k.value for k in call.keywords if k.arg}
            if call.func.attr == "add_subparsers" and isinstance(keys.get("dest"), ast.Constant):
                seen[str(keys["dest"].value)] = True
            elif call.func.attr == "add_argument":
                names = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                dest = (
                    str(keys["dest"].value)
                    if isinstance(keys.get("dest"), ast.Constant)
                    else (max(names, key=len).lstrip("-").replace("-", "_") if names else "")
                )
                if dest:
                    seen[dest] = seen.get(dest, True) and "choices" in keys
    return {d for d, closed in seen.items() if closed}


class Function:
    """What a function says about its names: where each is assigned, looped over, and tested, and its annotated parameters."""

    def __init__(self, node: ast.AST | None):
        self.assigned: dict[str, list[ast.expr | None]] = {}
        self.looped: dict[str, list[ast.expr]] = {}
        self.params: dict[str, ast.expr | None] = {}
        self.tested: set[str] = set()
        if node is None:
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs, *([a.vararg] if a.vararg else []), *([a.kwarg] if a.kwarg else [])]:
                self.params[arg.arg] = arg.annotation
        for n in ast.walk(node):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    self.assign(t, n.value)
            elif isinstance(n, (ast.AnnAssign, ast.NamedExpr)) and n.value is not None:
                self.assign(n.target, n.value)
            elif isinstance(n, ast.AugAssign):
                self.assign(n.target, n.value)
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                for name in (x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)):
                    self.looped.setdefault(name, []).append(n.iter)
            elif isinstance(n, (ast.With, ast.AsyncWith)):  # a name bound by `with`, `except`, or a lambda holds what no rule reads
                for held in (item.optional_vars for item in n.items if item.optional_vars is not None):
                    for name in (x.id for x in ast.walk(held) if isinstance(x, ast.Name)):
                        self.assigned.setdefault(name, []).append(None)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                self.assigned.setdefault(n.name, []).append(None)
            elif isinstance(n, ast.Lambda):
                for arg in [*n.args.posonlyargs, *n.args.args, *n.args.kwonlyargs]:
                    self.assigned.setdefault(arg.arg, []).append(None)
            if isinstance(n, (ast.If, ast.IfExp, ast.While, ast.Assert)):
                self.tested |= {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
            elif isinstance(n, ast.BoolOp):
                self.tested |= {x.id for v in n.values for x in ast.walk(v) if isinstance(x, ast.Name)}

    def assign(self, target: ast.expr, value: ast.expr) -> None:
        if isinstance(target, ast.Name):
            self.assigned.setdefault(target.id, []).append(value)
        else:  # an unpacking, an attribute, an item: the name's value is not the right side whole
            for name in (x.id for x in ast.walk(target) if isinstance(x, ast.Name)):
                self.assigned.setdefault(name, []).append(None)


class Index:
    """What the source defines: each CAPITALS constant by its package and by its module, and the closed argparse values."""

    def __init__(self, files: list[Path], trees: list[ast.Module]):
        by_package: dict[str, list[ast.Module]] = {}
        by_module: dict[str, list[ast.Module]] = {}
        for path, tree in zip(files, trees, strict=True):
            parts = path.relative_to(ROOT).parts
            by_package.setdefault(parts[2] if parts[:2] == ("src", "aidd") and len(parts) > 3 else parts[-2], []).append(tree)
            by_module.setdefault(path.stem, []).append(tree)
        self.known = known = module_constants(trees)  # a first pass, for a constant that is another one
        self.packages = {k: module_constants(v, known) for k, v in by_package.items()}
        self.modules = {k: module_constants(v, known) for k, v in by_module.items()}
        self.closed = closed_arguments([t for p, t in zip(files, trees, strict=True) if "/cli/" in p.as_posix()])

    def imported(self, tree: ast.Module) -> dict[str, dict[str, bool]]:
        """The constants of each package a module imports a name from, by the name it imports."""
        found: dict[str, dict[str, bool]] = {}
        for node in (n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("aidd.")):
            package = self.packages.get(node.module.split(".")[1], {})
            for alias in node.names:
                found[alias.asname or alias.name] = package
        return found


class Scan:
    """The unproven values in the printed commands of one module's source."""

    def __init__(self, source: str, index: Index):
        self.tree = ast.parse(source)
        self.index, self.closed = index, index.closed
        # a name the module defines is its own; one it imports is the constant of the package it comes from
        self.constants = {
            **{k: v for imp in index.imported(self.tree).items() for k, v in [(imp[0], imp[1].get(imp[0], False))]},
            **module_constants([self.tree], index.known),
        }
        self.parent = {c: n for n in ast.walk(self.tree) for c in ast.iter_child_nodes(n)}
        self.imports_quoted = any(
            isinstance(n, ast.ImportFrom) and (n.module or "").endswith("command_names") and any(a.name == "quoted" and a.asname is None for a in n.names)
            for n in ast.walk(self.tree)
        )
        # the module's text templates, such as `_MISSING = "run `git -C {root} cat-file`"`, which `.format` fills elsewhere
        self.templates = {
            t.id: s.value.value
            for s in self.tree.body
            if isinstance(s, ast.Assign) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str)
            for t in s.targets
            if isinstance(t, ast.Name)
        }
        self.functions: dict[ast.AST | None, Function] = {}

    def function(self, node: ast.AST) -> Function:
        up: ast.AST | None = node
        while up is not None and not isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
            up = self.parent.get(up)
        return self.functions.setdefault(up, Function(up))

    def is_quoter(self, node: ast.expr) -> bool | None:
        """None for no quoter; else whether the call may return None."""
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            # by its full name, or by the name the module imported from `command_names`: another function called `quoted` proves nothing
            ours = ast.unparse(node.func) == "command_names.quoted" or (isinstance(node.func, ast.Name) and name == "quoted" and self.imports_quoted)
            if ours or (name in ("quote", "join") and ast.unparse(node.func).startswith("shlex.")):
                return QUOTERS[name]
        return None

    def safe(self, e: ast.expr, fn: Function, depth: int = 0) -> bool:
        if depth > 6:
            return False
        again = lambda x: self.safe(x, fn, depth + 1)  # noqa: E731
        if isinstance(e, ast.Constant):
            return True
        if self.is_quoter(e) is not None:
            return True
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "len":
            return True
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "str" and len(e.args) == 1:
            return again(e.args[0])
        if isinstance(e, ast.Subscript):  # one item of a safe list
            return again(e.value)
        if isinstance(e, (ast.ListComp, ast.GeneratorExp)):
            return again(e.elt)
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr == "join" and isinstance(e.func.value, ast.Constant):
            return all(again(a) for a in e.args)
        if isinstance(e, ast.IfExp):
            return again(e.body) and again(e.orelse)
        if isinstance(e, ast.BoolOp):
            return all(again(v) for v in e.values)
        if isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Add, ast.Mod)):
            return again(e.left) and again(e.right)
        if isinstance(e, ast.JoinedStr):
            return all(again(v.value) for v in e.values if isinstance(v, ast.FormattedValue))
        if isinstance(e, (ast.Tuple, ast.List, ast.Set)):
            return all(again(x) for x in e.elts)
        if isinstance(e, ast.Attribute):
            if e.attr.isupper():  # `config.MARKETPLACE`: the constant of the package or module named before the dot
                owner = e.value.id if isinstance(e.value, ast.Name) else ""
                return (self.index.packages.get(owner) or self.index.modules.get(owner) or {}).get(e.attr, False)
            return isinstance(e.value, ast.Name) and e.value.id == "args" and e.attr in self.closed
        if isinstance(e, ast.Name):
            return self.safe_name(e.id, fn, depth)
        return False

    def safe_name(self, name: str, fn: Function, depth: int) -> bool:
        if name in fn.params:
            ann = fn.params[name]
            typed = (isinstance(ann, ast.Name) and ann.id in NUMBER_TYPES) or (isinstance(ann, ast.Subscript) and ast.unparse(ann.value).endswith("Literal"))
            if not typed or not (name in fn.assigned or name in fn.looped):
                return typed
        if name in fn.assigned or name in fn.looped:  # every binding the function gives the name counts: a safe one never excuses a raw one
            values = fn.assigned.get(name, [])
            if any(v is None or not self.safe(v, fn, depth + 1) for v in values):
                return False
            # `quoted` gives None for a name it refuses: the function has to test the name before the command holds it
            if not (name in fn.tested or not any(self.is_quoter(v) for v in values if v is not None)):
                return False
            return all(isinstance(it, (ast.Tuple, ast.List, ast.Set)) and all(isinstance(x, ast.Constant) for x in it.elts) for it in fn.looped.get(name, []))
        return name.isupper() and self.constants.get(name, False)

    # What a string expression is made of: text, and the expressions that fill its holes.

    def parts(self, node: ast.expr, fn: Function, depth: int = 0) -> list[str | ast.expr]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            out: list[str | ast.expr] = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    out.append(str(v.value))
                else:
                    inner = v.value  # type: ignore[attr-defined]
                    built = self.built_here(inner, fn) if depth < 3 else None
                    out += self.parts(built, fn, depth + 1) if built is not None else [inner]
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.parts(node.left, fn, depth) + self.parts(node.right, fn, depth)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and self.template(node.left) is not None:
            given = list(node.right.elts) if isinstance(node.right, ast.Tuple) else [node.right]
            out = []
            for chunk in re.split(r"(%[-#0 +]*\d*(?:\.\d+)?[sdrfi%])", self.template(node.left) or ""):
                if chunk == "%%":
                    out.append("%")
                elif chunk.startswith("%") and len(chunk) > 1:
                    out.append(ast.Constant(0) if chunk[-1] in "dif" else given.pop(0) if given else node)
                else:
                    out.append(chunk)
            return out
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" and self.template(node.func.value) is not None:
            return self.format_parts(node)
        return [node]

    def template(self, node: ast.expr) -> str | None:
        """The text of a string literal, or of a module's constant that is one."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return self.templates.get(node.id) if isinstance(node, ast.Name) else None

    def format_parts(self, node: ast.Call) -> list[str | ast.expr]:
        out: list[str | ast.expr] = []
        auto = 0
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        for literal, field, _, _ in string.Formatter().parse(self.template(node.func.value) or ""):  # type: ignore[attr-defined]
            out.append(literal)
            if field is None:
                continue
            if field == "" and auto < len(node.args):
                out.append(node.args[auto])
                auto += 1
            elif field.isdigit() and int(field) < len(node.args):
                out.append(node.args[int(field)])
            elif field in keywords:
                out.append(keywords[field])
            else:
                out.append(node)  # a field this scan cannot resolve is not proven
        return out

    def built_here(self, e: ast.expr, fn: Function) -> ast.expr | None:
        """The string expression a name was assigned in this function, when it is assigned once from one."""
        if isinstance(e, ast.Name) and len(fn.assigned.get(e.id, [])) == 1:
            value = fn.assigned[e.id][0]
            if isinstance(value, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "format"
            ):
                return value
        return None

    def roots(self) -> list[ast.expr]:
        """The strings that are built from pieces, at the top of each chain of `+`."""
        found = []
        for n in ast.walk(self.tree):
            if (
                isinstance(n, ast.JoinedStr)
                or (isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Mod)))
                or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "format")
            ):
                up = self.parent.get(n)
                if isinstance(up, ast.BinOp) and isinstance(up.op, ast.Add):
                    continue
                if isinstance(up, ast.BinOp) and isinstance(up.op, ast.Mod) and up.left is n:
                    continue
                found.append(n)
        return found

    def findings(self) -> list[tuple[int, str, str]]:
        """Each unproven value in a printed command: the line, the command with its holes as `{}`, and the expression."""
        out = []
        for root in self.roots():
            fn = self.function(root)
            pieces = self.parts(root, fn)
            if not any(not isinstance(p, str) for p in pieces):
                continue
            text = "".join(p if isinstance(p, str) else HOLE for p in pieces)
            holes = [p for p in pieces if not isinstance(p, str)]
            for start, end, shown in self.commands(text):
                for hole in range(text[:start].count(HOLE), text[:end].count(HOLE)):
                    if not self.safe(holes[hole], fn):
                        out.append((root.lineno, shown.replace(HOLE, "{}"), ast.unparse(holes[hole])))
            for m in SPAN.finditer(text):  # a span that begins with words joined by a space is a whole command, whatever its program
                first = holes[text[: m.start(1)].count(HOLE)] if m.group(1).startswith(HOLE) else None
                made = (
                    [v for v in fn.assigned.get(first.id, []) if v is not None] if isinstance(first, ast.Name) else [first]
                )  # the join, or the name it was given
                if first is not None and any(self.joins_words(v) for v in made) and not self.safe(first, fn):
                    out.append((root.lineno, m.group(1).replace(HOLE, "{}"), ast.unparse(first)))
        return sorted(set(out))

    @staticmethod
    def joins_words(e: ast.expr) -> bool:
        """Whether `e` joins words with a space, as `" ".join(command)` does: the shape of a command built from a list."""
        func = e.func if isinstance(e, ast.Call) else None
        return isinstance(func, ast.Attribute) and func.attr == "join" and isinstance(func.value, ast.Constant) and func.value.value == " "

    @staticmethod
    def commands(text: str) -> list[tuple[int, int, str]]:
        """The stretches of `text` that are a command: a backtick span that starts with a program, and a shell command in
        prose up to the end of its clause. Each as its start, end, and words."""
        found = []
        inside = set()
        for m in SPAN.finditer(text):
            inside.update(range(m.start(), m.end()))
            words = m.group(1).split()
            if HOLE in m.group(1) and words and words[0] in PROGRAMS:
                found.append((m.start(1), m.end(1), m.group(1)))
        for m in re.finditer(r"(?<![\w`.-])(" + "|".join(SHELL_WORDS) + r")\s[^;(\n`]*", text):
            if m.start() not in inside and HOLE in m.group(0):
                found.append((m.start(), m.end(), m.group(0)))
        return found


@functools.cache
def build() -> tuple[list[Path], Index]:
    files = module_files()
    return files, Index(files, [ast.parse(p.read_text(encoding="utf-8")) for p in files])


@functools.cache
def unproven() -> dict[tuple[str, str, str], list[int]]:
    files, index = build()
    found: dict[tuple[str, str, str], list[int]] = {}
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        for line, command, expr in Scan(path.read_text(encoding="utf-8"), index).findings():
            found.setdefault((rel, command, expr), []).append(line)
    return found


def scan_text(source: str) -> list[str]:
    """The unproven expressions in a snippet, with this repository's constants and its parser's closed values."""
    return [expr for _, _, expr in Scan(source, build()[1]).findings()]


# The rule applied to a snippet each way: an expression that is raw text, and one each rule proves.
RAW = {
    "an f-string with a path": 'def f(path):\n    return f"`aidd status {path}`"',
    "a file name from a loop": 'def f(names):\n    return [f"`git rm -- {n}`" for n in names]',
    "a .format call": 'def f(path):\n    return "run `aidd validate {}`".format(path)',
    "a percent format": 'def f(path):\n    return "run `aidd validate %s`" % path',
    "a plus join": 'def f(path):\n    return "run `aidd validate " + path + "`"',
    "a path as_posix": 'def f(folder):\n    return f"`aidd explore {folder.as_posix()}`"',
    "a name quoted but never tested": 'def f(p):\n    w = command_names.quoted(p)\n    return f"`aidd status {w}`"',
    "a name built in the function from raw text": 'def f(p):\n    cmd = f"aidd status {p}"\n    return f"run `{cmd}`"',
    "a shell command with no backticks": 'def f(p):\n    return f"start with: mkdir -p {p} && cp -R a {p}"',
    "a constant that holds a quote": 'ODD = "a b; c"\ndef f():\n    return f"`aidd status {ODD}`"',
    "a parameter that is only a string": 'def f(n: str):\n    return f"`aidd status {n}`"',
    "an unresolved format field": 'def f(p):\n    return "`aidd status {0.name}`".format(p)',
    "a name set to a literal and then looped over raw text": 'def f(names):\n    n = "x"\n    return [f"`git rm -- {n}`" for n in names]',
    "another function named quoted": 'def f(p):\n    return f"`aidd status {design_checks.quoted(p)}`"',
    "a local function named quoted": 'def quoted(x):\n    return x\ndef f(p):\n    return f"`aidd status {quoted(p)}`"',
    "a command joined from a list with spaces": "def f(x):\n    return f\"tests: `{' '.join(x)}`\"",
    "a joined command given a name first": 'def f(x):\n    cmd = " ".join(x)\n    return f"tests: `{cmd}`"',
    "a name bound by with": 'def f(p):\n    with open(p) as name:\n        return f"`aidd status {name}`"',
    "a name bound by except": 'def f():\n    try:\n        pass\n    except OSError as exc:\n        return f"`aidd status {exc}`"',
    "a number parameter rebound to raw text": 'def f(n: int, names):\n    return [f"`aidd status {n}`" for n in names]',
}
SAFE = {
    "a quoted call": 'def f(p):\n    return f"`aidd status {command_names.quoted(p)}`"',
    "shlex.quote": 'def f(p):\n    return f"`aidd status {shlex.quote(p)}`"',
    "a name quoted and tested": 'def f(p):\n    w = command_names.quoted(p)\n    return f"`aidd status {w}`" if w else "by hand"',
    "a quoted call with a placeholder": "def f(p):\n    return f\"`aidd new spec {command_names.quoted(p) or '<ID>'}`\"",
    "a literal": "def f():\n    return f\"`aidd status {'x'}`\"",
    "a number": 'def f(n: int):\n    return f"`aidd test --retries {n}`"',
    "a length": 'def f(xs):\n    return f"`aidd test --retries {len(xs)}`"',
    "a percent d": 'def f(n):\n    return "`aidd test --retries %d`" % n',
    "a loop over literals": 'def f():\n    return [f"`aidd new {t} x`" for t in ("spec", "intent")]',
    "a constant with only plain characters": 'KEEP = "aidd-team"\ndef f():\n    return f"`claude plugin install {KEEP}`"',
    "a span with no program": 'def f(p):\n    return f"`{p}` is wrong"',
    "no interpolation in the span": 'def f(p):\n    return f"`aidd status` {p}"',
    "a command joined by shlex.join": 'def f(x):\n    return f"tests: `{shlex.join(x)}`"',
    "words joined by shlex.join inside a command": 'def f(x):\n    return f"`aidd test -- {shlex.join(x)}`"',
    "quoted, imported by its own name": "from aidd.kernel.command_names import quoted\ndef f(p):\n    return f\"`aidd status {quoted(p) or '<path>'}`\"",
}


class Rule(unittest.TestCase):
    def test_a_raw_value_in_a_printed_command_is_found(self):
        for label, source in RAW.items():
            with self.subTest(case=label):
                self.assertTrue(scan_text(source), f"the check missed: {source}")

    def test_a_value_a_rule_proves_is_not_found(self):
        for label, source in SAFE.items():
            with self.subTest(case=label):
                self.assertEqual(scan_text(source), [])


class TheSource(unittest.TestCase):
    def test_every_value_in_a_printed_command_is_proven_safe_or_accepted_with_its_reason(self):
        found = unproven()
        loose = {
            f"{rel}:{lines[0]}: `{command}` holds {expr}, raw text a shell may expand. Pass it through `command_names.quoted` "
            f"(and say it in words when that gives None), or describe it in words with no command"
            for (rel, command, expr), lines in sorted(found.items())
            if (rel, command, expr) not in ACCEPTED
        }
        self.assertEqual(sorted(loose), [])

    def test_every_accepted_site_still_exists_and_names_a_test_that_holds_it(self):
        found = unproven()
        self.assertEqual([k for k in ACCEPTED if k not in found], [], "take a row out of ACCEPTED when its site is fixed or gone")
        for key, (reason, held_by) in ACCEPTED.items():
            with self.subTest(site=key):
                self.assertTrue(reason.strip())
                path, _, name = held_by.partition("::")
                held = (ROOT / path).read_text(encoding="utf-8")
                self.assertTrue(all(part in held for part in name.split(".")), f"{held_by} holds {key[1]}")

    def test_the_programs_are_the_ones_the_source_suggests(self):
        """A program a span suggests in the source with an interpolation is in PROGRAMS, so a new one is not skipped."""
        files, _ = build()
        missing = set()
        for path in files:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.JoinedStr):
                    text = "".join(str(v.value) if isinstance(v, ast.Constant) else HOLE for v in node.values)
                    for m in SPAN.finditer(text):
                        words = m.group(1).split()
                        if (
                            HOLE in m.group(1)
                            and words
                            and re.fullmatch(r"[a-z][a-z0-9]*", words[0])
                            and words[0]
                            in {
                                "sudo",
                                "curl",
                                "wget",
                                "bash",
                                "sh",
                                "export",
                                "npx",
                                "pipx",
                                "brew",
                                "docker",
                                "kubectl",
                                "terraform",
                                "touch",
                                "sed",
                                "tar",
                                "ln",
                            }
                        ):
                            missing.add(words[0])
        self.assertEqual(sorted(missing), [], "add the program to PROGRAMS")


if __name__ == "__main__":
    unittest.main()
