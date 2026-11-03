---
name: prototyping
description: "Practice skill: build an interactive prototype for Spec approval. Use in an aidd repository when a user-facing Spec needs a clickable flow, not just a wireframe."
metadata:
  checked: "2026-10-22"
---

# Prototyping

**Use it when** a Spec names a user-facing surface and Spec approval depends on how it *behaves*, not only its layout. It owns the screenshot matrix the UI packs point to.

**Do not use when** the change is copy, one static screen, or a restyle with no new interaction, or the flow is built (test the product). A restyle still lists the parts to keep.

## Standards

<!-- aidd:gen practice:prototyping -->
| Standard | Edition |
| --- | --- |
| Prototype fidelity matched to the decision: interactive where the behavior is in question, a wireframe where only the layout is | — |
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

### Size it, then pick a direction

Size the work to the ask: one screen or flow is one prototype file, maybe the whole job. Offer directions only when the approach is open or the person asks.

1. Plan before code: two or three directions differing in approach, not color, each with a layout concept, type, and 4–6 named colors on `DESIGN.md` roles. Then an anti-default review ([references/design-review.md](references/design-review.md)).
2. Sketch each direction's key screen in an exploration (`aidd explore`, timeboxed by `/aidd-team:explore`). A person, never an agent, picks one, recorded in the Spec's `## Design` (who, when, why). Only then build the prototype at full fidelity.

### Build

- One file per flow, `specs/<ID>/design/prototype.html` (`aidd new design-spec --prototype`; `--area <flow>` for more), in the format its comment teaches. Where the project keeps a product prototype, `docs/design/app/`, the same change updates it; never start one unasked. `aidd prototype <file>` opens it; each view has a deep link, `#<screen>/<state>?theme=dark&frame=ios`.
- The file holds the design only; the viewer is the tool's.
- Name each reusable part `data-component`, with `data-variant`, and each screen and label, by `aidd-team:naming`; the developer builds each (`web-front-end:component-catalog`).
- The prototype uses the one design system, `DESIGN.md` and `design/tokens.json`, and never copies it. A missing token or component is a separate change. Components first: the system's, else the `web-front-end:component-library` choice, such as shadcn/ui on Radix, or a headless library ([references/design-system-contract.md](references/design-system-contract.md)).
- Match the showcase's format and finish (`aidd prototype --example`); never start from it.
- Use the design tools the project enabled in its settings, else the prototype tool (`aidd prototype --help`; without aidd, `tools/prototype/README.md`). The HTML prototype and the design spec stay the source of truth. A tool's export, for example a Claude Design handoff bundle, a Figma link, or DTCG, is only an input, rewritten into the format.
- Every state is reachable from fixtures. Use real copy at realistic lengths, never lorem ipsum. Never invent a metric, testimonial, logo, or customer count; mark a slot instead. Wire keyboard, reduced motion, and both themes. Add no backend, secret, network, or build step.
- A redesign first lists, in the design spec, the parts it must keep: every link, form field, handler, test id, heading, and route. The verifier turns the list into a frozen test. A part dropped on purpose is a line in the Spec.

### Rounds

- A round is a pass a person reviews: `specs/<ID>/design/rounds/<N>/`, a screenshot per screen, state, target, and theme. Feedback: `feedback-round-<N>.json`. Answer each item in `rounds/<N+1>/changes.json`. `aidd explore` shows the unanswered. Before a round and done, run the full fidelity pass (320 to 1024, both themes, axe, placement) ([references/design-review.md](references/design-review.md)).

## Review

- After Implement, compare the built UI with the prototype state by state: keyboard, screen reader, and 320 CSS px. Name its screenshots as the loop does, for Compare. Use pass/fail criteria, each result with its proof, sorted Keep, Fix, or Quick win, no numeric score ([references/design-review.md](references/design-review.md)).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Prototype lint | no raw color, hotlink, placeholder, or emoji icon; every control named and reachable | a command per rule, [references/prototype-screenshots.md](references/prototype-screenshots.md) |
| Token drift test | the CSS and `DESIGN.md`'s tokens match `design/tokens.json` | `node design/build.mjs --check` (Style Dictionary once it reads DTCG 2025.10) |
| DESIGN.md lint | no broken reference; each component pair 4.5:1 in both themes | `npx @google/design.md@0.4.0 lint DESIGN.md`, failing on a `broken-ref` or `contrast-ratio` finding |
| Screenshot matrix | no unreviewed change per screen, state, target, and theme | web: Playwright `toHaveScreenshot()` after `page.emulateMedia({colorScheme})`, one pinned OS image, `*-snapshots/` in `tests.files` (Spec approval freezes the baseline), `<screen>-<state>-<target>-<theme>.png` (`<screen>-<state>-<target>.png` with `dark_mode` off); iOS: swift-snapshot-testing, `performAccessibilityAudit`; Android: Paparazzi or Roborazzi, Espresso accessibility checks |

## Stop if

- An open approach has no picked direction, and you are about to build at full fidelity.
- The prototype needs a color, font, or component the design system lacks.
- You are about to change design files Spec approval froze.
- A redesign drops a part it listed to keep, and the Spec doesn't say so.

## Hand off

- Done: the direction recorded, if any, the prototype in `design.files` with every state reachable, and its tests for the verifier to freeze (`new_behavior: false`). Next: the verifier, then Spec approval. Needs: a person to pick a direction, a state with no right answer, or a missing token. Stopped at: none, or the stop rule that fired.
