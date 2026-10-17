---
id: typescript/testing-library
type: opinionated
fills: [web-front-end:component-test]
default: true
implements: accessible-ui:Accessibility per state
roles: [developer, tester, reviewer]
when_changed: ["**/*.tsx", "**/*.test.tsx", package.json]
why: "Testing Library finds elements the way a person does, by role, label, and text, so a component test breaks when the behavior or the accessible name changes, not when the markup moves."
reviewed: "2026-10-16"
maturity: established
tool:
  name: testing-library
  registry: npm
  package: "@testing-library/react"
version_policy: current_major
checked_version: "16.3.3"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@testing-library/react/dist-tags
evidence: "\"latest\":\"16.3.3\""
alternatives: [Vitest browser mode, Cypress component testing, Storybook interaction tests]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/@testing-library/react/package.json').version.startsWith('16.') ? 0 : 1)"
---

# Testing Library tests the React components

It answers the component-test choice of `aidd-team:web-front-end`.

## What the team does

- Render each component with `@testing-library/react`, run by the project's test runner in a DOM environment.
- Query by role and accessible name first (`getByRole`), then by label and text. A test id is the last resort, with a reason.
- Drive input with `@testing-library/user-event`, including the keyboard path through the component.
- Assert what a person sees or hears, never a component's state or its private props.
- Render each state that `Accessibility per state` of `aidd-team:accessible-ui` names, and query it by role and name.

## What the gate runs

The component tests run in the test runner's own `tests` entry. This standard adds one entry that checks the project resolves the major release it was checked at.
