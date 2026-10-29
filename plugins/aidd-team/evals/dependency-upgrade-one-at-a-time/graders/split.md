---
type: llm
---

PASS if the reply declines the single all-in-one change and does all of these:

- It proposes one change per package or coherent group, for example `react` with `react-dom`.
- Each major version (such as Express 5, a new React, or a new ESLint) is its own change. That change reads the changelog and migration guide, and applies the official codemod where there is one.
- It checks advisories (OSV, `npm audit`) and provenance, and runs the full suite per change.
- It keeps rollback to reverting that change's manifest and lockfile.
- It flags the deprecated or unmaintained package (`left-pad`) as a removal rather than an upgrade.

FAIL if the reply produces or endorses one change that bumps everything, treats major versions like patches, or says nothing about changelogs, advisories, or rollback.
