---
id: typescript/ai-sdk
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
default: true
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, ml-engineer, reviewer]
when_changed: ["**/*.ts", "**/*.tsx", package.json]
why: "The AI SDK runs a tool-calling agent loop in TypeScript behind one interface for many model providers, with a step limit, tool approval, and mock models for tests built in."
reviewed: "2026-10-16"
maturity: emerging
tool:
  name: ai
  registry: npm
  package: ai
version_policy: current_major
checked_version: "7.0.142"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/ai/dist-tags
evidence: "\"latest\":\"7.0.142\""
alternatives: [the provider's SDK, Claude Agent SDK, OpenAI Agents SDK, Mastra]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/ai/package.json').version.startsWith('7.') ? 0 : 1)"
---

# The AI SDK runs the TypeScript agent loop

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools`. License: Apache-2.0, for `ai` and the `@ai-sdk/*` provider packages.

## What the team does

- Build the agent as a `ToolLoopAgent` with its model, its tools, and its instructions in one module.
- Set `stopWhen` on every agent, such as `isStepCount(20)`, even where it equals the default, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`. Never use `isLoopFinished()`, which removes the limit.
- Give each tool a Zod input schema. Set `toolApproval` to `user-approval` for a tool that writes, spends, or sends, so a person approves the call.
- Call the model through the provider's own `@ai-sdk/<provider>` package, pinned with `ai`.
- Test the agent with `MockLanguageModelV4` from `ai/test`, and assert the tools it calls as well as the answer.
- Review this choice every quarter: the SDK changes fast.

## What the gate runs

One `tests` entry fails when the installed AI SDK is not the major this file was checked at. The agent tests run in the test runner's own entry.
