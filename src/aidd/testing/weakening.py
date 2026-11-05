"""The moves that weaken a check, which `aidd test --changed` names as a note (R334): a new skip marker, a new
suppression comment, a deleted test file, a lowered or removed coverage floor, and a test file that loses assertions on
net with no test beside it that gains them (R351), from the merge base, untracked files included.

AGENTS.md says to never weaken a check to pass a test, and only review held that. This reads the diff for the common
moves, with the patterns as data (`schemas/weakening-moves.json`). Each counts only on net, so a marker moved within a
file, a renamed file, or a check made stricter says nothing. It is a note, never a failure: a person may skip a test
with a reason.

It is a net for the common shortcuts, not a control: a determined author can still hide a move, as from any check that
reads text, so a person's review stays the control, as SECURITY.md says of every command pattern.

A changed line is judged in its whole file, never in its hunk alone: whether it starts inside a string that spans lines
comes from the file at the base (a removed line) or now (an added one), so an edit far away never hides a marker.

Where the reading is unsure, it fails closed toward a note: an unclear line counts a marker, and a removed assertion,
but never an added assertion, so an unclear line hides no loss.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from aidd.kernel import documents, git, globs, resources

# The most of one file it reads, whole or untracked: a test or a config is small, so a larger file is no check.
MAX_FILE_BYTES = 256 * 1024
# The most of a line it reads at each end, and the most of one file's diff: a crafted line or a vast file never costs
# much. A longer line keeps its start and its end, so padding hides neither a leading marker nor a trailing comment,
# and a file cut short says so; the cap is each file's, so one vast file never hides another.
MAX_LINE_CHARS = 64 * 1024
MAX_FILE_DIFF_CHARS = 1024 * 1024
# git's own settings never change the headers it reads: the prefixes stay `a/` and `b/`, and a path stays as it is.
_DIFF = ["-c", "core.quotepath=off", "diff", "-U0", "--no-color", "--no-ext-diff", "-M", "--src-prefix=a/", "--dst-prefix=b/"]
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# The strings that span lines: a fixture inside one holds a test file's text, never code.
_SPANNING = ('"""', "'''", "`")
_SECTION = re.compile(r"^\s*\[{1,2}([^\]\n]{1,200})\]{1,2}\s*$")

Lines = list[tuple[int, str]]  # (the line's number in its file, its text)
# A renamed file's path at the base, by its path now, from the last diff read: the base is read where the file was.
RENAMED: dict[str, str] = {}


def _moves() -> dict:
    return resources.load_json("weakening-moves.json")


def _lines(text: str) -> list[str]:
    """`text` split into lines the way git numbers them: at each newline, a trailing carriage return dropped. Never
    `str.splitlines`, which also breaks at a form feed or U+2028, so a line's number would differ from git's."""
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return [x[:-1] if x.endswith("\r") else x for x in parts]


def _bounded(line: str) -> str:
    """A line as it is read: whole when short; else its start and its end, joined by a newline, which no pattern
    crosses."""
    return line if len(line) <= 2 * MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + "\n" + line[-MAX_LINE_CHARS:]


def _path(header: str) -> str | None:
    """The path a `+++ ` header names, or None for `/dev/null` or a name git quoted, which it never decodes."""
    name = header[4:].split("\t", 1)[0]
    return name[2:] if name.startswith("b/") else None


def _untracked(repo: str) -> list[str]:
    return [p for p in git.run(["-c", "core.quotepath=off", "ls-files", "-z", "--others", "--exclude-standard"], repo, check=False).split("\0") if p]


def _small(repo: str, rel: str) -> bool:
    f = Path(repo) / rel
    return f.is_file() and not f.is_symlink() and f.stat().st_size <= MAX_FILE_BYTES


def _diff_lines(repo: str, base_sha: str) -> tuple[dict[str, tuple[Lines, Lines]], list[str]]:
    """Per file, (the lines added, numbered in the file now; the lines removed, numbered in the file at the base), an
    untracked file all added; and the files whose diff passed MAX_FILE_DIFF_CHARS, so the rest of each went unread.
    Headers are read only between `diff --git` and the first hunk, so a line of content never reads as one."""
    out: dict[str, tuple[Lines, Lines]] = {}
    RENAMED.clear()
    read: dict[str, int] = {}
    cut: list[str] = []
    path, in_header, old_no, new_no, renamed_from = None, False, 0, 0, ""
    for line in _lines(git.run([*_DIFF, base_sha, "--"], repo, check=False)):
        if line.startswith("diff --git "):
            path, in_header, renamed_from = None, True, ""
        elif in_header and line.startswith("rename from "):
            renamed_from = line[len("rename from ") :]
        elif in_header and line.startswith("+++ "):
            path = _path(line)
            if path is not None:
                out.setdefault(path, ([], []))
                if renamed_from:
                    RENAMED[path] = renamed_from
        elif m := _HUNK.match(line):
            in_header, old_no, new_no = False, int(m.group(1)), int(m.group(2))
        elif in_header or path is None:
            continue
        elif read.get(path, 0) > MAX_FILE_DIFF_CHARS:
            if path not in cut:
                cut.append(path)
        elif line[:1] == "+":
            read[path] = read.get(path, 0) + len(line)
            out[path][0].append((new_no, _bounded(line[1:])))
            new_no += 1
        elif line[:1] == "-":
            read[path] = read.get(path, 0) + len(line)
            out[path][1].append((old_no, _bounded(line[1:])))
            old_no += 1
    for rel in _untracked(repo):
        if _small(repo, rel):
            text = (Path(repo) / rel).read_text(encoding="utf-8", errors="replace")
            out[rel] = ([(i, _bounded(x)) for i, x in enumerate(_lines(text), 1)], [])
    return out, cut


def _whole(repo: str, base_sha: str, path: str) -> tuple[list[str], list[str]]:
    """The file's lines at the base and now, each empty when the file is not there, each read to MAX_FILE_BYTES."""
    old = git.run(["show", f"{base_sha}:{RENAMED.get(path, path)}"], repo, check=False)[:MAX_FILE_BYTES]
    new = (Path(repo) / path).read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES] if _small(repo, path) else ""
    return _lines(old), _lines(new)


def _code_mask(line: str, unsure: int = 1, comment: int = 1) -> bytearray:
    """For each position of `line`, 1 when it sits outside a string literal, read once, left to right, with each
    quote's escapes. A comment (`#`, `//`, or `/* ... */`) outside a string is `comment`: 1 for a marker, which lives
    in one, and 0 for an assertion, which a comment turns off; a quote in it opens nothing. A line whose quotes do not
    balance is unclear, so every position is `unsure`: 1 fails closed for a marker or a removed assertion, and 0 for an
    added assertion."""
    mask, quote, i, n = bytearray(len(line)), "", 0, len(line)
    while i < n:
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch == "#" or line.startswith("//", i):
            mask[i:] = bytes([comment]) * (n - i)
            return mask
        elif line.startswith("/*", i):
            end = line.find("*/", i + 2)
            stop = n if end < 0 else end + 2
            mask[i:stop] = bytes([comment]) * (stop - i)
            i = stop
            continue
        else:
            mask[i] = 1
        i += 1
    return bytearray(bytes([unsure]) * n) if quote else mask


def _in_spanning_strings(lines: list[str], skip_when_unsure: bool = False) -> set[int]:
    """The numbers (from 1) of the lines that start inside a string that spans lines, read with the same left-to-right
    scanner as `_code_mask`, so a `\"\"\"` inside a one-line string or a comment opens nothing. When the reading
    ends inside such a string it is unsure, so it fails closed: no line is left out, or, for an added assertion
    (`skip_when_unsure`), every line is."""
    inside, open_ = set(), ""
    for no, x in enumerate(lines, 1):
        if open_:
            inside.add(no)
        quote, i = "", 0
        while i < len(x):
            if open_:
                if x[i] == "\\":
                    i += 2
                    continue
                if x.startswith(open_, i):
                    i, open_ = i + len(open_), ""
                    continue
            elif quote:
                if x[i] == "\\":
                    i += 1
                elif x[i] == quote:
                    quote = ""
            elif spans := next((s for s in _SPANNING if x.startswith(s, i)), ""):
                i, open_ = i + len(spans), spans
                continue
            elif x[i] in "\"'":
                quote = x[i]
            elif x[i] == "#" or x.startswith("//", i):
                break
            elif x.startswith("/*", i):
                end = x.find("*/", i + 2)
                if end < 0:
                    break
                i = end + 2
                continue
            i += 1
    if open_:
        return set(range(1, len(lines) + 1)) if skip_when_unsure else set()
    return inside


def _count(rxs: list[re.Pattern[str]], lines: Lines, inside: set[int], unsure: int = 1, comment: int = 1) -> int:
    """How many places in `lines` one of `rxs` matches, outside a string, on a line that starts outside a string that
    spans lines, with `_code_mask`'s `unsure` and `comment`. A place two patterns match counts once."""
    total = 0
    for no, x in lines:
        if no in inside:
            continue
        for part in x.split("\n"):
            starts = {m.start() for rx in rxs for m in rx.finditer(part)}
            if starts:
                mask = _code_mask(part, unsure, comment)
                total += sum(mask[i] for i in starts)
    return total


def _marker_notes(moves: dict, shown: str, added: Lines, removed: Lines, whole: tuple[list[str], list[str]]) -> list[str]:
    old_inside, new_inside = _in_spanning_strings(whole[0]), _in_spanning_strings(whole[1])
    notes = []
    for kind, key in (("a skip marker", "skip_markers"), ("a suppression comment", "suppressions")):
        for entry in moves[key]:
            rx = [re.compile(entry["regex"])]
            if _count(rx, added, new_inside) > _count(rx, removed, old_inside):
                notes.append(f"{shown} adds {kind} ({entry['name']}): a check runs less; if a person agreed, say why beside it")
    return notes


def _assertions_lost(rxs: list[re.Pattern[str]], added: Lines, removed: Lines, whole: tuple[list[str], list[str]]) -> int:
    """How many assertions a test file loses on net, each line judged in its whole file, never in a comment. A removed
    line counts when unsure and an added one never does. A line the change keeps counts as lost when the change puts it
    inside a string that spans lines, as a test wrapped in a docstring is; never the other way, so nothing unclear hides
    a loss."""
    old, new = whole
    old_inside, new_inside = _in_spanning_strings(old), _in_spanning_strings(new)
    lost = _count(rxs, removed, old_inside, comment=0)
    lost -= _count(rxs, added, _in_spanning_strings(new, skip_when_unsure=True), unsure=0, comment=0)
    gone, here = {no for no, _ in removed}, {no for no, _ in added}
    kept = zip((no for no in range(1, len(old) + 1) if no not in gone), (no for no in range(1, len(new) + 1) if no not in here), strict=False)
    wrapped = [(a, _bounded(old[a - 1])) for a, b in kept if a not in old_inside and b in new_inside]
    return lost + _count(rxs, wrapped, set(), comment=0)


def _assertion_notes(lost: dict[str, int]) -> list[str]:
    """Each test file that loses assertions on net, unless the test files beside it, in the same folder, gain as many:
    a test moved to a file beside it loses nothing."""
    by_folder: dict[PurePosixPath, int] = {}
    for path, n in lost.items():
        by_folder[PurePosixPath(path).parent] = by_folder.get(PurePosixPath(path).parent, 0) + n
    return [
        f"{documents.one_line(path, 200)} loses {n} assertion{'s' if n > 1 else ''} on net, with no test beside it that gains them: "
        "say what proves that behavior now, or keep them"
        for path, n in sorted(lost.items())
        if n > 0 and by_folder[PurePosixPath(path).parent] > 0
    ]


def _floors(rules: list[dict], path: str, lines: list[str]) -> dict[tuple[str, str], list[float]]:
    """Each coverage floor in `lines`, by (the `[section]` above it, its key), in the order they appear."""
    found: dict[tuple[str, str], list[float]] = {}
    for rule in rules:
        if rule["files"] is not None and not globs.match_any(rule["files"], path):
            continue
        rx, section = re.compile(rule["regex"]), ""
        for x in lines:
            if m := _SECTION.match(x):
                section = m.group(1).strip()
            for part in _bounded(x).split("\n"):
                for f in rx.finditer(part):
                    found.setdefault((section, f["key"]), []).append(float(f["n"]))
    return found


def _floor_notes(path: str, was: dict[tuple[str, str], list[float]], now: dict[tuple[str, str], list[float]]) -> list[str]:
    """A floor the change takes out, or lowers, each compared with its own section's: a reordered file hides nothing.
    Within one section, floors pair in the order they appear, and the lowest floor of a key never drops."""
    notes = []
    for (section, key), old in was.items():
        new = now.get((section, key), [])
        where = f" in [{section}]" if section else ""
        if len(new) < len(old):
            notes.append(f"{path} removes the coverage floor {key}{where}: coverage only rises")
            continue
        lowered = [(a, b) for a, b in zip(old, new, strict=False) if b < a]
        if not lowered and min(new) < min(old):
            lowered = [(min(old), min(new))]
        notes += [f"{path} lowers the coverage floor {key}{where} from {a:g} to {b:g}: coverage only rises" for a, b in lowered]
    # A floor set to 0 where there was none, such as `--cov-fail-under=0` in a Makefile, turns another floor off.
    notes += [f"{path} sets the coverage floor {key} to 0: coverage only rises" for (sec, key), new in now.items() if (sec, key) not in was and 0 in new]
    return notes


def _moved(repo: str, base_sha: str, deleted_tests: list[str]) -> set[str]:
    """The deleted test files, and the untracked test files, of each pair that holds the same content: a test moved
    with `mv` and not yet added, which git reads as a deletion and a new file. A test moved out of the test paths no
    longer runs, so its deletion note stays. One `git cat-file` reads every deleted file's blob."""
    if not deleted_tests:
        return set()
    tests = _moves()["test_files"]
    small = [p for p in _untracked(repo) if "\n" not in p and globs.match_any(tests, p) and _small(repo, p)]
    if not small:
        return set()
    shas = git.run(["hash-object", "--stdin-paths"], repo, input="".join(f"{p}\n" for p in small), check=False).split()
    by_sha = dict(zip(shas, small, strict=False))
    named = [d for d in deleted_tests if "\n" not in d]
    was = git.run(["cat-file", "--batch-check=%(objectname)"], repo, input="".join(f"{base_sha}:{d}\n" for d in named), check=False).split("\n")
    # A move counts only to a name that still runs as a test: the same suffix, on a test path.
    return {p for d, sha in zip(named, was, strict=False) if sha in by_sha and Path(by_sha[sha]).suffix == Path(d).suffix for p in (d, by_sha[sha])}


def weakening_notes(repo: str, base_sha: str) -> list[str]:
    """One note for each move that weakens a check, each naming the file and what to do."""
    moves = _moves()
    code = tuple(moves["code_suffixes"])
    deleted = git.run(["-c", "core.quotepath=off", "diff", "--name-only", "-M", "--diff-filter=D", "-z", base_sha, "--"], repo, check=False).split("\0")
    deleted_tests = [p for p in deleted if p and globs.match_any(moves["test_files"], p)]
    moved = _moved(repo, base_sha, deleted_tests)
    lines, cut = _diff_lines(repo, base_sha)
    notes = [
        f"{documents.one_line(p, 200)} changes more than {MAX_FILE_DIFF_CHARS // (1024 * 1024)} MiB, so only its start was read; review the rest by hand"
        for p in cut
    ]
    patterns = [re.compile(e["regex"]) for key in ("skip_markers", "suppressions") for e in moves[key]]
    assertions = [re.compile(e["regex"]) for e in moves["assertions"]]
    lost: dict[str, int] = {}
    for path, (added, removed) in sorted(lines.items()):
        if path in moved:
            continue
        shown = documents.one_line(path, 200)
        texts = [x for _, x in added + removed]
        marked = path.endswith(code) and any(rx.search(part) for rx in patterns for x in texts for part in x.split("\n"))
        # A file cut short has its own note, so its partial count neither names it nor offsets a loss beside it.
        asserted = path.endswith(code) and path not in cut and globs.match_any(moves["test_files"], path)
        asserted = asserted and (any(s in x for s in _SPANNING for x in texts) or any(rx.search(p) for rx in assertions for x in texts for p in x.split("\n")))
        floored = bool(_floors(moves["coverage_floors"], path, texts))
        if not (marked or asserted or floored):
            continue
        whole = _whole(repo, base_sha, path)  # read only for a file whose change touches a marker, an assertion, or a floor
        if marked:
            notes += _marker_notes(moves, shown, added, removed, whole)
        if asserted:
            lost[path] = _assertions_lost(assertions, added, removed, whole)
        if floored:
            notes += _floor_notes(shown, _floors(moves["coverage_floors"], path, whole[0]), _floors(moves["coverage_floors"], path, whole[1]))
    notes += _assertion_notes(lost)
    notes += [f"{documents.one_line(p, 200)} is a test file, deleted: say what proves its behavior now, or keep it" for p in deleted_tests if p not in moved]
    for p in (d for d in deleted if d and d not in lines):  # a deleted config takes its floors with it
        old = _lines(git.run(["show", f"{base_sha}:{p}"], repo, check=False)[:MAX_FILE_BYTES])
        notes += _floor_notes(documents.one_line(p, 200), _floors(moves["coverage_floors"], p, old), {})
    return [f"a change may weaken a check: {n}" for n in notes]
