"""The findings that `aidd validate --json` and `aidd status --json` print beside their lists of text (`finding` in the common
schema). Each line the command already gives is the message of one finding, taken as the list holds it, so a list and its
findings never disagree. The checks do not carry codes of their own yet: a finding's code says its kind, and its message
says the rest."""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import findings
from aidd.workitems import validation


def validate_findings(errors: list[str], warnings: list[str], notes: list[str], root: Path) -> list[dict]:
    """One finding for each error, warning, and note of `aidd validate`, in that order, with each message as its list gives it.
    A message that opens with the path of a file in `root` (`<path>: <what is wrong>`) gives that path."""
    found = [
        findings.finding("validate.no_config", e) if e == validation.NO_CONFIG else findings.finding("validate.error", e, path=_file_named(e, root))
        for e in errors
    ]
    found += [findings.finding("validate.warning", w, path=_file_named(w, root)) for w in warnings]
    found += [findings.finding("validate.note", n, path=_file_named(n, root)) for n in notes]
    return found


def _file_named(message: str, root: Path) -> str | None:
    """The file that `message` opens with, as a path from `root`, or None: only a relative path of a regular file inside `root`."""
    head, colon, _ = message.partition(": ")
    if not colon or not head or "\n" in head or Path(head).is_absolute() or ".." in Path(head).parts:
        return None
    try:
        inside = (root / head).resolve().is_relative_to(root.resolve()) and (root / head).is_file()
    except (OSError, ValueError):
        return None
    return Path(head).as_posix() if inside else None


def status_findings(answer: dict) -> list[dict]:
    """One finding for each work item `aidd status` could not read, each shared id, and each thing past its due date, from the answer."""
    found = [
        findings.finding("status.unreadable_item", u["error"], path=u["path"], data={"place": u["place"]} if "place" in u else None)
        for u in answer.get("unreadable", [])
    ]
    found += [
        findings.finding(
            "status.duplicate_id",
            f"{len(d['paths'])} files share {d['id']} ({', '.join(d['paths'])}): run `aidd validate`, then give one of them a new id",
            path=d["paths"][0],
            data={"id": d["id"], "paths": d["paths"], **({"place": d["place"]} if "place" in d else {})},
        )
        for d in answer.get("duplicate_ids", [])
    ]
    return found + [findings.finding("status.overdue", d["what"], path=d["path"]) for d in answer.get("due", [])]
