"""The delivery flows end to end: the fast lane locally, approvals across a rebase, the Spec phase, shipping onto a
moved base, standard changes by update type, the emergency lane, and flaky tests."""

import contextlib
import io
import json
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, aidd_subprocess, build_once, decide, example, git, repo_state
from test_local_first import SPEC_FIELDS, at_a_terminal

from aidd.cli import app
from aidd.cli import arguments
from aidd.platforms import local_context
from aidd.gate import placement
from aidd.gate import test_runner
from aidd.gate import decision_report
from aidd.gate import inputs
from aidd.gate import routing
from aidd.workitems import decision_records
from aidd.workitems import spec_file
from aidd.kernel import git as gitutil

FEATURE = "02-normal-feature"


def shop(root: Path, profile: str = "solo", approvers: str = "email:me@example.com", extra: str = "") -> None:
    """A small Python shop adopted with `profile`: app/cart.py, its test, and the unittest suite as `tests`. Built once
    in a test process for each set of arguments; a later call copies it."""
    build_once(("shop", profile, approvers, extra), root, lambda: _build_shop(root, profile, approvers, extra))


def _build_shop(root: Path, profile: str, approvers: str, extra: str) -> None:
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    for rel, text in {
        ".gitignore": "__pycache__/\n/.aidd/*/\n",
        "app/__init__.py": "",
        "tests/__init__.py": "",
        "app/cart.py": "def total(items):\n    return sum(items)\n",
        "tests/test_cart.py": "import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n",
    }.items():
        Path(root, rel).parent.mkdir(parents=True, exist_ok=True)
        Path(root, rel).write_text(text, encoding="utf-8")
    _commit(root, "scaffold")
    suite = f"{shlex.quote(sys.executable)} -m unittest"
    run = aidd_subprocess("init", "--profile", profile, "--approvers", approvers, "--test", suite, "--ci", "none", "--harness", "none", cwd=root)
    assert run.returncode == 0, run.stdout + run.stderr
    if extra:
        with open(Path(root, ".aidd", "config.yaml"), "a", encoding="utf-8") as fh:
            fh.write(extra)
    _commit(root, "chore: adopt aidd")


def as_person(root, *argv: str, answer: str | None = None) -> tuple[int, str, str]:
    """`aidd <argv>` in this process, by a person at a terminal who answers yes (or `answer`)."""
    with contextlib.chdir(root), at_a_terminal(answer) as (out, err, _):
        code = app.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def run_cli(root, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


def spec_and_tests(root) -> None:
    """On a new branch: SPEC-1 and its failing test, committed. Built once in a test process from each starting state;
    a later call from the same state copies it."""
    build_once(("spec and tests", repo_state(root)), root, lambda: _spec_and_tests(root))


def _spec_and_tests(root) -> None:
    git(root, "switch", "-qc", "discount")
    run = aidd_subprocess("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--type", "feat", cwd=root)
    assert run.returncode == 0, run.stdout + run.stderr
    spec = Path(root, "specs/SPEC-1.md")
    text = spec.read_text(encoding="utf-8")
    for old, new in SPEC_FIELDS.items():
        text = text.replace(old, new)
    spec.write_text(text, encoding="utf-8")
    Path(root, "tests/test_discount.py").write_text(
        "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n",
        encoding="utf-8",
    )
    _commit(root, "spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5")


def _commit(root, message: str, files: dict[str, str] | None = None) -> str:
    for rel, text in (files or {}).items():
        p = Path(root, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message, "--allow-empty")
    return git(root, "rev-parse", "HEAD")


@unittest.skipUnless(shutil.which("git"), "git is required")
class SpecProofAcrossARebaseTests(unittest.TestCase):
    """A Spec commit rebased away still proves Spec approval came first: its own diff and its Spec's hash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        _commit(self.root, "base", {"README.md": "r\n"})
        git(self.root, "switch", "-qc", "feat")
        self.spec_text = example(FEATURE)["head_files"]["specs/SPEC-220.md"]
        self.spec_commit = _commit(self.root, "spec", {"specs/SPEC-220.md": self.spec_text, "tests/checkout/test_rate_limit.py": "assert False\n"})
        self.approved = spec_file.spec_hash(self.spec_text, gitutil.ls_tree(self.spec_commit, self.root))
        _commit(self.root, "impl", {"src/checkout/rate_limit/limiter.py": "x = 1\n"})

    def lookup(self):
        head = git(self.root, "rev-parse", "HEAD")
        base = git(self.root, "merge-base", "main", head)
        line = [{"body": f"/aidd approve-spec SPEC-220 {self.spec_commit}"}]
        return inputs.approval_commits(self.root, base, head, line, spec="specs/SPEC-220.md")[self.spec_commit]

    def test_a_rebased_spec_commit_keeps_its_own_diff_and_hash(self):
        self.assertEqual(self.lookup(), {"ancestor": True, "paths": ["specs/SPEC-220.md", "tests/checkout/test_rate_limit.py"], "spec_hash": self.approved})
        git(self.root, "switch", "-q", "main")
        _commit(self.root, "main moves", {"OTHER.md": "o\n"})
        git(self.root, "switch", "-q", "feat")
        git(self.root, "rebase", "-q", "main")
        found = self.lookup()
        self.assertFalse(found["ancestor"])  # the rebase replaced it
        self.assertEqual(found["paths"], ["specs/SPEC-220.md", "tests/checkout/test_rate_limit.py"])  # its own diff, not main's
        self.assertEqual(found["spec_hash"], self.approved)

    def test_the_verifier_counts_the_rebased_proof_under_require(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace("\nidentities:", "\ngates:\n  spec_approval_proof: require\n\nidentities:")
        h = spec_file.spec_hash(ctx["head_files"]["specs/SPEC-220.md"], ctx["head_tree"])
        sha = "5" * 40
        ctx["comments"][0]["body"] = f"/aidd approve-spec SPEC-220 {sha}"
        ctx["approval_commits"] = {sha: {"ancestor": False, "paths": ["specs/SPEC-220.md", "tests/checkout/test_rate_limit.py"], "spec_hash": h}}
        d = decide(ctx)
        self.assertEqual((d.decision, d.record["spec_approval_before_implementation"]), ("pass", True))
        # Not rebased but another commit altogether, where the Spec read otherwise: it approved another text, so it does
        # not count, and never with the misleading "after implementation".
        ctx["approval_commits"][sha]["spec_hash"] = "f" * 32
        d = decide(ctx)
        self.assertIn("pending spec_approval.missing", d.codes())
        self.assertNotIn("warn spec_approval.after_implementation", d.codes())


TEAM_CONFIG = (
    'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: [email:alice@example.com]\ntests:\n  - name: unit\n    command: [python3, -m, unittest]\n'
)
MINOR_BLOCK = "```yaml aidd\nroute: minor\ntype: fix\nscope: [a.txt]\nassisted_by: []\nrisk:\n  summary: One line.\n  dimensions: []\n  reversible: true\n```\n"
LINES = "".join(f"line {i}\n" for i in range(1, 21))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ApprovalCarryTests(unittest.TestCase):
    """A Merge approval carries across a trivial rebase, and only a trivial one (local context, real git)."""

    def setUp(self):
        from aidd.workitems import decision_records

        self.local = decision_records
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "dev@example.com")
        _commit(self.root, "adopt", {".aidd/config.yaml": TEAM_CONFIG, "a.txt": LINES})
        git(self.root, "switch", "-qc", "feat")
        self.approved = _commit(self.root, "fix: line 15", {"a.txt": LINES.replace("line 15\n", "line fifteen\n")})
        git(self.root, "config", "user.email", "alice@example.com")
        decision_records.record_local_approval(decision_records.approve_merge_line(self.approved), self.root)
        git(self.root, "config", "user.email", "dev@example.com")

    def main_moves(self, files: dict[str, str]) -> None:
        git(self.root, "switch", "-q", "main")
        _commit(self.root, "main moves", files)
        git(self.root, "switch", "-q", "feat")
        git(self.root, "rebase", "-q", "main")

    def decide(self):
        from aidd.platforms import local_context

        ctx = local_context.build_local_context(repo=self.root, base="main", body=MINOR_BLOCK, run_policy=False)
        ctx["evidence"] = {
            "aidd_version": "1.0.0",
            "head_sha": ctx["head_sha"],
            "base_sha": ctx["base_sha"],
            "results": [{"name": "unit", "command": ["python3", "-m", "unittest"], "red_green": "green", "status": "passed", "exit": 0}],
        }
        return ctx, decide(ctx)

    def test_a_trivial_rebase_carries_the_approval_and_the_record_names_both_heads(self):
        self.main_moves({"b.txt": "unrelated\n", "a.txt": LINES.replace("line 1\n", "line one\n")})  # far from the change
        ctx, d = self.decide()
        self.assertNotEqual(ctx["head_sha"], self.approved)
        self.assertEqual(d.decision, "pass", d.codes())
        self.assertIn("warn merge_approval.carried", d.codes())
        entry = d.record["merge_approvals"][0]
        self.assertEqual((entry["approved_sha"], entry["carried_to"], entry["commit"]), (self.approved, ctx["head_sha"], ctx["head_sha"]))
        self.assertIn("trivial rebase", entry["carry_reason"])

    def test_a_rebase_that_changes_the_diff_does_not_carry(self):
        self.main_moves({"a.txt": LINES.replace("line 13\n", "line thirteen\n")})  # inside the change's context lines
        _, d = self.decide()
        self.assertEqual(d.decision, "pending")
        self.assertIn("warn merge_approval.not_carried", d.codes())
        self.assertIn("pending merge_approval.missing", d.codes())

    def test_a_new_committer_does_not_carry_and_whitespace_counts(self):
        self.main_moves({"b.txt": "unrelated\n"})
        git(self.root, "config", "user.email", "carol@example.com")
        git(self.root, "commit", "-q", "--amend", "--no-edit")  # carol rewrote the head: a new committer
        _, d = self.decide()
        self.assertIn("warn merge_approval.not_carried", d.codes())
        git(self.root, "config", "user.email", "dev@example.com")
        git(self.root, "reset", "-q", "--hard", "main")
        _commit(self.root, "fix: line 15", {"a.txt": LINES.replace("line 15\n", "line fifteen \n")})  # one trailing space
        _, d = self.decide()
        self.assertIn("warn merge_approval.not_carried", d.codes())


@unittest.skipUnless(shutil.which("git"), "git is required")
class SpecPhaseTests(RepoTemplateCase):
    """A branch that holds only the Spec and its tests: `aidd test` exits 0 with the red runs as early proof, and the gate
    leads with Spec approval, asks for no Merge approval, and never passes."""

    @classmethod
    def build_template(cls, root):
        shop(root, "team", "email:alice@example.com")
        spec_and_tests(root)

    def test_aidd_test_exits_0_and_keeps_the_red_runs(self):
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 0, out)
        self.assertIn("[..] green", out)  # the failing green runs are expected, and marked so
        self.assertIn("[ok] red   acceptance", out)  # red on base: early proof the test detects the change
        self.assertIn("Spec phase", out)
        ev = test_runner.json.loads(Path(self.root, ".aidd/evidence/evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(ev["spec_phase"])

    def test_the_gate_leads_with_spec_approval_and_waits(self):
        run_cli(self.root, "test", "--base", "main")
        with contextlib.chdir(self.root):
            ctx = local_context.build_local_context(
                repo=str(self.root), base="main", evidence=str(self.root / ".aidd/evidence/evidence.json"), run_policy=False
            )
        d = decide(ctx)
        self.assertEqual(d.decision, "pending")
        # No Merge approval and no untouched Task yet; only Spec approval and the phase itself (locally, commit emails also warn).
        self.assertEqual([c for c in d.codes() if not c.startswith("warn authors.")], ["pending spec_approval.missing", "pending tests.spec_phase"])
        self.assertEqual(d.record["phase"], "spec")
        text = decision_report.decision_text(d)
        self.assertIn("Spec phase", text)
        self.assertLess(text.index("spec_approval"), text.index("tests.spec_phase:"))
        # Once a Task's file changes, the phase is over: the same failing test fails the gate.
        _commit(self.root, "feat: start", {"app/discount.py": "def discount(total, percent):\n    return total\n"})
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 1, out)


FIX = "def total(items):\n    return sum(i for i in items if i is not None)\n"


@unittest.skipUnless(shutil.which("git"), "git is required")
class LocalFastLaneTests(RepoTemplateCase):
    """The fast lane on one machine: the Change Request block lives in a commit, and one code approves and ships."""

    @classmethod
    def build_template(cls, root):
        shop(root, "solo")
        git(root, "switch", "-qc", "fix")
        _commit(root, "fix(cart): skip None items\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/cart.py": FIX})

    def test_change_commit_records_the_block_where_test_gate_and_ship_read_it(self):
        code, out = run_cli(self.root, "describe", "--commit", "--base", "main")
        self.assertEqual(code, 0, out)
        self.assertIn("type: fix", out)  # from the Conventional Commit prefix
        message = git(self.root, "log", "-1", "--format=%B")
        self.assertIn("```yaml aidd", message)
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", message)
        self.assertEqual(git(self.root, "diff", "--name-only", "HEAD~1", "HEAD"), "")  # an empty commit
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 0, out)
        code, out = run_cli(self.root, "gate", "--base", "main")
        self.assertEqual(code, 3, out)  # only the Merge approval is missing
        self.assertNotIn("change_request", out)
        self.assertIn("merge_approval", out)
        # One code approves and ships: no separate `aidd approve merge`.
        code, out, err = as_person(self.root, "land", "--squash")
        self.assertEqual(code, 0, out + err)
        self.assertIn("landed fix", out)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "fix(cart): skip None items")
        self.assertIn("Aidd-Merge-Approval", git(self.root, "log", "-1", "--format=%B", "refs/aidd/decisions"))

    def test_without_a_block_the_gate_derives_the_change_and_the_head_stays(self):
        """No `aidd describe --commit`: the gate takes the route from the diff, the type from the subject, and the agent
        from the trailer, so the head the tests ran on is the head that lands."""
        head = git(self.root, "rev-parse", "HEAD")
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 0, out)
        code, out = run_cli(self.root, "gate", "--base", "main")
        self.assertEqual(code, 3, out)  # only the Merge approval is missing
        self.assertNotIn("change_request", out)
        self.assertNotIn("provenance", out)
        record = decide(local_context.build_local_context(repo=str(self.root), base="main")).record
        self.assertEqual((record["declaration"], record["route"], record["type"]), ("derived", "minor", "fix"))
        self.assertEqual(record["assisted_by"], ["claude-code/claude-opus-5-5"])
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)  # no block commit: the tested head is the one that lands
        code, out, err = as_person(self.root, "land", "--squash")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "fix(cart): skip None items")

    def test_a_co_authored_by_trailer_alone_gives_a_valid_block(self):
        """Claude Code writes `Co-Authored-By: Claude ... <noreply@anthropic.com>` by default: the block names the agent
        as one word, so the schema takes it, and the gate's provenance rule passes (a real autopilot run found this)."""
        git(self.root, "reset", "-q", "--hard", "main")
        _commit(self.root, "fix(cart): skip None items\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", {"app/cart.py": FIX})
        code, out = run_cli(self.root, "describe", "--commit", "--base", "main")
        self.assertEqual(code, 0, out)
        self.assertIn("claude-opus-5.5", git(self.root, "log", "-1", "--format=%B"))
        code, out = run_cli(self.root, "gate", "--base", "main")
        self.assertNotIn("change_request", out)
        self.assertNotIn("provenance", out)
        # With an `Assisted-by` trailer too, only its value is listed: the gate requires it, and nothing else.
        git(self.root, "reset", "-q", "--hard", "main")
        message = "fix(cart): skip None items\n\nAssisted-by: claude-code/claude-opus-5-5\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
        _commit(self.root, message, {"app/cart.py": FIX})
        code, out = run_cli(self.root, "describe", "--base", "main")
        self.assertIn("assisted_by: [claude-code/claude-opus-5-5]", out)

    def test_ship_fails_fast_on_the_declaration_before_any_test(self):
        Path(self.root, "README.md").write_text("more\n", encoding="utf-8")
        block = "```yaml aidd\nroute: minor\ntype: fix\nscope: [app/cart.py]\nassisted_by: [claude-code/claude-opus-5-5]\n```"
        _commit(self.root, f"chore: block\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5")
        code, out, err = as_person(self.root, "land")
        self.assertEqual(code, 1, out + err)
        self.assertIn("scope", out)  # README.md is outside the declared scope
        self.assertIn("no test ran", err)
        self.assertFalse(Path(self.root, ".aidd/evidence/evidence.json").exists())

    def test_a_body_file_overrides_the_commit_block(self):
        run_cli(self.root, "describe", "--commit", "--base", "main")
        body = Path(self.root, "..", "body.md")
        body.write_text("```yaml aidd\nroute: minor\ntype: docs\nscope: [docs/]\nassisted_by: [claude-code/claude-opus-5-5]\n```\n", encoding="utf-8")
        code, out = run_cli(self.root, "gate", "--base", "main", "--body-file", str(body))
        self.assertIn("outside the scope", out)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShipOntoAMovedBaseTests(RepoTemplateCase):
    """When the base moved, `aidd land` tests the head merged into the base tip and lands exactly that tree."""

    @classmethod
    def build_template(cls, root):
        shop(root, "solo")
        git(root, "switch", "-qc", "fix")
        block = "```yaml aidd\nroute: minor\ntype: fix\nscope: [app/cart.py]\nassisted_by: [claude-code/claude-opus-5-5]\n```"
        _commit(root, f"fix(cart): skip None items\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/cart.py": FIX})
        git(root, "switch", "-q", "main")
        _commit(root, "docs: readme", {"README.md": "the shop\n"})
        git(root, "switch", "-q", "fix")

    def test_the_merged_tree_is_tested_and_shipped(self):
        main = git(self.root, "rev-parse", "main")
        code, out, err = as_person(self.root, "land")
        self.assertEqual(code, 0, out + err)
        self.assertIn("testing", out)
        self.assertEqual(git(self.root, "rev-parse", "main^1"), main)  # the moved base is the first parent
        self.assertEqual(git(self.root, "rev-parse", "main^2"), git(self.root, "rev-parse", "fix"))
        self.assertEqual(Path(self.root, "README.md").read_text(encoding="utf-8"), "the shop\n")
        self.assertEqual(Path(self.root, "app/cart.py").read_text(encoding="utf-8"), FIX)
        ev = test_runner.json.loads(Path(self.root, ".aidd/evidence/evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(ev["head_sha"], git(self.root, "rev-parse", "main"))  # the evidence is for the commit that landed
        self.assertEqual(git(self.root, "worktree", "list").count("\n"), 0)  # the temporary worktree is gone

    def test_a_squash_lands_the_same_tree_on_the_moved_base(self):
        code, out, err = as_person(self.root, "land", "--squash")
        self.assertEqual(code, 0, out + err)
        tested = test_runner.json.loads(Path(self.root, ".aidd/evidence/evidence.json").read_text(encoding="utf-8"))["head_sha"]
        self.assertEqual(git(self.root, "rev-parse", "main^{tree}"), git(self.root, "rev-parse", f"{tested}^{{tree}}"))
        self.assertEqual(git(self.root, "rev-list", "--count", "main"), "4")  # scaffold, adopt, readme, the squash
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", git(self.root, "log", "-1", "--format=%B", "main"))

    def test_a_conflict_with_the_moved_base_ships_nothing(self):
        git(self.root, "switch", "-q", "main")
        _commit(self.root, "fix: another total", {"app/cart.py": "def total(items):\n    return sum(items or [])\n"})
        main = git(self.root, "rev-parse", "main")
        git(self.root, "switch", "-q", "fix")
        code, out, err = as_person(self.root, "land")
        self.assertEqual(code, 1, out + err)
        self.assertIn("conflicts with the base tip", err)
        self.assertEqual(git(self.root, "rev-parse", "main"), main)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "fix")


@unittest.skipUnless(shutil.which("git"), "git is required")
class EmergencyRevertTests(unittest.TestCase):
    """git's revert of a merged commit, recognized from the diff, ships on the commander's approval alone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "dev@example.com")
        config = TEAM_CONFIG.replace('["email:alice@example.com"]', '["email:alice@example.com", "email:bob@example.com"]')
        config += 'tests:\n  - name: smoke\n    command: [python3, -c, "0"]\n    smoke: true\nowners:\n  specialists:\n    security: [email:sec@example.com]\n'
        _commit(self.root, "adopt", {".aidd/config.yaml": config, "a.txt": LINES, "src/auth/login.py": "ok: True\n"})
        self.bad = _commit(self.root, "feat: the change that broke login", {"src/auth/login.py": "ok: False\n"})
        git(self.root, "switch", "-qc", "revert")
        git(self.root, "revert", "--no-edit", self.bad)
        _commit(self.root, "docs: backfill", {"specs/INC-1.md": "---\nkind: spec\nroute: emergency\n---\n"})
        self.block = (
            "```yaml aidd\nroute: emergency\ntype: fix\nscope: [src/auth/login.py]\nassisted_by: []\nbackfill: specs/INC-1.md\n"
            "risk:\n  summary: Restore login.\n  dimensions: [security]\n  reversible: true\n"
            'emergency:\n  severity: sev1\n  kind: outage\n  commander: email:alice@example.com\n  incident: INC-1\n  review_due: "2099-01-01"\n```\n'
        )

    def test_the_revert_is_recognised_and_needs_no_specialist(self):
        ctx = local_context.build_local_context(repo=self.root, base="main", body=self.block, run_policy=False)
        self.assertEqual(ctx["revert_of"], {"sha": self.bad, "on_base": True, "exact": True})
        tests, _ = routing.required_tests(
            [{"name": "unit", "command": ["x"]}, {"name": "smoke", "command": ["y"], "smoke": True}], [], "change_request", ["a"], route="emergency"
        )
        self.assertEqual([c["name"] for c, _ in tests], ["smoke"])  # the smoke set alone on the emergency route
        # Anything beyond the revert (and its backfill) makes it an ordinary repair again.
        _commit(self.root, "fix: and one more thing", {"a.txt": LINES + "more\n"})
        ctx = local_context.build_local_context(repo=self.root, base="main", body=self.block, run_policy=False)
        self.assertFalse(ctx["revert_of"]["exact"])


FLAKY = "import os,sys; p='.flaky-marker'; seen=os.path.exists(p); open(p,'w').close(); sys.exit(0 if seen else 1)"


@unittest.skipUnless(shutil.which("git"), "git is required")
class FlakyTests(unittest.TestCase):
    """`tests` entries with `retries: N`: every attempt in the evidence, a pass after a failure is flaky, and metrics count it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        command = f"command: [{json.dumps(sys.executable)}, {json.dumps('-c')}, {json.dumps(FLAKY)}]\n    retries: 1\n"
        config = TEAM_CONFIG.replace("command: [python3, -m, unittest]\n", command)
        _commit(self.root, "adopt", {".aidd/config.yaml": config, ".gitignore": ".flaky-marker\nout/\n", "a.txt": LINES})
        git(self.root, "switch", "-qc", "fix")
        _commit(self.root, "fix: a line", {"a.txt": LINES + "x\n"})

    def test_a_retry_that_passes_is_green_and_flaky_and_counted(self):
        from aidd.tracking import metrics

        ev, _ = test_runner.run_tests(repo=self.root, base="main", out_dir=str(Path(self.root, "out")), body=MINOR_BLOCK)
        (r,) = ev["results"]
        self.assertEqual((r["status"], r["flaky"], [a["status"] for a in r["attempts"]]), ("passed", True, ["failed", "passed"]))
        self.assertTrue(Path(self.root, "out", r["attempts"][1]["log"]).is_file())  # each attempt keeps its log
        ctx = local_context.build_local_context(repo=self.root, base="main", body=MINOR_BLOCK, run_policy=False)
        ctx["evidence"] = ev
        d = decide(ctx)
        self.assertIn("warn tests.flaky", d.codes())
        self.assertNotIn("tests", d.rules_at("fail"))
        event = decision_report.decision_event(d, "o/r")
        self.assertEqual(metrics.summarize_events([event])["flaky_runs"], 1)


class SmallerFixesTests(unittest.TestCase):
    def test_assisted_by_is_outside_the_spec_hash_and_provenance_still_reads_it(self):
        ctx = example(FEATURE)
        text = ctx["head_files"]["specs/SPEC-220.md"]
        self.assertIn("assisted_by", text)
        changed = text.replace("assisted_by: [claude-code/claude-opus-5-5]", "assisted_by: [claude-code/claude-opus-5-5, codex/gpt-5]")
        self.assertNotEqual(changed, text)
        self.assertEqual(spec_file.spec_hash(changed, ctx["head_tree"]), spec_file.spec_hash(text, ctx["head_tree"]))
        ctx["commits"][0]["message"] += "\nAssisted-by: other/agent"
        self.assertIn("fail provenance.undeclared_trailer", decide(ctx).codes())

    def test_approvers_split_on_commas_and_are_checked(self):
        self.assertEqual(arguments.approvers(["@a,@org/team", "email:me@example.com", "@a"]), ["@a", "@org/team", "email:me@example.com"])
        for bad in (["agent:claude"], ["@a b"], ["email:nobody"], ["@org/team/sub"]):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "not an approver identity"):
                arguments.approvers(bad)

    def test_a_security_pool_is_named_once(self):
        ctx = example("04-major-permission")
        ctx["base_config"] = ctx["base_config"].replace('  specialists:\n    security: ["@sec-alice"]\n', "")
        msg = next(f.message for f in decide(ctx).findings if f.code == "specialist_approval.unbound")
        self.assertNotIn("(or owners.specialists.security)", msg)

    def test_the_route_preview_expands_a_glob_to_the_tracked_file_that_forces_major(self):
        from aidd import config

        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')
        a = routing.assess_paths(cfg, ["src/**"], tracked=["src/app.py", "src/auth/login.py", "docs/x.md"])
        self.assertEqual(a.required_route, "major")
        self.assertTrue(any("src/auth/login.py" in r for r in a.reasons), a.reasons)
        self.assertNotEqual(routing.assess_paths(cfg, ["src/**"]).required_route, "major")  # a sample path alone misses it

    def test_the_newest_attempts_artifact_is_read_and_a_run_that_tested_nothing_is_passed_over(self):
        from aidd.platforms import github

        calls = []

        class Client:
            token = "t"

            def get(self, path, params=None):
                calls.append(path)
                if path.endswith("/runs"):
                    runs = [
                        {"id": 2, "name": "aidd-tests", "status": "completed", "conclusion": "success", "created_at": "2026-09-23T10:00:00Z"},
                        {"id": 1, "name": "aidd-tests", "status": "completed", "conclusion": "success", "created_at": "2026-09-23T09:00:00Z"},
                    ]
                    return {"workflow_runs": runs}
                if path.endswith("/runs/2/artifacts"):
                    return {"artifacts": []}  # a description edit that left the block alone: the tests job skipped
                return {
                    "artifacts": [
                        {"id": 10, "name": "aidd-evidence", "created_at": "2026-09-23T09:05:00Z", "archive_download_url": "old"},
                        {"id": 11, "name": "aidd-evidence", "created_at": "2026-09-23T09:30:00Z", "archive_download_url": "new"},
                    ]
                }

            def download(self, url, max_bytes=None):
                buf = io.BytesIO()
                import zipfile

                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("evidence.json", json.dumps({"attempt": url}))
                return buf.getvalue()

        data, _ = github._evidence(Client(), "o/r", "a" * 40, "aidd-tests", "aidd-evidence")
        self.assertEqual(data, {"attempt": "new"})


@unittest.skipUnless(shutil.which("git"), "git is required")
class LocalHintsTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root, "team", "email:alice@example.com")
        spec_and_tests(root)

    def test_local_only_without_a_remote_or_a_ci_gate(self):
        self.assertEqual(placement.platform_of(str(self.root)), "local")
        git(self.root, "remote", "add", "origin", "https://example.com/shop.git")
        self.assertEqual(placement.platform_of(str(self.root)), "local")  # `aidd init --ci none`: this machine gates
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        self.assertEqual(placement.platform_of(str(self.root)), "local")  # not published yet: the team works here
        git(self.root, "update-ref", f"refs/remotes/origin/{git(self.root, 'branch', '--show-current')}", "HEAD")
        self.assertEqual(placement.platform_of(str(self.root)), "preflight")  # published: the platform's gate decides
        with contextlib.chdir(self.root):
            d = decide(local_context.build_local_context(repo=str(self.root), base="main", run_policy=False))
        fix = next(f.fix for f in d.findings if f.code == "spec_approval.missing")
        self.assertNotIn("aidd approve spec", fix)  # a platform decides: the Approver posts the line on the PR/MR
        self.assertIn(f"/aidd approve-spec SPEC-1 {d.record['head_sha']}", fix)  # the commit the person reads it at

    def test_approve_spec_warns_when_head_already_holds_implementation(self):
        _commit(self.root, "feat: begin", {"app/discount.py": "def discount(total, percent):\n    return total\n"})
        git(self.root, "config", "user.email", "alice@example.com")  # the Approver, at her own terminal
        code, out, err = as_person(self.root, "approve", "spec", "specs/SPEC-1.md", "--base", "main")
        self.assertEqual(code, 0, out + err)
        self.assertIn("already holds implementation (app/discount.py)", err)

    def test_a_manifest_change_is_implementation_even_when_the_spec_freezes_its_test_section(self):
        """As the gate's spec_approval.after_implementation reads it: a frozen section freezes that section, not its
        manifest, so the rest of `pyproject.toml` changed on the branch is implementation."""
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8").replace("files: [tests/test_discount.py]", 'files: [tests/test_discount.py, "pyproject.toml#tool.pytest"]')
        _commit(self.root, "spec: freeze the pytest settings", {"specs/SPEC-1.md": text, "pyproject.toml": '[project]\nname = "shop"\n'})
        git(self.root, "config", "user.email", "alice@example.com")
        code, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--base", "main", "--show")
        self.assertEqual(code, 0, out)
        self.assertIn("already holds implementation (pyproject.toml)", " ".join(json.loads(out)["warnings"]))

    def test_the_plans_other_work_items_are_not_implementation(self):
        # A plan commits its Initiative, Epics, and sibling Specs with the Spec: approving there is still before code.
        _commit(self.root, "docs(plan): the plan", {"specs/EPIC-1.md": "---\nid: EPIC-1\n---\n", "specs/SPEC-2.md": "---\nid: SPEC-2\n---\n"})
        git(self.root, "config", "user.email", "alice@example.com")
        code, out, err = as_person(self.root, "approve", "spec", "SPEC-1", "--base", "main")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("already holds implementation", err)
        with contextlib.chdir(self.root):
            d = decide(local_context.build_local_context(repo=str(self.root), base="main", run_policy=False))
        self.assertTrue(d.record.get("spec_approval_before_implementation"), d.findings)
        self.assertNotIn("spec_approval.after_implementation", [f.code for f in d.findings])

    def test_show_prints_what_a_person_would_approve_and_records_nothing(self):
        git(self.root, "config", "user.email", "alice@example.com")
        code, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--show")
        self.assertEqual(code, 0, out)
        shown = json.loads(out)
        self.assertEqual((shown["id"], shown["acceptance"], shown["problems"], shown["warnings"]), ("SPEC-1", ["A1"], [], []))
        self.assertTrue(shown["risk"].startswith("route "), shown["risk"])  # what the go/no-go weighs, in one line
        self.assertIn("rollback: Revert the change", shown["risk"])
        self.assertEqual(shown["commit"], git(self.root, "rev-parse", "HEAD"))
        self.assertFalse(git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip())

    def test_a_confirmed_approval_records_exactly_the_commit_confirmed_and_says_where(self):
        git(self.root, "config", "user.email", "alice@example.com")
        _, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--show")
        h = json.loads(out)["commit"]
        code, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--confirmed", "0" * 40)  # not what is committed now
        self.assertEqual(code, 1, out)
        self.assertIn("Nothing was recorded", out)
        self.assertFalse(git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip())
        code, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--confirmed", h)  # no terminal: the dialog was the question
        self.assertEqual(code, 0, out)
        self.assertIn("Approved SPEC-1", out)
        body = git(self.root, "log", "-1", "--format=%B", decision_records.DECISIONS_REF)
        self.assertIn(f"/aidd approve-spec SPEC-1 {h}", body)
        self.assertIn(f"{decision_records.DECIDED_VIA_TRAILER}: claude-code", body)
        _, comments, _ = decision_records.load_local_approvals(str(self.root))  # what the local gate reads: the line alone
        self.assertEqual([c["body"] for c in comments], [f"/aidd approve-spec SPEC-1 {h}"])

    def test_a_changed_spec_is_approved_again_with_its_changes_shown(self):
        from aidd.cli import mcp_server

        git(self.root, "config", "user.email", "alice@example.com")
        first = json.loads(run_cli(self.root, "approve", "spec", "SPEC-1", "--show")[1])
        self.assertIsNone(first["since"])  # a first approval has nothing to compare
        self.assertEqual(run_cli(self.root, "approve", "spec", "SPEC-1", "--confirmed", first["commit"])[0], 0)
        spec = Path(self.root, "specs/SPEC-1.md")
        spec.write_text(spec.read_text(encoding="utf-8").replace("then the total is 180", "then the total is 170"), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: SPEC-1 asks for 15%")
        again = json.loads(run_cli(self.root, "approve", "spec", "SPEC-1", "--show")[1])
        self.assertNotEqual(again["commit"], first["commit"])  # the change voids the approval: a new commit to approve
        self.assertEqual(again["since"]["files"], [{"path": "specs/SPEC-1.md", "added": "1", "removed": "1"}])
        self.assertTrue(any("total is 170" in line and line.startswith("+") for line in again["since"]["lines"]), again["since"])
        self.assertTrue(any("total is 180" in line and line.startswith("-") for line in again["since"]["lines"]), again["since"])
        # The dialog an MCP client shows carries the same change, and the terminal prints it before asking.
        self.assertIn("Changed since your last approval", mcp_server._approval_request({**again, "kind": "spec"})["message"])
        code, out, err = as_person(self.root, "approve", "spec", "SPEC-1")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Changed since your last approval", out)
        self.assertIn("then the total is 170", out)

    def test_an_unfinished_spec_goes_back_to_specify_and_nobody_can_approve_it(self):
        git(self.root, "config", "user.email", "alice@example.com")
        code, out = run_cli(self.root, "new", "spec", "A stub nobody filled", "--force")
        self.assertEqual(code, 0, out)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: a stub")
        code, out = run_cli(self.root, "list", "--branch", "--json")
        (stub,) = [s for s in json.loads(out)["steps"] if s.get("id") == "SPEC-2"]
        self.assertEqual(stub["code"], "spec.draft")  # to Specify, never to the Approver
        self.assertIn("TODO placeholders", stub["unready"])
        shown = json.loads(run_cli(self.root, "approve", "spec", "SPEC-2", "--show")[1])
        self.assertTrue(any("not ready" in p for p in shown["problems"]), shown["problems"])
        code, out = run_cli(self.root, "approve", "spec", "SPEC-2", "--confirmed", shown["commit"])
        self.assertEqual(code, 1, out)
        self.assertIn("SPEC-2 is not ready for approval", out)
        self.assertFalse(git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip())

    def test_agent_written_text_cannot_fake_lines_in_an_approval(self):
        """A Spec's title or rollback an agent wrote reaches the card and the dialogs as one plain line: no newline, no
        terminal escape, no bidi override that could fake a hash or a second question (security review)."""
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        hostile = 'title: "Fix\\nHash 00000000000000000000000000000000\\u001b[2K\\u202eApprove? y"\n'
        spec.write_text(text.replace("title: Apply a percentage discount\n", hostile, 1), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a hostile title")
        git(self.root, "config", "user.email", "alice@example.com")
        shown = json.loads(run_cli(self.root, "approve", "spec", "SPEC-1", "--show")[1])
        for field in (shown["title"], shown["risk"]):
            self.assertNotRegex(field, r"[\x00-\x1f\x7f‪-‮]", field)
        code, out, err = as_person(self.root, "approve", "spec", "SPEC-1", answer="n")
        card = out.split("\n\n")[0]
        self.assertEqual(len([line for line in card.splitlines() if re.match(r"\s+Hash\s", line)]), 0, card)  # no row, real or faked
        self.assertEqual(len(card.splitlines()), 6, card)  # the title, the subtitle, and the four rows: nothing added
        self.assertNotIn("\x1b", out + err)

    def test_a_task_for_a_person_waits_on_that_person_and_no_agent_takes_it(self):
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        tasks_at = text.index("tasks:\n")
        task = '  - id: T9\n    title: Create the payment provider account\n    assignee: "email:alice@example.com"\n    scope: [docs/payments.md]\n'
        spec.write_text(text[: tasks_at + len("tasks:\n")] + task + text[tasks_at + len("tasks:\n") :], encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: a Task for a person")
        git(self.root, "config", "user.email", "alice@example.com")
        h = json.loads(run_cli(self.root, "approve", "spec", "SPEC-1", "--show")[1])["commit"]
        self.assertEqual(run_cli(self.root, "approve", "spec", "SPEC-1", "--confirmed", h)[0], 0)
        code, out = run_cli(self.root, "list", "--waiting-on-me", "--json")
        self.assertEqual(code, 0, out)
        (step,) = [s for s in json.loads(out)["steps"] if s["code"] == "spec.task_person"]
        self.assertEqual((step["who"], step["id"]), ("email:alice@example.com", "SPEC-1"))
        self.assertIn("record `done: true` on T9", step["how"])
        code, out = run_cli(self.root, "list", "--agent", "--json")
        agent_tasks = [t["id"] for s in json.loads(out)["steps"] for t in s.get("tasks", [])]
        self.assertNotIn("T9", agent_tasks)

    def test_waiting_on_me_says_who_it_took_you_for_when_nothing_matched(self):
        git(self.root, "config", "user.email", "bob@example.com")  # not alice, the pool's one Approver
        code, out = run_cli(self.root, "list", "--waiting-on-me")
        self.assertEqual(code, 0, out)
        self.assertIn("1 item waits on an Approver, none matched to you (email:bob@example.com", out)
        self.assertIn("git config github.user", out)

    def test_a_branch_is_approved_from_another_worktree(self):
        git(self.root, "config", "user.email", "alice@example.com")
        branch = git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
        head = git(self.root, "rev-parse", "HEAD")
        git(self.root, "switch", "-q", "main")
        code, out = run_cli(self.root, "approve", "spec", "SPEC-1", "--ref", branch, "--show")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["commit"], head)

    def test_approve_merge_shows_the_state_first_and_is_the_persons_whatever_else_fails(self):
        """The person's Merge approval is theirs to give: aidd records it, says what still fails, and the gate holds the
        merge until that is fixed."""
        with open(Path(self.root, "tests/test_discount.py"), "a", encoding="utf-8") as fh:
            fh.write("# edited\n")
        Path(self.root, "README.md").write_text("outside every scope\n", encoding="utf-8")
        _commit(self.root, "chore: scope creep")
        git(self.root, "config", "user.email", "alice@example.com")  # the Approver, at her own terminal
        code, out, err = as_person(self.root, "approve", "merge", "--base", "main")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Merge approval summary", out)
        self.assertIn("README.md", out)  # the diffstat
        self.assertIn("aidd gate:", out)
        self.assertIn("the gate still fails on scope", out)
        self.assertNotEqual(git(self.root, "for-each-ref", "refs/aidd/decisions"), "")  # recorded
        code, out = run_cli(self.root, "gate", "--base", "main")
        self.assertIn("[FAIL] scope", out)  # and the gate still holds the merge


class DependencyUpdateTests(unittest.TestCase):
    """Standard changes by update type: read from manifests and lockfiles, worst of the diff and Dependabot's metadata."""

    def updates(self, path, old, new):
        from aidd.gate import dependency_updates

        return [(u["name"], u["update_type"]) for u in dependency_updates.updates([path], lambda p: old, lambda p: new)]

    def test_each_ecosystem_is_read_and_classified(self):
        pkg = '{"dependencies": {"left-pad": "^1.3.0", "lodash": "4.17.20"}, "devDependencies": {"jest": "~29.1.0"}}'
        self.assertEqual(
            self.updates("package.json", pkg, pkg.replace("1.3.0", "1.3.1").replace("4.17.20", "4.18.0").replace("29.1.0", "30.0.0")),
            [("dependencies:left-pad", "patch"), ("dependencies:lodash", "minor"), ("devDependencies:jest", "major")],
        )
        lock = '{"lockfileVersion": 3, "packages": {"": {}, "node_modules/a": {"version": "1.0.0"}}}'
        self.assertEqual(self.updates("package-lock.json", lock, lock.replace("1.0.0", "1.0.1")), [("node_modules/a", "patch")])
        self.assertEqual(self.updates("requirements.txt", "requests==2.31.0\n# c\n", "requests==2.32.0\n"), [("requests", "minor")])
        uv = '[[package]]\nname = "idna"\nversion = "3.6"\n'
        self.assertEqual(self.updates("uv.lock", uv, uv.replace("3.6", "3.7")), [("idna@", "minor")])
        self.assertEqual(self.updates("poetry.lock", uv, uv.replace("3.6", "4.0")), [("idna@", "major")])
        gomod = "module x\n\ngo 1.22\n\nrequire (\n\tgithub.com/a/b v1.2.3\n)\n"
        self.assertEqual(self.updates("go.mod", gomod, gomod.replace("v1.2.3", "v1.2.4")), [("github.com/a/b", "patch")])
        cargo = '[dependencies]\nserde = "1.0.1"\ntokio = { version = "1.2.0" }\n'
        self.assertEqual(self.updates("Cargo.toml", cargo, cargo.replace('"1.2.0"', '"1.3.0"')), [("dependencies:tokio", "minor")])

    def test_what_cannot_be_classified_is_unknown(self):
        self.assertEqual(self.updates("package.json", '{"dependencies": {}}', '{"dependencies": {"new": "1.0.0"}}'), [("dependencies:new", "unknown")])
        self.assertEqual(self.updates("requirements.txt", "a==2.0.0\n", "a==1.9.0\n"), [("a", "unknown")])  # a downgrade
        self.assertEqual(self.updates("go.sum", "x h1:aaa\n", "x h1:bbb\n"), [(None, "unknown")])  # a checksum only
        self.assertEqual(self.updates("package-lock.json", "{", "}"), [(None, "unknown")])
        self.assertEqual(self.updates("src/app.py", "a", "b"), [])  # not a manifest

    def test_dependabot_metadata_counts_one_type_per_dependency(self):
        from aidd.gate import dependency_updates

        meta = "---\nupdated-dependencies:\n- dependency-name: a\n  update-type: version-update:semver-minor\n- dependency-name: b\n...\n"
        self.assertEqual(dependency_updates.dependabot_types([meta, "no metadata"]), ["minor", "unknown"])

    def test_doctor_and_validate_warn_when_a_third_party_class_takes_major(self):
        from aidd import config

        text = (
            'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\nstandard_changes:\n  - name: deps\n    paths: [package.json]\n'
            '    authors: ["dependabot[bot]"]\n    update_types: [patch, minor, major]\n'
        )
        self.assertIn("takes major third-party updates", " ".join(config.advice(config.load_text(text))))
        self.assertEqual(config.advice(config.load_text(text.replace(", major", ""))), [])


if __name__ == "__main__":
    unittest.main()
