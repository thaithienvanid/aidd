"""A Model Context Protocol server over stdio: aidd as agent tools.

`aidd mcp` speaks JSON-RPC 2.0, one message per line, with no dependencies.
Each tool runs the same code as the CLI command it names, in the repository
the server was started in, so an agent gets the gate's answers while it works
instead of a red gate after it pushes. Every answer is local and advisory.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

from . import __version__, cli, guard, nextstep, resources

PROTOCOL = "2025-06-18"
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_LINE_BYTES = 1024 * 1024
TYPES = list(cli.TYPES)
DIMENSIONS = list(cli.DIMENSIONS)
ROLES = list(resources.roles()["order"])


def _is_safe_repo_path(p: str, root: str) -> bool:
    """A relative path that stays inside `root`. A `..` component that climbs out is refused; a name that only
    starts with two dots, such as `..notes/x.md`, is an ordinary name."""
    if not isinstance(p, str) or os.path.isabs(p):
        return False
    try:
        rel = os.path.relpath(os.path.join(root, p), root)
    except ValueError:
        return False
    return rel.replace(os.sep, "/").split("/")[0] != ".."


TOOLS = [
    {
        "name": "assess",
        "description": "Check a change's route before the first edit, as JSON. For planned paths, or, with no paths, for this branch's change, "
        "it gives the route and its lane, with the reasons, the implied risk dimensions, and the specialist pools. For this branch's change, "
        "the route is the higher of what the diff needs and what its Spec or Change Request block declares. It also gives the next steps for "
        "this change, who takes each, and the other branches it overlaps. Advisory: the gate recomputes the route from the real diff and "
        "can only raise it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "planned paths or globs relative to the repository root, before any code exists; omit for this branch's change",
                },
                "type": {"type": "string", "enum": TYPES, "description": "the change type, such as feat or fix (default feat)"},
                "dimension": {
                    "type": "array",
                    "items": {"type": "string", "enum": DIMENSIONS},
                    "description": "with paths only: declared risk dimensions (ignored for this branch's change, whose Spec or block declares them)",
                },
                "irreversible": {"type": "boolean", "description": "with paths only: a revert would not restore the prior state (forces major)"},
            },
        },
    },
    {
        "name": "check_edit",
        "description": "Before editing a file: allow or deny, never a question. It checks the path against the active Spec's scope, its test "
        "and design files, and its frozen linked docs (frozen once Spec approval of the current hash holds). It also checks protected paths "
        "(allowed only inside an approved scope) and, when given, an aidd-team role's write area. A deny names the route that fixes it. The active Spec is the one AIDD_SPEC names, "
        "else every Spec this branch adds or changes. It allows when it cannot tell: with no valid .aidd/config.toml, and, with no role, "
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
                    "description": "an aidd-team role: product-manager, delivery-manager, architect, product-designer, security-engineer, compliance-analyst, tester, developer, ml-engineer, data-engineer, platform-engineer, tech-writer, verifier, reviewer, sre, or agile-coach",
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
        "description": "Run every gate rule locally against the branch's committed change (base to HEAD) and return the report: pass, fail, "
        "or pending, each finding with its fix, and what the gate would still wait for. Fail and pending are answers, not tool errors. "
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
                    "description": "the evidence `aidd test` wrote, relative to the repository root (default aidd-evidence/evidence.json)",
                },
            },
        },
    },
]


def _cli(argv: list[str], root: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse exits on bad input; the server must answer and keep serving
            code = exc.code if isinstance(exc.code, int) and exc.code else 2
    return code, (out.getvalue() + err.getvalue()).strip()


def assess_answer(args: dict, root: str) -> dict:
    """The `assess` tool: `aidd assess --json`, for planned paths or this branch's change, with a note that it is advice."""
    paths, ctype, dims = args.get("paths") or [], args.get("type") or "feat", args.get("dimension") or []
    irreversible = args.get("irreversible", False)
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise TypeError("paths must be a list of strings")
    if ctype not in TYPES:
        raise TypeError(f"type must be one of {', '.join(TYPES)}")
    if not isinstance(dims, list) or any(d not in DIMENSIONS for d in dims):
        raise TypeError(f"dimension must be a list of {', '.join(DIMENSIONS)}")
    if not isinstance(irreversible, bool):
        raise TypeError("irreversible must be true or false")
    with contextlib.chdir(root):
        answer = nextstep.assess(Path(root), paths=paths, ctype=ctype, dimensions=dims, irreversible=irreversible)
    from .cli import JSON_SCHEMA_VERSION

    return {"schema_version": JSON_SCHEMA_VERSION} | answer | {"note": "advisory: the gate recomputes the route from the real diff and can only raise it"}


def _opt(flag: str, value) -> str:
    """`--flag=value`, so a value such as `--help` can never be read as an option."""
    if not isinstance(value, str):
        raise TypeError(f"{flag} must be a string")
    return f"{flag}={value}"


def call(name: str, args: dict, root: str) -> tuple[bool, str]:
    """(is_error, text) for one tool call."""
    for p in [*(args.get("paths") or []), *(args[k] for k in ("path", "spec", "evidence") if k in args)]:
        if not _is_safe_repo_path(p, root):
            return True, f"path {p!r} is outside the repository"

    if name == "check_edit":
        decision, reason = guard.check_edit(root, guard.repo_relative(root, args["path"]), args.get("role"))
        return False, f"{decision}: {reason}"
    if name == "assess":
        try:
            return False, json.dumps(assess_answer(args, root), indent=2)
        except TypeError as exc:
            return True, f"bad arguments: {exc}"
    if name == "validate":
        paths = args.get("paths", [])
        argv = ["validate"] + (["--", *paths] if paths else [])
    elif name == "approval_line":
        if not isinstance(args["spec"], str) or args["spec"].startswith("-"):
            return True, f"spec {args['spec']!r} is not a file path"
        argv = ["hash", "--line", "--", args["spec"]]
    elif name == "describe":
        argv = ["describe"] + ([_opt("--type", args["type"])] if args.get("type") else [])
    elif name == "gate":
        argv = ["gate"] + [_opt(f"--{k}", args[k]) for k in ("spec", "evidence") if args.get(k)]
    else:
        return True, f"unknown tool {name}"
    code, text = _cli(argv, root)
    # gate: 0 pass, 1 fail, 3 pending are answers, not tool errors.
    return code == 2, text or f"exit {code}"


def handle(msg: dict, root: str) -> dict | None:
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request: not an object"}}
    mid = msg.get("id")
    if mid is None:
        return None  # a notification, such as notifications/initialized
    if "method" not in msg or not isinstance(msg.get("method"), str):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32600, "message": "invalid request: missing method"}}
    method = msg["method"]
    result: dict
    if method == "initialize":
        # Answer with the client's version when this server speaks it, otherwise with the newest it does.
        requested = (msg.get("params") or {}).get("protocolVersion")
        result = {
            "protocolVersion": requested if requested in SUPPORTED else PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "aidd", "version": __version__},
            "instructions": "aidd change control. Check a change's route with assess before the first edit, use check_edit before editing files, and "
            "validate before asking for Spec approval. Answers are advisory; the aidd/gate status decides.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        try:
            is_error, text = call(params.get("name", ""), params.get("arguments") or {}, root)
        except (KeyError, TypeError) as exc:
            is_error, text = True, f"bad arguments: {exc}"
        except Exception as exc:  # noqa: BLE001  # a tool error is an answer, never a dead server
            is_error, text = True, f"{type(exc).__name__}: {exc}"
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None, root: str | None = None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    root = root or os.getcwd()
    reply: dict | None
    while True:
        line = stdin.readline(MAX_LINE_BYTES + 1)
        if not line:
            break
        if len(line) > MAX_LINE_BYTES and not line.endswith("\n"):
            while True:
                chunk = stdin.readline(MAX_LINE_BYTES)
                if not chunk or chunk.endswith("\n"):
                    break
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error: message exceeds size cap"}}
        elif not line.strip():
            continue
        else:
            try:
                msg = json.loads(line)
            except ValueError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            else:
                reply = handle(msg, root)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
