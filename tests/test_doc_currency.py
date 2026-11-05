"""The docs stay current when a concept is added, renamed, or retired.

Generated blocks keep the tables and counts in step with the schemas (`aidd gen-docs --check`). Prose is kept in step by
two lists here. RETIRED holds wording a change made wrong: once a concept changes, its old wording goes in the list, and
no page may say it again. CONCEPTS holds each concept a reader must meet by name: each has a row in the glossary and a
mention in llms.txt, the page an agent reads first. Each name a schema defines needs a glossary row too, read from the
schema, never listed here. CONTRIBUTING.md ("Keeping the docs current") says when to add to
each list.
"""

from __future__ import annotations

import json
import re
import unittest

from helpers import ROOT

# Wording a change made wrong, and what replaced it. The text is matched as written, in every page aidd ships.
# Empty until the first release: before a tag, a rename is a plain change, with nothing to keep out (owner 2026-10-27).
RETIRED: dict[str, str] = {}

# Each concept a reader must meet by name: its glossary row (the first cell), and llms.txt mentions it.
CONCEPTS = (
    "Action",
    "Area",
    "Environment",
    "Risk rule",
    "Level",
    "Route",
    "Lane",
    "Spec approval",
    "Merge approval",
    "Profile",
    "Harness ask rule",
    "Session override",
    "Headless run",
    "Evidence",
    "Interface",
    "Test report",
    "Transcript",
    "Trace",
    "Orca payload",
    "Independent review",
    "Control register",
    "Improvement log",
    "Metrics dictionary",
    "Product brief",
    "Service card",
    "SRS",
    "Handoff note",
    "Record",
    "Recall",
    "Index",
    "Work-item page",
    "Local trunk",
    "Cost estimate",
    "Roll out",
    "Inner loop",
    "Outer loop",
    "Big goal",
    "Small goal",
    "Runbook",
    "Lead",
    "Deprecation calendar",
    "Support period",
    "Vulnerability policy",
    "DORA metrics",
    "DORA (EU) 2022/2554",
    "Release cooldown",
    "Release",
    "Dirty tree",
    "Rework",
    "Role placement",
    "Builder",
    "Product prototype",
    "Project template",
    "Product-level work",
    "Prototype tool",
    "Comment",
    "Fidelity pass",
    "Toolset",
    "Enabled",
    "Delivery team",
    "Spend cap",
)

PAGES = (
    sorted(ROOT.glob("*.md"))
    + [ROOT / "llms.txt"]
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

    def test_each_name_a_schema_defines_has_a_glossary_row(self):
        # R326: each name is read from the schema that owns it, so a new route, status, document type, record type,
        # role, change type, or question type needs a row. A row defines a name when its term is the name, when it is
        # the family's row and lists the name in backticks, or when it names a document type or a role as its own
        # (`` `authz` doc ``, `` `aidd new architecture` ``, `` the `verifier` role ``).
        def schema(name):
            return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

        common, roles, records = schema("common.schema.json")["$defs"], schema("roles.json"), schema("records.json")["types"]
        families = {  # the family's glossary row, and the names
            "Route": common["route"]["enum"],
            "Lane": common["lane"]["enum"],
            "Level": schema("risks.json")["levels"],
            "Spec status": common["status"]["enum"],
            "Container status": common["container_status"]["enum"],
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
