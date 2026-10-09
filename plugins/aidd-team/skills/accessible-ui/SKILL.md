---
name: accessible-ui
description: "Practice skill: build and check accessible UI (WCAG 2.2 AA). Use in an aidd repository when a Task changes a screen, form, or UI copy, or someone says a11y, focus, or contrast."
metadata:
  checked: "2026-09-30"
---

# Accessible UI

**Use it when** a Task adds or changes a screen, component, form, or user-facing copy, on the web or in a mobile app. The `aidd-team:web-front-end` and `aidd-team:mobile-apps` packs say what applies. This skill is how to do the work. It owns the accessibility tests the packs point to.

**Do not use when** the change touches no screen, document, or user-facing text, or the question is mapping a legal obligation, which is the compliance analyst's, not a build practice.

## Standards

<!-- aidd:gen practice:accessible-ui -->
| Standard | Edition |
| --- | --- |
| WCAG 2.2 AA | 2.2 |
| WAI-ARIA and the ARIA Authoring Practices | WAI-ARIA 1.2 |
| EN 301 549 accessibility requirements for ICT products and services | V4.1.1 |
| W3C ACT Rules as the machine-checkable form of a WCAG success criterion | ACT Rules Format 1.1 |
| Apple Human Interface Guidelines and Material Design 3 | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:accessible-ui`.
<!-- aidd:end -->

## Specify

- Every screen state (empty, loading, error, partial, success, offline) has accessibility notes: name, role, state, and its keyboard path.
- Targets are at least 24 by 24 CSS pixels (WCAG 2.5.8). Text contrast is 4.5:1 and UI contrast 3:1. Motion has a reduced alternative. Each error is described in text and tied to its field.

## Implement

- Use semantic HTML or platform components first. Use ARIA only where no native element exists, with only the roles and states the pattern defines.
- Focus is visible (WCAG 2.4.7), not obscured by sticky content (2.4.11), never trapped. Manage it on dialogs and route changes. Tab order follows reading order.
- Every image has a text alternative or is marked decorative. Media have captions and transcripts. Forms have labels, instructions, and error recovery.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`. Content and function survive 200 percent zoom and a 320 CSS pixel width.

## Review

- Tab through every state. Check contrast, focus, announcements on dynamic updates, and that nothing depends on color, hover, or a pointer alone.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Accessibility per state | no WCAG 2.2 A or AA violation in any screen state or theme | axe-core per state (`@axe-core/playwright@4.13.0`, or `npx @axe-core/cli@4.13.0`), after `page.emulateMedia({ colorScheme })` for each theme |
| Keyboard-only flows | every critical flow completes by keyboard, in the order the Spec names | Playwright (`@playwright/test@1.63.0`) tests that Tab through each flow, asserting each focused `data-testid` |
| Screen-reader pass | the flows the Spec names are announced and operable | a recorded pass with NVDA, VoiceOver, and TalkBack |
| Mobile accessibility checks | labels, contrast, and touch targets pass on each native screen, automated | XCUITest `performAccessibilityAudit()` on the `XCUIApplication` (iOS 17 or later); Espresso `AccessibilityChecks.enable()` (`androidx.test.espresso.accessibility`) in the instrumented tests |

## Stop if

- A state was never designed, so its name, role, or keyboard path would be invented.
- A fix would add ARIA where a native element exists, or suppress an axe rule rather than meet it.
- A mobile screen has only a manual accessibility check, none automated in the tests.

## Hand off

- Done: the UI with its accessibility tests green. Next: the product designer's design review, then the reviewer. Needs: a design decision when a state was never designed. Stopped at: none, or the stop rule that fired.
