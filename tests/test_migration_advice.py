"""A migrated repository gives the advice of the one checked by hand: the same `aidd risk` answers for a table of paths and
commands, the same `aidd status`, and the same `aidd delegate check`, with the delegation's date still deciding. The old shape
cannot give advice, because a closed schema stops at its first retired name; this compares the migrated files with the ones
written by hand (tests/fixtures/migration/today)."""

import json
import os
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_here
from migration_fixture import CONFIG, FIXTURES, WRITTEN, Repo, commit

from aidd.setup import migrating


def advice(root: Path) -> list[str]:
    """What aidd advises in `root` for a table of paths (one under a project rule's `when_changed`, one outside it) and commands, its
    status, and what `aidd validate` finds in the work items and documents, the Specs with a retired change type among them."""
    paths = ("src/billing/charge.py", "docs/README.md", ".github/workflows/ci.yml", "migrations/001.sql", "src/app.py", "web/index.html")
    commands = ("git push origin main", "rm -rf build", "kubectl apply -f x.yaml")
    return (
        [aidd_here("risk", "--paths", path, "--json", cwd=root).stdout for path in paths]
        + [aidd_here("risk", "--command", command, cwd=root).stdout for command in commands]
        + [aidd_here("status", "--json", cwd=root).stdout]
        + [aidd_here("validate", "--json", "specs", "proposals", "docs/runbooks", "docs/postmortems", cwd=root).stdout]
    )


class TheAdviceAfterTheMigration(Repo):
    def test_the_advice_of_the_migrated_tree_is_the_advice_of_the_one_checked_by_hand(self):
        self.upgrade(yes=True)
        migrated = advice(self.root)
        by_hand = self.clone()
        for rel in WRITTEN:
            shutil.copyfile(FIXTURES / "today" / rel, by_hand / rel)
        self.assertEqual(migrated, advice(by_hand))
        self.assertTrue(all(migrated))
        self.assertIn("no-secrets", migrated[4], "a rule held for src/** applies there")
        self.assertNotIn("no-secrets", migrated[5], "and not outside it")

    def delegation(self, root: Path, review: str) -> dict:
        """What `aidd delegate check` says of a push, with the delegation's review date set to `review`."""
        cfg = root / CONFIG
        cfg.write_text(re.sub(r"(review_by|review_due): \"[0-9-]+\"", rf'\1: "{review}"', cfg.read_text(encoding="utf-8")), encoding="utf-8")
        migrating.apply(root, migrating.plan(root))
        head = commit(root)
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):  # the one session a delegation decides in
            done = aidd_here("delegate", "check", "--action", "git.push", "--command", "git push origin feat", "--head", head, "--json", cwd=root)
        return {k: v for k, v in json.loads(done.stdout.replace(head, "HEAD")).items() if k != "record"}

    def test_a_delegation_decides_as_before_and_its_date_still_counts(self):
        decided = {}
        for review in ("2020-01-01", "2999-01-01"):
            migrated = self.delegation(self.clone(), review)
            by_hand = self.clone()
            for rel in WRITTEN:
                shutil.copyfile(FIXTURES / "today" / rel, by_hand / rel)
            self.assertEqual(migrated, self.delegation(by_hand, review), review)
            decided[review] = {r["code"] for r in migrated["reasons"]}
        self.assertIn("delegation_review_due", decided["2020-01-01"] - decided["2999-01-01"], "the date moved to review_due and still decides")


if __name__ == "__main__":
    unittest.main()
