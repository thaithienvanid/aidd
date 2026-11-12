"""Where a role's worktree starts (setup/worktree_base.py). Claude Code branches a subagent's worktree from the remote's
default branch unless the project sets `worktree.baseRef` to `head`, so a role would lack the change's commits and frozen
tests, and a lead would reset it, an `ask`, at every start.

The invariants:
1. Where the team's roles run in a harness that documents the setting, `aidd init --aidd-team` and `aidd upgrade --yes` write
   it, a plan writes nothing, and a value a file already holds (`fresh`, `head`, or any other) stays as it is. A file aidd
   cannot read as a JSON object, or one whose `worktree` is no object, is left alone with a line that says so.
2. Raise-only: the setting adds no permission and changes no ask, allow, or deny rule (test_worktree_base_raise_only.py).
3. `aidd uninstall` takes out only what aidd wrote, while it still holds aidd's value.
4. `aidd doctor` notes the setting's absence where the team's roles run, and is silent where any settings file sets it,
   where no team is installed, and for a harness that documents no such setting.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  # the hermetic environment
from helpers import git

from aidd import config
from aidd.setup import adoption, doctor_team, init_plan, uninstalling, upgrading, worktree_base

SETTINGS = ".claude/settings.json"
LEDGER = ".aidd/harness-rules.json"
KEY = "claude-code" + worktree_base.LEDGER_SUFFIX
# A person's own settings file, with permissions and a key of their own, as a real one holds.
THEIRS = {"model": "x", "permissions": {"allow": ["Bash(ls)"], "ask": ["Bash(make deploy)"], "deny": ["Read(./.env)"]}}


class Repo(unittest.TestCase):
    def repo(self, settings: str | None = None) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "repo"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "T")
        if settings is not None:
            (root / ".claude").mkdir()
            (root / SETTINGS).write_text(settings, encoding="utf-8")
        return root

    def init(self, root: Path, profile: str = "solo", **options) -> list[str]:
        options.setdefault("harnesses", ["claude-code"])
        return adoption.init(root, adoption.InitOptions(profile=profile, ci="none", links=[], skill=False, **options))

    def worktree(self, root: Path) -> object:
        return json.loads((root / SETTINGS).read_text()).get("worktree") if (root / SETTINGS).is_file() else None

    def ledger(self, root: Path) -> dict:
        return json.loads((root / LEDGER).read_text()) if (root / LEDGER).is_file() else {}

    def start_from(self, root: Path, start: str | None, aidds: object = None) -> None:
        """Put the starting settings file in place, and the ledger entry `aidds` when it is given: True for the one aidd writes."""
        (root / SETTINGS).unlink(missing_ok=True)
        if start is not None:
            (root / SETTINGS).write_text(start, encoding="utf-8")
        ledger = {k: v for k, v in self.ledger(root).items() if k != KEY} | ({} if aidds is None else {KEY: ["worktree.baseRef"] if aidds is True else aidds})
        (root / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")


class InitWritesItOrKeepsTheirs(Repo):
    def test_each_starting_file(self):
        # (starting settings, worktree after the write, the line's first word or None for no line, whether the ledger lists it)
        cases = [
            (None, {"baseRef": "head"}, "wrote", True),
            (json.dumps(THEIRS), {"baseRef": "head"}, "updated", True),
            ('{"worktree": {"baseRef": "fresh"}}', {"baseRef": "fresh"}, "kept", False),
            ('{"worktree": {"baseRef": "main"}}', {"baseRef": "main"}, "kept", False),
            ('{"worktree": {"baseRef": 7}}', {"baseRef": 7}, "kept", False),
            ('{"worktree": {"baseRef": "head"}}', {"baseRef": "head"}, None, False),
            ('{"worktree": {"sparsePaths": ["src"]}}', {"sparsePaths": ["src"], "baseRef": "head"}, "updated", True),
            ('{"worktree": "head"}', "head", "kept", False),
            ('{"worktree": null}', None, "kept", False),
        ]
        root = self.repo()
        self.assertTrue([a for a in self.init(root, aidd_team=True) if "worktree.baseRef" in a], "init writes it where the team's roles run")
        for start, after, word, listed in cases:
            with self.subTest(start=start):
                self.start_from(root, start)
                lines = worktree_base.apply(root, ["claude-code"])
                self.assertEqual(self.worktree(root), after)
                self.assertEqual([a.split()[0] for a in lines], [word] if word else [])
                self.assertEqual(KEY in self.ledger(root), listed)

    def test_a_file_aidd_cannot_read_as_settings_is_left_alone(self):
        root = self.repo()
        self.init(root, aidd_team=True)
        for start in ("{ not json", "[1, 2]"):
            with self.subTest(start=start):
                self.start_from(root, start)
                lines = worktree_base.apply(root, ["claude-code"])
                self.assertEqual((root / SETTINGS).read_text(), start)
                self.assertEqual([a.split()[0] for a in lines], ["kept"])
        (root / "elsewhere.json").write_text("{}", encoding="utf-8")
        (root / SETTINGS).unlink()
        os.symlink(root / "elsewhere.json", root / SETTINGS)
        self.assertEqual([a.split()[0] for a in worktree_base.apply(root, ["claude-code"])], ["kept"])
        self.assertEqual((root / "elsewhere.json").read_text(), "{}")
        self.assertTrue((root / SETTINGS).is_symlink())

    def test_no_team_and_no_documented_setting_write_and_say_nothing(self):
        root = self.repo()
        self.assertFalse([a for a in self.init(root) if "baseRef" in a])
        self.assertIsNone(self.worktree(root))
        no_key = {k: dataclasses.replace(h, worktree_base=None) for k, h in config.HARNESSES.items()}
        with mock.patch.dict(config.HARNESSES, no_key):
            root = self.repo()
            self.assertFalse([a for a in self.init(root, aidd_team=True) if "baseRef" in a])
            self.assertIsNone(self.worktree(root))
        self.assertEqual([k for k, h in config.HARNESSES.items() if h.worktree_base], ["claude-code"])

    def test_a_plan_writes_nothing_and_says_what_init_writes(self):
        root = self.repo()
        plan = init_plan.plan_init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, aidd_team=True, harnesses=["claude-code"]))
        line = [a for a in init_plan.dry_run_lines(plan.actions) if "worktree.baseRef" in a]
        self.assertEqual([a.split()[:2] for a in line], [["would", "update"]])
        self.assertEqual(json.loads(plan.writes[SETTINGS])["worktree"], {"baseRef": "head"})
        self.assertFalse((root / SETTINGS).exists())

    def test_upgrade_adds_it_once_and_a_second_run_changes_nothing(self):
        root = self.repo()
        self.init(root, aidd_team=True)
        data = json.loads((root / SETTINGS).read_text())
        data.pop("worktree")
        (root / SETTINGS).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        dry = [a for a in upgrading.upgrade(root) if "baseRef" in a]
        self.assertEqual([a.split()[:2] for a in dry], [["would", "update"]])
        self.assertNotIn("worktree", json.loads((root / SETTINGS).read_text()))
        self.assertTrue([a for a in upgrading.upgrade(root, yes=True) if "baseRef" in a])
        self.assertEqual(self.worktree(root), {"baseRef": "head"})
        before = {p: p.read_bytes() for p in (root / SETTINGS, root / LEDGER)}
        self.assertFalse([a for a in upgrading.upgrade(root, yes=True) if "baseRef" in a])
        self.assertEqual({p: p.read_bytes() for p in before}, before)


class UninstallTakesOnlyAidds(Repo):
    def test_each_case(self):
        # (the settings before uninstall, the ledger's entry for it (True: the one aidd writes; None: none), worktree after uninstall)
        cases = [
            ('{"worktree": {"baseRef": "head"}}', True, None),
            ('{"worktree": {"baseRef": "fresh"}}', True, {"baseRef": "fresh"}),  # a person changed it since
            ('{"worktree": {"baseRef": "head"}}', None, {"baseRef": "head"}),  # the person's own
            ('{"worktree": {"baseRef": "head"}}', 5, {"baseRef": "head"}),  # a ledger entry that is no list names nothing
            ('{"worktree": {"baseRef": "head"}}', "worktree.baseRef.x", {"baseRef": "head"}),
            ('{"worktree": {"sparsePaths": ["src"], "baseRef": "head"}}', True, {"sparsePaths": ["src"]}),
        ]
        template = self.repo()
        self.init(template, aidd_team=True)
        for n, (start, aidds, after) in enumerate(cases):
            with self.subTest(start=start, aidds=aidds):
                root = template.parent / f"copy-{n}"
                shutil.copytree(template, root, symlinks=True)
                self.start_from(root, start, aidds)
                dry = uninstalling.uninstall(root)
                self.assertEqual((root / SETTINGS).read_text(), start, "a dry run removes nothing")
                self.assertIn("dry run", dry[-2])
                uninstalling.uninstall(root, yes=True)
                self.assertEqual(self.worktree(root), after)
                self.assertNotIn(KEY, self.ledger(root))


class DoctorNotesItsAbsence(Repo):
    def notes(self, root: Path, wired: list[str] | None = None) -> list[str]:
        return [m for level, m in doctor_team.team_lines(root, wired or ["claude-code"]) if "baseRef" in m]

    def test_each_case(self):
        user = Path(os.environ["HOME"]) / "claude-config"
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(user)}):
            root = self.repo()
            self.init(root, aidd_team=True)
            data = json.loads((root / SETTINGS).read_text())
            data.pop("worktree")
            (root / SETTINGS).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            (note,) = self.notes(root)
            self.assertIn('{"worktree": {"baseRef": "head"}}', note)
            self.assertIn("aidd upgrade --yes", note)
            self.assertEqual([lvl for lvl, m in doctor_team.team_lines(root, ["claude-code"]) if "baseRef" in m], ["note"])
            # set anywhere Claude Code reads it, to any value: silent
            for where, value in ((root / SETTINGS, "fresh"), (root / ".claude/settings.local.json", "head"), (user / "settings.json", "head")):
                with self.subTest(where=where.name, value=value):
                    was = where.read_text() if where.is_file() else None
                    where.parent.mkdir(parents=True, exist_ok=True)
                    where.write_text(json.dumps({**json.loads(was or "{}"), "worktree": {"baseRef": value}}), encoding="utf-8")
                    self.assertEqual(self.notes(root), [])
                    if was is None:
                        where.unlink()
                    else:
                        where.write_text(was, encoding="utf-8")
            self.assertEqual(len(self.notes(root)), 1)
            # no team installed here: silent
            bare = self.repo()
            self.init(bare)
            self.assertEqual(self.notes(bare), [])
            # a harness that documents no such setting: silent
            no_key = {k: dataclasses.replace(h, worktree_base=None) for k, h in config.HARNESSES.items()}
            with mock.patch.dict(config.HARNESSES, no_key):
                self.assertEqual(self.notes(root), [])


class TheFactHasItsSource(unittest.TestCase):
    def test_the_setting_is_read_from_the_vendors_page_with_a_date(self):
        base = config.HARNESSES["claude-code"].worktree_base
        assert base is not None
        self.assertTrue(base.source.startswith("https://code.claude.com/docs/"))
        self.assertRegex(base.read, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(json.loads(base.shown()), {"worktree": {"baseRef": "head"}})
        self.assertEqual(json.loads(base.shown(1)), {"baseRef": "head"})

    def test_the_role_files_it_looks_for_are_the_ones_init_writes(self):
        from aidd.setup import team_install

        written = sorted(rel for rel in team_install.team_files([], True) if rel.startswith(".claude/agents/"))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertFalse(worktree_base.runs_roles(root, "claude-code", []))
            for rel in written:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
                with self.subTest(rel=rel):
                    self.assertTrue(worktree_base.runs_roles(root, "claude-code", []))
                (root / rel).unlink()


if __name__ == "__main__":
    unittest.main()
