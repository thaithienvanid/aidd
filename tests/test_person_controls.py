"""The checks that keep a person's decisions a person's: triage and owners are people, a handoff note names a role and
never an approval, and a path a file names stays inside the repository.

Each is a table of cases, so a new case is one line. The cases count findings, never pin their wording.
"""

import os
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd.docsgen import generate
from aidd.kernel import repo_paths
from aidd.risk import rule_set
from aidd.workitems import handoff_notes, triage

SUGGESTED = {"type": "spec", "suggested_by": "agent:product-manager"}


class TriageTests(unittest.TestCase):
    def test_suggested_work_waits_for_a_persons_triage(self):
        accepted = {"decision": "accepted", "by": "@lead"}
        cases = [
            # (front matter, proactive roles, how many findings)
            ({"type": "epic", "suggested_by": "agent:x", "status": "ready"}, None, 0),
            ({**SUGGESTED, "status": "draft"}, None, 0),
            ({**SUGGESTED, "status": "ready"}, None, 1),
            ({**SUGGESTED, "status": "ready", "triage": accepted}, None, 0),
            ({**SUGGESTED, "status": "ready", "triage": {"decision": "pending", "by": "@lead"}}, None, 1),
            ({**SUGGESTED, "status": "ready", "triage": {"decision": "accepted", "by": "agent:architect"}}, None, 1),
            ({**SUGGESTED, "status": "ready", "triage": {"decision": "declined", "by": "@lead"}}, None, 1),
            ({**SUGGESTED, "status": "draft", "triage": {"decision": "declined", "by": "@lead"}}, None, 1),
            ({**SUGGESTED, "status": "cancelled", "triage": {"decision": "declined", "by": "@lead"}}, None, 0),
            ({**SUGGESTED, "status": "draft"}, ["product-manager"], 0),
            ({**SUGGESTED, "status": "draft"}, [], 1),
            ({"type": "spec", "suggested_by": "@person", "status": "ready"}, None, 0),
        ]
        for data, proactive, n in cases:
            with self.subTest(data=data, proactive=proactive):
                self.assertEqual(len(triage.triage_errors(data, proactive=proactive)), n)

    def test_a_listed_bot_counts_as_an_agent(self):
        data = {**SUGGESTED, "status": "ready", "triage": {"decision": "accepted", "by": "@release-helper"}}
        self.assertEqual(triage.triage_errors(data), [])
        self.assertEqual(len(triage.triage_errors(data, {"release-helper"})), 1)

    def test_an_owner_and_a_flag_owner_are_people(self):
        cases = [
            ({"type": "spec", "owner": "@lead"}, 0),
            ({"type": "spec", "owner": "agent:developer"}, 1),
            ({"type": "spec", "owner": "@lead", "flags": [{"name": "f", "owner": "agent:sre"}, {"name": "g", "owner": "@ops"}, "x"]}, 1),
            ({"type": "epic", "owner": "@lead", "flags": [{"name": "f", "owner": "agent:sre"}]}, 0),
        ]
        for data, n in cases:
            with self.subTest(data=data):
                self.assertEqual(len(triage.owner_errors(data)), n)

    def test_bots_come_from_the_config_without_the_at_sign(self):
        class Cfg:
            def get(self, *keys, default=None):
                return ["@Deploy-Bot", "ci"] if keys == ("identities", "bots") else default

        self.assertEqual(triage.bots_of(Cfg()), {"deploy-bot", "ci"})
        self.assertEqual(triage.bots_of(None), set())


def note(body: str) -> str:
    return f"text\n\n```aidd-handoff\n{body}\n```\n"


FULL = "done: x\nnext: verifier\nneeds: none\nstopped_at: none"


class HandoffNoteTests(unittest.TestCase):
    def test_a_note_names_a_role_never_an_approval(self):
        cases = [
            (FULL, 0),
            (FULL + '\nstatus: approved\nspend: "1 run"', 0),
            ("done: x\nnext: verifier", 1),  # needs and stopped_at missing
            (FULL + "\nmood: fine", 1),  # a key aidd does not read
            (FULL.replace("verifier", "merge-approval"), 1),  # an approval is a person's, not a role's
            (FULL.replace("verifier", "the-boss"), 1),
            (FULL.replace("next: verifier", "next: [verifier]"), 1),
            (FULL + "\nstatus: shipped", 1),
            ("done: [unclosed", 1),  # not YAML
        ]
        for body, n in cases:
            with self.subTest(body=body):
                self.assertEqual(len(handoff_notes.handoff_warnings("specs/SPEC-1.md", note(body))), n)

    def test_every_block_is_read_in_order(self):
        text = note(FULL) + note("done: [unclosed")
        self.assertEqual([err == "" for _, _, err in handoff_notes.handoff_blocks(text)], [True, False])
        self.assertEqual(handoff_notes.handoff_blocks("no note here"), [])


class RepoPathTests(unittest.TestCase):
    def test_a_path_resolves_only_to_a_regular_file_inside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / "repo"
            (root / "docs").mkdir(parents=True)
            (root / "docs" / "a.md").write_text("a", encoding="utf-8")
            (base / "outside.md").write_text("o", encoding="utf-8")
            try:
                os.symlink(base / "outside.md", root / "docs" / "out.md")
                os.symlink(root / "docs" / "a.md", root / "docs" / "in.md")
            except OSError:
                self.skipTest("this system cannot make symbolic links")
            cases = [
                ("docs/a.md", root / "docs" / "a.md"),
                ("docs/in.md", root / "docs" / "a.md"),
                ("docs/out.md", None),
                ("../outside.md", None),
                ("docs", None),
                ("docs/missing.md", None),
                (str(root / "docs" / "a.md"), None),
                ("", None),
            ]
            for rel, want in cases:
                with self.subTest(rel=rel):
                    self.assertEqual(repo_paths.inside(root, rel), want)


class AskHoldsTests(unittest.TestCase):
    def test_the_platform_column_names_only_real_ask_actions(self):
        asking = {r.action for r in rule_set(None).rules if r.level == "ask"}
        self.assertLessEqual(set(generate.PLATFORM_HOLDS), asking)


if __name__ == "__main__":
    unittest.main()
