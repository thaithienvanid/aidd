"""The store's speed budgets, measured at the store design's sizes. It runs by hand, never in the per-change suite
(tests/run.py collects only `tests/test_*.py`):

    python3 tests/benchmarks/store_budgets.py

It builds, in a temporary folder, a day log of 50,000 records, 10,000 work-item rows, and 100,000 decision statements
for the fold, then times each path the design budgets. It prints a table, and exits 1 when a path is over its budget.
The budgets are the design's: the guard's append adds under 2 ms, a warm `aidd list` (open, a refresh with nothing
new, one indexed query) takes under 100 ms, and a full rebuild takes under 10 s. A refresh after 100 new records
must fit the warm list's 100 ms, since the cost follows the change, and the fold alone must fit the rebuild's 10 s.
"""

from __future__ import annotations

import random
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aidd import store  # noqa: E402

LOG_RECORDS, WORK_ITEMS, STATEMENTS, APPENDS_TIMED, NEW_RECORDS = 50_000, 10_000, 100_000, 2_000, 100
REVOKING = {"revoke", "reject"}


def synthetic_statements(count: int, seed: int = 267) -> list[store.Statement]:
    """`count` statements over count/4 keys: chains of grants, with revokes, rejections, and concurrent pairs."""
    rng = random.Random(seed)
    statements: list[store.Statement] = []
    last: dict[int, str] = {}
    for n in range(count):
        key = rng.randrange(count // 4)
        kind = rng.choices(["approve", "revoke", "reject"], weights=[8, 1, 1])[0]
        supersedes = (last[key],) if key in last and rng.random() < 0.9 else ()
        statement = store.Statement(f"s{n:07}", f"SPEC-{key % 10_000}", "spec_approval", f"sha256:{key:x}", kind, supersedes)
        statements.append(statement)
        last[key] = statement.id
    return statements


def projections(log_dir: Path, statements: list[store.Statement]) -> list[store.Projection]:
    work_items = [
        {"id": f"SPEC-{n}", "title": f"Work item {n}", "status": ("open", "approved", "landed")[n % 3], "branch": f"spec-{n}"} for n in range(WORK_ITEMS)
    ]

    def read_items(marks: Mapping[str, str]) -> store.Batch:
        return store.Batch({}) if marks.get("items") == "1" else store.Batch({"items": "1"}, {"work_items": work_items})

    def read_decisions(marks: Mapping[str, str]) -> store.Batch:
        if marks.get("statements") == str(len(statements)):
            return store.Batch({})
        folded = store.fold_statements(statements, REVOKING)
        rows = [{"item": k[0], "decision": k[1], "digest": k[2], "stands": int(s.stands), "conflict": len(s.conflict)} for k, s in folded.items()]
        return store.Batch({"statements": str(len(statements))}, {"decisions": rows})

    def read_records(marks: Mapping[str, str]) -> store.Batch:
        rows, ends = [], {}
        for part in store.read_since(log_dir, {k: int(v) for k, v in marks.items()}):
            rows += [{"id": r["id"], "type": r["type"], "subject": r.get("subject")} for r in part.records]
            ends[part.source] = str(part.end)
        return store.Batch(ends, {"records": rows})

    return [
        store.Projection(
            "work_items",
            {"work_items": "id TEXT PRIMARY KEY, title TEXT, status TEXT, branch TEXT"},
            read_items,
            ("CREATE INDEX work_items_status ON work_items (status, id)",),
        ),
        store.Projection(
            "decisions",
            {"decisions": "item TEXT, decision TEXT, digest TEXT, stands INTEGER, conflict INTEGER, PRIMARY KEY (item, decision, digest)"},
            read_decisions,
        ),
        store.Projection("records", {"records": "id TEXT PRIMARY KEY, type TEXT, subject TEXT"}, read_records),
    ]


def seconds(action: Callable[[], object]) -> float:
    start = time.perf_counter()
    action()
    return time.perf_counter() - start


def append_one(log_dir: Path, n: int) -> None:
    store.append(log_dir, "main", store.new_record("aidd.guard.denied", "aidd/guard", {"path": f"src/file_{n}.py", "rule": "scope"}, subject=f"SPEC-{n % 500}"))


def measure(folder: Path) -> list[tuple[str, str, float, float]]:
    """(path, size, measured in ms, budget in ms) for each budgeted path."""
    log_dir, index_path = folder / "log", folder / "index.sqlite"
    timed = [seconds(lambda n=n: append_one(log_dir, n)) * 1000 for n in range(APPENDS_TIMED)]
    for n in range(APPENDS_TIMED, LOG_RECORDS):
        append_one(log_dir, n)
    statements = synthetic_statements(STATEMENTS)
    fold_ms = seconds(lambda: store.fold_statements(statements, REVOKING)) * 1000
    every = projections(log_dir, statements)
    with store.open_index(index_path) as index:
        rebuild_ms = seconds(lambda: index.rebuild(every)) * 1000
    for n in range(NEW_RECORDS):
        append_one(log_dir, LOG_RECORDS + n)
    with store.open_index(index_path) as index:
        refresh_ms = seconds(lambda: index.refresh(every)) * 1000

    def warm_list() -> None:
        with store.open_index(index_path) as index:
            index.refresh(every)
            index.rows("SELECT id, title, branch FROM work_items WHERE status = 'open' ORDER BY id")

    warm_ms = statistics.median(seconds(warm_list) * 1000 for _ in range(5))
    return [
        ("append a record (p95)", f"{APPENDS_TIMED:,} appends", statistics.quantiles(timed, n=20)[18], 2),
        ("fold the statements", f"{STATEMENTS:,} statements", fold_ms, 10_000),
        ("rebuild the index", f"{WORK_ITEMS:,} items, {STATEMENTS:,} statements, {LOG_RECORDS:,} records", rebuild_ms, 10_000),
        ("refresh after new records", f"{NEW_RECORDS} new of {LOG_RECORDS:,}", refresh_ms, 100),
        ("warm list (median of 5)", f"{WORK_ITEMS:,} items", warm_ms, 100),
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aidd-store-budgets-") as tmp:
        results = measure(Path(tmp))
    width = max(len(path) for path, *_ in results)
    size_width = max(len(size) for _, size, *_ in results)
    print(f"{'path':<{width}}  {'size':<{size_width}}  {'measured':>11}  {'budget':>10}  result")
    over = 0
    for path, size, measured, budget in results:
        ok = measured <= budget
        over += not ok
        print(f"{path:<{width}}  {size:<{size_width}}  {measured:>8.2f} ms  {budget:>7,} ms  {'within' if ok else 'OVER'}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
