"""Explorations: two or three divergent directions for one question, compared on one page, then iterated in rounds.

An exploration is a folder in the folder of the work item it informs, `specs/<ID>/explore/<slug>/` for a Spec and
`product/intents/<ID>/explore/<slug>/` for an Intent (or `specs/explore/<topic>/` while no work item exists yet: EXPLORATION_HOME), holding `exploration.md` (front matter checked by schemas/exploration.schema.json: the question, the role, the
timebox, the status, and a spike's outcome and basis; then a `## Direction X: name` section per direction with its `### Trade-offs`), the directions' wireframes or diagrams, `rounds/<N>/` with the screenshots of
each round named `<direction>-<screen>-<state>-<frame>-<theme>.png` by the direction's design in `directions/`, each
direction's `comments-<direction>.json` a person copies out of the prototype viewer, each comment naming its screen and
state, and the `changes.json` the agent writes. A Spec's design folder keeps the same rounds with `comments.json`.

`aidd new exploration <folder>` writes it; `aidd explore <folder>` renders the one comparison page (views/exploration_page.py): the directions side by side,
the rounds paired screen by screen with the comment each change answers, and a choice to copy. The page records
nothing and approves nothing: the person's pick and reason are written by the owning role, in `DESIGN.md`, the Spec's
`## Design`, or an ADR. Also here: the `aidd validate` hints for design and exploration folders.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from aidd import knowledge
from aidd.kernel import command_names, documents, regular_files, repo_paths, retired_names
from aidd.workitems import intent_paths, item_folder
from aidd.workitems.spec_file import ID_PREFIXES, WORK_ID

EXPLORATION_FILE = item_folder.EXPLORATION_FILE
ROUNDS_DIR = "rounds"
TEXT_SUFFIXES = {".htm", ".html", ".css", ".js", ".json", ".md", ".txt"}
MAX_LINT_BYTES = 2 * 1024 * 1024

DIRECTION_HEADING: re.Pattern[str] = re.compile(r"^Direction\s+([A-Za-z0-9]+)\s*[:.–—-]?\s*(.*)$")
_IMAGE_REF = re.compile(r"`([^`\s]+\.(?:png|jpe?g|gif|webp|svg))`", re.I)
_LOREM = re.compile(r"lorem\s+ipsum", re.I)
# A round's comments: `comments.json` for a design, and one `comments-<direction>.json` per direction of an exploration, a
# design in its `directions/` folder, named by that file's name. The name goes into a file name and a comment id, so it is
# letters, digits, and `-` only.
COMMENTS_FILE = "comments.json"
DIRECTION_NAME = re.compile(r"[A-Za-z0-9-]+")
DIRECTIONS_FOLDER = "directions"
MAX_DIRECTION_FILES = 26  # the directions' comments files one round reads; the rest are named and left out
# A comment's id, `r<round>-<n>`, or `<direction>-r<round>-<n>` for a direction: the group is the direction it names.
_COMMENT_ID = re.compile(r"(?:([A-Za-z0-9-]+)-)?r[0-9]+-[0-9]+")


@dataclass
class Direction:
    letter: str
    name: str
    body: str
    tradeoffs: str
    images: list[str] = field(default_factory=list)


# Everything about a work item lives in its folder beside it, `specs/<ID>/` for a Spec and `product/intents/<ID>/` for an Intent
# (item_folder): its design files in `design/`, and each exploration in `explore/<slug>/`. One asked before any work item exists
# goes in `specs/explore/<topic>/`.
DESIGN_FOLDER = item_folder.DESIGN_FOLDER
EXPLORE_FOLDER = item_folder.EXPLORE_FOLDER
EXPLORATION_HOME = (
    "An exploration lives in the folder of the work item it informs, `specs/<ID>/explore/<slug>/` for a Spec or `product/intents/<ID>/explore/<slug>/` for an "
    "Intent, or in `specs/explore/<topic>/` while no work item exists yet"
)


def folders(root: Path, specs_dir: str = "specs", product_dir: str = "product") -> list[Path]:
    """The repository's design and exploration folders, each in its work item's folder: every `<ID>/design/` and every
    `<ID>/explore/<slug>/` in the specs folder and the Intents' folder, and every `specs/explore/<topic>/`."""
    out: list[Path] = []
    for folder in intent_paths.work_folders(specs_dir, product_dir):
        base = root / folder
        for item in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
            if item.name == EXPLORE_FOLDER:
                out += sorted(p for p in item.iterdir() if p.is_dir())
                continue
            if (item / DESIGN_FOLDER).is_dir():
                out.append(item / DESIGN_FOLDER)
            if (item / EXPLORE_FOLDER).is_dir():
                out += sorted(p for p in (item / EXPLORE_FOLDER).iterdir() if p.is_dir())
    return out


def exploration_misplaced(folder: Path, specs_dir: str = "specs", product_dir: str = "product", root: Path = Path()) -> str | None:
    """Where an exploration given `folder` belongs instead, when `folder` is not an exploration's home (EXPLORATION_HOME);
    None when it is. `specs/SPEC-1/refund-limit` becomes `specs/SPEC-1/explore/refund-limit`, and an Intent's home is the
    Intents' folder: `product/intents/INTENT-1/explore/refund-limit`. An Intent's folder in the specs folder is a home only while
    the Intent's file is still there in `root`, until a person moves it, so an Intent never gets a second folder."""
    parts = [p for p in folder.as_posix().removeprefix("./").strip("/").split("/") if p]
    bases = [[p for p in b.split("/") if p] for b in intent_paths.work_folders(specs_dir, product_dir)]
    intent = f"{ID_PREFIXES['intent']}-"
    for base in bases:
        rest = parts[len(base) :] if parts[: len(base)] == base else None
        if rest is not None and len(rest) == 2 and rest[0] == EXPLORE_FOLDER and base == bases[0]:
            return None  # an exploration asked before any work item exists lives in the specs folder only
        if rest is not None and len(rest) == 3 and rest[1] == EXPLORE_FOLDER:
            if not (base == bases[0] and rest[0].startswith(intent)) or (root / "/".join(base) / f"{rest[0]}.md").is_file():
                return None
    owner = next((p for p in parts if WORK_ID.fullmatch(p)), "<ID>")  # the work item the old path names, if any
    slug = parts[-1] if parts and parts[-1] not in (owner, DESIGN_FOLDER, EXPLORE_FOLDER) else "<slug>"
    home = bases[-1] if owner.startswith(intent) else bases[0]
    return f"{'/'.join(home)}/{owner}/{EXPLORE_FOLDER}/{slug}"


def exploration_rounds(folder: Path) -> list[tuple[int, Path]]:
    """Each `rounds/<N>/` folder, by N."""
    base = folder / ROUNDS_DIR
    if not base.is_dir():
        return []
    # Digits 0-9 only, as the prototype tool's own check: `str.isdigit` also passes `²`, which `int` refuses.
    return sorted((int(p.name), p) for p in base.iterdir() if p.is_dir() and re.fullmatch(r"[0-9]{1,4}", p.name))


def comment_id_direction(ident: str) -> str | None:
    """The direction a comment id names: `a` for `a-r1-2`, "" for a design's own `r1-2`, and None for no comment id."""
    found = _COMMENT_ID.fullmatch(ident)
    return (found.group(1) or "") if found else None


def round_comment_files(round_folder: Path, top: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """A round folder's comments files, each with its direction ("" for a design's own `comments.json`), and why any
    other is left out: a `comments-<direction>.json` whose name is no direction's, one past the first
    MAX_DIRECTION_FILES, or a file that is a link, leads out of `top`, or is larger than the cap."""
    found: list[tuple[str, Path]] = []
    left_out: list[str] = []
    directions = 0
    for path in sorted(round_folder.glob("comments*.json")):
        if path.name != COMMENTS_FILE and not path.name.startswith("comments-"):
            continue
        name = path.name.removeprefix("comments-").removesuffix(".json") if path.name != COMMENTS_FILE else ""
        if path.name != COMMENTS_FILE and not DIRECTION_NAME.fullmatch(name):
            left_out.append(f"{path.name} is left out: a direction's name is its design file's name, with letters, digits, and `-` only")
            continue
        directions += bool(name)
        if directions > MAX_DIRECTION_FILES:
            left_out.append(f"{path.name} is left out: a round reads the comments of {MAX_DIRECTION_FILES} directions at most")
        elif path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(top.resolve()) or path.stat().st_size > MAX_LINT_BYTES:
            left_out.append(f"{path.name} is left out: it is a link, leads out of the folder, or is larger than {MAX_LINT_BYTES} bytes")
        else:
            found.append((name, path))
    return found, left_out


def round_screenshots(folder: Path) -> dict[str, Path]:
    """A round's images by name without the extension (`<screen>-<state>-<frame>-<theme>`)."""
    return {p.stem: p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in repo_paths.IMAGE_TYPES}


def load_exploration(folder: Path) -> tuple[dict, str]:
    from aidd.kernel import json_schema

    path = folder / EXPLORATION_FILE
    if not path.is_file():
        raise ValueError(
            f'no {EXPLORATION_FILE} in {folder.as_posix()}: start one with `aidd new exploration {command_names.quoted(folder.as_posix()) or "<folder>"} --title "..."`, which writes it from the template'
        )
    text = regular_files.file_text(regular_files.working_root(path), path, documents.MAX_DOCUMENT_BYTES)
    if text is None:
        raise ValueError(
            f"{path.as_posix()} is a link, a device, or larger than {documents.MAX_DOCUMENT_BYTES} bytes, which aidd never reads; replace it with the file"
        )
    data, body = documents.split_front_matter(text, path.as_posix())
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


def new_exploration(folder: Path, *, question: str, role: str = "product-designer", timebox: str = "45 minutes", today: dt.date | None = None) -> Path:
    """Write `exploration.md` from the template (`aidd new exploration`), the project's own first; refuse when one exists."""
    from aidd.kernel.text import fill_template
    from aidd.workitems import authoring

    path = folder / EXPLORATION_FILE
    if path.exists():
        raise FileExistsError(f"{path.as_posix()} exists: render it with `aidd explore {command_names.quoted(folder.as_posix()) or '<folder>'}`")
    if role not in knowledge.roles()["roles"]:
        raise ValueError(f"--role is an aidd-team role, such as product-designer or architect, not {role!r}")
    text = authoring.template_text(Path("."), "exploration", EXPLORATION_FILE)
    values = {
        "title": question,
        "question": question,
        "role": role,
        "timebox": timebox,
        "today": (today or dt.date.today()).isoformat(),
    }
    regular_files.write_text_safely(regular_files.working_root(path), path, fill_template(text, **values))  # never through a link on the way
    return path


# ---- `aidd validate` hints: advice, never a block ----


_DATE_LIKE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def spike_hints(rel: str, data: dict, today: dt.date) -> list[str]:
    """A spike whose timebox date has passed while it is open with no outcome, a timebox that looks like a date but is
    not one, and an outcome an agent recorded (`identities.is_agent`)."""
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
    if who and config.is_agent(who):
        out.append(f"{rel}: outcome.by {who} is an agent account; a person decides a spike")
    return out


def front_matter_warnings(rel: str, path: Path) -> tuple[dict, list[str]]:
    """The exploration's front matter and what is wrong with it: front matter that does not parse, or that the schema
    rejects. `aidd explore` refuses both, so `aidd validate` names them first, as warnings."""
    from aidd.kernel import json_schema

    try:
        data, _ = documents.split_front_matter(regular_files.file_text(regular_files.working_root(path), path, documents.MAX_DOCUMENT_BYTES) or "", rel)
    except documents.DocumentError as exc:
        return {}, [str(exc)]
    return data, [f"{rel}: {retired_names.explain('exploration', e)}" for e in json_schema.validate(data, "exploration.schema.json")]


def hints(root: Path, cfg, today: dt.date | None = None) -> list[str]:
    """A round with screenshots but no dark one while `project.defaults dark_mode` is on, placeholder copy
    (lorem ipsum) in a design or exploration folder, front matter the exploration schema rejects, and the spike checks
    (`spike_hints`)."""
    from aidd import config

    dark = config.project_defaults(cfg)["dark_mode"]
    today = today or dt.date.today()
    out: list[str] = []
    for folder in folders(root, (cfg or config.EMPTY).specs_dir, (cfg or config.EMPTY).product_dir):
        rel = folder.relative_to(root).as_posix()
        path = folder / EXPLORATION_FILE
        if path.is_file():
            data, wrong = front_matter_warnings(f"{rel}/{EXPLORATION_FILE}", path)
            out += wrong + spike_hints(f"{rel}/{EXPLORATION_FILE}", data, today)
        for n, path in exploration_rounds(folder) if dark else []:
            shots = round_screenshots(path)
            if shots and not any(s.lower().endswith("-dark") for s in shots):
                out.append(
                    f"{rel}/{ROUNDS_DIR}/{n} has no dark screenshot and `project.defaults` dark_mode is on. Add "
                    "<screen>-<state>-<frame>-dark.png beside each light one (a direction's start with its name, a-), or turn dark_mode off with its reason"
                )
        out += round_file_warnings(root, folder)
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size <= MAX_LINT_BYTES:
                if _LOREM.search(regular_files.file_text(root, p, MAX_LINT_BYTES) or ""):
                    out.append(f"{p.relative_to(root).as_posix()} holds lorem ipsum; write real copy and realistic sample data (the prototype lint's rule 3)")
    return out


# The round files a person and an agent write beside a design, each with its schema: the comments a person makes, and the
# changes that answer them. The warnings come in this order.
ROUND_FILES = (
    (f"{ROUNDS_DIR}/*/{COMMENTS_FILE}", "round-comments.schema.json"),
    (f"{ROUNDS_DIR}/*/comments-*.json", "round-comments.schema.json"),
    (f"{ROUNDS_DIR}/*/changes.json", "round-changes.schema.json"),
)


def round_file_warnings(root: Path, folder: Path) -> list[str]:
    """Each `rounds/<N>/comments.json`, direction's `comments-<direction>.json`, and `changes.json` in a design or
    exploration folder that its schema rejects, or that is no JSON, as a warning naming the file and the first problems.
    Also each `comments-<direction>.json` whose name is no direction's or names no design in `directions/`, and each
    comments file that holds another direction's ids."""
    import json

    from aidd.kernel import json_schema

    out: list[str] = []
    for pattern, schema in ROUND_FILES:
        for path in sorted(folder.glob(pattern)):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()) or path.stat().st_size > MAX_LINT_BYTES:
                continue
            rel = path.relative_to(root).as_posix()
            if path.name.startswith("comments-") and not DIRECTION_NAME.fullmatch(path.name.removeprefix("comments-").removesuffix(".json")):
                out.append(
                    f"{rel} names no direction, so no page reads it: a direction is its design file's name in directions/, "
                    "with letters, digits, and `-` only. Rename the design, then copy the round again from the viewer"
                )
                continue
            try:
                data = json.loads(regular_files.file_text(root, path, regular_files.MAX_REPOSITORY_FILE) or "")
            except (OSError, ValueError, RecursionError):
                out.append(f"{rel} is not JSON; write it as schemas/{schema} describes, or copy it again from the viewer")
                continue
            errors = json_schema.validate(data, schema)
            if errors:
                out.append(f"{rel} does not match schemas/{schema}: {'; '.join(errors[:3])}")
            elif path.name.startswith("comments"):
                out += _comments_file_warnings(rel, path, folder, data)
    return out


def _comments_file_warnings(rel: str, path: Path, folder: Path, data: dict) -> list[str]:
    """A sound comments file that names a direction with no design in `directions/`, or holds another direction's ids."""
    direction = path.name.removeprefix("comments-").removesuffix(".json") if path.name != COMMENTS_FILE else ""
    out = []
    if direction and not (folder / DIRECTIONS_FOLDER / f"{direction}.html").is_file():
        out.append(f"{rel} names the direction `{direction}`, but {DIRECTIONS_FOLDER}/{direction}.html is not in the folder: name the file by its design")
    foreign = [item["id"] for item in data["items"] if comment_id_direction(item["id"]) != direction]
    if foreign:
        own = f"start with `{direction}-`" if direction else "name no direction, such as r1-2"
        out.append(f"{rel} holds {', '.join(foreign[:3])}, the ids of another direction: the ids in this file {own}")
    return out
