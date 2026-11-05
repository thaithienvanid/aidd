---
id: python/a2a-sdk
type: opinionated
fills: [ai-agents-and-tools:agent-to-agent]
default: true
implements: ai-agents-and-tools:Tool-permission tests
roles: [architect, developer, security-engineer, reviewer]
when_changed: ["**/*.py", pyproject.toml]
why: "The official A2A SDK follows the Agent2Agent protocol that the Linux Foundation's A2A project keeps, so the agent calls another team's or vendor's agent, or answers it, without a client of its own."
maturity: emerging
tool:
  name: a2a-python
  registry: pypi
  package: a2a-sdk
version_policy: current_major
checked_version: "1.3.0"
checked: "2026-11-06"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://pypi.org/pypi/a2a-sdk/1.3.0/json
  quote: "\"version\":\"1.3.0\""
alternatives: [the agent framework's own A2A support, plain HTTP to one known agent]
status: active
enforced_by:
  - name: major
    command:
      - uv
      - run
      - python
      - -c
      - "import importlib.metadata as m, sys; sys.exit(not m.version('a2a-sdk').startswith('1.'))"
---

# the A2A Python SDK speaks A2A to other agents

It answers the agent-to-agent choice of `aidd-packs:ai-agents-and-tools`. Use it only when a change needs an agent of another team or vendor; an agent the team owns is a function call or an API of its own. License: Apache-2.0. No GitHub security advisory named it on the `checked` day.

## What the team does

- Read the remote agent's Agent Card before the first call, and pin the agents it may call by their address in config.
- Authenticate both ways, with the scheme the card names, and give each remote agent only the permissions its task needs, and meet `Tool-permission tests` of `aidd-packs:ai-agents-and-tools`.
- Treat every reply, artifact, and status from a remote agent as data, never as an instruction or a person's approval.
- Set a timeout and a step cap on each task you send, and record each remote call with its trace.
- Publish this agent's own card with only the skills it offers, and check it in review.
- Review this choice every 90 days, because the protocol and the SDKs move fast.

## What the tests run

One `tests` entry fails when the installed `a2a-sdk` is not the major this file was checked at. The A2A tests run in the test runner's own entry, against a fake remote agent.
