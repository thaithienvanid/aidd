"""The Mermaid diagrams of the team: the loop with its roles and the two human approvals, the flows, and the handoffs."""

from __future__ import annotations

import re

from aidd import knowledge


def _mermaid(lines: list[str]) -> str:
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _label(text: str, width: int | None = None) -> str:
    """Text inside a quoted Mermaid label. Backticks go (entity codes render inconsistently), double quotes become
    single ones, and a `width` breaks the text into lines at word boundaries so a node stays narrow."""
    text = text.replace("`", "").replace('"', "'")
    if not width:
        return text
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return "<br/>".join(lines)


# One look for every place a person decides, readable on GitHub's light and dark themes alike: an amber fill with
# dark text set explicitly. Everything else keeps the viewer's theme, so it follows light or dark by itself.
HUMAN_CLASS = "  classDef human fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#1c1917"


def _node_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", text)


# Node ids are single words; Mermaid reads a space as the end of the id, and GitHub then renders nothing.
GATES = {
    "Specify": ("SpecApproval", "Spec approval", "a human approves the Spec and its tests"),
    "Review": ("MergeApproval", "Merge approval", "a human approves the head commit"),
}


def _wrap(words: list[str], width: int = 26) -> str:
    """Join words with commas, breaking the line (`<br/>`) before one would pass `width` characters, short enough
    that Mermaid never wraps a line itself and splits a hyphenated role name."""
    rows: list[str] = []
    for word in words:
        if rows and len(rows[-1]) + len(word) + 2 <= width:
            rows[-1] += ", " + word
        else:
            rows.append(word)
    return ",<br/>".join(rows)


# The loop in three rows, read top to bottom, so it stays narrow enough to review on a page. Before the first edit, the
# gate gives a change its route (`aidd gate --paths`), and the lane follows from it: the fast and emergency lanes skip
# Plan and Specify and start at Implement.
LOOP_ROWS = (
    ("before", "Before any code: the fast lane skips to Implement", ("Plan", "Specify")),
    ("build", "Build and prove", ("Implement", "Verify", "Review")),
    ("run", "Ship and learn", ("Ship", "Learn")),
)

# The inner loop's own way back, drawn solid: a red test or a mismatch the Verifier finds returns the head to Implement.
VERIFY_BACK = ("Verify", "Implement", "red, or a mismatch")

# Human feedback paths are dashed, in an amber that reads on GitHub's light and dark themes alike: the same family as
# the human decision nodes, dark enough on white and light enough on near-black.
FEEDBACK_STYLE = "stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4"


def _point_id(point: str) -> str:
    """The node id of a loop step, or of one of the two human approvals."""
    return next((gate for gate, name, _ in GATES.values() if name == point), _node_id(point))


def loop_diagram() -> str:
    """The loop with the roles of each step, the two human approvals, and the human feedback paths, dashed.

    A feedback path inside one row joins its two nodes. One back to an earlier row (Learn to Plan) ends at a
    "back to Plan" marker in its own row: a link from a node to another row makes Mermaid drop the rows'
    left-to-right direction, and a back link between rows makes it stack the rows in the wrong order."""
    data = knowledge.roles()
    loop = data["loop"]
    steps = loop["steps"]
    if [x for _, _, row in LOOP_ROWS for x in row] != steps:
        raise ValueError(f"LOOP_ROWS must list the loop steps in order: {steps}")
    row_of = {}
    for key, _, row in LOOP_ROWS:
        for step in row:
            row_of[_node_id(step)] = key
            if step in GATES:
                row_of[GATES[step][0]] = key
    feedback = [(f, _point_id(f["from"]), _point_id(f["to"])) for f in loop["loops"]["feedback"]]
    covered = {(a, b) for _, a, b in feedback}
    lines = ["flowchart TD"]
    dashed: list[str] = []
    links = 0  # Mermaid numbers links in the order they are drawn, and linkStyle picks the dashed ones by number
    for key, title, row in LOOP_ROWS:
        lines += [f'  subgraph {key}["{title}"]', "    direction LR"]
        chain = []
        for step in row:
            roles = [k for k in data["order"] if step in data["roles"][k]["steps"]]
            label = step + "<br/><i>" + (_wrap(roles) or "a human merges") + "</i>"
            lines.append(f'    {_node_id(step)}["{label}"]')
            chain.append(_node_id(step))
            if step in GATES:
                gate, name, meaning = GATES[step]
                lines.append(f'    {gate}{{{{"{name}<br/>{meaning}"}}}}')  # a hexagon: a diamond grows too large for its text
                chain.append(gate)
        run = [chain[0]]
        for a, b in zip(chain, chain[1:], strict=False):
            if (a, b) in covered:  # a path people take only on a signal is drawn once, dashed
                lines += ["    " + " --> ".join(run)] if len(run) > 1 else []
                run = [b]
            else:
                run.append(b)
                links += 1
        lines += ["    " + " --> ".join(run)] if len(run) > 1 else []
        if VERIFY_BACK[0] in row:
            src, dst, why = VERIFY_BACK
            lines.append(f'    {_node_id(src)} -->|"{why}"| {_node_id(dst)}')
            links += 1
        for f, a, b in feedback:
            if row_of[a] != key:
                continue
            if row_of[b] != key:  # the way back to an earlier row ends at a marker in this row, named for its target
                lines.append(f'    {b}_again(["back to {f["to"]}"])')
                b = f"{b}_again"
            lines.append(f'    {a} -.->|"{_label(f["when"], 22)}"| {b}')
            dashed.append(str(links))
            links += 1
        lines.append("  end")
    keys = [key for key, _, _ in LOOP_ROWS]
    for a, b in zip(keys, keys[1:], strict=False):
        lines.append(f"  {a} --> {b}")
        links += 1
    lines += [HUMAN_CLASS, "  class " + ",".join(gate for gate, _, _ in GATES.values()) + " human"]
    lines.append(f"  linkStyle {','.join(dashed)} {FEEDBACK_STYLE}")
    return _mermaid(lines)


def flows_diagram() -> str:
    """Every command as one row, top to bottom: its role groups in order (several roles in a group run in parallel),
    and the person it stops for. Invisible links stack the rows, so the diagram grows down, not across."""
    data = knowledge.roles()
    lines, rows, stops = ["flowchart TB"], [], []
    for f in data["loop"]["flows"]:
        cmd = f["command"]
        rows.append(cmd)
        lines += [f'  subgraph {cmd}["/aidd-team:{cmd}"]', "    direction LR"]
        ids = []
        for i, group in enumerate(f["runs"]):
            nid = f"{cmd}_{i}"
            label = "<br/>".join(group) + ("<br/><i>in parallel</i>" if len(group) > 1 else "")
            lines.append(f'    {nid}["{label}"]')
            ids.append(nid)
        stop = f"{cmd}_stop"
        lines.append(f'    {stop}{{{{"{_label(f["stops_at"], 26)}"}}}}')
        stops.append(stop)
        lines += ["    " + " --> ".join(ids + [stop]), "  end"]
    lines.append("  " + " ~~~ ".join(rows))
    lines += [HUMAN_CLASS, "  class " + ",".join(stops) + " human"]
    return _mermaid(lines)


def handoffs_diagram() -> str:
    """Each handoff as one row, top to bottom: who hands off, what travels (the edge's label), and who receives it.
    A side with several roles is one node; a person who receives is drawn as a decision point."""
    data = knowledge.roles()
    lines, rows, people = ["flowchart TB"], [], []
    for i, h in enumerate(data["loop"]["handoffs"]):
        row, src, dst = f"h{i}", f"h{i}_from", f"h{i}_to"
        rows.append(row)
        lines += [f'  subgraph {row}[" "]', "    direction LR"]
        lines.append(f'    {src}["{"<br/>".join(h["from"])}"]')
        lines.append(f'    {dst}["{_label("<br/>".join(h["to"]))}"]')
        lines.append(f'    {src} -- "{_label(h["through"], 26)}" --> {dst}')
        lines.append("  end")
        if any(not t.replace("-", "").isalpha() or " " in t for t in h["to"]):
            people.append(dst)
    lines.append("  " + " ~~~ ".join(rows))
    lines.append(HUMAN_CLASS)
    if people:
        lines.append("  class " + ",".join(people) + " human")
    return _mermaid(lines)
