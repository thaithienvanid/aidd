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
# Before a tag, a rename is a plain change. The two work-item levels above the Spec folded into the Intent before the
# tag, and their words are listed so a leftover fails. In alphabetical order.
RETIRED: dict[str, str] = {
    "`/aidd-team:secure`": "`/aidd-team:review`, whose security engineer's findings get a challenge pass",
    "`/aidd-team:verify`": "`/aidd-team:review`, which runs the verifier, or `/aidd-team:rework` for a new head",
    "aidd trace": "aidd status <path or id>",
    "aidd-secure": "the review command, whose security engineer's findings get a challenge pass",
    "aidd-team:api-design": "aidd-team:apis-and-services, the pack that holds an API's contract",
    "aidd-verify": "the review command, which runs the verifier, or the rework command for a new head",
    "`api-design`": "the `apis-and-services` pack, which holds an API's contract",
    "Big goal": "an Intent",
    "build phase": "the Build stage",
    "Container status": "an Intent's status",
    "design phase": "the Design stage",
    "emergency lane": "the emergency route",
    "Epic": "a phase of an Intent",
    "fast lane": "no Spec",
    "Fast lane": "No Spec",
    "fast-lane": "with no Spec",
    "implement phase": "the Build stage",
    "Initiative": "an Intent",
    "`milestones`": "`phases`, the field",
    "Name the stage": "Name how far it got",
    "never gates": "never blocks",
    "rollout stage": "a rollout wave",
    "Small goal": "a phase",
    "spec lane": "Spec first",
    "Spec lane": "Spec first",
    "Spec phase": "the Design stage",
    "Spec stub": "a slice, until its work starts",
    "spec-lane": "Spec-first",
    "test phase": "the Test stage",
    "`trace`, ": "the command list without it: trace folded into `status <path or id>`",
}

# Each concept a reader must meet by name: its glossary row (the first cell), and llms.txt mentions it. In the glossary's
# order, alphabetical.
CONCEPTS = (
    "Acceptance test",
    "Action",
    "Agent round",
    "Area",
    "Branch protection",
    "Brief",
    "Brief coverage",
    "Builder",
    "Comfort check",
    "Comment",
    "Concern",
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
    "Gate",
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
    "Lane",
    "Lead",
    "Level",
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
    "Project template",
    "Prototype tool",
    "Recall",
    "Record",
    "Release",
    "Release cooldown",
    "Repository settings",
    "Reserved action",
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
    "Support period",
    "Test report",
    "Toolset",
    "Trace",
    "Transcript",
    "Vulnerability policy",
    "Work history",
    "Work-item page",
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


class RetiredWordingTests(unittest.TestCase):
    def test_no_page_says_what_a_change_retired(self):
        found = []
        for path in PAGES:
            # A glossary row's *Avoid:* note names the retired wording on purpose.
            text = "\n".join(line.split("*Avoid:*", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())
            found += [f"{path.relative_to(ROOT)}: {old!r} (now: {new})" for old, new in RETIRED.items() if old in text]
        self.assertEqual(found, [])


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
