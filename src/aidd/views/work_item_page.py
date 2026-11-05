"""The work-item page (`aidd status --html`): the open work as one static page, read from `aidd status`'s answer.

One list, sorted by whose move it is: what needs you, what your agents take next, and what is blocked, each row with its
next step and the words to type to your agent. Initiatives and Epics stand apart, with their progress and children, so a
container never shows as an empty step. Read-only: the state stays in each item's front matter and a decision stays in
the chat, so the page holds no form and no link that acts. Every value comes from a file, and a fetched branch's file is
another person's text, so each is escaped.
"""

from __future__ import annotations

from aidd.views import html_parts
from aidd.views.html_parts import Html, Section, el, join
from aidd.views.markdown_html import inline

CONTAINERS = ("initiative", "epic")
# Whose move each item is, from who takes its next step: a person's, an agent's, or nobody's while it waits on other
# work. Each move is a section of the page, in this order.
MOVES = (("needs-you", "Needs you"), ("agents", "For your agents"), ("blocked", "Blocked"), ("finished", "Done or cancelled"))
MOVE_OF = {"person": "needs-you", "agent": "agents"}
TYPE_NAMES = {"spec": "Spec", "epic": "Epic", "initiative": "Initiative", "proposal": "Proposal"}
STATUS_LEVELS = {"started": "pass", "completed": "pass", "backlog": "quiet", "cancelled": "quiet"}
STYLE = """
.wrap{max-width:76rem}
header{padding-bottom:.5rem}
header .lead{color:var(--fg);font-size:1.25rem;line-height:1.4;max-width:60ch;margin:.25rem 0 .5rem;text-wrap:balance}
nav ol{gap:.5rem}nav:has(li:only-child){display:none}
nav a{display:inline-flex;align-items:center;gap:.4rem;min-height:2.25rem;padding:.25rem .8rem;border:1px solid var(--border);
border-radius:2rem;color:var(--fg);text-decoration:none}
nav a:hover{background:var(--panel)}
h2{display:flex;align-items:center;gap:.6rem;border-bottom:0;margin:2.25rem 0 .75rem}
h2::before,.mark{content:"";flex:none;display:inline-block;width:.7rem;height:.7rem;border-radius:50%;border:2px solid var(--muted)}
#needs-you h2::before,.mark.needs-you{background:var(--accent);border-color:var(--accent)}
#agents h2::before,.mark.agents{border-color:var(--pass-fg);background:linear-gradient(90deg,var(--pass-fg) 50%,transparent 50%)}
#blocked h2::before,.mark.blocked{border-radius:2px;border-color:var(--warn-fg)}
#finished h2::before,.mark.finished{border-color:var(--muted);background:var(--muted)}
#due h2::before{border-radius:2px;border-color:var(--fail-fg);background:var(--fail-fg)}
#plans h2::before{display:none}
.work-list,.plan,.plan ul{list-style:none;margin:0;padding:0}
.row{display:grid;grid-template-columns:6.5rem minmax(0,1fr);gap:.2rem 1rem;padding:.9rem .75rem;border-top:1px solid var(--border)}
.row:last-child{border-bottom:1px solid var(--border)}
#needs-you .row{background:var(--accent-bg);border:1px solid var(--accent-border);border-radius:.5rem;margin-bottom:.6rem}
#needs-you .row pre{background:var(--bg)}
.row p{margin:0}.row>div{min-width:0;display:grid;gap:.3rem}
.id{font-weight:650;white-space:nowrap;font-variant-numeric:tabular-nums}
.headline{display:flex;flex-wrap:wrap;align-items:baseline;gap:.15rem .6rem}
.title{font-weight:600;overflow-wrap:break-word;min-width:0}
.meta{color:var(--muted);font-size:.875rem}
.meta code{font-size:.8rem}
.step b{font-weight:600}
.say{font-size:.8rem;color:var(--muted);margin-top:.2rem}
.row .copyline pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:.45rem .65rem;flex-basis:16rem}
.badge{font-size:.8rem;font-weight:600;padding:0 .5rem}.badge.quiet{color:var(--muted)}
.row:target,.node:target{animation:landed 2s cubic-bezier(.16,1,.3,1)}
@keyframes landed{from{background:var(--accent-border)}}
@media (prefers-reduced-motion:reduce){.row:target,.node:target{animation:none;outline:2px solid var(--accent);outline-offset:2px}}
.plan ul{padding-inline-start:1.1rem;border-inline-start:1px solid var(--border);margin:.4rem 0 .2rem .35rem}
.node{padding:.6rem 0 .2rem}
.node-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.15rem .6rem}
.progress{display:flex;align-items:center;gap:.6rem;margin:.35rem 0;font-size:.875rem;color:var(--muted)}
progress{-webkit-appearance:none;appearance:none;color:var(--pass-fg);width:7rem;height:.45rem;border:0;border-radius:1rem;background:var(--border);overflow:hidden}
progress::-webkit-progress-bar{background:var(--border);border-radius:1rem}
progress::-webkit-progress-value{background:var(--pass-fg);border-radius:1rem}
progress::-moz-progress-bar{background:var(--pass-fg);border-radius:1rem}
.leaf{display:grid;grid-template-columns:.55rem auto minmax(0,1fr);align-items:baseline;gap:0 .5rem;padding:.2rem 0}
.leaf .mark{width:.55rem;height:.55rem}.leaf .title{font-weight:400}.leaf>.meta,.leaf>ul{grid-column:3}
.empty{color:var(--muted);margin:0;padding:.9rem .75rem;border:1px dashed var(--border);border-radius:.5rem}
@media (min-width:70rem){main{display:grid;grid-template-columns:minmax(0,1fr) minmax(17rem,22rem);column-gap:3.5rem;align-items:start}
main>section{grid-column:1}main>#plans{grid-column:2;grid-row:1/span 9}}
@media (max-width:36rem){.row{grid-template-columns:1fr;padding:.8rem .6rem}header .lead{font-size:1.125rem}}
"""


def whose_move(item: dict) -> str | None:
    """Whose move the item is, from who takes its next step. A person's or an agent's step comes first, even on finished
    work; nobody's step is finished work, or work blocked until other work finishes. A container with no step of its own
    has no move: it shows with its children, never as an empty step."""
    who = (item.get("next") or {}).get("who")
    if who in MOVE_OF:
        return MOVE_OF[who]
    if item.get("group") in ("completed", "cancelled"):
        return "finished"
    if who == "nobody":
        return "blocked"
    return None if item.get("type") in CONTAINERS else "agents"


def words_to_type(item: dict) -> str:
    """What a person types to their agent to move the item on: short, because the row already says the step."""
    step, ident = item.get("next") or {}, item["id"]
    who, code = step.get("who"), step.get("code")
    if who == "agent":
        return f"Go on with {ident}"
    if who != "person":
        return ""
    if code == "spec.approval":
        return f"Show me {ident} for Spec approval"
    if code == "spec.merge":
        return f"Show me the report on {ident} for Merge approval"
    if code == "spec.blocked":
        return f"Show me what stopped {ident}, then wait for my answer"
    return f"Show me what {ident} needs from me, then wait for my answer"


def _sentence(text: str) -> Html:
    """A step from `aidd status`, which starts lower-case, as a sentence, with its `code` spans set as code. aidd's own
    name stays lower-case."""
    text = text[:1].upper() + text[1:] if text[:1].islower() and not text.startswith("aidd ") else text
    return inline(text if text.endswith((".", "?", "!")) else text + ".")


def _status_name(item: dict) -> str:
    return str(item.get("status", "")).replace("_", " ").capitalize()


class WorkItems:
    """The page's work items, in the order `aidd status` gives, and the markup for each: its row (`w-<n>`), its place
    in the plan (`p-<n>`), and the links between them."""

    def __init__(self, items: list[dict]):
        self.items = items
        self.at: dict[str, int] = {}
        for n, i in enumerate(items):
            self.at.setdefault(i["id"], n)

    def link(self, ident: str) -> Html:
        n = self.at.get(ident)
        if n is None:
            return el("span", ident, class_="id")
        target = "p" if whose_move(self.items[n]) is None else "w"
        return el("a", ident, href=f"#{target}-{n}", class_="id")

    def _step(self, item: dict) -> Html:
        step = item.get("next") or {}
        if step.get("who") == "nobody" and item.get("waiting_on"):
            waits = item["waiting_on"]
            links = join([join(self.link(w), " and " if k < len(waits) - 1 else "") for k, w in enumerate(waits)])
            moving = [self.items[self.at[w]] for w in waits if w in self.at]
            now = join(" ", ", ".join(f"{i['id']} is {str(i.get('status', '')).replace('_', ' ')}" for i in moving), ".") if moving else ""
            return el("p", el("b", "Starts when "), links, " finish." if len(waits) > 1 else " finishes.", now, class_="step")
        if step:
            return el("p", el("b", "Next: "), _sentence(str(step.get("what", ""))), class_="step")
        return el("p", "No next step yet.", class_="step muted")

    def row(self, n: int) -> Html:
        item = self.items[n]
        parent, say = item.get("parent"), words_to_type(item)
        meta = [TYPE_NAMES.get(item["type"], item["type"])]
        if item.get("route"):
            meta.append(f"{item['route']} route")
        if item.get("progress"):
            meta.append(f"{item['progress']['finished']} of {item['progress']['of']} finished")
        bits: list[object] = [join(m, " · ") for m in meta]
        if parent and parent in self.at and parent != item["id"]:
            bits += ["in ", self.link(parent), " ", self.items[self.at[parent]]["title"], " · "]
        bits.append(el("code", item["path"]))
        if item.get("places"):
            bits += [" · held in ", ", ".join(item["places"])]
        return el(
            "li",
            el("span", item["id"], class_="id"),
            el(
                "div",
                el("p", el("span", item["title"], class_="title"), self._badge(item), class_="headline"),
                el("p", bits, class_="meta"),
                self._step(item),
                join(el("p", "Type to your agent", class_="say"), html_parts.copyable(f"say-{n}", say, f"Copy the words for {item['id']}")) if say else "",
            ),
            class_="row",
            id=f"w-{n}",
        )

    @staticmethod
    def _badge(item: dict) -> Html:
        """The item's status, or Blocked when a person must clear what stops it."""
        if (item.get("next") or {}).get("code") == "spec.blocked":
            return html_parts.badge("warn", "Blocked")
        return html_parts.badge(STATUS_LEVELS.get(str(item.get("group")), "neutral"), _status_name(item))

    def moves(self) -> list[Section]:
        found: dict[str, list[int]] = {}
        for n, i in enumerate(self.items):
            found.setdefault(whose_move(i) or "", []).append(n)
        sections = []
        for key, name in MOVES:
            rows = found.get(key, [])
            if rows or key == "needs-you":
                body = el("ol", [self.row(n) for n in rows], class_="work-list") if rows else el("p", "Nothing needs you now.", class_="empty")
                sections.append(Section(key, name, body, count=len(rows)))
        return sections

    def plan(self) -> Html:
        """Each item under its parent; an item whose parent is not open, or has none, at the top, and so is the first item
        of a loop of parents (an item that names itself, or two that name each other), so no item drops out."""
        kids: dict[str, list[int]] = {}
        for n, i in enumerate(self.items):
            kids.setdefault(str(i["parent"]) if i.get("parent") in self.at and i["parent"] != i["id"] else "", []).append(n)
        while True:
            reached, todo = set(), [""]
            while todo:
                for n in kids.get(todo.pop(), []):
                    if n not in reached:
                        reached.add(n)
                        todo.append(self.items[n]["id"])
            lost = next((n for n in range(len(self.items)) if n not in reached), None)
            if lost is None:
                break
            kids[str(self.items[lost]["parent"])].remove(lost)
            kids.setdefault("", []).append(lost)

        def branch(parent: str, seen: frozenset[str]) -> Html:
            rows = []
            for n in kids.get(parent, []):
                i = self.items[n]
                more = branch(i["id"], seen | {i["id"]}) if i["id"] not in seen and i["id"] != parent else ""
                rows.append(self._node(n, more) if i["type"] in CONTAINERS else self._leaf(n, more))
            return el("ul", rows) if rows else Html("")

        return el("div", branch("", frozenset()), class_="plan")

    def _node(self, n: int, children: object) -> Html:
        item, progress = self.items[n], self.items[n].get("progress") or {}
        done, total = int(progress.get("finished", 0)), int(progress.get("of", 0))
        bar = (
            el("p", el("progress", f"{done} of {total}", max=total, value=done, aria_hidden="true"), f"{done} of {total} finished", class_="progress")
            if total
            else el("p", "Nothing in it yet.", class_="progress")
        )
        mine = el("a", "Needs you", href=f"#w-{n}", class_="badge pending") if whose_move(item) == "needs-you" else ""
        head = el("p", el("span", item["id"], class_="id"), " ", el("span", item["title"], class_="title"), " ", self._badge(item), mine, class_="node-head")
        return el("li", head, bar, children, class_="node", id=f"p-{n}")

    def _leaf(self, n: int, children: object) -> Html:
        item, where = self.items[n], whose_move(self.items[n]) or "agents"
        state = dict(MOVES)[where] if where in ("needs-you", "blocked") else _status_name(item)
        return el(
            "li",
            el("span", class_=f"mark {where}", aria_hidden="true"),
            self.link(item["id"]),
            " ",
            el("span", item["title"], class_="title"),
            el("span", state, class_="meta"),
            children,
            class_="leaf",
        )


def _due(answer: dict) -> Html:
    rows = [
        el(
            "li",
            el("span", "Past due", class_="id"),
            el(
                "div",
                el("p", _sentence(d["what"]), class_="title"),
                el("p", el("code", d["path"]), class_="meta"),
                el("p", el("b", "Next: "), _sentence(d["next"]["what"]), class_="step"),
            ),
            class_="row",
        )
        for d in answer.get("due", [])
    ]
    rows += [
        el(
            "li",
            el("span", "Unreadable", class_="id"),
            el(
                "div",
                el("p", el("code", u["path"]), class_="title"),
                el("p", inline(u["error"]), class_="meta"),
                el("p", el("b", "Next: "), "Fix its front matter, then run ", el("code", f"aidd validate {u['path']}"), ".", class_="step"),
            ),
            class_="row",
        )
        for u in answer.get("unreadable", [])
    ]
    return el("ol", rows, class_="work-list")


def _lead(items: list[dict], answer: dict) -> Html:
    """The page's verdict in one line: how many need you, then what moves without you, then what is blocked."""
    count = {key: sum(whose_move(i) == key for i in items) for key, _ in MOVES}
    need, late = count["needs-you"], len(answer.get("due", [])) + len(answer.get("unreadable", []))
    parts = [f"{need} item{'s need' if need > 1 else ' needs'} you." if need else "Nothing needs you now."]
    if count["agents"]:
        parts.append(f"Your agents have {count['agents']} to move on.")
    if count["blocked"]:
        parts.append(f"{count['blocked']} {'are' if count['blocked'] > 1 else 'is'} blocked.")
    if late:
        parts.append(f"{late} item{'s are' if late > 1 else ' is'} past due or unreadable.")
    return join(" ".join(parts))


def status_page(answer: dict, *, title: str = "The open work", as_of: str = "") -> str:
    """The page for `answer`, the dict `aidd status` prints as JSON (schemas/status.schema.json). `as_of` says when it
    was written, so a page left open never passes for the current state."""
    items = list(answer.get("items", []))
    work = WorkItems(items)
    late = len(answer.get("due", [])) + len(answer.get("unreadable", []))
    if "next" in answer:
        lead: object = _sentence(answer["next"]["what"])
        teach = "When your agent writes a Spec, an Epic, or an Initiative, run `aidd status --html` again. What needs you shows first, then what your agents take next, then what is blocked."
        sections = [Section("start", "What to do next", el("p", inline(teach), class_="empty"))]
    else:
        lead = _lead(items, answer)
        sections = work.moves()
    if late:
        sections.append(Section("due", "Past due, or unreadable", _due(answer), count=late))
    if any(i["type"] in CONTAINERS for i in items):
        sections.append(Section("plans", "Initiatives and Epics", work.plan(), count=sum(i["type"] in CONTAINERS for i in items)))
    note = join("Written ", as_of, ". Run ", el("code", "aidd status --html"), " again to see the latest.") if as_of else ""
    footer = "Written by aidd from the work items' files. This page only reads: it never approves, and a decision stays in the chat."
    return html_parts.page(title, sections, lead=lead, note=note, footer=footer, style=STYLE)
