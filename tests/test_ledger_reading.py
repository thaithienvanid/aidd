"""A newer aidd reads every older ledger (CONTRIBUTING.md, "Public contracts"), because `aidd upgrade` and `aidd uninstall`
read what aidd wrote before to find what is aidd's: the ask rules and allowed tools of `.aidd/harness-rules.json`, and the team
files of `.aidd/team-files.json`. A shape that this code stopped reading would leave stale rules and files behind.

`tests/fixtures/ledgers/<version>/` keeps each shape a release wrote. A release that changes a ledger's shape adds a folder and
leaves the older ones, so these tests read all of them with the code of today. A key an older aidd does not know is left
alone, and it stays when the ledger is rewritten."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers  # puts src/ on the path and makes the run hermetic
from helpers import git, run_cli

from aidd import config
from aidd.risk import harness_rules
from aidd.setup import delegation_wiring, mcp_wiring, team_record, worktree_base

FIXTURES = helpers.ROOT / "tests" / "fixtures" / "ledgers"
VERSIONS = sorted(p for p in FIXTURES.iterdir() if p.is_dir())
NEWER_KEY = "added_by_a_newer_aidd"
PERSONS_OWN_RULE = "Bash(my-own-script *)"
# The ledger keys that name a harness format, as the 1.0.0 ledgers wrote them. This list is the fixtures' fact, never read
# from today's formats, so a format renamed in the code stays a key these ledgers hold, and its test fails.
FORMAT_KEYS = ("claude-code", "codex", "opencode")


def ledger(version: Path) -> dict:
    return json.loads((version / "harness-rules.json").read_text(encoding="utf-8"))


def team_files(version: Path) -> dict:
    return json.loads((version / "team-files.json").read_text(encoding="utf-8"))


def repository_with(root: Path, **files: object) -> None:
    for rel, content in files.items():
        path = root / rel.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


class FixtureTests(unittest.TestCase):
    def test_a_fixture_folder_holds_each_ledger_and_each_ledger_holds_what_aidd_records(self):
        self.assertTrue(VERSIONS, "the shapes a release wrote")
        for version in VERSIONS:
            with self.subTest(version=version.name):
                self.assertEqual(sorted(p.name for p in version.iterdir()), ["harness-rules.json", "team-files.json"])
                formats = [k for k in ledger(version) if k in FORMAT_KEYS]
                self.assertTrue(formats and all(ledger(version)[k] for k in formats), "ask rules by harness format")
                self.assertTrue(team_files(version)["files"], "team files by path")

    def test_the_ledgers_aidd_writes_today_have_no_key_that_no_fixture_holds(self):
        """A release that adds a key adds a fixture folder holding it, so the next release is tested against this one."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            args = ("init", "--profile", "solo", "--approvers", "@me", "--ci", "none", "--test", "true", "--aidd-team")
            code, text = run_cli(*args, "--harness", "claude-code", "--harness", "codex", "--harness", "opencode", "--delegate", "--claude-plugins", str(root))
            self.assertEqual(code, 0, text)
            written = json.loads((root / config.HARNESS_RULES_FILE).read_text(encoding="utf-8"))
            record = json.loads((root / config.TEAM_FILES_FILE).read_text(encoding="utf-8"))
        known = {k for v in VERSIONS for k in ledger(v)}
        self.assertEqual(sorted(set(written) - known), [], "a ledger key with no fixture")
        self.assertEqual(sorted(set(record) - {k for v in VERSIONS for k in team_files(v)}), [], "a team record key with no fixture")


def settings_list(root: Path, *path: str) -> list:
    """The list at `path` in `.claude/settings.json`, empty where the file or a step on the way is gone."""
    data = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for step in path:
        data = data.get(step, {}) if isinstance(data, dict) else {}
    return data if isinstance(data, list) else []


def read_format(key: str):
    """The reader of a format's list: `harness_rules.owned`. It returns what it read, and no person's entry to keep."""

    def read(root: Path, entries: list[str]) -> tuple[set[str], list | None]:
        return set(harness_rules.owned(root).get(key, [])), None

    return read


def read_mcp_allowed(root: Path, entries: list[str]) -> tuple[set[str], list | None]:
    """Uninstall takes out of `permissions.allow` the tool names the ledger lists."""
    repository_with(root, **{".claude__settings.json": {"permissions": {"allow": [*entries, PERSONS_OWN_RULE]}}})
    mcp_wiring.remove_mcp(root, [], yes=True)
    left = settings_list(root, "permissions", "allow")
    return set(entries) - set(left), left


def read_delegation(root: Path, entries: list[str]) -> tuple[set[str], list | None]:
    """Uninstall takes out the delegation's hooks and the ask rules the ledger lists."""
    asks = [e for e in entries if not e.startswith("hooks.")]
    hooks = {event: [group] for event, group in delegation_wiring.HOOKS.items()}
    repository_with(root, **{".claude__settings.json": {"hooks": hooks, "permissions": {"ask": [*asks, PERSONS_OWN_RULE]}}})
    delegation_wiring.remove(root)
    data = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    left = settings_list(root, "permissions", "ask")
    return {f"hooks.{event}" for event in hooks if event not in data.get("hooks", {})} | (set(asks) - set(left)), left


def read_worktree(root: Path, entries: list[str]) -> tuple[set[str], list | None]:
    """Uninstall takes out the worktree setting the ledger lists, while it holds aidd's value."""
    repository_with(root, **{".claude__settings.json": {"worktree": {"baseRef": "head"}, "permissions": {"ask": [PERSONS_OWN_RULE]}}})
    worktree_base.remove(root)
    data = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return {"worktree.baseRef"} - {f"worktree.{k}" for k in data.get("worktree", {})}, settings_list(root, "permissions", "ask")


# Every key the fixtures hold, with the code that reads it. A key that no row names has no test of its own.
READERS = {
    **{key: read_format(key) for key in FORMAT_KEYS},
    "claude-code-mcp-allowed": read_mcp_allowed,
    "claude-code-delegation": read_delegation,
    "claude-code-worktree": read_worktree,
}


class EveryKeyIsReadTests(unittest.TestCase):
    def test_every_key_the_fixtures_hold_has_a_reader_and_every_reader_a_key(self):
        keys = {k for v in VERSIONS for k in ledger(v)}
        self.assertEqual(sorted(keys - set(READERS)), [], "a key that no reader below reads")
        self.assertEqual(sorted(set(READERS) - keys), [], "a reader of a key that no fixture holds")

    def test_the_code_of_today_reads_every_entry_each_ledger_lists_under_each_key(self):
        for version in VERSIONS:
            for key, entries in ledger(version).items():
                if key not in READERS:
                    continue
                with self.subTest(version=version.name, key=key), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    repository_with(root, **{".aidd__harness-rules.json": ledger(version)})
                    read, kept = READERS[key](root, entries)
                    self.assertEqual(sorted(read), sorted(entries), "everything the ledger lists is read as aidd's")
                    if kept is not None:
                        self.assertEqual(kept, [PERSONS_OWN_RULE], "and the person's own entry stays")


class HarnessRulesTests(unittest.TestCase):
    def test_the_code_of_today_reads_the_ask_rules_each_ledger_lists_by_format(self):
        for version in VERSIONS:
            with self.subTest(version=version.name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                repository_with(root, **{".aidd__harness-rules.json": ledger(version)})
                expected = {k: v for k, v in ledger(version).items() if k in FORMAT_KEYS}
                self.assertEqual(harness_rules.owned(root), expected)
                self.assertEqual(harness_rules.written_formats(root), list(expected))

    def test_a_key_a_newer_aidd_adds_changes_nothing_that_is_read(self):
        for version in VERSIONS:
            for value in (["x"], {"x": 1}, "x", 7):
                with self.subTest(version=version.name, value=value), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    repository_with(root, **{".aidd__harness-rules.json": {**ledger(version), NEWER_KEY: value}})
                    expected = {k: v for k, v in ledger(version).items() if k in FORMAT_KEYS}
                    self.assertEqual(harness_rules.owned(root), expected)

    def test_uninstall_takes_out_the_ask_rules_a_ledger_lists_and_leaves_the_persons_own_and_the_key_it_does_not_know(self):
        for version in VERSIONS:
            with self.subTest(version=version.name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                mine = ledger(version)["claude-code"]
                repository_with(
                    root,
                    **{
                        ".aidd__harness-rules.json": {**ledger(version), NEWER_KEY: ["x"]},
                        ".claude__settings.json": {"permissions": {"ask": [*mine, PERSONS_OWN_RULE]}},
                    },
                )
                done = harness_rules.remove_harness_rules(root)
                self.assertTrue(done, "it removed what the ledger lists")
                left = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
                self.assertEqual(left["permissions"]["ask"], [PERSONS_OWN_RULE], "no stale ask rule stays, and the person's own does")
                kept = json.loads((root / config.HARNESS_RULES_FILE).read_text(encoding="utf-8"))
                self.assertIn(NEWER_KEY, kept, "a key that names no format is another writer's")
                self.assertNotIn("claude-code", kept)


class TeamRecordTests(unittest.TestCase):
    def test_the_code_of_today_reads_the_team_files_each_record_lists(self):
        for version in VERSIONS:
            with self.subTest(version=version.name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                repository_with(root, **{".aidd__team-files.json": team_files(version)})
                self.assertEqual(team_record.read_record(root), team_files(version)["files"])

    def test_a_key_a_newer_aidd_adds_changes_nothing_that_is_read(self):
        for version in VERSIONS:
            for value in (["x"], {"x": 1}, "x", 7):
                with self.subTest(version=version.name, value=value), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    repository_with(root, **{".aidd__team-files.json": {**team_files(version), NEWER_KEY: value}})
                    self.assertEqual(team_record.read_record(root), team_files(version)["files"])

    def test_a_path_the_record_lists_that_this_aidd_no_longer_writes_is_told_apart_from_one_it_writes(self):
        for version in VERSIONS:
            with self.subTest(version=version.name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                listed = team_files(version)["files"]
                repository_with(root, **{".aidd__team-files.json": team_files(version)})
                writes = dict.fromkeys(listed, "text")
                self.assertEqual(team_record.stale(root, writes), ([], []), "every listed path is one aidd writes")
                self.assertEqual(team_record.stale(root, {}), ([], sorted(listed)), "none is stale or removed, and each is named as ignored")


if __name__ == "__main__":
    unittest.main()
