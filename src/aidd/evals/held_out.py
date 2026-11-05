"""The held-out cases as data: a case's `tier` says it is held out, and `evals/held-out.lock.json` locks what each one says.

A held-out case is read once, at a release, and never tuned against. The lock holds, for each, a hash of its content and the
date its score was first read. A case whose content differs from its hash after that date fails a test, so an edit cannot hide
behind a rename or a re-run. The lock's shape is schemas/eval-held-out.schema.json. Nothing here runs an agent.

The text of a held-out case must not appear in the skill, the roles, the docs, the code, or another case, because an agent
that reads the text there has seen the answer. `leaks` finds a run of words shared with those files.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from aidd.evals import claim_registry, claims, trigger_cases
from aidd.kernel import regular_files

LOCK_FILE = "evals/held-out.lock.json"
# The fields of a routing or roles case that an agent reads, and of a folder case: its prompt.
TEXT_FIELDS = ("situation", "prompt", "fixture")
# A run of this many words in a held-out case and in another file is a quote of it. A development case that repeats this share
# of a held-out case's runs quotes it; a smaller share is the sentences two cases of one role share.
SHINGLE = 10
SHARED_SHARE = 0.25
# Where the text of a held-out case must not appear: what an agent reads, and what teaches it.
GUARDED = (".agents", "plugins", "templates", "schemas", "src", "docs", "standards", "stacks", "tests", "README.md", "AGENTS.md", "llms.txt", "CONTRIBUTING.md")
# Held-out data itself: the lock, the samples that score the cases, and the trigger cases' source. Only the cases are searched in them.
HELD_OUT_DATA = ("evals/held-out.lock.json", "evals/claims.json")
SCAN_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".sh", ".toml", ".html", ".css", ".js"}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scenario_text(sc: dict) -> tuple[str, str]:
    """(the hash input, the words an agent reads) of a routing or roles case: the whole case as sorted JSON, and its situation, prompt, and fixture."""
    whole = json.dumps({k: v for k, v in sc.items() if k != "_file"}, sort_keys=True, ensure_ascii=False)
    return whole, "\n".join(str(sc[f]) for f in TEXT_FIELDS if f in sc)


def _folder_text(root: Path, suite: str, name: str) -> tuple[str, str]:
    """(the hash input, the prompt) of a plugin or team case: every file of its folder, or the files a trigger case is built from."""
    if suite == "team" and name.startswith(trigger_cases.PREFIXES):
        files = {rel: text for rel, text in trigger_cases.case_files(trigger_cases.load_triggers(root)).items() if rel.startswith(f"{name}/")}
    else:
        folder = root / claims.SUITES[suite] / name
        files = {p.relative_to(folder.parent).as_posix(): p.read_text(encoding="utf-8") for p in sorted(folder.rglob("*")) if p.is_file()}
    return json.dumps(files, sort_keys=True, ensure_ascii=False), files.get(f"{name}/prompt.md", "").split("\n---\n", 1)[-1]


def held_out_cases(root: Path) -> dict[tuple[str, str], dict]:
    """Every case whose tier is `held-out`, by (suite, id), with its `sha256` and the `text` an agent reads. Sorted by suite, then id."""
    from aidd.evals import suites

    scenarios = {s: {str(sc["id"]): sc for sc in suites.load_scenarios(root / claims.SUITES[s])} for s in ("routing", "roles")}
    out: dict[tuple[str, str], dict] = {}
    for row in sorted(claims.suite_cases(root), key=lambda r: (r["suite"], r["id"])):
        if row["tier"] != "held-out":
            continue
        whole, text = _scenario_text(scenarios[row["suite"]][row["id"]]) if row["suite"] in scenarios else _folder_text(root, row["suite"], row["id"])
        out[(row["suite"], row["id"])] = {"sha256": _digest(whole), "text": text}
    return out


def read_lock(root: Path) -> dict:
    return json.loads((root / LOCK_FILE).read_text(encoding="utf-8"))


def lock_problems(root: Path, lock: dict | None = None) -> list[str]:
    """Each way the lock and the held-out cases disagree: a case with no entry, an entry with no case, and a case edited after
    its score was first read. An edit before the first read only needs the lock's hash refreshed, and the message gives it."""
    lock = read_lock(root) if lock is None else lock
    cases, entries = held_out_cases(root), {(e["suite"], e["case"]): e for e in lock["cases"]}
    problems = [
        f"{s}/{c}: held out, but the lock has no entry: add it with first_read_on null and content_sha256 {cases[(s, c)]['sha256']}"
        for s, c in cases
        if (s, c) not in entries
    ]
    problems += [f"{s}/{c}: in the lock, but no case with that id has the tier held-out" for s, c in entries if (s, c) not in cases]
    for key, entry in entries.items():
        if key in cases and entry["content_sha256"] != cases[key]["sha256"]:
            read = entry["first_read_on"]
            if read:
                problems.append(
                    f"{key[0]}/{key[1]}: edited after its score was read on {read}. It is no longer unseen: make its tier `full` and write a new blind case"
                )
            else:
                problems.append(f"{key[0]}/{key[1]}: edited before its first read; set its content_sha256 to {cases[key]['sha256']}")
    keys = [(e["suite"], e["case"]) for e in lock["cases"]]
    if keys != sorted(keys):
        problems.append("the lock's cases are out of order: sort them by suite, then case")
    return problems


def record_blockers(root: Path) -> list[str]:
    """Why a score recorded now could not be trusted, from the eval data itself: a held-out case that disagrees with its lock,
    or a claim registry that disagrees with the files that own its facts. Empty where the repository holds no eval data."""
    if not (root / LOCK_FILE).is_file() or not (root / claims.CLAIMS_FILE).is_file():
        return []
    return [*lock_problems(root), *claim_registry.registry_problems(claims.claims_file(root), root)]


def mark_held_out_read(root: Path, suite: str, ids: list[str], date: str) -> list[str]:
    """Set `first_read_on` to `date` for each of these held-out cases of `suite` that the lock holds unread, and write the lock. Returns the ids it set."""
    lock = read_lock(root)
    set_now = [e["case"] for e in lock["cases"] if e["suite"] == suite and e["case"] in ids and not e["first_read_on"]]
    for entry in lock["cases"]:
        if entry["suite"] == suite and entry["case"] in set_now:
            entry["first_read_on"] = date
    if set_now:
        regular_files.write_text_safely(root, LOCK_FILE, json.dumps(lock, indent=2, ensure_ascii=False) + "\n")
    return set_now


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_.']+", text.lower())


def _shingles(text: str) -> set[str]:
    words = _words(text)
    return {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def _searched(root: Path) -> list[Path]:
    """The files that may not quote a held-out case: the guarded folders and files, without held-out data."""
    skip = {root / rel for rel in HELD_OUT_DATA}
    found = []
    for name in GUARDED:
        top = root / name
        paths = [top] if top.is_file() else sorted(top.rglob("*")) if top.is_dir() else []
        found += [
            p for p in paths if p.is_file() and p.suffix in SCAN_SUFFIXES and p not in skip and "__pycache__" not in p.parts and p.stat().st_size < 2_000_000
        ]
    return found


def leaks(root: Path) -> list[str]:
    """Where a held-out case's text appears outside the held-out data: the file it is in, or the other case that repeats it. A run of
    SHINGLE words counts, so a shared phrase is no leak but a copied sentence is."""
    from aidd.evals import suites

    held = {key: _shingles(case["text"]) for key, case in held_out_cases(root).items()}
    found: list[str] = []
    for path in _searched(root):
        words = " ".join(_words(path.read_text(encoding="utf-8", errors="replace")))
        found += [f"{path.relative_to(root).as_posix()} quotes {s}/{c}" for (s, c), shingles in held.items() if any(sh in words for sh in shingles)]
    for suite in ("routing", "roles"):  # a development case that repeats a held-out one
        for sc in suites.load_scenarios(root / claims.SUITES[suite]):
            key = (suite, str(sc["id"]))
            if key in held:
                continue
            own = _shingles(_scenario_text(sc)[1])
            found += [
                f"{suite}/{sc['id']} quotes {s}/{c}" for (s, c), shingles in held.items() if shingles and len(shingles & own) / len(shingles) >= SHARED_SHARE
            ]
    return sorted(set(found))
