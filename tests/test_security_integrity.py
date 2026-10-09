"""Identity, provenance, config, evidence-selection, and gate-loop integrity: each test was a way to get a wrong pass or a stale status."""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from helpers import FakeTransport, decide, example, rules

from aidd import config, github, policy
from aidd.rules import select_tests

API = "https://api.github.test"
RUNS = f"{API}/repos/o/r/actions/workflows/aidd-tests.yml/runs"


def zipped(doc) -> bytes:
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as zf:
        zf.writestr("evidence.json", doc if isinstance(doc, str) else json.dumps(doc))
    return blob.getvalue()


def run(i, conclusion="success", created="2026-09-23T10:00:00Z"):
    return {
        "id": i,
        "name": "aidd-tests",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created,
        "path": ".github/workflows/aidd-tests.yml",
        "event": "pull_request",
        "head_sha": "h",
        "head_branch": "feat",
    }


class IdentityTests(unittest.TestCase):
    def test_emergency_commander_must_be_a_human_approver(self):
        for commander in ("claude[bot]", "drive-by"):
            ctx = example("05-emergency-under-freeze")
            ctx["change"]["body"] = ctx["change"]["body"].replace('commander = "@oncall-lead"', f'commander = "@{commander}"')
            ctx["reviews"].append({"user": commander, "state": "approved", "commit_sha": ctx["head_sha"]})
            self.assertIn("emergency", rules(decide(ctx), "fail"), commander)

    def test_specialist_approvaler_can_block(self):
        ctx = example("04-major-permission")
        ctx["reviews"].append({"user": "sec-alice", "state": "changes_requested", "commit_sha": ctx["head_sha"], "submitted_at": "2099-01-01T00:00:00Z"})
        d = decide(ctx)
        self.assertIn("merge_approval", rules(d, "pending"))
        self.assertIn("changes requested by sec-alice", " ".join(f.message for f in d.findings))

    def test_unlinked_commit_emails(self):
        ctx = example("02-normal-feature")
        ctx["commits"][0]["author"] = "email:alice@example.com"
        self.assertIn("authors", rules(decide(ctx), "warn"))
        ctx["base_config"] += '\n[gates]\nunlinked_authors = "fail"\n'
        self.assertIn("authors", rules(decide(ctx), "fail"))
        ctx["committer_approval_blocked"] = True
        self.assertNotIn("authors", rules(decide(ctx), "fail"))

    def test_child_cannot_exempt_people(self):
        parent = 'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n'
        child = (
            'aidd_version = "1.0.0"\nprofile = "team"\nextends = [{ path = "p.toml" }]\n'
            '[owners]\napprovers = ["@x"]\n[identities]\nsystem_accounts = ["web-flow", "alice"]\n'
        )
        c = config.load_text(child, prefetched={"p.toml": parent})
        self.assertEqual(c.get("identities", "system_accounts"), ["web-flow"])
        self.assertTrue(any("cannot add" in w for w in c.warnings))


class ProvenanceTests(unittest.TestCase):
    def regulated(self, message):
        ctx = example("02-normal-feature")
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "regulated"')
        ctx["commits"][0]["message"] = message
        return rules(decide(ctx), "fail")

    def test_every_commit_means_every_commit(self):
        self.assertIn("provenance", self.regulated("Implement the change"))
        self.assertNotIn("provenance", self.regulated("Implement the change\n\nAssisted-by: claude-code/claude-opus-5-5"))


class ConfigTests(unittest.TestCase):
    def test_org_preset_extends_by_url_only(self):
        base = 'aidd_version = "1.0.0"\nprofile = "org"\n[owners.specialists]\nsecurity = ["@org/security"]\n'
        pin = hashlib.sha256(base.encode()).hexdigest()
        preset = f'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{{ url = "https://example.test/base.toml", sha256 = "{pin}" }}]\n'
        repo = 'aidd_version = "1.0.0"\nprofile = "org"\n[owners]\napprovers = ["@x"]\n'
        c = config.load_text(repo, prefetched={"https://example.test/base.toml": base}, root_preset=preset)
        self.assertEqual(c.specialists["security"], ["@org/security"])
        rogue = 'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{ path = "weak.toml" }]\n'
        with self.assertRaises(config.ConfigError):
            config.load_text(repo, prefetched={"weak.toml": base}, root_preset=rogue)

    def test_extends_path_cannot_escape_the_repo(self):
        bad = [
            'extends = [{ path = "../secret.toml" }]',
            'extends = [{ path = "../../.aws/credentials" }]',
            'extends = [{ path = "/etc/passwd" }]',
            "extends = [{ path = '..\\secret.toml' }]",
            'extends = [{ path = "parent/*.toml" }]',
        ]
        for line in bad:
            raw = f'aidd_version = "1.0.0"\nprofile = "solo"\n{line}\n'
            with self.assertRaises(config.ConfigError, msg=line):
                config.load_text(raw)

    def test_a_standard_change_grant_matches_exactly(self):
        # Grants widen what merges without a human, so case folding must not widen them.
        from aidd.rules import standard_match

        entry = {"name": "deps", "paths": ["package-lock.json"], "authors": ["renovate[bot]"]}
        self.assertEqual(standard_match(entry, paths=["package-lock.json"], identities={"renovate[bot]"}, changed_lines=1), [])
        self.assertTrue(standard_match(entry, paths=["Package-Lock.json"], identities={"renovate[bot]"}, changed_lines=1))

    def test_when_changed_ignores_case(self):
        cmd = {"name": "db", "command": ["x"], "when_changed": ["db/migrations/**"]}
        self.assertEqual(select_tests([cmd], ["DB/Migrations/0042.sql"]), [cmd])

    def test_policy_json_findings_join_the_decision(self):
        script = (
            "import json, os; d = json.load(open(os.environ['AIDD_INPUT_FILE']));"
            "print(json.dumps({'verdict': 'allow', 'findings': [{'rule': 'ticket', 'level': 'fail', 'message': str(len(d['paths']))}]}))"
        )
        out = policy.evaluate(
            [sys.executable, "-c", script], cwd=".", change_id="1", base_sha="b", head_sha="h", paths=["src/a.py", "src/b.py"], body="", head_files={}
        )
        self.assertEqual((out["result"], out["findings"][0]["message"]), ("allow", "2"))
        ctx = example("02-normal-feature")
        ctx["policy"] = out
        self.assertIn("policy:ticket", rules(decide(ctx), "fail"))
        bad = policy.run([sys.executable, "-c", 'print(\'{"verdict": "maybe"}\')'])
        self.assertEqual(bad["result"], "unreachable")

    def test_policy_allow_needs_exit_zero(self):
        self.assertEqual(policy.run([sys.executable, "-c", "print('allow'); raise SystemExit(3)"])["result"], "unreachable")
        self.assertEqual(policy.run([sys.executable, "-c", "print('deny no'); raise SystemExit(1)"])["result"], "deny")


class EvidenceSelectionTests(unittest.TestCase):
    def client(self, routes):
        return github.Client("t", API, transport=FakeTransport(routes))

    def test_skipped_and_cancelled_runs_are_passed_over(self):
        routes = {
            RUNS: ({}, {"workflow_runs": [run(3, "skipped", "2026-09-23T12:00:00Z"), run(2, "cancelled", "2026-09-23T11:00:00Z"), run(1)]}),
            f"{API}/repos/o/r/actions/runs/1/artifacts": ({}, {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/1.zip"}]}),
            "https://dl.test/1.zip": ({}, zipped({"head_sha": "h"})),
        }
        ev, _ = github._evidence(self.client(routes), "o/r", "h", "aidd-tests", "aidd-evidence", head_ref="feat")
        self.assertEqual(ev, {"head_sha": "h"})

    def test_signed_evidence_needs_a_valid_attestation(self):
        routes = {
            RUNS: ({}, {"workflow_runs": [run(1)]}),
            f"{API}/repos/o/r/actions/runs/1/artifacts": ({}, {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/1.zip"}]}),
            "https://dl.test/1.zip": ({}, zipped({"head_sha": "h"})),
        }
        for verdict, expect_invalid in ((None, False), ("no valid attestation", True)):
            with mock.patch.object(github, "verify_attestation", return_value=verdict) as v:
                ev, _ = github._evidence(
                    self.client(routes), "o/r", "h", "aidd-tests", "aidd-evidence", signer_workflow="org/central/.github/workflows/aidd-tests.yml"
                )
            self.assertEqual("invalid" in ev, expect_invalid)
            self.assertEqual(v.call_args.args[2], "org/central/.github/workflows/aidd-tests.yml")

    def test_runs_from_another_branch_do_not_count(self):
        decoy = dict(run(1), head_branch="decoy")
        ev, _ = github._evidence(self.client({RUNS: ({}, {"workflow_runs": [decoy]})}), "o/r", "h", "aidd-tests", "aidd-evidence", head_ref="feat")
        self.assertIsNone(ev)

    def test_unreadable_artifact_is_invalid_evidence(self):
        routes = {
            RUNS: ({}, {"workflow_runs": [run(1)]}),
            f"{API}/repos/o/r/actions/runs/1/artifacts": ({}, {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/1.zip"}]}),
            "https://dl.test/1.zip": ({}, b"not a zip"),
        }
        ev, _ = github._evidence(self.client(routes), "o/r", "h", "aidd-tests", "aidd-evidence")
        self.assertIn("invalid", ev)
        ctx = example("02-normal-feature")
        ctx["evidence"] = ev
        self.assertIn("tests", rules(decide(ctx), "fail"))

    def test_second_pr_from_the_same_branch_into_another_base_blocks_evidence(self):
        pulls = [
            {"number": 1, "head": {"sha": "h"}, "base": {"ref": "main"}},
            {"number": 2, "head": {"sha": "h"}, "base": {"ref": "evil-base"}, "state": "closed"},
        ]
        client = self.client({f"{API}/repos/o/r/pulls": ({}, pulls)})
        kw = {"number": 1, "head_owner": "o", "head_ref": "feat", "head_sha": "h", "base_ref": "main"}
        self.assertEqual(github._branch_conflicts(client, "o/r", **kw), [2])
        pulls[1]["head"]["sha"] = "older"
        self.assertEqual(github._branch_conflicts(client, "o/r", **kw), [])


class GateLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        event = os.path.join(self.tmp.name, "event.json")
        with open(event, "w", encoding="utf-8") as fh:
            json.dump({"pull_request": {"number": 1}}, fh)
        self.env = mock.patch.dict(
            os.environ,
            {
                "GITHUB_REPOSITORY": "o/r",
                "GITHUB_EVENT_PATH": event,
                "GITHUB_API_URL": API,
                "GITHUB_TOKEN": "t",
                "GITHUB_RUN_ID": "5",
                "AIDD_PROTECTED_BRANCHES": "release/*",
                "GITHUB_STEP_SUMMARY": "",
                "AIDD_ORG_PRESET": "",
                "AIDD_MODE": "",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def transport(self, head, siblings=()):
        pulls = [{"number": n, "state": "open", "head": {"sha": head}, "base": {"ref": b}} for n, b in siblings]
        return FakeTransport(
            {
                f"{API}/repos/o/r/pulls/1": ({}, {"head": {"sha": head}, "base": {"ref": "main"}}),
                f"{API}/repos/o/r/commits/{head}/pulls": ({}, pulls),
                f"{API}/repos/o/r/statuses/": ({}, {}),
                f"{API}/repos/o/r": ({}, {"default_branch": "main"}),
            }
        )

    def posted(self, t):
        return [c[3] for c in t.calls if c[0] == "POST"]

    def test_a_crash_posts_an_error_status(self):
        t = self.transport("h" * 40)
        with mock.patch.object(github.http, "request", t), mock.patch.object(github, "build_context", side_effect=ValueError("boom")):
            with contextlib.redirect_stdout(io.StringIO()):
                code = github.gate(cwd=self.tmp.name)
        self.assertEqual(code, 2)
        self.assertEqual([p["state"] for p in self.posted(t)], ["error"])

    def test_shared_head_posts_the_worst_decision(self):
        passing = example("02-normal-feature")
        failing = example("08-scope-creep")
        head = passing["head_sha"]
        failing["head_sha"] = head
        for ctx in (passing, failing):
            ctx["_evidence_note"], ctx["_base_ref"] = "", "main"
        t = self.transport(head, siblings=[(2, "release/1.x")])
        with (
            mock.patch.object(github.http, "request", t),
            mock.patch.object(github, "build_context", side_effect=lambda c, r, n, **kw: dict(passing if n == 1 else failing)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            github.gate(cwd=self.tmp.name)
        posts = self.posted(t)
        self.assertEqual([p["state"] for p in posts], ["failure"])
        self.assertIn("shared with PR #2", posts[0]["description"])


if __name__ == "__main__":
    unittest.main()
