"""`aidd upgrade`'s fold of the work items an older aidd wrote: an Initiative and its Epics become one Intent.

- An Initiative becomes an Intent in place: its id, path, body, and fields stay, and its `milestones` become `phases`.
- Each Epic under it folds into it as a phase with the Epic's id, so every reference to an Epic still resolves. The
  phase takes the Epic's title as its name, the date of a closing "by YYYY-MM-DD" in its goal as `due`, and its
  `specs` as slices. Its goal, its context, and its body move into the Intent, then its file goes; git keeps it.
- An Epic with no parent becomes an Intent of its own, whose `specs` are its slices.
- A Spec's `parent: EPIC-n` names the Intent, a proposal need's `epic` becomes `phase`, and a delivery team's `epics`
  become `intents`. Approvals, revisions, and the records are never touched.
- With `collapse`, a Spec nobody started (a draft with no approval, no revision, no branch ahead, committed as it is)
  becomes its slice line, with `drafted_in` naming the commit that holds it, so `aidd new spec <id>` brings it back. Only
  a Spec whose slice line the fold writes collapses, and a Spec whose Epic ranks it apart from its Intent stays a file.
  So does a Spec that `provides` an interface another Spec `consumes`, because a slice line holds no `provides`.
- It stops, and writes nothing, for a cancelled Epic that still has unfinished Specs, because they would come back as
  live slices: a person ends each Spec, or moves it, and runs the fold again. That loses no decision.

It never writes an agreement: a record is never a yes. It stops, naming what, when a fact has no home in an Intent,
and then writes nothing. Nothing here reads a repository's brief, such as a root `intent.md`: only the Specs folder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import records, workitems
from aidd.kernel import documents, git, strict_yaml

_FRONT = re.compile(r"\A---\n(.*?\n)---\n", re.S)
_DUE = re.compile(r"\bby (\d{4}-\d{2}-\d{2})\W*$")
# The Epic fields a phase or its Intent holds; any other field set on an Epic stops the fold (`_homeless`).
_FOLDED = (
    "aidd_version",
    "type",
    "id",
    "parent",
    "title",
    "goal",
    "owner_team",
    "priority",
    "context",
    "specs",
    "covers",
    "reaches",
    "launch",
    "labels",
    "status",
)


@dataclass
class Migration:
    """What the fold writes: each file's new text, the files it removes, and the lines it shows. `stops` name what has no
    home in an Intent: with any, nothing is written."""

    writes: dict[Path, str] = field(default_factory=dict)
    removes: list[Path] = field(default_factory=list)
    reasons: dict[Path, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    stops: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Item:
    path: Path
    text: str
    data: dict


def _split(text: str) -> tuple[list[str], str]:
    """A document's front matter as lines, and the rest of it after the closing `---`."""
    m = _FRONT.match(text)
    if not m:
        raise ValueError("no front matter")
    return m.group(1).rstrip("\n").split("\n"), text[m.end() :]


def _join(head: list[str], body: str) -> str:
    return "---\n" + "\n".join(head) + "\n---\n" + body


def _block(head: list[str], name: str) -> tuple[int, int] | None:
    """The lines of top-level key `name`: its line, then the indented lines and `- ` items below it."""
    start = next((i for i, ln in enumerate(head) if re.match(rf"{re.escape(name)}:(\s|$)", ln)), None)
    if start is None:
        return None
    stop = start + 1
    while stop < len(head) and head[stop][:1] in (" ", "\t", "-"):
        stop += 1
    return start, stop


def _set(head: list[str], name: str, value: object) -> list[str]:
    """`head` with top-level `name` set to `value`, in place of its old lines, else at the end. A slice is one line, as
    `aidd new spec` reads it back."""
    lines = _slices_lines(name, value) if name in ("phases", "slices") and isinstance(value, list) else strict_yaml.dump_lines({name: value})
    found = _block(head, name)
    return [*head[: found[0]], *lines, *head[found[1] :]] if found else [*head, *lines]


def _slices_lines(name: str, value: list) -> list[str]:
    """`phases` or `slices` as block YAML, each slice in flow style on its own line."""
    if name == "slices":
        return ["slices:", *(f"  - {strict_yaml.flow(s)}" for s in value)]
    out = ["phases:"]
    for phase in value:
        rest = {k: v for k, v in phase.items() if k != "slices"}
        first, *more = strict_yaml.dump_lines(rest, 4)
        out += [f"  - {first.lstrip()}", *more, "    slices:", *(f"      - {strict_yaml.flow(s)}" for s in phase.get("slices") or [])]
        if not phase.get("slices"):
            out[-1] = "    slices: []"
    return out


def _drop(head: list[str], name: str) -> list[str]:
    found = _block(head, name)
    return [*head[: found[0]], *head[found[1] :]] if found else head


def _read(root: Path, specs_dir: str) -> tuple[list[_Item], list[str]]:
    """Every work item in the Specs folder, and the files that do not parse."""
    found, bad = [], []
    for path in workitems.object_files(root, specs_dir):
        try:
            text = path.read_text(encoding="utf-8")
            data, _ = documents.split_front_matter(text, path.as_posix())
        except (OSError, UnicodeDecodeError, documents.DocumentError) as exc:
            bad.append(f"{path.relative_to(root).as_posix()}: {documents.one_line(str(exc), 200)}")
            continue
        if isinstance(data, dict) and _FRONT.match(text):
            found.append(_Item(path, text, data))
    return found, bad


def _demoted(body: str, levels: int) -> str:
    """A Markdown body with each heading outside a code fence moved down `levels`."""
    out, fence = [], False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        out.append("#" * levels + line if not fence and re.match(r"#{1,6} ", line) else line)
    return "\n".join(out)


def _titles(items: list[_Item]) -> dict[str, str]:
    return {str(i.data.get("id")): str(i.data.get("title") or i.data.get("id")) for i in items if i.data.get("type") == "spec"}


def _slice(sid: str, titles: dict[str, str], extras: dict[str, dict] | None = None) -> dict:
    """A slice line: the id, its Spec's title, and what a collapsed Spec's line gains (`extras`)."""
    return {"id": sid, "title": titles.get(sid, sid)[:120], **(extras or {}).get(sid, {})}


def _epic_specs(epic: dict, items: list[_Item]) -> list[str]:
    """An Epic's Specs: its `specs` in order, then each other Spec that names it as parent, in id order."""
    listed = [str(s) for s in epic.get("specs") or []]
    named = sorted(
        (str(i.data["id"]) for i in items if i.data.get("type") == "spec" and str(i.data.get("parent") or "") == str(epic["id"])), key=workitems.id_order
    )
    return list(dict.fromkeys(listed + named))


def _homeless(epics: list[dict], initiative: dict) -> list[str]:
    """Why these Epics cannot fold into `initiative`: a field no Intent holds, `reaches` values that differ, two launches,
    an owner that differs, too many labels, or milestones beside the Epics."""
    out = []
    for e in epics:
        out += [
            f"{e['id']} sets `{k}`, which an Intent's phase has no place for: move it by hand, then run `aidd upgrade` again" for k in e if k not in _FOLDED
        ]
        if e.get("owner") and e.get("owner") != initiative.get("owner"):
            out.append(f"{e['id']} names owner {e['owner']}, not its Initiative's: set one owner on {initiative['id']}, then run `aidd upgrade` again")
    if len({str(e.get("reaches") or "incremental") for e in epics}) > 1:
        out.append(f"the Epics of {initiative['id']} reach users in different ways (`reaches`): an Intent has one, so split it into Intents by hand")
    if len([e for e in epics if e.get("launch")]) > 1:
        out.append(f"more than one Epic of {initiative['id']} names a `launch`: an Intent has one, so split it into Intents by hand")
    labels = list(dict.fromkeys([*(initiative.get("labels") or []), *(x for e in epics for x in e.get("labels") or [])]))
    if len(labels) > 8:
        out.append(f"{initiative['id']} and its Epics hold {len(labels)} labels, more than an Intent's 8: drop some, then run `aidd upgrade` again")
    if epics and initiative.get("milestones"):
        out.append(f"{initiative['id']} holds milestones and Epics, which both become phases: fold the milestones into the Epics by hand")
    return out


def _phase(epic: dict, items: list[_Item], team: str, extras: dict[str, dict]) -> dict:
    """The phase an Epic becomes. A slice with no Spec file takes the Epic's team when it differs from the Intent's."""
    titles = _titles(items)
    slices = [_slice(s, titles, extras) for s in _epic_specs(epic, items)]
    if epic.get("owner_team") and epic["owner_team"] != team:
        slices = [{**s, "owner_team": str(epic["owner_team"])} if (s["id"] not in titles or "drafted_in" in s) and "owner_team" not in s else s for s in slices]
    phase: dict = {"id": str(epic["id"]), "name": str(epic.get("title") or epic["id"])[:120]}
    if m := _DUE.search(str(epic.get("goal") or "")):
        phase["due"] = m.group(1)
    return {**phase, "slices": slices}


def _milestone_phase(m: dict, titles: dict[str, str]) -> dict:
    """The phase a milestone becomes: its fields, `reached_on` as `finished_on`, and its trigger's Specs as slices."""
    phase = {k: v for k, v in m.items() if k in ("id", "name", "due", "amount", "currency", "trigger", "invoice_ref")}
    if m.get("reached_on"):
        phase["finished_on"] = m["reached_on"]
    return {**phase, "slices": [_slice(str(s), titles) for s in (m.get("trigger") or {}).get("specs") or []]}


_COMMENT = re.compile(r"<!--.*?-->[ \t]*\n?", re.S)
_TABLE = re.compile(r"(?:^\|[^\n]*(?:\n|\Z))+", re.M)


def _written_table(table: str) -> bool:
    """Whether an `| Epic |` table holds text a person wrote: a reason under a heading that starts "Why"."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table.strip().split("\n")]
    if not rows or rows[0][0].lower() != "epic":
        return True  # some other table is not the old template's copy of the phases
    why = [i for i, c in enumerate(rows[0]) if c.lower().startswith("why")]
    return any(len(r) > i and r[i] and not r[i].startswith("TODO") for r in rows[2:] for i in why)


def _without_guidance(body: str) -> str:
    """A body without the old templates' guidance: its HTML comments, and its `| Epic |` table when no row holds a reason
    a person wrote, because the phases hold the Epics and their order."""
    out = _TABLE.sub(lambda m: m.group(0) if _written_table(m.group(0)) else "", _COMMENT.sub("", body))
    return re.sub(r"\n{3,}", "\n\n", out) if out != body else body


def _epic_section(e: _Item) -> str:
    """An Epic's body under the Intent's `## Phases`: its id and title, its goal, and its own text, headings moved down."""
    _, body = _split(e.text)
    goal = str(e.data.get("goal") or "")
    status = f"\n\nStatus: {e.data['status']}, as a person recorded it on the Epic." if e.data.get("status") in ("done", "cancelled") else ""
    return f"### {e.data['id']}: {e.data.get('title') or ''}\n\nGoal: {goal}{status}\n\n{_demoted(_without_guidance(body).strip(), 2)}\n"


def _with_phases(body: str, sections: list[str]) -> str:
    """The Intent's body with the folded Epics under `## Phases`: in place of its `## Epics` heading when it has one, at
    the end of that section; else at the end."""
    if not sections:
        return body
    block = "\n" + "\n".join(sections)
    m = re.search(r"^## Epics[ \t]*$", body, re.M)
    if not m:
        return body.rstrip("\n") + "\n\n## Phases\n\n" + block.lstrip("\n")
    nxt = re.search(r"^## ", body[m.end() :], re.M)
    at = m.end() + nxt.start() if nxt else len(body)
    head, tail = body[: m.start()] + "## Phases" + body[m.end() : at], body[at:]
    return head.rstrip("\n") + "\n\n" + block.lstrip("\n") + ("\n" + tail if tail else "")


def _fold(init: _Item, epics: list[_Item], items: list[_Item], extras: dict[str, dict]) -> str:
    """The Initiative's new text: an Intent with its Epics as phases."""
    head, body = _split(init.text)
    d, titles = init.data, _titles(items)
    head = [("type: intent" if re.match(r"type:\s", ln) else ln) for ln in head]
    phases = [_phase(e.data, items, str(d.get("owner_team") or ""), extras) for e in epics]
    phases += [_milestone_phase(m, titles) for m in d.get("milestones") or [] if isinstance(m, dict)]
    head = _drop(head, "milestones")
    if phases:
        head = _set(head, "phases", phases)
    epic_data = [e.data for e in epics]
    if reaches := next((str(e["reaches"]) for e in epic_data if e.get("reaches")), ""):
        head = _set(head, "reaches", reaches)
    if launch := next((str(e["launch"]) for e in epic_data if e.get("launch")), ""):
        head = _set(head, "launch", launch)
    if covers := list(dict.fromkeys([*(d.get("covers") or []), *(c for e in epic_data for c in e.get("covers") or [])])):
        head = _set(head, "covers", covers)
    labels = list(dict.fromkeys([*(d.get("labels") or []), *(x for e in epic_data for x in e.get("labels") or [])]))
    if labels and labels != list(d.get("labels") or []):
        head = _set(head, "labels", labels)
    if contexts := [f"{e['id']}: {e['context']}" for e in epic_data if e.get("context")]:
        head = _set(head, "context", "\n\n".join(contexts))
    return _join(head, _with_phases(_without_guidance(body), [_epic_section(e) for e in epics]))


def _lone_epic(e: _Item, items: list[_Item], extras: dict[str, dict]) -> str:
    """An Epic with no parent, as an Intent of its own: `specs` become its slices."""
    head, body = _split(e.text)
    head = _drop([("type: intent" if re.match(r"type:\s", ln) else ln) for ln in head], "specs")
    slices = [_slice(s, _titles(items), extras) for s in _epic_specs(e.data, items)]
    return _join(_set(head, "slices", slices) if slices else head, body)


def _ranked_apart(by_id: dict[str, _Item], parent: str, owner_id: str) -> str:
    """The priority of Epic `parent` when it differs from its Intent's `owner_id`; "" when they agree, or the Epic is the Intent."""
    epic = str(by_id[parent].data.get("priority") or "")
    return epic if parent != owner_id and epic != str(by_id[owner_id].data.get("priority") or "") else ""


def _stays_a_file(spec: _Item, iid: str, listed: set[str], by_id: dict[str, _Item]) -> str:
    """Why a Spec nobody started still stays a file, though a slice line could usually replace it: no phase of the Intent
    lists it, or its Epic ranks it apart from the Intent, which a slice line has no field for. "" when it may collapse."""
    sid, parent = str(spec.data.get("id")), str(spec.data.get("parent"))
    if sid not in listed:
        return f"{parent} lists it in no phase of {iid}, so no slice line of the fold can replace it"
    if (apart := _ranked_apart(by_id, parent, iid)) and not spec.data.get("priority"):
        return f"its Epic {parent} ranks it {apart}, which {iid} does not, and a slice line holds no priority"
    return ""


def _feeds(spec: _Item, items: list[_Item]) -> str:
    """Why a Spec nobody started stays a file though a slice line could replace it: it `provides` an interface another Spec
    `consumes`, and a slice line holds no `provides`. "" when nothing reads what it provides."""
    others = [i for i in items if i.data.get("type") == "spec" and i is not spec]
    readers = {
        n: [str(i.data["id"]) for i in others if n in workitems.interface_names(i.data, "consumes")] for n in workitems.interface_names(spec.data, "provides")
    }
    return "; ".join(f"it provides {n}, which {', '.join(r)} consume, and a slice line holds no `provides`" for n, r in readers.items() if r)


def _spec_text(spec: _Item, parent: str, priority: str) -> str:
    """A Spec's text with its `parent` naming the Intent, and the Epic's `priority` when the Spec sets none."""
    head, body = _split(spec.text)
    head = [f"parent: {strict_yaml.scalar(parent)}" if re.match(r"parent:\s", ln) else ln for ln in head]
    if priority and not spec.data.get("priority"):
        at = next((i + 1 for i, ln in enumerate(head) if re.match(r"parent:\s", ln)), len(head))
        head.insert(at, f"priority: {strict_yaml.scalar(priority)}")
    return _join(head, body)


_KEY = r"(?:^[ \t]*(?:-[ \t]+)?|[{,][ \t]*)"  # where a mapping key can start: a line or list item, or a flow mapping


def _proposal_text(text: str) -> str:
    """A proposal's text with each need's `epic` key named `phase` (the folded Epic's id is its phase's id), and its
    `milestones` named `phases`, each `reached_on` as `finished_on`. Only a key is renamed, where a key can start."""
    head, body = _split(text)
    for name, old, new in (("needs", "epic", "phase"), ("milestones", "reached_on", "finished_on")):
        if found := _block(head, name):
            start, stop = found
            head[start:stop] = [re.sub(rf"({_KEY}){old}:(?=\s)", rf"\g<1>{new}:", ln) for ln in head[start:stop]]
    head = [re.sub(r"^milestones:", "phases:", ln) for ln in head]
    return _join(head, body)


def _renamed(data: dict) -> dict:
    """A proposal's parsed front matter with the keys the fold renames: what its text must parse to after the fold."""
    out = {("phases" if k == "milestones" else k): v for k, v in data.items()}
    for key, old, new in (("needs", "epic", "phase"), ("phases", "reached_on", "finished_on")):
        if isinstance(out.get(key), list):
            out[key] = [{(new if k == old else k): v for k, v in i.items()} if isinstance(i, dict) else i for i in out[key]]
    return out


def _proposal_fold(text: str) -> tuple[str, str]:
    """(the proposal's text after the fold, why it must stop): the reason is empty when the new text parses to the old one
    with only the renamed keys changed, so nothing a person wrote, or a client signed, moves."""
    new = _proposal_text(text)
    if new == text:
        return text, ""
    try:
        before, after = documents.split_front_matter(text, "proposal")[0], documents.split_front_matter(new, "proposal")[0]
    except documents.DocumentError as exc:
        return text, f"it does not parse ({documents.one_line(str(exc), 120)})"
    if _renamed(before) != after:
        return text, "renaming `epic` and `milestones` would change more than those keys; rename them by hand"
    return new, ""


def _teams_text(text: str, intents: dict[str, list[str]]) -> str:
    """The config's text with each delivery team's `epics` replaced by its `intents` (dropped when it has none)."""
    lines = text.split("\n")
    top = next((i for i, ln in enumerate(lines) if re.match(r"delivery_teams:\s*(#.*)?$", ln)), None)
    if top is None:
        return text
    team, i, width = "", top + 1, _indent(lines, top)
    while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (" ", "\t", "#")):
        ln = lines[i]
        if (m := re.match(r"( *)([^\s:#][^:]*):\s*(#.*)?$", ln)) and len(m.group(1)) == width:
            team = m.group(2).strip().strip("\"'")
        if (m := re.match(r"( +)epics:(.*)$", ln)) and len(m.group(1)) > width:
            stop = i + 1
            if not m.group(2).split("#", 1)[0].strip():
                while stop < len(lines) and re.match(rf"{m.group(1)}\s*- ", lines[stop]):
                    stop += 1
            new = [f"{m.group(1)}intents: {strict_yaml.flow(intents[team])}"] if intents.get(team) else []
            lines[i:stop] = new
            i += len(new)
            continue
        i += 1
    return "\n".join(lines)


def _indent(lines: list[str], top: int) -> int:
    """The indent of the first key under line `top`: a team's own line."""
    return next((len(ln) - len(ln.lstrip(" ")) for ln in lines[top + 1 :] if ln.strip() and not ln.lstrip().startswith("#")), 2)


def _not_unstarted(root: Path, spec: _Item, base: str) -> str:
    """Why a Spec is not unstarted, so it stays a file; "" when it may become its slice line: a draft with no approval,
    no revision, no relation but `blocked_by`, no folder of its own, committed as it is, and no `spec/<id>` branch
    ahead of `base`."""
    d, sid = spec.data, str(spec.data.get("id"))
    rel = spec.path.relative_to(root).as_posix()
    if str(d.get("status") or "draft") != "draft" or d.get("approved_at") or d.get("revisions"):
        return "it has started"
    if any(isinstance(r, dict) and r.get("type") != "blocked_by" for r in d.get("relations") or []):
        return "a slice line holds only its `blocked_by` relations"
    if (spec.path.parent / sid).is_dir():
        return f"it has a folder, {spec.path.parent.relative_to(root).as_posix()}/{sid}/"
    try:
        if git.run(["status", "--porcelain", "--", rel], str(root)).strip() or not git.run(["log", "-1", "--format=%H", "--", rel], str(root)).strip():
            return "it has changes no commit holds"
        refs = git.run(["for-each-ref", "--format=%(refname)", f"refs/heads/spec/{sid}", f"refs/remotes/*/spec/{sid}"], str(root)).split()
        if any(int(git.run(["rev-list", "--count", f"{base}..{ref}"], str(root)).strip() or 0) for ref in refs):
            return f"a spec/{sid} branch is ahead of {base}"
    except (git.GitError, ValueError):
        return "git cannot say whether it started"
    return ""


def _collapsed(root: Path, specs: list[_Item], team: str, keep: dict[str, str]) -> tuple[dict[str, dict], list[str], list[str]]:
    """The unstarted Specs among `specs`, each as the fields its slice line gains; the open questions they held, as
    lines, in number order; and a note for each Spec that stays a file, with why. `keep` names a reason, by Spec id,
    that a slice line cannot replace the Spec even when nobody started it."""
    try:
        base = git.default_base(str(root))
    except git.GitError:
        return {}, [], ["kept every Spec as a file: git names no default branch to tell an unstarted Spec from a started one"]
    lines: dict[str, dict] = {}
    asked: list[str] = []
    notes: list[str] = []
    for spec in sorted(specs, key=lambda s: workitems.id_order(str(s.data.get("id")))):
        sid = str(spec.data.get("id"))
        if why := _not_unstarted(root, spec, base) or keep.get(sid, ""):
            if why != "it has started":
                notes.append(f"kept {spec.path.relative_to(root).as_posix()} as a file: {why}")
            continue
        rel = spec.path.relative_to(root).as_posix()
        extra: dict = {}
        waits = [str(r["id"]) for r in spec.data.get("relations") or [] if isinstance(r, dict) and r.get("type") == "blocked_by"]
        if waits:
            extra["blocked_by"] = waits
        if spec.data.get("owner_team") and spec.data["owner_team"] != team:
            extra["owner_team"] = str(spec.data["owner_team"])
        extra["drafted_in"] = git.run(["log", "-1", "--format=%H", "--", rel], str(root)).strip()
        lines[sid] = extra
        asked += [f"- {sid}: {q}" for q in spec.data.get("open_questions") or [] if isinstance(q, str)]
    return lines, asked, notes


def _with_questions(text: str, asked: list[str]) -> str:
    """The Intent's text with the collapsed drafts' open questions at the end of its `## Open questions`, replacing the
    template's "none", and the section added before `## Learn` (else at the end) when it has none."""
    if not asked:
        return text
    head, body = _split(text)
    block = "\n".join(asked) + "\n"
    m = re.search(r"^## Open questions[ \t]*$", body, re.M)
    if m:
        nxt = re.search(r"^## ", body[m.end() :], re.M)
        at = m.end() + nxt.start() if nxt else len(body)
        held = re.sub(r"\n+none[ \t]*$", "", body[m.end() : at].rstrip("\n"))  # the template's "none" says no question is open
        return _join(head, body[: m.end()] + held + "\n\n" + block + ("\n" + body[at:] if body[at:] else ""))
    learn = re.search(r"^## Learn[ \t]*$", body, re.M)
    section = "## Open questions\n\n" + block
    if learn:
        return _join(head, body[: learn.start()] + section + "\n" + body[learn.start() :])
    return _join(head, body.rstrip("\n") + "\n\n" + section)


def _agreement_note(root: Path, intent_id: str) -> str:
    """What the agent asks once about an Intent's agreement. It cites the newest decision record that accepted an agreement
    to the Intent (an action ending `.agree`, its answer `accept`); any other record is no yes to this, so the agent asks
    the plain question. "" when no record names the Intent."""
    try:
        found, _ = records.read_records(str(root), record_type="decision", subject=intent_id)
    except (OSError, ValueError):
        return ""
    if not found:
        return ""
    base = f"{intent_id} records no agreement, and upgrade never writes one, because a record is never a yes."
    tail = "On the person's yes, it sets `agreed_by` and `agreed_at` and commits them with an `Agreed-by:` trailer"
    accepted = [r for r in found if _accepts_agreement(r)]
    if not accepted:
        return f'{base} The agent asks once: "Agree to {intent_id}?" {tail}'
    rec, day = accepted[0], str(accepted[0].get("at") or "")[:10]
    return f'{base} The decision record {rec["id"]} names it, so the agent asks once: "Record that you agreed to {intent_id} on {day}, as that day\'s record says?" {tail}'


def _accepts_agreement(record: dict) -> bool:
    """Whether a decision record is a person's accepted answer to an agreement."""
    data = record.get("data") or {}
    return str(data.get("action") or "").endswith(".agree") and (data.get("answer") or {}).get("outcome") == "accept"


@dataclass(frozen=True)
class _Plan:
    """The fold's shape: each Initiative's Epics by the Intent's id, each Epic's Specs, and the lone Epics."""

    groups: dict[str, list[str]]
    epic_specs: dict[str, list[str]]
    lone: list[str]


def _teams(cfg_text: str, shape: _Plan, extras: dict[str, dict], out: Migration) -> str:
    """The config's text with each delivery team's `epics` as `intents`: an Intent whose every Epic the team held, or an
    Epic that became an Intent of its own. An Epic held alone gives its slices the team's `owner_team` (in `extras`). A
    team left with neither areas nor Intents stops the fold."""
    try:
        teams = documents.parse_yaml(cfg_text, "config").get("delivery_teams") or {}
    except documents.DocumentError:
        return cfg_text
    held: dict[str, list[str]] = {}
    for name, team in teams.items() if isinstance(teams, dict) else []:
        epics = {str(e) for e in team.get("epics") or []} if isinstance(team, dict) else set()
        if not epics:
            continue
        whole = [i for i, members in shape.groups.items() if members and set(members) <= epics]
        held[name] = whole + sorted((e for e in epics if e in shape.lone), key=workitems.id_order)
        for e in sorted(epics - {m for i in whole for m in shape.groups[i]} - set(shape.lone), key=workitems.id_order):
            out.notes.append(f"delivery team {name} held {e} alone, so its slices name `owner_team: {name}`")
            for sid in shape.epic_specs.get(e, []):
                extras.setdefault(sid, {})["owner_team"] = str(name)
        if not held[name] and not team.get("areas"):
            out.stops.append(f"delivery team {name} holds only some Epics of an Intent and no areas: give it `areas`, or name its Intent, then run again")
    return _teams_text(cfg_text, held) if held else cfg_text


def _cancelled_with_live_specs(items: list[_Item]) -> list[str]:
    """A stop for each cancelled Epic that still has an unfinished Spec, or a Spec with no file: the fold would turn them
    into live slices. Stopping loses no decision; a person ends each Spec or moves it, then runs the fold again."""
    states = {str(i.data.get("id")): str(i.data.get("status") or "draft") for i in items if i.data.get("type") == "spec"}
    out = []
    for epic in (i for i in items if i.data.get("type") == "epic" and i.data.get("status") == "cancelled"):
        live = [s for s in _epic_specs(epic.data, items) if not workitems.finished(states.get(s, "draft"))]
        if fileless := [s for s in live if s not in states]:
            out.append(
                f"{epic.data['id']} is cancelled, but lists {', '.join(fileless)} with no file, and the fold would turn "
                f"{'it' if len(fileless) == 1 else 'them'} into live slices: remove {'it' if len(fileless) == 1 else 'each'} from the Epic's `specs`, "
                "then run `aidd upgrade` again"
            )
        if live := [s for s in live if s in states]:
            out.append(
                f"{epic.data['id']} is cancelled, but {', '.join(live)} {'is' if len(live) == 1 else 'are'} not finished, and the fold would turn "
                "them into live slices: set `status: cancelled` on each Spec, or move it to another Epic, then run `aidd upgrade` again"
            )
    return out


def _shape(items: list[_Item], out: Migration) -> tuple[_Plan, list[_Item]]:
    """Which Epics fold into which Initiative, and the Epics with no parent; a stop for each Epic or reference the fold
    cannot place."""
    by_id = {str(i.data.get("id")): i for i in items}
    groups: dict[str, list[str]] = {str(i.data["id"]): [] for i in items if i.data.get("type") == "initiative"}
    lone: list[_Item] = []
    for e in sorted((i for i in items if i.data.get("type") == "epic"), key=lambda i: workitems.id_order(str(i.data.get("id")))):
        parent = str(e.data.get("parent") or "")
        if parent in groups:
            groups[parent].append(str(e.data["id"]))
        elif parent:
            out.stops.append(f"{e.path.name}: its parent {parent} is no Initiative in the Specs folder; remove `parent` or add the Initiative, then run again")
        else:
            lone.append(e)
            out.stops += [f"{e.data['id']} sets `{k}`, which an Intent has no place for: move it by hand, then run again" for k in e.data if k not in _FOLDED]
    for iid, members in groups.items():
        out.stops += _homeless([by_id[m].data for m in members], by_id[iid].data)
    out.stops += _cancelled_with_live_specs(items)
    phases = {m for members in groups.values() for m in members}
    for i in items:
        for r in i.data.get("relations") or []:
            if isinstance(r, dict) and str(r.get("id")) in phases:
                out.stops.append(
                    f"{i.path.name}: its {r.get('type')} relation names {r['id']}, an Epic that becomes a phase, which no relation can name: point it at the phase's Specs, then run again"
                )
    epic_specs = {str(e.data["id"]): _epic_specs(e.data, items) for e in items if e.data.get("type") == "epic"}
    return _Plan(groups, epic_specs, [str(e.data["id"]) for e in lone]), lone


def _errors(text: str, what: str) -> list[str]:
    _, _, errors = workitems.load_object(text, what)
    return [e for e in errors if not e.startswith("warning: ")]


def _proposal_changed(old: str, new: str) -> bool:
    """Whether the new text of a proposal no longer matches what was signed off: its sign-off hash moves, or it no longer parses."""
    try:
        return workitems.proposal_hash(old) != workitems.proposal_hash(new)
    except documents.DocumentError:
        return True


def _checked(out: Migration, root: Path) -> None:
    """A stop for each error the fold would add to a file it writes, so nothing it writes fails where it passed."""
    for path, text in out.writes.items():
        if path.suffix != ".md":
            continue
        what = path.relative_to(root).as_posix()
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        before = set(_errors(old, what)) if old else set()
        out.stops += [f"the fold would leave {e}" for e in _errors(text, what) if e not in before]
        if path.name == "proposal.md" and old and _proposal_changed(old, text):
            out.stops.append(f"the fold would change {what} beyond what a client signed off: leave it as it is, then run `aidd upgrade` again")


def plan(root: Path, specs_dir: str, proposals_dir: str, cfg_path: Path, *, collapse: bool = False) -> Migration:
    """What the fold writes in `root`, with its notes; a Migration with `stops`, and nothing to write, when any fact has no
    home. Empty when no Initiative or Epic is left."""
    out = Migration()
    for proposal in sorted((root / proposals_dir).glob("*/proposal.md")):
        text = proposal.read_text(encoding="utf-8")
        if not _FRONT.match(text):
            continue
        new, why = _proposal_fold(text)
        if why:
            out.stops.append(f"{proposal.relative_to(root).as_posix()}: {why}, then run `aidd upgrade` again")
        elif new != text:
            out.writes[proposal] = new
            out.reasons[proposal] = "its needs and its delivery name phases, as an Intent does"
    items, bad = _read(root, specs_dir)
    if not any(i.data.get("type") in workitems.FOLDED_TYPES for i in items):
        _checked(out, root)
        return out
    out.stops += [f"{b}: fix it, so the fold reads every work item" for b in bad]
    shape, lone = _shape(items, out)
    if out.stops:
        out.writes, out.reasons = {}, {}
        return out
    by_id = {str(i.data.get("id")): i for i in items}
    owner = {m: iid for iid, members in shape.groups.items() for m in members} | {iid: iid for iid in shape.groups}
    owner |= {str(e.data["id"]): str(e.data["id"]) for e in lone}
    extras: dict[str, dict] = {}
    asked: dict[str, list[str]] = {}
    if collapse:
        for iid in [*shape.groups, *(str(e.data["id"]) for e in lone)]:
            specs = [i for i in items if i.data.get("type") == "spec" and owner.get(str(i.data.get("parent") or "")) == iid]
            listed = {s for member in shape.groups.get(iid) or [iid] for s in shape.epic_specs.get(member, [])}
            keep = {str(s.data.get("id")): why for s in specs if (why := _stays_a_file(s, iid, listed, by_id) or _feeds(s, items))}
            lines, asked[iid], notes = _collapsed(root, specs, str(by_id[iid].data.get("owner_team") or ""), keep)
            extras |= lines
            out.notes += notes
    cfg_text = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    new_cfg = _teams(cfg_text, shape, extras, out)
    if new_cfg != cfg_text:
        out.writes[cfg_path] = new_cfg
        out.reasons[cfg_path] = "its delivery teams name Intents in place of Epics"
    for iid, members in shape.groups.items():
        out.writes[by_id[iid].path] = _with_questions(_fold(by_id[iid], [by_id[m] for m in members], items, extras), asked.get(iid, []))
        out.reasons[by_id[iid].path] = f"an Initiative and its {len(members)} Epics, now one Intent with a phase for each; every id is kept"
        out.removes += [by_id[m].path for m in members]
        out.reasons |= {by_id[m].path: f"now phase {m} of {iid}; git keeps the file" for m in members}
    for e in lone:
        out.writes[e.path] = _with_questions(_lone_epic(e, items, extras), asked.get(str(e.data["id"]), []))
        out.reasons[e.path] = "an Epic with no Initiative, now an Intent of its own"
    for spec in (i for i in items if i.data.get("type") == "spec" and str(i.data.get("parent") or "") in owner):
        parent = str(spec.data["parent"])
        if "drafted_in" in extras.get(str(spec.data.get("id")), {}):
            out.removes.append(spec.path)
            out.reasons[spec.path] = f"unstarted, now a slice line of {owner[parent]}, whose `drafted_in` names the commit that holds it"
        elif owner[parent] != parent:
            out.writes[spec.path] = _spec_text(spec, owner[parent], _ranked_apart(by_id, parent, owner[parent]))
            out.reasons[spec.path] = f"its parent {parent} is now a phase of {owner[parent]}, which it names"
    _checked(out, root)
    out.notes += [n for iid in sorted({*owner.values()}, key=workitems.id_order) if (n := _agreement_note(root, iid))]
    return out


def uncommitted(root: Path, paths: list[str]) -> list[str]:
    """The paths among `paths` with changes no commit holds, so the fold waits for them; all of them when git cannot say."""
    try:
        listed = git.run(["status", "--porcelain", "--untracked-files=all", "--", *paths], str(root))
    except git.GitError:
        return paths
    return sorted({line[3:] for line in listed.splitlines() if len(line) > 3})
