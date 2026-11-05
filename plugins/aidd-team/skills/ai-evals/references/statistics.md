# Eval statistics, what to score, and the model's life after launch

Load this when an eval result decides a change, or when a pinned model, its traffic, or its golden set changes.

## Uncertainty and sample size

- Report every score with its 95% confidence interval, the mean plus or minus 1.96 standard errors over items. Cluster the standard error when items share a source document or a conversation, since those are not independent.
- Size the golden set so the interval is narrower than the gap the decision turns on. About 400 items give plus or minus 5 points near 50%, and 1,600 give 2.5.
- Compare two versions on the same items, paired: the difference per item has a much smaller error than two separate scores.
- A threshold met by the point estimate but not by the interval is not met; say so in the PR/MR.

## Reliability over repeated trials

- Run a model or an agent that answers differently run to run k times per item (k: 5 is a common start).
- Report pass@1 (the share of trials that pass) and pass^k (every one of the k trials passes, the τ-bench measure).
- Set the threshold on pass^k where a user meets every run, as with an agent acting on their behalf.
- Pin temperature and seed where the provider allows it. Still use pass^k, because a seed does not make most hosted models repeat.

## What to score

- Score retrieval on its own, as recall at k on labeled queries, so a retrieval miss is never blamed on the prompt.
- Score an agent's tool calls and their order, not only its final answer.
- Report the score per slice the product cares about, such as language or user group, so an average never hides a regression.

## Judges

- Calibrate an LLM judge against human labels on a sample, and record the agreement rate.
- Check the judge for position and length bias. Swap the order of the two answers, and use a different model family from the one it judges.

## Contamination

- Keep the golden set out of prompts, fine-tuning data, and public repositories; a canary string in each file shows a leak.
- Keep a private held-out split that is never used while iterating on prompts, and score the release on it once.
- A public benchmark score never stands in for the golden set: it may be in the model's training data.

## After launch

- Sample live traffic on a schedule (a fixed share, redacted under the privacy rules), and label it. Add each new failure mode to the golden set with its fix.
- Model retirement: the Spec or the runbook holds the provider's retirement date for every pinned model. The replacement is a change of its own that passes the full suite, with its intervals, before that date.
