"""Proposals: the case put to someone who decides, before any code, and the bridge to delivery once it is accepted.

A proposal goes to a client (a bid, a pitch, a response to a request for proposal) or to the company's own decision
makers (a change put to leadership). Its front matter holds what a decision maker compares: the needs and how each
is answered, the options, a range estimate and its parts, the claims and their evidence, the RAID log (risks,
assumptions, issues, dependencies), the milestones, the exclusions, and open questions. `matrix` renders them as tables
for the document that is sent, and `convert` turns an accepted proposal into an Initiative and Epics whose ids trace
back to it. One home per phase: the proposal keeps what was promised, frozen at sign-off, and the Initiative takes the
milestones, the RAID log, and the scope decisions log as the delivery record, so every change delivered later answers
to what was promised and nothing is tracked twice.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import model
from .util import md_cell

ANSWER_WORDS = {"met": "Met", "partly_met": "Partly met", "alternative": "Alternative", "not_met": "Not met"}


def load(path: Path) -> dict:
    data, _, errors = model.load_object(path.read_text(encoding="utf-8"), str(path))
    if errors:
        raise model.ModelError("\n".join(errors))
    if data.get("kind") != "proposal":
        raise model.ModelError(f"{path}: not a proposal (kind = {data.get('kind')!r})")
    return data


def matrix(p: dict) -> str:
    """The structured parts of a proposal as Markdown tables, ready to paste into the document that is sent."""
    out = [f"# {p['title']}", "", f"For {p['addressee']}. {p['goal']}", ""]
    needs = p.get("needs", [])
    if needs:
        counts = {k: sum(1 for n in needs if n["answer"] == k) for k in ANSWER_WORDS}
        tally = ", ".join(f"{v} {ANSWER_WORDS[k].lower()}" for k, v in counts.items() if v)
        out += ["## Needs and how we answer them", "", f"{len(needs)} needs: {tally}.", ""]
        out += ["| Id | Need | Source | Answer | Note |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {n['id']} | {md_cell(n['need'])} | {md_cell(n.get('source'))} | {ANSWER_WORDS[n['answer']]} | {md_cell(n.get('note'))} |" for n in needs]
        out.append("")
    if p.get("options"):
        out += ["## Options", "", "| Option | Summary | Recommended |", "| --- | --- | --- |"]
        out += [f"| {md_cell(o['name'])} | {md_cell(o['summary'])} | {'yes' if o.get('recommended') else ''} |" for o in p["options"]]
        out.append("")
    est = p.get("estimate")
    if est:
        out += [
            "## Estimate",
            "",
            f"Between {model.fmt_number(est['low'])} and {model.fmt_number(est['high'])} {est['unit']}, most likely {model.fmt_number(est['likely'])}. {est['basis']}",
            "",
        ]
    for field, title in (("assumptions", "Assumptions"), ("issues", "Issues"), ("dependencies", "Dependencies")):
        out += _raid(p.get(field) or [], title)
    if p.get("exclusions"):
        out += ["## Not included", "", *[f"- {x}" for x in p["exclusions"]], ""]
    if p.get("milestones"):
        out += ["## Milestones", "", "| Id | Milestone | Due | Amount | Trigger |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {m['id']} | {md_cell(m['name'])} | {m['due']} | {_amount(m)} | {md_cell(trigger_text(m.get('trigger') or {}))} |" for m in p["milestones"]]
        out.append("")
    if p.get("risks"):
        out += ["## Risks", "", "| Id | Risk | Owner | Status | Likelihood | Impact | Mitigation |", "| --- | --- | --- | --- | --- | --- | --- |"]
        out += [
            f"| {r['id']} | {md_cell(r['text'])} | {md_cell(r['owner'])} | {r['status']} | {r['likelihood']} | {r['impact']} | {md_cell(r.get('mitigation'))} |"
            for r in p["risks"]
        ]
        out.append("")
    open_q = [q for q in p.get("questions", []) if not q.get("answer")]
    if open_q:
        out += ["## Questions for you", "", *[f"- **{q['id']}.** {q['question']}" for q in open_q], ""]
    return "\n".join(out).rstrip() + "\n"


RAID_NOUN = {"Assumptions": "Assumption", "Issues": "Issue", "Dependencies": "Dependency"}
RAID_KEYS = ("risks", "assumptions", "issues", "dependencies")


def _raid(items: list[dict], title: str) -> list[str]:
    """One RAID section as a table: each item with its owner, status, and due date."""
    if not items:
        return []
    out = [f"## {title}", "", f"| Id | {RAID_NOUN[title]} | Owner | Status | Due |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {x['id']} | {md_cell(x['text'])} | {md_cell(x['owner'])} | {x['status']} | {x.get('due') or ''} |" for x in items]
    return out + [""]


def _amount(m: dict) -> str:
    if m.get("amount") is None:
        return ""
    value = m["amount"]
    shown = f"{int(value)}" if float(value).is_integer() else f"{value:.2f}"
    return f"{shown} {m.get('currency', '')}".strip()


def trigger_text(trigger: dict) -> str:
    """A milestone's trigger in words: the Specs, then the Acceptance ids, then any other event."""
    parts = [", ".join(str(x) for x in trigger.get(k) or []) for k in ("specs", "acceptance")] + [str(trigger.get("event") or "")]
    return "; ".join(x for x in parts if x)


def _toml(value) -> str:
    """A TOML value for the fields a milestone holds: text, a number, a list of text, or an inline table of them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return f"{value}"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(x) for x in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    return _q(str(value))


def _tables(key: str, items: list[dict]) -> str:
    """A list of the proposal's tables (its milestones, or a RAID list) as the Initiative's `[[key]]` tables, key for key."""
    return "".join(f"\n[[{key}]]\n" + "".join(f"{k} = {_toml(v)}\n" for k, v in m.items()) for m in items)


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


TITLE_MAX = 120  # epic.schema.json and initiative.schema.json `title` maxLength


def _title(text: str) -> str:
    """A title that fits the schema: a longer one is cut at a word and marked with an ellipsis."""
    text = " ".join(str(text).split())
    if len(text) <= TITLE_MAX:
        return text
    cut = text[: TITLE_MAX - 1].rsplit(" ", 1)[0] or text[: TITLE_MAX - 1]
    return cut.rstrip() + "…"


def convert(p: dict, specs_dir: Path, owner_team: str = "") -> list[Path]:
    """An accepted proposal becomes an Initiative, and one Epic per `epic` group of its needs, in the Specs folder.

    The Initiative names the proposal and takes over its delivery record (the milestones, the RAID log, and the scope
    decisions log), and each Epic names the needs it covers, so a Spec written under them traces back to the promise.
    Needs answered `not_met` promise nothing and go to no Epic.
    """
    if model.proposal_status(p) != "accepted":
        raise ValueError(f"{p['id']} is {model.proposal_status(p)}; only an accepted proposal becomes delivery work")
    groups: dict[str, list[dict]] = {}
    for n in p.get("needs", []):
        if n["answer"] != "not_met":
            groups.setdefault(n.get("epic") or "Delivery", []).append(n)
    init_id = f"INIT-{p['id']}"
    files: list[tuple[Path, str]] = []
    team = owner_team or p.get("owner_team") or "TODO"
    epic_rows = []
    for i, (name, needs) in enumerate(groups.items(), start=1):
        epic_id = f"EPIC-{p['id']}-{i}"
        epic_rows.append(f"| {epic_id} | {md_cell(name)} | {md_cell(team)} | {i} | |")
        covers = ", ".join(_q(n["id"]) for n in needs)
        body = "\n".join(f"- **{n['id']}** ({ANSWER_WORDS[n['answer']].lower()}): {n['need']}" for n in needs)
        files.append(
            (
                specs_dir / f"{epic_id}.md",
                f'+++\naidd_version = "1.0.0"\nkind = "epic"\nid = "{epic_id}"\nparent = "{init_id}"\ntitle = {_q(_title(name))}\n'
                f'goal = "TODO: the measurable outcome of this part of {p["id"]}"\nowner_team = {_q(team)}\ncovers = [{covers}]\n+++\n\n'
                f"## Needs this Epic delivers\n\nFrom {p['id']}, as accepted by {p['addressee']}. Each Spec under this Epic names the needs it meets.\n\n{body}\n",
            )
        )
    exclusions = "\n".join(f"- {x}" for x in p.get("exclusions", [])) or "- none stated"
    # The delivery record moves to the Initiative: the milestones, the whole RAID log, and the scope decisions log, kept
    # current there from now on. The claims stay: they are part of the promise.
    record = "".join(_tables(key, p.get(key) or []) for key in ("milestones", *RAID_KEYS, "decisions"))
    files.insert(
        0,
        (
            specs_dir / f"{init_id}.md",
            f'+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "{init_id}"\ntitle = {_q(_title(p["title"]))}\ngoal = {_q(p["goal"])}\n'
            f"owner_team = {_q(team)}\nproposal = {_q(p['id'])}\n{record}+++\n\n"
            f"## Outcome\n\nDelivers {p['id']}, accepted by {p['addressee']}: {p['goal']}\n\n"
            "## Epics\n\n| Epic | Title | Owner team | Order | Why this order |\n| --- | --- | --- | --- | --- |\n" + "\n".join(epic_rows) + "\n\n"
            f"## Out of scope\n\nWhat {p['id']} excluded:\n\n{exclusions}\n",
        ),
    )
    # Every object is checked before anything is written: a long proposal id makes an id past the 64-character limit,
    # which no truncation can fix without breaking the trace back to the proposal.
    for path, text in files:
        _, _, errors = model.load_object(text, str(path))
        if errors:
            raise ValueError(f"{p['id']} cannot become delivery work as is; {path.name} would not validate: " + "; ".join(errors))
    for path, _ in files:
        if path.exists():
            raise FileExistsError(f"{path} exists")
    specs_dir.mkdir(parents=True, exist_ok=True)
    for path, text in files:
        path.write_text(text, encoding="utf-8")
    return [path for path, _ in files]
