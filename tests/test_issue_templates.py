"""The issue forms. "An agent broke the loop" asks for what a maintainer needs to reproduce an agent's mistake: the
harness, the model, the effort, how full the context was, a session excerpt, and the rule it broke.

The forms are GitHub issue forms (YAML). The test reads them line by line, in the subset the forms use, so it needs no
YAML library.
"""

import re
import unittest

from helpers import ROOT

FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
AGENT_FORM = FORMS / "agent-broke-the-loop.yml"


def fields(text: str) -> list[dict[str, str]]:
    """Each body element: its type, id, label, and whether it is required."""
    out: list[dict[str, str]] = []
    for block in re.split(r"(?m)^  - type: ", text.split("\nbody:\n", 1)[1])[1:]:
        kind = block.split("\n", 1)[0].strip()
        found = {k: m.group(1).strip() for k in ("id", "label", "required") if (m := re.search(rf"(?m)^ +{k}: (.+)$", block))}
        out.append({"type": kind, **found})
    return out


class AgentBrokeTheLoopFormTests(unittest.TestCase):
    def setUp(self):
        self.text = AGENT_FORM.read_text(encoding="utf-8")
        self.fields = {f["id"]: f for f in fields(self.text) if "id" in f}

    def test_it_is_an_issue_form(self):
        self.assertRegex(self.text, r"(?m)^name: An agent broke the loop$")
        self.assertRegex(self.text, r"(?m)^description: .+")
        self.assertRegex(self.text, r"(?m)^labels: \[.*\]$")
        self.assertIn("\nbody:\n", self.text)

    def test_it_asks_what_reproduces_the_mistake(self):
        for key in ("harness", "model", "effort", "context", "excerpt", "rule", "what", "version"):
            self.assertIn(key, self.fields, key)
        for key in ("harness", "model", "excerpt", "rule", "what", "version"):
            self.assertEqual(self.fields[key].get("required"), "true", key)
        self.assertEqual(self.fields["excerpt"]["type"], "textarea")
        self.assertEqual(self.fields["effort"]["type"], "dropdown")

    def test_it_warns_about_secrets_and_points_a_wrong_pass_to_private_reporting(self):
        self.assertEqual(fields(self.text)[0]["type"], "markdown")
        self.assertIn("secrets", self.text)
        self.assertIn("Report it privately", self.text)

    def test_every_form_has_unique_ids_and_a_label_for_each(self):
        for path in sorted(FORMS.glob("*.yml")):
            if path.name == "config.yml":
                continue
            with self.subTest(form=path.name):
                found = fields(path.read_text(encoding="utf-8"))
                ids = [f["id"] for f in found if "id" in f]
                self.assertEqual(len(ids), len(set(ids)), ids)
                for f in found:
                    if f["type"] != "markdown":
                        self.assertIn("id", f, f)
                        self.assertIn("label", f, f)


if __name__ == "__main__":
    unittest.main()
