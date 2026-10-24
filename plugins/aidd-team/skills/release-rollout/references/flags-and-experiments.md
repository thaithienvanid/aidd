# Feature flags and experiments: the detail

Load this when a Spec adds a flag, picks a flag provider, or plans an A/B test.

## A flag entry

A flag never goes on a minor change. The architect adds one `flags` entry per flag, with these fields:

- `name`;
- `default`: `off` for a new feature, and `on` only for a kill switch that guards existing behavior;
- `owner`: a person, never an agent;
- `cleanup_due`: usually two to six weeks after full rollout;
- `purpose`: release toggle, experiment, kill switch, or operational toggle.

Name every flag as `aidd-team:naming` says (references/systems.md, Flags). A kill switch names the capability it keeps on, with `default: on`, so a provider failure keeps today's behavior.

## The provider: the first rung the project can already run

1. No service: an environment variable or a config file through an OpenFeature in-process provider.
2. One small container: flagd reading a flag file from the repository. The file is then a `protected_paths` entry, so a flip is a major change through the gate.
3. A database the project already runs, when people must flip flags without a deploy.
4. A vendor the project already pays for, through its OpenFeature provider; never a new vendor for one flag.

## In code

Code against the OpenFeature API, never a vendor SDK. Check once per decision point, at the edge, and pass the result down as a value. The code falls back to the Spec's `default` when the provider fails. No personal data in the evaluation context beyond what targeting needs; log the flag key and variant, never the context.

## Rings

Turn a flag on ring by ring. These rings are defaults: the runbook's Rollout table holds the project's own.

| Ring | Who gets the new path | Go to the next ring when |
| --- | --- | --- |
| 0. Shadow | nobody: the new path runs, and the old path serves | the two results match on an agreed sample |
| 1. Team | the people who built it | it works end to end, with no new errors |
| 2. Internal | staff, or internal tenants | errors, latency, and support tickets do not get worse |
| 3. Canary | 1 to 10% of customers or tenants | the business and technical metrics match the control group |
| 4. Everyone | all users | it stays stable for the agreed time; then the cleanup Spec |

- Write the go and no-go thresholds of each ring before the ring starts, never after you see its numbers.
- Tag errors, latency, and the key business metrics with the flag state, so a dashboard compares on with off.
- Use the shadow ring for pricing, billing, permissions, and other logic where a wrong answer costs money or exposes data. Both paths run. The code compares the results, logs each difference, and serves the old result.
- The shadow path has no side effects: no writes, emails, payments, or events. A test proves it.

## Shipping and cleanup

A person flips a production flag, held by a `guard.held_commands` entry for the flag CLI or by the flag file being a protected path. Roll out by stage while the observe signal holds; turning the flag off is the first rollback step, named in the Spec's `rollback`. Cleanup is a follow-up Spec that deletes the flag, its dead branch, and the off-state test, and lists the flag in `removes_flags`. After `cleanup_due`, `aidd validate` warns, and `aidd list` shows the cleanup as the owner's work.

## Experiments

The product manager plans the A/B test in the Spec's `experiment` block and names its events in the tracking plan's Experiment section. Assignment is by a stable unit (the user or account id), never per request. The sample ratio check is a chi-squared test of the observed split against the plan, at p < 0.001. At the planned sample or duration, apply the rule as written, and put the number in `outcome.result` (met, missed, or inconclusive). The losing variant's code goes with the flag's cleanup Spec.
