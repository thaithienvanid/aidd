"""Locate bundled data: schemas, the skill, CI templates, the aidd-team plugin, and the standards library and stacks.

An installed wheel carries them under aidd/_data. A source checkout reads them
from the repository root, so the package and the repo never hold two copies.
The zipapp (`aidd.pyz`, built by `aidd.pyz`) carries them under aidd/_data inside
the archive; the first run extracts that folder, once per archive, into the user's
cache, since callers copy and walk the data as real files.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

_PKG = Path(__file__).resolve().parent
_REPO = _PKG.parent.parent

_LAYOUT = {
    "schemas": "schemas",
    "skill": ".agents/skills/aidd",
    "templates": "templates",
    "team": "plugins/aidd-team",
    "standards": "standards",
    "stacks": "stacks",
}
DATA_PREFIX = "aidd/_data/"


def archive() -> Path | None:
    """The zipapp this aidd runs from, or None when it runs from files on disk."""
    parent = _PKG.parent
    return parent if parent.is_file() and zipfile.is_zipfile(parent) else None


def _cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "aidd"


@functools.cache
def _extracted(pyz: Path) -> Path:
    """The archive's aidd/_data, extracted under the user's cache in a folder named by the archive's sha256, so a new
    or changed archive never reads another's data. Written to a temporary folder and renamed into place whole."""
    digest = hashlib.sha256(pyz.read_bytes()).hexdigest()[:24]
    dest = _cache_home() / f"pyz-{digest}"
    if (dest / ".complete").is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".pyz-", dir=dest.parent))
    try:
        with zipfile.ZipFile(pyz) as zf:
            for info in zf.infolist():
                if not info.filename.startswith(DATA_PREFIX) or info.is_dir():
                    continue
                rel = PurePosixPath(info.filename[len(DATA_PREFIX) :])
                if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                    raise ValueError(f"{pyz}: unsafe member {info.filename!r}")
                target = tmp.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        (tmp / ".complete").write_text(digest + "\n", encoding="utf-8")
        try:
            os.replace(tmp, dest)
        except OSError:  # another process finished first, or a stale partial folder is in the way
            if not (dest / ".complete").is_file():
                shutil.rmtree(dest, ignore_errors=True)
                os.replace(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest


def data_dir(name: str) -> Path:
    pyz = archive()
    if pyz is not None:
        extracted = _extracted(pyz) / name
        if extracted.is_dir():
            return extracted
        raise FileNotFoundError(f"aidd data directory not found in {pyz}: {name}")
    bundled = _PKG / "_data" / name
    if bundled.is_dir():
        return bundled
    source = _REPO / _LAYOUT[name]
    if source.is_dir():
        return source
    raise FileNotFoundError(f"aidd data directory not found: {name}")


def repo_root() -> Path | None:
    """The source checkout root, or None when running from an installed wheel or the zipapp."""
    if archive() is not None:
        return None
    return _REPO if (_REPO / "schemas").is_dir() and (_REPO / "src" / "aidd").is_dir() else None


@functools.cache
def load_json(name: str) -> dict:
    return json.loads((data_dir("schemas") / name).read_text(encoding="utf-8"))


SCHEMA_URN = "urn:aidd:1:"


def schema_file(ref_file: str) -> str:
    """The bundled file a $ref's document part names: `urn:aidd:1:<name>` (a schema's `$id`) is `<name>.schema.json`;
    a plain file name is itself."""
    if ref_file.startswith(SCHEMA_URN):
        return ref_file.removeprefix(SCHEMA_URN) + ".schema.json"
    return ref_file


def profiles() -> dict:
    return load_json("profiles.json")


def harness_paths(protected: list[str]) -> list[str]:
    """Every path a supported agent harness reads as instructions or runs as a hook (`harnesses.protected_paths()`) that
    `protected` does not already cover (`.opencode/agents/**` under `.opencode/**`, `CLAUDE.md` under `**/CLAUDE.md`)."""
    from . import globs, harnesses

    return [p for p in harnesses.protected_paths() if p not in protected and not globs.match_any(protected, globs.literal_form(p))]


def merge_harness_paths(protected: list[str]) -> list[str]:
    """`protected`, then every harness path it does not already cover."""
    return list(protected) + harness_paths(protected)


def baseline_json_text(text: str) -> str:
    """baseline.json as `aidd gen-docs` writes it: the hand-written `protected_paths` as they are, and `harness_paths`
    generated from src/aidd/harnesses.py right after them, so what an outside implementer reads is the whole set the gate
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
def baseline() -> dict:
    """baseline.json with `protected_paths` as the whole set the gate enforces: the hand-written list, then its generated
    `harness_paths`, then any harness path neither covers yet. Deriving them here too protects a new harness the day it
    is added, even before `aidd gen-docs` runs."""
    data = load_json("baseline.json")
    listed = list(data["protected_paths"]) + [p for p in data.get("harness_paths", []) if p not in data["protected_paths"]]
    return data | {"protected_paths": merge_harness_paths(listed)}


def standard_edition_text(s: dict) -> str | None:
    """One line for a person: the edition, when it was published, and the notes."""
    head = " ".join(x for x in (s.get("edition"), f"(published {s['published']})" if s.get("published") else None) if x)
    return "; ".join(x for x in (head, s.get("notes")) if x) or None


def resolve_standard(ref, table: dict) -> dict:
    """A role's or pack's standard reference as the full entry: its id, `as` wording in place of the name, and one `edition` line."""
    sid, as_ = (ref, None) if isinstance(ref, str) else (ref["id"], ref.get("as"))
    entry = dict(table[sid], id=sid)
    if as_:
        entry["name"] = as_
    text = standard_edition_text(entry)
    if entry.get("edition"):
        entry["release"] = entry["edition"]  # the bare edition, without the publication date and notes
    entry.pop("edition", None)
    if text:
        entry["edition"] = text
    return entry


@functools.cache
def roles() -> dict:
    """roles.json with every standard reference resolved against the `standards` table, as the docs and the evals read it.

    `load_json("roles.json")` is the file itself, which the schema validates.
    """
    data = json.loads(json.dumps(load_json("roles.json")))
    table = data.get("standards", {})
    for r in data["roles"].values():
        r["standards"] = [resolve_standard(x, table) for x in r["standards"]]
    for d in data["domains"]:
        d["standards"] = [resolve_standard(x, table) for x in d["standards"]]
    for p in data.get("practices", {}).values():
        p["standards"] = [resolve_standard(x, table) for x in p["standards"]]
    # A contract rule is its text; `contract_applies_to` keeps, in the same order, the roles or steps a scoped rule binds.
    # The hard-rules digest has the same shape: `digest_applies_to` keeps each scoped rule's roles or steps.
    for name in ("contract", "digest"):
        items = data["loop"].get(name, [])
        data["loop"][name] = [x if isinstance(x, str) else x["rule"] for x in items]
        data["loop"][f"{name}_applies_to"] = [None if isinstance(x, str) else list(x["applies_to"]) for x in items]
    return data


def _scoped_for(key: str, data: dict, name: str) -> list[str]:
    role = data["roles"][key]
    return [
        rule
        for rule, scope in zip(data["loop"][name], data["loop"][f"{name}_applies_to"], strict=True)
        if scope is None or key in scope or set(role["steps"]) & set(scope)
    ]


def contract_for(key: str, data: dict | None = None) -> list[str]:
    """The loop-contract rules that bind role `key`: every unscoped rule, and each scoped one naming the role or one of its steps."""
    return _scoped_for(key, data or roles(), "contract")


def digest_for(key: str, data: dict | None = None) -> list[str]:
    """The hard rules, in brief, that bind role `key`, scoped as the contract is."""
    return _scoped_for(key, data or roles(), "digest")


# A role's `tier` is harness-neutral: it names what the work needs, not who sells it. The team ships
# to 26 harnesses, so the tier is the registry's field and the model each harness runs for it lives
# here, in one place, and nowhere else. A harness with no entry reads the tier and picks its own.
# Claude Code takes an alias (`opus`, `sonnet`, `haiku`, `fable`), `inherit`, or a full model ID in an
# agent's `model:` frontmatter; any other value is not a model it knows. There are two tiers (owner, 2026-10-02):
# `reasoning` decides on the strongest model, and `execution` builds on a mid-size one rather than the session's,
# which is often the strongest, so the roles meant to be cheap are. Sonnet is the smallest model aidd runs an agent
# on in Claude Code. `[agents.models]` can set `inherit`, or any model by name, per tier or role (agentmodels).
MODELS_BY_HARNESS = {
    "claude-code": {"reasoning": "opus", "execution": "sonnet"},
    "codex": {"reasoning": "gpt-6-astra", "execution": "gpt-6-sol"},
}

# What each tier is for, in the order the docs list them.
TIER_MEANING = {
    "reasoning": "decides, designs, or judges where a mistake, or a missing option, is invisible to every later check; the strongest model",
    "execution": "builds, proposes, or runs checks where the tests, the gate, or a person catch the mistake; a mid-size model",
}

# The aidd-team plugin's agent files are Claude Code artifacts, so their `model:` frontmatter is
# derived from this harness. `aidd init --team` writes the same value into a copied agent file.
PLUGIN_HARNESS = "claude-code"


def tier_model(tier: str, harness: str = PLUGIN_HARNESS) -> str | None:
    """The model `harness` runs for `tier`, or None for a harness with no mapping: it reads the tier and picks its own."""
    mapping = MODELS_BY_HARNESS.get(harness)
    return mapping[tier] if mapping else None
