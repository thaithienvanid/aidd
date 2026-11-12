"""The work-items page's Search and keyboard views. The script shows the results that match; with scripts off every row shows."""

from __future__ import annotations

from aidd.views.html_parts import Html, el
from aidd.views.work_parts import icon, slug, status_name, step_label, title_button, view


def result_words(item: dict) -> list[object]:
    """A result's status, as its file holds it, then its step; a step that starts with the status says it once."""
    status, step = status_name(item), step_label(item)
    if step.startswith(status):
        return [step]
    return [el("span", status, data_field="status"), f", {step}" if step else ""]


def search_results(items: list[dict]) -> list[Html]:
    """A row for each item; the script shows the ones that match the query."""
    return [
        el(
            "li",
            el(
                "p",
                el("span", i["id"], class_="id"),
                title_button(i, "link-title", f"result-{slug(i['id'])}"),
                class_="result-head",
            ),
            el("p", *result_words(i), class_="muted"),
            class_="result",
            data_result=i["id"],
        )
        for i in items
    ]


def search_view(items: list[dict], foot_html: Html) -> Html:
    results = search_results(items)
    return view(
        "search",
        el(
            "div",
            el("header", el("h1", "Search", tabindex="-1"), class_="head"),
            el(
                "div",
                icon("search"),
                el(
                    "input",
                    type="search",
                    aria_label="Search by id or title",
                    placeholder="Search by id or title",
                    autocomplete="off",
                    class_="field",
                    data_testid="search-input",
                ),
                class_="search-field",
            ),
            el(
                "p",
                "Finds ids, and words in titles in any script. Case and accents don't matter, so thong bao finds thông báo.",
                class_="hint",
            ),
            el("p", "", class_="results-count", role="status", data_testid="search-status"),
            el("ol", results, class_="results"),
            class_="page search-page",
        ),
        foot_html,
        label="Search",
    )


# Each key, what it does, and whether the switch for single keys turns it off (Enter, Esc, and Tab keep working).
KEYS = (
    ("/", "Search by id or title", True),
    ("1, 2, 3", "Open Needs you, the Board, or the Tree", True),
    ("J, K", "The next or previous item", True),
    ("C", "Copy the item's words", True),
    ("Enter", "Open the item", False),
    ("Esc", "Close the search or this list, or go back from an item", False),
    ("?", "Show this list", True),
)


def keys_table() -> Html:
    """Each key, what it does, and whether it acts now: the switch for single keys turns the others off."""
    rows = [
        el(
            "tr",
            el("th", el("kbd", k)),
            el("td", what),
            el("td", el("span", "On", class_="is-on"), el("span", "Off", class_="is-off"), class_="now") if single else el("td", "On", class_="now-always"),
        )
        for k, what, single in KEYS
    ]
    return el("table", el("thead", el("tr", el("th", "Key"), el("th", "What it does"), el("th", "Now"))), el("tbody", rows), class_="keys")


def keys_view(foot_html: Html) -> Html:
    return view(
        "keys",
        el(
            "div",
            el(
                "div",
                el(
                    "header",
                    el("h1", "Keyboard shortcuts", tabindex="-1"),
                    el(
                        "button",
                        icon("close"),
                        el("span", "Close the shortcuts", class_="sr-only"),
                        type="button",
                        class_="btn btn-quiet btn-icon",
                        data_go="back",
                        data_testid="keys-close",
                    ),
                    class_="dialog-head",
                ),
                el(
                    "div",
                    el(
                        "button",
                        el("span", "Single-key shortcuts"),
                        el("span", el("span", "On", class_="is-on"), el("span", "Off", class_="is-off"), class_="switch-state"),
                        type="button",
                        role="switch",
                        aria_checked="true",
                        class_="switch",
                        data_testid="keys-single-off",
                        aria_describedby="keys-hint",
                    ),
                    el(
                        "p",
                        "Turn them off if you use speech input or your screen reader's own keys. Enter, Esc, and Tab keep working. This browser remembers your choice.",
                        class_="muted",
                        id="keys-hint",
                    ),
                    keys_table(),
                    el("p", "Shortcuts never fire while you type in a field, such as Search.", class_="muted"),
                    class_="dialog-body",
                ),
                class_="dialog",
            ),
            class_="page keys-page",
        ),
        foot_html,
        label="Keyboard shortcuts",
    )
