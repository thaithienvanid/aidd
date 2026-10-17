"""Which Specs autopilot may implement, and which a person must look at first: a Spec's route from its Tasks and from the branch's real diff, judged under the base branch's config, and whether a person approved its current hash."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from aidd import config, gate, workitems
from aidd.kernel import git, globs, json_schema


class Unknown(Exception):
    """A route autopilot cannot compute: it asks a person."""


def task_route(data: dict, cfg: config.Config, tracked: list[str]) -> str:
    """The route the Spec's Task paths and risk need (`routing.assess_paths`), as an agent wrote them."""
    scopes = [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    if not scopes:
        raise Unknown("no Task scope")
    risk = data.get("risk") or {}
    try:
        return gate.assess_paths(
            cfg,
            scopes,
            ctype=str(data.get("type") or "feat"),
            dimensions=[str(d) for d in risk.get("dimensions") or []],
            irreversible=risk.get("reversible") is False,
            tracked=tracked,
        ).required_route
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc


MAX_UNTRACKED_BYTES = 20 * 1024 * 1024  # an untracked file larger than this counts as a binary
TERMINAL = frozenset({"shipped", "done", "rolled_back", "cancelled"})


def _untracked(top: str) -> list[dict]:
    """Each untracked file (ignored ones left out) as a diff entry: its lines as added, or binary as git would call it
    (a NUL byte), so the line budget counts what the working tree adds."""
    out = []
    for rel in (p for p in git.run(["ls-files", "--others", "--exclude-standard", "-z"], top, check=False).split("\0") if p):
        path = Path(top) / rel
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                continue
            data = path.read_bytes() if st.st_size <= MAX_UNTRACKED_BYTES else b"\0"
        except OSError:
            continue
        binary = b"\0" in data[:8000] or st.st_size > MAX_UNTRACKED_BYTES
        lines = 0 if binary else data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        out.append({"path": rel, "previous_path": None, "additions": lines, "deletions": 0, "binary": binary})
    return out


def diff_files(root: Path, base_sha: str, sha: str, *, worktree: bool) -> tuple[str, list[dict]]:
    """(the fork, every file the branch changes from it to `sha` with its lines). For this working tree: to the working
    tree instead (committed, staged, and unstaged), plus the untracked files and their lines."""
    top = str(root)
    fork = git.merge_base(base_sha, sha, top)
    if not worktree:
        return fork, git.numstat(fork, sha, top)
    return fork, git.numstat(fork, None, top) + _untracked(top)


def diff_route(root: Path, cfg: config.Config, base_sha: str, sha: str, data: dict, *, worktree: bool) -> str | None:
    """The route the branch's real diff needs, as the gate computes it: every file from the fork to `sha` (for this
    working tree, to the working tree, untracked files included), with its changed lines (less the Specs and their
    frozen files, as the gate counts them), binaries, added dependencies, and the content rules' matches, under the base
    config. None when nothing changed."""

    top = str(root)
    try:
        fork, files = diff_files(root, base_sha, sha, worktree=worktree)
        listed = gate.changed_paths(files)
        if not listed:
            return None
        after = (lambda p: gate.worktree_text(top, p)) if worktree else (lambda p: git.show(sha, p, top))
        deps = gate.added_dependencies(listed, lambda p: git.show(fork, p, top), after)
        risk = data.get("risk") or {}
        return gate.assess_route(
            paths=listed,
            cfg=cfg,
            ctype=str(data.get("type") or "feat"),
            risk={"dimensions": list(risk.get("dimensions") or []), "reversible": risk.get("reversible") is not False},
            confidence="high",
            task_count=max(1, len([t for t in data.get("tasks") or [] if isinstance(t, dict)])),
            changed_lines=gate.budget_lines(files, cfg, gate.reviewed_on_branch(top, cfg, listed) + gate.proposal_only(listed, cfg)),
            binary_files=gate.counted_binaries(files, cfg, listed),
            dependencies=deps,
            binary_paths=gate.binary_paths(files),
            content=gate.content_matches(top, cfg, fork, None if worktree else sha, files),
        ).required_route
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc


def _scopes(data: dict) -> list[tuple[str, tuple[str, ...]]]:
    return sorted((str(t.get("id")), tuple(str(g) for g in t.get("scope") or [])) for t in data.get("tasks") or [] if isinstance(t, dict))


def emergency_finished(obs: workitems.Observer, rel: str, base: dict, text: str) -> bool:
    """Whether the base branch's copy of an emergency is finished: its post-incident review recorded
    (`outcome.learn_ref`), its repair shipped on the base branch (the facts git proves there, as `aidd list` derives
    them, since nobody stores a status in the normal flow), or a status, derived or stored, of shipped, done, rolled
    back, or cancelled."""
    if (base.get("outcome") or {}).get("learn_ref") or workitems.spec_status(base, approval=False) in TERMINAL:
        return True
    if not obs.base_sha:
        raise Unknown("no base branch")
    try:
        facts = obs.at(obs.base_sha, rel, text, base)
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc
    return bool(facts.shipped) or obs.status(facts, base) in TERMINAL


def same_open_emergency(root: Path, obs: workitems.Observer, sha: str, rel: str, data: dict, base: tuple[str, dict, str], *, worktree: bool) -> bool:
    """An emergency the base branch already holds, still open, that this copy only continues: the base copy (its
    path, front matter, and text) is an emergency and not finished (`emergency_finished`), the emergency block and
    every Task's scope are the base copy's, and the branch changes nothing beyond that scope, the Spec, and its frozen
    files. A finished emergency's id is never reused: a person declares a new emergency."""
    base_rel, data_base, text = base
    if data_base.get("route") != "emergency" or not obs.base_sha or emergency_finished(obs, base_rel, data_base, text):
        return False
    if data.get("emergency") != data_base.get("emergency") or _scopes(data) != _scopes(data_base):
        return False
    allowed = [g for _, scope in _scopes(data_base) for g in scope] + workitems.frozen_paths(data_base) + [rel]
    try:
        _, files = diff_files(root, obs.base_sha, sha, worktree=worktree)
    except Exception as exc:  # noqa: BLE001
        raise Unknown(str(exc)) from exc
    return all(globs.match_any(allowed, p) for p in gate.changed_paths(files))


def spec_approval_needed_for(routes: list[str | None], cfg: config.Config) -> bool:
    """Spec approval is needed on the highest of the routes given (declared, from the Tasks, from the diff)."""
    from aidd import tracking

    order = tracking.ROUTE_ORDER
    known = [r for r in routes if r]
    if any(r not in order for r in known):
        raise Unknown(f"an unknown route among {known}")
    route = max(known, key=order.index)
    return route in ((cfg.gates.get("spec_approval_routes") if cfg else None) or workitems.DEFAULT_ROUTES)


def person_approved(root: Path, obs: workitems.Observer, sid: str, h: str | None, platform=None) -> bool:
    """A person approved the Spec's current hash, by a source an agent cannot write: the local approvals ref (signature-
    checked under `gates.local_approvals: signed`, from the base config), or the platform's own approval lines as
    the gate reads them (`github.spec_approval_holds`, with a token), only from the repository the base config pins
    (`project.repo`) and only for this head and Spec hash. Never a record file: the evidence folder is in the working
    tree."""
    if h and any(i == sid and x == h for i, x in obs._approval_lines() or []):
        return True
    from aidd import platforms

    pinned = obs.cfg.get("project", "repo") if obs.cfg else None  # the base branch's config: a person pinned it
    return bool((platform or platforms.spec_approval_holds)(str(root), sid, pinned=pinned, spec_hash=h))


def cleared_specs(root: Path, obs: workitems.Observer, cfg: config.Config | None, specs: list, platform=None) -> tuple[set[str], dict[str, str]]:
    """(the Specs that may be implemented, the Specs a person must look at first, with why). A Spec is cleared when the
    highest of its declared route, the route its Tasks need, and the route the branch's real diff needs (under the base
    config) needs no Spec approval, or a person approved its current hash (`person_approved`). An emergency counts
    only when it continues an open emergency the base branch holds with the same scope (`same_open_emergency`), or a
    person approved it. Person-owned fields count only as the base branch holds them. A Spec its schema refuses is
    unknown. Never the stored status, a record file, or the declared route alone; anything unknown asks."""
    unverified: dict[str, str] = {}
    cleared: set[str] = set()
    if cfg is None or not obs.base_sha:
        return cleared, unverified
    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    at_base = {str(d.get("id")): (r, d, t) for r, d, _, t in workitems.objects_at(root, obs.base_sha, cfg.specs_dir)[0]}
    head = git.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    for it in specs:
        data, sid = it.data, it.id
        base_copy = at_base.get(sid)
        base = base_copy[1] if base_copy else {}
        if it.sha != obs.base_sha:
            for key in ("triage", "suggested_by"):
                if data.get(key) is not None and data.get(key) != base.get(key):
                    unverified[sid] = f"`{key}` is set on the branch only"
        sha = it.sha or head
        h = obs.hash_at(sha, it.text) if sha else None
        # The diff to judge: the Spec's own branch; for a copy read from the base branch, the branch here, where
        # autopilot's Implement would run.
        work = head if it.sha in (None, obs.base_sha) else it.sha
        declared = str(data.get("route") or "normal")
        try:
            if data.get("kind", "spec") == "spec" and json_schema.validate(data, "spec.schema.json"):
                raise Unknown("its schema refuses the Spec")
            if declared == "emergency":
                if base_copy and h is not None and h == obs.hash_at(obs.base_sha, base_copy[2]) and emergency_finished(obs, base_copy[0], base, base_copy[2]):
                    continue  # the base branch's own copy, finished: its backfill goes on, and there is nothing to clear
                continues = bool(work) and base_copy is not None and same_open_emergency(root, obs, work, it.rel, data, base_copy, worktree=work == head)
                if continues or person_approved(root, obs, sid, h, platform):
                    cleared.add(sid)
                else:
                    unverified.setdefault(
                        sid,
                        "its emergency is not one the base branch holds open with this scope (a finished emergency's id is never reused), and no person approved it",
                    )
                continue
            routes = [declared, task_route(data, cfg, tracked), diff_route(root, cfg, obs.base_sha, work, data, worktree=work == head) if work else None]
            if not spec_approval_needed_for(routes, cfg) or person_approved(root, obs, sid, h, platform):
                cleared.add(sid)
        except Unknown:
            continue  # not cleared: autopilot asks
    return cleared, unverified


_SPEC_LANE = "the spec lane: this change needs a Spec, approved before any code"


def lane_cleared(root: Path, obs: workitems.Observer, cfg: config.Config | None, steps: list[dict]) -> set[str]:
    """The branch's lane step may run Implement only when its real diff, judged under the base config (not the working
    tree's), needs no Spec approval: the fast lane as the gate would find it. A fast-lane step whose diff needs Spec
    approval becomes the spec lane's step: no Spec carries the change, so no Spec approval can be given, and a Spec
    comes first."""
    head = git.run(["rev-parse", "HEAD"], str(root), check=False).strip()
    out = set()
    for s in steps:
        if s.get("code") != "lane" or cfg is None or not obs.base_sha or not head:
            continue
        try:
            route = diff_route(root, cfg, obs.base_sha, head, {}, worktree=True)
            if route and not spec_approval_needed_for([route], cfg):
                out.add(str(s["id"]))
            elif route and s.get("lane") == "fast":
                s.update(lane="spec", route=route, what=_SPEC_LANE, how='write the Spec and its tests first: `aidd new spec <ID> --title "..."`')
        except Unknown:
            continue
    return out
