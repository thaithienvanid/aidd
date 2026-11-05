---
id: typescript/mastra-agents
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, reviewer]
when_changed: ["**/*.ts", package.json]
why: "Mastra gives a TypeScript team agents, tools, workflows, and memory in one framework, with typed tool inputs and a local playground to try an agent before it ships."
maturity: emerging
tool:
  name: mastra
  registry: npm
  package: "@mastra/core"
version_policy: current_major
checked_version: "1.82.0"
checked: "2026-11-06"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@mastra/core/dist-tags
evidence: "\"latest\":\"1.82.0\""
alternatives: [the AI SDK, the provider's SDK, Claude Agent SDK, OpenAI Agents SDK, LangGraph.js]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/@mastra/core/package.json').version.startsWith('1.') ? 0 : 1)"
---

# Mastra runs a TypeScript agent with its tools and memory

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools` for a TypeScript team that wants one framework for agents, workflows, and memory. The AI SDK stays the TypeScript default. License: Apache-2.0 for `@mastra/core`, as its package says. Check each other `@mastra/*` package's own license before you add it. No GitHub security advisory named `@mastra/core` on the `checked` day.

## What the team does

- Build each agent with its model, its instructions, and its tools in one module, and give each tool a Zod input schema.
- Cap the steps on every call, even where the cap equals the default, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`.
- Make a tool that writes, spends, or sends wait for a person's approval before it runs.
- Keep memory and workflow state in the project's database, never in a store that loses them on a restart.
- Test each agent with a mock model, and assert the tools it calls as well as the answer.
- Review this choice every 90 days, because the framework releases often.

## What the tests run

One `tests` entry fails when the installed `@mastra/core` is not the major this file was checked at. The agent tests run in the test runner's own entry.
