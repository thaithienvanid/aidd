---
type: llm
---

PASS if the reply declines the single all-in-one change and proposes one change per package or coherent group (for example `react` with `react-dom`), with each major version (such as Express 5, a new React, or a new ESLint) as its own change that reads the changelog and migration guide and applies the official codemod where there is one; checks advisories (OSV, `npm audit`) and provenance; runs the full suite per change; keeps rollback to reverting that change's manifest and lockfile; and flags the deprecated or unmaintained package (`left-pad`) as a removal rather than an upgrade.
FAIL if the reply produces or endorses one change that bumps everything, treats major versions like patches, or says nothing about changelogs, advisories, or rollback.
