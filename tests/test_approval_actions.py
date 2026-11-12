"""The actions a person's decision asks about: each new one asks and is never lowered by a suggestion or delegated, every
action `aidd approve` and `aidd cancel` serve holds the patterns of its command in every harness that can, a commit straight
onto a local default branch asks as a merge does, and the risk area's `action` names the action its change needs."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git, run_cli

from aidd import config, risk
from aidd.config import profile_data
from aidd.delegation import policy
from aidd.kernel import resources
from aidd.risk import commands, harness_rules, holds, rules, suggestions

NEW_ACTIONS = ("result.approve", "intent.cancel", "spec.cancel", "postmortem.publish")
# The actions each command serves, and the patterns that hang on every one of them.
APPROVE_SERVES = ("product_scope.approve", "intent.approve", "result.approve", "spec.approve")
CANCEL_SERVES = ("intent.cancel", "spec.cancel")
APPROVE = ("git commit *Approves*", "git * commit *Approves*", "*aidd approve*", "*aidd.pyz approve*", "aidd approve*")
CANCEL = ("git commit *Cancels*", "git * commit *Cancels*", "*aidd cancel*", "*aidd.pyz cancel*", "aidd cancel*")
# A runner form of `aidd <verb> *` for each way aidd starts (commands.RUNNER_FORMS), beside the four patterns.
FORMS_PER_ACTION = len(APPROVE) + len(commands.RUNNER_FORMS["aidd"])


def cfg(text: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text)


def level(rs: risk.RuleSet, line: str, **where) -> str:
    return str(commands.command_level(rs, line, **({"cwd": None} | where))["level"])


class TheNewActionsAskTests(unittest.TestCase):
    def test_each_asks_in_every_profile_and_through_the_command(self):
        for action in NEW_ACTIONS:
            for profile in profile_data.profiles()["profiles"]:
                with self.subTest(action=action, profile=profile):
                    rs = rules.rule_set(config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n'))
                    self.assertEqual(rules.level_of(rs, action)[0], "ask")
            with self.subTest(action=action, how="aidd risk --action"):
                code, out = run_cli("risk", "--action", action, "--json")
                self.assertEqual((code, '"level": "ask"' in out), (0, True), out)

    def test_each_is_a_decision_point_that_no_suggestion_lowers_and_no_config_delegates(self):
        points = {action for action, _, _ in suggestions.DECISION_POINTS}
        for action in NEW_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, points)
                self.assertNotIn(action, policy.delegable())
                with self.assertRaises(config.ConfigError):
                    config.load_text(
                        f'aidd_version: "1.0.0"\nprofile: solo\ndelegation:\n  by: "Ada <ada@users.noreply.github.com>"\n  at: "2026-11-01T09:00:00Z"\n  decides: [{action}]\n  review_due: "2099-01-01"\n'
                    )

    def test_the_actions_a_command_serves_are_decision_points_too(self):
        points = {action for action, _, _ in suggestions.DECISION_POINTS}
        self.assertLessEqual({*APPROVE_SERVES, *CANCEL_SERVES}, points)


class EveryActionHasARuleTests(unittest.TestCase):
    @staticmethod
    def without_a_rule(data: dict) -> list[str]:
        """The actions of risks.json that no rule names, even through a prefix: each reads `allow` for want of one."""
        return [a for a in data["actions"] if not any(config.action_matches(r["action"], a) for r in data["rules"])]

    def test_no_built_in_action_lacks_a_rule(self):
        self.assertEqual(self.without_a_rule(resources.load_json("risks.json")), [])

    def test_the_check_finds_an_action_seeded_with_no_rule(self):
        data = resources.load_json("risks.json")
        seeded = {**data, "actions": {**data["actions"], "thing.done": {"description": "x", "commands": [], "examples": []}}}
        self.assertEqual(self.without_a_rule(seeded), ["thing.done"])
        for action in (*NEW_ACTIONS, *APPROVE_SERVES, *CANCEL_SERVES):
            dropped = {**data, "rules": [r for r in data["rules"] if r["action"] != action]}
            with self.subTest(action=action):
                self.assertEqual(self.without_a_rule(dropped), [action])


class TheCommandsAskTests(unittest.TestCase):
    ROWS = {
        "approve": [
            "aidd approve INTENT-1",
            "aidd approve",
            "python3 -m aidd approve",
            "python3 -m aidd approve INTENT-1",
            "uvx aidd approve INTENT-1",
            "PYTHONPATH=src python3 -m aidd approve INTENT-1#S1",
            "python3 aidd.pyz approve product/prd.md",
            "./scripts/aidd approve INTENT-1",
            'git commit --trailer "Approves=INTENT-1"',
            'git -C . commit -m s -m "Approves: INTENT-1"',
            'git -c commit.gpgsign=false commit --trailer "Approves=INTENT-1"',
            'git commit -m s -m "Approves: INTENT-1"',
            'git commit -m s --trailer "Approves: INTENT-1#S1"',
        ],
        "cancel": [
            'aidd cancel INTENT-1 --reason "dup of INTENT-4"',
            "aidd cancel",
            "uvx aidd cancel",
            'python3 -m aidd cancel SPEC-3 --reason "dup"',
            'uvx aidd cancel INTENT-1 --reason "dup"',
            'PYTHONPATH=src python3 -m aidd cancel INTENT-1 --reason "dup"',
            'python3 aidd.pyz cancel INTENT-1 --reason "dup"',
            'git commit --trailer "Cancels=INTENT-1"',
            'git -C /work/tree commit -m s -m "Cancels: INTENT-1"',
            'git commit -m s -m "Cancels: INTENT-1"',
        ],
    }
    # Honest work no pattern may stop: other aidd commands, and a commit that names neither trailer.
    HONEST = [
        "aidd status",
        "aidd validate",
        "aidd risk --paths README.md",
        "aidd new intent",
        "aidd status --all-branches",
        'git log --grep "approve"',
        'git commit -m "fix a typo"',
    ]

    def test_each_form_of_each_command_asks_under_every_profile(self):
        for profile in profile_data.profiles()["profiles"]:
            rs = rules.rule_set(config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n'))
            for verb, lines in self.ROWS.items():
                for line in lines:
                    with self.subTest(profile=profile, line=line):
                        self.assertEqual(level(rs, line), "ask", verb)

    def test_the_work_a_pattern_could_catch_by_its_words_still_passes(self):
        rs = rules.rule_set(None)
        for line in self.HONEST:
            with self.subTest(line=line):
                self.assertEqual(level(rs, line, branch="own"), "allow")


class TheHoldsDoNotHangOnOneLowerableActionTests(unittest.TestCase):
    """Each command's patterns hang on every action it serves, so lowering one action keeps the ask on the command (F10)."""

    @staticmethod
    def lowered(*actions: str) -> risk.RuleSet:
        return risk.rule_set(cfg("risks:\n  rules:\n" + "".join(f"    - {{action: {a}, level: allow}}\n" for a in actions)))

    def test_each_served_action_carries_the_patterns_of_its_command(self):
        data = resources.load_json("risks.json")["actions"]
        for serves, patterns in ((APPROVE_SERVES, APPROVE), (CANCEL_SERVES, CANCEL)):
            for action in serves:
                with self.subTest(action=action):
                    self.assertLessEqual(set(patterns), set(data[action]["commands"]))

    def test_lowering_any_one_served_action_keeps_every_pattern_written(self):
        for serves, patterns in ((APPROVE_SERVES, APPROVE), (CANCEL_SERVES, CANCEL)):
            for action in serves:
                rs = self.lowered(action)
                with self.subTest(lowered=action):
                    self.assertEqual(rules.level_of(rs, action)[0], "allow")
                    self.assertLessEqual(set(patterns), set(harness_rules.harness_patterns(rs, "main")))

    def test_a_route_rule_that_lowers_spec_approval_still_writes_the_patterns_and_the_command_asks(self):
        rs = risk.rule_set(cfg("risks:\n  rules:\n    - {action: spec.approve, route: normal, level: allow}\n    - {action: spec.approve, level: report}\n"))
        self.assertLessEqual(set(APPROVE), set(harness_rules.harness_patterns(rs, "main")))
        self.assertEqual(level(rs, "aidd approve SPEC-1"), "ask")

    def test_the_patterns_go_only_when_every_action_the_command_serves_stops_asking(self):
        for serves, patterns in ((APPROVE_SERVES, APPROVE), (CANCEL_SERVES, CANCEL)):
            written = set(harness_rules.harness_patterns(self.lowered(*serves), "main"))
            with self.subTest(serves=serves):
                self.assertTrue(written.isdisjoint(patterns), written & set(patterns))


class EachHarnessHoldsWhatItCanTests(unittest.TestCase):
    FULL = ("claude-code", "vscode", "opencode", "grok")
    LEADING_WORDS = ("codex", "qwen")

    def test_a_format_that_reads_globs_or_regular_expressions_holds_every_pattern(self):
        for fmt in self.FULL:
            for patterns in (APPROVE, CANCEL):
                with self.subTest(format=fmt, patterns=patterns):
                    self.assertEqual(harness_rules.unwritten(fmt, list(patterns)), [])
                    # the literal command is inside `*aidd approve*`, which a glob holds
                    self.assertEqual(len(harness_rules.command_entries(fmt, list(patterns), ["origin"])), len(patterns) - 1)

    def test_a_leading_words_format_holds_the_literal_command_and_asks_at_no_commit(self):
        for fmt in self.LEADING_WORDS:
            for patterns in (APPROVE, CANCEL):
                with self.subTest(format=fmt, patterns=patterns):
                    # the wrapped forms and the trailer have no leading-words form, and asking before every commit would slow every change
                    self.assertEqual(harness_rules.unwritten(fmt, list(patterns)), list(patterns[:-1]))
                    self.assertEqual(harness_rules.widened(fmt, list(patterns)), {})
        self.assertEqual(harness_rules.command_entries("codex", ["aidd approve*"], ["origin"]), ['["aidd", "approve"]'])
        self.assertEqual(harness_rules.command_entries("qwen", ["aidd cancel*"], ["origin"]), ["Bash(aidd cancel)", "Bash(aidd cancel *)"])

    def test_a_glob_format_writes_a_launch_form_once_where_a_wider_pattern_holds_it_and_a_leading_words_format_writes_each(self):
        patterns = harness_rules.harness_patterns(rules.rule_set(None), "main")
        launch = "python3 -m aidd approve*"
        self.assertIn(launch, patterns)
        for fmt in self.FULL:
            entries = harness_rules.command_entries(fmt, patterns, ["origin"])
            with self.subTest(format=fmt):
                self.assertFalse([e for e in entries if "-m aidd approve" in e or "-m aidd cancel" in e], "`*aidd approve*` holds it")
                self.assertTrue([e for e in entries if "aidd approve" in e], "the wider pattern is written")
        for fmt in self.LEADING_WORDS:
            with self.subTest(format=fmt):
                self.assertTrue([e for e in harness_rules.command_entries(fmt, patterns, ["origin"]) if "python3" in e and "approve" in e])

    def test_the_counts_aidd_doctor_reads_say_what_each_format_holds_of_each_action(self):
        rs = rules.rule_set(None)
        for fmt in (*self.FULL, *self.LEADING_WORDS):
            counts = holds.hold_counts(rs, "main", fmt)
            for action in (*APPROVE_SERVES, *CANCEL_SERVES):
                with self.subTest(format=fmt, action=action):
                    held = counts[action]
                    self.assertEqual(held.forms, FORMS_PER_ACTION)
                    # a leading-words format holds the literal command in each way aidd starts, 8 of 11
                    literal = 1 + len(commands.RUNNER_FORMS["aidd"])
                    self.assertEqual((held.full, held.narrower), (held.forms, 0) if fmt in self.FULL else (literal, 0))
            with self.subTest(format=fmt, action="postmortem.publish"):
                self.assertEqual(holds.held_by_none(counts).count("postmortem.publish"), 1)

    def test_doctor_names_the_actions_a_harness_holds_only_in_part_or_not_at_all(self):
        from aidd.setup import doctor_harnesses

        lines = {h: " ".join(m for _, m in doctor_harnesses.hold_lines(config.HARNESSES[h], rules.rule_set(None), ["main"])) for h in ("claude-code", "codex")}
        self.assertIn("`postmortem.publish`", lines["claude-code"])
        for action in (*APPROVE_SERVES, *CANCEL_SERVES):
            self.assertNotIn(f"`{action}` (", lines["claude-code"], "held in every form")
            self.assertIn(f"`{action}` (", lines["codex"], "held only in part")


@unittest.skipUnless(shutil.which("git"), "git is required")
class ACommitStraightOntoALocalDefaultBranchAsksTests(unittest.TestCase):
    """With no remote, a commit on the default branch is the merge (N20): it takes the level of `git.merge` there."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def repo(self, name: str, *, remote: bool, branch: str) -> str:
        root = self.base / name
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "T")
        (root / "f").write_text("x")
        git(root, "add", "f")
        git(root, "commit", "-qm", "init")
        if remote:
            git(root, "remote", "add", "origin", "https://example.com/r.git")
            git(root, "update-ref", "refs/remotes/origin/main", "HEAD")  # as a fetch leaves it: the trunk is the remote's branch
        if branch != "main":
            git(root, "switch", "-qc", branch)
        return str(root)

    def test_it_asks_on_the_default_branch_with_no_remote_and_nowhere_else(self):
        rs = rules.rule_set(None)
        cases = [
            ("main, no remote", {"remote": False, "branch": "main"}, "ask"),
            ("main, a remote", {"remote": True, "branch": "main"}, "allow"),
            ("a feature branch, no remote", {"remote": False, "branch": "feat"}, "allow"),
            ("a feature branch, a remote", {"remote": True, "branch": "feat"}, "allow"),
        ]
        for name, kw, want in cases:
            where = self.repo(name.replace(", ", "-").replace(" ", "-"), **kw)
            for line in ("git commit -m x", "git commit --amend --no-edit", "git commit -am x"):
                with self.subTest(case=name, line=line):
                    self.assertEqual(level(rs, line, cwd=where), want)

    def test_the_answer_names_the_merge_it_is_read_as(self):
        where = self.repo("named", remote=False, branch="main")
        answer = commands.command_level(rules.rule_set(None), "git commit -m x", cwd=where)
        self.assertIn(("git.merge", "ask", "default"), [(a["action"], a["level"], a["branch"]) for a in answer["actions"]])

    def test_a_caller_that_names_the_branch_is_read_the_same_way(self):
        rs = rules.rule_set(None)
        bare, remote = self.repo("a", remote=False, branch="main"), self.repo("b", remote=True, branch="main")
        self.assertEqual(level(rs, "git commit -m x", cwd=bare, branch="default"), "ask")
        self.assertEqual(level(rs, "git commit -m x", cwd=bare, branch="own"), "allow")
        self.assertEqual(level(rs, "git commit -m x", cwd=remote, branch="default"), "allow")

    def test_a_checkout_earlier_on_the_line_is_read_beside_the_branch_checked_out(self):
        rs = rules.rule_set(None)
        where = self.repo("moves", remote=False, branch="feat")
        self.assertEqual(level(rs, "git commit -m x", cwd=where), "allow")
        self.assertEqual(level(rs, "git checkout main && git commit -m x", cwd=where), "ask")

    def test_a_repository_aidd_cannot_read_reads_as_the_strictest(self):
        rs = rules.rule_set(None)
        where = self.repo("far", remote=True, branch="feat")
        self.assertEqual(level(rs, "git commit -m x", cwd=None), "ask")
        self.assertEqual(level(rs, f"git -C {self.base / 'elsewhere'} commit -m x", cwd=where), "ask")

    def test_a_config_that_lowers_the_merge_lowers_the_commit_and_no_other_command_changes(self):
        where = self.repo("lowered", remote=False, branch="main")
        lowered = risk.rule_set(cfg("risks:\n  rules:\n    - {action: git.merge, level: allow}\n"))
        self.assertEqual(level(lowered, "git commit -m x", cwd=where), "allow")
        rs = rules.rule_set(None)
        for line, want in (("git status", "allow"), ("git log --oneline", "allow"), ("git merge feat", "ask")):
            with self.subTest(line=line):
                self.assertEqual(level(rs, line, cwd=where), want)

    def test_a_rule_that_asks_for_a_merge_on_your_own_branch_does_not_ask_for_every_commit(self):
        where = self.repo("own-merge", remote=False, branch="feat")
        rs = risk.rule_set(cfg("risks:\n  rules:\n    - {action: git.merge, branch: own, level: ask}\n"))
        self.assertEqual(level(rs, "git commit -m x", cwd=where), "allow")

    # A commit that git is told to run another way: another folder, a setting, or a ref moved on the line.
    WAYS = ["git -C . commit -m x", "git -c commit.gpgsign=false commit -m x", "git checkout -b feat2 && git commit -m x", "git fetch && git commit -m x"]

    def diverged(self, name: str, *, remote: bool, branch: str) -> str:
        """`main` holds two commits, and `feat` one more that `main` lacks, so a command that lands `feat` on `main` moves it ahead."""
        where = self.repo(name, remote=False, branch="main")
        (Path(where) / "g").write_text("y")
        git(where, "add", "g")
        git(where, "commit", "-qm", "second")
        git(where, "switch", "-qc", "feat", "HEAD~1")
        (Path(where) / "h").write_text("z")
        git(where, "add", "h")
        git(where, "commit", "-qm", "third")
        git(where, "switch", "-q", branch)
        if remote:
            git(where, "remote", "add", "origin", "https://example.com/r.git")
            git(where, "update-ref", "refs/remotes/origin/main", "main")
        return where

    LANDS = [
        "git cherry-pick feat",
        "git revert HEAD",
        "git am x.patch",
        "git rebase feat",
        "git branch -f main feat",
        "git checkout -B main feat",
        "git switch -C main feat",
        "git update-ref refs/heads/main feat",
        "git fetch . feat:main",
        "git reset --soft feat",
        "git reset feat",
    ]
    LANDS_NOTHING = [
        "git commit-tree HEAD^{tree} -m x",
        "git cherry-pick --abort",
        "git rebase --abort",
        "git revert --quit",
        "git am --show-current-patch",
        "git reset HEAD g",
        "git reset --soft HEAD~1",
        "git branch -f other feat",
        "git update-ref refs/heads/other feat",
        "git fetch origin",
    ]

    def test_every_command_that_lands_work_on_the_default_branch_asks_with_no_remote(self):
        rs = rules.rule_set(None)
        main, feat = self.diverged("lands-main", remote=False, branch="main"), self.diverged("lands-feat", remote=False, branch="feat")
        for line in self.LANDS:
            with self.subTest(on="main", line=line):
                self.assertEqual(level(rs, line, cwd=main), "ask")
            if not line.startswith(("git branch -f main", "git checkout -B main", "git switch -C main", "git update-ref", "git fetch .")):
                with self.subTest(on="feat", line=line):
                    self.assertEqual(level(rs, line, cwd=feat), "allow", "work landed on a branch of your own")
            else:
                with self.subTest(on="feat, naming main", line=line):
                    self.assertEqual(level(rs, line, cwd=feat), "ask", "a command that names the default branch moves it from any branch")
        for line in self.LANDS_NOTHING:
            with self.subTest(nothing=line):
                self.assertEqual(level(rs, line, cwd=main), "allow")

    def test_with_a_remote_that_holds_the_trunk_nothing_that_lands_work_asks(self):
        rs = rules.rule_set(None)
        main = self.diverged("lands-remote", remote=True, branch="main")
        for line in [*self.LANDS, *self.LANDS_NOTHING]:
            with self.subTest(line=line):
                self.assertEqual(level(rs, line, cwd=main), "allow")

    def test_the_trunk_is_the_one_aidd_reads_everywhere_else(self):
        """A remote that is not `origin`, or an `origin` never fetched, leaves the trunk a local branch, so a commit there is the merge."""
        rs = rules.rule_set(None)
        other = self.repo("other-remote", remote=False, branch="main")
        git(other, "remote", "add", "backup", "https://example.com/b.git")
        unfetched = self.repo("unfetched", remote=False, branch="main")
        git(unfetched, "remote", "add", "origin", "https://example.com/r.git")
        fetched = self.repo("fetched", remote=True, branch="main")
        for name, where, want in (("another remote", other, "ask"), ("origin never fetched", unfetched, "ask"), ("origin fetched", fetched, "allow")):
            with self.subTest(name):
                self.assertEqual(level(rs, "git commit -m x", cwd=where), want)

    def test_with_a_remote_each_way_to_run_a_commit_stays_allowed(self):
        rs = rules.rule_set(None)
        for branch in ("main", "feat"):
            where = self.repo(f"remote-{branch}", remote=True, branch=branch)
            for line in [*self.WAYS, f"git -C {where} commit -m x"]:
                with self.subTest(branch=branch, line=line):
                    self.assertEqual(level(rs, line, cwd=where), "allow")

    def test_with_no_remote_each_way_still_asks_on_the_default_branch_and_not_elsewhere(self):
        rs = rules.rule_set(None)
        main = self.repo("bare-main", remote=False, branch="main")
        for line in [*self.WAYS, f"git -C {main} commit -m x"]:
            with self.subTest(line=line):
                self.assertEqual(level(rs, line, cwd=main), "ask")
        feat = self.repo("bare-feat", remote=False, branch="feat")
        self.assertEqual(level(rs, "git -C . commit -m x", cwd=feat), "allow", "the branch is read in the folder it names")

    def test_git_dash_c_reads_the_remote_and_the_branch_of_the_folder_it_names(self):
        rs = rules.rule_set(None)
        bare, remote = self.repo("a-bare", remote=False, branch="main"), self.repo("a-remote", remote=True, branch="main")
        self.assertEqual(level(rs, f"git -C {remote} commit -m x", cwd=bare), "allow")
        self.assertEqual(level(rs, f"git -C {bare} commit -m x", cwd=remote), "ask")
        self.assertEqual(level(rs, "git -C /no/such/folder commit -m x", cwd=remote), "ask", "a folder aidd cannot read asks")
        # from a folder that is no repository, an absolute folder is still read: the way a session in a worktree commits
        self.assertEqual(level(rs, f"git -C {remote} commit -m x", cwd=None), "allow")
        self.assertEqual(level(rs, f"git -C {bare} commit -m x", cwd=None), "ask")
        self.assertEqual(level(rs, "git -C relative commit -m x", cwd=None), "ask")
        self.assertEqual(level(rs, f"git --git-dir={remote}/.git commit -m x", cwd=remote), "ask", "another way to name a repository asks")

    def test_the_action_reads_as_the_command_does(self):
        """`aidd risk --action git.commit` and the MCP tool read the same level as the command, on the default branch with no remote."""
        import contextlib

        bare, remote = self.repo("act-bare", remote=False, branch="main"), self.repo("act-remote", remote=True, branch="main")
        feat = self.repo("act-feat", remote=False, branch="feat")
        cases = [
            (bare, [], "ask"),
            (bare, ["--branch", "default"], "ask"),
            (bare, ["--branch", "own"], "allow"),
            (remote, [], "allow"),
            (remote, ["--branch", "default"], "allow"),
            (feat, [], "allow"),
        ]
        for folder, extra, want in cases:
            with self.subTest(folder=Path(folder).name, extra=extra), contextlib.chdir(folder):
                code, out = run_cli("risk", "--action", "git.commit", *extra, "--json")
                self.assertEqual((code, json.loads(out)["level"]), (0, want), out)
                if want == "ask":  # it names the rule that decides, as the command does, and says why
                    self.assertEqual(json.loads(out)["rule"], "git.merge: ask")
                    self.assertTrue([n for n in json.loads(out)["notes"] if "is the merge" in n], out)
                _, by_command = run_cli(
                    "risk", "--command", "git commit -m x", *(["--branch", "default"] if extra == ["--branch", "default"] else []), "--json"
                )
                if not extra or extra == ["--branch", "default"]:
                    self.assertEqual(json.loads(by_command)["level"], want)

    def test_no_harness_pattern_asks_before_every_commit(self):
        patterns = harness_rules.harness_patterns(rules.rule_set(None), "main")
        self.assertEqual([p for p in patterns if p in ("git commit", "git commit*", "git commit *")], [])


class TheRiskAreaNamesItsActionTests(unittest.TestCase):
    def test_the_built_in_area_holds_its_action_under_the_key_action(self):
        area = resources.load_json("risks.json")["areas"]["product_scope"]
        self.assertEqual(area.get("action"), "product_scope.approve")
        self.assertNotIn("approval", area)

    def test_the_next_step_names_the_action_of_each_area_the_change_touches(self):
        answer = risk.advice(None, ["product/prd.md"], tracked=[])
        self.assertIn("`product_scope.approve`", answer["next"]["what"])
        area = "risks:\n  areas:\n    audit:\n      paths: ['audit/**']\n      route: minor\n      action: pr.merge\n"
        self.assertIn("`pr.merge`", risk.advice(cfg(area), ["audit/log.md"], tracked=[])["next"]["what"])

    def test_a_config_area_that_still_says_approval_is_refused_naming_the_field(self):
        area = "risks:\n  areas:\n    audit:\n      paths: ['audit/**']\n      route: minor\n      approval: pr.merge\n"
        with self.assertRaises(config.ConfigError) as caught:
            cfg(area)
        self.assertIn("approval", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
