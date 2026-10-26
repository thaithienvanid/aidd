"""The role and command files aidd writes for a coding agent other than Claude Code say only what is true there.

aidd wires its guard hook for Claude Code, Codex, Antigravity, Grok Build, and OpenCode, and only Claude Code has the `Skill`, `Agent`,
`Edit`, and `Write` tools and preloads an agent file's skills. So no file another harness reads may promise a hook deny or name those
tools, and each says how that harness finds a skill and what its own agent file enforces (`aidd.setup.harness_text`)."""

import json
import re
import tomllib
import unittest

import helpers
from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import config
from aidd.kernel import resources
from aidd.setup import harness_text, team_install

OTHERS = [h for h in team_install.NATIVE_AGENT_HARNESSES if h != "claude-code"]
# Words that name what only Claude Code has, or promise its hook.
CLAUDE_ONLY = (
    "CLAUDE_",
    ".claude/agents",
    ".claude/commands",
    "Agent call",
    "Skill tool",
    "`Skill`",
    "/clear",
    "/loop",
    "isolation:",
    "`opus`",
    "`sonnet`",
    "aidd:aidd",
    "preloaded",
    "the hook denies",
    "hook deny",
    "the guard denies",
    "the guard then",
    "the guard keeps",
    "one Edit",
    "(Write only",
    "(Explore)",
)
# The harnesses other than Claude Code that get command files and where `aidd init` wires the guard hook, and the words
# that then hold in their command files. Agent files still may not say them. Only OpenCode's guard reads the role from
# every call (the agent's name) without a trust step, so only its files say "the guard keeps" a role's paths closed.
GUARD_WORDS = {
    "antigravity": ("the guard denies", "the guard then"),
    "grok-build": ("the guard denies", "the guard then"),
    "codex": ("the guard denies", "the guard then"),
    "opencode": ("the guard denies", "the guard then", "the guard keeps"),
}


def role_tools() -> dict[str, set[str]]:
    """Each role's Claude Code tools, from its agent file's front matter."""
    out = {}
    for src in sorted((resources.data_dir("team") / "agents").glob("*.md")):
        front, _ = team_install._front_and_body(src.read_text(encoding="utf-8"))
        out[src.stem] = {t.strip() for t in front["tools"].split(",")}
    return out


def role_file(rel: str) -> bool:
    """A role's agent file; a skill's `agents/` folder holds Codex's metadata (`agents/openai.yaml`), never a role."""
    return "/agents/" in rel and "/skills/" not in rel


class EveryOtherHarnessTests(unittest.TestCase):
    def files(self, harness: str, **models) -> dict[str, str]:
        out = team_install.team_files([harness], claude_files=False, models=models or {})
        return {rel: text for rel, text in out.items() if rel != team_install.TEAM_ROLES_REF}

    def test_every_harness_with_role_files_has_a_voice(self):
        self.assertEqual(sorted(OTHERS), sorted(harness_text.VOICES))
        for key in harness_text.VOICES:
            self.assertIn(key, config.HARNESSES)

    def test_no_claude_code_only_text_reaches_any_other_harness(self):
        """Every role and command file for each native harness other than Claude Code, with and without a configured
        model, and the roles reference every harness reads. Antigravity, Grok Build, Codex, and OpenCode run aidd's guard, so their
        command files may say what the guard denies. Agent files still may not."""
        for harness in OTHERS:
            for models in ({}, {"execution": "anthropic/claude-sonnet-5"}):
                files = self.files(harness, **models)
                self.assertEqual(len([r for r in files if role_file(r)]), len(role_tools()), harness)
                for rel, text in files.items():
                    allowed = GUARD_WORDS.get(harness, ()) if not role_file(rel) else ()
                    for word in (w for w in CLAUDE_ONLY if w not in allowed):
                        with self.subTest(harness=harness, rel=rel, word=word):
                            self.assertNotIn(word, text)
        shared = team_install.team_files(["codex"], claude_files=False)[team_install.TEAM_ROLES_REF]
        for word in ("`Skill`", "Skill tool", "aidd:aidd"):
            with self.subTest(shared=word):
                self.assertNotIn(word, shared)

    def test_every_swap_still_matches_its_source(self):
        """A Claude Code phrase reworded in the source would leave that phrase in another harness's file."""
        team = resources.data_dir("team")
        agents = [team_install._team_text(p.read_text(encoding="utf-8")) for p in (team / "agents").glob("*.md")]
        for field, old in harness_text.AGENT.items():
            with self.subTest(field):
                self.assertTrue(any(old in a for a in agents), old)
        roles_ref = team_install._team_text((team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8"))
        for old, _ in harness_text.SHARED:
            with self.subTest(shared=old[:40]):
                self.assertIn(old, roles_ref)

    def test_each_file_says_how_its_harness_finds_a_skill(self):
        for harness in OTHERS:
            voice = harness_text.VOICES[harness]
            for rel, text in self.files(harness).items():
                if role_file(rel):
                    with self.subTest(harness=harness, rel=rel):
                        self.assertIn(voice.skills, prompt(harness, text))
                        self.assertIn(voice.rulebook, prompt(harness, text))

    def test_a_read_only_role_is_told_only_what_its_harness_enforces(self):
        """Codex runs a role with no write area in its read-only sandbox and Kiro gives it no `write` tool, so their
        files may say so; Copilot's file sets no tools, so its text promises nothing."""
        tools = role_tools()
        read_only = {role for role, t in tools.items() if not t & {"Write", "Edit"}}
        self.assertEqual(read_only, {"domain-expert", "reviewer"})
        for harness in OTHERS:
            voice = harness_text.VOICES[harness]
            for role in tools:
                path, _ = team_install._native_agent(harness, f"aidd-{role}", {"description": ""}, "")
                text = prompt(harness, self.files(harness)[path])
                with self.subTest(harness=harness, role=role):
                    self.assertEqual(voice.read_only in text, role in read_only)
                if role in read_only and harness == "codex":
                    self.assertEqual(tomllib.loads(self.files(harness)[path])["sandbox_mode"], "read-only")
                if role in read_only and harness == "kiro":
                    self.assertNotIn("write", json.loads(self.files(harness)[path])["tools"])
        self.assertNotIn("sandbox", harness_text.VOICES["copilot"].read_only)
        self.assertNotIn("tool", harness_text.VOICES["copilot"].read_only)

    def test_each_read_only_claim_matches_the_tools_the_rendered_file_grants(self):
        """What a read-only role's text says its file enforces is what the rendered file grants. A claim about the file
        (no `write` tool, the read-only sandbox) must hold in it, and where the file still grants a shell that writes,
        the text says so instead of reading as if the shell were covered too."""
        tools = role_tools()
        read_only = sorted(role for role, t in tools.items() if not t & {"Write", "Edit"})
        for role in read_only:  # Claude Code: no edit tool, and a shell whose writes only the guard hook denies
            self.assertIn("Bash", tools[role])  # (tests/test_guard_hooks.py, test_a_read_only_role_writes_nothing_through_the_shell)
        for harness in OTHERS:
            files = self.files(harness)
            for role in read_only:
                path, _ = team_install._native_agent(harness, f"aidd-{role}", {"description": ""}, "")
                text = harness_text.VOICES[harness].read_only
                with self.subTest(harness=harness, role=role):
                    self.assertIn(text, prompt(harness, files[path]))
                    self.assertEqual(read_only_claim_problems(text, granted(harness, files[path])), [])

    def test_the_read_only_claim_check_catches_an_overclaim(self):
        kiro = {"write": False, "shell_writes": True, "sandbox": False}
        overclaim = "You write no file, not even through the shell: this file gives you no `write` tool."
        self.assertTrue(read_only_claim_problems(overclaim, kiro))
        self.assertTrue(read_only_claim_problems("This file gives you no `write` tool.", {"write": True, "shell_writes": False, "sandbox": False}))
        self.assertTrue(read_only_claim_problems("This file runs you in the read-only sandbox.", {"write": False, "shell_writes": False, "sandbox": False}))
        self.assertTrue(read_only_claim_problems("`shell` can still write, so don't.", {"write": False, "shell_writes": False, "sandbox": True}))
        self.assertEqual(read_only_claim_problems("You write no file, not even through the shell.", kiro), [])

    def test_kiro_roles_do_not_count_on_a_helper(self):
        """A Kiro agent file lists the tools the role may use, and aidd's lists none that starts another agent."""
        for rel, text in self.files("kiro").items():
            data = json.loads(text)
            with self.subTest(rel):
                self.assertTrue(set(data["tools"]) <= {"read", "write", "shell"})
                self.assertNotIn("helpers of your own", data["prompt"])

    def test_each_advisory_says_what_its_harness_guard_enforces(self):
        """A harness whose guard stops an approval never reads that nothing stops one. Codex's and Antigravity's guard
        cannot tell the role, so their roles keep their write area themselves; Grok Build's and OpenCode's guard read it."""
        no_guard = "no hook checks this role's writes or stops an approval"
        for harness in OTHERS:
            advisory = harness_text.VOICES[harness].advisory
            guarded = config.HARNESSES[harness].guard
            with self.subTest(harness=harness):
                self.assertEqual(no_guard in advisory, not guarded)
                self.assertNotIn("nothing checks", advisory)
                if guarded:
                    self.assertIn("an approval or a merge", advisory)
        for harness in ("codex", "antigravity"):
            self.assertIn("cannot tell which role made a call", harness_text.VOICES[harness].advisory)
        self.assertIn("this role's write area", harness_text.VOICES["opencode"].advisory)
        self.assertIn("write area", harness_text.VOICES["grok-build"].advisory)

    def test_opencode_commands_keep_the_guards_part_in_mvp_and_specify(self):
        """OpenCode's guard reads the role from the agent's name, so its flow commands keep what the guard does there;
        Antigravity's guard cannot tell the role, so its commands drop those sentences."""
        team = resources.data_dir("team") / "commands"
        for name, sentence in (("mvp.md", "so the guard keeps those paths closed to them"), ("specify.md", "The guard then lets only that role write")):
            source = team_install._team_text((team / name).read_text(encoding="utf-8"))
            with self.subTest(name):
                self.assertIn(sentence, harness_text.command(name, source, "opencode"))
                self.assertNotIn(sentence, harness_text.command(name, source, "antigravity"))

    def test_grok_roles_are_told_where_the_packs_live(self):
        self.assertIn("`.claude/skills/aidd-<name>/`", harness_text.VOICES["grok-build"].skills)

    def test_the_agents_md_section_says_what_each_guard_holds(self):
        section = team_install.team_section(["codex", "antigravity", "opencode", "copilot"], claude_files=False)
        self.assertIn("On Codex the guard in `.codex/hooks.json` stops an approval", section)
        self.assertIn("On Google Antigravity the guard in `.agents/hooks.json` stops an approval", section)
        self.assertIn("On OpenCode the guard plugin", section)
        self.assertIn("where aidd wires no guard, the team is advisory", section)


def granted(harness: str, text: str) -> dict[str, bool]:
    """What a rendered role file lets the role do: `write` (an edit or write tool), `shell_writes` (a shell that can
    write files with no person approving each command), and `sandbox` (Codex's read-only sandbox)."""
    if harness == "codex":
        sandbox = tomllib.loads(text).get("sandbox_mode") == "read-only"
        # In the read-only sandbox, an edit or a command needs a person's approval; outside it, both run.
        return {"write": not sandbox, "shell_writes": not sandbox, "sandbox": sandbox}
    if harness == "kiro":
        kiro_tools = json.loads(text)["tools"]
        return {"write": "write" in kiro_tools, "shell_writes": "shell" in kiro_tools, "sandbox": False}
    if harness == "opencode":
        rules = helpers.opencode_permissions(text)
        # `ask` puts a person before each command, so only `allow` lets the shell write unattended.
        return {
            "write": helpers.opencode_effect(rules, "edit", "src/app.py") != "deny",
            "shell_writes": helpers.opencode_effect(rules, "shell", "touch x") == "allow",
            "sandbox": False,
        }
    if harness == "copilot":  # aidd sets no `tools`, and an unset `tools` "defaults to all tools"
        return {"write": True, "shell_writes": True, "sandbox": False}
    if harness == "antigravity":
        front = text.split("---", 2)[1]
        agy_tools = {m.group(1) for m in re.finditer(r"^\s*-\s*(\w+)$", front, re.M)}
        return {
            "write": bool(agy_tools & {"write_file", "edit_file", "write_to_file", "replace_file_content"}),
            "shell_writes": "run_command" in agy_tools,
            "sandbox": False,
        }
    if harness == "grok-build":
        grok_tools: set[str] = set()
        for line in text.splitlines():
            if line.startswith("tools:"):
                grok_tools = {part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()}
        return {
            "write": bool(grok_tools & {"search_replace", "write"}),
            "shell_writes": "run_terminal_command" in grok_tools,
            "sandbox": False,
        }
    raise KeyError(harness)


def read_only_claim_problems(text: str, grants: dict[str, bool]) -> list[str]:
    """Each claim in a read-only text that the rendered file's grants do not back."""
    problems = []
    if "no `write` tool" in text and grants["write"]:
        problems.append("claims no `write` tool, but the file grants one")
    if "sandbox" in text and not grants["sandbox"]:
        problems.append("claims a read-only sandbox the file does not set")
    if "can still write" in text and not grants["shell_writes"]:
        problems.append("says the shell can still write, but the file keeps it from writing")
    names_the_file = re.search(r"\bthis file\b", text, re.I)
    if names_the_file and grants["shell_writes"] and "`shell` can still write" not in text:
        problems.append("credits the file with keeping writes out, but it grants a shell that writes and the text does not say so")
    return problems


def prompt(harness: str, text: str) -> str:
    """The role's prompt as its harness reads it, out of the file's format."""
    if harness == "codex":
        return tomllib.loads(text)["developer_instructions"]
    if harness == "kiro":
        return json.loads(text)["prompt"]
    return text


if __name__ == "__main__":
    unittest.main()


class AutopilotFlowCommandTests(unittest.TestCase):
    """The autopilot flow as each harness reads it: every `aidd autopilot` command it names parses once its placeholders
    are filled, names that harness to `next`, and uses no session variable the harness leaves empty."""

    # What fills each harness's session: Claude Code's own variable, aidd's OpenCode plugin, or aidd's session note.
    FILLED = {"claude-code": "${CLAUDE_SESSION_ID}", "opencode": "${AIDD_SESSION_ID}"}

    def flows(self) -> dict[str, str]:
        out = {"claude-code": (ROOT / "plugins" / "aidd-team" / "commands" / "autopilot.md").read_text(encoding="utf-8")}
        for harness in ("codex", "opencode", "grok-build", "antigravity"):
            out[harness] = team_install.team_files([harness], claude_files=False)[team_install.flow_command_file(harness, "autopilot")]
        out["agents-skills"] = team_install.team_files(["codex", "antigravity"], claude_files=False)[".agents/skills/aidd-autopilot/SKILL.md"]
        return out

    def test_every_autopilot_command_in_each_rendered_flow_parses(self):
        import shlex

        from aidd.cli import parser

        cli = parser.build_parser()
        for harness, text in self.flows().items():
            # Each command it runs; a bare name in a sentence, such as (`aidd autopilot next`), runs nothing.
            commands = [c for c in re.findall(r"`(aidd autopilot [^`]+)`", text) if " --" in c]
            self.assertGreaterEqual(len(commands), 4, harness)
            for command in commands:
                with self.subTest(harness=harness, command=command):
                    leftover = set(re.findall(r"\$\{[A-Z_]+\}", command)) - {self.FILLED.get(harness, "")}
                    self.assertEqual(leftover, set(), "a session variable nothing fills here")
                    filled = command.replace(self.FILLED.get(harness, "<session>"), "s1").replace("<session>", "s1")
                    filled = filled.replace("<work>", "all").replace("<harness>", "codex").replace("<the ask>", "a goal")
                    filled = filled.replace('"<code> <result>"', '"spec.in_progress ok"').replace("<ID>", "SPEC-1")
                    self.assertNotIn("<", filled)
                    args = cli.parse_args(shlex.split(filled)[1:])
                    if args.action == "next" and "--harness" in filled:
                        self.assertEqual(args.harness, "codex" if harness == "agents-skills" else harness)

    def test_codex_names_each_flow_as_it_runs_one(self):
        text = self.flows()["codex"]
        self.assertIn("`$aidd-fix`", text)
        self.assertNotRegex(text, r"(?<![\w./-])/aidd-[a-z]")

    def test_next_takes_the_harnesses_whose_flow_passes_one(self):
        from aidd.autopilot import harness_commands
        from aidd.cli import parser

        sub = next(a for a in parser.build_parser()._actions if getattr(a, "choices", None) and "autopilot" in a.choices).choices["autopilot"]
        nxt = next(a for a in sub._actions if getattr(a, "choices", None) and "next" in a.choices).choices["next"]
        self.assertEqual(tuple(next(a for a in nxt._actions if a.dest == "harness").choices), harness_commands.HARNESSES)

    def test_an_action_names_each_command_as_its_harness_runs_it(self):
        import tempfile
        from pathlib import Path

        from aidd.autopilot import harness_commands

        action = {
            "action": "run",
            "code": "spec.in_progress",
            "flow": "implement",
            "command": "/aidd-team:implement",
            "why": "w",
            "also": [{"code": "spec.draft", "flow": "specify", "command": "/aidd-team:specify", "spec": "SPEC-2", "why": "w"}],
            "decisions": [{"what": "SPEC-3 waits", "how": "type `land it` (or `/aidd land`)"}],
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plugin = harness_commands.in_harness(action, root, "claude-code")
            self.assertEqual((plugin["command"], "file" in plugin), ("/aidd-team:implement", False))
            (root / ".claude" / "commands").mkdir(parents=True)
            (root / ".claude" / "commands" / "aidd-implement.md").write_text("x", encoding="utf-8")
            installed = harness_commands.in_harness(action, root, "claude-code")
            self.assertEqual((installed["command"], installed["file"]), ("/aidd-implement", ".claude/commands/aidd-implement.md"))
            codex = harness_commands.in_harness(action, root, "codex")
            self.assertEqual((codex["command"], codex["file"]), ("$aidd-implement", ".agents/skills/aidd-implement/SKILL.md"))
            self.assertEqual(codex["also"][0]["command"], "$aidd-specify")
            self.assertEqual(codex["decisions"][0]["how"], "type `land it`", "Codex has no `/aidd` verbs")
            opencode = harness_commands.in_harness(action, root, "opencode")
            self.assertEqual((opencode["command"], opencode["file"]), ("/aidd-implement", ".opencode/commands/aidd-implement.md"))
            self.assertIn("/aidd land", opencode["decisions"][0]["how"])
            grok = harness_commands.in_harness(action, root, "grok-build")
            self.assertEqual((grok["command"], grok["file"]), ("/aidd-implement", ".grok/skills/aidd-implement/SKILL.md"))
