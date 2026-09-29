---
name: diagrams
description: "Practice skill: explain a change visually, as a Mermaid diagram in the file itself. Use when writing a Spec's Design, a threat model, an Initiative map, an architecture decision, a data pipeline, or a runbook, or when someone asks to draw it, show the flow, a sequence diagram, an architecture or data-flow diagram, a state machine, or Mermaid: which diagram for which question, how to keep it small and honest, how humans preview and discuss it, and how to check it renders."
metadata:
  checked: "2026-09-25"
---

# Diagrams

**Use it when** a file is meant to be understood by a human at a gate or in a review: a Spec's Design (Spec approval), a threat model, an Initiative plan, an ADR, a pipeline, a runbook. One diagram of the shape, then the words.

**Do not use when** prose already answers the question and a picture would only restate it; a diagram of a list of independent local fixes is decoration. Say so in one line instead.

## Standards

- Mermaid (flowchart, sequenceDiagram, stateDiagram-v2, erDiagram, gantt; C4 diagrams stay experimental in Mermaid, so draw C4 levels as flowcharts with subgraphs).
- Mermaid is the format because it is text (every agent can write and diff it), it renders on GitHub, GitLab, and in VS Code without a toolchain, and it has been maintained since 2014.
- The C4 model for what goes in an architecture picture (context, container, component).
- STRIDE data-flow diagrams for threat models.
- ISO/IEC/IEEE 42010 for naming the concern a view answers.
- One diagram answers one question; the question is its title.

## Which diagram

| Question | Diagram | Where it lives |
| --- | --- | --- |
| What does this change touch, and in what order does data or control move? | `flowchart LR` with the components as nodes and the change's path highlighted | the Spec's Design |
| Who calls whom, in what order? | `sequenceDiagram` | the Spec's Design or an ADR |
| What states can this screen or entity be in? | `stateDiagram-v2` with every state the designer named (empty, loading, error, partial, success, offline) | `design.files` |
| Where does untrusted data cross a trust boundary? | `flowchart` with `subgraph` per trust zone and the boundaries labeled: the STRIDE data-flow diagram | the threat model |
| How do Epics and Specs depend on each other? | `flowchart TB` from the Initiative to the Specs, edges for `depends_on` | the Initiative's file |
| What does the on-call person decide, and when do we roll back? | `flowchart TD` of decision points, the rollback trigger as a diamond | the runbook |
| What moves through the pipeline, and where is lineage lost? | `flowchart LR` of datasets and jobs | the Spec's Design |

## Draw

- Draw the smallest true picture: at most one screen, at most about a dozen nodes; split anything bigger into two diagrams with two questions.
- Label edges with what travels (a request, an event, a file), and nodes with the names the code uses, so the reviewer can grep them.
- Mark the change: style the nodes this Spec adds or alters (`style X fill:#fde68a`), so the reader sees the delta, not the whole system.
- Keep the source in the Markdown file next to the words. No exported PNG without its source; an image from a design tool goes in `design.files` with a link to its source.
- A diagram in a Spec or in `design.files` is frozen by Spec approval like the rest: changing it after approval is a Spec change and a new Spec approval.

## Preview and discuss

- GitHub and GitLab render `mermaid` code fences in files, pull requests, and comments; VS Code previews them with the built-in Markdown preview plus a Mermaid extension; the Mermaid live editor renders pasted source.
- Reviewers comment on the diagram's lines in the pull request, like on code; the author updates the source, the Spec hash changes, and the approval line names the new hash. That is the feedback loop: minutes, in the file, with no meeting.
- `aidd validate` warns when a normal or major Spec has no diagram; it never blocks on one.

## Test commands

- Optional syntax check where Node is available: `npx -y @mermaid-js/mermaid-cli -i docs/design/flow.mmd -o /tmp/flow.svg` (mermaid-cli, 2018; needs a headless browser). Without it, a Markdown preview that renders Mermaid (a forge's file view, or an editor's preview) is the check: a broken diagram shows its parse error.

## Hand off

- Done: the file and the question each diagram answers. Next: the role that reads it (the tester for `design.files`, the reviewer for the Spec, the on-call for a runbook). Needs: a fact the diagram had to assume, named in the Spec's Context. Stopped at: none, or the stop rule that fired.
