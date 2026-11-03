"""The exploration comparison page: the directions side by side, with each round's screenshots, feedback, and changes."""

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
    found = workitems.exploration_rounds(folder)
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
            before = (n, shots)
            continue
        prev_n, prev = before
        fb_data, fb_problem = _json(folder / f"feedback-round-{prev_n}.json")
        feedback = _feedback_items(fb_data)
        if fb_problem:
            parts.append(el("p", html_parts.badge("warn", "feedback"), " ", fb_problem))
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
            given = _feedback_for(name, feedback)
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
        choice.append(html_parts.copyable(f"choice-{d.letter.lower()}", text))
    choice.append(el("p", "This page never records a choice and approves nothing: its buttons only copy text.", class_="muted"))
    sections.append(Section("choice", "Your choice", join(choice)))
    lead = f"{len(found)} directions, owner {owner}, timebox {data.get('timebox') or 'none set'}"
    return html_parts.page(f"Exploration: {question}", sections, lead=lead, badge=html_parts.badge("pending", "a person picks"))
