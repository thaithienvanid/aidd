"""The JSON files a harness's ask rules live in, read and written as aidd writes them: read through the safe reader, so a
link, a pipe, or a device is never read, and written with OpenCode's rules one to a line. A file the harness documents as taking
comments (`jsonc`) is read with them and edited in place, so a person's comments, key order, and other settings stay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aidd.kernel import regular_files
from aidd.risk import jsonc


def settings_text(root: Path, rel: str) -> str:
    """A harness's settings file in the repository as text, "" when there is none. It reads through the safe reader, and
    a link, a pipe, or a device there, or a file past the cap, is an error, so aidd never writes over what it never read."""
    text, why = regular_files.named_text(root, rel)
    if text is None and why == regular_files.MISSING:
        return ""
    if text is None:  # never read, and so never written through
        raise ValueError(f"{rel} is {why}, which aidd never reads or writes through: replace it with the file, then run the command again")
    return text


SYNTAX_NAMES = {"json": "JSON", "comments": "JSON with comments", "jsonc": "JSON with comments and trailing commas"}


@dataclass(frozen=True)
class Settings:
    """A settings file as it was read: its text, the data in it, and what its harness lets it hold (`jsonc.py`)."""

    text: str
    data: dict
    syntax: str


def read_settings(root: Path, path: Path, syntax: str = "json") -> Settings:
    """A harness's JSON settings file in the repository, empty when there is none. It reads through the safe reader, and a
    link, a pipe, or a device there is an error, so aidd never reads it and never writes through it. `syntax` is what the
    harness documents the file takes."""
    text, why = regular_files.named_text(root, path.relative_to(root).as_posix())
    if text is None and why == regular_files.MISSING:
        return Settings("", {}, syntax)
    if text is None:  # never read, and so never written through
        raise ValueError(f"{path} is {why}, which aidd never reads; replace it with the file, then run the command again")
    try:
        data = jsonc.loads(text, syntax)
    except ValueError as exc:
        raise ValueError(f"{path} is not valid {SYNTAX_NAMES[syntax]} ({exc}); fix it, then run the command again") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a JSON object; fix it, then run the command again")
    return Settings(text, data, syntax)


def read_json(root: Path, path: Path, syntax: str = "json") -> dict:
    """`read_settings`' data alone."""
    return read_settings(root, path, syntax).data


def save(root: Path, path: Path, was: Settings, new: dict) -> None:
    """Write `new` over a settings file that was read as `was`. A file that takes comments keeps every byte aidd does not
    change (`jsonc.patch`), or is left as it is when the edit cannot be proven; any other is written whole."""
    if was.syntax == "json" or not was.text.strip():
        write_json(root, path, new)
        return
    try:
        out = jsonc.patch(was.text, was.data, new, was.syntax)
    except ValueError as exc:
        raise ValueError(
            f"{path} cannot be edited without changing more than aidd's rules ({exc}), so it is left as it is; add aidd's ask rules by hand"
        ) from exc
    regular_files.write_safely(root, path, out.encode("utf-8"))


def write_json(root: Path, path: Path, data: dict) -> None:
    """Write a harness's JSON settings file in the repository `root` through the safe writer, so a link at it or on the
    way to it, such as `.claude -> ~/.ssh`, is WriteRefused and never written through, even for a file not there yet."""
    regular_files.write_text_safely(root, path, json_text(data))


def json_text(data: dict) -> str:
    """`data` indented, with each rule of a top-level `permissions` list on one line, as OpenCode's rules read best, and a
    third smaller. A marker that the data itself holds falls back to plain indenting."""
    rules = data.get("permissions")
    marks = [f"aidd-rule-{i}" for i in range(len(rules))] if isinstance(rules, list) else []
    plain = json.dumps(data, indent=2)
    if not marks or any(f'"{m}"' in plain for m in marks):
        return plain + "\n"
    text = json.dumps({**data, "permissions": marks}, indent=2)
    for mark, rule in zip(marks, rules or [], strict=True):
        text = text.replace(f'"{mark}"', json.dumps(rule), 1)
    return text + "\n"
