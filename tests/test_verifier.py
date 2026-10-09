"""The gate end to end: decisions, Spec approval proof, the git and runner helpers, HTTP redirects, templates, and conformance."""

import contextlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, decide, example, git, make_repo, rules

from aidd import config, evals, gitutil, guard, inputs, model, repo, runner, schema
from aidd import http as aidd_http
from aidd import rules as aidd_rules
from aidd.verify import verify

FEATURE = "02-normal-feature"
PY = sys.executable.replace("\\", "/")


def aidd(cwd, *args):
    return aidd_subprocess(*args, cwd=cwd)


class VerifierTests(unittest.TestCase):
    def test_policy_directory_is_protected(self):
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n[policy]\ncommand = ["./scripts/aidd-policy-opa"]\n')
        for path in ("scripts/aidd.rego", "scripts/lib/helper.sh"):
            self.assertTrue(any(h.rule == "protected" for h in aidd_rules.scan([path], cfg)), path)

    def test_invalid_context_keeps_the_head(self):
        d = verify({"platform": "github", "head_sha": "a" * 40})
        self.assertEqual((d.decision, d.record["head_sha"]), ("fail", "a" * 40))

    def test_emergency_window_starts_when_the_change_opened(self):
        ctx = example("05-emergency-under-freeze")
        ctx["change"]["created_at"] = ctx["now"]
        ctx["now"] = "2026-09-30T10:00:00Z"  # days later, a re-run must not expire the emergency
        self.assertNotIn("emergency", rules(decide(ctx), "fail"))

    def test_approval_binding_is_gone(self):
        self.assertTrue(schema.validate({"aidd_version": "1.0.0", "profile": "team", "gates": {"approval_binding": "any"}}, "config.schema.json"))

    def test_config_suite_has_no_new_behavior(self):
        cfg = {"aidd_version": "1.0.0", "profile": "team", "tests": [{"name": "u", "command": ["t"], "new_behavior": True}]}
        self.assertTrue(schema.validate(cfg, "config.schema.json"))

    def test_spec_route_is_normal_major_or_emergency(self):
        text = example(FEATURE)["head_files"]["specs/SPEC-220.md"].replace('route = "normal"', 'route = "minor"')
        self.assertTrue(model.load_object(text, "s")[2])

    def test_parent_locks(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "org"\nlocks = ["disable_rules"]\n'
        child = 'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{ path = "p.toml" }]\ndisable_rules = ["baseline:auth"]\n[owners]\napprovers = ["@x"]\n'
        self.assertIsNone(config.load_text(child, prefetched={"p.toml": parent}).get("disable_rules"))

    def test_spec_and_checks_do_not_count_toward_the_budget(self):
        self.assertLess(decide(example(FEATURE)).record["changed_lines"], 183)

    def test_both_provenance_problems_are_reported(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "regulated"')
        ctx["commits"].append(dict(ctx["commits"][0], sha="3" * 40, message="no trailer"))
        spec = ctx["head_files"]["specs/SPEC-220.md"]
        ctx["head_files"]["specs/SPEC-220.md"] = spec.replace('assisted_by = ["claude-code/claude-opus-5-5"]', "assisted_by = []")
        msgs = [f.message for f in decide(ctx).findings if f.rule == "provenance"]
        self.assertEqual(len(msgs), 2, msgs)

    def test_security_dimension_forces_major(self):
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n')
        c = aidd_rules.assess(
            paths=["src/a.py"], cfg=cfg, ctype="feat", risk={"dimensions": ["security"], "reversible": True}, confidence="high", task_count=1, changed_lines=1
        )
        self.assertEqual(c.required_route, "major")

    def test_config_tighten_matrix(self):
        c = config.load_text(
            'aidd_version = "1.0.0"\nprofile = "regulated"\n[gates]\ncooloff_minutes = { major = 0 }\n'
            'specialist_approvals = 0\nprovenance = "declare"\nunlinked_authors = "warn"\nspec_approval_proof = "optional"\n'
        )
        self.assertEqual(
            (c.gates["specialist_approvals"], c.gates["provenance"], c.gates["unlinked_authors"], c.gates["spec_approval_proof"]),
            (1, "every_commit", "fail", "require"),
        )
        self.assertEqual(len(c.warnings), 4)


class ErrorEventTests(unittest.TestCase):
    def test_a_crashed_run_writes_an_error_event(self):
        from aidd import github, report

        line = report.error_event("o/r", "7", RuntimeError("boom"), mode="enforce", run_url="https://x/run/1")
        self.assertEqual(schema.validate(line, "event.schema.json"), [])
        self.assertEqual((line["decision"], line["error"]), ("error", "RuntimeError"))
        self.assertNotIn("boom", json.dumps(line))
        with tempfile.TemporaryDirectory() as d:
            event_path, events = os.path.join(d, "event.json"), os.path.join(d, "events.jsonl")
            with open(event_path, "w", encoding="utf-8") as fh:
                json.dump({"pull_request": {"number": 7}}, fh)
            env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_EVENT_PATH": event_path, "GITHUB_TOKEN": "", "GITHUB_RUN_ID": "1"}

            def crash(*a, **kw):
                raise RuntimeError("boom")

            with (
                mock.patch.dict(os.environ, env),
                mock.patch.object(github, "_gate_one", crash),
                mock.patch.object(github, "protected_branches", lambda client, repo: ["main"]),
                contextlib.redirect_stdout(io.StringIO()) as out,
            ):
                code = github.gate(dry_run=True, events_out=events)
            self.assertEqual(code, 2)
            self.assertIn("PR #7: gate error", out.getvalue())
            written = [json.loads(x) for x in Path(events).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(e["decision"], e["change"], e["error"]) for e in written], [("error", "7", "RuntimeError")])
            self.assertEqual(schema.validate(written[0], "event.schema.json"), [])


class G1ProofTests(unittest.TestCase):
    """An approval that names its commit proves Spec approval came before implementation."""

    def ctx(self, paths):
        ctx = example(FEATURE)
        sha = "9" * 40
        c = next(c for c in ctx["comments"] if "approve-spec" in c["body"])
        c["body"] = c["body"] + " " + sha
        ctx["approval_commits"] = {sha: {"ancestor": True, "paths": paths}}
        return ctx

    def test_proof_recorded(self):
        d = decide(self.ctx(["specs/SPEC-220.md", "tests/checkout/test_rate_limit.py"]))
        self.assertEqual((d.decision, d.record["spec_approval_before_implementation"]), ("pass", True))

    def test_implementation_before_g1_warns(self):
        d = decide(self.ctx(["specs/SPEC-220.md", "src/checkout/rate_limit/limiter.py"]))
        self.assertFalse(d.record["spec_approval_before_implementation"])
        self.assertIn("spec_approval", rules(d, "warn"))

    def test_regulated_requires_the_proof(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "regulated"')
        self.assertIn("spec_approval", rules(decide(ctx), "pending"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", approvers=["@me"])

    def write_spec(self, name, scope):
        text = (
            example(FEATURE)["head_files"]["specs/SPEC-220.md"]
            .replace("SPEC-220", name)
            .replace('scope = ["src/checkout/rate_limit/"]', f'scope = ["{scope}"]')
        )
        (self.root / "specs" / f"{name}.md").write_text(text, encoding="utf-8")

    def test_guard_with_two_specs_needs_aidd_spec(self):
        self.write_spec("S-1", "src/a/")
        self.write_spec("S-2", "src/b/")
        self.assertEqual(guard.check_edit(str(self.root), "src/b/x.py")[0], "allow")  # ambiguous: no active Spec
        with mock.patch.dict(os.environ, {"AIDD_SPEC": "specs/S-1.md"}):
            self.assertEqual(guard.check_edit(str(self.root), "src/b/x.py")[0], "deny")
        self.assertEqual(guard.repo_relative(str(self.root), str(self.root / "src/a/x.py")), "src/a/x.py")

    def test_approval_commits_from_git(self):
        base = git(self.root, "rev-parse", "HEAD")
        self.write_spec("S-1", "src/a/")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "spec")
        g1 = git(self.root, "rev-parse", "HEAD")
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "build")
        head = git(self.root, "rev-parse", "HEAD")
        found = inputs.approval_commits(str(self.root), base, head, [{"body": f"/aidd approve-spec S-1 {'a' * 32} {g1}"}])
        self.assertEqual(found[g1], {"ancestor": True, "paths": ["specs/S-1.md"]})

    def test_hash_worktree_counts_untracked_tests(self):
        self.write_spec("S-1", "src/a/")
        (self.root / "tests" / "checkout").mkdir(parents=True)
        (self.root / "tests/checkout/test_rate_limit.py").write_text("assert True\n", encoding="utf-8")
        out = aidd(self.root, "hash", "specs/S-1.md", "--worktree")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "spec")
        committed = model.spec_hash((self.root / "specs/S-1.md").read_text(encoding="utf-8"), gitutil.ls_tree("HEAD", str(self.root)))
        self.assertEqual(out.stdout.strip(), committed, out.stderr)

    def test_validate_directory_reads_only_aidd_files(self):
        (self.root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        self.assertEqual([e for e in repo.validate_file(self.root) if not e.startswith("warning")], [])

    def test_observe_runs_and_records(self):
        text = example(FEATURE)["head_files"]["specs/SPEC-220.md"]
        text = text.replace("\n+++\n", f'\n\n[observe]\nwindow = "1h"\nrollback_trigger = "errors"\ncommand = ["{PY}", "-c", "pass"]\n+++\n', 1)
        (self.root / "specs" / "S-9.md").write_text(text, encoding="utf-8")
        out = aidd(self.root, "observe", "specs/S-9.md", "--write")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data, _ = model.split_front_matter((self.root / "specs/S-9.md").read_text(encoding="utf-8"))
        self.assertEqual(data["outcome"]["observe_result"], "pass")

    def test_observe_hides_credentials_unless_passed_by_name(self):
        # The command exits 3 when it can read the deploy token.
        probe = "import os, sys; sys.exit(3 if os.environ.get('DEPLOY_TOKEN') else 0)"
        text = example(FEATURE)["head_files"]["specs/SPEC-220.md"]
        text = text.replace("\n+++\n", f'\n\n[observe]\nwindow = "1h"\nrollback_trigger = "errors"\ncommand = ["{PY}", "-c", "{probe}"]\n+++\n', 1)
        (self.root / "specs" / "S-8.md").write_text(text, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "DEPLOY_TOKEN": "s3cret"}
        run = lambda *extra: subprocess.run(  # noqa: E731
            [sys.executable, "-m", "aidd", "observe", "specs/S-8.md", *extra], cwd=self.root, capture_output=True, text=True, env=env, encoding="utf-8"
        )
        self.assertEqual(run().returncode, 0)
        self.assertEqual(run("--pass-env", "DEPLOY_TOKEN").returncode, 1)  # passed on purpose, the probe sees it and fails


class CredentialScrubTests(unittest.TestCase):
    def test_credential_like_names_are_dropped(self):
        from aidd.util import scrub_credentials

        env = {"PATH": "/bin", "DEPLOY_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "x", "DB_PASSWORD": "x", "GITHUB_TOKEN": "x", "SIGNING_KEY": "x", "LANG": "C"}
        self.assertEqual(sorted(scrub_credentials(env)), ["LANG", "PATH"])
        self.assertIn("DB_PASSWORD", scrub_credentials(env, keep=["DB_PASSWORD"]))
        self.assertNotIn("GITHUB_TOKEN", scrub_credentials(env, keep=["GITHUB_TOKEN"]))  # the platform tokens never pass


class RunnerTests(unittest.TestCase):
    def test_timeout_and_not_started(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "x.log"
            r = runner.execute([sys.executable, "-c", "import time; time.sleep(5)"], cwd=d, log=log, timeout=0.2)
            self.assertEqual((r["status"], r["exit"]), ("timeout", None))
            r = runner.execute(["/nonexistent/binary"], cwd=d, log=log, timeout=5)
            self.assertEqual(r["status"], "not_started")


class HttpRedirectTests(unittest.TestCase):
    def test_auth_is_not_forwarded_on_redirect(self):
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/target")
                    self.end_headers()
                    return
                seen["auth"] = self.headers.get("Authorization")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            aidd_http.request("GET", f"http://127.0.0.1:{server.server_port}/start", auth=("Authorization", "Bearer secret"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)
        self.assertIsNone(seen["auth"])


class TemplateTests(unittest.TestCase):
    def test_pr_template_block_is_commented_out(self):
        """A forgotten template must not declare a scope."""
        self.assertNotIn("```toml aidd\nroute", (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8"))

    def test_commented_blocks_do_not_count(self):
        template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
        body = template + '\n```toml aidd\nspec = "specs/S-1.md"\n```\n'
        self.assertEqual(model.parse_change_block(body), ({"spec": "specs/S-1.md"}, []))
        self.assertEqual(model.parse_change_block(template), (None, []))

    def test_version_test_reads_tracked_files_only(self):
        self.assertNotIn('"-co"', (ROOT / "tests/test_version.py").read_text(encoding="utf-8"))


class ConformanceTests(unittest.TestCase):
    # Replaying every mutation is tests/test_conformance_coverage.py's test_every_case_matches_its_expectation.
    def test_apply_ops(self):
        doc = {"a": {"b/c": 1}, "l": [1]}
        evals.apply_ops(doc, [{"op": "set", "path": "/a/b~1c", "value": 2}, {"op": "append", "path": "/l", "value": 2}])
        self.assertEqual(doc, {"a": {"b/c": 2}, "l": [1, 2]})

    def test_replace_text_needs_exactly_one_occurrence(self):
        doc = {"s": "a-b-a"}
        evals.apply_ops(doc, [{"op": "replace_text", "path": "/s", "old": "b", "new": "c"}])
        self.assertEqual(doc, {"s": "a-c-a"})
        for old, n in (("a", 2), ("z", 0)):
            with self.assertRaisesRegex(ValueError, f"occurs {n} times"):
                evals.apply_ops(doc, [{"op": "replace_text", "path": "/s", "old": old, "new": "x"}])
        self.assertEqual(doc, {"s": "a-c-a"})


class EdgeCaseTests(unittest.TestCase):
    """Edge cases of new objects, validation, outcome recording, scenarios, and the hook."""

    def test_new_spec_escapes_quotes_in_the_title(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "specs").mkdir()
            path = repo.new_object(root, kind="spec", id="SPEC-1", title='Say "hi" \\ now', owner_team='a"b')
            data, _ = model.split_front_matter(path.read_text(encoding="utf-8"), str(path))
            self.assertEqual(data["title"], 'Say "hi" \\ now')
            self.assertEqual(data["owner_team"], 'a"b')

    def test_validate_reports_an_emergency_spec_without_review_due_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="solo", ci="none", links=[], harnesses=[])
            text = repo.new_object(root, kind="spec", id="INC-1", title="Outage", route="emergency").read_text(encoding="utf-8")
            text = text.replace("review_due = ", "review_due_missing = ", 1)
            (root / "specs" / "INC-1.md").write_text(text, encoding="utf-8")
            errors, _ = repo.check_repo(root)
            self.assertTrue(any("INC-1" in e for e in errors))

    def test_set_outcome_handles_a_commented_table_and_refuses_an_inline_one(self):
        text = '+++\nid = "S"\n\n[outcome]  # bookkeeping\nreleased_on = "2026-09-25"\n+++\n\nbody\n'
        out = model.set_outcome(text, "observe_result", "pass")
        self.assertEqual(out.count("[outcome]"), 1)
        self.assertIn('observe_result = "pass"', out)
        with self.assertRaises(model.ModelError):
            model.set_outcome('+++\nid = "S"\noutcome = { released_on = "2026-09-25" }\n+++\n', "observe_result", "pass")

    def test_an_empty_scenario_list_loads_as_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.toml").write_text("scenario = []\n", encoding="utf-8")
            self.assertEqual(evals.load_scenarios(Path(d)), [])

    def test_the_hook_allows_when_its_own_code_fails(self):
        out = io.StringIO()
        event = {"tool_name": "Edit", "cwd": "/nonexistent/path/that/does/not/exist", "tool_input": {"file_path": "/nonexistent/x.py"}}
        self.assertEqual(guard.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        self.assertEqual(out.getvalue(), "")
        broken = guard._pre_tool
        guard._pre_tool = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            self.assertEqual(guard.pre_tool_hook(io.StringIO("{}"), out), 0)
        finally:
            guard._pre_tool = broken

    def test_version_tuple_ignores_a_prerelease_suffix(self):
        from aidd import gates

        self.assertEqual(gates._version_tuple("2.0.0-beta"), (2, 0, 0))
        self.assertEqual(gates._version_tuple("2.0.0+2"), (2, 0, 0))
        self.assertGreater(gates._version_tuple("2.0.0-rc.1"), gates._version_tuple("1.9.9"))


if __name__ == "__main__":
    unittest.main()
