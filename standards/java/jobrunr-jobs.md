---
id: java/jobrunr-jobs
type: opinionated
fills: [resilience:job-library]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/jobs/**", "**/*Job.java", "**/*Job.kt", "**/application*.yml", "**/application*.properties"]
why: "JobRunr keeps fire-and-forget, delayed, scheduled, and recurring jobs in the database the Java service already runs, and spreads them over as many job servers as the load needs. It is under LGPL v3, or a commercial license."
maturity: established
tool:
  name: jobrunr
  registry: maven
  package: "org.jobrunr:jobrunr"
version_policy: current_stable
checked_version: "9.0.3"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://raw.githubusercontent.com/jobrunr/jobrunr/master/License.md
  quote: JobRunr software is an open-source software that is multi-licensed
alternatives: [the host's queue consumer, Quartz Scheduler, db-scheduler]
status: active
---

# JobRunr runs the Java background jobs

It answers the job-library choice of `aidd-team:resilience` on the JVM. Mind the license. JobRunr is under LGPL v3, or a commercial license, and its open-source edition covers what follows. Quartz Scheduler suits a team whose jobs only run on a schedule.

## What the team does

- Keep the jobs in the service's own SQL database, so no broker joins the system.
- Enqueue from an outbox, or after the transaction commits.
- Pass an id as the job's argument, never an entity.
- Set the number of retries for each job kind, rather than keeping the default.
- Run the background job servers as a deployment of their own once request latency matters. Keep the dashboard off the public network.
- Alert on the enqueued and failed counts.
