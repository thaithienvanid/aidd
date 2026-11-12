"""The Mermaid diagram of the team's loop: its steps with their roles, the human approvals, and the feedback paths."""

from __future__ import annotations

import functools
import re

from aidd import knowledge


def mermaid(lines: list[str]) -> str:
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _label(text: str, width: int) -> str:
    """Text inside a quoted Mermaid label. Backticks go (entity codes render inconsistently), double quotes become
    single ones, and `width` breaks the text into lines at word boundaries so a node stays narrow."""
    text = text.replace("`", "").replace('"', "'")
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return "<br/>".join(lines)


# The lines of the diagram palette in docs/design/DESIGN.md that the generated diagrams use, which tests/test_diagram_rules.py
# holds equal to it. `default` tints every box and `group` every row, each its border's hue at a low alpha with no text
# color, so a box reads as a light card on GitHub's light page and a dark card on its dark page. `human`, one look for
# every place a person decides, is the one opaque class, with its own light text.
DEFAULT_CLASS = "  classDef default fill:#7a787433,stroke:#7a7874,stroke-width:1px"
GROUP_CLASS = "  classDef group fill:#7a787414,stroke:#7a7874"
HUMAN_CLASS = "  classDef human fill:#4d4b47,stroke:#7a7874,stroke-width:2px,color:#fafaf9"


def _node_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", text)


@functools.cache
def gates() -> dict[str, list[tuple[str, str]]]:
    """The gates of `graph.gates` that follow each step, in the loop's order: (a gate's node id, its name). Node ids are
    single words; Mermaid reads a space as the end of the id, and GitHub then renders nothing."""
    loop = knowledge.roles()["graph"]
    steps = loop["steps"]
    out: dict[str, list[tuple[str, str]]] = {}
    for gate in loop["gates"]:
        after = steps[steps.index(gate["before"]) - 1]
        node = "".join(word[0].upper() for word in str(gate["name"]).split())  # short, so the page that draws it stays small
        out.setdefault(after, []).append((node, str(gate["name"])))
    return out


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


# The loop in three rows, read top to bottom, so it stays narrow enough to review on a page. Before the first edit,
# `aidd risk --paths` gives a change its route: a change with no Spec and the emergency route skip Plan and
# Specify and start at Implement.
LOOP_ROWS = (
    ("before", "Before any code: with no Spec, go to Implement", ("Plan", "Specify")),
    ("build", "Build and prove", ("Implement", "Verify", "Review")),
    ("run", "Merge, roll out, and learn", ("Merge", "Roll out", "Learn")),
)

# The inner loop's own ways back, drawn solid: a red test or a mismatch the Verifier finds, or a finding Review makes on
# the same head, returns the head to Implement.
VERIFY_BACK = ("Verify", "Implement", "red, or a mismatch")
REVIEW_BACK = ("Review", "Implement", "a finding")

# Human feedback paths are dashed (`-.->`) and drawn thicker, in the theme's own line color, so they read on GitHub's
# light and dark pages alike; a color of their own would read on one page only.
FEEDBACK_STYLE = "stroke-width:2px,stroke-dasharray:6 4"
LOOP_LEGEND = "\n\nLegend: a dark hexagon is a point where a person decides, and a dashed line is a path a person sends work back on."


def _point_id(point: str) -> str:
    """The node id of a loop step, or of one of the two human approvals."""
    return next((gate for found in gates().values() for gate, name in found if name == point), _node_id(point))


def graph_diagram() -> str:
    """The loop with the roles of each step, the two human approvals, and the human feedback paths, dashed.

    A feedback path inside one row joins its two nodes. One back to an earlier row (Learn to Plan) ends at a
    "back to Plan" marker in its own row: a link from a node to another row makes Mermaid drop the rows'
    left-to-right direction, and a back link between rows makes it stack the rows in the wrong order."""
    data = knowledge.roles()
    loop = data["graph"]
    steps = loop["steps"]
    if [x for _, _, row in LOOP_ROWS for x in row] != steps:
        raise ValueError(f"LOOP_ROWS must list the loop steps in order: {steps}")
    row_of = {}
    for key, _, row in LOOP_ROWS:
        for step in row:
            row_of[_node_id(step)] = key
            for gate, _ in gates().get(step, []):
                row_of[gate] = key
    feedback = [(f, _point_id(f["from"]), _point_id(f["to"])) for f in loop["loops"]["feedback"]]
    covered = {(a, b) for _, a, b in feedback}
    lines = [
        "flowchart TD",
        "  accTitle: The loop, its roles, and the human approvals",
        "  accDescr: Three rows, top to bottom: before any code, build and prove, and merge, roll out, and learn. Each step"
        " names the roles that work in it, each hexagon is a point where a person decides, and each dashed line is a"
        " path a person sends work back on.",
    ]
    dashed: list[str] = []
    links = 0  # Mermaid numbers links in the order they are drawn, and linkStyle picks the dashed ones by number
    for key, title, row in LOOP_ROWS:
        lines += [f'  subgraph {key}["{title}"]', "    direction LR"]
        chain = []
        for step in row:
            roles = [k for k in data["order"] if step in data["roles"][k]["steps"]]
            label = step + "<br/><i>" + (_wrap(roles) or "a person") + "</i>"
            lines.append(f'    {_node_id(step)}["{label}"]')
            chain.append(_node_id(step))
            for gate, name in gates().get(step, []):
                lines.append(f'    {gate}{{{{"{name}"}}}}')  # a hexagon: the class of a point where a person decides
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
        for src, dst, why in (VERIFY_BACK, REVIEW_BACK):
            if src in row:
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
    lines += [DEFAULT_CLASS, GROUP_CLASS, "  class " + ",".join(keys) + " group"]
    lines += [HUMAN_CLASS, "  class " + ",".join(gate for found in gates().values() for gate, _ in found) + " human"]
    lines.append(f"  linkStyle {','.join(dashed)} {FEEDBACK_STYLE}")
    return mermaid(lines) + LOOP_LEGEND
