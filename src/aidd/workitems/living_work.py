"""The same-change check: a change that alters a document feeding a role's product-level work brings that work in line.

Each document type says in `schemas/roles.json` (`loop.documents`) whether it is product-level or belongs to one Spec,
which product-level type a per-change type feeds, and the files that make each up. A Spec whose change alters the files
of a type that feeds another, while that other's files stay as they were, gets a warning naming both, so the product's
product-level work (the whole-product prototype, the architecture overview) never drifts behind the changes that shape
it. It warns, never fails: a person may decide a change feeds nothing. It reads only an open Spec when the Spec comes first,
since a change with no Spec has none, and only product-level work the repository keeps already. It asks git only for a Spec
whose folder holds a feeding type's files, and only about the paths those types name, so `aidd validate` stays fast.
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config, knowledge
from aidd.kernel import documents, git, globs, regular_files
from aidd.workitems import objects
from aidd.workitems import status as status_of
from aidd.workitems.spec_file import design_paths


def _expand(pattern: str, *, specs: str, docs: str, sid: str = "") -> str:
    return pattern.replace("{specs}", specs).replace("{docs}", docs).replace("<ID>", sid)


def _folder(pattern: str) -> str:
    """The folder a glob names before its first wildcard: `specs/SPEC-1/design/**` is `specs/SPEC-1/design`."""
    return pattern.split("*", 1)[0].rsplit("/", 1)[0]


def _on_disk(root: Path, patterns: list[str]) -> bool:
    """Whether any file under the patterns' folders matches them, read from the working tree, with no git process."""
    for folder in {_folder(p) for p in patterns}:
        base = root / folder
        if base.is_dir() and any(globs.match_any(patterns, f.relative_to(root).as_posix()) for f in base.rglob("*") if f.is_file()):
            return True
    return False


def _base(root: Path, named: str) -> str:
    """Where this change starts: the merge-base with the Spec's own `base` when it names one, else with the default
    branch; "HEAD" when git can name neither."""
    if named:
        try:
            return git.merge_base(git.rev_parse(named, str(root)), "HEAD", str(root))
        except (git.GitError, ValueError, LookupError):
            return "HEAD"
    return git.branch_base(str(root))


def _planned(scopes: list[str], theirs: list[str]) -> bool:
    """Whether a Task's scope names the product-level work's home, so the same change plans to bring it in line."""
    homes = {_folder(p) for p in theirs}
    return any(scope.startswith(home + "/") or scope.rstrip("/*") == home for scope in scopes for home in homes)


def same_change_warnings(path: Path, data: dict, root: Path | None, *, specs_dir: str = "specs", docs_dir: str = "docs") -> list[str]:
    """One warning per product-level type this Spec's change feeds and leaves as it was. Empty with no Spec first, for a
    closed Spec, outside a git checkout, or when git cannot name the base, so it never guesses."""
    if root is None or str(data.get("route") or "normal") not in config.SPEC_FIRST_ROUTES or data.get("status") in status_of.ENDED_UNLANDED:
        return []
    documents = knowledge.roles()["loop"]["documents"]
    sid = str(data.get("id") or "")
    pairs: list[tuple[str, str, list[str], list[str]]] = []
    for doc_type, doc in documents.items():
        target = documents.get(str(doc.get("feeds") or ""))
        if not sid or not target or not doc.get("files") or not target.get("files"):
            continue
        mine = [_expand(g, specs=specs_dir, docs=docs_dir, sid=sid) for g in doc["files"]]
        theirs = [_expand(g, specs=specs_dir, docs=docs_dir) for g in target["files"]]
        if _on_disk(root, mine) and _on_disk(root, theirs):
            pairs.append((doc_type, doc["feeds"], mine, theirs))
    if not pairs:
        return []
    try:
        base = _base(root, str(data.get("base") or ""))
        if base == "HEAD":
            return [
                f"warning: {path}: aidd found no base branch (main, master, or the remote's default), so it cannot tell what "
                "this change altered: fetch the base branch, or name it in the Spec's `base`"
            ]
        changed = git.changed_since(str(root), base, *sorted({_folder(p) for _, _, mine, theirs in pairs for p in mine + theirs}))
        kept = git.run(["ls-files", "-z", "--", *sorted({_folder(p) for _, _, _, theirs in pairs for p in theirs})], str(root)).split("\0")
    except git.GitError:
        return []
    warnings: list[str] = []
    planned = [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    for doc_type, feeds, mine, theirs in pairs:
        fed = sorted(c for c in changed if globs.match_any(mine, c))
        if not fed or any(globs.match_any(theirs, c) for c in changed) or not any(globs.match_any(theirs, k) for k in kept if k):
            continue
        if _planned(planned, theirs):
            continue  # a Task brings it in line, as Spec approval will show
        warnings.append(
            f"warning: {path}: this change updates its {doc_type} ({', '.join(fed[:3])}{', ...' if len(fed) > 3 else ''}) "
            f"and leaves the product's {feeds} ({', '.join(theirs)}) as it was. Bring that in line in the same change: "
            f"the {documents[feeds]['written_by']} may write it while the Spec is a draft, or a Task's scope names it"
        )
    return warnings


# Files every change may touch beside its plan, such as the changelog entry each change adds.
_ANY_CHANGE = ("CHANGELOG.md",)


def _spec_data(root: Path, rel: str) -> dict | None:
    """The front matter of the changed file `rel` when it is a Spec (Markdown whose front matter says `type: spec`), else None."""
    text = objects.read_document(root, rel)[0]
    try:
        data, _ = documents.split_front_matter(text, rel) if text is not None else ({}, "")
    except documents.DocumentError:
        return None
    return data if data.get("type") == "spec" else None


def _spec_data_at(root: Path, ref: str, rel: str) -> dict | None:
    """The front matter of `rel` at commit `ref` when it is a Spec, else None."""
    try:
        data, _ = documents.split_front_matter(git.show(ref, rel, str(root)) or "", rel)
    except documents.DocumentError:
        return None
    return data if data.get("type") == "spec" else None


def unplanned_change_warnings(path: Path, data: dict, root: Path | None, *, specs_dir: str = "specs") -> list[str]:
    """One warning per file this change altered that the approved plan never names: no Task's scope, test file, design
    file, or linked doc, and not the Spec or its own folder. Unrequested work, as advice, never an error.

    A branch that changes several Specs reads each file against every changed Spec's plan, so no Spec's work is named as
    unplanned by another's. Empty for a branch that builds another Spec, `main` itself, before approval, once the Spec
    closes, with no Spec first, outside a git checkout, or when git cannot name the base."""
    if root is None or str(data.get("route") or "normal") not in config.SPEC_FIRST_ROUTES or status_of.spec_status(data) not in status_of.IN_FLIGHT:
        return []
    try:
        spec = path.resolve().relative_to(root.resolve()).as_posix()
        base = _base(root, str(data.get("base") or ""))
        if base == "HEAD":
            return []
        changed = git.changed_since(str(root), base)
    except (ValueError, git.GitError):
        return []
    if spec not in changed:
        return []
    planned = plan_globs(spec, data, specs_dir)
    for other in (c for c in changed if c != spec and c.endswith(".md") and c.startswith(f"{specs_dir}/")):
        if (theirs := _spec_data(root, other)) is not None:
            planned += plan_globs(other, theirs, specs_dir)
    return [
        f"warning: {path}: {f} changed, but no Task's scope, test, design file, or linked doc names it; ask for `spec.revise` "
        "to widen a Task's scope, or drop the change"
        for f in changed
        if not globs.match_any(planned, f)
    ]


def plan_globs(spec: str, data: dict, specs_dir: str) -> list[str]:
    """What a Spec's plan names: each Task's scope, its test files, its design files and linked docs, the Spec and its
    folder, and the files every change may touch."""
    sid = str(data.get("id") or "")
    planned = [str(g) for t in data.get("tasks") or [] if isinstance(t, dict) for g in t.get("scope") or []]
    planned += [str(f).split("#", 1)[0] for f in (data.get("tests") or {}).get("files") or []]
    planned += design_paths(data) + [str(d["path"]) for d in data.get("docs") or [] if isinstance(d, dict) and isinstance(d.get("path"), str)]
    return planned + [spec, f"{spec.rsplit('.', 1)[0]}/**", *_ANY_CHANGE] + ([f"{specs_dir}/{sid}/**"] if sid else [])


def _revisions_at(root: Path, ref: str, spec: str) -> int:
    """How many `revisions` the Spec records at commit `ref`: 0 when it is not there or does not parse."""
    text = git.show(ref, spec, str(root))
    try:
        data, _ = documents.split_front_matter(text or "", spec)
    except documents.DocumentError:
        return 0
    found = data.get("revisions") if isinstance(data, dict) else None
    return len(found) if isinstance(found, list) else 0


def _names_path(text: str, path: str) -> bool:
    """Whether `text` names `path` as a whole path: not as the end of a longer path (`lib/src/a.py`) or the start of
    another name (`a.pyc`), though a full stop that ends a sentence may follow it."""
    return re.search(rf"(?<![\w./-]){re.escape(path)}(?![\w/-]|\.\w)", text) is not None


def merged_drift_warnings(path: Path, data: dict, root: Path | None, *, specs_dir: str = "specs") -> list[str]:
    """Plan drift, once a Spec merged: one warning per file its merge changed that the plan never names, when the merge
    did not update the plan too: no `spec.revise`, which adds an entry to `revisions`. A file the Spec's `## Learn` names
    is a drift on record, so it warns no more. It reads the last merge commit on the first-parent history that changed the
    Spec, against that merge's first parent. A merge that changed other Specs reads each file against every one of their
    plans, so it never names another plan's work. Empty with no Spec first, before `done`, outside a git checkout, or when
    git cannot read the merge."""
    if root is None or str(data.get("route") or "normal") not in config.SPEC_FIRST_ROUTES or status_of.spec_status(data) != "done":
        return []
    try:
        spec = path.resolve().relative_to(root.resolve()).as_posix()
        found = git.log_fields(["-1", "--first-parent", "--merges", "--", spec], ["%H", "%P"], str(root), check=False)
        if not found:
            return []
        merge, first = found[0][0], found[0][1].split()[0]
        changed = [f for f in git.run(["diff", "--name-only", "-z", first, merge], str(root)).split("\0") if f]
    except (ValueError, IndexError, git.GitError):
        return []
    if spec not in changed:
        return []
    if _revisions_at(root, merge, spec) > _revisions_at(root, first, spec):
        return []  # the change updated its plan, on the person's yes to `spec.revise`
    planned = plan_globs(spec, data, specs_dir)
    for other in (c for c in changed if c != spec and c.endswith(".md") and c.startswith(f"{specs_dir}/")):
        if (theirs := _spec_data_at(root, merge, other)) is not None:
            planned += plan_globs(other, theirs, specs_dir)  # a merge of several Specs: no Spec's work is another's drift
    # A drift the Spec's `## Learn` names is recorded, so it warns no more.
    learned = documents.markdown_section(regular_files.file_text(root, path, documents.MAX_DOCUMENT_BYTES) or "", "Learn")
    return [
        f"warning: {path}: its merge {merge[:10]} changed {f}, which no Task's scope, test, design file, or linked doc names, "
        "and the plan stayed as it was: name the file and why in the Spec's `## Learn`, and widen the Tasks' scope next time with `spec.revise`"
        for f in changed
        if not globs.match_any(planned, f) and not _names_path(learned, f)
    ]
