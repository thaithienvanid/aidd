---
id: typescript/pino-logging
type: opinionated
fills: [observability:logging-library]
default: true
implements: observability:Logs
roles: [developer, sre, reviewer]
when_changed: ["**/*.ts", package.json]
why: "Pino writes one JSON object per log line with little overhead, redacts named paths, and is Fastify's built-in logger, so a Node.js service needs no second logging library."
reviewed: "2026-10-16"
maturity: established
tool:
  name: pino
  registry: npm
  package: pino
version_policy: current_major
checked_version: "10.4.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/pino/dist-tags
evidence: "\"latest\":\"10.4.0\""
alternatives: [Winston, LogTape, "the runtime's console, writing JSON lines"]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/pino/package.json').version.startsWith('10.') ? 0 : 1)"
---

# Pino writes the TypeScript service's logs

It answers the logging-library choice of `aidd-team:observability` for a TypeScript service on Node.js. License: MIT.

## What the team does

- Build one root logger at start, with the level read from config, and pass child loggers (`logger.child({...})`) to each module. In Fastify, use `request.log`.
- Name every secret or personal field in the `redact` option, with `remove: true` where the field must not appear at all.
- Log an error under the `err` key, so Pino's serializer keeps its message and stack.
- Write to stdout and let the platform ship the lines. Keep `pino-pretty` a dev dependency for local reading only.

## What the gate runs

One `tests` entry fails when the installed Pino is not the major this file was checked at, so an upgrade is a reviewed change.
