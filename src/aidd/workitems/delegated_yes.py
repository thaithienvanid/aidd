"""What `aidd validate` warns about a delegated yes: a Spec's `delegate_answer` that no delegate's accept on record
backs, and a commit whose `Decided-by`, `On-behalf-of`, or `Delegation` trailer is malformed or stands beside
`Approved-by` or `Agreed-by`. A warning blocks nothing: the delegate check, run again at the hook, is what holds."""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config, records
from aidd.kernel import documents, git

TRAILERS = ("Decided-by", "On-behalf-of", "Delegation")
# A person's own yes: a delegated yes never stands beside either, and `Agreed-by` is the Intent's.
PERSONS_YES = ("Approved-by", "Agreed-by")
_SHAPES = {
    "Decided-by": re.compile(r"^agent:\S+$"),
    "On-behalf-of": re.compile(r"^[^<>\n]+ <[^<>@\s]+@[^<>\s]+>$"),
    "Delegation": re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$"),
}


def spec_warnings(root: Path, path: str, data: dict) -> list[str]:
    """A Spec's `delegate_answer` with an `approved_by` beside it, or with no delegate's accept of this Spec on record."""
    rid = data.get("delegate_answer")
    if data.get("type") != "spec" or not rid:
        return []
    out = []
    if data.get("approved_by"):
        out.append(f"{path}: delegate_answer and approved_by are both set; a delegated approval names no person as approver, so drop approved_by")
    try:
        accepts = {r["id"] for r in records.delegate_accepts(str(root), str(data.get("id")))}
    except (git.GitError, OSError):
        return out
    if str(rid) not in accepts:
        out.append(
            f"{path}: delegate_answer {documents.one_line(str(rid))} is no delegate's accept of {data.get('id')} in this clone's records; ask the person for Spec approval"
        )
    return out


def trailer_problems(message: str) -> list[str]:
    """What is wrong with a commit's delegated-yes trailers: one missing, one malformed, or a person's own yes, `Approved-by`
    or `Agreed-by`, beside them."""
    lines = {k: v.strip() for k, _, v in (ln.partition(":") for ln in message.splitlines()) if k in (*TRAILERS, *PERSONS_YES)}
    present = [t for t in TRAILERS if t in lines]
    if not present:
        return []
    out = [f"no {t} trailer beside the others" for t in TRAILERS if t not in lines]
    out += [
        f"{t}: {documents.one_line(lines[t], 80)!r} is not {('agent:<harness>/<who>', 'Name <email>', 'a commit id')[TRAILERS.index(t)]}"
        for t in present
        if not _SHAPES[t].match(lines[t])
    ]
    if "Decided-by" in lines and not config.is_agent(lines["Decided-by"]):
        out.append("Decided-by names a person; a delegated yes names the delegate")
    out += [f"{k} stands beside the delegation's trailers; {k} is a person's own yes, so drop it" for k in PERSONS_YES if k in lines]
    return out


def commit_warnings(root: Path) -> list[str]:
    """Each commit since the default branch whose delegated-yes trailers `trailer_problems` finds wrong."""
    try:
        base = git.branch_base(str(root))
        shas = [r[0] for r in git.log_fields([f"{base}..HEAD"], ["%H"], str(root), check=False)][:200]
        said = git.messages(shas, str(root)) if shas else {}
    except (git.GitError, OSError, ValueError):
        return []
    return [f"commit {sha[:12]}: {p}" for sha in shas for p in trailer_problems(said.get(sha, ""))]
