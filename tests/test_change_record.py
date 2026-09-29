"""Tenants, the agent change record (an in-toto statement per gate decision), `aidd verify`, and agent approvals."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import decide, example, run_cli

from aidd import changerecord, export, gates, report, schema
from aidd import config as cfgmod
from aidd.util import scoped, split_tenant

FEATURE = "02-normal-feature"
HEAD = "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
PY = sys.executable
BASE = 'aidd_version = "1.0.0"\nprofile = "team"\n'
OWNERS = '[owners]\napprovers = ["@lead"]\n'


def with_tenant(ctx: dict, tenant: str = "acme") -> dict:
    ctx["base_config"] = ctx["base_config"].replace('profile = "team"\n', f'profile = "team"\ntenant = "{tenant}"\n', 1)
    return ctx


class TenantIdentityTests(unittest.TestCase):
    def test_split_and_scope(self):
        self.assertEqual(split_tenant("acme:@Alice"), ("acme", "alice"))
        self.assertEqual(split_tenant("acme:email:a@b.co"), ("acme", "email:a@b.co"))
        self.assertEqual(split_tenant("email:a@b.co"), (None, "email:a@b.co"))
        self.assertEqual(split_tenant("agent:claude"), (None, "agent:claude"))
        self.assertEqual(split_tenant("@org/team"), (None, "org/team"))
        self.assertEqual(scoped("acme:alice", "acme"), "alice")
        self.assertEqual(scoped("alice", "acme"), "alice")
        self.assertIsNone(scoped("globex:alice", "acme"))
        # Without a tenant nothing is scoped: a qualified identity matches only itself.
        self.assertEqual(scoped("globex:alice", None), "globex:alice")

    def test_a_child_cannot_change_its_parents_tenant(self):
        parent = BASE + 'tenant = "acme"\n' + OWNERS
        cfg = cfgmod.load_text('aidd_version = "1.0.0"\nprofile = "team"\ntenant = "globex"\nextends = [{ path = "p.toml" }]\n', read=lambda _: parent)
        self.assertEqual(cfg.tenant, "acme")
        self.assertTrue(any("tenant 'globex' ignored" in w for w in cfg.warnings), cfg.warnings)

    def test_a_child_may_set_the_same_tenant_or_one_its_parent_leaves_open(self):
        parent = BASE + 'tenant = "acme"\n' + OWNERS
        same = cfgmod.load_text('aidd_version = "1.0.0"\nprofile = "team"\ntenant = "acme"\nextends = [{ path = "p.toml" }]\n', read=lambda _: parent)
        self.assertEqual((same.tenant, [w for w in same.warnings if "tenant" in w]), ("acme", []))
        own = cfgmod.load_text('aidd_version = "1.0.0"\nprofile = "team"\ntenant = "globex"\nextends = [{ path = "p.toml" }]\n', read=lambda _: BASE + OWNERS)
        self.assertEqual(own.tenant, "globex")

    def test_an_org_preset_sets_and_locks_the_tenant(self):
        preset = BASE + 'tenant = "acme"\nlocks = ["tenant"]\n' + OWNERS
        cfg = cfgmod.load_text('aidd_version = "1.0.0"\nprofile = "team"\ntenant = "globex"\n', root_preset=preset)
        self.assertEqual(cfg.tenant, "acme")
        self.assertTrue(any("tenant is locked" in w for w in cfg.warnings), cfg.warnings)
        self.assertEqual(cfgmod.preset_tenant(preset), "acme")
        self.assertIsNone(cfgmod.preset_tenant("not toml ["))
        self.assertIsNone(cfgmod.preset_tenant(None))

    def test_a_tenant_id_must_match_the_pattern(self):
        with self.assertRaises(cfgmod.ConfigError):
            cfgmod.load_text(BASE + 'tenant = "Acme Corp"\n' + OWNERS)

    def test_the_record_and_the_event_carry_the_tenant(self):
        d = decide(with_tenant(example(FEATURE)))
        self.assertEqual((d.decision, d.record["tenant"]), ("pass", "acme"))
        ev = report.event(d, "acme/shop")
        self.assertEqual(ev["tenant"], "acme")
        self.assertEqual(schema.validate(d.record, "record.schema.json"), [])
        self.assertIsNone(report.event(decide(example(FEATURE)), "acme/shop")["tenant"])
        err = report.error_event("acme/shop", "42", RuntimeError("x"), tenant="acme")
        self.assertEqual((err["tenant"], schema.validate(err, "event.schema.json")), ("acme", []))

    def test_a_pool_entry_of_another_tenant_names_nobody(self):
        ctx = with_tenant(example(FEATURE))
        ctx["base_config"] = ctx["base_config"].replace('"@checkout-lead", ', '"globex:checkout-lead", "acme:@platform-lead", ')
        d = decide(ctx)
        self.assertIn("merge_approval", d.rules_at("pending"))
        ctx["reviews"][0]["user"] = "platform-lead"
        ctx["comments"][0]["user"] = "platform-lead"
        self.assertEqual(decide(ctx).decision, "pass")

    def test_a_qualified_identity_without_a_config_tenant_matches_only_itself(self):
        ctx = example(FEATURE)
        ctx["reviews"][0]["user"] = "acme:checkout-lead"
        self.assertIn("merge_approval", decide(ctx).rules_at("pending"))


class AgentApprovalTests(unittest.TestCase):
    def test_which_accounts_are_agents(self):
        for login in ("copilot-pull-request-reviewer[bot]", "copilot", "copilot-swe-agent[bot]", "claude[bot]", "my-codex-runner[bot]"):
            self.assertTrue(gates.agent_account(login), login)
        for login in ("renovate[bot]", "review-bot[bot]", "junie", "alice"):
            self.assertFalse(gates.agent_account(login), login)
        self.assertTrue(gates.agent_account("builder", {"builder"}))

    def test_a_named_agent_never_approves_but_a_named_bot_still_does(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('"@oncall-lead"', '"@oncall-lead", "claude-reviewer[bot]", "review-bot[bot]"')
        ctx["reviews"] = [{"user": "claude-reviewer[bot]", "state": "approved", "commit_sha": HEAD, "submitted_at": "2026-09-23T09:30:00Z"}]
        d = decide(ctx)
        self.assertIn("merge_approval.agent_approval", [f.code for f in d.findings])
        self.assertIn("merge_approval", d.rules_at("pending"))
        ctx["reviews"][0]["user"] = "review-bot[bot]"
        d = decide(ctx)
        self.assertEqual(d.decision, "pass")
        self.assertNotIn("merge_approval.agent_approval", [f.code for f in d.findings])


class ChangeRecordTests(unittest.TestCase):
    def statement(self, ctx: dict | None = None) -> dict:
        ctx = ctx if ctx is not None else with_tenant(example(FEATURE))
        stmt = changerecord.statement(decide(ctx), ctx)
        assert stmt is not None
        return stmt

    def test_the_statement_names_the_head_and_holds_the_decision(self):
        stmt = self.statement()
        self.assertEqual(stmt["_type"], "https://in-toto.io/Statement/v1")
        self.assertEqual(stmt["predicateType"], changerecord.PREDICATE_TYPE)
        self.assertEqual(stmt["subject"], [{"name": f"git+https://github.com/acme/shop@{HEAD}", "digest": {"gitCommit": HEAD}}])
        pred = stmt["predicate"]
        self.assertEqual(schema.validate(pred, "change-record.schema.json"), [])
        self.assertEqual((pred["tenant"], pred["route"], pred["lane"], pred["decision"], pred["findings"]), ("acme", "normal", "spec", "pass", []))
        self.assertEqual(pred["spec"]["approvals"], [{"identity": "checkout-lead", "at": "2026-09-23T08:00:00Z", "commit": None}])
        self.assertTrue(pred["spec"]["approval_required"])
        self.assertEqual(pred["merge_approval"]["approvals"], [{"identity": "checkout-lead", "at": "2026-09-23T09:30:00Z", "commit": HEAD}])
        tests = {t["name"]: t for t in pred["evidence"]["tests"]}
        self.assertEqual((tests["rate-limit"]["red_exit"], tests["rate-limit"]["green_exit"]), (1, 0))
        self.assertIsNone(tests["unit"]["red_exit"])
        self.assertEqual(pred["evidence"]["runner"], {"ci": "github", "run_id": "1"})
        self.assertEqual(pred["scope"]["result"], "within")
        self.assertEqual(pred["provenance"]["assisted_by"], ["claude-code/claude-opus-5-5"])
        self.assertEqual(pred["provenance"]["agent_accounts"], ["claude[bot]"])

    def test_every_conformance_decision_gives_a_valid_predicate(self):
        """The adapters refuse to write an invalid predicate, so no decision the corpus reaches may produce one."""
        from helpers import ROOT

        from aidd import evals

        for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
            ctx, _ = evals.load_example(case)
            contexts = [(case.name, ctx)]
            for m in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
                contexts.append((f"{case.name}/{m.stem}", evals.apply_ops(copy.deepcopy(ctx), json.loads(m.read_text(encoding="utf-8"))["ops"])))
            for name, c in contexts:
                stmt = changerecord.statement(decide(copy.deepcopy(c)), c)
                if stmt is not None:
                    self.assertEqual(schema.validate(stmt["predicate"], "change-record.schema.json"), [], name)

    def test_no_statement_without_a_head(self):
        d = decide({"not": "a context"})
        self.assertIsNone(changerecord.statement(d, {}))

    def test_gate_record_writes_the_statement_beside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx_path = Path(tmp) / "context.json"
            ctx_path.write_text(json.dumps(with_tenant(example(FEATURE))), encoding="utf-8")
            (Path(tmp) / "aidd-evidence").mkdir()
            record = Path(tmp) / "aidd-evidence" / "record.json"
            code, _ = run_cli("gate", "--context", str(ctx_path), "--record", str(record))
            self.assertEqual(code, 0)
            stmt = json.loads((Path(tmp) / "aidd-evidence" / changerecord.FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(stmt["predicate"]["tenant"], "acme")
            self.assertEqual(changerecord.check(stmt), [])

    def test_the_path_is_numbered_for_several_pull_requests(self):
        self.assertEqual(changerecord.path_for("/t/aidd-record.json"), Path("/t/change-record.intoto.json"))
        self.assertEqual(changerecord.path_for("/t/aidd-record.json", 7), Path("/t/change-record-7.intoto.json"))

    def test_tampered_records_are_refused(self):
        good = self.statement()
        self.assertEqual(changerecord.check(good, sha=HEAD, tenant="acme"), [])
        cases = {
            "other head in the predicate": lambda s: s["predicate"].__setitem__("head_sha", "b" * 40),
            "other subject": lambda s: s["subject"][0]["digest"].__setitem__("gitCommit", "c" * 40),
            "a second subject": lambda s: s["subject"].append(copy.deepcopy(s["subject"][0])),
            "not pass": lambda s: s["predicate"].__setitem__("decision", "pending"),
            "no merge approval": lambda s: s["predicate"]["merge_approval"].__setitem__("approvals", []),
            "an agent approved": lambda s: s["predicate"]["merge_approval"]["approvals"][0].__setitem__("identity", "copilot-pull-request-reviewer[bot]"),
            "a listed agent approved the Spec": lambda s: s["predicate"]["spec"]["approvals"][0].__setitem__("identity", "claude[bot]"),
            "no spec approval": lambda s: s["predicate"]["spec"].__setitem__("approvals", []),
            "approval bound elsewhere": lambda s: s["predicate"]["merge_approval"]["approvals"][0].__setitem__("commit", "d" * 40),
            "other predicate type": lambda s: s.__setitem__("predicateType", "https://example.com/x"),
            "an extra field": lambda s: s["predicate"].__setitem__("approved", True),
            "not from a trusted context": lambda s: s["predicate"].__setitem__("trusted", False),
        }
        for name, tamper in cases.items():
            with self.subTest(name):
                bad = copy.deepcopy(good)
                tamper(bad)
                self.assertNotEqual(changerecord.check(bad), [], name)
        self.assertTrue(changerecord.check(good, sha="e" * 40))
        self.assertTrue(changerecord.check(good, tenant="globex"))
        self.assertEqual(changerecord.check([]), ["not a JSON object"])

    def test_a_standard_change_needs_no_human_approval(self):
        stmt = self.statement(example("06-standard-dependency"))
        self.assertEqual((stmt["predicate"]["route"], stmt["predicate"]["merge_approval"]["approvals"]), ("standard", []))
        self.assertEqual(changerecord.check(stmt), [])


@unittest.skipIf(os.name == "nt", "the fake gh is a shell script")
class VerifyCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        ctx = with_tenant(example(FEATURE))
        self.stmt = changerecord.statement(decide(ctx), ctx)
        (self.dir / "aidd-evidence").mkdir()
        self.path = self.dir / "aidd-evidence" / changerecord.FILENAME
        self.path.write_text(json.dumps(self.stmt), encoding="utf-8")
        # Hermetic: the checkout the tests run in has an origin of its own; each test says which repository it is in.
        self.origin = mock.patch("aidd.github.origin_repo", return_value=None)
        self.origin.start()
        self.addCleanup(self.origin.stop)

    def fake_gh(self, exit_code: int, predicate: dict | None = None, sleep: float = 0) -> Path:
        bindir = self.dir / "bin"
        bindir.mkdir(exist_ok=True)
        log = self.dir / "argv.json"
        out = json.dumps([{"verificationResult": {"statement": {"predicate": predicate}}}]) if predicate is not None else "[]"
        gh = bindir / "gh"
        gh.write_text(
            f"#!{PY}\nimport json, sys, time\njson.dump(sys.argv[1:], open({str(log)!r}, 'w'))\ntime.sleep({sleep})\n"
            f"sys.stdout.write({out!r})\nsys.stderr.write('rejected')\nsys.exit({exit_code})\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return log

    def test_unsigned_is_said_and_fails_unless_allowed(self):
        code, out = run_cli("verify", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("signature unsigned", out)
        code, out = run_cli("verify", str(self.path), "--allow-unsigned", "--tenant", "acme")
        self.assertEqual(code, 0, out)
        self.assertIn("unsigned", out)

    def test_by_sha_finds_the_record_in_the_evidence_folder(self):
        code, out = run_cli("verify", HEAD, "--dir", str(self.dir / "aidd-evidence"), "--allow-unsigned")
        self.assertEqual(code, 0, out)
        code, out = run_cli("verify", "f" * 40, "--dir", str(self.dir / "aidd-evidence"))
        self.assertEqual(code, 2)
        self.assertIn("no change record", out)

    def test_a_tampered_file_fails(self):
        bad = copy.deepcopy(self.stmt)
        bad["predicate"]["decision"] = "fail"
        self.path.write_text(json.dumps(bad), encoding="utf-8")
        code, out = run_cli("verify", str(self.path), "--allow-unsigned")
        self.assertEqual(code, 1)
        self.assertIn("decided fail", out)
        code, out = run_cli("verify", str(self.path), "--allow-unsigned", "--tenant", "globex")
        self.assertIn("not 'globex'", out)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(run_cli("verify", str(self.path))[0], 1)

    def test_a_signature_is_checked_with_gh_and_its_predicate_compared(self):
        log = self.fake_gh(0, self.stmt["predicate"])
        with mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}):
            code, out = run_cli(
                "verify",
                str(self.path),
                "--repo",
                "acme/shop",
                "--bundle",
                str(self.dir / "b.jsonl"),
                "--signer-workflow",
                "acme/shop/.github/workflows/release.yml",
                "--default-branch",
                "trunk",
            )
        self.assertEqual(code, 0, out)
        self.assertIn("signature signed", out)
        argv = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(argv[:3], ["attestation", "verify", str(self.path)])
        self.assertEqual(
            argv[3:],
            [
                "--repo",
                "acme/shop",
                "--predicate-type",
                changerecord.PREDICATE_TYPE,
                "--format",
                "json",
                "--bundle",
                str(self.dir / "b.jsonl"),
                "--signer-workflow",
                "acme/shop/.github/workflows/release.yml",
                "--source-ref",
                "refs/heads/trunk",
                "--deny-self-hosted-runners",
            ],
        )

    def test_the_repository_comes_from_the_checkout_and_the_signer_defaults_to_its_gate(self):
        log = self.fake_gh(0, self.stmt["predicate"])
        with (
            mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}),
            mock.patch("aidd.github.origin_repo", return_value="acme/shop"),
            mock.patch("aidd.cli._default_branch", return_value="main"),
        ):
            code, out = run_cli("verify", str(self.path), "--online")
        self.assertEqual(code, 0, out)
        argv = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--repo") + 1], "acme/shop")
        self.assertEqual(argv[argv.index("--signer-workflow") + 1], "acme/shop/.github/workflows/aidd-gate.yml")
        self.assertEqual(argv[argv.index("--source-ref") + 1], "refs/heads/main")
        self.assertIn("--deny-self-hosted-runners", argv)

    def test_a_record_naming_another_repository_fails_even_when_its_signature_verifies_there(self):
        # A record an attacker signed in their own repository: gh accepts it for that repository, so the check
        # must be against the repository the verifier is in, never the one the record names.
        forged = copy.deepcopy(self.stmt)
        forged["predicate"]["repo"] = "attacker/evil"
        forged["subject"][0]["name"] = forged["subject"][0]["name"].replace("acme/shop", "attacker/evil")
        self.path.write_text(json.dumps(forged), encoding="utf-8")
        self.assertEqual(changerecord.check(forged), [])
        log = self.fake_gh(0, forged["predicate"])
        for extra, origin in (([], "acme/shop"), (["--repo", "acme/shop"], None)):
            with (
                self.subTest(extra=extra),
                mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}),
                mock.patch("aidd.github.origin_repo", return_value=origin),
            ):
                code, out = run_cli("verify", str(self.path), "--online", *extra)
            self.assertEqual(code, 1, out)
            self.assertIn("'attacker/evil', not acme/shop", out)
        self.assertFalse(log.exists())

    def test_a_signature_over_another_predicate_fails(self):
        other = dict(self.stmt["predicate"], decision="pending")
        self.fake_gh(0, other)
        with mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}):
            code, out = run_cli("verify", str(self.path), "--online", "--repo", "acme/shop")
        self.assertEqual(code, 1)
        self.assertIn("predicate differs", out)

    def test_a_rejected_or_missing_or_hung_gh_fails(self):
        self.fake_gh(1)
        with mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}):
            code, out = run_cli("verify", str(self.path), "--online", "--repo", "acme/shop")
        self.assertEqual(code, 1)
        self.assertIn("rejected it: rejected", out)
        with mock.patch.dict(os.environ, {"PATH": str(self.dir / "empty")}):
            code, out = run_cli("verify", str(self.path), "--online", "--repo", "acme/shop")
        self.assertIn("gh CLI is not on PATH", out)
        self.fake_gh(0, self.stmt["predicate"])
        with (
            mock.patch.dict(os.environ, {"PATH": str(self.dir / "bin")}),
            mock.patch.object(changerecord.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 120)),
        ):
            code, out = run_cli("verify", str(self.path), "--online", "--repo", "acme/shop")
        self.assertIn("did not finish", out)

    def test_a_record_off_github_needs_a_repo_for_its_signature(self):
        stmt = copy.deepcopy(self.stmt)
        stmt["predicate"]["platform"] = "local"
        self.path.write_text(json.dumps(stmt), encoding="utf-8")
        code, out = run_cli("verify", str(self.path), "--online")
        self.assertEqual(code, 1)
        self.assertIn("pass --repo", out)
        code, out = run_cli("verify", str(self.path), "--online", "--repo", "acme/shop")
        self.assertEqual(code, 1)
        self.assertIn("names the local repository", out)
        self.assertIn("is not an owner/name", changerecord.verify_signature(self.path, stmt, repo="a b") or "")


class TenantFilterTests(unittest.TestCase):
    def test_export_and_metrics_filter_on_the_tenant(self):
        acme = report.event(decide(with_tenant(example(FEATURE))), "acme/shop")
        globex = report.event(decide(with_tenant(example(FEATURE), "globex")), "globex/shop")
        none = report.event(decide(example(FEATURE)), "x/y")
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text("".join(json.dumps(e) + "\n" for e in (acme, globex, none)), encoding="utf-8")
            self.assertEqual([e["repo"] for e in export.collect("events", [str(events)], tenant="acme")], ["acme/shop"])
            self.assertEqual(len(export.collect("events", [str(events)])), 3)
            code, out = run_cli("export", "events", str(events), "--tenant", "globex")
            self.assertEqual((code, [e["repo"] for e in json.loads(out)]), (0, ["globex/shop"]))
            code, out = run_cli("metrics", str(events), "--tenant", "acme", "--json")
            self.assertEqual(json.loads(out)["changes"], 1, out)
            record = Path(tmp) / "r.json"
            record.write_text(json.dumps(decide(with_tenant(example(FEATURE))).record), encoding="utf-8")
            self.assertEqual(len(export.collect("records", [str(record)], tenant="acme")), 1)
            self.assertEqual(export.collect("records", [str(record)], tenant="globex"), [])


if __name__ == "__main__":
    unittest.main()
