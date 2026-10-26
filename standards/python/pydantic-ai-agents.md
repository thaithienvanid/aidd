---
id: python/pydantic-ai-agents
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, reviewer]
when_changed: ["**/*.py", pyproject.toml]
why: "Pydantic AI runs a typed agent loop in plain Python, where Pydantic validates each tool's input and the final output, with usage limits, tool approval, and a test model built in."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: pydantic-ai
  registry: pypi
  package: pydantic-ai
version_policy: current_major
checked_version: "2.56.0"
cooldown_until: "2026-10-28"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/pydantic-ai/2.56.0/json
evidence: "\"version\":\"2.56.0\""
alternatives: [LangGraph, the provider's SDK, OpenAI Agents SDK, Google ADK]
status: active
enforced_by:
  - name: major
    command:
      - uv
      - run
      - python
      - -c
      - "import importlib.metadata as m, sys; sys.exit(not m.version('pydantic-ai').startswith('2.'))"
---

# Pydantic AI runs the Python agent loop

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools`, for a team that wants a typed loop without a graph. Pydantic AI is under the MIT license. LangGraph stays aidd's default for Python, because it saves each step and resumes a long run.

## What the team does

- Give every agent an `output_type`, so a run ends only with output that passes validation.
- Pass `UsageLimits` to every run, with `request_limit`, `tool_calls_limit`, and a token limit, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`.
- Mark each tool that writes, spends, or sends with `requires_approval=True`. The run then ends with `DeferredToolRequests`, and the person's answer goes back as `DeferredToolResults`.
- Test the agent with `TestModel` or `FunctionModel` through `Agent.override`. Set `ALLOW_MODEL_REQUESTS = False` in the tests, so no test calls a real model.
- Turn on its OpenTelemetry instrumentation, so each model call and tool call becomes a span.
- Review this choice every quarter, because a minor release adds features often.

## What the gate runs

One `tests` entry fails when the installed Pydantic AI is not the major this file was checked at. The `TestModel` tests run with the rest of the unit tests.
