"""The verdict of an `aidd test` run: which results are good, and the exit code the run ends with.

`aidd test` exits on it and `aidd status` summarizes the last run with it, so the two never disagree. Evidence is the
runner's exit code on a commit; this verdict only reads the evidence file that code wrote.
"""

from __future__ import annotations

from aidd.testing.runner import red_ok


def result_good(result: dict) -> bool:
    """A green result passed; a red result failed with a real exit code (the new behavior's test fails on the base)."""
    return (result["red_green"] == "green" and result["status"] == "passed") or (result["red_green"] == "red" and red_ok(result))


def result_mark(result: dict, *, before_implement: bool) -> str:
    """`ok` for a good result, `..` for a failing green run in the Design stage (expected before Implement), else `!!`."""
    if result_good(result):
        return "ok"
    return ".." if before_implement and result["red_green"] == "green" else "!!"


def exit_code(evidence: dict, *, no_red: bool = False) -> int:
    """1 when a result is bad, except in the Design stage, where a failing green run is expected before Implement. A full
    run in a dirty tree proves nothing about the head commit, so it fails too; a quick check (`--changed`, `--no-red`)
    may run mid-change."""
    before_implement = bool(evidence.get("before_implement"))
    bad = any(result_mark(r, before_implement=before_implement) == "!!" for r in evidence["results"])
    dirty_full = evidence.get("dirty_tree") and not evidence.get("partial") and not no_red
    return 1 if bad or dirty_full else 0
