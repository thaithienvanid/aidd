"""Repository-relative paths: inside a root or not, shown for a person, and the image file types a page embeds."""

from __future__ import annotations

import os
import posixpath
import stat
from pathlib import Path, PurePath, PurePosixPath


def inside(root: Path, rel: str) -> Path | None:
    """The file `rel` names, when it is a regular file inside the repository once every link is resolved; else None."""
    if not rel or Path(rel).is_absolute() or Path(rel).drive:
        return None
    top = root.resolve()
    try:
        target = (top / rel).resolve()
    except (OSError, RuntimeError):
        return None
    if not target.is_relative_to(top):
        return None
    try:
        return target if stat.S_ISREG(os.stat(target).st_mode) else None
    except OSError:
        return None


def repo_path(path: str) -> str:
    """Normalize a user-supplied repo path: forward slashes, no leading ./, and a folder's trailing slash kept."""
    s = path.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    folder = s.endswith("/") and s.strip("/") != ""
    return PurePosixPath(s).as_posix() + ("/" if folder else "")


def readings(text: str, *, top: str, here: str) -> list[str]:
    """The repository paths `text` can mean, typed in the folder `here` (repository-relative, "" at the top), as text: the
    folder's reading first, as a shell reads it, then the top's, as `git diff --name-only` prints it. One when they match.
    It never follows a link, as git never does; a folder keeps its trailing slash, the top itself reads `./`, and a
    path that names a folder in the repository gets the slash when it was typed without one. A reading that climbs out
    is left out, and when every reading does, ValueError names the next step. An absolute path through a linked parent
    folder, such as macOS `/tmp` for `/private/tmp`, is inside when its longest prefix is the repository's top."""
    s = text.replace("\\", "/")
    folder = s.endswith(("/", "/.", "/..")) or s in ("", ".", "..")
    if os.path.isabs(s):
        norm = os.path.normpath(s)
        candidates = [rel for base in dict.fromkeys((top, os.path.realpath(top))) if (rel := os.path.relpath(norm, base).replace(os.sep, "/"))]
        if all(_climbs(c) for c in candidates):
            candidates = _through_link(norm, top)
    else:
        candidates = [posixpath.join(here, s), *([s] if here else [])]
    out = []
    for c in candidates:
        n = posixpath.normpath(c)
        if _climbs(n) or posixpath.isabs(n):
            continue
        is_folder = folder or (os.path.isdir(p := os.path.join(top, n)) and not os.path.islink(p))
        out.append("./" if n == "." else n + ("/" if is_folder else ""))
    if not out:
        raise ValueError(
            f"{text} is outside this repository: name a path inside it, from this folder or from the repository's top, "
            "or run aidd in the repository that holds it"
        )
    return list(dict.fromkeys(out))


def bare_readings(text: str, found: list[str]) -> list[str]:
    """The readings of `found` without their trailing slash, for a folder that `text` named with no slash. A pattern for the
    folder itself, such as `**/secrets.*` for `conf/secrets.d`, matches that text and not the one with a slash, so both
    route and the stricter wins. A folder typed with a slash or with dots (`..`) is one reading."""
    s = text.replace("\\", "/")
    if s.endswith(("/", "/.", "/..")) or s in ("", ".", ".."):
        return []
    return [r.rstrip("/") for r in found if r.endswith("/") and r != "./"]


def _climbs(n: str) -> bool:
    n = posixpath.normpath(n)
    return n == ".." or n.startswith("../")


def _through_link(norm: str, top: str) -> list[str]:
    """The text after the longest prefix of the absolute path `norm` that is the repository's top (the same folder, by
    `os.path.samefile`, whatever links lead to it); empty when no prefix is."""
    parts = norm.split("/")
    for i in range(len(parts) - 1, 0, -1):
        try:
            if os.path.samefile("/".join(parts[:i]) or "/", top):
                return ["/".join(parts[i:]) or "."]
        except OSError:
            continue
    return []


def link_readings(found: list[str], *, top: str) -> list[str]:
    """Where a link inside the repository leads: for each of `found`, the reading of its real location when that is
    another path inside the repository, so an edit through a link such as `web/billlink` is routed as the folder it
    points to. A link that leads out, or a loop, adds none; the text readings stay."""
    real_top = os.path.realpath(top)
    out = []
    for r in found:
        if r == "./":
            continue
        try:
            real = os.path.realpath(os.path.join(top, r))
        except (OSError, RuntimeError):  # a link loop, on a Python that raises for one
            continue
        rel = os.path.relpath(real, real_top).replace(os.sep, "/")
        if rel == "." or _climbs(rel) or posixpath.isabs(rel):
            continue
        reading = rel + ("/" if r.endswith("/") else "")
        if reading != r:
            out.append(reading)
        if not r.endswith("/") and os.path.isdir(real):  # a link to a folder typed with no slash: the folder's files too
            out.append(rel + "/")
    return list(dict.fromkeys(out))


def real_readings(text: str, *, top: str, here: str) -> list[str]:
    """Where the operating system takes `text`, typed in the folder `here`, once every link is followed in the order the path
    is written: `src/web/cilink/../workflows/ci.yml` goes up from where `cilink` leads, which `readings` folds as text
    before it follows any link. Each reading of `top`, `here`, and the text that stays inside the repository counts, so the
    stricter wins; a folder keeps its slash."""
    s = text.replace("\\", "/")
    if not s or os.path.isabs(s):
        return []
    real_top, out = os.path.realpath(top), []
    for c in dict.fromkeys((posixpath.join(here, s), s)):
        try:
            real = os.path.realpath(os.path.join(top, c))
        except (OSError, RuntimeError):
            continue
        rel = os.path.relpath(real, real_top).replace(os.sep, "/")
        if rel == "." or _climbs(rel) or posixpath.isabs(rel):
            continue
        out += [rel + "/"] if s.endswith("/") else [rel, rel + "/"] if os.path.isdir(real) else [rel]
    return out


def shown(path: object) -> str:
    """A path as aidd prints it: forward slashes on every OS, like the docs and the config, and from the working folder
    when it lies in it, so a command run on an absolute root prints the paths a person typed."""
    if isinstance(path, PurePath) and path.is_absolute() and path.is_relative_to(os.getcwd()):
        return path.relative_to(os.getcwd()).as_posix()
    return path.as_posix() if isinstance(path, PurePath) else str(path)


# The image files a page embeds and a round's screenshots may be, by suffix, with their media types.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
