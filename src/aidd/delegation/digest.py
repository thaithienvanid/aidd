"""The digest: what `aidd status` shows a person of what a delegation decided for them. It starts from git, so a
delegated commit with no answer on record is named, not hidden."""

from __future__ import annotations

from aidd import records
from aidd.kernel import documents, git

# The most answers the digest lists, newest first, so it fits one screen.
MAX_ANSWERS = 10


def unrecorded(cwd: str, branch: str) -> list[str]:
    """Each commit on `branch` whose message carries a `Delegation:` trailer, as its short id, when no delegate's accept
    on record covers its tree. A merge of a head that holds the tip has the head's tree, so the accept names it."""
    accepted = {
        (r["data"].get("covers") or {}).get("tree")
        for r in records.read_records(cwd, record_type="delegate_answer")[0]
        if (r.get("data") or {}).get("outcome") == "accept"
    }
    rows = git.log_fields(["--first-parent", "-n", "200", branch], ["%H", "%T"], cwd, check=False)
    shas = [sha for sha, _tree in rows]
    said = git.messages(shas, cwd) if shas else {}
    trailer = lambda sha: any(line.startswith("Delegation:") for line in said.get(sha, "").splitlines())  # noqa: E731
    return [sha[:12] for sha, tree in rows if trailer(sha) and tree not in accepted]


def digest_text(cwd: str, branch: str) -> str:
    """The lines `aidd status` adds under a delegation: any delegated commit with no answer on record first, then each
    answer, newest first."""
    lines = [f"Not on record: {sha} carries a Delegation trailer, but no delegate's accept covers it. Check it yourself." for sha in unrecorded(cwd, branch)]
    answers = records.read_records(cwd, record_type="delegate_answer")[0][:MAX_ANSWERS]
    for rec in answers:
        data = rec.get("data") or {}
        head = str((data.get("covers") or {}).get("head", ""))[:12]
        lines.append(f"{rec.get('at', '')}  {data.get('action')} {data.get('outcome')} on {head}: {documents.one_line(str(data.get('reason', '')), 120)}")
    if not lines:
        return "Decided for you: nothing yet. `aidd delegate stop` turns the delegation off.\n"
    return "Decided for you, newest first (`aidd delegate stop` turns it off):\n" + "".join(f"  {line}\n" for line in lines)
