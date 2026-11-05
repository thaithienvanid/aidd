"""The checks `aidd validate` runs on Intents: unique slices, a Spec under the Intent that lists it, who agreed, an
agreement that a later change to the slices or the goal left behind, and the Request coverage table, in one Intent and across them.

Order, names, dates, and the other slice fields are bookkeeping, so changing them never asks for a new agreement. A
slice added or removed, or a new `goal`, changes what the person agreed to, so it warns until a person agrees again.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, resources, retired_names
from aidd.kernel.text import did_you_mean
from aidd.workitems import backlog, delegated_yes, ids, intents, old_shape, repo_reads, spec_file, status

COVERAGE = "Request coverage"
# A comment, or one that never closes, which hides the rest: one scan, however many `<!--` a crafted text holds.
_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_DEFERRED = re.compile(r"deferred,\s*asked\b[\s:,;-]*(.*)", re.I | re.S)
_NON_GOAL = "the request's non-goal"
# A request item a minor fix covers, which has no work item: the row says `minor fix` while the fix is open, then
# `merged_in <commit>` once it lands, as a minor slice's line records `merged_in`.
_MINOR_FIX = "minor fix"
_MERGED_IN = "merged_in"
_COMMIT = re.compile(r"[0-9a-fA-F]{7,40}")
# The most characters a check reads from one cell of the table: a longer cell is one error, before any pattern reads it.
MAX_CELL = 2000
_NO_PROOF = (
    "no slice of this Intent and no work item in the repository; name a slice it lists, `SPEC-1 A3`, `exit: P1`, "
    f"another work item's id, `deferred, asked: <question>`, `{_MINOR_FIX}`, `merged_in <commit>`, or `{_NON_GOAL}`"
)
# What `_proof_problem` says of an id this Intent does not hold: the caller looks it up among the other work items.
OUTSIDE = "outside"
# The most proofs a check reads from one Request coverage cell (`proofs_of`).
MAX_PROOFS = 20
_TABLE_RULE = re.compile(r"\|[\s|:-]*\|")
_FIRST_SLICE = re.compile(r"^###[ \t]+First slice[ \t]*\n(.*?)(?=^#{1,3}[ \t]|\Z)", re.S | re.M)
_LINE_OF_SLICE = re.compile(r"(.+?)\s+(A[1-9][0-9]{0,3})")
_PHASE_EXIT = re.compile(r"exit:\s*(\S+)", re.I)


def _first_slice(data: dict, text: str) -> tuple[str, set[str]]:
    """The first slice's id and the ids of the acceptance lines its `### First slice` lists, the ids empty when it lists none."""
    ids = intents.slice_ids(data)
    block = _COMMENT.sub("", m.group(1)) if (m := _FIRST_SLICE.search(text)) else ""
    return (ids[0] if ids else ""), set(spec_file.ACCEPTANCE_ID.findall(block))


def _proof_problem(proof: str, known: set[str], phases: set[str], first: tuple[str, set[str]], self_id: str) -> str:
    """What is wrong with one proof in a row's cell: empty when it stands on this Intent, or OUTSIDE when it is an id this
    Intent does not hold, which may be another work item."""
    if proof in known:
        return ""
    if m := _PHASE_EXIT.fullmatch(proof):
        return "" if m.group(1) in phases else "no phase of this Intent; name a phase it lists, as `exit: P1`"
    if (m := _LINE_OF_SLICE.fullmatch(proof)) and m.group(1) in known:
        if m.group(1) != first[0] or m.group(2) in first[1]:
            return ""
        return f"no acceptance line of the first slice; name a line its `### First slice` lists ({', '.join(sorted(first[1])) or 'it lists none'})"
    if proof == self_id:
        return "this Intent itself; name the work item that covers the item, or a slice of this one"
    return OUTSIDE if ids.is_id(proof) else _NO_PROOF


def _outside_finding(path: object, label: str, proof: str, items: Mapping[str, dict]) -> str:
    """The finding for a proof that names another work item: an error when no work item in the repository has that id,
    a warning when it is a closed Intent or Spec (done or cancelled), else empty."""
    item = items.get(proof)
    if item is None:
        return f"{path}: {COVERAGE} row '{label}' names {proof}, which is {_NO_PROOF}"
    kind = item.get("type")
    shut = status.intent_status(item, []) if kind == "intent" else status.spec_status(item) if kind == "spec" else ""
    if shut in status.INTENT_ENDED:  # a Spec that merged or was cancelled reads as an Intent a person closed
        return f"warning: {path}: {COVERAGE} row '{label}' names {proof}, but {proof} is {shut}; cover the item here, defer it with a question, or mark it {_NON_GOAL}"
    return ""


def _settling_problem(where: str) -> str | None:
    """What is wrong with a cell that settles its item without a slice, a phase, or a work item: a question asked
    (`deferred, asked: ...`), the request's non-goal, a minor fix still open, or one that landed (`merged_in <commit>`).
    Empty when it is right, and None when the cell is none of these."""
    if m := _DEFERRED.fullmatch(where):
        return "" if m.group(1).strip() else "is deferred with no question; name the question put to the person"
    if where.lower().rstrip(".") in (_NON_GOAL, _MINOR_FIX):
        return ""
    rest = where[len(_MERGED_IN) :]
    if where[: len(_MERGED_IN)].lower() == _MERGED_IN and not rest[:1].isalnum() and rest[:1] != "_":
        commit = rest.lstrip(" \t:")
        return "" if _COMMIT.fullmatch(commit) else "says merged_in with no commit; name the commit the minor fix landed in, as `merged_in 1a2b3c4`"
    return None


def proofs_of(where: str) -> tuple[list[str], bool]:
    """The proofs a row's cell names, comma-separated, at most MAX_PROOFS of them, and whether it names more. Repository
    text is another person's, so a check reads no more than that from one cell."""
    proofs = [x.strip() for x in where.split(",")]
    return proofs[:MAX_PROOFS], len(proofs) > MAX_PROOFS


def _too_long(item: str, where: str) -> bool:
    """Whether a row's item or cell is past MAX_CELL, so no pattern reads it."""
    return len(item) > MAX_CELL or len(where) > MAX_CELL


def coverage_rows(text: str) -> list[tuple[str, str, str]]:
    """Each row of the table under `## Request coverage`, as (the request's item, what covers it, the row), comments left out."""
    lines = [ln.strip() for ln in _COMMENT.sub("", documents.raw_section(text, COVERAGE)).splitlines() if ln.strip().startswith("|")]
    rule = next((i for i, ln in enumerate(lines) if _TABLE_RULE.fullmatch(ln)), None)
    out = []
    for row in lines[rule + 1 :] if rule is not None else []:
        cells = [c.strip().strip("`").strip() for c in row.strip("|").split("|")]
        out.append((cells[0], " ".join(cells[1:]).strip(), row))
    return out


def coverage_findings(path: object, text: str, data: dict, work_items: Callable[[], Mapping[str, dict]] | None = None) -> list[str]:
    """The checks on an Intent's `## Request coverage` table, one row for each success criterion and hard constraint of
    the request. Each row names its proof, comma-separated: a slice, a slice with its acceptance line (`SPEC-1 A3`), a
    phase's exit criterion (`exit: P1`), or another work item that covers the item, an Intent or a Spec (`INTENT-2`).
    Or it says `deferred, asked` with the question put to the person, `minor fix` or `merged_in <commit>` for a minor fix, or `the request's non-goal`.

    These are errors: an empty cell, a row naming none of these, a slice or phase the Intent does not list, a line the
    first slice's `### First slice` does not list, a work item that does not exist, and this Intent itself. A closed
    Intent is a warning. `work_items` gives the repository's work items by id. It is called at most once, and only for
    a proof this Intent does not hold; with none given, no other work item exists. A later slice's acceptance is written
    when it starts, so a line of it is not checked. A row that still holds a TODO is left to the placeholder reminder.
    An Intent with phases and no section is a warning, because an Intent may start from an idea with no request: the
    section then says so in one line."""
    if data.get("type") != "intent" or not isinstance(data.get("phases"), list) or not data["phases"]:
        return []
    if not documents.markdown_section(text, COVERAGE):
        return [
            f"warning: {path}: no '## {COVERAGE}' section; add one row for each success criterion and hard constraint of the request, "
            "or one line that says there is no request"
        ]
    known = set(intents.slice_ids(data))
    phases = {str(p["id"]) for p in intents.phases_of(data) if p.get("id")}
    first = _first_slice(data, text)
    items: Mapping[str, dict] | None = None
    out: list[str] = []
    for item, where, row in coverage_rows(text):
        if status.PLACEHOLDER in row:
            continue
        label = documents.one_line(item, 60)
        if _too_long(item, where):
            out.append(f"{path}: a {COVERAGE} row is longer than {MAX_CELL} characters ({label}); keep each cell to the item and its proof")
        elif not item or not where:
            out.append(f"{path}: a {COVERAGE} row is empty ({label or row}); name the slice, `deferred, asked`, or `{_NON_GOAL}`")
        elif (settled := _settling_problem(where)) is not None:
            if settled:
                out.append(f"{path}: {COVERAGE} row '{label}' {settled}")
        else:
            proofs, more = proofs_of(where)
            if more:
                out.append(f"{path}: {COVERAGE} row '{label}' names more than {MAX_PROOFS} proofs; name at most {MAX_PROOFS}, the ones that cover it")
            for proof in proofs:
                problem = _proof_problem(proof, known, phases, first, str(data.get("id")))
                if problem == OUTSIDE:
                    if items is None:
                        items = work_items() if work_items else {}
                    if finding := _outside_finding(path, label, proof, items):
                        out.append(finding)
                elif problem:
                    out.append(f"{path}: {COVERAGE} row '{label}' names {proof}, which is {problem}")
    return out


def _item_key(item: str) -> str:
    """A row's item as the rows of two Intents match it: its words, spaced once, in any case."""
    return " ".join(item.split()).casefold()


def _settled_here(where: str, intent_ids: set[str]) -> bool:
    """Whether a row's cell settles its item without another Intent: a question, the non-goal, a placeholder, or a proof
    that is no Intent's id (a slice, a phase, or a Spec, which the file's own check judges)."""
    if status.PLACEHOLDER in where or _settling_problem(where) is not None:
        return True
    return any(proof not in intent_ids for proof in proofs_of(where)[0])


def _row(rows: Mapping[str, str], at: str) -> str | None:
    """The cell of `at`'s row for one item, or None when it has no such row: one expansion of the walk."""
    return rows.get(at)


# The most Intents a chain shows in a finding; the rest are counted.
MAX_CHAIN_SHOWN = 8


def _shown_chain(path: list[str]) -> str:
    """The Intents of a chain as a finding names them: the first MAX_CHAIN_SHOWN, then how many more."""
    more = len(path) - MAX_CHAIN_SHOWN
    return ", ".join(path[:MAX_CHAIN_SHOWN]) + (f", and {more} more" if more > 0 else "")


def _reaching(rows: Mapping[str, str], intent_ids: set[str], closed: set[str]) -> tuple[dict[str, list[str]], set[str]]:
    """For one item: the Intents each unsettled row names, by the row's Intent, and the Intents whose rows reach a slice,
    a phase, or a Spec, found in one backward pass from every row that settles the item."""
    nexts: dict[str, list[str]] = {}
    good: list[str] = []
    for at in rows:
        where = _row(rows, at) or ""
        proofs = proofs_of(where)[0]
        if _settled_here(where, intent_ids) or any(p in closed for p in proofs):
            good.append(at)
        else:
            nexts[at] = proofs
    before: dict[str, list[str]] = {}
    for at, named in nexts.items():
        for nxt in named:
            before.setdefault(nxt, []).append(at)
    reached = set(good)
    while good:
        for at in before.get(good.pop(), []):
            if at not in reached:
                reached.add(at)
                good.append(at)
    return nexts, reached


def chain_reasons(rows: Mapping[str, str], intent_ids: set[str], closed: set[str]) -> dict[str, str]:
    """For one item: why each Intent with a row for it never reaches a slice, a phase, or a Spec, by its id; an Intent
    that reaches one is left out. `rows` is each Intent's cell for the item. A closed Intent ends a path, because
    `coverage_findings` warns about it. It costs one pass over the rows and the proofs they name (`_reaching`), then
    one walk of the rest, each Intent expanded once and each reason kept from the first the walk meets."""
    nexts, reached = _reaching(rows, intent_ids, closed)
    reasons: dict[str, str] = {}
    walked: set[str] = set()
    for start in nexts:
        if start in reached or start in walked:
            continue
        # Every Intent on `path` from the start up to `told` already has its reason: the first one the walk met below it.
        path, on_path, stack, told = [start], {start}, [iter(nexts[start])], 0
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                walked.add(path[-1])
                on_path.discard(path.pop())
                told = min(told, len(path))
                continue
            if nxt not in rows:
                why = f"{nxt} has no row for it in the same words; add one there, with the slice, the phase, or the Spec that covers the item"
            elif nxt in on_path:
                why = f"{_shown_chain(path)}, and back to {nxt}; one of them must cover the item with a slice, a phase, or a Spec"
            elif nxt in walked:
                why = reasons.get(nxt, "")
            else:
                path.append(nxt)
                on_path.add(nxt)
                stack.append(iter(nexts[nxt]))
                continue
            if why:
                reasons.update(dict.fromkeys(path[told:], why))
                told = len(path)
    return reasons


def coverage_chain_findings(objects: list[tuple[str, dict]], texts: Mapping[str, str]) -> list[str]:
    """The errors across Intents, for `aidd validate` of the repository: a Request coverage row that names only other
    Intents, whose own rows for the same item come back to where they started or never reach a slice, a phase, or a
    Spec. Each Intent of one request covers the whole request, so the Intent a row names holds a row for the item too.
    A row that names its own Intent is `coverage_findings`' error alone. Each item is walked once (`chain_reasons`)."""
    paths = {str(d["id"]): p for p, d in objects if d.get("type") == "intent" and d.get("id")}
    closed = {str(d["id"]) for p, d in objects if str(d.get("id")) in paths and status.intent_status(d, []) in status.INTENT_ENDED}
    intent_ids = set(paths)
    tables = {iid: coverage_rows(texts.get(p, "")) for iid, p in paths.items()}
    by_item: dict[str, dict[str, str]] = {}
    for iid, table in tables.items():
        for item, where, _ in table:
            if not _too_long(item, where):  # `coverage_findings` gives the error for a longer row
                by_item.setdefault(_item_key(item), {}).setdefault(iid, where)
    reasons: dict[str, dict[str, str]] = {}
    out = []
    for iid, table in tables.items():
        for item, where, _ in table:
            if not item or not where or _too_long(item, where) or _settled_here(where, intent_ids) or iid in proofs_of(where)[0]:
                continue
            key = _item_key(item)
            if key not in reasons:
                reasons[key] = chain_reasons(by_item[key], intent_ids, closed)
            if why := reasons[key].get(iid):
                out.append(f"{paths[iid]}: {COVERAGE} row '{documents.one_line(item, 60)}' reaches no slice, phase, or Spec: {why}")
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
    for the agreement until then. The caller compares the version with the file for a slice or a goal added since. `tip` is the commit whose history holds the file: a branch's, in `--all-branches`. The
    version comes back in today's shape, because the agreement may be from before an upgrade."""
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
    try:
        return old_shape.todays_shape(then)
    except retired_names.Refused:  # what the person agreed to cannot be read, so no agreement stands until they agree again
        return None


def agreement_problems(path: object, data: dict) -> list[str]:
    """`agreed_by` on one Intent: an error for an agent's name, which only a person may hold, and a warning for a form
    `approved_by` would not take. `aidd validate` gives them for one file and for the repository alike."""
    who = data.get("agreed_by") if data.get("type") == "intent" else None
    if not isinstance(who, str) or not who:
        return []
    if config.approver_is_agent(who):
        return [f"{path}: agreed_by {who} names an agent or a bot; only a person agrees to an Intent, in the chat: write the person's `@handle`"]
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


def delivery_team_problems(data: dict, cfg: config.Config | None) -> list[str]:
    """Each `delivery_team` a Spec or an Intent, or a slice of its phases, names that is no key of the config's
    `delivery_teams`, with the closest key. Empty when there is no config, or when every name holds."""
    if cfg is None or data.get("type") not in backlog.WORK_TYPES:
        return []
    known = sorted(cfg.get("delivery_teams", default={}) or {})
    slices = [s for p in data.get("phases") or [] if isinstance(p, dict) for s in p.get("slices") or [] if isinstance(s, dict)]
    named = [
        (where, d["delivery_team"])
        for where, d in (("", data), *(("slice " + str(s.get("id")) + " ", s) for s in slices))
        if isinstance(d.get("delivery_team"), str)
    ]
    hint = f"name one of {', '.join(known)}" if known else "add the team under `delivery_teams` in the config, or drop `delivery_team`"
    return [
        f"{where}delivery_team {team!r} is no key of the config's `delivery_teams`. {did_you_mean(team, known) or hint.capitalize() + '.'}"
        for where, team in named
        if team not in known
    ]


def document_team_warnings(data: dict, root: Path | None) -> list[str]:
    """A proposal, a runbook, or a postmortem whose `delivery_team` is no key of the config's `delivery_teams` at `root`, with the
    closest key. Empty when the config has no `delivery_teams`: such a repository names a team in plain words, and is never asked
    to declare one. A Spec or an Intent is checked as an error (`delivery_team_problems`)."""
    kind, team = data.get("type"), data.get("delivery_team")
    if kind in backlog.WORK_TYPES or kind not in config.types_with_field("delivery_team") or not isinstance(team, str) or team == status.PLACEHOLDER:
        return []
    cfg = repo_reads.config_at(root)
    known = sorted(cfg.get("delivery_teams", default={}) or {}) if cfg is not None else []
    if not known or team in known:
        return []
    return [f"delivery_team {team!r} is no key of the config's `delivery_teams`. {did_you_mean(team, known) or 'Name one of ' + ', '.join(known) + '.'}"]
