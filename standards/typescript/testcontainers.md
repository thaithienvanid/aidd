---
id: typescript/testcontainers
type: opinionated
fills: [test-design:integration-test-services]
default: true
implements: test-design:Real throwaway dependencies
roles: [developer, verifier, reviewer]
when_changed: ["**/*.integration.test.ts", vitest.config.ts, package.json]
why: "Testcontainers for Node.js starts the real database and services from the test run, one throwaway container each, and its modules, such as PostgreSQL, hand the test a ready connection URI."
maturity: established
tool:
  name: testcontainers-node
  registry: npm
  package: testcontainers
version_policy: current_stable
checked_version: "12.2.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://node.testcontainers.org/
  quote: "Testcontainers is a library that supports tests, providing lightweight, throwaway instances of common databases, Selenium web browsers, or anything else that can run in a Docker container."
alternatives: [Docker Compose started by the test run, the provider's local emulator]
status: active
lock_command: [pnpm, add, -D, testcontainers]
enforced_by:
  - name: integration
    command: [pnpm, exec, vitest, run, --project, integration]
---

# Testcontainers starts the TypeScript integration-test services

It answers the integration-test-services choice of `aidd-team:test-design` for TypeScript on Node.js. License: MIT.

## What the team does

- Add `testcontainers` and the module for each service, such as `@testcontainers/postgresql`, as exact dev dependencies.
- Name each integration test `*.integration.test.ts`, and run them in a Vitest project named `integration`, so the unit tests run without Docker.
- Start each container with `await using`, or stop it in `afterAll`, so none outlives its suite.
- Give each image a tag and digest, on the same major release as production.
- Read the address from the container, such as `getConnectionUri()`, never from a fixed host or port.
- Apply the real migrations to the container before the tests, with the project's migration tool.

## What the tests run

One `tests` entry runs the `integration` Vitest project. A container that does not start, or a failing test, fails the change.
