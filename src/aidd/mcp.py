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

from . import __version__, cli, guard, nextstep, rules
from . import config as cfgmod

PROTOCOL = "2025-06-18"
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_LINE_BYTES = 1024 * 1024
TYPES = list(cli.TYPES)
DIMENSIONS = list(cli.DIMENSIONS)


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
        "name": "next",
        "description": "Where every change starts: the minimum route and its lane (with the reasons, the implied risk dimensions, and the "
        "specialist pools) for planned paths, or for the branch's diff when no paths are given, and the next steps in this repository "
        "and who takes each, as JSON. Advisory: the gate recomputes the route from the real diff and can only raise it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "planned paths or globs, before any code exists"},
                "type": {"type": "string", "enum": TYPES, "description": "the change type, such as feat or fix (default feat)"},
                "dimension": {"type": "array", "items": {"type": "string", "enum": DIMENSIONS}, "description": "declared risk dimensions"},
            },
        },
    },
    {
        "name": "check_edit",
        "description": "Before editing a file: allow or deny, never a question, against the active Spec's scope, its test and design files (frozen once the Spec's status says Spec approval), protected paths (allowed only inside an approved scope), and, when given, an aidd-team role's write area. A deny names the route that fixes it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "role": {
                    "type": "string",
                    "description": "an aidd-team role: product-manager, architect, product-designer, security-engineer, compliance-analyst, tester, developer, ml-engineer, data-engineer, platform-engineer, tech-writer, verifier, reviewer, sre, or agile-coach",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "validate",
        "description": "Validate Specs, the config, or the whole repository; placeholders in executable fields are errors.",
        "inputSchema": {"type": "object", "properties": {"paths": {"type": "array", "items": {"type": "string"}}}},
    },
    {
        "name": "hash",
        "description": "The committed Spec's approval line (/aidd approve-spec ID HASH COMMIT), to hand to the author. Never post it yourself.",
        "inputSchema": {"type": "object", "properties": {"spec": {"type": "string"}}, "required": ["spec"]},
    },
    {
        "name": "change",
        "description": "A starting toml aidd block for the branch's diff, or the instruction to write a Spec.",
        "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}}},
    },
    {
        "name": "gate",
        "description": "Run every gate rule locally against the branch (untrusted: it sees only the approvals a person recorded on this machine with `aidd approve`, never a platform's). Report what the gate would still wait for.",
        "inputSchema": {"type": "object", "properties": {"spec": {"type": "string"}, "evidence": {"type": "string"}}},
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


def next_answer(args: dict, root: str) -> dict:
    """The `next` tool: the route and lane for planned paths or the branch's diff, and `aidd next`'s steps."""
    paths, ctype, dims = args.get("paths") or [], args.get("type") or "feat", args.get("dimension") or []
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise TypeError("paths must be a list of strings")
    if ctype not in TYPES:
        raise TypeError(f"type must be one of {', '.join(TYPES)}")
    if not isinstance(dims, list) or any(d not in DIMENSIONS for d in dims):
        raise TypeError(f"dimension must be a list of {', '.join(DIMENSIONS)}")
    route: dict | None
    with contextlib.chdir(root):
        if paths:
            cfg = cfgmod.load_file(cfgmod.CONFIG_PATH, root)
            route = rules.summary(rules.assess_paths(cfg, paths, ctype=ctype, dimensions=dims), "planned paths")
        else:
            route = rules.assess_diff(root, ctype=ctype)
        steps = nextstep.plan(Path(root))
    if route is not None:
        route["reasons"] = rules.reason_lines(route)
    return {"route": route, "next": steps, "note": "advisory: the gate recomputes the route from the real diff and can only raise it"}


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
    if name == "next":
        try:
            return False, json.dumps(next_answer(args, root), indent=2)
        except TypeError as exc:
            return True, f"bad arguments: {exc}"
    if name == "validate":
        paths = args.get("paths", [])
        argv = ["validate"] + (["--", *paths] if paths else [])
    elif name == "hash":
        if not isinstance(args["spec"], str) or args["spec"].startswith("-"):
            return True, f"spec {args['spec']!r} is not a file path"
        argv = ["hash", "--comment", "--", args["spec"]]
    elif name == "change":
        argv = ["change"] + ([_opt("--type", args["type"])] if args.get("type") else [])
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
            "instructions": "aidd change control. Every change starts with next (its route and lane), use check_edit before editing files, and "
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
