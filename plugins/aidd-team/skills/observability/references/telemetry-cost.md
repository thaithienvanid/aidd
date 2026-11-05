# Telemetry cost

Telemetry is billed like any other infrastructure, and it grows with traffic and with every label added. Budget it in the Spec that adds it, and watch it in the observe window.

## What drives the bill

| Driver | Grows with | Control |
| --- | --- | --- |
| Log volume ingested | requests × lines × bytes | levels: debug off in production; one line per event, not per step; no request or response bodies |
| Active metric series | the product of every label's distinct values | labels from a bounded set (route template, status class, region), never a user id, request id, email, or raw URL |
| Spans stored | requests × spans per request × sampling rate | head sampling in the SDK, tail sampling in the Collector |
| Retention | days kept × volume | short in the hot store, longer in cheap storage only where an audit or a regulation asks |

## Sampling

- **Head sampling** decides at the root span, in the SDK. `OTEL_TRACES_SAMPLER=parentbased_traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1` keeps a tenth of new traces. It follows the parent's decision downstream, so a trace is whole or absent.
- **Tail sampling** decides after the trace ends, in the OpenTelemetry Collector's `tail_sampling` processor. Keep every trace with a `status_code` of `ERROR`, every one above a `latency` threshold, and a share of the rest. The processor holds spans in memory for `decision_wait` (30 s by default), so size the Collector for it.
- Metrics are not sampled: an SLI comes from metrics, which stay exact, while traces explain individual requests.

## In the Spec and the change

- The Spec that adds telemetry names its volume at today's load and at 10x: log lines, series, and spans a request. It puts the monthly cost in the same estimate as the infrastructure (`aidd-team:cloud-and-infrastructure`).
- Each environment has an ingest budget with an alert, in the same place as its infrastructure budget.
- Every log group has a set retention, never the provider's keep-forever default. The `log-retention` open choice sets the period.
- A new metric label names its distinct values; one that can grow without bound is a Review finding.

## Test

A cardinality test, in this order:

1. Run the suite with an in-memory metric reader.
2. Collect every metric's label sets.
3. Assert that each label's distinct values stay within a stated bound.
4. Assert that no label key is on the deny-list, by exact name: `user_id`, `request_id`, `email`, `url.full`, `url.path`, and `url.query`.

Run it with the redaction test.
