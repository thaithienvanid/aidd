"""The parts the work-items page's views share: icons, labels for a step, the copy button, the team filter, and the foot.

Every part is plain markup from the status answer (schemas/status.schema.json), escaped by `el`. Facts the page works out, with
no key of their own, are the step's short name, the Board's columns, and the counts."""

from __future__ import annotations

import re
import shlex

from aidd import knowledge, workitems
from aidd.kernel import json_schema
from aidd.views.html_parts import Html, el, join
from aidd.workitems import is_id

OPEN = workitems.OPEN_GROUPS
# The work items that group others in the Tree: an Intent, with its phases and the Specs under it.
GROUPING_TYPES = ("intent",)
# The Board's other columns, the status groups. Done holds no cards.
GROUP_COLUMNS = (("backlog", "Backlog"), ("unstarted", "Unstarted"), ("started", "Started"))
# Needs you lists what is stopped first, then the step nearest to done; any other step a person takes follows, in the answer's order.
NEEDS_ORDER = ("spec.blocked", "pr.merge", "spec.approve", "spec.triage")
STEP_NAMES = {
    "spec.blocked": "Blocked",
    "spec.triage": "Triage",
    "spec.verify": "Verifying",
    "exploration.open": "Open question",
}
# The icons, by where a page first draws them: the top bar, the banner and the words, the views' controls, the states and
# an open question's mark, then the foot and the dialog.
ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "keys": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6.5 10h1M10.5 10h1M14.5 10h1M7 14h10"/>',
    "warn": '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.1"/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/><path d="M15.5 8.5V5.5a1.5 1.5 0 0 0-1.5-1.5H5.5A1.5 1.5 0 0 0 4 5.5V14a1.5 1.5 0 0 0 1.5 1.5h3"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "right": '<path d="m9 6 6 6-6 6"/>',
    "back": '<path d="m15 6-6 6 6 6"/>',
    "block": '<circle cx="12" cy="12" r="8"/><path d="M8 12h8"/>',
    "pause": '<circle cx="12" cy="12" r="8"/><path d="M10 9v6M14 9v6"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="currentColor"/>',
    "ask": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.2v.1"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "fail": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
}


def icon(name: str) -> Html:
    """An icon from the page's one sprite, so it is drawn once however many places use it."""
    return Html(f'<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>')


def sprite() -> Html:
    """Every icon once, as symbols, at the top of the page."""
    symbols = "".join(f'<symbol id="i-{name}" viewBox="0 0 24 24">{body}</symbol>' for name, body in ICONS.items())
    return Html(f'<svg class="sprite" width="0" height="0" aria-hidden="true" focusable="false"><defs>{symbols}</defs></svg>')


def title_button(item: dict, class_: str, testid: str) -> Html:
    """An item's title as the button that opens it. The direction is on an inner span, so a right-to-left title never flips
    the button's own layout."""
    return el(
        "button",
        el("span", item["title"], dir="auto", data_title=True),
        type="button",
        class_=class_,
        data_go="item",
        data_item=item["id"],
        data_testid=testid,
    )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# What the steps that name a field of the Spec say to a person who never read the Spec format.
PLAIN_WHAT = {
    "flag.overdue": "A feature flag is past its cleanup date. An agent writes the Spec that removes it.",
    "deprecation.overdue": "A deprecation is past its end date. An agent writes the Spec that removes it.",
    "spec.emergency": "An emergency Spec is open. Restore service inside its scope first, then finish the Spec before its review date.",
}
PLAIN_HEADING = {"flag.overdue": "Feature flag past due", "deprecation.overdue": "Deprecation past due"}


def what_of(step: dict) -> str:
    """The step in words for a person: plain words for a step that would name a field of the Spec, else its own, as a sentence."""
    return PLAIN_WHAT.get(str(step.get("code", ""))) or sentence(str(step.get("what", "")))


def why_line(step: dict) -> Html:
    """Why the step comes next, as `aidd status` says it, read from the data that owns the reason; nothing when no data
    owns one."""
    why = str(step.get("why") or "")
    return el("p", "Why: ", sentence(why), class_="why prose", data_field="why") if why else Html("")


def stale(item: dict) -> bool:
    """Whether the item's last test run was for another commit than the head: only a run on the head counts."""
    ev: dict = item.get("last_test_run") or {}
    return bool(ev) and ev["commit"] != ev["head"]


def stale_text(ev: dict) -> str:
    """Why a run no longer counts: it is behind the head by some commits, or it is for another commit."""
    return f"Last test run is {plural(ev['behind'], 'commit')} old" if ev.get("behind") else "Last test run is for another commit than the head"


def team_label(name: str) -> str:
    """A delivery team's name for a person to read: `checkout-web` as `Checkout web`. The name itself stays the key."""
    return name.replace("-", " ").replace("_", " ").capitalize()


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else many or one + 's'}"


def step_of(item: dict) -> dict:
    return item.get("next") or {}


def teams_of(item: dict) -> list[str]:
    return list(item.get("teams_in_scope") or [])


def words_of(item: dict) -> str:
    return str(step_of(item).get("words") or "")


def status_name(item: dict) -> str:
    return str(item.get("status", "")).replace("_", " ").capitalize()


def sentence(text: str) -> str:
    """A step from `aidd status`, which starts lower-case, as a sentence with no code marks: capitalized, ended by a period.
    aidd's own name stays lower-case."""
    text = text.replace("`", "")
    text = text[:1].upper() + text[1:] if text[:1].islower() and not text.startswith("aidd ") else text
    return text if text.endswith((".", "?", "!")) else text + "."


def step_name(item: dict) -> str:
    """The step's short name: the gate it waits at, such as Spec approval, Blocked, or the code's own words."""
    code = str(step_of(item).get("code", ""))
    return gate_of(item) or STEP_NAMES.get(code) or code.split(".")[-1].replace("_", " ").capitalize()


EMERGENCY_FIELDS = ("severity", "type", "commander", "incident", "backfill_due")
EMERGENCY_REQUIRED = ("severity", "type", "commander", "backfill_due")


def emergency_facts(item: dict) -> dict[str, tuple[str, str]]:
    """Each field of the item's `emergency` as ("ok", its text), ("absent", ""), or ("invalid", ""): good when it passes its own
    sub-schema in common.schema.json, so one bad field never hides the rest, and absent only when it is not there. An
    `emergency` that is no object makes each required field unreadable."""
    found = item.get("emergency")
    block: dict = found if isinstance(found, dict) else {}
    out: dict[str, tuple[str, str]] = {}
    for key in EMERGENCY_FIELDS:
        if key in block:
            bad = json_schema.validate(block[key], f"common.schema.json#/$defs/emergency/properties/{key}")
            out[key] = ("invalid", "") if bad else ("ok", str(block[key]))
        else:
            out[key] = ("invalid", "") if found is not None and not isinstance(found, dict) and key in EMERGENCY_REQUIRED else ("absent", "")
    return out


def place_unknown(item: dict) -> bool:
    """Whether an open emergency came from `--all-branches` with no block of its own: that version's block is incomplete or
    differs by place, and this worktree's block is not its block, so the page claims nothing about its fields."""
    return bool(item.get("places")) and "emergency" not in item and is_emergency(item)


UNKNOWN_BLOCK = "Its emergency block is incomplete or differs by place: run"


def emergency_incomplete(item: dict) -> bool:
    facts = emergency_facts(item)
    return any(facts[k][0] != "ok" for k in EMERGENCY_REQUIRED) or facts["incident"][0] == "invalid"


def is_emergency(item: dict) -> bool:
    """Whether an open item is an emergency: it is on the emergency route, or its step is the emergency's. Not whether its
    `emergency` block is whole, which is a fact the page shows as it is, never a reason to hide the emergency."""
    return item.get("group") in OPEN and (item.get("route") == "emergency" or step_of(item).get("code") == "spec.emergency")


def first_open_task(item: dict) -> tuple[str, int] | None:
    tasks = item.get("tasks") or []
    todo = next((t for t in tasks if t["status"] != "done"), None)
    return (str(todo["id"]), len(tasks)) if todo else None


def step_label(item: dict) -> str:
    """What the step is, in a few words for a card or a row: who answers, what is built, or who it waits for."""
    step, person = step_of(item), str(step_of(item).get("person") or "")
    code, task = str(step.get("code", "")), first_open_task(item)
    if code in ("spec.approve", "pr.merge", "spec.triage"):
        return f"Waits for {person}" if person and code != "spec.triage" else ("You accept, decline, or snooze it" if code == "spec.triage" else "")
    if code == "spec.blocked":
        return f"Waits for {person}" if person else "Waits for a person"
    if code == "spec.blocked_by":
        return "Waits for " + ", ".join(item.get("blocked_by") or ["other work"])
    if code == "spec.planned":
        return "Planned"
    if code == "spec.draft":
        return "Writing the Spec"
    if code == "spec.emergency":
        return f"Repair, {task[0]} of {task[1]}" if task else "Repair"
    if code == "spec.in_progress" and task:
        return f"Building, {task[0]} of {task[1]}"
    if code == "spec.in_progress" and item.get("tasks"):
        return "Verifying"
    if code == "spec.approved" and task:
        return f"Approved in its file, next {task[0]}"
    return step_name(item) if step else ""


def board_stages() -> list[str]:
    """The Board's columns: the stages a Spec moves through, from `loop.stages`. Plan is where an Intent is planned, and
    Maintain follows finished work, so each stays on the Intent's page and in the Tree."""
    others = (workitems.stage_of_step("Plan"), workitems.stage_of_step("Learn"))
    return [name for name, _ in workitems.stages() if name not in others]


def gate_of(item: dict) -> str:
    """The gate the item's step waits at, such as Spec approval: the gate in `loop.gates` whose actions hold the step's code,
    which a gate step takes from the action a person's yes covers. "" when it waits at no gate."""
    code = str(step_of(item).get("code", ""))
    return next((str(g["name"]) for g in knowledge.roles()["loop"]["gates"] if code in g["actions"]), "")


def one_line(words: str) -> str:
    """Words to copy, on one line with no control character: a newline pasted into a terminal would run what follows it."""
    return " ".join("".join(c if c.isprintable() else " " for c in words).split())


def command(*argv: str) -> str:
    """A shell command to copy: each word quoted, so a file name with `$(...)`, a backtick, or a space is one word. A command
    never holds text from the repository that is not a path or an id, such as an error message."""
    return " ".join(shlex.quote(a) for a in argv)


def item_ref(item: dict) -> str:
    """How a command names an item: its id when that is a plain id, else its path."""
    return str(item["id"]) if is_id(item["id"]) else str(item["path"])


def copy_button(label_for: str, words: str, testid: str, text: str = "Copy", *, primary: bool = False) -> Html:
    """Copy is a default button; primary only for the step a view leads with, such as an item's next step."""
    words = one_line(words)
    return el(
        "button",
        icon("copy"),
        text,
        el("span", f" the words for {label_for}", class_="sr-only"),
        type="button",
        class_="btn btn-primary" if primary else "btn",
        data_copy=words,
        data_for=label_for,
        data_testid=testid,
    )


def words_box(label_for: str, words: str, testid: str, field: str = "words", *, next_step: bool = False) -> Html:
    """Words to copy. `next_step` marks the one box a row leads with, its next step, whose Copy turns primary while the row
    is the current one."""
    words = one_line(words)
    button = copy_button(label_for, words, testid)
    return el(
        "div", el("code", words, dir="auto", data_field=field), button, class_="words words-next" if next_step else "words", data_component="words-to-copy"
    )


def flags(item: dict) -> Html:
    """The marks beside a title: a shape and a word together, so color is never the only cue. A step a person takes reads
    Needs you, or the gate's name when it waits at one."""
    code, out = str(step_of(item).get("code", "")), []
    if is_emergency(item):
        out.append(el("span", icon("warn"), "Emergency", class_="flag flag-emergency", data_flag="emergency"))
    if code == "spec.blocked":
        out.append(el("span", icon("block"), "Blocked", class_="flag flag-strong", data_flag="blocked"))
    elif step_of(item).get("who") == "person":
        out.append(el("span", icon("dot"), gate_of(item) or "Needs you", class_="flag flag-needs", data_flag="needs"))
    if item.get("unsaved"):
        out.append(el("span", icon("warn"), "Unsaved", class_="flag flag-warn", data_flag="unsaved"))
    return join(*out)


def team_filter(answer: dict, items: list[dict], *, needing: bool = False) -> Html:
    """The delivery-team filter: a button for each team in the config, with its open Specs (with `needing`, the ones that wait
    for a person, and the open questions in their folders), and none without teams."""
    names = answer.get("delivery_teams") or []
    if not names:
        return Html("")
    by_id = {i["id"]: i for i in items}
    homes = [by_id.get(str(q.get("item") or ""), {}) for q in answer.get("explorations") or []] if needing else []
    buttons = [el("button", "All teams", type="button", aria_pressed="true", data_team_all=True, data_set="team=", data_testid="team-all")]
    for name in names:
        n = sum(name in teams_of(i) for i in items if i["type"] == "spec" and (not needing or step_of(i).get("who") == "person"))
        n += sum(name in teams_of(home) for home in homes)
        buttons.append(
            el(
                "button",
                team_label(name),
                " ",
                el("span", n, class_="count", data_field="count"),
                type="button",
                aria_pressed="false",
                data_team=name,
                data_set=f"team={name.lower()}",
                data_testid=f"team-{slug(name)}",
            )
        )
    return el("div", buttons, class_="seg team-filter", role="group", aria_label="Delivery team", data_field="team-filter")


def foot(written: str, offset: str, name: str = "status-work.html") -> Html:
    note = f"Written {written}. Times are in {offset}. Run "
    return el(
        "div",
        el("p", note, el("code", "aidd status --html"), " for the latest."),
        el(
            "p",
            icon("link"),
            el("span", "Link to this view"),
            el("code", name, dir="ltr", data_field="view-link"),
            el("button", "Copy link", type="button", class_="btn btn-quiet js-only", data_copy=name, data_for="this view", data_testid="view-link-copy"),
            class_="link-line",
        ),
        class_="foot",
        data_field="foot",
    )


# What each view keeps in the address, besides the view itself: the script writes these and no other state.
KEPT = {"needs-you": "team", "board": "team columns rows intent", "tree": "open", "item": "item", "search": "q", "keys": ""}


def view(name: str, *body, label: str, ident: str = "", **attrs) -> Html:
    return el("section", *body, class_="view", id=ident or f"view-{name}", data_view=name, data_url=KEPT[name], aria_label=label, **attrs)


def title_span(item: dict, **attrs) -> Html:
    return el("span", item["title"], dir="auto", data_title=True, **attrs)


def phases_list(item: dict, by_id: dict[str, dict], prefix: str) -> Html:
    """An Intent's phases, in order, each headed by its place and name, with its due day or the day it finished, and each
    slice with its status and its stage: a slice with a Spec on the page opens it, with its flags and its step as a leaf has,
    and a planned one shows as planned.
    `prefix` keeps the test ids of the Tree and of the Intent's page apart. Empty for an item with no phase."""
    phases = item.get("phases") or []
    groups = []
    for at, phase in enumerate(phases):
        rows = []
        for line in phase["slices"]:
            spec = by_id.get(line["id"])
            state = str(line.get("status", "")).replace("_", " ")
            # A slice with a Spec on the page says what its step is, as a leaf does; else its status.
            step = step_label(spec) if spec is not None else ""
            words = " · ".join(w for w in (step or state.capitalize(), str(line.get("stage") or "")) if w)
            title = (
                title_button(spec, "link-title", f"{prefix}-slice-{line['id']}")
                if spec is not None
                else el("span", line.get("title") or line["id"], dir="auto", class_="slice-title")
            )
            rows.append(
                el(
                    "li",
                    el("span", line["id"], class_="id"),
                    title,
                    el("span", flags(spec) if spec is not None else "", el("span", words, class_="muted slice-state"), class_="leaf-step"),
                    class_="slice",
                    data_slice=line["id"],
                    data_slice_status=str(line.get("status", "")),
                    data_stage=str(line.get("stage") or ""),
                )
            )
        heading = el("p", workitems.phase_heading(phases, at), class_="phase-head")
        groups.append(el("li", heading, el("ul", rows, class_="slices"), class_="phase", data_phase=str(phase.get("id") or at + 1)))
    return el("ol", groups, class_="phases") if groups else Html("")
