"""Which actions a simple command is by the files it reads: a reader that an action's `file_reads` names, such as `cat`, on a path in
the action's area (`cat .env`)."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from aidd.kernel import globs
from aidd.risk.rules import RuleSet
from aidd.risk.shell import SETTING, shell_words

# The readers whose first word is a pattern or a script, never a file, unless an option gives it instead: `-e` or `-f`, in a
# run of short flags too (`-ie x`), or `--regexp`, `--expression`, or `--file`, also with `=`. `-f` and `--file` read a file.
_PATTERN_FIRST = {"grep", "rg", "sed", "awk"}
_PATTERN_LONG = {"--regexp", "--expression", "--file"}
# The flags each of them takes with no value, which aidd fully understands. Any other option keeps the first word.
_PATTERN_FLAGS = {"grep": "abcEFGhHiIlLnoqrRsUvVwxzZ", "rg": "aceFhHiIlLnNopPqsSuUvwxz", "sed": "Einrsuz", "awk": ""}
_PATTERN_FLAGS_LONG = {
    "--count",
    "--extended-regexp",
    "--files-with-matches",
    "--fixed-strings",
    "--ignore-case",
    "--invert-match",
    "--line-number",
    "--quiet",
    "--recursive",
    "--word-regexp",
}


def _pattern_option(program: str, word: str, rest: list[str]) -> tuple[bool, list[str], bool]:
    """One option of a grep-like reader: whether it gives the pattern, the files it reads, and whether aidd fully
    understands it. It takes its value from `rest` when none is attached."""
    if word.startswith("--"):
        name, eq, value = word.partition("=")
        if name in _PATTERN_LONG:
            value = value if eq else (rest.pop(0) if rest else "")
            return True, [value] if name == "--file" else [], True
        return False, [], not eq and word in _PATTERN_FLAGS_LONG
    for pos, char in enumerate(word[1:], 1):
        if char in "ef":
            value = word[pos + 1 :] or (rest.pop(0) if rest else "")
            return True, [value] if char == "f" else [], True
        if char not in _PATTERN_FLAGS[program]:
            return False, [], False
    return False, [], True


def read_paths_of(program: str, words: Sequence[tuple[str, bool]]) -> list[str]:
    """The words of a reader's command that name a file it reads: a word that is no option, no target of an output
    redirection, and no pattern of a grep-like reader, the file after an input redirection, and a file `-f` gives. For
    `cp`, never its last word, the file it writes. A grep-like reader's first word stays when an option it has gives the
    pattern, or when aidd does not fully understand one of its options. `words` are those after the program, as
    `shell_words` gives them."""
    queue = deque(words)  # so a line of many options costs time in its length, never its square
    reads: list[str] = []
    positional: list[str] = []
    pattern_given, understood, options_done = False, True, False
    while queue:
        word, operator = queue.popleft()
        target = queue.popleft()[0] if operator and queue and not queue[0][1] else ""
        if operator:
            reads += [target] if word.lstrip("0123456789") in ("<", "<>") else []  # the shell opens it for the reader
        elif options_done or word == "-" or not word.startswith("-"):
            positional.append(word)
        elif word == "--":
            options_done = True
        elif program in _PATTERN_FIRST:
            rest = [queue[0][0]] if queue else []  # an option takes at most the next word as its value
            given, files, known = _pattern_option(program, word, rest)
            if queue and not rest:
                queue.popleft()
            pattern_given, understood = pattern_given or given, understood and known
            reads += files
    if program in _PATTERN_FIRST and not pattern_given and understood:
        positional = positional[1:]
    return reads + (positional[:-1] if program == "cp" else positional)


def file_read_actions(rs: RuleSet, call: str) -> list[str]:
    """The actions whose `file_reads` a simple command, as typed, is: its program is one of the readers, and a file it
    reads (`read_paths_of`) matches one of the action's `paths` and none of its `exclude`, unless one of its `include`. Case is ignored, as for an
    area."""
    words = shell_words(call)
    words = words[next((i for i, (w, op) in enumerate(words) if op or not SETTING.fullmatch(w)), len(words)) :]
    if not words:
        return []
    program = words[0][0].rsplit("/", 1)[-1]
    out = []
    for action, spec in rs.actions.items():
        reads = spec.get("file_reads") or {}
        if program not in reads.get("readers", []):
            continue
        paths, exclude, include = reads.get("paths", []), reads.get("exclude", []), reads.get("include", [])
        files = read_paths_of(program, words[1:])
        kept = [p for p in files if globs.match_any(include, p, fold_case=True) or not globs.match_any(exclude, p, fold_case=True)]
        if any(globs.match_any(paths, p, fold_case=True) for p in kept):
            out.append(action)
    return out
