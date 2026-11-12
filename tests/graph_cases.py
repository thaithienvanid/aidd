"""The loop's design as table-driven cases: the facts the files hold, and what aidd reads from them.

The cases are data in tests/fixtures/design/graph_cases/, one file for each table of the design, and every row keeps the design's id
(`T13` for a move of the one transition table, `C1-21` for a deploy shape, `C2-W3` for a stored word, `C2-H12` for a hard case).
A row has a `title`, the design's own words in `says` when they add to it, and either `facts` and `reads` or `variants`: one
`{name, facts, reads}` for each "or" the design's row holds. A variant may carry its own `status_package` and `next_package`.

- `facts`: what the files and git hold. The keys are `intent` and `intents`, `spec` (SPEC-1) and `specs`, `trunk` (what the default
  branch holds, null for none), `branches`, `config`, `releases` (written in any order), `evidence` (this clone's test run, null
  for none), `postmortems`, `scope`, `docs`, `records`, `notes` (handoff notes), `git` (commits with their trailers and what they
  change, tags, the remote, a shallow clone), `told` (what a person said, which is no file), and `day`. tests/graph_repo.py builds
  the files and the scratch repository from them, and every reader starts there.
- `reads`: what the design says is read. `status`, `statuses`, `status_line`, `findings`, `live_in`, and `criteria` say what the
  facts make of the items; `line` (the design's line id), `acts` (`agent` or `person`, null for a line that waits), `action` (an
  action id, or null), and `item_lines` (the same for each item of the row, by address) say who does what next. A value that is a
  list means any of them. A finding is a full phrase, matched whole, or `{"level": ...}` where the design words none.
- `status_package` and `next_package`: the package of the redesign that makes the status part and the next part read right, or
  `today` when the current code reads it right already. tests/fixtures/design/packages.json says what each package does.

`READERS` says which packages have landed: a function for each, from a case's facts to what it reads. A package with no reader yet
is not an error: its cases are expected failures, run against `read_current`, so a case that starts passing fails the run until
its package is added here. `SWITCHED_ON` lists the parts of cases that one Task of a package reads right before the whole package
lands, each with that Task's reader, so they run for real. A reader from a landed package returns the line of every case that has one, and a wrong line fails.
Only `read_current` may leave the line out, because the current code has no lines. The test file runs each part of each case once.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import helpers
import graph_repo
from helpers import ROOT

CASES = ROOT / "tests" / "fixtures" / "design" / "graph_cases"
DESIGN = "the loop's design (d4-whole-loop), as revised after its first build package"
# The design's tables, the file of each, and how many rows the design has in it.
TABLES: dict[str, tuple[str, str, int]] = {
    "transitions": ("transitions.json", "A.12, the whole loop as one transition table", 35),
    "deploy-shapes": ("deploy-shapes.json", "C.1, why a release is stored: 24 deploy shapes and events", 24),
    "stored-words": ("stored-words.json", "C.2, the Spec's stored words", 7),
    "hard-cases": ("hard-cases.json", "C.2, the hard cases", 34),
}
# The packages a case waits on, in the order they land; tests/fixtures/design/packages.json says what each one does.
PACKAGES = ("today", "C2", "C3", "C4", "C5", "C6")
STATUS_KEYS = ("status", "statuses", "status_line", "findings", "live_in", "criteria")
NEXT_KEYS = ("line", "acts", "action", "item_lines")
PARTS = {"status": STATUS_KEYS, "next": NEXT_KEYS}
FACT_KEYS = {
    "intent",
    "intents",
    "spec",
    "specs",
    "trunk",
    "branches",
    "config",
    "releases",
    "evidence",
    "postmortems",
    "scope",
    "docs",
    "records",
    "notes",
    "git",
    "told",
    "day",
}
# The current code has no lines, so its reader may leave these out; every other reader gives them.
LINE_KEYS = ("line", "item_lines")
Reader = Callable[[dict], "dict | None"]


class Case(NamedTuple):
    """One case of a row: the row itself, or one of its variants."""

    row: str
    name: str
    facts: dict
    reads: dict
    status_package: str | None
    next_package: str | None
    needs_person: bool

    @property
    def label(self) -> str:
        return f"{self.row} ({self.name})" if self.name else self.row


def load(table: str) -> list[dict]:
    return json.loads((CASES / TABLES[table][0]).read_text(encoding="utf-8"))["rows"]


def all_rows() -> dict[str, list[dict]]:
    return {table: load(table) for table in TABLES}


def cases_of(row: dict) -> list[Case]:
    """Each case of a row: one for each variant, or the row's own."""
    variants = row.get("variants") or [{"name": "", "facts": row["facts"], "reads": row["reads"]}]
    return [
        Case(
            row["id"],
            v["name"],
            v["facts"],
            v["reads"],
            v.get("status_package", row.get("status_package")),
            v.get("next_package", row.get("next_package")),
            bool(v.get("needs_person", row.get("needs_person"))),
        )
        for v in variants
    ]


def parts_of(case: Case) -> list[str]:
    """The parts of a case that say something: `status` and `next`."""
    return [part for part, names in PARTS.items() if set(case.reads) & set(names)]


def package_of(case: Case, part: str) -> str | None:
    return case.status_package if part == "status" else case.next_package


def count_problems(table: str, rows: list[dict]) -> list[str]:
    """What is wrong with a table's rows: the count against the design, a repeated id, and a case with no package, no read, or no facts."""
    _, label, want = TABLES[table]
    problems = [f"{label}: {len(rows)} rows, and the design has {want}"] if len(rows) != want else []
    ids = [row.get("id") for row in rows]
    problems += [f"{label}: the id {i!r} is used twice" for i in sorted({i for i in ids if ids.count(i) > 1}, key=str)]
    for row in rows:
        if not row.get("title"):
            problems.append(f"{row.get('id')}: it has no title")
        names = [v.get("name") for v in row.get("variants", [])]
        if "variants" in row and (len(names) < 2 or not all(names) or len(set(names)) != len(names)):
            problems.append(f"{row.get('id')}: its variants are fewer than two, or their names are blank or repeat")
        for case in cases_of(row):
            if not parts_of(case):
                problems.append(f"{case.label}: it says nothing is read: a status, a line, who acts, or the action")
            for part in parts_of(case):
                if package_of(case, part) not in PACKAGES:
                    problems.append(f"{case.label}: {part}_package is not one of {PACKAGES}")
            if not case.facts:
                problems.append(f"{case.label}: it has no facts")
    return problems


def finding_matches(want, got: list) -> bool:
    """A finding is read when a reader gives its whole phrase, or a finding of its level where the design words none."""
    if isinstance(want, dict):
        return any(isinstance(g, dict) and g.get("level") == want["level"] for g in got)
    return any(str(g.get("text") if isinstance(g, dict) else g).strip().casefold() == want.strip().casefold() for g in got)


def subset_problems(key: str, want: dict, got: dict, relaxed: bool) -> list[str]:
    """Each key the design gives for an item or a criterion must be what the reader read."""
    out = []
    for address, expected in want.items():
        if address not in got:
            if not relaxed:
                out.append(f"{key}[{address}]: the reader does not read it")
            continue
        for sub, value in (expected if isinstance(expected, dict) else {"": expected}).items():
            mine = got[address].get(sub) if sub else got[address]
            if isinstance(value, dict):
                out += subset_problems(f"{key}[{address}].{sub}", {sub: value}, {sub: mine or {}}, relaxed)
            elif mine != value and not (isinstance(value, list) and mine in value):
                out.append(f"{key}[{address}].{sub}: the design says {value!r}, and the reader read {mine!r}")
    return out


def problems(reads: dict, got: dict | None, part: str, relaxed: bool = False) -> list[str]:
    """What differs between what the design says is read and what a reader read, for the keys of one part. A reader that is
    `relaxed` may leave the lines out; no other reader may."""
    expected = {key: reads[key] for key in PARTS[part] if key in reads}
    if not expected:
        return []
    if got is None:
        return ["the reader cannot read these facts"]
    out = []
    for key, want in expected.items():
        if key not in got:
            if not (relaxed and key in LINE_KEYS):
                out.append(f"{key}: the reader does not read it")
        elif key == "findings":
            out += [f"findings: {w!r} is not among {got[key]}" for w in want if not finding_matches(w, got[key])]
        elif key in ("statuses", "criteria", "item_lines"):
            out += subset_problems(key, want, got[key], relaxed)
        elif got[key] != want and not (isinstance(want, list) and got[key] in want):
            out.append(f"{key}: the design says {want!r}, and the reader read {got[key]!r}")
    return out


# ---- the reader of the current code --------------------------------------------------------------------------------

TODAY = dt.date(2026, 11, 13)
SPEC_KEYS = {"status", "tasks", "revisions", "placeholder"}
WHO = {"agent": "agent", "person": "person"}


def buildable(facts: dict) -> bool:
    """Whether the current code can read the facts: a lone Spec on a branch, with the keys it already has and no approval object."""
    spec = facts.get("spec")
    return set(facts) == {"spec"} and isinstance(spec, dict) and set(spec) <= SPEC_KEYS and spec.get("status") not in ("built", "approved", "in_progress")


@functools.cache
def current_reads() -> dict[str, dict]:
    """What `aidd status` reads today for every buildable case of every row, from one repository that holds each as a Spec."""
    todo: dict[str, str] = {}
    for rows in all_rows().values():
        for row in rows:
            for case in cases_of(row):
                if buildable(case.facts):
                    todo.setdefault(json.dumps(case.facts, sort_keys=True), f"SPEC-{len(todo) + 1}")
    actions = set(json.loads((ROOT / "schemas" / "risks.json").read_text(encoding="utf-8"))["actions"])
    with tempfile.TemporaryDirectory() as tmp:
        built = graph_repo.build({"specs": {spec_id: json.loads(key)["spec"] for key, spec_id in todo.items()}}, Path(tmp).resolve() / "repo")
        items = {item["id"]: item for item in helpers.open_work(built.root, today=TODAY, include_done=True)}
    reads = {}
    for key, spec_id in todo.items():
        item = items[spec_id]
        code = item["next"]["code"]
        reads[key] = {"status": item["status"], "acts": WHO.get(item["next"]["who"]), "action": code if code in actions else None}
    return reads


def read_current(facts: dict) -> dict | None:
    """What aidd's status reads today for the facts, or None for facts it cannot hold."""
    return current_reads().get(json.dumps(facts, sort_keys=True)) if buildable(facts) else None


@functools.cache
def _intent_reads(key: str) -> dict | None:
    facts = json.loads(key)
    iid = (facts["intent"] or {}).get("id", "INTENT-1")
    with tempfile.TemporaryDirectory() as tmp:
        built = graph_repo.build(facts, Path(tmp).resolve() / "repo")
        items = {item["id"]: item for item in helpers.open_work(built.root, today=TODAY, include_done=True)}
        from aidd.workitems import validation

        found = validation.validate_file(built.root / "product" / "intents" / f"{iid}.md")
    if iid not in items:
        return None
    findings = [{"level": "error" if validation.is_error(f) else "warning", "text": f} for f in found]
    return {"status": items[iid]["status"], "findings": findings}


def read_intent_status(facts: dict) -> dict | None:
    """What aidd reads of one Intent's status: its status in `aidd status`, and the findings `aidd validate` gives its file. None for
    facts that hold anything but that one Intent and the commits of its history."""
    if set(facts) - {"intent", "git"} or not isinstance(facts.get("intent"), dict):
        return None
    return _intent_reads(json.dumps(facts, sort_keys=True))


# The reader of each package that has landed, from a case's facts to what it reads. A builder adds its package here when its
# code reads the design's facts: the cases that wait on it then run for real, and a case that fails is a failure.
READERS: dict[str, Reader] = {"today": read_current}
# The parts of the cases that one Task of a package reads right before the whole package lands, by the case's label and its part,
# each with that Task's reader. A part listed here runs for real, so it fails the run when it reads wrong. When the package lands
# whole, its reader goes in READERS and its entries here go.
SWITCHED_ON: dict[tuple[str, str], Reader] = {
    ("T5 (no criteria)", "status"): read_intent_status,
    ("T5 (one criterion)", "status"): read_intent_status,
    ("T6", "status"): read_intent_status,
    ("C2-H23", "status"): read_intent_status,
}


def reader_for(case: Case, part: str, readers: dict[str, Reader], switched: dict[tuple[str, str], Reader]) -> Reader | None:
    """The reader that runs one part of one case for real: its package's, or the Task's that switched the part on; None while it waits."""
    return readers.get(package_of(case, part)) or switched.get((case.label, part))


def run_case(
    case: Case, part: str, readers: dict[str, Reader], current: Reader = read_current, switched: dict[tuple[str, str], Reader] | None = None
) -> list[str]:
    """The problems of one part of one case, read by the reader of its package or of the Task that switched it on, or by the current
    code while it waits."""
    reader = reader_for(case, part, readers, SWITCHED_ON if switched is None else switched) or current
    return [f"{case.label}: {p}" for p in problems(case.reads, reader(case.facts), part, relaxed=reader is read_current)]
