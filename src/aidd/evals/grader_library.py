"""The shared graders of the live suites: one library file for each grader that more than one case holds.

`claude plugin eval` reads a case's own `graders/` folder and has no include, so a shared grader must be a file in each case.
`evals/library/graders.json` names each shared grader by its purpose and lists the cases that hold a copy, with the file name the
case gives it. `evals/library/graders/<name>.md` is the one text. This module checks every copy against it and writes the copies,
so a fix to a grader is made once and `python3 -m aidd.evals.grader_library` carries it into every case. A grader that two
cases hold alike and the library lacks is a drift risk, so the checker names it. The shape is schemas/eval-grader-library.schema.json.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from aidd.evals import trigger_cases
from aidd.kernel import regular_files

LIBRARY = "evals/library"
INDEX = f"{LIBRARY}/graders.json"
SUITES = ("plugin", "team")


def case_graders(root: Path) -> dict[str, str]:
    """Every grader file of the hand-written cases as `<suite>/<case>/<stem>` and its text. The trigger cases are written from
    triggers.json, so their graders have one owner already."""
    found = {}
    for suite in SUITES:
        for path in sorted((root / "evals" / suite).glob("*/graders/*.md")):
            case = path.parent.parent.name
            if not (suite == "team" and case.startswith(trigger_cases.PREFIXES)):
                found[f"{suite}/{case}/{path.stem}"] = path.read_text(encoding="utf-8")
    return found


def read_index(root: Path) -> dict:
    return json.loads((root / INDEX).read_text(encoding="utf-8"))


def library_text(root: Path, name: str) -> str:
    return (root / LIBRARY / "graders" / f"{name}.md").read_text(encoding="utf-8")


def problems(root: Path) -> list[str]:
    """Each way the cases and the library disagree: a copy that differs from its library file, a use whose case has no such grader,
    a library file nothing uses, and two cases that hold one grader alike with no library entry."""
    index, found = read_index(root), case_graders(root)
    out: list[str] = []
    claimed: set[str] = set()
    for name, entry in index["graders"].items():
        path = root / LIBRARY / "graders" / f"{name}.md"
        if not path.is_file():
            out.append(f"{name}: no library file {path.relative_to(root).as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        if len(entry["uses"]) < 2:
            out.append(f"{name}: a shared grader has at least two uses")
        for use in entry["uses"]:
            claimed.add(use)
            if use not in found:
                out.append(f"{name}: {use} is no grader of a case")
            elif found[use] != text:
                out.append(f"{name}: {use} differs from the library file: run `python3 -m aidd.evals.grader_library`, or edit the library file and run it")
    listed = {p.stem for p in (root / LIBRARY / "graders").glob("*.md")}
    out += [f"{name}: a library file no entry names" for name in sorted(listed - set(index["graders"]))]
    alike: dict[str, list[str]] = collections.defaultdict(list)
    for use, text in found.items():
        if use not in claimed:
            alike[text].append(use)
    out += [f"{' and '.join(uses)} hold one grader alike: add it to {INDEX}" for uses in alike.values() if len(uses) > 1]
    return out


def write_copies(root: Path) -> list[str]:
    """Write every use from its library file, and return the paths it changed."""
    changed = []
    for name, entry in read_index(root)["graders"].items():
        text = library_text(root, name)
        for use in entry["uses"]:
            suite, case, stem = use.split("/")
            rel = f"evals/{suite}/{case}/graders/{stem}.md"
            if regular_files.repository_text(root, rel) != text:
                regular_files.write_text_safely(root, rel, text)
                changed.append(rel)
    return changed


def adopt(root: Path) -> dict:
    """The index of every grader that two or more cases hold alike, named by its commonest file stem, for a maintainer to review
    and save. A stem two groups share gets the first case's name after it."""
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for use, text in case_graders(root).items():
        groups[text].append(use)
    graders: dict[str, dict] = {}
    for uses in sorted(groups.values(), key=lambda u: u[0]):
        if len(uses) < 2:
            continue
        stems = collections.Counter(u.rsplit("/", 1)[1] for u in uses)
        name = sorted(stems, key=lambda s: (-stems[s], s))[0]
        if name in graders:
            name = f"{name}--{uses[0].split('/')[1]}"
        graders[name] = {"uses": uses}
    return {"graders": dict(sorted(graders.items()))}


def main(argv: list[str] | None = None) -> int:
    """Write the copies into the cases of the checkout this aidd runs from (or the folder given); `--check` writes nothing and fails on a problem."""
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    rest = [a for a in args if a != "--check"]
    root = Path(rest[0]) if rest else Path(__file__).resolve().parents[3]
    if not (root / INDEX).is_file():
        print(f"no {INDEX} under {root}: run this from aidd's source checkout, or name it", file=sys.stderr)
        return 2
    if check:
        found = problems(root)
        print("\n".join(found) if found else "the shared graders match the library")
        return 1 if found else 0
    changed = write_copies(root)
    print("\n".join(f"wrote: {c}" for c in changed) if changed else "the shared graders are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
