"""The checks `aidd validate` runs on Intents: unique slices, a Spec under the Intent that lists it, who approved, and an
approval with no hold or that a later change to the slices or the outcome left behind.

An approval holds only by the commit that brought it: `Approved-by:` and `Approves:` with the Intent's exact id in its last
paragraph, and no change to the Intent but its `approval` (`stamped_version`). A field with no such commit is an error and reads as
draft. Order, names, dates, and the other slice fields an agent keeps are bookkeeping, so changing them never asks for a new
approval. A slice added or removed, or a new `outcome`, changes what the person approved, so it warns until a person approves again.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import NamedTuple

from aidd import config
from aidd.kernel import command_names, documents, git, regular_files, resources, retired_names
from aidd.kernel.text import did_you_mean
from aidd.workitems import approval_commits, backlog, criteria, intent_paths, intents, old_shape, repo_reads, status


def intent_findings(objects: list[tuple[str, dict]]) -> tuple[list[str], list[str]]:
    """(errors, warnings) across the repository's Intents and Specs: a slice id listed twice, an agent in `approval.by`, a
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
            for line in intents.planned_specs_of(phase):
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
        if d.get("type") == "spec" and parent and parent[1].get("type") == "intent" and str(d.get("id")) not in intents.planned_spec_ids(parent[1]):
            warnings.append(
                f"{p}: its parent {parent[1].get('id')} lists no slice {d.get('id')}; add the slice line to the Intent, and ask the person to approve it again"
            )
    return errors, warnings


class Stamp(NamedTuple):
    """A person's yes as a file records it: the key of its object (`approval`), or None where the file keeps a loose pair at its top
    level; the fields for who and when, inside that object or at the top; where the schema gives the time's pattern (its one owner);
    and the key of the item's id that `Approves:` names, or None where it names the file's path, as for a file with no id."""

    key: str | None
    by: str
    at: str
    schema: str
    pointer: tuple[str, ...]
    ident: str | None


# An Intent's approval, one object. The approval of a file of the product scope is `product_approval.APPROVAL`, a loose pair.
APPROVAL = Stamp("approval", "by", "at", "common.schema.json", ("$defs", "instant"), "id")


def stamp_fields(stamp: Stamp) -> tuple[str, ...]:
    """The top-level keys of the front matter that the yes sets: its object, or its two loose fields."""
    return (stamp.key,) if stamp.key else (stamp.by, stamp.at)


def stamp_of(stamp: Stamp, data: dict) -> tuple[str, str]:
    """Who said yes and when, as `data` records it, each "" when it holds none. An object of the wrong shape holds none."""
    holder = data.get(stamp.key) if stamp.key else data
    if not isinstance(holder, dict):
        return "", ""
    return str(holder.get(stamp.by) or ""), str(holder.get(stamp.at) or "")


def approval_of(data: dict) -> tuple[str, str]:
    """Who approved the Intent `data` and when, as its `approval` records it, each "" when it holds none. A claim, never a hold."""
    return stamp_of(APPROVAL, data)


@functools.cache
def _time_pattern(stamp: Stamp) -> str:
    """The pattern the schema gives the stamp's time, its one owner."""
    node = resources.load_json(stamp.schema)
    for key in stamp.pointer:
        node = node[key]
    return str(node["pattern"])


def _front_matter_at(root: Path, sha: str, places: list[str]) -> tuple[str, dict, str] | None:
    """The place, the front matter, and the body of the file at commit `sha`, from the first of `places` that holds a file there."""
    for rel in places:
        text = approval_commits.file_at(str(root), sha, rel)
        if text is None:
            continue
        try:
            data, body = documents.split_front_matter(text, rel)
        except documents.DocumentError:
            return None
        return (rel, data, body) if isinstance(data, dict) else None
    return None


def _approval_commit(root: Path, places: list[str], at: str, tip: str, stamp: Stamp) -> tuple[str, str, dict, str] | None:
    """The first commit of the file, at any of `places`, whose parsed front matter holds the stamp's time `at`, with the place it
    lay in and that front matter and body. It reads the parsed value, never the text, so a single-quoted value or a trailing
    comment finds the same commit, and another line of the file that holds the bare value does not. `at` is checked against the
    schema's RFC 3339 pattern first. It looks in the history of `tip`. None when no commit holds it, or git cannot say."""
    if not re.fullmatch(_time_pattern(stamp), at):
        return None
    try:
        found = git.log_fields(["--reverse", tip, "--", *places], ["%H"], str(root), check=False)
    except git.GitError:
        return None
    for (sha,) in found:
        then = _front_matter_at(root, sha, places)
        if then is not None and stamp_of(stamp, then[1])[1] == at:
            return sha, *then
    return None


def approval_commit(root: Path, rel: str, data: dict, tip: str = "HEAD") -> str | None:
    """The commit that recorded the approval of the Intent `data` at `rel`, in the history of `tip`: the first one whose front matter
    holds its `approval.at`. None when there is none, which the caller reads as no approval it can date."""
    found = _approval_commit(root, [rel], stamp_of(APPROVAL, data)[1], tip, APPROVAL)
    return found[0] if found else None


def _current_body(root: Path, rel: str, tip: str) -> str | None:
    """The body of the Intent file `rel` now: as the working tree holds it, or as the commit `tip` holds it when one is named. None
    when it cannot be read, which reads as no difference, since `aidd validate` reports a file that does not read."""
    if tip == "HEAD":
        raw, _ = regular_files.file_bytes(root, root / rel, documents.MAX_DOCUMENT_BYTES)
        text = raw.decode("utf-8", errors="replace") if raw is not None else None
    else:
        text = approval_commits.file_at(str(root), tip, rel)
    try:
        return documents.split_front_matter(text, rel)[1] if text is not None else None
    except documents.DocumentError:
        return None


def approved_version(root: Path, rel: str, data: dict, tip: str = "HEAD") -> dict | None:
    """The Intent as the person approved it, or None when no approval holds: `approved_document`'s front matter, marked with
    `intents.BODY_CHANGED` when the body of the file now differs from the approved body, so every reader that compares a version
    with the file reads the body through `intents.approved_changes`, as the delegate does."""
    found = approved_document(root, rel, data, tip)
    if found is None:
        return None
    now = _current_body(root, rel, tip)
    if now is not None and intents.approval_body(now) != intents.approval_body(found[1]):
        return {**found[0], intents.BODY_CHANGED: True}
    return found[0]


def approved_document(root: Path, rel: str, data: dict, tip: str = "HEAD") -> tuple[dict, str] | None:
    """The Intent's front matter and body as the person approved them, or None when no approval holds. It fails closed: the file's
    `approval.by` names a person (`approved_by_kind` finds nothing wrong), and `approval.at` is an RFC 3339 time. The first
    commit whose front matter holds that `approval.at` is its hold (`stamped_version`): the same person, an `Approved-by` line of
    theirs and an `Approves` line with the Intent's exact id, and no change to the Intent but its `approval`. `aidd status` asks for
    the approval until then. The caller compares the version with the file for a slice or an outcome added since. `tip` is the
    commit whose history holds the file: a branch's, in `--all-branches`."""
    who, at = stamp_of(APPROVAL, data)
    if not who or not at or config.approved_by_kind(who) is not None:
        return None
    if (approved := _approved_in(root, [rel], data, tip)) is not None:
        return approved
    # The file's own path holds no approval a person made. Git's own record of its renames may name another place it lay in, and
    # the first commit of the new path alone would be the move, which holds no trailer.
    names = intent_paths.former_intent_names(root, rel, tip)
    return _approved_in(root, [rel, *names], data, tip) if names else None


def stamped_version(root: Path, places: list[str], data: dict, tip: str, stamp: Stamp) -> tuple[dict, str] | None:
    """The one lookup of who said yes to a version of a file: the front matter and the body of the file as the person `data`'s stamp
    names said yes to it at the stamp's time, from the first commit that holds that time in any of `places`, or None. It fails closed:
    - the person is one `approved_by_kind` finds nothing wrong with;
    - that version is the same item (its `id`), and its own stamp names the person;
    - the commit's last paragraph holds an `Approved-by` line for the person, and only for them, and an `Approves` line that names
      the item's id exactly (`stamp.ident`), or the place the file lay in at that commit for an item named by its path, such as a
      file of the product scope; a commit that names one item holds no yes for another it changes;
    - no delegated yes's trailer stands in its message; and
    - the commit changes nothing in the file but the yes (`approval_commits.changes_only_the_yes`).
    A move keeps the id, so a version of another item in a place with the same name is no yes.

    What it trusts: a trailer is the record of a branch, which anyone who can push to it can write, so this is no proof of who
    said yes."""
    who, at = stamp_of(stamp, data)
    if not who or not at or config.approved_by_kind(who) is not None:
        return None
    found = _approval_commit(root, places, at, tip, stamp)
    if found is None:
        return None
    sha, place, then, body = found
    if then.get("id") != data.get("id") or config.normalize_identity(stamp_of(stamp, then)[0]) != config.normalize_identity(who):
        return None
    try:
        message = approval_commits.raw_message(root, sha)
    except git.GitError:
        return None
    trailers = approval_commits.trailer_values(message, approval_commits.APPROVED_BY)
    if not trailers or {config.normalize_identity(v) for v in trailers} != {config.normalize_identity(who)}:
        return None
    ident = str(data.get(stamp.ident) or "") if stamp.ident else place
    if not approval_commits.approves(message, ident) or not approval_commits.changes_only_the_yes(root, sha, place, (then, body), stamp_fields(stamp)):
        return None
    return then, body


def _approved_in(root: Path, places: list[str], data: dict, tip: str) -> tuple[dict, str] | None:
    """The Intent `data` as its `approval.by` approved it at its `approval.at` (`stamped_version`): its front matter in today's shape, and its body."""
    found = stamped_version(root, places, data, tip, APPROVAL)
    if found is None:
        return None
    try:
        return old_shape.todays_shape(found[0]), found[1]
    except retired_names.Refused:  # what the person approved cannot be read, so no approval holds until they approve again
        return None


def approval_problems(path: object, data: dict) -> list[str]:
    """`approval.by` on one Intent, and on each criterion's result: an error for an agent's name, which only a person may hold, and a
    warning for a form `approved_by` would not take. `aidd validate` gives them for one file and for the repository alike."""
    if data.get("type") != "intent":
        return []
    named = [("approval.by", stamp_of(APPROVAL, data)[0])]
    for c in criteria.criteria_of(data):
        result = c.get("result")
        named.append((f"success_criteria {c.get('id')} result.approval.by", stamp_of(APPROVAL, result)[0] if isinstance(result, dict) else ""))
    out = []
    for field, who in named:
        if not who:
            continue
        if config.approver_is_agent(who):
            out.append(f"{path}: {field} {who} names an agent or a bot; only a person approves: write the person's `Name <email>` or `@handle`")
        elif problem := config.approved_by_problem(who, field):
            out.append(f"warning: {path}: {problem}")
    return out


def criteria_problems(path: object, data: dict) -> list[str]:
    """Errors on one Intent that the schema cannot say: a criterion id listed twice, which would make an address name two criteria,
    and a proposal named in both `proposal` and `from`, which would store one fact twice."""
    if data.get("type") != "intent":
        return []
    out = [
        f"{path}: success criterion {cid} is listed twice; an id is unique in its Intent and never reused, so give each criterion its own"
        for cid in criteria.duplicate_ids(data)
    ]
    if isinstance(data.get("proposal"), str) and data.get("proposal") == data.get("from"):
        out.append(f"{path}: `proposal` and `from` both name {data['proposal']}; name the proposal once, in `proposal`, and remove `from`")
    return out


def from_findings(objects: list[tuple[str, dict]]) -> list[str]:
    """An error for each item whose `from` names itself or its own Intent's criterion, which no item can have raised, and for each
    whose `from` is a criterion's address when its Intent is in this repository and lists no such criterion. An address whose Intent
    lies elsewhere is left alone: aidd reads no other repository."""
    listed = {str(d["id"]): [str(c["id"]) for c in criteria.criteria_of(d)] for _, d in objects if d.get("type") == "intent" and d.get("id")}
    out = []
    for p, d in objects:
        parsed = criteria.parse_address(d.get("from"))
        if d.get("id") and (d.get("from") == d["id"] or (parsed and parsed[0] == d["id"])):
            out.append(f"{p}: `from` names {d['from']}, which is this item itself; name what raised it, never itself")
        elif parsed and parsed[0] in listed and parsed[1] not in listed[parsed[0]]:
            have = ", ".join(listed[parsed[0]]) or "none"
            out.append(f"{p}: `from` names {d['from']}, but {parsed[0]} lists no criterion {parsed[1]} (it lists {have}); name one it lists")
    return out


def place_problem(path: Path, root: Path, cfg: config.Config | None) -> str:
    """The finding for an Intent file at `path` that lies outside the Intents' folder; empty for one in it. aidd moves no Intent, so
    it says where an Intent lives and the `git mv` that moves this one."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""
    product_dir = (cfg or config.EMPTY).product_dir
    if intent_paths.in_intents_folder(rel, product_dir):
        return ""
    folder = intent_paths.intents_folder(product_dir)
    move = f"git mv {command_names.quoted(rel) or '<this file>'} {command_names.quoted(f'{folder}/{Path(rel).name}') or '<the folder>'}"
    return (
        f"{path}: an Intent lives in {folder}/, so this one is misplaced: move it with `{move}`, "
        "and the folder beside it that holds its evidence and decision cards, if it has one"
    )


def approval_warnings(path: Path, data: dict, root: Path | None) -> list[str]:
    """An error when the Intent's `approval` has no hold, and a warning when a slice was added or removed, or anything the approval
    covers changed, after the person approved. It fails closed: an `approval` that no commit holds (`approved_document`), or that git
    cannot read, is an error and reads as draft. Empty for an Intent nobody approved yet, which `aidd status` names as waiting for its
    approval."""
    who, at = stamp_of(APPROVAL, data)
    if data.get("type") != "intent" or not (who or at or data.get("approval")):
        return []
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix() if root is not None else ""
    except ValueError:
        rel = ""
    then = approved_version(root, rel, data) if root is not None and rel else None
    iid = command_names.quoted(str(data.get("id") or "")) or "<ID>"
    if then is None:
        return [approval_commits.no_hold_error(path, root, str(data.get("id") or ""), who)]
    if not (changed := intents.changes_since(then, data)):
        return []
    return [
        f"warning: {path}: {'; '.join(changed)} since {documents.one_line(who, 120)} approved on {documents.one_line(at, 40)}; ask the "
        f"person to approve it again (`intent.approve`): their yes in the chat, or `aidd approve {iid}` in their terminal"
    ]


def development_team_problems(data: dict, cfg: config.Config | None) -> list[str]:
    """Each `development_team` a Spec or an Intent, or a slice of its phases, names that is no key of the config's
    `development_teams`, with the closest key. Empty when there is no config, or when every name holds."""
    if cfg is None or data.get("type") not in backlog.WORK_TYPES:
        return []
    known = sorted(cfg.get("development_teams", default={}) or {})
    lines = [s for p in data.get("phases") or [] if isinstance(p, dict) for s in p.get("specs") or [] if isinstance(s, dict)]
    named = [
        (where, d["development_team"])
        for where, d in (("", data), *(("slice " + str(s.get("id")) + " ", s) for s in lines))
        if isinstance(d.get("development_team"), str)
    ]
    hint = f"name one of {', '.join(known)}" if known else "add the team under `development_teams` in the config, or drop `development_team`"
    return [
        f"{where}development_team {team!r} is no key of the config's `development_teams`. {did_you_mean(team, known) or hint.capitalize() + '.'}"
        for where, team in named
        if team not in known
    ]


def document_team_warnings(data: dict, root: Path | None) -> list[str]:
    """A proposal, a runbook, or a postmortem whose `development_team` is no key of the config's `development_teams` at `root`, with the
    closest key. Empty when the config has no `development_teams`: such a repository names a team in plain words, and is never asked
    to declare one. A Spec or an Intent is checked as an error (`development_team_problems`)."""
    kind, team = data.get("type"), data.get("development_team")
    if kind in backlog.WORK_TYPES or kind not in config.types_with_field("development_team") or not isinstance(team, str) or team == status.PLACEHOLDER:
        return []
    cfg = repo_reads.config_at(root)
    known = sorted(cfg.get("development_teams", default={}) or {}) if cfg is not None else []
    if not known or team in known:
        return []
    return [f"development_team {team!r} is no key of the config's `development_teams`. {did_you_mean(team, known) or 'Name one of ' + ', '.join(known) + '.'}"]
