"""`aidd export`: gate records and gate events as JSON or CSV, for a log store, a warehouse, or a spreadsheet.

The output is deterministic: the same inputs give the same bytes, whatever order the files were found in, so an export
can be diffed, hashed, and re-run. Records are the files `aidd gate --record` writes (`aidd-record.json` in CI); events
are the JSON lines `aidd gate --events` appends (`aidd-events.jsonl`).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from . import metrics, resources
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


def to_json(items: list[dict]) -> str:
    return json.dumps(items, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


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
        return to_json(items)
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
