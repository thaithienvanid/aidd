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


def check_mcp_tool(name: str, tool_input: dict) -> tuple[str, str]:
    """allow or deny for an MCP tool call (`mcp__<server>__<tool>`), by the rules in the module docstring."""
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
