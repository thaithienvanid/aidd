"""How the guard reads an adopted repository: its config (never a URL parent), and a path as it compares one."""

from __future__ import annotations

import os
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, repo_paths


def offline_fetch(url: str) -> bytes:
    """Refuse an `extends` URL parent. The guard runs inside a 20-second edit hook, so a
    repo-controlled URL must never block the edit or beacon from a developer's machine."""
    raise RuntimeError(f"not fetched: the guard does not use the network ({url})")


def repo_relative(root: str, path: str) -> str:
    """A path as the guard compares it: relative to the repository, whether given absolute or `./`-prefixed."""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return path
    return repo_paths.repo_path(path)


def edit_path(event: dict) -> str | None:
    tool_input = event.get("tool_input") or {}
    return tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")


def is_adopted(root: str) -> bool:
    """The repository has an aidd config: the team's rules apply here, and nowhere else."""
    return (Path(root) / config.CONFIG_PATH).is_file()


FAIL_CLOSED_ENV = "AIDD_HOOK_FAIL_CLOSED"
# The profile line of config.FAIL_CLOSED_PROFILES, read from the config's text: the guard that asks has failed, so it
# cannot count on loading the config. The shell fallbacks match the same line (setup/hook_wiring.fail_closed_test).
_FAIL_CLOSED_LINE = re.compile(rf"^profile:[ \t]*[\"']?(?:{'|'.join(config.FAIL_CLOSED_PROFILES)})[\"']?[ \t]*(?:#[^\n]*)?\r?$", re.M)


def fails_closed(root: str | None) -> bool:
    """Whether the guard blocks, rather than allows, when it cannot decide in the repository at `root`. Only in one that
    adopted aidd: when its own config picks a profile in config.FAIL_CLOSED_PROFILES, or an organization's managed settings
    set AIDD_HOOK_FAIL_CLOSED=1. With no `root` (where the guard cannot tell), the organization's setting alone."""
    if root is None:
        return os.environ.get(FAIL_CLOSED_ENV) == "1"
    if not is_adopted(root):
        return False
    if os.environ.get(FAIL_CLOSED_ENV) == "1":
        return True
    try:
        text = (Path(root) / config.CONFIG_PATH).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_FAIL_CLOSED_LINE.search(text))


def load_config(root: str) -> config.Config | None:
    """The repository's aidd config, or None when it has none the guard can read."""
    try:
        return config.load_file(config.CONFIG_PATH, root, fetch=offline_fetch, skip_unread=True)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        return None
