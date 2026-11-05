"""What a delegated change touches, read from git objects and never the working tree: the paths in a reserved area,
the workflows that deploy on a push to a branch, and the test files that lost a line."""

from __future__ import annotations

import re
from collections.abc import Sequence

from aidd import config, risk
from aidd.delegation import policy, workflow_triggers
from aidd.kernel import git, globs, resources

WORKFLOWS = ".github/workflows/"
# The actions a workflow's `run:` line deploys by, as `aidd risk --command` reads it.
DEPLOYING = ("deploy.run", "release.publish", "infra.apply")
# The deploy flag and targets: a `--prod` flag, or a package or make `deploy` target.
_DEPLOY_COMMANDS = re.compile(r"--prod\b|\b(npm|yarn|pnpm|bun)\s+(run\s+)?deploy\b|\bmake\s+deploy\b", re.I)
# A run of path characters with no `/`: a deploy script's name is `deploy` then `.sh` inside one such run.
_NAME_RUN = re.compile(r"[\w.-]+")
_DEPLOY_NAME = re.compile("deploy", re.I)
_SH_END = re.compile(r"\.sh\b", re.I)


def names_a_deploy(text: str) -> bool:
    """Whether a step runs a deploy by its words, whatever the tool: the deploy flag or targets, or a deploy script.
    A false match only defers. The time is linear in the line's length."""
    if _DEPLOY_COMMANDS.search(text):
        return True
    for run in _NAME_RUN.finditer(text):
        found = _DEPLOY_NAME.search(run.group())
        if found and _SH_END.search(run.group(), found.end()):
            return True
    return False


def changed(base: str, head: str, cwd: str) -> list[str]:
    """Every path `base...head` adds, changes, renames, or deletes, from the commits alone."""
    out = git.run(["diff", "--name-only", "-z", "--no-renames", "--end-of-options", f"{base}...{head}"], cwd)
    return sorted(p for p in out.split("\0") if p)


def host_deploy_by_area(rs: risk.RuleSet) -> dict[str, list[str]]:
    """The files a host deploys from on a merge, such as `vercel.json`, by the area that lists them: every area's
    `deploys_on_merge`, the built-in globs and the config's together, so a config's area can only add to what is reserved."""
    builtin = resources.load_json("risks.json")["areas"]
    out = {}
    for name in dict.fromkeys([*builtin, *rs.areas]):
        found = list(dict.fromkeys([*builtin.get(name, {}).get("deploys_on_merge", []), *rs.areas.get(name, {}).get("deploys_on_merge", [])]))
        if found:
            out[name] = found
    return out


def host_deploy_globs(rs: risk.RuleSet) -> list[str]:
    """The files a host deploys from on a merge, whatever area lists them."""
    return list(dict.fromkeys(g for found in host_deploy_by_area(rs).values() for g in found))


def _reserved_globs(rs: risk.RuleSet, parents: Sequence[str] = ()) -> dict[str, list[str]]:
    """Each reserved area's globs by its name, the files a host deploys from under the area that lists them, and the parent configs the
    tip's config extends as `parent config`: the built-in paths and the config's together, so a preset or the tip's config
    that redefines an area can only add to what is reserved."""
    builtin = resources.load_json("risks.json")["areas"]
    out = {}
    for name in policy.builtin()["reserved_areas"]:
        out[name] = list(dict.fromkeys([*builtin.get(name, {}).get("paths", []), *rs.areas.get(name, {}).get("paths", [])]))
    for name, found in host_deploy_by_area(rs).items():
        out[name] = list(dict.fromkeys([*out.get(name, []), *found]))
    if parents:
        out["parent config"] = list(parents)
    return out


def reserved_paths(rs: risk.RuleSet, paths: list[str], parents: Sequence[str] = ()) -> list[str]:
    """Each path in a reserved area, as `path (area)`: what decides, CI, the test-runner config, the dependencies, or
    a file a host deploys from."""
    areas = _reserved_globs(rs, parents)
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


def reserved_scopes(rs: risk.RuleSet, scopes: list[str], parents: Sequence[str] = ()) -> list[str]:
    """Each Task scope glob that could reach a reserved area, as `glob (area)`. A scope of `**` reaches all of them."""
    hits = []
    for scope in scopes:
        named = [a for a, pats in _reserved_globs(rs, parents).items() if any(_reaches(scope, p) for p in pats)]
        if named:
            hits.append(f"{scope} ({', '.join(sorted(set(named)))})")
    return hits


def changed_test_files(base: str, head: str, cwd: str) -> list[str]:
    """Each test file the merge base holds that the head does not hold byte for byte: changed, renamed, or removed. A
    new test file is fine, since it only adds proof."""
    start = git.merge_base(base, head, cwd)
    before, after = git.ls_tree(start, cwd), git.ls_tree(head, cwd)
    return sorted(p for p, oid in before.items() if config.looks_like_test(p, fold_case=True) and after.get(p) != oid)


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def block_under(lines: list[str], start: int) -> list[str]:
    """The lines indented under line `start`, up to the next line at its indent or less. A key with no value on its line also
    holds the `- item` lines at its own indent, the way YAML allows a list under a key: `branches:` then `- main`."""
    base, out = indent_of(lines[start]), []
    holds_items = lines[start].rstrip().endswith(":") and not lines[start].lstrip().startswith("-")
    for line in lines[start + 1 :]:
        level = indent_of(line)
        sibling_item = holds_items and level == base and line.lstrip().startswith("- ")
        if line.strip() and not line.lstrip().startswith("#") and level <= base and not sibling_item:
            break
        out.append(line)
    return out


# A step or job key, quoted or not, at the start of a line or inside a flow map (`{uses: x, with: {}}`), with its value; and a block
# scalar header (`|`, `|+`, `>-`, `|2`).
BLOCK_HEADER = re.compile(r"^[|>][+-]?[0-9]?[+-]?$")
LINE_KEY = re.compile(r"""^["']?(environment|uses|run)["']?\s*:\s*(.*)$""")
FLOW_KEY = re.compile(r"""[{,]\s*["']?(environment|uses|run)["']?\s*:\s*([^,}]*)""")
# A flow map this reader follows: one pair of braces on one line, after an optional key, with no quote, brace, or bracket inside.
SIMPLE_FLOW = re.compile(r"""^(?:[\w.-]+\s*:\s*)?\{[^{}\[\]"']*\}$""")
# A quoted key with an escape in it, such as `"envi\x72onment":`, may decode to any key, so the line counts as a deploy.
ESCAPED_KEY = re.compile(r"""(?:^|[{,\s])(["'])[^"'\\]*\\[^"']*\1\s*:""")  # the first backslash is fixed, so no scan backs up


def deploy_line(text: str, rs: risk.RuleSet) -> int | None:
    """The first line (from 1) where a workflow deploys: a job's `environment:`, a step that `uses:` a deploy action or
    another workflow, or a `run:` line that `aidd risk --command` reads as a deploy, a release, or an infra apply. A key may be
    quoted, a `run:` block may start with any block scalar header, and a job or step written as a flow map counts too."""
    actions = tuple(a.lower() + "@" for a in policy.builtin()["deploy_actions"])
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        stripped = line.strip().removeprefix("- ").strip()
        if ESCAPED_KEY.search(stripped):
            return n
        if "{" in stripped and FLOW_KEY.search(stripped) and not SIMPLE_FLOW.match(stripped.split(" #")[0].strip()):
            return n  # a flow map is read only when it is one plain pair of braces with no quote: else count it
        first = LINE_KEY.match(stripped)
        pairs = [(m.group(1), m.group(2).strip()) for m in [*([first] if first else []), *FLOW_KEY.finditer(stripped)]]
        if any(kind == "environment" for kind, _ in pairs):
            return n
        for kind, value in pairs:
            uses = re.match(r"""['"]?([^'"\s#]+)""", value) if kind == "uses" else None
            if uses and (uses.group(1).lower().startswith(actions) or "/.github/workflows/" in uses.group(1) or uses.group(1).startswith("./")):
                return n
        runs = [value for kind, value in pairs if kind == "run"]
        if (runs or n > 1) and names_a_deploy(stripped.split(" #")[0]):
            return n
        for value in runs:
            if value and not BLOCK_HEADER.match(value) and _continued(value, lines, n - 1):
                return n  # a value that runs on to the next lines, or a quote that never closes, is not read: count it
            body = [value.strip("'\"")] if not BLOCK_HEADER.match(value) and value else [x.strip() for x in block_under(lines, n - 1)]
            if any(a["action"] in DEPLOYING for cmd in body if cmd for a in risk.command_level(rs, cmd, cwd=None)["actions"]):
                return n
    return None


def _continued(value: str, lines: list[str], i: int) -> bool:
    """Whether a `run:` value on line `i` goes on past its line, which YAML allows and this reader does not follow: a quote
    it opens and never closes, by YAML's quoting rules, or a deeper line under it. A plain scalar goes on on any line indented
    past its key's column, whatever that line holds; a line at the key's column is the next key."""
    if value[0] in "'\"" and not _closes(value):
        return True
    line = lines[i]
    rest = line.lstrip()
    column = indent_of(line) + (len(rest) - len(rest[1:].lstrip()) if rest.startswith("-") else 0)
    below = next((x for x in lines[i + 1 :] if x.strip() and not x.lstrip().startswith("#")), "")
    return bool(below) and indent_of(below) > column


def _closes(value: str) -> bool:
    """Whether a quoted value ends on its line: the quote that opens it is closed, by YAML's rules (a backslash escapes in
    double quotes, `''` is a quote in single quotes), with nothing after it but spaces or a comment."""
    quote, k = value[0], 1
    while k < len(value):
        ch = value[k]
        if quote == '"' and ch == "\\":
            k += 2
            continue
        if ch == quote:
            if quote == "'" and value[k + 1 : k + 2] == "'":
                k += 2
                continue
            tail = value[k + 1 :].strip()
            return not tail or tail.startswith("#")
        k += 1
    return False


def deploying_workflows(rs: risk.RuleSet, tip: str, branch: str, cwd: str) -> list[str]:
    """Each workflow at the commit `tip` that deploys on a push to `branch`, as `path:line`; one that cannot be read, or that is a
    link, as `path (unreadable)`, because it may deploy."""
    found = []
    entries = git.run(["ls-tree", "-r", "-z", "--full-tree", tip, "--", WORKFLOWS[:-1]], cwd).split("\0")
    for entry in sorted(e for e in entries if e):
        meta, path = entry.split("\t", 1)
        if not path.endswith((".yml", ".yaml")) or meta.split()[1] != "blob":
            continue
        text = git.show(tip, path, cwd) if meta.split()[0] in ("100644", "100755") else None
        if text is None:
            found.append(f"{path} (unreadable)")
            continue
        line = deploy_line(text, rs) if workflow_triggers.push_reaches(text, branch) else None
        if line:
            found.append(f"{path}:{line}")
    return found
