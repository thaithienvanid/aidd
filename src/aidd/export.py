"""`aidd record export`: gate records and gate events as JSON or CSV, for a log store, a warehouse, or a spreadsheet;
and, with `--by-control`, the records and the linked docs grouped by control (schemas/control-evidence.schema.json).

The output is deterministic: the same inputs give the same bytes, whatever order the files were found in, so an export
can be diffed, hashed, and re-run. Records are the files `aidd gate --record` writes (`aidd-record.json` in CI); events
are the JSON lines `aidd gate --events` appends (`aidd-events.jsonl`).
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from . import metrics, model, resources
from .util import EPOCH, parse_time

KINDS = ("records", "events")
FORMATS = ("json", "csv")
_SCHEMA = {"records": "record.schema.json", "events": "event.schema.json"}
_GLOB = {"records": "*.json", "events": "*.jsonl"}


def columns(kind: str) -> list[str]:
    """The CSV columns: the schema's top-level fields, in the schema's order. The schema documents each one."""
    return list(resources.load_json(_SCHEMA[kind])["properties"])


def _files(kind: str, paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out += sorted(f for f in path.rglob(_GLOB[kind]) if f.is_file())
        elif path.is_file():
            out.append(path)
        else:
            raise FileNotFoundError(f"{p}: no such file or directory")
    return out


def _canonical(item: dict) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _is_record(item: object) -> bool:
    return isinstance(item, dict) and all(k in item for k in ("aidd_version", "decision", "failed_rules", "pending_rules"))


def _is_event(item: dict) -> bool:
    return "decision" in item and "ts" in item and "change" in item


def collect(kind: str, paths: list[str], since: str | None = None, tenant: str | None = None) -> list[dict]:
    """Every record or event under `paths` (files, or directories searched for *.json or *.jsonl), each exactly once, in
    a stable order: events by time, then repository, change, and head; records by change and head. Files that are not
    records (such as evidence.json) and lines that are not events are skipped. With `tenant`, only those whose `tenant`
    is that one: an item without a tenant belongs to none."""
    if kind not in KINDS:
        raise ValueError(f"export takes {' or '.join(KINDS)}, not {kind!r}")
    files = _files(kind, paths)
    if kind == "events":
        items = [e for e in metrics.load([str(f) for f in files], since=since) if _is_event(e)]
    else:
        if since:
            raise ValueError("records carry no time, so --since filters events only; export the events, or pass the records of the period")
        items = []
        for f in files:
            try:
                item = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if _is_record(item):
                items.append(item)
    if tenant:
        items = [i for i in items if i.get("tenant") == tenant]
    unique = {_canonical(i): i for i in items}
    if kind == "events":
        key = lambda i: (parse_time(i.get("ts")) or EPOCH, str(i.get("repo") or ""), str(i.get("change") or ""), str(i.get("head_sha") or ""), _canonical(i))  # noqa: E731
    else:
        key = lambda i: (EPOCH, "", str(i.get("change") or ""), str(i.get("head_sha") or ""), _canonical(i))  # noqa: E731  (same shape as events)
    return sorted(unique.values(), key=key)


# ---- Evidence by control ------------------------------------------------------------------------------------------

# A cell that names no control: an empty cell, a placeholder, or a dash.
_NO_ID = re.compile(r"^(?:|TODO.*|-+|—|n/?a)$", re.I)


def _obligations(text: str) -> list[dict]:
    """The rows of a compliance doc's `## Obligations` table that name a control id, one entry per id: the columns by
    their header (`Control id`, `Obligation`, `Control`, `Evidence`, `Owner`), several ids split on commas. A table
    without a `Control id` column declares none."""
    lines = model.section(text, "Obligations").splitlines()
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines if line.strip().startswith("|")]
    rows = [r for r in rows if not all(re.fullmatch(r":?-*:?", c) for c in r)]  # no separator row, whatever read it
    if len(rows) < 2:
        return []
    head = [h.lower() for h in rows[0]]
    col = {key: next((i for i, h in enumerate(head) if h.startswith(key)), None) for key in ("control id", "obligation", "control", "evidence", "owner")}
    if col["control id"] is None:
        return []
    col["control"] = next((i for i, h in enumerate(head) if h.startswith("control") and not h.startswith("control id")), None)
    out = []
    for row in rows[1:]:
        cells = {key: row[i] if i is not None and i < len(row) else "" for key, i in col.items()}
        for cid in (x.strip().strip("`") for x in cells["control id"].split(",")):
            if not _NO_ID.match(cid):
                out.append({"id": cid, **{k: cells[k] for k in ("obligation", "control", "evidence", "owner")}})
    return out


def by_control(root: Path, record_paths: list[str]) -> dict:
    """`aidd record export records --by-control`: the gate records under `record_paths` and the Specs' linked docs,
    grouped by the control ids the Specs' compliance docs declare (the `Control id` column of `## Obligations`). A
    control lists its obligations, the Specs that declare it, every doc those Specs link (the threat model, the
    authorization matrix, the runbook, the compliance doc itself), and the gate records of those Specs. Deterministic:
    sorted by control id, then Spec id, path, change, and head. `unmapped_records` counts the records no control
    reaches, so a gap in the mapping shows."""
    from . import repo, workitems

    cfg = workitems.config_at(root)
    specs_dir = cfg.specs_dir if cfg else "specs"
    controls: dict[str, dict] = {}
    for path in repo.object_files(root, specs_dir):
        try:
            data, _ = model.split_front_matter(path.read_text(encoding="utf-8"), path.name)
        except (OSError, UnicodeDecodeError, model.ModelError):
            continue
        if data.get("kind") != "spec" or not data.get("id"):
            continue
        sid = str(data["id"])
        linked = [d for d in data.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str)]
        files = {d["path"]: repo._matching(root, d["path"]) for d in linked}
        for d in linked:
            if d.get("kind") != "compliance":
                continue
            for rel in files[d["path"]]:
                try:
                    text = (root / rel).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for ob in _obligations(text):
                    c = controls.setdefault(ob.pop("id"), {"obligations": [], "specs": set(), "docs": {}})
                    c["obligations"].append({"spec": sid, "doc": rel, **ob})
                    c["specs"].add(sid)
                    for other in linked:
                        for f in files[other["path"]]:
                            c["docs"][(sid, f)] = {"spec": sid, "kind": str(other.get("kind")), "path": f}
    records = collect("records", record_paths)
    reached: set[str] = set()
    out = []
    for cid in sorted(controls):
        c = controls[cid]
        recs = [
            {k: r.get(k) for k in ("change", "head_sha", "spec_id", "decision", "route", "profile")}
            for r in records
            if str(r.get("spec_id") or "") in c["specs"]
        ]
        reached |= {_canonical(r) for r in records if str(r.get("spec_id") or "") in c["specs"]}
        out.append(
            {
                "id": cid,
                "obligations": c["obligations"],  # in Spec order, then as each doc's table lists them
                "specs": sorted(c["specs"]),
                "docs": [c["docs"][k] for k in sorted(c["docs"])],
                "records": sorted(recs, key=lambda r: (str(r["change"] or ""), str(r["head_sha"] or ""))),
            }
        )
    return {"schema_version": "1", "controls": out, "unmapped_records": sum(1 for r in records if _canonical(r) not in reached)}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list) and all(isinstance(v, str | int | float) and not isinstance(v, bool) for v in value):
        return ";".join(str(v) for v in value)
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return str(value)


# The version of `aidd record export --format json` (schemas/export.schema.json): a new key keeps it, a renamed or
# removed one bumps it.
SCHEMA_VERSION = "1"


def to_json(kind: str, items: list[dict]) -> str:
    """`{schema_version, kind, items}`: the records or events, each as it was written."""
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": kind, "items": items}, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def to_csv(kind: str, items: list[dict]) -> str:
    """One row per item, the columns from `columns(kind)`. Lists of plain values are joined with `;`; objects and lists
    of objects are compact JSON with sorted keys; null is empty; booleans are true and false. A field the schema does
    not name is left out of the CSV (the JSON export keeps it)."""
    cols = columns(kind)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for item in items:
        w.writerow([_cell(item.get(c)) for c in cols])
    return buf.getvalue()


def render(kind: str, items: list[dict], fmt: str) -> str | bytes:
    """`items` in `fmt`: json or csv built in, or an exporter an installed package registers under `aidd.exporters`."""
    if fmt == "json":
        return to_json(kind, items)
    if fmt == "csv":
        return to_csv(kind, items)
    from . import ext

    exporters = ext.installed("aidd.exporters")
    if fmt not in exporters:
        known = ", ".join([*FORMATS, *sorted(exporters)])
        raise ValueError(f"no exporter {fmt!r}; the formats are {known}")
    out = exporters[fmt](kind, items)
    if not isinstance(out, str | bytes):
        raise RuntimeError(f"exporter {fmt!r} returned {type(out).__name__}, not text or bytes")
    return out
