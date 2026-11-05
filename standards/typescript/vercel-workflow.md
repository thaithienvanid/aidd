---
id: typescript/vercel-workflow
type: opinionated
fills: [resilience:durable-execution]
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/workflows/**", "**/*workflow*.ts", package.json]
why: "The Workflow DevKit turns a TypeScript function into a durable workflow with two directives, so a step that fails is retried, a finished step is not run again on replay, and a run can sleep or wait for a webhook without a worker of its own."
maturity: emerging
tool:
  name: vercel-workflow
  registry: npm
  package: workflow
version_policy: current_major
checked_version: "5.4.0"
checked: "2026-11-06"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/workflow/dist-tags
evidence: "\"latest\":\"5.4.0\""
alternatives: [Temporal, an outbox and a sweep, the host's own engine, DBOS, Inngest, Restate]
status: active
enforced_by:
  - name: major
    command:
      - node
      - -e
      - "process.exit(require('./node_modules/workflow/package.json').version.startsWith('5.') ? 0 : 1)"
---

# The Workflow DevKit runs a durable TypeScript workflow

It answers the durable-execution choice of `aidd-team:resilience` for a TypeScript team, often one on Vercel, that wants durable steps without running a workflow server. Temporal stays the TypeScript default. License: Apache-2.0. On the `checked` day, GitHub listed one advisory, GHSA-9r75-g2cr-3h76 (medium, March 2026): a webhook could be created with a token the caller chose and others could guess. It affected every release up to 4.1.0-beta.63, and 4.2.0-beta.64 fixed it.

## What the team does

- Mark the workflow function `"use workflow"` and each function with a side effect `"use step"`. Keep the workflow body free of I/O, so a replay gives the same result.
- Give each step an idempotency key from the run and the step, because a step that fails is retried.
- Authenticate each webhook request itself, because the library says its generated token is hard to guess but no security contract.
- Model a person's approval as a hook the run waits on, with a timeout, and check who answered before the run goes on. The Spec says what happens when no answer comes.
- Choose where runs are stored before the first deploy, and test a run that crashes between two steps.
- Review this choice every 90 days, because the DevKit is young.

## What the tests run

One `tests` entry fails when the installed `workflow` is not the major this file was checked at. The workflow tests run in the test runner's own entry.
