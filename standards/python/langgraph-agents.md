---
id: python/langgraph-agents
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
default: true
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, reviewer]
when_changed: ["**/*.py", pyproject.toml, langgraph.json]
why: "LangGraph runs an agent as an explicit graph of steps with saved state, so a run can stop at a step cap, pause for a person, and resume from its last checkpoint."
reviewed: "2026-10-16"
maturity: emerging
tool:
  name: langgraph
  registry: pypi
  package: langgraph
version_policy: current_major
checked_version: "1.2.16"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/langgraph/json
evidence: "\"version\":\"1.2.16\""
alternatives: [the provider's SDK, Claude Agent SDK, OpenAI Agents SDK, Pydantic AI]
status: active
enforced_by:
  - name: major
    command:
      - uv
      - run
      - python
      - -c
      - "import importlib.metadata as m, sys; sys.exit(not m.version('langgraph').startswith('1.'))"
---

# LangGraph runs the Python agent loop

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools`.

## What the team does

- Draw the agent as a `StateGraph` with typed state; each node does one step, and each edge says when it runs.
- Set `recursion_limit` on every run, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`.
- Save state with a checkpointer backed by the project's database, so a run resumes after a crash.
- Put an `interrupt` before any tool that writes, spends, or sends, so a person approves it.
- Test the graph with fake models and tools, and assert the path it takes as well as the answer.
- Review this choice every quarter: the library changes fast.

## What the gate runs

One `tests` entry fails when the installed LangGraph is not the major this file was checked at. The graph tests run in the test runner's own entry.
