"""The generated tables the control differentials read: identities in every form a writer could give, and Specs over every value of
the risk fields and the triage fields, and planned paths under every change type. tests/fixtures/start-answers/ holds what aidd
answered for each row on the commit before `role:`, `irreversible`, and `backfill_due` became the one form (a1c04f10), and, for
routes.json, on the commit before the change types became nine (cd5359b1), so a later reading can only refuse more, never less.

Rebuild an answers file only on purpose, with the reason in the commit: `python3 tests/control_tables.py` prints the answers
the code in `src/` gives now."""

from __future__ import annotations

import itertools
import json
import sys

from helpers import ROOT

ANSWERS = ROOT / "tests" / "fixtures" / "start-answers"

# Each prefix a writer could type, honest or not: the typed forms, a tenant before them, the cases, a fullwidth letter, a zero-width
# space, a Cyrillic `о`, an accent, a space, and near misses.
PREFIXES = (
    "",
    "@",
    "agent:",
    "role:",
    "email:",
    "person:",
    "acme:",
    "acme:agent:",
    "acme:role:",
    "acme:email:",
    "Agent:",
    "AGENT:",
    "Role:",
    "ROLE:",
    "\uff52ole:",
    "ro​le:",
    "rоle:",
    "rôle:",
    "róle:",
    " role:",
    "role:role:",
    "roles:",
    "agents:",
    "role-x:",
)
VALUES = (
    "architect",
    "developer",
    "product-manager",
    "alice",
    "Alice",
    "claude",
    "jean-claude",
    "claude-code/claude-opus-5-5",
    "alice@example.com",
    "noreply@anthropic.com",
    "org/team",
    "dependabot[bot]",
    "github-actions",
    "José",
    "Nguyễn",
    "Ольга",
    "李",
    "a:b",
    "",
)
# Whole values that are no prefix and a value: git's trailer form, an address alone, and a person's name with a colon.
WHOLE = (
    "Devin Lee <devin@example.com>",
    "José García <jose@example.com>",
    "Claude <noreply@anthropic.com>",
    "<alice@example.com>",
    "Jean:Paul",
    "jean:paul",
    "acme:@alice",
    "role",
    "agent",
)


def identities() -> list[str]:
    """Every identity of the table, in one order."""
    return [p + v for p, v in itertools.product(PREFIXES, VALUES)] + list(WHOLE)


def risk_specs() -> dict[str, dict]:
    """A Spec's front matter for each route, dimension set, change type, and `risk.reversible` (true, false, or absent), the shape
    before 1.0.0, by a key that names them."""
    out = {}
    for route, dims, ctype, rev in itertools.product(("normal", "major"), ([], ["data"]), ("feat", "data"), (True, False, None)):
        risk: dict = {"summary": "s", "dimensions": dims}
        if rev is not None:
            risk["reversible"] = rev
        key = f"{route}|{','.join(dims) or '-'}|{ctype}|{'absent' if rev is None else str(rev).lower()}"
        out[key] = {"type": "spec", "id": "SPEC-1", "route": route, "change_type": ctype, "risk": risk, "tasks": [{"id": "T1", "scope": ["src/a/"]}]}
    return out


SUGGESTERS = (
    "",
    "@alice",
    "agent:product-manager",
    "agent:architect",
    "agent:claude-code/claude-opus-5-5",
    "agent:",
    "role:product-manager",
    "role:architect",
    "Role:architect",
    "acme:role:architect",
    "acme:agent:architect",
    "dependabot[bot]",
    "claude",
)
PROACTIVE = (None, [], ["product-manager"], ["architect", "product-manager"])
STATUSES = (None, "draft", "ready", "approved")
TRIAGES = (None, {"decision": "accepted", "by": "@p", "decided_on": "2026-10-01"}, {"decision": "declined", "by": "@p", "decided_on": "2026-10-01"})


def triage_cases() -> dict[str, tuple[dict, list[str] | None]]:
    """A Spec's front matter and the proactive roles, for each suggester, list, status, and triage, by a key that names them."""
    out = {}
    for who, proactive, status, triage in itertools.product(SUGGESTERS, PROACTIVE, STATUSES, TRIAGES):
        data: dict = {"type": "spec", "id": "SPEC-1"}
        if who:
            data["suggested_by"] = who
        if status:
            data["status"] = status
        if triage:
            data["triage"] = dict(triage)
        key = json.dumps([who, proactive, status, (triage or {}).get("decision")], ensure_ascii=False)
        out[key] = (data, proactive)
    return out


# The change types before 1.0.0, five of which were retired for a type and a dimension (schemas/retired-names.json).
CHANGE_TYPES_BEFORE = ("feat", "fix", "refactor", "perf", "docs", "test", "build", "ci", "chore", "deps", "infra", "data", "security", "compliance")


def route_cases() -> dict[str, tuple[str, list[str], str]]:
    """A profile, planned paths, and a change type, for a path of each built-in area, a file in none, and a glob, under each
    profile, by a key that names them."""
    from aidd import risk
    from aidd.kernel import globs

    paths = sorted({globs.sample_path(area["paths"][0]) for area in risk.builtin()["areas"].values() if area.get("paths")})
    paths += ["README.md", "garden/ember.txt", "src/app.py", "src/", "**/*.py"]
    return {f"{profile}|{p}|{t}": (profile, [p], t) for profile in ("solo", "team") for p in paths for t in CHANGE_TYPES_BEFORE}


def route_answer(profile: str, paths: list[str], change_type: str) -> dict:
    """What `aidd risk --paths` answers for a case. A retired type is given as the flags its retired-names row says to type now,
    so a table written before the retirement compares with the same request typed today."""
    from aidd import config, risk
    from aidd.cli import arguments
    from aidd.kernel import retired_names

    flags = ["--change-type", change_type]
    if change_type not in arguments.CHANGE_TYPES:
        flags = next(r["new"] for r in retired_names.rows("cli_value") if r["old"] == f"--change-type {change_type}").split()
    pairs = dict(zip(flags[::2], flags[1::2], strict=True))
    extra = {"declared": risk.DeclaredRisk((pairs["--dimension"],))} if "--dimension" in pairs else {}
    cfg = config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["@x"]\n')
    a = risk.advice(cfg, paths, change_type=pairs.get("--change-type", "feat"), **extra)
    return {"route": a["route"], "dimensions": a["dimensions"], "edit": a["edit"]["level"], "spec_approval": a["spec_approval"]}


def answers_now() -> dict[str, dict]:
    """What the code in `src/` answers for every table, as the answers files hold it."""
    from aidd import config, workitems
    from aidd.workitems import triage

    return {
        "identities": {i: {"is_agent": config.is_agent(i), "approved_by_kind": config.approved_by_kind(i)} for i in identities()},
        "required-docs": {k: sorted(f"{a.doc_type} {a.level} {a.living}" for a in workitems.required_docs(d, None)) for k, d in risk_specs().items()},
        "routes": {k: route_answer(*case) for k, case in route_cases().items()},
        "triage": {k: len(triage.triage_errors(d, proactive=p)) for k, (d, p) in triage_cases().items()},
    }


if __name__ == "__main__":
    json.dump(answers_now(), sys.stdout, ensure_ascii=False, indent=1, default=str)
