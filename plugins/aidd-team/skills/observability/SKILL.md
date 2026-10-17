---
name: observability
description: "Practice skill: make a change observable, with a rollback trigger. Use in an aidd repository when writing an observe block, adding logs, metrics, traces, or alerts, or a release."
metadata:
  checked: "2026-09-30"
---

# Observability

**Use it when** you write a Spec's `observe` block, instrument a change, or run the observe window after release.

**Do not use when** the change produces no runtime behavior worth watching. A docs-only or build-only change has no signal, and an observe block for it is a formality.

## Standards

<!-- aidd:gen practice:observability -->
| Standard | Edition |
| --- | --- |
| SLIs, SLOs, and error budgets (Google SRE book and workbook) | — |
| The four golden signals, and the RED and USE methods | — |
| OpenTelemetry for traces, metrics, and logs | 1.44.0 |
| OpenTelemetry GenAI semantic conventions (emerging) | — |
| The OWASP Logging Cheat Sheet and the OWASP Application Logging Vocabulary for security events | — |
| The Twelve-Factor App | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:observability`.
<!-- aidd:end -->

## Specify

- Name the SLI showing the change works, the SLO it must hold, the observe window, and a rollback trigger tied to error-budget burn or a symptom threshold.
- Name the dashboard or query a human watches (`signals`), and any post-release command that exits 0 when healthy (`command`). Without an observability service, the signal is a local command or log query a person runs. Never require one the project lacks.
- Add a runbook Task for each new failure mode, written after Spec approval in `docs/runbooks/`.

## Implement

- Traces propagate context across every hop. Metrics follow the semantic conventions (GenAI for model and agent calls) and carry the dimensions the SLI needs. Logs are structured and joined to traces by id.
- Log the fact, not the sensitive value: `password reset sent` with the user id, never the email or the token. Every log and span attribute passes through one redaction step: a case-insensitive key deny-list (`password`, `token`, `secret`, `authorization`, `cookie`, `email`, `phone`, and the project's own), applied to nested maps and lists, masking too much rather than too little. How, with its test: [references/redaction.md](references/redaction.md).
- Security events are logged with a stable name and the actor: authentication success and failure, authorization denial with the resource, privileged or admin operations, rate-limit hits, and repeated authentication failures from one source.
- Health and readiness endpoints reflect the change. Feature flags show in telemetry. The `operability` product default (`/healthz`, `/readyz`, JSON logs, graceful SIGTERM) is `aidd-team:product-defaults`'.
- Telemetry cost (labels, sampling, volume at 10x): [references/telemetry-cost.md](references/telemetry-cost.md).

### Twelve-Factor

The runtime factors are this skill's. The build and deploy ones are `aidd-team:ci-pipeline`'s.

- **Config in the environment:** every value that differs between deploys is an environment variable, validated at start. A missing or malformed one stops the process, naming it.
- **Backing services** (database, queue, cache, mail) are a URL and credentials in config. Swapping a local one for a managed one changes only config.
- **Disposability:** processes are stateless and start in seconds. On SIGTERM they stop taking work, finish or hand back in-flight work within a deadline, and exit 0. Jobs are idempotent.
- **Logs:** one JSON object per line to stdout, never a file the app writes.
- **Admin processes** (a migration, a one-off fix) run as a command from the same release and config, never in a shell on a server.

Test:

- Start with a required variable unset and assert a non-zero exit naming it
- Run the integration tests against the backing service by URL
- Send SIGTERM mid-request and assert it completes with exit 0
- Assert every stdout line parses as JSON and no log file exists

## Ship

- Run `aidd observe <spec>` once, or with `--window` to poll the observe command until the window ends. It stops when the rollback trigger fires. `--write` records the result. Compare canary and baseline on the SLI where the project runs a canary, else before and after. When the trigger fires, say so first and stop. Humans roll back.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Telemetry test exporter | the spans and metrics the SLI needs are emitted | an OpenTelemetry test exporter in the tests |
| Alert rule tests | each alert fires on its condition, and only then | `promtool test rules`, or the equivalent |
| Synthetic check | the critical path works from outside | a scheduled synthetic request |
| Redaction test | a nested payload with `token` and `email` (mixed case, in a list) comes out masked | a unit test of the redaction step |
| Security event tests | each security event is emitted with its name and actor, and no secret | a test per event |
| Metric cardinality test | label values stay bounded | references/telemetry-cost.md |

## Stop if

- A change ships with no SLI, no window, or no rollback trigger.
- A log or span attribute bypasses the redaction step.
- The trigger fired and the rollout is still widening.

## Hand off

- Done: the observe block, the instrumentation, and the runbook. Next: the platform engineer for the rollout, the author for the observe window. Needs: an SLO the product manager has not set. Stopped at: none, or the stop rule that fired.
