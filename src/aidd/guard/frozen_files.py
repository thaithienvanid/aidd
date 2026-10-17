"""The files a Spec freezes: its tests, design files, and frozen docs, held once its approval holds, and protected
paths outside every approved scope.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config, knowledge, workitems
from aidd.guard import role_areas, verdicts
from aidd.kernel import git, globs, repo_paths


def approved_spec_ids(root: str, cfg: config.Config, specs: list[tuple[str, dict]]) -> set[str]:
    """IDs of the active Specs whose Spec approval holds (`derived_status.approval_holds`, the one check the forecast, `aidd list`, and
    `aidd validate` share): a counted approval of the hash HEAD or the working tree holds, or, where nothing local
    records approvals, a stored status at or past ready."""
    obs = workitems.Observer(Path(root), cfg)
    return {str(d.get("id")) for rel, d in specs if workitems.approval_holds(obs, rel, d)}


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
        # Its tests too, under `tests.mode: with`: unfrozen for its own implementer, never for another branch.
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
    """Whether `role` writes `{tests}` or `{design}`: the tester and the product designer, and on an emergency backfill
    the developer's regression test. The session itself, with no role, plays every role."""
    return role is None or placeholder in role_areas.write_area(role, unfrozen)


def protected_deny(rel: str, protected: str, where: str) -> verdicts.Verdict:
    """A protected path with no approved scope that covers it: the one next step first, the agent's own when it can."""
    if "no active Spec" in where:
        step = (
            f"write the Spec that covers it: `aidd new spec --paths {rel}` (or `/aidd-team:specify`), then ask the person to type `approve <ID>`. "
            "To try an idea first with free edits, the person starts an explore branch (`git switch -c explore/<topic>`): nothing merges from it as it is"
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
        owner = "the tester" if kind == "test" else "the product designer"
    frozen = _frozen_by(specs, rel, section, held)
    if frozen:
        return "deny", (
            f"{rel} is a {kind} file of {', '.join(frozen)}, frozen by Spec approval (an approval of its current hash holds), and any "
            f'edit voids the approval. To change it, run `aidd revise {frozen[0]} "<what was wrong>"`: it records why and makes the '
            f"Spec a draft again. Then let {owner} change its {section}, and ask for Spec approval again on the new hash: one typed `approve <ID>`, "
            "or the person's standing approval covers it (a wrong name is fixed this way, while nothing outside depends on it)"
        )
    if not _owns(role, placeholder, unfrozen):
        return "deny", (
            f"{rel} is a {kind} file of the Spec: {owner} writes it while specifying, and after Spec approval nobody does. Hand the change to that role"
        )
    return "allow", (
        f"a {kind} file of the Spec, before Spec approval: no approval of the Spec's current hash holds, so write it now. "
        "It is frozen once the Spec is approved"
    )
