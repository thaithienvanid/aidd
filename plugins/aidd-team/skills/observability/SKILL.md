---
name: observability
description: "Practice skill: make a change observable and give it a rollback trigger. Use when writing a Spec's observe block, instrumenting code, adding logs, metrics, traces, dashboards, or alerts, or watching a release, or when someone mentions monitoring, SLOs, error budgets, OpenTelemetry, we cannot see what happened, noisy alerts, personal data or secrets in logs, redaction, or audit and security logs: SLIs and SLOs, the golden signals, OpenTelemetry conventions, redaction and security events, alerts on symptoms, runbooks, and aidd observe."
metadata:
  checked: "2026-09-28"
---

# Observability

**Use it when** you write a Spec's `[observe]` block, instrument a change, or run the observe window after release.

**Do not use when** the change produces no runtime behavior worth watching — a docs-only or build-only change has no signal to add, and an observe block there is a formality.

## Standards

- Google SRE: SLIs, SLOs, and error budgets.
- The four golden signals, RED for services, USE for resources.
- OpenTelemetry semantic conventions, including the GenAI conventions for model and agent calls.
- Structured logging.
- The OWASP Logging Cheat Sheet and the OWASP Application Logging Vocabulary for security events.
- Runbooks.

## Specify, before Spec approval

- Name the SLI that shows the change working, the SLO it must hold, the observe window, and a rollback trigger tied to error-budget burn or a symptom threshold.
- Name the dashboard or query a human watches (`signals`), and the post-release command that exits 0 when healthy (`command`), when one exists. Without an observability service, the signal is a local command or a log query a person runs; never require one the project lacks.
- Add a runbook Task for any new failure mode, written after Spec approval in `docs/runbooks/`.

## Implement

- Traces propagate context across every hop; metrics follow the semantic conventions and carry the dimensions the SLI needs; logs are structured and joined to traces by id.
- Log the fact, not the sensitive value: `password reset sent` with the user id, never the email address or the token. Every log and span attribute passes through one redaction step: a case-insensitive key deny-list (`password`, `token`, `secret`, `authorization`, `cookie`, `email`, `phone`, and the project's own), applied to nested maps and lists, that prefers masking too much to too little. How, and its unit test: [references/redaction.md](references/redaction.md).
- Security events are logged with a stable name and the actor: authentication success and failure, authorization denial with the resource, privileged or administrative operations, rate-limit hits, and repeated authentication failures from one source; they are the signals the security engineer alerts on.
- Health and readiness endpoints reflect the change; feature flags are visible in telemetry.

## Test commands

- An OpenTelemetry test exporter asserts the spans and metrics the SLI needs; alert rules have unit tests (`promtool test rules` or the equivalent); a synthetic check exercises the critical path.
- The redaction unit test: a nested payload containing `token` and `email` (in mixed case, inside a list) comes out masked; a test per security event asserts it is emitted with its name and actor.

## Ship

- Run `aidd observe <spec> --write` at the start and the end of the window; compare canary and baseline on the SLI where the project runs a canary, or before and after otherwise; when the trigger fires, say so first and stop; humans roll back.

## Hand off

- Done: the observe block, the instrumentation, and the runbook. Next: the platform engineer for the rollout mechanics, the author for the observe window. Needs: an SLO the product manager has not set. Stopped at: none, or the stop rule that fired.
