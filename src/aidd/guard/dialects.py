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
import os
import re
import shlex
from pathlib import Path

from aidd.kernel import git

# A patch in Codex's format (`*** Begin Patch`), which the guard reads as an edit of each file it names.
APPLY_PATCH = "apply_patch"

# Antigravity's file tools that write: each names its file in `TargetFile`, `Path`, or `NotebookPath` (https://antigravity.google/docs/hooks).
_ANTIGRAVITY_WRITES = ("write_to_file", "replace_file_content", "multi_replace_file_content", "write_file", "edit_file", "notebook_edit")
# Antigravity's built-in subagents that are not aidd's roles: helpers, which may read and never write.
_ANTIGRAVITY_HELPERS = frozenset({"research", "self", "image-generator"})
# Grok Build's hook events (https://docs.x.ai, Grok Build hooks): camelCase `hookEventName` values, lowercase.
_GROK_EVENTS = frozenset({"pre_tool_use", "session_start", "user_prompt_submit", "stop", "subagent_stop", "pre_compact"})
# The Grok tools the guard checks, under Claude Code's names, from grok 1.0.62's hooks and headless guides: the shell
# route's (`run_terminal_command`, shown for `run_terminal_cmd`; `hashline_edit` is the other file-edit tool) and the
# daemon route's, which the Cursor preset shows too (`Shell`, `StrReplace` and `Write` with `path`, `EditNotebook` with
# `target_notebook`, `Delete`). An MCP call reaches the hook as `<server>__<tool>`.
_GROK_TOOLS = {
    "run_terminal_command": "Bash",
    "run_terminal_cmd": "Bash",
    "bash": "Bash",
    "Shell": "Bash",
    "search_replace": "Edit",
    "hashline_edit": "Edit",
    "StrReplace": "Edit",
    "EditNotebook": "Edit",
    "Delete": "Edit",
    "write": "Write",
    "write_file": "Write",
    "Write": "Write",
}
# The Grok tools that only read, plan, ask, or wait on a task the guard already checked: they reach no check. Any
# other tool, a new one included, is denied in a repository that adopted aidd, since the guard cannot tell what it
# writes or runs (`unknown_tool`): an image or video generator, a workflow (`execute`, `workflow`), a monitor, or a
# new scheduled task. The names a live session used (read_file, grep, list_dir, web_search, web_fetch, todo_write,
# spawn_subagent, get_command_or_subagent_output, kill_command_or_subagent, search_tool, ask_user_question) are here.
_GROK_READS = frozenset(
    {
        "read_file", "hashline_read", "grep", "grep_search", "hashline_grep", "list_dir", "web_search", "web_fetch",
        "todo_write", "search_tool", "lsp", "task", "spawn_subagent", "get_task_output", "get_command_or_subagent_output",
        "wait_tasks", "wait_commands_or_subagents", "kill_task", "kill_command_or_subagent", "ask_user_question",
        "enter_plan_mode", "Read", "Grep", "Glob", "LS", "List", "WebSearch", "WebFetch", "Fetch", "TodoWrite", "Task",
        "Await", "AwaitShell", "AskQuestion", "SwitchMode", "CreatePlan", "ReadLints", "GetMcpTools", "ListMcpResources",
        "CreateGoal", "UpdateGoal", "XSearch", "grep_files", "memory_get", "memory_search", "skill", "exit_plan_mode",
        "send_subagent_message", "send_feedback", "scheduler_list", "scheduler_delete",
    }
)  # fmt: skip


def unknown_tool(name: str) -> str:
    """The deny reason for a harness tool the guard does not know, with what to do instead."""
    return (
        f"`{name}` is a tool the guard does not know, so it cannot tell what the call writes or runs: use the shell, "
        "edit, or write tool instead, or ask the person to run it"
    )


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

    def no_opinion(self, event: dict | None = None) -> dict | None:
        """A PreToolUse allow for the call in `event`: None writes nothing, and the harness's own permission settings
        decide."""
        return None

    def context(self, hook: str, text: str, shown: str = "") -> dict:
        """Context for the agent from a session hook (`SessionStart`, `UserPromptSubmit`), and `shown`, what the person
        reads directly: Claude Code shows a hook's top-level `systemMessage` to them, apart from the model's context."""
        return {"hookSpecificOutput": {"hookEventName": hook, "additionalContext": text}, **({"systemMessage": shown} if shown else {})}

    def idle(self) -> dict | None:
        """A session hook with nothing to add: None writes nothing."""
        return None

    # Whether the harness shows the model an allowing UserPromptSubmit hook's output; when not, the line that says aidd
    # recorded a typed decision waits for the next PreToolUse or Stop hook (pending_notes.py).
    shows_prompt_note = True

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
        tool_name, tool_input, opaque = name, {}, None
        if isinstance(args.get("CommandLine"), str):
            tool_name, tool_input = "Bash", {"command": args["CommandLine"]}
        elif not _antigravity_is_read(name, args) and (
            name in _ANTIGRAVITY_WRITES or any(isinstance(args.get(k), str) for k in ("TargetFile", "Path", "NotebookPath"))
        ):
            try:
                tool_name, tool_input = _antigravity_edit(name, args)
            except _Ambiguous:
                tool_name, tool_input, opaque = "Edit", args, AMBIGUOUS_CALL
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
        agent = next((event[k] for k in ("agentName", "subagentType", "agentType") if isinstance(event.get(k), str) and event[k]), "")
        parent = event.get("parentConversationId")
        if "agent_type" not in out and (agent.startswith("aidd-") or agent in _ANTIGRAVITY_HELPERS or (isinstance(parent, str) and parent)):
            out["agent_type"] = agent or "subagent"
        if cwd:
            out["cwd"] = cwd
        if opaque:
            out["opaque_tool"] = opaque
        if not call and "prompt" not in event and (typed := _antigravity_prompt(event)) is not None:
            out["prompt"] = typed
        return out | ({"tool_name": tool_name, "tool_input": tool_input} if call else {})

    def decision(self, decision: str, reason: str) -> dict:
        return {"decision": decision, "reason": f"aidd: {reason}"}

    def no_opinion(self, event: dict | None = None) -> dict | None:
        # agy 1.4.2 denies on an empty or missing decision (live: "tool call denied by pre-tool hook: "), so a call the
        # guard lets through is answered: a file read inside the workspace is allowed (reads never prompt), and any
        # other call, a tool aidd does not know included, is put to the person (`ask`), whose prompt remembers
        # "Always Allow". `allow` on a command or a write would approve it for them.
        return {"decision": "allow" if event is not None and _antigravity_workspace_read(event) else "ask"}

    def context(self, hook: str, text: str, shown: str = "") -> dict:
        # A system message stays in the conversation; the prompt's line is ephemeral, dropped after the turn. `shown` is
        # in `text` already: Antigravity has no field the person alone reads.
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


_USER_REQUEST = re.compile(r"\s*<USER_REQUEST>\n?(.*?)\n?</USER_REQUEST>", re.S)
# A coding agent's own record of the conversation, which aidd reads for the person's typed words where the harness's
# hook event does not carry them (Antigravity's transcript under `.system_generated/logs/`): the guard denies agents any
# write there or replacement of the brain folder (delegation), while artifacts (`brain/<id>/<name>.md`) stay writable.
HARNESS_RECORDS = re.compile(
    r"/\.gemini/antigravity[^/]*(?:/(?:brain/(?:[^/]+/)?\.system_generated/|brain/(?:[^/]+/)?$|(?:\.+/)*(?:.*/)?transcript(?:_full)?\.jsonl(?:/|$))|/?$)",
    re.I,
)
# How much of the transcript's end the prompt hook reads: the person's newest message, never the whole conversation.
_TRANSCRIPT_TAIL = 256 * 1024


def _antigravity_prompt(event: dict) -> str | None:
    """What the person typed, for a turn's first model call (PreInvocation, `invocationNum` 0): Antigravity's event
    carries no prompt, so the transcript it names says. Only its last step counts, and only when it is the person's
    own message (`USER_INPUT`, `USER_EXPLICIT`), the one step at the index Antigravity counts for this turn
    (`initialNumSteps` - 1), so a step written into the file by anything else never passes for it; the guard denies
    agents any write there (delegation.HARNESS_RECORDS). None when nothing says so, `initialNumSteps` included."""
    path, steps = event.get("transcriptPath"), event.get("initialNumSteps")
    if event.get("invocationNum") != 0 or not isinstance(path, str):
        return None
    real = os.path.realpath(path)
    if not all(
        p.endswith(("/.system_generated/logs/transcript.jsonl", "/.system_generated/logs/transcript_full.jsonl"))
        and HARNESS_RECORDS.search(p.replace("\\", "/"))
        for p in (path, real)
    ):
        return None  # only a transcript where the guard denies agents every write
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
        return None
    try:
        with open(real, "rb") as fh:
            fh.seek(0, 2)
            start = max(0, fh.tell() - _TRANSCRIPT_TAIL)
            fh.seek(start)
            lines = fh.read().decode("utf-8", errors="replace").splitlines()[1 if start else 0 :]  # a cut first line goes
        entries = [json.loads(line) for line in lines if line.strip()]
    except (OSError, ValueError):
        return None
    if not entries or not all(isinstance(e, dict) for e in entries):
        return None
    last = entries[-1]
    if (last.get("type"), last.get("source")) != ("USER_INPUT", "USER_EXPLICIT") or last.get("step_index") != steps - 1:
        return None
    if sum(e.get("step_index") == steps - 1 for e in entries) != 1:
        return None
    content = last.get("content")
    if not isinstance(content, str):
        return None
    # Antigravity frames the words typed with its own metadata: `<USER_REQUEST>...</USER_REQUEST>`, then the time and
    # settings blocks (agy 1.4.2, a live session).
    framed = _USER_REQUEST.match(content)
    return framed.group(1) if framed else content


# Antigravity's single-file reads (its step types), plus `notebook_edit`'s read actions (`list`, `get`,
# `get_with_outputs`). One of a file inside a workspace folder that git keeps needs nobody's yes; a listing or a search
# reaches a folder's every file, ignored ones included, so it is asked.
_ANTIGRAVITY_READS = frozenset(
    {"view_file", "read_file", "view_file_outline", "view_code_item", "view_content_chunk", "read_notebook"}
)  # fmt: skip
_ANTIGRAVITY_NOTEBOOK_READS = frozenset({"list", "get", "get_with_outputs"})


def _antigravity_is_read(name: str, args: dict) -> bool:
    return name in _ANTIGRAVITY_READS or (name == "notebook_edit" and args.get("Action") in _ANTIGRAVITY_NOTEBOOK_READS)


def _antigravity_workspace_read(event: dict) -> bool:
    """Whether the event is one of Antigravity's file reads that names a path, every one inside a workspace folder and
    none that git ignores (a `.env`, a key, a build folder): `allow` there widens nothing the person keeps closed."""
    raw = event.get("toolCall")
    call: dict = raw if isinstance(raw, dict) else {}
    raw_args = call.get("args")
    args: dict = raw_args if isinstance(raw_args, dict) else {}
    if not _antigravity_is_read(str(call.get("name") or ""), args):
        return False
    roots = [Path(p).resolve() for p in event.get("workspacePaths") or [] if isinstance(p, str) and p]
    paths = [v for k, v in args.items() if isinstance(v, str) and ("Path" in k or "File" in k or k in ("Directory", "Cwd"))]
    for value in paths:
        try:
            path = Path(value).resolve()
        except (OSError, ValueError):
            return False
        top = next((r for r in roots if path == r or path.is_relative_to(r)), None)
        # `-n -v` prints `::<tab><path>` for a path no rule ignores; an error prints nothing, and is asked (fail closed).
        if top is None or not git.run(["check-ignore", "-n", "-v", "--no-index", "--", str(path)], str(top), check=False).startswith("::\t"):
            return False
    return bool(roots and paths)


def _antigravity_edit(name: str, args: dict) -> tuple[str, dict]:
    """An Antigravity file write as the guard's Edit, MultiEdit, or Write, with the text it carries, so the rules on a
    person's decisions read the change: `write_to_file` (`CodeContent`) or `write_file` (`Content`, `Append`),
    `replace_file_content` (`TargetContent`, `ReplacementContent`) or `edit_file` (`Target`, `Replacement`), and
    `multi_replace_file_content` (`ReplacementChunks`). Without the text, an Edit that names only the file, which the
    decision rules deny on."""
    path = _one(args, ("TargetFile", "Path", "NotebookPath")) or ""
    if name in ("write_to_file", "write_file"):
        content = _one(args, ("CodeContent", "Content"))
        if content is None and any(isinstance(args.get(k), str) for k in ("CodeContent", "Content")):
            content = ""
        if content is not None:
            return "Write", {"file_path": path, "content": content, **({"append": True} if args.get("Append") is True else {})}
    target = _one(args, ("TargetContent", "Target"))
    replacement = _one(args, ("ReplacementContent", "Replacement"))
    if replacement is None and any(isinstance(args.get(k), str) for k in ("ReplacementContent", "Replacement")):
        replacement = ""
    if target is not None and replacement is not None:
        return "Edit", {
            "file_path": path,
            "old_string": target,
            "new_string": replacement,
            "replace_all": name == "edit_file" or args.get("AllowMultiple") is True,
        }
    if any(isinstance(args.get(k), str) and not args.get(k) for k in ("TargetContent", "Target")) and replacement is not None:
        # An empty target replaces the whole file: the guard reads it as the write it is.
        return "Write", {"file_path": path, "content": replacement}
    chunks = args.get("ReplacementChunks")
    if (
        isinstance(chunks, list)
        and chunks
        and all(isinstance(c, dict) and isinstance(c.get("TargetContent"), str) and isinstance(c.get("ReplacementContent"), str) for c in chunks)
    ):
        return "MultiEdit", {
            "file_path": path,
            "edits": [{"old_string": c["TargetContent"], "new_string": c["ReplacementContent"], "replace_all": c.get("AllowMultiple") is True} for c in chunks],
        }
    return "Edit", {"file_path": path}


def _opencode_edit(tool: str, args: dict) -> tuple[str, dict]:
    """An OpenCode file write as the guard's Edit, MultiEdit, or Write, with its text: `write` (`content`), `edit`
    (`oldString`, `newString`), and `multiedit` (`edits`). The path is `path`, or V1's `filePath`."""
    path = _one(args, ("path", "filePath")) or ""
    if tool == "write" and isinstance(args.get("content"), str):
        return "Write", {"file_path": path, "content": args["content"]}
    if isinstance(args.get("oldString"), str) and isinstance(args.get("newString"), str):
        if not args["oldString"]:  # OpenCode writes the whole file from an empty oldString: read it as that write
            return "Write", {"file_path": path, "content": args["newString"]}
        return "Edit", {"file_path": path, "old_string": args["oldString"], "new_string": args["newString"], "replace_all": args.get("replaceAll") is True}
    edits = args.get("edits")
    if (
        isinstance(edits, list)
        and edits
        and all(isinstance(e, dict) and isinstance(e.get("oldString"), str) and isinstance(e.get("newString"), str) for e in edits)
    ):
        return "MultiEdit", {"file_path": path, "edits": [{"old_string": e["oldString"], "new_string": e["newString"]} for e in edits]}
    return "Edit", {"file_path": path}


def _grok_mcp_name(name: str) -> str | None:
    """`aidd__gate` and `mcp__aidd__gate` as the guard's `mcp__<server>__<tool>`. A name with no `__` is not one."""
    if name.startswith("mcp__") and name.count("__") >= 2:
        return name
    if name.count("__") == 1:
        return "mcp__" + name
    return None


# A call that names its file, its text, or its patch in more than one field, with different values: the harness reads
# one, and the guard cannot tell which, so it denies the call.
AMBIGUOUS_CALL = (
    "this call names its file, its text, or its patch in more than one field, and they differ, so the guard cannot tell "
    "which one the tool uses: run it again with each named once"
)


class _Ambiguous(ValueError):
    """Two fields of one call that a harness may read for the same thing hold different values."""


def _one(args: dict, keys: tuple[str, ...]) -> str | None:
    """The one non-empty text `args` holds under any of `keys`; None when none does. _Ambiguous when two differ."""
    found = {args[k] for k in keys if isinstance(args.get(k), str) and args[k]}
    if len(found) > 1:
        raise _Ambiguous(keys)
    return next(iter(found), None)


def _grok_file_input(name: str, tool_input: dict) -> dict | None:
    """A Grok file tool's input with its file under `file_path` and a write's text under `content`, as the guard reads
    them: the daemon route names the file in `path` (`StrReplace`, `Write`, `Delete`) or `target_notebook`
    (`EditNotebook`), and `Write` holds its text in `contents`. None when no file is named the guard can read, and
    _Ambiguous when two fields name different files or texts."""
    path = _one(tool_input, ("file_path", "path", "target_notebook", "target_file"))
    if not path:
        return None
    if name == "Delete":  # removing a file is an edit of it, with no text the decision rules could read
        return {"file_path": path}
    out = {**tool_input, "file_path": path}
    if (text := _one(tool_input, ("content", "contents"))) is not None:
        out["content"] = text
    return out


def _grok_tool(name: str, tool_input: dict) -> tuple[str, dict, str | None] | None:
    """A Grok tool call in the guard's names, with the reason it is denied when the guard cannot read it; None when this
    call reaches no check (a read)."""
    if name in _GROK_TOOLS:
        mapped = _GROK_TOOLS[name]
        if mapped == "Bash":
            return mapped, tool_input, None if isinstance(tool_input.get("command"), str) else OPAQUE_SHELL
        try:
            files = _grok_file_input(name, tool_input)
        except _Ambiguous:
            return mapped, tool_input, AMBIGUOUS_CALL
        return (mapped, files, None) if files is not None else (mapped, tool_input, unknown_tool(name))
    if name == APPLY_PATCH:  # the Codex file toolset's patch, read per file as Codex's is
        try:
            return APPLY_PATCH, {"command": _one(tool_input, ("input", "patch", "patchText", "command")) or ""}, None
        except _Ambiguous:
            return APPLY_PATCH, tool_input, AMBIGUOUS_CALL
    if name == "FetchMcpResource":  # a resource saved to `downloadPath` is a write of that file; else a read
        target = tool_input.get("downloadPath")
        return ("Write", {"file_path": target}, None) if isinstance(target, str) and target else None
    if name in _GROK_READS:
        return None
    if name == "use_tool":
        inner = tool_input.get("tool_name")
        if isinstance(inner, str) and (mapped_name := _grok_mcp_name(inner)):
            args = tool_input.get("tool_input")
            return mapped_name, args if isinstance(args, dict) else {}, None
        return name, tool_input, unknown_tool(name)
    mcp = _grok_mcp_name(name)
    return (mcp, tool_input, None) if mcp else (name, tool_input, unknown_tool(name))


class Grok(Dialect):
    """Grok Build's hooks (its hooks guide; grok 1.0.60 and 1.0.62 ship a copy). The event uses `hookEventName`, `toolName`,
    `toolInput`, `sessionId`, `workspaceRoot`, and `subagentType`, and a Stop says `stopHookActive`. SessionStart reads
    only a top-level `systemMessage`; Stop reads Claude Code's reply. An allow writes nothing, so the person's
    permission settings decide; Grok's `allow` would only mean "not blocked", never an approval."""

    key = "grok-build"
    names_its_session = False  # no variable names the session, so a command prints the id it made
    shows_prompt_note = False  # an allowing UserPromptSubmit hook's stdout is discarded (its hooks guide)

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
        if isinstance(tool, str) and (tool in _GROK_TOOLS or tool in _GROK_READS or tool == "use_tool" or _grok_mcp_name(tool)):
            return True
        return "subagentType" in event or "subagent_type" in event

    def normalize(self, event: dict) -> dict:
        """Map Grok's names onto the guard's: `subagentType` to `agent_type`, `sessionId` to `session_id`,
        `workspaceRoot` to `cwd` when the event has none, and a shell, an edit, or an MCP call onto its check. A tool
        the guard cannot read, or does not know, is marked, and the guard denies it (`opaque_tool`)."""
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
            out["tool_name"], out["tool_input"], opaque = mapped
            if opaque:
                out["opaque_tool"], out["unknown_tool"] = opaque, opaque not in (OPAQUE_SHELL, AMBIGUOUS_CALL)
        return out

    def context(self, hook: str, text: str, shown: str = "") -> dict:
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

    def context(self, hook: str, text: str, shown: str = "") -> dict:
        # Codex documents no hook field the person alone reads: `shown` stays in `text`, for the agent to say.
        return super().context(hook, text)

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
# A shell call whose command is not text: the guard denies it (guard/pre_tool), since it cannot read what would run.
OPAQUE_SHELL = "this shell call names its command in a form the guard cannot read: run it again as one command line"
# OpenCode's Code Mode: `execute` runs code whose own tool calls never reach `execute.before`, so the event names no file
# and no command the guard can read. The dialect marks it, and the guard denies it (guard/pre_tool.CODE_MODE).
_OPENCODE_OPAQUE = frozenset({"execute"})


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
            command = args.get("command")
            out["tool_name"], out["tool_input"] = "Bash", {"command": command if isinstance(command, str) else ""}
            if not isinstance(command, str):  # no command the guard can read, so never an empty one it would allow
                out["opaque_tool"] = OPAQUE_SHELL
        elif tool in ("edit", "write", "multiedit"):
            try:
                out["tool_name"], out["tool_input"] = _opencode_edit(tool, args)
            except _Ambiguous:
                out["tool_name"], out["tool_input"], out["opaque_tool"] = "Edit", args, AMBIGUOUS_CALL
        elif tool in (APPLY_PATCH, "patch"):
            try:
                out["tool_name"], out["tool_input"] = APPLY_PATCH, {"command": _one(args, ("patchText", "patch", "input")) or ""}
            except _Ambiguous:
                out["tool_name"], out["tool_input"], out["opaque_tool"] = APPLY_PATCH, args, AMBIGUOUS_CALL
        elif tool and tool not in _OPENCODE_READS:
            out["tool_name"], out["tool_input"] = f"mcp__opencode__{tool}", args
            if tool in _OPENCODE_OPAQUE:
                out["opaque_tool"] = True
        return out

    def decision(self, decision: str, reason: str) -> dict:
        return {"decision": decision, "reason": f"aidd: {reason}"}

    def context(self, hook: str, text: str, shown: str = "") -> dict:
        # The plugin reads `context` from the session-start and the prompt hooks, and adds it to the person's prompt, which
        # the person reads in the session too: `shown` is in `text` already.
        return {"context": text}


CLAUDE_CODE = Dialect()
ANTIGRAVITY = Antigravity()
GROK = Grok()
CODEX = Codex()
OPENCODE = OpenCode()
DIALECTS: tuple[Dialect, ...] = (ANTIGRAVITY, GROK, OPENCODE, CODEX)  # tried in order; Claude Code's answers any other event


def of(event: object) -> Dialect:
    """The dialect of the harness that sent `event`."""
    return next((d for d in DIALECTS if d.claims(event)), CLAUDE_CODE)
