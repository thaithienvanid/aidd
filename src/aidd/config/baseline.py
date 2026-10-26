"""The data every config builds on: the profiles (schemas/profiles.json), and the baseline (schemas/baseline.json) with
the paths each coding agent reads as instructions or runs as a hook."""

from __future__ import annotations

import functools
import json

from aidd.kernel import resources


def profiles() -> dict:
    return resources.load_json("profiles.json")


def profile_mode(profile: str | None) -> str:
    """The mode a profile starts in when the config names none: advisory (the guard and the gate report, never block)
    or enforce. An unknown profile enforces."""
    mode = (profiles()["profiles"].get(str(profile)) or {}).get("mode")
    return mode if mode in ("advisory", "enforce") else "enforce"


def harness_paths(protected: list[str]) -> list[str]:
    """Every path a supported agent harness reads as instructions or runs as a hook (`harnesses.harness_protected_paths()`) that
    `protected` does not already cover (`.opencode/agents/**` under `.opencode/**`, `CLAUDE.md` under `**/CLAUDE.md`)."""
    from aidd.config import harnesses
    from aidd.kernel import globs

    return [p for p in harnesses.harness_protected_paths() if p not in protected and not globs.match_any(protected, globs.literal_form(p))]


def merge_harness_paths(protected: list[str]) -> list[str]:
    """`protected`, then every harness path it does not already cover."""
    return list(protected) + harness_paths(protected)


def baseline_json_text(text: str) -> str:
    """baseline.json as `aidd gen-docs` writes it: the hand-written `protected_paths` as they are, and `harness_paths`
    generated from src/aidd/config/harnesses.py right after them, so what an outside implementer reads is the whole set the gate
    enforces (the two lists together) and `gen-docs --check` fails on drift. Nothing is ever appended to the
    hand-written list, so removing a harness removes its paths."""
    data = json.loads(text)
    out: dict = {}
    for k, v in data.items():
        if k == "harness_paths":
            continue
        out[k] = v
        if k == "protected_paths":
            out["harness_paths"] = harness_paths(v)
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


@functools.cache
def baseline_data() -> dict:
    """baseline.json with `protected_paths` as the whole set the gate enforces: the hand-written list, then its generated
    `harness_paths`, then any harness path neither covers yet. Deriving them here too protects a new harness the day it
    is added, even before `aidd gen-docs` runs."""
    data = resources.load_json("baseline.json")
    listed = list(data["protected_paths"]) + [p for p in data.get("harness_paths", []) if p not in data["protected_paths"]]
    return data | {"protected_paths": merge_harness_paths(listed)}
