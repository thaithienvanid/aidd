"""Render a Decision for terminals, PR summaries, commit statuses, and metrics."""

from __future__ import annotations

from aidd import __version__
from aidd.gate.engine import Decision
from aidd.kernel import resources
from aidd.kernel.text import md_cell
from aidd.kernel.timestamps import utc_stamp

# The version of the event line's shape (schemas/event.schema.json). A new optional field keeps it; a renamed, removed,
# or retyped field bumps it, so a consumer can tell two shapes apart.
EVENT_SCHEMA_VERSION = "1"

_ICON = {"fail": "FAIL", "pending": "WAIT", "warn": "WARN"}
_MD_ICON = {"fail": ":x:", "pending": ":hourglass:", "warn": ":warning:"}


_SPEC_PHASE_FIRST = ("spec_approval", "specialist_approval")
SPEC_PHASE_LINE = (
    "Spec phase: the change holds only the Spec and its frozen files, so the gate waits for Spec approval first. Failing tests are expected until Implement"
)


def _by_level(d: Decision) -> list:
    """Worst first; in the Spec phase, Spec approval leads, because it is the decision the change waits for."""
    first = d.record.get("phase") == "spec"
    return sorted(d.findings, key=lambda f: (first and f.rule not in _SPEC_PHASE_FIRST, ("fail", "pending", "warn").index(f.level)))


def decision_text(d: Decision) -> str:
    r = d.record
    lines = [
        f"aidd gate: {d.decision.upper()}" + ("" if d.trusted else " (local, untrusted)"),
        f"  change {r.get('change')}  head {str(r.get('head_sha'))[:12]}  profile {r.get('profile', '?')}",
    ]
    if r.get("route"):
        lines.append(
            f"  route {r['route']} (required {r.get('required_route', '?')})  type {r.get('type')}  "
            f"lines {r.get('changed_lines', 0)}  files {r.get('changed_files', 0)}"
        )
    if r.get("phase") == "spec":
        lines.append(f"  {SPEC_PHASE_LINE}")
    for f in _by_level(d):
        lines.append(f"  [{_ICON[f.level]}] {f.rule}: {f.message}")
        lines += [("        fix: " if i == 0 else "             ") + fl for i, fl in enumerate(f.fix.splitlines())]
    if not d.findings:
        lines.append("  every gate holds")
    lines += [f"  note: {n}" for n in d.notes]
    return "\n".join(lines)


def decision_markdown(d: Decision) -> str:
    r = d.record
    head = f"### aidd gate: **{d.decision}**" + ("" if d.trusted else " (local, untrusted)")
    out = [head, ""] + ([f"> {SPEC_PHASE_LINE}.", ""] if r.get("phase") == "spec" else [])
    specialists = ", ".join(f"{pool}: {', '.join(users) or 'none'}" for pool, users in (r.get("specialist_approved_by") or {}).items())
    rows = [
        ("Tenant", r.get("tenant")),
        ("Profile", r.get("profile")),
        ("Route", f"{r.get('route')} (required: {r.get('required_route')})" if r.get("route") else None),
        ("Spec", r.get("spec")),
        ("Type", r.get("type")),
        ("Head", f"`{str(r.get('head_sha'))[:12]}`"),
        ("Changed", f"{r.get('changed_files', 0)} files, {r.get('changed_lines', 0)} lines" if "changed_lines" in r else None),
        ("Spec hash", f"`{r['spec_hash']}`" if r.get("spec_hash") else None),
        ("Spec approved by", ", ".join(r.get("spec_approved_by", [])) or None),
        ("Approved by", ", ".join(r.get("approved_by", [])) or None),
        ("Specialist approval", specialists or None),
        ("Separation of duties", r.get("separation_of_duties")),
        ("Policy", r.get("policy")),
        ("Assisted by", ", ".join(r.get("assisted_by") or []) or None),
    ]
    out += ["| | |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in rows if v]
    if r.get("tests"):
        out += ["", "| Test | Source | Exit | Status | Seconds |", "| --- | --- | --- | --- | --- |"]
        out += [
            f"| `{c['name']}` | {c['source']} | {c['exit']} | {c['status']} | {c.get('duration_seconds') if c.get('duration_seconds') is not None else ''} |"
            for c in r["tests"]
        ]
    if d.findings:
        out += ["", "| | Rule | Finding | Fix |", "| --- | --- | --- | --- |"]
        for f in _by_level(d):
            out.append(f"| {_MD_ICON[f.level]} | `{f.rule}` | {md_cell(f.message, '<br>')} | {md_cell(f.fix, '<br>')} |")
    if d.notes:
        out += [""] + [f"> {md_cell(n, '<br>')}" for n in d.notes]
    if r.get("route_reasons"):
        out += ["", "<details><summary>Route reasons</summary>", ""] + [f"- {md_cell(x, '<br>')}" for x in r["route_reasons"]] + ["", "</details>"]
    return "\n".join(out) + "\n"


def status_line(d: Decision) -> str:
    """At most 140 characters, for a commit status description."""
    if d.decision == "pass":
        msg = f"pass: {d.record.get('route')} route, every gate holds"
    else:
        first = next((f for f in _by_level(d) if f.level == d.decision), None)
        msg = f"{d.decision}: {first.rule}: {first.message}" if first else d.decision
    if d.record.get("shared_with"):
        msg = f"head shared with PR {d.record['shared_with']}: {msg}"
    msg = " ".join(msg.split())
    return msg if len(msg) <= 140 else msg[:137] + "..."


def loop_version() -> str:
    """The loop contract's version (`loop.version` in roles.json), recorded on every gate event so metrics can tell
    two loops apart."""
    return str(resources.load_json("roles.json")["loop"]["version"])


def event_header() -> dict:
    return {"schema_version": EVENT_SCHEMA_VERSION, "aidd_version": __version__, "loop_version": loop_version(), "ts": utc_stamp()}


def error_event(repo: str, change: str, exc: BaseException, *, mode: str = "enforce", run_url: str | None = None, tenant: str | None = None) -> dict:
    """The event line for a run that crashed: the audit trail shows the gap, and metrics count it. `tenant` is the org
    preset's, when the run got that far; the repository's own config was not read."""
    return event_header() | {
        "repo": repo,
        "tenant": tenant,
        "change": change,
        "head_sha": "",
        "profile": None,
        "decision": "error",
        "error": type(exc).__name__,
        "failed_rules": [],
        "pending_rules": [],
        "mode": mode,
        "run_url": run_url,
    }


def decision_event(
    d: Decision, repo: str | None = None, *, author: str | None = None, base_ref: str | None = None, mode: str = "enforce", run_url: str | None = None
) -> dict:
    r = d.record
    ev = event_header() | {
        "repo": repo or "",
        "tenant": r.get("tenant"),
        "change": str(r["change"]) if r.get("change") is not None else "",
        "head_sha": r.get("head_sha") or "",
        "spec": r.get("spec"),
        "spec_id": r.get("spec_id"),
        "spec_hash": r.get("spec_hash"),
        "trace_id": r.get("trace_id"),
        "owner_team": r.get("owner_team"),
        "route": r.get("route"),
        "required_route": r.get("required_route"),
        "declared_route": r.get("declared_route"),
        "type": r.get("type"),
        "profile": r.get("profile"),
        "decision": d.decision,
        "failed_rules": d.rules_at("fail"),
        "pending_rules": d.rules_at("pending"),
        "changed_files": int(r.get("changed_files", 0)),
        "changed_lines": int(r.get("changed_lines", 0)),
        "approvals": len(r.get("approved_by", [])),
        "untouched_tasks": len((r.get("plan") or {}).get("untouched_tasks", [])),
        "assisted_by": list(r.get("assisted_by") or []),
        "tests": [
            {"name": c["name"], "red_green": "green", "status": c["status"], "duration_seconds": c.get("duration_seconds")}
            | ({"flaky": True} if c.get("flaky") else {})
            for c in r.get("tests", [])
        ],
        "platform": r.get("platform"),
        "author": author,
        "base_ref": base_ref,
        "mode": mode,
        "config_sha256": r.get("config_sha256"),
        "run_url": run_url,
        # When the change was opened and its head pushed: the start of time to first feedback.
        "opened_at": d.timing.get("opened_at"),
        "head_pushed_at": d.timing.get("head_pushed_at"),
    }
    from aidd.kernel import json_schema

    errs = json_schema.validate(ev, "event.schema.json")
    if errs:
        raise RuntimeError(f"invalid gate event: {'; '.join(errs)}")
    return ev
