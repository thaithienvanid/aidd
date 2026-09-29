---
name: prototyping
description: "Practice skill: build a high-fidelity, interactive prototype that a human approves at Spec approval and the team builds against. Use when a Spec has a user-facing surface and `design.files` needs more than a wireframe, or when someone asks for a clickable prototype, a mock-up that works, a demo of the flow, design directions or options to choose from, a design system or tokens for a prototype, or a design review of the built UI: rough directions a person picks from first, one named design system (DESIGN.md and tokens), lint rules the tester can freeze, and a Keep, Fix, Quick win review with proof."
metadata:
  checked: "2026-09-28"
---

# Prototyping

**Use it when** a Spec names a user-facing surface and the decision at Spec approval depends on how the thing *behaves*, not only on how it is laid out. A wireframe answers "where does it go"; a prototype answers "what is it like to use".

**Do not use when** the change is copy, one static screen, or a restyle with no new interaction (a wireframe is enough), or the flow is already built (test the product instead).

## Standards

- ISO 9241-210:2019 human-centred design and ISO 9241-110:2020 interaction principles: design, then evaluate on something that responds to input, before the build commits.
- Fidelity as a dial (Nielsen Norman Group): match fidelity to the decision. Rough while choosing a direction, high fidelity only for the chosen one.
- WCAG 2.2 AA applies to the prototype itself; the detail is in `aidd-team:accessible-ui`.
- Design Tokens Format Module 2025.10 (Design Tokens Community Group, Final Community Group Report, 28 October 2025; not a W3C Standard) for the tokens file.
- Nielsen's ten usability heuristics (1994, revised 2020) to name what a review point rests on.

## Pick a direction first

- Before any detail, offer two or three rough directions for the same brief: low fidelity, the key screen of the flow in each, and one line on what each one favors. Make them differ in approach, not in colour.
- A person picks one. Record it in the Spec's `## Design` section: the direction, who picked it, the date, and why the others lost. The rough sketches stay in `design.files` next to the prototype.
- Only then build the chosen direction at full fidelity. An agent never picks the direction for the person.

## Specify, before Spec approval

- One prototype per flow the Spec's Acceptance names: the entry point, the decisions, the errors, and the exit.
- It uses one named design system: a short `DESIGN.md` (principles, type scale, colour roles, spacing, components used) and a tokens file in the Design Tokens format. Both live in `design.files`, so Spec approval freezes them with the prototype. Shape and drift test: [references/design-system-contract.md](references/design-system-contract.md).
- Name the states it must reach (empty, loading, error, partial, success, offline) and how a reviewer reaches each; an unreachable state gets invented by the developer.
- It runs with one command, from a clean checkout, with no secrets and no backend. A prototype that needs a service is a build.

## Build

- A static `index.html` plus assets, or the project's framework with fixtures. No production code, real API calls, or auth.
- Every colour, size, and space comes from the tokens. Real copy at realistic lengths, never lorem ipsum: the short name, the 200-character one, the zero-row case.
- Wire focus order, keyboard operation, loading and error transitions, the destructive-action confirmation, undo, `prefers-reduced-motion`, and `prefers-color-scheme`.
- Fixture data in one place, switchable per state; a stable `data-testid` on every interactive element.
- A banner and a `README` say it is a design artifact, frozen at Spec approval, never imported by product code.

## Test commands, into the Spec's tests

- The prototype lint, deterministic so the tester can freeze it: no raw colour outside the tokens file, no hotlinked images or fonts, no placeholder text, no emoji as icons, and every interactive element with a name and reachable by keyboard. Commands: [references/prototype-lint.md](references/prototype-lint.md).
- The token drift test: regenerate the CSS or theme file from the tokens and diff it with the committed one.
- Playwright with axe-core per named state, and a serve check (200 from a clean checkout). All `new_behavior = false`: nothing in production changed.

## Review

- Drive every named state keyboard-only, with a screen reader, and at 320 CSS pixels wide.
- After Implement, compare the built UI with the prototype state by state and write the report as Keep, Fix, or Quick win, each point with its proof and no score: [references/design-review.md](references/design-review.md). An improvement on the prototype goes back through Spec approval.

## Hand off

- Done: the chosen direction recorded, `DESIGN.md`, the tokens file, and the prototype in `design.files`, every state reachable, and the lint and state list for the tester. Next: the tester, to freeze them as the Spec's tests; then Spec approval. Needs: a person to pick a direction, a decision when a state has no right answer, or a token the design system lacks. Stopped at: none, or the stop rule that fired.

## Stop if

- Nobody has picked a direction and you are about to build at full fidelity.
- The prototype needs a colour, font, or component the named design system does not have: ask, do not invent one.
- A Spec approval already froze the design files and you are about to change them.
