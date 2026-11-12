"""The profiles (schemas/profiles.json): `solo` and `team`, each a set of risk rules over the built-in ones and the
routes that ask for Spec approval."""

from __future__ import annotations

from aidd.kernel import resources


def profiles() -> dict:
    """schemas/profiles.json, as data."""
    return resources.load_json("profiles.json")
