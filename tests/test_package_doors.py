"""Every package door (aidd.kernel.doors) says the same thing to the type checker and at run time, and every name it
exports reaches the child that defines it.

A door's `__init__.py` lists its exports twice: as `from aidd.p.child import name as export` under `TYPE_CHECKING`, for
mypy, and as the map it gives `doors.exports`, for `__getattr__`. These tests read both from the source and check:

- the two lists agree, name for name and child for child, and `__all__` names each export;
- each export resolves at run time to the very object its child defines, and `dir()` lists it;
- no child module is named like an export: importing `aidd.p.name` sets the attribute `name` on the package, which would
  hide the export of the same name;
- a patch of the defining child reaches a caller that goes through the door;
- a door holds no code: no `__init__.py` defines a function or a class, and a door's only statements are its
  docstring, its two imports, `__all__`, and the TYPE_CHECKING block, so every body lives in a child (CONTRIBUTING,
  "Doors", and docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

SRC = ROOT / "src" / "aidd"


def _doors() -> dict[str, Path]:
    """Each package whose __init__.py calls doors.exports, by dotted name."""
    out = {}
    for init in sorted(SRC.rglob("__init__.py")):
        text = init.read_text(encoding="utf-8")
        if "doors.exports(" in text:
            parts = init.parent.relative_to(SRC.parent).parts
            out[".".join(parts)] = init
    return out


def _declared(init: Path) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]], list[str]]:
    """(the TYPE_CHECKING exports, the run-time map, `__all__`), each export as name -> (child, defined name). A child is
    named by its path under the package (`rules.gate_run`), from the import that binds the export."""
    tree = ast.parse(init.read_text(encoding="utf-8"))
    package = ".".join(init.parent.relative_to(SRC.parent).parts)
    typed: dict[str, tuple[str, str]] = {}
    runtime: dict[str, tuple[str, str]] = {}
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            names = list(ast.literal_eval(node.value))
        if isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING":
            for stmt in node.body:
                assert isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.module.startswith(package + "."), ast.unparse(stmt)
                for alias in stmt.names:
                    typed[alias.asname or alias.name] = (stmt.module.removeprefix(package + "."), alias.name)
            for call in ast.walk(ast.Module(body=node.orelse, type_ignores=[])):
                if isinstance(call, ast.Call) and ast.unparse(call.func) == "doors.exports":
                    for key, value in ast.literal_eval(call.args[1]).items():
                        child, _, defined = value.partition(":")
                        runtime[key] = (child, defined or key)
    return typed, runtime, names


class DoorTests(unittest.TestCase):
    def test_the_scan_finds_the_doors(self):
        self.assertIn("aidd.docsgen", _doors())

    def test_both_lists_and_all_agree(self):
        for package, init in _doors().items():
            typed, runtime, names = _declared(init)
            with self.subTest(package=package):
                self.assertTrue(runtime, "a door exports at least one name")
                self.assertEqual(typed, runtime, "the TYPE_CHECKING names and the doors.exports map must match")
                self.assertEqual(sorted(set(runtime) - set(names)), [], "__all__ names every export")

    def test_every_export_is_the_childs_own_object(self):
        for package, init in _doors().items():
            module = importlib.import_module(package)
            _, runtime, _ = _declared(init)
            for name, (child, defined) in runtime.items():
                with self.subTest(package=package, name=name):
                    owner = importlib.import_module(f"{package}.{child}")
                    self.assertIs(getattr(module, name), getattr(owner, defined))
                    self.assertIn(name, dir(module))
            with self.assertRaises(AttributeError):
                module.no_such_export  # noqa: B018

    def test_no_child_module_is_named_like_an_export(self):
        for package, init in _doors().items():
            _, runtime, _ = _declared(init)
            children = {p.stem for p in init.parent.glob("*.py")} | {p.name for p in init.parent.iterdir() if (p / "__init__.py").is_file()}
            with self.subTest(package=package):
                self.assertEqual(sorted(children & set(runtime)), [])

    def test_a_door_name_is_its_childs_name(self):
        """A door exports each name under the name its child defines it by, so one search finds both."""
        for package, init in _doors().items():
            typed, runtime, _ = _declared(init)
            with self.subTest(package=package):
                self.assertEqual({k: d for k, (_, d) in runtime.items() if d != k}, {})
                self.assertEqual({k: d for k, (_, d) in typed.items() if d != k}, {})

    def test_every_package_but_kernel_has_a_door(self):
        packages = {p.parent.name for p in SRC.glob("*/__init__.py")}
        self.assertEqual(sorted(packages - {d.rpartition(".")[2] for d in _doors() if d.count(".") == 1}), ["kernel"])

    def test_no_package_init_defines_a_function_or_a_class(self):
        for init in sorted(SRC.rglob("__init__.py")):
            tree = ast.parse(init.read_text(encoding="utf-8"))
            defined = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            with self.subTest(init=str(init.relative_to(SRC.parent))):
                self.assertEqual(defined, [], "move it into a child; the door only names it")

    def test_a_door_is_only_its_names(self):
        allowed = {"from __future__ import annotations", "from typing import TYPE_CHECKING"}
        for package, init in _doors().items():
            tree = ast.parse(init.read_text(encoding="utf-8"))
            _, runtime, names = _declared(init)
            with self.subTest(package=package):
                self.assertEqual(sorted(names), sorted(runtime), "__all__ names exactly the exports")
                for i, node in enumerate(tree.body):
                    docstring = i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                    names_list = isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == ["__all__"]
                    door = isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING"
                    self.assertTrue(docstring or names_list or door or ast.unparse(node) in allowed, ast.unparse(node)[:80])

    def test_a_patch_of_the_child_reaches_a_caller_through_the_door(self):
        from aidd import docsgen
        from aidd.docsgen import pack_budget

        with mock.patch.object(pack_budget, "pack_sizes_and_problems", lambda: ({}, ["patched"])):
            self.assertEqual(docsgen.pack_sizes_and_problems(), ({}, ["patched"]))
        self.assertIs(docsgen.pack_sizes_and_problems, pack_budget.pack_sizes_and_problems)


if __name__ == "__main__":
    unittest.main()
