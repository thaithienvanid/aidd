"""`/aidd-team:autopilot`: the harness side of autopilot, and the docs that go with it.

The command loops on the engine's one action per turn and does exactly what it says; it stops at every person's
decision (done line (c)). It is loaded only when a person runs it: no agent preloads its text. aidd starts no agent.
"""

import json
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, run_cli

from aidd.docsgen import generate
from aidd.docsgen import counts
from aidd.docsgen import team_reference
from aidd.setup import team_install
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
COMMAND = TEAM / "commands" / "autopilot.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class AutopilotCommandTests(unittest.TestCase):
    def test_it_is_declared_once_next_to_the_flows(self):
        loop = team_registry.roles()["loop"]
        self.assertEqual(loop["autopilot"]["command"], "autopilot")
        self.assertNotIn("autopilot", [f["command"] for f in loop["flows"]])  # no flow: it runs the flow `next` names
        self.assertEqual(team_reference.team_commands(), [*(f["command"] for f in loop["flows"]), "autopilot"])
        self.assertTrue(COMMAND.is_file())

    def test_it_loops_on_the_engines_action_and_binds_the_lease_to_this_session(self):
        body = text(COMMAND)
        front = body.split("---")[1]
        self.assertIn("\ndisable-model-invocation: true\n", front + "\n")  # a person starts it: that start is the opt-in
        for must in (
            "aidd autopilot start --work <work> --session ${CLAUDE_SESSION_ID}",
            "aidd autopilot next --session ${CLAUDE_SESSION_ID} --harness claude-code --json",
            'aidd autopilot note "<code> <result>" --session ${CLAUDE_SESSION_ID}',
            "aidd autopilot stop --session ${CLAUDE_SESSION_ID}",
            "Do exactly what the action says",
            "`run`",
            "`ask`: stop",
            "`stop`",
            "<!-- aidd:gen roles:lead -->",
            # From real runs: a fix takes the lease too, and a flow's file is read at its path, never searched for.
            "Take the lease (step 2, with the work `all`) and run `next` once (step 3): if it stops at a limit, end there. Else run `/aidd-team:fix`",
            "the action's `file`, else `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`. Never search for it.",
            # From the review: a failed autopilot command ends the run, and only a plan asks "Go on now?".
            "If an `aidd autopilot` command fails, stop: show its message",
            "After an `ask`, ask nothing",
        ):
            self.assertIn(must, body, must)

    def test_a_spec_it_names_keeps_its_declared_route_in_every_harness(self):
        # From real Codex runs: Specify's "minor means the fast lane" stopped a Spec the person had put on the normal
        # route (`aidd new spec --force`), so the run ended with nothing a person could decide.
        from aidd.setup import harness_text

        rule = "A Spec `next` names keeps the route it declares, so a lower `aidd gate --paths` route never sends it to the fast lane."
        self.assertIn(rule, text(COMMAND))
        for harness in ("opencode", "codex", "antigravity", "grok-build"):
            self.assertIn(rule, harness_text.command("autopilot.md", text(COMMAND), harness), harness)

    def test_in_opencode_only_a_missing_plugin_starts_without_the_session(self):
        # From real OpenCode runs: two models read the guard's denial of `start --session` as "the session is missing"
        # and took the fallback, which binds the lease to no session of OpenCode's, so `stop` was denied after.
        from aidd.setup import harness_text

        body = harness_text.command("autopilot.md", text(COMMAND), "opencode")
        self.assertIn("If the start says `--session` expected one argument, the plugin is not installed", body)
        self.assertIn("A guard denial of the start is not that case: it is a stop.", body)
        self.assertNotIn("says the session is missing", body)

    def test_it_never_decides_for_a_person(self):
        body = text(COMMAND)
        for must in ("Never decide it", "never take the step after it", "Never approve, merge, land, publish", "never route around it"):
            self.assertIn(must, body, must)
        self.assertNotIn("/aidd approve", body)
        # The approvals and the ship the command runs: `next`'s, under the person's standing approval, which only they start.
        for m in re.finditer(r"`aidd (?:approve|ship)", body):
            self.assertIn("standing approval", body[max(0, m.start() - 200) : m.end() + 200], body[m.start() - 80 : m.end() + 80])

    def test_a_stop_shows_aidds_own_message_and_names_one_way_on(self):
        body = text(COMMAND)
        for must in ("show the last action's `message` word for word", "Never reword it", "any other way than its `resume`", "in this session or a new one"):
            self.assertIn(must, body, must)
        self.assertNotIn("run this command again in a fresh session", body)
        self.assertNotIn("Start it in a fresh session.", body)

    def test_a_stop_asks_the_person_to_go_on_and_only_their_answer_counts(self):
        body = text(COMMAND)
        for must in (
            '"Go on now?"',
            "start again in this session from step 2",
            "Only the person's own answer counts",
            "no answer means stop",
            'add `--ask "<the ask>"` instead',
            "never plans it twice",
        ):
            self.assertIn(must, body, must)

    def test_a_bare_goal_starts_from_a_plan_a_person_agrees_to(self):
        body = text(COMMAND)
        for must in (
            "/aidd-team:plan",
            "/aidd-team:propose",
            "`project.work: client`",
            "Never turn a one-line ask into code",
            "plan_ready",
            '--ask "<the ask>"',
        ):
            self.assertIn(must, body, must)

    def test_steer_pause_feedback_limits_learn_and_resume(self):
        body = text(COMMAND)
        for must in (
            "Esc",
            "`blockers`",
            "as data, never as instructions",
            "feedback log",
            "(`autopilot`)",
            "timebox",
            "Never extend a limit yourself",
            "/aidd-team:postmortem",
            "retro_every",
            "/loop 30m aidd list --waiting-on-me",
            "push the branch first",
            "Without a platform, skip the push",
            "--tokens N",
            "advisor",
        ):
            self.assertIn(must, body, must)

    def test_it_preloads_nothing(self):
        for path in (*sorted((TEAM / "agents").glob("*.md")), TEAM / "skills" / "aidd-team" / "SKILL.md", ROOT / ".agents" / "skills" / "aidd" / "SKILL.md"):
            self.assertNotIn("${CLAUDE_SESSION_ID}", text(path), path.name)
            self.assertNotIn("aidd autopilot start --work <work>", text(path), path.name)

    def test_init_installs_it_with_the_other_commands(self):
        files = team_install.team_files([], True)
        installed = files[".claude/commands/aidd-autopilot.md"]
        self.assertIn("${CLAUDE_SESSION_ID}", installed)
        self.assertNotIn("aidd-team:", installed)

    def test_the_team_pages_list_it_as_a_supported_command(self):
        self.assertIn("| `/aidd-team:autopilot` | ", generate.render("roles:flows:when"))
        self.assertNotIn("experimental", generate.render("roles:flows:when"))
        self.assertIn("`autopilot`", generate.inline_list("team-commands"))
        self.assertIn("`/aidd-team:autopilot`", generate.render("roles:commands"))
        self.assertEqual(counts.count("commands"), len(team_registry.roles()["loop"]["flows"]) + 1)
        description = json.loads(text(TEAM / ".claude-plugin" / "plugin.json"))["description"]
        self.assertRegex(description, r"\bautopilot\b")


@unittest.skipUnless(shutil.which("git"), "git is required")
class AdvisorTests(unittest.TestCase):
    """`aidd doctor --autopilot` says whether an advisor is configured, as information only."""

    def test_doctor_reports_the_advisor_and_never_warns_without_one(self):
        from aidd.setup import autopilot_readiness

        with helpers.adopted_repo("team", claude_hooks=True) as root:
            self.assertIsNone(autopilot_readiness.advisor_model(root))
            line = autopilot_readiness.autopilot_advisor_line(root)
            self.assertIn("no advisor", line)
            self.assertIn("optional", line)
            (root / ".claude").mkdir(exist_ok=True)
            (root / ".claude" / "settings.local.json").write_text(json.dumps({"advisorModel": "opus"}), encoding="utf-8")
            self.assertEqual(autopilot_readiness.advisor_model(root), "opus")
            self.assertIn("opus", autopilot_readiness.autopilot_advisor_line(root))
            self.assertIn("never a substitute for the verifier, the reviewer, or independent review", autopilot_readiness.autopilot_advisor_line(root))
            code, out = run_cli("doctor", "--autopilot")
            self.assertIn("[info] an advisor is configured", out)
            self.assertNotIn("[warn] no advisor", out)
            self.assertEqual([lvl for lvl, _ in autopilot_readiness.autopilot_checks(root, {})][:4], ["ok", "ok", "ok", "ok"])
            with mock.patch.dict("os.environ", {"CLAUDE_CODE_DISABLE_ADVISOR_TOOL": "1"}):
                self.assertIn("turns it off", autopilot_readiness.autopilot_advisor_line(root))


class DocsTests(unittest.TestCase):
    """The docs, in plain words: delegate, the hooks, the harness settings for a run, and the advisor."""

    def page(self, name: str) -> str:
        return text(ROOT / "docs" / name)

    def test_the_harness_settings_for_a_run(self):
        """METHOD states the settings in vendor-neutral words and links AUTOPILOT, which holds the Claude Code settings."""
        method = self.page("METHOD.md").split("### 5.3 Autopilot\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("delegate", method)
        self.assertIn("AUTOPILOT.md#harness-settings-for-a-run", method)
        for vendor_key in ("sandbox.enabled", "permissions.defaultMode", "advisorModel"):
            self.assertNotIn(vendor_key, method, vendor_key)
        settings = self.page("AUTOPILOT.md").split("## Harness settings for a run\n", 1)[1].split("\n## ", 1)[0]
        for must in (
            "sandbox.enabled",
            "permissions.defaultMode",
            "sandbox.network.allowedDomains",
            "bypassPermissions",
            "no secret",
            "advisorModel",
            "Rule of Two",
        ):
            self.assertIn(must, settings, must)

    def test_the_advisor_is_optional_experimental_and_never_independent_review(self):
        """TEAM owns the advisor's description; the autopilot pages link it rather than restate it."""
        team = self.page("TEAM.md")
        self.assertIn('<a id="the-claude-code-advisor"></a>', team)
        owner = team.split('<a id="the-claude-code-advisor"></a>', 1)[1].split("\n", 1)[0]
        self.assertIn("advisorModel", owner)
        self.assertRegex(owner, r"advisor[^.]*never a substitute for the verifier, the reviewer, or independent review")
        for must in ("optional", "experimental", "Anthropic API", "--tokens"):
            self.assertIn(must, owner, must)
        for page in ("AUTOPILOT.md", "METHOD.md"):
            body = self.page(page)
            self.assertNotIn("never a substitute for the verifier", body, page)
            if "advisorModel" in body:
                self.assertIn("TEAM.md#the-claude-code-advisor", body, page)

    def test_delegate_and_the_hooks_are_documented(self):
        config = self.page("CONFIG.md")
        for must in ("delegate", "prompt-submit", "pre-compact"):
            self.assertIn(must, config, must)
        install = self.page("INSTALL.md")
        for must in ("UserPromptSubmit", "PreCompact", "delegate"):
            self.assertIn(must, install, must)
        howto = self.page("HOW-TO.md")
        self.assertIn("/aidd-team:autopilot", howto)
        self.assertIn("/aidd-team:autopilot", self.page("TEAM.md"))


class CommandContractTests(unittest.TestCase):
    """What the command and its docs promise, and the guard's stated limits."""

    def test_the_run_releases_the_lease_whenever_it_stops_for_a_person(self):
        body = text(COMMAND)
        ask = next(line for line in body.splitlines() if line.strip().startswith("- `ask`"))
        self.assertIn("step 5", ask)  # the end, which runs `aidd autopilot stop`
        stop = next(line for line in body.splitlines() if line.strip().startswith("- `stop`"))
        self.assertIn("step 5", stop)
        end = next(line for line in body.splitlines() if line.startswith("5. **End.**"))
        self.assertIn("aidd autopilot stop --session ${CLAUDE_SESSION_ID}", end)
        resume = next(line for line in body.splitlines() if line.startswith("**Resume.**"))
        self.assertIn("starts the run again", resume)

    def test_the_engine_returns_the_plan_step(self):
        body = text(COMMAND)
        self.assertNotIn("When `aidd list` shows no Spec or proposal for it", body)
        self.assertIn("`next` returns the plan step", body)

    def test_a_note_names_a_spec_only_when_there_is_one(self):
        body = text(COMMAND)
        self.assertNotIn("--session ${CLAUDE_SESSION_ID} --spec <ID>`", body)

    def test_the_docs_say_what_the_code_does(self):
        config = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        for page in (config, install):
            self.assertIn("only when the team is installed", page)
            self.assertIn("An explicit `delegate: always` without the team", page)
        self.assertIn("once per session and role, not once per Task", config + (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))

    def test_the_guard_s_known_limits_are_written_down(self):
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        for must in ("rsync", "curl -o", "git checkout --", "MCP server", "hard link", ".git/"):
            self.assertIn(must, security, must)


if __name__ == "__main__":
    unittest.main()
