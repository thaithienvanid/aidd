"""`aidd delegate check`'s gates, on real repositories with no network: a stand-in GitHub reader where a remote exists.
Each gate defers on the first fact it cannot prove, and the model's part is an eval, never a gate."""

import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd import delegation
from aidd.delegation import check as check_mod
from aidd.delegation import commands, diff_signals, policy

ENV = {"CLAUDECODE": "1"}
NAME = ["-c", "user.name=Maya", "-c", "user.email=maya@users.noreply.github.com"]
SUITE = "import pathlib, sys; sys.exit(1 if 'broken' in pathlib.Path('src/app.py').read_text() else 0)"


def config_text(profile="solo", deploys="false", review_by="2099-01-01", decides="all", extra=""):
    deploys_line = f"  default_branch_deploys: {deploys}\n" if deploys is not None else ""
    return (
        'aidd_version: "1.0.0"\n'
        f"profile: {profile}\n"
        "tests:\n"
        "  - name: unit\n"
        f"    command: [python3, -c, {json.dumps(SUITE)}]\n"
        "delegation:\n"
        "  default_branch: main\n"
        "  to: delegate\n"
        '  set_by: "Maya Lee <maya@users.noreply.github.com>"\n'
        f"  decides: {decides}\n"
        f"{deploys_line}"
        f'  review_by: "{review_by}"\n' + extra
    )


def note(head: str, needs: str = "none") -> str:
    return f'```aidd-handoff\ndone: verified\nnext: reviewer\nneeds: {needs}\nstopped_at: none\nhead: "{head}"\n```\n'


class Repo:
    """A solo repository with no remote: a delegation on main, and a branch whose change and note make the head."""

    def __init__(self, root: Path, **cfg):
        self.root = root
        git(root, "init", "-q", "-b", "main")
        self.write(".aidd/config.yaml", config_text(**cfg))
        self.write("src/app.py", "print('hello')\n")
        self.commit("setup")
        git(root, "checkout", "-qb", "feature")

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self, message: str, *extra: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, *NAME, "commit", "-q", "--allow-empty", "-m", message, *extra)
        return git(self.root, "rev-parse", "HEAD")

    def change(self, path="src/app.py", text="print('hello, world')\n") -> str:
        """The change, then an empty commit whose message holds the note on it: the head."""
        self.write(path, text)
        code = self.commit("Say hello to the world")
        head = self.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def check(self, head: str, command: str | None = None, action="git.merge", **kw) -> dict:
        command = f"git merge --no-ff {head}" if command is None else command
        req = delegation.Request(action=action, command=command, head=head, cwd=str(self.root), env=kw.pop("env", ENV), **kw)
        return delegation.run_check(req)


def codes(result: dict) -> list[str]:
    return [r["code"] for r in result["reasons"]]


class FakeGitHub:
    """The platform's reads, as a test sets them."""

    def __init__(self, tip: str, **facts):
        self.tip, self.facts = tip, facts

    def default_branch(self):
        return "main"

    def branch_tip(self, branch):
        return self.tip

    def __getattr__(self, name):
        if name in ("rules", "pull", "open_pull_for", "tests_run", "pages_branch"):
            return lambda *a: self.facts.get(name)
        raise AttributeError(name)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self, **cfg) -> Repo:
        return Repo(self.root, **cfg)


class LocalMergeTests(Case):
    def test_a_green_local_merge_is_eligible_for_its_exact_command(self):
        repo = self.repo()
        head = repo.change()
        first = repo.check(head)
        self.assertEqual((first["outcome"], codes(first)), ("eligible", []))
        command = first["covers"]["command"]
        self.assertIn("--no-ff -m", command)
        for trailer in first["trailers"]:
            self.assertIn(trailer, command)
        self.assertNotIn("Approved-by", command)
        again = repo.check(head, command)
        self.assertEqual((again["outcome"], again["covers"]["command"]), ("eligible", command), "the hook's rerun of the exact command passes")
        self.assertEqual(len(git(self.root, "worktree", "list").splitlines()), 1, "the check removes its worktree")

    def test_check_reruns_the_suite_for_a_local_merge_and_defers_a_red_one(self):
        repo = self.repo()
        head = repo.change(text="broken = True\n")
        repo.write(".aidd/evidence/evidence.json", json.dumps({"head_sha": head, "results": [{"name": "unit", "red_green": "green", "status": "passed"}]}))
        result = repo.check(head)
        self.assertEqual(codes(result), ["suite-red"], "a green evidence file in the worktree counts for nothing")

    def test_check_defers_a_local_merge_under_team_with_a_remote_or_without_the_tip(self):
        cases = {
            "team": ({"profile": "team"}, "team-review"),
            "unknown deploys": ({"deploys": None}, "deploys-unknown"),
            "merge deploys": ({"deploys": "true"}, "merge-deploys"),
        }
        for name, (cfg, code) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                repo = Repo(Path(d).resolve(), **cfg)
                self.assertIn(code, codes(repo.check(repo.change())))
        repo = self.repo()
        head = repo.change()
        repo.write("README.md", "moved on\n")
        repo.commit("main moves on")
        self.assertEqual(codes(repo.check(head)), ["base-moved"])

    def test_check_defers_a_local_merge_with_a_remote(self):
        repo = self.repo()
        head = repo.change()
        git(self.root, "remote", "add", "origin", "https://gitlab.com/acme/shop.git")
        self.assertEqual(codes(repo.check(head)), ["platform-not-supported"])
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
        tip = git(self.root, "rev-parse", "main")
        self.assertEqual(codes(repo.check(head, github=FakeGitHub(tip))), ["has-remote"])
        self.assertEqual(codes(repo.check(head, env={**ENV, "AIDD_OFFLINE": "1"})), ["offline"], "it never falls back to local evidence")

    def test_check_refuses_a_moved_head(self):
        repo = self.repo()
        head = repo.change()
        other = git(self.root, "rev-parse", "feature~1")
        self.assertIn("head-moved", codes(repo.check(head, f"git merge --no-ff {other}")))
        git(self.root, "checkout", "-q", "feature")
        self.assertIn("head-moved", codes(repo.check(head)), "the default branch must be checked out at its tip")

    def test_a_tag_named_like_the_default_branch_moves_no_head(self):
        """With a tag named `main`, `symbolic-ref --short HEAD` prints `heads/main`; the check reads the full name."""
        repo = self.repo()
        head = repo.change()
        git(self.root, "tag", "main", "main")
        self.assertNotIn("head-moved", codes(repo.check(head)))

    def test_a_note_must_name_the_head_and_need_nothing(self):
        repo = self.repo()
        repo.write("src/app.py", "print('hi')\n")
        code = repo.commit("Change")
        stale = repo.commit("Note on the parent's parent", "-m", note(git(self.root, "rev-parse", "main")))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(stale)), ["report-other-head"])
        git(self.root, "checkout", "-q", "feature")
        blocked = repo.commit("Note that asks", "-m", note(code, needs="pick a name"))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(blocked)), ["report-blocking"])


class ConfigTests(Case):
    def test_check_reads_the_default_branch_config(self):
        repo = self.repo()
        head = repo.change()
        git(self.root, "checkout", "-q", "feature")
        repo.write(".aidd/config.yaml", config_text(decides="[spec.approve]"))
        git(self.root, *NAME, "commit", "-qam", "narrow on the branch")
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(head)), [], "a branch's config never changes what the tip delegates")
        git(self.root, "checkout", "-q", "-b", "nodelegation", "main")
        repo.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: solo\n')
        git(self.root, *NAME, "commit", "-qam", "no delegation")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "reset", "-q", "--hard", "nodelegation")
        repo.write(".aidd/config.yaml", config_text())  # only in the working tree
        self.assertEqual(codes(repo.check(head)), ["default-branch-unknown"], "the tip's own config names no default branch")

    def test_the_default_branch_comes_from_what_a_person_set(self):
        repo = self.repo()
        head = repo.change()
        self.assertEqual(codes(repo.check(head)), [])
        git(self.root, "branch", "master", "main")  # a second candidate whose config names main too: one answer
        self.assertEqual(codes(repo.check(head)), [])
        git(self.root, "checkout", "-q", "master")
        repo.write(".aidd/config.yaml", config_text().replace("default_branch: main", "default_branch: master"))
        git(self.root, *NAME, "commit", "-qam", "a candidate that names itself")
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(head)), ["default-branch-unknown"], "two candidates each name themselves")
        git(self.root, "branch", "-D", "master")
        git(self.root, "update-ref", "refs/remotes/origin/main", "main")
        self.assertEqual(codes(repo.check(head)), ["default-branch-unknown"], "a remote's ref with no remote")
        git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        git(self.root, "checkout", "-q", "-b", "trunk", "main")
        repo.write(".aidd/config.yaml", config_text().replace("default_branch: main", "default_branch: trunk"))
        git(self.root, *NAME, "commit", "-qam", "a branch that names itself")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "config", "init.defaultBranch", "trunk")
        self.assertEqual(codes(repo.check(head)), [], "the repository's own init.defaultBranch, which an agent can write, is never read")
        globals_file = self.root.parent / "global.gitconfig"
        globals_file.write_text("[init]\n\tdefaultBranch = trunk\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(globals_file)}):
            self.assertEqual(codes(repo.check(head)), ["default-branch-unknown"], "the person's global default names trunk, which names itself too")

    def test_check_defers_after_review_by_and_once_stopped(self):
        repo = self.repo(review_by="2026-01-01")
        head = repo.change()
        self.assertIn("delegation-review-due", codes(repo.check(head, today=dt.date(2026, 6, 1))))
        stop = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir"), *policy.STOP_FILE)
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text("stopped\n", encoding="utf-8")
        self.assertIn("delegation-stopped", codes(repo.check(head, today=dt.date(2025, 6, 1))))

    def test_a_reserved_or_undelegated_action_and_another_harness_defer(self):
        repo = self.repo(decides="[spec.approve]")
        head = repo.change()
        reserved = repo.check(head, "vercel deploy --prod", action="deploy.run")
        self.assertEqual((codes(reserved), reserved["reserved"]), (["reserved-action"], True))
        self.assertEqual(codes(repo.check(head)), ["not-delegated"])
        self.assertEqual(codes(repo.check(head, env={})), ["harness-not-delegated"])

    def test_all_excludes_irreversible(self):
        data = {"actions": {"git.push": {"since": "1.0.0"}, "data.delete": {"since": "1.0.0"}, "git.push.force": {"since": "1.2.0"}}}
        with mock.patch.object(policy, "builtin", return_value=data), mock.patch.object(policy, "irreversible", side_effect=lambda a: a == "data.delete"):
            self.assertEqual(policy.covered({"decides": "all"}, "1.2.0"), ["git.push", "git.push.force"])
            self.assertEqual(policy.covered({"decides": "all"}, "1.0.0"), ["git.push"], "a later aidd's action needs its name")
            self.assertEqual(policy.covered({"decides": ["data.delete"], "reserved": []}, "1.0.0"), ["data.delete"])
            self.assertEqual(policy.covered({"decides": "all", "reserved": ["git.push"]}, "1.0.0"), [])


class CommandTests(Case):
    def test_check_defers_a_non_canonical_command(self):
        repo = self.repo()
        head = repo.change()
        bad = [
            f"git merge --no-ff {head} && rm -rf src",
            f"git merge {head}",
            f"sudo git merge --no-ff {head}",
            "git merge --no-ff $(git rev-parse feature)",
            f"git merge --no-ff {head} > /dev/null",
            f"git merge --no-ff {head}\nrm -rf src",
            f"git merge --no-ff -m 'my own words' {head}",
        ]
        for command in bad:
            with self.subTest(command):
                self.assertEqual(codes(repo.check(head, command)), ["command-not-canonical"])

    def test_check_refuses_admin_and_repo_flags(self):
        repo = self.repo()
        head = repo.change()
        cases = {
            f"GH_REPO=acme/other gh pr merge 1 --repo acme/shop --squash --match-head-commit {head}": "pr.merge",
            f"gh pr merge 1 --repo acme/shop --squash --admin --match-head-commit {head}": "pr.merge",
            f"git -C ../other merge --no-ff {head}": "git.merge",
        }
        for command, action in cases.items():
            with self.subTest(command):
                result = repo.check(head, command, action=action)
                self.assertEqual((codes(result), result["reserved"]), (["admin-or-repo-flag"], True))

    def test_the_template_fills_and_refuses_word_by_word(self):
        shape = policy.template("git.push")
        sha = "a" * 40
        self.assertEqual(commands.fit(shape, f"git push origin {sha}:refs/heads/feat/cart")[0], {"sha": sha, "branch": "feat/cart"})
        for line in (f"git push origin +{sha}:refs/heads/feat", f"git push origin {sha}:refs/heads/main --force", f"git push upstream {sha}:refs/heads/x"):
            self.assertIsNone(commands.fit(shape, line)[0], line)


class DiffTests(Case):
    def test_check_defers_a_ci_path_a_dependency_or_a_test_script_change(self):
        for path in (".github/workflows/release.yml", "package.json", "Makefile", "conftest.py", ".aidd/config.yaml", "vercel.json"):
            with self.subTest(path), tempfile.TemporaryDirectory() as d:
                repo = Repo(Path(d).resolve())
                text = config_text(extra="  reserved: []\n") if path == ".aidd/config.yaml" else "x = 1\n"
                result = repo.check(repo.change(path, text))
                self.assertIn("reserved-path", codes(result))
                self.assertTrue(result["reserved"])

    def test_a_test_renamed_away_on_the_fast_lane_lost_its_lines(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        body = "".join(f"def test_{i}():\n    assert {i} == {i}\n" for i in range(12))
        repo.write("tests/test_cart.py", body)
        repo.commit("a test")
        git(self.root, "checkout", "-q", "-B", "feature")
        git(self.root, "mv", "tests/test_cart.py", "tests/test_basket.py")
        repo.write("tests/test_basket.py", body.replace("assert 11 == 11", "pass"))
        head = repo.change()
        self.assertIn("tests/test_cart.py", diff_signals.changed_test_files("main", head, str(self.root)))
        self.assertIn("tests-changed", codes(repo.check(head)))

    def test_check_defers_a_deploy_workflow_at_the_tip(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        repo.write(
            ".github/workflows/deploy.yml",
            "name: deploy\non:\n  push:\n    branches: [main]\njobs:\n  ship:\n    environment: production\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ship\n",
        )
        repo.commit("deploy on push")
        git(self.root, "checkout", "-q", "-B", "feature")
        head = repo.change()
        self.assertEqual(codes(repo.check(head)), ["deploy-workflow-found"])

    def test_a_workflow_deploys_on_a_push_only_where_its_filter_reaches(self):
        rs = check_mod.risk.rule_set(None)
        cases = {
            "on: push\njobs:\n  a:\n    steps:\n      - run: vercel deploy --prod\n": ("main", True),
            "on:\n  push:\n    branches: [release/*]\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on:\n  push:\n    branches-ignore: [main]\njobs:\n  a:\n    environment: prod\n": ("main", True),
            "on:\n  push:\n    tags: ['v*']\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on:\n  pull_request:\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on: [push]\njobs:\n  a:\n    steps:\n      - uses: peaceiris/actions-gh-pages@v4\n": ("main", True),
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: pytest\n": ("main", False),
        }
        for text, (branch, deploys) in cases.items():
            with self.subTest(text):
                self.assertEqual(diff_signals.push_reaches(text, branch) and diff_signals.deploy_line(text, rs) is not None, deploys)


class CliShapeTests(unittest.TestCase):
    def test_the_door_and_the_reasons_agree(self):
        self.assertEqual(sorted(delegation.delegable()), ["git.merge", "git.push", "pr.merge", "spec.approve"])
        self.assertIn("suite-red", delegation.reasons())
        with self.assertRaises(delegation.UsageError):
            delegation.run_check(delegation.Request(action="git.merge", head="abc", cwd=tempfile.gettempdir(), env=ENV))
        self.assertTrue(subprocess.run(["git", "--version"], capture_output=True).returncode == 0)


if __name__ == "__main__":
    unittest.main()
