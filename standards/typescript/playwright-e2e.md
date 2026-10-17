---
id: typescript/playwright-e2e
type: opinionated
fills: [web-front-end:e2e-test]
default: true
implements: web-front-end:Cookie and tracker consent test
roles: [tester, developer, reviewer]
when_changed: ["app/**", "src/**", "e2e/**", playwright.config.ts, package.json]
why: "Playwright drives Chromium, Firefox, and WebKit from one API, records each request, cookie, and trace, and is the runner the accessibility and product-default checks already use."
reviewed: "2026-10-16"
maturity: established
version_policy: current_stable
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@playwright/test/dist-tags
evidence: "\"latest\":\"1.64.1\""
alternatives: [Cypress, WebdriverIO]
status: active
enforced_by:
  - name: e2e
    command: [pnpm, exec, playwright, test]
---

# Playwright drives the end-to-end tests

It answers the e2e-test choice of `aidd-team:web-front-end`.

## What the team does

- Add `@playwright/test` as an exact dev dependency at the release the packs name, and install its browsers in CI with `playwright install --with-deps`.
- Keep the tests in `e2e/`, one file per user journey, against a production build started by `webServer` in `playwright.config.ts`.
- Find elements by role, label, and text. A CSS or XPath selector needs a reason beside it.
- Wait on web-first assertions (`expect(locator)`), never on a fixed sleep.
- Keep the trace for each failed test (`trace: 'retain-on-failure'`) as the evidence a person reads.

## What the gate runs

One `tests` entry runs `playwright test`. A failing journey fails the change.
