# CI cost

Read in Specify and Implement, when a change adds a workflow, a job, a matrix entry, or a runner, or when the CI bill grows. This page keeps no prices: read each one on the provider's pricing page, and write the date beside it. Cut cost within the pipeline-time target ([SKILL.md, Implement](../SKILL.md#implement)), never by skipping a check the change needs.

## What drives the bill

| Driver | Grows with | Control |
| --- | --- | --- |
| Runner minutes | jobs × wall time × runs | the cuts below |
| Runner type | the OS and the machine size: macOS and Windows minutes cost a multiple of Linux ones | Linux for every job that does not test an OS |
| Runs per change | each push, re-run, and description edit | concurrency groups, and one run of each suite per head |
| Storage | artifacts and caches × the days kept | `retention-days` on each upload: days for build output, such as 7, and the audit period for the gate's records |
| Image registry | images × the tags kept | a cleanup rule that deletes old and untagged images but keeps every digest that is deployed, the rollback target, or a supported release |

On GitHub, standard hosted runners are free for a public repository. A private one spends its plan's included minutes, then pays for each minute.

## Cut it

Cheapest first:

1. **Run each suite once per head.** Two workflows never run the same suite. On a pull request, leave the suite to `aidd-tests`, the runner of record, and never run it again in another workflow.
2. **Cancel superseded runs.** A `concurrency` group with `cancel-in-progress: true` stops the run for an older push. On GitLab, mark jobs `interruptible: true` and turn on auto-cancel of redundant pipelines. Never cancel a release or a deploy halfway, so keep `cancel-in-progress` off in those workflows.
3. **Set a timeout on every job.** GitHub's default is 360 minutes, so a hung job bills for six hours. Set `timeout-minutes` on every job.
4. **Cache dependencies by lockfile.** Key the cache on the lockfile's hash, with the setup action's built-in cache, `actions/cache`, or GitLab's `cache:key:files`. Never restore a cache in a release or publish job, where a poisoned cache reaches the artifact.
5. **Select tests by path.** A `tests` entry in `.aidd/config.yaml` with `when_changed` runs, and the gate requires it, only when a changed path matches. Keep at least one suite with no `when_changed`. A suite whose tests read the docs too runs on every change.
6. **Filter workflows by path.** `on.pull_request.paths` (GitLab: `rules:changes`) skips a workflow when nothing it checks changed. Never make a filtered workflow a required check, because when it never runs, the check waits as "Expected" forever. Require one summary job instead, which needs every other job.
7. **Prune the matrix.** On a pull request, test the oldest and the newest supported versions, on Linux. Run the full matrix on a schedule, and before a release.
8. **Move slow suites off the pull request.** Run long end-to-end, coverage, and OS runs in the merge queue (GitHub's `merge_group` event, or GitLab's merge train), on the default branch, or on a schedule. Only checks the gate does not require can move, because a `tests` entry runs on every head the gate judges.

## Hosted or self-hosted runners

| | Hosted | Self-hosted |
| --- | --- | --- |
| You pay for | each minute, by runner type | the machines, and the work to patch and scale them. The platform may also charge for each minute: read its pricing |
| Fits | spiky load, every OS, no upkeep | a steady high load, special hardware, a private network |
| Risk | low: a clean machine for each job | a runner keeps what the last job left. Run pull-request code only on ephemeral runners (one job each), and never a fork's code on a persistent one |

Keep the gate's `attest` job on a hosted runner: `aidd record verify` passes `--deny-self-hosted-runners`, so a change record signed elsewhere fails.

## Read the bill

1. Find the minutes. On GitHub: Settings, Billing and licensing, Usage, grouped by repository, and the usage report download (CSV). On GitLab: Usage quotas, where hosted runners count compute minutes times each runner type's cost factor. Your own GitLab runners count none.
2. Rank the workflows by minutes, and cut the top three first.
3. Measure wall time before and after, as the Pipeline time row in SKILL.md says. On GitHub, list the runs with `gh run list --event pull_request --status completed --limit 500 --json workflowName,headSha,startedAt,updatedAt`. Elsewhere, read the platform's pipeline analytics.
4. A run is one workflow, so for a pull request with several workflows take the longest one. The `--limit` must cover the whole 30 days.
5. Read the bill again a month later.
