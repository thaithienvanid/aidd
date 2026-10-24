"""The docs stay current when a concept is added, renamed, or retired.

Generated blocks keep the tables and counts in step with the schemas (`aidd gen-docs --check`). Prose is kept in step by
two lists here. RETIRED holds wording a change made wrong: once a concept changes, its old wording goes in the list, and
no page may say it again. CONCEPTS holds each concept a reader must meet by name: each has a row in the glossary and a
mention in llms.txt, the page an agent reads first. CONTRIBUTING.md ("Keeping the docs current") says when to add to
each list.
"""

from __future__ import annotations

import unittest

from helpers import ROOT

# Wording a change made wrong, and what replaced it. The text is matched as written, in every page aidd ships.
RETIRED: dict[str, str] = {}

# Each concept a reader must meet by name: its glossary row (the first cell), and llms.txt mentions it.
CONCEPTS = (
    "Cost estimate",
    "Preference key",
    "Skipped step",
    "Land",
    "Landed",
    "Local trunk",
    "Merge it",
    "Publish",
    "Roll out",
    "Three rings",
    "Outer loop",
    "Inner loop",
    "Four decisions",
    "Big goal",
    "Small goal",
    "Reaches",
    "Goal branch",
    "Integrate",
    "Outside change",
    "Launch",
    "Trunk-based flow",
    "Explore branch",
    "Advisory mode",
    "Enforce mode",
    "Runbook",
    "Always-on rules",
    "Decision records",
    "Changed-line limit",
    "Guard",
    "Gate",
    "Lead",
    "Change order",
    "Deprecation calendar",
    "Support period",
    "Vulnerability policy",
    "Rule of Two",
    "DORA metrics",
    "DORA (EU) 2022/2554",
    "Finding code",
    "Release cooldown",
    "Merge queue",
    "Release",
    "Dirty tree",
)

PAGES = (
    sorted(ROOT.glob("*.md"))
    + [ROOT / "llms.txt", ROOT / "specs" / "README.md"]
    + sorted(ROOT.glob("docs/**/*.md"))
    + sorted(ROOT.glob(".agents/skills/aidd/**/*.md"))
    + sorted(ROOT.glob("plugins/**/*.md"))
    + sorted(ROOT.glob("templates/**/*.md"))
    + sorted(ROOT.glob("schemas/*.json"))
)


class RetiredWordingTests(unittest.TestCase):
    def test_no_page_says_what_a_change_retired(self):
        found = []
        for path in PAGES:
            # A glossary row's *Avoid:* note names the retired wording on purpose.
            text = "\n".join(line.split("*Avoid:*", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())
            found += [f"{path.relative_to(ROOT)}: {old!r} (now: {new})" for old, new in RETIRED.items() if old in text]
        self.assertEqual(found, [])


class ConceptTests(unittest.TestCase):
    def test_each_concept_has_a_glossary_row(self):
        rows = {
            line.split("|")[1].strip().lower() for line in (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8").splitlines() if line.startswith("| ")
        }
        self.assertEqual([c for c in CONCEPTS if c.lower() not in rows], [])

    def test_llms_txt_names_each_concept(self):
        text = (ROOT / "llms.txt").read_text(encoding="utf-8").lower()
        self.assertEqual([c for c in CONCEPTS if c.lower() not in text], [])


if __name__ == "__main__":
    unittest.main()
