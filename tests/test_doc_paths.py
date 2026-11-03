"""What the repository's prose and configs say about aidd's own code still exists: the source paths they name, the
module file names they mention, and the Python they tell people to run.

A module that moves leaves behind every page that named it (REVIEW.md's list of the files the gate depends on,
CODEOWNERS, CONTRIBUTING's gate-rule row) and every snippet that imports it (`from aidd import knowledge` in the
standards workflow an adopter copies). The source and the tests are left out: code that names a path fails on its own.
"""

from __future__ import annotations

import importlib
import re
import unittest

from helpers import ROOT, repo_files

SRC = ROOT / "src" / "aidd"

# `src/aidd/gates.py`, `/src/aidd/verify.py` (CODEOWNERS), or `aidd/cli.py`, but not `acme_aidd/cli.py`.
SOURCE_PATH = re.compile(r"(?<![\w.-])/?(?:src/)?aidd/((?:\w+/)*\w+\.py)\b")
# A file name alone, as REVIEW.md lists them: `rules.py`, `rulebook.py`.
BARE_FILE = re.compile(r"(?<![\w./-])(\w+\.py)\b")
# aidd's module file names when this test was written; a page that names one bare means aidd's file.
MODULE_FILES = frozenset(
    "agentmodels autopilot autopilotcheck bands changerecord cli codeowners config contextpack depdiff detect digest docs "
    "evals explore export ext gates github gitlab gitutil globs guard harnesses hooks http importers inputs intake knowledge "
    "lease local localctx mcp metrics model nextstep observe owners packs policy project proposal pyz repo report resources "
    "rollup rulebook rules runner schema speclog standards state upkeep util verify views workitems".split()
)
FROM_IMPORT = re.compile(r"\bfrom (aidd(?:\.\w+)*) import (\w+(?:\s*,\s*\w+)*)")
IMPORT_AIDD = re.compile(r"\bimport (aidd(?:\.\w+)*)\b(?! *[\w.]*/)")


def prose_files() -> dict[str, str]:
    """Every tracked text file outside src/ and tests/, by path."""
    out = {}
    for rel in repo_files():
        if rel.startswith(("src/", "tests/")) or rel.endswith(".py"):
            continue
        try:
            out[rel] = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
    return out


def module_basenames() -> set[str]:
    return {p.name for p in SRC.rglob("*.py")}


class DocPathTests(unittest.TestCase):
    def test_every_source_path_named_exists(self):
        missing = sorted(
            {f"{rel}: {m.group(0)}" for rel, text in prose_files().items() for m in SOURCE_PATH.finditer(text) if not (SRC / m.group(1)).is_file()}
        )
        self.assertEqual(missing, [])

    def test_every_module_file_named_alone_exists(self):
        here = module_basenames()
        missing = sorted(
            {
                f"{rel}: {name}"
                for rel, text in prose_files().items()
                for name in BARE_FILE.findall(text)
                if name.removesuffix(".py") in MODULE_FILES and name not in here
            }
        )
        self.assertEqual(missing, [], "a page names a module file aidd no longer has; name where the code lives now")

    def test_every_python_snippet_imports_what_exists(self):
        bad = []
        snippets = 0
        for rel, text in prose_files().items():
            for line in text.replace("\\\n", " ").splitlines():
                bound: dict[str, object] = {}
                for m in FROM_IMPORT.finditer(line):
                    snippets += 1
                    try:
                        module = importlib.import_module(m.group(1))
                    except ImportError:
                        bad.append(f"{rel}: no module {m.group(1)}")
                        continue
                    for name in re.split(r"\s*,\s*", m.group(2)):
                        try:
                            bound[name] = importlib.import_module(f"{m.group(1)}.{name}")
                        except ImportError:
                            if not hasattr(module, name):
                                bad.append(f"{rel}: {m.group(1)} has no {name}")
                for m in IMPORT_AIDD.finditer(line):
                    snippets += 1
                    try:
                        bound[m.group(1).split(".")[0]] = importlib.import_module(m.group(1).split(".")[0])
                        importlib.import_module(m.group(1))
                    except ImportError:
                        bad.append(f"{rel}: no module {m.group(1)}")
                # A call or a value in parentheses (`knowledge.markdown(`, `aidd.__version__)`), not a file (`knowledge.md`).
                for name, module in bound.items():
                    for attr in re.findall(rf"(?<![\w.]){re.escape(name)}\.(\w+)(?=[()])", line):
                        if not hasattr(module, attr):
                            bad.append(f"{rel}: {name}.{attr} does not exist")
        self.assertGreater(snippets, 5, "the scan found no snippet: the pattern no longer matches how pages import aidd")
        self.assertEqual(sorted(set(bad)), [])


if __name__ == "__main__":
    unittest.main()
