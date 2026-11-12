"""The docs stay current when a concept is added, renamed, or retired.

Generated blocks keep the tables and counts in step with the schemas (`aidd gen-docs --check`). Prose is kept in step by
two lists here. RETIRED holds wording a change made wrong after the 1.0.0 release: once a concept changes, its old wording
goes in the list, and no page may say it again. CONCEPTS holds each concept a reader must meet by name: each has a row in
the glossary and a mention in llms.txt, the page an agent reads first. Each name a schema defines needs a glossary row
too, read from the schema, never listed here. CONTRIBUTING.md ("Keeping the docs current") says when to add to each list.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config

# Wording a change made wrong after the 1.0.0 release, and what replaced it. The text is matched as written, in every page
# aidd ships. A rename or a retirement lists its old wording at once, so a leftover fails. In alphabetical order. Before the
# release, a rename is a plain change swept with `git grep`, so the list starts empty.
RETIRED: dict[str, str] = {}

# Each concept a reader must meet by name: its glossary row (the first cell), and llms.txt mentions it. In the glossary's
# order, alphabetical.
CONCEPTS = (
    "Acceptance test",
    "Action",
    "Agent round",
    "Area",
    "Backfill Spec",
    "Branch protection",
    "Builder",
    "Citation",
    "Comfort check",
    "Comment",
    "Concern",
    "Confidence",
    "Control register",
    "Cost estimate",
    "Cost per pass",
    "Delegate",
    "Delegate answer",
    "Delegate check",
    "Delegation",
    "Delivery team",
    "Deprecation calendar",
    "Digest",
    "Dirty tree",
    "DORA (EU) 2022/2554",
    "DORA metrics",
    "Enabled",
    "Environment",
    "Evidence",
    "Fidelity pass",
    "Finding code",
    "Frozen test",
    "Gate",
    "Governance layer",
    "Handoff note",
    "Harness ask rule",
    "Headless run",
    "Held-out case",
    "Improvement log",
    "Independent review",
    "Index",
    "Inner loop",
    "Intent",
    "Intent agreement",
    "Interface",
    "Lead",
    "Level",
    "Limit",
    "Living doc",
    "Local trunk",
    "Merge approval",
    "Metrics dictionary",
    "Orca payload",
    "Outer loop",
    "Phase",
    "Product brief",
    "Product prototype",
    "Product-level work",
    "Profile",
    "Project shape",
    "Project template",
    "Prototype tool",
    "Read form",
    "Recall",
    "Record",
    "Release",
    "Release cooldown",
    "Repository settings",
    "Request",
    "Request coverage",
    "Reserved action",
    "Retired name",
    "Rework",
    "Risk rule",
    "Role operation",
    "Role placement",
    "Roll out",
    "Route",
    "Runbook",
    "Service card",
    "Session override",
    "Slice",
    "Spec approval",
    "Spend cap",
    "SRS",
    "Stable branch",
    "Stage",
    "Stop code",
    "Stop rule",
    "Support period",
    "Test report",
    "Toolset",
    "Trace",
    "Trailer",
    "Transcript",
    "Typed document",
    "Verification report",
    "Vulnerability policy",
    "Work history",
    "Work item",
    "Work-item page",
    "Writing level",
)

PAGES = (
    sorted(ROOT.glob("*.md"))
    + [ROOT / "llms.txt"]
    + sorted(ROOT.glob("docs/**/*.md"))
    + sorted(ROOT.glob(".agents/skills/aidd/**/*.md"))
    + sorted(ROOT.glob("plugins/**/*.md"))
    + sorted(ROOT.glob("templates/**/*.md"))
    + sorted(ROOT.glob("schemas/*.json"))
    + sorted(ROOT.glob("docs/**/*.html"))
    + sorted(p for p in ROOT.glob("evals/**/*") if p.suffix in (".yaml", ".json", ".md"))
)


def retired_found(pages: list[Path], retired: dict[str, str]) -> list[str]:
    """Each retired wording a page still says. A glossary row's *Avoid:* note names the retired wording on purpose."""
    found = []
    for path in pages:
        text = "\n".join(line.split("*Avoid:*", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())
        shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
        found += [f"{shown}: {old!r} (now: {new})" for old, new in retired.items() if old in text]
    return found


_GENERATED_BLOCK = re.compile(r"<!-- aidd:gen [^>]*-->.*?<!-- aidd:end -->", re.S)


def hand_lists_found(pages: list[Path], labels: list[str]) -> list[str]:
    """Each page line that names every label outside a generated block: a hand list that drifts when one label changes."""
    found = []
    for path in pages:
        text = _GENERATED_BLOCK.sub("", path.read_text(encoding="utf-8"))
        shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
        found += [f"{shown}:{number}" for number, line in enumerate(text.splitlines(), 1) if all(label in line for label in labels)]
    return found


class HandListTests(unittest.TestCase):
    def test_no_hand_list_names_every_agent_aidd_wires(self):
        # README and CHANGELOG render `list:harnesses`, so a rename in harnesses.py reaches every list in one `aidd gen-docs`.
        labels = [h.label for h in config.HARNESSES.values()]
        self.assertEqual(hand_lists_found(PAGES, labels), [])


class RetiredWordingTests(unittest.TestCase):
    def test_no_page_says_what_a_change_retired(self):
        self.assertEqual(retired_found(PAGES, RETIRED), [])

    def test_a_page_that_says_a_retired_wording_fails_and_an_avoid_note_does_not(self):
        sample = {"sample old name": "the sample new name"}
        with tempfile.TemporaryDirectory() as tmp:
            says, avoids, clean = (Path(tmp) / name for name in ("says.md", "avoids.md", "clean.md"))
            says.write_text("The sample old name is still here.\n", encoding="utf-8")
            avoids.write_text("| Term | A thing. *Avoid:* sample old name. |\n", encoding="utf-8")
            clean.write_text("The sample new name is here.\n", encoding="utf-8")
            self.assertEqual(retired_found([says, avoids, clean], sample), ["says.md: 'sample old name' (now: the sample new name)"])


def alphabetical(term: str) -> str:
    """Where a term sorts in the glossary: by its letters, ignoring case and code marks."""
    return term.strip("`").lower()


class ConceptTests(unittest.TestCase):
    def test_the_glossary_and_concepts_are_alphabetical(self):
        # The glossary groups its terms by where a reader meets them, one table a section, each table alphabetical.
        sections = re.split(r"^## ", (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8"), flags=re.M)[1:]
        self.assertGreater(len(sections), 1, "the glossary lost its sections")
        for section in sections:
            terms = [line.split("|")[1].strip() for line in section.splitlines() if line.startswith("| ")][2:]  # the header and its rule
            self.assertEqual(terms, sorted(terms, key=alphabetical), f"add a glossary row where its letters place it: {section.splitlines()[0]}")
        self.assertEqual(list(CONCEPTS), sorted(CONCEPTS, key=alphabetical), "add a concept where its letters place it")

    def test_each_concept_has_a_glossary_row(self):
        rows = {
            line.split("|")[1].strip().lower() for line in (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8").splitlines() if line.startswith("| ")
        }
        self.assertEqual([c for c in CONCEPTS if c.lower() not in rows], [])

    def test_llms_txt_names_each_concept(self):
        text = (ROOT / "llms.txt").read_text(encoding="utf-8").lower()
        self.assertEqual([c for c in CONCEPTS if c.lower() not in text], [])

    def test_each_name_a_schema_defines_has_a_glossary_row(self):
        # Each name is read from the schema that owns it, so a new route, status, document type, record type,
        # role, change type, or question type needs a row. A row defines a name when its term is the name, when it is
        # the family's row and lists the name in backticks, or when it names a document type or a role as its own
        # (`` `authz-matrix` doc ``, `` `aidd new architecture` ``, `` the `verifier` role ``).
        def schema(name):
            return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

        common, roles, records = schema("common.schema.json")["$defs"], schema("roles.json"), schema("records.json")["types"]
        families = {  # the family's glossary row, and the names
            "Route": common["route"]["enum"],
            "Level": schema("risks.json")["levels"],
            "Spec status": common["status"]["enum"],
            "Status group": common["status_group"]["enum"],
            "Change type": common["change_type"]["enum"],
            "Record": list(records),
            "Question type": records["decision"]["data"]["properties"]["question"]["properties"]["type"]["enum"],
            None: [*roles["loop"]["documents"], *roles["roles"]],
        }
        rows = {}
        for line in (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("| "):
                term, meaning = line.split("|")[1:3]
                rows[term.strip()] = meaning

        def norm(text):
            return re.sub(r"[\s_-]+", " ", text.replace("`", "").lower()).strip()

        def defined(family, name):
            own = re.compile(rf"`{re.escape(name)}` (?:doc|role)\b|`aidd new {re.escape(name)}[ `]")
            return (
                any(norm(term) == norm(name) for term in rows)
                or (family in rows and f"`{name}`" in rows[family])
                or any(own.search(meaning) for meaning in rows.values())
            )

        self.assertEqual([f"{family or 'a row of its own'}: {n}" for family, names in families.items() for n in names if not defined(family, n)], [])


if __name__ == "__main__":
    unittest.main()
