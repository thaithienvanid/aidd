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

    def test_the_page_reads_each_items_newest_five_in_one_records_read_and_one_git_log(self):
        from unittest import mock

        from aidd import workitems
        from aidd.kernel import git as kernel_git

        for n in range(7):
            git(self.root, "commit", "-q", "--allow-empty", "-m", f"feat: step {n} (SPEC-4)")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "chore: notes for SPEC-41")
        files.add_record(
            "report", {"action": "pr.open", "covers": {"branch": "x"}, "said": "Another item."}, by="agent:codex/x", subject="SPEC-41", cwd=str(self.root)
        )
        reads, logs = [], []
        real_read, real_run = files.read_records, kernel_git.run

        def read(*args, **kw):
            reads.append(kw)
            return real_read(*args, **kw)

        def run(args, *a, **kw):
            logs.append(args[0])
            return real_run(args, *a, **kw)

        with mock.patch("aidd.records.files.read_records", read), mock.patch("aidd.kernel.git.run", run):
            found = workitems.work_items_history(self.root, ["SPEC-4", "SPEC-41", "SPEC-9"])
        self.assertEqual((len(reads), logs.count("log")), (1, 1), "one records read and one git log, whatever the number of items")
        self.assertEqual(len(found["SPEC-4"]), 5)
        self.assertEqual(sorted(e["type"] for e in found["SPEC-41"]), ["commit", "report"], "SPEC-41's own entries, and none of SPEC-4's")
        self.assertEqual(found["SPEC-9"], [])
        self.assertEqual(found["SPEC-4"], sorted(found["SPEC-4"], key=lambda e: e["at"], reverse=True))

    def test_the_page_shows_the_history_and_the_json_stays_small(self):
        git(self.root, "commit", "-q", "--allow-empty", "-m", "feat: refunds (SPEC-4)")
        code, out = helpers.run_cli("status", "--html")
        self.assertEqual(code, 0, out)
        page = (self.root / ".aidd" / "views" / "status-work.html").read_text(encoding="utf-8")
        self.assertIn("feat: refunds (SPEC-4)", page)
        self.assertRegex(page, r"<span class=\"muted\">\d{1,2} [A-Z][a-z]{2}, \d\d:\d\d</span>", "a time a person reads")
        code, out = helpers.run_cli("status", "--json")
        self.assertTrue(all("history" not in i for i in json.loads(out)["items"]), "the same files give the same answer, with no history")


if __name__ == "__main__":
    unittest.main()
