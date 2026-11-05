# Diagram craft: rules for any Mermaid diagram

Each rule holds for a diagram a person reviews, and it is stated once here. A rule's source is a page, not an aidd invention. "diagram-design" is cathrynlavery/diagram-design (`skills/diagram-design/SKILL.md`, by section). "archify" is tt-a1i/archify (`archify/references/authoring-defaults.md`, Composition and meaning). Both are emerging, so each rule is kept only where a Mermaid diagram can follow it.

## The rules

| Rule | What holds | Source |
| --- | --- | --- |
| D1 Choose | Choose the diagram by the question the reader has, from the table in SKILL.md. If a table or a paragraph answers it as well, write that instead. | diagram-design §2, §3; archify's type router |
| D2 Cut | Every node is a distinct idea, so merge two that always travel together. Remove an edge when the layout already shows the relationship. | diagram-design §1, §9 |
| D3 Size | At most twelve nodes and twelve edges. Past that, split into an overview and a detail, each with its own question. | diagram-design §7 (nine nodes, twelve arrows) |
| D4 Edges | Label every edge with what crosses it: a request, an event, a file. Put a gate (an approval, an authorization check, a state change) on the edge it governs, never only in a note. | archify; diagram-design §1 |
| D5 Boundaries | Draw a `subgraph` only for a real boundary: isolation, ownership, runtime, or persistence. | archify |
| D6 Legend | Add a legend whenever a shape, a line style, or a color carries meaning. It lists what the diagram uses and nothing else, and sits under the diagram as a table or list, never inside the graph. | diagram-design §4, §9 |
| D7 No decoration | Add no shadow, glow, icon, or gradient. A `classDef` exists to carry meaning (added, changed, removed, focal). Accent at most two nodes, because an accent on five erases the signal. | diagram-design §1, §4 |
| D8 Color | Text keeps 4.5:1 and a stroke or fill that carries meaning keeps 3:1 against its ground, in the light and the dark theme, so set `color` with every `fill`. Never color alone: pair it with a border style, a shape, or a label. | WCAG 2.2 SC 1.4.1, 1.4.3, 1.4.11 |

Where a screen's contrast target sits above the floor, `aidd-team:accessible-ui` owns the numbers.
