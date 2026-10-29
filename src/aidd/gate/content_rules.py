"""Risk rules that read what a diff adds (`risk_rules[].content`): what the code does, wherever it sits. The adapter
reads the added lines with git and puts the matches in the context (`content_matches`); the gate only reads them.
What the adapter cannot read counts as a match, never as none: a reviewer is asked rather than skipped."""

from __future__ import annotations

import re
from collections.abc import Callable

from aidd.kernel import git, globs

# The files a diff may have under content rules, and the characters a line may hold, that the adapter still reads.
# Beyond either, the rule counts as matched (fail closed).
MAX_FILES = 500
MAX_LINE = 100_000


def rules(active: list[dict]) -> list[dict]:
    """Of the active rules (routing.active_rules), those that name `content`, each with its patterns compiled (the
    config's load already refused one that does not compile)."""
    return [dict(r, compiled=[re.compile(p) for p in r["content"]]) for r in active if r.get("content")]


def _wanted(active: list[dict], path: str) -> list[dict]:
    """The content rules that read `path`: its `paths` match it (any file without `paths`) and its `exclude` does not.
    Path matching ignores case, as the path rules do."""
    return [
        r
        for r in active
        if (not r.get("paths") or globs.match_any(r["paths"], path, fold_case=True)) and not globs.match_any(r.get("exclude", []), path, fold_case=True)
    ]


def _segments(line: str) -> list[str]:
    """A line, and each part of it another language would read as its own line (a bare carriage return, a form
    feed, U+2028, U+2029, ...): a pattern anchored with `^` or `$` matches either way."""
    parts = line.splitlines()
    return [line, *parts] if len(parts) > 1 else [line]


def matches(active: list[dict], paths: list[str], added: Callable[[str], list[str] | None]) -> list[dict]:
    """One {rule, path} for each rule and file where a line `added(path)` returns matches one of the rule's patterns.
    The adapter never reports "no match" for what it did not read, so each of these counts as a match: a file
    `added` could not read (None), a line longer than MAX_LINE, and every rule of a file past the first MAX_FILES
    files some content rule reads."""
    out: list[dict] = []
    relevant = [(path, wanted) for path in paths if (wanted := _wanted(active, path))]
    for path, wanted in relevant[:MAX_FILES]:
        lines = added(path)
        if lines is None:
            out += [{"rule": r["name"], "path": path} for r in wanted]
            continue
        texts = [s for line in lines for s in _segments(line)]
        out += [{"rule": r["name"], "path": path} for r in wanted if any(len(t) > MAX_LINE or p.search(t) for p in r["compiled"] for t in texts)]
    unread = {r["name"]: path for path, wanted in relevant[MAX_FILES:] for r in wanted}
    out += [{"rule": name, "path": path} for name, path in unread.items() if {"rule": name, "path": path} not in out]
    return out


def added_lines(cwd: str, base_sha: str, head: str | None, path: str) -> list[str]:
    """The lines the diff adds to `path`, from `base_sha` to `head` (None: the working tree), split on newlines only,
    as git wrote them (matches() also reads each part another language would split off). The path is literal, never a
    pathspec: a file named `*.py` or `:(exclude)x` names only itself. A git error raises, so the context build fails
    rather than report no match."""
    span = [base_sha, head] if head else [base_sha]
    text = git.run(["--literal-pathspecs", "diff", "--no-color", "--no-ext-diff", "--unified=0", *span, "--", path], cwd, raw=True)
    out, in_hunk = [], False
    for line in text.split("\n"):
        if line.startswith("@@"):
            in_hunk = True  # the file's header (`+++ b/<path>`) comes before its first hunk
        elif in_hunk and line.startswith("+"):
            out.append(line[1:].removesuffix("\r"))
    return out
