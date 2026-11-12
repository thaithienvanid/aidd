"""The `jq` recipes docs/CLI.md gives for `aidd status --json`: each answers its question on a status the schema
accepts, so a recipe never drifts from the output it reads. Skipped where `jq` is missing."""

import json
import re
import shutil
import subprocess
import unittest

from helpers import ROOT

from aidd.kernel import json_schema

STATUS = {
    "schema_version": "1",
    "items": [
        {
            "id": "SPEC-3",
            "type": "spec",
            "title": "Refunds",
            "path": "specs/SPEC-3.md",
            "status": "ready",
            "group": "unstarted",
            "next": {"code": "spec.approve", "who": "person", "what": "approve SPEC-3"},
        },
        {
            "id": "SPEC-4",
            "type": "spec",
            "title": "Slugs",
            "path": "specs/SPEC-4.md",
            "status": "in_progress",
            "group": "started",
            "next": {"code": "spec.blocked", "who": "person", "what": "clear the blocker"},
        },
        {
            "id": "SPEC-5",
            "type": "spec",
            "title": "Search",
            "path": "specs/SPEC-5.md",
            "status": "approved",
            "group": "started",
            "next": {"code": "spec.approved", "who": "agent", "what": "implement SPEC-5"},
        },
    ],
    "due": [
        {
            "path": "specs/SPEC-1.md",
            "what": "flag new_cart is past its cleanup_due",
            "next": {"code": "flag.overdue", "who": "person", "what": "remove the flag"},
        }
    ],
}
# Each recipe's comment in docs/CLI.md, and what it prints on STATUS.
WANT = {
    "what waits on me": "SPEC-3\tapprove SPEC-3\nSPEC-4\tclear the blocker\n",
    "what is blocked": "SPEC-4\n",
    "what is past due": "specs/SPEC-1.md\tflag new_cart is past its cleanup_due\n",
    "one Spec's next step": "approve SPEC-3\n",
}


def recipes() -> dict[str, str]:
    """The `jq` program of each recipe line in docs/CLI.md, by its comment."""
    text = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
    found = re.findall(r"^aidd status --json \| jq -r '(.+)'\s+# (.+)$", text, re.M)
    return {comment.strip(): program for program, comment in found}


class StatusRecipeTests(unittest.TestCase):
    def test_the_fixture_is_a_status_the_schema_accepts(self):
        self.assertEqual(json_schema.validate(STATUS, "status.schema.json"), [])

    @unittest.skipUnless(shutil.which("jq"), "jq is not installed")
    def test_each_recipe_answers_its_question(self):
        found = recipes()
        self.assertEqual(sorted(found), sorted(WANT))
        for comment, program in found.items():
            with self.subTest(recipe=comment):
                done = subprocess.run(["jq", "-r", program], input=json.dumps(STATUS), capture_output=True, text=True, check=True)
                self.assertEqual(done.stdout, WANT[comment])


if __name__ == "__main__":
    unittest.main()
