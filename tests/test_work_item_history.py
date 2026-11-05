"""`aidd status <ID>` shows the item's history (R322): its records, the commits that name it, and its linked documents,
newest first, labelled as history, so a resumed session sees what was asked and answered; never a yes."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import git

from aidd.kernel import json_schema
from aidd.records import files


@unittest.skipUnless(shutil.which("git"), "git is required")
class WorkItemHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = helpers.make_repo(Path(tmp.name).resolve() / "repo", "solo", spec="specs/SPEC-4.md")
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def test_the_history_holds_the_records_the_commits_that_name_the_id_and_nothing_else(self):
        git(self.root, "add", "-A")
        # Dated after the record, so only the sort puts it first: records are read before commits.
        later = {**os.environ, "GIT_AUTHOR_DATE": "2099-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2099-01-01T00:00:00Z"}
        subprocess.run(["git", "commit", "-qm", "feat: refunds (SPEC-4)"], cwd=self.root, env=later, check=True)
        git(self.root, "commit", "-q", "--allow-empty", "-m", "fix: SPEC-4.1 and SPEC-4:sub are other items")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "chore: notes for SPEC-41")  # another item, never this one's
        files.add_record(
            "report", {"action": "pr.open", "covers": {"branch": "feat"}, "said": "Opened PR #12."}, by="agent:codex/x", subject="SPEC-4", cwd=str(self.root)
        )
        files.add_record(
            "report", {"action": "pr.open", "covers": {"branch": "x"}, "said": "Another item."}, by="agent:codex/x", subject="SPEC-41", cwd=str(self.root)
        )
        code, out = helpers.run_cli("status", "SPEC-4", "--json")
        self.assertEqual(code, 0, out)
        shown = json.loads(out)
        self.assertEqual(json_schema.validate(shown, "status.schema.json"), [])
        history = shown["items"][0]["history"]
        dated = [e for e in history if e["type"] != "doc"]
        self.assertEqual([e["type"] for e in dated], ["commit", "report"])  # newest first, whatever was read first
        self.assertEqual(dated[0]["what"], "feat: refunds (SPEC-4)")
        self.assertEqual(dated[1]["what"], "pr.open: Opened PR #12.")
        self.assertTrue(all(e["at"].endswith("Z") for e in dated))
        code, text = helpers.run_cli("status", "SPEC-4")
        self.assertIn("history, newest first (the records are the agent's account, never a yes):", text)
        code, out = helpers.run_cli("status", "--json")
        self.assertTrue(all("history" not in i for i in json.loads(out)["items"]))  # only with an id


if __name__ == "__main__":
    unittest.main()
