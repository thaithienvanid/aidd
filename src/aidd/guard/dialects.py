"""How each coding agent speaks the hook protocol: the event it sends aidd's hooks, and the answer it reads back.

The guard (`pre_tool`) and the session hooks (`session_hooks`) decide in one vocabulary, Claude Code's: an event with
`tool_name`, `tool_input`, `cwd`, and `session_id`, and a decision of allow or deny. A `Dialect` translates for one
harness: `normalize` turns its event into that vocabulary, and the other methods write each answer in its format.
`of(event)` picks the dialect that claims an event, else Claude Code's.

To give another harness aidd's hooks: write a Dialect here from the harness's hook documentation, add it to DIALECTS,
and wire its hook file in `aidd.setup` (as `antigravity_wiring`, `grok_wiring`, `codex_wiring`, and `opencode_wiring` do).
Nothing in the checks themselves changes.
"""

from __future__ import annotations

import json
import shlex

# A patch in Codex's format (`*** Begin Patch`), which the guard reads as an edit of each file it names.
APPLY_PATCH = "apply_patch"

# Antigravity's file tools that write: each names its file in `TargetFile` (https://antigravity.google/docs/hooks).
_ANTIGRAVITY_WRITES = ("write_to_file", "replace_file_content", "multi_replace_file_content")
# Grok Build's hook events (https://docs.x.ai, Grok Build hooks): camelCase `hookEventName` values, lowercase.
_GROK_EVENTS = frozenset({"pre_tool_use", "session_start", "user_prompt_submit", "stop", "subagent_stop", "pre_compact"})
# The Grok tools the guard already knows how to check, under Claude Code's names. A read stays unnamed.
# `hashline_edit` is the other file-edit tool; `Shell` and `StrReplace` are the Cursor preset's (`agent_type = "cursor"`).
_GROK_TOOLS = {
    "run_terminal_command": "Bash",
    "Shell": "Bash",
    "search_replace": "Edit",
    "hashline_edit": "Edit",
    "StrReplace": "Edit",
    "write": "Write",
}


class Dialect:
    """Claude Code's hooks (https://code.claude.com/docs/en/hooks), the default. Every method is one answer's format."""

    key = "claude-code"
    adds_tool_context = True  # PreToolUse may add context for the agent with no decision
    names_its_session = True  # the harness gives a command a variable for the session (${CLAUDE_SESSION_ID})

    def claims(self, event: object) -> bool:
        return True

    def normalize(self, event: dict) -> dict:
        """The event in the guard's fields: `tool_name`, `tool_input`, `cwd`, `session_id`."""
        return event

    def decision(self, decision: str, reason: str) -> dict:
        """A PreToolUse deny (or another decision), with its reason."""
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": f"aidd: {reason}"}}

    def no_opinion(self) -> dict | None:
        """A PreToolUse allow: None writes nothing, and the harness's own permission settings decide."""
        return None

    def context(self, hook: str, text: str) -> dict:
        """Context for the agent from a session hook (`SessionStart`, `UserPromptSubmit`)."""
        return {"hookSpecificOutput": {"hookEventName": hook, "additionalContext": text}}

    def idle(self) -> dict | None:
        """A session hook with nothing to add: None writes nothing."""
        return None

    def prompt_hint_due(self, event: dict) -> bool:
        """Whether this prompt-hook event is one the next-step line goes with."""
        return True

    def stop_held(self, event: dict) -> bool:
        """A stop the hook leaves alone: a stop hook already continued the agent."""
        return event.get("stop_hook_active") is True

    def stop(self, event: dict, reminder: str, strict: bool) -> dict:
        """The stop reminder: a block at level strict, else context the agent reads."""
        if strict:
            return {"decision": "block", "reason": reminder}
        return self.context("SubagentStop" if event.get("hook_event_name") == "SubagentStop" else "Stop", reminder)


class Antigravity(Dialect):
    """Google Antigravity's hooks (https://antigravity.google/docs/hooks; `agy` 1.3 ships a copy). Every hook reads a
    JSON object back; the counters (`invocationNum`, `executionNum`) start at 0, as a live `agy` session sends them."""

    key = "antigravity"
    adds_tool_context = False  # PreToolUse answers a decision, a reason, permission grants, or argument overwrites
    names_its_session = False  # no variable names the conversation, so the session note does

    def claims(self, event: object) -> bool:
        return isinstance(event, dict) and (isinstance(event.get("toolCall"), dict) or "conversationId" in event or "workspacePaths" in event)

    def normalize(self, event: dict) -> dict:
        """The tool told apart by its arguments, since Antigravity names a tool from its step type: a shell command
        (`CommandLine`, run in `Cwd`), a file write (`TargetFile`), or an MCP call (`ServerName`, `ToolName`,
        `Arguments`). Any other tool, such as a read, reaches no check. The session is the conversation
        (`conversationId`), and the working directory the first workspace path, since the hook runs in `.agents/`."""
        call: dict = event["toolCall"] if isinstance(event.get("toolCall"), dict) else {}
        args: dict = call["args"] if isinstance(call.get("args"), dict) else {}
        name = str(call.get("name") or "")
        paths = event.get("workspacePaths")
        workspace = paths[0] if isinstance(paths, list) and paths and isinstance(paths[0], str) else None
        cwd = args["Cwd"] if isinstance(args.get("Cwd"), str) and args["Cwd"] else workspace
        tool_name, tool_input = name, {}
        if isinstance(args.get("CommandLine"), str):
            tool_name, tool_input = "Bash", {"command": args["CommandLine"]}
        elif name in _ANTIGRAVITY_WRITES or isinstance(args.get("TargetFile"), str):
            tool_name, tool_input = "Edit", {"file_path": str(args.get("TargetFile") or "")}
        elif isinstance(args.get("ServerName"), str) and isinstance(args.get("ToolName"), str):
            arguments = args.get("Arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            tool_name, tool_input = f"mcp__{args['ServerName']}__{args['ToolName']}", arguments if isinstance(arguments, dict) else {}
        session = event.get("conversationId")
        out = {**event, "session_id": session if isinstance(session, str) else ""}
        if cwd:
            out["cwd"] = cwd
        return out | ({"tool_name": tool_name, "tool_input": tool_input} if call else {})

    def decision(self, decision: str, reason: str) -> dict:
        return {"decision": decision, "reason": f"aidd: {reason}"}

    def no_opinion(self) -> dict | None:
        # An empty decision leaves the call to the person's permission settings; "allow" would approve it for them.
        return {"decision": ""}

    def context(self, hook: str, text: str) -> dict:
        # A system message stays in the conversation; the prompt's line is ephemeral, dropped after the turn.
        return {"injectSteps": [{"ephemeralMessage": text} if hook == "UserPromptSubmit" else {"systemMessage": {"systemMessage": text}}]}

    def idle(self) -> dict | None:
        return {}

    def prompt_hint_due(self, event: dict) -> bool:
        # PreInvocation runs before each model call; the line goes before a turn's first.
        return event.get("invocationNum") in (None, 0)

    def stop_held(self, event: dict) -> bool:
        # Not a finished turn (an error, a cancel, a limit), or an execution after the first, which a continue may have started.
        n = event.get("executionNum")
        return event.get("terminationReason") not in (None, "NO_TOOL_CALL") or (isinstance(n, int) and n > 0)

    def stop(self, event: dict, reminder: str, strict: bool) -> dict:
        # No reminder exists at a stop: both levels continue the agent once, with the reminder as a system message.
        return {"decision": "continue", "reason": reminder}


def _grok_mcp_name(name: str) -> str | None:
    """`aidd__gate` and `mcp__aidd__gate` as the guard's `mcp__<server>__<tool>`. A name with no `__` is not one."""
    if name.startswith("mcp__") and name.count("__") >= 2:
        return name
    if name.count("__") == 1:
        return "mcp__" + name
    return None


def _grok_tool(name: str, tool_input: dict) -> tuple[str, dict] | None:
    """A Grok tool call in the guard's names, or None when this call reaches no check (a read)."""
    if name in _GROK_TOOLS:
        return _GROK_TOOLS[name], tool_input
    if name == "use_tool":
        inner = tool_input.get("tool_name")
        if isinstance(inner, str) and (mapped := _grok_mcp_name(inner)):
            args = tool_input.get("tool_input")
            return mapped, args if isinstance(args, dict) else {}
        return None
    mapped = _grok_mcp_name(name)
    return (mapped, tool_input) if mapped else None


class Grok(Dialect):
    """Grok Build's hooks (its hooks guide; grok 1.0.60 ships a copy). The event uses `hookEventName`, `toolName`,
    `toolInput`, `sessionId`, `workspaceRoot`, and `subagentType`, and a Stop says `stopHookActive`. SessionStart reads
    only a top-level `systemMessage`; Stop reads Claude Code's reply. An allow writes nothing, so the person's
    permission settings decide; Grok's `allow` would only mean "not blocked", never an approval."""

    key = "grok-build"
    names_its_session = False  # no variable names the session, so a command prints the id it made

    def claims(self, event: object) -> bool:
        if not isinstance(event, dict):
            return False
        # Antigravity's markers win when both are present; Grok uses `workspaceRoot`, never `workspacePaths`.
        if isinstance(event.get("toolCall"), dict) or "conversationId" in event or "workspacePaths" in event:
            return False
        kind = event.get("hookEventName")
        if isinstance(kind, str) and kind in _GROK_EVENTS:
            return True
        tool = event.get("toolName")
        if isinstance(tool, str) and (tool in _GROK_TOOLS or tool == "use_tool" or _grok_mcp_name(tool)):
            return True
        return "subagentType" in event or "subagent_type" in event

    def normalize(self, event: dict) -> dict:
        """Map Grok's names onto the guard's: `subagentType` to `agent_type`, `sessionId` to `session_id`,
        `workspaceRoot` to `cwd` when the event has none, and a shell, an edit, or an MCP call onto its check."""
        out = dict(event)
        if "session_id" not in out and isinstance(out.get("sessionId"), str):
            out["session_id"] = out["sessionId"]
        if not out.get("cwd") and isinstance(out.get("workspaceRoot"), str):
            out["cwd"] = out["workspaceRoot"]
        agent = out.get("subagentType") if isinstance(out.get("subagentType"), str) else out.get("subagent_type")
        if isinstance(agent, str) and "agent_type" not in out:
            out["agent_type"] = agent
        raw_name = out.get("toolName") if isinstance(out.get("toolName"), str) else None
        if raw_name is None:
            return out
        tool_input = out.get("toolInput")
        raw_input = tool_input if isinstance(tool_input, dict) else {}
        mapped = _grok_tool(raw_name, raw_input)
        if mapped:
            out["tool_name"], out["tool_input"] = mapped
        return out

    def context(self, hook: str, text: str) -> dict:
        # SessionStart reads only a top-level systemMessage. UserPromptSubmit drops additionalContext; Stop still reads it.
        if hook == "SessionStart":
            return {"systemMessage": text}
        return super().context(hook, text)

    def prompt_hint_due(self, event: dict) -> bool:
        # Grok discards an allowing UserPromptSubmit hook's stdout, so the next-step line would reach nobody.
        return False

    def stop_held(self, event: dict) -> bool:
        # Grok says `stopHookActive` where Claude Code says `stop_hook_active`: a stop hook already continued the agent.
        return event.get("stopHookActive") is True or super().stop_held(event)


# The shells whose `-c` (or `-lc`) script a word list runs; any other program's `-c` is that program's own code.
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})


class Codex(Dialect):
    """Codex's hooks (https://learn.chatgpt.com/docs/hooks; codex 0.156 sends them): Claude Code's shape and answers,
    with a `turn_id` on every turn's event. A shell command is `Bash` with `tool_input.command`, and an edit is
    `apply_patch`, its patch in `tool_input.command`. No variable names the session for a command."""

    key = "codex"
    names_its_session = False

    def claims(self, event: object) -> bool:
        # A turn's events carry `turn_id`; a session's start does not, but its transcript lives under ~/.codex/.
        if not isinstance(event, dict) or not isinstance(event.get("hook_event_name"), str):
            return False
        transcript = event.get("transcript_path")
        return "turn_id" in event or (isinstance(transcript, str) and "/.codex/sessions/" in transcript.replace("\\", "/"))

    def normalize(self, event: dict) -> dict:
        """A shell command given as words (`["bash", "-lc", "..."]`) read as the script it runs."""
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            return event
        command = tool_input.get("command")
        if event.get("tool_name") == "Bash" and isinstance(command, list) and all(isinstance(w, str) for w in command):
            shell = len(command) == 3 and command[1] in ("-c", "-lc") and command[0].rsplit("/", 1)[-1] in _SHELLS
            script = command[2] if shell else shlex.join(command)
            return {**event, "tool_input": {**tool_input, "command": script}}
        return event


# OpenCode's built-in tools that only read, plan, or ask: they reach no check. Any other tool not mapped below is an
# MCP server's or a plugin's (`<server>_<tool>`), checked as an MCP tool.
_OPENCODE_READS = frozenset(
    {"read", "list", "glob", "grep", "codesearch", "webfetch", "websearch", "todoread", "todowrite", "question", "skill", "task", "subagent", "lsp"}
)
# OpenCode's subagents that are not aidd's roles: helpers, which may read and never write.
_OPENCODE_HELPERS = frozenset({"general", "explore"})


class OpenCode(Dialect):
    """OpenCode V2, through the plugin `aidd init` writes (`setup/opencode_wiring.py`): its `tool` `execute.before`
    hook sends `harness`, `tool`, `input`, `sessionID`, `agent`, and `cwd`, and throws on a deny, which the agent reads
    as the tool's error. An allow writes nothing; OpenCode's own permission rules decide."""

    key = "opencode"
    adds_tool_context = False
    names_its_session = False

    def claims(self, event: object) -> bool:
        return isinstance(event, dict) and event.get("harness") == "opencode"

    def normalize(self, event: dict) -> dict:
        """OpenCode's tool and agent in the guard's names: `bash` (or `shell`), `edit` and `write` (their `path`, or V1's
        `filePath`), `apply_patch` (or `patch`, its `patchText`), and any other tool as `mcp__opencode__<tool>`.
        An agent named `aidd-<role>` is that role, `general` and `explore` are helpers, and any other is the main session."""
        tool = str(event.get("tool") or "").lower()
        raw = event.get("input")
        args: dict = raw if isinstance(raw, dict) else {}
        out = {**event, "session_id": event["sessionID"] if isinstance(event.get("sessionID"), str) else ""}
        agent = event.get("agent")
        if isinstance(agent, str) and (agent.startswith("aidd-") or agent in _OPENCODE_HELPERS):
            out["agent_type"] = agent
        if tool in ("bash", "shell"):
            out["tool_name"], out["tool_input"] = "Bash", {"command": str(args.get("command") or "")}
        elif tool in ("edit", "write", "multiedit"):
            out["tool_name"], out["tool_input"] = "Edit", {"file_path": str(args.get("path") or args.get("filePath") or "")}
        elif tool in (APPLY_PATCH, "patch"):
            text = next((args[k] for k in ("patchText", "patch", "input") if isinstance(args.get(k), str) and args[k]), "")
            out["tool_name"], out["tool_input"] = APPLY_PATCH, {"command": text}
        elif tool and tool not in _OPENCODE_READS:
            out["tool_name"], out["tool_input"] = f"mcp__opencode__{tool}", args
        return out

    def decision(self, decision: str, reason: str) -> dict:
        return {"decision": decision, "reason": f"aidd: {reason}"}

    def context(self, hook: str, text: str) -> dict:
        return {"context": text}

    def prompt_hint_due(self, event: dict) -> bool:
        return False


CLAUDE_CODE = Dialect()
ANTIGRAVITY = Antigravity()
GROK = Grok()
CODEX = Codex()
OPENCODE = OpenCode()
DIALECTS: tuple[Dialect, ...] = (ANTIGRAVITY, GROK, OPENCODE, CODEX)  # tried in order; Claude Code's answers any other event


def of(event: object) -> Dialect:
    """The dialect of the harness that sent `event`."""
    return next((d for d in DIALECTS if d.claims(event)), CLAUDE_CODE)
