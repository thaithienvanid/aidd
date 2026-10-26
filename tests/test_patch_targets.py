"""Every patch a test makes still reaches the code it means to replace.

`mock.patch.object(module, "name", ...)` replaces one binding: the name in that module's namespace. Code that looks the
name up there (the module's own functions, or `module.name` elsewhere) sees the replacement; code that bound the name
itself (`from aidd.module import name`) does not. When a function moves to another module, a patch of its old home
keeps passing while the real function runs: the real git, the network, or this machine's home directory. These tests
read every patch of an aidd module in tests/ (helpers.py's global ones too) and check, statically, that it still lands:

- the patched name is defined in that module (a function, a class, or an assignment), or the module imports it and
  uses it, so the patch replaces the module's own lookup; a module that only re-exports a name is never patched;
- no other aidd module imports the name from it by name, which would bypass the patch (the rule in CONTRIBUTING: import
  modules, not names, for anything a test patches). The few that do today are listed and may only go;
- a patch of a standard-library module reached through an aidd module (`patch.object(gitutil.subprocess, "run")`)
  still goes through a module the aidd module binds, and that module looks the name up as `subprocess.run`, never
  imports it by name;
- a patch of an aidd class's attribute (`patch.object(dialects.Antigravity, "normalize")`) names an attribute the class
  or a class it inherits from defines.

`helpers.py`'s hermetic patch of `repo.installed_harnesses` is also checked as it runs: every aidd function that calls
`installed_harnesses` resolves the hermetic replacement.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import os
import sys
import tempfile
import types
import unittest
from functools import cache
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT

SRC = ROOT / "src" / "aidd"
TESTS = ROOT / "tests"

# Imports by name of a name tests patch in the module it comes from, as they were when this test was written. The patch
# misses the importer; the tests that patch these names do not reach it. The list may only get shorter.
KNOWN_BYPASSES: frozenset[tuple[str, str, str]] = frozenset()


def _module_names(tree: ast.AST) -> dict[str, str]:
    """The names a test file binds to aidd modules: `from aidd import repo`, `from aidd import config as cfgmod`."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and (node.module == "aidd" or node.module.startswith("aidd.")):
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if _is_module(full):
                    out[alias.asname or alias.name] = full
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("aidd.") and alias.asname:
                    out[alias.asname] = alias.name
    return out


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _resolve(expr: ast.expr, names: dict[str, str]) -> object | None:
    if isinstance(expr, ast.Name):
        if expr.id in names:
            return importlib.import_module(names[expr.id])
        return helpers if expr.id == "helpers" else None
    if isinstance(expr, ast.Attribute):
        base = _resolve(expr.value, names)
        return None if base is None else getattr(base, expr.attr, None)
    return None


@cache
def _scan() -> tuple[tuple[tuple[str, int, str, str], ...], tuple[tuple[str, int, str, str, str], ...], tuple[tuple[str, int, type, str], ...]]:
    """Every patch in tests/ of something aidd owns, in three kinds: an aidd module's name, a standard-library module's
    name reached through an aidd module, and an aidd class's attribute."""
    modules, stdlib, classes = [], [], []
    for path in sorted(TESTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = _module_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = ast.unparse(node.func)
            if func.endswith("patch.object") and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                target, name = _resolve(node.args[0], names), node.args[1].value
                if isinstance(target, types.ModuleType) and target.__name__.startswith("aidd"):
                    modules.append((path.name, node.lineno, target.__name__, name))
                elif isinstance(target, types.ModuleType) and isinstance(node.args[0], ast.Attribute):
                    owner = _resolve(node.args[0].value, names)
                    if isinstance(owner, types.ModuleType) and owner.__name__.startswith("aidd"):
                        stdlib.append((path.name, node.lineno, owner.__name__, node.args[0].attr, name))
                elif isinstance(target, type) and target.__module__.startswith("aidd"):
                    classes.append((path.name, node.lineno, target, name))
            elif func.endswith("patch") and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                dotted = node.args[0].value
                if dotted.startswith("aidd."):
                    module, _, name = dotted.rpartition(".")
                    modules.append((path.name, node.lineno, module, name))
    return tuple(modules), tuple(stdlib), tuple(classes)


def patch_targets() -> tuple[tuple[str, int, str, str], ...]:
    """(test file, line, aidd module, name) for every `patch.object(<aidd module>, "name")` and `patch("aidd.m.name")`."""
    return _scan()[0]


def stdlib_patch_targets() -> tuple[tuple[str, int, str, str, str], ...]:
    """(test file, line, aidd module, binding, name) for every `patch.object(<aidd module>.<binding>, "name")` whose
    binding is a module outside aidd, such as `gitutil.subprocess`."""
    return _scan()[1]


def class_patch_targets() -> tuple[tuple[str, int, type, str], ...]:
    """(test file, line, class, name) for every `patch.object(<aidd class>, "name")`, such as `dialects.Antigravity`."""
    return _scan()[2]


def aidd_modules() -> list[str]:
    """Every module of the aidd package, by name; `aidd.__main__` runs the CLI when imported, so it is left out."""
    out = []
    for path in sorted(SRC.rglob("*.py")):
        parts = path.relative_to(SRC.parent).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if parts[-1] != "__main__":
            out.append(name)
    return out


@cache
def module_tree(module: str) -> ast.Module:
    return ast.parse(inspect.getsource(importlib.import_module(module)))


def defined(module: str) -> set[str]:
    """The names a module binds at its top level by def, class, or assignment."""
    out: set[str] = set()
    for node in module_tree(module).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                out |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
    return out


def imported_and_used(module: str, name: str) -> bool:
    """The module imports `name` and looks it up itself, so a patch of the module's binding replaces its own calls."""
    tree = module_tree(module)
    imported = any(
        (alias.asname or alias.name).split(".")[0] == name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    )
    used = any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load) for n in ast.walk(tree))
    return imported and used


@cache
def imports_by_name() -> dict[tuple[str, str], frozenset[str]]:
    """(module, name) -> the aidd modules that bind that name by importing it from that module, at any depth. An import
    under `if TYPE_CHECKING:` (a door's list for the type checker) never runs, so it binds nothing a patch could miss."""
    found: dict[tuple[str, str], set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC.parent).with_suffix("")
        me = ".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)
        package = me if path.name == "__init__.py" else me.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        typing_only = {
            id(n)
            for block in ast.walk(tree)
            if isinstance(block, ast.If) and ast.unparse(block.test) == "TYPE_CHECKING"
            for stmt in block.body
            for n in ast.walk(stmt)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or id(node) in typing_only:
                continue
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                source = f"{base}.{node.module}" if node.module else base
            else:
                source = node.module or ""
            if source.startswith("aidd"):
                for alias in node.names:
                    found.setdefault((source, alias.name), set()).add(me)
    return {k: frozenset(v) for k, v in found.items()}


class PatchTargetTests(unittest.TestCase):
    def test_the_scan_finds_the_patches(self):
        # A change in how tests import aidd must not make this scan silently find nothing.
        self.assertGreater(len(patch_targets()), 150)
        self.assertIn(("helpers.py", "aidd.setup.adoption", "installed_harnesses"), {(f, m, n) for f, _, m, n in patch_targets()})

    def test_every_patched_name_is_defined_or_used_where_it_is_patched(self):
        bad = []
        for file, line, module, name in patch_targets():
            if not hasattr(importlib.import_module(module), name):
                bad.append(f"{file}:{line}: {module} has no {name}")
            elif name not in defined(module) and not imported_and_used(module, name):
                bad.append(f"{file}:{line}: {module}.{name} is neither defined nor used in {module}; patch the module that defines and calls it")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_no_module_imports_a_patched_name_past_its_patch(self):
        bypasses = set()
        for _file, _line, module, name in patch_targets():
            bypasses |= {(importer, module, name) for importer in imports_by_name().get((module, name), ()) if importer != module}
        new = sorted(bypasses - KNOWN_BYPASSES)
        self.assertEqual(new, [], "import the module, not the name: a test's patch of the module misses these importers")


class StdlibAndClassPatchTests(unittest.TestCase):
    """A patch of a standard-library module through an aidd module, and of an aidd class's attribute, still lands."""

    def test_the_scan_finds_them(self):
        self.assertGreaterEqual(len(stdlib_patch_targets()), 20)
        self.assertIn(("aidd.kernel.git", "subprocess", "run"), {(m, b, n) for _, _, m, b, n in stdlib_patch_targets()})
        self.assertGreaterEqual(len(class_patch_targets()), 3)

    def test_each_stdlib_patch_goes_through_a_module_the_aidd_module_binds_and_looks_up(self):
        bad = []
        for file, line, module, binding, name in stdlib_patch_targets():
            bound = vars(importlib.import_module(module)).get(binding)
            tree = module_tree(module)
            if not isinstance(bound, types.ModuleType):
                bad.append(f"{file}:{line}: {module} no longer binds the module {binding}; patch the module that uses {name}")
                continue
            if not hasattr(bound, name):
                bad.append(f"{file}:{line}: {bound.__name__} has no {name}")
            looked_up = any(
                isinstance(n, ast.Attribute) and n.attr == name and isinstance(n.value, ast.Name) and n.value.id == binding and isinstance(n.ctx, ast.Load)
                for n in ast.walk(tree)
            )
            if not looked_up:
                bad.append(f"{file}:{line}: {module} never reads {binding}.{name}, so the patch reaches none of its code")
            by_name = [
                n.lineno
                for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module == bound.__name__ and any(alias.name == name for alias in n.names)
            ]
            if by_name:
                bad.append(f"{file}:{line}: {module} imports {name} from {bound.__name__} by name (line {by_name[0]}), past the patch")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_each_class_patch_names_an_attribute_the_class_defines(self):
        bad = []
        for file, line, cls, name in class_patch_targets():
            owners = [k.__qualname__ for k in cls.__mro__ if k is not object and name in vars(k)]
            if not owners:
                bad.append(f"{file}:{line}: {cls.__module__}.{cls.__qualname__} defines no {name}, nor does a class it inherits from")
        self.assertEqual(bad, [], "\n".join(bad))


class HermeticPatchTests(unittest.TestCase):
    """helpers.py replaces `installed_harnesses` for the whole run, so no test reads this machine's home directory."""

    def test_every_caller_resolves_the_hermetic_replacement(self):
        hermetic = helpers._installed_harnesses
        callers = []
        for module_name in aidd_modules():
            module = importlib.import_module(module_name)
            for node in ast.walk(module_tree(module_name)):
                if isinstance(node, ast.Name) and node.id == "installed_harnesses" and isinstance(node.ctx, ast.Load):
                    callers.append(module_name)
                    self.assertIs(vars(module).get("installed_harnesses"), hermetic, f"{module_name} calls an installed_harnesses the hermetic patch misses")
                elif isinstance(node, ast.Attribute) and node.attr == "installed_harnesses" and isinstance(node.value, ast.Name):
                    owner = vars(module).get(node.value.id)
                    if isinstance(owner, types.ModuleType):
                        callers.append(module_name)
                        self.assertIs(owner.installed_harnesses, hermetic, f"{module_name} calls {owner.__name__}.installed_harnesses, which the patch misses")
        self.assertTrue(callers, "nothing in aidd calls installed_harnesses: the hermetic patch in helpers.py guards nothing")

    @unittest.skipIf(os.name == "nt", "a POSIX home directory and an executable without a suffix")
    def test_init_never_sees_this_machine(self):
        # A home with Claude Code's folder and a PATH with its binary: the hermetic probe still finds no agent.
        from aidd.setup import adoption

        with tempfile.TemporaryDirectory() as tmp:
            home, bin_dir = Path(tmp) / "home", Path(tmp) / "bin"
            (home / ".claude").mkdir(parents=True)
            bin_dir.mkdir()
            (bin_dir / "claude").write_text("#!/bin/sh\n", encoding="utf-8")
            (bin_dir / "claude").chmod(0o755)
            self.assertIn("claude-code", helpers.real_installed_harnesses(home=home, path=str(bin_dir)))
            with mock.patch.dict("os.environ", {"HOME": str(home), "PATH": str(bin_dir)}):
                self.assertEqual(vars(sys.modules[adoption.init.__module__])["installed_harnesses"](), [])


if __name__ == "__main__":
    unittest.main()
