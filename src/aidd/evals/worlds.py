"""The worlds a live eval case's project is set in, and the shares that no one world, language, or domain may pass.

`evals/worlds.json` lists the worlds: each is a programming language and a business domain, with a small project that its
`seed` script builds. A live case, which builds its project with its own `fixture.sh`, names its world as a `world:<name>` tag
beside its `claim:`, `tier:`, and `shape:` tags. A routing, roles, or trigger case builds no project, so it names none.

The file holds `cap`, the most of the live cases any one world, language, or domain may have, so the cases cannot all be set in
the one world their author knew. `over_cap` lists the shares that are over it today, each with its case count, and a count may
only fall. Nothing here runs an agent.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from aidd.evals import claims, trigger_cases

WORLDS_FILE = "evals/worlds.json"
AXES = ("world", "language", "domain")
# The language `none` is a project with no source file, and the domain `general` is a project about no business. Both are values of
# the shares like any other, so the cap holds for them. The tests leave them out when they count how many languages and domains differ.
NO_LANGUAGE = "none"
NO_DOMAIN = "general"


def worlds_file(root: Path) -> dict:
    """evals/worlds.json: `cap`, `languages` (each with its file markers), `worlds`, and `over_cap`."""
    return trigger_cases.read_json(root, WORLDS_FILE)


def case_worlds(root: Path) -> list[dict]:
    """Every live case as `{suite, id, worlds}`: a plugin or team case that builds its project with its own `fixture.sh`. `worlds` is
    the list of the worlds it names, which is empty for a case that names none and holds more than one for a case that names several."""
    rows = []
    for row in claims.suite_cases(root):
        if row["suite"] not in ("plugin", "team") or (row["suite"] == "team" and row["id"].startswith(trigger_cases.PREFIXES)):
            continue
        if (root / claims.SUITES[row["suite"]] / row["id"] / "fixture.sh").is_file():
            named = [t.removeprefix("world:") for t in row["tags"] if t.startswith("world:")]
            rows.append({"suite": row["suite"], "id": row["id"], "worlds": named})
    return rows


def one_world(row: dict) -> str:
    """The world a live case names, or "" when it names none or more than one."""
    return row["worlds"][0] if len(row["worlds"]) == 1 else ""


def definition_problems(root: Path, file: dict) -> list[str]:
    """Each world that is not named by its language and domain, names a language the file lacks, or has no seed script."""
    out = []
    for name, world in file["worlds"].items():
        if world["language"] not in file["languages"]:
            out.append(f"world {name}: its language {world['language']!r} is not one of {', '.join(file['languages'])}")
        if name != f"{world['language']}-{world['domain']}":
            out.append(f"world {name}: name it {world['language']}-{world['domain']}, its language and its domain")
        if not (root / world["seed"]).is_file():
            out.append(f"world {name}: its seed {world['seed']} is not a file")
    return out


def naming_problems(rows: list[dict], file: dict) -> list[str]:
    """Each live case that names no world, more than one, or one the file lacks."""
    out = []
    for row in rows:
        where = f"{row['suite']}/{row['id']}"
        if not row["worlds"]:
            out.append(f"{where}: name its project's world as a `world:<name>` tag ({WORLDS_FILE})")
        elif len(row["worlds"]) > 1:
            out.append(f"{where}: it names {len(row['worlds'])} worlds; a case shows one project, so keep one `world:` tag")
        elif row["worlds"][0] not in file["worlds"]:
            out.append(f"{where}: its world {row['worlds'][0]!r} is not one of {', '.join(file['worlds'])}")
    return out


def share_counts(rows: list[dict], file: dict) -> dict[str, Counter]:
    """For each axis (world, language, domain), how many live cases are set in each of its values, `none` and `general` included.
    A case that names no known world counts nowhere."""
    counts: dict[str, Counter] = {axis: Counter() for axis in AXES}
    for row in rows:
        world = file["worlds"].get(one_world(row))
        if world is None:
            continue
        counts["world"][one_world(row)] += 1
        counts["language"][world["language"]] += 1
        counts["domain"][world["domain"]] += 1
    return counts


def cap_text(cap: float) -> str:
    """The cap as a percentage with no trailing zeros: 0.4 is "40%"."""
    return f"{cap * 100:g}%"


def share_problems(rows: list[dict], file: dict) -> list[str]:
    """Each world, language, or domain over `cap` of the live cases that `over_cap` does not list, and each `over_cap` row whose count
    is no longer the real one. A count may only fall: when it rises, the next step is to move cases to another world, and when it
    fell, the next step is to lower the recorded count. A row goes once its count is under the cap."""
    total, cap = len(rows), file["cap"]
    cap_percent = cap_text(cap)
    counts = share_counts(rows, file)
    out = []
    for axis in AXES:
        listed = file["over_cap"][axis]
        for value, found in sorted(counts[axis].items()):
            if found > cap * total and value not in listed:
                out.append(
                    f"{axis} {value} is in {found} of {total} live cases, over the cap of {cap_percent}: move cases to another world until it is under the cap, because `over_cap` takes no new row"
                )
        for value, count in listed.items():
            found = counts[axis][value]
            if found <= cap * total:
                out.append(f"{axis} {value} is in {found} of {total} live cases, under the cap of {cap_percent}: remove it from `over_cap`")
            elif found > count:
                out.append(
                    f"{axis} {value} is in {found} live cases, and `over_cap` says {count}: move cases to another world, because this count may only fall"
                )
            elif found < count:
                out.append(
                    f"{axis} {value} is in {found} live cases, and `over_cap` says {count}: cases moved, so lower the count to {found}, the one edit it takes"
                )
    return out


def world_problems(root: Path, rows: list[dict], file: dict) -> list[str]:
    """Every problem of the worlds, the live cases' names for them, and the shares: what `aidd gen-docs` refuses to print a table over."""
    return [*definition_problems(root, file), *naming_problems(rows, file), *share_problems(rows, file)]


def world_coverage_table(rows: list[dict], file: dict) -> str:
    """The worlds as a Markdown table, each with its language, its domain, and its share of the live cases, then each share over `cap`.
    A share shows one decimal, because 40.3% is over a cap of 40% and "40%" would hide it."""
    total, cap = len(rows), file["cap"]
    cap_percent = cap_text(cap)
    cases = Counter(one_world(row) for row in rows)
    lines = ["| World | Language | Domain | Live cases | Share |", "| --- | --- | --- | --- | --- |"]
    for name, world in file["worlds"].items():
        lines.append(f"| `{name}` | {world['language']} | {world['domain']} | {cases[name]} | {cases[name] / total:.1%} |")
    over = [
        f"- `{value}` ({axis}): {found} of {total} live cases, {found / total:.1%}"
        for axis, counter in share_counts(rows, file).items()
        for value, found in sorted(counter.items())
        if found > cap * total
    ]
    lines += ["", f"Over the cap of {cap_percent}, each a share to cut:" if over else f"No world, language, or domain is over the cap of {cap_percent}.", ""]
    return "\n".join([*lines, *over]).rstrip("\n")
