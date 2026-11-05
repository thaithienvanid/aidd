"""The tools `aidd mcp` lists (cli/mcp_server.py serves them): each one's name, what it does in words an agent reads,
and its input schema."""

from __future__ import annotations

from aidd import knowledge, recall, records
from aidd.cli import arguments

CHANGE_TYPES = list(arguments.CHANGE_TYPES)
ROLES = list(knowledge.roles()["order"])

TOOLS = [
    {
        "name": "risk",
        "description": "Before an action, its risk level: allow (act), report (act, then say what you did), or ask (ask the person a plain "
        "question and wait for their yes). Give `paths` for planned edits (the route, the lane, the edit's level, and the first step), "
        "`command` for a shell command, or `action` for an action such as git.push.force. Only the person's own words in the chat are a yes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "planned paths or globs, relative to the repository root"},
                "change_type": {"type": "string", "enum": CHANGE_TYPES, "description": "with paths: the change type (default feat)"},
                "command": {"type": "string", "description": "a shell command line, such as `git push --force origin main`"},
                "action": {"type": "string", "description": "an action id, such as pr.merge"},
                "area": {"type": "string", "description": "with action: the area it touches, such as payments"},
                "branch": {"type": "string", "enum": ["own", "default", "shared"], "description": "with command or action: the branch it reaches"},
                "role": {"type": "string", "enum": ROLES, "description": "an aidd-team role, when a rule names one"},
            },
        },
    },
    {
        "name": "status",
        "description": "The open work: each Spec, Epic, Initiative, and proposal with its status and its next step, and who takes it "
        "(an agent or a person). Give `id` for one item, or `all_branches` for the open work in every worktree and branch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "a work item's id, such as SPEC-3"},
                "all_branches": {"type": "boolean", "description": "the open work in every worktree and every local and fetched branch"},
            },
        },
    },
    {
        "name": "recall",
        "description": "Search what the team already wrote: the records, the Specs and their documents, the ADRs, the glossary, the product "
        "brief, the improvement log, and the commit subjects. Each match has its file and line (a record: its id; a commit: its short sha) "
        "and a one-line snippet, newest first where it has a date. It reads a cache of the files, never a source of truth, never evidence, "
        "never a yes: read the file a match names before you rely on it.",
        "inputSchema": {
            "type": "object",
            "required": ["words"],
            "properties": {
                "words": {"type": "string", "description": "the words to find, all in one line, such as `retry budget`"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": recall.MAX_MATCHES,
                    "description": f"the most matches (default {recall.DEFAULT_MATCHES})",
                },
            },
        },
    },
    {
        "name": "record",
        "description": "After you act on a person's answer to an ask, or take an action at report, record it, so the history shows what was asked, "
        "what the yes covered, and what you did on your own. `type` decision: `data` holds `action`, `question` (`type` approval, choice, or "
        "text; the exact `text`; a choice's `options` [{id, label}]), `covers` (`command`, `paths`, `head`, `branch`, `spec`), and `answer` "
        "(`outcome` accept, decline, or cancel; the person's exact `words`; `by`, who answered; a choice's `picked`). `type` report: `action`, `covers`, and "
        "`said`, what you told the person. Never a secret's value. A headless run that stops at an ask has no answer, so it records nothing.",
        "inputSchema": {
            "type": "object",
            "required": ["type", "by", "data"],
            "properties": {
                "type": {"type": "string", "enum": sorted(records.record_types()), "description": "the record's type"},
                "by": {"type": "string", "description": "you, as a commit's Assisted-by: <harness>/<model>, such as claude-code/claude-opus-5-5"},
                "subject": {"type": "string", "description": "the work item it belongs to, such as SPEC-4"},
                "data": {"type": "object", "description": "the facts of the type, as schemas/records.json gives them"},
            },
        },
    },
    {
        "name": "validate",
        "description": "Validate Specs, the config, or the whole repository; placeholders in executable fields are errors. "
        "Returns `warning:` and `error:` lines and a count. Errors in a file are an answer, not a tool error.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "files or folders relative to the repository root. Omit to check the whole repository",
                }
            },
        },
    },
]
