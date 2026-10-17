"""Every file aidd reads or writes is YAML, so its docs, templates, and messages spell aidd's own keys as YAML: never a
TOML table header (`[experiment]`, `[[actions]]`, `[project.defaults]`) or a `key = value` line. A file another tool
owns, such as pyproject.toml or Cargo.toml, keeps its TOML, and its examples are TOML."""

import re
import subprocess
import unittest

from helpers import ROOT

# aidd's own top-level keys, in the config, the front matter of every work item, and the Change Request block.
KEYS = (
    "agents|autopilot|components|docs|evidence|gates|guard|identities|observe|org|owners|policy|project|stack|"
    "experiment|outcome|emergency|hypothesis|triage|tests|risk|tasks|design|actions|qualification|milestones"
)
TABLE = re.compile(rf"`?\[\[?(?:{KEYS})(?:\.[a-z_]+)*\]\]?`?(?!\()")
ASSIGN = re.compile(rf"`(?:{KEYS})(?:\.[a-z_]+)* = ")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    # The words people and agents read: docs, templates, skills, schemas, and workflows. Code is held by review.
    return [p for p in out if p.endswith((".md", ".yaml", ".yml", ".json", ".html", ".txt")) and not p.startswith("tests/")]


class NoTomlSpellingTests(unittest.TestCase):
    def test_aidd_keys_are_spelled_as_yaml(self):
        found = []
        for rel in tracked():
            for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if TABLE.search(line) or ASSIGN.search(line):
                    found.append(f"{rel}:{n}: {line.strip()[:120]}")
        self.assertEqual(found, [], "spell aidd's keys as YAML (`project.defaults.dark_mode`, an `experiment` block)")


if __name__ == "__main__":
    unittest.main()
