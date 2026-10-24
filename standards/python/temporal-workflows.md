---
id: python/temporal-workflows
type: opinionated
fills: [resilience:durable-execution]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/workflows/**", "**/activities/**", "**/*workflow*.py", pyproject.toml]
why: "Temporal records each step of a long run in its event history, so a crash, a deploy, or a wait of days resumes the run where it stopped, and no step that finished runs again."
reviewed: "2026-10-22"
maturity: established
tool:
  name: temporalio
  registry: pypi
  package: temporalio
version_policy: current_stable
checked_version: "1.34.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.34.0"
source: https://pypi.org/pypi/temporalio/1.34.0/json
evidence: "\"version\":\"1.34.0\""
alternatives: [an outbox and a sweep, the host's own engine, DBOS, Inngest, Restate]
status: active
enforced_by:
  - name: replay
    command: [uv, run, pytest, tests/replay]
---

# Temporal runs the durable Python workflows

It answers the durable-execution choice of `aidd-team:resilience` in Python. The `temporalio` SDK and the Temporal server are under the MIT license, and Temporal Cloud is the paid host.

Use an engine when a run spans minutes to days, waits for a person, or has two or more steps with side effects. A LangGraph checkpointer is enough for a short run inside one process. Of the other engines, DBOS is under MIT and emerging. The Inngest server is under SSPL-1.0, and its SDK under Apache-2.0. The Restate server is under BSL 1.1, and its SDK under MIT.

## What the team does

- Keep the workflow code deterministic. It reads no clock, no random number, and no network or file outside an activity, and uses `workflow.now()` and `workflow.random()` instead.
- Make each model call and each tool call its own activity, with a timeout, a retry policy, and an idempotency key built from the workflow id and the step.
- Wait for a person's approval as a signal, with `workflow.wait_condition` and a timeout. Decide in the Spec what the run does when the wait times out.
- Change a workflow that has runs in flight behind `workflow.patched()`, or with Worker Versioning. Remove the old branch only once no run uses it.
- Save the history of a real run of each workflow in `tests/replay/histories/`, refreshed when the workflow changes.

## What the gate runs

One `tests` entry runs the tests in `tests/replay`. Each one replays the saved histories with `Replayer`, and a change that breaks determinism fails it.
