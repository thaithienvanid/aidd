"""The Specs whose own tests `aidd test` runs for a change.

A Spec applies to a change, and its commands run and count, when the diff holds it (added, changed, deleted, or moved), when
the branch is `spec/<ID>`, or when `--spec` names it. A Spec the diff only reaches through a Task's scope, while it is
approved or in progress, does not run: an unrelated change inside a wide scope must not fail on tests that fail by design
until the Spec is built. Such a Spec gets a note and a place in the evidence, and the delegate's merge check notes it too.
The base decides what a Spec is (`base_view`): the head cannot lower, move, or rewrite a Spec the base holds.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass

from aidd import workitems
from aidd.kernel import documents, git, globs, repo_paths, retired_names
from aidd.testing import base_view

# The sets of the Spec status table (common.schema.json `x-sets`) a run decides by. A Spec the base holds in one of IN_FLIGHT is open:
# a deleted or moved one still applies, and a change that only reaches its scope is told.
IN_FLIGHT = workitems.FROZEN_STATUSES
# A Spec not built yet (`can_wait`). Its new-behavior commands also run on the base, and a change that only reaches its scope is told.
NOT_BUILT = workitems.CAN_WAIT
# A Spec in Implement (`implementing`): a change that only reaches its Task scope does not run its tests.
OPEN = workitems.IMPLEMENTING
BRANCH = re.compile(r"spec/(?P<id>[A-Za-z][A-Za-z0-9]*-[0-9]+)")


@dataclass(frozen=True)
class Governing:
    """One Spec an `aidd test` run answers to: its path, its front matter as the run decides by it (`base_view.spec_view`),
    and why it applies: `changed`, `given`, `branch`, `base` (the base commit's Spec, which the head deleted, moved, or
    broke), or `scope` (the change only touches its Task scope, so its tests do not run). `head` is the head's own text and
    `base_status` the status the base holds, None for a Spec new in the head."""

    path: str
    data: dict
    why: str
    head: dict | None = None
    base_status: str | None = None

    @property
    def runs(self) -> bool:
        return self.why != "scope"

    @property
    def red(self) -> bool:
        """Whether its new-behavior commands also run on the base: a Spec new in the head, or one the base does not hold as
        built. Never for a Spec the head deleted, since its test files may be gone from the head too, nor for one the base holds as
        built (a prose fix to a done Spec), whose new behavior the base already has."""
        return self.why not in ("base", "scope") and (self.base_status is None or self.base_status in NOT_BUILT)


@dataclass(frozen=True)
class GoverningChange:
    """What the run covers: the committed diff (`files`), the paths it covers (the working tree's, for a quick check), the
    branch's name, the Spec `--spec` names, if any, the base commit, whose view of the Specs and the config decides, and whether
    the head is a commit the change does not control, whose Specs then read in today's shape (`read_old_shape`)."""

    files: list[dict]
    paths: list[str]
    branch: str = ""
    spec: str | None = None
    base_sha: str | None = None
    read_old_shape: bool = False


def change_branch(repo: str, env: dict[str, str] | None = None) -> str:
    """The branch the change is on: the checked-out one, else the one a CI platform names for a pull or merge request, since CI
    checks out a commit and not a branch. The same name a local run and a CI run read, so the `spec/<ID>` rule is one rule."""
    seen = dict(os.environ) if env is None else env
    return git.current_branch(repo) or seen.get("GITHUB_HEAD_REF", "") or seen.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "")


def specs_at(repo: str, ref: str, specs_dirs: list[str]) -> dict[str, dict]:
    """Every Spec under the `specs_dirs` at `ref` that parses, by path. A saved request, a README, and any other file are left out."""
    wanted: dict[str, str] = {}
    for specs_dir in specs_dirs:
        for p, oid in git.ls_tree(ref, repo, paths=[specs_dir]).items():
            if p.endswith(".md") and not workitems.is_saved_request(p, specs_dir.rstrip("/")):
                wanted[p] = oid
    blobs = git.raw_objects(sorted(set(wanted.values())), repo)
    found: dict[str, dict] = {}
    for path, oid in sorted(wanted.items()):
        try:
            raw, _ = documents.split_front_matter(blobs.get(oid, b"").decode("utf-8", errors="replace"), path)
        except (documents.DocumentError, RecursionError):
            continue
        if (data := _read_as_today(path, raw)) is not None:  # a commit before an upgrade holds the old names, and they still decide
            found[path] = data
    return found


def _read_as_today(path: str, raw: dict) -> dict | None:
    """The front matter `raw` of a Spec in today's shape, or None for a file that is no Spec. A Spec the upgrade leaves for a person
    (an `experiment`, a new name beside the old) cannot be read: one that is approved or later decides the run by what it froze, so
    the run stops and says so; any other binds nothing here and is left out, as a file that does not parse is."""
    if raw.get("type") != "spec":
        return None
    try:
        return workitems.todays_shape(raw)
    except retired_names.Refused as exc:
        if workitems.spec_status(raw) not in workitems.PAST_APPROVAL:
            return None
        raise documents.DocumentError(
            f"{path}: {exc}. aidd cannot read what that approved Spec froze, so it cannot tell what this run must hold the change to. "
            "Make that change by hand, as `aidd upgrade` says, on the branch that holds it, update this branch from that branch, then run `aidd test` again"
        ) from None


def _scope_hits(data: dict, paths: list[str]) -> list[str]:
    scopes = [s for t in data.get("tasks") or [] if isinstance(t, dict) for s in t.get("scope") or [] if isinstance(s, str)]
    return [p for p in paths if globs.match_any(scopes, p)]


def find_governing(repo: str, specs_dir: str, head_sha: str, change: GoverningChange) -> tuple[list[Governing], list[str]]:
    """The Specs this run answers to, in path order (those only reached by scope last), and the notes that say which and why.

    A Spec that cannot be told stops the run: a branch named `spec/<ID>` with no such Spec at the head, or two Specs with one id."""
    files, paths, spec = change.files, change.paths, change.spec
    base_cfg, _ = base_view.load_config(repo, change.base_sha)
    dirs = base_view.spec_dirs(specs_dir, base_cfg)
    changed = sorted({p for d in dirs for p in workitems.find_specs_in_diff(files, d, lambda path: git.show(head_sha, path, repo))})
    why = {p: "changed" for p in changed}
    if spec:  # a flag adds a Spec to the run and hides none: every Spec that applies still runs
        why[repo_paths.repo_path(spec)] = "given"
    named = BRANCH.fullmatch(change.branch)
    tree = specs_at(repo, head_sha, dirs) if paths or named else {}
    base_tree = specs_at(repo, change.base_sha, [(base_cfg.specs_dir if base_cfg else specs_dir)]) if change.base_sha else {}
    base_by_id = {str(d.get("id")): d for d in base_tree.values()}
    if named:
        ids = {str(d.get("id")): p for p, d in tree.items()}
        if named["id"] not in ids:
            raise documents.DocumentError(
                f"the branch is {change.branch}, but {specs_dir}/ holds no Spec {named['id']} at the head, so aidd cannot tell which Spec's tests to run: "
                f"commit {named['id']}, or rename the branch"
            )
        why.setdefault(ids[named["id"]], "branch")
    for path, data in tree.items():
        if path not in why and workitems.spec_status(base_view.spec_view(data, base_by_id.get(str(data.get("id"))))[0]) in OPEN and _scope_hits(data, paths):
            why[path] = "scope"
    entries, notes = [], []
    for path, kind in sorted(why.items()):
        entry, said = _entry(repo, head_sha, (path, kind), base_by_id, change.read_old_shape)
        entries.append(entry)
        notes += said
    entries += _dropped(repo, change, base_tree, {str(d.get("id")) for d in tree.values()}, paths)
    _refuse_twins(entries)
    entries.sort(key=lambda g: (not g.runs, g.path))
    return entries, notes + _notes(entries)


def _entry(repo: str, head_sha: str, applies: tuple[str, str], base_by_id: dict[str, dict], read_old_shape: bool) -> tuple[Governing, list[str]]:
    path, kind = applies
    repo_real = os.path.realpath(repo)
    target_real = os.path.realpath(os.path.join(repo_real, path))
    try:
        inside = os.path.commonpath([repo_real, target_real]) == repo_real
    except ValueError:
        inside = False
    if not inside:
        raise documents.DocumentError(f"{path} is outside the repository; name a Spec inside it, or run `aidd status` to see open Specs")
    if os.path.isdir(target_real):
        raise documents.DocumentError(f"{path} is a directory, not a Spec file; run `aidd status` to see open Specs, or pass a Spec file or id")
    text = git.show(head_sha, path, repo)
    if text is None:
        if not os.path.isfile(target_real):
            raise documents.DocumentError(f"{path} does not exist; run `aidd status` to see open Specs, or `aidd new spec <title>` to create one")
        raise documents.DocumentError(f"{path} is not in the head commit; commit it first")
    # The Spec names the commands and their log files: it must pass its schema before anything runs.
    data, _, errs = workitems.load_object(text, path, read_old_shape=read_old_shape)
    if errs:
        raise documents.DocumentError("; ".join(errs))
    base = base_by_id.get(str(data.get("id")))
    view, notes = base_view.spec_view(data, base)
    return Governing(path, view, kind, data, workitems.spec_status(base) if base is not None else None), notes


def _dropped(repo: str, change: GoverningChange, base_tree: dict[str, dict], head_ids: set[str], paths: list[str]) -> list[Governing]:
    """The Specs the diff holds that are not at the head under their id, because the head deleted, moved, or broke the file, or
    changed its id. Each runs from its declaration at the base, so the author cannot drop a Spec's tests by dropping the Spec. A
    Spec the head still holds is judged by the head, which `find_governing` already did."""
    found = []
    for path, data in base_tree.items():
        if path in paths and str(data.get("id")) not in head_ids and workitems.spec_status(data) in IN_FLIGHT:
            text = git.show(change.base_sha or "", path, repo) or ""
            loaded, _, errs = workitems.load_object(text, path, read_old_shape=True)
            if errs:
                raise documents.DocumentError("; ".join(errs))
            found.append(Governing(path, loaded, "base", None, workitems.spec_status(loaded)))
    return found


def _refuse_twins(entries: list[Governing]) -> None:
    twins = sorted(i for i, n in Counter(str(g.data.get("id")) for g in entries).items() if n > 1)
    if twins:
        paths = ", ".join(g.path for g in entries if str(g.data.get("id")) in twins)
        raise documents.DocumentError(
            f"two Specs have the id {twins[0]} ({paths}), so aidd cannot tell which one's tests to run: give one of them a new id, then run `aidd test` again"
        )


def _notes(entries: list[Governing]) -> list[str]:
    ran = [g for g in entries if g.runs]
    reasons = {
        "changed": "the change holds it",
        "given": "--spec names it",
        "branch": "the branch is named for it",
        "base": "the head deleted, moved, or broke it, so its declaration at the base ran: restore the Spec, or end it with its status",
    }
    out = []
    if ran and (len(ran) > 1 or any(g.why != "changed" for g in ran)):
        shown = "; ".join(f"{g.data.get('id')} ({reasons[g.why]}{', green only' if not g.red and g.why != 'base' else ''})" for g in ran)
        out.append(f"Spec tests run for {shown}")
    for g in entries:
        if not g.runs:
            sid = g.data.get("id")
            out.append(
                f"{sid} ({g.path}) is {workitems.spec_status(g.data)} and this change touches its Task scope, but does not hold it, so its tests did not run. "
                f"If this is {sid}'s work, work on a branch named spec/{sid} or pass --spec {sid}; if not, nothing to do"
            )
    return out
