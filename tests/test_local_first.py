"""Local-first: the two human decisions and the merge on one machine, with no GitHub or GitLab."""

import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_subprocess, git

from aidd import cli, guard, local, localctx, report
from aidd.util import parse_time
from aidd.verify import verify


@unittest.skipUnless(shutil.which("git"), "git is required")
class LocalFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = str(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        Path(self.root, "a.txt").write_text("a\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "day 0")

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_approval_is_recorded_outside_every_branch_and_read_back(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        local.record(local.approve_merge_line(head), self.root)
        local.record(local.approve_spec_line("SPEC-1", "0" * 32, head), self.root)
        reviews, comments, notes = local.load(self.root)
        self.assertEqual([(r["user"], r["state"], r["commit_sha"]) for r in reviews], [("email:me@example.com", "approved", head)])
        self.assertEqual(comments[0]["body"], f"/aidd approve-spec SPEC-1 {'0' * 32} {head}")
        self.assertIn("not signed", notes[0])
        self.assertEqual(git(self.root, "branch", "--list").split(), ["*", "main"])  # no branch, no tag
        self.assertEqual(git(self.root, "tag", "--list"), "")
        ctx = localctx.build(repo=self.root, base="main", run_policy=False)
        self.assertEqual(ctx["reviews"][0]["commit_sha"], head)

    def test_once_signing_is_set_up_an_unsigned_approval_does_not_count(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        local.record(local.approve_merge_line(head), self.root)  # written before signing was configured, or by an agent
        git(self.root, "config", "user.signingkey", "/nonexistent/key")
        reviews, comments, notes = local.load(self.root)
        self.assertEqual((reviews, comments), ([], []))
        self.assertIn("not signed with a trusted key", notes[0])

    def test_only_a_good_signature_from_the_approvers_own_principal_counts(self):
        self.assertFalse(local.verified("U", "", "me@example.com", ssh=False))  # a key anyone can make
        self.assertTrue(local.verified("G", "", "me@example.com", ssh=False))
        self.assertFalse(local.verified("G", "agent@example.com", "me@example.com", ssh=True))
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen is required")
        keys = tempfile.TemporaryDirectory()
        self.addCleanup(keys.cleanup)
        key = Path(keys.name) / "agent-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", str(key))):
            git(self.root, "config", k, v)
        head = git(self.root, "rev-parse", "HEAD").strip()
        local.record(local.approve_merge_line(head), self.root)  # a good signature, from a key nobody vouched for
        self.assertEqual(local.load(self.root)[0], [])
        allowed = Path(keys.name) / "allowed_signers"
        git(self.root, "config", "gpg.ssh.allowedSignersFile", str(allowed))
        pub = Path(f"{key}.pub").read_text(encoding="utf-8").strip()
        allowed.write_text(f"someone-else@example.com {pub}\n", encoding="utf-8")  # trusted, but for another principal
        self.assertEqual(local.load(self.root)[0], [])
        allowed.write_text(f"me@example.com {pub}\n", encoding="utf-8")
        self.assertEqual([r["commit_sha"] for r in local.load(self.root)[0]], [head])

    def test_the_base_branch_config_decides_whether_approvals_must_be_signed(self):
        Path(self.root, ".aidd").mkdir()
        cfg = 'aidd_version = "1.0.0"\nprofile = "solo"\n[owners]\napprovers = ["email:me@example.com"]\n'
        Path(self.root, ".aidd/config.toml").write_text(cfg, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "b")
        head = git(self.root, "rev-parse", "HEAD").strip()
        local.record(local.approve_merge_line(head), self.root)  # unsigned, as an agent that cleared signing would write it
        block = (
            '```toml aidd\nroute = "minor"\ntype = "docs"\nconfidence = "high"\nscope = ["b.txt"]\nrollback = "Revert."\n'
            'assisted_by = []\n[risk]\nsummary = "A text file."\ndimensions = []\nreversible = true\n```\n'
        )
        ctx = localctx.build(repo=self.root, base="main", body=block, run_policy=False)
        self.assertEqual([r["verified"] for r in ctx["reviews"]], [False])
        self.assertEqual(verify(ctx).record["approved_by"], ["email:me@example.com"])

        def does_not_count(ctx):
            # The context carries the approval as unverified, with a note; the gate, not the adapter, drops it.
            self.assertEqual([r["verified"] for r in ctx["reviews"]], [False])
            self.assertTrue(any("no local approval counts" in n for n in ctx["notes"]), ctx["notes"])
            d = verify(ctx)
            self.assertEqual(d.record["approved_by"], [])
            self.assertIn("warn merge_approval.unsigned", d.codes())
            self.assertIn("pending merge_approval.missing", d.codes())
            self.assertEqual(d.notes, ctx["notes"])
            self.assertIn(f"note: {ctx['notes'][0]}", report.text(d))
            self.assertIn("no local approval counts", report.markdown(d))

        git(self.root, "switch", "-q", "main")
        Path(self.root, ".aidd/config.toml").write_text(cfg + '[gates]\nlocal_approvals = "signed"\n', encoding="utf-8")
        git(self.root, "commit", "-qam", "require signed approvals")
        git(self.root, "switch", "-q", "feat")
        does_not_count(localctx.build(repo=self.root, base="main", body=block, run_policy=False))
        # A branch cannot loosen it: the requirement is read from the base.
        Path(self.root, ".aidd/config.toml").write_text(cfg + '[gates]\nlocal_approvals = "any"\n', encoding="utf-8")
        git(self.root, "commit", "-qam", "try to loosen")
        does_not_count(localctx.build(repo=self.root, base="main", body=block, run_policy=False))

    def test_recording_never_overwrites_an_approval_written_meanwhile(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        first, _ = local.record(local.approve_merge_line(head), self.root)
        real = local.gitutil.run

        def stale(args, cwd=".", check=True, env=None):  # the ref did not exist when this recorder looked
            return "" if args[:1] == ["rev-parse"] else real(args, cwd, check, env)

        with mock.patch.object(local.gitutil, "run", stale), self.assertRaises(local.gitutil.GitError):
            local.record(local.approve_merge_line(head), self.root)
        self.assertEqual(git(self.root, "rev-parse", local.APPROVALS_REF).strip(), first)

    def test_a_malformed_entry_is_skipped_with_a_note(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        local.record("half an entry\x1eand another", self.root)
        local.record(local.approve_merge_line(head), self.root)
        reviews, _, notes = local.load(self.root)
        self.assertEqual([r["commit_sha"] for r in reviews], [head])
        self.assertTrue(any("control separator" in n for n in notes), notes)

    def test_the_local_cooloff_starts_at_the_head_commits_committer_date(self):
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        env = os.environ | {"GIT_COMMITTER_DATE": "2026-09-01T10:00:00+00:00"}
        subprocess.run(["git", "commit", "-qm", "b"], cwd=self.root, env=env, check=True)
        ctx = localctx.build(repo=self.root, base="main", run_policy=False)
        self.assertEqual(parse_time(ctx["head_pushed_at"]), parse_time("2026-09-01T10:00:00Z"))

    def test_the_local_policy_sees_what_the_platform_policy_sees(self):
        Path(self.root, ".aidd").mkdir()
        Path(self.root, ".aidd/config.toml").write_text(
            'aidd_version = "1.0.0"\nprofile = "solo"\n[owners]\napprovers = ["email:me@example.com"]\n[policy]\ncommand = ["true"]\n', encoding="utf-8"
        )
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        git(self.root, "mv", "a.txt", "moved.txt")
        git(self.root, "commit", "-qm", "move")
        with mock.patch.object(localctx.policy, "evaluate_in_base", return_value={"result": "allow"}) as ev:
            localctx.build(repo=self.root, base="main")
        kw = ev.call_args.kwargs
        self.assertEqual(sorted(kw["paths"]), ["a.txt", "moved.txt"])  # the rename source too, as on GitHub and GitLab
        self.assertEqual(kw["cfg"].profile, "solo")
        self.assertIn("changed_lines", kw)

    def test_ship_merges_the_verified_commit_or_nothing(self):
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "a.txt").write_text("feat\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "feat")
        verified = git(self.root, "rev-parse", "HEAD").strip()
        Path(self.root, "a.txt").write_text("feat, moved on\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "after the gate")
        with self.assertRaisesRegex(RuntimeError, "moved"):
            local.ship("feat", "main", squash=True, message="x", head=verified, cwd=self.root)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feat")
        # A conflict: the merge is undone, the branch checked out again, and the recovery named.
        git(self.root, "switch", "-q", "main")
        Path(self.root, "a.txt").write_text("main\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "main moves")
        git(self.root, "switch", "-q", "feat")
        head = git(self.root, "rev-parse", "HEAD").strip()
        for squash in (True, False):
            with self.assertRaisesRegex(RuntimeError, "git merge main"):
                local.ship("feat", "main", squash=squash, message="x", head=head, cwd=self.root)
            self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feat")
            self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=no"), "")
            self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main").strip(), "main moves")

    def test_the_guard_sees_approve_and_ship_through_any_wrapper(self):
        for command in (
            "uvx aidd approve merge",
            "uvx --from aidd aidd ship --squash",
            "uv run aidd approve spec specs/SPEC-1.md",
            "pipx run aidd ship",
            "python3 -m aidd approve merge",
            "script -q /dev/null aidd approve merge",
            "echo specs/SPEC-1.md | xargs aidd approve spec",
            "/usr/local/bin/aidd ship",
            "sh -c 'uvx aidd approve merge'",
        ):
            self.assertIsNotNone(guard.forbidden_action(command), command)
        for command in ("uvx aidd assess", "aidd gate --base main", "grep -rn 'aidd approve' docs", "echo run aidd ship yourself", "git commit -m 'aidd ship'"):
            self.assertIsNone(guard.forbidden_action(command), command)

    def test_the_guard_keeps_agents_off_the_approvals_ref(self):
        for command in (
            f"git update-ref {local.APPROVALS_REF} deadbeef",
            f"git commit-tree 4b825dc -m 'Aidd-Merge-Approval: abc' | xargs git update-ref {local.APPROVALS_REF}",
            f"git push origin {local.APPROVALS_REF}",
        ):
            self.assertIn(local.APPROVALS_REF, guard.forbidden_action(command) or "", command)
        for command in (f"git log {local.APPROVALS_REF}", "grep -rn Aidd-Merge-Approval src"):
            self.assertIsNone(guard.forbidden_action(command), command)

    def test_the_guard_protects_the_default_branch_from_force_and_delete(self):
        git(self.root, "branch", "-m", "main", "trunk-of-mine")
        git(self.root, "remote", "add", "origin", self.root)
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "remote", "set-head", "origin", "trunk-of-mine")
        self.assertIsNone(guard.forbidden_action("git push -f origin trunk-of-mine"))  # without a root, the default branch is unknown
        for command in (
            "git push -f origin trunk-of-mine",
            "git push --force",  # no refspec: the current branch, which is the default branch
            "git push --force-with-lease origin",
            "git push origin +HEAD",
            "git push origin --delete trunk-of-mine",
            "git push origin :trunk-of-mine",
            "git push -d origin main",
            "git push --mirror origin",
        ):
            self.assertIsNotNone(guard.forbidden_action(command, self.root), command)
        git(self.root, "switch", "-qc", "feat")
        for command in ("git push -f", "git push --force origin feat", "git push origin --delete feat"):
            self.assertIsNone(guard.forbidden_action(command, self.root), command)
        # With no CI gate the local gate is the gate, so even a plain push lands work on the default branch only through
        # `aidd ship`.
        self.assertIn("aidd ship", guard.forbidden_action("git push origin trunk-of-mine", self.root) or "")

    def test_agents_cannot_approve_or_ship(self):
        for command in ("aidd approve merge", "aidd approve spec specs/SPEC-1.md", "python3 -m aidd ship --squash", "cd x && aidd ship"):
            self.assertIsNotNone(guard.forbidden_action(command), command)
        self.assertIsNone(guard.forbidden_action("aidd assess"))
        person = {k: v for k, v in os.environ.items() if k not in local.AGENT_ENV} | {"PYTHONPATH": str(ROOT / "src")}
        for env, reason in (
            (person, "needs a person at an interactive terminal"),
            (person | {"CLAUDE_CODE_CHILD_SESSION": "1"}, "an agent started this shell"),
            (person | {"CLAUDECODE": "1"}, "a terminal no agent started"),
            (person | {"AI_AGENT": "1"}, "a terminal no agent started"),
        ):
            run = subprocess.run(
                [sys.executable, "-m", "aidd", "approve", "merge"],
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 1)
            self.assertIn(reason, run.stderr)
            self.assertTrue(run.stderr.rstrip().endswith(":\n  aidd approve merge"), run.stderr)  # the command, for the person to copy
        self.assertFalse(git(self.root, "for-each-ref", local.APPROVALS_REF).strip())  # nothing was recorded
        with mock.patch.dict(os.environ, {"AIDD_AGENT": "1"}), self.assertRaises(local.NotAPerson):
            local.require_person("Merge approval", ask=shown_code)

    def test_a_squash_keeps_every_agents_provenance(self):
        git(self.root, "switch", "-qc", "feat")
        for i, agent in enumerate(("claude-code/claude-opus-5-5", "codex/gpt-5", "claude-code/claude-opus-5-5")):
            Path(self.root, f"f{i}.txt").write_text(str(i), encoding="utf-8")
            git(self.root, "add", ".")
            git(self.root, "commit", "-qm", f"step {i}\n\nAssisted-by: {agent}")
        new = local.ship("feat", "main", squash=True, message="Add the feature (SPEC-1)", cwd=self.root)
        body = git(self.root, "log", "-1", "--format=%B", new)
        self.assertTrue(body.startswith("Add the feature (SPEC-1)"))
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5\nAssisted-by: codex/gpt-5", body)
        self.assertEqual(git(self.root, "rev-list", "--count", "main").strip(), "2")  # day 0 plus one squashed commit


# The short Spec `aidd new spec` writes, filled in as the Quickstart fills it.
SPEC_FIELDS = {
    'owner_team = "maintainers"': 'owner_team = "shop"',  # solo's default team
    "assisted_by = []": 'assisted_by = ["claude-code/claude-opus-5-5"]',
    'summary = "TODO: who or what behaves differently after this change"': 'summary = "Cart totals can apply a discount."',
    'title = "TODO: the first slice"': 'title = "Add discount()"',
    'scope = ["src/TODO/"]': 'scope = ["app/discount.py"]',
    'files = ["tests/TODO"]': 'files = ["tests/test_discount.py"]',
    'command = ["TODO"]': f'command = [{json.dumps(sys.executable)}, "-m", "unittest", "tests.test_discount"]',
    "TODO: quote the request.": "Checkout needs a percentage discount.",
    "- A1: TODO: given ..., when ..., then ...": "- A1: given a total of 200, when a 10% discount applies, then the total is 180",
    "TODO: the approach.": "One pure function, discount(total, percent), in app/discount.py.",
    "TODO: how to undo it.": "Revert the change; nothing is stored.",
}


class _Terminal(io.StringIO):
    """Output that says it is a terminal, as a person's shell is."""

    def isatty(self):
        return True


def shown_code(prompt: str) -> str:
    """The one-time code a confirmation prompt shows."""
    found = re.search(r"Type (\S+) to approve: $", prompt)
    assert found, prompt
    return found.group(1)


@contextlib.contextmanager
def at_a_terminal(answer: str | None = None):
    """Run in-process as a person at an interactive terminal who, when asked, types `answer`, or with no `answer` the
    one-time code the prompt shows. Yields (stdout, stderr, input)."""
    out, err = _Terminal(), io.StringIO()
    with (
        mock.patch.object(sys, "stdin", _Terminal()),
        mock.patch("builtins.input", side_effect=lambda prompt: shown_code(prompt) if answer is None else answer) as asked,
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        yield out, err, asked


@unittest.skipUnless(shutil.which("git"), "git is required")
class RequirePersonTests(unittest.TestCase):
    def test_a_person_at_a_terminal_confirms_by_typing_the_one_time_code_shown(self):
        with at_a_terminal() as (_, _, asked):
            self.assertIsNone(local.require_person("Merge approval for the head commit abc1234"))
        code = shown_code(asked.call_args.args[0])
        self.assertRegex(code, rf"^[{local.CODE_ALPHABET}]{{{local.CODE_LENGTH}}}$")
        with mock.patch.object(local, "one_time_code", return_value="K7Q2XM"):
            for wrong in ("", "abc", "yes", "K7Q2X", "K7Q2XMM", "K7Q2XN"):
                with self.subTest(answer=wrong), at_a_terminal(wrong), self.assertRaisesRegex(local.NotAPerson, "was not confirmed"):
                    local.require_person("Merge approval")
            for right in ("K7Q2XM", "  K7Q2XM \n", "k7q2xm"):  # the whitespace a terminal adds, and the case, do not matter
                with self.subTest(answer=right), at_a_terminal(right):
                    local.require_person("Merge approval")

    def test_end_of_input_at_the_prompt_is_no_confirmation(self):
        # Ctrl-D at the prompt raises EOFError from input(); it must read as "not confirmed", never as a crash.
        with at_a_terminal() as (_, _, asked):
            asked.side_effect = EOFError
            with self.assertRaisesRegex(local.NotAPerson, "was not confirmed"):
                local.require_person("Merge approval")

    def test_what_an_agent_knows_ahead_of_time_does_not_confirm(self):
        # An agent that starts a terminal running `aidd approve` could type the Spec id, the head commit, or the
        # branch name before the prompt appears; the one-time code is made only when it does.
        for known in ("SPEC-1", "abc1234", "discount", "yes", "y"):
            with self.subTest(answer=known), at_a_terminal(known), self.assertRaisesRegex(local.NotAPerson, "was not confirmed"):
                local.require_person("Spec approval for SPEC-1: its Spec and tests at abc1234")
        codes = {local.one_time_code() for _ in range(200)}
        self.assertGreater(len(codes), 195)  # fresh each time, never a fixed value

    def test_an_agent_shell_is_refused_even_at_a_terminal(self):
        for var in local.AGENT_ENV:
            with self.subTest(var=var), mock.patch.dict(os.environ, {var: "1"}), at_a_terminal() as (_, _, asked):
                with self.assertRaisesRegex(local.NotAPerson, "an agent started this shell"):
                    local.require_person("Merge approval")
                asked.assert_not_called()

    def test_without_a_terminal_nobody_is_asked(self):
        with mock.patch("builtins.input") as asked, contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(local.NotAPerson, "interactive terminal"):
            local.require_person("Merge approval")
        asked.assert_not_called()


@unittest.skipUnless(shutil.which("git"), "git is required")
class LocalLoopTests(unittest.TestCase):
    """The whole loop on one machine: a Spec, its approval, the build, the evidence, the Merge approval, and the ship."""

    @classmethod
    def setUpClass(cls):
        # One adopted repository for the class; each test works on a copy of it.
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = str(Path(cls.template_dir.name) / "shop")
        os.mkdir(cls.template)
        git(cls.template, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(cls.template, "config", k, v)
        for rel, text in {
            "app/__init__.py": "",
            "tests/__init__.py": "",
            "app/cart.py": "def total(items):\n    return sum(items)\n",
            "tests/test_cart.py": "import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n",
        }.items():
            Path(cls.template, rel).parent.mkdir(parents=True, exist_ok=True)
            Path(cls.template, rel).write_text(text, encoding="utf-8")
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "scaffold")
        suite = f"{shlex.quote(sys.executable)} -m unittest"
        run = aidd_subprocess(
            "init", "--profile", "solo", "--approvers", "email:me@example.com", "--test", suite, "--ci", "none", "--harness", "none", cwd=cls.template
        )
        assert run.returncode == 0, run.stdout + run.stderr
        # Solo asks for Spec approval on major changes only; this one asks on normal ones too, so the loop records it.
        with open(Path(cls.template, ".aidd", "config.toml"), "a", encoding="utf-8") as fh:
            fh.write('\n[gates]\nspec_approval_routes = ["normal", "major"]\n')
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "chore: adopt aidd")

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name) / "shop")
        shutil.copytree(self.template, self.root, symlinks=True)

    def aidd(self, *args, expect=0, cwd=None):
        """`aidd <args>` in a child process, which has no terminal; fails the test unless it exits `expect`."""
        run = aidd_subprocess(*args, cwd=cwd or self.root)
        self.assertEqual(run.returncode, expect, f"aidd {' '.join(args)}\n{run.stdout}\n{run.stderr}")
        return run

    def as_person(self, answer, *argv):
        """`aidd <argv>` in this process, run by a person at a terminal who types `answer`, or with `answer` None the
        one-time code the prompt shows: (exit code, stdout, stderr)."""
        with contextlib.chdir(self.root), at_a_terminal(answer) as (out, err, _):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def head(self):
        return git(self.root, "rev-parse", "HEAD")

    def main_log(self):
        return git(self.root, "log", "--format=%s", "main").splitlines()

    def spec_and_tests(self):
        """On a new branch: SPEC-1 and its failing test, committed. Returns the Spec's path."""
        git(self.root, "switch", "-qc", "discount")
        self.aidd("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--type", "feat")
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        for old, new in SPEC_FIELDS.items():
            self.assertIn(old, text, old)
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        Path(self.root, "tests/test_discount.py").write_text(
            "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n",
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5")
        return spec

    def gate_rules(self, level):
        """The rules the local gate reports at `level` for this branch, from the evidence `aidd test` wrote."""
        with contextlib.chdir(self.root):
            ctx = localctx.build(repo=self.root, base="main", evidence=f"{self.root}/aidd-evidence/evidence.json", run_policy=False)
            return verify(ctx).rules_at(level)

    def build_to_merge_approval(self, *, approve_merge=True):
        """The loop up to the Merge approval, every step through the command line a person or an agent uses."""
        self.spec_and_tests()
        self.assertIn("spec_approval", self.gate_rules("pending"))
        code, out, err = self.as_person(None, "approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        self.assertIn("recorded an unsigned approval", out)
        self.assertNotIn("spec_approval", self.gate_rules("pending"))  # the recorded Spec approval counts
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        tested = self.aidd("test", "--base", "main").stdout
        # Paths print relative to the repository root, not as absolute paths.
        self.assertIn("evidence: aidd-evidence/evidence.json ", tested)
        self.assertRegex(tested, r"log aidd-evidence/\S+\.log")
        self.assertNotIn(str(self.root), tested)
        self.assertIn("a person runs `aidd approve merge`", self.aidd("gate", "--base", "main", expect=3).stdout)
        self.assertEqual(self.gate_rules("fail"), [])
        if approve_merge:
            code, _, err = self.as_person(None, "approve", "merge")
            self.assertEqual(code, 0, err)
            self.aidd("gate", "--base", "main")  # passes now

    def test_next_counts_the_changed_lines_as_the_gate_does(self):
        # The Quickstart branch: a Spec, its test, and the code. The Spec and its tests.files were reviewed at Spec
        # approval, so the gate leaves them out of the budget; `aidd assess` must count the same, never more.
        from aidd import rules as aidd_rules

        self.spec_and_tests()
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        with contextlib.chdir(self.root):
            gate = verify(localctx.build(repo=self.root, base="main", run_policy=False)).record
            nxt = aidd_rules.assess_diff(self.root, "main")
        assert nxt is not None
        self.assertEqual(nxt["changed_lines"], gate["changed_lines"])
        self.assertEqual(gate["changed_lines"], 2)  # app/discount.py alone

    def test_a_change_goes_from_spec_to_main_with_no_platform(self):
        self.build_to_merge_approval()
        with contextlib.chdir(self.root):
            ctx = localctx.build(repo=self.root, base="main", evidence=f"{self.root}/aidd-evidence/evidence.json")
            self.assertEqual(verify(ctx).decision, "pass")
            self.assertEqual(cli._ship_message(ctx, "discount"), "Apply a percentage discount (SPEC-1)")  # the one Spec's title
        code, out, err = self.as_person(None, "ship", "--squash")
        self.assertEqual(code, 0, out + err)
        self.assertIn("shipped discount", out)
        self.assertEqual(self.main_log(), ["Apply a percentage discount (SPEC-1)", "chore: adopt aidd", "scaffold"])
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", git(self.root, "log", "-1", "--format=%B", "main"))

    def test_a_ship_without_squash_keeps_the_branch_history(self):
        self.build_to_merge_approval()
        branch_head = self.head()
        code, out, err = self.as_person(None, "ship")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(git(self.root, "rev-parse", "main^2"), branch_head)  # a merge commit whose second parent is the branch
        self.assertEqual(self.main_log()[0], "Apply a percentage discount (SPEC-1)")
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_a_ship_the_person_does_not_confirm_merges_nothing(self):
        self.build_to_merge_approval()
        for typed in ("main", "discount"):  # the branch name an agent knows is no confirmation either
            code, _, err = self.as_person(typed, "ship")
            self.assertEqual(code, 1)
            self.assertIn("was not confirmed", err)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])

    def test_ship_refuses_the_base_branch_and_a_dirty_tree(self):
        code, _, err = self.as_person(None, "ship")
        self.assertEqual(code, 2)
        self.assertIn("switch to the branch to ship", err)
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "app/cart.py").write_text("def total(items):\n    return sum(items) + 0\n", encoding="utf-8")
        code, _, err = self.as_person(None, "ship")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", err)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])

    def test_ship_with_a_pending_gate_merges_nothing(self):
        # Pending on more than the Merge approval `aidd ship` may record: a frozen test changed after Spec approval.
        self.build_to_merge_approval(approve_merge=False)
        with open(Path(self.root, "tests/test_discount.py"), "a", encoding="utf-8") as fh:
            fh.write("# edited after Spec approval\n")
        git(self.root, "commit", "-qam", "test: edit a frozen test\n\nAssisted-by: claude-code/claude-opus-5-5")
        main = git(self.root, "rev-parse", "main")
        code, out, err = self.as_person(None, "ship", "--squash")
        self.assertEqual(code, 1, out + err)
        self.assertIn("Not shipped: the local gate is pending (details below)", err)
        self.assertIn("spec_approval", out)
        self.assertEqual(git(self.root, "rev-parse", "main"), main)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "discount")

    def test_approve_spec_takes_only_what_is_committed(self):
        code, _, err = self.as_person(None, "approve", "spec")
        self.assertEqual((code, "name the Spec" in err), (2, True))
        code, _, err = self.as_person(None, "approve", "spec", "specs/SPEC-404.md")
        self.assertEqual((code, "no such Spec" in err), (2, True))
        spec = self.spec_and_tests()
        spec.write_text(spec.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        code, _, err = self.as_person(None, "approve", "spec", "specs/SPEC-1.md")
        self.assertEqual((code, "uncommitted changes" in err), (1, True))
        git(self.root, "checkout", "--", "specs/SPEC-1.md")
        Path(self.root, "tests/test_discount.py").write_text("# weakened\n", encoding="utf-8")  # a frozen test, modified
        code, _, err = self.as_person(None, "approve", "spec", "specs/SPEC-1.md")
        self.assertEqual((code, "uncommitted changes" in err), (1, True))
        git(self.root, "checkout", "--", "tests/test_discount.py")
        Path(self.root, "specs/SPEC-2.md").write_text(spec.read_text(encoding="utf-8").replace("SPEC-1", "SPEC-2"), encoding="utf-8")
        code, _, err = self.as_person(None, "approve", "spec", "specs/SPEC-2.md")
        self.assertEqual((code, "is not committed" in err), (1, True))
        self.assertEqual(git(self.root, "for-each-ref", local.APPROVALS_REF), "")  # nothing was recorded

    def test_ship_runs_the_tests_itself_and_ignores_evidence_on_disk(self):
        git(self.root, "switch", "-qc", "broken")
        Path(self.root, "app/cart.py").write_text("def total(items):\n    return 0\n", encoding="utf-8")
        # A valid Change Request block (as `aidd describe --commit` records it), so the declaration passes and the tests decide.
        block = '```toml aidd\nroute = "minor"\ntype = "fix"\nscope = ["app/cart.py"]\nassisted_by = ["claude-code/claude-opus-5-5"]\n```'
        git(self.root, "commit", "-qam", f"fix: break the cart\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5")
        head = self.head()
        forged = Path(self.root, "aidd-evidence", "evidence.json")
        forged.parent.mkdir()
        forged.write_text(
            json.dumps({"head_sha": head, "base_sha": head, "results": [{"name": "suite", "red_green": "green", "status": "passed", "exit": 0}]}),
            encoding="utf-8",
        )
        local.record(local.approve_merge_line(head), self.root)
        run = self.aidd("ship", "--squash", expect=1)
        self.assertIn("Not shipped: the local gate fails (details below)", run.stderr)
        self.assertIn('"status": "failed"', forged.read_text(encoding="utf-8"))  # rewritten by the run on this head
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "chore: adopt aidd")

    def test_ship_names_the_newest_commit_when_there_is_no_spec(self):
        ctx = {"head_sha": "0" * 40, "change": {"body": ""}, "commits": [{"message": "newest\n\nbody"}, {"message": "oldest"}]}
        self.assertEqual(cli._ship_message(ctx, "b"), "newest")

    def test_worktrees_share_the_approvals_and_keep_their_own_work(self):
        wt = str(Path(self.tmp.name) / "task-2")
        git(self.root, "worktree", "add", "-q", wt, "-b", "task-2", "main")
        head = git(wt, "rev-parse", "HEAD")
        local.record(local.approve_merge_line(head), wt)
        self.assertEqual(local.load(self.root)[0][0]["commit_sha"], head)  # recorded in one worktree, read in another
        self.assertIn("nothing is open on this branch", self.aidd("assess", cwd=wt).stdout)
        self.assertEqual(guard.check_edit(wt, "specs/SPEC-2.md", "product-manager")[0], "allow")


if __name__ == "__main__":
    unittest.main()
