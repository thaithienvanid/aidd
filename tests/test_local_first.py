"""Local-first: the two human decisions and the merge on one machine, with no GitHub or GitLab."""

import argparse
import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_subprocess, build_once, git

from aidd.guard import edit_check
from aidd.guard import approval_commands
from aidd.cli import app, arguments
from aidd.cli.commands import operate
from aidd.platforms import local_context
from aidd.gate import decision_report
from aidd.workitems import decision_records
from aidd.platforms import local_land
from aidd.kernel.timestamps import parse_time
from aidd.gate import decide, policy


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
        decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", head), self.root)
        reviews, comments, notes = decision_records.load_local_approvals(self.root)
        self.assertEqual([(r["user"], r["state"], r["commit_sha"]) for r in reviews], [("email:me@example.com", "approved", head)])
        self.assertEqual(comments[0]["body"], f"/aidd approve-spec SPEC-1 {head}")
        self.assertIn("not signed", notes[0])
        self.assertEqual(git(self.root, "branch", "--list").split(), ["*", "main"])  # no branch, no tag
        self.assertEqual(git(self.root, "tag", "--list"), "")
        ctx = local_context.build_local_context(repo=self.root, base="main", run_policy=False)
        self.assertEqual(ctx["reviews"][0]["commit_sha"], head)

    def test_a_record_from_before_1_0_with_its_old_trailer_still_counts(self):
        """Records written before 1.0 name where the person decided as `Aidd-Confirmed-In`, the trailer's old name:
        they read as they did."""
        head = git(self.root, "rev-parse", "HEAD").strip()
        old = decision_records.approve_merge_line(head) + "\n\nAidd-Confirmed-In: claude-code"
        decision_records.record_local_approval(old, self.root)
        decision_records.record_local_approval(f"Aidd-Land: {head}\n\nSaid at 2026-09-01T00:00:00+00:00.\n\nAidd-Confirmed-In: prompt", self.root)
        reviews, _, _ = decision_records.load_local_approvals(self.root)
        self.assertEqual([r["commit_sha"] for r in reviews], [head])
        self.assertTrue(decision_records.land_said(self.root, head, ["email:me@example.com"]))

    def test_once_signing_is_set_up_an_unsigned_approval_does_not_count(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)  # written before signing was configured, or by an agent
        git(self.root, "config", "user.signingkey", "/nonexistent/key")
        reviews, comments, notes = decision_records.load_local_approvals(self.root)
        self.assertEqual((reviews, comments), ([], []))
        self.assertIn("not signed with a trusted key", notes[0])

    def test_only_a_good_signature_from_the_approvers_own_principal_counts(self):
        self.assertFalse(decision_records.is_signature_trusted("U", "", "me@example.com", ssh=False))  # a key anyone can make
        self.assertTrue(decision_records.is_signature_trusted("G", "", "me@example.com", ssh=False))
        self.assertFalse(decision_records.is_signature_trusted("G", "agent@example.com", "me@example.com", ssh=True))
        if not shutil.which("ssh-keygen"):
            self.skipTest("ssh-keygen is required")
        keys = tempfile.TemporaryDirectory()
        self.addCleanup(keys.cleanup)
        key = Path(keys.name) / "agent-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", str(key))):
            git(self.root, "config", k, v)
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)  # a good signature, from a key nobody vouched for
        self.assertEqual(decision_records.load_local_approvals(self.root)[0], [])
        allowed = Path(keys.name) / "allowed_signers"
        git(self.root, "config", "gpg.ssh.allowedSignersFile", str(allowed))
        pub = Path(f"{key}.pub").read_text(encoding="utf-8").strip()
        allowed.write_text(f"someone-else@example.com {pub}\n", encoding="utf-8")  # trusted, but for another principal
        self.assertEqual(decision_records.load_local_approvals(self.root)[0], [])
        allowed.write_text(f"me@example.com {pub}\n", encoding="utf-8")
        self.assertEqual([r["commit_sha"] for r in decision_records.load_local_approvals(self.root)[0]], [head])

    def test_the_base_branch_config_decides_whether_approvals_must_be_signed(self):
        Path(self.root, ".aidd").mkdir()
        cfg = 'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: [email:me@example.com]\n'
        Path(self.root, ".aidd/config.yaml").write_text(cfg, encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "b")
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(
            decision_records.approve_merge_line(head), self.root
        )  # unsigned, as an agent that cleared signing would write it
        block = (
            "```yaml aidd\nroute: minor\ntype: docs\nconfidence: high\nscope: [b.txt]\nrollback: Revert.\n"
            "assisted_by: []\nrisk:\n  summary: A text file.\n  dimensions: []\n  reversible: true\n```\n"
        )
        ctx = local_context.build_local_context(repo=self.root, base="main", body=block, run_policy=False)
        self.assertEqual([r["verified"] for r in ctx["reviews"]], [False])
        self.assertEqual(decide(ctx).record["approved_by"], ["email:me@example.com"])

        def does_not_count(ctx):
            # The context carries the approval as unverified, with a note; the gate, not the adapter, drops it.
            self.assertEqual([r["verified"] for r in ctx["reviews"]], [False])
            self.assertTrue(any("no local approval counts" in n for n in ctx["notes"]), ctx["notes"])
            d = decide(ctx)
            self.assertEqual(d.record["approved_by"], [])
            self.assertIn("warn merge_approval.unsigned", d.codes())
            self.assertIn("pending merge_approval.missing", d.codes())
            self.assertEqual(d.notes, ctx["notes"])
            self.assertIn(f"note: {ctx['notes'][0]}", decision_report.decision_text(d))
            self.assertIn("no local approval counts", decision_report.decision_markdown(d))

        git(self.root, "switch", "-q", "main")
        Path(self.root, ".aidd/config.yaml").write_text(cfg + "gates:\n  local_approvals: signed\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "require signed approvals")
        git(self.root, "switch", "-q", "feat")
        does_not_count(local_context.build_local_context(repo=self.root, base="main", body=block, run_policy=False))
        # A branch cannot loosen it: the requirement is read from the base.
        Path(self.root, ".aidd/config.yaml").write_text(cfg + "gates:\n  local_approvals: any\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "try to loosen")
        does_not_count(local_context.build_local_context(repo=self.root, base="main", body=block, run_policy=False))

    def test_recording_never_overwrites_an_approval_written_meanwhile(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        first, _ = decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)
        real = decision_records.git.run

        def stale(args, cwd=".", check=True, env=None):  # the ref did not exist when this recorder looked
            return "" if args[:1] == ["rev-parse"] else real(args, cwd, check, env)

        with mock.patch.object(decision_records.git, "run", stale), self.assertRaises(decision_records.git.GitError):
            decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)
        self.assertEqual(git(self.root, "rev-parse", decision_records.DECISIONS_REF).strip(), first)

    def test_a_malformed_entry_is_skipped_with_a_note(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval("half an entry\x1eand another", self.root)
        decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)
        reviews, _, notes = decision_records.load_local_approvals(self.root)
        self.assertEqual([r["commit_sha"] for r in reviews], [head])
        self.assertTrue(any("control separator" in n for n in notes), notes)

    def test_the_local_push_time_is_the_head_commits_committer_date(self):
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", ".")
        env = os.environ | {"GIT_COMMITTER_DATE": "2026-09-01T10:00:00+00:00"}
        subprocess.run(["git", "commit", "-qm", "b"], cwd=self.root, env=env, check=True)
        ctx = local_context.build_local_context(repo=self.root, base="main", run_policy=False)
        self.assertEqual(parse_time(ctx["head_pushed_at"]), parse_time("2026-09-01T10:00:00Z"))

    def test_the_local_policy_sees_what_the_platform_policy_sees(self):
        Path(self.root, ".aidd").mkdir()
        Path(self.root, ".aidd/config.yaml").write_text(
            'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: [email:me@example.com]\npolicy:\n  command: ["true"]\n', encoding="utf-8"
        )
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "adopt")
        git(self.root, "switch", "-qc", "feat")
        git(self.root, "mv", "a.txt", "moved.txt")
        git(self.root, "commit", "-qm", "move")
        with mock.patch.object(policy, "evaluate_in_base", return_value={"result": "allow"}) as ev:
            local_context.build_local_context(repo=self.root, base="main")
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
            local_land.land_locally("feat", "main", squash=True, message="x", head=verified, cwd=self.root)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feat")
        # A conflict: the merge is undone, the branch checked out again, and the recovery named.
        git(self.root, "switch", "-q", "main")
        Path(self.root, "a.txt").write_text("main\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "main moves")
        git(self.root, "switch", "-q", "feat")
        head = git(self.root, "rev-parse", "HEAD").strip()
        for squash in (True, False):
            with self.assertRaisesRegex(RuntimeError, "git merge main"):
                local_land.land_locally("feat", "main", squash=squash, message="x", head=head, cwd=self.root)
            self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feat")
            self.assertEqual(git(self.root, "status", "--porcelain", "--untracked-files=no"), "")
            self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main").strip(), "main moves")

    def test_the_guard_sees_approve_and_ship_through_any_wrapper(self):
        for command in (
            "uvx aidd approve merge",
            "uvx --from aidd aidd land --squash",
            "uv run aidd approve spec specs/SPEC-1.md",
            "pipx run aidd land",
            "python3 -m aidd approve merge",
            "script -q /dev/null aidd approve merge",
            "echo specs/SPEC-1.md | xargs aidd approve spec",
            "/usr/local/bin/aidd land",
            "sh -c 'uvx aidd approve merge'",
        ):
            self.assertIsNotNone(approval_commands.forbidden_action(command), command)
        for command in (
            "uvx aidd list --branch",
            "aidd gate --paths src/a.py",
            "aidd gate --base main",
            "grep -rn 'aidd approve' docs",
            "echo run aidd land yourself",
            "git commit -m 'aidd land'",
        ):
            self.assertIsNone(approval_commands.forbidden_action(command), command)

    def test_the_guard_keeps_agents_off_the_decision_records(self):
        for command in (
            f"git update-ref {decision_records.DECISIONS_REF} deadbeef",
            f"git commit-tree 4b825dc -m 'Aidd-Merge-Approval: abc' | xargs git update-ref {decision_records.DECISIONS_REF}",
            f"git push origin {decision_records.DECISIONS_REF}",
        ):
            self.assertIn(decision_records.DECISIONS_REF, approval_commands.forbidden_action(command) or "", command)
        for command in (f"git log {decision_records.DECISIONS_REF}", "grep -rn Aidd-Merge-Approval src"):
            self.assertIsNone(approval_commands.forbidden_action(command), command)

    def test_the_guard_protects_the_default_branch_from_force_and_delete(self):
        git(self.root, "branch", "-m", "main", "trunk-of-mine")
        git(self.root, "remote", "add", "origin", self.root)
        git(self.root, "fetch", "-q", "origin")
        git(self.root, "remote", "set-head", "origin", "trunk-of-mine")
        self.assertIsNone(approval_commands.forbidden_action("git push -f origin trunk-of-mine"))  # without a root, the default branch is unknown
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
            self.assertIsNotNone(approval_commands.forbidden_action(command, self.root), command)
        git(self.root, "switch", "-qc", "feat")
        for command in ("git push -f", "git push --force origin feat", "git push origin --delete feat"):
            self.assertIsNone(approval_commands.forbidden_action(command, self.root), command)
        # With no CI gate the local gate is the gate, so even a plain push lands work on the default branch only through
        # `aidd land`.
        self.assertIn("aidd land", approval_commands.forbidden_action("git push origin trunk-of-mine", self.root) or "")

    def test_agents_cannot_approve_or_ship(self):
        for command in ("aidd approve merge", "aidd approve spec specs/SPEC-1.md", "python3 -m aidd land --squash", "cd x && aidd land"):
            self.assertIsNotNone(approval_commands.forbidden_action(command), command)
        self.assertIsNone(approval_commands.forbidden_action("aidd gate --paths src/a.py"))
        person = {k: v for k, v in os.environ.items() if k not in local_land.AGENT_ENV} | {"PYTHONPATH": str(ROOT / "src")}
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
        self.assertFalse(git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip())  # nothing was recorded
        with mock.patch.dict(os.environ, {"AIDD_AGENT": "1"}), self.assertRaises(local_land.NotAPerson):
            local_land.require_person("Merge approval", ask=shown_code)

    def test_a_squash_keeps_every_agents_provenance(self):
        git(self.root, "switch", "-qc", "feat")
        for i, agent in enumerate(("claude-code/claude-opus-5-5", "codex/gpt-5", "claude-code/claude-opus-5-5")):
            Path(self.root, f"f{i}.txt").write_text(str(i), encoding="utf-8")
            git(self.root, "add", ".")
            git(self.root, "commit", "-qm", f"step {i}\n\nAssisted-by: {agent}")
        new = local_land.land_locally("feat", "main", squash=True, message="Add the feature (SPEC-1)", cwd=self.root)
        body = git(self.root, "log", "-1", "--format=%B", new)
        self.assertTrue(body.startswith("Add the feature (SPEC-1)"))
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5\nAssisted-by: codex/gpt-5", body)
        self.assertEqual(git(self.root, "rev-list", "--count", "main").strip(), "2")  # day 0 plus one squashed commit


# The short Spec `aidd new spec` writes, filled in as the Quickstart fills it.
SPEC_FIELDS = {
    "owner_team: maintainers": "owner_team: shop",  # solo's default team
    "assisted_by: []": "assisted_by: [claude-code/claude-opus-5-5]",
    'summary: "TODO: who or what behaves differently after this change"': "summary: Cart totals can apply a discount.",
    'title: "TODO: the first slice"': "title: Add discount()",
    'scope: ["src/TODO/"]': "scope: [app/discount.py]",
    'files: ["tests/TODO"]': "files: [tests/test_discount.py]",
    'command: ["TODO"]': f'command: [{json.dumps(sys.executable)}, "-m", "unittest", "tests.test_discount"]',
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
    """The answer a person gives a confirmation prompt, `[y/N]`: yes."""
    assert prompt.endswith("[y/N] "), prompt
    return "y"


@contextlib.contextmanager
def at_a_terminal(answer: str | None = None):
    """Run in-process as a person at an interactive terminal who, when asked, types `answer`, or with no `answer` yes.
    Yields (stdout, stderr, input)."""
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
    def test_a_person_at_a_terminal_confirms_with_yes(self):
        with at_a_terminal() as (_, _, asked):
            self.assertIsNone(local_land.require_person("Merge approval for the head commit abc1234", question="Approve merging feat at abc1234?"))
        self.assertEqual(asked.call_args.args[0], "Approve merging feat at abc1234? [y/N] ")
        for wrong in ("", "n", "no", "abc", "yess", "approve"):  # the default is no
            with self.subTest(answer=wrong), at_a_terminal(wrong), self.assertRaisesRegex(local_land.NotAPerson, "was not confirmed"):
                local_land.require_person("Merge approval")
        for right in ("y", "yes", "  Y \n", "YES"):  # the whitespace a terminal adds, and the case, do not matter
            with self.subTest(answer=right), at_a_terminal(right):
                local_land.require_person("Merge approval")

    def test_end_of_input_at_the_prompt_is_no_confirmation(self):
        # Ctrl-D at the prompt raises EOFError from input(); it must read as "not confirmed", never as a crash.
        with at_a_terminal() as (_, _, asked):
            asked.side_effect = EOFError
            with self.assertRaisesRegex(local_land.NotAPerson, "was not confirmed"):
                local_land.require_person("Merge approval")

    def test_an_agent_shell_is_refused_even_at_a_terminal(self):
        for var in local_land.AGENT_ENV:
            with self.subTest(var=var), mock.patch.dict(os.environ, {var: "1"}), at_a_terminal() as (_, _, asked):
                with self.assertRaisesRegex(local_land.NotAPerson, "an agent started this shell"):
                    local_land.require_person("Merge approval")
                asked.assert_not_called()

    def test_without_a_terminal_nobody_is_asked(self):
        with (
            mock.patch("builtins.input") as asked,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(local_land.NotAPerson, "interactive terminal"),
        ):
            local_land.require_person("Merge approval")
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
        with open(Path(cls.template, ".aidd", "config.yaml"), "a", encoding="utf-8") as fh:
            fh.write("\ngates:\n  spec_approval_required_routes: [normal, major]\n")
        # The bytecode the suite leaves behind, ignored as a Python project ignores it, so the next `aidd test` runs in a clean tree.
        with open(Path(cls.template, ".gitignore"), "a", encoding="utf-8") as fh:
            fh.write("__pycache__/\n")
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
        """`aidd <argv>` in this process, run by a person at a terminal who types `answer`, or with `answer` None yes:
        (exit code, stdout, stderr)."""
        with contextlib.chdir(self.root), at_a_terminal(answer) as (out, err, _):
            code = app.main(list(argv))
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
            ctx = local_context.build_local_context(repo=self.root, base="main", evidence=f"{self.root}/.aidd/evidence/evidence.json", run_policy=False)
            return decide(ctx).rules_at(level)

    def build_to_merge_approval(self, *, approve_merge=True):
        """The loop up to the Merge approval, every step through the command line a person or an agent uses. The first
        test of the class to ask builds it up to the Merge approval; every later one starts from a copy of that
        repository, and each records the Merge approval itself."""
        build_once((type(self).__name__, "merge approval"), self.root, self.build_to_the_merge_approval)  # each test starts it on a fresh copy
        if approve_merge:
            code, _, err = self.as_person(None, "approve", "merge")
            self.assertEqual(code, 0, err)
            self.aidd("gate", "--base", "main")  # passes now

    def build_to_the_merge_approval(self):
        self.spec_and_tests()
        self.assertIn("spec_approval", self.gate_rules("pending"))
        code, out, err = self.as_person(None, "approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        self.assertIn("Approved SPEC-1. Recorded unsigned", out)
        self.assertNotIn("spec_approval", self.gate_rules("pending"))  # the recorded Spec approval counts
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        tested = self.aidd("test", "--base", "main").stdout
        # Paths print relative to the repository root, not as absolute paths.
        self.assertIn("evidence: .aidd/evidence/evidence.json ", tested)
        self.assertRegex(tested, r"log .aidd/evidence/\S+\.log")
        self.assertNotIn(str(self.root), tested)
        self.assertIn("by typing `land it` at their coding agent's prompt", self.aidd("gate", "--base", "main", expect=3).stdout)
        self.assertEqual(self.gate_rules("fail"), [])

    def picked(self, *answers):
        """`aidd approve` alone at a terminal, answering each prompt in turn: (exit code, stdout, the prompts)."""
        with contextlib.chdir(self.root), at_a_terminal() as (out, _, asked):
            asked.side_effect = list(answers)
            code = app.main(["approve"])
        return code, out.getvalue(), [c.args[0] for c in asked.call_args_list]

    def test_several_specs_are_approved_after_one_question(self):
        spec = self.spec_and_tests()
        second = Path(self.root, "specs/SPEC-2.md")
        second.write_text(
            spec.read_text(encoding="utf-8").replace("id: SPEC-1", "id: SPEC-2").replace("trace_id: spec-1", "trace_id: spec-2"), encoding="utf-8"
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-2\n\nAssisted-by: claude-code/claude-opus-5-5")
        with contextlib.chdir(self.root), at_a_terminal() as (out, err, asked):
            code = app.main(["approve", "spec", "SPEC-1", "SPEC-2"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertEqual([c.args[0] for c in asked.call_args_list], ["Approve SPEC-1, SPEC-2? [y/N] "])
        self.assertIn("Approved SPEC-1. Recorded", out.getvalue())
        self.assertIn("Approved SPEC-2. Recorded", out.getvalue())
        self.assertNotIn("spec_approval", self.gate_rules("pending"))
        with contextlib.chdir(self.root), at_a_terminal("n") as (out, err, _):
            self.assertEqual(app.main(["approve", "spec", "SPEC-1", "SPEC-2", "--show"]), 2)  # a preview is one Spec at a time

    def test_approve_alone_lists_what_waits_and_approves_the_one_picked(self):
        self.spec_and_tests()
        code, out, prompts = self.picked("", "y")
        self.assertEqual(code, 0, out)
        self.assertIn("1. SPEC-1", out)
        self.assertIn("Spec approval", out)
        self.assertIn("Nothing approved.", out)
        self.assertFalse(git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip())
        code, out, prompts = self.picked("1", "y")
        self.assertEqual(code, 0, out)
        self.assertEqual(prompts, ["Which one? [1, Enter for none] ", "Approve SPEC-1? [y/N] "])
        self.assertIn("Approved SPEC-1.", out)
        code, out, _ = self.picked()
        self.assertIn("Nothing waits on your approval.", out)

    def test_merge_approval_from_an_mcp_dialog_records_the_head_shown(self):
        from aidd.cli import mcp_server

        self.build_to_merge_approval(approve_merge=False)
        meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "ide"},
            "io.modelcontextprotocol/clientCapabilities": {"elicitation": {}},
        }
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "approve_merge", "arguments": {}, "_meta": meta}}
        with contextlib.chdir(self.root):
            first = mcp_server.handle_message(call, str(self.root))["result"]
            self.assertEqual(first["resultType"], "input_required")
            message = first["inputRequests"]["approve"]["params"]["message"]
            self.assertIn(f"Merge discount at {self.head()[:12]}", message)
            self.assertIn("besides your approval it waits on nothing else", message)
            # A state signed for a Spec approval never approves a merge, and the reverse.
            spec_state = mcp_server._sign_state({"kind": "spec", "id": "SPEC-1", "hash": "0" * 32, "ref": "HEAD", "spec": "specs/SPEC-1.md"})
            accept = {"approve": {"action": "accept", "content": {"decision": "Approve"}}}
            crossed = dict(call, id=2, params={**call["params"], "inputResponses": accept, "requestState": spec_state})
            self.assertTrue(mcp_server.handle_message(crossed, str(self.root))["result"]["isError"])
            retry = dict(call, id=3, params={**call["params"], "inputResponses": accept, "requestState": first["requestState"]})
            done = mcp_server.handle_message(retry, str(self.root))["result"]
        self.assertFalse(done["isError"], done)
        self.assertIn("Approved merging discount", done["content"][0]["text"])
        self.assertIn("Aidd-Decided-Via: mcp:ide", git(self.root, "log", "-1", "--format=%B", decision_records.DECISIONS_REF))
        self.aidd("gate", "--base", "main")  # passes now

    def test_a_confirmed_merge_approval_needs_the_head_the_person_saw(self):
        self.build_to_merge_approval(approve_merge=False)
        shown = json.loads(self.aidd("approve", "merge", "--show").stdout)
        self.assertEqual((shown["branch"], shown["head"], shown["failing"], shown["problems"]), ("discount", self.head(), [], []))
        moved = self.aidd("approve", "merge", "--confirmed", "0" * 40, expect=1)
        self.assertIn("Nothing was recorded", moved.stderr)
        self.aidd("approve", "merge", "--confirmed", self.head())
        self.aidd("gate", "--base", "main")

    def test_next_counts_the_changed_lines_as_the_gate_does(self):
        # The Quickstart branch: a Spec, its test, and the code. The Spec and its tests.files were reviewed at Spec
        # approval, so the gate leaves them out of the changed-line limit; its forecast must count the same, never more.
        from aidd.gate import routing

        self.spec_and_tests()
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        with contextlib.chdir(self.root):
            gate = decide(local_context.build_local_context(repo=self.root, base="main", run_policy=False)).record
            nxt = routing.assess_diff(self.root, "main")
        assert nxt is not None
        self.assertEqual(nxt["changed_lines"], gate["changed_lines"])
        self.assertEqual(gate["changed_lines"], 2)  # app/discount.py alone

    def test_a_change_goes_from_spec_to_main_with_no_platform(self):
        self.build_to_merge_approval()
        with contextlib.chdir(self.root):
            ctx = local_context.build_local_context(repo=self.root, base="main", evidence=f"{self.root}/.aidd/evidence/evidence.json")
            self.assertEqual(decide(ctx).decision, "pass")
            self.assertEqual(operate._land_message(ctx, "discount"), "feat: Apply a percentage discount (SPEC-1)")  # the one Spec's title
        code, out, err = self.as_person(None, "land", "--squash")
        self.assertEqual(code, 0, out + err)
        self.assertIn("landed discount", out)
        self.assertEqual(self.main_log(), ["feat: Apply a percentage discount (SPEC-1)", "chore: adopt aidd", "scaffold"])
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", git(self.root, "log", "-1", "--format=%B", "main"))

    def goal_spec(self, spec_id: str, module: str, func: str, code: str, test: str, *, integrate: bool = False) -> None:
        """One Spec of goal/discount, from its own branch to the goal: written with `--base`, approved, built, tested
        against the goal (no --base anywhere), and landed into it, or integrated by the team with no person asked."""
        git(self.root, "switch", "-q", "goal/discount")
        git(self.root, "switch", "-qc", f"spec/{spec_id}")
        self.aidd("new", "spec", spec_id, "--title", f"Add {func}()", "--type", "feat", "--base", "goal/discount")
        spec = Path(self.root, f"specs/{spec_id}.md")
        text = spec.read_text(encoding="utf-8")
        self.assertIn("base: goal/discount", text)
        fields = {k: v.replace("discount", module) for k, v in SPEC_FIELDS.items()}
        for old, new in fields.items():
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        Path(self.root, f"tests/test_{module}.py").write_text(test, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", f"spec: {spec_id} and its test\n\nAssisted-by: claude-code/claude-opus-5-5")
        self.assertEqual(self.as_person(None, "approve", "spec", f"specs/{spec_id}.md")[0], 0)
        Path(self.root, f"app/{module}.py").write_text(code, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", f"feat: add {func}()\n\nAssisted-by: claude-code/claude-opus-5-5")
        self.aidd("test")
        if integrate:
            out = self.aidd("integrate").stdout  # a child process with no terminal: nobody could be asked
            self.assertIn(f"integrated {spec_id}", out)
            return
        for argv in (["approve", "merge"], ["land", "--squash"]):
            code_, out, err = self.as_person(None, *argv)
            self.assertEqual(code_, 0, out + err)
        self.assertIn("into goal/discount", out)

    def test_the_team_integrates_a_goals_specs_and_the_person_releases_the_goal(self):
        """Integrate is the team's step: a Spec whose approval holds lands in its goal as a merge commit, once its tests
        pass on the merged tree, with no person asked. Sync merges newer work in, never rebasing. The release to main
        is one Merge approval, and the goal gate judges each integrated Spec again."""
        from aidd import workitems

        with open(Path(self.root, ".gitignore"), "a", encoding="utf-8") as ignore:
            ignore.write("__pycache__/\n")
        git(self.root, "commit", "-qam", "chore: ignore bytecode")
        git(self.root, "switch", "-qc", "goal/discount")
        self.aidd("new", "initiative", "INIT-1", "--title", "Discounts")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "plan: discounts\n\nAssisted-by: claude-code/claude-opus-5-5")
        plan = self.head()
        test = "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n"
        self.goal_spec("SPEC-1", "discount", "discount", "def discount(total, percent):\n    return total - total * percent // 100\n", test, integrate=True)
        spec_head = self.head()
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "goal/discount"), "feat: Add discount() (SPEC-1)")
        self.assertEqual(git(self.root, "rev-parse", "goal/discount^2"), spec_head)  # a merge: the approved commits stay as they were
        self.assertEqual(workitems.integrated(self.root, "goal/discount"), {"SPEC-1": spec_head})
        self.assertIn("is already in goal/discount", self.aidd("integrate").stdout)

        # A Spec with no approval never integrates, whoever runs it.
        git(self.root, "switch", "-qc", "spec/SPEC-4", "goal/discount")
        self.aidd("new", "spec", "SPEC-4", "--title", "Add rebate()", "--type", "feat", "--base", "goal/discount")
        spec = Path(self.root, "specs/SPEC-4.md")
        text = spec.read_text(encoding="utf-8")
        for old, new in {k: v.replace("discount", "rebate") for k, v in SPEC_FIELDS.items()}.items():
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        Path(self.root, "tests/test_rebate.py").write_text(test.replace("discount", "rebate"), encoding="utf-8")
        Path(self.root, "app/rebate.py").write_text("def rebate(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add rebate()")
        self.assertIn("Not integrated", self.aidd("integrate", expect=1).stderr)
        self.assertEqual(workitems.integrated(self.root, "goal/discount"), {"SPEC-1": spec_head})

        # A Spec's branch cut before its sibling integrated merges the goal in; the goal merges main in when it moves.
        git(self.root, "switch", "-qc", "spec/SPEC-3", plan)
        Path(self.root, "specs/SPEC-3.md").write_text("---\nkind: spec\nid: SPEC-3\ntitle: t\nbase: goal/discount\n---\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-3")
        self.assertIn("synced goal/discount", self.aidd("sync").stdout)
        self.assertTrue(Path(self.root, "app/discount.py").is_file())
        self.assertIn("already holds", self.aidd("sync").stdout)
        git(self.root, "switch", "-q", "main")
        Path(self.root, "NOTES.md").write_text("hotfix\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "docs: notes")
        git(self.root, "switch", "-q", "goal/discount")
        self.assertIn("synced main", self.aidd("sync").stdout)
        refused = self.aidd("sync", "--from", "spec/SPEC-4", expect=2).stderr  # unapproved work reaches a goal only through integrate
        self.assertIn("A Spec lands with `aidd integrate`", refused)

        # `aidd list` says the goal is ready to release: SPEC-1 integrated, SPEC-3 empty and SPEC-4 unapproved are not.
        listed = json.loads(self.aidd("list", "--json").stdout)
        (goal,) = listed["goals"]
        self.assertEqual((goal["branch"], goal["integrated"], goal["behind"]), ("goal/discount", ["SPEC-1"], 0))
        self.assertFalse(goal["release_ready"])
        self.assertNotIn("SPEC-1", [s.get("id") for s in listed["steps"]])  # integrated: nobody has a step until the release
        for sid in ("SPEC-3", "SPEC-4"):
            git(self.root, "branch", "-D", f"spec/{sid}")
        listed = json.loads(self.aidd("list", "--json").stdout)
        self.assertTrue(listed["goals"][0]["release_ready"], listed["goals"])
        self.assertIn("goal/discount is ready to release", self.aidd("list").stdout)

        # The release: one Merge approval of the goal's head, and the goal gate judges SPEC-1 again.
        self.assertIn("spec-1.acceptance", self.aidd("test").stdout)  # each Spec's own tests, red on main
        for argv in (["approve", "merge"], ["land"]):
            code, out, err = self.as_person(None, *argv)
            self.assertEqual(code, 0, out + err)
        self.assertEqual(self.main_log()[0], "feat: discount (SPEC-1)")

    def test_a_goals_specs_land_in_the_goal_branch_and_the_goal_ships_to_main(self):
        """A goal branch: its plan, then each Spec's branch cut from goal/<name>, naming it as its
        `base`, so test, gate, and ship compare against it and land in it; then the goal ships to main whole, each Spec
        judged as its own change, with one Merge approval."""
        with open(Path(self.root, ".gitignore"), "a", encoding="utf-8") as ignore:
            ignore.write("__pycache__/\n")
        git(self.root, "commit", "-qam", "chore: ignore bytecode")
        main_before = self.main_log()
        git(self.root, "switch", "-qc", "goal/discount")
        self.aidd("new", "initiative", "INIT-1", "--title", "Discounts")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "plan: discounts\n\nAssisted-by: claude-code/claude-opus-5-5")
        test = "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n"
        self.goal_spec("SPEC-1", "discount", "discount", "def discount(total, percent):\n    return total - total * percent // 100\n", test)
        test = test.replace("discount", "coupon").replace("coupon(200, 10), 180", "coupon(200, 10), 190")
        self.goal_spec("SPEC-2", "coupon", "coupon", "def coupon(total, amount):\n    return total - amount\n", test)
        self.assertEqual(self.main_log(), main_before)  # main waits for the goal
        self.assertEqual(
            git(self.root, "log", "-2", "--format=%s", "goal/discount").splitlines(), ["feat: Add coupon() (SPEC-2)", "feat: Add discount() (SPEC-1)"]
        )
        # The goal ships to main: no Change Request block needed on a goal branch, each Spec's tests run, one Merge approval.
        git(self.root, "switch", "-q", "goal/discount")
        tested = self.aidd("test").stdout
        self.assertIn("spec-1.acceptance", tested)
        self.assertIn("spec-2.acceptance", tested)
        code, out, err = self.as_person(None, "approve", "merge")
        self.assertEqual(code, 0, out + err)
        with contextlib.chdir(self.root):
            ctx = local_context.build_local_context(repo=self.root, base="main", evidence=f"{self.root}/.aidd/evidence/evidence.json")
            d = decide(ctx)
        self.assertEqual(d.decision, "pass", [(f.level, f.code, f.message) for f in d.findings if f.level != "warn"])
        self.assertEqual([s["spec_id"] for s in d.record["specs"]], ["SPEC-1", "SPEC-2"])
        self.assertTrue(all(s["spec_approval_before_implementation"] for s in d.record["specs"]))  # the other Spec's code is not this one's
        self.assertNotIn("warn spec_approval.after_implementation", d.codes())
        with contextlib.chdir(self.root):
            # A block that leaves SPEC-2 out never carries its work: it is outside SPEC-1's scope.
            ctx = local_context.build_local_context(repo=self.root, base="main", body=local_context.spec_block("specs/SPEC-1.md"))
            self.assertIn("fail scope.outside", decide(ctx).codes())
        code, out, err = self.as_person(None, "land")
        self.assertEqual(code, 0, out + err)
        self.assertIn("into main", out)
        self.assertEqual(self.main_log()[0], "feat: discount (SPEC-1, SPEC-2)")
        self.assertTrue(Path(self.root, "app/coupon.py").is_file())
        # A Spec names its base, but only a goal branch the work is cut from counts: never any other target.
        for claimed in ("goal/discount", "release"):
            git(self.root, "switch", "-qc", f"other-{claimed.replace('/', '-')}", "main~1")
            Path(self.root, "specs/SPEC-9.md").write_text(f"---\nkind: spec\nid: SPEC-9\ntitle: t\nbase: {claimed}\n---\n", encoding="utf-8")
            git(self.root, "add", "-A")
            git(self.root, "commit", "-qm", "spec: SPEC-9")
            git(self.root, "branch", "-f", "release", "main")
            args = argparse.Namespace(base=None)
            with contextlib.chdir(self.root):
                arguments.base_from_spec(args)
            self.assertIsNone(args.base, claimed)

    def test_a_small_goal_that_ships_together_opens_integrates_takes_a_fix_and_undoes(self):
        """An Epic with `reaches: batched` gets goal/<EPIC> once its plan is on main; its Specs take that base from it;
        the goal is ready only when every planned Spec is in; a fast-lane fix integrates too; `--undo` takes a Spec
        out again."""
        from aidd import workitems

        with open(Path(self.root, ".gitignore"), "a", encoding="utf-8") as ignore:
            ignore.write("__pycache__/\n")
        epic = '---\naidd_version: "1.0.0"\nkind: epic\nid: EPIC-1\ntitle: Discounts\ngoal: "10% of carts use a discount"\nreaches: batched\nspecs: [SPEC-1, SPEC-2]\n---\n'
        Path(self.root, "specs").mkdir(exist_ok=True)
        Path(self.root, "specs/EPIC-1.md").write_text(epic, encoding="utf-8")
        Path(self.root, "specs/EPIC-2.md").write_text(epic.replace("EPIC-1", "EPIC-2").replace("reaches: batched\n", ""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "plan: discounts")
        self.assertIn("opened goal/EPIC-1", self.aidd("goal", "open", "EPIC-1").stdout)
        self.assertIn("is open", self.aidd("goal", "open", "EPIC-1").stdout)
        self.assertIn("is incremental", self.aidd("goal", "open", "EPIC-2", expect=2).stderr)

        git(self.root, "switch", "-qc", "spec/SPEC-1", "goal/EPIC-1")
        self.aidd("new", "spec", "SPEC-1", "--title", "Add discount()", "--type", "feat", "--parent", "EPIC-1")
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        self.assertIn("base: goal/EPIC-1", text)  # from its Epic: no agent picks the goal
        for old, new in SPEC_FIELDS.items():
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        test = "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n"
        Path(self.root, "tests/test_discount.py").write_text(test, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5")
        self.assertEqual(self.as_person(None, "approve", "spec", "specs/SPEC-1.md")[0], 0)
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        self.aidd("test")
        self.assertIn("integrated SPEC-1", self.aidd("integrate").stdout)

        (goal,) = json.loads(self.aidd("list", "--json").stdout)["goals"]
        self.assertEqual((goal["epic"], goal["integrated"], goal["waiting"], goal["release_ready"]), ("EPIC-1", ["SPEC-1"], ["SPEC-2"], False))

        # A fast-lane fix cut from the goal integrates too, naming the goal.
        git(self.root, "switch", "-qc", "fix/notes", "goal/EPIC-1")
        Path(self.root, "docs").mkdir(exist_ok=True)
        Path(self.root, "docs/discounts.md").write_text("# Discounts\n\nA percentage off the total.\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "docs: discounts")
        self.aidd("describe", "--commit", "--base", "goal/EPIC-1")
        self.assertIn("integrated the fix", self.aidd("integrate", "--goal", "goal/EPIC-1").stdout)
        self.assertEqual(git(self.root, "show", "goal/EPIC-1:docs/discounts.md").splitlines()[0], "# Discounts")

        # Taking SPEC-1 out again: one revert on the goal, and the goal no longer holds it.
        self.assertIn("took SPEC-1 out of goal/EPIC-1", self.aidd("integrate", "--undo", "SPEC-1").stdout)
        self.assertEqual(workitems.integrated(self.root, "goal/EPIC-1"), {})
        self.assertNotEqual(subprocess.run(["git", "cat-file", "-e", "goal/EPIC-1:app/discount.py"], cwd=self.root).returncode, 0)
        self.assertIn("no goal branch holds SPEC-1", self.aidd("integrate", "--undo", "SPEC-1", expect=2).stderr)

    def test_a_ship_without_squash_keeps_the_branch_history(self):
        self.build_to_merge_approval()
        branch_head = self.head()
        code, out, err = self.as_person(None, "land")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(git(self.root, "rev-parse", "main^2"), branch_head)  # a merge commit whose second parent is the branch
        self.assertEqual(self.main_log()[0], "feat: Apply a percentage discount (SPEC-1)")
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_a_ship_the_person_does_not_confirm_merges_nothing(self):
        self.build_to_merge_approval()
        for typed in ("main", "discount"):  # the branch name an agent knows is no confirmation either
            code, _, err = self.as_person(typed, "land")
            self.assertEqual(code, 1)
            self.assertIn("was not confirmed", err)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])

    def test_a_confirmed_ship_lands_only_the_head_the_person_saw(self):
        self.build_to_merge_approval(approve_merge=False)
        head = self.head()
        moved = self.aidd("land", "--confirmed", "0" * 40, expect=1)
        self.assertIn("Nothing was landed", moved.stderr)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])
        # A shell cannot claim an MCP client's dialog: that answer counts only inside aidd's MCP server (the next test).
        forged = self.aidd("land", "--confirmed", head, "--decided-via", "mcp:ide", expect=1)
        self.assertIn("counts only from aidd's MCP server", forged.stderr)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])
        landed = self.aidd("land", "--confirmed", head, "--decided-via", "claude-code")  # no terminal: the dialog was the question
        self.assertIn(f"landed discount at {head[:12]} into main", landed.stdout)
        self.assertIn("Aidd-Decided-Via: claude-code", git(self.root, "log", "-1", "--format=%B", decision_records.DECISIONS_REF))

    def test_ship_from_an_mcp_dialog_runs_the_tests_and_lands(self):
        from aidd.cli import mcp_server

        self.build_to_merge_approval(approve_merge=False)
        meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "ide"},
            "io.modelcontextprotocol/clientCapabilities": {"elicitation": {}},
        }
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "land", "arguments": {"squash": True}, "_meta": meta}}
        with contextlib.chdir(self.root):
            first = mcp_server.handle_message(call, str(self.root))["result"]
            self.assertEqual(first["resultType"], "input_required")
            message = first["inputRequests"]["approve"]["params"]["message"]
            self.assertIn(f"Land discount at {self.head()[:12]} into main as one squashed commit", message)
            self.assertIn("The tests run again first", message)
            self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])  # asking ships nothing
            accept = {"approve": {"action": "accept", "content": {"decision": "Approve"}}}
            retry = dict(call, id=2, params={**call["params"], "inputResponses": accept, "requestState": first["requestState"]})
            done = mcp_server.handle_message(retry, str(self.root))["result"]
        self.assertFalse(done["isError"], done)
        self.assertIn("landed discount", done["content"][0]["text"])
        self.assertEqual(len(self.main_log()), 3)  # one squashed commit landed

    def test_ship_refuses_the_base_branch_and_a_dirty_tree(self):
        code, _, err = self.as_person(None, "land")
        self.assertEqual(code, 2)
        self.assertIn("switch to the branch to land", err)
        git(self.root, "switch", "-qc", "feat")
        Path(self.root, "app/cart.py").write_text("def total(items):\n    return sum(items) + 0\n", encoding="utf-8")
        code, _, err = self.as_person(None, "land")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", err)
        self.assertEqual(self.main_log(), ["chore: adopt aidd", "scaffold"])

    def test_ship_with_a_pending_gate_merges_nothing(self):
        # Pending on more than the Merge approval `aidd land` may record: a frozen test changed after Spec approval.
        self.build_to_merge_approval(approve_merge=False)
        with open(Path(self.root, "tests/test_discount.py"), "a", encoding="utf-8") as fh:
            fh.write("# edited after Spec approval\n")
        git(self.root, "commit", "-qam", "test: edit a frozen test\n\nAssisted-by: claude-code/claude-opus-5-5")
        main = git(self.root, "rev-parse", "main")
        code, out, err = self.as_person(None, "land", "--squash")
        self.assertEqual(code, 1, out + err)
        self.assertIn("Not landed: the local gate is pending (details below)", err)
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
        self.assertEqual(git(self.root, "for-each-ref", decision_records.DECISIONS_REF), "")  # nothing was recorded

    def test_ship_runs_the_tests_itself_and_ignores_evidence_on_disk(self):
        git(self.root, "switch", "-qc", "broken")
        Path(self.root, "app/cart.py").write_text("def total(items):\n    return 0\n", encoding="utf-8")
        # A valid Change Request block (as `aidd describe --commit` records it), so the declaration passes and the tests decide.
        block = "```yaml aidd\nroute: minor\ntype: fix\nscope: [app/cart.py]\nassisted_by: [claude-code/claude-opus-5-5]\n```"
        git(self.root, "commit", "-qam", f"fix: break the cart\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5")
        head = self.head()
        forged = Path(self.root, ".aidd", "evidence", "evidence.json")
        forged.parent.mkdir()
        forged.write_text(
            json.dumps({"head_sha": head, "base_sha": head, "results": [{"name": "suite", "red_green": "green", "status": "passed", "exit": 0}]}),
            encoding="utf-8",
        )
        decision_records.record_local_approval(decision_records.approve_merge_line(head), self.root)
        run = self.aidd("land", "--squash", expect=1)
        self.assertIn("Not landed: the local gate fails (details below)", run.stderr)
        self.assertIn('"status": "failed"', forged.read_text(encoding="utf-8"))  # rewritten by the run on this head
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "chore: adopt aidd")

    def test_ship_names_the_newest_commit_when_there_is_no_spec(self):
        ctx = {"head_sha": "0" * 40, "change": {"body": ""}, "commits": [{"message": "newest\n\nbody"}, {"message": "oldest"}]}
        self.assertEqual(operate._land_message(ctx, "b"), "newest")

    def test_worktrees_share_the_approvals_and_keep_their_own_work(self):
        wt = str(Path(self.tmp.name) / "task-2")
        git(self.root, "worktree", "add", "-q", wt, "-b", "task-2", "main")
        head = git(wt, "rev-parse", "HEAD")
        decision_records.record_local_approval(decision_records.approve_merge_line(head), wt)
        self.assertEqual(decision_records.load_local_approvals(self.root)[0][0]["commit_sha"], head)  # recorded in one worktree, read in another
        self.assertIn("Nothing is open on this branch", self.aidd("list", "--branch", cwd=wt).stdout)
        self.assertEqual(edit_check.check_edit(wt, "specs/SPEC-2.md", "product-manager")[0], "allow")


if __name__ == "__main__":
    unittest.main()
