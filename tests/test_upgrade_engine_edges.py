"""What the row engine behind `aidd upgrade` does at the edges of a file, proved with rows made for the tests (tests/test_upgrade_engine.py
holds the rules of a row): a file the engine cannot edit whole, the files it reads and the ones it never follows, what it prints, and
what it never rewrites.

Invariants. (1) A file or a place the engine cannot edit whole stays as it is, and a line names the way out; nothing is half moved.
(2) The engine reads the files a row can reach (the config and its parents in the repository, each work item and typed document where it
lies, an edited copy of a library standard) and no other: not a link, not a nested repository's config, not a file with
two names, not a copy aidd wrote. (3) No line of its output holds a credential that a file holds, and a `migrated` line is printed only
for a file that was written. (4) It never rewrites a record. (5) The reader of a standard's copy names the retired keys of an edited
copy and says nothing for a copy of today's shape."""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, aidd_here, git, made_up_row, only_rows
from test_upgrade_engine import CONFIG, RECORD_KEY, RENAME_CONFIG, RENAME_SPEC, SPEC, spec_text

from aidd import config, setup
from aidd.kernel import secret_patterns, yaml_edit
from aidd.knowledge import standard_copy_checks, standards
from aidd.setup import adoption, migrating

COPY = "docs/standards/python/ruff-lint-format.md"
HEAD = "---\nid: python/ruff-lint-format\ntype: opinionated\nchecked: '2026-10-20'\n"
TAIL = "status: active\n---\n\nBody.\n"
RENAME_COPY = made_up_row("standard-legacy-note", "standard", "legacy_note", "note", "rename")
RENAME_TEST_COMMAND = made_up_row("spec-test-retries", "spec", "tests.commands[].retries_old", "tests.commands[].reruns", "rename")
RENAME_PROPOSAL = made_up_row("proposal-note", "proposal", "note_old", "note", "rename")
RENAME_RUNBOOK = made_up_row("runbook-note", "runbook", "note_old", "note", "rename")
RENAME_EXPLORATION = made_up_row("exploration-note", "exploration", "note_old", "note", "rename")
RENAME_HANDOFF = made_up_row("handoff-next", "handoff", "next_old", "next_role", "rename")
CUT_REPO = made_up_row("config-repo", "config", "limits.repo_old", None, "cut")
CUT_SERVICES = made_up_row("config-services", "config", "limits.services_old", None, "cut")
STANDARD_ENTRY = (
    '\nstandards:\n  - name: python-ruff-lint-format\n    path: "{path}"\n    roles: [developer]\n    from_library:\n'
    '      id: python/ruff-lint-format\n      aidd_version: "1.0.0"\n      sha256: "{sha}"\n'
)


class Edges(RepoTemplateCase):
    @classmethod
    def build_template(cls, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        adoption.init(
            root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@lead"], aidd_team=True, harnesses=["claude-code"], ref="v1.0.0")
        )

    def setUp(self):
        super().setUp()
        (self.root / "specs").mkdir(exist_ok=True)
        self.config = (self.root / CONFIG).read_text(encoding="utf-8")

    def put(self, rel: str, text: str | bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    def plan(self, *rows: dict) -> migrating.Plan:
        with only_rows(*rows):
            return migrating.plan(self.root)

    def upgrade(self, *rows: dict, yes: bool = True) -> list[str]:
        with only_rows(*rows):
            return setup.upgrade(self.root, ref="v1.0.0", yes=yes)


class AFileTheEngineCannotEditWhole(Edges):
    def test_an_edit_that_does_not_read_back_is_refused(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        with mock.patch.object(yaml_edit, "rename_key", return_value="limits: [broken\n"):
            found = self.plan(RENAME_CONFIG)
        self.assertEqual(found.texts, {})
        [(kind, line)] = found.lines
        self.assertEqual(kind, "manual")
        self.assertIn("did not read back", line)

    def test_line_endings_stay_and_a_file_that_mixes_them_is_left_alone(self):
        old = spec_text(("\nroute: ", "\nwaits_for: a\nroute: "))
        self.put(SPEC, old.replace("\n", "\r\n"))
        found = self.plan(RENAME_SPEC)
        self.assertEqual(found.texts[SPEC], old.replace("\n", "\r\n").replace("waits_for:", "waiting_on:"))
        self.put(SPEC, old.replace("\n", "\r\n").replace("title: Add a percentage discount\r\n", "title: Add a percentage discount\n"))
        found = self.plan(RENAME_SPEC)
        self.assertEqual(found.texts, {})
        self.assertIn("two kinds of line ending", found.lines[-1][1])

    def test_a_name_in_another_place_of_the_file_is_not_touched(self):
        """The old name is a key of the front matter. The same word in the body, in a fenced example, is prose."""
        self.put(SPEC, spec_text(("## Design\n", "## Design\n\n```yaml\nwaits_for: example\n```\n")))
        found = self.plan(RENAME_SPEC)
        self.assertEqual((found.lines, found.texts), ([], {}))

    def test_a_rename_in_the_tests_of_an_approved_spec_is_noted_because_it_is_no_revision(self):
        approved = '\nstatus: approved\napproved_by: "@x"\napproved_at: "2026-11-01T09:00:00Z"\nroute: '
        for is_approved, noted in ((True, True), (False, False)):
            swaps = [("      covers: [A1]", "      covers: [A1]\n      retries_old: 1")]
            self.put(SPEC, spec_text(*swaps, *([("\nroute: ", approved)] if is_approved else [])))
            found = self.plan(RENAME_TEST_COMMAND)
            with self.subTest(approved=is_approved):
                self.assertIn("reruns: 1", found.texts[SPEC])
                said = any(k == "note" and "no revision" in line and "nothing waits for a person" in line for k, line in found.lines)
                self.assertEqual(said, noted, found.lines)


class TheFilesTheEngineReads(Edges):
    def test_a_remote_parent_is_named_and_a_parent_in_the_repository_is_moved(self):
        parent = 'aidd_version: "1.0.0"\nprofile: team\nlimits:\n  max_retries_old: 2\n'
        self.put(".aidd/org.yaml", parent)
        self.put(CONFIG, self.config + '\nextends:\n  - path: .aidd/org.yaml\n  - url: https://example.com/org.yaml\n    sha256: "' + "0" * 64 + '"\n')
        found = self.plan(RENAME_CONFIG)
        self.assertEqual(found.texts, {".aidd/org.yaml": parent.replace("max_retries_old", "max_task_retries")})
        self.assertTrue(any(k == "note" and "remote" in line for k, line in found.lines), found.lines)

    def test_a_link_is_never_followed_and_a_nested_repository_is_not_read(self):
        outside = Path(self.tmp.name) / "outside.yaml"
        outside.write_text(self.config + "\nlimits:\n  max_retries_old: 2\n", encoding="utf-8")
        (self.root / CONFIG).unlink()
        (self.root / CONFIG).symlink_to(outside)
        self.assertEqual(self.plan(RENAME_CONFIG).texts, {})
        self.assertIn("max_retries_old", outside.read_text(encoding="utf-8"))
        (self.root / CONFIG).unlink()
        self.put(CONFIG, self.config)
        self.put("packages/a/.aidd/config.yaml", self.config + "\nlimits:\n  max_retries_old: 2\n")
        self.assertEqual(self.plan(RENAME_CONFIG).texts, {})

    def test_each_typed_document_and_each_handoff_note_is_read_where_it_lies(self):
        note = "```aidd-handoff\ndone: d\nnext_old: verifier\n```\n"
        proposal = f"---\ntype: proposal\nid: PROP-1\nnote_old: a\n---\n\n{note}"
        runbook = "---\ntype: runbook\nid: RB-1\nnote_old: a\n---\n"
        exploration = "---\ntype: exploration\nid: EXP-1\nnote_old: a\n---\n"
        places = {
            "specs/PROP-1.md": proposal,
            "proposals/PROP-1/proposal.md": proposal.replace("PROP-1", "PROP-2"),
            "docs/runbooks/RB-1.md": runbook,
            "specs/RB-2.md": runbook.replace("RB-1", "RB-2"),
            "specs/explore/pick/exploration.md": exploration,
        }
        for rel, text in places.items():
            self.put(rel, text)
        found = self.plan(RENAME_PROPOSAL, RENAME_RUNBOOK, RENAME_EXPLORATION, RENAME_HANDOFF)
        self.assertEqual(sorted(found.texts), sorted(places), "a typed document is read in each folder aidd reads")
        for rel, text in found.texts.items():
            self.assertNotIn("note_old", text, rel)
            self.assertIn("note: a", text, rel)
        self.assertIn("next_role: verifier", found.texts["specs/PROP-1.md"], "and its handoff note")

    def test_an_edited_copy_of_a_standard_moves_and_a_copy_aidd_wrote_or_a_path_outside_the_folder_is_not_read(self):
        old = HEAD + "legacy_note: hello\n" + TAIL
        recorded = "0" * 64
        self.put(COPY, old)
        self.put(CONFIG, self.config + STANDARD_ENTRY.format(path=COPY, sha=recorded))
        found = self.plan(RENAME_COPY)
        self.assertEqual(found.texts[COPY], HEAD + "note: hello\n" + TAIL)
        beyond = tempfile.TemporaryDirectory()  # a file beyond the repository, which a link in the folder points at
        self.addCleanup(beyond.cleanup)
        outside = Path(beyond.name) / "ruff-lint-format.md"
        outside.write_text(old, encoding="utf-8")
        (self.root / "docs" / "standards" / "python" / "link.md").symlink_to(outside)
        self.put("docs/elsewhere/ruff-lint-format.md", old)  # a file the config lists, outside the folder
        for name, entry in {
            "unedited, an older aidd wrote it": STANDARD_ENTRY.format(path=COPY, sha=standards.digest(old)),
            "a path outside the standards folder": STANDARD_ENTRY.format(path="docs/elsewhere/ruff-lint-format.md", sha=recorded),
            "a path that leaves the repository": STANDARD_ENTRY.format(path="../ruff-lint-format.md", sha=recorded),
            "a link to a file beyond the repository": STANDARD_ENTRY.format(path="docs/standards/python/link.md", sha=recorded),
        }.items():
            with self.subTest(name), mock.patch.object(standards, "__version__", "1.9.9"):  # a later aidd than the one that wrote the copy
                self.put(CONFIG, self.config + entry)
                found = self.plan(RENAME_COPY)
                self.assertEqual({rel for rel in found.texts if "ruff-lint-format" in rel or "link" in rel}, set())
                self.assertFalse([line for _, line in found.lines if "ruff-lint-format" in line], found.lines)

    def test_the_reader_of_a_copy_names_its_retired_keys_and_a_copy_of_today_says_nothing(self):
        with only_rows(RENAME_COPY):
            self.assertEqual(standard_copy_checks.retired_keys(HEAD + "legacy_note: hello\n" + TAIL, COPY), ["`legacy_note` is now `note`"])
            self.assertEqual(standard_copy_checks.retired_keys(HEAD + "note: hello\n" + TAIL, COPY), [])
            self.assertEqual(standard_copy_checks.retired_keys("not a front matter", COPY), [])
        with only_rows():
            self.assertEqual(standard_copy_checks.retired_keys(HEAD + "legacy_note: hello\n" + TAIL, COPY), [], "with no row there is no retired key")


class WhatTheUpgradeWritesAndPrints(Edges):
    def test_the_dry_run_loads_the_config_as_the_real_run_will_and_writes_nothing(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        seen = []
        with mock.patch.object(setup.upgrading, "_bring_up", side_effect=lambda *a, **k: seen.append(config.load_file(CONFIG, str(self.root))) or []):
            self.upgrade(RENAME_CONFIG, yes=False)
        self.assertEqual(len(seen), 1, "the rest of the upgrade loads the migrated config in a dry run")
        self.assertIn("max_retries_old", (self.root / CONFIG).read_text(encoding="utf-8"), "and the file on disk is still the old one")

    def test_only_ask_rules_runs_no_migration(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        before = (self.root / CONFIG).read_bytes()
        with only_rows(RENAME_CONFIG), mock.patch.object(migrating, "plan", side_effect=AssertionError("the migration ran")):
            setup.upgrade(self.root, only="ask-rules", yes=True)
        self.assertEqual((self.root / CONFIG).read_bytes(), before)

    def test_the_command_runs_from_a_folder_inside_the_repository(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        with only_rows(RENAME_CONFIG):
            done = aidd_here("upgrade", "--ref", "v1.0.0", cwd=sub)
        self.assertIn("would migrate", done.stdout)

    def test_a_file_aidd_may_not_write_has_no_migrated_line_and_the_dry_run_says_the_same_as_the_real_run(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        self.put(SPEC, spec_text(("\nroute: ", "\nwaits_for: a\nroute: ")))
        self.put("specs/SPEC-2.md", spec_text(("\nroute: ", "\nwaits_for: b\nroute: ")).replace("SPEC-1", "SPEC-2"))
        outside = Path(self.tmp.name) / "outside-spec.md"
        outside.write_bytes((self.root / "specs/SPEC-2.md").read_bytes())
        (self.root / "specs/SPEC-2.md").unlink()
        os.link(outside, self.root / "specs/SPEC-2.md")  # a file with two names: aidd writes none
        before = {
            p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts
        }
        dry = self.upgrade(RENAME_CONFIG, RENAME_SPEC, yes=False)
        self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}, before)
        real = self.upgrade(RENAME_CONFIG, RENAME_SPEC, yes=True)

        def files(lines: list[str], verb: str) -> set[str]:
            return {m.group(1) for line in lines if (m := re.match(rf"{verb}\s+(\S+?):", line))}

        self.assertTrue(any(line.startswith("manual") and "specs/SPEC-2.md" in line and "not changed" in line for line in real), real)
        self.assertEqual(files(real, "migrated"), {CONFIG, SPEC})
        self.assertEqual(files(dry, "would migrate"), files(real, "migrated"), "the dry run says would for exactly what the real run does")
        self.assertEqual((self.root / "specs/SPEC-2.md").read_bytes(), outside.read_bytes())
        self.assertIn(b"waits_for: b", (self.root / "specs/SPEC-2.md").read_bytes())

    def test_a_record_with_the_old_names_is_no_work_for_the_upgrade_and_is_never_rewritten(self):
        records = Path(git(self.root, "rev-parse", "--git-path", "aidd/records"))
        records = records if records.is_absolute() else self.root / records
        folder = records / "2026" / "11"
        folder.mkdir(parents=True)
        old = {
            "id": "20261101T100000000Z-a0000001",
            "type": "report",
            "stamp": "2026-11-01T10:00:00Z",
            "by": "agent:claude-code/m",
            "data": {"action": "pr.open"},
        }
        (folder / f"{old['id']}.json").write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8")
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n")
        before = {p.name: p.read_bytes() for p in records.rglob("*.json")}
        lines = self.upgrade(RENAME_CONFIG, RECORD_KEY, yes=True)
        self.assertFalse([line for line in lines if "record" in line.lower()], "no line is about a record")
        self.assertEqual({p.name: p.read_bytes() for p in records.rglob("*.json")}, before)
        self.assertIn("max_task_retries", (self.root / CONFIG).read_text(encoding="utf-8"), "while the rest of the upgrade ran")


class NoCredentialIsPrinted(Edges):
    PEM = "-----BEGIN RSA PRIVATE KEY-----\n      MIIabcBODYofTHEkey\n      -----END RSA PRIVATE KEY-----"
    TOKEN = "ghp_" + "a1B2" * 9
    # (name, the cut keys written under `limits:`, the secret text the file holds, whether a line hides one)
    CASES = {
        "a URL with a user and a password": ("  repo_old: https://user:s3cretPass@example.com/x.git\n", ("s3cretPass",), True),
        "a token-looking value": (f"  repo_old: {TOKEN}\n", (TOKEN,), True),
        "a value with no secret": ("  repo_old: acme/shop\n", (), False),
        "a multi-line value": (f"  repo_old: |\n      {PEM}\n", ("MIIabcBODYofTHEkey",), True),
        "a service URL with a password": ('  services_old:\n    up: [psql, "postgres://app:pa55wordXY@db.example.com/shop"]\n', ("pa55wordXY",), True),
    }

    def test_no_line_holds_a_credential_the_file_holds_and_the_line_still_says_what_it_was(self):
        for name, (cut, secrets, hidden) in self.CASES.items():
            for yes in (False, True):
                with self.subTest(name, yes=yes):
                    self.put(CONFIG, self.config + "\nlimits:\n" + cut)
                    lines = self.upgrade(CUT_REPO, CUT_SERVICES, yes=yes)
                    shown = "\n".join(lines)
                    for secret in secrets:
                        self.assertNotIn(secret, shown, "the output holds the credential")
                    for line in lines:
                        self.assertEqual(secret_patterns.secret_types(line, loose=True), [], line)
                    cut_lines = [line for line in lines if re.search(r"cut limits\.(repo_old|services_old)", line)]
                    self.assertEqual(len(cut_lines), 1, "the key still shows")
                    self.assertEqual(secret_patterns.REDACTED in cut_lines[0], hidden)
                    self.assertEqual("history in git holds the full value" in cut_lines[0], hidden, "a hidden value says where the full one is")
                    if not hidden:
                        self.assertIn("= acme/shop", cut_lines[0], "a value with no secret prints as it was")


if __name__ == "__main__":
    unittest.main()
