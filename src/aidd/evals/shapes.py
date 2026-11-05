"""The project-shape matrix: the project shape each eval case and core fixture shows, and the pairs no case shows.

`evals/shapes.json` holds four axes: the project's type, its stage, its team, and its regulation. A project shape is one value of
each, as `type/stage/team/regulation`, and a type of `any` says the case holds whatever the project builds. A routing or roles case
holds its project shape as `shape`; a plugin or team case holds a `shape:<shape>` tag, beside its `claim:` and `tier:` tags; and a
trigger case, which triggers.json writes, holds `shape` there, beside its prompt. Nothing here runs an agent.

The coverage table counts each type against each value of the other three axes. That is pairwise coverage, a standard way to
cover several axes with few cases, so the report asks for a case where two axes meet, never one for each of every combination.
"""

from __future__ import annotations

import json
from pathlib import Path

from aidd.evals import claims, suites, trigger_cases
from aidd.kernel import regular_files

SHAPES_FILE = "evals/shapes.json"
AXES = ("type", "stage", "team", "regulation")
ANY = "any"
FIXTURES = "tests/fixtures"


def shapes_file(root: Path) -> dict:
    """evals/shapes.json: `axes` (each axis's values and what each means), `concerns`, `fixtures`, and `not_project_shaped`."""
    return trigger_cases.read_json(root, SHAPES_FILE)


def _trigger_shapes(root: Path) -> dict[str, str]:
    """Each trigger case's project shape, from triggers.json, by the case's name."""
    rel = f"{claims.SUITES['team']}/triggers.json"
    text = regular_files.repository_text(root, rel)
    if text is None:
        return {}
    data = json.loads(text)
    return {str(c["name"]): str(c.get("shape", "")) for entry in data.get("skills", {}).values() for c in entry.get("cases", [])}


def case_shapes(root: Path) -> list[dict]:
    """Every case of the four suites as `{suite, id, shape}`. `shape` is "" for a case that names none, and the shapes joined by a
    space for a case that names more than one."""
    rows = []
    for suite in ("routing", "roles"):
        rows += [{"suite": suite, "id": str(sc["id"]), "shape": str(sc.get("shape") or "")} for sc in suites.load_scenarios(root / claims.SUITES[suite])]
    triggers = _trigger_shapes(root)
    for row in claims.suite_cases(root):
        if row["suite"] not in ("plugin", "team"):
            continue
        if row["id"] in triggers:
            shape = triggers[row["id"]]
        else:
            shapes = [t.removeprefix("shape:") for t in row["tags"] if t.startswith("shape:")]
            shape = " ".join(shapes)
        rows.append({"suite": row["suite"], "id": row["id"], "shape": shape})
    return rows


def project_shape_problem(shape: str, file: dict) -> str | None:
    """Why `shape` is not one value of each axis, in the axes' order, or None when it is."""
    parts = shape.split("/")
    if len(parts) != len(AXES):
        return f"`shape` is {shape!r}: name it as {'/'.join(AXES)}"
    for axis, value in zip(AXES, parts, strict=True):
        if value not in file["axes"][axis]:
            return f"`shape` is {shape!r}: its {axis} is one of {', '.join(file['axes'][axis])}"
    return None


def shape_problems(rows: list[dict], file: dict) -> list[str]:
    """Each case that names no project shape, more than one, or one outside the axes."""
    out = []
    for row in rows:
        where = f"{row['suite']}/{row['id']}"
        if not row["shape"]:
            out.append(f"{where}: name its `shape`, as {'/'.join(AXES)} ({SHAPES_FILE})")
        elif " " in row["shape"]:
            out.append(f"{where}: it names {len(row['shape'].split())} shapes; a case shows one project, so keep one `shape:` tag")
        elif problem := project_shape_problem(row["shape"], file):
            out.append(f"{where}: {problem}")
    return out


def fixture_problems(root: Path, file: dict) -> list[str]:
    """Each core test fixture that names no project shape and sits in no folder `not_project_shaped` lists, and each listed path that
    is gone."""
    shaped, unshaped = file.get("fixtures", {}), file.get("not_project_shaped", {})
    out = [f"{rel}: listed in {SHAPES_FILE}, but the path is gone" for rel in [*shaped, *unshaped] if not (root / rel).exists()]
    out += [f"{rel}: {problem}" for rel, shape in shaped.items() if (problem := project_shape_problem(shape, file))]
    folder = root / FIXTURES
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel not in shaped and not any(rel.startswith(f"{u}/") for u in unshaped):
            out.append(f"{rel}: name its project shape in `fixtures`, or its folder in `not_project_shaped`, in {SHAPES_FILE}")
    return out


def _pairs(file: dict) -> list[tuple[str, str]]:
    """The other axes' values, as (axis, value), in the axes' order: the table's columns."""
    return [(axis, value) for axis in AXES[1:] for value in file["axes"][axis]]


def shape_counts(shapes: list[str], file: dict) -> dict[str, dict[tuple[str, str], int]]:
    """For each type, how many of `shapes` pair it with each value of the other axes."""
    counts = {kind: dict.fromkeys(_pairs(file), 0) for kind in file["axes"]["type"]}
    for shape in shapes:
        kind, *rest = shape.split("/")
        for axis, value in zip(AXES[1:], rest, strict=True):
            counts[kind][(axis, value)] += 1
    return counts


def empty_pairs(shapes: list[str], file: dict) -> dict[str, list[str]]:
    """For each type, the values of the other axes that none of `shapes` pairs it with; a type of `any` is no type, so it has none."""
    counts = shape_counts(shapes, file)
    return {kind: empty for kind, row in counts.items() if kind != ANY and (empty := [value for (_, value), n in row.items() if n == 0])}


def shape_coverage_table(rows: list[dict], file: dict) -> str:
    """The eval cases per type and per value of the other axes, as a Markdown table, then the pairs no case covers. The Fixtures
    column counts the core fixtures of each type, which test aidd's code and stand in for no eval case, so the pairs leave them out."""
    cases = [row["shape"] for row in rows]
    fixtures = list(file.get("fixtures", {}).values())
    counts = shape_counts(cases, file)
    totals = {kind: sum(c.split("/", 1)[0] == kind for c in cases) for kind in file["axes"]["type"]}
    fixed = {kind: sum(c.split("/", 1)[0] == kind for c in fixtures) for kind in file["axes"]["type"]}
    columns = _pairs(file)
    lines = [
        "| Type | Cases | Fixtures | " + " | ".join(value for _, value in columns) + " |",
        "| --- | --- | --- | " + " | ".join("---" for _ in columns) + " |",
    ]
    for kind, row in counts.items():
        lines.append(f"| `{kind}` | {totals[kind]} | {fixed[kind]} | " + " | ".join(str(row[c]) for c in columns) + " |")
    empty = empty_pairs(cases, file)
    lines += ["", "The empty pairs, each a case to write:" if empty else "No pair is empty.", ""]
    lines += [f"- `{kind}`: {', '.join(values)}" for kind, values in empty.items()]
    return "\n".join(lines).rstrip("\n")
