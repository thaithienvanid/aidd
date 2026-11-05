"""The work-items page's item page: what moves the item first, then its Tasks, evidence, and history, with the details beside
them. Every value is from the status answer, so the page and `aidd status --json` agree on each item."""

from __future__ import annotations

import datetime as dt

from aidd.kernel import resources, timestamps
from aidd.views.html_parts import Html, el, join
from aidd.views.work_parts import (
    command,
    copy_button,
    emergency_facts,
    flags,
    icon,
    is_emergency,
    item_ref,
    one_line,
    phases_list,
    place_unknown,
    plural,
    slug,
    stale,
    stale_text,
    status_name,
    step_name,
    step_of,
    team_label,
    teams_of,
    view,
    what_of,
    why_line,
    words_box,
    words_of,
)
from aidd.workitems import is_id

TASK_STATES = {"todo": "Not started", "done": "Done", "stopped": "Blocked", "blocked": "Waits"}
# What the box above the Tasks says: a person must act, the work waits for other work, or someone moves it.
HEADINGS = {"spec.blocked": "Blocked: a person must act", "spec.blocked_by": "Waits for other work", "spec.emergency": "Restore service first"}


WAITS_FOR_BUILD = ("spec.planned", "spec.draft", "spec.consumers", "spec.ask_approval", "spec.approve")


def waits_note(item: dict) -> str:
    """Which work the item's Implement waits for, from `blocked_by` and never from the words of its step: the Spec is still
    written or asked about, and only building it waits."""
    waits = item.get("blocked_by") or []
    return f"Implement waits for {', '.join(waits)}." if waits and step_of(item).get("code") in WAITS_FOR_BUILD else ""


def heading(item: dict, today: dt.date) -> str:
    step = step_of(item)
    code = str(step.get("code", ""))
    if stale(item):
        return "Run the tests again first"
    if code == "spec.emergency" and review_overdue(item):
        return "The review is overdue"
    if code in HEADINGS:
        return HEADINGS[code]
    if step.get("who") == "person":
        return f"Waits for {step_name(item)}" if code in ("spec.approve", "pr.merge") else f"Needs {step.get('person') or 'a person'}"
    if step.get("who") == "agent":
        return "Your agent builds it" if code in ("spec.in_progress", "spec.approved") else "Your agent moves it"
    return "Nothing to do" if step else "No next step yet"


def review_overdue(item: dict) -> bool:
    """Whether the emergency's backfill is overdue, as `aidd status` read it (`backfill_overdue`), so the page and `aidd validate`
    never disagree: an item without the answer is never overdue."""
    return item.get("backfill_overdue") is True


def when(day: str, today: dt.date) -> str:
    """A date as `Mon 9 Nov`, with the year when it is not the page's; a text that is no date, as it is. Never "in 2 days":
    the page is read after it was written, and a relative phrase would freeze wrong, while the date stays true."""
    try:
        d = dt.date.fromisoformat(day)
    except ValueError:
        return day or "no date"
    return f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if d.year != today.year else "")


def nice_time(stamp: str, today: dt.date) -> str:
    """A time as `7 Nov, 11:20` in local time, as the page's own written time is, with the year when it is not the page's
    (`7 Nov 2025, 11:20`); a text that is no time, as it is."""
    try:
        t = dt.datetime.strptime(stamp, timestamps.UTC_FORMAT).replace(tzinfo=dt.UTC).astimezone()
    except ValueError:
        return stamp
    return f"{t.day} {t:%b}" + (f" {t.year}" if t.year != today.year else "") + f", {t:%H:%M}"


def evidence_line(ev: dict, today: dt.date) -> str:
    when_ = nice_time(str(ev["at"]), today) if "T" in str(ev["at"]) else str(ev["at"])
    dirty = (
        " It ran in a tree with uncommitted changes" + (", so commit or stash them and run it again." if ev["result"] != "partial" else ".")
        if ev.get("dirty_tree")
        else ""
    )
    revised = (
        f" The change revises {', '.join(ev['revised_frozen'])} and rewrites files it froze, which the run passed with a note: the person who approves reads the revision and approves again."
        if ev.get("revised_frozen")
        else ""
    ) + (" The repository suite ran as its smoke set alone, because a Spec of this change has the emergency route." if ev.get("emergency_subset") else "")
    if ev["result"] == "partial":
        return f"aidd test ran only a quick check, on part of the suite or with the red run skipped (commit {ev['commit']}, at {when_}), so it is not evidence for the head.{dirty}{revised}"
    if ev["result"] == "untested":
        return f"aidd test ran no test, because no test command applies to the paths this change touched (commit {ev['commit']}, at {when_}), so nothing here shows it works.{dirty}{revised}"
    ran = {"passed": "passed", "failed": "failed"}[ev["result"]]
    where = f"on {ev['commit']}" + (
        ", the head"
        if ev["commit"] == ev["head"]
        else f", {plural(ev['behind'], 'commit')} behind the head {ev['head']}"
        if ev.get("behind")
        else f"; the head is {ev['head']}"
    )
    return f"aidd test {ran} {where}, at {when_}.{dirty}{revised}"


def next_box(item: dict, today: dt.date) -> Html:
    step, ev = step_of(item), item.get("last_test_run") or {}
    is_stale = stale(item)
    words, person = words_of(item), str(step.get("person") or "")
    kind = "next-blocked" if step.get("code") == "spec.blocked" else "next-emergency" if is_emergency(item) else "next-stale" if is_stale else ""
    parts: list[object] = [el("h2", heading(item, today))]
    if is_stale:
        parts.append(el("p", el("span", icon("warn"), stale_text(ev), class_="flag flag-pending"), " Only a run on the head counts."))
        then = command("aidd", "test", "--spec", item_ref(item))
        parts.append(el("p", "Run in a terminal, or ask your agent", class_="run"))
        parts.append(
            el("div", el("code", one_line(then), data_field="then-words"), copy_button("the tests", then, "item-copy-then", primary=True), class_="words")
        )
    if step.get("what"):
        parts.append(el("p", what_of(step) if step.get("code") != "spec.blocked_by" else waiting_what(item), class_="prose", data_field="what"))
    note = waits_note(item)
    if note and note.rstrip(".") not in str(step.get("what", "")):  # the step's own words may already say it
        parts.append(el("p", note, class_="prose", data_field="waits-note"))
    if person:
        parts.append(el("p", f"Waits for {person}", data_field="person", data_person=person))
    parts.append(why_line(step))
    if words:
        if is_stale:
            parts.append(el("p", "Then say to your agent", class_="run"))
        parts.append(
            el(
                "div",
                el("code", one_line(words), dir="auto", data_field="words"),
                copy_button(item["id"], words, "item-copy", primary=not is_stale),
                class_="words",
                data_component="words-to-copy",
            )
        )
    return el("div", *parts, class_=f"box next-box {kind}".strip())


def question_section(question: dict) -> Html:
    """An open question in the item's folder: the pick a person owes, with its step, why, and words."""
    step = question["next"]
    words = str(step.get("words") or "")
    return el(
        "div",
        el("h2", "Open question", class_="sec"),
        el("p", question["question"], class_="question", dir="auto", data_field="question"),
        el("p", what_of(step), class_="prose"),
        why_line(step),
        words_box(question["question"], words, f"item-question-copy-{slug(str(question['path']))}", field="question-words") if words else "",
        el("p", "File ", el("code", question["path"]), class_="muted"),
        class_="question-sec",
    )


# The unsaved paths an item page names, as `aidd status` does; the count covers the rest.
SHOWN_UNSAVED = 3


def unsaved_meaning() -> str:
    """Why work in no commit yet is the next step, as status.schema.json's `unsaved` says it, its one owner: the sentence
    after the one that says when the key is set."""
    meaning = resources.load_json("status.schema.json")["properties"]["items"]["items"]["properties"]["unsaved"]["description"]
    return str(meaning).split(". ", 1)[1]


def unsaved_section(item: dict) -> Html:
    """Work on the item's branch in no commit yet, with the next step its meaning gives: commit it there."""
    found = item.get("unsaved")
    if not found:
        return Html("")
    paths, count = list(found["paths"])[:SHOWN_UNSAVED], int(found["count"])
    words = f"Commit the unsaved work for {item['id']} on its branch" if is_id(item["id"]) else ""
    return el(
        "div",
        el("h2", "Unsaved work", class_="sec"),
        el(
            "p",
            f"{plural(count, 'file')} on ",
            el("code", found["branch"]),
            f" {'is' if count == 1 else 'are'} in no commit yet. {unsaved_meaning()}",
            class_="prose",
        ),
        el("ul", [el("li", el("code", path)) for path in paths], class_="paths"),
        el("p", f"and {count - len(paths)} more", class_="muted") if count > len(paths) else "",
        words_box(item["id"], words, "item-unsaved-copy", field="unsaved-words") if words else "",
        data_field="unsaved",
        data_count=count,
    )


def inline_code(text: str) -> Html:
    """A sentence with its `code` spans set as code; the text is escaped by `el`."""
    parts = text.split("`")
    return join(*[el("code", p) if n % 2 else p for n, p in enumerate(parts)])


def waits_flag(item: dict) -> Html:
    """The mark of a Spec that waits for other work, in a word and a shape: it is no one's move, so it is not Blocked."""
    waits = item.get("blocked_by") or []
    if step_of(item).get("code") != "spec.blocked_by" or not waits:
        return Html("")
    return el("span", icon("pause"), "Waits for " + ", ".join(waits), class_="flag flag-muted", data_flag="waits")


def waiting_what(item: dict) -> str:
    """What a Spec that waits for other work says, from `blocked_by`: it starts when they are done, and nobody acts on it now."""
    waits = item.get("blocked_by") or []
    if not waits:
        return what_of(step_of(item))
    return f"This Spec starts when {', '.join(waits)} {'is' if len(waits) == 1 else 'are'} done. Nobody needs to act on {item['id']} now."


def note(task: dict, item: dict) -> str:
    """What stands beside a Task that cannot go on: for a stopped one, the Spec's `waiting_on`, where the loop records why it
    stopped; else the Task's own reason."""
    if task["status"] == "stopped" and str(item.get("waiting_on") or "").strip():
        return str(item["waiting_on"])
    return str(task.get("why") or "") if task["status"] in ("stopped", "blocked") else ""


def task_state(status: str, label: str) -> Html:
    """A Task's state in words: Done and a stopped Task as flags, with a hue and an icon; the rest as muted text."""
    if status in ("done", "stopped"):
        hue, glyph = ("flag-pass", "check") if status == "done" else ("flag-strong", "block")
        return el("span", icon(glyph), label, class_=f"task-state flag {hue}")
    return el("span", label, class_="task-state")


def tasks_section(item: dict) -> Html:
    """The Tasks of a Spec. `item["retry_limit"]` is the retries a Task gets, which the page sets beside the answer's own keys."""
    rows = []
    for t in item.get("tasks") or []:
        status = t["status"]
        label = f"Blocked, {t['retry_count']} of {item['retry_limit']} retries" if status == "stopped" else TASK_STATES[status]
        rows.append(
            el(
                "li",
                el("span", t["id"], class_="id"),
                el("span", t["title"], class_="task-title", dir="auto"),
                task_state(status, label),
                el("p", note(t, item), class_="note" if t["status"] == "stopped" else "note note-wait") if note(t, item) else "",
                class_=f"task-{status}",
                data_task=t["id"],
                data_task_status=status,
                data_retries=t["retry_count"],
            )
        )
    return el("div", el("h2", "Tasks", class_="sec"), el("ol", rows, class_="tasks")) if rows else Html("")


# A run's result as a flag: its hue, icon, and word. Only a full run on the head has one: a partial run, or a run on another
# commit, is not evidence for the head, so its sentence says so with no Passed or Failed beside it.
RAN_FLAGS = {"passed": ("flag-pass", "check", "Passed"), "failed": ("flag-fail", "fail", "Failed")}
NO_EVIDENCE = "The page has no test run for this Spec. It reads only this worktree's last `aidd test` run, when that run answered to this Spec."


def evidence_section(item: dict, today: dt.date) -> Html:
    """The item's last test run; without one, a sentence that holds in every case: the run was for no Spec, for several, for
    another Spec, or there was none."""
    ev = item.get("last_test_run")
    if not ev:
        return el("div", el("h2", "Last test run", class_="sec"), el("p", inline_code(NO_EVIDENCE), class_="evidence muted prose", data_field="no-evidence"))
    ran = RAN_FLAGS.get(ev["result"]) if ev["commit"] == ev["head"] else None
    return el(
        "div",
        el("h2", "Last test run", class_="sec"),
        el(
            "p",
            el("span", icon(ran[1]), ran[2], class_=f"flag {ran[0]}") if ran else "",
            " " if ran else "",
            evidence_line(ev, today),
            class_="evidence prose",
            data_field="last-test-run",
            data_result=ev["result"],
            data_commit=ev["commit"],
            data_head=ev["head"],
            data_behind=ev.get("behind", ""),
        ),
    )


def history_section(item: dict, today: dt.date) -> Html:
    rows = [
        el(
            "li",
            el("span", nice_time(str(h["at"]), today), class_="muted"),
            el("span", h["what"]),
            el("span", h["type"], class_="h-type"),
        )
        for h in (item.get("history") or [])[:5]
    ]
    return el("div", el("h2", "History", class_="sec"), el("ol", rows, class_="history", data_field="history")) if rows else Html("")


def relations_section(item: dict, by_id: dict[str, dict]) -> Html:
    """What the item is blocked by (what it waits for) and what it blocks (the items that wait for it)."""

    def links(ids: list[str]) -> list[Html]:
        return [
            el(
                "li",
                el("a", w, href=f"#view-item-{w}", class_="link", data_go="item", data_item=w, data_testid=f"item-rel-{w.lower()}")
                if w in by_id
                else el("span", w, class_="id"),
                " ",
                by_id.get(w, {}).get("title", ""),
            )
            for w in ids
        ]

    waits = item.get("blocked_by") or []
    blocks = [i["id"] for i in by_id.values() if item["id"] in (i.get("blocked_by") or [])]
    return el(
        "div",
        el("h2", "Waits for", class_="sec") if waits else "",
        el("ul", links(waits), class_="rel", data_field="waits") if waits else "",
        el("h2", "Blocks", class_="sec") if blocks else "",
        el("ul", links(blocks), class_="rel", data_field="blocks") if blocks else "",
    )


def details(item: dict, today: dt.date) -> Html:
    rows: list[tuple[str, object]] = [("Status", el("span", status_name(item), data_field="status"))]
    if item.get("stage"):
        rows.append(("Stage", el("span", item["stage"], data_field="stage")))
    if item.get("route"):
        rows.append(("Route", str(item["route"]).capitalize()))
    if item.get("delivery_team"):
        rows.append(("Team", el("span", team_label(str(item["delivery_team"])), data_field="delivery-team")))
    elif teams_of(item):
        rows.append(("Team", ", ".join(map(team_label, teams_of(item)))))
    if item.get("owner"):
        rows.append(("Owner", el("span", item["owner"], data_field="owner")))
    if place_unknown(item):
        rows.append(("Emergency", "incomplete or differs by place: run " + command("aidd", "validate", str(item["path"])) + " in that branch"))
    elif is_emergency(item):
        facts = emergency_facts(item)
        gone = {"absent": "not named", "invalid": "has a value aidd can't read"}
        for label, key in (("Severity", "severity"), ("Type", "type"), ("Incident", "incident")):
            state, value = facts[key]
            if state != "absent" or key != "incident":  # an incident is optional: it is named only when it is there
                rows.append((label, value if state == "ok" else gone[state]))
        state, value = facts["commander"]
        rows.append(("Commander", el("span", value if state == "ok" else gone[state], data_field="emergency", data_commander=value)))
        state, value = facts["backfill_due"]
        rows.append(("Review due", when(value, today) if state == "ok" else "not set" if state == "absent" else "can't be read"))
    rows.append(("File", el("code", item["path"])))
    if item.get("places"):
        rows.append(("Held in", ", ".join(item["places"])))
    cells = [x for k, v in rows for x in (el("dt", k), el("dd", v))]
    return el("aside", el("h2", "Details", class_="sec"), el("dl", cells, class_="facts"), class_="item-aside")


def crumbs(item: dict, by_id: dict[str, dict]) -> str:
    chain, seen, parent = [], {item["id"]}, item.get("parent")
    while parent in by_id and parent not in seen:
        seen.add(parent)
        chain.append(f"{parent} {by_id[parent]['title']}")
        parent = by_id[parent].get("parent")
    return " / ".join(reversed(chain)) if chain else "No Intent"


def item_view(item: dict, by_id: dict[str, dict], today: dt.date, *, questions: tuple[dict, ...] = (), handoff: Html | None = None) -> Html:
    head = el(
        "section",
        el("button", icon("back"), "Back", type="button", class_="back", data_go="back", data_testid="item-back"),
        el("p", crumbs(item, by_id), class_="crumbs"),
        el("h1", item["title"], class_="item-title", dir="auto", tabindex="-1", data_field="title"),
        el(
            "p",
            el("span", item["id"], class_="id"),
            flags(item),
            waits_flag(item),
            el("span", ", ".join(map(team_label, teams_of(item)))) if teams_of(item) else "",
            class_="item-meta",
        ),
    )
    phases = el("div", el("h2", "Phases", class_="sec"), phases_list(item, by_id, f"item-{item['id']}")) if item.get("phases") else ""
    main = el(
        "div",
        next_box(item, today),
        phases,
        [question_section(q) for q in questions],
        unsaved_section(item),
        handoff,
        tasks_section(item),
        evidence_section(item, today),
        relations_section(item, by_id),
        history_section(item, today),
    )
    body = el("div", head, el("div", main, details(item, today), class_="item-grid"), class_="page page-wide item-page")
    step = step_of(item)
    return view(
        "item",
        body,
        label=item["title"],
        ident=f"view-item-{item['id']}",
        data_item=item["id"],
        data_status=item["status"],
        data_group=item["group"],
        data_step=step.get("code", ""),
        data_who=step.get("who", ""),
    )
