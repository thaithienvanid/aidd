"""The checked findings of the 2026-10 audit plan (BACKLOG §0z, Z12-Z22): each pinned by a case that failed before
its fix."""

import contextlib
import io
import json
import shutil
import unittest


from helpers import adopted_repo, decide, example, git, run_cli

from aidd import config
from aidd.knowledge import library_checks
from aidd.platforms import github_person

EMERGENCY = "05-emergency-under-freeze"


def solo_emergency() -> dict:
    ctx = example(EMERGENCY)
    ctx["base_config"] = ctx["base_config"].replace("profile: org", "profile: solo")
    return ctx


class EmergencyCommanderTests(unittest.TestCase):
    """Z12: under solo the commander may be the author, but must still be an Approver who approved this head."""

    def test_solo_still_needs_the_commander_to_be_an_approver(self):
        ctx = solo_emergency()
        ctx["change"]["body"] = ctx["change"]["body"].replace('commander: "@oncall-lead"', 'commander: "@somebody"')
        self.assertIn("fail emergency.commander_not_approver", decide(ctx).codes())

    def test_solo_still_needs_the_commanders_approval_of_this_head(self):
        ctx = solo_emergency()
        ctx["reviews"] = [r for r in ctx["reviews"] if r["user"] != "oncall-lead"]
        self.assertIn("pending emergency.commander_pending", decide(ctx).codes())

    def test_solo_lets_the_commander_be_the_author(self):
        ctx = solo_emergency()
        ctx["change"]["author"] = "oncall-lead"
        self.assertNotIn("fail emergency.commander_is_author", decide(ctx).codes())


@unittest.skipUnless(shutil.which("git"), "git is required")
class AutopilotLimitsTests(unittest.TestCase):
    """Z13: autopilot's limits come from the base branch's config, never the working tree's, which an agent writes."""

    def test_a_working_tree_timebox_never_widens_the_run(self):
        from aidd.autopilot import engine, lease, turn

        with adopted_repo("team") as root:
            path = root / config.CONFIG_PATH
            path.write_text(path.read_text(encoding="utf-8") + '\nautopilot:\n  timebox: "9h"\n', encoding="utf-8")
            self.assertEqual(turn.gather(root).limits.timebox, lease.DEFAULT_TIMEBOX)
            git(root, "commit", "-qam", "a person widens it on the branch")
            git(root, "checkout", "-q", "main")
            git(root, "merge", "-q", "--ff-only", "feat")
            self.assertEqual(turn.gather(root).limits.timebox, "9h")
            self.assertIsInstance(turn.gather(root).limits, engine.Limits)


@unittest.skipUnless(shutil.which("git"), "git is required")
class WorkItemIdTests(unittest.TestCase):
    """Z14: a command that takes a Spec takes its id, from the root or from a subfolder, as aidd itself recommends."""

    def test_observe_takes_the_id(self):
        with adopted_repo("team") as root:
            spec = root / "specs" / "SPEC-9.md"
            spec.parent.mkdir(exist_ok=True)
            spec.write_text('---\nkind: spec\nid: SPEC-9\nobserve:\n  not_applicable: "a library: nothing runs"\n---\n', encoding="utf-8")
            code, out = run_cli("observe", "SPEC-9")
            self.assertEqual(code, 0, out)
            self.assertIn("nothing to watch", out)
            (root / "src").mkdir(exist_ok=True)
            with contextlib.chdir(root / "src"):
                code, out = run_cli("observe", "SPEC-9")
            self.assertEqual(code, 0, out)
            self.assertIn("specs/SPEC-9.md: nothing to watch", out)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitWritesTests(unittest.TestCase):
    """Z15: git commands that write a file the guard must read as a write: `git checkout <file>` with no ref, and
    `--output=<file>`. Here the file is the guard's own wiring, which the always-on rules keep from every agent."""

    def deny(self, root, command: str) -> bool:
        from aidd.guard import pre_tool

        out = io.StringIO()
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root), "session_id": "s"}
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
        return '"deny"' in out.getvalue()

    def test_a_checkout_of_a_file_and_an_output_file_are_writes(self):
        with adopted_repo("team", enforce=False) as root:
            wiring = root / ".claude" / "settings.json"
            wiring.parent.mkdir(exist_ok=True)
            wiring.write_text("{}\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "wiring")
            for command in (
                "echo x > .claude/settings.json",  # the always-on rules hold for the session's shell writes as for its edits
                "git checkout .claude/settings.json",
                "git diff --output=.claude/settings.json",
                "git log -1 --output .claude/settings.json",
                "git diff --outp=.claude/settings.json",  # git takes the option abbreviated
                "git -C .claude diff --output=settings.json",  # from another folder
                "git diff -C --output=.claude/settings.json",  # `-C` after the subcommand detects copies: no folder
                "git checkout no-such-branch .claude/settings.json",  # a first word that is no ref is a path too
            ):
                with self.subTest(command=command):
                    self.assertTrue(self.deny(root, command), command)
            for command in ("git checkout main", "git diff --stat", "git checkout -- README-not-here.md"):
                with self.subTest(command=command):
                    self.assertFalse(self.deny(root, command), command)


class AgentNameTests(unittest.TestCase):
    """Z16: one rule says whether a name is an agent's, for an identity and for a co-author trailer alike."""

    def test_a_coauthor_is_an_agent_by_the_rule_an_identity_is(self):
        from aidd.config import identities

        for name, agent in (("Claude", True), ("Claude Code", True), ("Jean-Claude", False), ("claude_martin", False)):
            with self.subTest(name=name):
                message = f"fix\n\nCo-authored-by: {name} <someone@example.com>"
                self.assertEqual(bool(identities.agent_coauthors(message)), agent)
                self.assertEqual(identities.is_agent(f"@{name.replace(' ', '-')}") if " " not in name else agent, agent)


class McpPathTests(unittest.TestCase):
    """Z17: a path the MCP server is given stays inside the repository once its links are resolved."""

    def test_a_link_inside_that_points_outside_is_refused(self):
        import os
        import tempfile
        from pathlib import Path

        from aidd.cli import mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp, "repo"), Path(tmp, "secret.md")
            root.mkdir()
            outside.write_text("x\n", encoding="utf-8")
            (root / "docs").mkdir()
            os.symlink(outside, root / "docs" / "notes.md")
            (root / "docs" / "real.md").write_text("y\n", encoding="utf-8")
            self.assertFalse(mcp_server._is_safe_repo_path("docs/notes.md", str(root)))
            self.assertTrue(mcp_server._is_safe_repo_path("docs/real.md", str(root)))
            self.assertTrue(mcp_server._is_safe_repo_path("docs/new.md", str(root)))  # not written yet
            self.assertFalse(mcp_server._is_safe_repo_path("../secret.md", str(root)))


@unittest.skipUnless(shutil.which("git"), "git is required")
class OfflineForecastTests(unittest.TestCase):
    """Z18 (no longer failing; pinned): the route of planned paths needs no parent fetched, offline."""

    def test_gate_paths_offline_with_a_url_parent(self):
        import os
        from unittest import mock

        with adopted_repo("team") as root:
            path = root / config.CONFIG_PATH
            parent = 'extends: [{url: "https://example.com/p.yaml", sha256: "' + "0" * 64 + '"}]\nprofile: team'
            path.write_text(path.read_text(encoding="utf-8").replace("profile: team", parent, 1), encoding="utf-8")
            with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}):
                code, out = run_cli("gate", "--paths", "src/x.py")
        self.assertEqual(code, 0, out)
        self.assertIn("Route: minor", out)


class TenantPoolTests(unittest.TestCase):
    """Z19 (held; pinned): a pool that lists an identity qualified with the repository's own tenant counts that
    person's bare login, for Spec approval as for Merge approval."""

    def test_a_qualified_pool_counts_the_bare_login(self):
        import re

        ctx = example("02-normal-feature")
        ctx["base_config"] = ctx["base_config"].replace(
            'changed_lines_exclude_paths: ["**/package-lock.json"]\n', 'tenant: acme\nchanged_lines_exclude_paths: ["**/package-lock.json"]\n'
        )
        ctx["base_config"] = re.sub(r"approvers: \[[^\]]*\]", 'approvers: ["acme:@checkout-lead"]', ctx["base_config"], count=1)
        self.assertEqual(decide(ctx).codes(), [])


@unittest.skipUnless(shutil.which("git"), "git is required")
class StaleLeaseTests(unittest.TestCase):
    """Z20: a lease on all replaces a stale lease on any narrower work, as a lease on that work does."""

    def test_a_lease_on_all_replaces_a_stale_one_on_a_spec(self):
        import datetime as dt

        from aidd.autopilot import lease

        with adopted_repo("team") as root:
            t0 = dt.datetime(2026, 10, 19, 9, 0, tzinfo=dt.UTC)
            lease.take_lease(root, work="SPEC-3", session_id="aaaa1111", timebox="1h", now=t0)
            _, said = lease.take_lease(root, work="all", session_id="bbbb2222", timebox="1h", now=t0 + dt.timedelta(hours=3))
            held = lease.leases(root)
        self.assertEqual([x["session_id"] for x in held], ["bbbb2222"])
        self.assertIn("replaced the stale lease of session aaaa1111", said)


class EvalMaterialTests(unittest.TestCase):
    """Z21: an eval record's material hash covers the prompt templates, which live in suites.py."""

    def test_the_prompts_are_part_of_the_material(self):
        import tempfile
        from pathlib import Path

        from aidd.evals import records, suites

        with tempfile.TemporaryDirectory() as tmp:
            for suite in ("routing", "roles"):
                with self.subTest(suite=suite):
                    self.assertIn(Path(suites.__file__), records.material_files(suite, Path(tmp)))


class TemplateTests(unittest.TestCase):
    """Z22: a value is filled in once, never read again as a template, so text a person gave (a goal) cannot fill
    another field; a template token with no value still fails."""

    def test_a_value_is_never_filled_again(self):
        from aidd.kernel import text

        self.assertEqual(text.fill_template("{{a}} {{b}}", a="{{b}}", b="B"), "{{b}} B")
        front = '---\ntitle: "{{title}}"\nnote: "x {{note}}"\n---\n{{body}}\n'
        self.assertEqual(text.fill_template(front, title="{{note}}", note="N", body="{{title}}"), '---\ntitle: "{{note}}"\nnote: "x N"\n---\n{{title}}\n')
        with self.assertRaises(ValueError):
            text.fill_template("{{a}} {{c}}", a="A")


@unittest.skipUnless(shutil.which("git"), "git is required")
class FastListTests(unittest.TestCase):
    """Z23: a caller that looks only for a failure (`aidd list`, the pane) never waits on the network, nor on checks
    that only ever warn."""

    def test_failures_only_reaches_no_platform(self):
        from unittest import mock

        from aidd.setup import doctor_checks

        with adopted_repo("team", ci="github") as root:
            with mock.patch.object(github_person, "protection_checks", side_effect=AssertionError("a network check ran")):
                doctor_checks.doctor(root, failures_only=True)
            with mock.patch.object(github_person, "protection_checks", return_value=[("warn", "probed")]) as probe:
                lines = doctor_checks.doctor(root)
            self.assertTrue(probe.called)
            self.assertIn(("warn", "probed"), lines)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardCostTests(unittest.TestCase):
    """Z24: one guarded edit reads the repository once: a read-only git query is never run twice in one hook call."""

    def test_one_edit_runs_few_git_processes(self):
        from unittest import mock

        from aidd.guard import pre_tool
        from aidd.kernel import git as gitmod

        runs: list[tuple[str, ...]] = []
        real = gitmod._run_git

        def counted(args, *a, **k):
            runs.append(tuple(args))
            return real(args, *a, **k)

        with adopted_repo("team", spec="02-normal-feature:specs/SPEC-220.md") as root:
            target = str(root / "src/checkout/rate_limit/limiter.py")
            event = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": target, "old_string": "", "new_string": "x\n"}}
            event |= {"cwd": str(root), "session_id": "s"}
            with mock.patch.object(gitmod, "_run_git", counted):
                pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), io.StringIO())
        reads = [r for r in runs if gitmod._read_only(list(r))]
        self.assertEqual(len(reads), len(set(reads)), "a read-only query ran twice")
        self.assertLessEqual(len(runs), 16, runs)
        self.assertIsNone(gitmod._MEMO.get())  # outside a hook call nothing is kept


@unittest.skipUnless(shutil.which("git"), "git is required")
class GateCostTests(unittest.TestCase):
    """F1: one local `aidd gate` run asks git each read-only question once: 39 git processes here, and 91 before."""

    def test_one_gate_run_runs_few_git_processes(self):
        from unittest import mock

        from aidd.cli import app
        from aidd.kernel import git as gitmod

        runs: list[tuple[str, ...]] = []
        real = gitmod._run_git

        def counted(args, *a, **k):
            runs.append(tuple(args))
            return real(args, *a, **k)

        with adopted_repo("team") as root:
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            git(root, "add", "app.py")
            git(root, "commit", "-qm", "feat: x\n\nAssisted-by: claude-code/claude-opus-5-5")
            with mock.patch.object(gitmod, "_run_git", counted), contextlib.redirect_stdout(io.StringIO()):
                app.main(["gate", "--base", "main"])
        reads = [r for r in runs if gitmod._read_only(list(r))]
        self.assertEqual(len(reads), len(set(reads)), "a read-only query ran twice")
        self.assertLessEqual(len(runs), 45, runs)
        self.assertIsNone(gitmod._MEMO.get())


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitMemoTests(unittest.TestCase):
    """Inside `git.memo()` a read-only query runs once, a read that writes nothing keeps the answers, and any other call
    clears them, so a read after a write sees what the write did."""

    def test_a_write_inside_the_memo_clears_it(self):
        from unittest import mock

        from aidd.kernel import git as gitmod

        runs: list[tuple[str, ...]] = []
        real = gitmod._run_git

        def counted(args, *a, **k):
            runs.append(tuple(args))
            return real(args, *a, **k)

        with adopted_repo("team") as root, mock.patch.object(gitmod, "_run_git", counted), gitmod.memo():
            first = gitmod.rev_parse("HEAD")
            self.assertEqual((gitmod.rev_parse("HEAD"), gitmod.run(["remote"]), gitmod.run(["remote"])), (first, "", ""))
            gitmod.config_value("user.name")
            gitmod.config_value("user.name")
            gitmod.run(["log", "-1", "--format=%H"])
            gitmod.run(["config", "--list"])
            self.assertEqual(gitmod.rev_parse("HEAD"), first)
            self.assertEqual(runs.count(("rev-parse", "--verify", "HEAD^{commit}")), 1)
            self.assertEqual((runs.count(("remote",)), runs.count(("config", "--get", "user.name"))), (1, 1))
            git(root, "commit", "-q", "--allow-empty", "-m", "outside aidd: not through the memo")
            gitmod.run(["commit", "-q", "--allow-empty", "-m", "a write through aidd"])
            self.assertNotEqual(gitmod.rev_parse("HEAD"), first)
            self.assertEqual(runs.count(("rev-parse", "--verify", "HEAD^{commit}")), 2)

    def test_only_read_forms_are_kept(self):
        from aidd.kernel import git as gitmod

        for args in (["remote"], ["config", "--get", "user.name"], ["rev-parse", "HEAD"], ["symbolic-ref", "-q", "HEAD"]):
            self.assertTrue(gitmod._read_only(args), args)
        self.assertTrue(gitmod._read_only(["symbolic-ref", "-q", "--short", "HEAD"]))
        for args in (["remote", "add", "o", "u"], ["remote", "-v"], ["config", "user.name", "x"], ["config", "--get", "--unset", "k"]):
            self.assertFalse(gitmod._read_only(args), args)
        # A delete names one ref, as a read does, yet writes.
        for args in (["symbolic-ref", "-q", "-d", "HEAD"], ["symbolic-ref", "-q", "--delete", "HEAD"], ["symbolic-ref", "-qd", "HEAD"]):
            self.assertFalse(gitmod._read_only(args), args)
            self.assertFalse(gitmod._keeps_memo(args), args)
        keeps = (["show", "HEAD:x"], ["log", "-1"], ["config", "--list"], ["remote", "-v"], ["cat-file", "--batch"], ["hash-object", "x"])
        for args in (*keeps, ["-c", "core.quotePath=false", "diff", "-U0", "a", "b"]):
            self.assertTrue(gitmod._keeps_memo(args), args)
        writes = (["fetch", "origin"], ["commit", "-m", "x"], ["update-ref", "r", "x"], ["remote", "add", "o", "u"], ["config", "user.name", "x"])
        writes += (["config", "--unset", "k"], ["diff", "--output=x"], ["log", "--output=x"], ["hash-object", "-w", "x"], ["symbolic-ref", "HEAD", "r"])
        writes += (["checkout", "main"], ["worktree", "add", "x"], [], ["-c", "user.name=x", "commit", "-m", "x"])
        for args in writes:
            self.assertFalse(gitmod._keeps_memo(args), args)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShortRefTests(unittest.TestCase):
    """Z11: `--ref` takes an abbreviated SHA, expanded in aidd's own checkout, and pins the full one."""

    def test_a_short_sha_is_pinned_in_full(self):
        from helpers import IN_GIT_CHECKOUT, ROOT

        from aidd.setup import pins

        if not IN_GIT_CHECKOUT:
            self.skipTest("aidd runs from a git checkout here only")
        full = git(ROOT, "rev-parse", "HEAD")
        self.assertEqual(pins.full_ref(full[:8]), full)
        self.assertEqual(pins.full_ref(full), full)
        self.assertEqual(pins.full_ref("v1.0.0"), "v1.0.0")
        with self.assertRaises(ValueError):
            pins.full_ref("0000000")


class StandardPinTests(unittest.TestCase):
    """Z31: a standard that follows the current release pins what it checked (a range that covers it counts)."""

    def test_a_pin_behind_the_checked_version_is_a_problem(self):
        import tempfile
        from pathlib import Path

        from helpers import ROOT

        source = (ROOT / "standards" / "rust" / "axum.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp, "rust")
            folder.mkdir()
            (folder / "axum.md").write_text(source, encoding="utf-8")
            self.assertFalse([p for p in library_checks.library_problems(Path(tmp)) if "pins" in p and "axum" in p])  # 0.8 covers 0.8.9
            (folder / "axum.md").write_text(source.replace('pin: "0.8"', 'pin: "0.7"'), encoding="utf-8")
            self.assertTrue([p for p in library_checks.library_problems(Path(tmp)) if "pins 0.7, but the version it checked is 0.8.9" in p])


class CostEstimateSchemaTests(unittest.TestCase):
    """Z52: the Spec's one place for what a change costs to run (tests/test_cost_estimate.py holds the hint)."""

    def test_the_schema_takes_an_estimate_and_names_its_month(self):
        from aidd.kernel import json_schema

        schema = json_schema.bundled("spec.schema.json")["properties"]["cost_estimate"]
        errs: list[str] = []
        json_schema._check({"monthly": "40 EUR", "at_10x": "300 EUR", "source": "infracost diff"}, schema, "$", schema, errs)
        self.assertEqual(errs, [])
        json_schema._check({"at_10x": "300 EUR"}, schema, "$", schema, errs)
        self.assertTrue(errs)  # an estimate names its monthly cost


if __name__ == "__main__":
    unittest.main()
