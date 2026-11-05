"""`aidd delegate check`'s checks, on real repositories with no network: a stand-in GitHub reader where a remote exists.
Each check defers on the first fact it cannot prove, and the model's part is an eval, never one of the checks."""

import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git, hermetic_environ

from aidd import delegation
from aidd.delegation import check as check_mod  # noqa: F401  (test_delegation_spec reads it from here)
from aidd.delegation import commands, diff_signals, policy  # noqa: F401
from aidd.kernel import strict_yaml

ENV = {"CLAUDECODE": "1"}
NAME = ["-c", "user.name=Maya", "-c", "user.email=maya@users.noreply.github.com"]
SUITE = "import pathlib, sys; sys.exit(1 if 'broken' in pathlib.Path('src/app.py').read_text() else 0)"


def config_text(profile="solo", environments=(), review_due="2099-01-01", decides="[spec.approve, git.push, git.merge, pr.merge]", extra="", top=""):
    """`environments` is the list the config declares, `()` for none deploys from a push, and None for unset. `top` is more
    top-level config, such as an `extends` parent."""
    deploys = strict_yaml.dump({"environments": list(environments)}) if environments is not None else ""
    return (
        'aidd_version: "1.0.0"\n'
        f"profile: {profile}\n"
        f"{top}"
        f"{deploys}"
        "tests:\n"
        "  - name: unit\n"
        f"    command: [python3, -c, {json.dumps(SUITE)}]\n"
        "delegation:\n"
        "  default_branch: main\n"
        '  set_by: "Maya Lee <maya@users.noreply.github.com>"\n'
        f"  decides: {decides}\n"
        f'  review_due: "{review_due}"\n' + extra
    )


def note(head: str, needs: str = "none") -> str:
    return f'```aidd-handoff\ndone: verified\nnext_role: reviewer\nneeds: {needs}\nstopped_at: none\nhead: "{head}"\n```\n'


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
            return lambda *a: self.fact(name)
        raise AttributeError(name)

    def fact(self, name):
        """What a test set for a read: its answer, or the error it raises."""
        value = self.facts.get(name)
        if isinstance(value, Exception):
            raise value
        return value


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

    def test_the_merge_runs_the_suite_with_require_green_so_it_excuses_nothing(self):
        from unittest import mock

        from aidd.delegation import local_run
        from aidd.testing import runner

        repo = self.repo()
        head = repo.change()
        with mock.patch.object(runner, "run_tests", return_value=({"results": []}, [])) as run:
            local_run.run_on_head(str(self.root), head, "main")
        self.assertTrue(run.call_args.kwargs["require_green"], "a run that gates a merge excuses no failing test")

    def test_a_merge_no_test_applies_to_defers_with_its_own_code_and_a_next_step(self):
        """The base's config limits its only command to docs, so a change to src/ has no test that could show it works: a green
        run proves nothing, and the merge defers, as `aidd status` reads the run as no test applied, never passed."""
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        scoped = (
            (self.root / ".aidd/config.yaml").read_text(encoding="utf-8").replace("    command: [python3", "    when_changed: [docs/**]\n    command: [python3")
        )
        repo.write(".aidd/config.yaml", scoped)
        repo.commit("scope the suite to docs")
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        result = repo.check(repo.change())
        self.assertEqual(codes(result), ["untested"])
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        docs = repo.check(repo.change(path="docs/guide.md", text="guide\n"))
        self.assertEqual(codes(docs), [], "a change a test covers is judged as ever")

    def test_check_reruns_the_suite_for_a_local_merge_and_defers_a_red_one(self):
        repo = self.repo()
        head = repo.change(text="broken = True\n")
        repo.write(".aidd/evidence/evidence.json", json.dumps({"head_sha": head, "results": [{"name": "unit", "red_green": "green", "status": "passed"}]}))
        result = repo.check(head)
        self.assertEqual(codes(result), ["suite_red"], "a green evidence file in the worktree counts for nothing")

    def test_check_defers_a_local_merge_under_team_with_a_remote_or_without_the_tip(self):
        cases = {
            "team": ({"profile": "team"}, "team_review"),
        }
        for name, (cfg, code) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                repo = Repo(Path(d).resolve(), **cfg)
                self.assertIn(code, codes(repo.check(repo.change())))
        repo = self.repo()
        head = repo.change()
        repo.write("README.md", "moved on\n")
        repo.commit("main moves on")
        self.assertEqual(codes(repo.check(head)), ["base_moved"])

    def test_check_defers_a_local_merge_with_a_remote(self):
        repo = self.repo()
        head = repo.change()
        git(self.root, "remote", "add", "origin", "https://gitlab.com/acme/shop.git")
        self.assertEqual(codes(repo.check(head)), ["platform_not_supported"])

    def test_a_remote_that_names_no_repository_is_not_on_github(self):
        """The check reads the remote's `owner/name` as `aidd init` does: a `..` name is no repository."""
        repo = self.repo()
        head = repo.change()
        git(self.root, "remote", "add", "origin", "https://github.com/acme/..")
        self.assertEqual(codes(repo.check(head)), ["platform_not_supported"])
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
        tip = git(self.root, "rev-parse", "main")
        self.assertEqual(codes(repo.check(head, github=FakeGitHub(tip))), ["has_remote"])
        self.assertEqual(codes(repo.check(head, env={**ENV, "AIDD_OFFLINE": "1"})), ["offline"], "it never falls back to local evidence")

    def test_check_refuses_a_moved_head(self):
        repo = self.repo()
        head = repo.change()
        other = git(self.root, "rev-parse", "feature~1")
        self.assertIn("head_moved", codes(repo.check(head, f"git merge --no-ff {other}")))
        git(self.root, "checkout", "-q", "feature")
        self.assertIn("head_moved", codes(repo.check(head)), "the default branch must be checked out at its tip")

    def test_a_tag_named_like_the_default_branch_moves_no_head(self):
        """With a tag named `main`, `symbolic-ref --short HEAD` prints `heads/main`; the check reads the full name."""
        repo = self.repo()
        head = repo.change()
        git(self.root, "tag", "main", "main")
        self.assertNotIn("head_moved", codes(repo.check(head)))

    def test_a_note_must_name_the_head_and_need_nothing(self):
        repo = self.repo()
        repo.write("src/app.py", "print('hi')\n")
        code = repo.commit("Change")
        stale = repo.commit("Note on the parent's parent", "-m", note(git(self.root, "rev-parse", "main")))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(stale)), ["note_other_head"])
        git(self.root, "checkout", "-q", "feature")
        blocked = repo.commit("Note that asks", "-m", note(code, needs="pick a name"))
        git(self.root, "checkout", "-q", "main")
        self.assertEqual(codes(repo.check(blocked)), ["note_needs_decision"])


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
        self.assertEqual(codes(repo.check(head)), ["default_branch_unknown"], "the tip's own config names no default branch")

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
        self.assertEqual(codes(repo.check(head)), ["default_branch_unknown"], "two candidates each name themselves")
        git(self.root, "branch", "-D", "master")
        git(self.root, "update-ref", "refs/remotes/origin/main", "main")
        self.assertEqual(codes(repo.check(head)), ["default_branch_unknown"], "a remote's ref with no remote")
        git(self.root, "update-ref", "-d", "refs/remotes/origin/main")
        git(self.root, "checkout", "-q", "-b", "trunk", "main")
        repo.write(".aidd/config.yaml", config_text().replace("default_branch: main", "default_branch: trunk"))
        git(self.root, *NAME, "commit", "-qam", "a branch that names itself")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "config", "init.defaultBranch", "trunk")
        self.assertEqual(codes(repo.check(head)), [], "the repository's own init.defaultBranch, which an agent can write, is never read")
        home = tempfile.TemporaryDirectory()  # its own folder, never the shared temporary folder above the repository
        self.addCleanup(home.cleanup)
        globals_file = Path(home.name) / "global.gitconfig"
        globals_file.write_text("[init]\n\tdefaultBranch = trunk\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(globals_file)}):
            self.assertEqual(codes(repo.check(head)), ["default_branch_unknown"], "the person's global default names trunk, which names itself too")

    def test_check_defers_after_review_due_and_once_stopped(self):
        repo = self.repo(review_due="2026-01-01")
        head = repo.change()
        self.assertIn("delegation_review_due", codes(repo.check(head, today=dt.date(2026, 6, 1))))
        stop = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir"), *policy.STOP_FILE)
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text("stopped\n", encoding="utf-8")
        self.assertIn("delegation_stopped", codes(repo.check(head, today=dt.date(2025, 6, 1))))

    @unittest.skipIf(os.name == "nt", "a symlink needs no privilege on POSIX only")
    def test_a_link_at_the_stop_file_counts_as_a_stop_even_when_it_points_nowhere(self):
        repo = self.repo()
        head = repo.change()
        stop = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir"), *policy.STOP_FILE)
        stop.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(self.root.parent / "nowhere", stop)
        self.assertFalse(stop.exists())
        self.assertIn("delegation_stopped", codes(repo.check(head, today=dt.date(2025, 6, 1))))

    def test_a_reserved_or_undelegated_action_and_another_harness_defer(self):
        repo = self.repo(decides="[spec.approve]")
        head = repo.change()
        reserved = repo.check(head, "vercel deploy --prod", action="deploy.run")
        self.assertEqual((codes(reserved), reserved["reserved"]), (["reserved_action"], True))
        self.assertEqual(codes(repo.check(head)), ["not_delegated"])
        self.assertEqual(codes(repo.check(head, env={})), ["harness_not_supported"])

    def test_the_undoable_actions_exclude_the_irreversible_and_a_decides_that_is_no_list_decides_nothing(self):
        data = {"actions": {"git.push": {}, "data.delete": {}, "git.push.force": {}}}
        with mock.patch.object(policy, "builtin", return_value=data), mock.patch.object(policy, "irreversible", side_effect=lambda a: a == "data.delete"):
            self.assertEqual(policy.undoable(), ["git.push", "git.push.force"])
            self.assertEqual(policy.covered({"decides": ["data.delete"], "reserved": []}), ["data.delete"])
            self.assertEqual(policy.covered({"decides": ["git.push"], "reserved": ["git.push"]}), [])
            self.assertEqual(policy.covered({"decides": "all", "reserved": []}), [], "a decides that is no list decides nothing")


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
                self.assertEqual(codes(repo.check(head, command)), ["command_not_canonical"])

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
                self.assertEqual((codes(result), result["reserved"]), (["bypass_flag"], True))

    def test_the_folder_flag_names_where_the_command_runs_as_risk_does(self):
        repo = self.repo()
        head = repo.change()
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        args = ("delegate", "check", "--action", "git.merge", "--command", f"git merge --no-ff {head}", "--head", head)
        done = aidd_subprocess(*args, "--folder", str(repo.root), cwd=elsewhere.name, env=hermetic_environ())
        self.assertIn(f"git.merge on {head[:12]}", done.stdout)
        old = aidd_subprocess(*args, "--cwd", str(repo.root), cwd=elsewhere.name, env=hermetic_environ())
        self.assertEqual(old.returncode, 2)
        self.assertIn("unknown option --cwd", old.stderr)

    def test_the_template_fills_and_refuses_word_by_word(self):
        shape = policy.template("git.push")
        sha = "a" * 40
        self.assertEqual(commands.fit(shape, f"git push origin {sha}:refs/heads/feat/cart")[0], {"sha": sha, "branch": "feat/cart"})
        for line in (f"git push origin +{sha}:refs/heads/feat", f"git push origin {sha}:refs/heads/main --force", f"git push upstream {sha}:refs/heads/x"):
            self.assertIsNone(commands.fit(shape, line)[0], line)


class CliShapeTests(unittest.TestCase):
    def test_the_door_and_the_reasons_agree(self):
        self.assertEqual(sorted(policy.delegable()), ["git.merge", "git.push", "pr.merge", "spec.approve"])
        self.assertIn("suite_red", policy.reasons())
        with self.assertRaises(check_mod.UsageError):
            delegation.run_check(delegation.Request(action="git.merge", head="abc", cwd=tempfile.gettempdir(), env=ENV))
        self.assertTrue(subprocess.run(["git", "--version"], capture_output=True).returncode == 0)


if __name__ == "__main__":
    unittest.main()
