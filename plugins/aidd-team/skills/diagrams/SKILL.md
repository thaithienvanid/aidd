---
name: diagrams
description: "Practice skill: explain a change as a Mermaid diagram. Use in an aidd repository when a Design, threat model, plan, or runbook needs a picture, or someone asks to draw the flow."
metadata:
  checked: "2026-09-30"
---

# Diagrams

**Use it when** a human must understand a file at a gate or in a review: a Spec's Design (Spec approval), a threat model, an Initiative plan, an ADR, a pipeline, a runbook. One diagram of the shape, then the words. Mermaid, because it is text every agent can write and diff, and it renders without a toolchain.

**Do not use when** prose already answers the question and a picture would only restate it; a diagram of independent local fixes is decoration. Say so in one line instead.

## Standards

<!-- aidd:gen practice:diagrams -->
| Standard | Edition |
| --- | --- |
| Mermaid diagrams as text (flowchart, sequenceDiagram, stateDiagram-v2, erDiagram, gantt), rendered by GitHub, GitLab, and VS Code | — |
| C4 model diagrams | — |
| STRIDE threat modeling with data-flow diagrams | — |
| ISO/IEC/IEEE 42010 (stakeholders, concerns, views) | 2022 |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:diagrams`.
<!-- aidd:end -->

## Specify

One diagram answers one question; the question is its title.

| Question | Diagram | Where it lives |
| --- | --- | --- |
| What does this change touch, and in what order do data and control move? | `flowchart LR`, the change's path highlighted | the Spec's Design |
| Who calls whom, in what order? | `sequenceDiagram` | the Spec's Design or an ADR |
| What states can this screen or entity be in? | `stateDiagram-v2` with every state the designer named (empty, loading, error, partial, success, offline) | `design.files` |
| Where does untrusted data cross a trust boundary? | `flowchart`, a `subgraph` per trust zone, boundaries labeled: the STRIDE data-flow diagram | the threat model |
| How do Epics and Specs depend on each other? | `flowchart TB` from the Initiative to the Specs, edges for `depends_on` | the Initiative's file |
| What does on-call decide, and when do we roll back? | `flowchart TD` of decision points, the rollback trigger a diamond | the runbook |
| What moves through the pipeline, and where is lineage lost? | `flowchart LR` of datasets and jobs | the Spec's Design |

- Draw the smallest true picture: one screen, about a dozen nodes; split anything bigger into two diagrams, two questions. Draw C4 levels (context, container, component) as flowcharts with subgraphs.
- Label edges with what travels (a request, an event, a file) and nodes with the code's names, so the reviewer can grep them.
- Mark the change: style the nodes this Spec adds or alters (`style X fill:#fde68a`) so the reader sees the delta.
- Keep the source in the Markdown file beside the words. No exported PNG without its source; a design tool's image goes in `design.files`, linked to its source.
- Spec approval freezes a diagram in a Spec or `design.files`: changing it after is a Spec change and a new Spec approval.

## Review

- GitHub and GitLab render `mermaid` fences in files, pull requests, and comments; VS Code previews them; the Mermaid live editor renders pasted source.
- Reviewers comment on the diagram's lines as on code; the author updates the source, the Spec hash changes, and the approval line names the new hash: minutes, in the file, no meeting.
- `aidd validate` warns when a major Spec's Design has no diagram and little prose, and no linked tech spec has one; it never blocks.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Mermaid syntax check | every diagram parses | `npx -y @mermaid-js/mermaid-cli@12.0.0 -i specs/SPEC-220/design/flow.mmd -o /tmp/flow.svg` where Node and a headless browser exist; without them, a Mermaid preview shows a broken diagram's parse error |

## Stop if

- The diagram restates prose, or draws unrelated local fixes.
- One diagram tries to answer two questions, or runs past one screen.
- A frozen diagram is about to change after Spec approval without a new approval.

## Hand off

- Done: the file and the question each diagram answers. Next: its reader (the tester for `design.files`, the reviewer for the Spec, on-call for a runbook). Needs: a fact the diagram had to assume, named in the Spec's Context. Stopped at: none, or the stop rule that fired.
