"""What the target branch changed, since a branch forked from it, in what decides an `aidd test` run.

The base is the commit the branch forked from, and the author chooses the fork point. So a run decides by the fork point's values
(`base_view`), never by the target's newest. It does not fail a branch because the target added a test since: that test may need code
the branch does not have yet, and keeping a branch up to date is the platform's job. It says so instead. When the target's tip is
ahead of the fork point and what decides differs between the two, the evidence holds `target_moved` and the run prints one note.
The tip is the local ref the run already resolved for `--base`, so reading it needs no network call. What holds a branch to the
target's newest commit is the platform's "require branches to be up to date before merging", or a merge queue.
"""

from __future__ import annotations

from aidd import config, workitems
from aidd.kernel import documents, json_schema
from aidd.testing import base_view, governing

CHANGES = "evidence.schema.json#/properties/target_moved/properties/changes"  # the evidence's own bound on the entries it holds
MAX_SHOWN = 5  # the names an entry lists, and the entries a note names
MAX_NAME = 40  # the characters of one name or value in an entry, so an entry stays within the schema's 300


def _names(names: list[str]) -> str:
    """The first `MAX_SHOWN` names, each shortened, and the count of the rest."""
    shown = ", ".join(documents.one_line(n, MAX_NAME) for n in names[:MAX_SHOWN])
    return shown + (f", and {len(names) - MAX_SHOWN} more" if len(names) > MAX_SHOWN else "")


def _test_changes(then: list[dict], now: list[dict]) -> list[str]:
    old, new = {c["name"]: c for c in then}, {c["name"]: c for c in now}
    parts = {
        "added": [n for n in new if n not in old],
        "changed": [n for n in new if n in old and new[n] != old[n]],
        "removed": [n for n in old if n not in new],
    }
    return [f"`tests` {verb}: {_names(names)}" for verb, names in parts.items() if names]


def _config_changes(then: config.Config, now: config.Config | None) -> list[str]:
    """What the target's config changed that decides a run: its `tests` (with their `smoke` markers) and the two folders."""
    if now is None:
        return [f"{config.CONFIG_PATH} is gone or does not load"]
    out = _test_changes(then.tests, now.tests)
    out += [
        f"`{key}` is {documents.one_line(getattr(now, key), MAX_NAME)}, not {documents.one_line(getattr(then, key), MAX_NAME)}"
        for key in ("specs_dir", "docs_dir")
        if getattr(now, key) != getattr(then, key)
    ]
    return out


def _spec_state(data: dict) -> dict:
    """The values of a Spec that a run decides by (`base_view.spec_view`)."""
    tests, tasks = data.get("tests") or {}, [t for t in data.get("tasks") or [] if isinstance(t, dict)]
    return {
        "status": workitems.spec_status(data),
        "route": data.get("route"),
        "test commands": tests.get("commands") or [],
        "frozen files": sorted(workitems.frozen_files(data)),
        "Task scope": [t.get("scope") for t in tasks],
    }


def _spec_changes(repo: str, fork: str, tip: str, dirs: tuple[str, str], ids: set[str]) -> list[str]:
    """The Specs this run answers to whose deciding values differ at the target's tip from the fork point's."""
    then, now = ({str(d.get("id")): d for d in governing.specs_at(repo, ref, [folder]).values()} for ref, folder in ((fork, dirs[0]), (tip, dirs[1])))
    out = []
    for sid in sorted(ids & then.keys()):
        if sid not in now:
            out.append(f"{documents.one_line(sid, MAX_NAME)} is gone")
            continue
        old, new = _spec_state(then[sid]), _spec_state(now[sid])
        if fields := [key for key in old if old[key] != new[key]]:
            out.append(f"{documents.one_line(sid, MAX_NAME)}: {', '.join(fields)}")
    return out


def moved(repo: str, tip: str, fork: str, fork_cfg: config.Config | None, specs: list[governing.Governing]) -> dict:
    """`{"tip", "changes"}` when the target's `tip` is ahead of the `fork` commit and what decides differs between them, else {}.
    With no config at the fork point (a first adoption) there is nothing the target decided, so {}."""
    if fork_cfg is None or not tip or tip == fork:
        return {}
    tip_cfg, _ = base_view.load_config(repo, tip)
    dirs = (fork_cfg.specs_dir, (tip_cfg or fork_cfg).specs_dir)
    changes = _config_changes(fork_cfg, tip_cfg) + _spec_changes(repo, fork, tip, dirs, {str(g.data.get("id")) for g in specs})
    most = json_schema.keyword_at(CHANGES, "maxItems")  # the last entry says how many more there were
    if len(changes) > most:
        changes = [*changes[: most - 1], f"and {len(changes) - most + 1} more changes"]
    return {"tip": tip, "changes": changes} if changes else {}


def note(target: str, fork: str, found: dict) -> str:
    """The note for a branch whose target moved: the first of the evidence's entries, that the run used the fork point's values,
    and the next step."""
    changes = found["changes"]
    more = f", and {len(changes) - MAX_SHOWN} more" if len(changes) > MAX_SHOWN else ""
    return (
        f"{target} has moved since this branch forked from it ({fork[:12]}, now {found['tip'][:12]}), and it changed what decides this run: "
        f"{'; '.join(changes[:MAX_SHOWN])}{more}. This run used the fork point's values, so it does not hold the branch to them. "
        f"Update the branch from {target}, then run `aidd test` again"
    )
