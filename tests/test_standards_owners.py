"""Standards (`standards`): the team's own rules and the library standards it adopted, read by the roles they name before a step.

`aidd owners` lists them by role with their type and marks each enforced by a test or guidance; `aidd owners --json --changed`
gives an agent exactly the ones to load; `aidd doctor` warns about a missing document, an unknown role, and an
`enforced_by` that names no test; a child config adds standards and cannot drop or redefine a parent's.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.setup import doctor_checks
from aidd.knowledge import owners
from aidd.kernel import documents, json_schema

HEAD = 'aidd_version: "1.0.0"\nprofile: team\n'
OWNERS = 'owners:\n  approvers: ["@org/leads"]\ntests:\n  - name: unit\n    command: [make, test]\n  - name: lint\n    command: [make, lint]\n'
STANDARDS = (
    "standards:\n  - name: api-errors\n    path: docs/standards/api-errors.md\n    roles: [developer, reviewer]\n"
    '    when_changed: ["src/api/**"]\n    enforced_by: [lint]\n'
    '  - name: writing\n    path: docs/standards/writing.md\n    roles: ["*"]\n'
)


def load(text: str = STANDARDS) -> config.Config:
    return config.load_text(HEAD + OWNERS + text)


class SchemaTests(unittest.TestCase):
    def check(self, entry: str) -> list[str]:
        return json_schema.validate(
            documents.parse_yaml(HEAD + "standards:\n  - " + entry.rstrip("\n").replace("\n", "\n    ") + "\n", "c"), "config.schema.json"
        )

    def test_a_standard_names_a_document_and_the_roles_that_read_it(self):
        self.assertEqual(self.check("name: a\npath: docs/a.md\nroles: [developer]\n"), [])
        self.assertTrue(any("roles" in e for e in self.check("name: a\npath: docs/a.md\n")))
        self.assertTrue(any("path" in e for e in self.check('name: a\npath: "docs/*.md"\nroles: ["*"]\n')))  # a document, not a glob
        self.assertTrue(any("roles" in e for e in self.check("name: a\npath: docs/a.md\nroles: []\n")))
        self.assertTrue(any("roles" in e for e in self.check("name: a\npath: docs/a.md\nroles: [Developer]\n")))
        self.assertTrue(any("enforced_by" in e for e in self.check('name: a\npath: docs/a.md\nroles: ["*"]\nenforced_by: [Unit Tests]\n')))
        self.assertTrue(any("unknown field" in e for e in self.check('name: a\npath: docs/a.md\nroles: ["*"]\nseverity: high\n')))


class MergeTests(unittest.TestCase):
    def test_a_child_adds_standards_and_cannot_redefine_a_parents(self):
        parent = HEAD + 'owners:\n  approvers: ["@x"]\nstandards:\n  - name: security\n    path: org/security.md\n    roles: ["*"]\n'
        child = (
            HEAD
            + 'extends: [{path: p.yaml}]\nowners:\n  approvers: ["@x"]\n'
            + "standards:\n  - name: security\n    path: docs/lax.md\n    roles: [developer]\n"
            + "  - name: api\n    path: docs/api.md\n    roles: [developer]\n"
        )
        cfg = config.load_text(child, prefetched={"p.yaml": parent})
        self.assertEqual({s["name"]: s["path"] for s in cfg.standards}, {"security": "org/security.md", "api": "docs/api.md"})
        self.assertTrue(any("standards 'security' is set by a parent config" in w for w in cfg.warnings), cfg.warnings)

    def test_a_child_that_names_none_keeps_the_parents(self):
        parent = HEAD + 'owners:\n  approvers: ["@x"]\nstandards:\n  - name: security\n    path: org/security.md\n    roles: ["*"]\n'
        cfg = config.load_text(HEAD + 'extends: [{path: p.yaml}]\nowners:\n  approvers: ["@x"]\n', prefetched={"p.yaml": parent})
        self.assertEqual([s["name"] for s in cfg.standards], ["security"])
        self.assertEqual(config.load_text(HEAD).standards, [])


class OwnersTests(unittest.TestCase):
    def test_each_role_lists_the_standards_it_reads(self):
        r = owners.owners_view(load())
        by_role = {a["role"]: a["standards"] for a in r["agents"]}
        self.assertEqual(by_role["developer"], ["api-errors", "writing"])
        self.assertEqual(by_role["verifier"], ["writing"])  # `*`: every role
        self.assertEqual({s["name"]: s["enforcement"] for s in r["standards"]}, {"api-errors": "enforced by lint", "writing": "guidance"})
        self.assertEqual({s["name"]: s["type"] for s in r["standards"]}, {"api-errors": "opinionated", "writing": "opinionated"})

    def test_when_changed_narrows_the_standards_to_the_change(self):
        cfg = load()
        by_role = lambda changed: {a["role"]: a["standards"] for a in owners.owners_view(cfg, changed=changed)["agents"]}  # noqa: E731
        self.assertEqual(by_role(["src/api/orders.py"])["developer"], ["api-errors", "writing"])
        self.assertEqual(by_role(["web/app.tsx"])["developer"], ["writing"])
        standards = owners.config_standards(cfg)
        self.assertEqual([s["name"] for s in owners.standards_for(standards, "reviewer", ["src/api/x.py"])], ["api-errors", "writing"])
        self.assertEqual([s["name"] for s in owners.standards_for(standards, "sre", ["src/api/x.py"])], ["writing"])

    def test_the_markdown_marks_each_standard_enforced_or_guidance(self):
        text = owners.owners_markdown(owners.owners_view(load(STANDARDS + "  - name: x\n    path: x.md\n    roles: [intern]\n    enforced_by: [ghost]\n")))
        self.assertNotIn("House standards", text)
        section = text.split("## Standards: read before your step", 1)[1]
        rows = [tuple(c.strip() for c in ln.strip("|").split("|")) for ln in section.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
        self.assertEqual(
            rows,
            [
                ("every role", "`writing`", "opinionated", "[docs/standards/writing.md](docs/standards/writing.md)", "every change", "guidance"),
                (
                    "`developer`",
                    "`api-errors`",
                    "opinionated",
                    "[docs/standards/api-errors.md](docs/standards/api-errors.md)",
                    "`src/api/**`",
                    "enforced by lint",
                ),
                (
                    "`reviewer`",
                    "`api-errors`",
                    "opinionated",
                    "[docs/standards/api-errors.md](docs/standards/api-errors.md)",
                    "`src/api/**`",
                    "enforced by lint",
                ),
                ("`intern`", "`x`", "opinionated", "[x.md](x.md)", "every change", "enforced by ghost (no `tests` entry named ghost)"),
            ],
        )
        self.assertIn("Unknown roles in standards: intern.", text)
        self.assertNotIn("House standards", owners.owners_markdown(owners.owners_view(load(""))))
        self.assertNotIn("## Standards: read before your step", owners.owners_markdown(owners.owners_view(load(""))))

    def test_the_command_gives_agents_the_standards_as_json(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            (Path(d) / ".aidd").mkdir()
            (Path(d) / ".aidd" / "config.yaml").write_text(HEAD + OWNERS + STANDARDS, encoding="utf-8")
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            run = subprocess.run(
                [sys.executable, "-m", "aidd", "owners", "--json", "--changed", "web/app.tsx"], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            out = json.loads(run.stdout)
            self.assertEqual({a["role"]: a["standards"] for a in out["agents"]}["developer"], ["writing"])
            self.assertEqual([s["name"] for s in out["standards"]], ["api-errors", "writing"])


class DoctorTests(unittest.TestCase):
    def doctor(self, standards: str, files=("docs/standards/api-errors.md", "docs/standards/writing.md")) -> list[tuple[str, str]]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(HEAD + OWNERS + standards, encoding="utf-8")
            for f in files:
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_text("# standard\n", encoding="utf-8")
            return [x for x in doctor_checks.doctor(root) if "standards" in x[1]]

    def test_a_sound_set_of_standards_is_ok(self):
        self.assertEqual(self.doctor(STANDARDS), [("ok", "standards: 2 (2 opinionated), 1 enforced by tests; `aidd owners` lists them by role")])
        self.assertEqual(self.doctor(""), [])

    def test_a_missing_document_an_unknown_role_and_an_unknown_test_are_warned(self):
        found = self.doctor(
            "standards:\n  - name: api\n    path: docs/standards/api.md\n    roles: [developer, intern]\n    enforced_by: [lint, contract]\n",
            files=(),
        )
        self.assertEqual(
            found,
            [
                ("warn", "standards 'api': docs/standards/api.md does not exist, so no agent can read it"),
                ("warn", "standards 'api': unknown role intern; name aidd-team roles (`aidd owners` lists them) or *"),
                ("warn", "standards 'api': enforced_by names no `tests` entry: contract; until one runs, the standard is guidance"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
