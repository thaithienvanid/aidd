"""Advisory by default: in the solo and team profiles the guard and the gate advise, and enforce mode (org, audited, or
`mode: enforce`) blocks what the rules forbid. The always-on rules hold in every mode: no agent decides for a person (an
approval, a merge, a ship, a decision record, the config's profile, mode, or gates), changes the guard's own wiring,
or rewrites the default branch."""

import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import check_agent_edit, example, git, make_repo

from aidd import config, gate, workitems
from aidd.guard import approval_commands, pre_tool

SPEC = "02-normal-feature:specs/SPEC-220.md"
REVIEWER = {"agent_type": "aidd-team:reviewer"}


def edit_event(root: Path, rel: str, old: str, new: str, **extra) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(root / rel), "old_string": old, "new_string": new},
        "cwd": str(root),
        "session_id": "s",
        **extra,
    }


def shell_event(root: Path, command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root), "session_id": "s"}


def denied(event: dict) -> bool:
    return '"deny"' in hook(event)


def hook(event: dict) -> str:
    out = io.StringIO()
    pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out)
    return out.getvalue()


class ModeTests(unittest.TestCase):
    def test_solo_and_team_advise_and_org_and_audited_enforce(self):
        self.assertEqual(
            {p: config.profile_mode(p) for p in ("solo", "team", "org", "audited")},
            {"solo": "advisory", "team": "advisory", "org": "enforce", "audited": "enforce"},
        )
        self.assertEqual(config.profile_mode("unknown"), "enforce")

    def test_the_config_wins_then_a_trusted_ci_input_then_the_profile(self):
        self.assertEqual(config.effective_mode("enforce", "advisory", input_trusted=True, fallback="advisory"), "enforce")
        self.assertEqual(config.effective_mode(None, "enforce", input_trusted=True, fallback="advisory"), "enforce")
        self.assertEqual(config.effective_mode(None, "enforce", input_trusted=False, fallback="advisory"), "advisory")
        self.assertEqual(config.effective_mode(None, None, input_trusted=False, fallback="advisory"), "advisory")
        self.assertEqual(config.effective_mode(None, None, input_trusted=False), "enforce")


class SkipTests(unittest.TestCase):
    def test_a_skip_the_person_asked_for_is_reported_and_never_decides(self):
        ctx = example("02-normal-feature")
        before = gate.decide(ctx)
        ctx["commits"][-1]["message"] += "\n\nAidd-Skipped: spec: just do it, I am in a rush\nAssisted-by: claude-code/claude-opus-5-5"
        after = gate.decide(ctx)
        self.assertEqual((after.decision, after.codes()), (before.decision, before.codes()))
        self.assertTrue(any("skipped by the person" in n and "just do it, I am in a rush" in n for n in after.notes), after.notes)


class GuardModeTests(unittest.TestCase):
    def repo(self, profile: str = "team", **init) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_repo(Path(tmp.name).resolve() / "repo", profile, spec=SPEC, status="ready", **init)

    def test_each_mode_comes_from_the_config_the_profile_the_loop_and_the_branch(self):
        root = self.repo(enforce=False)
        cfg = workitems.config_at(root)
        self.assertEqual(workitems.guard_mode(cfg, str(root)), "advise")
        self.assertEqual(workitems.guard_mode(workitems.config_at(self.repo()), "."), "enforce")  # mode: enforce
        self.assertEqual(workitems.guard_mode(workitems.config_at(self.repo("org", enforce=False)), "."), "enforce")
        git(root, "switch", "-qc", "explore/idea")
        self.assertEqual(workitems.guard_mode(cfg, str(root)), "advise")  # the prefix alone frees nothing: the person's record does

    def test_an_edit_enforce_mode_stops_goes_through_with_a_note(self):
        root = self.repo(enforce=False)
        event = edit_event(root, "src/app.py", "", "x = 1\n", **REVIEWER)  # a reviewer writes no code
        self.assertEqual(check_agent_edit(str(root), "src/app.py", event)[0], "allow")
        out = json.loads(hook(event))["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertIn("advisory mode", out["additionalContext"])
        self.assertIn("reviewer", out["additionalContext"])

    def test_each_kind_of_note_comes_once_a_session(self):
        root = self.repo(enforce=False)
        first = json.loads(hook(edit_event(root, "src/app.py", "", "x = 1\n", **REVIEWER)))["hookSpecificOutput"]
        self.assertIn("once a session", first["additionalContext"])
        again = hook(edit_event(root, "src/other.py", "", "y = 2\n", **REVIEWER))
        self.assertNotIn("advisory mode", again)
        self.assertIn("advisory mode", hook(edit_event(root, "src/other.py", "", "y = 2\n", **REVIEWER, session_id="s2")))

    def test_enforce_mode_still_stops_it(self):
        root = self.repo()
        event = edit_event(root, "src/app.py", "", "x = 1\n", **REVIEWER)
        self.assertEqual(check_agent_edit(str(root), "src/app.py", event)[0], "deny")
        self.assertEqual(json.loads(hook(event))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_the_always_on_rules_hold_in_advisory_mode(self):
        root = self.repo(enforce=False)
        loosen = edit_event(root, ".aidd/config.yaml", "profile: team", "profile: solo")
        self.assertEqual(check_agent_edit(str(root), ".aidd/config.yaml", loosen)[0], "deny")
        for wiring in (".codex/hooks.json", ".opencode/plugins/aidd.js", ".claude/settings.json"):
            with self.subTest(wiring=wiring):
                (root / wiring).parent.mkdir(parents=True, exist_ok=True)
                (root / wiring).write_text("{}\n", encoding="utf-8")
                self.assertEqual(check_agent_edit(str(root), wiring, edit_event(root, wiring, "{}", "{ }"))[0], "deny")
        for command in ("gh pr merge 1", "git push --force origin main", "aidd approve spec specs/SPEC-220.md"):
            with self.subTest(command=command):
                self.assertTrue(approval_commands.forbidden_action(command, str(root)), command)

    def test_the_always_on_rules_read_the_mode_the_profile_sets_and_keeps_the_held_commands(self):
        root = self.repo("org", enforce=False)
        text = (root / ".aidd/config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("\nmode:", text)  # org enforces by its profile
        self.assertTrue(denied(edit_event(root, ".aidd/config.yaml", "profile: org", "profile: org\nmode: advisory")))
        root = self.repo(enforce=False)
        held = "guard:\n  held_commands: [{name: deploy, match: [make deploy]}]\n"
        with (root / ".aidd/config.yaml").open("a", encoding="utf-8") as f:
            f.write(held)
        self.assertIsNotNone(workitems.config_at(root))
        self.assertTrue(denied(shell_event(root, "make deploy")))
        self.assertTrue(denied(edit_event(root, ".aidd/config.yaml", held, "")))

    def test_a_config_denial_names_a_way_that_works(self):
        # `loop off` is retired: the way to work free of the loop's checks is an explore branch, which a person starts.
        root = self.repo(enforce=False)
        for event in (
            edit_event(root, ".aidd/config.yaml", "profile: team", "profile: team\ncomponents: {spec_steps: false}"),
            shell_event(root, "echo x >> .aidd/config.yaml"),
        ):
            with self.subTest(tool=event["tool_name"]):
                reason = json.loads(hook(event))["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn("`explore branch <topic>`", reason)
                self.assertNotIn("loop off", reason)

    def test_the_stricter_kept_config_decides_every_edit_while_the_disk_one_is_looser(self):
        """The person's last decision kept `mode: enforce`; a program switched the disk config to advisory. Every
        entry point decides by the kept config: the edit hook, the MCP check_edit tool, and a role's edit."""
        from aidd.guard import edit_check, outside_changes

        root = self.repo()
        outside_changes.keep_state_at_decision(str(root), "land it")
        outside = edit_event(root, "src/elsewhere/new.py", "", "x = 1\n")  # outside every Task's scope
        self.assertTrue(denied(outside), "enforce: denied")
        cfg_path = root / ".aidd/config.yaml"
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace("mode: enforce", "mode: advisory"), encoding="utf-8")
        self.assertTrue(denied(outside), "the kept enforce still decides the hook")
        self.assertEqual(edit_check.check_edit(str(root), "src/elsewhere/new.py", None)[0], "deny")  # the MCP check_edit tool
        self.assertEqual(edit_check.check_edit(str(root), "src/elsewhere/new.py", "developer")[0], "deny")

    def test_a_kept_config_that_no_longer_loads_holds_as_an_invalid_one(self):
        """From the security review of the rename: the stricter config a person's last decision kept, when it no
        longer loads, never yields to a looser one on disk. A role's edit and a held command are denied, as with an
        invalid config, and the denial names the person's next step."""
        from aidd.guard import decision_snapshot, outside_changes, repo_config

        root = self.repo()
        cfg_path = root / ".aidd/config.yaml"
        outside_changes.keep_state_at_decision(str(root), "land it")
        record = decision_snapshot.record_path(str(root))
        kept = json.loads(record.read_text(encoding="utf-8"))
        record.write_text(json.dumps(kept | {"config_text": kept["config_text"] + "bogus_key: 1\n"}), encoding="utf-8")
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace("mode: enforce", "mode: advisory"), encoding="utf-8")
        self.assertIsNone(repo_config.load_config(str(root)))
        edit = edit_event(root, "src/checkout/new.py", "", "x = 1\n", agent_type="aidd-team:developer")
        self.assertIn("no longer loads", hook(edit))
        self.assertTrue(denied(edit))
        # The session's own edit and shell write too: the person's decision, or `aidd upgrade`, comes first.
        own = edit_event(root, "src/checkout/new.py", "", "x = 1\n")
        self.assertIn("no longer loads", hook(own))
        self.assertTrue(denied(own))
        self.assertTrue(denied(shell_event(root, "echo x > src/checkout/new.py")))
        from aidd.guard import edit_check

        self.assertEqual(edit_check.check_edit(str(root), "src/checkout/new.py", None)[0], "deny")  # the MCP check_edit tool
        held = hook(shell_event(root, "terraform apply -auto-approve"))
        self.assertIn('"deny"', held)
        self.assertIn("`aidd upgrade --yes`", held)
        # The kept config loads again: it holds, and the looser disk config does not.
        record.write_text(json.dumps(kept), encoding="utf-8")
        held_cfg = repo_config.load_config(str(root))
        self.assertEqual(held_cfg.raw.get("mode") if held_cfg else None, "enforce")

    def test_a_config_made_invalid_never_switches_the_always_on_rules_off(self):
        root = self.repo(enforce=False)
        self.assertTrue(denied(edit_event(root, ".aidd/config.yaml", "profile: team", "profile: team\nbogus_key: 1")))
        with (root / ".aidd/config.yaml").open("a", encoding="utf-8") as f:
            f.write("bogus_key: 1\n")  # broken by a person: the always-on rules still hold
        (root / ".claude").mkdir(exist_ok=True)
        (root / ".claude/settings.json").write_text("{}\n", encoding="utf-8")
        self.assertTrue(denied(edit_event(root, ".claude/settings.json", "{}", "{ }")))
        for command in ("echo x > .claude/settings.json", "printf 'components: {spec_steps: false}' >> .aidd/config.yaml"):
            with self.subTest(command=command):
                self.assertTrue(denied(shell_event(root, command)), command)

    def test_a_folder_or_a_pathspec_that_holds_a_person_only_file_is_held(self):
        root = self.repo(enforce=False)
        (root / ".claude").mkdir(exist_ok=True)
        (root / ".claude/settings.json").write_text("{}\n", encoding="utf-8")
        for command in (
            "rm -rf .aidd",
            "mv .claude x",
            "git rm -q .claude/settings.json",
            "git mv .aidd z",
            "git checkout HEAD -- .aidd",
            "git restore .claude",
            "git checkout main -- '.aidd/*.yaml'",
            "git checkout main -- ':(glob).aidd/**'",
            "git restore --pathspec-from-file=f -s main",
            "echo '{}' > .mcp.json",
        ):
            with self.subTest(command=command):
                self.assertTrue(denied(shell_event(root, command)), command)
        for command in ("rm -rf build", "git checkout main -- 'src/*.py'", "git rm -q src/old.py", "echo x > $TMPDIR/log"):
            with self.subTest(command=command):
                self.assertFalse(denied(shell_event(root, command)), command)

    def test_the_top_and_an_unexpanded_name_are_held_where_they_reach_a_person_only_file(self):
        root = self.repo(enforce=False)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "spec")
        for command in ("git restore .", "git checkout -- .", "git checkout HEAD -- ."):
            with self.subTest(command=command):
                self.assertFalse(denied(shell_event(root, command)), command)  # it leaves the config as it is
        with (root / ".aidd/config.yaml").open("a", encoding="utf-8") as f:
            f.write("# a person's change\n")
        for command in (
            "git restore .",
            "git checkout -- .",
            "rm -rf .",
            "rm -rf *",
            "echo x > $F",
            "F=.aidd/config.yaml; echo x > $F",
            "echo x > $PWD/.aidd/config.yaml",
            "T=$(mktemp -d); echo x > $T/../.aidd/config.yaml",
            "T=$(mktemp); echo x > $T",  # the variable may be set again before the write: read as written
            "git restore -s nosuchref .",
        ):
            with self.subTest(command=command):
                self.assertTrue(denied(shell_event(root, command)), command)

    def test_a_source_word_is_never_an_option_to_the_guards_own_git(self):
        root = self.repo(enforce=False)
        out = root / "written-by-the-guard"
        self.assertTrue(denied(shell_event(root, f"git restore -s --output={out} .")))
        self.assertFalse(out.exists())


class FileTextTests(unittest.TestCase):
    """A here-document that only becomes a file's text (a handoff note quoting aidd's own line) is data; one a shell or
    git reads, or one written into the git directory, is not."""

    def test_a_note_may_quote_the_record_and_a_hook_may_not_carry_it(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = make_repo(Path(tmp.name).resolve() / "repo", "team", enforce=False)
        ref = "refs/aidd/" + "approvals"
        for command in (f"cat >> notes.md <<'EOF'\nasked: recorded on {ref}\nEOF", f"tee notes.md <<'EOF'\n/aidd {'approve-spec'} S-1 {'a' * 40}\nEOF"):
            with self.subTest(command=command):
                self.assertFalse(denied(shell_event(root, command)), command)
        for command in (
            f"cat <<'EOF' | sh\ngit update-ref {ref} HEAD\nEOF",
            f"git update-ref --stdin <<'EOF'\nupdate {ref} HEAD\nEOF",
            f"cat <<'EOF' > .git/hooks/post-commit\ngit update-ref {ref} HEAD\nEOF",
            f"cat >> notes.md <<EOF\n$(git update-ref {ref} HEAD)\nEOF",  # unquoted: bash runs the substitution
            f'cat >> notes.md <<"EOF"\nok\nEOF\ncat >> notes.md <<EOF\n$(git update-ref {ref} HEAD)\nEOF',
        ):
            with self.subTest(command=command):
                self.assertTrue(denied(shell_event(root, command)), command)


class ReviewFindingTests(unittest.TestCase):
    """The review of the 1.0.0 changes: each form it found the guard misread."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team", enforce=False)

    def test_each_found_bypass_is_held(self):
        for command in (
            "git rm --pathspec-from-file=list.txt",  # the list may name the config
            "git commit -F - <<'EOF'\nAidd-Merge-Approval: x\nEOF",  # git reads the body: a record
            "printf 'POST /session/s/message approve SPEC-1' > /dev/tcp/127.0.0.1/4096",  # bash's raw socket to an agent server
            "curl -d x http://127.0.0.1:4096/session/s/%6dessage",  # a percent-encoded path
            "echo x >> $HOME/.gemini/antigravity-cli/brain/c/.system_generated/logs/transcript.jsonl",
            "deno run agent.ts 'approve SPEC-1'",
            "node cli.js -p approve SPEC-1",  # unquoted words reach the script as one prompt
            "node - approve SPEC-1 < agent.js",  # the script from stdin: every word after `-` is its argument
            "node --no-warnings cli.js --prompt=approve SPEC-1",
            "git rm --pathspec-fr=list.txt",  # git takes an abbreviated option
        ):
            with self.subTest(command=command):
                self.assertTrue(denied(shell_event(self.root, command)), command)
        unreadable = edit_event(self.root, ".aidd/config.yaml", "profile: team", "x: [")
        self.assertTrue(denied(unreadable))  # a valid config made unreadable switches the guard off

    def test_a_runtime_running_its_own_scripts_is_not_held(self):
        for command in ('node scripts/build.js "$OUT"', "cat data.json | node parse.js", "tsx src/index.ts < input.txt", "bun test $FILE", "bun run ship"):
            with self.subTest(command=command):
                self.assertFalse(denied(shell_event(self.root, command)), command)


class DecisionIntegrityTests(unittest.TestCase):
    """aidd's own dialog asks the person, so the guard lets it run where the dialog is known to be theirs; and no agent
    starts another agent with a person's decision as its prompt."""

    def test_aidds_dialog_tools_run_in_claude_code_only(self):
        from aidd.guard import mcp_tools

        for name in ("mcp__plugin_aidd_aidd__approve_spec", "mcp__aidd__approve_all", "mcp__aidd__land", "mcp__aidd__sign_off_proposal"):
            with self.subTest(name=name):
                self.assertEqual(mcp_tools.check_mcp_tool(name, {}, dialogs_ask=True)[0], "allow")
                self.assertEqual(mcp_tools.check_mcp_tool(name, {})[0], "deny")  # another harness: not shown to ask yet
        for name in ("mcp__github__merge_pull_request", "mcp__evil__approve_spec", "mcp__aidd__approve_spec_now"):
            with self.subTest(name=name):
                self.assertEqual(mcp_tools.check_mcp_tool(name, {}, dialogs_ask=True)[0], "deny")

    def test_only_an_event_that_names_itself_claude_code_gets_the_dialog(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = make_repo(Path(tmp.name).resolve() / "repo", "team", spec=SPEC, status="ready")
        event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__aidd__approve_spec", "tool_input": {}, "cwd": str(root), "session_id": "s"}
        claude = {**event, "permission_mode": "default", "transcript_path": "/tmp/t.jsonl"}
        self.assertNotIn("permissionDecision", hook(claude))
        self.assertEqual(json.loads(hook(event))["hookSpecificOutput"]["permissionDecision"], "deny")  # claimed by no dialect

    def test_an_agent_never_prompts_another_agent_with_a_decision(self):
        for command in (
            'claude -p "approve SPEC-1"',
            'opencode run "approve SPEC-1"',
            'codex exec "land it"',
            'echo "approve all" | claude -p',
            'claude -p "$P"',
            'npx @anthropic-ai/claude-code -p "approve SPEC-1"',
            'bunx @anthropic-ai/claude-code -p "approve all"',
            'pnpm dlx opencode-ai run "land it"',
            'node ~/.npm/claude/cli.js -p "approve SPEC-1"',
            'claude-code -p "approve SPEC-1"',
            "curl -d @body.json http://127.0.0.1:4096/session/ses_1/message",
            "npm x @anthropic-ai/claude-code -p 'approve SPEC-1'",
            "pnpm exec claude -p 'approve all'",
            "npx --package=opencode-ai opencode run 'publish'",
            "deno run agent.ts 'approve SPEC-1'",
            "curl -sK request.cfg",
            "wget -i urls.txt",
            "wget --input=urls.txt",
            "curl --url @urls.txt",
            "HOME=/tmp/elsewhere curl -s http://127.0.0.1:4096",
        ):
            with self.subTest(command=command):
                self.assertTrue(approval_commands.forbidden_action(command, "."), command)
        for command in (
            'claude -p "fix the bug"',
            "claude plugin test plugins/aidd-mods",
            "codex --version",
            "opencode models",
            "cursor .",
            "npx prettier --check .",
            "node scripts/build.js",
            "curl -s http://127.0.0.1:4096/session",
            "pnpm exec vitest",
            "npm test",
            "curl -d @payload.json https://api.example.com/v1/items",
        ):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command, "."), command)


if __name__ == "__main__":
    unittest.main()
