"""Where aidd keeps the watched state at a person's last decision, with the config and its local parents as they read then:
outside_changes.py writes it, and repo_config.py reads those texts, so a program the agent runs between two decisions never
loosens the guard, in the config or in a parent it extends."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from aidd import config


def record_path(top: str) -> Path:
    """The record of the worktree at `top`, which every session in it shares. ValueError outside git."""
    key = hashlib.sha256(os.path.realpath(top).encode()).hexdigest()[:24]
    return config.state_dir(top) / config.WATCHED_STATE_DIR / f"{key}.json"


def read_record(top: str) -> dict | None:
    """The record of the worktree at `top`, or None when there is none. ValueError when it is not a JSON object, OSError
    when unreadable."""
    try:
        text = record_path(top).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("the watched state of the last decision is not one aidd wrote")
    return data


def _recorded(top: str) -> dict:
    try:
        return read_record(top) or {}
    except (OSError, ValueError):
        return {}


def recorded_config_text(top: str) -> str | None:
    """The config's text at the person's last decision, or None when there is no decision this worktree recorded."""
    text = _recorded(top).get("config_text")
    return text if isinstance(text, str) else None


def recorded_said(top: str) -> str:
    """The words of the person's last decision (`land it`, `approve SPEC-1`), or "" when the record names none."""
    said = _recorded(top).get("said")
    return said if isinstance(said, str) else ""


def recorded_parent_texts(top: str) -> dict[str, str | None]:
    """Each local parent of the config (`extends: [{path: ...}]`, the whole chain) as it read at the last decision."""
    texts = _recorded(top).get("parent_texts")
    return {str(k): (v if isinstance(v, str) else None) for k, v in texts.items()} if isinstance(texts, dict) else {}


def _offline(url: str) -> bytes:
    raise RuntimeError(f"not fetched: aidd reads only the config's local parents here ({url})")


def parent_texts(top: str) -> dict[str, str | None]:
    """Each local parent of the config as it reads now, by repository path (config.Config.parent_paths); {} when the
    config cannot be read."""
    try:
        paths = config.load_file(config.CONFIG_PATH, top, fetch=_offline, skip_unread=True).parent_paths
    except Exception:  # noqa: BLE001  # a config aidd cannot read names no parent here; the check reads the config itself
        return {}
    return {rel: read_text(top, rel) for rel in paths}


def read_text(top: str, rel: str) -> str | None:
    """A repository file's text, or None when it is gone or unreadable."""
    try:
        return (Path(top) / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
