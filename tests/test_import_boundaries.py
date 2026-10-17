"""aidd's own module boundaries: `.importlinter` holds, and its list of known wrong-way imports only gets shorter.

`.importlinter` groups the modules into the layers of the package layout and lists, in `ignore_imports`, each import
that breaks them (none since the packages were done). Import Linter fails on a new wrong-way import and on an ignore
that no longer matches, so a fixed import must leave the list. This test adds the other half: no line may join it. The
contracts run when Import Linter is importable and skip otherwise; CI's lint toolchain installs it hash-pinned
(.github/requirements/lint.txt) and sets REQUIRE_IMPORT_LINTER=1, so the check cannot skip there.
"""

from __future__ import annotations

import configparser
import contextlib
import io
import os
import unittest

from helpers import ROOT

try:
    from importlinter.cli import lint_imports
except ImportError:  # pragma: no cover - exercised where Import Linter is not installed
    lint_imports = None

CONFIG = ROOT / ".importlinter"

# The wrong-way imports the baseline holds now: none (35 when it was written, the last fixed when the packages were
# done). The file may never add one.
BASELINE: frozenset[str] = frozenset()


def contracts() -> dict[str, configparser.SectionProxy]:
    parser = configparser.ConfigParser()
    parser.read_string(CONFIG.read_text(encoding="utf-8"))
    return {name.removeprefix("importlinter:contract:"): parser[name] for name in parser.sections() if name.startswith("importlinter:contract:")}


def lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


class BaselineTests(unittest.TestCase):
    def test_the_layers_contract_covers_every_module(self):
        layers = contracts()["layers"]
        self.assertEqual(layers["type"], "layers")
        listed = {m.strip() for line in lines(layers["layers"]) for m in line.replace("|", ":").split(":")}
        modules = {p.stem for p in (ROOT / "src" / "aidd").glob("*.py") if p.stem != "__init__"}
        modules |= {p.name for p in (ROOT / "src" / "aidd").iterdir() if (p / "__init__.py").is_file()}
        self.assertEqual(modules - listed, set(), "a module no layer names is checked by no contract")

    def test_the_known_wrong_way_imports_never_grow(self):
        ignored = [line for contract in contracts().values() for line in lines(contract.get("ignore_imports", ""))]
        self.assertEqual(len(ignored), len(set(ignored)), "an ignore_imports line is listed twice")
        added = sorted(set(ignored) - BASELINE)
        self.assertEqual(added, [], "fix the import instead of adding it to ignore_imports")


@unittest.skipIf(lint_imports is None and os.environ.get("REQUIRE_IMPORT_LINTER") != "1", "Import Linter is not installed")
class ContractsTests(unittest.TestCase):
    def test_every_contract_is_kept(self):
        if lint_imports is None:
            raise AssertionError("REQUIRE_IMPORT_LINTER=1, but Import Linter is not importable")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = lint_imports(config_filename=str(CONFIG), no_cache=True)
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
