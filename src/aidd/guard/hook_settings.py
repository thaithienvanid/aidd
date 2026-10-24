"""What the session hooks read from the repository: its config as the hooks load it (offline, skipping a parent they
cannot fetch), how much they say (`hooks.level`, and each hook's own switch), and where `aidd test` wrote evidence."""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config
from aidd.kernel import documents

EVIDENCE_FILE = "evidence.json"


def load_config(root: str) -> config.Config | None:
    """The config as the hooks load it, or None when it does not load."""
    from aidd.guard.repo_config import offline_fetch

    try:
        return config.load_file(config.CONFIG_PATH, root, fetch=offline_fetch, skip_unread=True)
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError):
        return None


def level(cfg: config.Config) -> str:
    """off, minimal, balanced, or strict: `hooks.level`, or the profile's default (config.HOOK_LEVEL_DEFAULTS)."""
    return config.hook_level(cfg.raw)


def hook_level_at_least(cfg: config.Config, wanted: str) -> bool:
    return config.HOOK_LEVELS.index(level(cfg)) >= config.HOOK_LEVELS.index(wanted)


def enabled(cfg: config.Config, switch: str | None = None) -> bool:
    """Whether the session hooks speak: every one speaks for the loop, so each is silent at `hooks.level: off` or when
    `components.spec_steps` is off. With a `switch`, `hooks.<switch>` (`orca_status`) can also turn that one off."""
    if level(cfg) == "off" or not config.component_on(cfg.raw, "spec_steps"):
        return False
    return switch is None or cfg.get("hooks", switch, default=True) is not False


def evidence_paths(cfg: config.Config) -> list[str]:
    """Where `aidd test` writes evidence: .aidd/evidence/, and the folder `evidence.artifact` names when it is set."""
    dirs = [config.EVIDENCE_DIR, *([str(cfg.get("evidence", "artifact"))] if cfg.get("evidence", "artifact") else [])]
    return [f"{d.rstrip('/')}/{EVIDENCE_FILE}" for d in dict.fromkeys(dirs)]


def evidence_files(root: Path, rels: list[str]) -> list[tuple[str, float, object]]:
    """(path, modification time, parsed JSON) of each evidence file that reads."""
    found = []
    for rel in rels:
        try:
            found.append((rel, (root / rel).stat().st_mtime, json.loads((root / rel).read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return found
