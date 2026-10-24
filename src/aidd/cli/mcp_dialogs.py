"""What aidd's MCP server shows the person in a client's dialog (elicitation): the lines for each kind of decision,
what approving records, and the one question, with the safe answer first and the default, so a form sent untouched
approves nothing. cli/mcp_server.py asks and records; this module only words it."""

from __future__ import annotations

from aidd import workitems

APPROVE, NOT_NOW = "Approve", "Not now"


def what(shown: dict) -> str:
    """What the person approves, in a few words: `SPEC-1`, `merging feat/x`, `landing feat/x on main`, `publishing
    feat/x`, or `approving for you`."""
    if shown.get("items"):
        return ", ".join(x["id"] for x in shown["items"])
    if shown["kind"] == "decide":
        return f"{shown['decision']} on {shown['id']}"
    if shown["kind"] == "sign-off":
        return f"the sign-off of {shown['id']}"
    if shown["kind"] == "all":
        publish = " and publishing" if "and-publish" in shown["scope"] else ""
        return f"approving{publish} for you" + (", except on major changes" if shown["scope"].endswith("but-major") else "")
    if shown["kind"] == "land":
        return f"landing {shown['branch']} on {shown['base_branch']}"
    if shown["kind"] == "publish":
        return f"publishing {shown['branch']} to {shown['remote']}"
    return shown["id"] if shown["kind"] == "spec" else f"merging {shown['branch']}"


def approval_request(shown: dict) -> dict:
    """The form-mode `elicitation/create` params: what is approved in a few lines, what changed outside the agent's
    session since the person's last decision, which their answer takes in, and one question."""
    kind = "specs" if shown.get("items") else shown["kind"]
    lines, record = _LINES.get(kind, _merge_lines)(shown)
    lines += [*(f"Note: {w}" for w in shown.get("warnings") or []), *outside_lines(shown)]
    lines += [f"{'Landing makes' if shown['kind'] == 'land' else 'Approving records'} {record}."]
    return {
        "mode": "form",
        "message": "\n".join(lines),
        "requestedSchema": {
            "type": "object",
            "properties": {"decision": {"type": "string", "title": f"Approve {what(shown)}?", "enum": [NOT_NOW, APPROVE], "default": NOT_NOW}},
            "required": ["decision"],
        },
    }


def outside_lines(shown: dict) -> list[str]:
    """What changed outside the agent's session since the person's last decision, as the dialog lists it before they
    answer: their answer takes it in as theirs, and each line says how to put it back (guard/outside_changes.py)."""
    changes = [c for x in (shown.get("items") or [shown]) for c in x.get("outside_changes") or []]
    seen = list({c["what"]: c for c in changes}.values())
    if not seen:
        return []
    return ["Since your last decision, this also changed outside the agent's session, and counts as yours with this answer:"] + [
        f"- {c['what']}{' (it weakens the guard)' if c.get('held') else ''} (to put it back: {c['restore']})" for c in seen
    ]


def _specs_lines(shown: dict) -> tuple[list[str], str]:
    """Several Specs in one dialog: each shown as its own dialog would show it (its risk, what changed since the person
    last approved it, and its warnings), then what approving records."""
    lines: list[str] = []
    for x in shown["items"]:
        one, _ = _spec_lines(x)
        lines += [*one, *(f"Note ({x['id']}): {w}" for w in x.get("warnings") or []), ""]
    return lines[:-1], f"your Spec approval of each of these {len(shown['items'])} Specs, each for exactly its hash"


def _spec_lines(shown: dict) -> tuple[list[str], str]:
    n = len(shown.get("acceptance") or [])
    lines = [
        f"{shown['id']}: {shown.get('title') or ''}",
        f"Acceptance: {n} item{'' if n == 1 else 's'}" + (f" ({', '.join(shown['acceptance'])})" if n else ""),
        f"Commit {shown['commit'][:12]} ({shown['ref']})",
        *([f"Risk: {shown['risk']}"] if shown.get("risk") else []),
        *([f"Revised: {shown['revised']}"] if shown.get("revised") else []),
    ]
    if since := shown.get("since"):
        # A re-approval: what changed since the person last approved, so they approve the change, not the title.
        lines.append(workitems.since_text(since).rstrip())
    return lines, "your Spec approval of exactly this hash"


def _standing_lines(shown: dict) -> tuple[list[str], str]:
    but = ", except on major changes," if shown["scope"].endswith("but-major") else ""
    publish = ", and publish each reviewed change (push it, and open its PR/MR)" if "and-publish" in shown["scope"] else ""
    lines = [
        f"Let the agent record every Spec approval and Merge approval{publish} for you{but} until {shown.get('until') or 'you stop it'}.",
        "Each record cites this one. The gate still runs on every change. To end it any time: `/aidd stop`, or type `stop approving`.",
    ]
    return lines, "your standing approval"


def _land_lines(shown: dict) -> tuple[list[str], str]:
    waits = ", ".join(shown.get("pending") or []) or "nothing else"
    lines = [
        f"Land {shown['branch']} at {shown['head'][:12]} into {shown['base_branch']}" + (" as one squashed commit" if shown.get("squash") else ""),
        f"Changed: {shown.get('changed') or 'nothing'}",
        f"The tests run again first, on what lands; it lands only if they pass. Besides your approval the gate waits on {waits}.",
    ]
    return lines, f"the merge into {shown['base_branch']}, and your Merge approval of this head when the gate still needs it"


def _publish_lines(shown: dict) -> tuple[list[str], str]:
    n = shown.get("commits") or 0
    lines = [
        f"Publish {shown['branch']} at {shown['head'][:12]} to {shown['remote']}/{shown['to']} ({', '.join(shown.get('urls') or []) or 'no URL'})"
        + (f", then a pull request into {shown['base']}" if shown.get("pull_request") else ""),
        f"{n} commit{'' if n == 1 else 's'} the remote lacks" + (":" if shown.get("shown") else ""),
        *(f"  {c}" for c in shown.get("shown") or []),
    ]
    return lines, "your publish of exactly this head to this remote, then pushes it"


def _merge_lines(shown: dict) -> tuple[list[str], str]:
    waits = ", ".join(shown.get("pending") or []) or "nothing else"
    lines = [
        f"Merge {shown['branch']} at {shown['head'][:12]}" + (f" ({shown['spec']})" if shown.get("spec") else ""),
        f"Changed: {shown.get('changed') or 'nothing'}",
        f"Gate: {shown['decision']}; besides your approval it waits on {waits}",
        *([f"It still fails on {', '.join(shown['failing'])}: your approval is recorded, and the merge waits for that fix."] if shown.get("failing") else []),
    ]
    return lines, "your Merge approval of exactly this head commit"


def _proposal_lines(shown: dict) -> tuple[list[str], str]:
    """A proposal decision's dialog lines, and what approving records."""
    lines = [f"{shown['id']}: {shown.get('title') or ''}", f"File: {shown['path']}", f"For: {shown.get('addressee') or 'nobody named'}"]
    if shown["kind"] == "decide":
        lines.append(f"Decision: {shown['decision']}" + (f", because {shown['reason']}" if shown.get("reason") else ""))
        record = f"your {shown['decision']}, as {shown['by']}, in the proposal for you to commit"
    else:
        lines.append("Means: it may be sent, as it reads now, with its price, commitments, assumptions, and exclusions")
        record = f"your sign-off of exactly this text, as {shown['by']}, in the proposal for you to commit"
    if shown.get("replaces"):
        lines.append(f"Replaces: {shown['replaces']}")
    return lines, record


# Each dialog's lines and what approving records, by the kind of decision (a merge when none matches).
_LINES = {
    "specs": _specs_lines,
    "spec": _spec_lines,
    "decide": _proposal_lines,
    "sign-off": _proposal_lines,
    "all": _standing_lines,
    "land": _land_lines,
    "publish": _publish_lines,
}
