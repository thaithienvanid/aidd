"""The work-items page (`aidd status --html`): the open work as one read-only page, from the answer `aidd status --json` gives.

A top bar with the views' tabs, an emergency banner above every view, Needs you, the Board, the Tree, Search, the keys, and an
item page for each work item. Python renders every view's markup, escaped by `el`, so with scripts off the page reads as one
scroll. The script (`work_item_page.js`) only shows one view at a time, filters by `data-*`, folds search text, moves focus,
copies, and keeps the state in the URL. The page writes nothing: every action is words to copy, and a decision stays in the chat.

Its look is the design system of aidd's built-in pages (`system_css`), then its own layout in `work_item_page.css`. The
Content-Security-Policy
names the one style and the one script by hash, loads nothing, and lets nothing fetch.
"""

from __future__ import annotations

import datetime as dt

from aidd import config
from aidd.kernel import resources
from aidd.views.html_parts import Html, csp_hash, el, esc, page_style, utc_offset, written_texts
from aidd.views.work_item_detail import item_view, review_overdue, when
from aidd.views.work_parts import (
    UNKNOWN_BLOCK,
    command,
    copy_button,
    emergency_facts,
    emergency_incomplete,
    foot,
    icon,
    is_emergency,
    one_line,
    place_unknown,
    slug,
    sprite,
    step_of,
    title_button,
)
from aidd.views.work_search import keys_view, search_view
from aidd.views.work_views import board_view, handoff_section, needs_view, tree_view
from aidd.workitems import branch_item

# The top views, in the tab row. The Tree lists each Intent's phases and slices, each with its stage. A fourth tab would
# take the key 4: the tab row holds four tabs at 320 px wide with no scroll, as test_work_page_layout checks.
TABS = (("needs-you", "Needs you"), ("board", "Board"), ("tree", "Tree"))


def banner_fold(item: dict, left: str, ident: str) -> Html:
    """The banner on a narrow screen: one line, and a button that opens the words."""
    return el(
        "p",
        icon("warn"),
        el("span", f"Emergency: {item['id']}" + (f", {left}" if left else "")),
        el(
            "button",
            "Words",
            el("span", f" to copy for {item['id']}", class_="sr-only"),
            icon("down"),
            type="button",
            class_="btn btn-fold",
            aria_expanded="false",
            aria_controls=ident,
            data_testid="emergency-fold",
        ),
        class_="banner-fold",
    )


def commander_line(facts: dict[str, tuple[str, str]]) -> str:
    state, value = facts["commander"]
    return {"ok": f"{value} leads the incident", "absent": "No commander is named", "invalid": "The commander has a value aidd can't read"}[state]


def banner(item: dict, today: dt.date) -> Html:
    """One emergency, above every view, always: its icon and the word Emergency carry it, never color alone. Each good field shows;
    a field that is absent or unreadable says so, and an incomplete block says how to see the problem."""
    facts = emergency_facts(item)
    state, due_text = facts["backfill_due"]
    gap: int | None = None
    if state == "ok":
        try:
            gap = (dt.date.fromisoformat(due_text) - today).days
        except ValueError:
            state = "invalid"
    overdue = gap is not None and review_overdue(item)
    # A date, never "in 2 days": the page is read after it is written, and a date stays true.
    due = when(due_text, today) if gap is not None else ""
    left = "" if gap is None else "review overdue" if overdue else f"review due {due}"
    if gap is None:
        review = "Review due: not set" if state == "absent" else "Review due: can't be read"
    else:
        review = f"Review overdue: it was due {due}" if overdue else f"Review due {due}"
    ident = f"banner-{slug(item['id'])}"
    words = str(step_of(item).get("words") or "")
    path = str(item.get("path", ""))
    return el(
        "div",
        banner_fold(item, left, ident),
        el(
            "div",
            el("p", icon("warn"), el("span", "Emergency"), class_="banner-label"),
            el("p", el("span", item["id"], class_="id"), title_button(item, "link", "emergency-open"), class_="what"),
            el("p", el("span", commander_line(facts)), el("span", review), class_="banner-facts") if not place_unknown(item) else "",
            el(
                "p",
                (UNKNOWN_BLOCK if place_unknown(item) else "Its emergency block is incomplete: run") + " ",
                el("code", command("aidd", "validate", path)),
                " in that branch" if place_unknown(item) else "",
                class_="banner-facts",
                data_field="incomplete",
            )
            if place_unknown(item) or emergency_incomplete(item)
            else "",
            el(
                "div",
                el("code", one_line(words), dir="auto"),
                copy_button(item["id"], words, "emergency-copy"),
                class_="words end-words",
                data_component="words-to-copy",
            )
            if words
            else "",
            class_="banner-full",
            id=ident,
        ),
        class_="banner callout callout-emergency callout-overdue" if overdue else "banner callout callout-emergency",
        role="region",
        aria_label="Emergency",
        data_testid="emergency-banner",
        data_item=item["id"],
        data_overdue=str(overdue).lower(),
    )


def top_bar(written_short: str, project: str) -> Html:
    tabs = [el("a", name, href=f"#view-{key}", data_go=key, data_testid=f"tab-{key}") for key, name in TABS]
    return el(
        "header",
        el(
            "p",
            el("span", project, class_="product", data_field="product", dir="auto"),
            el("span", f"Written {written_short}", class_="written", data_testid="written"),
            class_="topbar-name",
        ),
        el("nav", tabs, class_="tabs", aria_label="Views"),
        el(
            "div",
            el(
                "button",
                icon("search"),
                el("span", "Search by id or title", class_="search-label"),
                el("kbd", "/", aria_hidden="true"),
                type="button",
                class_="search-btn js-only",
                data_go="search",
                aria_keyshortcuts="/",
                data_testid="search-open",
            ),
            el(
                "button",
                icon("keys"),
                type="button",
                class_="btn btn-quiet btn-icon js-only",
                data_go="keys",
                aria_label="Keyboard shortcuts",
                aria_keyshortcuts="?",
                data_testid="keys-open",
            ),
            class_="topbar-end",
        ),
        class_="topbar",
    )


def status_page(answer: dict, *, title: str = "The open work", written: dt.datetime | None = None, project: str = "", retry_limit: int | None = None) -> str:
    """The page for `answer`, the dict `aidd status` prints as JSON (schemas/status.schema.json). `written` is when the page
    was written, which it shows on every view, so a page left open never passes for the current state. `project` is the
    project's name, shown in the top bar."""
    now = written or dt.datetime.now()
    short, long_ = written_texts(now)
    today = now.date()
    items = list(answer.get("items", []))
    by_id = {i["id"]: i for i in items}
    foot_html = foot(long_, utc_offset(now))
    banners = [banner(i, today) for i in items if is_emergency(i)]
    note = answer.get("handoff")
    home = branch_item(items, str(note["branch"])) if note else None
    views = [
        needs_view(answer, items, foot_html),
        board_view(answer, items, foot_html),
        tree_view(answer, items, foot_html),
        search_view(items, foot_html),
        keys_view(foot_html),
        *[
            item_view(
                {**i, "retry_limit": config.EMPTY.max_task_retries if retry_limit is None else retry_limit},
                by_id,
                today,
                questions=tuple(q for q in answer.get("explorations") or [] if q.get("item") == i["id"]),
                handoff=handoff_section(note, home, "sec") if home is i else None,
            )
            for i in items
        ],
    ]
    style = page_style(resources.package_text("aidd.views", "work_item_page.css"))
    script = resources.package_text("aidd.views", "work_item_page.js")
    policy = (
        f"default-src 'none'; style-src {csp_hash(style)}; img-src data:; script-src {csp_hash(script)}; "
        "require-trusted-types-for 'script'; base-uri 'none'; form-action 'none'"
    )
    body = [
        sprite(),
        el("a", "Skip to the page", href="#main", class_="skip"),
        top_bar(short, project or "project"),
        el("main", *banners, *views, id="main", tabindex="-1"),
        el("p", "", class_="toast", role="status", data_testid="copy-status"),
    ]
    return (
        "<!doctype html>\n"
        + str(
            Html(
                '<html lang="en">'
                f'<head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{esc(policy)}">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f"<title>{esc(title)}</title><style>{style}</style></head>"
                f"<body>{''.join(str(b) for b in body)}<script>{script}</script></body></html>"
            )
        )
        + "\n"
    )
