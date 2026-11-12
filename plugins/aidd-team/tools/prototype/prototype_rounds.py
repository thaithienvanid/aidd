"""Review-round comments for a prototype: read the earlier rounds beside a design, or an exploration direction."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

# What a comment asks: the types the viewer offers, and the one a comment without a type reads as.
COMMENT_TYPES = ("change", "remove", "add", "question")
# A round's folder, `rounds/<N>/`, which holds its comments (`comments.json`) and the changes that answer earlier ones.
_ROUND_DIR = re.compile(r"^[0-9]{1,4}$")
# A design in an exploration's `directions/` folder is a direction, named by its file's stem: its comments live in the
# exploration's own rounds, one file per direction, `rounds/<N>/comments-<direction>.json`, and each comment's id starts
# with its name, so two directions' ids never collide.
DIRECTIONS, EXPLORATION_FILE = "directions", "exploration.md"
_DIRECTION_NAME = re.compile(r"[A-Za-z0-9-]+")
# A comment's id, `r<round>-<n>`, or `<direction>-r<round>-<n>` for a direction: the group is the direction it names.
_COMMENT_ID = re.compile(r"(?:([A-Za-z0-9-]+)-)?r[0-9]+-[0-9]+")
# What a page carries, so a large folder never makes a large page: the newest rounds, each item's fields cut, and a
# total across every round.
MAX_ROUNDS, MAX_ITEMS, MAX_TEXT, MAX_TOTAL = 20, 200, 500, 200_000
MAX_FILE_BYTES = 1_000_000  # a comments or changes file read at most this far: larger is left out, never read whole


def _plain(value: object) -> str:
    """A field's text: a string or a number as it reads, anything else (a list, an object, nesting) as nothing."""
    return str(value) if isinstance(value, str | int | float) and not isinstance(value, bool) else ""


def direction_of(root: Path, design: Path) -> tuple[str, Path, str]:
    """A design file's direction: (its name, or "" for a design that is no direction; the folder its rounds live in; and
    why its name is refused, or "")."""
    folder = design.parent
    marker = folder.parent / EXPLORATION_FILE
    inside = folder.parent.resolve().is_relative_to(root.resolve())
    if folder.name != DIRECTIONS or not inside or marker.is_symlink() or not marker.is_file():
        return "", folder, ""
    if not _DIRECTION_NAME.fullmatch(design.stem):
        return (
            "",
            folder.parent,
            f"{design.name}: a direction's file name names its comments file and its comment ids, so it takes letters, digits, and `-` only: rename it, such as directions/a.html",
        )
    return design.stem, folder.parent, ""


def comments_file(direction: str = "") -> str:
    """The name of a round's comments file: `comments.json`, or `comments-<direction>.json` for a direction."""
    return f"comments-{direction}.json" if direction else "comments.json"


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _read_round_json(folder: Path, top: Path, path: Path, problems: list[str]) -> dict:
    """Read one regular JSON object inside `folder`, within MAX_FILE_BYTES."""
    shown = path.relative_to(folder).as_posix()
    try:
        st = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(st.st_mode) or not path.resolve().is_relative_to(top):
            problems.append(f"{shown}: not a plain file in the design folder, so it is left out")
            return {}
        if st.st_size > MAX_FILE_BYTES:
            problems.append(f"{shown}: larger than {MAX_FILE_BYTES} bytes, so it is left out")
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        problems.append(f"{shown}: not JSON ({type(exc).__name__}), so it is left out")
        return {}
    if not isinstance(data, dict):
        problems.append(f"{shown}: not a JSON object, so it is left out")
        return {}
    return data


def _read_listed(folder: Path, data: dict, key: str, where: Path, problems: list[str]) -> list:
    value = data.get(key) or []
    if isinstance(value, list):
        return value
    problems.append(f"{where.relative_to(folder).as_posix()}: `{key}` is not a list, so it is left out")
    return []


def _scan_rounds(folder: Path, top: Path, name: str, problems: list[str]) -> tuple[dict[int, Path], dict[int, set[str]]]:
    """Collect the newest round comment files and the comment ids answered by each round's changes.json."""
    answered: dict[int, set[str]] = {}
    files: dict[int, Path] = {}
    rounds_dir = folder / "rounds"
    found_dirs = [d for d in rounds_dir.iterdir() if _ROUND_DIR.match(d.name)] if rounds_dir.is_dir() and not rounds_dir.is_symlink() else []
    for round_dir in sorted(found_dirs, key=lambda d: (int(d.name), d.name))[-(MAX_ROUNDS + 1) :]:
        num, changes, comments = int(round_dir.name), round_dir / "changes.json", round_dir / name
        if _present(comments) and num in files:
            kept = files[num].relative_to(folder).as_posix()
            problems.append(f"rounds/{round_dir.name}/{name}: round {num} has another file, {kept}, so this one is left out")
        elif _present(comments):
            files[num] = comments
        if not _present(changes):
            continue
        ids: set[str] = set()
        for change in _read_listed(folder, _read_round_json(folder, top, changes, problems), "changes", changes, problems):
            answers = change.get("answers") if isinstance(change, dict) else None
            if isinstance(answers, list):
                ids |= {str(a) for a in answers if isinstance(a, str | int)}
            else:
                problems.append(f"{changes.relative_to(folder).as_posix()}: a change's `answers` is not a list of comment ids")
        answered[num] = ids
    return files, answered


def round_comments(folder: Path, direction: str = "") -> tuple[list[dict], list[str]]:
    """The comments of the earlier rounds beside a design, for the viewer, and what could not be read."""
    problems: list[str] = []
    top = folder.resolve()
    files, answered = _scan_rounds(folder, top, comments_file(direction), problems)
    found: list[dict] = []
    total = 0
    for num in sorted(files)[-MAX_ROUNDS:]:
        later = set().union(*(ids for r, ids in answered.items() if r > num))
        items: list[dict] = []
        shown_file = files[num].relative_to(folder).as_posix()
        for it in _read_listed(folder, _read_round_json(folder, top, files[num], problems), "items", files[num], problems)[:MAX_ITEMS]:
            if not isinstance(it, dict) or not _plain(it.get("id")):
                continue
            cid = _plain(it["id"])
            if (named := _COMMENT_ID.fullmatch(cid)) and (named.group(1) or "") != direction:
                problems.append(f"{shown_file}: {cid[:MAX_TEXT]} is left out: its id names another direction")
                continue
            ctype = _plain(it.get("type")) or "change"
            item = {
                **{k: _plain(it.get(k))[:MAX_TEXT] for k in ("id", "screen", "state", "testid", "comment")},
                "type": ctype if ctype in COMMENT_TYPES else "change",
                "done": cid in later,
            }
            if writer := _plain(it.get("by"))[:MAX_TEXT]:
                item["by"] = writer
            total += sum(len(v) for v in item.values() if isinstance(v, str))
            if total > MAX_TOTAL:
                problems.append(f"the rounds hold more than {MAX_TOTAL} characters, so the rest is left out")
                return [*found, {"round": num, "items": items}], problems
            items.append(item)
        found.append({"round": num, "items": items})
    return found, problems


def _clean_saved_item(raw: object, direction: str, index: int, problems: list[str]) -> dict | None:
    if not isinstance(raw, dict):
        problems.append(f"item {index + 1} is not a JSON object")
        return None
    cid = _plain(raw.get("id"))
    if not cid or not _COMMENT_ID.fullmatch(cid):
        problems.append(f"item {index + 1} has missing or invalid id {_plain(raw.get('id'))!r}")
        return None
    if (named := _COMMENT_ID.fullmatch(cid)) and (named.group(1) or "") != direction:
        problems.append(f"comment `{cid}` names direction `{named.group(1) or 'none'}`, expected `{direction or 'none'}`")
        return None
    required = {k: _plain(raw.get(k))[:MAX_TEXT] for k in ("screen", "state", "comment")}
    if any(not required[k] for k in ("screen", "state", "comment")):
        problems.append(f"comment `{cid}` needs screen, state, and comment")
        return None
    ctype = _plain(raw.get("type")) or "change"
    item: dict = {"id": cid, "type": ctype if ctype in COMMENT_TYPES else "change", **required}
    if tid := _plain(raw.get("testid"))[:MAX_TEXT]:
        item["testid"] = tid
    if isinstance(raw.get("index"), int) and not isinstance(raw.get("index"), bool) and raw["index"] >= 0:
        item["index"] = raw["index"]
    for key in ("frame", "theme", "link", "by"):
        if val := _plain(raw.get(key))[:MAX_TEXT]:
            item[key] = val
    box = raw.get("box")
    if isinstance(box, dict) and all(
        isinstance(box.get(k), int | float) and not isinstance(box.get(k), bool) and math.isfinite(box[k]) for k in ("x", "y", "width", "height")
    ):
        b = {k: int(round(box[k])) for k in ("x", "y", "width", "height")}
        if b["width"] >= 0 and b["height"] >= 0:
            item["box"] = b
    return item


def _reject_constant(token: str) -> None:
    raise ValueError(f"unsupported JSON constant `{token}`")


def _read_source_json(source: str) -> tuple[dict | None, str]:
    if source == "-":
        raw_bytes = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        if len(raw_bytes) > MAX_FILE_BYTES:
            return None, f"{source}: larger than {MAX_FILE_BYTES} bytes"
        try:
            raw_text = raw_bytes.decode("utf-8")
        except ValueError as exc:
            return None, f"{source}: cannot be read ({exc})"
    else:
        path = Path(source)
        try:
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode):
                return None, f"{source}: is a symlink; pass a regular JSON file"
            if not stat.S_ISREG(st.st_mode):
                return None, f"{source}: not a plain file; pass a regular JSON file"
            if st.st_size > MAX_FILE_BYTES:
                return None, f"{source}: larger than {MAX_FILE_BYTES} bytes"
            with path.open("rb") as fh:
                raw_bytes = fh.read(MAX_FILE_BYTES + 1)
            if len(raw_bytes) > MAX_FILE_BYTES:
                return None, f"{source}: larger than {MAX_FILE_BYTES} bytes"
            raw_text = raw_bytes.decode("utf-8")
        except (OSError, ValueError) as exc:
            return None, f"{source}: cannot be read ({exc})"
    try:
        data = json.loads(raw_text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        return None, f"{source}: not valid JSON ({exc})"
    return (data, "") if isinstance(data, dict) else (None, f"{source}: JSON must be an object with `round` and `items`")


def save_round_comments(folder: Path, source: str, *, direction: str = "", round_num: int | None = None) -> tuple[Path | None, list[str]]:
    """Validate exported viewer JSON from `source` and write it into `folder/rounds/<N>/comments[-dir].json`."""
    data, read_err = _read_source_json(source)
    if data is None:
        return None, [read_err]
    chosen = data.get("round") if round_num is None else round_num
    if not isinstance(chosen, int) or isinstance(chosen, bool) or not 1 <= chosen <= 9999:
        return None, ["comments JSON needs an integer `round` from 1 to 9999 (or pass --round N)"]
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return None, ["comments JSON needs a non-empty `items` list"]
    problems: list[str] = []
    cleaned = [it for i, raw in enumerate(raw_items[:MAX_ITEMS]) if (it := _clean_saved_item(raw, direction, i, problems)) is not None]
    if problems:
        return None, problems
    rounds_dir = folder / "rounds"
    target_dir = rounds_dir / str(chosen)
    for step in (folder, rounds_dir, target_dir):
        if step.is_symlink():
            return None, [f"{step} is a symlink: rounds/ must be plain folders"]
        if step.exists() and not step.is_dir():
            return None, [f"{step} is a file, not a folder: rounds/ must be plain folders; move the file away, then save again"]
    dest = target_dir / comments_file(direction)
    if _present(dest):
        return None, [f"{dest.name} in round {chosen} already exists: never overwrite a round file; pass --round {chosen + 1}"]
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"round": chosen, "items": cleaned}, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return dest, []
