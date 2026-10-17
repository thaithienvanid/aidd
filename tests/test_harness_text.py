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
# The harnesses other than Claude Code where `aidd init` wires the guard hook, and the words that then hold in command
# files. Agent files still may not say them. "the guard keeps" stays banned for every harness.
GUARD_HOOKED = {"antigravity", "grok-build", "opencode"}
GUARD_WORDS = ("the guard denies", "the guard then")


def role_tools() -> dict[str, set[str]]:
    """Each role's Claude Code tools, from its agent file's front matter."""
    out = {}
    for src in sorted((resources.data_dir("team") / "agents").glob("*.md")):
        front, _ = team_install._front_and_body(src.read_text(encoding="utf-8"))
        out[src.stem] = {t.strip() for t in front["tools"].split(",")}
    return out


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
        model, and the roles reference every harness reads. Antigravity, Grok Build, and OpenCode run aidd's guard, so their
        command files may say what the guard denies. Agent files still may not."""
        for harness in OTHERS:
            for models in ({}, {"execution": "anthropic/claude-sonnet-5"}):
                files = self.files(harness, **models)
                self.assertEqual(len([r for r in files if "/agents/" in r]), len(role_tools()), harness)
                for rel, text in files.items():
                    hooked = harness in GUARD_HOOKED and "/agents/" not in rel
                    for word in (w for w in CLAUDE_ONLY if not (hooked and w in GUARD_WORDS)):
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
                if "/agents/" in rel:
                    with self.subTest(harness=harness, rel=rel):
                        self.assertIn(voice.skills, prompt(harness, text))
                        self.assertIn(voice.rulebook, prompt(harness, text))

    def test_a_read_only_role_is_told_only_what_its_harness_enforces(self):
        """Codex runs a role with no write area in its read-only sandbox and Kiro gives it no `write` tool, so their
        files may say so; Copilot's file sets no tools, so its text promises nothing."""
        tools = role_tools()
        read_only = {role for role, t in tools.items() if not t & {"Write", "Edit"}}
        self.assertEqual(read_only, {"domain-expert", "reviewer", "verifier"})
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
            "write": bool(agy_tools & {"write_to_file", "replace_file_content"}),
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
