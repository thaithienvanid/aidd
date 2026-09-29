"""CODEOWNERS as a source of per-path Approvers (config `owners.codeowners = true`).

The platform's own file is reused instead of restating owners in config. Like
GitHub and GitLab, the last matching rule wins, and a rule with no owners
means the path has none. Patterns follow gitignore rules and are converted to
aidd globs. GitLab `[Section]` headers are skipped (their rules still apply);
email owners are ignored, because approvals come from platform accounts.
"""

from __future__ import annotations

from . import globs

LOCATIONS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")


def to_glob(pattern: str) -> str:
    """Convert one gitignore-style CODEOWNERS pattern to an aidd glob."""
    anchored = pattern.startswith("/")
    p = pattern.lstrip("/")
    directory = p.endswith("/")
    p = p.rstrip("/")
    if not anchored and "/" not in p:
        p = "**/" + p  # no slash: match at any depth
    if p.endswith("/*") and not directory:
        return p  # `docs/*`: files directly inside, not deeper
    return p + "/**" if directory or not any(c in p.rsplit("/", 1)[-1] for c in "*?") else p


def parse(text: str) -> list[tuple[str, list[str]]]:
    rules: list[tuple[str, list[str]]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("[") or line.startswith("^["):
            continue
        parts = line.split()
        owners = [o for o in parts[1:] if o.startswith("@")]
        rules.append((to_glob(parts[0]), owners))
    return rules


def owners_for(rules: list[tuple[str, list[str]]], path: str) -> list[str]:
    """The owners of the last rule that matches, or [] when none does."""
    found: list[str] = []
    for pattern, owners in rules:
        if globs.match(pattern, path, fold_case=True):
            found = owners
    return found


def entries(text: str | None, paths: list[str]) -> list[dict]:
    """owners.paths-shaped entries for the given paths: one per distinct owner set."""
    if not text:
        return []
    rules = parse(text)
    groups: dict[tuple[str, ...], list[str]] = {}
    for p in paths:
        owners = owners_for(rules, p)
        if owners:
            groups.setdefault(tuple(owners), []).append(p)
    return [{"paths": sorted(ps), "approvers": list(owners)} for owners, ps in groups.items()]


def all_owners(text: str | None) -> list[str]:
    return sorted({o for _, owners in parse(text or "") for o in owners})
