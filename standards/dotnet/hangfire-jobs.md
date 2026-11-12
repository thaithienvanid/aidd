---
id: dotnet/hangfire-jobs
type: opinionated
fills: [resilience:job-library]
default: true
implements: resilience:Repeat safety
roles: [architect, developer, sre, reviewer]
when_changed: ["**/Jobs/**", "**/*Job.cs", "**/*.csproj"]
why: "Hangfire runs fire-and-forget, delayed, and recurring jobs inside a .NET app, with no Windows Service or separate process required. It is under LGPL v3, or a commercial license."
maturity: established
tool:
  name: hangfire
  registry: nuget
  package: Hangfire.Core
version_policy: current_stable
checked_version: "1.8.25"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://raw.githubusercontent.com/HangfireIO/Hangfire/main/LICENSE.md
  quote: Hangfire software is an open-source software that is multi-licensed
alternatives: [the host's queue consumer, Quartz.NET]
status: active
---

# Hangfire runs the .NET background jobs

It answers the job-library choice of `aidd-team:resilience` in .NET. Mind the license. Hangfire is under LGPL v3, or a commercial license, and its open-source edition covers what follows.

## What the team does

- Store the jobs in the app's own SQL database, so the system needs no broker.
- Enqueue after the transaction commits, or through an outbox.
- Pass ids as job arguments, never entities, because Hangfire stores the arguments with the job.
- Set `AutomaticRetry` with an attempt count on each job, and `OnAttemptsExceeded` to fail it, so it waits on the failed list for a person.
- Run the Hangfire server in a worker service of its own once request latency matters.
- Put the dashboard behind the app's own authorization filter, never open to the network.
- Alert on the enqueued and failed counts.
