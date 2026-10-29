# The speed band

Load this when a date or a price assumes that agents make the team faster. It sets how much faster a plan may assume, and how to show that the speed is real.

## The band

Compare the whole project with the same project at the team's normal pace. The normal pace comes from the team's record without agents, or from the reference class. Never compare one task.

The band is the team's design choice, not a published figure. The estimate's owner sets its numbers.

| Point | Speed-up | Estimate value |
| --- | --- | --- |
| Ceiling | 3× | `low`: the shortest duration, the normal pace divided by 3 |
| Target | 2×, or about 2.5× for a port with clear specs | `likely`: the normal pace divided by the target |
| Minimum | 1× until the team's own record shows a speed-up | `high`: the longest duration, the normal pace divided by the minimum |

- METR's randomized trial in 2025 found experienced open-source developers 19% slower with AI tools. So the minimum assumes no speed-up until the team's own record shows one.
- The estimate's `low`, `likely`, and `high` are effort or duration, with `low` ≤ `likely` ≤ `high`.
- A larger speed-up gives a shorter duration. Thus the ceiling gives `low`, and the minimum gives `high`.
- Report the band as a range, as for any estimate.
- A date above 3× names its cuts: the scope, the quality checks, or the parts it leaves out. A person decides each cut.
- A port has clear specs when the old system defines the behavior and its tests can run against the new one.

## What never compresses

- Human testing, review, and external waits are never compressed. Add them at the normal pace, after you apply the band.
- External waits include a store review, a vendor, a client's own tasks, and a legal or security review outside the team.
- The calendar is never shorter than the external waits. If the waits take 6 weeks, the date is 6 weeks away at least.

## When the speed counts

Speed counts only when the project finishes sooner and quality holds. Quality is the first-pass share, the change failure rate, and the time to restore.

- The project's duration comes from the Initiative's milestone dates, or from the proposal's milestones. Compare it with the estimate at the normal pace.
- `aidd metrics` gives the median lead time in hours. The lead time of each change runs from its first gate run to its first pass. It measures the flow of changes, not the project's duration.
- `aidd metrics` with `--dora --specs <dir>` reports the change failure rate and the time to restore. Its summary gives the first-pass share.
- A shorter duration or lead time while one of the three gets worse is not speed. Report it as a loss.
- Measure by A/B: compare work done with agents against similar work done at the normal pace, in the same period. Give the sample size with each result.
- Until the team has its own record, the band is an assumption. Write it in the estimate's basis as an assumption.
