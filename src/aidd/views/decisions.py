"""The decisions page: every step `aidd list` gave, a person's decisions first, each with who decides and how."""

from __future__ import annotations

import shlex

from aidd import workitems
from aidd.views import html_parts, markdown_html

# The page each kind of decision has, as the command that writes it; a decision with none is read in its file.
_DECISION_PAGES = {
    "spec.spec_approval": "aidd hash {where} --summary --html",
    "spec.in_review": "aidd gate --spec {where} --html",
}


def _step_card(s: dict, n: int) -> html_parts.Html:
    rows: list[tuple[str, object]] = [
        ("Who", s.get("who")),
        ("Where", html_parts.el("code", s["where"]) if s.get("where") else None),
        ("Status", s.get("status")),
        ("Approvers", ", ".join(s.get("approvers") or [])),
        ("Waiting", f"{s['waiting_minutes']} minutes" if s.get("waiting_minutes") is not None else None),
    ]
    page_cmd = _DECISION_PAGES.get(str(s.get("code")))
    return html_parts.el(
        "article",
        html_parts.el("h3", s.get("what") or s.get("code")),
        html_parts.facts(rows),
        html_parts.el("p", markdown_html.inline(str(s.get("how") or ""))),
        html_parts.join(html_parts.el("p", "Its page:", class_="muted"), html_parts.copyable(f"page-{n}", page_cmd.format(where=shlex.quote(str(s["where"])))))
        if page_cmd and s.get("where")
        else "",
    )


def decision_page(steps: list[dict], title: str = "Decisions waiting on you") -> str:
    """Every step `aidd list` gave, a person's decisions first, each with who decides, how, and the command that writes
    its own page. Like every view, it holds no form and approves nothing: a decision is made where its `how` says."""

    # By the step-code contract, never the `who` text: an owner shows as an email or "@x's agent" there.
    people = [s for s in steps if s.get("code") != "lane" and workitems.STEP_CODES.get(str(s.get("code")), "author") != workitems.AGENT]
    rest = [s for s in steps if s not in people]
    sections = [
        html_parts.Section(
            "decisions",
            f"Decisions ({len(people)})",
            html_parts.el("div", [_step_card(s, i) for i, s in enumerate(people)], class_="cards")
            if people
            else html_parts.el("p", "No decision waits.", class_="muted"),
        )
    ]
    if rest:
        sections.append(
            html_parts.Section(
                "work", f"Other open work ({len(rest)})", html_parts.el("div", [_step_card(s, len(people) + i) for i, s in enumerate(rest)], class_="cards")
            )
        )
    lead = "Each decision says who takes it and how. Decide each one where its how says; the page itself records nothing."
    return html_parts.page(
        title, sections, lead=lead, badge=html_parts.badge("pending", f"{len(people)} waiting") if people else html_parts.badge("pass", "nothing waits")
    )
