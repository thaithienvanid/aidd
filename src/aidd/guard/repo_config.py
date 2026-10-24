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
# The profile line of config.FAIL_CLOSED_PROFILES, or the mode line of config.FAIL_CLOSED_MODES, read from the config's
# text: the guard that asks has failed, so it cannot count on loading the config. The shell fallbacks match the same
# lines (setup/hook_wiring.fail_closed_test), and so does the OpenCode plugin (templates/opencode/aidd.js).
_FAIL_CLOSED_PATTERN = (
    rf"^(?:profile:[ \t]*[\"']?(?:{'|'.join(config.FAIL_CLOSED_PROFILES)})"
    rf"|mode:[ \t]*[\"']?(?:{'|'.join(config.FAIL_CLOSED_MODES)}))[\"']?[ \t]*(?:#[^\n]*)?\r?$"
)
_FAIL_CLOSED_LINE = re.compile(_FAIL_CLOSED_PATTERN, re.M)


def fails_closed(root: str | None) -> bool:
    """Whether the guard blocks, rather than allows, when it cannot decide in the repository at `root`. Only in one that
    adopted aidd: when its own config picks a profile in config.FAIL_CLOSED_PROFILES or a mode in config.FAIL_CLOSED_MODES
    (`mode: enforce`), or an organization's managed settings set AIDD_HOOK_FAIL_CLOSED=1. With no `root` (where the guard
    cannot tell), the organization's setting alone."""
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


class KeptConfigUnreadable(ValueError):
    """The config a person's last decision kept is stricter than the one on disk, and it no longer loads."""


# Said where the config is invalid (path_location.config_problem), so every caller holds as it holds an invalid config.
KEPT_UNREADABLE = (
    "the aidd config is invalid here: the stricter config a person's last decision kept no longer loads ({why}), and "
    "the one on disk is looser. A person runs `aidd upgrade --yes` at their own terminal, or makes their next decision, "
    "which shows the change"
)


def load_config(root: str) -> config.Config | None:
    """The repository's aidd config, or None when it has none the guard can read: none at all, one that does not load,
    or a looser one on disk whose stricter kept config no longer loads (`held_config`). A caller holds on None as it
    holds on an invalid config (path_location.config_problem says which)."""
    try:
        return held_config(root, config.load_file(config.CONFIG_PATH, root, fetch=offline_fetch, skip_unread=True))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        return None


def kept_unreadable(root: str) -> str | None:
    """Why the stricter config a person's last decision kept holds here yet no longer loads (KEPT_UNREADABLE), or
    None: no decision kept one, it loads, or the config on disk does not load at all (path_location.config_problem)."""
    try:
        held_config(root, config.load_file(config.CONFIG_PATH, root, fetch=offline_fetch, skip_unread=True))
    except KeptConfigUnreadable as exc:
        return str(exc)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        return None
    return None


def held_config(root: str, cfg: config.Config) -> config.Config:
    """The config at the person's last decision, with its local parents as they read then, when the config on disk or
    a parent loosens it (`_looser`), else the one on disk: a program the agent runs never loosens the guard, while a
    person's tightening holds at once and their loosening after their next decision, which lists it. KeptConfigUnreadable
    when the kept config holds but no longer loads: it never yields to the looser one on disk."""
    from aidd.guard import decision_snapshot

    try:
        recorded = decision_snapshot.recorded_config_text(root)
        disk = (Path(root) / config.CONFIG_PATH).read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return cfg
    if recorded is None:
        return cfg
    parents = decision_snapshot.recorded_parent_texts(root)
    now = {rel: decision_snapshot.read_text(root, rel) for rel in sorted(set(parents) | set(cfg.parent_paths))}
    if recorded == disk and all(parents.get(rel) == text for rel, text in now.items()):
        return cfg
    key = (os.path.realpath(root), recorded, disk, repr(sorted(parents.items())), repr(sorted(now.items())))
    if key not in _HELD:
        _HELD[key] = any(looser_text(before, after) for before, after in [(recorded, disk), *((parents.get(rel), text) for rel, text in now.items())])
    if not _HELD[key]:
        return cfg
    try:
        return config.load_text(recorded, read=lambda rel: parents[rel] if rel in parents else _read(root, rel), fetch=offline_fetch, skip_unread=True)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError) as exc:
        why = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        raise KeptConfigUnreadable(KEPT_UNREADABLE.format(why=why)) from None


def looser_text(before: str | None, after: str | None) -> bool:
    """Whether one file's text loosens a control the other set, as each text sets it, as decision_files reads an edit: a
    profile's defaults are the profile's, not a change. A file added, removed, or that does not parse counts as looser."""
    if before == after:
        return False
    if before is None or after is None:
        return True
    try:
        old, new = documents.parse_yaml(before, config.CONFIG_PATH), documents.parse_yaml(after, config.CONFIG_PATH)
    except documents.DocumentError:
        return True
    return not (isinstance(old, dict) and isinstance(new, dict)) or _looser(old, new)


_HELD: dict[tuple[str, ...], bool] = {}  # the texts compared: whether the recorded ones hold


def _read(root: str, rel: str) -> str | None:
    path = Path(root) / rel
    return path.read_text(encoding="utf-8") if path.is_file() else None


_LOCKED = ("gates", "limits", "extends", "guard", "publish")


def _looser(before: dict, after: dict) -> bool:
    """Whether `after` loosens a control `before` sets: a weaker profile, `mode` off enforce, a lower `hooks.level` or
    `agents.delegate`, a component switched off, or any change to the gates, the limits, the parents, the held
    commands, or publishing, which cannot be told tighter or looser here (decision_files.config_loosening's rule)."""
    import json

    order = config.profiles()["order"]
    if before.get("profile") in order and (after.get("profile") not in order or order.index(after["profile"]) < order.index(before["profile"])):
        return True
    if effective_mode(before) == "enforce" and effective_mode(after) != "enforce":
        return True
    if config.HOOK_LEVELS.index(config.hook_level(after)) < config.HOOK_LEVELS.index(config.hook_level(before)):
        return True
    if config.DELEGATE_MODES.index(config.delegate_mode(after)) < config.DELEGATE_MODES.index(config.delegate_mode(before)):
        return True
    names = {*(before.get("components") or {}), *(after.get("components") or {})}
    if any(config.component_on(before, n) and not config.component_on(after, n) for n in names):
        return True
    return any(json.dumps(before.get(k), sort_keys=True, default=str) != json.dumps(after.get(k), sort_keys=True, default=str) for k in _LOCKED)


def effective_mode(data: dict) -> str | None:
    """The mode a config's data sets: its own `mode`, else its profile's; None for a broken profile, which an agent may fix."""
    mode = data.get("mode")
    if isinstance(mode, str):
        return mode
    return config.profile_mode(data["profile"]) if data.get("profile") in config.profiles()["order"] else None
