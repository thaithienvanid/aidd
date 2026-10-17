"""The tools `aidd mcp` lists (cli/mcp_server.py serves them): each one's name, what it does in words an agent reads,
and its input schema."""

from __future__ import annotations

from aidd import knowledge
from aidd.cli import arguments

TYPES = list(arguments.TYPES)
DIMENSIONS = list(arguments.DIMENSIONS)
ROLES = list(knowledge.roles()["order"])

TOOLS = [
    {
        "name": "check_edit",
        "description": "Before editing a file: allow or deny, never a question. It checks the path against the active Spec's scope, its test "
        "and design files, and its frozen linked docs (frozen once Spec approval of the current hash holds). It also checks protected paths "
        "(allowed only inside an approved scope) and, when given, an aidd-team role's write area. A deny names the route that fixes it. The active Spec is the one AIDD_SPEC names, "
        "else every Spec this branch adds or changes. It allows when it cannot tell: with no valid .aidd/config.yaml, and, with no role, "
        "with no active Spec or several, unless the path is protected. It does not see the edit's text, so only the edit hook checks a "
        "proposal's go_no_go, sign_off, and outcome. Advisory: the gate checks the real diff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "the file to edit, relative to the repository root, such as src/app.py; an absolute path is refused as outside the repository",
                },
                "role": {
                    "type": "string",
                    "enum": ROLES,
                    "description": "an aidd-team role: product-manager, delivery-manager, architect, product-designer, security-engineer, compliance-analyst, domain-expert, tester, developer, ml-engineer, data-engineer, platform-engineer, tech-writer, verifier, reviewer, sre, or agile-coach",
                },
            },
            "required": ["path"],
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
                    "description": "files or folders relative to the repository root; in a folder, each config and aidd Markdown file is checked. "
                    "Omit to check the whole repository",
                }
            },
        },
    },
    {
        "name": "approval_line",
        "description": "The approval line (/aidd approve-spec ID HASH COMMIT) for the Spec as committed at HEAD, to hand to the author; "
        "for a proposal, its sign_off line. An uncommitted Spec is an error. Uncommitted changes to the Spec or its frozen files give a "
        "warning, because the line covers HEAD only. Never post it yourself: an approval is a person's.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "string",
                    "description": "the Spec or proposal: a path relative to the repository root, such as specs/SPEC-1.md, or its id, such as SPEC-1",
                }
            },
            "required": ["spec"],
        },
    },
    {
        "name": "describe",
        "description": "The Change Request block that describes the branch's committed change (base to HEAD; uncommitted work does not count), "
        "with the reasons for its route. When the route needs a Spec and the diff has none, it gives instead the `aidd new spec` command "
        "to write one. It records nothing. A branch with no committed change since its base is an error.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": TYPES,
                    "description": "the change type (default: the type of the newest Conventional Commit subject, else docs when every changed "
                    "file is .md, .rst, or .txt, else feat)",
                }
            },
        },
    },
    {
        "name": "gate",
        "description": "Before the first edit, with `paths`: forecast a change's route as JSON. For the planned paths it gives the route and "
        "its lane, with the reasons, the implied risk dimensions, the specialist pools, and the lane's first step. It records nothing, and "
        "on the branch the gate computes the route again from the real diff, which can only raise it. Without `paths`: run every gate rule "
        "locally against the branch's committed change (base to HEAD). It returns the report: pass, fail, "
        "or pending, each finding with its fix, what the gate would still wait for, the route it computed, and the other branches it overlaps. "
        "Fail and pending are answers, not tool errors. "
        "Untrusted: it sees only the approvals a person recorded on this machine with `aidd approve`, never a platform's. It reads the "
        "evidence `aidd test` wrote, which this server does not run, and it runs the Policy command the base branch's config sets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "string",
                    "description": "the Spec this change implements, relative to the repository root (default: the Change Request block of the newest "
                    "branch commit that has one, else the one Spec in the diff)",
                },
                "evidence": {
                    "type": "string",
                    "description": "the evidence `aidd test` wrote, relative to the repository root (default .aidd/evidence/evidence.json)",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "before any code exists: the planned paths or globs, relative to the repository root, to forecast the route of",
                },
                "type": {"type": "string", "enum": TYPES, "description": "with paths only: the change type, such as feat or fix (default feat)"},
                "dimension": {
                    "type": "array",
                    "items": {"type": "string", "enum": DIMENSIONS},
                    "description": "with paths only: declared risk dimensions",
                },
                "irreversible": {"type": "boolean", "description": "with paths only: a revert would not restore the prior state (forces major)"},
            },
        },
    },
    {
        "name": "approve_spec",
        "description": "Ask the person to approve a Spec in this client's own dialog (MCP elicitation). Call it when the person says they "
        "approve a Spec, or asks you to get a waiting Spec approved. They see the Spec's title, its Acceptance, the commit, and the hash, and "
        "choose Approve or Not now; with `specs`, several Specs in one dialog and one choice. Only their choice records the approval, for exactly that hash; you never answer the dialog, and never "
        "call it again to press them. A client that cannot ask returns how the person approves instead: the `approve <ID>` prompt with "
        "the aidd-mods plugin in Claude Code, or `aidd approve spec <ID>` at their own terminal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string", "description": "the Spec: its id, such as SPEC-1, or its path, such as specs/SPEC-1.md"},
                "specs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 10,
                    "description": "instead of spec: several Specs on this branch, shown in one dialog and approved with one choice",
                },
                "ref": {"type": "string", "description": "the branch or commit that holds the Spec, such as spec/SPEC-1 (default: HEAD)"},
            },
        },
    },
    {
        "name": "approve_merge",
        "description": "Ask the person for Merge approval of this branch's head commit in this client's own dialog (MCP elicitation). Call it "
        "when the person says they approve the merge, after `aidd test` and with the gate passing but for that approval. They see the branch, "
        "the head, what changed, and what else the gate waits on, and choose Approve or Not now. Only their choice records the approval, for "
        "exactly that head; you never answer it. A client that cannot ask returns how the person approves instead.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ship",
        "description": "Local-first, with no platform: ask the person to ship this branch into the base branch, in this client's own dialog "
        "(MCP elicitation). Call it when the person says to ship. They see the branch, the head, what changed, and what else the gate waits "
        "on, and choose Approve or Not now. On their Approve, `aidd ship` runs the tests again on what lands and merges only if the gate "
        "passes, recording their Merge approval when that is all it waits for. You never answer it. On a platform, the PR/MR merges instead.",
        "inputSchema": {"type": "object", "properties": {"squash": {"type": "boolean", "description": "land one squashed commit (default false)"}}},
    },
    {
        "name": "approve_all",
        "description": "Ask the person, in this client's own dialog (MCP elicitation), to start a standing approval: from then on you record "
        "each Spec approval and Merge approval it covers, and ship, until they stop it. Call it when the person says to approve all or to "
        "automate. They see what it covers and how to stop it, and choose Approve or Not now. Only their choice starts it; you never answer it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "but_major": {"type": "boolean", "description": "leave major changes to the person (default false)"},
                "until": {"type": "string", "description": "the last day it holds, YYYY-MM-DD (default: until the person stops it)"},
            },
        },
    },
    {
        "name": "proposal_decide",
        "description": "Ask the person, in this client's own dialog (MCP elicitation), to record a proposal's go or no-go. Call it when the "
        "person says go or no-go on a proposal. They see the proposal, who it is for, the decision, and any earlier one it replaces, and "
        "choose Approve or Not now. Only their choice writes it into the proposal, for them to commit; you never answer it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "proposal": {"type": "string", "description": "the proposal: its id, such as PROP-1, or its path"},
                "decision": {"type": "string", "enum": ["go", "no-go"], "description": "go, to draft it, or no-go"},
                "reason": {"type": "string", "description": "why, in one sentence, as the person said it"},
            },
            "required": ["proposal", "decision"],
        },
    },
    {
        "name": "proposal_sign_off",
        "description": "Ask the person, in this client's own dialog (MCP elicitation), to sign off a proposal after its go, so it may be "
        "sent. They see the proposal and the hash of exactly its text, and choose Approve or Not now. Only their choice records it, for "
        "that text; you never answer it.",
        "inputSchema": {
            "type": "object",
            "properties": {"proposal": {"type": "string", "description": "the proposal: its id, such as PROP-1, or its path"}},
            "required": ["proposal"],
        },
    },
]
