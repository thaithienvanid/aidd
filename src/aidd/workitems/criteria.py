"""An Intent's success criteria: each one is a line under its Intent, with an id, an address, and a day read from facts.

A criterion has no status and no file of its own. Its id is `S` and a number (`S1`), unique in its Intent. Its address is the
Intent's id, `#`, and its id (`INTENT-1#S1`), which `from` and `Approves:` name. Its day to measure is never stored: it is the
day of the last release of the Intent's work, where users are, plus `measure_after_days`; a person may type `measure_on`, which
replaces it unless it is earlier than that release. The patterns are the schema's, in `common.schema.json`, and are read from it.
"""

from __future__ import annotations

import datetime as dt
import functools
import re
from collections.abc import Iterable, Mapping
from typing import NamedTuple

from aidd.kernel import git, resources
from aidd.workitems import status

# A commit name as a planned Spec's `merged_in` writes it: hex digits only, so a name read from a file is never an option to git.
_COMMIT = re.compile(r"[0-9a-f]{4,64}")


@functools.cache
def _pattern(name: str) -> re.Pattern[str]:
    """The pattern the common schema gives `$defs.<name>`, compiled."""
    return re.compile(resources.load_json("common.schema.json")["$defs"][name]["pattern"])


def is_id(text: object) -> bool:
    """Whether `text` is a criterion's id (`S1`), by the schema's pattern."""
    return isinstance(text, str) and _pattern("criterion_id").fullmatch(text) is not None


def address(intent_id: str, criterion_id: str) -> str:
    """The address of one criterion: `INTENT-1#S1`."""
    return f"{intent_id}#{criterion_id}"


def parse_address(text: object) -> tuple[str, str] | None:
    """The Intent's id and the criterion's id in an address, or None for text that is no address: `INTENT-1#`, `#S1`, `INTENT-1#S0`,
    `INTENT-1#s1`, and an address with a second `#` or text round it."""
    if not isinstance(text, str) or _pattern("criterion_address").fullmatch(text) is None:
        return None
    intent_id, _, criterion_id = text.partition("#")
    return intent_id, criterion_id


def criteria_of(data: dict) -> list[dict]:
    """The Intent's criteria that carry an id, in the order it lists them. A field of the wrong shape counts as empty, and
    `aidd validate` names it by the schema."""
    found = data.get("success_criteria")
    return [c for c in found if isinstance(c, dict) and is_id(c.get("id"))] if isinstance(found, list) else []


def duplicate_ids(data: dict) -> list[str]:
    """The criterion ids that the Intent lists more than once, once each, in the order of their second appearance."""
    seen: set[str] = set()
    twice: list[str] = []
    for c in criteria_of(data):
        cid = str(c["id"])
        if cid in seen and cid not in twice:
            twice.append(cid)
        seen.add(cid)
    return twice


def _day(value: object) -> dt.date | None:
    """The day a `YYYY-MM-DD` text names, else None. A stricter read than a timestamp's: a criterion's day is a date."""
    try:
        return dt.date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def measure_day(criterion: dict, last_release: dt.date | None) -> tuple[dt.date | None, str]:
    """The day to read the measure, and a note when a `measure_on` is ignored. None before a release: nothing is measured on code that
    users do not have. After it, the release day plus `measure_after_days`; a `measure_on` replaces that unless it is earlier than the
    release, and then it is ignored, with the note."""
    days = criterion.get("measure_after_days")
    if last_release is None or not isinstance(days, int) or isinstance(days, bool) or days < 1:
        return None, ""
    due = last_release + dt.timedelta(days=days)
    chosen = _day(criterion.get("measure_on"))
    if chosen is None:
        return due, ""
    if chosen < last_release:
        return due, f"{criterion.get('id')}: measure_on {chosen} is earlier than the last release ({last_release}), so aidd ignores it and reads {due}"
    return chosen, ""


def result_of(criterion: dict, last_release: dt.date | None) -> dict | None:
    """What the criterion read, as `{measured_on, decision}`, or None while it has no result that counts. A result needs the two fields
    the schema requires of every result, a day and a decision. It counts only when it was measured on or after the last release: one
    measured before it is discarded with it, and while the release day is not known nothing counts, because nothing is measured on
    code that users may not have."""
    result = criterion.get("result")
    if not isinstance(result, dict) or last_release is None:
        return None
    measured, decision = _day(result.get("measured_on")), result.get("decision")
    if measured is None or not isinstance(decision, str) or measured < last_release:
        return None
    return {"measured_on": measured.isoformat(), "decision": decision}


def counted(data: dict, last_release: dt.date | None) -> dict:
    """The Intent with each criterion's `result` kept only where it counts (`result_of`), so a reader that asks whether the results are
    in reads the same answer as `aidd status` gives for each criterion."""
    kept = [c if result_of(c, last_release) else {k: v for k, v in c.items() if k != "result"} for c in criteria_of(data)]
    return {**data, "success_criteria": kept}


def measured(data: dict) -> bool:
    """Whether the Intent has criteria and every one holds a result. Ask it of `counted(...)`, so a discarded result is not one."""
    found = criteria_of(data)
    return bool(found) and all(isinstance(c.get("result"), dict) for c in found)


def rows(data: dict, last_release: dt.date | None) -> list[dict]:
    """The Intent's criteria as `aidd status --json` gives them (schemas/status.schema.json, `$defs.criterion`)."""
    out = []
    for c in criteria_of(data):
        day, _ = measure_day(c, last_release)
        metric = c.get("metric")
        name = metric.get("name") if isinstance(metric, dict) else None
        out.append(
            {
                "id": c["id"],
                "address": address(str(data.get("id")), c["id"]),
                "metric_name": name if isinstance(name, str) else "",
                "measure_from": day.isoformat() if day else None,
                "result": result_of(c, last_release),
            }
        )
    return out


def notes(data: dict, last_release: dt.date | None) -> list[str]:
    """What aidd tells a person about the days it read: each `measure_on` that it ignored, and why."""
    return [note for c in criteria_of(data) if (note := measure_day(c, last_release)[1])]


class Work(NamedTuple):
    """What is known of the work Intents plan: each item's status, each Spec's front matter, each planned Spec's line, and the day of
    each commit a line records as `merged_in`."""

    states: Mapping[str, str]
    specs: Mapping[str, dict]
    lines: Mapping[str, tuple[dict, dict, dict]]
    merged_on: Mapping[str, dt.date]


def _read_release(
    kids: Iterable[str],
    work: Work,
) -> tuple[dt.date | None, list[str]]:
    """The day users got the last of an Intent's work, or None while any of it is not released, and why a day cannot be read where the
    work says it is built. `kids` are its planned Specs and its child Specs. A Spec that has its file is released on
    `status.released_on`, and failing that on the day of its line's `merged_in` commit (`merged_on`, from `merged_days_of`). A cancelled
    child never reached anyone, and a rolled-back one no longer has. A line with a `repo` was built in another repository, which aidd
    cannot read, and a `merged_in` commit this clone lacks cannot be read either: each is a reason, never a guess."""
    days: list[dt.date] = []
    reasons: list[str] = []
    unknown = False
    states, specs, lines, merged_on = work
    for kid in kids:
        state = states.get(kid)
        if state == "cancelled":
            continue
        if state == "rolled_back":
            unknown = True
            continue
        line = lines.get(kid)
        sha = str(line[2].get("merged_in") or "") if line else ""
        repo = str(line[2].get("repo") or "") if line else ""
        day = status.released_on(specs[kid]) if kid in specs else None
        if day is None and sha and repo:
            reasons.append(f"{kid} was built in another repository ({repo}), which aidd cannot read, so the day of its commit {sha[:10]} is not known here")
        elif day is None and sha:
            day = merged_on.get(sha)
            if day is None:
                reasons.append(f"{kid}: its merged_in commit {sha[:10]} is not in this clone, so its day is not checked: fetch the history")
        if day is None:
            unknown = True
        else:
            days.append(day)
    return (None if unknown else max(days, default=None)), reasons


def last_release(
    kids: Iterable[str],
    work: Work,
) -> dt.date | None:
    """The day users got the last of an Intent's work, or None while any of it is not released or its day cannot be read (`_read_release`)."""
    return _read_release(kids, work)[0]


def unread_days(
    kids: Iterable[str],
    work: Work,
) -> list[str]:
    """Why the day of some of an Intent's work cannot be read here: built in another repository, or its commit is not in this clone."""
    return _read_release(kids, work)[1]


def reads_of(
    found: Iterable[tuple[str, dict]],
    children: Mapping[str, list[str]],
    work: Work,
) -> dict[str, tuple[dict, dt.date | None]]:
    """For each Intent with criteria, by id: the fields `aidd status` adds to its item (`criteria`, and `criteria_note` when the day of
    some of its work cannot be read) and the last release they were read from, which the product line reads results by as well."""
    out: dict[str, tuple[dict, dt.date | None]] = {}
    for _, d in found:
        if d.get("type") != "intent" or not d.get("id") or not criteria_of(d):
            continue
        kids = children.get(str(d["id"]), [])
        last = last_release(kids, work)
        why = unread_days(kids, work)
        out[str(d["id"])] = ({"criteria": rows(d, last), **({"criteria_note": "; ".join(why)} if why else {})}, last)
    return out


def merged_days_of(root: str, items: Iterable[dict]) -> dict[str, dt.date]:
    """The day of each commit that the planned Spec lines of the Intents with success criteria record as `merged_in`, for the day a
    criterion is measured from. A line with a `repo` names a commit of another repository, so it is left out. Empty when no such line
    exists, so no git call is made."""
    names = []
    for d in items:
        if d.get("type") == "intent" and criteria_of(d) and isinstance(d.get("phases"), list):
            for phase in (p for p in d["phases"] if isinstance(p, dict) and isinstance(p.get("specs"), list)):
                names += [str(s["merged_in"]) for s in phase["specs"] if isinstance(s, dict) and s.get("merged_in") and not s.get("repo")]
    return merged_days(root, names)


def merged_days(root: str, names: Iterable[str]) -> dict[str, dt.date]:
    """The day, in UTC, of each commit that `names` give, by the name as given. A name that no commit of the repository has is left
    out, and outside a repository the answer is empty."""
    wanted = [n for n in dict.fromkeys(names) if _COMMIT.fullmatch(n)]
    if not wanted or git.repository_top(root) is None:
        return {}
    out: dict[str, dt.date] = {}
    for name, raw in git.raw_commits(wanted, root).items():
        head = raw.partition(b"\n\n")[0].decode("utf-8", errors="replace")
        stamp = next((line.split()[-2] for line in head.split("\n") if line.startswith("committer ") and len(line.split()) >= 3), "")
        if stamp.isdigit():
            out[name] = dt.datetime.fromtimestamp(int(stamp), dt.UTC).date()
    return out
