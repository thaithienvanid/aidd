# Diagram craft: rules for any Mermaid diagram

Each rule holds for a diagram a person reviews, and it is stated once here. A rule's source is a page or a standard, not an aidd invention. "diagram-design" is cathrynlavery/diagram-design (`skills/diagram-design/SKILL.md`, by section). "archify" is tt-a1i/archify (`archify/references/authoring-defaults.md`, Composition and meaning). Both are emerging, so each rule is kept only where a Mermaid diagram can follow it. "C4" is the C4 model's notation page (c4model.com, Notation). "ISO 5807" is the flowchart symbols standard.

## The rules

| Rule | What holds | Source |
| --- | --- | --- |
| D1 Choose | Choose the diagram by the question the reader has, from the table in SKILL.md. If a table or a paragraph answers it as well, write that instead. | diagram-design §2, §3; archify's type router |
| D2 Cut | Every node is a distinct idea, so merge two that always travel together. Remove an edge when the layout already shows the relationship. | diagram-design §1, §9 |
| D3 Size | At most twelve nodes and twelve edges. Past that, split into an overview and a detail, each with its own question (D12). | diagram-design §7 (nine nodes, twelve arrows) |
| D4 Edges | Label an edge with what crosses it: a request, an event, a file. Put a gate (an approval, an authorization check, a state change) on the edge it governs, never only in a note. Leave a label off only where the two ends already say it. | archify; diagram-design §1 |
| D5 Boundaries | Draw a `subgraph` only for a real boundary: isolation, ownership, runtime, or persistence (D11). | archify |
| D6 Legend | Add a legend whenever a shape, a line style, or a class carries meaning. It lists what the diagram uses and nothing else, and sits under the diagram as a line or a table, never inside the graph. | diagram-design §4, §9; C4 ("every diagram should have a key") |
| D7 No decoration | Add no shadow, glow, icon, or gradient. A class carries meaning (D13), except `default` and `group`, which only make every box and group read in both themes (D14). Mark at most two nodes as the focus, because a mark on five erases the signal. | diagram-design §1, §4 |
| D8 Color | Text keeps 4.5:1 and a stroke or fill that carries meaning keeps 3:1 against its ground, in the light and the dark theme (D14). So an opaque fill sets its `color`, and a tint sets none. Never color alone: pair it with a border style, a shape, or a label. | WCAG 2.2 SC 1.4.1, 1.4.3, 1.4.11 |

Where a screen's contrast target sits above the floor, `aidd-team:accessible-ui` owns the numbers.

## Lay it out for the page

A diagram is read where the file is read. GitHub draws it in the page's text column, about 840 px wide for a README in a 1280 px window, and shrinks a wider one to fit. A diagram twice that wide shows its text at half size, too small to read. Mermaid lays a flowchart out in ranks, so the direction decides which way it grows.

**D9 Direction.** Choose the direction by the widest row the layout makes, against the column the page gives. Draw top-down (`TD`) by default: a chain, or a set of zones one feeds the next, grows down the page and never shrinks. As a rule of thumb, a row of `LR` holds three short nodes, and two when a link between them carries a label, because Mermaid widens the gap to fit the label. The same holds for a subgraph's own `direction LR`. Inside `TD`, a rank holds about four short nodes side by side, so a node with many targets fans out down, not across. A check estimates the width from the labels instead of counting nodes. A node is about 9 px a character, up to Mermaid's wrap at 16, plus 40 px. Ranks stand 50 px apart, plus about 8 px a character of the widest label between them. The column is the project's own, such as 838 px for a README on GitHub in a 1280 px window. A sequence diagram holds at most four participants, because each takes a fixed width, and its messages stay short. Put the detail of a message in the text under it. Why: past the column, every label shrinks with the whole diagram.

```text
Before: flowchart LR, Cart -->|checkout| Order -->|paid| Payment -->|captured| Shipment --> Invoice
        five ranks with labels: about 1,500 px drawn in 840, its text at half size.
After:  flowchart TD, the same chain down the page: 600 px wide, its text at full size.
```

**D10 Labels.** A node's label is its name, and at most two short lines of detail. Mermaid wraps a line at about 16 characters, so break the line yourself with `<br/>` before that, at a word, where the break means something. An edge's label is at most four words, because it sits on the line between two ranks and widens the gap. Move a list, a reason, or an example into the text under the diagram. Why: a wrap Mermaid makes splits a name in the middle, and a long edge label pushes the ranks apart.

```text
Before: billing["Billing service with invoices, refunds, and tax"]    drawn as "Billing service / with invoices, / refunds, and tax"
After:  billing["Billing<br/>invoices, refunds"]                     and the text under the diagram names the rest
```

**D11 Group.** Put the nodes of one boundary or one stage in one `subgraph`, so the eye reads them as one region before it reads the lines. Order the groups as the reader moves through them, untrusted to trusted, or first step to last. Give a group its own `direction` only when its row still passes D9. Keep an edge from crossing a group it does not enter: move the node, or split the diagram. Why: a shared region groups more strongly than closeness (the Gestalt principle of common region), and a crossing line reads as a relationship that is not there.

```text
Before: three trust zones in a row, LR, with an edge from the first looping round the second to reach the third.
After:  the three trust zones stacked TD in trust order; the long edge runs down the side of the middle one.
```

**D12 Split.** One diagram answers one question (D1). Split it when it answers two, when it passes D3, or when it repeats the same shape once per row, such as one chain per command. Draw the overview once and each detail in its own diagram, under the heading it explains. When the rows are the content, write a table instead. Why: a reader takes in about a screen at a time, and twenty copies of one shape are a table drawn badly.

```text
Before: one diagram of twenty handoff rows, 4,500 px tall, each row the same two boxes and a paragraph on the edge.
After:  the handoff table the page already holds, and no diagram.
```

## The same look, in both themes

**D13 Same kind, same look.** Give each kind of thing one shape and one class, the same in every diagram of the project. A rectangle is a part, a cylinder `[( )]` stored data, and a stadium `([ ])` a person. A hexagon `{{ }}` is a point where a person decides, and a diamond `{ }` a branch the system takes (ISO 5807's decision symbol). A dashed line `-.->` is a path taken only on a signal, such as a rollback. C4 asks the same: notation consistent "within and across diagrams". Why: a reader learns the look once, and a look that changes between diagrams reads as a change in meaning.

```text
Before: a person decides drawn as an amber box in one file, a blue pill in another, and a plain hexagon in a third.
After:  a hexagon with the human class wherever a person decides.
```

**D14 Palette.** Take the colors from the project's own design tokens. Name a few classes, state them once as `classDef` lines in its DESIGN.md, and copy them unchanged into each diagram that uses one. GitHub draws Mermaid in its `default` theme on a white page in light mode, and in its `dark` theme on a near-black page in dark mode. One `classDef` applies in both, so draw every box as a tint the page shows through:

- **A tint in the border's hue.** A class fills its box with its border's color at a low alpha and sets no text color. The alpha is about 20% for a plain box and 15% for a hue that marks a kind. The box is then a light card on the white page and a dark card on the dark one. The reader's theme keeps the text readable on both.
- **A border mixed for both pages.** A border takes its role's light and dark token values, mixed to the point where it reads alike on both pages, about 4.3:1. That sits in the comfort band, never the maximum on either.
- **A `default` class and a neutral group.** `classDef default` tints every box no other class marks. A subgraph takes a neutral tint of about 8% by a `class` line, so no group keeps the theme's own fill. An opaque fill is the exception, and it sets its own text color at 4.5:1 or more.
- **Color is never the only cue.** With the colors taken away, each class keeps a look of its own. A plain box has a 1px border, `added` 2px, `changed` 3px, and `focus` 4px. `removed` and a `boundary` group are dashed, and `human` has its shape, a stadium or a hexagon. A change's diagram also keeps its table keyed by node id. Check the status hues under the three common color-vision deficiencies.
- **The rest keeps the theme.** Lines, edge labels, and subgraph titles stay the theme's, which each theme draws readable on its own page. A sequence or an entity diagram takes no class. Never set a theme or theme variables with `%%{init}%%`: it overrides the light or dark choice the reader made.

Why: a color picked on one page fails on the other, such as an opaque amber fill at 15:1 against the dark page. A tint follows the reader's mode with one line. Render each diagram in both themes before review.

```text
Before: classDef added fill:#fde68a,stroke:#b45309,color:#1c1917          a bright patch at 15:1 on the dark page
After:  classDef added fill:<border>26,stroke:<border>,stroke-width:2px   <border> mixed from the role's light and dark values
```

The aidd skill's design-system template (`assets/DESIGN.md`, which `aidd new design-system` writes) holds the default palette: a quiet neutral, one accent, and three status hues, as `default`, `group`, `boundary`, `focus`, `human`, `added`, `changed`, and `removed`. A project that has its own tokens keeps the names and the technique in its DESIGN.md and replaces each hue with its own role's mix. A check of a project's diagrams reads the `classDef` lines of the project's own DESIGN.md, so it holds the project's hues, never the default's.
