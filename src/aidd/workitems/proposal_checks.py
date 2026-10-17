"""What a proposal owes while it is drafted and signed off, and the change orders beside it."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from aidd.kernel import documents
from aidd.workitems import authoring, spec_file

# A change order the sign-off check reads: a regular file `CO-<n>.md` directly in the proposal's `change-orders/`.
_CHANGE_ORDER_NAME = re.compile(r"CO-\d+\.md")
# The one line of the change-order template that names the proposal hash after the change; the rest of the file is not read.
_CHANGE_ORDER_HASH = re.compile(r"(?m)^[ \t]*Proposal hash after this change:[ \t]*(`?)([0-9a-f]{32})\1[ \t]*$")
_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


def proposal_findings(path: Path, text: str, data: dict) -> list[str]:
    """What a proposal owes. While it is drafted (go recorded, no sign-off yet), an open dependency names its owner, due
    date, and mitigation (a warning): a person sets them before the sign-off, so the change needs no new sign-off.
    Once signed off, its text still matches `sign_off.hash`, or a change order names the new hash (an error
    otherwise). A sign-off with no hash binds no text (a warning)."""
    out = []
    if spec_file.proposal_status(data) == "drafting":
        for dep in data.get("dependencies") or []:
            if not isinstance(dep, dict) or dep.get("status") != "open":
                continue
            missing = [what for key, what in (("owner", "owner"), ("due", "due date"), ("mitigation", "mitigation")) if not str(dep.get(key) or "").strip()]
            if missing:
                them = "it" if len(missing) == 1 else "them"
                out.append(
                    f"warning: {path}: dependency {dep.get('id')} is open and has no {' and no '.join(missing)}; a person sets {them} before the sign-off"
                )
    sign_off = data.get("sign_off")
    if not isinstance(sign_off, dict):
        return out
    now = spec_file.proposal_hash(text)
    signed = sign_off.get("hash")
    if not signed:
        out.append(f"warning: {path}: sign_off records no hash, so it binds no text; a person adds sign_off.hash from `aidd hash {path.as_posix()}`")
    elif signed != now:
        named, unread = _change_order_hashes(path)
        out += unread
        if now not in named:
            out.append(
                f"{path}: the proposal changed after sign-off: its hash is {now}, and sign_off.hash is {signed}. "
                f"A person signs it off again, or a change order in {authoring.CHANGE_ORDERS}/ records the change "
                "and names the new hash on its `Proposal hash after this change:` line"
            )
    return out


def _change_order_hashes(path: Path) -> tuple[set[str], list[str]]:
    """The hashes the change orders beside the proposal at `path` name, and a warning for each one not read.

    It reads only regular files named `CO-<n>.md` directly in `change-orders/`: never a symlink, a symlinked folder, a
    subfolder, or a file over model.MAX_DOCUMENT_BYTES. In each, only the template's `Proposal hash after this change:`
    line counts, outside HTML comments."""
    folder = path.parent / authoring.CHANGE_ORDERS
    if folder.is_symlink():
        return set(), [f"warning: {path}: {authoring.CHANGE_ORDERS}/ is not read: it is a symlink"]
    try:
        entries = sorted((e for e in os.scandir(folder) if _CHANGE_ORDER_NAME.fullmatch(e.name)), key=lambda e: e.name)
    except FileNotFoundError:
        return set(), []
    except OSError as exc:
        return set(), [f"warning: {path}: {authoring.CHANGE_ORDERS}/ is not read: {exc.strerror or exc}"]
    named: set[str] = set()
    unread = []
    for entry in entries:
        why = ""
        try:
            if entry.is_symlink():
                why = "it is a symlink"
            elif not entry.is_file(follow_symlinks=False):
                why = "it is not a regular file"
            else:
                body = _read_change_order(entry.path)
                if body is None:
                    why = f"it is over {documents.MAX_DOCUMENT_BYTES} bytes"
                else:
                    named.update(m.group(2) for m in _CHANGE_ORDER_HASH.finditer(_HTML_COMMENT.sub("", body)))
        except OSError as exc:
            why = exc.strerror or str(exc)
        if why:
            unread.append(f"warning: {path}: change order {authoring.CHANGE_ORDERS}/{entry.name} is not read: {why}")
    return named, unread


def _read_change_order(where: str) -> str | None:
    """A change order's text, or None when it is over model.MAX_DOCUMENT_BYTES. It never follows a symlink or blocks on
    a special file that took the file's place after the folder was listed: either is an OSError."""
    fd = os.open(where, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise OSError(0, "it is not a regular file")
        blob = fh.read(documents.MAX_DOCUMENT_BYTES + 1)
    return None if len(blob) > documents.MAX_DOCUMENT_BYTES else blob.decode("utf-8", errors="replace")
