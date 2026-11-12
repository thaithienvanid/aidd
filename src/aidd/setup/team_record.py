"""The record of the team files aidd wrote (`.aidd/team-files.json`), so `aidd upgrade` and `aidd uninstall` remove a file
aidd no longer writes, and only while it still holds what aidd wrote.

`aidd init --aidd-team` and `aidd upgrade` record each team file by its path and the SHA-256 of the text aidd wrote, as
`.aidd/harness-rules.json` records the ask rules. A recorded path this aidd no longer writes for any harness is stale:
it goes when its hash still matches, and a changed one stays, with a note.

The record is committed repository text, so it is data, never an instruction: a path in it counts only when it is one
aidd writes or once wrote, never through a link, and never outside the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from aidd import config
from aidd.kernel.regular_files import link_on_the_way, regular_file_bytes, repository_text
from aidd.setup import files

# The role and flow names aidd wrote and writes no more, in the order they retired. A name goes here when its role or flow
# leaves the team, so `aidd upgrade` and `aidd uninstall` can tell its recorded files from a path aidd never wrote. None
# has left since 1.0.0.
RETIRED_ROLES: tuple[str, ...] = ()
RETIRED_FLOWS: tuple[str, ...] = ()
# A live role and flow whose paths show where each harness keeps a role's or a flow's files.
_ROLE_TEMPLATE, _FLOW_TEMPLATE = "developer", "plan"
# A team file is a few KiB; a recorded path that is larger is not one aidd wrote.
MAX_BYTES = 512 * 1024
PREFIX = "aidd-"  # the start of every team file's or folder's own name (setup.domain_packs.TEAM_PREFIX)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_record(root: Path) -> dict[str, str]:
    """The recorded team files, path to SHA-256, as the file says; empty when the repository has no record or it does not read."""
    text = _text(root, config.TEAM_FILES_FILE)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    listed = data.get("files") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in listed.items()} if isinstance(listed, dict) else {}


def write_record(root: Path, wanted: dict[str, str], actions: list[str]) -> None:
    """Record each team file on disk that holds what aidd writes there; a file a person kept is not aidd's to record. It
    writes as every aidd write does (`files.write_or_skip`): never through a link on the way, nor at the file, and `actions` names a
    refusal."""
    mine = {rel: digest(text) for rel, text in sorted(wanted.items()) if _text(root, rel) == text}
    # A link, a hard link, or a device there is skipped and named: the record stays as it was, and a file goes only by the record's hash.
    text = json.dumps({"files": mine}, indent=2) + "\n"
    changed = repository_text(root, config.TEAM_FILES_FILE) != text
    if files.write_or_skip(root, root / config.TEAM_FILES_FILE, text, actions) and changed:
        actions.append(f"updated  {config.TEAM_FILES_FILE} (the team files aidd wrote, so a later run removes only those)")


def _text(root: Path, rel: str) -> str | None:
    """A regular file's text inside the repository, never through a link; None for anything else."""
    if _unsafe(rel) or link_on_the_way(root, rel):
        return None
    data, _why = regular_file_bytes(root, rel, MAX_BYTES)
    if data is None or len(data) > MAX_BYTES:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _unsafe(rel: str) -> bool:
    """A path that could leave the repository: absolute, with `..`, or with a backslash a Windows checkout reads as a step."""
    p = PurePosixPath(rel)
    return not rel or p.is_absolute() or ".." in p.parts or "\\" in rel or rel.startswith("~")


def retired_paths(every: dict[str, str]) -> set[str]:
    """Each path a retired role or flow had, rendered from a live one's paths in `every` (all of `team_files()`)."""
    out: set[str] = set()
    for template, names in ((_ROLE_TEMPLATE, RETIRED_ROLES), (_FLOW_TEMPLATE, RETIRED_FLOWS)):
        pattern = re.compile(rf"(?<=/){PREFIX}{template}(?=[./])")
        for rel in every:
            if pattern.search(rel):
                out.update(pattern.sub(f"{PREFIX}{name}", rel) for name in names)
    return out


def stale(root: Path, every: dict[str, str]) -> tuple[list[tuple[str, bool]], list[str]]:
    """The team files aidd wrote that this aidd writes for no harness (`every`, all of `team_files()`), each with whether
    it still holds what aidd wrote; and each record entry ignored, because it names no path aidd writes or once wrote.
    Only a regular file inside the repository, reached through no link, counts."""
    retired = retired_paths(every)
    record = read_record(root)
    ignored = sorted(rel for rel in record if rel not in every and rel not in retired)
    found = [(rel, digest(text) == sha) for rel, sha in record.items() if rel in retired and (text := _text(root, rel)) is not None]
    return found, ignored


def remove(root: Path, rel: str) -> bool:
    """Remove one team file, never through a link, then each folder it leaves empty that aidd's own path names (one named
    `aidd-<name>`, and the folders inside it), strictly inside the repository. False when it removed nothing."""
    if _unsafe(rel) or link_on_the_way(root, rel) or not (root / rel).is_file():
        return False
    (root / rel).unlink()
    parts = PurePosixPath(rel).parts[:-1]
    first = next((i for i, part in enumerate(parts) if part.startswith(PREFIX)), None)
    if first is None:
        return True
    for k in range(len(parts), first, -1):
        folder = root.joinpath(*parts[:k])
        if link_on_the_way(root, folder.relative_to(root)) or not folder.is_dir() or any(folder.iterdir()):
            break
        folder.rmdir()
    return True
