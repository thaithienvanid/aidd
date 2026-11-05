"""Repository-relative paths: inside a root or not, shown for a person, whether a path is a test file, and the image
file types a page embeds."""

from __future__ import annotations

import os
import re
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
    """Normalize a user-supplied repo path: forward slashes, no leading ./"""
    s = path.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return PurePosixPath(s).as_posix()


def shown(p: object) -> str:
    """A path as aidd prints it: forward slashes on every OS, like the docs and the config."""
    return p.as_posix() if isinstance(p, PurePath) else str(p)


# A file a test runner would pick up: the naming conventions of the common runners, or a file under a tests folder.
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|spec|e2e|testing)/|(?:^|/)test_[^/]*\.py$|_test\.(?:py|go|rb|dart)$|\.(?:test|spec)\.[cm]?[jt]sx?$|Tests?\.(?:java|cs|kt)$|_spec\.rb$"
)


def looks_like_test(rel: str) -> bool:
    return bool(_TEST_PATH.search(rel))


# The image files a page embeds and a round's screenshots may be, by suffix, with their media types.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
