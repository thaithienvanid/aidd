"""The tools `aidd mcp` lists (cli/mcp_server.py serves them): each one's name, what it does in words an agent reads,
and its input schema."""

from __future__ import annotations

from aidd import knowledge
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
        "(an agent or a person). Give `id` for one item.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "a work item's id, such as SPEC-3"}}},
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
