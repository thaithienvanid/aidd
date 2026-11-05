"""The work-items page's views: Needs you, the Board, the Tree, Search, and the keys (R377).

Every view is plain markup from the status answer, escaped by `el`; with scripts off they read as one scroll, and the script only
shows one at a time. The shared parts are in `work_parts.py`."""

from __future__ import annotations

from aidd.views.html_parts import Html, el, facts
from aidd.views.work_parts import (
    GROUP_COLUMNS,
    GROUPING_TYPES,
    NEEDS_ORDER,
    OPEN,
    PLAIN_HEADING,
    STEP_COLUMNS,
    column_of,
    command,
    flags,
    icon,
    is_emergency,
    item_ref,
    phases_list,
    plural,
    sentence,
    slug,
    stale,
    stale_text,
    step_label,
    step_name,
    step_of,
    team_filter,
    team_label,
    teams_of,
    title_button,
    title_span,
    view,
    what_of,
    why_line,
    words_box,
    words_of,
)
from aidd.workitems import branch_item

# Needs you ---------------------------------------------------------------------------------------------------------------------


def root_blocker(answer: dict) -> str:
    """The line Needs you shows in place of "Nothing needs you now" when open work has steps and none is a person's: what the
    answer's `root_blocker` says (R385), such as which item the Specs wait behind and the move that frees them."""
    return str(answer.get("root_blocker") or "")


def needs_lead(answer: dict, items: list[dict]) -> str:
    people = [i for i in items if step_of(i).get("who") == "person"]
    questions = answer.get("explorations") or []
    agents = sum(step_of(i).get("who") == "agent" for i in items if i["type"] == "spec" or step_of(i))
    waits = sum(step_of(i).get("who") == "nobody" and bool(i.get("waiting_on")) for i in items)
    open_emergency = any(is_emergency(i) for i in items)
    quiet = "An emergency is open, and nothing else waits for a person." if open_emergency else "Nothing needs you now."
    owed = [plural(n, word) for n, word in ((len(people), "item"), (len(questions), "question")) if n]
    many = len(people) + len(questions) > 1
    parts = [f"{' and '.join(owed)} {'wait' if many else 'waits'} for a person." if owed else quiet]
    tail = []
    if agents:
        tail.append(f"Your agents move {agents} more" if owed else f"Your agents move {agents}")
    if waits:
        tail.append(f"{waits} waits for other work" if waits == 1 else f"{waits} wait for other work")
    if tail:
        parts.append(", and ".join(tail) + ".")
    return " ".join(parts)


def need_row(item: dict, teams_set: bool) -> Html:
    step, person = step_of(item), str(step_of(item).get("person") or "")
    blocked = step.get("code") == "spec.blocked"
    meta = [
        flags(item) if blocked else el("b", step_name(item)),
        el("span", f"Waits for {person}") if person else "",
        *(
            [el("span", ", ".join(map(team_label, teams_of(item))), class_="muted")]
            if teams_of(item)
            else [el("span", "No team", class_="muted")]
            if item["type"] == "spec" and teams_set
            else []
        ),
        el("span", icon("warn"), "Unsaved", class_="flag flag-warn") if item.get("unsaved") and not blocked else "",
    ]
    return el(
        "li",
        el(
            "p",
            el("span", item["id"], class_="id"),
            title_button(item, "link-title", f"need-open-{slug(item['id'])}"),
            class_="need-title",
        ),
        el("p", meta, class_="need-step"),
        el("p", what_of(step), class_="why"),
        *stale_rows(item),
        el("p", "Then say to your agent", class_="run") if stale(item) and words_of(item) else "",
        words_box(item["id"], words_of(item), f"need-copy-{slug(item['id'])}", next_step=not stale(item)) if words_of(item) else "",
        class_="need",
        data_need=item["id"],
        data_person=person,
        data_teams=" ".join(teams_of(item)),
    )


def question_row(question: dict, by_id: dict[str, dict]) -> Html:
    """An open exploration: a pick a person owes, as a question in Needs you. Its title opens the work item whose folder
    holds it, whose page says why the step comes next, as each item's page does. One under `specs/explore/` has no item, so
    its row says why itself and gives the command that draws its options."""
    step, path = question["next"], str(question["path"])
    home = by_id.get(str(question.get("item") or ""))
    words = str(step.get("words") or "")
    title = (
        el("button", el("span", question["question"], dir="auto", data_title=True), type="button", class_="link-title", data_go="item", data_item=home["id"])
        if home
        else el("span", question["question"], dir="auto", data_title=True)
    )
    where = el("span", f"For {home['id']} ", el("span", home["title"], dir="auto")) if home else ""
    explore = command("aidd", "explore", path.rsplit("/", 1)[0])
    return el(
        "li",
        el("p", icon("ask"), title, class_="need-title"),
        el("p", el("b", step_name({"next": step})), where, class_="need-step"),
        el("p", what_of(step), class_="why"),
        "" if home else why_line(step),
        words_box(question["question"], words, f"need-copy-{slug(path)}", next_step=True)
        if words
        else el(
            "div",
            el("p", "Run in a terminal to see its options side by side", class_="run"),
            words_box("its options", explore, f"need-explore-{slug(path)}", field="command", next_step=True),
        ),
        class_="need",
        data_need=path,
        data_person="",
        data_teams=" ".join(teams_of(home)) if home else "",
    )


def handoff_section(note: dict | None, home: dict | None, heading_class: str = "h2") -> Html:
    """Where the work on this branch stopped, from the handoff note in its last commit: the agent's account, never a yes.
    In Needs you (`h2`), it links the item the branch is for, `home`; on that item's page (`sec`), it needs no link."""
    if not note:
        return Html("")
    rows = [
        (label, sentence(str(note[key])))
        for key, label in (("done", "Done"), ("next", "Next"), ("needs", "Needs"), ("stopped_at", "Stopped at"))
        if note.get(key)
    ]
    return el(
        "section",
        el("h2", "Where the work stopped", class_=heading_class),
        el(
            "p",
            "The agent's account, from the note in the last commit on ",
            el("code", note["branch"]),
            " (",
            el("code", note["commit"]),
            ").",
            class_="muted prose",
        ),
        el("p", "For ", el("span", home["id"], class_="id"), " ", title_button(home, "link-title", f"handoff-open-{slug(home['id'])}"))
        if home and heading_class == "h2"
        else "",
        facts(rows),
        class_="handoff",
        data_field="handoff",
        aria_label="Where the work stopped",
    )


def stale_rows(item: dict) -> list[Html]:
    """A row whose last test run was for another commit than the head: the flag, and the command to run first, in its own box."""
    if not stale(item):
        return []
    then = command("aidd", "test", "--spec", item_ref(item))
    return [
        el("p", el("span", icon("warn"), stale_text(item["evidence"]), class_="flag flag-pending"), class_="why"),
        el("p", "Run in a terminal, or ask your agent", class_="run"),
        words_box("the tests", then, f"need-test-{slug(item['id'])}", field="test-words", next_step=True),
    ]


def late_rows(answer: dict) -> list[Html]:
    rows = []
    for d in answer.get("due", []):
        stem = str(d["path"]).rsplit("/", 1)[-1].removesuffix(".md")
        rows.append(
            late_row(
                PLAIN_HEADING.get(str(d["next"].get("code")), "Past due"),
                sentence(str(d["what"])),
                str(d["path"]),
                (f"due-copy-{slug(stem)}", str(d["next"].get("words", ""))),
                what_of(d["next"]),
            )
        )
    for u in answer.get("unreadable", []):
        path = str(u["path"])
        words = command("aidd", "validate", path)
        rows.append(unreadable_row(u, (f"due-copy-{slug(path)}", words)))
    return rows


def unreadable_row(u: dict, copy: tuple[str, str]) -> Html:
    """A file aidd cannot read: what is wrong, and the command whose run shows the problem. The path is in the command."""
    testid, words = copy
    return el(
        "li",
        el("p", el("span", icon("warn"), "Unreadable", class_="flag flag-warn"), " ", f"aidd can't read this file: {u['error']}."),
        el("p", "Run it to see the problem; an agent fixes it", class_="why"),
        words_box(str(u["path"]), words, testid),
        class_="due-row",
        data_late=True,
    )


def late_row(kind: str, what: str, path: str, copy: tuple[str, str], who: str) -> Html:
    """A past-due or unreadable item; `copy` is the test id and the words of its button."""
    testid, words = copy
    return el(
        "li",
        el("p", el("span", icon("warn"), kind, class_="flag flag-warn"), " ", what),
        el("p", el("code", path), " ", el("span", who, class_="muted"), class_="why"),
        words_box(path, words, testid) if words else "",
        class_="due-row",
        data_late=True,
    )


def needs_empty(answer: dict, foot_html: Html) -> Html:
    """The empty project: its one next step with its words, where the work on this branch stopped, and what each view will
    hold."""
    step = answer.get("next") or {}
    words = str(step.get("words") or "")
    return view(
        "needs-you",
        el(
            "div",
            el(
                "header",
                el("h1", "Nothing is open yet", tabindex="-1"),
                el(
                    "p",
                    "This project has no Spec or Intent. Describe the next change to your agent, and it writes the first Spec.",
                    class_="lead prose",
                ),
                class_="head",
            ),
            words_box("the next change", words, "empty-copy") if words else "",
            handoff_section(answer.get("handoff"), None),
            el("h2", "What each view will hold", class_="h2"),
            el(
                "dl",
                el("dt", "Needs you"),
                el("dd", "What waits for a person, each with the words to copy."),
                el("dt", "Board"),
                el("dd", "Each open Spec in a column for its loop step."),
                el("dt", "Tree"),
                el("dd", "Each Intent with what is finished and left."),
                class_="views-help",
            ),
            class_="page empty",
        ),
        foot_html,
        label="Needs you",
    )


def needs_view(answer: dict, items: list[dict], foot_html: Html) -> Html:
    questions = answer.get("explorations") or []
    if not items and not answer.get("due") and not answer.get("unreadable") and not questions:
        return needs_empty(answer, foot_html)
    by_id = {i["id"]: i for i in items}
    people = [i for i in items if step_of(i).get("who") == "person"]
    people.sort(key=lambda i: (NEEDS_ORDER.index(step_of(i)["code"]) if step_of(i)["code"] in NEEDS_ORDER else len(NEEDS_ORDER), not stale(i)))
    late = late_rows(answer)
    body: list[object] = [
        el(
            "header",
            el(
                "h1",
                "Needs you ",
                el("span", len(people) + len(questions), class_="count", data_field="count", data_counts="[data-need]:not([hidden])"),
                tabindex="-1",
            ),
            el("p", needs_lead(answer, items), class_="lead"),
            team_filter(answer, items, needing=True) if people or questions else "",
            class_="head",
        )
    ]
    if people or questions:
        body.append(
            el(
                "p",
                el("kbd", "J"),
                el("kbd", "K"),
                " move, ",
                el("kbd", "Enter"),
                " opens, ",
                el("kbd", "C"),
                " copies the words, ",
                el("kbd", "?"),
                " lists every key.",
                class_="box keys-hint js-only",
                data_testid="keys-hint",
            )
        )
        rows = [need_row(i, bool(answer.get("delivery_teams"))) for i in people] + [question_row(q, by_id) for q in questions]
        body.append(el("ol", rows, class_="needs"))
    elif not any(is_emergency(i) for i in items) and root_blocker(answer):
        # With nothing for a person, the lead has said so once; the box exists only to give the answer's root blocker.
        body.append(
            el(
                "div",
                icon("check"),
                el("div", el("p", root_blocker(answer), class_="clear-h")),
                class_="state state-empty clear",
                data_testid="needs-you-all-clear",
            )
        )
    note = answer.get("handoff")
    body.append(handoff_section(note, branch_item(items, str(note["branch"])) if note else None))
    if late:
        body.append(el("h2", "Past due or unreadable ", el("span", len(late), class_="count"), class_="h2"))
        body.append(el("ol", late, class_="due"))
    body.append(el("p", el("button", "See the Board", type="button", class_="link", data_go="board", data_testid="needs-to-board"), class_="more"))
    return view("needs-you", el("div", *body, class_="page"), foot_html, label="Needs you")


# The Board ---------------------------------------------------------------------------------------------------------------------


def card(item: dict) -> Html:
    code = str(step_of(item).get("code", ""))
    kind = (
        " card-emergency"
        if is_emergency(item)
        else " card-blocked"
        if code == "spec.blocked"
        else " card-needs"
        if step_of(item).get("who") == "person"
        else ""
    )
    teams = teams_of(item)
    label = step_label(item)
    return el(
        "li",
        title_button(item, "card-title", f"card-{slug(item['id'])}"),
        el(
            "p",
            el("span", item["id"], class_="id"),
            flags(item),  # a state before the team, so a narrow card never clips it
            el("span", ", ".join(map(team_label, teams))) if teams else "",
            el("span", label, class_="step") if label else "",
            class_="card-meta",
        ),
        class_="card" + kind,
        data_card=item["id"],
        data_teams=" ".join(teams),
        data_intent=item.get("parent", ""),
    )


def done_count(items: list[dict]) -> tuple[int, int]:
    """How many items are finished, and in how many Intents. The answer lists open work, so only an Intent's progress knows
    how many of its children are finished: a finished Spec with no Intent is not counted, and with no Intent that has progress
    there is no number at all."""
    owners = [i for i in items if i["type"] == "intent" and i.get("progress")]
    return sum(e["progress"]["finished"] for e in owners), len(owners)


def finished_note(items: list[dict]) -> str:
    """ "; 7 more are finished in their Intents" when an Intent knows, else nothing: never a second number from nowhere."""
    done, owners = done_count(items)
    return f"; {done} more {'is' if done == 1 else 'are'} finished in their Intents" if owners else ""


def done_cell(items: list[dict], tag: str = "section") -> Html:
    n, owners = done_count(items)
    return el(
        tag,
        el("h2", "Done", class_="col-head", id=None) if tag == "section" else "",
        el("p", n, class_="done-n") if owners else "",
        el("p", f"finished in {plural(owners, 'Intent')}" if owners else "", class_="muted") if owners else "",
        el("p", "Finished Specs with no Intent aren't counted here.", class_="muted"),
        el("button", "See each Intent's progress in the Tree", type="button", class_="link", data_go="tree", data_testid="done-to-tree") if owners else "",
        class_="col col-done",
        data_column="done" if tag == "section" else None,
        data_cell="done" if tag == "div" else None,
    )


def columns_of(layout: str) -> list[tuple[str, str, tuple[str, ...]]]:
    if layout == "steps":
        return [(k, n, s) for k, n, s in STEP_COLUMNS]
    return [(k, n, ()) for k, n in GROUP_COLUMNS]


def in_column(item: dict, layout: str, key: str) -> bool:
    return column_of(item) == key if layout == "steps" else item.get("group") == key


def steps_strip(name: str, layout: str, specs: list[dict]) -> Html:
    """Below a desktop's width, a button for each column, with its count, that scrolls the Board to it."""
    links = [
        el("a", n, " ", el("span", sum(in_column(i, layout, k) for i in specs), class_="count"), href=f"#{name}-{k}", class_="btn", data_testid=f"strip-{k}")
        for k, n, _ in columns_of(layout)
    ]
    done = el("a", "Done", href=f"#{name}-done", class_="btn", data_testid="strip-done")
    return el("nav", links, done, class_="steps-strip", aria_label="Columns")


def board_layout(layout: str, rows: str, items: list[dict], answer: dict, specs: list[dict]) -> Html:
    cols = columns_of(layout)
    name = f"{layout}-{rows}"
    strip = steps_strip(name, layout, specs)
    if rows == "one":
        sections = [
            el(
                "section",
                el("h2", n, " ", el("span", len(mine := [i for i in specs if in_column(i, layout, k)]), class_="count"), class_="col-head"),
                el("ol", [card(i) for i in mine], class_="cards"),
                class_="col",
                id=f"{name}-{k}",
                data_column=k,
            )
            for k, n, _ in cols
        ]
        return el("div", strip, el("div", sections, done_cell(items), class_="cols"), class_="board-layout", data_board=name)
    lanes = []
    names = [*(answer.get("delivery_teams") or [])]
    if any(not teams_of(i) for i in specs):
        names.append("")
    for team in names:
        mine = [i for i in specs if (team in teams_of(i) if team else not teams_of(i))]
        cells = [
            el(
                "div",
                el("span", n, class_="lane-step"),
                el("ol", [card(i) for i in mine if in_column(i, layout, k)], class_="cards"),
                class_="lane-cell",
                data_cell=k,
            )
            for k, n, _ in cols
        ]
        owned = ", ".join(i["id"] for i in items if i["type"] == "intent" and team in teams_of(i))
        lanes.append(
            el(
                "section",
                el("h2", team_label(team) if team else "No team", el("span", owned, class_="intent") if owned else "", class_="lane-name"),
                cells,
                el("div", el("span", "Done", class_="lane-step"), class_="lane-done", data_cell="done"),
                class_="lane",
                data_lane=team,
                data_teams=team,
            )
        )
    head = el("div", [el("span", n) for _, n, _ in cols], el("span", "Done"), class_="lanes-head")
    return el("div", el("div", head, lanes, class_="lanes"), class_="board-layout", data_board=name)


def board_lead(open_specs: int, items: list[dict]) -> str:
    """How many Specs are open and, when an Intent knows, how many more are finished in their Intents."""
    return plural(open_specs, "open Spec") + finished_note(items)


def board_options(answer: dict, items: list[dict], teams: bool, owners: list[dict]) -> Html:
    """The Board's switches: the columns, the rows, the team, and the Intent."""
    return el(
        "div",
        el(
            "div",
            el("button", "Loop steps", type="button", aria_pressed="true", data_set="columns=steps", data_testid="columns-steps"),
            el("button", "Status groups", type="button", aria_pressed="false", data_set="columns=groups", data_testid="columns-groups"),
            class_="seg",
            role="group",
            aria_label="Columns",
        ),
        el(
            "div",
            el("button", "One board", type="button", aria_pressed="true", data_set="rows=one", data_testid="rows-one"),
            el("button", "A lane per team", type="button", aria_pressed="false", data_set="rows=team", data_testid="rows-team"),
            class_="seg",
            role="group",
            aria_label="Rows",
        )
        if teams
        else "",
        team_filter(answer, items),
        el(
            "select",
            el("option", "All Intents", value=""),
            [el("option", f"{e['id']} {e['title']}", value=e["id"]) for e in owners],
            class_="select",
            aria_label="Intent",
            data_testid="intent-filter",
        )
        if owners
        else "",
        class_="opts",
    )


def board_view(answer: dict, items: list[dict], foot_html: Html) -> Html:
    specs = [i for i in items if i["type"] == "spec" and i.get("group") in OPEN]
    if not items:
        words = str((answer.get("next") or {}).get("words") or "")
        return view(
            "board",
            el(
                "div",
                el(
                    "header",
                    el("h1", "Board", tabindex="-1"),
                    el("p", "The Board shows each open Spec in a column for its loop step. Nothing is open yet, so it has no columns.", class_="lead"),
                    class_="board-head",
                ),
                words_box("the next change", words, "board-empty-copy") if words else "",
                class_="board-wrap",
            ),
            foot_html,
            label="Board",
        )
    teams = bool(answer.get("delivery_teams"))
    owners = [i for i in items if i["type"] == "intent"]
    opts = board_options(answer, items, teams, owners)
    layouts = [board_layout(c, r, items, answer, specs) for c in ("steps", "groups") for r in (("one", "team") if teams else ("one",))]
    return view(
        "board",
        el(
            "div",
            el(
                "header",
                el("h1", "Board", tabindex="-1"),
                el("p", board_lead(len(specs), items), class_="lead"),
                el("span", class_="grow"),
                opts,
                el("button", "Board options", type="button", class_="btn opts-btn", aria_expanded="false", data_testid="board-options"),
                class_="board-head",
            ),
            layouts,
            class_="board-wrap",
        ),
        foot_html,
        label="Board",
    )


# The Tree ----------------------------------------------------------------------------------------------------------------------


def leaf(item: dict) -> Html:
    label = step_label(item)
    return el(
        "li",
        el("span", item["id"], class_="id"),
        title_button(item, "link-title", f"tree-open-{slug(item['id'])}"),
        el("span", flags(item), el("span", label, class_="muted") if label else "", class_="leaf-step"),
        class_="leaf",
        data_leaf=item["id"],
    )


def node_summary(kids: list[dict]) -> list[Html]:
    blocked = sum(step_of(k).get("code") == "spec.blocked" for k in kids)
    needing = sum(step_of(k).get("who") == "person" for k in kids) - blocked  # a blocked Spec is counted once, as blocked
    emergencies = sum(is_emergency(k) for k in kids)
    counts = [el("span", t, class_="flag flag-muted") for n, t in ((needing, f"{needing} need you"), (blocked, f"{blocked} blocked")) if n]
    return [*counts, el("span", icon("warn"), f"{emergencies} emergency", class_="flag flag-emergency")] if emergencies else counts


def node(item: dict, kids_of: dict[str, list[dict]], depth: int) -> Html:
    kids = kids_of.get(item["id"], [])
    progress = item.get("progress") or {"finished": 0, "of": 0}
    done, total = progress["finished"], progress["of"]
    open_ = [k for k in kids]
    children = [node(k, kids_of, depth + 1) for k in kids if k["type"] in GROUPING_TYPES]
    # Its phases show every slice, a planned one too; a Spec that names the Intent and is no slice is a leaf after them.
    phases = phases_list(item, {k["id"]: k for k in kids}, f"tree-{slug(item['id'])}")
    in_slices = {s["id"] for p in item.get("phases") or [] for s in p["slices"]}
    leaves = [leaf(k) for k in kids if k["type"] not in GROUPING_TYPES and k["id"] not in in_slices]
    if item.get("phases"):
        children.insert(0, el("li", phases, class_="phases-wrap"))
    toggle = bool(children or leaves)  # an Intent is the top of the Tree, and each one opens and closes
    ident = f"leaves-{item['id']}"
    label = f"{item['id']} {item['title']}"
    head = (
        el(
            "button",
            icon("right"),
            el("span", item["id"], class_="id"),
            title_span(item),
            type="button",
            class_="disc",
            aria_expanded="true",
            aria_controls=ident,
            data_testid=f"tree-toggle-{slug(item['id'])}",
            data_toggle=item["id"],
        )
        if toggle
        else el("span", el("span", item["id"], class_="id"), " ", title_span(item), class_="disc disc-static")
    )
    return el(
        "li",
        el(
            "div",
            head,
            el("progress", f"{done} of {total}", max=max(total, 1), value=done, aria_label=f"{label}: {done} of {total} finished"),
            el("span", f"{done} of {total} finished" if total else "Nothing in it yet", class_="node-prog", data_field="progress"),
            el("span", f"{total - done} left" if total else "", class_="node-left muted"),
            el("span", node_summary(open_), class_="node-flags"),
            class_="node-row",
        ),
        el("ul", children, el("li", el("ul", leaves, class_="leaves"), class_="leaves-wrap") if leaves else "", class_="intents", id=ident)
        if (children or leaves)
        else "",
        class_="node",
        data_node=item["id"],
    )


def reached(top: list[dict], kids_of: dict[str, list[dict]]) -> set[str]:
    seen: set[str] = set()
    todo = list(top)
    while todo:
        i = todo.pop()
        if i["id"] not in seen:
            seen.add(i["id"])
            todo += kids_of.get(i["id"], [])
    return seen


def tree_view(answer: dict, items: list[dict], foot_html: Html) -> Html:
    if not items:
        words = str((answer.get("next") or {}).get("words") or "")
        return view(
            "tree",
            el(
                "div",
                el(
                    "header",
                    el("h1", "Tree", tabindex="-1"),
                    el("p", "The Tree shows each Intent with its Specs. Nothing is open yet.", class_="lead"),
                    class_="head",
                ),
                words_box("the next change", words, "tree-empty-copy") if words else "",
                class_="page page-wide tree-page",
            ),
            foot_html,
            label="Tree",
        )
    ids = {i["id"] for i in items}
    kids_of: dict[str, list[dict]] = {}
    top: list[dict] = []
    for i in items:
        parent = i.get("parent")
        (kids_of.setdefault(str(parent), []) if parent in ids and parent != i["id"] else top).append(i)
    # An item in a loop of parents, or one that names itself, is reachable from no top: it becomes one, so none drops out.
    while (lost := next((i for i in items if i["id"] not in reached(top, kids_of)), None)) is not None:
        kids_of[str(lost.get("parent"))].remove(lost)
        top.append(lost)
    grouping = [i for i in top if i["type"] in GROUPING_TYPES]
    loose = [i for i in top if i["type"] not in GROUPING_TYPES]
    open_specs = sum(i["type"] == "spec" and i.get("group") in OPEN for i in items)
    kinds = [plural(n, name) for name in ("Intent",) if (n := sum(i["type"] == name.lower() for i in items))]
    lead = (" and ".join(kinds) + ". " if kinds else "") + board_lead(open_specs, items) + "."
    body = [el("ul", [node(c, kids_of, 0) for c in grouping], class_="tree")] if grouping else []
    for group, title, note in (
        ([i for i in loose if i["type"] == "spec"], "No Intent yet", "Specs with no Intent yet. When you plan an Intent, its Specs group under it here."),
        ([i for i in loose if i["type"] == "proposal"], "Proposals", "Proposals wait for a decision before they become an Intent."),
    ):
        if group:
            body.append(
                el(
                    "div",
                    el("h2", title, class_="h2"),
                    el("p", note, class_="muted"),
                    el("ul", [leaf(i) for i in group], class_="leaves flat"),
                    class_="tree-loose",
                    data_node="none" if title == "No Intent yet" else "proposals",
                )
            )
    return view(
        "tree",
        el("div", el("header", el("h1", "Tree", tabindex="-1"), el("p", lead, class_="lead"), class_="head"), *body, class_="page page-wide tree-page"),
        foot_html,
        label="Tree",
    )
