---
id: ai/langfuse-traces
type: opinionated
fills: [ai-agents-and-tools:trace-backend]
default: true
implements: ai-agents-and-tools:Trace coverage
roles: [developer, sre, reviewer]
when_changed: ["**/*.py", "**/*.ts", pyproject.toml, package.json]
why: "Langfuse takes the agent's OpenTelemetry spans as they are and adds what an AI team reads them for: prompts, costs, and scores beside each trace, self-hosted or in its cloud."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: langfuse
  registry: pypi
  package: langfuse
version_policy: current_major
checked_version: "5.0.4"
cooldown_until: "2026-10-28"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/langfuse/5.0.4/json
evidence: "\"version\":\"5.0.4\""
alternatives: [an OpenTelemetry collector and the team's tracing backend, MLflow, LangSmith, Arize Phoenix]
status: active
---

# Langfuse receives the agent's traces

It answers the trace-backend choice of `aidd-team:ai-agents-and-tools`. Langfuse is under the MIT license outside its `ee/` folders, which need a commercial license. ClickHouse acquired Langfuse in January 2026, and Langfuse said it planned no change to its licensing.

The others, as read on the `checked` day: MLflow is under Apache-2.0. LangSmith is a proprietary service. Arize Phoenix is under the Elastic License 2.0, which is not an OSI license.

## What the team does

- Send the spans over OTLP with the OpenTelemetry GenAI conventions, through the Langfuse SDK (`langfuse` 5 for Python, `@langfuse/tracing` 6 for TypeScript) or any OpenTelemetry exporter. The backend can then change without new instrumentation.
- Pin the SDK and every instrumentation package. The GenAI conventions are still in Development, so an upgrade can rename attributes. Check the dashboards after each one.
- Capture prompt and output text only behind a redaction step for personal data and secrets, and with a set retention. Langfuse's retention setting is an enterprise module, so without that license a scheduled job deletes old traces. Otherwise record the metadata alone: the model, tokens, cost, latency, and tool names.
- Tag each trace an eval makes with the eval run's id, and store the trace id in the eval's results. A failed case then opens its trace.
- Give each environment its own project and keys. Name a worktree's project by `AIDD_WORKTREE`.
- Review this choice every 90 days, because the conventions and the SDKs move fast.

## What the gate runs

Nothing of its own. The Trace coverage test of `aidd-team:ai-agents-and-tools` proves that every tool call emits a span.
