---
name: diagrams
description: "Practice skill: explain a change as a Mermaid diagram. Use in an aidd repository when a Design, threat model, plan, or runbook needs a picture, or someone asks to draw the flow."
metadata:
  checked: "2026-11-10"
---

# Diagrams

**Use it when** a person must understand a file to decide or review it: a Spec's Design (Spec approval), a threat model, an Intent, an ADR, a pipeline, a runbook. One diagram of the shape, then the words. Mermaid, because it is text every agent can write and diff.

**Do not use when** prose already answers the question and a picture would only restate it; a diagram of independent local fixes is decoration. Say so in one line instead.

## Standards

<!-- aidd:gen practice:diagrams -->
| Standard | Edition |
| --- | --- |
| Mermaid diagrams as text (flowchart, sequenceDiagram, stateDiagram-v2, erDiagram, gantt), rendered by GitHub and GitLab, and in VS Code with an extension | — |
| C4 model diagrams | — |
| STRIDE threat modeling with data-flow diagrams | — |
| ISO/IEC/IEEE 42010 (stakeholders, concerns, views) | 2022 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:diagrams`.
<!-- aidd:end -->

## Specify

One diagram answers one question; the question is its title.

| Question | Diagram | Where it lives |
| --- | --- | --- |
| What does this change touch, and in what order do data and control move? | `flowchart`, the change's path marked `changed` | the Spec's Design |
| Who calls whom, in what order? | `sequenceDiagram` | the Spec's Design or an ADR |
| What states can this screen or entity be in? | `stateDiagram-v2` with every state the designer named (empty, loading, error, partial, success, offline) | `design-files` doc |
| What does the data look like, and what refers to what? | `erDiagram` of the tables the change adds or alters | the Spec's Design or the migration plan |
| What does this change add, remove, and move? | `flowchart` of the after state, with `added`, `changed`, and `removed` classes, and a table of the changes | the Spec's Design |
| Where does untrusted data cross a trust boundary? | `flowchart TD`, a `boundary` subgraph per trust zone in trust order, and labeled crossings, as STRIDE draws it | the threat model |
| What moves through the pipeline, and where is lineage lost? | `flowchart` of datasets and jobs | the Spec's Design |
| How do an Intent's slices depend on each other? | `flowchart TB` from the phases to the slices, edges for `blocked_by` | the Intent's file |
| What does on-call decide, and when do we roll back? | `flowchart TD` of decision points, the rollback trigger a diamond | the runbook |

- Draw the smallest true picture, by the rules in [references/craft.md](references/craft.md). They cover the type for the reader's question, a size limit, labeled edges, a legend, no decoration, and color. They also cover the direction that fits the page's width, short labels, groups, when to split, one look for each kind of thing, and a palette that reads in the light and the dark theme. Draw C4 levels (context, container, component) as flowcharts with subgraphs.
- Choose the direction by the widest row against the page's column (craft D9). Top-down is the default; `LR` fits about three short nodes, or two with a labeled link, before the diagram shrinks to fit the page.
- Name nodes with the code's names, so the reviewer can grep them.
- Use only the classes the project's DESIGN.md states (craft D14), copied unchanged, and no `style`, colored `linkStyle`, or `%%{init}%%`. Each class is a tint of its border's hue with no text color, so a box reads on the light and the dark page. Every flowchart carries `default`, and every subgraph `group` or `boundary`. A project without its own palette copies the default from the aidd skill's design-system template (`aidd new design-system`). Mark the nodes this Spec adds or alters with `added`, `changed`, and `removed`. Each changes the border too, so the delta shows without color ([worked example](references/change-delta.md)). Give each diagram `accTitle` and `accDescr`, and a legend under it.
- Mermaid stays for anything committed and reviewed, because it renders where the file is read, diffs line by line, and has a parse check. A visual that a person reads and does not review, such as a proposal, an onboarding explainer, or a stakeholder update, may be polished HTML or SVG. Make it with the `archify` or `diagram-design` extension (emerging) if the project pins it. It is never the diagram in a Spec, an ADR, or a threat model.
- Keep the source in the Markdown file beside the words. No exported image without its source, and a design tool's image goes in a `design-files` doc.
- Spec approval freezes a diagram in a Spec or a `design-files` doc, so a later change needs a new Spec approval.

### Existing code

A diagram of code that already exists is a claim about the source, so make each part checkable.

- Name the base commit the diagram reads, in a line under its title.
- Give each node and each edge a `%% path:lines` comment, such as `%% src/pay/client.py:40-62`.
- Trace each edge to its real call site, never to a module's description of itself.
- Draw an edge the source does not show as dashed, and label it `unverified`.

## Review

- Reviewers comment on the diagram's lines as on code, and the author updates the source.
- Render each diagram you review in the light and the dark theme, at the page's width: the platform's preview, or the Mermaid CLI with `-t default` and `-t dark`. Look at each picture, never only the source. A check can count nodes and classes; only a reader sees the rest.
  - The text reads at full size, and the diagram did not shrink to fit the column (craft D9, D10).
  - No line crosses another, a group, or a label where a move or a split avoids it (D11, D12).
  - The same kind of thing has the same shape and class as in the project's other diagrams (D13).
  - Every node, edge label, and subgraph title reads in both themes, the unclassed ones too (D14).
  - The legend names each shape, line style, and class the diagram uses (D6).
  - The diagram says what the text and the code say. A picture made tidier by changing a fact is a finding.
- `aidd validate` warns when a major Spec's Design has no diagram and little prose, and no linked tech spec has one; it never blocks.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Mermaid syntax check | every diagram parses | `npx -y @mermaid-js/mermaid-cli@12.2.0 -i <file>.md -o <tmp>/out.md` on each Markdown file with a `mermaid` fence, as a `tests` entry in CI |
| Diagram rules check | each diagram uses only the classes of the project's own DESIGN.md, unchanged, with `default` and a class on each subgraph, and no `style`, colored `linkStyle`, or `%%{init}%%`; each tint keeps 4.5:1 with the theme's text on both pages; at most twelve nodes and twelve edges; a row that fits the page (D9); `accTitle`, `accDescr`, and a legend | a test in the project's own runner that reads every `mermaid` fence in the tracked Markdown files and the `classDef` lines of the project's DESIGN.md |

## Stop if

- The diagram restates prose, or draws unrelated local fixes.
- One diagram tries to answer two questions, or runs past one screen.
- A frozen diagram is about to change after Spec approval without a new approval.

## Hand off

- Done: the file and the question each diagram answers. Next role: its reader (the verifier for `design-files` docs, the reviewer for the Spec, on-call for a runbook). Needs: a fact the diagram had to assume, named in the Spec's Context. Stopped at: none, or the stop rule's code.
