"""A finding: one thing a check found, built from its row in schemas/findings.json (`finding` in the common schema).

The row owns what the code means: its severity and its next step. A caller gives the full code, `<group>.<code>`, and the
words that say what it found, so the words of a message live where the check lives and the meaning lives in one file."""

from __future__ import annotations

import functools

from aidd.kernel import resources


@functools.cache
def groups() -> dict[str, dict]:
    """Each group of the registry by name, with its owner and its codes."""
    return dict(resources.load_json("findings.json")["groups"])


def codes() -> dict[str, dict]:
    """Every full code of the registry, `<group>.<code>`, with its row, in the registry's order."""
    return {f"{name}.{code}": row for name, group in groups().items() for code, row in group["codes"].items()}


def finding(code: str, message: str, *, path: str | None = None, line: int | None = None, data: dict | None = None) -> dict:
    """The finding for a full code and the words that say what was found. Its severity and next step come from the code's
    row. A code with no row is a bug in the caller, so it raises."""
    row = codes().get(code)
    if row is None:
        raise KeyError(f"{code} is no code of schemas/findings.json: add its row there")
    made: dict = {"code": code, "severity": row["severity"], "message": message}
    if path is not None:
        made["path"] = path
    if line is not None:
        made["line"] = line
    made["next"] = dict(row["next"])
    if data is not None:
        made["data"] = data
    return made
