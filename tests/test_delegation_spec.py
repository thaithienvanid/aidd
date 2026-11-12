"""`aidd delegate check` on a Spec: its approval's checks, how a merge proves the approval from what the change cannot
write itself, and the delegate's defer, which an amend never clears. Split from test_delegation_check to keep each file
inside the test budget; what a change moves after the approval is in test_delegation_spec_changes."""

import contextlib
import tempfile
from pathlib import Path

from helpers import SAMPLE_SPEC, git
from test_delegation_check import ENV, NAME, Case, Repo, check_mod, codes, diff_signals, note

from aidd import config, delegation, records


class RecordTests(Case):
    def defer_record(self, tree: str, action="git.merge"):
        data = {
            "action": action,
            "covers": {"head": "a" * 40, "tree": tree},
            "outcome": "defer",
            "reason": "drifts from the intent",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by="agent:claude-code/aidd-team:delegate", cwd=str(self.root))

    def test_defer_survives_an_amend(self):
        repo = self.repo()
        head = repo.change()
        tree = git(self.root, "rev-parse", f"{head}^{{tree}}")
        self.defer_record(tree)
        self.assertEqual(codes(repo.check(head)), ["deferred_before"])
        git(self.root, "checkout", "-q", "feature")
        git(self.root, *NAME, "commit", "-q", "--amend", "--allow-empty", "-m", "Hand off, in other words", "-m", note(git(self.root, "rev-parse", "HEAD~1")))
        amended = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-q", "main")
        self.assertNotEqual(amended, head)
        self.assertEqual(codes(repo.check(amended)), ["deferred_before"])

    def test_check_ignores_a_forged_record(self):
        repo = self.repo()
        head = repo.change(text="broken = True\n")
        tree = git(self.root, "rev-parse", f"{head}^{{tree}}")
        data = {
            "action": "git.merge",
            "covers": {"head": head, "tree": tree},
            "outcome": "accept",
            "reason": "all green",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by="agent:claude-code/aidd-team:delegate", cwd=str(self.root))
        self.assertEqual(codes(repo.check(head)), ["suite_red"], "an accept on record buys nothing: the check runs again")


class SpecCase(Case):
    """A Spec and its tests on a delegation's repository, its approval, and the change built on it: no test of its own."""

    def spec_repo(self, scope='["src/checkout/"]', red=True, specs="specs", spec_text=None, on_main=None, **cfg) -> tuple[Repo, str]:
        """`spec_text` replaces the Spec's text; `on_main` is files (path to text) the default branch holds before the change."""
        repo = self.repo(**cfg)
        if on_main:
            git(self.root, "checkout", "-q", "main")
            for path, text in on_main.items():
                repo.write(path, text)
            repo.commit("On the default branch")
            git(self.root, "checkout", "-q", "feature")
            git(self.root, "merge", "-q", "--ff-only", "main")
        spec = spec_text or SAMPLE_SPEC.replace("route: normal", "status: ready\nroute: normal").replace('scope: ["src/checkout/"]', f"scope: {scope}")
        repo.write(f"{specs}/SPEC-220.md", spec)
        body = (
            "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        self.assertTrue("
            + ("__import__('os').path.exists('src/checkout/discount.py')" if red else "True")
            + ")\n"
        )
        repo.write("tests/test_discount.py", body)
        return repo, repo.commit("SPEC-220: the Spec and its tests")

    def approve(self, repo: Repo, head: str) -> dict:
        return delegation.run_check(delegation.Request(action="spec.approve", head=head, spec="SPEC-220", cwd=str(repo.root), env=ENV))

    def built(self, repo: Repo, tests: dict[str, str | None], spec: str = "specs/SPEC-220.md") -> str:
        """The approved Spec's implementation, with `tests` written (None removes one), then a note on it: the head."""
        text = (self.root / spec).read_text(encoding="utf-8").replace("status: ready", "status: approved")
        repo.write(spec, text)
        trailers = ["Decided-by: agent:claude-code/aidd-team:delegate", "On-behalf-of: Maya Lee <maya@users.noreply.github.com>", "Delegation: " + "b" * 40]
        repo.commit("Approve SPEC-220", "-m", "\n".join(trailers))
        repo.write("src/checkout/discount.py", "RATE = 0.1\n")
        for path, body in tests.items():
            if body is None:
                (self.root / path).unlink()
            else:
                repo.write(path, body)
        code = repo.commit("Implement")
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def delegate_approved(self, spec_head: str) -> None:
        """The delegate's accept of SPEC-220's approval on `spec_head`: the one record a delegated merge counts."""
        data = {
            "action": "spec.approve",
            "covers": {"spec": "SPEC-220", "head": spec_head, "tree": git(self.root, "rev-parse", f"{spec_head}^{{tree}}")},
            "outcome": "accept",
            "reason": "ready",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by=config.DECIDED_BY, cwd=str(self.root))

    def person_decided(self, spec_head: str, by: str = "Maya Lee") -> None:
        """A `decision` record that SPEC-220's approval was a person's yes: any session can write one, so none counts."""
        data = {
            "action": "spec.approve",
            "question": {"type": "yes_no", "text": "Approve SPEC-220?"},
            "covers": {"spec": "SPEC-220", "head": spec_head},
            "answer": {"outcome": "accept", "words": "yes", "by": by},
        }
        records.add_record("decision", data, by="agent:claude-code/claude-opus-5-5", cwd=str(self.root))


class SpecApprovalTests(SpecCase):
    def test_a_ready_spec_red_on_base_is_eligible(self):
        repo, head = self.spec_repo()
        result = self.approve(repo, head)
        self.assertEqual((result["outcome"], codes(result)), ("eligible", []))
        self.assertNotIn("command", result["covers"])

    def test_check_defers_a_scope_that_overlaps_a_reserved_area(self):
        # The Spec's schema refuses a catch-all scope first, so `**` defers as an error before the overlap is read.
        cases = {'["**"]': "validate_errors", '[".github/**"]': "reserved_path", '["src/", "pyproject.toml"]': "reserved_path", '["src/**/*.py"]': None}
        for scope, code in cases.items():
            with self.subTest(scope), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo, head = self.spec_repo(scope)
                found = codes(self.approve(repo, head))
                self.assertEqual(found, [code] if code else [])
        self.assertEqual(diff_signals.reserved_scopes(check_mod.risk.rule_set(None), ["**"])[0].split(" ")[0], "**", "`**` reaches every area")

    def test_check_defers_tests_that_pass_on_the_base(self):
        repo, head = self.spec_repo(red=False)
        self.assertEqual(codes(self.approve(repo, head)), ["not_red_on_base"])

    def test_a_trailer_the_change_writes_never_approves_its_spec(self):
        repo, _ = self.spec_repo()
        head = self.built(repo, {})
        self.assertEqual(codes(repo.check(head)), ["no_spec"], "Approved-by or Delegation in a commit is the author's own word")

    def test_only_the_delegates_own_accept_is_an_approval_and_only_while_the_specs_gates_pass_again(self):
        """Invariant: for every record a session can write, a delegated merge counts as the Spec's approval only the
        delegate's own accept, only while `spec.approve` is delegated, and only while the Spec's checks pass again."""
        reserved = dict(decides="[git.push, git.merge, pr.merge]")
        cases = {
            "a decision through the command line": dict(decision="Maya Lee", codes=["no_spec"]),
            "a decision through the MCP tool": dict(decision="Maya Lee", mcp=True, codes=["no_spec"]),
            "a decision naming an agent": dict(decision="agent:claude-code/claude-opus-5-5", codes=["no_spec"]),
            "the delegate's accept": dict(delegate=True, codes=[]),
            "the delegate's accept, tests that pass on the base": dict(delegate=True, red=False, codes=["no_spec"]),
            "the delegate's accept, spec.approve reserved": dict(delegate=True, cfg=reserved, codes=["no_spec"], says="reserved"),
            "a decision, spec.approve reserved": dict(decision="Maya Lee", cfg=reserved, codes=["no_spec"], says="reserved"),
        }
        for name, how in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo, spec_head = self.spec_repo(red=how.get("red", True), **how.get("cfg", {}))
                if how.get("decision"):
                    with records.written_with_mcp() if how.get("mcp") else contextlib.nullcontext():
                        self.person_decided(spec_head, by=how["decision"])
                if how.get("delegate"):
                    self.delegate_approved(spec_head)
                result = repo.check(self.built(repo, {}))
                self.assertEqual(codes(result), how["codes"])
                if how.get("says"):
                    self.assertIn(how["says"], result["reasons"][0]["detail"], "the reason says why, so the person knows the next step")

    def test_a_delegates_approval_counts_only_while_its_check_passes_again(self):
        repo, spec_head = self.spec_repo()
        tree = git(self.root, "rev-parse", f"{spec_head}^{{tree}}")
        data = {
            "action": "spec.approve",
            "covers": {"spec": "SPEC-220", "head": spec_head, "tree": tree},
            "outcome": "accept",
            "reason": "ready",
            "check": "20261108T101500123Z-1a2b3c4d",
            "delegation_commit": "b" * 40,
        }
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by="agent:claude-code/aidd-team:delegate", cwd=str(self.root))
        head = self.built(repo, {})
        self.assertEqual(codes(repo.check(head)), [])
        data = dict(data, outcome="defer", reason="drifts from the intent")
        with records.written_by_delegation():
            records.add_record("delegate_answer", data, by="agent:claude-code/aidd-team:delegate", cwd=str(self.root))
        self.assertEqual(codes(repo.check(head)), ["no_spec"], "a later defer on the approved tree is final")


if __name__ == "__main__":
    import unittest

    unittest.main()
