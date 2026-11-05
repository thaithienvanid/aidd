"""The checks `aidd validate` runs on Intents: unique slices, a Spec under the Intent that lists it, who agreed, an
agreement that a later change to the slices or the goal left behind, and the brief coverage table.

Order, names, dates, and the other slice fields are bookkeeping, so changing them never asks for a new agreement. A
slice added or removed, or a new `goal`, changes what the person agreed to, so it warns until a person agrees again.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, resources
from aidd.workitems import delegated_yes, intents, spec_file

COVERAGE = "Brief coverage"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_DEFERRED = re.compile(r"deferred,\s*asked\b[\s:,;-]*(.*)", re.I | re.S)
_NON_GOAL = "the brief's non-goal"
_TABLE_RULE = re.compile(r"\|[\s|:-]*\|")
_FIRST_SLICE = re.compile(r"^###[ \t]+First slice[ \t]*\n(.*?)(?=^#{1,3}[ \t]|\Z)", re.S | re.M)
_LINE_OF_SLICE = re.compile(r"(.+?)\s+(A[1-9][0-9]{0,3})")
_PHASE_EXIT = re.compile(r"exit:\s*(\S+)", re.I)


def _first_slice(data: dict, text: str) -> tuple[str, set[str]]:
    """The first slice's id and the ids of the acceptance lines its `### First slice` lists, the ids empty when it lists none."""
    ids = intents.slice_ids(data)
    block = _COMMENT.sub("", m.group(1)) if (m := _FIRST_SLICE.search(text)) else ""
    return (ids[0] if ids else ""), set(spec_file.ACCEPTANCE_ID.findall(block))


def _proof_problem(proof: str, known: set[str], phases: set[str], first: tuple[str, set[str]]) -> str:
    """What is wrong with one proof in a row's cell, or empty when it stands."""
    if proof in known:
        return ""
    if m := _PHASE_EXIT.fullmatch(proof):
        return "" if m.group(1) in phases else "no phase of this Intent; name a phase it lists, as `exit: P1`"
    if (m := _LINE_OF_SLICE.fullmatch(proof)) and m.group(1) in known:
        if m.group(1) != first[0] or m.group(2) in first[1]:
            return ""
        return f"no acceptance line of the first slice; name a line its `### First slice` lists ({', '.join(sorted(first[1])) or 'it lists none'})"
    return f"no slice of this Intent; name a slice it lists, `SPEC-1 A3`, `exit: P1`, `deferred, asked: <question>`, or `{_NON_GOAL}`"


def coverage_findings(path: object, text: str, data: dict) -> list[str]:
    """The checks on an Intent's `## Brief coverage` table, one row for each success criterion and hard constraint of the
    brief. Each row names its proof, comma-separated: a slice, a slice with its acceptance line (`SPEC-1 A3`), or a
    phase's exit criterion (`exit: P1`). Or it says `deferred, asked` with the question put to the person, or `the brief's
    non-goal`. An empty cell, a row naming none of these, a slice or phase the Intent does not list, and a line the first
    slice's `### First slice` does not list are errors. A later slice's acceptance is written when it starts, so a line of
    it is not checked. A row that still holds a TODO is left to the placeholder reminder. An Intent with phases and no section is a warning,
    because an Intent may start from an idea with no brief: the section then says so in one line."""
    if data.get("type") != "intent" or not isinstance(data.get("phases"), list) or not data["phases"]:
        return []
    if not documents.markdown_section(text, COVERAGE):
        return [
            f"warning: {path}: no '## {COVERAGE}' section; add one row for each success criterion and hard constraint of the brief, "
            "or one line that says there is no brief"
        ]
    known = set(intents.slice_ids(data))
    phases = {str(p["id"]) for p in intents.phases_of(data) if p.get("id")}
    first = _first_slice(data, text)
    out: list[str] = []
    lines = [ln.strip() for ln in _COMMENT.sub("", documents.raw_section(text, COVERAGE)).splitlines() if ln.strip().startswith("|")]
    rule = next((i for i, ln in enumerate(lines) if _TABLE_RULE.fullmatch(ln)), None)
    for row in lines[rule + 1 :] if rule is not None else []:
        cells = [c.strip().strip("`").strip() for c in row.strip("|").split("|")]
        item, where = cells[0], " ".join(cells[1:]).strip()
        if "TODO" in row:
            continue
        label = documents.one_line(item, 60)
        if not item or not where:
            out.append(f"{path}: a {COVERAGE} row is empty ({label or row}); name the slice, `deferred, asked`, or `{_NON_GOAL}`")
        elif m := _DEFERRED.fullmatch(where):
            if not m.group(1).strip():
                out.append(f"{path}: {COVERAGE} row '{label}' is deferred with no question; name the question put to the person")
        elif where.lower().rstrip(".") != _NON_GOAL:
            for proof in (x.strip() for x in where.split(",")):
                if problem := _proof_problem(proof, known, phases, first):
                    out.append(f"{path}: {COVERAGE} row '{label}' names {proof}, which is {problem}")
    return out


def intent_findings(objects: list[tuple[str, dict]]) -> tuple[list[str], list[str]]:
    """(errors, warnings) across the repository's Intents and Specs: a slice id listed twice, an agent in `agreed_by`, a
    Spec whose `parent` Intent lists no slice of its id, and a slice whose Spec names another parent."""
    errors: list[str] = []
    warnings: list[str] = []
    listed: dict[str, str] = {}
    by_id = {str(d.get("id")): (p, d) for p, d in objects if d.get("id")}
    for p, d in objects:
        if d.get("type") != "intent":
            continue
        seen: set[str] = set()
        for phase in intents.phases_of(d):
            for line in intents.slices_of(phase):
                sid = str(line["id"])
                if sid in seen:
                    errors.append(f"{p}: slice {sid} is listed twice; keep one line for it")
                elif sid in listed:
                    errors.append(f"{p}: slice {sid} is also a slice of {listed[sid]}; a slice belongs to one Intent")
                seen.add(sid)
                listed.setdefault(sid, p)
                spec = by_id.get(sid)
                if spec and spec[1].get("type") == "spec" and str(spec[1].get("parent") or "") != str(d.get("id")):
                    warnings.append(f"{spec[0]}: {p} lists it as a slice, so set its `parent: {d.get('id')}`")
    for p, d in objects:
        parent = by_id.get(str(d.get("parent") or ""))
        if d.get("type") == "spec" and parent and parent[1].get("type") == "intent" and str(d.get("id")) not in intents.slice_ids(parent[1]):
            warnings.append(
                f"{p}: its parent {parent[1].get('id')} lists no slice {d.get('id')}; add the slice line to the Intent, and ask the person to agree to it again"
            )
    return errors, warnings


@functools.cache
def _agreed_at_pattern() -> str:
    """The pattern the Intent schema gives `agreed_at`, its one owner."""
    return str(resources.load_json("intent.schema.json")["properties"]["agreed_at"]["pattern"])


def _front_matter_at(root: Path, sha: str, rel: str) -> dict | None:
    text = git.show(sha, rel, str(root))
    try:
        data, _ = documents.split_front_matter(text or "", rel)
    except documents.DocumentError:
        return None
    return data if isinstance(data, dict) else None


def _agreement_commit(root: Path, rel: str, agreed_at: str, tip: str = "HEAD") -> tuple[str, dict] | None:
    """The first commit of `rel` whose parsed front matter holds `agreed_at`, with that front matter. It reads the parsed
    value, never the text, so a single-quoted value or a trailing comment finds the same commit, and another line of the
    file that holds the bare value does not. `agreed_at` is checked against the schema's RFC 3339 pattern first. It looks in
    the history of `tip`. None when no commit holds it, or git cannot say."""
    if not re.fullmatch(_agreed_at_pattern(), agreed_at):
        return None
    try:
        found = git.log_fields(["--reverse", tip, "--", rel], ["%H"], str(root), check=False)
    except git.GitError:
        return None
    for (sha,) in found:
        then = _front_matter_at(root, sha, rel)
        if then is not None and str(then.get("agreed_at")) == agreed_at:
            return sha, then
    return None


def _agreed_by_trailers(message: str) -> list[str]:
    """The values of the `Agreed-by` trailers in a commit message's last paragraph, the key in exactly that case; none
    when a delegated yes's trailer stands anywhere in the message, because a delegate's answer is not a person's."""
    keys = {k.lower() for k in delegated_yes.TRAILERS}
    if any(ln.partition(":")[0].strip().lower() in keys for ln in message.split("\n")):
        return []
    last = message.strip("\n").split("\n\n")[-1].split("\n")
    return [ln.partition(":")[2].strip() for ln in last if ln.partition(":")[0] == "Agreed-by"]


def agreed_version(root: Path, rel: str, data: dict, tip: str = "HEAD") -> dict | None:
    """The Intent's front matter as the person agreed to it, or None when no agreement stands. It fails closed: the file's
    `agreed_by` names a person (`approved_by_kind` finds nothing wrong), and `agreed_at` is an RFC 3339 time. The first
    commit whose front matter first holds that `agreed_at` has the same `agreed_by`, and carries an `Agreed-by` trailer of
    that value (any case of the value, the key in exactly that case) and no delegated yes's trailer. `aidd status` asks
    for the agreement until then. The caller compares the version with the file for a slice or a goal added since. `tip` is the commit whose history holds the file: a branch's, in `--all-branches`."""
    who = str(data.get("agreed_by") or "")
    at = str(data.get("agreed_at") or "")
    if not who or not at or config.approved_by_kind(who) is not None:
        return None
    found = _agreement_commit(root, rel, at, tip)
    if found is None:
        return None
    sha, then = found
    if config.normalize_identity(str(then.get("agreed_by") or "")) != config.normalize_identity(who):
        return None
    try:
        trailers = _agreed_by_trailers(git.messages([sha], str(root)).get(sha, ""))
    except git.GitError:
        return None
    if not trailers or {config.normalize_identity(v) for v in trailers} != {config.normalize_identity(who)}:
        return None
    return then


def agreement_problems(path: object, data: dict) -> list[str]:
    """`agreed_by` on one Intent: an error for an agent's name, which only a person may hold, and a warning for a form
    `approved_by` would not take. `aidd validate` gives them for one file and for the repository alike."""
    who = data.get("agreed_by") if data.get("type") == "intent" else None
    if not isinstance(who, str) or not who:
        return []
    if config.is_agent(who) or config.approved_by_kind(who) == "agent":
        return [f"{path}: agreed_by {who} names an agent or a bot; only a person agrees to an Intent, in the chat"]
    problem = config.approved_by_problem(who, "agreed_by")
    return [f"warning: {path}: {problem}"] if problem else []


def agreement_warnings(path: Path, data: dict, root: Path | None) -> list[str]:
    """A warning when a slice was added or removed, or `goal` changed, after the person agreed. It fails closed: an
    `agreed_at` that no commit recorded, or that git cannot read, warns as no agreement. Empty for an Intent nobody
    agreed to yet, which `aidd status` names as waiting for its agreement."""
    agreed_at = str(data.get("agreed_at") or "")
    if data.get("type") != "intent" or not agreed_at:
        return []
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix() if root is not None else ""
    except ValueError:
        rel = ""
    then = agreed_version(root, rel, data) if root is not None and rel else None
    if then is None:
        return [
            f"warning: {path}: no commit with an `Agreed-by:` trailer of {data.get('agreed_by')} records its agreement of {agreed_at}, so aidd "
            "reads it as not agreed. Ask the person to agree (`intent.agree`), then commit `agreed_by` and `agreed_at` with that trailer"
        ]
    if not (changed := intents.changes_since(then, data)):
        return []
    return [
        f"warning: {path}: {'; '.join(changed)} since {data.get('agreed_by')} agreed on {agreed_at}; ask the person to agree again "
        "(`intent.agree`), then record the new `agreed_by` and `agreed_at`"
    ]
