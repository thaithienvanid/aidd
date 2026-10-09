"""The delivery flows end to end: the fast lane locally, approvals across a rebase, the Spec phase, shipping onto a
moved base, standard changes by update type, the emergency lane, and flaky tests."""

import contextlib
import io
import json
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, aidd_subprocess, decide, example, git
from test_local_first import SPEC_FIELDS, at_a_terminal

from aidd import cli, gitutil, inputs, localctx, model, report, rules, runner

FEATURE = "02-normal-feature"


def shop(root: Path, profile: str = "solo", approvers: str = "email:me@example.com", extra: str = "") -> None:
    """A small Python shop adopted with `profile`: app/cart.py, its test, and the unittest suite as [[tests]]."""
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    for rel, text in {
        ".gitignore": "__pycache__/\naidd-evidence/\n",
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
        with open(Path(root, ".aidd", "config.toml"), "a", encoding="utf-8") as fh:
            fh.write(extra)
    _commit(root, "chore: adopt aidd")


def as_person(root, *argv: str, answer: str | None = None) -> tuple[int, str, str]:
    """`aidd <argv>` in this process, by a person at a terminal who types the one-time code shown (or `answer`)."""
    with contextlib.chdir(root), at_a_terminal(answer) as (out, err, _):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def run_cli(root, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def spec_and_tests(root) -> None:
    """On a new branch: SPEC-1 and its failing test, committed."""
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
        self.approved = model.spec_hash(self.spec_text, gitutil.ls_tree(self.spec_commit, self.root))
        _commit(self.root, "impl", {"src/checkout/rate_limit/limiter.py": "x = 1\n"})

    def lookup(self):
        head = git(self.root, "rev-parse", "HEAD")
        base = git(self.root, "merge-base", "main", head)
        line = [{"body": f"/aidd approve-spec SPEC-220 {self.approved} {self.spec_commit}"}]
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
        ctx["base_config"] = ctx["base_config"].replace("[identities]", '[gates]\nspec_approval_proof = "require"\n\n[identities]')
        h = model.spec_hash(ctx["head_files"]["specs/SPEC-220.md"], ctx["head_tree"])
        sha = "5" * 40
        ctx["comments"][0]["body"] = f"/aidd approve-spec SPEC-220 {h} {sha}"
        ctx["approval_commits"] = {sha: {"ancestor": False, "paths": ["specs/SPEC-220.md", "tests/checkout/test_rate_limit.py"], "spec_hash": h}}
        d = decide(ctx)
        self.assertEqual((d.decision, d.record["spec_approval_before_implementation"]), ("pass", True))
        # Not rebased but another commit altogether: its own code, and never the misleading "after implementation".
        ctx["approval_commits"][sha]["spec_hash"] = "f" * 32
        d = decide(ctx)
        self.assertIn("warn spec_approval.not_ancestor", d.codes())
        self.assertNotIn("warn spec_approval.after_implementation", d.codes())


TEAM_CONFIG = (
    'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["email:alice@example.com"]\n'
    '[[tests]]\nname = "unit"\ncommand = ["python3", "-m", "unittest"]\n'
)
MINOR_BLOCK = (
    '```toml aidd\nroute = "minor"\ntype = "fix"\nscope = ["a.txt"]\nassisted_by = []\n[risk]\nsummary = "One line."\ndimensions = []\nreversible = true\n```\n'
)
LINES = "".join(f"line {i}\n" for i in range(1, 21))


@unittest.skipUnless(shutil.which("git"), "git is required")
class ApprovalCarryTests(unittest.TestCase):
    """A Merge approval carries across a trivial rebase, and only a trivial one (local context, real git)."""

    def setUp(self):
        from aidd import local

        self.local = local
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "dev@example.com")
        _commit(self.root, "adopt", {".aidd/config.toml": TEAM_CONFIG, "a.txt": LINES})
        git(self.root, "switch", "-qc", "feat")
        self.approved = _commit(self.root, "fix: line 15", {"a.txt": LINES.replace("line 15\n", "line fifteen\n")})
        git(self.root, "config", "user.email", "alice@example.com")
        local.record(local.approve_merge_line(self.approved), self.root)
        git(self.root, "config", "user.email", "dev@example.com")

    def main_moves(self, files: dict[str, str]) -> None:
        git(self.root, "switch", "-q", "main")
        _commit(self.root, "main moves", files)
        git(self.root, "switch", "-q", "feat")
        git(self.root, "rebase", "-q", "main")

    def decide(self):
        from aidd import localctx

        ctx = localctx.build(repo=self.root, base="main", body=MINOR_BLOCK, run_policy=False)
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
        ev = runner.json.loads(Path(self.root, "aidd-evidence/evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(ev["spec_phase"])

    def test_the_gate_leads_with_spec_approval_and_waits(self):
        run_cli(self.root, "test", "--base", "main")
        with contextlib.chdir(self.root):
            ctx = localctx.build(repo=str(self.root), base="main", evidence=str(self.root / "aidd-evidence/evidence.json"), run_policy=False)
        d = decide(ctx)
        self.assertEqual(d.decision, "pending")
        # No Merge approval and no untouched Task yet; only Spec approval and the phase itself (locally, commit emails also warn).
        self.assertEqual([c for c in d.codes() if not c.startswith("warn authors.")], ["pending spec_approval.missing", "pending tests.spec_phase"])
        self.assertEqual(d.record["phase"], "spec")
        text = report.text(d)
        self.assertIn("Spec phase", text)
        self.assertLess(text.index("spec_approval"), text.index("tests:"))
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
        self.assertIn('type = "fix"', out)  # from the Conventional Commit prefix
        message = git(self.root, "log", "-1", "--format=%B")
        self.assertIn("```toml aidd", message)
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", message)
        self.assertEqual(git(self.root, "diff", "--name-only", "HEAD~1", "HEAD"), "")  # an empty commit
        code, out = run_cli(self.root, "test", "--base", "main")
        self.assertEqual(code, 0, out)
        code, out = run_cli(self.root, "gate", "--base", "main")
        self.assertEqual(code, 3, out)  # only the Merge approval is missing
        self.assertNotIn("change_request", out)
        self.assertIn("merge_approval", out)
        # One code approves and ships: no separate `aidd approve merge`.
        code, out, err = as_person(self.root, "ship", "--squash")
        self.assertEqual(code, 0, out + err)
        self.assertIn("shipped fix", out)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "fix(cart): skip None items")
        self.assertIn("Aidd-Merge-Approval", git(self.root, "log", "-1", "--format=%B", "refs/aidd/approvals"))

    def test_ship_fails_fast_on_the_declaration_before_any_test(self):
        Path(self.root, "README.md").write_text("more\n", encoding="utf-8")
        block = '```toml aidd\nroute = "minor"\ntype = "fix"\nscope = ["app/cart.py"]\nassisted_by = ["claude-code/claude-opus-5-5"]\n```'
        _commit(self.root, f"chore: block\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5")
        code, out, err = as_person(self.root, "ship")
        self.assertEqual(code, 1, out + err)
        self.assertIn("scope", out)  # README.md is outside the declared scope
        self.assertIn("no test ran", err)
        self.assertFalse(Path(self.root, "aidd-evidence/evidence.json").exists())

    def test_a_body_file_overrides_the_commit_block(self):
        run_cli(self.root, "describe", "--commit", "--base", "main")
        body = Path(self.root, "..", "body.md")
        body.write_text(
            '```toml aidd\nroute = "minor"\ntype = "docs"\nscope = ["docs/"]\nassisted_by = ["claude-code/claude-opus-5-5"]\n```\n', encoding="utf-8"
        )
        code, out = run_cli(self.root, "gate", "--base", "main", "--body-file", str(body))
        self.assertIn("outside the scope", out)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShipOntoAMovedBaseTests(RepoTemplateCase):
    """When the base moved, `aidd ship` tests the head merged into the base tip and lands exactly that tree."""

    @classmethod
    def build_template(cls, root):
        shop(root, "solo")
        git(root, "switch", "-qc", "fix")
        block = '```toml aidd\nroute = "minor"\ntype = "fix"\nscope = ["app/cart.py"]\nassisted_by = ["claude-code/claude-opus-5-5"]\n```'
        _commit(root, f"fix(cart): skip None items\n\n{block}\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/cart.py": FIX})
        git(root, "switch", "-q", "main")
        _commit(root, "docs: readme", {"README.md": "the shop\n"})
        git(root, "switch", "-q", "fix")

    def test_the_merged_tree_is_tested_and_shipped(self):
        main = git(self.root, "rev-parse", "main")
        code, out, err = as_person(self.root, "ship")
        self.assertEqual(code, 0, out + err)
        self.assertIn("testing", out)
        self.assertEqual(git(self.root, "rev-parse", "main^1"), main)  # the moved base is the first parent
        self.assertEqual(git(self.root, "rev-parse", "main^2"), git(self.root, "rev-parse", "fix"))
        self.assertEqual(Path(self.root, "README.md").read_text(encoding="utf-8"), "the shop\n")
        self.assertEqual(Path(self.root, "app/cart.py").read_text(encoding="utf-8"), FIX)
        ev = runner.json.loads(Path(self.root, "aidd-evidence/evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(ev["head_sha"], git(self.root, "rev-parse", "main"))  # the evidence is for the commit that landed
        self.assertEqual(git(self.root, "worktree", "list").count("\n"), 0)  # the temporary worktree is gone

    def test_a_squash_lands_the_same_tree_on_the_moved_base(self):
        code, out, err = as_person(self.root, "ship", "--squash")
        self.assertEqual(code, 0, out + err)
        tested = runner.json.loads(Path(self.root, "aidd-evidence/evidence.json").read_text(encoding="utf-8"))["head_sha"]
        self.assertEqual(git(self.root, "rev-parse", "main^{tree}"), git(self.root, "rev-parse", f"{tested}^{{tree}}"))
        self.assertEqual(git(self.root, "rev-list", "--count", "main"), "4")  # scaffold, adopt, readme, the squash
        self.assertIn("Assisted-by: claude-code/claude-opus-5-5", git(self.root, "log", "-1", "--format=%B", "main"))

    def test_a_conflict_with_the_moved_base_ships_nothing(self):
        git(self.root, "switch", "-q", "main")
        _commit(self.root, "fix: another total", {"app/cart.py": "def total(items):\n    return sum(items or [])\n"})
        main = git(self.root, "rev-parse", "main")
        git(self.root, "switch", "-q", "fix")
        code, out, err = as_person(self.root, "ship")
        self.assertEqual(code, 1, out + err)
        self.assertIn("conflicts with the base tip", err)
        self.assertEqual(git(self.root, "rev-parse", "main"), main)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "fix")


@unittest.skipUnless(shutil.which("git"), "git is required")
class EmergencyRevertTests(unittest.TestCase):
    """git's revert of a merged commit, recognised from the diff, ships on the commander's approval alone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "dev@example.com")
        config = TEAM_CONFIG.replace('["email:alice@example.com"]', '["email:alice@example.com", "email:bob@example.com"]')
        config += '[[tests]]\nname = "smoke"\ncommand = ["python3", "-c", "0"]\nsmoke = true\n[owners.specialists]\nsecurity = ["email:sec@example.com"]\n'
        _commit(self.root, "adopt", {".aidd/config.toml": config, "a.txt": LINES, "src/auth/login.py": "ok = True\n"})
        self.bad = _commit(self.root, "feat: the change that broke login", {"src/auth/login.py": "ok = False\n"})
        git(self.root, "switch", "-qc", "revert")
        git(self.root, "revert", "--no-edit", self.bad)
        _commit(self.root, "docs: backfill", {"specs/INC-1.md": '+++\nkind = "spec"\nroute = "emergency"\n+++\n'})
        self.block = (
            '```toml aidd\nroute = "emergency"\ntype = "fix"\nscope = ["src/auth/login.py"]\nassisted_by = []\nbackfill = "specs/INC-1.md"\n'
            '[risk]\nsummary = "Restore login."\ndimensions = ["security"]\nreversible = true\n'
            '[emergency]\nseverity = "sev1"\nkind = "outage"\ncommander = "email:alice@example.com"\nincident = "INC-1"\nreview_due = "2099-01-01"\n```\n'
        )

    def test_the_revert_is_recognised_and_needs_no_specialist(self):
        ctx = localctx.build(repo=self.root, base="main", body=self.block, run_policy=False)
        self.assertEqual(ctx["revert_of"], {"sha": self.bad, "on_base": True, "exact": True})
        tests, _ = rules.required_tests(
            [{"name": "unit", "command": ["x"]}, {"name": "smoke", "command": ["y"], "smoke": True}], [], "change_request", ["a"], route="emergency"
        )
        self.assertEqual([c["name"] for c, _ in tests], ["smoke"])  # the smoke set alone on the emergency route
        # Anything beyond the revert (and its backfill) makes it an ordinary repair again.
        _commit(self.root, "fix: and one more thing", {"a.txt": LINES + "more\n"})
        ctx = localctx.build(repo=self.root, base="main", body=self.block, run_policy=False)
        self.assertFalse(ctx["revert_of"]["exact"])


FLAKY = "import os,sys; p='.flaky-marker'; seen=os.path.exists(p); open(p,'w').close(); sys.exit(0 if seen else 1)"


@unittest.skipUnless(shutil.which("git"), "git is required")
class FlakyTests(unittest.TestCase):
    """`[[tests]] retries = N`: every attempt in the evidence, a pass after a failure is flaky, and metrics count it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve())
        git(self.root, "init", "-q", "-b", "main")
        command = f"command = [{json.dumps(sys.executable)}, {json.dumps('-c')}, {json.dumps(FLAKY)}]\nretries = 1\n"
        config = TEAM_CONFIG.replace('command = ["python3", "-m", "unittest"]\n', command)
        _commit(self.root, "adopt", {".aidd/config.toml": config, ".gitignore": ".flaky-marker\nout/\n", "a.txt": LINES})
        git(self.root, "switch", "-qc", "fix")
        _commit(self.root, "fix: a line", {"a.txt": LINES + "x\n"})

    def test_a_retry_that_passes_is_green_and_flaky_and_counted(self):
        from aidd import metrics

        ev, _ = runner.run_tests(repo=self.root, base="main", out_dir=str(Path(self.root, "out")), body=MINOR_BLOCK)
        (r,) = ev["results"]
        self.assertEqual((r["status"], r["flaky"], [a["status"] for a in r["attempts"]]), ("passed", True, ["failed", "passed"]))
        self.assertTrue(Path(self.root, "out", r["attempts"][1]["log"]).is_file())  # each attempt keeps its log
        ctx = localctx.build(repo=self.root, base="main", body=MINOR_BLOCK, run_policy=False)
        ctx["evidence"] = ev
        d = decide(ctx)
        self.assertIn("warn tests.flaky", d.codes())
        self.assertNotIn("tests", d.rules_at("fail"))
        event = report.event(d, "o/r")
        self.assertEqual(metrics.summarize([event])["flaky_runs"], 1)


class SmallerFixesTests(unittest.TestCase):
    def test_assisted_by_is_outside_the_spec_hash_and_provenance_still_reads_it(self):
        ctx = example(FEATURE)
        text = ctx["head_files"]["specs/SPEC-220.md"]
        self.assertIn("assisted_by", text)
        changed = text.replace('assisted_by = ["claude-code/claude-opus-5-5"]', 'assisted_by = ["claude-code/claude-opus-5-5", "codex/gpt-5"]')
        self.assertNotEqual(changed, text)
        self.assertEqual(model.spec_hash(changed, ctx["head_tree"]), model.spec_hash(text, ctx["head_tree"]))
        ctx["commits"][0]["message"] += "\nAssisted-by: other/agent"
        self.assertIn("fail provenance.undeclared_trailer", decide(ctx).codes())

    def test_approvers_split_on_commas_and_are_checked(self):
        self.assertEqual(cli._approvers(["@a,@org/team", "email:me@example.com", "@a"]), ["@a", "@org/team", "email:me@example.com"])
        for bad in (["agent:claude"], ["@a b"], ["email:nobody"], ["@org/team/sub"]):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "not an approver identity"):
                cli._approvers(bad)

    def test_a_security_pool_is_named_once(self):
        ctx = example("04-major-permission")
        ctx["base_config"] = ctx["base_config"].replace('[owners.specialists]\nsecurity = ["@sec-alice"]', "")
        msg = next(f.message for f in decide(ctx).findings if f.code == "specialist_approval.unbound")
        self.assertNotIn("(or owners.specialists.security)", msg)

    def test_the_route_preview_expands_a_glob_to_the_tracked_file_that_forces_major(self):
        from aidd import config

        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n')
        a = rules.assess_paths(cfg, ["src/**"], tracked=["src/app.py", "src/auth/login.py", "docs/x.md"])
        self.assertEqual(a.required_route, "major")
        self.assertTrue(any("src/auth/login.py" in r for r in a.reasons), a.reasons)
        self.assertNotEqual(rules.assess_paths(cfg, ["src/**"]).required_route, "major")  # a sample path alone misses it

    def test_the_newest_attempts_artifact_is_read_and_a_run_that_tested_nothing_is_passed_over(self):
        from aidd import github

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
        self.assertEqual(localctx.platform_of(str(self.root)), "local")
        git(self.root, "remote", "add", "origin", "https://example.com/shop.git")
        self.assertEqual(localctx.platform_of(str(self.root)), "local")  # `aidd init --ci none`: this machine gates
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        self.assertEqual(localctx.platform_of(str(self.root)), "preflight")
        with contextlib.chdir(self.root):
            d = decide(localctx.build(repo=str(self.root), base="main", run_policy=False))
        fix = next(f.fix for f in d.findings if f.code == "spec_approval.missing")
        self.assertNotIn("aidd approve spec", fix)  # a platform decides: the Approver posts the line on the PR/MR
        self.assertIn(f"/aidd approve-spec SPEC-1 {d.record['spec_hash']} {d.record['head_sha']}", fix)  # as `aidd hash --line` prints it

    def test_approve_spec_warns_when_head_already_holds_implementation(self):
        _commit(self.root, "feat: begin", {"app/discount.py": "def discount(total, percent):\n    return total\n"})
        git(self.root, "config", "user.email", "alice@example.com")  # the Approver, at her own terminal
        code, out, err = as_person(self.root, "approve", "spec", "specs/SPEC-1.md", "--base", "main")
        self.assertEqual(code, 0, out + err)
        self.assertIn("HEAD already holds implementation (app/discount.py)", err)

    def test_approve_merge_shows_the_state_first_and_refuses_a_failing_gate(self):
        with open(Path(self.root, "tests/test_discount.py"), "a", encoding="utf-8") as fh:
            fh.write("# edited\n")
        Path(self.root, "README.md").write_text("outside every scope\n", encoding="utf-8")
        _commit(self.root, "chore: scope creep")
        git(self.root, "config", "user.email", "alice@example.com")  # the Approver, at her own terminal
        code, out, err = as_person(self.root, "approve", "merge", "--base", "main")
        self.assertEqual(code, 1, out + err)
        self.assertIn("Merge approval digest", out)
        self.assertIn("README.md", out)  # the diffstat
        self.assertIn("aidd gate:", out)
        self.assertIn("not approved: the gate fails on scope", err)
        self.assertEqual(git(self.root, "for-each-ref", "refs/aidd/approvals"), "")  # nothing was recorded


class DependencyUpdateTests(unittest.TestCase):
    """Standard changes by update type: read from manifests and lockfiles, worst of the diff and Dependabot's metadata."""

    def updates(self, path, old, new):
        from aidd import depdiff

        return [(u["name"], u["update_type"]) for u in depdiff.updates([path], lambda p: old, lambda p: new)]

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
        from aidd import depdiff

        meta = "---\nupdated-dependencies:\n- dependency-name: a\n  update-type: version-update:semver-minor\n- dependency-name: b\n...\n"
        self.assertEqual(depdiff.dependabot_types([meta, "no metadata"]), ["minor", "unknown"])

    def test_doctor_and_validate_warn_when_a_third_party_class_takes_major(self):
        from aidd import config

        text = (
            'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n[[standard_changes]]\nname = "deps"\npaths = ["package.json"]\n'
            'authors = ["dependabot[bot]"]\nupdate_types = ["patch", "minor", "major"]\n'
        )
        self.assertIn("takes major third-party updates", " ".join(config.advice(config.load_text(text))))
        self.assertEqual(config.advice(config.load_text(text.replace(', "major"', ""))), [])


if __name__ == "__main__":
    unittest.main()
