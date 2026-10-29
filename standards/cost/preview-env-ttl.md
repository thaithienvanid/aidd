---
id: cost/preview-env-ttl
type: opinionated
fills: [release-rollout:preview-environment-ttl]
default: true
implements: release-rollout:Isolated environment check
roles: [sre, developer]
when_changed:
  - ".github/workflows/**"
  - ".gitlab-ci.yml"
  - "**/*.tf"
  - "**/*.tofu"
  - wrangler.jsonc
  - wrangler.json
  - wrangler.toml
why: "A preview environment that outlives its pull request bills for nothing anyone watches, so a closed pull request deletes it and a daily sweep deletes any preview older than its time to live."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [scaled to zero when idle, after a set number of days only]
status: active
source: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
evidence: "To run a workflow when a pull request merges, use the pull_request closed event type along with a conditional that checks the merged value of the event."
---

# A preview environment ends with its pull request

It answers the preview-environment-ttl choice of `aidd-team:release-rollout`.

## What the team does

- Name each preview after its pull request, such as `pr-123`. Tag or label every resource it creates with the pull request number and the day it was created.
- Run a workflow on the `pull_request` `closed` event, merged or not, that deletes the preview: `wrangler delete` for a Worker, `tofu destroy` on the preview's workspace, or `gcloud run services delete` for a Cloud Run service.
- Run a scheduled sweep each day that deletes any preview older than its time to live, seven days unless the Spec names another.
- Scale every preview to zero when idle, and give it the smallest database the tests need.
- Never copy production data into a preview.
- Put previews in their own account or project, under the sandbox stop of the provider's spend-caps standard.

## What the gate runs

Nothing of its own. The pack's Isolated environment check keeps each preview away from shared stores.
