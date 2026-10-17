"""A Model Context Protocol server over stdio: aidd as agent tools.

`aidd mcp` speaks JSON-RPC 2.0, one message per line, with no dependencies. It is dual-era (`mcp_protocol`): a
request whose `_meta` names the 2026-07-28 revision is served on its own, an `initialize` selects a legacy revision
for the process, and any other request is served only after that `initialize`; before one, it gets -32602.
Each tool runs the same code as the CLI command it names, in the repository
the server was started in, so an agent gets the gate's answers while it works
instead of a red gate after it pushes. Every answer is local and advisory.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable
from pathlib import Path

from aidd import __version__, guard, tracking, workitems
from aidd.cli import app, arguments, mcp_protocol
from aidd.cli.mcp_dialogs import APPROVE as APPROVE
from aidd.cli.mcp_dialogs import approval_request as _approval_request
from aidd.cli.mcp_dialogs import what as _what
from aidd.cli.mcp_tools import DIMENSIONS as DIMENSIONS
from aidd.cli.mcp_tools import ROLES as ROLES
from aidd.cli.mcp_tools import TOOLS as TOOLS
from aidd.cli.mcp_tools import TYPES as TYPES

MAX_LINE_BYTES = 1024 * 1024


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


TOOL_NAMES = frozenset(tool["name"] for tool in TOOLS)
# The tools whose answer is the person's, asked in the client's dialog, and the kind of decision each records; never
# served by `call`.
APPROVAL_TOOLS = {
    "approve_spec": "spec",
    "approve_merge": "merge",
    "ship": "ship",
    "approve_all": "all",
    "proposal_decide": "decide",
    "proposal_sign_off": "sign-off",
}


# The state a 2026-07-28 approval carries between its two calls, signed with a key only this process holds, for 15
# minutes: the client echoes it, and must not be able to change the Spec, the commit, or the hash the person saw.
_STATE_KEY = secrets.token_bytes(32)
STATE_TTL_SECONDS = 15 * 60
CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo"


def _can_elicit(capabilities: object) -> bool:
    """Whether a client declared form-mode elicitation: `elicitation: {}` (form only) or one that names `form`."""
    eliciting = capabilities.get("elicitation") if isinstance(capabilities, dict) else None
    return isinstance(eliciting, dict) and (not eliciting or "form" in eliciting)


def _client_name(info: object) -> str:
    """The client's name for the approval record, as `mcp:<name>`: letters, digits, and `.:_-` only."""
    name = info.get("name") if isinstance(info, dict) else None
    clean = "".join(c for c in name if c.isalnum() or c in ".:_-")[:48] if isinstance(name, str) else ""
    return f"mcp:{clean or 'client'}"


def _approval_preview(tool: str, args: dict, root: str) -> tuple[dict | None, str]:
    """What `aidd approve spec|merge --show` says the person would approve, or None and why it cannot be asked. The
    preview carries `kind`, so the retry of a 2026-07-28 call records the same kind it showed."""
    if tool in ("proposal_decide", "proposal_sign_off"):
        return _proposal_preview(tool, args, root)
    if tool == "approve_all":
        but, until = args.get("but_major", False), args.get("until")
        if not isinstance(but, bool) or not (until is None or workitems.day(until) is not None):
            return None, "bad arguments: but_major must be true or false, and until a date, YYYY-MM-DD"
        return {"kind": "all", "scope": "all-but-major" if but else "all", "until": until}, ""
    if tool == "approve_merge":
        code, text = _cli(["approve", "merge", "--show"], root)
        kind, name = "merge", "the merge"
    elif tool == "ship":
        if not isinstance(args.get("squash", False), bool):
            return None, "bad arguments: squash must be true or false"
        code, text = _cli(["ship", "--show", *(["--squash"] if args.get("squash") else [])], root)
        kind, name = "ship", "this branch"
    elif isinstance(args.get("specs"), list):
        return _specs_preview(args, root)
    else:
        spec, ref = args.get("spec"), args.get("ref") or "HEAD"
        if not isinstance(spec, str) or not isinstance(ref, str) or spec.startswith("-") or ref.startswith("-"):
            return None, "bad arguments: spec and ref must be a Spec id or path and a branch or commit"
        code, text = _cli(["approve", "spec", _opt("--ref", ref), "--show", "--", spec], root)
        kind, name = "spec", spec
    if code != 0:
        return None, text or f"exit {code}"
    shown = {**json.loads(text), "kind": kind}
    if shown.get("problems"):
        return None, f"{shown.get('id') or name} cannot be approved yet: {'; '.join(shown['problems'])}"
    return shown, ""


def _specs_preview(args: dict, root: str) -> tuple[dict | None, str]:
    """Several Specs for one dialog: each one's `aidd approve spec --show`, or why none of them can be asked."""
    specs, ref = args.get("specs"), args.get("ref") or "HEAD"
    if (
        not isinstance(specs, list)
        or not 2 <= len(specs) <= 10
        or len(set(map(str, specs))) != len(specs)
        or not all(isinstance(x, str) and x and not x.startswith("-") for x in specs)
        or not isinstance(ref, str)
        or ref.startswith("-")
    ):
        return None, "bad arguments: specs must be 2 to 10 different Spec ids or paths, and ref a branch or commit"
    items = []
    for spec in specs:
        shown, why = _approval_preview("approve_spec", {"spec": spec, "ref": ref}, root)
        if shown is None:
            return None, why
        items.append(shown)
    return {"kind": "spec", "items": items}, ""


def _proposal_preview(tool: str, args: dict, root: str) -> tuple[dict | None, str]:
    """What `aidd proposal decide|sign-off --show` says the person would record, or None and why it cannot be asked."""
    pid, decision, reason = args.get("proposal"), args.get("decision"), args.get("reason")
    action = "decide" if tool == "proposal_decide" else "sign-off"
    named = isinstance(pid, str) and (re.fullmatch(r"PROP-\d{1,9}", pid) or (pid.endswith(".md") and not pid.startswith("-") and _is_safe_repo_path(pid, root)))
    if not named or (action == "decide" and decision not in ("go", "no-go")):
        return None, "bad arguments: proposal must be a proposal id (PROP-1) or a .md path inside the repository" + (
            ", and decision go or no-go" if action == "decide" else ""
        )
    if reason is not None and (action != "decide" or not isinstance(reason, str) or len(reason) > 500 or "\n" in reason):
        return None, "bad arguments: reason is one line of at most 500 characters, for decide only"
    extra = [_opt("--reason", reason)] if isinstance(reason, str) and reason else []
    tail = [pid, decision] if action == "decide" and isinstance(decision, str) else [pid]
    code, text = _cli(["proposal", action, "--show", *extra, "--", *tail], root)
    if code != 0:
        return None, text or f"exit {code}"
    shown = {**json.loads(text), "kind": action, "proposal": pid}
    if not isinstance(shown.get("path"), str) or not _is_safe_repo_path(shown["path"], root):
        return None, f"{pid} is not a proposal inside this repository"
    if shown.get("problems"):
        return None, f"{shown.get('id') or pid} cannot be recorded: {'; '.join(shown['problems'])}"
    return shown, ""


def _approved(answer: object) -> bool:
    """Only an accepted form whose decision is exactly Approve; decline, cancel, or anything else approves nothing."""
    return (
        isinstance(answer, dict)
        and answer.get("action") == "accept"
        and isinstance(answer.get("content"), dict)
        and answer["content"].get("decision") == APPROVE
    )


def _record_approval(shown: dict, root: str, client: str) -> tuple[bool, str]:
    """`aidd approve spec|merge --confirmed` or `aidd ship --confirmed`: (is_error, text). aidd refuses when the Spec no
    longer hashes to what was shown, or the branch's head moved."""
    if shown.get("items"):
        said = [_record_approval(x, root, client) for x in shown["items"]]
        return any(bad for bad, _ in said), "\n".join(text for _, text in said)
    if shown["kind"] in ("decide", "sign-off"):
        decided = shown["decision"] if shown["kind"] == "decide" else shown["hash"]
        extra = [_opt("--reason", shown["reason"])] if shown.get("reason") else []
        tail = [shown["proposal"], *([shown["decision"]] if shown["kind"] == "decide" else [])]
        argv = ["proposal", shown["kind"], *extra, _opt("--confirmed", decided), _opt("--confirmed-in", client), "--", *tail]
    elif shown["kind"] == "merge":
        argv = ["approve", "merge", _opt("--confirmed", shown["head"]), _opt("--confirmed-in", client)]
    elif shown["kind"] == "all":
        until = [_opt("--until", shown["until"])] if shown.get("until") else []
        but = ["--but-major"] if shown["scope"] == "all-but-major" else []
        argv = ["approve", "all", *but, *until, _opt("--confirmed", shown["scope"]), _opt("--confirmed-in", client)]
    elif shown["kind"] == "ship":
        argv = ["ship", _opt("--confirmed", shown["head"]), _opt("--confirmed-in", client), *(["--squash"] if shown.get("squash") else [])]
    else:
        argv = ["approve", "spec", _opt("--ref", shown["ref"]), _opt("--confirmed", shown["hash"]), _opt("--confirmed-in", client), "--", shown["spec"]]
    with arguments.mcp_dialog():  # this process asked the person: an `mcp:` confirmation counts only from here
        code, text = _cli(argv, root)
    return code != 0, text or f"exit {code}"


def _sign_state(shown: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({**shown, "exp": int(time.time()) + STATE_TTL_SECONDS}).encode()).decode()
    return f"{payload}.{hmac.new(_STATE_KEY, payload.encode(), hashlib.sha256).hexdigest()}"


def _read_state(state: object) -> dict | None:
    """The preview a signed, unexpired state holds, or None for anything this process did not sign."""
    if not isinstance(state, str) or state.count(".") != 1:
        return None
    payload, mac = state.split(".")
    if not hmac.compare_digest(mac, hmac.new(_STATE_KEY, payload.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        shown = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except ValueError:
        return None
    return shown if isinstance(shown, dict) and shown.get("exp", 0) >= time.time() else None


def _cannot_ask(shown: dict) -> str:
    if shown.get("items"):
        ids = " ".join(x["id"] for x in shown["items"])
        prompt, command = f"approve {ids}", f"aidd approve spec {ids}"
    elif shown["kind"] in ("decide", "sign-off"):
        tail = f" {shown['decision']}" if shown["kind"] == "decide" else ""
        prompt, command = f"/aidd {shown['kind']} {shown['id']}{tail}", f"aidd proposal {shown['kind']} {shown['id']}{tail}"
    elif shown["kind"] == "merge":
        prompt, command = "approve merge", "aidd approve merge"
    elif shown["kind"] == "all":
        but = " --but-major" if shown["scope"] == "all-but-major" else ""
        prompt, command = f"/aidd approve all{but}", f"aidd approve all{but}"
    elif shown["kind"] == "ship":
        prompt, command = "ship it", "aidd ship" + (" --squash" if shown.get("squash") else "")
    else:
        prompt, command = f"approve {shown['id']}", f"aidd approve spec {shown['id']}" + (f" --ref {shown['ref']}" if shown["ref"] != "HEAD" else "")
    return (
        f"This client cannot ask the person here, so nothing was recorded. To approve {_what(shown)}, the person types `{prompt}` at the "
        f"Claude Code prompt with the aidd-mods plugin, or runs `{command}` in their own terminal. Tell them; never approve for them."
    )


def _not_approved(shown: dict) -> dict:
    return _tool_result(False, f"Not approved: the person did not approve {_what(shown)}. Nothing was recorded.")


def _approve_modern(params: dict, root: str) -> dict:
    """The approval tools (APPROVAL_TOOLS) in the 2026-07-28 revision: an `input_required` result with the dialog, then,
    on the retry that carries the person's answer and the signed state, the approval. A tool result, or input_required."""
    meta = params["_meta"]
    client = _client_name(meta.get(CLIENT_INFO_KEY))
    tool = params.get("name")
    if "requestState" in params or "inputResponses" in params:
        shown = _read_state(params.get("requestState"))
        if shown is None or shown.get("kind") != APPROVAL_TOOLS.get(str(tool)):
            return _tool_result(True, f"the approval state is not this server's, or it expired; call {tool} again for a fresh dialog")
        answer = (params.get("inputResponses") or {}).get("approve") if isinstance(params.get("inputResponses"), dict) else None
        if not _approved(answer):
            return _not_approved(shown)
        return _tool_result(*_record_approval(shown, root, client))
    shown, why = _approval_preview(str(tool), params.get("arguments") or {}, root)
    if shown is None:
        return _tool_result(True, why)
    if not _can_elicit(meta.get(mcp_protocol.CAPABILITIES_KEY)):
        return _tool_result(False, _cannot_ask(shown))
    return {
        "resultType": "input_required",
        "inputRequests": {"approve": {"method": "elicitation/create", "params": _approval_request(shown)}},
        "requestState": _sign_state(shown),
    }


def _approve_legacy(params: dict, root: str, session: Session) -> dict:
    """The approval tools (APPROVAL_TOOLS) in the 2025 revisions: the server asks the client mid-call
    (`elicitation/create`) and waits."""
    shown, why = _approval_preview(str(params.get("name")), params.get("arguments") or {}, root)
    if shown is None:
        return _tool_result(True, why)
    if not _can_elicit(session.capabilities) or session.ask is None:
        return _tool_result(False, _cannot_ask(shown))
    request = _approval_request(shown)
    if session.legacy == "2025-06-18":
        request.pop("mode")  # form is the only mode there
    answer = session.ask("elicitation/create", request)
    if not _approved(answer):
        return _not_approved(shown)
    return _tool_result(*_record_approval(shown, root, session.client))


def _tool_result(is_error: bool, text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _cli(argv: list[str], root: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = app.main(argv)
        except SystemExit as exc:  # argparse exits on bad input; the server must answer and keep serving
            code = exc.code if isinstance(exc.code, int) and exc.code else 2
    return code, (out.getvalue() + err.getvalue()).strip()


def forecast_answer(args: dict, root: str) -> dict:
    """The `gate` tool with `paths`: `aidd gate --paths --json`, the route of planned paths, with a note that it is a forecast."""
    paths, ctype, dims = args.get("paths") or [], args.get("type") or "feat", args.get("dimension") or []
    irreversible = args.get("irreversible", False)
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise TypeError("paths must be a list of strings")
    if not paths:
        raise TypeError("paths must name at least one planned path; without paths, the gate judges the branch")
    if ctype not in TYPES:
        raise TypeError(f"type must be one of {', '.join(TYPES)}")
    if not isinstance(dims, list) or any(d not in DIMENSIONS for d in dims):
        raise TypeError(f"dimension must be a list of {', '.join(DIMENSIONS)}")
    if not isinstance(irreversible, bool):
        raise TypeError("irreversible must be true or false")
    with contextlib.chdir(root):
        answer = tracking.forecast(Path(root), paths=paths, ctype=ctype, dimensions=dims, irreversible=irreversible)
    from aidd.cli.arguments import JSON_SCHEMA_VERSION

    return (
        {"schema_version": JSON_SCHEMA_VERSION} | answer | {"note": "a forecast: the gate computes the route again from the real diff, and can only raise it"}
    )


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
    if name == "gate" and "paths" in args:
        if any(k in args for k in ("spec", "evidence")):
            return True, "bad arguments: paths forecasts a planned change, so it takes no spec or evidence"
        try:
            return False, json.dumps(forecast_answer(args, root), indent=2)
        except TypeError as exc:
            return True, f"bad arguments: {exc}"
    if name == "gate" and any(k in args for k in ("type", "dimension", "irreversible")):
        return True, "bad arguments: type, dimension, and irreversible describe planned paths: give them with paths"
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
    else:  # the server answers an unknown name with a protocol error before it calls (`_unknown_tool`)
        return True, f"unknown tool {name}"
    code, text = _cli(argv, root)
    # gate: 0 pass, 1 fail, 3 pending are answers, not tool errors.
    return code == 2, text or f"exit {code}"


INSTRUCTIONS = (
    "aidd change control. Check a change's route with gate and its planned paths before the first edit, use check_edit before editing files, and "
    "validate before asking for Spec approval. Answers are advisory; the aidd/gate status decides."
)
SERVER_INFO = {"name": "aidd", "version": __version__}
# How long a client may keep the tool list or the discovery answer: the tools change only with aidd itself, and
# nothing in them depends on who asks (https://modelcontextprotocol.io/specification/2026-07-28/server/discover).
CACHE = {"ttlMs": 3_600_000, "cacheScope": "public"}


class Session:
    """What one stdio process remembers: the legacy revision an `initialize` chose, if any. `handle_message` reads it
    for a request whose `_meta` names no 2026-07-28 revision: served with legacy semantics once it is set, refused with
    -32602 before. A modern request never reads it (the 2026-07-28 revision keeps no session), so one process may
    serve both eras."""

    def __init__(self) -> None:
        self.legacy: str | None = None
        # What the legacy `initialize` said about the client: its capabilities, and its name for an approval record.
        self.capabilities: dict = {}
        self.client = _client_name(None)
        # Sends a request to the client mid-call and waits for its result (None when it answers with an error or
        # never does); set by `serve`, None when there is no client to ask (a message handled alone).
        self.ask: Callable[[str, dict], object] | None = None
        # Messages that arrived while the server waited for an answer, served next, in order.
        self.backlog: list[str] = []


def _error(mid, code: int, message: str, data: dict | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": error}


def _unknown_tool(mid, params: dict) -> dict | None:
    """The JSON-RPC error for a `tools/call` that names no tool this server lists, or None. Both eras call an unknown
    tool a protocol error, -32602, not a tool result with `isError`
    (https://modelcontextprotocol.io/specification/2026-07-28/server/tools#error-handling)."""
    name = params.get("name")
    if isinstance(name, str) and name in TOOL_NAMES:
        return None
    return _error(mid, mcp_protocol.INVALID_PARAMS, f"Unknown tool: {name if isinstance(name, str) else json.dumps(name)}")


def _tools_call(params: dict, root: str) -> dict:
    try:
        is_error, text = call(params.get("name", ""), params.get("arguments") or {}, root)
    except (KeyError, TypeError) as exc:
        is_error, text = True, f"bad arguments: {exc}"
    except Exception as exc:  # noqa: BLE001  # a tool error is an answer, never a dead server
        is_error, text = True, f"{type(exc).__name__}: {exc}"
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _modern(mid, method: str, params: dict, root: str) -> dict:
    """A 2026-07-28 request, served on its own: every result says `resultType` and names the server in `_meta`."""
    meta = params["_meta"]
    if not isinstance(meta.get(mcp_protocol.CAPABILITIES_KEY), dict):
        return _error(mid, mcp_protocol.INVALID_PARAMS, f"invalid params: _meta needs {mcp_protocol.CAPABILITIES_KEY}, an object")
    result: dict
    if method == "server/discover":
        result = {"supportedVersions": list(mcp_protocol.SUPPORTED), "capabilities": {"tools": {}}, "instructions": INSTRUCTIONS, **CACHE}
    elif method == "tools/list":
        result = {"tools": TOOLS, **CACHE}
    elif method == "tools/call":
        if unknown := _unknown_tool(mid, params):
            return unknown
        result = _approve_modern(params, root) if params.get("name") in APPROVAL_TOOLS else _tools_call(params, root)
        if result.get("resultType") == "input_required":
            return {"jsonrpc": "2.0", "id": mid, "result": {**result, "_meta": {mcp_protocol.SERVER_INFO_KEY: SERVER_INFO}}}
    else:  # initialize, ping, and logging/setLevel are not 2026-07-28 methods
        return _error(mid, mcp_protocol.METHOD_NOT_FOUND, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": mid, "result": {"resultType": "complete", **result, "_meta": {mcp_protocol.SERVER_INFO_KEY: SERVER_INFO}}}


def _legacy(mid, method: str, params: dict, root: str, session: Session) -> dict:
    """A request of the `initialize` era (2025-11-25 and 2025-06-18), whose results carry no `resultType`."""
    result: dict
    if method == "initialize":
        requested = params.get("protocolVersion")
        session.legacy = requested if requested in mcp_protocol.LEGACY else mcp_protocol.LEGACY_LATEST
        caps = params.get("capabilities")
        session.capabilities = caps if isinstance(caps, dict) else {}
        session.client = _client_name(params.get("clientInfo"))
        result = {"protocolVersion": session.legacy, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        if unknown := _unknown_tool(mid, params):
            return unknown
        result = _approve_legacy(params, root, session) if params.get("name") in APPROVAL_TOOLS else _tools_call(params, root)
    else:
        return _error(mid, mcp_protocol.METHOD_NOT_FOUND, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _no_era(mid) -> dict:
    """The -32602 for a request other than `initialize` that comes before any `initialize` and whose `_meta` names no
    2026-07-28 revision: it is neither modern nor part of a legacy session, so it is malformed, never served by guess
    (https://modelcontextprotocol.io/specification/2026-07-28/basic/index#meta)."""
    return _error(
        mid,
        mcp_protocol.INVALID_PARAMS,
        f"invalid params: the request names no {mcp_protocol.PROTOCOL} revision in `_meta`, and no `initialize` came first. "
        f"Send `initialize` first for a legacy revision "
        f"({' or '.join(mcp_protocol.LEGACY)}), or name the revision in `_meta` ({mcp_protocol.PROTOCOL}: "
        f"{mcp_protocol.VERSION_KEY} and {mcp_protocol.CAPABILITIES_KEY})",
    )


def handle_message(msg: dict, root: str, session: Session | None = None) -> dict | None:
    """One JSON-RPC message's answer, or None when it gets none: a notification, or a response (the server sends no
    request, so a response answers nothing). A `_meta` that is not an object is -32602. A request whose `_meta` names
    the 2026-07-28 revision is modern; `initialize` starts the legacy era for `session`; any other request is served
    with legacy semantics only once `session` holds a legacy revision, and gets -32602 before. Without a `session`,
    the message stands alone, as if it were the process's first."""
    session = session if session is not None else Session()
    if not isinstance(msg, dict):
        return _error(None, -32600, "invalid request: not an object")
    mid = msg.get("id")
    if mid is None or "method" not in msg:
        return None  # a notification, such as notifications/initialized, or a response sent to the server
    if not isinstance(msg["method"], str):
        return _error(mid, -32600, "invalid request: the method is not a string")
    method = msg["method"]
    raw = msg.get("params")
    params: dict = raw if isinstance(raw, dict) else {}
    if "_meta" in params and not isinstance(params["_meta"], dict):
        return _error(mid, mcp_protocol.INVALID_PARAMS, "invalid params: _meta must be an object")
    meta: dict = params.get("_meta") or {}
    if method != "initialize" and mcp_protocol.VERSION_KEY in meta:
        requested = meta[mcp_protocol.VERSION_KEY]
        if requested not in mcp_protocol.SUPPORTED:
            data = {"supported": list(mcp_protocol.SUPPORTED), "requested": requested if isinstance(requested, str) else json.dumps(requested)}
            return _error(mid, mcp_protocol.UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version", data)
        if requested in mcp_protocol.MODERN:
            return _modern(mid, method, params, root)
    elif method == "server/discover":  # a modern method: its revision is required
        return _error(mid, mcp_protocol.INVALID_PARAMS, f"invalid params: _meta needs {mcp_protocol.VERSION_KEY}")
    if method != "initialize" and session.legacy is None:
        return _no_era(mid)
    return _legacy(mid, method, params, root, session)


def serve(stdin=None, stdout=None, root: str | None = None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    root = root or os.getcwd()
    session = Session()
    asked = 0

    def ask(method: str, params: dict) -> object:
        """A request to the client mid-call (legacy only): its result, or None for an error or a closed input."""
        nonlocal asked
        asked += 1
        rid = f"aidd-{asked}"
        stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
        stdout.flush()
        while True:
            waiting = stdin.readline(MAX_LINE_BYTES + 1)
            if not waiting:
                return None
            try:
                msg = json.loads(waiting)
            except ValueError:
                msg = None
            if isinstance(msg, dict) and msg.get("id") == rid and "method" not in msg:
                return msg.get("result")
            session.backlog.append(waiting)

    session.ask = ask
    reply: dict | None
    while True:
        line = session.backlog.pop(0) if session.backlog else stdin.readline(MAX_LINE_BYTES + 1)
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
                reply = handle_message(msg, root, session)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
