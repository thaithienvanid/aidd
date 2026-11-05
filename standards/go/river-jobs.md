---
id: go/river-jobs
type: opinionated
fills: [resilience:job-library]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/jobs/**", "**/workers/**", "**/*_job.go", go.mod]
why: "River keeps the jobs in the PostgreSQL database the service already runs. A job is inserted in the same transaction as the data it acts on, with no broker to run. It is under MPL-2.0 and has no 1.0 release yet."
maturity: emerging
tool:
  name: river
  registry: go
  package: github.com/riverqueue/river
version_policy: current_stable
checked_version: "v0.51.0"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/riverqueue/river/master/docs/README.md
evidence: "River is a fast, transactional job queue backed by Postgres or SQLite."
alternatives: [the host's queue consumer, Asynq]
status: active
---

# River runs the Go background jobs in PostgreSQL

It answers the job-library choice of `aidd-team:resilience` in Go. River is under the Mozilla Public License 2.0. It has no 1.0 release yet, so it is marked emerging. Asynq, on Redis under MIT, has more GitHub stars and is also before 1.0. It suits a service without PostgreSQL.

## What the team does

- Insert each job with `InsertTx`, in the transaction that changes the data, so the job exists exactly when the change does.
- Apply River's own migrations through the project's migration tool, beside the app's.
- Set `MaxAttempts` for each job kind. Return `river.JobCancel` for a permanent failure, so River does not retry it.
- Use unique jobs where one piece of work must never queue twice.
- Run the workers in a process of their own, and stop them on SIGTERM so active jobs finish first.
- Alert on the count of available jobs and on the age of the oldest one.
