"""The aidd-team files aidd generates for OpenCode V2: native `permissions:` front matter for the role
subagents, the flow commands as `.opencode/commands/*.md`, and the docs that tell an adopter how to wire
the aidd MCP server. The formats are verified against OpenCode V2's documentation: agents
(https://opencode.ai/v2/docs/agents, the native `permissions:` rule list, not the V1 `permission`/`tools`/`prompt`)
and commands (https://opencode.ai/v2/docs/commands, Markdown with `description` front matter)."""

import contextlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, opencode_effect, opencode_permissions

from aidd import knowledge
from aidd.cli.commands import confirmations
from aidd.setup import harness_text, opencode_wiring, upgrading
from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.setup import team_install
from aidd.config import baseline, harnesses
from aidd.kernel import globs, resources
from aidd.workitems import typed_words

NODE = shutil.which("node") or ""  # the pure status module runs under node, as the plugin does


class OpenCodeAgentFilesTests(unittest.TestCase):
    """`repo.team_files(["opencode"])` emits the role agents in V2-native front matter."""

    def files(self, **models):
        return team_install.team_files(["opencode"], claude_files=False, models=models or {})

    def test_every_role_agent_uses_v2_front_matter(self):
        out = self.files()
        team = resources.data_dir("team")
        for src in sorted((team / "agents").glob("*.md")):
            rel = f".opencode/agents/aidd-{src.stem}.md"
            with self.subTest(rel):
                text = out[rel]
                self.assertRegex(text, r"^---\ndescription: ")
                self.assertIn("\nmode: subagent\n", text)
                for legacy in ("\npermission:\n", "\ntools:\n", "\nprompt:\n"):
                    self.assertNotIn(legacy, text)
                rules = opencode_permissions(text)
                self.assertEqual({"edit", "shell"}, {r["action"] for r in rules})
                for rule in rules:
                    self.assertEqual(set(rule), {"action", "resource", "effect"})

    def test_each_role_gets_the_rules_its_tools_call_for(self):
        """The last matching rule decides (https://opencode.ai/v2/docs/agents): a role without Write or Edit cannot
        edit, a role without Bash cannot run a command, and a role with Bash is asked before each one."""
        out = self.files()
        team = resources.data_dir("team")
        for src in sorted((team / "agents").glob("*.md")):
            front, _ = team_install._front_and_body(src.read_text(encoding="utf-8"))
            tools = {t.strip() for t in front["tools"].split(",")}
            with self.subTest(src.stem):
                rules = opencode_permissions(out[f".opencode/agents/aidd-{src.stem}.md"])
                for rule in rules:
                    self.assertIn(rule["effect"], ("allow", "ask", "deny"))
                writes = bool(tools & {"Write", "Edit"})
                self.assertEqual(opencode_effect(rules, "edit", "src/app.py"), "allow" if writes else "deny")
                self.assertEqual(opencode_effect(rules, "shell", "git push"), "ask" if "Bash" in tools else "deny")

    def test_reviewer_roles_are_read_only(self):
        out = self.files()
        for role in ("reviewer",):
            with self.subTest(role):
                rules = opencode_permissions(out[f".opencode/agents/aidd-{role}.md"])
                for path in ("src/app.py", "specs/SPEC-1.md", ".aidd/config.yaml"):
                    self.assertEqual(opencode_effect(rules, "edit", path), "deny")
                self.assertNotEqual(opencode_effect(rules, "shell", "rm -rf src"), "allow")

    def test_a_role_without_bash_is_denied_the_shell(self):
        # No landed role lacks Bash today, so the rule is checked on a role made for the test.
        _, text = team_install._native_agent("opencode", "aidd-x", {"description": "x", "tools": "Read, Grep, Glob"}, "body")
        rules = opencode_permissions(text)
        self.assertEqual(opencode_effect(rules, "shell", "ls"), "deny")
        self.assertEqual(opencode_effect(rules, "edit", "a.md"), "deny")

    def test_the_bodies_name_opencode_enforcement_not_a_missing_hook(self):
        developer = self.files()[".opencode/agents/aidd-developer.md"]
        body = developer.split("\n---\n\n", 1)[1]
        self.assertNotIn("no hook checks", body)
        self.assertIn("permissions", body)
        self.assertIn("this role's write area", body)  # the guard plugin reads the role from the agent's name
        # A harness with no guard keeps the advisory that names the missing hook.
        copilot = team_install.team_files(["copilot"], claude_files=False)[".github/agents/aidd-developer.agent.md"]
        self.assertIn("no hook checks", copilot)

    def test_the_configured_model_stays_provider_slash_model(self):
        out = self.files(execution="anthropic/claude-sonnet-5", reviewer="openai/gpt-6-astra")
        developer = out[".opencode/agents/aidd-developer.md"]
        self.assertIn("\nmodel: anthropic/claude-sonnet-5\n", developer)
        # No variant is invented: the front matter keeps the role's provider/model as configured.
        self.assertNotRegex(developer.split("\n---\n", 1)[0], r"model: [^\n]+#")
        self.assertIn("\nmodel: openai/gpt-6-astra\n", out[".opencode/agents/aidd-reviewer.md"])

    def test_inherit_writes_no_model_line(self):
        out = self.files(execution="inherit")
        self.assertNotIn("\nmodel:", out[".opencode/agents/aidd-developer.md"])


class OpenCodeCommandFilesTests(unittest.TestCase):
    """The flow commands as OpenCode commands, generated from the same source as Claude Code's."""

    def commands(self):
        return team_install.team_files(["opencode"], claude_files=False)

    def test_every_flow_command_exists_as_an_opencode_command(self):
        out = self.commands()
        team = resources.data_dir("team")
        srcs = sorted((team / "commands").glob("*.md"))
        self.assertGreaterEqual(len(srcs), 19)
        for src in srcs:
            rel = f".opencode/commands/aidd-{src.stem}.md"
            with self.subTest(rel):
                self.assertIn(rel, out)
                front, body = team_install._front_and_body(out[rel])
                self.assertEqual(list(front), ["description"])
                self.assertNotIn("disable-model-invocation", out[rel])
                self.assertNotIn("argument-hint", out[rel])
                # `_team_text` renames every aidd-team: reference to the OpenCode aidd- names.
                self.assertNotIn("aidd-team:", out[rel])
                self.assertTrue(body.strip())

    def test_no_claude_code_only_text_reaches_opencode(self):
        """OpenCode never expands `${CLAUDE_SESSION_ID}` and has no `Agent` or `Skill` tool and no `.claude/` command
        files (https://opencode.ai/v2/docs/commands, /tools), so none of it may reach a file OpenCode reads."""
        forbidden = ("CLAUDE_", ".claude/", "Agent call", "Skill tool", "`Skill`", "/clear", "/loop", "isolation:", "`opus`", "`sonnet`")
        for models in ({}, {"execution": "anthropic/claude-sonnet-5"}):
            out = team_install.team_files(["opencode"], claude_files=False, models=models)
            files = {rel: text for rel, text in out.items() if rel.startswith(".opencode/")}
            self.assertEqual(len([r for r in files if r.startswith(".opencode/commands/")]), len(list((resources.data_dir("team") / "commands").glob("*.md"))))
            for rel, text in files.items():
                for word in forbidden:
                    with self.subTest(rel=rel, word=word):
                        self.assertNotIn(word, text)

    def test_every_swap_still_matches_its_source(self):
        """A swap whose Claude Code text was reworded in the source would leave that text in the OpenCode file."""
        team = resources.data_dir("team")
        for name, swaps in harness_text.COMMANDS.items():
            text = team_install._team_text((team / "commands" / name).read_text(encoding="utf-8"))
            for old, _ in swaps:
                with self.subTest(command=name, text=old[:40]):
                    self.assertIn(old, text)
        agents = [team_install._team_text(p.read_text(encoding="utf-8")) for p in (team / "agents").glob("*.md")]
        for old, _ in harness_text.VOICES["opencode"].swaps():
            with self.subTest(agent_text=old[:40]):
                self.assertTrue(any(old in a for a in agents))
        lead = knowledge.roles()["loop"]["lead"]
        for old in harness_text.LEAD:
            with self.subTest(lead=old[:40]):
                self.assertTrue(any(old in rule for rule in lead))

    def test_every_command_carries_the_opencode_lead_block(self):
        lead = harness_text.lead_block()
        self.assertEqual(lead.count("\n1. "), 1)
        self.assertIn("`subagent` tool", lead)
        for rel, text in self.commands().items():
            if rel.startswith(".opencode/commands/") and "**You are the lead.**" in text:
                with self.subTest(rel):
                    self.assertIn(lead, text)
                    self.assertNotIn("<!-- aidd:gen roles:lead", text)

    def test_autopilot_binds_its_lease_to_the_session_the_plugin_names(self):
        """No OpenCode variable names the session, so aidd's plugin puts the session's id in place of
        `${AIDD_SESSION_ID}`, and every autopilot command names it; without the plugin, the id start prints."""
        text = self.commands()[".opencode/commands/aidd-autopilot.md"]
        self.assertIn("Run `aidd autopilot start --work <work> --session ${AIDD_SESSION_ID}`.", text)
        self.assertIn(".opencode/plugins/aidd.js", text)
        self.assertIn("`session:` line", text)
        sessions = re.findall(r"--session (\S+?)[`\s]", text)
        self.assertGreaterEqual(len(sessions), 3)
        self.assertEqual(set(sessions), {"${AIDD_SESSION_ID}"})
        self.assertIn(".opencode/commands/aidd-<flow>.md", text)

    def test_the_body_references_the_opencode_names(self):
        specify = self.commands()[".opencode/commands/aidd-specify.md"]
        self.assertIn("`aidd-architect`", specify)  # the roles read as aidd-<role>
        self.assertIn("/aidd-", specify)  # the flow commands read as /aidd-<flow>


class OpenCodeInitTests(unittest.TestCase):
    """`aidd init --team` for an OpenCode adopter, and the docs name the wire-up."""

    def test_init_writes_agents_and_commands_and_uninstall_removes_them(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, team=True, harnesses=["opencode"], approvers=["@me"]))
            specify = root / ".opencode/commands/aidd-specify.md"
            self.assertTrue(specify.is_file())
            self.assertTrue((root / ".opencode/agents/aidd-developer.md").is_file())
            protected = baseline.baseline_data()["protected_paths"]
            for rel in team_install.team_files(["opencode"]):
                self.assertTrue(globs.match_any(protected, rel), rel)
            uninstalling.uninstall(root, yes=True)
            self.assertFalse(specify.exists())
            self.assertFalse((root / ".opencode/agents/aidd-developer.md").exists())

    def test_upgrade_rewrites_a_v1_role_file_in_the_v2_shape(self):
        """The docs promise that `aidd upgrade --yes` rewrites role files an older aidd wrote in OpenCode's V1 shape."""
        if not shutil.which("git"):
            self.skipTest("git is required")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, team=True, harnesses=["opencode"], approvers=["@me"]))
            role = root / ".opencode/agents/aidd-reviewer.md"
            v1 = '---\ndescription: "AIDD reviewer"\nmode: subagent\npermission:\n  edit: deny\n  bash: ask\n---\n\nOld body.\n'
            role.write_text(v1, encoding="utf-8")
            upgrading.upgrade(root, ref="v1.0.0", yes=True)
            text = role.read_text(encoding="utf-8")
            self.assertNotIn("\npermission:\n", text)
            rules = opencode_permissions(text)
            self.assertEqual(opencode_effect(rules, "edit", "src/app.py"), "deny")
            self.assertEqual(text, team_install.team_files(["opencode"], False)[".opencode/agents/aidd-reviewer.md"])

    def test_the_install_snippet_wires_aidd_mcp(self):
        install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        section = install.split("### OpenCode", 1)[1].split("\n### ", 1)[0]
        snippet = re.search(r"```json\n(.*?)```", section, re.S)
        self.assertIsNotNone(snippet)
        data = json.loads(snippet.group(1))
        self.assertEqual(data["mcp"]["servers"]["aidd"]["command"], ["aidd", "mcp"])
        self.assertEqual(data["mcp"]["servers"]["aidd"]["type"], "local")

    def test_the_docs_name_the_opencode_wire_up_and_what_an_adopter_gets(self):
        install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
        section = install.split("### OpenCode", 1)[1].split("\n### ", 1)[0]
        self.assertIn("opencode mcp add aidd -- aidd mcp", section)
        # aidd requires OpenCode V2; V1 is not supported. The version its plugin contract was checked against is named.
        self.assertIn("OpenCode V2", section)
        self.assertIn("V1 is not supported", section)
        self.assertIn(opencode_wiring.OPENCODE_VERSION, section)
        # What the plugin now does: the guard, the loop hooks, and the terminal surface.
        self.assertIn("`.opencode/plugins/aidd.js`", section)
        self.assertIn(opencode_wiring.TUI_DIR, section)
        self.assertIn("`/aidd status`", section)
        self.assertNotIn("No session hooks", section)
        self.assertNotIn("skips the plugin on Windows", section)
        table = harnesses.harnesses_table()
        (row,) = [line for line in table.splitlines() if line.startswith("| OpenCode V2")]
        self.assertIn(".opencode/commands/aidd-<flow>.md", row)
        self.assertIn("opencode mcp add aidd -- aidd mcp", row)
        self.assertNotIn("outside Windows", row)
        # The row INSTALL.md shows is the same text, so the two never drift.
        (shown,) = [line for line in install.splitlines() if line.startswith("| OpenCode V2")]
        self.assertNotIn("outside Windows", shown)
        team = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        (open_row,) = [line for line in team.splitlines() if line.startswith("| OpenCode")]
        self.assertIn("`.opencode/commands/aidd-<flow>.md`", open_row)
        self.assertIn("/aidd status", open_row)
        self.assertNotIn("There are no commands", open_row)
        self.assertIn("/aidd", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


# Every decision that is the person's: the words they type, and the `/aidd` verb beside them. Both homes' menus
# (`/aidd` alone) hold this list, so a person learns one thing, `/aidd`.
DECISIONS = (
    ("approve SPEC-1", "/aidd approve SPEC-1"),
    ("approve merge", "/aidd approve merge"),
    ("land it", "/aidd land"),
    ("publish", "/aidd publish"),
    ("merge it", "/aidd merge"),
    ("approve all", "/aidd approve all"),
    ("stop approving", "/aidd stop"),
    ("decide PROP-1 go", "/aidd decide PROP-1 go"),
    ("sign off PROP-1", "/aidd sign-off PROP-1"),
    ("explore branch <topic>", "/aidd explore <topic>"),
)


class OpenCodeSurfaceTests(unittest.TestCase):
    """The terminal half: the verbs, the argv that records a person's answer, and the status the pane draws. The pure
    module runs under node; the terminal wiring is pinned by text, since only OpenCode's own TUI can load it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for rel, text in opencode_wiring.files().items():
            path = self.tmp / Path(rel).name
            path.write_text(text, encoding="utf-8")
        (self.tmp / "driver.mjs").write_text(
            "import { readFileSync } from 'node:fs'\n"
            "import { pathToFileURL } from 'node:url'\n"
            "const mod = await import(pathToFileURL(process.argv[2]).href)\n"
            "const asks = JSON.parse(readFileSync(process.argv[3], 'utf8'))\n"
            "console.log(JSON.stringify(asks.map(([fn, args]) => mod[fn](...args))))\n",
            encoding="utf-8",
        )

    def ask(self, *asks: tuple) -> list:
        """Run the status module under node and return one answer per (function, args) asked."""
        if not NODE:
            self.skipTest("node runs the status module, as OpenCode runs the plugin")
        path = self.tmp / "asks.json"
        path.write_text(json.dumps([[fn, args] for fn, args in asks]), encoding="utf-8")
        r = subprocess.run(
            [NODE, str(self.tmp / "driver.mjs"), str(self.tmp / "status.js"), str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_the_verbs_are_read_the_way_the_person_typed_them(self):
        asked = self.ask(
            (
                "parseVerb",
                ["status"],
            ),
            ("parseVerb", ["approve SPEC-1 SPEC-2"]),
            ("parseVerb", [""]),
            ("parseVerb", ["frobnicate"]),
            ("helpLines", []),
        )
        self.assertEqual(asked[0], {"verb": "status", "args": []})
        self.assertEqual(asked[1], {"verb": "approve", "args": ["SPEC-1", "SPEC-2"]})
        self.assertEqual(asked[2], {"verb": "menu", "args": []})  # `/aidd` alone lists every decision
        self.assertIn("problem", asked[3])
        help_lines = asked[4]
        self.assertGreaterEqual(len(help_lines), 6)
        for verb in ("status", "approve", "stop", "land", "publish", "merge", "decide", "sign-off", "explore", "update", "help"):
            with self.subTest(verb):
                self.assertTrue(any(verb in line for line in help_lines), help_lines)

    def test_the_status_draws_each_step_aidd_printed(self):
        """The pane draws what `aidd list --waiting-on-me --json` says, in its own words, and nothing else."""
        step = {
            "code": "spec.spec_approval",
            "id": "SPEC-1",
            "where": "specs/SPEC-1.md",
            "what": "waits on your Spec approval",
            "who": "Approver",
            "how": "approve SPEC-1",
        }
        lines = self.ask(
            ("statusLines", [{"schema_version": "1", "steps": [step]}]),
            ("statusLines", [{"schema_version": "1", "steps": []}]),
            ("statusLines", [{"schema_version": "1", "repos": {"~/work/app": [step]}}]),
        )
        self.assertEqual(lines[0], ["SPEC-1: waits on your Spec approval — approve SPEC-1"])
        self.assertEqual(lines[1], ["Nothing waits on you."])
        self.assertEqual(lines[2], ["~/work/app  SPEC-1: waits on your Spec approval — approve SPEC-1"])

    def test_stop_and_explore_are_verbs_and_a_dialog_lists_what_changed_outside_the_session(self):
        changed = [
            {"what": ".aidd/config.yaml changed its control keys (mode)", "restore": "`git checkout -- .aidd/config.yaml`", "held": True, "guard": False}
        ]
        digest = "e" * 64
        asked = self.ask(
            ("parseVerb", ["stop"]),
            ("parseVerb", ["explore caching"]),
            ("parseVerb", ["keep-changes"]),  # retired: no verb records it now
            ("exploreAsked", [["caching"]]),
            ("exploreAsked", [["branch", "explore/cache"]]),
            ("exploreAsked", [["a..b", "c"]]),
            ("exploreArgv", ["explore/caching", False]),
            ("exploreArgv", ["explore/caching", True]),
            ("standingArgv", ["stop"]),
            ("standingArgv", ["all-but-major", True]),
            ("outsideOf", [{"outside_changes": changed}]),
            ("outsideText", [changed]),
            ("outsideText", [[]]),
            (
                "previewOf",
                [
                    "merge",
                    {
                        "failed": False,
                        "said": json.dumps({"head": "a" * 40, "branch": "x", "outside_changes": changed, "outside_hash": digest, "problems": []}),
                    },
                ],
            ),
            ("countedLine", ["Approved.\nSince your last decision, these changed outside the session and count as yours: x.\n"]),
            ("failedLine", ["boom", "stop"]),
            ("landArgv", [{"head": "a" * 40, "seen": digest}]),
            ("approveArgv", ["SPEC-1", "b" * 40, digest]),
            ("standingArgv", ["all", False, digest]),
            ("landArgv", [{"head": "a" * 40, "seen": "not hex"}]),
            ("outsideText", [[{"what": "the git hook pre-commit was added", "restore": "remove the hook pre-commit", "held": True, "guard": True}]]),
        )
        self.assertEqual(asked[0], {"verb": "stop", "args": []})
        self.assertEqual(asked[1], {"verb": "explore", "args": ["caching"]})
        self.assertIn("problem", asked[2])
        self.assertEqual(asked[3:6], ["caching", "cache", None])
        self.assertEqual(asked[6]["switch"], ["switch", "-c", "explore/caching"])
        self.assertEqual(asked[7]["switch"], ["switch", "explore/caching"])
        self.assertEqual(asked[6]["check"], ["check-ref-format", "--branch", "explore/caching"])
        self.assertEqual(asked[8], ["approve", "stop"])
        self.assertEqual(asked[9], ["approve", "all", "--but-major", "--show"])  # the dialog shows first; it records nothing
        self.assertEqual(asked[10], changed)
        self.assertIn(
            "this also changed outside the agent's session, and counts as yours with this answer:\n- .aidd/config.yaml changed its control keys (mode) "
            "(it weakens the guard) (to put it back: `git checkout -- .aidd/config.yaml`)",
            asked[11],
        )
        self.assertEqual(asked[12], "")
        self.assertEqual(asked[13]["outside"], changed)
        self.assertEqual(asked[13]["seen"], digest)
        # The answer names the hash of exactly what the dialog showed, so it takes in a change that weakens the guard.
        self.assertEqual(asked[16], ["land", "--confirmed", "a" * 40, "--outside-hash", digest, "--decided-via", "opencode"])
        self.assertEqual(asked[17][-4:], ["--outside-hash", digest, "--decided-via", "opencode"])
        self.assertEqual(asked[18][-4:], ["--outside-hash", digest, "--decided-via", "opencode"])
        self.assertNotIn("--outside-hash", asked[19])
        # A change that could stop the guard stays held whatever this terminal's dialog answers.
        self.assertIn("(it could stop the guard, so this answer leaves it held: aidd's own dialog or your terminal takes it in)", asked[20])
        self.assertEqual(asked[14], "Since your last decision, these changed outside the session and count as yours: x.")
        self.assertIn("aidd approve stop", asked[15])

    def test_a_bare_aidd_lists_every_decision_and_the_status_says_how_to_end_a_standing_approval(self):
        standing = {"scope": "all-but-major", "since": "2026-10-16T16:52:00+07:00"}
        asked = self.ask(
            ("menuLines", []),
            ("statusFrom", [{"failed": False, "said": json.dumps({"steps": [], "standing": standing})}]),
            ("footerLine", [{"waits": 0, "standing": "x", "failed": False}]),
            ("footerLine", [{"waits": 2, "standing": "x", "failed": False}]),
            ("standingLine", [{"steps": []}]),
        )
        menu = "\n".join(asked[0])
        for words, verb in DECISIONS:
            with self.subTest(words):
                self.assertIn(f"  {words} ", menu)
                self.assertIn(verb, menu)
        line = "Standing approval is on, so aidd records your approvals. To end it: `/aidd stop`, or type `stop approving`. It covers all but major, since 2026-10-16 16:52."
        self.assertEqual(asked[1]["lines"][0], line)
        self.assertEqual(asked[2], "aidd: standing approval on: /aidd stop ends it")
        self.assertEqual(asked[3], "aidd: 2 wait on you (/aidd status) · standing approval on: /aidd stop ends it")
        self.assertEqual(asked[4], "")

    def test_the_status_names_the_product_level_work_as_claude_codes_pane_does(self):
        living = [
            {"kind": "product-prototype", "home": "docs/design/app/", "files": 7, "opened_by": "aidd prototype"},
            {"kind": "architecture", "home": "docs/architecture/", "files": 2},
        ]
        asked = self.ask(
            ("livingLine", [{"steps": [], "living": living}]),
            ("livingLine", [{"steps": []}]),
            ("statusFrom", [{"failed": False, "said": json.dumps({"steps": [], "living": living})}]),
        )
        line = "Product-level work: product prototype in docs/design/app/, 7 files (`aidd prototype` opens it); architecture in docs/architecture/, 2 files."
        self.assertEqual(asked[0], line)
        self.assertEqual(asked[1], "")
        self.assertEqual(asked[2]["lines"][-1], line)
        mod = (ROOT / "plugins" / "aidd-mods" / "hooks" / "register.test.tsx").read_text(encoding="utf-8")
        self.assertIn(line.replace('"', "'"), mod)  # the same words in both harnesses

    def test_every_answer_the_person_gives_names_the_opencode_terminal_and_the_commit_it_read(self):
        head, commit = "a" * 40, "b" * 40
        asked = self.ask(
            ("approveArgv", ["SPEC-1", commit]),
            ("mergeArgv", [{"head": head}, False]),
            ("mergeArgv", [{"head": head}, True]),
            ("landArgv", [{"head": head}]),
            ("standingArgv", ["all"]),
            ("standingArgv", ["all-but-major"]),
            ("standingArgv", ["stop"]),
            ("updateChecks", []),
            ("updateSteps", [{"isDue": True}, {"isDue": True}]),
            ("initCheckArgv", []),
            ("initArgs", ["--team"]),
            ("initArgs", ["--profile", "audited"]),
        )
        repo = {"lines": ["would update .opencode/plugins/aidd.js"], "isDue": True}
        said = self.ask(
            ("updateSaid", [["self-update"], {"failed": True, "said": "no release yet\n"}, repo]),
            ("updateSaid", [["upgrade", "--yes"], {"failed": False, "said": "updated 1 file\n"}, repo]),
            ("updateSaid", [["upgrade", "--yes"], {"failed": False, "said": "updated 1 file\n"}, {"lines": ["would update AGENTS.md"], "isDue": True}]),
        )
        # The words Claude Code's `/aidd update` uses; the plugin aidd just changed loads at OpenCode's next start.
        self.assertEqual(said[0], "The CLI was not updated: no release yet.")
        self.assertEqual(said[1], "This repository's aidd files changed: commit them on a branch, as any change. Restart OpenCode to load the new aidd plugin.")
        self.assertEqual(said[2], "This repository's aidd files changed: commit them on a branch, as any change.")
        self.assertEqual(asked[0], ["approve", "spec", "SPEC-1", "--confirmed", commit, "--decided-via", "opencode"])
        self.assertEqual(asked[1], ["approve", "merge", "--confirmed", head, "--decided-via", "opencode"])
        self.assertEqual(asked[2], ["approve", "merge", "--confirmed", head, "--auto-merge", "--decided-via", "opencode"])
        self.assertEqual(asked[3], ["land", "--confirmed", head, "--decided-via", "opencode"])
        self.assertEqual(asked[4], ["approve", "all", "--confirmed", "all", "--decided-via", "opencode"])
        self.assertEqual(asked[5], ["approve", "all", "--but-major", "--confirmed", "all-but-major", "--decided-via", "opencode"])
        self.assertEqual(asked[6], ["approve", "stop"])
        self.assertEqual(asked[7], [["self-update", "--check"], ["upgrade"]])  # what `/aidd update` shows first
        self.assertEqual(asked[8], [["self-update"], ["upgrade", "--yes"]])  # the CLI, then this repository's files
        self.assertEqual(asked[9], ["init", "--dry-run"])  # what `/aidd init` runs first, and shows
        self.assertEqual(asked[10], ["--profile", "solo", "--team"])  # solo unless a profile is named
        self.assertEqual(asked[11], ["--profile", "audited"])
        for argv in asked[:6]:
            with self.subTest(argv=argv):
                self.assertIn("--confirmed", argv)
                self.assertEqual(argv[argv.index("--decided-via") + 1], "opencode")
        for argv in asked[6:]:
            self.assertNotIn("--confirmed", argv)

    def test_decide_and_sign_off_read_the_preview_then_record_exactly_what_the_dialog_showed(self):
        """As aidd-mods' `/aidd decide` and `/aidd sign-off`: `--show` first, and the record binds the decision, or for a
        sign-off the hash the preview named, with `--decided-via opencode`. Words after `--` can never read as flags."""
        h = "a" * 32
        decide = {"verb": "decide", "id": "PROP-1", "decision": "go", "reason": "fits"}
        sign = {"verb": "sign-off", "id": "PROP-1", "decision": None, "reason": ""}
        asked = self.ask(
            ("parseVerb", ["Decide prop-1 go because fits"]),
            ("proposalAsked", ["decide", ["prop-1", "go", "because", "fits"]]),
            ("proposalAsked", ["sign-off", ["PROP-1"]]),
            ("proposalAsked", ["decide", ["PROP-1"]]),
            ("proposalAsked", ["sign-off", ["PROP-1", "go"]]),
            ("proposalAsked", ["decide", ["--by=@x", "go"]]),
            ("proposalShowArgv", [decide]),
            ("proposalShowArgv", [sign]),
            ("proposalArgv", [decide, {"hash": h}]),
            ("proposalArgv", [sign, {"hash": h}]),
            ("proposalPreviewOf", [sign, {"failed": False, "said": json.dumps({"id": "PROP-1", "title": "T", "hash": h, "problems": []})}]),
            ("proposalPreviewOf", [sign, {"failed": False, "said": json.dumps({"id": "PROP-1", "title": "T", "hash": "", "problems": []})}]),
            ("proposalPreviewOf", [decide, {"failed": True, "said": "", "stderr": "aidd: PROP-9: no such file\n"}]),
            ("proposalPreviewOf", [sign, {"failed": False, "said": json.dumps({"id": "PROP-1", "hash": h, "problems": ["PROP-1 has no go yet"]})}]),
            ("proposalQuestion", [sign, {"id": "PROP-1", "title": "Billing"}]),
            ("recordedLine", ["Proposal PROP-1\n  By  @ana\nRecorded go_no_go in proposals/PROP-1/proposal.md. Commit it"]),
        )
        self.assertEqual(asked[0], {"verb": "decide", "args": ["prop-1", "go", "because", "fits"]})
        self.assertEqual(asked[1], decide)
        self.assertEqual(asked[2], sign)
        self.assertEqual(asked[3:6], [None, None, None])
        self.assertEqual(asked[6], ["proposal", "decide", "--show", "--reason=fits", "--", "PROP-1", "go"])
        self.assertEqual(asked[7], ["proposal", "sign-off", "--show", "--", "PROP-1"])
        self.assertEqual(asked[8], ["proposal", "decide", "--reason=fits", "--confirmed", "go", "--decided-via", "opencode", "--", "PROP-1", "go"])
        self.assertEqual(asked[9], ["proposal", "sign-off", "--confirmed", h, "--decided-via", "opencode", "--", "PROP-1"])
        self.assertEqual(asked[10]["problems"], [])
        self.assertEqual(asked[11]["problems"], ["aidd printed no proposal to decide"])  # no hash to bind: never asks
        self.assertEqual(asked[12]["problems"], ["aidd: PROP-9: no such file"])
        self.assertEqual(asked[13]["problems"], ["PROP-1 has no go yet"])
        self.assertEqual(asked[14], "PROP-1: Billing\n\nSign off PROP-1, as it reads now, so it may be sent?")
        self.assertTrue(asked[15].startswith("Recorded go_no_go"))
        tui = opencode_wiring.tui_text()
        self.assertIn("proposalPreviewOf(asked, await run(dir, proposalShowArgv(asked)))", tui)
        self.assertIn("proposalArgv(asked, shown)", tui)

    def test_the_cli_records_the_argv_the_terminal_builds(self):
        """The argv `/aidd decide` and `/aidd sign-off` run, through the real CLI: the preview names the proposal and
        records nothing, and the confirmed run records exactly that decision, then exactly that text's sign-off."""
        from helpers import make_repo, run_cli

        from aidd import workitems

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = make_repo(Path(tmp.name).resolve() / "repo", "team")
        path = root / "proposals" / "PROP-1" / "proposal.md"
        decide = {"verb": "decide", "id": "PROP-1", "decision": "go", "reason": "fits"}
        sign = {"verb": "sign-off", "id": "PROP-1", "decision": None, "reason": ""}
        with contextlib.chdir(root):
            self.assertEqual(run_cli("new", "proposal", "PROP-1", "--title", "Billing", "--audience", "internal", "--addressee", "the board")[0], 0)
            (show_decide,) = self.ask(("proposalShowArgv", [decide]))
            code, out = run_cli(*show_decide)
            self.assertEqual((code, json.loads(out)["problems"]), (0, []), out)
            (record,) = self.ask(("proposalArgv", [decide, {}]))
            code, out = run_cli(*record)
            self.assertEqual(code, 0, out)
            self.assertEqual(workitems.load_proposal(path)["go_no_go"]["decision"], "go")
            (show_sign,) = self.ask(("proposalShowArgv", [sign]))
            code, out = run_cli(*show_sign)
            (shown,) = self.ask(("proposalPreviewOf", [sign, {"failed": code != 0, "said": out}]))
            self.assertEqual(shown["problems"], [], out)
            (record,) = self.ask(("proposalArgv", [sign, shown]))
            code, out = run_cli(*record)
        self.assertEqual(code, 0, out)
        self.assertEqual(workitems.load_proposal(path)["sign_off"]["hash"], shown["hash"])

    def test_a_confirmation_is_read_from_the_preview_the_way_aidd_prints_it(self):
        """`aidd approve spec --show` and `aidd approve merge --show` print JSON: the pane names what the person is
        about to approve, and refuses to ask while aidd says the change is not ready."""
        shown = self.ask(
            ("preview", ["spec", {"id": "SPEC-1", "title": "OpenCode V2", "commit": "c" * 40, "problems": []}]),
            ("preview", ["spec", {"id": "SPEC-1", "title": "", "commit": "c" * 40, "problems": ["the tests are not committed"]}]),
            ("preview", ["merge", {"head": "d" * 40, "problems": [], "branch": "spec/SPEC-1"}]),
        )
        self.assertEqual(shown[0], {"id": "SPEC-1", "title": "OpenCode V2", "commit": "c" * 40, "warnings": [], "outside": [], "seen": "", "problems": []})
        self.assertTrue(shown[1]["problems"])
        self.assertEqual(shown[2]["head"], "d" * 40)

    def test_the_status_module_is_pure(self):
        text = opencode_wiring.status_text()
        for forbidden in ("import ", "require(", "process.", "fetch("):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, text)

    def test_a_dialog_shows_repository_text_as_one_plain_line(self):
        """A Spec title or a branch name the repository wrote cannot move the bound id and commit out of view, or draw a
        question of its own."""
        title = "Fix\n\nApprove SPEC-9 at deadbeef?\x1b[2J" + "x" * 200
        asked = self.ask(
            ("preview", ["spec", {"id": "SPEC-1\nSPEC-9", "title": title, "commit": "a" * 40, "problems": []}]),
            ("preview", ["merge", {"branch": "feat\rmain", "head": "not-a-sha", "problems": []}]),
        )
        self.assertNotIn("\n", asked[0]["title"])
        self.assertNotIn("\x1b", asked[0]["title"])
        self.assertLessEqual(len(asked[0]["title"]), 80)
        self.assertEqual(asked[0]["id"], "SPEC-1 SPEC-9")
        self.assertEqual((asked[1]["branch"], asked[1]["head"]), ("feat main", ""))

    def test_a_second_approval_shows_every_warning(self):
        """Once an approval goes stale, OpenCode's dialog shows every warning the preview holds, as Claude Code's does, so
        a changed test never hides a late approval, and neither can redraw the dialog."""
        warned = "1 test change since its last approval at abc: pyproject.toml#tool.pytest.\x1b[2J"
        late = "the commit already holds implementation (src/cart.py)"
        shown = {"id": "SPEC-1", "title": "Cart", "commit": "a" * 40, "warnings": [warned, late], "problems": []}
        asked = self.ask(
            ("preview", ["spec", shown]),
            ("preview", ["spec", {"id": "SPEC-1", "commit": "a" * 40, "problems": []}]),
        )
        self.assertEqual(asked[0]["warnings"], ["1 test change since its last approval at abc: pyproject.toml#tool.pytest. [2J", late])
        self.assertEqual(asked[1]["warnings"], [])
        (question,) = self.ask(("specQuestion", [[{"id": "SPEC-1", "shown": asked[0]}]]))
        self.assertTrue(question.startswith(f"SPEC-1 at {'a' * 12}: Cart\n  ! 1 test change"), question)
        self.assertIn(f"\n  ! {late}", question)
        self.assertTrue(question.endswith("Approve SPEC-1?"), question)

    def test_the_merge_and_land_dialogs_show_every_gate_warning(self):
        """OpenCode's merge and land dialogs show every gate warning the preview holds, as Claude Code's do, and a
        warning can never redraw the dialog."""
        warned = ["the change touches a frozen file\x1b[2J", "the Spec has no rollback"]
        (merge,) = self.ask(("preview", ["merge", {"branch": "discount", "head": "d" * 40, "warnings": warned, "problems": []}]))
        self.assertEqual(merge["warnings"], ["the change touches a frozen file [2J", "the Spec has no rollback"])
        (question,) = self.ask(("mergeQuestion", [merge, "Land it?"]))
        self.assertTrue(question.startswith(f"discount at {'d' * 12}\n  ! the change touches a frozen file"), question)
        self.assertIn("\n  ! the Spec has no rollback", question)
        self.assertTrue(question.endswith("\n\nLand it?"), question)

    def test_a_preview_with_no_commit_to_bind_never_asks(self):
        """A `--show` run that failed, or printed no commit, stops with aidd's own reason, as Claude Code's mod does; the
        status lines and a dialog drop bidi overrides as well as control characters."""
        asked = self.ask(
            ("previewOf", ["spec", {"failed": True, "said": "error: no Spec SPEC-9 here\n"}]),
            ("previewOf", ["merge", {"failed": False, "said": json.dumps({"branch": "b", "head": "", "problems": []})}]),
            ("previewOf", ["merge", {"failed": False, "said": json.dumps({"branch": "b", "head": "d" * 40, "problems": []})}]),
            ("oneLine", ["SPEC-1‮ gnihton"]),
            ("statusLines", [{"steps": [{"id": "SPEC-1", "what": "SPEC-1 Fix\x1b[2J⁦x", "how": "type\napprove SPEC-1"}]}]),
        )
        self.assertEqual(asked[0]["problems"], ["error: no Spec SPEC-9 here"])
        self.assertEqual(asked[1]["problems"], ["aidd printed no commit to approve"])
        self.assertEqual(asked[2]["problems"], [])
        self.assertEqual(asked[3].split(), ["SPEC-1", "gnihton"])  # the override is gone, so nothing reads reversed
        self.assertEqual(asked[4], ["SPEC-1: Fix [2J x — type approve SPEC-1"])

    def test_update_reads_each_check_on_its_own(self):
        asked = self.ask(
            ("cliUpdate", ["error: no release of aidd is out yet\n"]),  # before the first release, or offline
            ("cliUpdate", ["would update from aidd 1.0.0 (aaaa) to 1.0.1 with uv\n"]),
            ("repoUpdate", ["would update .agents/skills/aidd/SKILL.md\n\nThe CLI itself: `aidd self-update`.\n"]),
            ("repoUpdate", ["nothing to update: this repository already matches aidd 1.0.0\n"]),
            ("updateSteps", [{"isDue": False, "isCurrent": True}, {"isDue": True}]),
            ("updateQuestion", [{"line": "would update to 1.0.1", "isDue": True}, {"lines": ["would update x"], "isDue": True}]),
        )
        self.assertEqual(asked[0], {"line": "error: no release of aidd is out yet", "isDue": False, "isCurrent": False})
        self.assertTrue(asked[1]["isDue"])
        self.assertEqual(asked[2], {"lines": ["would update .agents/skills/aidd/SKILL.md"], "isDue": True})
        self.assertFalse(asked[3]["isDue"])
        self.assertEqual(asked[4], [["upgrade", "--yes"]])  # a current CLI updates the repository's files
        self.assertIn("The aidd CLI: update to 1.0.1", asked[5])
        self.assertTrue(asked[5].endswith("Update now?"))

    def test_merge_asks_only_where_a_pull_request_merges(self):
        asked = self.ask(
            ("mergesOnPlatform", [{"merges_on_platform": True}]),
            ("mergesOnPlatform", [{"branch": "discount", "problems": []}]),
            ("mergesOnPlatform", [None]),
        )
        self.assertEqual(asked, [True, False, False])
        # Checked before any dialog or record; a failed `land --show` never reads as "not on a platform".
        self.assertIn("if (!where.failed && !mergesOnPlatform(", opencode_wiring.tui_text())

    def test_a_failed_status_says_why_and_never_that_nothing_waits(self):
        """A failed `aidd list --waiting-on-me --json` shows aidd's reason, as Claude Code's pane does; the footer counts
        only real waits, and says when aidd could not say."""
        nothing = {"code": "nothing_matches", "what": "nothing waits on you", "how": "`aidd list` shows all open work"}
        step = {"code": "spec.spec_approval", "id": "SPEC-1", "what": "waits", "how": "approve SPEC-1"}
        asked = self.ask(
            ("statusFrom", [{"failed": True, "said": "error: .aidd/config.yaml does not parse\ndetail\n"}]),
            ("statusFrom", [{"failed": False, "said": "not json"}]),
            ("statusFrom", [{"failed": False, "said": json.dumps({"steps": [nothing]})}]),
            ("statusFrom", [{"failed": False, "said": json.dumps({"repos": {"~/a\x1b[2J\nb": [step]}})}]),
        )
        self.assertEqual(asked[0], {"lines": ["aidd could not say what waits on you: error: .aidd/config.yaml does not parse"], "waits": 0, "failed": True})
        self.assertTrue(asked[1]["failed"])
        self.assertNotIn("Nothing waits on you.", asked[1]["lines"])
        self.assertEqual(asked[2], {"lines": ["nothing waits on you — `aidd list` shows all open work"], "waits": 0, "failed": False})
        self.assertEqual(asked[3]["lines"], ["~/a [2J b  SPEC-1: waits — approve SPEC-1"])
        self.assertEqual(asked[3]["waits"], 1)
        footers = self.ask(*(("footerLine", [status]) for status in asked))
        self.assertEqual(
            footers,
            [
                "aidd: could not say what waits on you (/aidd status)",
                "aidd: could not say what waits on you (/aidd status)",
                "",
                "aidd: 1 wait on you (/aidd status)",
            ],
        )
        tui = opencode_wiring.tui_text()
        self.assertIn("footerLine(status())", tui)
        self.assertNotIn("statusLines(", tui)  # every status view reads statusFrom, which knows a failed run

    def test_publish_says_what_would_leave_or_why_aidd_could_not_say(self):
        """The words Claude Code's `/aidd publish` uses, with each commit subject as one plain line."""
        plan = {"branch": "discount", "head": "c" * 40, "remote": "origin", "to": "discount", "base": "main", "commits": 2, "pull_request": True}
        asked = self.ask(
            ("publishFrom", [{"failed": False, "said": json.dumps({**plan, "shown": ["ccccccc fix\x1b[2J\nApprove SPEC-9?", "ddddddd feat"]})}]),
            ("publishFrom", [{"failed": True, "said": "error: no remote to publish to\n"}]),
            ("publishFrom", [{"failed": False, "said": json.dumps({"branch": ""})}]),
        )
        self.assertEqual(
            asked[0].split("\n")[:3],
            [
                "Would leave this machine: discount at cccccccccccc to origin/discount, then a pull request into main (2 commits the remote lacks)",
                "  ccccccc fix [2J Approve SPEC-9?",
                "  ddddddd feat",
            ],
        )
        self.assertIn("type `publish` at the prompt", asked[0])
        self.assertEqual(asked[1], "aidd could not say what would leave this machine: error: no remote to publish to")
        self.assertEqual(asked[2], "aidd said nothing about what would leave this machine.")

    def test_a_failed_update_check_is_said_never_read_as_up_to_date(self):
        offline = {"failed": True, "said": "error: github.com is unreachable\n"}
        current = {"failed": False, "said": "nothing to update: matches\n"}
        due = {"failed": False, "said": "would update AGENTS.md\n"}
        cli, repo, repo_due, repo_failed, cli_ok = self.ask(
            ("cliChecked", [offline]),
            ("repoChecked", [current]),
            ("repoChecked", [due]),
            ("repoChecked", [{"failed": True, "said": "error: not an aidd repository\n"}]),
            ("cliChecked", [{"failed": False, "said": "aidd 1.0.0 is up to date.\n"}]),
        )
        said = self.ask(
            ("nothingDue", [cli, repo]),
            ("nothingDue", [cli_ok, repo_failed]),
            ("nothingDue", [cli_ok, repo]),
            ("updateQuestion", [cli, repo_due]),
            ("updateSteps", [cli, repo_due]),
        )
        self.assertEqual(
            said[0],
            {"message": "aidd could not check for a new CLI: error: github.com is unreachable This repository's aidd files are up to date.", "failed": True},
        )
        self.assertEqual(
            said[1], {"message": "aidd 1.0.0 is up to date. aidd could not check this repository's files: error: not an aidd repository", "failed": True}
        )
        self.assertEqual(said[2], {"message": "aidd is up to date. aidd 1.0.0 is up to date.", "failed": False})
        self.assertTrue(said[3].startswith("aidd could not check for a new CLI: error: github.com is unreachable\n\nThis repository's aidd files"))
        self.assertNotIn("up to date", said[3])
        # A CLI that may be behind would write its older files, so the repository's files wait, and the dialog says why.
        self.assertIn("would update AGENTS.md\n\nThis repository's aidd files wait, because aidd can't tell that this CLI is current", said[3])
        self.assertEqual(said[4], [])
        tui = opencode_wiring.tui_text()
        self.assertIn("if (checked.said === MISSING) return toast(context, MISSING, true)", tui)  # aidd did not start: a failure
        self.assertIn('if (steps.length === 0) return toast(context, checkParts(cli, repo).join(" "), true)', tui)  # nothing would run
        self.assertIn("const waits = stepWaits(argv, failed)", tui)  # a failed CLI update stops the files (stepWaits)

    def test_the_files_upgrade_only_on_a_cli_known_to_be_current(self):
        """A checkout's line, or any line but "is up to date", leaves the CLI unknown, so the files wait; after a failed
        CLI update they wait too."""
        checkout = "aidd runs from the checkout at /src/aidd, so it follows that checkout: `git pull` there updates it.\n"
        latest = "aidd 1.0.0 (06b091a81bcd) is up to date: the latest is v1.0.0 (06b091a81bcd).\n"
        due = {"lines": ["would update AGENTS.md"], "isDue": True}
        asked = self.ask(
            ("cliUpdate", [checkout]),
            ("cliUpdate", [latest]),
            ("updateSteps", [{"line": checkout, "isDue": False, "isCurrent": False}, due]),
            ("updateSteps", [{"line": latest, "isDue": False, "isCurrent": True}, due]),
            ("updateSteps", [{"line": "would update", "isDue": True, "isCurrent": False}, due]),
            ("checkParts", [{"line": checkout, "isDue": False, "isCurrent": False}, due]),
            ("stepWaits", [["upgrade", "--yes"], True]),
            ("stepWaits", [["upgrade", "--yes"], False]),
            ("stepWaits", [["self-update"], True]),
        )
        self.assertFalse(asked[0]["isCurrent"])
        self.assertTrue(asked[1]["isCurrent"])
        self.assertEqual(asked[2], [])
        self.assertEqual(asked[3], [["upgrade", "--yes"]])
        self.assertEqual(asked[4], [["self-update"], ["upgrade", "--yes"]])
        self.assertTrue(any(part.startswith("This repository's aidd files wait") for part in asked[5]), asked[5])
        self.assertTrue(asked[6].startswith("This repository's aidd files wait"))
        self.assertIsNone(asked[7])
        self.assertIsNone(asked[8])

    def test_a_failed_self_update_says_the_last_line_the_installer_printed(self):
        repo = {"lines": [], "isDue": False}
        asked = self.ask(
            (
                "updateSaid",
                [
                    ["self-update"],
                    {
                        "failed": True,
                        "said": "Resolved 3 packages\nerror: the wheel did not match its checksum.\n",
                        "stderr": "Resolved 3 packages\nerror: the wheel did not match its checksum.",
                    },
                    repo,
                ],
            ),
            ("lastLine", ["one\ntwo\n\n"]),
        )
        self.assertEqual(asked[0], "The CLI was not updated: error: the wheel did not match its checksum.")
        self.assertEqual(asked[1], "two")

    def test_a_failed_preview_run_never_asks_even_with_a_commit_in_its_json(self):
        """Claude Code's pane stops on any failed `--show` run, so OpenCode's does too, unless aidd's JSON names its own
        problems; a process a signal stopped says so, never "exited null"."""
        shown = json.dumps({"id": "SPEC-1", "title": "t", "commit": "a" * 40, "problems": []})
        asked = self.ask(
            ("previewOf", ["spec", {"failed": True, "said": shown, "stderr": "error: the Spec changed while it was read\n"}]),
            ("previewOf", ["spec", {"failed": True, "said": shown}]),
            ("previewOf", ["spec", {"failed": True, "said": json.dumps({"commit": "a" * 40, "problems": ["the tests are not committed"]})}]),
        )
        self.assertEqual(asked[0]["problems"], ["error: the Spec changed while it was read"])
        self.assertEqual(asked[1]["problems"], ["aidd stopped before it named a commit to approve"])
        self.assertEqual(asked[2]["problems"], ["the tests are not committed"])
        self.assertIn("was stopped by ${error.signal}", opencode_wiring.tui_text())

    def test_a_verb_that_throws_names_a_command_that_works_in_a_terminal(self):
        asked = self.ask(
            ("failedLine", ["dialog closed\nstack", "approve SPEC-1"]),
            ("failedLine", ["", "update"]),
            ("failedLine", [None, "nonsense"]),
        )
        self.assertEqual(asked[0], "aidd: dialog closed; run `aidd approve` in a terminal")
        self.assertEqual(asked[1], "aidd: the command failed; run `aidd self-update` in a terminal")
        self.assertEqual(asked[2], "aidd: the command failed; run `aidd --help` in a terminal")
        self.assertIn("failedLine(error?.message ?? error, input)", opencode_wiring.tui_text())

    def test_one_character_set_in_both_homes_the_clis(self):
        """`oneLine` and Claude Code's `clean` use the CLI's `plain()` set, plus U+2028 and U+2029, and replace each run
        with one space."""
        asked = self.ask(("oneLine", ["l‎r‏a؜b c d‪e⁦f\x9bg"]))
        self.assertEqual(asked[0], "l r a b c d e f g")
        status = (ROOT / "templates" / "opencode" / "aidd-tui" / "status.js").read_text(encoding="utf-8")
        mods = (ROOT / "plugins" / "aidd-mods" / "hooks" / "aidd.ts").read_text(encoding="utf-8")
        sets = [re.search(r"const UNSAFE = (/.*/g)\n", text).group(1) for text in (status, mods)]
        self.assertEqual(sets[0], sets[1])

    def test_the_explore_question_and_line_name_the_topic(self):
        for said in self.ask(("exploreQuestion", ["explore/caching"]), ("exploreLine", ["explore/caching"])):
            self.assertIn("`explore branch caching`", said)
            self.assertNotIn("<topic>", said)

    def test_land_publish_merge_and_the_retired_ship(self):
        asked = self.ask(
            ("standingScope", [["and", "publish"]]),
            ("standingScope", [["and", "publish,", "but", "major"]]),
            ("standingArgv", ["all-and-publish-but-major"]),
            ("publishShowArgv", []),
            ("parseVerb", ["ship"]),
        )
        self.assertEqual(asked[0], "all-and-publish")
        self.assertEqual(asked[1], "all-and-publish-but-major")
        self.assertEqual(asked[2], ["approve", "all", "--and-publish", "--but-major", "--confirmed", "all-and-publish-but-major", "--decided-via", "opencode"])
        self.assertEqual(asked[3], ["publish", "--show"])  # the plan alone: the person's typed `publish` records it
        self.assertIn("`/aidd land`", asked[4]["problem"])  # a retired verb records nothing and names the new ones

    def test_the_terminal_half_speaks_opencode_and_asks_no_model(self):
        text = opencode_wiring.tui_text()
        self.assertIn("@opencode/plugin/tui", text)
        self.assertIn("./status.js", text)
        for verb in ("status", "approve", "land", "publish", "merge", "update", "init", "help"):
            with self.subTest(verb):
                self.assertIn(verb, text)
        for forbidden in ("generate", "mcp", "model", "anthropic", "openai"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, text)

    def test_opencode_is_a_place_a_persons_confirmation_can_come_from(self):
        """The dialog answer records `--decided-via opencode`; the guard denies the same words from an agent's shell, so
        adding the value does not widen who may approve."""
        self.assertIsNone(confirmations.confirmation_problem("opencode"))
        self.assertIsNone(confirmations.confirmation_problem(confirmations.DECIDED_VIA))
        self.assertIsNotNone(confirmations.confirmation_problem("opencode-tui"))
        self.assertIsNotNone(confirmations.confirmation_problem(""))
        self.assertTrue(confirmations.DECIDED_WHERE.fullmatch("opencode"))
        self.assertIn("opencode", opencode_wiring.tui_text())

    def test_no_shipped_command_can_be_read_as_a_typed_decision_or_shadow_the_verb(self):
        """A slash command a person runs expands into a prompt the plugin sends to aidd's prompt hook. If a body read as
        a typed decision, running a command would approve for them; and a command named `aidd` would take the `/aidd`
        verb's place."""
        out = team_install.team_files(["opencode"], claude_files=False)
        commands = {rel: text for rel, text in out.items() if rel.startswith(".opencode/commands/")}
        self.assertGreaterEqual(len(commands), 19)
        self.assertNotIn(".opencode/commands/aidd.md", out)
        for rel, text in commands.items():
            front, body = team_install._front_and_body(text)
            with self.subTest(rel):
                self.assertIsNone(typed_words.parse_typed(body), f"{rel} reads as a typed decision")
                self.assertIsNone(typed_words.parse_typed(text), f"{rel} reads as a typed decision as one file")


class VerbParityTests(unittest.TestCase):
    """The OpenCode terminal and the aidd-mods pane in Claude Code give a person the same `/aidd` verbs, so a verb added to
    one is never forgotten in the other. The only differences are named here, each with its reason."""

    # aidd-mods' own verbs that OpenCode answers another way.
    MODS_ONLY = {
        "close": "hides the Claude Code pane; OpenCode has no pane",
        "skill": "loads the aidd skill for Claude Code's agent, as a bare `/aidd` did; OpenCode's agent reads the skill by itself",
    }

    def test_both_homes_hold_the_repository_files_for_a_current_cli_in_the_same_words(self):
        aidd_ts = (ROOT / "plugins" / "aidd-mods" / "hooks" / "aidd.ts").read_text(encoding="utf-8")
        status = (ROOT / "templates" / "opencode" / "aidd-tui" / "status.js").read_text(encoding="utf-8")
        found = [re.search(r'export const REPO_WAITS =\s+"([^"]+)"', text) for text in (aidd_ts, status)]
        self.assertTrue(all(found), "REPO_WAITS moved in one home: update this test")
        self.assertEqual(found[0].group(1), found[1].group(1))
        self.assertIn("`aidd upgrade --yes`", found[0].group(1))  # the step that works once the CLI is current

    def test_each_verb_is_in_both_or_named_with_its_reason(self):
        mods = (ROOT / "plugins" / "aidd-mods" / "hooks" / "register.tsx").read_text(encoding="utf-8")
        listed = re.search(r"!\[([^\]]*)\]\.includes\(asked\.verb\)", mods)
        self.assertIsNotNone(listed, "aidd-mods' verb list moved: update this test")
        aidd_ts = (ROOT / "plugins" / "aidd-mods" / "hooks" / "aidd.ts").read_text(encoding="utf-8")
        status = (ROOT / "templates" / "opencode" / "aidd-tui" / "status.js").read_text(encoding="utf-8")
        # The explore verb is one constant in each home, so renaming it is one line there.
        word = re.search(r"export const EXPLORE_WORD = '([a-z-]+)'", aidd_ts).group(1)
        self.assertEqual(re.search(r'export const EXPLORE_WORD = "([a-z-]+)"', status).group(1), word)
        self.assertEqual(word, typed_words.EXPLORE_WORD)
        mods_verbs = set(re.findall(r"'([a-z-]+)'", listed.group(1))) | ({word} if "EXPLORE_WORD" in listed.group(1) else set())
        mods_verbs -= {"ship", "menu"}  # retired in both; and the bare `/aidd`, which both answer with the menu
        found = re.search(r"export const VERBS = \[([^\]]*)\]", status).group(1)
        opencode_verbs = set(re.findall(r'"([a-z-]+)"', found)) | ({word} if "EXPLORE_WORD" in found else set())
        self.assertEqual(mods_verbs - opencode_verbs, set(self.MODS_ONLY), "a verb aidd-mods has: add it to the OpenCode terminal too")
        self.assertEqual(opencode_verbs - mods_verbs, set(), "a verb the OpenCode terminal has: add it to aidd-mods too")
        retired = re.search(r"export const RETIRED = \{([^}]*)\}", status).group(1)
        self.assertIn("ship", retired)  # both point the retired word on

    def test_both_menus_list_every_decision_with_its_words_and_its_verb(self):
        aidd_ts = (ROOT / "plugins" / "aidd-mods" / "hooks" / "aidd.ts").read_text(encoding="utf-8")
        menu = re.search(r"export const AIDD_MENU = \[(.*?)\]\.join", aidd_ts, re.S).group(1).replace("${EXPLORE_WORD}", "explore")
        for words, verb in DECISIONS:
            with self.subTest(words):
                self.assertIn(f"  {words} ", menu)
                self.assertIn(verb, menu)
        # Each typed word in the list is one aidd's own prompt hook reads, so the menu never names words it ignores.
        for words, _ in DECISIONS:
            with self.subTest(typed=words):
                self.assertIsNotNone(typed_words.parse_typed(words.replace("<topic>", "cache")), words)


if __name__ == "__main__":
    unittest.main()
