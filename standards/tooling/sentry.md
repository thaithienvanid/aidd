---
id: tooling/sentry
type: opinionated
fills: [observability:error-tracking]
default: true
implements: observability:Redaction test
roles: [developer, sre, security-engineer, reviewer]
when_changed: ["**/*sentry*", "**/instrument*.*", "**/instrumentation*.*"]
why: "Sentry groups each error with its stack trace, release, and environment, across services and apps, through an SDK for each main language. Its server is source-available under FSL, and its SDKs are under MIT."
maturity: established
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://open.sentry.io/licensing/
  quote: All components powering the main Sentry web app use FSL
alternatives: [GlitchTip, Rollbar, the trace backend's exception view]
status: active
---

# Sentry tracks the application's errors

It answers the error-tracking choice of `aidd-team:observability`. Mind the license. Sentry's server is under the Functional Source License (FSL-1.1-Apache-2.0): source-available, not open source, and never to be offered as a commercial Sentry-like service. Each version becomes Apache-2.0 after two years. Its SDKs are under the MIT license. The hosted service is the usual way to run it. The self-hosted package is meant for low-volume deployments and trials.

## What the team does

- Install the SDK for each language through the project's lockfile. Set `release` to the deployed version and `environment` on every event.
- Run the redaction step in the SDK's before-send hook, and keep the SDK from sending personal data by default.
- Upload source maps and debug symbols from CI for each release, and keep source maps off the public site.
- Send every error, and sample the performance traces. Where the team runs a trace backend, traces go there.
- Alert the owning team on a new issue and on a regression.
- Give each app its own Sentry project, and each environment its own tag.
