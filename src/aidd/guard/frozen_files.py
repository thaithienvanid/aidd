"""The files a Spec freezes: its tests, design files, and frozen docs, held once its approval holds, and protected
paths outside every approved scope.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config, knowledge, workitems
from aidd.guard import role_areas, verdicts
from aidd.kernel import git, globs, repo_paths

# Marks a view entry that only an approval of this branch holds, with no active Spec behind it (frozen_view); its value
# is that approval's lineage (stale_approvals._lineage).
STANDING = "_standing"


def frozen_view(root: str, cfg: config.Config, specs: list[tuple[str, dict]]) -> tuple[set[str], list[tuple[str, dict]]]:
    """(the ids of the frozen Specs, the active Specs with each frozen one as its approval froze it). A Spec is frozen
    while its approval holds, or while one of an earlier version stands until `aidd revise` reopens it
    (`stale_approvals.approved_text`), so a change that voids the approval never opens the tests before the person
    approves again. A frozen Spec reads with the approved id, route, and test mode, and the files both texts freeze:
    an edit of the working tree's Spec never unfreezes what was approved. Another approval made on this branch joins as
    an entry of its own, marked STANDING."""
    obs = workitems.Observer(Path(root), cfg)
    held: set[str] = set()
    view = []
    for rel, d in specs:
        # A key that starts with `_` is the guard's own marker (STANDING, role_areas.APPROVED_TASKS), never the Spec's:
        # a role that writes the Spec could otherwise write one in to open a scope or drop the Spec's rules.
        d = {k: v for k, v in d.items() if not str(k).startswith("_")}
        approved = workitems.approved_text(obs, rel, d)
        if approved is not None:
            d = _as_approved(d, approved)
            held.add(str(d.get("id")))
            if obs.knows_approvals():
                # The Tasks a recorded approval froze, for `{scope:assigned}`; never where only a stored status answers,
                # which the role that writes the Spec could write itself.
                d[role_areas.APPROVED_TASKS] = approved.get("tasks")
        view.append((rel, d))
    # Every other approval made on this branch freezes what it froze, as its own entry with no Tasks (so it adds no write
    # scope): no id change, move, removal, or decoy file sheds it (stale_approvals.standing_approvals).
    for _, _, front, path, lineage in workitems.standing_approvals(obs, {str(d.get("id")) for _, d in specs}):
        sid = str(front.get("id"))
        held.add(sid)
        view.append((path or f"{cfg.specs_dir}/{sid}.md", {**_as_approved({}, front), STANDING: lineage}))
    return held, view


def _as_approved(now: dict, then: dict) -> dict:
    """The Spec `now` with what the approved text `then` froze: its id, route, and test mode, and both texts' tests,
    design files, and docs."""
    tests_now, tests_then = _section(now, "tests"), _section(then, "tests")
    tests = {**tests_now, "files": _union(tests_then.get("files"), tests_now.get("files"))}
    tests["commands"] = _union(tests_then.get("commands"), tests_now.get("commands"))
    tests.pop("mode", None)
    tests.update({"mode": tests_then["mode"]} if "mode" in tests_then else {})
    docs_then = [d for d in _union(then.get("docs"), []) if isinstance(d, dict)]
    paths = {d.get("path") for d in docs_then}
    docs = docs_then + [d for d in _union(now.get("docs"), []) if isinstance(d, dict) and d.get("path") not in paths]
    design = {**_section(now, "design"), "files": _union(_section(then, "design").get("files"), _section(now, "design").get("files"))}
    return {**now, "id": then.get("id", now.get("id")), "route": then.get("route"), "tests": tests, "design": design, "docs": docs}


def _section(data: dict, key: str) -> dict:
    found = data.get(key)
    return found if isinstance(found, dict) else {}


def _union(first: object, second: object) -> list:
    """The items of two lists, in order, each once (a non-list counts as empty)."""
    items = [*(first if isinstance(first, list) else []), *(second if isinstance(second, list) else [])]
    return [x for i, x in enumerate(items) if x not in items[:i]]


def _frozen_by(specs: list[tuple[str, dict]], rel: str, section: str, held: set[str]) -> list[str]:
    """IDs of the active Specs that list `rel` among their `tests` or `design` files or their frozen `docs`, and whose
    Spec approval holds. An emergency Spec is a backfill: nothing on it is frozen yet."""
    return [
        str(d.get("id"))
        for _, d in specs
        if d.get("route") != "emergency"
        and str(d.get("id")) in held
        and not (section == "tests" and workitems.tests_with(d))  # written with the code: never frozen
        and globs.match_any(workitems.frozen_docs(d) if section == "docs" else (d.get(section) or {}).get("files", []), rel)
    ]


def draft_spec_ids(specs: list[tuple[str, dict]], held: set[str]) -> list[str]:
    """IDs of the active Specs that have not had Spec approval yet: their scope and tests can still change, so a path
    they miss means "add it to the Spec", never "get it approved again". A cancelled Spec is neither."""
    return [str(d.get("id")) for _, d in specs if d.get("route") != "emergency" and str(d.get("id")) not in held and workitems.stored_status(d) != "cancelled"]


def draft_hint(rel: str, ids: str) -> str:
    """What to do with a path a not-yet-approved Spec does not cover: change the Spec, which is still open."""
    if repo_paths.looks_like_test(rel):
        return f"{rel} is outside the scope of {ids} and not in its tests.files: add it to tests.files in the Spec (it isn't approved yet). Then write it"
    return (
        f"{rel} is outside the scope of {ids}: add it to a Task's scope in the Spec (it isn't approved yet). "
        "Then build it after Spec approval. Or leave it alone"
    )


def frozen_by_carried(root: str, cfg: config.Config, specs: list[tuple[str, dict]], rel: str) -> str | None:
    """Why `rel` is not this branch's to write although the branch binds another Spec: it belongs to a Spec the branch
    only carries from the branch it was built on (the Spec itself, its tests, design files, or frozen docs)."""
    active = {r for r, _ in specs}
    for r, d in workitems.carried_specs(root, cfg) if active else []:
        # Its tests too, under `tests.mode: with_code`: unfrozen for its own builder, never for another branch.
        tests = list((d.get("tests") or {}).get("files") or [])
        if r not in active and globs.match_any([r, *tests, *workitems.frozen_paths(d)], rel):
            return (
                f"{rel} belongs to {d.get('id')}, which this branch only carries from the branch it was built on. Next: change it on "
                f"{d.get('id')}'s own branch, then take that branch in here"
            )
    return None


def unlisted_test(rel: str, ids: str) -> str:
    """The test writer's new test file for a Spec not yet approved: write it now, and list it while the Spec is open."""
    return (
        f"{rel}: your new test file for {ids}, before Spec approval: write it, then list it in `tests.files` in the Spec before "
        "you ask for approval. Until it is listed, the gate's scope rule fails it"
    )


def new_on_branch(root: str, rel: str) -> bool:
    """Whether `rel` is new on this branch: its base has no such file. A role's write-first allowance covers only what
    it adds, never a file the base already holds (another feature's test, an accepted ADR)."""
    base = git.branch_base(root)
    return git.show(base, rel, root) is None


def living_work_note(rel: str, docs_dir: str, role: str | None, specs: list[tuple[str, dict]]) -> str | None:
    """The note for the owner's write to its own product-level work while a Spec is a draft: keep it living, never link
    it from the Spec's `docs`, which would freeze it with one Spec (unlinked_paperwork's advice for every other new
    file). None for another role, for a file any active Spec freezes or lists (its own rules decide), and for a file
    that is no product-level work."""
    if not role or not globs.match_any(role_areas.living_files(role, docs_dir), rel):
        return None
    if globs.match_any([p for _, d in specs for p in workitems.frozen_paths(d)], rel):
        return None
    return f"{rel}: the product's living work: update it in the same change as the Spec's own design or tech spec, and never link it from a Spec's `docs`, which would freeze it with one Spec"


def unlinked_paperwork(root: str, specs: list[tuple[str, dict]], drafts: list[str], rel: str, literal: list[str]) -> str | None:
    """Why a role may write `rel`, a document of its own kind that a Spec not yet approved does not link yet, and the
    one step that registers it; None when `rel` is not one. `drafts` are the draft ids role_areas.safe_draft_ids
    checked, so each names its Spec file's own folder. The role's area (checked before) already holds `rel`: in the
    draft Spec's own folder (`specs/<ID>/`), or, when new on this branch, a folder of its own area such as `docs/adr/`.
    A file any active Spec freezes or lists is never one: its own rules decide. A person writes the document first and
    files it before sign-off; so does a role."""
    if globs.match_any([p for _, d in specs for p in workitems.frozen_paths(d)], rel):
        return None
    for spec_rel, d in specs:
        sid = str(d.get("id"))
        if sid not in drafts:
            continue
        folder = spec_rel.removesuffix(".md")
        linked = [x["path"] for x in d.get("docs") or [] if isinstance(x, dict) and isinstance(x.get("path"), str)]
        if globs.match_any(linked, rel):
            return None  # registered: the rules for a linked document decide
        if globs.match_any([f"{folder}/design/**"], rel):
            return f"{rel}: a design file of {sid}, before Spec approval: write it, then list it in `design.files` before you ask for approval"
        if globs.match_any([f"{folder}/**"], rel) or (globs.match_any(literal, rel) and new_on_branch(root, rel)):
            if f"/{workitems.THREAT_MODELS}/" in f"/{rel}":
                return (
                    f"{rel}: the component's threat model, for {sid}: write it, then link it from the Spec's `docs` as a living doc "
                    "(`kind: threat-model`, `frozen: false`) before you ask for approval; the Spec's own delta goes in its Design"
                )
            return (
                f"{rel}: your document for {sid}, before Spec approval: write it, then link it from the Spec's `docs` (frozen by default; "
                "`frozen: false` keeps it living) before you ask for approval. Until then `aidd validate` warns and the gate's scope rule fails it"
            )
    return None


def _owns(role: str | None, placeholder: str, unfrozen: bool) -> bool:
    """Whether `role` writes `{tests}` or `{design}`: the verifier and the product designer, and on an emergency backfill
    the developer's regression test. The session itself, with no role, plays every role."""
    return role is None or placeholder in role_areas.write_area(role, unfrozen)


def protected_deny(rel: str, protected: str, where: str) -> verdicts.Verdict:
    """A protected path with no approved scope that covers it: the one next step first, the agent's own when it can."""
    if "no active Spec" in where:
        step = (
            f"write the Spec that covers it: `aidd new spec --paths {rel}` (or `/aidd-team:specify`), then ask the person to type `approve <ID>`, "
            "or `approve all` to let you record each approval as you go. A person who wants notes instead of stops sets `mode: advisory` in .aidd/config.yaml"
        )
    else:
        step = "add it to a Task's scope in the Spec, then ask the person to type `approve <ID>` again (the change voids the old approval)"
    return "deny", (
        f"{rel} is a protected path ({protected}), and {where}: a change to it is major, so it waits for a scope the person approves. "
        f"Next: {step}. Or leave it alone"
    )


def _doc_owner(specs: list[tuple[str, dict]], rel: str) -> tuple[str, str]:
    """A frozen doc's placeholder, `{docs:<kind>}`, and the roles whose write area names it, in words."""
    kind = next(
        (d.get("kind") for _, s in specs for d in s.get("docs") or [] if d.get("path") in workitems.frozen_docs(s) and globs.match_any([d["path"]], rel)),
        "other",
    )
    placeholder = f"{{docs:{kind}}}"
    roles = knowledge.roles()["roles"]
    owners = [k for k in knowledge.roles()["order"] if placeholder in roles[k]["writes"]]
    return placeholder, " or ".join(f"the {k.replace('-', ' ')}" for k in owners) or "the author"


def frozen_file(specs: list[tuple[str, dict]], rel: str, role: str | None, kind: str, unfrozen: bool, held: set[str]) -> verdicts.Verdict:
    """A test or design file, or a frozen doc, of the Spec: its owner writes it until Spec approval, and nobody after."""
    if kind == "doc":
        section, (placeholder, owner) = "docs", _doc_owner(specs, rel)
    else:
        section, placeholder = ("tests", "{tests}") if kind == "test" else ("design", "{design}")
        owner = "the verifier" if kind == "test" else "the product designer"
    frozen = _frozen_by(specs, rel, section, held)
    if frozen:
        # The Spec `aidd revise` takes: the frozen one, or, for an approval only this branch holds, the one active Spec,
        # which revise reopens it through. Its id where its file is named for it, else the file's path as it is now.
        entry = next(((r, d) for r, d in specs if str(d.get("id")) == frozen[0]), ("", {"id": frozen[0]}))
        if entry[1].get(STANDING):
            # Only a Spec in the approval's lineage with no approval of its own reopens it, the one `aidd revise` takes.
            lineage = entry[1][STANDING] if isinstance(entry[1][STANDING], list) else []
            active = {r: d for r, d in specs if not d.get(STANDING) and str(d.get("id")) not in held}
            entry = next(((r, active[r]) for r in lineage if r in active), entry)
        sid = str(entry[1].get("id"))
        target = sid if not entry[0] or Path(entry[0]).name == f"{sid}.md" else entry[0]
        lead = ""
        if entry[1].get(STANDING):  # its Spec left the branch: revise restores it to record why, then removes it again
            target, lead = sid, " from the main session (a role hands it this step)"
        return "deny", (
            f"{rel} is a {kind} file of {', '.join(frozen)}, frozen by Spec approval (an approval of it holds, or one of an earlier "
            f"version stands until the Spec is revised), and any "
            f'edit voids the approval. To change it, run `aidd revise {target} "<what was wrong>"`{lead} (commit a moved Spec first): it records why and makes the '
            f"Spec a draft again. Then let {owner} change its {section}, and ask for Spec approval again on the new hash: one typed `approve <ID>`, "
            "or the person's standing approval covers it (a wrong name is fixed this way, while nothing outside depends on it)"
        )
    if not _owns(role, placeholder, unfrozen):
        return "deny", (
            f"{rel} is a {kind} file of the Spec: {owner} writes it while specifying, and after Spec approval nobody does. Hand the change to that role"
        )
    return "allow", (
        f"a {kind} file of the Spec, before Spec approval: no approval of the Spec as it reads now holds, so write it now. "
        "It is frozen once the Spec is approved"
    )


def frozen_section_edit(view: list[tuple[str, dict]], held: set[str], rel: str, texts: tuple[str | None, str | None]) -> str | None:
    """Why an edit of manifest `rel` is denied: it changes a test section a frozen Spec freezes by itself
    (`pyproject.toml#tool.pytest`), read as the Spec hash reads it (`workitems.section_digest`), so a manifest that does
    not parse counts as changed. The rest of the manifest, such as a dependency bump, stays free. `view` and `held` are
    `frozen_view`'s. An edit that gives no new text (an edit tool without it) is denied, failing closed; a shell write,
    which gives neither text, is left to the gate, which voids the approval, while the tests stay frozen as the stale
    approval's (`stale_approvals`)."""
    old_text, new_text = texts
    if old_text is None or rel.rsplit("/", 1)[-1] not in workitems.SECTION_MANIFESTS:
        return None
    entries = [
        (str(d.get("id")), e)
        for _, d in view
        if d.get("route") != "emergency" and str(d.get("id")) in held
        for e in (d.get("tests") or {}).get("files") or []
        if (workitems.frozen_section(str(e)) or ("", ""))[0] == rel
    ]
    for sid, entry in entries:
        before = workitems.section_digest(entry, {rel: "before"}, lambda _p: old_text)
        after = workitems.section_digest(entry, {rel: "after"}, lambda _p: new_text) if new_text is not None else None
        if new_text is None or before != after:
            return (
                f"{rel}: this edit changes `{entry}`, a test setting of {sid} frozen by Spec approval with its tests, or gives no new text the "
                f"guard can read, so it could void the approval. The rest of the file, such as a dependency, stays free. To change the "
                f'setting, run `aidd revise {sid} "<what was wrong>"`, then ask for Spec approval again'
            )
    return None


def frozen_any(specs: list[tuple[str, dict]], rel: str, held: set[str]) -> verdicts.Verdict | None:
    """The deny for a test or design file, or a frozen doc, that a frozen Spec freezes, whoever edits it; None when no
    frozen Spec freezes `rel`. For the paths the edit check would otherwise allow early (several Specs on one branch)."""
    for section, kind in (("tests", "test"), ("design", "design"), ("docs", "doc")):
        if _frozen_by(specs, rel, section, held):
            return frozen_file(specs, rel, None, kind, False, held)
    return None
