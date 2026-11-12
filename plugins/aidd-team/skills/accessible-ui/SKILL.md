---
name: accessible-ui
description: "Practice skill: build and check accessible, comfortable UI. Use in an aidd repository when a Task changes a screen, form, or UI copy, or someone says a11y, focus, contrast, or eye strain."
metadata:
  checked: "2026-10-22"
---

# Accessible UI

**Use it when** a Task adds or changes a screen, component, form, or user-facing copy. The `aidd-packs:web-front-end` and `aidd-packs:mobile-apps` packs say what applies; this skill says how, and owns the accessibility tests they point to.

**Do not use when** the change touches no screen, document, or user-facing text, or the question is a legal obligation, the compliance analyst's.

## Standards

<!-- aidd:gen practice:accessible-ui -->
| Standard | Edition |
| --- | --- |
| WCAG 2.2 AA | 2.2 |
| APCA contrast (emerging) | — |
| WCAG 3.0, as the direction of the standard only (emerging) | W3C Working Draft |
| WAI-ARIA and the ARIA Authoring Practices | WAI-ARIA 1.2 |
| EN 301 549 accessibility requirements for ICT products and services | V4.1.1 |
| W3C ACT Rules as the machine-checkable form of a WCAG success criterion | ACT Rules Format 1.1 |
| Apple Human Interface Guidelines and Material Design 3 | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:accessible-ui`.
<!-- aidd:end -->

## Specify

- Every screen state (empty, loading, error, partial, success, offline) has accessibility notes: name, role, state, and keyboard path.
- Targets are at least 24 by 24 CSS pixels (WCAG 2.5.8). Text contrast of 4.5:1 and UI of 3:1 is the floor below [comfort](references/comfort.md). Each error is described in text and tied to its field.
- The WCAG 2.2 criteria teams miss: [references/criteria.md](references/criteria.md). The EU statement, and where WCAG 3 is heading as habits, never a check or a claim: [references/statement.md](references/statement.md).

## Implement

- Use semantic HTML or platform components first. Use ARIA only where no native element exists, with only the roles and states the pattern defines.
- Focus is visible (WCAG 2.4.7), not obscured by sticky content (2.4.11), never trapped. Manage it on dialogs and route changes. Tab order follows reading order.
- Before you change a control's look or a state indicator, such as a focus ring or a selection mark, read "State indicators" in [references/criteria.md](references/criteria.md). It says how to draw each indicator from the object it decorates and keep every interaction state apart, and gives the check.
- Every image has a text alternative or is marked decorative. Media have captions and transcripts. Forms have labels, instructions, and error recovery.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`. Content and function survive 200% zoom and a 320 CSS pixel width.

## Review

- Tab through every state. Check contrast and comfort, focus, announcements on dynamic updates, and that nothing depends on color, hover, or a pointer alone.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Accessibility per state | no violation of the WCAG A and AA rules axe checks, per state, theme, and motion | axe-core with the WCAG tags, as [references/criteria.md](references/criteria.md) says |
| Comfort checks | each comfort rule in both themes | a token script and a state probe, as comfort.md says |
| State check | no two interaction states of a changed control look alike or differ only by color, and no indicator takes its edge's color, on each variant and theme | `look` and `stateProblems` in the screenshot loop, as [references/criteria.md](references/criteria.md) says |
| Keyboard-only flows | every critical flow completes by keyboard, in the order the Spec names | the `e2e-test` runner (`web-front-end:e2e-test`) Tabs through each flow, asserting each focused `data-testid` |
| Screen-reader pass | a person heard the flows the Spec names announced and operable | a recorded pass with NVDA, VoiceOver, and TalkBack, a person's evidence |
| Mobile accessibility checks | labels, contrast, and touch targets pass on each native screen, automated | XCUITest `performAccessibilityAudit()` (iOS 17 or later); Espresso `AccessibilityChecks.enable()`; a toolkit's own checks |

## Stop if

- A state was never designed, so its name, role, or keyboard path would be invented.
- A fix would add ARIA where a native element exists, or suppress an axe rule rather than meet it.
- A mobile screen has only a manual accessibility check.

## Hand off

- Done: the UI with its accessibility tests green. Next role: the product designer's design review, then the reviewer. Needs: a decision for a state never designed. Stopped at: none, or the stop rule's code.
