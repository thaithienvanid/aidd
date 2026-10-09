---
name: prototyping
description: "Practice skill: build an interactive prototype for Spec approval. Use in an aidd repository when a user-facing Spec needs a clickable flow, not just a wireframe."
metadata:
  checked: "2026-09-30"
---

# Prototyping

**Use it when** a Spec names a user-facing surface and Spec approval depends on how it *behaves*, not only its layout. It owns the screenshot matrix the UI packs point to.

**Do not use when** the change is copy, one static screen, or a restyle with no new interaction (a wireframe will do), or the flow is built (test the product).

## Standards

<!-- aidd:gen practice:prototyping -->
| Standard | Edition |
| --- | --- |
| Prototype fidelity matched to the decision: interactive where the behaviour is in question, a wireframe where only the layout is | — |
| Plan before code, reviewed against the defaults | — |
| WCAG 2.2 AA, for the prototype itself | 2.2 |
| Design tokens (W3C Design Tokens format) and a design system over one-off styles (emerging) | 2025.10 |
| DESIGN.md format (Google Labs): YAML token front matter, then prose (emerging) | alpha |
| Nielsen's ten usability heuristics | 1994, revised 2020 |
| A state a reviewer cannot reach is one the developer invents: every state from fixtures, a `data-testid` on each control | — |
| A prototype consumes the real tokens, components, and copy, and runs from a clean checkout with one command and no backend | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:prototyping`.
<!-- aidd:end -->

## Specify

### Pick a direction first

1. Plan before code: two or three directions differing in approach, not colour, each with a layout concept, type, and 4–6 named colours on `DESIGN.md` roles. Then an anti-default review ([references/design-review.md](references/design-review.md)).
2. Draw each key screen in the prototype (`aidd new design-spec --prototype`), `?mode=wireframe`. A person, never an agent, picks one, recorded in the Spec's `## Design` (who, when, why). Only then build at full fidelity. `/aidd-team:explore` timeboxes it.

### Build

- One file per flow, `docs/design/<ID>/prototype.html` (`--area <flow>` for more, listed in `docs/design/index.md`): `data-screen`, `data-state`, `data-go`. Every view has a deep link, `prototype.html#<screen>/<state>?theme=dark&frame=ios`.
- The prototype uses the one design system, `DESIGN.md` and `design/tokens.json`, and never copies it. A missing token or component is a separate change. Components first: the system's, else shadcn/ui registry items on Radix primitives on a React stack, otherwise the stack's accessible headless component library ([references/design-system-contract.md](references/design-system-contract.md)).
- The HTML prototype and the design spec are the source of truth. A Claude Design handoff bundle, a Figma link, or its DTCG export is only an input, for example to start a direction.
- Every state is reachable from fixtures. Use real copy at realistic lengths, never lorem ipsum. Wire keyboard, reduced motion, and both themes. Add no backend, secret, network, or build step.

### Rounds

- A round is a pass a person reviews: `docs/design/<ID>/rounds/<N>/`, a screenshot per screen, state, target, and theme. Feedback: `feedback-round-<N>.json`. Answer each item in `rounds/<N+1>/changes.json`. `aidd explore` shows the unanswered. Before a round, run axe per state in both themes at every frame: 320 to 1440, iOS, and Android (`aidd-team:accessible-ui`).

## Review

- After Implement, compare the built UI with the prototype state by state (keyboard, screen reader, 320 CSS pixels). Use pass/fail criteria, each result with its proof, sorted Keep, Fix, or Quick win, no numeric score ([references/design-review.md](references/design-review.md)).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Prototype lint | no raw colour, hotlink, placeholder, or emoji icon; every control named and reachable | a command per rule, [references/prototype-screenshots.md](references/prototype-screenshots.md) |
| Token drift test | the CSS and `DESIGN.md`'s tokens match `design/tokens.json` | `node design/build.mjs --check` (Style Dictionary once it reads DTCG 2025.10) |
| DESIGN.md lint | no broken reference; each component pair 4.5:1 in both themes | `npx @google/design.md@0.4.0 lint DESIGN.md`, failing on a `broken-ref` or `contrast-ratio` finding |
| Screenshot matrix | no unreviewed change per screen, state, target, and theme | web: Playwright `toHaveScreenshot()` after `page.emulateMedia({ colorScheme })`, one pinned OS image, `*-snapshots/` in `tests.files` (Spec approval freezes the baseline), `<screen>-<state>-<target>-<theme>.png` (`<screen>-<state>-<target>.png` with `dark_mode` off); iOS: swift-snapshot-testing, `performAccessibilityAudit`; Android: Paparazzi or Roborazzi, Espresso accessibility checks |

## Stop if

- Nobody picked a direction and you are about to build at full fidelity.
- The prototype needs a colour, font, or component the design system lacks.
- You are about to change design files Spec approval froze.

## Hand off

- Done: the direction recorded, the prototype in `design.files` with every state reachable, and its tests for the tester to freeze (`new_behavior = false`). Next: the tester, then Spec approval. Needs: a person to pick a direction, a state with no right answer, or a missing token. Stopped at: none, or the stop rule that fired.
