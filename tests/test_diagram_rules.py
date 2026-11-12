"""The diagrams skill's rules that a check can hold, on every Mermaid diagram in the tracked Markdown files.

`references/craft.md` in the `diagrams` practice skill states the rules. A diagram uses only its palette's classes, each
line copied unchanged, with `default` on every flowchart and a class on every subgraph (D14). It holds at most twelve
nodes and twelve edges (D3), and its widest row fits the page's text column by an estimate from its labels (D9). It has
`accTitle` and `accDescr`, and a legend when a shape, a line style, or a class carries meaning (D6).

A palette is the fence of `classDef` lines in a DESIGN.md. The design-system template holds the default one that the
templates and the skill's example copy; aidd's own DESIGN.md holds aidd's version, which every other diagram copies. Each
is checked against its own file's color roles: every class is a tint of its border's hue with no text color, every
border is a mix of its role's light and dark values that reads alike on GitHub's two pages, and the classes differ by
more than hue. Mermaid itself parses every block in CI (tools/mermaid/check-mermaid.mjs). A rule that cannot hold for one
diagram is named in ACCEPTED with its reason, and the check fails when that diagram stops breaking it.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT, repo_files
from test_design_system import ratio

DESIGN_MD = ROOT / "docs" / "design" / "DESIGN.md"
TEMPLATE_DESIGN_MD = ROOT / ".agents" / "skills" / "aidd" / "assets" / "DESIGN.md"
# What a project copies, so it carries the template's default palette: the aidd skill's templates and the diagrams
# skill's own example. Every other diagram is aidd's own and carries aidd's palette.
DEFAULT_PALETTE_PATHS = (".agents/skills/aidd/assets/", "plugins/aidd-team/skills/diagrams/")
# GitHub draws a diagram in a frame whose page is Primer's bgColor-default, with Mermaid's own theme text on it: the
# default theme in light mode, the dark theme in dark mode (Mermaid 12.2, the frame's version).
PAGES = {"light": (1.0, 1.0, 1.0), "dark": (13 / 255, 17 / 255, 23 / 255)}
THEME_TEXT = {"light": (0x33 / 255,) * 3, "dark": (0xCC / 255,) * 3}
# The text column a diagram must fit, in CSS px: a README on GitHub in a 1280 px window. A project sets its own.
COLUMN_PX = 838
CLASSES = ("default", "group", "boundary", "focus", "human", "added", "changed", "removed")

# The team's loop (`aidd gen-docs`, roles:graph:diagram) is one picture of its thirteen steps and approvals and their
# fourteen paths, in three rows read left to right, so it goes past the size limit and GitHub draws it at about 0.6 of its
# width. The owner chose to keep it whole and left to right, because the order of the steps and the paths back are the
# point of it. Each pair is (file, rule): "size" is D3, "row" is D9.
LOOP = "the team's loop, kept whole and left to right: thirteen steps and approvals and fourteen paths in three rows"
ACCEPTED = {
    ("docs/TEAM.md", "size"): LOOP,
    ("docs/TEAM.md", "row"): LOOP,
    ("plugins/aidd-team/skills/aidd-team/SKILL.md", "size"): LOOP,
    ("plugins/aidd-team/skills/aidd-team/SKILL.md", "row"): LOOP,
}

BLOCK = re.compile(r"```mermaid\n(.*?)```", re.S)
SHAPED = re.compile(r"\(\[|\{\{|\[\(|(?<![A-Za-z0-9_])[A-Za-z0-9_]+\{")
COLOR_PROPERTY = re.compile(r"\b(fill|stroke|color):")
NODE_ID = re.compile(r"^([A-Za-z0-9_]+)")
# A link in Mermaid 12's flowchart grammar, its text label already taken out: solid, thick, dotted, and invisible, with an
# arrow, a circle, or a cross at either end, and an optional edge id (`e1@-->`).
LINK = re.compile(r"(?:\b\w+@)?(?:(?<=\s)[ox]|<)?(?:~~~|={2,}[=>]?|-\.+-[>]?|-{2,}[->]?)(?:[ox](?=\s))?")
# A text label written inside the link: `-- text -->`, `== text ==>`, `-. text .->`.
INLINE_LABEL = re.compile(r"(--|==|-\.)\s+(?![->=.])([^|]+?)\s+(-->|---|==>|===|\.->|\.-)")
# The link each inline label's closing mark makes, once the label is taken out.
LABEL_ENDS = {"-->": "-->", "---": "---", "==>": "==>", "===": "===", ".->": "-.->", ".-": "-.-"}
SHAPE = re.compile(r'([A-Za-z0-9_]+)\s*(\(\[|\[\(|\{\{|\(\(|\[\[|\[|\(|\{|>)\s*"([^"]*)"')
# A node's shape and the text inside it, and a `:::class` mark: what lies between the ids and the links.
SHAPE_TEXT = re.compile(r"\(\[[^\]]*\]\)|\[\([^)]*\)\]|\{\{[^}]*\}\}|\(\([^)]*\)\)|\[\[[^\]]*\]\]|\[[^\]]*\]|\{[^}]*\}|\([^)]*\)|:::\w+")


def hex_rgba(value: str) -> tuple[tuple[float, float, float], float]:
    value = value.lstrip("#")
    alpha = int(value[6:8], 16) / 255 if len(value) == 8 else 1.0
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255), alpha


def over(color: tuple[float, float, float], alpha: float, page: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (alpha * c + (1 - alpha) * p for c, p in zip(color, page, strict=True))
    return r, g, b


def mix_error(light, dark, color) -> float:
    """How far `color` is from the nearest mix of `light` and `dark`, in the largest channel, over mixes in steps of 1%."""
    return min(max(abs(a + k / 100 * (b - a) - c) for a, b, c in zip(light, dark, color, strict=True)) for k in range(101))


def palette(path) -> list[str]:
    """The `classDef` lines of the one text fence in `path` that holds only `classDef` lines."""
    for fence in re.findall(r"```text\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
        lines = [x.strip() for x in fence.splitlines() if x.strip()]
        if lines and all(x.startswith("classDef ") for x in lines):
            return lines
    raise AssertionError(f"{path.name} holds no fence of classDef lines")


def props(line: str) -> dict[str, str]:
    return dict(p.split(":", 1) for p in line.split(maxsplit=2)[2].split(","))


def color_roles(path) -> dict[str, tuple[float, float, float]]:
    """The color roles in a DESIGN.md's token front matter, `name` and `name-dark`, each alias followed. A role with alpha is
    measured as drawn over its theme's page."""
    block = path.read_text(encoding="utf-8").split("\ncolors:\n", 1)[1]
    block = block[: re.search(r"^\S", block, re.M).start()]
    raw = dict(re.findall(r'^  ([a-z0-9-]+): "([^"]+)"$', block, re.M))
    out = {}
    for name, value in raw.items():
        while value.startswith("{colors."):
            value = raw[value[len("{colors.") : -1]]
        rgb, alpha = hex_rgba(value)
        out[name] = rgb if alpha >= 1 else over(rgb, alpha, PAGES["dark" if name.endswith("-dark") else "light"])
    return out


def border_roles(path) -> dict[str, str]:
    """Each class's role, the first role its row of the palette's table names in its last cell."""
    rows = re.findall(r"^\| `([a-z]+)` \|(.*)\|$", path.read_text(encoding="utf-8"), re.M)
    return {name: re.search(r"`([a-z-]+)`", cells.split("|")[-1]).group(1) for name, cells in rows if name in CLASSES}


def diagrams() -> list[tuple[str, str, str]]:
    """(file, the block's source, the text after its fence up to the next heading) for each block."""
    out = []
    for rel in repo_files():
        if not rel.endswith(".md"):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for m in BLOCK.finditer(text):
            after = re.split(r"\n#+ ", text[m.end() :], maxsplit=1)[0]
            out.append((rel, m.group(1), after[:800]))
    return out


def statements(block: str) -> list[str]:
    return [x.strip() for x in block.splitlines() if x.strip() and not x.strip().startswith("%%")]


def kind(block: str) -> str:
    return statements(block)[0].split()[0]


class Flow:
    """A flowchart read as Mermaid 12 lays it out: its direction, its nodes with their label widths in characters and
    their shapes, its links as (from, to, label characters, invisible), and the members and direction of each subgraph."""

    def __init__(self, block: str):
        lines = statements(block)
        self.direction = lines[0].split()[1] if len(lines[0].split()) > 1 else "TD"
        self.nodes: dict[str, tuple[int, str]] = {}
        self.links: list[tuple[str, str, int, bool]] = []
        self.members: dict[str, set[str]] = {}
        self.inner: dict[str, str] = {}
        stack: list[str] = []
        skip = ("accTitle", "accDescr", "classDef ", "class ", "linkStyle ", "style ", "click ")
        for line in lines[1:]:
            if line.startswith("subgraph "):
                stack.append(NODE_ID.match(line[len("subgraph ") :]).group(1))
                self.members.setdefault(stack[-1], set())
                continue
            if line == "end":
                stack.pop()
                continue
            if line.startswith("direction "):
                if stack:
                    self.inner[stack[-1]] = line.split()[1]
                continue
            if line.startswith(skip):
                continue
            for nid, shape, text in SHAPE.findall(line):
                chars = max((len(x) for x in re.split(r"<br\s*/?>", re.sub(r"</?i>", "", text))), default=0)
                self.nodes[nid] = (chars, shape)
            for nid in self._chain(line):
                self.nodes.setdefault(nid, (len(nid), "["))
                for group in stack:
                    self.members[group].add(nid)

    def _chain(self, line: str) -> list[str]:
        """Read one statement's links into `links`, and return the node ids it names, `&` lists included. A label's
        length travels as a marker after its link, so a link's label is the marker that opens the next part."""
        bare = re.sub(r'"[^"]*"', lambda m: '"' + "x" * (len(m.group(0)) - 2) + '"', line)  # quoted text: only its length
        bare = INLINE_LABEL.sub(lambda m: f" {LABEL_ENDS[m.group(3)]} \x00{len(m.group(2).strip(chr(34)))}\x00 ", bare)
        bare = re.sub(r"\|([^|]*)\|", lambda m: f" \x00{len(m.group(1).strip(chr(34)))}\x00 ", bare)
        bare = SHAPE_TEXT.sub("", bare)
        parts, arrows = LINK.split(bare), LINK.findall(bare)
        groups, sizes = [], []
        for part in parts:
            found = re.search(r"\x00(\d+)\x00", part)
            sizes.append(int(found.group(1)) if found else 0)
            part = re.sub(r"\x00\d+\x00", "", part)
            groups.append([m.group(1) for x in part.split("&") if (m := NODE_ID.match(x.strip()))])
        for i, arrow in enumerate(arrows):
            for a in groups[i]:
                for b in groups[i + 1]:
                    self.links.append((a, b, sizes[i + 1], arrow.endswith("~~~")))
        return [x for ids in groups for x in ids if x not in self.members]

    def node_ids(self) -> set[str]:
        return {n for n in self.nodes if n not in self.members}

    def edges(self) -> list[tuple[str, str, int, bool]]:
        """The links between nodes, a link to or from a subgraph standing for one to or from each of its members."""
        out = []
        for a, b, size, invisible in self.links:
            for x in self.members.get(a, {a}):
                for y in self.members.get(b, {b}):
                    if x in self.node_ids() and y in self.node_ids():
                        out.append((x, y, size, invisible))
        return out


def ranks(nodes: set[str], links) -> dict[str, int]:
    """Each node's rank as Mermaid's layered layout counts it: the longest path to it from a node nothing points to, with
    the links that close a cycle left out."""
    out_edges: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b, _, _ in links:
        if a in out_edges and b in out_edges:
            out_edges[a].append(b)
    state: dict[str, int] = {}
    order: list[str] = []
    back = set()

    def visit(n: str) -> None:
        state[n] = 1
        for m in out_edges[n]:
            if state.get(m) == 1:
                back.add((n, m))
            elif m not in state:
                visit(m)
        state[n] = 2
        order.append(n)

    for n in sorted(nodes):
        if n not in state:
            visit(n)
    rank = dict.fromkeys(nodes, 0)
    for n in reversed(order):
        for m in out_edges[n]:
            if (n, m) not in back:
                rank[m] = max(rank[m], rank[n] + 1)
    return rank


# The width model, calibrated on Mermaid 12.2's renders of this repository's diagrams: a node's line wraps at about 16
# characters of about 9 px, inside 40 px of padding; a hexagon or a diamond is about 1.45 times as wide, and a stadium 30 px
# wider; ranks stand 50 px apart, plus about 8 px a character of the widest label between them; the frame adds 48 px a side.
def node_px(chars: int, shape: str) -> float:
    width = min(chars, 16) * 9 + 40
    return width * 1.45 if shape in ("{{", "{") else width + 30 if shape == "([" else width


def row_px(direction: str, nodes: set[str], links, sizes: dict[str, tuple[int, str]]) -> float:
    """The estimated width of one layout: a left-to-right row adds its ranks and the gaps between them; a top-down rank
    adds its nodes side by side."""
    if not nodes:
        return 0.0
    rank = ranks(nodes, links)
    width = {n: node_px(*sizes[n]) for n in nodes}
    if direction in ("LR", "RL"):
        deepest = max(rank.values()) + 1
        across = sum(max(width[n] for n in nodes if rank[n] == r) for r in range(deepest))
        gaps = sum(50 + 8 * max([s for a, b, s, _ in links if rank.get(a) == r and rank.get(b) == r + 1] or [0]) for r in range(deepest - 1))
        return across + gaps + 96
    return max(sum(width[n] for n in nodes if rank[n] == r) + 50 * ([*rank.values()].count(r) - 1) for r in set(rank.values())) + 96


def row_problems(block: str, column: int = COLUMN_PX) -> list[str]:
    """What breaks D9: the whole diagram, or a subgraph with its own direction, estimated wider than the column."""
    flow = Flow(block)
    nodes, links = flow.node_ids(), flow.edges()
    found = []
    width = row_px(flow.direction, nodes, links, flow.nodes)
    if width > column:
        found.append(f"about {width:.0f} px, past the {column} px column: draw it top-down, shorten labels, or split it")
    for group, direction in flow.inner.items():
        members = flow.members[group] & nodes
        inside = [x for x in links if x[0] in members and x[1] in members]
        width = row_px(direction, members, inside, flow.nodes)
        if width > column:
            found.append(f"subgraph {group}: about {width:.0f} px, past the {column} px column")
    return found


class PaletteTests(unittest.TestCase):
    """The default palette and aidd's: each checked against the color roles of its own DESIGN.md."""

    OWNERS = (TEMPLATE_DESIGN_MD, DESIGN_MD)

    def test_each_palette_holds_the_same_classes(self):
        for path in self.OWNERS:
            self.assertEqual([x.split()[1] for x in palette(path)], list(CLASSES), path.name)
            self.assertEqual(set(border_roles(path)), set(CLASSES), f"{path.name}: each class names the role its border mixes")

    def test_each_border_is_its_roles_mix_and_reads_alike_on_both_pages(self):
        for path in self.OWNERS:
            roles, borders = color_roles(path), border_roles(path)
            for line in palette(path):
                name, p = line.split()[1], props(line)
                with self.subTest(path=path.name, name=name):
                    stroke, _ = hex_rgba(p["stroke"])
                    role = borders[name]
                    self.assertLessEqual(mix_error(roles[role], roles[f"{role}-dark"], stroke), 2 / 255, f"{name}'s border mixes {role}")
                    on_page = [ratio(stroke, page) for page in PAGES.values()]
                    self.assertGreaterEqual(min(on_page), 3, f"{name}'s border on both pages (WCAG 1.4.11)")
                    self.assertLessEqual(abs(on_page[0] - on_page[1]), 0.5, f"{name}'s border reads alike on both pages")

    def test_each_fill_is_a_tint_of_its_border_that_keeps_the_themes_text_readable(self):
        """A tint (alpha below one) is its border's color, sets no text color, and keeps 4.5:1 with the theme's text over
        each page. An opaque fill sets its own text color at 4.5:1."""
        for path in self.OWNERS:
            for line in palette(path):
                name, p = line.split()[1], props(line)
                fill, alpha = hex_rgba(p["fill"])
                with self.subTest(path=path.name, name=name):
                    if alpha < 1:
                        self.assertNotIn("color", p, f"{name} is a tint, so the reader's theme keeps its text")
                        self.assertEqual(fill, hex_rgba(p["stroke"])[0], f"{name}'s tint is its border's hue")
                        self.assertLessEqual(alpha, 0.4, f"{name} stays a tint")
                        for mode, page in PAGES.items():
                            self.assertGreaterEqual(ratio(THEME_TEXT[mode], over(fill, alpha, page)), 4.5, f"{name}'s text in {mode} (WCAG 1.4.3)")
                    else:
                        self.assertIn("color", p, f"{name} is opaque, so it sets its own text color")
                        self.assertGreaterEqual(ratio(hex_rgba(p["color"])[0], fill), 4.5, f"{name}'s own text (WCAG 1.4.3)")

    def test_the_classes_differ_by_more_than_hue(self):
        """WCAG 1.4.1: with the colors taken away, each class still has a look of its own, by its border's width, its dash,
        or its fill's strength."""
        for path in self.OWNERS:
            looks = {}
            for line in palette(path):
                p = props(line)
                looks[line.split()[1]] = (p.get("stroke-width", "1px"), "stroke-dasharray" in p, round(hex_rgba(p["fill"])[1], 2))
            self.assertEqual(len(set(looks.values())), len(looks), f"{path.name}: {looks}")

    def test_aidds_human_class_is_the_light_themes_primary_pair(self):
        roles = color_roles(DESIGN_MD)
        p = props(next(x for x in palette(DESIGN_MD) if x.split()[1] == "human"))
        for prop, role in (("fill", "primary"), ("color", "primary-foreground")):
            got = hex_rgba(p[prop])[0]
            self.assertLessEqual(max(abs(a - b) for a, b in zip(got, roles[role], strict=True)), 1 / 255, prop)


class DiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = diagrams()
        cls.aidd, cls.default = palette(DESIGN_MD), palette(TEMPLATE_DESIGN_MD)

    def test_the_blocks_are_found(self):
        self.assertGreater(len(self.blocks), 10)
        self.assertTrue(any(rel.startswith(".agents/skills/aidd/assets/") for rel, _, _ in self.blocks))

    def test_every_diagram_uses_only_its_palettes_classes(self):
        for rel, block, _ in self.blocks:
            allowed = self.default if rel.startswith(DEFAULT_PALETTE_PATHS) else self.aidd
            defined = set()
            for line in statements(block):
                with self.subTest(rel=rel, line=line):
                    self.assertFalse(line.startswith("%%{"), "no init directive: it overrides the viewer's theme")
                    self.assertFalse(line.startswith("style "), "no style of one node or group: a class from the palette")
                    if line.startswith("linkStyle "):
                        self.assertNotRegex(line, COLOR_PROPERTY, "no colored link: links keep the theme")
                    if line.startswith("classDef "):
                        self.assertIn(line, allowed, "a palette line, copied unchanged")
                        defined.add(line.split()[1])
            used = set(re.findall(r":::([A-Za-z0-9_]+)", block))
            used |= {m.split()[-1] for m in re.findall(r"^\s*class [^\n]+", block, re.M)}
            with self.subTest(rel=rel):
                self.assertLessEqual(used, defined, "each class used is defined in the block")

    def test_every_flowchart_tints_every_box_and_every_group(self):
        """D14: `default` tints every box no other class marks, and each subgraph takes `group` or `boundary`, so no box or
        group keeps the theme's own fill."""
        for rel, block, _ in self.blocks:
            if kind(block) not in ("flowchart", "graph"):
                continue
            with self.subTest(rel=rel, first=statements(block)[1][:60]):
                self.assertRegex(block, r"(?m)^\s*classDef default ")
                classed = set()
                for m in re.finditer(r"^\s*class ([\w,]+) (group|boundary)\s*$", block, re.M):
                    classed |= set(m.group(1).split(","))
                self.assertLessEqual(set(re.findall(r"^\s*subgraph (\w+)", block, re.M)), classed)

    def test_every_flowchart_holds_twelve_nodes_and_twelve_edges_at_most(self):
        """D3: past twelve, a reader no longer takes the picture in."""
        for rel, block, _ in self.blocks:
            if kind(block) not in ("flowchart", "graph"):
                continue
            flow = Flow(block)
            edges = len([x for x in flow.links if not x[3]])
            with self.subTest(rel=rel, first=statements(block)[1][:60]):
                self.assertEqual(len(flow.node_ids()) > 12 or edges > 12, (rel, "size") in ACCEPTED, f"{len(flow.node_ids())} nodes, {edges} edges")

    def test_every_flowchart_fits_the_column(self):
        """D9: the estimated width of the diagram, and of each subgraph with its own direction, fits the column."""
        for rel, block, _ in self.blocks:
            if kind(block) not in ("flowchart", "graph"):
                continue
            found = row_problems(block)
            with self.subTest(rel=rel, first=statements(block)[1][:60]):
                self.assertEqual(bool(found), (rel, "row") in ACCEPTED, found)

    def test_each_accepted_exception_names_a_diagram_and_a_rule(self):
        files = {rel for rel, _, _ in self.blocks}
        for rel, rule in ACCEPTED:
            self.assertIn(rel, files)
            self.assertIn(rule, ("size", "row"))

    def test_every_sequence_diagram_holds_four_participants_at_most(self):
        """D9: each participant takes a fixed width, so a fifth one pushes the diagram past the page's column."""
        for rel, block, _ in self.blocks:
            if kind(block) == "sequenceDiagram":
                with self.subTest(rel=rel):
                    self.assertLessEqual(len([x for x in statements(block) if x.startswith(("participant ", "actor "))]), 4)

    def test_every_diagram_has_a_title_a_description_and_a_legend_when_it_needs_one(self):
        for rel, block, after in self.blocks:
            lines = statements(block)
            with self.subTest(rel=rel, first=lines[1][:60] if len(lines) > 1 else ""):
                self.assertTrue(any(x.startswith("accTitle:") for x in lines), "accTitle")
                self.assertTrue(any(x.startswith("accDescr:") for x in lines), "accDescr")
                body = "\n".join(x for x in lines if not x.startswith(("accTitle", "accDescr", "classDef ")))
                if kind(block) not in ("flowchart", "graph"):
                    continue  # a sequence or an entity diagram's notation is the standard's own
                meaning = re.search(r":::(?!default\b)\w+|^\s*class [\w,]+ (?!group\b)\w+", body, re.M)
                if meaning or "-.->" in body or SHAPED.search(re.sub(r'"[^"]*"', "", body)):
                    self.assertRegex(after, re.compile(r"\blegend\b", re.I), "a shape, a line style, or a class needs a legend under it")


class FlowReadingTests(unittest.TestCase):
    """The reading the size and width checks rest on, on samples of each form Mermaid 12 writes."""

    def test_nodes_and_links_of_each_form(self):
        cases = (
            ("flowchart TD\n  r --> a & b & c & d & e & f", 7, 6),
            ("flowchart LR\n  a ==> b --o c --x d", 4, 3),
            ("flowchart LR\n  a <--> b -.- c --- d", 4, 3),
            ('flowchart LR\n  a -- "label" --> b\n  b -->|text| c\n  c -. text .-> d\n  d == text ==> e', 5, 4),
            ("flowchart LR\n  a e1@--> b", 2, 1),
            ('flowchart TD\n  subgraph s["S"]\n    a["A"]\n  end\n  a ~~~ b', 2, 1),
        )
        for source, nodes, links in cases:
            with self.subTest(source=source):
                flow = Flow(source)
                self.assertEqual(len(flow.node_ids()), nodes, flow.node_ids())
                self.assertEqual(len(flow.links), links, flow.links)

    def test_a_link_between_subgraphs_stacks_their_members(self):
        """Zones linked zone to zone stand one above the other, so their members never share a rank."""
        source = (
            'flowchart TD\n  subgraph u["U"]\n    a1["A one"]\n    a2["A two"]\n  end\n'
            '  subgraph v["V"]\n    b1["B one"]\n    b2["B two"]\n  end\n'
            '  subgraph w["W"]\n    c1["C one"]\n  end\n  u --> v\n  v --> w'
        )
        flow = Flow(source)
        rank = ranks(flow.node_ids(), flow.edges())
        self.assertEqual(max(list(rank.values()).count(r) for r in set(rank.values())), 2)
        self.assertEqual(row_problems(source), [])

    def test_the_width_check_at_its_boundary(self):
        """A left-to-right row of four short steps fits; a long labelled chain, a wide fan, and a wide subgraph do not; a
        project with a narrower column gets a narrower limit."""
        cases = (
            ('flowchart LR\n  a["Plan"] --> b["Build"] --> c["Test"] --> d["Ship"]', 0),
            ('flowchart LR\n  a["Cart"] -->|checkout| b["Order"] -->|paid| c["Payment"] -->|captured| d["Shipment"] --> e["Invoice"]', 1),
            ("flowchart TD\n  root --> alpha & bravo & charlie & delta & echo & foxtrot & golf & hotel", 1),
            (
                'flowchart TD\n  subgraph s["S"]\n    direction LR\n    a["First step"] --> b["Second step"] --> c["Third step"] --> d["Fourth step"] --> e["Fifth step"]\n  end',
                1,
            ),
            ('flowchart TD\n  a["One"] --> b["Two"]', 0),
        )
        for source, count in cases:
            with self.subTest(source=source):
                self.assertEqual(len(row_problems(source)), count, row_problems(source))
        self.assertEqual(len(row_problems('flowchart LR\n  a["Plan"] --> b["Build"] --> c["Test"] --> d["Ship"]', column=400)), 1)


if __name__ == "__main__":
    unittest.main()
