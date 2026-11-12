"""A template names the role that owns its document, and says whether the document is frozen or living, as `schemas/roles.json` does.

`graph.documents` in the roles registry owns both facts for each document type. Every table below is read from it and from
the templates `aidd new` writes, so a new template is covered with no new code, and a role that does not exist, such as
"the agile coach", fails here.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT

from aidd.kernel import resources
from aidd.workitems import authoring

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
ROLES = resources.load_json("roles.json")
DOCUMENTS = ROLES["graph"]["documents"]
# A template that holds a document of another type's living form: the component's test plan is the test plan, kept living.
FORMS = {"test-plan-living.md": ("test-plan", "living")}
# The role a template names is the registry's id, spoken: `product-manager` is "the product manager", and `sre` is "the SRE".
SPOKEN = {"sre": "SRE"}


def spoken(role: str) -> str:
    return SPOKEN.get(role, role.replace("-", " "))


def templates() -> dict[str, tuple[str, str | None]]:
    """Each template file `aidd new` writes for a document type of the registry, as {file: (type, lifecycle it is written as)}."""
    found: dict[str, tuple[str, str | None]] = {}
    for doc_type, name in authoring.DOC_TEMPLATES.items():
        found[name] = (doc_type, None)
    for doc_type, files in authoring.repo_docs().items():
        found.update({tpl: (doc_type, None) for _, tpl in files if tpl.endswith(".md")})
    found["runbook.md"] = ("runbook", None)
    for name, (doc_type, lifecycle) in FORMS.items():
        found[name] = (doc_type, lifecycle)
    return found


# How a template says who owns its document. "The X keeps it", "which the X writes", and "owned by the X" name any word, so a role that
# does not exist fails. "The X's plan" and "Owner: TODO: the X" are said of other things too ("the project's guide"), so they count only
# when X is a role.
ROLE = r"(SRE|[a-z]+(?: [a-z]+)?)"
CLAIMS = (
    re.compile(rf"\b[Tt]he {ROLE} (?:writes and keeps|keeps and writes|writes|keeps|owns|maintains) (?:this|it|the (?:runbook|file))\b"),
    re.compile(rf"\bwhich the {ROLE} writes\b"),
    re.compile(rf"\bowned by the {ROLE}\b"),
    re.compile(rf"\bThe {ROLE} is the only agent that writes it\b"),
)
ROLE_ONLY_CLAIMS = (re.compile(rf"<!-- The {ROLE}'s "), re.compile(rf"\bOwner: TODO: the {ROLE}\b"))
STATES = re.compile(r"\b(frozen|living)\b", re.I)


def squeezed(path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


class OwnerTests(unittest.TestCase):
    def test_the_registry_is_read(self):
        self.assertGreater(len(templates()), 25)
        self.assertLessEqual({t for t, _ in templates().values()}, set(DOCUMENTS), "a template of a type the registry lacks")

    def test_each_owner_a_template_names_is_the_registrys(self):
        names = {spoken(r) for r in ROLES["roles"]}
        for name, (doc_type, _) in sorted(templates().items()):
            owner = spoken(DOCUMENTS[doc_type]["written_by"])
            text = squeezed(ASSETS / name)
            said = [who for claim in CLAIMS for who in claim.findall(text)]
            said += [who for claim in ROLE_ONLY_CLAIMS for who in claim.findall(text) if who in names]
            for who in said:
                with self.subTest(template=name, who=who):
                    self.assertIn(who, names, f"{name} names {who!r}, which is no role of schemas/roles.json")
                    self.assertEqual(who, owner, f"{name} says {who}, and graph.documents.{doc_type}.owner is {owner}")

    def test_each_lifecycle_a_template_states_is_the_registrys(self):
        for name, (doc_type, form) in sorted(templates().items()):
            text = squeezed(ASSETS / name)
            header = text.split(" ## ", 1)[0]
            said = STATES.search(header)
            if not said:
                continue
            with self.subTest(template=name):
                self.assertEqual(said.group(1).lower(), form or DOCUMENTS[doc_type]["lifecycle"], f"{name}: {header[:200]}")

    def test_the_claims_find_the_owners_the_templates_state(self):
        found = {n for n in templates() if any(c.search(squeezed(ASSETS / n)) for c in (*CLAIMS, *ROLE_ONLY_CLAIMS))}
        self.assertGreater(len(found), 15, "the patterns above no longer read the templates")


if __name__ == "__main__":
    unittest.main()
