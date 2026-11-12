"""A file a Spec froze stays as the base holds it, unless the change revises that Spec.

The rule: a file that a Spec froze at the base is unchanged at the head, unless the change holds that Spec and records a revision
of it (`spec.revise`: the head's Spec has more `revisions` entries than the base's). The base decides which Specs froze what
(`base_view`): a Spec the base holds as approved, in progress, or in review (`workitems.FROZEN_STATUSES`, the span the harness ask
rules guard too), with the files `workitems.frozen_paths` gives for it: its `tests.files`, design files, and frozen docs, and the
files its test commands name as a path (`python3 tools/check.py`). A finished Spec (done, rolled back, cancelled) freezes nothing,
since its tests are now the suite.

Holding the Spec alone is no revision. A branch named `spec/<ID>`, `--spec`, or a prose edit of the Spec hold it, and none of them
changes what its approval froze. So a held Spec's changed frozen file is said in either case: with a recorded revision it is a note,
as `base_view` says of a revised Spec's own fields, and the person who agreed to it approves the Spec again; with none it is the
same problem as for a Spec the change does not hold, and a run that gates a merge stops on it.

A frozen section of a manifest (`pyproject.toml#tool.pytest`) freezes that section's value, not the file (`workitems.frozen_change`),
so a dependency bump beside it changes nothing frozen. A whole-file entry wins over a section of the same file, and a section that
cannot be read on either side counts as changed.

It does not cover a file a command only reaches: a helper the named script imports, a fixture it reads, or a file the
program loads. Those are not in `frozen_paths`, and this rule does not widen what "frozen" means.

A new file is no change to a frozen one: it adds to what the base holds, as `changed_test_files` has it. A rename, a removal,
and any difference in bytes, even a formatting change, count. The fork point is the base, as in the run. The base's config names the folders its Specs are read from; the head's folder is read
too (`base_view.spec_dirs`), so a head can only add folders to scan, never hide a base Spec. A base config that exists and does
not load stops the check with the next step. With no config at the base (a first adoption), aidd scans the head's folder at the base, so
a Spec file already there still freezes its files.
"""

from __future__ import annotations

from aidd import config, workitems
from aidd.kernel import git
from aidd.testing import base_view, governing

MAX_SHOWN = 5


def _revisions(data: dict | None) -> int:
    found = (data or {}).get("revisions")
    return len(found) if isinstance(found, list) else 0


def _listed(names: list[str]) -> str:
    return ", ".join(names[:MAX_SHOWN]) + (f", and {len(names) - MAX_SHOWN} more" if len(names) > MAX_SHOWN else "")


def _revisions_said(revised: dict[str, list[str]]) -> tuple[list[str], list[dict]]:
    """The note for each Spec the change revises whose frozen files it changes, and the same Specs as the evidence holds them."""
    notes = [
        f"{sid}: the head changes {_listed(names)}, which {sid} froze when approved, and records a revision of {sid}, so the base's frozen "
        "set decided what counts as frozen. A change to an approved Spec is `spec.revise`: the person who agreed to it approves the Spec again"
        for sid, names in sorted(revised.items())
    ]
    return notes, [{"id": sid, "files": names} for sid, names in sorted(revised.items())]


def base_frozen_problem(
    repo: str, specs_dir: str, commits: tuple[str, str], paths: list[str], held: dict[str, dict | None]
) -> tuple[str, list[str], list[dict]]:
    """Why the change from the base to the head (`commits`) rewrites a file a Spec froze at the base without revising that Spec,
    or "", a note for each Spec the change revises whose frozen files it changes, and those Specs as the evidence holds them
    (`revised_frozen`: each `id` with the `files` it changed). `paths` is every path the diff touches, a rename's old path too, and `held` the
    Specs the change holds, by id, each with the head's front matter (None for one the head deleted or moved)."""
    base_sha, head_sha = commits
    if not base_sha:
        return "", [], []
    present = git.ls_tree(base_sha, repo)
    touched = [p for p in paths if p in present]  # a path the base does not hold is new, so it changes nothing frozen
    if not touched:
        return "", [], []
    base_cfg, unread = base_view.load_config(repo, base_sha)
    if unread:  # the base has a config that does not load, so which Specs it approved is unknown: no pass on a guess
        return (
            (
                f"{', '.join(touched[:MAX_SHOWN])} changed, and aidd cannot tell whether a Spec froze it, because the base commit's "
                f"{config.CONFIG_PATH} does not load. Ask whoever owns the base branch to fix that file, update this branch from it, then run `aidd test` again. "
                "If this change is that fix, a person merges it past the required check."
            ),
            [],
            [],
        )
    texts: dict[str, tuple[str | None, str | None]] = {}

    def text_of(path: str) -> tuple[str | None, str | None]:
        if path not in texts:
            texts[path] = (git.show(base_sha, path, repo), git.show(head_sha, path, repo))
        return texts[path]

    found: dict[str, list[str]] = {}
    revised: dict[str, list[str]] = {}
    for data in governing.specs_at(repo, base_sha, base_view.spec_dirs(specs_dir, base_cfg)).values():
        sid = str(data.get("id"))
        if workitems.spec_status(data) not in workitems.FROZEN_STATUSES:
            continue
        changed = [p for p in touched if workitems.frozen_change(data, p, text_of)]
        if changed and sid in held and _revisions(held[sid]) > _revisions(data):
            revised[sid] = changed
        else:
            found.update({p: [*found.get(p, []), sid] for p in changed})
    notes, listed_revised = _revisions_said(revised)
    if not found:
        return "", notes, listed_revised
    names = sorted(found)
    owners = ", ".join(sorted({sid for ids in found.values() for sid in ids}))
    one = len(names) == 1
    return (
        (
            f"{_listed(names)} differ{'s' if one else ''} from the base, and {owners} froze {'it' if one else 'them'} when approved. "
            f"A change leaves what an approved Spec froze as it is, even for a formatting change, unless it revises that Spec. "
            f"Put new tests in a new file, or wait until {owners} is done, or revise {owners} in this change with its owner's yes "
            "(`spec.revise`: a `revisions` entry, then approval again)."
        ),
        notes,
        listed_revised,
    )
