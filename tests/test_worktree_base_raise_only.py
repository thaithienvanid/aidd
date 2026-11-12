"""Raise-only: the worktree setting aidd writes (setup/worktree_base.py) adds no permission and changes no ask, allow, or
deny rule. A differential over both profiles, every option that shapes Claude Code's settings, and a person's own starting
files: init, then `upgrade --yes`, once with the writer and once without it, which is the code path before it. Every file
is byte-identical, the `permissions` block of `.claude/settings.json` included, but for the new key and its ledger entry."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  # the hermetic environment
import test_doctor_holds as oracle
from helpers import git

from aidd.setup import adoption, upgrading, worktree_base

SETTINGS = ".claude/settings.json"
LEDGER = ".aidd/harness-rules.json"
KEY = "claude-code" + worktree_base.LEDGER_SUFFIX
THEIRS = {"model": "x", "permissions": {"allow": ["Bash(ls)"], "ask": ["Bash(make deploy)"], "deny": ["Read(./.env)"]}}
# Every option that changes what init writes into Claude Code's settings, with the team on and off.
OPTIONS = [
    {"aidd_team": False},
    {"aidd_team": True},
    {"aidd_team": True, "harnesses": ["claude-code", "codex", "opencode"]},
    {"aidd_team": True, "claude_plugins": True},
    {"aidd_team": True, "delegate": True, "environments": []},
]
STARTS = [None, json.dumps(THEIRS), '{"worktree": {"baseRef": "fresh"}}']
# A sample command for every ask rule, read back as Claude Code matches its file.
SAMPLES = sorted({s for p in ("git push --force*", "git reset --hard*", "rm -rf *", "gh pr merge*") for s in oracle.samples(p)})


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


class TheSettingIsRaiseOnly(unittest.TestCase):
    def run_both(self, start: str | None, profile: str, options: dict, upgrade: bool) -> tuple[dict[str, bytes], dict[str, bytes], list[set[str]]]:
        out, asked = [], []
        for writer in (True, False):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                git(root, "init", "-q", "-b", "main")
                git(root, "config", "user.email", "t@example.com")
                git(root, "config", "user.name", "T")
                if start is not None:
                    (root / ".claude").mkdir()
                    (root / SETTINGS).write_text(start, encoding="utf-8")
                kept = worktree_base.apply if writer else (lambda *a, **k: [])
                opts = {"harnesses": ["claude-code"], **options}
                with mock.patch.object(worktree_base, "apply", kept):
                    adoption.init(root, adoption.InitOptions(profile=profile, ci="none", links=[], skill=False, **opts))
                    if upgrade:
                        upgrading.upgrade(root, yes=True)
                out.append(tree(root))
                asks = oracle.asker(root, "claude-code")
                asked.append({c for c in SAMPLES if asks(c)})
        return out[0], out[1], asked

    def test_only_the_new_key_and_its_ledger_entry_differ(self):
        # Every option under `solo`, the team off and on under `team`, and a person's own files; upgrade where the team is on.
        rows = [("solo", o, None, o == OPTIONS[1]) for o in OPTIONS] + [("team", o, None, False) for o in OPTIONS[:2]]
        rows += [("solo", {"aidd_team": True}, s, True) for s in STARTS[1:]]
        for profile, option, start, upgrade in rows:
            with self.subTest(profile=profile, options=option, start=start, upgrade=upgrade):
                head, base, asked = self.run_both(start, profile, option, bool(upgrade))
                self.assertEqual(asked[0], asked[1], "the commands that ask are the same")
                self.assertEqual(sorted(head), sorted(base))
                others = [p for p in head if p not in (SETTINGS, LEDGER)]
                self.assertEqual([p for p in others if head[p] != base[p]], [])
                new, old = json.loads(head[SETTINGS]), json.loads(base[SETTINGS])
                self.assertEqual(json.dumps(new.get("permissions")), json.dumps(old.get("permissions")), "the permissions block is byte-identical")
                if option.get("aidd_team") and old.get("worktree") is None:
                    self.assertEqual(new.pop("worktree"), {"baseRef": "head"})
                    self.assertEqual(json.dumps(new, indent=2) + "\n", base[SETTINGS].decode(), "only the new key differs")
                    ledger = json.loads(head[LEDGER])
                    self.assertEqual(ledger.pop(KEY), ["worktree.baseRef"])
                    self.assertEqual(ledger, json.loads(base[LEDGER]))
                else:
                    self.assertEqual(head[SETTINGS], base[SETTINGS])
                    self.assertEqual(head.get(LEDGER), base.get(LEDGER))


if __name__ == "__main__":
    unittest.main()
