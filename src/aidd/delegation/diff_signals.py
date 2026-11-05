"""What a delegated change touches, read from git objects and never the working tree: the paths in a reserved area,
the workflows that deploy on a push to a branch, and the test files that lost a line."""

from __future__ import annotations

import re

from aidd import risk
from aidd.delegation import policy
from aidd.kernel import git, globs, resources

WORKFLOWS = ".github/workflows/"
# The actions a workflow's `run:` line deploys by, as `aidd risk --command` reads it.
DEPLOYING = ("deploy.run", "release.publish", "infra.apply")
# A step that runs a deploy by its words, whatever the tool: a `--prod` flag, a package or make `deploy` target, or a
# deploy script. A false match only defers.
DEPLOY_WORDS = re.compile(r"(--prod\b|\b(npm|yarn|pnpm|bun)\s+(run\s+)?deploy\b|\bmake\s+deploy\b|[\w./-]*deploy[\w.-]*\.sh\b)", re.I)


def changed(base: str, head: str, cwd: str) -> list[str]:
    """Every path `base...head` adds, changes, renames, or deletes, from the commits alone."""
    out = git.run(["diff", "--name-only", "-z", "--no-renames", "--end-of-options", f"{base}...{head}"], cwd)
    return sorted(p for p in out.split("\0") if p)


def _reserved_globs(rs: risk.RuleSet) -> dict[str, list[str]]:
    """Each reserved area's globs by its name, and the infra files a host deploys from as `infra`: the built-in paths and
    the config's together, so a preset or the tip's config that redefines an area can only add to what is reserved."""
    builtin = resources.load_json("risks.json")["areas"]
    out = {}
    for name in policy.builtin()["reserved_areas"]:
        out[name] = list(dict.fromkeys([*builtin.get(name, {}).get("paths", []), *rs.areas.get(name, {}).get("paths", [])]))
    out["infra"] = list(dict.fromkeys([*builtin["infra"].get("deploys_on_merge", []), *rs.areas.get("infra", {}).get("deploys_on_merge", [])]))
    return out


def reserved_paths(rs: risk.RuleSet, paths: list[str]) -> list[str]:
    """Each path in a reserved area, as `path (area)`: what decides, CI, the test-runner config, the dependencies, or
    a file a host deploys from."""
    areas = _reserved_globs(rs)
    hits = []
    for path in paths:
        named = [a for a, pats in areas.items() if globs.match_any(pats, path, fold_case=True)]
        if named:
            hits.append(f"{path} ({', '.join(named)})")
    return hits


def _reaches(scope: str, pattern: str) -> bool:
    """Whether a Task scope names a path an area's glob matches, or the glob names a path inside the scope: `**`,
    `.github/**`, or `package.json` reaches its area, and `src/cart/` reaches none of them."""
    if not scope.strip("*/"):
        return True  # a catch-all reaches every area
    glob = scope + "**" if scope.endswith("/") else scope
    samples = [globs.sample_path(glob)] + ([] if any(c in glob for c in "*?[") else [glob])
    if any(globs.match(pattern, s, fold_case=True) for s in samples):
        return True
    # A family of paths, such as `.github/workflows/**`, inside the scope; a single file a folder holds, such as
    # `docs/CODEOWNERS` under `docs/`, waits for the diff, where the reserved paths are read.
    return any(c in pattern for c in "*?[") and globs.match(glob, globs.sample_path(pattern), fold_case=True)


def reserved_scopes(rs: risk.RuleSet, scopes: list[str]) -> list[str]:
    """Each Task scope glob that could reach a reserved area, as `glob (area)`. A scope of `**` reaches all of them."""
    hits = []
    for scope in scopes:
        named = [a for a, pats in _reserved_globs(rs).items() if any(_reaches(scope, p) for p in pats)]
        if named:
            hits.append(f"{scope} ({', '.join(sorted(set(named)))})")
    return hits


def changed_test_files(base: str, head: str, cwd: str) -> list[str]:
    """Each test file the merge base holds that the head does not hold byte for byte: changed, renamed, or removed. A
    new test file is fine, since it only adds proof."""
    start = git.merge_base(base, head, cwd)
    tests = policy.builtin()["test_paths"]
    before, after = git.ls_tree(start, cwd), git.ls_tree(head, cwd)
    return sorted(p for p, oid in before.items() if globs.match_any(tests, p, fold_case=True) and after.get(p) != oid)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _block(lines: list[str], start: int) -> list[str]:
    """The lines indented under line `start`, up to the next line at its indent or less."""
    base, out = _indent(lines[start]), []
    for line in lines[start + 1 :]:
        if line.strip() and not line.lstrip().startswith("#") and _indent(line) <= base:
            break
        out.append(line)
    return out


def _listed(block: list[str], key: str) -> list[str] | None:
    """The values of `key` in a block, as an inline `[a, b]` or as `- a` lines under it; None when it has no such key."""
    for i, line in enumerate(block):
        found = re.match(rf"^\s*{re.escape(key)}\s*:\s*(.*)$", line)
        if not found:
            continue
        rest = found.group(1).split(" #")[0].strip()
        if rest:
            return [v.strip().strip("'\"") for v in rest.strip("[]").split(",") if v.strip()]
        return [m.group(1).strip().strip("'\"") for m in (re.match(r"^\s*-\s*(.+)$", x) for x in _block(block, i)) if m]
    return None


# The triggers that never run a workflow because a branch moved: a review, an issue, a manual run, a release. Any other,
# such as `workflow_run` after a test workflow or `schedule` on the default branch, counts as reaching it.
NOT_ON_MERGE = frozenset(
    {
        "pull_request",
        "pull_request_target",
        "pull_request_review",
        "pull_request_review_comment",
        "merge_group",
        "issues",
        "issue_comment",
        "workflow_dispatch",
        "release",
        "discussion",
        "discussion_comment",
        "label",
        "milestone",
        "watch",
        "fork",
        "branches",
        "tags",
        "types",
        "paths",
    }
)


def push_reaches(text: str, branch: str) -> bool:
    """Whether a workflow's `on:` runs it on a push to `branch`. A filter it cannot read, a `branches-ignore`, or a
    negated glob counts as reaching, so production fails closed."""
    lines = text.splitlines()
    on = next((i for i, line in enumerate(lines) if re.match(r"""^(on|"on"|'on'|true)\s*:""", line)), None)
    if on is None:
        return True  # no trigger the scan can read: count it as reaching
    inline = lines[on].split(":", 1)[1].split(" #")[0].strip()
    block = _block(lines, on)
    named = (
        re.findall(r"[A-Za-z_]+", inline)
        if inline
        else [
            m.group(1)
            for m in (re.match(r"^\s*-?\s*([A-Za-z_]+)\s*:?", ln) for ln in block)
            if m and _indent(m.string) == min(_indent(x) for x in block if x.strip())
        ]
    )
    if any(n not in NOT_ON_MERGE and n != "push" for n in named):
        return True  # `workflow_run`, `schedule`, or a trigger the scan does not know may run after a merge
    if inline or "push" not in named:
        return "push" in named
    at = next((i for i, line in enumerate(block) if re.match(r"^\s*-?\s*push\s*:?\s*(\{.*)?$", line)), None)
    if at is None:
        return True
    push = _block(block, at)
    if _listed(push, "branches-ignore") is not None:
        return True
    names = _listed(push, "branches")
    if names is None:
        return _listed(push, "tags") is None  # a push filtered to tags alone reaches no branch; a paths filter still may
    return any(n.startswith("!") or globs.match(n, branch) for n in names)


def deploy_line(text: str, rs: risk.RuleSet) -> int | None:
    """The first line (from 1) where a workflow deploys: a job's `environment:`, a step that `uses:` a deploy action or
    another workflow, or a `run:` line that `aidd risk --command` reads as a deploy, a release, or an infra apply."""
    actions = tuple(a.lower() + "@" for a in policy.builtin()["deploy_actions"])
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        stripped = line.strip().removeprefix("- ").strip()
        if re.match(r"^environment\s*:", stripped):
            return n
        uses = re.match(r"^uses\s*:\s*['\"]?([^'\"\s#]+)", stripped)
        if uses and (uses.group(1).lower().startswith(actions) or "/.github/workflows/" in uses.group(1) or uses.group(1).startswith("./")):
            return n
        run = re.match(r"^run\s*:\s*(.*)$", stripped)
        if (run or n > 1) and DEPLOY_WORDS.search(stripped.split(" #")[0]):
            return n
        if run:
            body = [run.group(1)] if run.group(1).strip() not in ("|", ">", "|-", ">-", "") else [x.strip() for x in _block(lines, n - 1)]
            if any(a["action"] in DEPLOYING for cmd in body if cmd for a in risk.command_level(rs, cmd, cwd=None)["actions"]):
                return n
    return None


def deploying_workflows(rs: risk.RuleSet, tip: str, branch: str, cwd: str) -> list[str]:
    """Each workflow at the commit `tip` that deploys on a push to `branch`, as `path:line`."""
    found = []
    for path in sorted(git.ls_tree(tip, cwd, paths=[WORKFLOWS[:-1]])):
        if not path.endswith((".yml", ".yaml")):
            continue
        text = git.show(tip, path, cwd) or ""
        line = deploy_line(text, rs) if push_reaches(text, branch) else None
        if line:
            found.append(f"{path}:{line}")
    return found
