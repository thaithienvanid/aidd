"""The issue forms. The form for an agent that did not ask, or asked when it should not, asks for what a maintainer
needs to reproduce the mistake: the harness, the model and effort, a session excerpt, and the action and its rule.

The forms are GitHub issue forms (YAML). The test reads them line by line, in the subset the forms use, so it needs no
YAML library.
"""

import re
import unittest

from helpers import ROOT

FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
AGENT_FORM = FORMS / "agent-did-not-ask.yml"
BUG_FORM = FORMS / "bug.yml"


def fields(text: str) -> list[dict[str, str]]:
    """Each body element: its type, id, label, and whether it is required."""
    out: list[dict[str, str]] = []
    for block in re.split(r"(?m)^  - type: ", text.split("\nbody:\n", 1)[1])[1:]:
        template_type = block.split("\n", 1)[0].strip()
        found = {k: m.group(1).strip() for k in ("id", "label", "required") if (m := re.search(rf"(?m)^ +{k}: (.+)$", block))}
        out.append({"type": template_type, **found})
    return out


class AgentBrokeTheLoopFormTests(unittest.TestCase):
    def setUp(self):
        self.text = AGENT_FORM.read_text(encoding="utf-8")
        self.fields = {f["id"]: f for f in fields(self.text) if "id" in f}

    def test_it_is_an_issue_form(self):
        self.assertRegex(self.text, r"(?m)^name: .+")
        self.assertRegex(self.text, r"(?m)^description: .+")
        self.assertRegex(self.text, r"(?m)^labels: \[.*\]$")
        self.assertIn("\nbody:\n", self.text)

    def test_it_asks_what_reproduces_the_mistake(self):
        for key in ("harness", "model", "excerpt", "rule", "ask-rule", "what", "version"):
            self.assertIn(key, self.fields, key)
            self.assertEqual(self.fields[key].get("required"), "true", key)
        self.assertEqual(self.fields["excerpt"]["type"], "textarea")
        self.assertEqual(self.fields["ask-rule"]["type"], "dropdown")
        self.assertIn("`aidd risk", self.fields["rule"].get("label", "") + self.text)

    def test_it_warns_about_secrets_and_points_a_wrong_pass_to_private_reporting(self):
        self.assertEqual(fields(self.text)[0]["type"], "markdown")
        self.assertIn("secrets", self.text)
        self.assertIn("Report it privately", self.text)

    def test_the_bug_form_asks_for_what_a_crash_tells_a_person_to_send(self):
        """A crash names this form (aidd.cli.app.crash_next_step), with `aidd --version` and `aidd doctor --json`."""
        text = BUG_FORM.read_text(encoding="utf-8")
        found = {f["id"]: f for f in fields(text) if "id" in f}
        for key, words in (
            ("version", "`aidd --version`"),
            ("doctor", "`aidd doctor --json`"),
            ("risk", "`aidd risk --paths"),
            ("harness", "Harness and its version"),
            ("system", "Python"),
            ("what", "AIDD_DEBUG=1"),
        ):
            self.assertIn(key, found, key)
            self.assertIn(words, text, key)
        for key in ("version", "doctor", "harness", "system"):
            self.assertEqual(found[key].get("required"), "true", key)
        from aidd.cli import app

        self.assertTrue(app.BUG_REPORT_URL.endswith(f"/issues/new?template={BUG_FORM.name}"))

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
