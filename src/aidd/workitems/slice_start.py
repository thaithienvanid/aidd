"""Start a slice: `aidd new spec <id>` for an id an Intent lists writes the Spec from its slice line.

The Spec takes the slice's title, the Intent as its `parent`, and the slice's `owner_team` and `blocked_by`, which leave
the line, so each fact keeps one owner: the Spec. A line written in flow style on one line (`- {id: ..., title: ...}`) is
rewritten; any other line keeps its facts and the Spec copies the team alone. A slice whose line names `drafted_in`
starts from that commit's draft of the Spec, so a draft that became a line returns whole, and its `drafted_in` leaves
the line, because the Spec file holds the draft again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from aidd.kernel import documents, git, strict_yaml
from aidd.workitems import intents, objects

# The slice fields that leave the line when its Spec file is written: a Spec takes the first two over, and `drafted_in`
# is spent once the draft is back.
MOVED = ("owner_team", "blocked_by", "drafted_in")


@dataclass(frozen=True)
class SliceFound:
    """A slice line and the Intent that lists it."""

    intent_path: Path
    intent_id: str
    line: dict


def find_slice(root: Path, specs_dir: str, slice_id: str) -> SliceFound | None:
    """The slice `slice_id` and its Intent, in the Specs folder; None when no Intent lists it."""
    for path in objects.object_files(root, specs_dir):
        if objects.front_type(path) != "intent":
            continue
        try:
            data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())
        except (documents.DocumentError, OSError):
            continue
        found = intents.slice_lines([data]).get(slice_id)
        if found:
            return SliceFound(path, str(data.get("id")), found[2])
    return None


def drafted_text(root: Path, specs_dir: str, found: SliceFound) -> str | None:
    """The draft of the slice's Spec at the commit its line names in `drafted_in`, with `parent` set to the Intent; None
    when the line names none, or the commit holds no such draft. A ValueError when this clone does not hold the commit
    (a shallow clone), because the blank template would silently drop the draft."""
    sha = str(found.line.get("drafted_in") or "")
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return None
    text = git.show(sha, f"{specs_dir.rstrip('/')}/{found.line['id']}.md", str(root))
    if text is None and git.attempt(["cat-file", "-e", f"{sha}^{{commit}}"], str(root))[0] != 0:
        raise ValueError(
            f"the draft of {found.line['id']} is in commit {sha[:12]}, which this clone does not hold: run `git fetch --unshallow` "
            "(or `git fetch origin` in a full clone), then run `aidd new spec` again"
        )
    if not text or not text.startswith("---\n"):
        return None
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        return None
    lines = [ln for ln in head.split("\n") if not ln.startswith("parent:")]
    at = next((i + 1 for i, ln in enumerate(lines) if ln.startswith("type:")), 0)
    lines.insert(at, f"parent: {strict_yaml.scalar(found.intent_id)}")
    return "---\n" + "\n".join(lines) + sep + body


def with_blocked_by(text: str, waits: list[str]) -> str:
    """A new Spec's text with a `blocked_by` relation for each id in `waits`, added to its front matter."""
    if not waits or not text.startswith("---\n"):
        return text
    head, sep, body = text[4:].partition("\n---\n")
    head = strict_yaml.append_items(head + "\n", "relations", [{"type": "blocked_by", "id": w} for w in waits]).rstrip("\n")
    return "---\n" + head + sep + body


def moved_out(found: SliceFound) -> str | None:
    """The Intent's text with the moved fields gone from the slice's line, when the line is one flow mapping that holds
    one; None when nothing moves, or the line keeps its facts."""
    if not any(k in MOVED for k in found.line):
        return None
    text = found.intent_path.read_text(encoding="utf-8")
    sid = re.escape(str(found.line["id"]))
    pattern = re.compile(rf"^(?P<pad>[ \t]*- )\{{[^\n]*\bid: *[\"']?{sid}[\"']?[,}}][^\n]*\}}[ \t]*$", re.M)
    hits = list(pattern.finditer(text))
    if len(hits) != 1:
        return None
    kept = {k: v for k, v in found.line.items() if k not in MOVED}
    new = text[: hits[0].start()] + hits[0].group("pad") + strict_yaml.flow(kept) + text[hits[0].end() :]
    try:
        documents.split_front_matter(new, found.intent_path.as_posix())
    except documents.DocumentError:
        return None
    return new
