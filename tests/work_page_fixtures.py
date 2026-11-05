"""The work-items page's states, as `aidd status --json` answers (R377 brief, section 4).

A small online shop with three delivery teams: Checkout, Catalog, and Payments. Each state is a status answer that is valid
under the schema with its optional keys, built from the prototype's data, so the page tests compare the page with the
answer and nothing else. The page was written on `WRITTEN`.

    STATES: the names of the eight states, in the brief's order
    state(name) -> dict: that state's answer

Each step says why it comes next, as `aidd status` does, in the words the data that owns the reason gives
(`step_reasons`), so the page tests read the real lines.
"""

from __future__ import annotations

import copy
import datetime as dt

import helpers  # noqa: F401  (puts src on the path)

from aidd.workitems import step_reasons

WRITTEN = dt.datetime(2026, 11, 7, 12, 40)
TEAMS = ["checkout", "catalog", "payments"]
STATES = ("empty", "one-spec", "busy", "blocked", "emergency", "stale", "long-title", "non-english")
# The same states plus the variants the tests also draw: an emergency whose review is past due, and a person who comes back
# to a branch: two open questions, work nobody committed, and where the agent stopped.
VARIANTS = (*STATES, "emergency-overdue", "resumed")

LONG_TITLE = "Show stock levels per warehouse on the product page, with a fallback when the inventory service is slow, and a note that says when each count was last refreshed"
LONG_FILE_TITLE = "Import supplier_catalog_export_2026_11_all_warehouses_stock_levels_and_variant_attributes_v3.csv each night"
VIETNAMESE = "Gửi thông báo khi đơn hàng được giao"
JAPANESE = "注文履歴をCSVで書き出す"
ARABIC = "إظهار حالة الطلب للعميل"
GERMAN = "Lieferantenproduktdatenimportschnittstellenkonfiguration einrichten"

GROUP = {"draft": "backlog", "ready": "unstarted", "approved": "unstarted", "in_progress": "started", "in_review": "started", "done": "completed"}
INTENT_OF = {"checkout": "INTENT-1", "catalog": "INTENT-2", "payments": "INTENT-3"}
WORDS = {
    "spec.approval": "Show me {id} for Spec approval",
    "spec.merge": "Show me the report on {id} for Merge approval",
    "spec.blocked": "Show me what stopped {id}, then wait for my answer",
    "spec.triage": "Show me what {id} needs from me, then wait for my answer",
    "spec.emergency": "Show me where the {id} repair stands",
}
WHAT = {
    "spec.draft": "the Spec and its tests are not finished: finish them, run `aidd validate`, then ask for Spec approval",
    "spec.approval": "the agent asked for Spec approval of {id}: {person} answers yes, or says what to change",
    "spec.approved": "the Spec is approved: implement it inside its Tasks' scope",
    "spec.in_progress": "the Spec is being built: finish its Tasks and get the tests green with `aidd test`",
    "spec.merge": "the built change waits for a person's Merge approval: they read the report, then say yes, or review the PR/MR",
    "spec.blocked": "{blocked}",
    "spec.blocked_by": "blocked by {waits}",
    "spec.triage": "an agent suggested this work: a person triages it (accepted, declined, or snoozed) before anyone builds it",
    "spec.emergency": "an emergency Spec is open: restore service inside its scope first, then complete the Spec before its `review_due`",
}
WHO = {"spec.approval": "person", "spec.merge": "person", "spec.blocked": "person", "spec.triage": "person", "spec.blocked_by": "nobody"}


def task(tid: str, title: str, status: str = "todo", retries: int = 0, why: str = "") -> dict:
    return {"id": tid, "title": title, "status": status, "retry_count": retries, **({"why": why} if why else {})}


def spec(sid: str, title: str, status: str, team: str | None, code: str, *, person: str = "", owner: str = "", **extra) -> dict:
    """One Spec as `aidd status --json` gives it, with the optional keys the page reads."""
    number = sid.split("-")[1]
    who = WHO.get(code, "agent")
    text = WHAT[code].format(id=sid, person=person, blocked=extra.get("blockers", ""), waits=", ".join(extra.get("waiting_on", [])))
    step: dict = {"code": code, "who": who, "what": text}
    if why := step_reasons.step_reason(code, extra.get("route")):
        step["why"] = why
    if person and who == "person":
        step["person"] = person
    if who != "nobody":
        step["words"] = WORDS.get(code, "Go on with {id}").format(id=sid)
    else:
        step["words"] = f"Show me what {extra['waiting_on'][0]} still needs"
    item: dict = {"id": sid, "type": "spec", "title": title, "path": f"specs/SPEC-{number}.md", "status": status, "group": GROUP[status]}
    if team:
        item.update(owner_team=team, delivery_teams=[team], parent=INTENT_OF[team])
    if owner:
        item["owner"] = owner
    item.update(extra)
    item["next"] = step
    return item


def containers(finished: tuple[int, int, int] = (3, 2, 1), of: tuple[int, int, int] = (12, 9, 8)) -> list[dict]:
    """The three Intents, one for each team, in the order of TEAMS."""
    intents = [
        ("INTENT-1", "Checkout that remembers you", "checkout"),
        ("INTENT-2", "Catalog from suppliers", "catalog"),
        ("INTENT-3", "Payments that stay up", "payments"),
    ]
    return [
        {
            "id": iid,
            "type": "intent",
            "title": title,
            "path": f"specs/{iid}.md",
            "status": "active",
            "group": "started",
            "owner_team": team,
            "delivery_teams": [team],
            "progress": {"finished": finished[n], "of": of[n]},
        }
        for n, (iid, title, team) in enumerate(intents)
    ]


def answer(items: list[dict], **extra) -> dict:
    return {"schema_version": "1", "items": items, "due": [], "delivery_teams": TEAMS, **extra}


def emergency_spec(overdue: bool = False) -> dict:
    due = "2026-11-05" if overdue else "2026-11-09"
    return spec(
        "SPEC-41",
        "Restore card payments after the gateway timeout",
        "in_progress",
        "payments",
        "spec.emergency",
        owner="Lan",
        route="emergency",
        emergency={"severity": "sev1", "type": "outage", "incident": "INC-207", "commander": "Lan", "review_due": due},
        tasks=[
            task("T1", "Raise the gateway timeout to 20 seconds", "done"),
            task("T2", "Retry once with the same payment id", "todo", 1),
            task("T3", "Backfill the Spec, its tests, and the postmortem"),
        ],
        evidence={"commit": "4f9e2a1", "head": "4f9e2a1", "result": "passed", "at": "2026-11-07T12:31:00Z"},
    )


def blocked_spec() -> dict:
    stopped = "T2 used its 3 retries; a person re-plans it"
    return spec(
        "SPEC-17",
        "Import the product catalog from a supplier CSV",
        "in_progress",
        "catalog",
        "spec.blocked",
        person="Kenji",
        owner="Kenji",
        blockers=stopped,
        tasks=[
            task("T1", "Read the supplier CSV", "done"),
            task("T2", "Map the CSV's columns to products", "stopped", 3, "used its 3 retries: a person re-plans it"),
            task("T3", "Show the rows that failed to import", "blocked", 0, "waits for T2 to be done"),
        ],
        evidence={"commit": "7c1d2e9", "head": "7c1d2e9", "result": "failed", "at": "2026-11-07T11:20:00Z"},
    )


def waiting_spec() -> dict:
    return spec(
        "SPEC-22",
        "Apply a discount code at checkout",
        "approved",
        "checkout",
        "spec.blocked_by",
        owner="Mai",
        waiting_on=["SPEC-14"],
        tasks=[task("T1", "Read a discount code at checkout"), task("T2", "Take the discount off the order total", "blocked", 0, "waits for T1 to be done")],
    )


def merge_spec(stale: bool = False) -> dict:
    evidence = {"commit": "9f8e7d6", "head": "9f8e7d6", "result": "passed", "at": "2026-11-07T12:05:00Z"}
    if stale:
        evidence = {"commit": "a1b2c3d", "head": "9f8e7d6", "behind": 3, "result": "passed", "at": "2026-11-07T09:12:00Z"}
    return spec(
        "SPEC-14",
        "Send a receipt email after checkout",
        "in_review",
        "checkout",
        "spec.merge",
        person="Mai",
        owner="Mai",
        tasks=[task("T1", "Write the receipt email", "done"), task("T2", "Send it after payment", "done")],
        evidence=evidence,
    )


def approval_spec(team: str | None = "checkout", sid: str = "SPEC-12") -> dict:
    wait = "the Spec waits for its approval; no Task starts before it"
    return spec(
        sid,
        "Let a shopper save a cart for later",
        "ready",
        team,
        "spec.approval",
        person="Mai",
        owner="Mai",
        tasks=[task("T1", "Save the cart when a shopper leaves", "blocked", 0, wait), task("T2", "Show saved carts on the account page", "blocked", 0, wait)],
    )


def triage_spec() -> dict:
    item = spec("SPEC-23", "Suggested: rate-limit the search endpoint", "draft", None, "spec.triage")
    return item


def building(sid: str, title: str, team: str, status: str = "in_progress", **extra) -> dict:
    code = "spec.approved" if status == "approved" else "spec.in_progress"
    return spec(sid, title, status, team, code, owner="Kenji", tasks=[task("T1", "Build it", "todo")], **extra)


def writing(sid: str, title: str, team: str | None) -> dict:
    return spec(sid, title, "draft", team, "spec.draft")


# The stage a Spec stands in, by its status: `aidd status --json` gives it from `loop.stages` in `schemas/roles.json`.
STAGE = {"draft": "Design", "ready": "Design", "approved": "Build", "in_progress": "Build", "in_review": "Test"}


def with_phases(items: list[dict]) -> list[dict]:
    """INTENT-1 with phases, as `aidd status --json` gives them: its Specs on the page in two phases, the second with a
    slice that has no Spec yet. The other Intents keep none, as a plan written without phases would."""
    mine = [i for i in items if i.get("parent") == "INTENT-1"]
    lines = [{"id": i["id"], "title": i["title"], "status": i["status"], "stage": STAGE[i["status"]]} for i in mine]
    planned = {"id": "SPEC-50", "title": "Offer a saved cart by email", "status": "planned", "stage": "Plan"}
    phases = [
        {"id": "PHASE-1", "name": "Walking skeleton", "due": "2026-11-20", "slices": lines[:3]},
        {"id": "PHASE-2", "name": "Remember the shopper", "due": "2026-12-04", "slices": [*lines[3:], planned]},
    ]
    return [{**i, "phases": phases} if i["id"] == "INTENT-1" else i for i in items]


def busy_items(*, overdue: bool = False, stale: bool = False) -> list[dict]:
    specify = [
        writing("SPEC-20", JAPANESE, "checkout"),
        writing("SPEC-21", ARABIC, "checkout"),
        triage_spec(),
        writing("SPEC-31", "Let a guest check out without an account", "checkout"),
        writing("SPEC-33", "Refund part of an order", "payments"),
        writing("SPEC-35", "Add size charts to clothing pages", "catalog"),
        writing("SPEC-36", "Add a second card gateway as a fallback", "payments"),
        writing("SPEC-40", GERMAN, "catalog"),
    ]
    implement = [
        emergency_spec(overdue),
        blocked_spec(),
        waiting_spec(),
        building("SPEC-18", LONG_TITLE, "catalog"),
        building("SPEC-19", VIETNAMESE, "checkout"),
        building("SPEC-25", "Map supplier categories to shop categories", "catalog"),
        building("SPEC-26", "Retry a card payment once after a timeout", "payments"),
        building("SPEC-27", "Show the delivery date before payment", "checkout"),
        building("SPEC-29", "Alert on-call when payment errors pass 2%", "payments"),
        building("SPEC-32", "Mark a product as discontinued", "catalog", "approved"),
        building("SPEC-37", "Split one order into two deliveries", "checkout"),
        building("SPEC-38", "Search products by brand", "catalog"),
        building("SPEC-42", "Show a clear message when a card is declined", "payments"),
        building("SPEC-43", "Reconcile gateway payouts each night", "payments"),
    ]
    return with_phases([*containers(), approval_spec(), merge_spec(stale), *specify, *implement])


def with_proposal(items: list[dict]) -> list[dict]:
    proposal = {
        "id": "PROP-1",
        "type": "proposal",
        "title": "Wholesale prices for trade buyers",
        "path": "proposals/PROP-1/proposal.md",
        "status": "drafting",
        "group": "started",
        "next": {
            "code": "proposal.drafting",
            "who": "agent",
            "what": "the proposal is being drafted: `/aidd-team:propose`, then `aidd validate`",
            "words": "Go on with PROP-1",
        },
    }
    return [*items, proposal]


def busy(*, overdue: bool = False, stale: bool = False) -> dict:
    due = [
        {
            "path": "specs/SPEC-9.md",
            "what": "flag new-cart was due for removal on 2026-10-01",
            "next": {
                "code": "flag.overdue",
                "who": "agent",
                "what": "a feature flag is past its `cleanup_due`: write the cleanup Spec that lists it in `removes_flags`",
                "words": "Write the cleanup Spec for the overdue flag in SPEC-9",
            },
        }
    ]
    unreadable = [{"path": "specs/SPEC-30.md", "error": "line 4 has a key with no value"}]
    return answer(with_proposal(busy_items(overdue=overdue, stale=stale)), due=due, unreadable=unreadable)


def question(path: str, text: str, item: str = "") -> dict:
    """An open exploration, as `aidd status --json` lists it: a pick a person owes, with words only when it has a plain id."""
    step = {
        "code": "exploration.open",
        "who": "person",
        "what": "an exploration waits for a person's pick: they read its options and its recommendation, then pick one in the chat",
        **({"words": f"Show me the open question in {item}, then wait for my pick"} if item else {}),
        "why": step_reasons.step_reason("exploration.open"),
    }
    return {"path": path, "question": text, **({"item": item} if item else {}), "next": step}


def resumed() -> dict:
    """A person comes back to `spec/SPEC-12`: its Spec waits for approval, its folder holds an open question, the worktree
    holds work nobody committed, and the branch's last commit holds where the agent stopped."""
    cart = approval_spec()
    paths = ["specs/SPEC-12/design/prototype.html", "specs/SPEC-12/design/flow.md", "tests/test_saved_cart.py", "src/cart/saved.py"]
    cart["unsaved"] = {"branch": "spec/SPEC-12", "count": 12, "paths": [*paths, *(f"specs/SPEC-12/design/rounds/1/cart-{n}-390-light.png" for n in range(6))]}
    handoff = {
        "branch": "spec/SPEC-12",
        "commit": "5d4c3b2a1f0e",
        "done": "the prototype's saved-cart flow, its empty and error states, and two directions for the cart list",
        "next": "the verifier, once a direction is picked",
        "needs": "a person to pick how a saved cart shows on the account page",
        "stopped_at": "an ask with no yes: Spec approval waits for Mai",
    }
    explorations = [
        question("specs/SPEC-12/explore/saved-carts/exploration.md", "How should saved carts show on the account page?", "SPEC-12"),
        question("specs/explore/delivery-date/exploration.md", "Where does the delivery date sit on the payment page?"),
    ]
    items = [*containers()[:2], cart, merge_spec(), building("SPEC-27", "Show the delivery date before payment", "checkout")]
    return answer(items, explorations=explorations, handoff=handoff)


def state(name: str) -> dict:
    """The status answer for one state of the brief, or the overdue variant. A fresh copy: a test may change it."""
    return copy.deepcopy(_build(name))


def _build(name: str) -> dict:
    if name == "empty":
        step = {
            "code": "nothing_open",
            "who": "person",
            "what": "nothing is open: describe the next change to the agent",
            "words": "Help me plan the next change, and write its Spec",
        }
        return {"schema_version": "1", "items": [], "due": [], "delivery_teams": TEAMS, "next": step}
    if name == "one-spec":
        return {"schema_version": "1", "items": [approval_spec(None, "SPEC-1")], "due": []}
    if name == "busy":
        return busy()
    if name == "blocked":
        return answer([*containers()[:2], blocked_spec(), waiting_spec(), merge_spec()])
    if name in ("emergency", "emergency-overdue"):
        return answer(
            [
                containers()[2],
                emergency_spec(name == "emergency-overdue"),
                building("SPEC-26", "Retry a card payment once after a timeout", "payments"),
            ]
        )
    if name == "stale":
        return answer([*containers()[:1], merge_spec(stale=True), approval_spec()])
    if name == "resumed":
        return resumed()
    if name == "long-title":
        return answer(
            [
                *containers()[:2],
                writing("SPEC-35", "Add size charts to clothing pages", "catalog"),
                building("SPEC-18", LONG_TITLE, "catalog"),
                spec("SPEC-44", LONG_FILE_TITLE, "in_review", "catalog", "spec.merge", person="Kenji", owner="Kenji"),
            ]
        )
    if name == "non-english":
        return answer(
            [
                *containers()[:2],
                spec("SPEC-19", VIETNAMESE, "in_review", "checkout", "spec.merge", person="Mai", owner="Mai"),
                spec("SPEC-20", JAPANESE, "ready", "checkout", "spec.approval", person="Mai", owner="Mai"),
                spec("SPEC-21", ARABIC, "ready", "checkout", "spec.approval", person="Mai", owner="Mai"),
                writing("SPEC-40", GERMAN, "catalog"),
            ]
        )
    raise KeyError(name)
