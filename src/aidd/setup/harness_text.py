"""The team's role and command files as each coding agent other than Claude Code reads them.

The roles and the flow commands are written once, for Claude Code, and a few of their words name what only Claude Code
has: its `Skill`, `Agent`, `Edit`, and `Write` tools, the skills an agent file preloads, its session variable, `/clear`
and `/loop`, its tier names, and the guard hook, which aidd wires for Claude Code, Codex, Antigravity, Grok Build, and OpenCode. Each harness that gets role files
(`team_install.NATIVE_AGENT_HARNESSES`) has a `Voice` here: how its agents find a skill, what its agent file enforces,
and whether the role can start a subagent, each from the harness's own documentation. `agent()` swaps every Claude Code
phrase (`AGENT`) for that harness's words. Where a capability could not be verified, the voice says less: it tells the
role what to do and promises no enforcement.

OpenCode V2, Google Antigravity, Grok Build, and Codex also get the flow commands; `CODEX_LEAD` and `CODEX_COMMANDS` are
Codex's, and `SHARED_SKILLS_LEAD` is the one `.agents/skills/` file Antigravity and Codex share where both are wired. `command()` and `lead_block()` take the harness;
`ANTIGRAVITY_LEAD` and `ANTIGRAVITY_COMMANDS` are Antigravity's, `GROK_LEAD` and `GROK_COMMANDS` are Grok Build's, and `LEAD` and
`COMMANDS` are OpenCode's (checked against https://opencode.ai/v2/docs on 2026-10-12): the `subagent`, `skill`, `edit`,
and `write` tools, the `explore` subagent, and `${AIDD_SESSION_ID}` for the session, which aidd's plugin fills in, because a
command template expands only `$ARGUMENTS` and `$1`... (https://opencode.ai/v2/docs/commands) and no variable names the session.

Each swap names the exact text it replaces, so a reworded source shows up as a swap that no longer matches
(`tests/test_harness_text.py`, `tests/test_opencode.py`), never as Claude Code wording left in another harness's file.
"""

from __future__ import annotations

import dataclasses
import re

from aidd import knowledge

# The first paragraph of a role file in a harness where no aidd hook runs.
ADVISORY = (
    "Outside Claude Code this team is advisory: no hook checks this role's writes or stops an approval, so follow the "
    "write area and the loop contract below yourself; the `aidd/gate` check decides what merges."
)

# Every Claude Code phrase of a role agent that names what only Claude Code has, by the `Voice` field that replaces it.
AGENT = {
    "rulebook": "The aidd skill (`aidd:aidd`; load it with `Skill` for a rule not here) is the rulebook.",
    "rulebook_preloaded": "The aidd skill, preloaded, is the rulebook.",
    "mcp": "Prefer the `aidd` MCP tools.",
    "read_only": "You write no file; the hook denies a shell write too.",
    "refusal": "or a hook deny.",
    "edit": "with one Edit (Write only a new or mostly rewritten file)",
    "helpers": "split large, independent work across subagents of your own `aidd-<role>` type, or helpers, which only read. Give each the practice skill for its work.",
}

# aidd wires its MCP server only for Claude Code (`config.harnesses`), so elsewhere the tools are there only if a person added them.
MCP = "Prefer the `aidd` MCP tools when this agent has them, else the `aidd` command."
REFUSAL = "or a refused tool call."
EDIT = "with one targeted edit (rewrite a whole file only when it is new or mostly rewritten)"
READ_SKILL = "The aidd skill (`.agents/skills/aidd/SKILL.md`; read it for a rule not here) is the rulebook."


@dataclasses.dataclass(frozen=True)
class Voice:
    """How one harness's role files word what Claude Code's word with its own tools and hook."""

    skills: str  # how this harness finds a skill, after the advisory
    rulebook: str = READ_SKILL
    read_only: str = "You write no file, not even through the shell."
    refusal: str = REFUSAL
    edit: str = EDIT
    helpers: str | None = None  # None keeps Claude Code's sentence: the role can start a subagent here too
    advisory: str = ADVISORY

    def swaps(self) -> list[tuple[str, str]]:
        """(Claude Code text, this harness's text) for each phrase in `AGENT`."""
        new = {"rulebook": self.rulebook, "rulebook_preloaded": self.rulebook, "mcp": MCP, "read_only": self.read_only}
        new |= {"refusal": self.refusal, "edit": self.edit, "helpers": self.helpers or AGENT["helpers"]}
        return [(AGENT[k], new[k]) for k in AGENT]


VOICES: dict[str, Voice] = {
    # https://learn.chatgpt.com/docs/build-skills: Codex scans `.agents/skills` from the working directory up to the
    # repository root, and selects a skill "when your task aligns with the skill's description field".
    # https://learn.chatgpt.com/docs/agent-configuration/subagents: a custom agent may set `sandbox_mode`, and local
    # Codex "spawn[s] agents after a direct request or applicable project or skill instruction".
    # https://learn.chatgpt.com/docs/sandboxing: in read-only, the agent "can't edit files or run commands without approval".
    "codex": Voice(
        skills=(
            "Codex looks for skills only in `.agents/skills/`, so read an `aidd-<name>` practice skill or domain pack "
            "yourself, from `.claude/skills/aidd-<name>/SKILL.md` when the team is installed there."
        ),
        read_only=(
            "You write no file, not even through the shell: this file runs you in Codex's read-only sandbox, where an "
            "edit or a command needs a person's approval."
        ),
        # The guard in `.codex/hooks.json` sees every tool call, but Codex's event names no subagent (SECURITY.md).
        advisory=(
            "In Codex, aidd's guard hook (`.codex/hooks.json`, when `aidd init` wired it) checks each write against the "
            "Spec's scope, the frozen tests, and the protected paths, and denies an approval or a merge. It cannot tell "
            "which role made a call, so follow your write area and the loop contract below yourself; the `aidd/gate` "
            "check decides what merges."
        ),
    ),
    # https://docs.github.com/en/copilot/concepts/agents/about-agent-skills: project skills live in `.github/skills`,
    # `.claude/skills`, or `.agents/skills`, and Copilot "can load [them] when relevant".
    # https://docs.github.com/en/copilot/reference/custom-agents-configuration: `tools`, "If unset, defaults to all
    # tools" (aidd sets none, so nothing here enforces a read-only role), and the `agent` tool invokes another custom agent.
    "copilot": Voice(
        skills=(
            "Copilot loads a skill from `.agents/skills/` or `.claude/skills/` when it is relevant to the task; read a "
            "skill's `SKILL.md` yourself when you need it now."
        ),
    ),
    # Antigravity's customization guide (shipped in `agy` 1.3): a Markdown agent in `.agents/agents/` lists its `tools`,
    # skills load from `.agents/skills/` and the directories `.agents/skills.json` names (init names `.claude/skills/`),
    # and only a skill's name and description sit in the context until the agent activates it. The guard hook in
    # `.agents/hooks.json` sees every tool call, but its event names the conversation, never the role.
    "antigravity": Voice(
        skills=(
            "Antigravity lists the workspace's skills, the `aidd-<name>` practice skills and domain packs among them "
            "when `.agents/skills.json` names `.claude/skills/`; activate one when its description fits your task, or "
            "read its `SKILL.md` yourself."
        ),
        read_only=(
            "You write no file, not even through the shell. This file gives you no `write` tool (no `write_file`, "
            "`edit_file`, `write_to_file`, or `replace_file_content`), but `shell` can still write through "
            "`run_command`, so don't."
        ),
        edit="with one `edit_file` or `replace_file_content` (`write_file` or `write_to_file` only for a new or mostly rewritten file)",
        advisory=(
            "In Antigravity, aidd's guard hook (`.agents/hooks.json`, when `aidd init` wired it) checks each write "
            "against the Spec's scope, the frozen tests, and the protected paths, and denies an approval or a merge. "
            "It cannot tell which role made a call, so follow your write area and the loop contract below yourself; "
            "the `aidd/gate` check decides what merges."
        ),
    ),
    # Grok Build reads `.grok/agents/*.md` (one `tools:` line) and loads skills from `.grok/skills/` and `.agents/skills/`.
    # The guard hook in `.grok/hooks/aidd.json` reads `subagentType` once the person trusts the folder. No role file lists
    # `spawn_subagent`: Grok's subagent depth is 1, so the lead starts every role.
    "grok-build": Voice(
        skills=(
            "Grok Build loads a skill from `.grok/skills/` or `.agents/skills/` when its description fits the task; read "
            "its `SKILL.md` yourself when you need it now. The `aidd-<name>` practice skills and domain packs are in "
            "`.claude/skills/aidd-<name>/` when the team is installed there."
        ),
        read_only=(
            "You write no file, not even through the shell. This file gives you no `write` tool (no `search_replace` or "
            "`write`), but `shell` can still write through `run_terminal_command`, so don't."
        ),
        edit="with one `search_replace` (`write` only a new or mostly rewritten file)",
        helpers="split large, independent work into parts and take them one at a time, since this file gives you no tool that starts a subagent.",
        advisory=(
            "Grok Build runs aidd's guard (`.grok/hooks/aidd.json`, when init wired it, and after the folder is trusted). "
            "It reads this role from `subagentType` and refuses a write outside the write area, and an approval or a merge. "
            "The lead starts every other role; this file gives no tool that starts a subagent."
        ),
    ),
    # https://kiro.dev/docs/custom-agents/configuration-reference/: `tools` is "the tools available to the agent"
    # (`read`, `write`, `shell`), and an agent reaches a skill through a `skill://` entry in its `resources`. aidd's
    # agent file lists no resources and no tool that starts another agent.
    "kiro": Voice(
        skills=(
            "This agent file attaches no skill, so read the `SKILL.md` of each one you need: an `aidd-<name>` practice "
            "skill or domain pack is in `.claude/skills/aidd-<name>/` when the team is installed there."
        ),
        # The file grants `shell` to a role that reads with one (git diff, the tests), and `shell` can write, so the
        # text claims only the missing `write` tool and leaves the shell to the role.
        read_only="You write no file, not even through the shell. This file gives you no `write` tool, but `shell` can still write, so don't.",
        helpers="split large, independent work into parts and take them one at a time, since this file gives you no tool that starts a subagent.",
    ),
    # https://opencode.ai/v2/docs/skills: OpenCode finds skills in `.opencode/skills/`, `.claude/skills/`, and
    # `.agents/skills/`, and an agent loads one with the `skill` tool. https://opencode.ai/v2/docs/agents: the agent's
    # `permissions:` rules are enforced on its edits and shell commands. aidd's guard plugin reads the role from the agent
    # name (`aidd-<role>`), so it holds the write area too (guard/dialects.OpenCode).
    "opencode": Voice(
        skills="Load a skill, the aidd skill or an `aidd-<name>` practice skill or domain pack, with the `skill` tool.",
        rulebook="The aidd skill (`aidd`; load it with the `skill` tool for a rule not here) is the rulebook.",
        refusal="or a denied permission.",
        edit="with one `edit` (`write` only a new or mostly rewritten file)",
        advisory=(
            "In OpenCode V2, aidd's guard plugin (`.opencode/plugins/aidd.js`, when `aidd init` wired it) checks each "
            "write against the Spec's scope, the frozen tests, the protected paths, and this role's write area, and "
            "denies an approval or a merge. The `permissions` rules above also hold this role's edits and shell "
            "commands. Follow the loop contract below; the `aidd/gate` check decides what merges."
        ),
    ),
}


def agent(harness: str, body: str) -> str:
    """A role agent's prompt for `harness`: its advisory, how it finds skills, and the body with each swap of its voice.
    Codex runs a flow as `$aidd-<flow>`, so its role files name each flow that way."""
    voice = VOICES[harness]
    for old, new in voice.swaps():
        body = body.replace(old, new)
    body = _SLASH_FLOW.sub("$aidd-", body) if harness == "codex" else body
    return f"{voice.advisory} {voice.skills}\n\n{body}"


# A flow named as `/aidd-<flow>` in a file both Codex and Antigravity read (the shared flows, the roles reference), where
# Codex runs it as `$aidd-<flow>`.
_NAMED_FLOW = re.compile(r"`/aidd-([a-z][a-z-]*)`")


def both_flow_names(text: str) -> str:
    """`text` with each `/aidd-<flow>` also named the way Codex runs it: "`/aidd-fix` (`$aidd-fix` in Codex)"."""
    return _NAMED_FLOW.sub(lambda m: f"`/aidd-{m.group(1)}` (`$aidd-{m.group(1)}` in Codex)", text)


# The installed roles reference (`team_install.TEAM_ROLES_REF`), which every harness reads, names Claude Code's `Skill`
# tool; elsewhere a role loads a practice skill the way its own file says.
SHARED = [
    ("the practice skills it loads with `Skill` (two per Task at most)", "the practice skills it loads (two per Task at most)"),
    ("(`Skill`, two per Task at most)", "(two per Task at most)"),
]


def shared(text: str) -> str:
    """A file every harness reads, with `SHARED`'s swaps."""
    for old, new in SHARED:
        text = text.replace(old, new)
    return text


# OpenCode's flow commands. The lead's rules (`schemas/roles.json`, `loop.lead`) that name Claude Code's tools, as OpenCode words them.
LEAD = {
    "Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (MODELS). "
    "Read-only search helpers (Explore) take the execution tier's model.": (
        "Launch each role with the `subagent` tool. Its agent file names its model, so pass none. For read-only search, launch the `explore` subagent."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `edit` (`write` only a new or mostly rewritten file)",
    "--session ${CLAUDE_SESSION_ID}": "--session ${AIDD_SESSION_ID}",
}

# Every harness but Claude Code gets the action's `file`, the flow's own file there (`aidd autopilot next --harness`).
READ_FILE = "Read the command's file: the action's `file`, else `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`. Never search for it."


def read_file(path: str) -> tuple[str, str]:
    return READ_FILE, f"Read the command's file: the action's `file`, which is `{path}`. Never search for it."


SESSION = (
    "aidd's plugin (`.opencode/plugins/aidd.js`) puts this session's id in place of `${AIDD_SESSION_ID}` in a shell "
    "command, so the lease binds to this session, and the guard denies a start or stop for any other session. Under "
    "`agents.delegate: auto`, the guard then denies your own edits of repository content: hand each one to the role that "
    "owns it. If the start says `--session` expected one argument, the plugin is not installed: run `aidd autopilot start --work "
    "<work>` instead, and pass the id it prints on its `session:` line as `--session` to every later autopilot command. "
    "A guard denial of the start is not that case: it is a stop."
)

# Per command file: (Claude Code text, OpenCode text). Every pair must match its file once. aidd's plugin guards each
# role's write area in OpenCode, so the guard's sentences in mvp.md and specify.md stay.
COMMANDS: dict[str, list[tuple[str, str]]] = {
    "autopilot.md": [
        ("Run `aidd autopilot start --work <work> --session ${CLAUDE_SESSION_ID}`.", "Run `aidd autopilot start --work <work> --session ${AIDD_SESSION_ID}`."),
        (
            "The session id binds the lease to this session, and the guard denies a start or stop for any other session. "
            "Under `agents.delegate: auto`, the guard then denies your own edits of repository content and names the "
            "role to hand each one to.",
            SESSION,
        ),
        ("--session ${CLAUDE_SESSION_ID}", "--session ${AIDD_SESSION_ID}"),
        read_file(".opencode/commands/aidd-<flow>.md"),
        ("--harness claude-code", "--harness opencode"),
        ("at a step boundary with Esc, or by telling you to stop", "at a step boundary by telling you to stop"),
        ("After a long run, a new session or `/clear` keeps the context small.", "After a long run, a new session keeps the context small."),
        (
            " Before a compaction, the aidd hook saves the state of the work there too, and reads it back after. To wait "
            "for a person, Claude Code can poll the inbox slowly, such as `/loop 30m aidd list --waiting-on-me`.",
            " To see what waits for a person, run `aidd list --waiting-on-me`.",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "create each worktree with `git worktree add`, then launch one subagent per step, all in one message, each told to work only in its worktree.",
        ),
    ],
    "fix.md": [("skill with the Skill tool before your first edit", "skill before your first edit")],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Give each Task its own git worktree on its own branch (`git worktree add`), then launch one subagent per Task, "
            "all in one message, each told to work only in its worktree.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Create each worktree on its own branch (`git worktree add`), then launch one subagent per slice, all in one "
            "message, each told to work only in its worktree.",
        ),
    ],
    "propose.md": [("Tell the subagent to load that skill with `Skill`.", "Tell the subagent to load that skill.")],
    "specify.md": [("skill with the Skill tool before your first edit", "skill before your first edit")],
    "rework.md": [("skill with the Skill tool before your first edit", "skill before your first edit")],
}

_LEAD_BLOCK = re.compile(r"<!-- aidd:gen roles:lead -->\n.*?<!-- aidd:end -->\n", re.S)

# Antigravity's flow commands, written as skills (`harness_files.FLOW_FILES`). The lead starts each role with the
# `invoke_subagent` tool, and a subagent's `share` workspace is its own worktree of the repository (the tool's schema,
# in `agy` 1.3). aidd's hooks in `.agents/hooks.json` run there, so the guard's sentences stay, except the ones on
# role write areas (mvp.md, specify.md): Antigravity's hook event names the conversation, never the role.
ANTIGRAVITY_LEAD = {
    "Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (MODELS). "
    "Read-only search helpers (Explore) take the execution tier's model.": (
        "Launch each role with the `invoke_subagent` tool, naming its agent, such as `aidd-developer`. Its agent file "
        "names its tools, so pass no model unless the person asks for one."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh conversation.",
    "--play --session ${CLAUDE_SESSION_ID}`": "--play --session <session>`, with the id aidd's session note names,",
    "with one Edit (Write only a new or mostly rewritten file)": (
        "with one `edit_file` or `replace_file_content` (`write_file` or `write_to_file` only for a new or mostly rewritten file)"
    ),
}

ANTIGRAVITY_SESSION = (
    "The session is this conversation's id, which aidd's session note names at the start. Without that note, aidd's "
    "hooks are not wired here: start with no `--session`, and pass the id the `session:` line prints instead. "
)


ANTIGRAVITY_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        ("--session ${CLAUDE_SESSION_ID}", "--session <session>"),
        ("The session id binds the lease to this session,", ANTIGRAVITY_SESSION + "The session id binds the lease to this session,"),
        read_file(".agents/skills/aidd-<flow>/SKILL.md"),
        ("--harness claude-code", "--harness antigravity"),
        ("After a long run, a new session or `/clear` keeps the context small.", "After a long run, a new conversation keeps the context small."),
        (
            " Before a compaction, the aidd hook saves the state of the work there too, and reads it back after. To wait "
            "for a person, Claude Code can poll the inbox slowly, such as `/loop 30m aidd list --waiting-on-me`.",
            " To see what waits for a person, run `aidd list --waiting-on-me`.",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "launch one subagent per step in a single `invoke_subagent` call, each in the `share` workspace mode.",
        ),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Launch one subagent per Task in a single `invoke_subagent` call, each in the `share` workspace mode. Each "
            "Task then builds in its own git worktree, on its own branch.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Launch one subagent per slice in a single `invoke_subagent` call, each in the `share` workspace mode.",
        ),
        ("so the guard keeps those paths closed to them, and the SRE", "so the SRE"),
    ],
    "specify.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        ("The guard then lets only that role write the Task's scope.", "Only that role then writes the Task's scope."),
    ],
}


# Grok Build's flow commands, written as skills. The lead starts each role with `spawn_subagent` and passes no model.
# A Task worktree is `git worktree add` (Grok has no `isolation:` flag). The guard in `.grok/hooks/aidd.json` reads
# `subagentType`, so the guard's sentences stay, except "the guard keeps", which no harness may say.
GROK_LEAD = {
    "Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (MODELS). "
    "Read-only search helpers (Explore) take the execution tier's model.": (
        "Start each role with `spawn_subagent` and `subagent_type` `aidd-<role>`. Pass no model. Give a Task its own worktree with `git worktree add`."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "--play --session ${CLAUDE_SESSION_ID}`": "--play --session <session>`, with the id aidd's session note names,",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `search_replace` (`write` only a new or mostly rewritten file)",
}

# Grok Build gives a command no variable for its session, but its SessionStart hook's `systemMessage` reaches the agent,
# so aidd's session note names the id there (guard.session_hooks.session_note), as in Antigravity and Codex.
GROK_SESSION = (
    "The session is this session's id, which aidd's session note names at the start. Without that note, aidd's hooks "
    "are not wired here: start with no `--session`, and pass the id the `session:` line prints instead. "
)

GROK_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        ("--session ${CLAUDE_SESSION_ID}", "--session <session>"),
        ("The session id binds the lease to this session,", GROK_SESSION + "The session id binds the lease to this session,"),
        read_file(".grok/skills/aidd-<flow>/SKILL.md"),
        ("--harness claude-code", "--harness grok-build"),
        ("After a long run, a new session or `/clear` keeps the context small.", "After a long run, a new session keeps the context small."),
        (
            " Before a compaction, the aidd hook saves the state of the work there too, and reads it back after. To wait "
            "for a person, Claude Code can poll the inbox slowly, such as `/loop 30m aidd list --waiting-on-me`.",
            " To see what waits for a person, run `aidd list --waiting-on-me`.",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "create each worktree with `git worktree add`, then launch one spawn_subagent per step, all in one message, each told to work only in its worktree.",
        ),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Give each Task its own git worktree on its own branch (`git worktree add`), then launch one spawn_subagent per Task, "
            "all in one message, each told to work only in its worktree.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Give each slice its own git worktree on its own branch (`git worktree add`), then launch one spawn_subagent per slice, "
            "all in one message, each told to work only in its worktree.",
        ),
        ("so the guard keeps those paths closed to them, and the SRE", "so the SRE"),
    ],
}

# Codex's flow commands, written as skills in `.agents/skills/`, the one project folder Codex reads skills from
# (codex 0.156); a person runs one as `$aidd-<flow>`. The lead spawns each role as its custom agent
# (`.codex/agents/aidd-<role>.toml`), and a Task worktree is `git worktree add`. Codex's hook event names no subagent, so
# the sentences on role write areas go, as in Antigravity. Codex has no session variable; aidd's session note names it.
_SPAWN = "Start each role as its custom agent, such as `aidd-developer`: ask Codex to spawn it by name. Its agent file names its model, so pass none."
CODEX_LEAD = {
    "Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (MODELS). "
    "Read-only search helpers (Explore) take the execution tier's model.": _SPAWN,
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session (`/new`).",
    "--play --session ${CLAUDE_SESSION_ID}`": "--play --session <session>`, with the id aidd's session note names,",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `apply_patch` (rewrite a whole file only when it is new or mostly rewritten)",
}

_WORKTREES = "Give each {0} its own git worktree on its own branch (`git worktree add`), then spawn one subagent per {0}, all at once, each told to work only in its worktree."

CODEX_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        ("--session ${CLAUDE_SESSION_ID}", "--session <session>"),
        ("The session id binds the lease to this session,", ANTIGRAVITY_SESSION + "The session id binds the lease to this session,"),
        read_file(".agents/skills/aidd-<flow>/SKILL.md"),
        ("--harness claude-code", "--harness codex"),
        ("After a long run, a new session or `/clear` keeps the context small.", "After a long run, a new session (`/new`) keeps the context small."),
        (
            " Before a compaction, the aidd hook saves the state of the work there too, and reads it back after. To wait "
            "for a person, Claude Code can poll the inbox slowly, such as `/loop 30m aidd list --waiting-on-me`.",
            " To see what waits for a person, run `aidd list --waiting-on-me`.",
        ),
        ('one Agent call per step with `isolation: "worktree"`, all in one message.', _WORKTREES.format("step")),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            _WORKTREES.format("Task"),
        ),
    ],
    "mvp.md": [
        ('Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.', _WORKTREES.format("slice")),
        ("so the guard keeps those paths closed to them, and the SRE", "so the SRE"),
    ],
    "specify.md": ANTIGRAVITY_COMMANDS["specify.md"],
}

# Codex and Antigravity both read `.agents/skills/`, so where both are wired, one flow file serves both: Codex's
# commands, which name no tool only one of them has, and a lead that names how each starts a role.
SHARED_SKILLS_LEAD = {
    **CODEX_LEAD,
    "Pass the `model` in every Agent call: the one the role's agent file names, which follows its tier (MODELS). "
    "Read-only search helpers (Explore) take the execution tier's model.": (
        "Start each role as its own agent, such as `aidd-developer`: with the `invoke_subagent` tool in Antigravity, or by "
        "asking Codex to spawn it by name. Its agent file names its model, so pass none."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "with one Edit (Write only a new or mostly rewritten file)": EDIT,
}

# Where Codex and Antigravity share one flow file, the lead names its own harness to `next`.
SHARED_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **CODEX_COMMANDS,
    "autopilot.md": [
        (old, new.replace("--harness codex", "--harness <harness>"))
        if old != "The session id binds the lease to this session,"
        else (old, ANTIGRAVITY_SESSION + "The harness is `codex` in Codex and `antigravity` in Antigravity. " + old)
        for old, new in CODEX_COMMANDS["autopilot.md"]
    ],
}

_LEAD = {"antigravity": ANTIGRAVITY_LEAD, "grok-build": GROK_LEAD, "codex": CODEX_LEAD, "agents-skills": SHARED_SKILLS_LEAD}
_COMMANDS = {"antigravity": ANTIGRAVITY_COMMANDS, "grok-build": GROK_COMMANDS, "codex": CODEX_COMMANDS, "agents-skills": SHARED_COMMANDS}
# Codex runs a flow skill as `$aidd-<flow>` (harness_files._codex_skill), so its text names each flow that way. A path
# such as `.opencode/commands/aidd-<flow>.md` keeps its slash: a word or a dot comes before it.
_SLASH_FLOW = re.compile(r"(?<![\w./-])/aidd-(?=[a-z<])")


def lead_block(harness: str = "opencode") -> str:
    """The lead's rules for one harness: `roles:lead` with the rules that name Claude Code's tools reworded."""
    swaps = _LEAD.get(harness, LEAD)
    rules = []
    for i, rule in enumerate(knowledge.roles()["loop"]["lead"], 1):
        for old, new in swaps.items():
            rule = rule.replace(old, new)
        rules.append(f"{i}. {rule}")
    return "**You are the lead.** You run this command and the roles do its work:\n\n" + "\n".join(rules) + "\n"


def command(name: str, body: str, harness: str = "opencode") -> str:
    """The body of command `name` (such as `implement.md`) for one harness: its own lead block, and each swap."""
    body = _LEAD_BLOCK.sub(lambda _: lead_block(harness), body)
    table = _COMMANDS.get(harness, COMMANDS)
    for old, new in table.get(name, []):
        body = body.replace(old, new)
    if harness == "codex":
        return _SLASH_FLOW.sub("$aidd-", body)
    return both_flow_names(body) if harness == "agents-skills" else body
