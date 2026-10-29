"""The Specs a branch carries: AIDD_SPEC, or every Spec the branch adds or changes, and the Spec a diff names."""

from __future__ import annotations

import os
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, repo_paths
from aidd.workitems.spec_file import could_be_work_item, find_specs_in_diff

# A branch named for a Spec, `spec/SPEC-3` or `SPEC-3`: its last path part is the Spec's id.
_BRANCH_SPEC = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9]*-[0-9]+)$")


def branch_spec(root: str, changed: list[str], cfg: config.Config) -> str | None:
    """The Spec the current branch is named for (`spec/<ID>`), as a repository path, when the branch adds or changes it
    (`changed`); else None. A branch built on another Spec's branch carries that Spec too, and only its own Spec binds
    it. A name alone never picks a Spec the branch does not touch: an agent names its branch, and could otherwise
    borrow an old Spec's wide scope."""
    name = git.run(["symbolic-ref", "-q", "--short", "HEAD"], root, check=False).strip()
    m = _BRANCH_SPEC.search(name)
    rel = globs.under(cfg.specs_dir, f"{m.group(1).upper()}.md") if m else None
    return rel if rel in changed else None


def active_specs(root: str, cfg: config.Config) -> list[tuple[str, dict]]:
    """AIDD_SPEC, or the Spec the branch is named for (`spec/<ID>`) when the branch adds or changes it, or every Spec
    this branch adds or changes."""
    return _read_specs(root, _candidates(root, cfg))


MAX_ITEM_BYTES = 1_000_000  # a work item's front matter and body; anything larger is read as unreadable, never whole


def unreadable_specs(root: str, cfg: config.Config) -> list[tuple[str, str]]:
    """The work items `active_specs` would read but cannot parse, each with why. Each could be the branch's Spec, so
    the guard fails closed on them rather than read the branch as having none. A plain page (a README, with no front
    matter and no work item's name) and a document in a Spec's own folder are no work item; the Spec the branch is
    bound to (AIDD_SPEC, `spec/<ID>`) always is."""
    found = []
    candidates = _candidates(root, cfg)
    bound = _bound(root, cfg)  # then the one candidate is the branch's Spec
    for rel in candidates:
        p = Path(root) / rel
        if not p.is_file():
            continue
        try:
            if p.stat().st_size > MAX_ITEM_BYTES:
                found.append((rel, f"{rel}: larger than {MAX_ITEM_BYTES} bytes, which no work item is"))
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if not bound and not could_be_work_item(rel, text, cfg.specs_dir):
                continue
            documents.split_front_matter(text, rel)
        except (documents.DocumentError, RecursionError) as exc:
            found.append((rel, str(exc) or f"{rel}: {type(exc).__name__}"))
        except OSError as exc:
            found.append((rel, f"{rel}: it cannot be read ({type(exc).__name__})"))
    return found


def _bound(root: str, cfg: config.Config) -> bool:
    """Whether the branch names its one Spec: AIDD_SPEC, or a `spec/<ID>` branch that changes it."""
    if os.environ.get("AIDD_SPEC"):
        return True
    changed = [p for p in git.changed_since(root, git.branch_base(root), cfg.specs_dir) if p.endswith(".md")]
    return branch_spec(root, changed, cfg) is not None


def _candidates(root: str, cfg: config.Config) -> list[str]:
    wanted = os.environ.get("AIDD_SPEC")
    changed = [] if wanted else [p for p in git.changed_since(root, git.branch_base(root), cfg.specs_dir) if p.endswith(".md")]
    wanted = wanted or branch_spec(root, changed, cfg)
    return [repo_paths.repo_path(wanted)] if wanted else changed


def carried_specs(root: str, cfg: config.Config) -> list[tuple[str, dict]]:
    """Every Spec this branch adds or changes, whichever one binds it: on a branch built on another Spec's branch, the
    files that other Spec's approval froze stay frozen here too."""
    return _read_specs(root, [p for p in git.changed_since(root, git.branch_base(root), cfg.specs_dir) if p.endswith(".md")])


def _read_specs(root: str, candidates: list[str]) -> list[tuple[str, dict]]:
    found = []
    for rel in candidates:
        p = Path(root) / rel
        if not p.is_file():
            continue
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), rel)
        except (documents.DocumentError, OSError, RecursionError):
            continue  # one unreadable Spec is not the branch's Spec; the others still bind
        if data.get("kind") == "spec":
            found.append((rel, data))
    return found


def find_spec_in_diff(files: list[dict], specs_dir: str, head_files_reader) -> str | None:
    """The one Spec a diff adds or changes, or None when it holds none or several (find_specs_in_diff)."""
    specs = find_specs_in_diff(files, specs_dir, head_files_reader)
    return specs[0] if len(specs) == 1 else None


def change_specs(cr: dict | None) -> list[str]:
    """The Spec paths a Change Request block names: its `spec`, or a goal's `specs`; none for an inline block."""
    if not cr:
        return []
    if isinstance(cr.get("spec"), str):
        return [cr["spec"]]
    return [s for s in cr.get("specs") or [] if isinstance(s, str)]
