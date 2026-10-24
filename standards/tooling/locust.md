---
id: tooling/locust
type: opinionated
fills: [apis-and-services:load-test]
default: false
implements: apis-and-services:Load test
roles: [sre, verifier, developer, reviewer]
when_changed: ["load/**"]
why: "Locust writes the load as plain Python classes, so a Python team tests in the language it already reviews, and a headless run sets a failing exit code. It is under MIT."
reviewed: "2026-10-22"
maturity: established
tool:
  name: locust
  registry: pypi
  package: locust
version_policy: current_stable
checked_version: "2.47.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "2.46.7"
cooldown_until: "2026-10-28"
source: https://pypi.org/pypi/locust/2.47.0/json
evidence: "\"version\":\"2.47.0\""
alternatives: [k6, Gatling]
status: active
enforced_by:
  - name: load
    command: [uvx, --from, locust==2.46.7, locust, --config, load/locust.conf]
---

# Locust runs the load test for a Python team

It answers the load-test choice of `aidd-team:apis-and-services` where the team writes Python. `tooling/k6` stays the default.

Locust 2.47.0 came out on 2026-10-21, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 2.46.7 until `cooldown_until`.

## What the team does

- Keep the user classes in `load/locustfile.py`, and the run's settings in `load/locust.conf`: `headless`, `users`, `spawn-rate`, `run-time`, and `host`.
- Set the host from the `LOCUST_HOST` variable in CI, and run against a test deployment, never production.
- Write each SLO as a check in a `quitting` event handler. Set `environment.process_exit_code = 1` when the 95th percentile or the failure ratio passes its bound, as the Locust docs show.
- Keep the default exit code of 1 for any failed request (`--exit-code-on-error`).
- For a large load, run workers with `--processes`, so one CPU core does not cap the test.

## What the gate runs

One `load` test runs Locust headless at `pin` with `load/locust.conf`. A failed request, or a broken SLO check, sets a non-zero exit code and fails the change.
