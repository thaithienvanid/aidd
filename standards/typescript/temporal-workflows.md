---
id: typescript/temporal-workflows
type: opinionated
fills: [resilience:durable-execution]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/workflows/**", "**/activities/**", "**/*workflow*.ts", package.json]
why: "Temporal keeps the event history of every TypeScript workflow it runs, so a run picks up after a crash, a deploy, or a person's slow reply, and never repeats a finished step."
reviewed: "2026-10-22"
maturity: established
tool:
  name: temporal-typescript
  registry: npm
  package: "@temporalio/workflow"
version_policy: current_stable
checked_version: "1.24.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.24.0"
source: https://registry.npmjs.org/@temporalio/workflow/1.24.0
evidence: "\"version\":\"1.24.0\""
alternatives: [an outbox and a sweep, the host's own engine, DBOS, Inngest, Restate]
status: active
enforced_by:
  - name: replay
    command: [pnpm, exec, vitest, run, tests/replay]
---

# Temporal runs the durable TypeScript workflows

It answers the durable-execution choice of `aidd-team:resilience` in TypeScript. The `@temporalio/*` packages and the Temporal server are under the MIT license. Keep every `@temporalio/*` package at one version.

An engine pays for itself when a run lasts minutes to days, waits on a person, or has several steps with side effects. For a short run in one process, the agent framework's own checkpoint is enough. As for the other engines, DBOS is MIT and emerging. Inngest's server is SSPL-1.0 with an Apache-2.0 SDK, and Restate's server is BSL 1.1 with an MIT SDK.

## What the team does

- Write workflow code that the sandbox can replay. Call no I/O there, and leave the clock and randomness to the sandbox, which makes them deterministic.
- Put each model call and each tool call in an activity, through `proxyActivities` with a `startToCloseTimeout` and a retry policy. Give each an idempotency key from the workflow id and the step.
- Model a person's approval as a signal, and wait with `condition(fn, timeout)`. The Spec says what happens when no answer comes.
- Guard a change to a workflow with runs in flight with `patched()`, or move it with Worker Versioning, and delete the old path after the last run ends.
- Export the history of a real run of each workflow to `tests/replay/histories/` when the workflow changes.

## What the gate runs

One `tests` entry runs `tests/replay`, which feeds each saved history to `Worker.runReplayHistories`. A non-deterministic change fails it.
