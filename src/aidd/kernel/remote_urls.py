"""What a git remote's URL names."""

from __future__ import annotations

import re

_GITHUB_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_-]{1,39}/[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)


def github_slug(url: str) -> str | None:
    """`owner/name` of a GitHub remote's URL (https with or without a user, `git@github.com:`, or `ssh://`), or None for any
    other host. A name of `.` or `..` is no repository, and it would climb out of a `repos/<slug>` path."""
    found = _GITHUB_REMOTE.match(url.strip())
    return found.group(1) if found and found.group(1).split("/")[1] not in (".", "..") else None
