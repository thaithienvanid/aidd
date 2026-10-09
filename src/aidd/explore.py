"""Explorations: two or three divergent directions for one question, compared on one page, then iterated in rounds.

An exploration is a folder (a Spec's design folder, `docs/design/<ID>/`, or `docs/architecture/explore/<topic>/`)
holding `exploration.md` (front matter checked by schemas/exploration.schema.json: the question, the owner role, the
timebox, the status, and a spike's outcome and evidence; then a `## Direction X: name` section per direction with its `### Trade-offs`), the directions' wireframes or diagrams, `rounds/<N>/` with the screenshots of
each round named `<screen>-<state>-<target>-<theme>.png` and the `changes.json` the agent writes, and the
`feedback-round-<N>.json` a person copies out of the prototype's feedback mode, each item naming its screen and state.

`aidd new exploration <folder>` writes it; `aidd explore <folder>` renders the one comparison page with the renderer in views.py: the directions side by side,
the rounds paired screen by screen with the feedback each change answers, and a choice to copy. The page records
nothing and approves nothing: the person's pick and reason are written by the owning role, in `DESIGN.md`, the Spec's
`## Design`, or an ADR. Also here: the `aidd validate` hints for design folders.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import model, resources, views
from .views import Html, Section, el, join

EXPLORATION = "exploration.md"
ROUNDS = "rounds"
# The most image bytes one page embeds, beyond each image's own limit (views.MAX_IMAGE_BYTES): the rest are named.
MAX_PAGE_IMAGE_BYTES = 40 * 1024 * 1024
TEXT_SUFFIXES = {".html", ".htm", ".md", ".json", ".css", ".js", ".txt"}
MAX_LINT_BYTES = 2 * 1024 * 1024

_DIRECTION = re.compile(r"^Direction\s+([A-Za-z0-9]+)\s*[:.–—-]?\s*(.*)$")
_IMAGE_REF = re.compile(r"`([^`\s]+\.(?:png|jpe?g|gif|webp|svg))`", re.I)
_LOREM = re.compile(r"lorem\s+ipsum", re.I)


@dataclass
class Direction:
    letter: str
    name: str
    body: str
    tradeoffs: str
    images: list[str] = field(default_factory=list)


def folders(root: Path, docs_dir: str = "docs") -> list[Path]:
    """The repository's exploration and design folders: each `docs/design/<ID>/` and `docs/architecture/explore/<topic>/`."""
    out: list[Path] = []
    for base in (root / docs_dir / "design", root / docs_dir / "architecture" / "explore"):
        if base.is_dir():
            out += sorted(p for p in base.iterdir() if p.is_dir())
    return out


def rounds(folder: Path) -> list[tuple[int, Path]]:
    """Each `rounds/<N>/` folder, by N."""
    base = folder / ROUNDS
    if not base.is_dir():
        return []
    return sorted((int(p.name), p) for p in base.iterdir() if p.is_dir() and p.name.isdigit())


def screenshots(folder: Path) -> dict[str, Path]:
    """A round's images by name without the extension (`<screen>-<state>-<target>-<theme>`)."""
    return {p.stem: p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in views.IMAGE_TYPES}


def load(folder: Path) -> tuple[dict, str]:
    from . import schema

    path = folder / EXPLORATION
    if not path.is_file():
        raise ValueError(
            f'no {EXPLORATION} in {folder.as_posix()}: start one with `aidd new exploration {folder.as_posix()} --title "..."`, which writes it from the template'
        )
    data, body = model.split_front_matter(path.read_text(encoding="utf-8"), path.as_posix())
    errors = schema.validate(data, "exploration.schema.json")
    if errors:
        raise ValueError(f"{path.as_posix()}: " + "; ".join(errors))
    return data, body


def _sections(body: str) -> list[tuple[str, str]]:
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


def directions(body: str) -> list[Direction]:
    found = []
    for heading, text in _sections(body):
        m = _DIRECTION.match(heading)
        if not m:
            continue
        parts = re.split(r"(?m)^###\s+Trade-offs\s*$", text, maxsplit=1)
        main, trade = (parts[0], parts[1]) if len(parts) == 2 else (text, "")
        found.append(Direction(m.group(1).upper(), m.group(2).strip(), main, trade, _IMAGE_REF.findall(main)))
    return found


class _Budget:
    def __init__(self) -> None:
        self.left = MAX_PAGE_IMAGE_BYTES


def image(folder: Path, rel: str, budget: _Budget) -> Html:
    """One image from the folder, embedded as a data: URI under the renderer's evidence rules (inside the folder, PNG,
    JPEG, GIF, or WebP, at most 5 MB), or its path and why it is not."""
    clean = rel.split("?", 1)[0]
    why = ""
    img: Html | str = ""
    root = folder.resolve()
    if not clean or clean.startswith(("/", "\\")) or ".." in Path(clean).parts or re.match(r"^[A-Za-z]:", clean):
        why = "not embedded: the path leaves the folder"
    else:
        p = (root / clean).resolve()
        mime = views.IMAGE_TYPES.get(p.suffix.lower())
        if not p.is_relative_to(root):
            why = "not embedded: the path leaves the folder"
        elif not p.is_file():
            why = "not embedded: no such file in the folder"
        elif mime is None:
            why = "not embedded: only PNG, JPEG, GIF, and WebP images are"
        elif p.stat().st_size > views.MAX_IMAGE_BYTES:
            why = f"not embedded: larger than {views.MAX_IMAGE_BYTES // (1024 * 1024)} MB"
        elif p.stat().st_size > budget.left:
            why = "not embedded: the page's image limit is reached"
        else:
            data = p.read_bytes()
            budget.left -= len(data)
            img = el("img", src=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", alt=clean, loading="lazy")
    return el("figure", img, el("figcaption", el("code", clean)), el("p", why, class_="muted") if why else "")


def _json(path: Path) -> tuple[dict | None, str]:
    if not path.is_file():
        return None, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return None, f"{path.name} is not JSON ({exc.msg} at line {exc.lineno}); fix it and render again"
    return (data, "") if isinstance(data, dict) else (None, f"{path.name} is not a JSON object")


def _feedback_items(data: dict | None) -> dict[str, dict]:
    items = (data or {}).get("items")
    out: dict[str, dict] = {}
    for i, item in enumerate(items if isinstance(items, list) else [], 1):
        if isinstance(item, dict):
            out[str(item.get("id") or f"item-{i}")] = item
    return out


def _where(item: dict) -> str:
    """The prototype view a feedback item was given on, `<screen>/<state>`, or the part of it the item names."""
    return "/".join(str(item[k]) for k in ("screen", "state") if isinstance(item.get(k), str) and item[k])


def _item_text(ident: str, item: dict | None) -> Html:
    if item is None:
        return join(el("code", ident), ": no such item in the feedback file")
    where = _where(item)
    return join(el("code", ident), " ", join(el("code", where), " ") if where else "", el("code", str(item.get("testid", ""))), ": ", str(item.get("note", "")))


def _feedback_for(name: str, feedback: dict[str, dict]) -> list[str]:
    """The feedback items given on the screen and state a screenshot `<screen>-<state>-<target>-<theme>` shows."""
    out = []
    for ident, item in feedback.items():
        screen, state = str(item.get("screen") or ""), str(item.get("state") or "")
        if screen and state and (name + "-").startswith(f"{screen}-{state}-"):
            out.append(ident)
    return out


def _changes_for(name: str, changes: list[dict]) -> list[dict]:
    out = []
    for c in changes:
        screen, state = str(c.get("screen") or ""), str(c.get("state") or "")
        prefix = f"{screen}-{state}-" if screen and state else f"{screen}-" if screen else ""
        if prefix and (name + "-").startswith(prefix):
            out.append(c)
    return out


def _change_list(changes: list[dict], feedback: dict[str, dict]) -> Html:
    rows = []
    for c in changes:
        answers = [str(a) for a in c.get("answers") or [] if isinstance(a, str | int)]
        rows.append(
            el(
                "li",
                str(c.get("summary") or "(no summary)"),
                el("ul", [el("li", "Answers ", _item_text(a, feedback.get(a))) for a in answers]) if answers else "",
            )
        )
    return el("ul", rows, class_="findings")


def rounds_section(folder: Path, budget: _Budget) -> Html:
    found = rounds(folder)
    parts: list = [
        el(
            "p",
            "Each round's screenshots beside the round before, screen by screen. With them: what the agent changed (its changes.json), "
            "and the feedback item each change answers (feedback-round-<N>.json).",
            class_="muted",
        )
    ]
    before: tuple[int, dict[str, Path]] | None = None
    for n, path in found:
        shots = screenshots(path)
        parts.append(el("h3", f"Round {n}"))
        data, problem = _json(path / "changes.json")
        changes = [c for c in (data or {}).get("changes") or [] if isinstance(c, dict)]
        if problem:
            parts.append(el("p", views.badge("warn", "changes"), " ", problem))
        if before is None:
            parts.append(el("p", "The first visual.", class_="muted"))
            parts.append(
                el("div", [image(folder, f"{ROUNDS}/{n}/{p.name}", budget) for p in shots.values()], class_="pair")
                if shots
                else el("p", "no screenshots", class_="muted")
            )
            before = (n, shots)
            continue
        prev_n, prev = before
        fb_data, fb_problem = _json(folder / f"feedback-round-{prev_n}.json")
        feedback = _feedback_items(fb_data)
        if fb_problem:
            parts.append(el("p", views.badge("warn", "feedback"), " ", fb_problem))
        matched: set[int] = set()
        for name in sorted(set(prev) | set(shots)):
            old, new = prev.get(name), shots.get(name)
            if old and new:
                same = hashlib.sha256(old.read_bytes()).digest() == hashlib.sha256(new.read_bytes()).digest()
                status = views.badge("pass", "unchanged") if same else views.badge("pending", "changed")
            elif new:
                status = views.badge("pending", f"new in round {n}")
            else:
                status = views.badge("warn", f"gone in round {n}")
            mine = _changes_for(name, changes)
            matched |= {id(c) for c in mine}
            given = _feedback_for(name, feedback)
            cells = [
                el(
                    "div",
                    el("p", el("strong", f"Round {prev_n}")),
                    image(folder, f"{ROUNDS}/{prev_n}/{old.name}", budget) if old else el("p", "none", class_="muted"),
                ),
                el("div", el("p", el("strong", f"Round {n}")), image(folder, f"{ROUNDS}/{n}/{new.name}", budget) if new else el("p", "none", class_="muted")),
            ]
            parts.append(
                el(
                    "details",
                    el("summary", el("code", name), " ", status),
                    el("div", cells, class_="pair"),
                    _change_list(mine, feedback) if mine else "",
                    join(el("p", "Feedback on this screen"), el("ul", [el("li", _item_text(k, feedback[k])) for k in given])) if given else "",
                    open=bool(mine or given),
                )
            )
        rest = [c for c in changes if id(c) not in matched]
        if rest:
            parts.append(el("h4", "Other changes"))
            parts.append(_change_list(rest, feedback))
        answered = {str(a) for c in changes for a in c.get("answers") or [] if isinstance(a, str | int)}
        open_items = [k for k in feedback if k not in answered]
        if open_items:
            parts.append(el("h4", "Not answered yet"))
            parts.append(el("ul", [el("li", _item_text(k, feedback[k])) for k in open_items]))
        before = (n, shots)
    return join(parts)


def _outcome_text(outcome: object) -> str:
    """A spike's recorded outcome, such as `adopted by @ana on 2026-09-19`; empty when none is recorded."""
    if not isinstance(outcome, dict):
        return ""
    return f"{outcome.get('decision')} by {outcome.get('by')} on {outcome.get('on')}"


def timebox_ends(data: dict) -> dt.date | None:
    """The date a spike's timebox ends, when the timebox is a date (YYYY-MM-DD); None for minutes or a cost."""
    raw = str(data.get("timebox") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def comparison_page(folder: Path) -> str:
    """The exploration's one page: the question and its timebox, the directions side by side with the trade-offs under
    each, the rounds, and a choice to copy for each direction."""
    data, body = load(folder)
    found = directions(body)
    if not found:
        raise ValueError(f"{(folder / EXPLORATION).as_posix()} has no `## Direction A: <name>` section; write two or three")
    budget = _Budget()
    question = str(data.get("question") or folder.name)
    owner = str(data.get("owner") or "product-designer")
    sections: list[Section] = [
        Section(
            "question",
            "The question",
            join(
                views.facts(
                    [
                        ("Question", question),
                        ("Owner", el("code", owner)),
                        ("Timebox", str(data.get("timebox") or "none set")),
                        ("Status", str(data.get("status") or "open")),
                        ("Outcome", _outcome_text(data.get("outcome"))),
                        ("Evidence", views.code_list([str(e) for e in data.get("evidence") or []]) if data.get("evidence") else ""),
                        ("Folder", el("code", folder.as_posix())),
                    ]
                ),
                el(
                    "p",
                    "Divergent directions, drawn rough (wireframe mode, `?mode=wireframe`, or a diagram), so the choice is about the approach, not the polish.",
                    class_="muted",
                ),
            ),
        )
    ]
    cards = []
    for d in found:
        cards.append(
            el(
                "article",
                el("h3", f"Direction {d.letter}: {d.name}" if d.name else f"Direction {d.letter}"),
                views.md(d.body, top=4),
                join([image(folder, rel, budget) for rel in d.images]),
                el("h4", "Trade-offs"),
                views.md(d.tradeoffs, top=5) if d.tradeoffs.strip() else el("p", "none written", class_="muted"),
                class_="direction",
                id=f"direction-{d.letter.lower()}",
            )
        )
    sections.append(Section("directions", "Directions", el("div", cards, class_="cards")))
    extra = [(h, t) for h, t in _sections(body) if not _DIRECTION.match(h)]
    for heading, text in extra:
        sections.append(Section("x-" + (re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "notes"), heading, views.md(text, top=3)))
    if rounds(folder):
        sections.append(Section("rounds", "Rounds: what changed", rounds_section(folder, budget)))
    where = "an ADR (`aidd new adr`)" if owner == "architect" else "the Spec's `## Design` section, or `DESIGN.md` for a design-system direction"
    choice: list = [
        el(
            "p",
            f"Copy the direction you pick, finish the Why line, and give it to the {owner} (or post it on the pull request). "
            f"The {owner} records your pick and your reason in {where}; the Decisions table in DESIGN.md or an ADR keeps it.",
        )
    ]
    for d in found:
        text = f"Direction {d.letter}: {d.name}\nWhy: <what made it win, and why the others lost>\nPicked by: <your name>"
        choice.append(views.copyable(f"choice-{d.letter.lower()}", text))
    choice.append(el("p", "This page never records a choice and approves nothing: its buttons only copy text.", class_="muted"))
    sections.append(Section("choice", "Your choice", join(choice)))
    lead = f"{len(found)} directions, owner {owner}, timebox {data.get('timebox') or 'none set'}"
    return views.page(f"Exploration: {question}", sections, lead=lead, badge=views.badge("pending", "a person picks"))


def new_exploration(folder: Path, *, question: str, owner: str = "product-designer", timebox: str = "45 minutes", today: dt.date | None = None) -> Path:
    """Write `exploration.md` from the template (`aidd new exploration`); refuse when one exists."""
    from .repo import fill

    path = folder / EXPLORATION
    if path.exists():
        raise FileExistsError(f"{path.as_posix()} exists: render it with `aidd explore {folder.as_posix()}`")
    if owner not in resources.roles()["roles"]:
        raise ValueError(f"--owner is an aidd-team role, such as product-designer or architect, not {owner!r}")
    text = (resources.data_dir("skill") / "assets" / EXPLORATION).read_text(encoding="utf-8")
    values = {
        "title": question,
        "question": json.dumps(question, ensure_ascii=False)[1:-1],
        "owner": owner,
        "timebox": json.dumps(timebox, ensure_ascii=False)[1:-1],
        "today": (today or dt.date.today()).isoformat(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(fill(text, **values), encoding="utf-8")
    return path


# ---- `aidd validate` hints: advice, never a gate rule ----


_DATE_LIKE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def spike_hints(rel: str, data: dict, today: dt.date, bots: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """A spike whose timebox date has passed while it is open with no outcome, a timebox that looks like a date but is
    not one, and an outcome an agent recorded (`project.is_agent` with the configured `bots`, or a baseline agent login)."""
    from . import gates, project
    from .util import norm

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
            f'outcome = {{ decision = "adopted", by = "@you", on = {today.isoformat()} }} (or rejected, or inconclusive) and sets status = "decided"'
        )
    outcome = data.get("outcome")
    who = str(outcome.get("by") or "") if isinstance(outcome, dict) else ""
    bare = who.split(":", 1)[1] if ":" in who and not who.lower().startswith(("agent:", "email:")) else who
    if who and (project.is_agent(who, bots) or gates.agent_account(norm(bare), bots)):
        out.append(f"{rel}: outcome.by {who} is an agent account; a person decides a spike")
    return out


def front_matter_warnings(rel: str, path: Path) -> tuple[dict, list[str]]:
    """The exploration's front matter and what is wrong with it: front matter that does not parse, or that the schema
    rejects. `aidd explore` refuses both, so `aidd validate` names them first, as warnings."""
    from . import schema

    try:
        data, _ = model.split_front_matter(path.read_text(encoding="utf-8", errors="replace"), rel)
    except model.ModelError as exc:
        return {}, [str(exc)]
    return data, [f"{rel}: {e}" for e in schema.validate(data, "exploration.schema.json")]


def hints(root: Path, cfg, today: dt.date | None = None) -> list[str]:
    """A round with screenshots but no dark one while `[project.defaults] dark_mode` is on, placeholder copy
    (lorem ipsum) in a design or exploration folder, front matter the exploration schema rejects, and the spike checks
    (`spike_hints`)."""
    from . import project, workitems

    dark = project.defaults(cfg)["dark_mode"]
    bots = workitems.bots_of(cfg)
    today = today or dt.date.today()
    out: list[str] = []
    for folder in folders(root, cfg.docs_dir if cfg is not None else "docs"):
        rel = folder.relative_to(root).as_posix()
        path = folder / EXPLORATION
        if path.is_file():
            data, wrong = front_matter_warnings(f"{rel}/{EXPLORATION}", path)
            out += wrong + spike_hints(f"{rel}/{EXPLORATION}", data, today, bots)
        for n, path in rounds(folder) if dark else []:
            shots = screenshots(path)
            if shots and not any(s.lower().endswith("-dark") for s in shots):
                out.append(
                    f"{rel}/{ROUNDS}/{n} has no dark screenshot and [project.defaults] dark_mode is on. Add "
                    "<screen>-<state>-<target>-dark.png beside each light one, or turn dark_mode off with its reason"
                )
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size <= MAX_LINT_BYTES:
                if _LOREM.search(p.read_text(encoding="utf-8", errors="replace")):
                    out.append(f"{p.relative_to(root).as_posix()} holds lorem ipsum; write real copy and realistic sample data (the prototype lint's rule 3)")
    return out
