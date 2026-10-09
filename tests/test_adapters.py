"""Platform adapters, exercised through a fake HTTP transport."""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import FakeTransport, ROOT  # noqa: F401

from aidd import github, gitlab, metrics, policy, report
from helpers import decide, example


class GitHubTests(unittest.TestCase):
    API = "https://api.github.test"

    def test_pr_number_from_events(self):
        client = github.Client("t", self.API, transport=FakeTransport({f"{self.API}/repos/o/r/commits/abc/pulls": ({}, [{"number": 7, "state": "open"}])}))
        self.assertEqual(github.pr_numbers({"pull_request": {"number": 3}}, client, "o/r"), [3])
        self.assertEqual(github.pr_numbers({"issue": {"number": 4, "pull_request": {}}}, client, "o/r"), [4])
        self.assertEqual(github.pr_numbers({"issue": {"number": 5}}, client, "o/r"), [])
        self.assertEqual(github.pr_numbers({"workflow_run": {"pull_requests": [], "head_sha": "abc"}}, client, "o/r"), [7])

    def test_paginate_follows_link_headers(self):
        page2 = f"{self.API}/repos/o/r/pulls/1/reviews?page=2"
        t = FakeTransport(
            {
                page2: ({}, [{"id": 2}]),
                f"{self.API}/repos/o/r/pulls/1/reviews": ({"link": f'<{page2}>; rel="next"'}, [{"id": 1}]),
            }
        )
        items = github.Client("t", self.API, transport=t).paginate("/repos/o/r/pulls/1/reviews")
        self.assertEqual([i["id"] for i in items], [1, 2])
        self.assertEqual(t.calls[0][2], ("Authorization", "Bearer t"))

    def test_evidence_download(self):
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as zf:
            zf.writestr("evidence.json", json.dumps({"head_sha": "h"}))
        t = FakeTransport(
            {
                f"{self.API}/repos/o/r/actions/runs/9/artifacts": (
                    {},
                    {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/a.zip"}]},
                ),
                f"{self.API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": (
                    {},
                    {"workflow_runs": [{"id": 9, "name": "aidd-tests", "status": "completed", "created_at": "2026"}]},
                ),
                "https://dl.test/a.zip": ({}, blob.getvalue()),
            }
        )
        ev, _ = github._evidence(github.Client("t", self.API, transport=t), "o/r", "h", "aidd-tests", "aidd-evidence")
        self.assertEqual(ev, {"head_sha": "h"})

    def test_fork_workflow_run_finds_the_pr_by_head_branch(self):
        t = FakeTransport({f"{self.API}/repos/o/r/pulls": ({}, [{"number": 9, "head": {"sha": "abc"}}, {"number": 10, "head": {"sha": "old"}}])})
        client = github.Client("t", self.API, transport=t)
        run = {"pull_requests": [], "head_sha": "abc", "head_branch": "fix", "head_repository": {"owner": {"login": "forker"}}}
        self.assertEqual(github.pr_numbers({"workflow_run": run}, client, "o/r"), [9])

    def test_evidence_only_from_the_checks_workflow_root_file(self):
        def zipped(name):
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w") as zf:
                zf.writestr(name, json.dumps({"head_sha": "h"}))
            return blob.getvalue()

        runs = {
            "workflow_runs": [
                {"id": 9, "name": "aidd-tests", "status": "completed", "created_at": "2026", "path": ".github/workflows/rogue.yml", "event": "pull_request"}
            ]
        }
        t = FakeTransport({f"{self.API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": ({}, runs)})
        ev, note = github._evidence(github.Client("t", self.API, transport=t), "o/r", "h", "aidd-tests", "aidd-evidence")
        self.assertIsNone(ev)
        runs["workflow_runs"][0]["path"] = ".github/workflows/aidd-tests.yml"
        t = FakeTransport(
            {
                f"{self.API}/repos/o/r/actions/runs/9/artifacts": (
                    {},
                    {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/a.zip"}]},
                ),
                f"{self.API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": ({}, runs),
                "https://dl.test/a.zip": ({}, zipped("nested/evidence.json")),
            }
        )
        ev, note = github._evidence(github.Client("t", self.API, transport=t), "o/r", "h", "aidd-tests", "aidd-evidence")
        self.assertIsNone(ev)
        self.assertIn("root", note)

    def test_status_context_is_per_protected_base(self):
        self.assertEqual(github.status_context("main", ["main"]), "aidd/gate")
        self.assertEqual(github.status_context("gh-pages", ["main"]), "aidd/gate (gh-pages)")

    def test_evidence_waits_for_running_workflow(self):
        t = FakeTransport(
            {f"{self.API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": ({}, {"workflow_runs": [{"id": 9, "name": "aidd-tests", "status": "in_progress"}]})}
        )
        ev, note = github._evidence(github.Client("t", self.API, transport=t), "o/r", "h", "aidd-tests", "aidd-evidence")
        self.assertIsNone(ev)
        self.assertIn("in_progress", note)

    def test_status_post_shape(self):
        t = FakeTransport({f"{self.API}/repos/o/r/statuses/": ({}, {})})
        d = decide(example("02-normal-feature"))
        github.post_status(github.Client("t", self.API, transport=t), "o/r", d, "https://run")
        method, url, _, data = t.calls[0]
        self.assertEqual((method, data["state"], data["context"]), ("POST", "success", "aidd/gate"))
        self.assertLessEqual(len(data["description"]), 140)

    def test_pushed_at_is_unknown_without_check_suites(self):
        t = FakeTransport({f"{self.API}/repos/o/r/commits/abc/check-suites": ({}, {"check_suites": []})})
        got = github._pushed_at(github.Client("t", self.API, transport=t), "o/r", "abc", "fix")
        self.assertIsNone(got)  # a cool-off with no server time never passes

    def test_pushed_at_ignores_suites_on_other_branches(self):
        suites = [
            {"created_at": "2026-09-25T08:00:00Z", "head_branch": "scratch"},  # pushed early to pre-age the cool-off
            {"created_at": "2026-09-25T11:00:00Z", "head_branch": "fix"},
        ]
        t = FakeTransport({f"{self.API}/repos/o/r/commits/abc/check-suites": ({}, {"check_suites": suites})})
        got = github._pushed_at(github.Client("t", self.API, transport=t), "o/r", "abc", "fix")
        self.assertEqual(got, "2026-09-25T11:00:00Z")

    def test_pushed_at_uses_the_earliest_check_suite(self):
        t = FakeTransport(
            {
                f"{self.API}/repos/o/r/commits/abc/check-suites": (
                    {},
                    {"check_suites": [{"created_at": "2026-09-25T11:00:00Z"}, {"created_at": "2026-09-25T10:00:00Z"}]},
                )
            }
        )
        got = github._pushed_at(github.Client("t", self.API, transport=t), "o/r", "abc")
        self.assertEqual(got, "2026-09-25T10:00:00Z")


class GitLabTests(unittest.TestCase):
    def test_approval_notes_bind_to_push_time(self):
        notes = [
            {"system": True, "body": "approved this merge request", "author": {"username": "lead"}, "created_at": "2026-09-23T09:00:00Z"},
            {"system": True, "body": "approved this merge request", "author": {"username": "old"}, "created_at": "2026-09-23T07:00:00Z"},
            {"system": True, "body": "approved this merge request", "author": {"username": "gone"}, "created_at": "2026-09-23T09:00:00Z"},
            {"system": True, "body": "unapproved this merge request", "author": {"username": "gone"}, "created_at": "2026-09-23T09:05:00Z"},
            {"system": False, "body": "/aidd approve abc", "author": {"username": "x"}, "created_at": "2026-09-23T09:00:00Z"},
        ]
        got = {r["user"]: r for r in gitlab._approvals(notes, "2026-09-23T08:00:00Z", "h")}
        self.assertEqual(got["lead"]["commit_sha"], "h")
        self.assertIsNone(got["old"]["commit_sha"])
        self.assertEqual(got["gone"]["state"], "dismissed")
        self.assertNotIn("x", got)

    def test_approval_times_compare_as_instants(self):
        notes = [
            {"system": True, "body": "approved this merge request", "author": {"username": "lead"}, "created_at": "2026-09-23T10:30:00+02:00"}
        ]  # 08:30 UTC, before the push
        got = gitlab._approvals(notes, "2026-09-23T09:00:00.000Z", "h")
        self.assertIsNone(got[0]["commit_sha"])


class PolicyAndReportTests(unittest.TestCase):
    def test_policy_verdicts(self):
        import sys

        self.assertEqual(policy.run(None)["result"], "unbound")
        self.assertEqual(policy.run([sys.executable, "-c", "print('freeze release week')"])["result"], "freeze")
        self.assertEqual(policy.run([sys.executable, "-c", "print('maybe')"])["result"], "unreachable")
        self.assertEqual(policy.run(["/nonexistent/aidd-policy"])["result"], "unreachable")
        self.assertEqual(policy.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)["result"], "unreachable")

    def test_reports_and_metrics(self):
        d = decide(example("03-normal-waiting"))
        self.assertIn("pending", report.markdown(d))
        ev = report.event(d, "acme/shop")
        self.assertEqual(ev["decision"], "pending")
        from aidd import schema

        self.assertEqual(schema.validate(ev, "event.schema.json"), [])
        other = report.event(decide(example("02-normal-feature")), "acme/shop")
        s = metrics.summarize([ev, other])
        by_owner = metrics.grouped([ev, other, dict(other, repo="globex/app")], "org")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "events.jsonl"
            f.write_text("\n".join(json.dumps(dict(ev, ts=t)) for t in ("2026-09-01T00:00:00Z", "2026-09-20T00:00:00Z")), encoding="utf-8")
            self.assertEqual([e["ts"] for e in metrics.load([str(f)], since="2026-09-11")], ["2026-09-20T00:00:00Z"])
        self.assertEqual(other["owner_team"], "checkout")
        self.assertEqual(set(metrics.grouped([ev, other], "team")), {"checkout"} | ({ev["owner_team"]} if ev["owner_team"] else {"no Spec"}))
        # Both acme/shop events are one change; the globex copy is another company's change.
        self.assertEqual({g: v["changes"] for g, v in by_owner.items()}, {"acme": 1, "globex": 1})
        self.assertEqual(s["changes"], 1)
        self.assertEqual(s["final_decisions"], {"pass": 1})

    def test_metrics_since_compares_instants_not_strings(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "events.jsonl"
            f.write_text("\n".join(json.dumps({"ts": t}) for t in ("2026-09-20T00:00:00+02:00", "2026-09-20T00:30:00Z")), encoding="utf-8")
            # The +02:00 instant is 2026-09-19T22:00Z, before midnight; only the 00:30Z event remains.
            self.assertEqual(metrics.load([str(f)], since="2026-09-20T00:00:00Z"), [{"ts": "2026-09-20T00:30:00Z"}])


if __name__ == "__main__":
    unittest.main()
