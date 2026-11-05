"""The repository's config, read offline, for the checks that need it and must never fetch."""

from __future__ import annotations

from pathlib import Path

from aidd import config


def config_at(root: Path | None) -> config.Config | None:
    """The repository's config, read offline; None when it is missing or unreadable."""
    if root is None or not (root / config.CONFIG_PATH).is_file():
        return None

    def offline(url: str) -> bytes:
        raise config.ConfigError(f"not fetched: {url}")

    try:
        return config.load_file(config.CONFIG_PATH, str(root), fetch=offline, skip_unread=True)
    except Exception:  # noqa: BLE001  # an unreadable config is `aidd validate`'s own finding; agent: ids still count
        return None
