"""The exploration comparison page: the directions side by side, with each round's screenshots, comments, and changes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from aidd import workitems
from aidd.kernel import repo_paths
from aidd.views import html_parts, markdown_html
from aidd.views.html_parts import Html, Section, el, join

# The most image bytes one page embeds, beyond each image's own limit (views.MAX_IMAGE_BYTES): the rest are named.
MAX_PAGE_IMAGE_BYTES = 40 * 1024 * 1024


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
        mime = repo_paths.IMAGE_TYPES.get(p.suffix.lower())
        if not p.is_relative_to(root):
            why = "not embedded: the path leaves the folder"
        elif not p.is_file():
            why = "not embedded: no such file in the folder"
        elif mime is None:
            why = "not embedded: only PNG, JPEG, GIF, and WebP images are"
        elif p.stat().st_size > html_parts.MAX_IMAGE_BYTES:
            why = f"not embedded: larger than {html_parts.MAX_IMAGE_BYTES // (1024 * 1024)} MB"
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


def _comment_items(data: dict | None) -> dict[str, dict]:
    items = (data or {}).get("items")
    out: dict[str, dict] = {}
    for i, item in enumerate(items if isinstance(items, list) else [], 1):
        if isinstance(item, dict):
            out[str(item.get("id") or f"item-{i}")] = item
    return out


def _round_comments(round_folder: Path, folder: Path) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """A round's comments by id, the direction each was made on ("" for a design's own), and what could not be read: its
    `comments.json`, and in an exploration each direction's `comments-<direction>.json`. A comment whose id names another
    direction is left out and named, so it never pairs with the wrong direction's screenshots."""
    files, problems = workitems.round_comment_files(round_folder, folder)
    comments: dict[str, dict] = {}
    directions: dict[str, str] = {}
    for direction, path in files:
        data, problem = _json(path)
        problems += [problem] if problem else []
        for ident, item in _comment_items(data).items():
            if workitems.comment_id_direction(ident) not in (None, direction):
                problems.append(f"{path.name}: {ident} is left out: its id names another direction")
                continue
            comments[ident], directions[ident] = item, direction
    return comments, directions, problems


def _where(item: dict) -> str:
    """The prototype view a comment was made on, `<screen>/<state>`, or the part of it the comment names."""
    return "/".join(str(item[k]) for k in ("screen", "state") if isinstance(item.get(k), str) and item[k])


def _item_text(ident: str, item: dict | None) -> Html:
    if item is None:
        return join(el("code", ident), ": no such comment in the round before")
    where = _where(item)
    return join(
        el("code", ident), " ", join(el("code", where), " ") if where else "", el("code", str(item.get("testid", ""))), ": ", str(item.get("comment", ""))
    )


def _comments_for(name: str, comments: dict[str, dict], directions: dict[str, str]) -> list[str]:
    """The comments made on the screen and state a screenshot `<screen>-<state>-<frame>-<theme>` shows. A direction's
    comments pair only with its own screenshots, whose names start with the direction: `a-<screen>-<state>-...`."""
    out = []
    for ident, item in comments.items():
        screen, state = str(item.get("screen") or ""), str(item.get("state") or "")
        own = f"{directions[ident]}-" if directions.get(ident) else ""
        if screen and state and (name + "-").startswith(f"{own}{screen}-{state}-"):
            out.append(ident)
    return out


def _changes_for(name: str, changes: list[dict]) -> list[dict]:
    """The changes a screenshot shows, by the screen and state each names. A change that answers a direction's comments
    (`a-r1-2`) shows on that direction's screenshots."""
    out = []
    for c in changes:
        screen, state = str(c.get("screen") or ""), str(c.get("state") or "")
        prefix = f"{screen}-{state}-" if screen and state else f"{screen}-" if screen else ""
        own = sorted({d for a in c.get("answers") or [] if (d := workitems.comment_id_direction(str(a)))})
        heads = [f"{d}-{prefix}" for d in own] or [prefix]
        if prefix and any((name + "-").startswith(head) for head in heads):
            out.append(c)
    return out


def _change_list(changes: list[dict], comments: dict[str, dict]) -> Html:
    rows = []
    for c in changes:
        answers = [str(a) for a in c.get("answers") or [] if isinstance(a, str | int)]
        rows.append(
            el(
                "li",
                str(c.get("summary") or "(no summary)"),
                el("ul", [el("li", "Answers ", _item_text(a, comments.get(a))) for a in answers]) if answers else "",
            )
        )
    return el("ul", rows, class_="findings")


def rounds_section(folder: Path, budget: _Budget) -> Html:
    found = workitems.exploration_rounds(folder)
    parts: list = [
        el(
            "p",
            "Each round's screenshots beside the round before, screen by screen. With them: what the agent changed (its changes.json), "
            "and the comment each change answers, from the round before: its comments.json, or each direction's comments-<direction>.json.",
            class_="muted",
        )
    ]
    before: tuple[int, dict[str, Path], Path] | None = None
    for n, path in found:
        shots = workitems.round_screenshots(path)
        parts.append(el("h3", f"Round {n}"))
        data, problem = _json(path / "changes.json")
        changes = [c for c in (data or {}).get("changes") or [] if isinstance(c, dict)]
        if problem:
            parts.append(el("p", html_parts.badge("warn", "changes"), " ", problem))
        if before is None:
            parts.append(el("p", "The first visual.", class_="muted"))
            parts.append(
                el("div", [image(folder, f"{workitems.ROUNDS_DIR}/{n}/{p.name}", budget) for p in shots.values()], class_="pair")
                if shots
                else el("p", "no screenshots", class_="muted")
            )
            before = (n, shots, path)
            continue
        prev_n, prev, prev_path = before
        comments, directions, comment_problems = _round_comments(prev_path, folder)
        parts += [el("p", html_parts.badge("warn", f"round {prev_n} comments"), " ", problem) for problem in comment_problems]
        matched: set[int] = set()
        for name in sorted(set(prev) | set(shots)):
            old, new = prev.get(name), shots.get(name)
            if old and new:
                same = hashlib.sha256(old.read_bytes()).digest() == hashlib.sha256(new.read_bytes()).digest()
                status = html_parts.badge("pass", "unchanged") if same else html_parts.badge("pending", "changed")
            elif new:
                status = html_parts.badge("pending", f"new in round {n}")
            else:
                status = html_parts.badge("warn", f"gone in round {n}")
            mine = _changes_for(name, changes)
            matched |= {id(c) for c in mine}
            given = _comments_for(name, comments, directions)
            cells = [
                el(
                    "div",
                    el("p", el("strong", f"Round {prev_n}")),
                    image(folder, f"{workitems.ROUNDS_DIR}/{prev_n}/{old.name}", budget) if old else el("p", "none", class_="muted"),
                ),
                el(
                    "div",
                    el("p", el("strong", f"Round {n}")),
                    image(folder, f"{workitems.ROUNDS_DIR}/{n}/{new.name}", budget) if new else el("p", "none", class_="muted"),
                ),
            ]
            parts.append(
                el(
                    "details",
                    el("summary", el("code", name), " ", status),
                    el("div", cells, class_="pair"),
                    _change_list(mine, comments) if mine else "",
                    join(el("p", "Comments on this screen"), el("ul", [el("li", _item_text(k, comments[k])) for k in given])) if given else "",
                    open=bool(mine or given),
                )
            )
        rest = [c for c in changes if id(c) not in matched]
        if rest:
            parts.append(el("h4", "Other changes"))
            parts.append(_change_list(rest, comments))
        answered = {str(a) for c in changes for a in c.get("answers") or [] if isinstance(a, str | int)}
        open_items = [k for k in comments if k not in answered]
        if open_items:
            parts.append(el("h4", "Not answered yet"))
            parts.append(el("ul", [el("li", _item_text(k, comments[k])) for k in open_items]))
        before = (n, shots, path)
    return join(parts)


def _outcome_text(outcome: object) -> str:
    """A spike's recorded outcome, such as `adopted by @ana on 2026-09-19`; empty when none is recorded."""
    if not isinstance(outcome, dict):
        return ""
    return f"{outcome.get('decision')} by {outcome.get('by')} on {outcome.get('decided_on')}"


def comparison_page(folder: Path) -> str:
    """The exploration's one page: the question and its timebox, the directions side by side with the trade-offs under
    each, the rounds, and a choice to copy for each direction."""
    data, body = workitems.load_exploration(folder)
    found = workitems.exploration_directions(body)
    if not found:
        raise ValueError(f"{(folder / workitems.EXPLORATION_FILE).as_posix()} has no `## Direction A: <name>` section; write two or three")
    budget = _Budget()
    question = str(data.get("question") or folder.name)
    owner = str(data.get("owner") or "product-designer")
    sections: list[Section] = [
        Section(
            "question",
            "The question",
            join(
                html_parts.facts(
                    [
                        ("Question", question),
                        ("Owner", el("code", owner)),
                        ("Timebox", str(data.get("timebox") or "none set")),
                        ("Status", str(data.get("status") or "open")),
                        ("Outcome", _outcome_text(data.get("outcome"))),
                        ("Evidence", html_parts.code_list([str(e) for e in data.get("evidence") or []]) if data.get("evidence") else ""),
                        ("Folder", el("code", folder.as_posix())),
                    ]
                ),
                el(
                    "p",
                    "Divergent directions, sketched rough (a design file, or a diagram), so the choice is about the approach, not the polish.",
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
                markdown_html.md(d.body, top=4),
                join([image(folder, rel, budget) for rel in d.images]),
                el("h4", "Trade-offs"),
                markdown_html.md(d.tradeoffs, top=5) if d.tradeoffs.strip() else el("p", "none written", class_="muted"),
                class_="direction",
                id=f"direction-{d.letter.lower()}",
            )
        )
    sections.append(Section("directions", "Directions", el("div", cards, class_="cards")))
    extra = [(h, t) for h, t in workitems.body_sections(body) if not workitems.DIRECTION_HEADING.match(h)]
    for heading, text in extra:
        sections.append(Section("x-" + (re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "notes"), heading, markdown_html.md(text, top=3)))
    if workitems.exploration_rounds(folder):
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
        choice.append(html_parts.copyable(f"choice-{d.letter.lower()}", text, f"Copy direction {d.letter}"))
    choice.append(el("p", "This page never records a choice and approves nothing: its buttons only copy text.", class_="muted"))
    sections.append(Section("choice", "Your choice", join(choice)))
    lead = f"{len(found)} directions, owner {owner}, timebox {data.get('timebox') or 'none set'}"
    return html_parts.page(f"Exploration: {question}", sections, lead=lead, badge=html_parts.badge("pending", "a person picks"))
