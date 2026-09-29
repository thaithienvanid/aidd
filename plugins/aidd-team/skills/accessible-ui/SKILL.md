---
name: accessible-ui
description: "Practice skill: build and check an accessible user interface. Use when a Task adds or changes a screen, a component, a form, a dialog, a menu, an error message, or user-facing copy, or when someone mentions accessibility, a11y, WCAG, screen readers, keyboard navigation, focus, tab order, contrast, alt text, ARIA, reduced motion, or an axe or Lighthouse accessibility failure: WCAG 2.2 AA from the first sketch, semantics before ARIA, keyboard and focus, contrast, motion, and the test commands that prove them."
metadata:
  checked: "2026-09-25"
---

# Accessible UI

**Use it when** a Task adds or changes a screen, a component, a form, or user-facing copy, on the web or in a mobile app. The `aidd-team:web-front-end` and `aidd-team:mobile-apps` packs say what applies; this skill is how to do the work.

**Do not use when** the change touches no screen, document, or user-facing text a person reads; or the accessibility question is a legal obligation mapping, which is compliance-analyst's, not a build practice.

## Standards

- WCAG 2.2 AA.
- WAI-ARIA 1.2 and the ARIA Authoring Practices.
- EN 301 549.
- The Apple Human Interface Guidelines and Material Design accessibility guidance.

## Specify, before Spec approval

- Every screen state (empty, loading, error, partial, success, offline) has accessibility notes: name, role, state, and the keyboard path through it.
- Targets are at least 24 by 24 CSS pixels (WCAG 2.5.8); text contrast is 4.5:1 and UI contrast 3:1; motion has a reduced alternative; errors are described in text and associated with their field.

## Implement

- Semantic HTML or platform components first; ARIA only where no native element exists, and only the roles and states the pattern defines.
- Focus is visible (WCAG 2.4.7) and not obscured by sticky content (2.4.11), never trapped, and managed on dialogs and route changes; the tab order follows the reading order.
- Every image has a text alternative or is marked decorative; media has captions and transcripts; forms have labels, instructions, and error recovery.
- `prefers-reduced-motion` and `prefers-color-scheme` are respected; zoom to 200 percent and 320 CSS pixel widths keep content and function.

## Test commands

- axe-core per screen state (`@axe-core/cli` or axe in Playwright); Lighthouse accessibility budget; Playwright keyboard-only tests for the critical flows; a screen-reader pass (NVDA, VoiceOver, TalkBack) recorded for the flows the Spec names.

## Review

- Tab through every state; check contrast and focus; check announcements on dynamic updates; check that nothing depends on color, hover, or a pointer alone.

## Hand off

- Done: the UI with its accessibility tests green. Next: the product designer's design review, then the reviewer. Needs: a design decision when a state was never designed. Stopped at: none, or the stop rule that fired.
