---
id: python/celery-jobs
type: opinionated
fills: [resilience:job-library]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/tasks.py", "**/tasks/**", "**/celery*.py", pyproject.toml]
why: "Celery is the long-standing Python task queue: workers take tasks from a broker, such as Redis, RabbitMQ, or Amazon SQS, so slow work leaves the request. It is under the BSD-3-Clause license."
maturity: established
tool:
  name: celery
  registry: pypi
  package: celery
version_policy: current_stable
checked_version: "5.6.3"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://raw.githubusercontent.com/celery/celery/main/README.rst
  quote: "A task queue's input is a unit of work, called a task, dedicated worker"
alternatives: [the host's queue consumer, RQ, Dramatiq, Procrastinate]
status: active
---

# Celery runs the Python background jobs

It answers the job-library choice of `aidd-team:resilience` in Python. Celery is under the BSD-3-Clause license. Its broker is Redis or RabbitMQ, or Amazon SQS or Google Pub/Sub where the host's queue carries the tasks.

## What the team does

- Send a task only once the transaction it reads has committed, through `transaction.on_commit` in Django or an outbox elsewhere. A worker then never looks for a row that does not exist yet.
- Pass ids as task arguments, never objects, serialized as JSON.
- Set `acks_late` with `reject_on_worker_lost`, so a task whose worker died runs again rather than being lost. That makes each task's Repeat safety a must.
- Retry transient errors only, through `autoretry_for` with `retry_backoff`, jitter, and `max_retries`. Keep a task that runs out of retries in a failed-jobs table, where a person can inspect and replay it.
- Set `time_limit` and `soft_time_limit` on every task. On Redis or SQS, set a visibility timeout longer than the longest task.
- Alert on the queue depth and on the age of the oldest waiting task.
