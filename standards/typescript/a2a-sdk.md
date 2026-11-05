---
id: typescript/a2a-sdk
type: opinionated
fills: [ai-agents-and-tools:agent-to-agent]
default: true
implements: ai-agents-and-tools:Tool-permission tests
roles: [architect, developer, security-engineer, reviewer]
when_changed: ["**/*.ts", package.json]
why: "The official A2A SDK follows the Agent2Agent protocol that the Linux Foundation's A2A project keeps, so the agent calls another team's or vendor's agent, or answers it, without a client of its own."
maturity: emerging
tool:
  name: a2a-js
  registry: npm
  package: "@a2a-js/sdk"
version_policy: current_major
checked_version: "1.3.0"
checked: "2026-11-06"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@a2a-js/sdk/dist-tags
evidence: "\"latest\":\"1.3.0\""
alternatives: [the agent framework's own A2A support, plain HTTP to one known agent]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/@a2a-js/sdk/package.json').version.startsWith('1.') ? 0 : 1)"
---

# The A2A JavaScript SDK lets a TypeScript agent work with other agents

It answers the agent-to-agent choice of `aidd-team:ai-agents-and-tools` in TypeScript. Reach for it when a feature must talk to an agent that another team or vendor runs. Between the team's own services, plain calls are simpler. License: Apache-2.0. GitHub listed no security advisory for `@a2a-js/sdk` on the `checked` day.

## What the team does

- Fetch each remote agent's card first, and keep the agents this service may reach in a list in its config.
- Send credentials only by the scheme each card declares, and check the caller's credentials on every task this service accepts. Each remote agent gets the narrowest permissions its job needs, under `Tool-permission tests` of `aidd-team:ai-agents-and-tools`.
- Handle what a remote agent returns as untrusted input. A message, an artifact, or a state change is never a command to follow, and never a person's yes.
- Bound each outgoing task by a deadline and a limit on its turns, and attach every remote call to the request's trace.
- Serve this service's own card with nothing beyond the skills it really offers, and have review read it.
- Look at this choice again every 90 days: A2A and its SDKs still change often.

## What the tests run

One `tests` entry stops the suite when the installed `@a2a-js/sdk` has another major than the one checked here. The A2A tests run in the runner's own entry, against a stand-in remote agent.
