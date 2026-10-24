"""The MCP tool check: a tool that merges, approves, or sets a status, or whose input carries an approval line."""

from __future__ import annotations

import re

from aidd.guard import verdicts

# An MCP tool whose name says it merges or approves, or sets a commit status (the gate's own channel). The name is
# split into lowercase words whatever its style (merge_pull_request, mergePullRequest, merge-pull-request).
MCP_READ_VERBS = frozenset({"get", "list", "search", "read", "check", "is", "can", "view", "describe"})
_MCP_WRITE_VERBS = frozenset({"set", "create", "post", "update", "add", "put", "write"})
_MCP_REQUEST_NOUNS = frozenset({"pull", "pr", "prs", "mr", "mrs", "request", "requests", "merge"})


def mcp_words(tool: str) -> list[str]:
    """The words of an MCP tool name: `approvePullRequest`, `approve-pull-request`, and `approve_pull_request` are
    all approve, pull, request."""
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", tool)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def _mcp_merges(words: list[str]) -> bool:
    """A tool whose words merge or approve (merge, approve, or an accept or complete of a pull or merge request);
    `merge request` is a noun, and a name that starts with a read verb only reads."""
    if not words or words[0] in MCP_READ_VERBS:
        return False
    actions = [w for i, w in enumerate(words) if not (w == "merge" and words[i + 1 : i + 2] in (["request"], ["requests"]))]
    if any(w in ("merge", "approve") or w.endswith("merge") for w in actions):
        return True
    return any(w in ("accept", "complete") for w in actions) and bool(_MCP_REQUEST_NOUNS & set(words))


def _mcp_sets_status(words: list[str]) -> bool:
    """A tool that sets, creates, posts, or updates a (commit) status."""
    if not words or words[0] in MCP_READ_VERBS:
        return False
    after_verb = any(
        w in _MCP_WRITE_VERBS and (words[i + 1 : i + 2] == ["status"] or words[i + 1 : i + 3] == ["commit", "status"]) for i, w in enumerate(words)
    )
    return after_verb or ("status" in words and "commit" in words and bool(_MCP_WRITE_VERBS & set(words)))


_APPROVAL_LINE = re.compile(r"(?mi)^[ \t>]*/aidd[ \t]+approve")


def _strings(value, depth: int = 0):
    """Every string in a tool input, a few levels deep."""
    if isinstance(value, str):
        yield value
    elif depth < 4 and isinstance(value, dict):
        for v in value.values():
            yield from _strings(v, depth + 1)
    elif depth < 4 and isinstance(value, list):
        for v in value[:100]:
            yield from _strings(v, depth + 1)


# aidd's own dialog tools: each asks the person in the client's own dialog (MCP elicitation) and refuses when the client
# cannot ask, so the agent that calls one decides nothing. Only under the server names Claude Code gives aidd's server
# (the plugin's, and the one `aidd init` wires), and only in Claude Code, where the dialog is known to be the person's;
# in another harness they stay denied until a live check shows its dialog cannot be answered for the person.
OWN_SERVERS = frozenset({"aidd", "plugin_aidd_aidd"})
DIALOG_TOOLS = frozenset({"approve_spec", "approve_merge", "approve_all", "land", "decide_proposal", "sign_off_proposal"})


def aidd_dialog(name: str) -> bool:
    """Whether an MCP tool call is one of aidd's own dialog tools, under a server name Claude Code gives aidd's server."""
    parts = name.split("__")
    return len(parts) == 3 and parts[0] == "mcp" and parts[1] in OWN_SERVERS and parts[2] in DIALOG_TOOLS


def _names_aidd_dialog(name: str) -> bool:
    """Whether a tool name is one of aidd's dialog tools under any harness's naming: Claude Code's and Codex's
    `mcp__aidd__land`, or OpenCode's `aidd_ship` (`mcp__opencode__aidd_ship` once the dialect names it)."""
    tool = name.rsplit("__", 1)[-1]
    return aidd_dialog(name) or (tool.startswith("aidd_") and tool[len("aidd_") :] in DIALOG_TOOLS)


def check_mcp_tool(name: str, tool_input: dict, *, dialogs_ask: bool = False) -> tuple[str, str]:
    """allow or deny for an MCP tool call (`mcp__<server>__<tool>`), by the rules in the module docstring. `dialogs_ask`:
    the harness is one whose MCP dialog is known to ask the person (Claude Code), so aidd's own dialog tools may run."""
    if _names_aidd_dialog(name):
        if dialogs_ask and aidd_dialog(name):
            return "allow", "aidd's own dialog: the person decides in it, and it refuses where the client cannot ask"
        return "deny", (
            f"MCP tool {name} asks the person for a decision in a dialog this harness is not known to show them. They decide "
            "by typing it at the prompt (`approve SPEC-1`, `land it`, `publish`, `merge it`), or with `aidd approve` in their own terminal. If they just "
            "typed it, aidd recorded it from their words before you read them: `aidd list` shows it, so go on with the work"
        )
    words = mcp_words(name.rsplit("__", 1)[-1])
    values = list(_strings(tool_input if isinstance(tool_input, dict) else {}))
    if _mcp_merges(words):
        return "deny", f"MCP tool {name} approves or merges: agents never approve or merge; a person does, once `aidd/gate` passes, so {verdicts.TELL_A_PERSON}"
    if _mcp_sets_status(words):
        return (
            "deny",
            f"MCP tool {name} sets a commit status: agents never approve or merge, and `aidd/gate` is the gate's own status. Leave statuses to CI, and report what you found",
        )
    if {"review", "reviews"} & set(words) and any(v.strip().upper() in ("APPROVE", "APPROVED") for v in values):
        return "deny", f"MCP tool {name} submits an approving review: agents never approve or merge; a person reviews. Post your findings as a comment instead"
    if any(_APPROVAL_LINE.search(v) for v in values):
        return "deny", f"MCP tool {name} carries `/aidd approve`: agents never approve; the author or an Approver posts it. Leave the line out, and ask them"
    return "allow", "MCP tool that neither approves nor merges"
