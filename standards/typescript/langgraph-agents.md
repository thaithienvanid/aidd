---
id: typescript/langgraph-agents
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, reviewer]
when_changed: ["**/*.ts", package.json, langgraph.json]
why: "LangGraph.js runs a TypeScript agent as an explicit graph of steps with saved state, as LangGraph does in Python, so a run stops at a step cap, pauses for a person, and resumes from its last checkpoint."
maturity: emerging
tool:
  name: langgraphjs
  registry: npm
  package: "@langchain/langgraph"
version_policy: current_major
checked_version: "1.7.1"
checked: "2026-11-06"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/@langchain/langgraph/dist-tags
evidence: "\"latest\":\"1.7.1\""
alternatives: [the AI SDK, the provider's SDK, Claude Agent SDK, OpenAI Agents SDK, Mastra]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/@langchain/langgraph/package.json').version.startsWith('1.') ? 0 : 1)"
---

# LangGraph.js runs a TypeScript agent as a graph

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools` for a TypeScript team that wants the graph and its checkpoints, such as a team that runs LangGraph in Python too. The AI SDK stays the TypeScript default. License: MIT. No GitHub security advisory named `@langchain/langgraph` on the `checked` day.

## What the team does

- Draw the agent as a `StateGraph` with typed state. Each node does one step, and each edge says when it runs.
- Set `recursionLimit` on every run, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`.
- Save state with a checkpointer backed by the project's database, such as `@langchain/langgraph-checkpoint-postgres`, so a run resumes after a crash.
- Call `interrupt()` in the node before a tool that writes, spends, or sends, and resume with the person's answer through a `Command`.
- In tests, swap in fake models and tools, and check the nodes a run visits, not only its final state.
- Review this choice every 90 days, because the library changes fast.

## What the tests run

One `tests` entry fails when the installed LangGraph.js is not the major this file was checked at. The graph tests run in the test runner's own entry.
