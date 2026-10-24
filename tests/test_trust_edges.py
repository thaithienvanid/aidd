"""The edges of what aidd trusts: a gate record the branch itself carries, the GitHub mode and exit code, a malformed
Spec in `aidd validate`, the extends parents an org preset or a fetch failure leaves out, the platform pages the gate
reads, and the process group a bounded command runs in."""

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_github_e2e as github_e2e
from helpers import FakeTransport, example, git, run_cli

from aidd import config
from aidd.platforms import gitlab
from aidd.platforms import github
from aidd.gate import test_runner
from aidd.gate import inputs
from aidd.workitems import derived_status
from aidd.config import extends
from aidd.kernel import egress, http, processes

GITHUB_API = github_e2e.API
GITLAB_API = "https://gitlab.test/api/v4"


def _repo(root: Path) -> Path:
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "a@example.com"), ("user.name", "A"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return root


@unittest.skipUnless(shutil.which("git"), "git is required")
class GateRecordProvenanceTests(unittest.TestCase):
    """A gate record counts as Spec approval only when a local gate run wrote it: never a record the branch commits or
    stages, and never one naming no commit this repository holds."""

    HASH = "a" * 32

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = _repo(Path(self.tmp.name))

    def write_record(self, **fields) -> Path:
        record = self.root / ".aidd" / "evidence" / "record.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        data = {"decision": "pending", "spec_id": "SPEC-1", "spec_hash": self.HASH, "spec_approved_by": ["@anyone"], **fields}
        record.write_text(json.dumps(data), encoding="utf-8")
        return record

    def observer(self) -> derived_status.Observer:
        return derived_status.Observer(self.root, None)

    def test_a_committed_record_is_not_evidence_of_approval(self):
        self.write_record(head_sha=git(self.root, "rev-parse", "HEAD"))
        git(self.root, "add", "-f", ".aidd/evidence/record.json")
        git(self.root, "commit", "-qm", "assert an approval")
        obs = self.observer()
        self.assertFalse(obs.knows_approvals())
        self.assertIsNone(obs.approved("SPEC-1", self.HASH))
        self.assertIsNone(obs.frozen("specs/SPEC-1.md", {"id": "SPEC-1"}))

    def test_a_staged_record_is_not_evidence_either(self):
        self.write_record(head_sha=git(self.root, "rev-parse", "HEAD"))
        git(self.root, "add", "-f", ".aidd/evidence/record.json")
        self.assertIsNone(self.observer().approved("SPEC-1", self.HASH))

    def test_a_record_a_local_gate_run_wrote_counts(self):
        head = git(self.root, "rev-parse", "HEAD")
        self.write_record(head_sha=head)
        self.assertTrue(self.observer().approved("SPEC-1", self.HASH))
        (self.root / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", "b.txt")
        git(self.root, "commit", "-qm", "later work")
        self.assertTrue(self.observer().approved("SPEC-1", self.HASH), "a record for an ancestor of HEAD still counts")

    def test_a_record_naming_no_commit_here_does_not_count(self):
        for fields in ({"head_sha": "0" * 40}, {"head_sha": None}, {}):
            with self.subTest(fields=fields):
                self.write_record(**fields)
                obs = self.observer()
                self.assertFalse(obs.knows_approvals())
                self.assertIsNone(obs.approved("SPEC-1", self.HASH))


# The `risk` mapping of a Spec, to replace with the string the field held before it was a mapping.
STRING_RISK = r"(?m)^risk:\n  summary: [^\n]*\n  dimensions: \[[^\n]*\]\n  reversible: true\n"


class ValidateMalformedSpecTests(unittest.TestCase):
    """`aidd validate` reports a Spec that fails its schema and exits 1; it never crashes on the data it rejected."""

    def spec(self, old: str, new: str) -> str:
        text = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"]
        changed = re.sub(old, new, text, count=1)
        self.assertNotEqual(changed, text)
        return changed

    def test_a_string_risk_is_a_schema_error_not_an_internal_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "SPEC-X.md"
            bad.write_text(self.spec(STRING_RISK, "risk: low\n"), encoding="utf-8")
            code, out = run_cli("validate", str(bad))
            self.assertEqual(code, 1, out)
            self.assertIn("$.risk", out)
            self.assertNotIn("internal error", out)

    def test_other_schema_errors_still_report_and_the_folder_form_validates_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "specs"
            folder.mkdir()
            (folder / "A.md").write_text(self.spec(STRING_RISK, "risk: low\n"), encoding="utf-8")
            (folder / "B.md").write_text(self.spec(r"(?m)^type: feat$", "type: change").replace("id: SPEC-220", "id: SPEC-221", 1), encoding="utf-8")
            code, out = run_cli("validate", str(folder))
            self.assertEqual(code, 1, out)
            self.assertNotIn("internal error", out)
            self.assertIn("A.md", out)
            self.assertIn("B.md", out)


class GitHubHarness:
    """The GitHub adapter end to end (tests/test_github_e2e.py's repository and fake API), with the environment and
    the base config under the test's control."""

    def __init__(self, case: unittest.TestCase):
        self.e2e = github_e2e.GitHubEndToEndTests("test_the_author_cannot_approve")
        self.e2e.setUp()
        case.addCleanup(self.e2e.tearDown)
        self.work = self.e2e.work

    def set_base_mode(self, mode: str) -> None:
        cfg = self.work / ".aidd/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("profile: team\n", f'profile: team\nmode: "{mode}"\n', 1), encoding="utf-8")
        git(self.work, "commit", "-qam", f"mode {mode}")
        git(self.work, "push", "-q", "origin", "main")

    def transport(self, *, scope: str = "docs/guide.md", reviewer: str = "lead") -> FakeTransport:
        t = self.e2e.transport(reviewer=reviewer)
        pr = t.routes[f"{GITHUB_API}/repos/o/r/pulls/1"][1]
        pr["body"] = pr["body"].replace("scope: [docs/guide.md]", f'scope: ["{scope}"]')
        return t

    def run(self, t: FakeTransport, *, mode: str | None = None, **env: str) -> tuple[int, dict | None]:
        full = {
            "GITHUB_REPOSITORY": "o/r",
            "GITHUB_EVENT_PATH": str(self.e2e.event),
            "GITHUB_API_URL": GITHUB_API,
            "GITHUB_TOKEN": "t",
            "GITHUB_RUN_ID": "5",
            "AIDD_PROTECTED_BRANCHES": "",
            "GITHUB_STEP_SUMMARY": "",
            "AIDD_ORG_PRESET": "",
            "AIDD_MODE": "",
            **env,
        }
        record = Path(self.e2e.tmp.name) / "record.json"
        if record.exists():
            record.unlink()
        with (
            mock.patch.dict(os.environ, full),
            mock.patch.object(http, "request", t),
            mock.patch.object(github, "_fetch", lambda cwd, token, refspecs: git(cwd, "fetch", "-q", "origin", *refspecs)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = github.github_gate(cwd=str(self.work), record_out=str(record), mode=mode)
        return code, json.loads(record.read_text(encoding="utf-8")) if record.exists() else None


def _posts(t: FakeTransport) -> list[tuple[str, str]]:
    return [(c[3]["state"], c[3]["context"]) for c in t.calls if c[0] == "POST"]


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitHubExitCodeTests(unittest.TestCase):
    """On GitHub the posted aidd/gate status is the control and the job's exit code follows it: 0 for a pass and for a
    pending decision (a pull request waiting on a person is not a failed job), 1 for a failure in enforce mode, 0 for
    any decision in advisory mode, and 2 for an error in enforce mode."""

    def setUp(self):
        self.h = GitHubHarness(self)

    def test_the_exit_code_for_each_decision(self):
        cases = (
            ({}, "pass", 0, "success"),
            ({"reviewer": "alice"}, "pending", 0, "pending"),
            ({"scope": "docs/other.md"}, "fail", 1, "failure"),
        )
        for kwargs, decision, code_want, state_want in cases:
            with self.subTest(decision=decision):
                t = self.h.transport(**kwargs)
                code, record = self.h.run(t)
                self.assertEqual((record["decision"], code), (decision, code_want), record)
                self.assertEqual(_posts(t), [(state_want, "aidd/gate")])

    def test_advisory_never_fails_the_job(self):
        t = self.h.transport(scope="docs/other.md")
        code, record = self.h.run(t, mode="advisory")
        self.assertEqual((record["decision"], code), ("fail", 0))
        self.assertEqual(_posts(t), [("failure", "aidd/gate (advisory)")])


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitHubModeTrustTests(unittest.TestCase):
    """Only the reusable workflow's `mode` input (passed as `--mode`) and the base config set the mode on GitHub. An
    AIDD_MODE variable, which a job's env or another workflow can set, never relaxes the gate, as on GitLab."""

    def setUp(self):
        self.h = GitHubHarness(self)

    def test_an_environment_variable_cannot_make_the_gate_advisory(self):
        t = self.h.transport(scope="docs/other.md")
        code, record = self.h.run(t, AIDD_MODE="advisory")
        self.assertEqual((record["decision"], code), ("fail", 1))
        self.assertEqual(_posts(t), [("failure", "aidd/gate")])

    def test_the_workflow_input_and_the_base_config_still_can(self):
        t = self.h.transport(scope="docs/other.md")
        self.assertEqual(self.h.run(t, mode="advisory")[0], 0)
        self.h.set_base_mode("advisory")
        t = self.h.transport(scope="docs/other.md")
        self.assertEqual(self.h.run(t)[0], 0)
        self.assertEqual(_posts(t), [("failure", "aidd/gate (advisory)")])

    def test_the_base_config_wins_over_the_workflow_input(self):
        self.h.set_base_mode("enforce")
        t = self.h.transport(scope="docs/other.md")
        self.assertEqual(self.h.run(t, mode="advisory")[0], 1)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitHubSetupErrorModeTests(unittest.TestCase):
    """A failure before any pull request is evaluated still posts `error`; its exit code follows the mode the base
    config sets, which is readable from the checkout even when the platform API is not."""

    def setUp(self):
        self.h = GitHubHarness(self)

    def fail_setup(self, **kwargs) -> tuple[int, list[tuple[str, str]]]:
        t = self.h.transport()

        def down(*a, **k):
            raise http.HttpError(502, f"{GITHUB_API}/repos/o/r/branches", "bad gateway")

        with mock.patch.object(github, "protected_branches", down):
            code, _ = self.h.run(t, **kwargs)
        return code, _posts(t)

    def test_an_enforcing_base_fails_closed(self):
        self.assertEqual(self.fail_setup(), (2, [("error", "aidd/gate")]))
        self.assertEqual(self.fail_setup(AIDD_MODE="advisory"), (2, [("error", "aidd/gate")]))

    def test_an_advisory_base_reports_the_error_without_failing(self):
        self.h.set_base_mode("advisory")
        self.assertEqual(self.fail_setup(), (0, [("error", "aidd/gate (advisory)")]))


class ExtendsFailureTests(unittest.TestCase):
    """A parent config that cannot be read is named with its cause: a fetch that failed, or an org preset naming a
    parent by path, which it cannot do because it lives outside the repository."""

    URL = "https://example.com/org/base.yaml"

    def child(self) -> str:
        return f'aidd_version: "1.0.0"\nprofile: team\nextends: [{{url: "{self.URL}", sha256: "{"0" * 64}"}}]\nowners:\n  approvers: ["@x"]\n'

    def test_every_fetch_failure_is_a_warning(self):
        for exc, want in (
            (http.HttpError(404, self.URL, "not found"), "HTTP 404"),
            (http.HttpError(0, self.URL, "refusing to fetch a private address"), "refusing"),
            (RuntimeError("boom"), "RuntimeError"),
        ):
            with self.subTest(exc=type(exc).__name__):

                def fetch(url, exc=exc):
                    raise exc

                with mock.patch.object(egress, "check_public_address", lambda *a: None):
                    warnings: list[str] = []
                    got = extends.collect_extends(self.child(), lambda p: None, fetch, warnings=warnings)
                self.assertEqual(got, {})
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn(self.URL, warnings[0])
                self.assertIn(want, warnings[0])

    def test_an_org_preset_naming_a_path_parent_says_why_it_cannot(self):
        preset = 'aidd_version: "1.0.0"\nprofile: org\nextends: [{path: org/base.yaml}]\n'
        child = 'aidd_version: "1.0.0"\nprofile: org\nowners:\n  approvers: ["@x"]\n'
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(child, root_preset=preset)
        self.assertIn("org/base.yaml", str(caught.exception))
        self.assertIn("by url only", str(caught.exception))
        warnings: list[str] = []
        extends.collect_extends(preset, None, lambda url: b"", warnings=warnings)
        self.assertTrue(any("org/base.yaml" in w and "by url only" in w for w in warnings), warnings)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_the_declared_inputs_carry_the_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _repo(Path(tmp))
            (root / ".aidd").mkdir()
            (root / ".aidd/config.yaml").write_text(self.child(), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "config")
            head = git(root, "rev-parse", "HEAD")

            def fetch(url):
                raise http.HttpError(404, url, "not found")

            with mock.patch.object(egress, "check_public_address", lambda *a: None):
                decl = inputs.declared_inputs(str(root), head, head, "", fetch=fetch)
            self.assertIsNone(decl["config"])
            self.assertTrue(any(self.URL in w and "HTTP 404" in w for w in decl["extends_warnings"]), decl["extends_warnings"])


class PlatformPageTests(unittest.TestCase):
    """The gate never reasons from a silently cut list, and a busy head does not make the gate error forever."""

    def test_gitlab_versions_past_the_limit_are_not_a_partial_list(self):
        routes = {}
        for page in range(1, 8):
            nxt = {"x-next-page": str(page + 1)}
            key = f"{GITLAB_API}/projects/7/merge_requests/1/versions?per_page=100" + (f"&page={page}" if page > 1 else "")
            routes[key] = (nxt, [{"head_commit_sha": f"{page:040d}", "created_at": "2026-09-25T09:00:00Z"}] * 100)
        # FakeTransport matches by prefix: the longest keys first.
        t = FakeTransport(dict(sorted(routes.items(), key=lambda kv: -len(kv[0]))))
        self.assertEqual(gitlab._versions(gitlab.Client("t", GITLAB_API, transport=t), "7", 1), [])

    def test_gitlab_versions_within_the_limit_are_read(self):
        t = FakeTransport({f"{GITLAB_API}/projects/7/merge_requests/1/versions": ({}, [{"head_commit_sha": "a" * 40}])})
        self.assertEqual(gitlab._versions(gitlab.Client("t", GITLAB_API, transport=t), "7", 1), [{"head_commit_sha": "a" * 40}])

    def test_a_head_with_thousands_of_other_check_runs_still_reads_the_named_one(self):
        other = [{"name": f"job-{i}", "conclusion": "success", "app": {"slug": "github-actions"}, "check_suite": {"head_branch": "feat"}} for i in range(100)]
        build = {
            "name": "build",
            "conclusion": "success",
            "status": "completed",
            "started_at": "2026-09-25T10:00:00Z",
            "app": {"slug": "github-actions"},
            "check_suite": {"head_branch": "feat", "id": 1},
        }
        base = f"{GITHUB_API}/repos/o/r/commits/h/check-runs"
        t = FakeTransport(
            {
                f"{base}?per_page=100&check_name=build": ({}, {"check_runs": [build]}),
                base: ({"link": f'<{base}?page=2>; rel="next"'}, {"check_runs": other}),
            }
        )
        client = github.Client("t", GITHUB_API, transport=t)
        self.assertEqual(github._status_checks(client, "o/r", "h", ["build"], apps=["github-actions"], head_ref="feat"), {"build": "success"})


@unittest.skipUnless(hasattr(os, "killpg"), "process groups are POSIX")
class ProcessGroupTests(unittest.TestCase):
    """A bounded command's process group is signalled while its leader is still unreaped, so the group id cannot have
    been recycled for an unrelated process."""

    def spy(self):
        seen: list[int | None] = []
        real = processes.kill_group

        def kill_group(proc):
            seen.append(proc.returncode)  # None until the leader is reaped
            real(proc)

        return seen, kill_group

    @unittest.skipUnless(hasattr(os, "waitid") and hasattr(os, "WNOWAIT"), "waiting without reaping needs os.waitid (macOS from Python 3.13)")
    def test_run_bounded_signals_the_group_before_reaping_the_leader(self):
        seen, spy = self.spy()
        with mock.patch.object(processes, "kill_group", spy):
            code, out, err = processes.run_bounded(
                [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], timeout_seconds=30
            )
        self.assertEqual((code, out.strip(), err.strip()), (3, "out", "err"))
        self.assertTrue(seen)
        self.assertEqual(seen, [None] * len(seen))

    def test_run_bounded_still_times_out_and_kills_the_group(self):
        seen, spy = self.spy()
        with mock.patch.object(processes, "kill_group", spy):
            code, _, _ = processes.run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout_seconds=0.5)
        self.assertIsNone(code)
        self.assertEqual(seen[:1], [None])

    def test_run_bounded_reads_output_larger_than_a_pipe_buffer(self):
        code, out, _ = processes.run_bounded([sys.executable, "-c", "print('x' * 1_000_000)"], timeout_seconds=30)
        self.assertEqual((code, len(out.strip())), (0, 1_000_000))

    @unittest.skipUnless(hasattr(os, "waitid") and hasattr(os, "WNOWAIT"), "waiting without reaping needs os.waitid (macOS from Python 3.13)")
    def test_the_test_runner_signals_the_group_before_reaping_the_leader(self):
        seen, spy = self.spy()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(processes, "kill_group", spy):
            result = test_runner.run_test_command([sys.executable, "-c", "print('ok')"], cwd=tmp, log=Path(tmp) / "logs" / "green-unit.log", timeout_seconds=30)
        self.assertEqual((result["exit"], result["status"]), (0, "passed"))
        self.assertEqual(seen, [None])


if __name__ == "__main__":
    unittest.main()
