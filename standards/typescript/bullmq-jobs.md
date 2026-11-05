---
id: typescript/bullmq-jobs
type: opinionated
fills: [resilience:job-library]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/jobs/**", "**/queues/**", "**/workers/**", package.json]
why: "BullMQ is the common job queue for Node.js, on Redis, with retries, delayed jobs, and rate limits, so slow work leaves the request. It is under the MIT license."
maturity: established
tool:
  name: bullmq
  registry: npm
  package: bullmq
version_policy: current_stable
checked_version: "6.6.0"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/taskforcesh/bullmq/master/README.md
evidence: "The fastest, most reliable, Redis-based distributed queue for Node.js"
alternatives: [the host's queue consumer, pg-boss, Graphile Worker]
status: active
---

# BullMQ runs the TypeScript background jobs

It answers the job-library choice of `aidd-team:resilience` for TypeScript on Node.js. BullMQ is under the MIT license. BullMQ Pro is a separate edition with more features, such as group rate limits, and nothing here needs it. On Cloudflare Workers, the Queues consumer answers this choice instead.

## What the team does

- Run Redis with `maxmemory-policy noeviction` and persistence on, because an evicted key is a lost job. The host's managed Redis is fine.
- Add a job after its transaction commits, or from an outbox. Give it a `jobId` from the work's own id, so adding the same work twice queues it once.
- Set `attempts` and an exponential `backoff` on every queue. Keep failed jobs (`removeOnFail` off, or a count) so a person can inspect and retry them.
- Throw an `UnrecoverableError` for a permanent failure, so BullMQ does not retry it.
- Run the workers as a process of their own with a `concurrency` cap. Close them on SIGTERM, so an active job finishes before the process exits.
- Alert on the waiting count and on the age of the oldest waiting job.
