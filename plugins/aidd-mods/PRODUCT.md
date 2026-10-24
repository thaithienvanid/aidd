# Product

<!-- impeccable:product-schema 1 -->

The aidd pane: `/aidd status` in Claude Code, drawn by the `aidd-mods` plugin beside the conversation. This record covers the pane only; aidd itself is described in the repository's README and docs/METHOD.md.

## Platform

web

<!-- A terminal interface inside Claude Code (its mod API: Box, Text, Button, theme color names), not a web page. Recorded as `web` because no native platform applies. -->

## Users

- **The lead (primary):** the person who uses aidd and its AI team in their coding harness and owns the decisions. They glance at the pane between turns, often for seconds, to see what waits on them and how the work stands, then type a decision at the prompt.
- **A developer pairing (secondary):** someone working one branch beside the agents, who opens the pane for that branch's Spec, its Tasks, and what blocks them.

Inferred from the conversation of 2026-10-17: the owner named the lead first and said "maybe both".

## Product Purpose

Show what the aidd engine already decided, without spending a model turn. It shows the person's four decisions: D1 the plan, D2 Spec approval, D3 the release, and D4 the launch. It shows the shape of the work: big goals, small goals, and how each reaches users (incremental, flagged, or batched). It also shows this branch's items, autopilot's run, and the trunk-based flow. Success: the lead knows within one glance whether anything needs them, and what to type.

## Positioning

The pane only shows what the aidd CLI prints; it never decides. The person's typed words ("approve SPEC-1", "land it", "merge it") are the decision, recorded by the mod for exactly the hash or head it shows. A typed "publish" goes on to aidd's own prompt hook, since the mod never pushes. Nothing the pane draws reaches the model.

## Operating Context

- Lives in a terminal, docked beside the conversation or inline above the prompt; it may be 40 to 200 columns wide.
- Refreshes after each turn; data comes from `aidd list --json`, `aidd list --waiting-on-me --json`, `aidd goal list --json`, and `aidd autopilot status --json`, each with a time limit.
- Keyboard first: arrow keys, Enter, single-letter hotkeys; the mouse also works on buttons.

## Capabilities and Constraints

- Drawing primitives: `Box`, `Text`, `Button` from Claude Code's mod API; colors are theme names (`claude`, `suggestion`, `success`, `warning`, `error`), with bold and dim.
- No network calls of its own, no writes except the decisions a person typed or confirmed in Claude Code's dialog.
- Every number and status comes from aidd; the pane invents none.

## Product Principles

1. The person's decisions come first; everything else is context for them.
2. Show who moves next, not just a status.
3. Each line says what to type or run next.
4. Calm by default: color marks only what needs someone.

## Accessibility & Inclusion

Color never carries meaning alone: every colored state also has a word or a symbol. Works at 40 columns.
