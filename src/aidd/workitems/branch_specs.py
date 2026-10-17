"""The Specs a branch carries: AIDD_SPEC, or every Spec the branch adds or changes, and the Spec a diff names."""

from __future__ import annotations

import os
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, repo_paths

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
    wanted = os.environ.get("AIDD_SPEC")
    changed = [] if wanted else [p for p in git.changed_since(root, git.branch_base(root), cfg.specs_dir) if p.endswith(".md")]
    wanted = wanted or branch_spec(root, changed, cfg)
    return _read_specs(root, [repo_paths.repo_path(wanted)] if wanted else changed)


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


def find_specs_in_diff(files: list[dict], specs_dir: str, head_files_reader) -> list[str]:
    """Every Spec a diff adds or changes, in path order: the Markdown files under `specs_dir` whose head kind is spec."""
    specs = []
    folder = globs.under(specs_dir, "")
    for p in sorted(f["path"] for f in files if f["path"].startswith(folder) and f["path"].endswith(".md")):
        text = head_files_reader(p)
        try:
            if text is not None and documents.split_front_matter(text, p)[0].get("kind") == "spec":
                specs.append(p)
        except documents.DocumentError:
            continue
    return specs


def change_specs(cr: dict | None) -> list[str]:
    """The Spec paths a Change Request block names: its `spec`, or a goal's `specs`; none for an inline block."""
    if not cr:
        return []
    if isinstance(cr.get("spec"), str):
        return [cr["spec"]]
    return [s for s in cr.get("specs") or [] if isinstance(s, str)]
