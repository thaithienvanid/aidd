"""Explorations: two or three divergent directions for one question, compared on one page, then iterated in rounds.

An exploration is a folder in the folder of the work item it informs, `specs/<ID>/explore/<slug>/` (or
`specs/explore/<topic>/` while no work item exists yet: EXPLORATION_HOME), holding `exploration.md` (front matter checked by schemas/exploration.schema.json: the question, the owner role, the
timebox, the status, and a spike's outcome and evidence; then a `## Direction X: name` section per direction with its `### Trade-offs`), the directions' wireframes or diagrams, `rounds/<N>/` with the screenshots of
each round named `<screen>-<state>-<target>-<theme>.png` and the `changes.json` the agent writes, and the
`feedback-round-<N>.json` a person copies out of the prototype's feedback mode, each item naming its screen and state.

`aidd new exploration <folder>` writes it; `aidd explore <folder>` renders the one comparison page (views/exploration_page.py): the directions side by side,
the rounds paired screen by screen with the feedback each change answers, and a choice to copy. The page records
nothing and approves nothing: the person's pick and reason are written by the owning role, in `DESIGN.md`, the Spec's
`## Design`, or an ADR. Also here: the `aidd validate` hints for design and exploration folders.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import knowledge
from aidd.kernel import documents, repo_paths, resources
from aidd.workitems import item_folder

EXPLORATION_FILE = item_folder.EXPLORATION_FILE
ROUNDS_DIR = "rounds"
TEXT_SUFFIXES = {".html", ".htm", ".md", ".json", ".css", ".js", ".txt"}
MAX_LINT_BYTES = 2 * 1024 * 1024

_WORK_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")  # a work item's id, as spec_file.WORK_ID
DIRECTION_HEADING: re.Pattern[str] = re.compile(r"^Direction\s+([A-Za-z0-9]+)\s*[:.–—-]?\s*(.*)$")
_IMAGE_REF = re.compile(r"`([^`\s]+\.(?:png|jpe?g|gif|webp|svg))`", re.I)
_LOREM = re.compile(r"lorem\s+ipsum", re.I)


@dataclass
class Direction:
    letter: str
    name: str
    body: str
    tradeoffs: str
    images: list[str] = field(default_factory=list)


# Everything about a work item lives in its folder beside it, `specs/<ID>/` (item_folder): its design files in
# `design/`, and each exploration in `explore/<slug>/`. One asked before any work item exists goes in `specs/explore/<topic>/`.
DESIGN_FOLDER = item_folder.DESIGN_FOLDER
EXPLORE_FOLDER = item_folder.EXPLORE_FOLDER
EXPLORATION_HOME = (
    "An exploration lives in the folder of the work item it informs, `specs/<ID>/explore/<slug>/`, or in `specs/explore/<topic>/` while no work item exists yet"
)


def folders(root: Path, specs_dir: str = "specs") -> list[Path]:
    """The repository's design and exploration folders, each in its work item's folder: every `specs/<ID>/design/`,
    every `specs/<ID>/explore/<slug>/`, and every `specs/explore/<topic>/`."""
    base = root / specs_dir
    out: list[Path] = []
    for item in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        if item.name == EXPLORE_FOLDER:
            out += sorted(p for p in item.iterdir() if p.is_dir())
            continue
        if (item / DESIGN_FOLDER).is_dir():
            out.append(item / DESIGN_FOLDER)
        if (item / EXPLORE_FOLDER).is_dir():
            out += sorted(p for p in (item / EXPLORE_FOLDER).iterdir() if p.is_dir())
    return out


def exploration_misplaced(folder: Path, specs_dir: str = "specs") -> str | None:
    """Where an exploration given `folder` belongs instead, when `folder` is not an exploration's home (EXPLORATION_HOME);
    None when it is. `specs/INIT-1/refund-limit` becomes `specs/INIT-1/explore/refund-limit`."""
    parts = [p for p in folder.as_posix().removeprefix("./").strip("/").split("/") if p]
    base = [p for p in specs_dir.strip("/").split("/") if p]
    rest = parts[len(base) :] if parts[: len(base)] == base else None
    if rest is not None and len(rest) == 2 and rest[0] == EXPLORE_FOLDER:
        return None
    if rest is not None and len(rest) == 3 and rest[1] == EXPLORE_FOLDER:
        return None
    owner = next((p for p in parts if _WORK_ID.fullmatch(p)), "<ID>")  # the work item the old path names, if any
    slug = parts[-1] if parts and parts[-1] not in (owner, DESIGN_FOLDER, EXPLORE_FOLDER) else "<slug>"
    return f"{'/'.join(base)}/{owner}/{EXPLORE_FOLDER}/{slug}"


def exploration_rounds(folder: Path) -> list[tuple[int, Path]]:
    """Each `rounds/<N>/` folder, by N."""
    base = folder / ROUNDS_DIR
    if not base.is_dir():
        return []
    return sorted((int(p.name), p) for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def round_screenshots(folder: Path) -> dict[str, Path]:
    """A round's images by name without the extension (`<screen>-<state>-<target>-<theme>`)."""
    return {p.stem: p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in repo_paths.IMAGE_TYPES}


def load_exploration(folder: Path) -> tuple[dict, str]:
    from aidd.kernel import json_schema

    path = folder / EXPLORATION_FILE
    if not path.is_file():
        raise ValueError(
            f'no {EXPLORATION_FILE} in {folder.as_posix()}: start one with `aidd new exploration {folder.as_posix()} --title "..."`, which writes it from the template'
        )
    data, body = documents.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())
    errors = json_schema.validate(data, "exploration.schema.json")
    if errors:
        raise ValueError(f"{path.as_posix()}: " + "; ".join(errors))
    return data, body


def body_sections(body: str) -> list[tuple[str, str]]:
    """Each `## heading` of the body and its text, fences kept."""
    out: list[tuple[str, str]] = []
    heading: str | None = None
    lines: list[str] = []
    fence = ""
    for line in body.splitlines():
        m = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if m:
            fence = "" if fence and line.strip().startswith(fence) else (fence or m.group(1))
        if not fence and not m and line.startswith("## "):
            if heading is not None:
                out.append((heading, "\n".join(lines)))
            heading, lines = line[3:].strip(), []
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        out.append((heading, "\n".join(lines)))
    return out


def exploration_directions(body: str) -> list[Direction]:
    found = []
    for heading, text in body_sections(body):
        m = DIRECTION_HEADING.match(heading)
        if not m:
            continue
        parts = re.split(r"(?m)^###\s+Trade-offs\s*$", text, maxsplit=1)
        main, trade = (parts[0], parts[1]) if len(parts) == 2 else (text, "")
        found.append(Direction(m.group(1).upper(), m.group(2).strip(), main, trade, _IMAGE_REF.findall(main)))
    return found


def timebox_ends(data: dict) -> dt.date | None:
    """The date a spike's timebox ends, when the timebox is a date (YYYY-MM-DD); None for minutes or a cost."""
    raw = str(data.get("timebox") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def new_exploration(folder: Path, *, question: str, owner: str = "product-designer", timebox: str = "45 minutes", today: dt.date | None = None) -> Path:
    """Write `exploration.md` from the template (`aidd new exploration`); refuse when one exists."""
    from aidd.kernel.text import fill_template

    path = folder / EXPLORATION_FILE
    if path.exists():
        raise FileExistsError(f"{path.as_posix()} exists: render it with `aidd explore {folder.as_posix()}`")
    if owner not in knowledge.roles()["roles"]:
        raise ValueError(f"--owner is an aidd-team role, such as product-designer or architect, not {owner!r}")
    text = (resources.data_dir("skill") / "assets" / EXPLORATION_FILE).read_text(encoding="utf-8")
    values = {
        "title": question,
        "question": question,
        "owner": owner,
        "timebox": timebox,
        "today": (today or dt.date.today()).isoformat(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(fill_template(text, **values), encoding="utf-8")
    return path


# ---- `aidd validate` hints: advice, never a gate rule ----


_DATE_LIKE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def spike_hints(rel: str, data: dict, today: dt.date, bots: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """A spike whose timebox date has passed while it is open with no outcome, a timebox that looks like a date but is
    not one, and an outcome an agent recorded (`identities.is_agent` with the configured `bots`)."""
    from aidd import config

    out = []
    ends = timebox_ends(data)
    raw = str(data.get("timebox") or "").strip()
    if ends is None and _DATE_LIKE.fullmatch(raw):
        out.append(
            f"{rel}: timebox {raw!r} looks like a date but is not YYYY-MM-DD, so aidd cannot read when the spike ends. "
            f"Write a real date as YYYY-MM-DD, such as {today.isoformat()}"
        )
    if ends is not None and ends < today and data.get("status") != "decided" and not data.get("outcome"):
        out.append(
            f"{rel}: the spike's timebox ended on {ends} with no outcome. A person records "
            f'`outcome: {{decision: adopted, by: "@you", decided_on: "{today.isoformat()}"}}` (or rejected, or inconclusive) and sets `status: decided`'
        )
    outcome = data.get("outcome")
    who = str(outcome.get("by") or "") if isinstance(outcome, dict) else ""
    if who and config.is_agent(who, bots):
        out.append(f"{rel}: outcome.by {who} is an agent account; a person decides a spike")
    return out


def front_matter_warnings(rel: str, path: Path) -> tuple[dict, list[str]]:
    """The exploration's front matter and what is wrong with it: front matter that does not parse, or that the schema
    rejects. `aidd explore` refuses both, so `aidd validate` names them first, as warnings."""
    from aidd.kernel import json_schema

    try:
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8", errors="replace"), rel)
    except documents.DocumentError as exc:
        return {}, [str(exc)]
    return data, [f"{rel}: {e}" for e in json_schema.validate(data, "exploration.schema.json")]


def hints(root: Path, cfg, today: dt.date | None = None) -> list[str]:
    """A round with screenshots but no dark one while `project.defaults dark_mode` is on, placeholder copy
    (lorem ipsum) in a design or exploration folder, front matter the exploration schema rejects, and the spike checks
    (`spike_hints`)."""
    from aidd import config
    from aidd.workitems import triage

    dark = config.project_defaults(cfg)["dark_mode"]
    bots = triage.bots_of(cfg)
    today = today or dt.date.today()
    out: list[str] = []
    for folder in folders(root, cfg.specs_dir if cfg is not None else "specs"):
        rel = folder.relative_to(root).as_posix()
        path = folder / EXPLORATION_FILE
        if path.is_file():
            data, wrong = front_matter_warnings(f"{rel}/{EXPLORATION_FILE}", path)
            out += wrong + spike_hints(f"{rel}/{EXPLORATION_FILE}", data, today, bots)
        for n, path in exploration_rounds(folder) if dark else []:
            shots = round_screenshots(path)
            if shots and not any(s.lower().endswith("-dark") for s in shots):
                out.append(
                    f"{rel}/{ROUNDS_DIR}/{n} has no dark screenshot and `project.defaults` dark_mode is on. Add "
                    "<screen>-<state>-<target>-dark.png beside each light one, or turn dark_mode off with its reason"
                )
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size <= MAX_LINT_BYTES:
                if _LOREM.search(p.read_text(encoding="utf-8", errors="replace")):
                    out.append(f"{p.relative_to(root).as_posix()} holds lorem ipsum; write real copy and realistic sample data (the prototype lint's rule 3)")
    return out
