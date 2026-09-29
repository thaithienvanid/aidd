# Platforms

How to set up the gate on GitHub, GitLab, and any other CI. This page owns the setup of the gate's GitHub App, its environment, and the branch ruleset; other pages link here. Why the gate is safe to run, and what it relies on, is in [METHOD.md §14](METHOD.md#14-platform-bindings-and-trust). To try the loop locally first, with none of this, follow the [Quickstart](QUICKSTART.md).

## GitHub

`aidd init --ci github` installs three workflows:

| Workflow | Trigger | Runs PR code? | Token | Role |
| --- | --- | --- | --- | --- |
| `aidd-tests` | `pull_request`, `merge_group` | yes (untrusted) | read-only, no secrets | runs tests green on head and red on base through the composite action `thaithienvanid/aidd@v1.0.0` (in a merge queue: on the merge-group commit); uploads `aidd-evidence` |
| `aidd-relay` | `pull_request_review` | no | none | relays review events |
| `aidd-gate` | `pull_request_target`, `issue_comment`, `workflow_run` | **never** | GitHub App, `statuses: write` | a thin caller of the reusable workflow `.github/workflows/gate.yml@v1.0.0`; builds the trusted context, verifies, and posts `aidd/gate` |

### Setup

**You need:** admin rights on the repository; permission to create a GitHub App for the account or organization that owns it (an organization owner, or a member an owner allowed to manage Apps); and, for a private repository, a plan with rulesets (GitHub Pro, Team, or Enterprise). Allow about an hour the first time.

1. **Connect your test suite.** In `.github/workflows/aidd-tests.yml`, install your toolchain before the aidd step, and make `[[tests]]` in `.aidd/config.toml` run your suite ([recipes below](#3-connect-your-test-suite)). Run `aidd doctor` until nothing fails, commit everything `aidd init` wrote, and open the setup pull request.
2. **Merge the setup PR first.** `aidd init` installs the gate in advisory mode, so it reports on `aidd/gate (advisory)` and blocks nothing until you set `mode: enforce`. The gate runs from the default branch, so it cannot judge anything until it is merged there. A change whose base has no config never passes.
3. **Create a GitHub App for the gate.** Settings → Developer settings → GitHub Apps, with webhooks off.
   - Permissions: `Commit statuses: write`, plus read access to `Contents`, `Pull requests`, `Issues`, `Actions`, and `Checks`. Add the organization permission `Members: read` if you list `@org/team` approvers.
   - Install it on the repository, or on the organization for a fleet.
4. **Create an environment named `aidd-gate`.**
   - Deployment branches: the protected bases only, which is the default branch plus any `AIDD_PROTECTED_BRANCHES` (for `pull_request_target`, the job runs on the PR's base branch).
   - Add the variable `AIDD_APP_ID` and the secret `AIDD_APP_PRIVATE_KEY`. Keep the key here only, never as a repository or organization secret, and pass no secrets from the caller.
   - Do not add required reviewers to the environment, or every gate run waits.
5. **Protect the default branch.** In Settings → Rules → Rulesets:
   - require a pull request
   - require the status check `aidd/gate`, with its expected source set to your App
   - block force pushes
   - recommended: "Require approval of the most recent reviewable push", which also stops whoever pushed last from approving

   Rulesets on private repositories need GitHub Pro, Team, or Enterprise.

   `aidd doctor` checks these rules when it can reach GitHub (a `GH_TOKEN`, or `gh auth login`; offline it says it skipped): it warns when `aidd/gate` is not required or not pinned to an App, when a GitHub App may bypass the ruleset, and when the last pusher may approve.

   Make `aidd/gate` the required check, not the review count ([below](#github-rulesets-and-aidd)). GitHub's own "required approvals" count an approval from any account with write access, a bot or an agent's App token included. aidd never counts an agent account (one in `identities.bots`, Copilot's `copilot-pull-request-reviewer[bot]`, a `[bot]` named for an agent), warns `merge_approval.agent_approval` when one approves, and counts another bot only when `owners.approvers` names it.
6. **Other protected branches.** The default branch is always protected; release branches, for example, are not. List the others in the repository variable `AIDD_PROTECTED_BRANCHES` (or the `protected-branches` input), comma-separated, globs allowed (`release/*`). PRs to any other base get the status `aidd/gate (<base>)`, which cannot satisfy the rule.
7. **Enforce.** Watch the advisory reports for a while (`aidd metrics` summarizes them, [ADOPTION.md](ADOPTION.md#team)). When they look right, set `mode = "enforce"` in `.aidd/config.toml` (the base branch's config wins over the workflow), or `mode: enforce` in `.github/workflows/aidd-gate.yml`. `aidd init --enforce` starts enforced.

<a id="3-connect-your-test-suite"></a>
### Toolchain recipes

| Stack | Install step in aidd-tests.yml | `[[tests]]` command |
| --- | --- | --- |
| Node | `actions/setup-node`, then `npm ci` | `["npm", "test"]` |
| Python | `actions/setup-python`, then `uv sync --frozen` or `pip install -r requirements.txt` | `["python", "-m", "pytest", "-q"]` |
| Go | `actions/setup-go`, then `go mod download` | `["go", "test", "./..."]` |
| Java | `actions/setup-java` (temurin) | `["./mvnw", "-B", "test"]` or `["./gradlew", "test"]` |
| Terraform | `hashicorp/setup-terraform` | `["terraform", "validate"]` (plan needs secrets, so keep it out of tests) |

Use lockfile-exact installs (`npm ci`, not `npm install`): the red run needs a clean tracked tree.

### Why the App matters

Anyone with push access can write a commit status, so only a status source pinned to the App makes `aidd/gate` trustworthy ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)). Without an App, the workflow falls back to `GITHUB_TOKEN`, and the gate is advisory against anyone with write access.

### Reusable workflow inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `mode` | `advisory` in the caller `aidd init` writes; `enforce` when you call the reusable workflow yourself | used when the base config sets no `mode`. `advisory` posts `aidd/gate (advisory)`, which never satisfies the rule: use it to roll out without blocking |
| `protected-branches` | `vars.AIDD_PROTECTED_BRANCHES` | protected bases besides the default branch |
| `org-preset-url`, `org-preset-sha256` | empty | an org preset and its pin, applied as the root parent of every repository's config ([ADOPTION.md](ADOPTION.md#organization)) |
| `runs-on` | `ubuntu-latest` | runner label, for self-hosted runners |
| `timeout-minutes` | `15` | gate job timeout |

The gate runs aidd from the exact commit of the reusable workflow you call, so pinning `uses: thaithienvanid/aidd/.github/workflows/gate.yml@<ref>` pins the verifier too. Pin a commit SHA for the strongest integrity. GitHub Enterprise Server lacks the `job.workflow_sha` context: copy `gate.yml` into your own repository there.

### Identities on GitHub

- The PR author, commit authors, and committers are authors (`web-flow` is ignored).
- Reviews come from the Reviews API; an approval counts only on the head commit, and a later comment-only review changes nothing.
- Comments come from the Issues API; edited comments are ignored.
- More than 250 commits cannot be verified and fail. More than 3,000 reviews or comments is a gate error, never a silent cut.
- A commit author GitHub cannot map to an account (an unlinked email) might be an Approver. The gate warns, or fails under `unlinked_authors = "fail"` (the regulated default). Link the email, or list agent emails in `identities.bots`.
- Only comments that carry, or carried, an `/aidd` command re-run the gate.
- Bot PRs (Dependabot, Renovate) without an `aidd` block are read as standard dependency changes; see [FAQ](FAQ.md#bots).

### Reuse what you already have

- **Owners from CODEOWNERS.** `owners.codeowners = true` reads the base branch's CODEOWNERS (`.github/`, root, or `docs/`). For every changed path, the last matching rule's owners must approve, at Spec approval and Merge approval, with separation of duties and team resolution applied, which GitHub's own code-owner review does not do. `[[owners.paths]]` still adds areas CODEOWNERS does not cover.
- **Your CI as evidence.** `evidence.status_checks = ["build", "test"]` requires those check runs to succeed on the head (success, neutral, or skipped). Only check runs count, from an app listed in `status_check_apps` and on the pull request's own branch; commit statuses never do. The repository suite then runs once, in your CI, and `aidd-tests` runs only the Spec's new-behavior tests for red-then-green. This is as trustworthy as your required checks, so pin their source in the ruleset too.
- **Rulesets.** Keep "Require approval of the most recent reviewable push" on beside `aidd/gate`.

### Evidence the pull request cannot touch

By default, the test workflow lives in each repository, so changing it is a protected, major change. For a stronger guarantee:

1. Put [`templates/github/aidd-tests-central.yml`](../templates/github/aidd-tests-central.yml) in a platform repository only the platform team can change.
2. Require it on the gated repositories with an organization ruleset ("Require workflows to pass before merging"). A pull request then cannot change how its tests run.
3. Set `evidence.signer_workflow = "<org>/<platform-repo>/.github/workflows/aidd-tests.yml"` in the org preset (it locks once a parent sets it).

The central workflow runs tests in one job and, in a second job that runs no pull request code, attests `evidence.json` with GitHub artifact attestations. The gate then verifies the attestation with `gh attestation verify --signer-workflow` and refuses anything else.

This closes evidence from any other workflow and edits to the test workflow itself. It cannot make the pull request's own test code honest; Spec approval and Merge approval still cover that.

This path is new in 1.0.0 and has not yet been exercised on a live organization.

### GitHub Enterprise Server and restricted Actions

- **GHES.** It lacks the `job.workflow_sha` context the reusable workflow uses to run aidd from its own commit. Copy `gate.yml` into a repository of your own, pin the aidd checkout inside it to a commit SHA, and call that copy from `aidd-gate.yml`. Artifact attestations and `actions/create-github-app-token` need a GHES version that ships them; without attestations, skip the central evidence workflow.
- **Actions allowlists.** Under "Allow select actions and reusable workflows", allow `thaithienvanid/aidd` (or your copy) and the actions the gate pins: `actions/checkout`, `actions/setup-python`, `actions/create-github-app-token`, `actions/upload-artifact`, `actions/download-artifact`, `actions/attest-build-provenance` for the central evidence workflow, and `actions/attest` for the optional change-record signing. An air-gapped instance mirrors them the same way it mirrors any action.
- **Egress.** At run time the gate reaches only:
  - the platform's API: `GITHUB_API_URL` and `GITHUB_SERVER_URL` on GitHub, `CI_API_V4_URL` on GitLab, so GHES and self-managed GitLab work
  - the artifact storage the API redirects evidence downloads to
  - the URL of an org preset or an `extends` parent, when you configure one
  - the attestation endpoints (`gh attestation verify`), when `evidence.signer_workflow` is set

  It sends nothing else anywhere: no telemetry, no vendor service. At gate time, the GitLab template fetches aidd from github.com at the pinned commit; to mirror it, change `aidd_host` in the template script. What the gate reads and writes is in [ENTERPRISE.md](ENTERPRISE.md#7-data-handling-and-privacy).

### Merge queues

The gate judges every queue entry and posts `aidd/gate` on its merge-group commit, which is what the queue waits for. Approvals stay on the pull request head; the tests run again on the merge-group commit; and that commit must hold exactly the approved head merged into the commit the entry was built on ([METHOD.md §7](METHOD.md#merge-queue-evidence)).

1. **Run the tests in the queue.** The `aidd-tests.yml` template triggers on `merge_group`, and the aidd action then runs `aidd test --merge-group`; a copy written before merge queues needs the template's `merge_group` trigger, its `pull-requests: read` permission (the queued pull request's description), and its concurrency group and checkout ref, which keep one queue entry from cancelling another. Keep `aidd-gate.yml` as it is: the queue reaches the gate when that `aidd-tests` run completes, through `workflow_run`. Never add `merge_group` to the gate workflow, which would run the workflow file from the merge-group commit.
2. **Turn on the queue** in the branch ruleset ("Require merge queue"), with `aidd/gate` still required and pinned to your App. The `aidd-gate` environment needs no change: the gate job runs on the default branch, as for pull requests.
3. **Only merge non-failing pull requests.** When the queue builds more than one entry at a time, turn it on (grouping strategy `ALLGREEN`). An entry built on another entry carries that entry's changes too, and the gate fails it until the queue is confirmed to merge only groups whose every entry passed. `aidd doctor` warns when it is off.

What fails, and why:

| Finding | Meaning | Fix |
| --- | --- | --- |
| `merge_queue.diff_mismatch` | the merge-group commit is not the approved head merged into its parent | remove the entry and queue the pull request again |
| `merge_queue.conflict` | the approved head no longer merges cleanly into the queue | update the pull request, get it approved on the new head, queue it again |
| `merge_queue.stacked_unverified` | the entry is stacked on another, and the queue may merge a failing entry | turn on "Only merge non-failing pull requests" |
| `tests.evidence_other_head` | the evidence is for the pull request head, not the merge-group commit | wait for the queue's `aidd-tests` run |

GitLab merge trains are not supported yet: turn them off on gated branches, because a train merges a result the gate never judged.

### GitHub rulesets and aidd

A ruleset setting either does work aidd relies on, or duplicates a rule aidd enforces itself. What each one does beside the gate:

| Ruleset setting | Set it to | The aidd rule that covers it, or relies on it |
| --- | --- | --- |
| Require status checks: `aidd/gate` | required, with its expected source set to your App | the whole gate: every rule posts through this one status. Without the App pin anyone with write access can post it ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)); `aidd doctor` warns |
| Required approvals (count) | 0 or more; aidd does not need it | `merge_approval` counts eligible Approvers itself (`gates.approvals` per route), excluding authors, co-authors, committers, and agent accounts. GitHub's count takes any write-access account, a bot or an agent included, so it must never be the only check; aidd warns `merge_approval.agent_approval` when an agent approved |
| Dismiss stale pull request approvals when new commits are pushed | on, recommended | `merge_approval` already counts only approvals of the head commit, and ignores ones given before the base changed; the setting keeps GitHub's own count honest too |
| Require approval of the most recent reviewable push | on | relied on: GitHub stops the last pusher from approving, including a person who pushed on an agent's behalf; aidd's author rule covers commit authors and committers, and `aidd doctor` warns when this is off |
| Require review from Code Owners | optional | `owners.codeowners = true` makes aidd read CODEOWNERS and require the owners at Spec approval and Merge approval, with separation of duties and team resolution applied (`merge_approval.owner_area`, `spec_approval.owner_area`) |
| Required status checks from your CI, pinned to their app | optional | `evidence.status_checks` with `evidence.status_check_apps` counts only check runs from the apps you name (`tests.check_failed`, `tests.check_waiting`); pin the same apps in the ruleset |
| Bypass list | empty, or people only | aidd has no bypass: an actor on the bypass list merges past `aidd/gate`, and no gate record is written for it. `aidd doctor` warns when a GitHub App may bypass, because an agent's App could merge unreviewed |
| Require merge queue, "Only merge non-failing pull requests" | on for a queue that builds more than one entry | relied on by `merge_queue`: a stacked entry fails (`merge_queue.stacked_unverified`) until the grouping strategy is `ALLGREEN`; `aidd doctor` warns |
| Copilot code review, "Automatically request Copilot code review" | optional | Copilot reviews as `copilot-pull-request-reviewer[bot]`. Its review is a comment; if an agent account ever approves, it never counts toward Merge approval, and the gate warns `merge_approval.agent_approval` so you can check the ruleset's own count |
| Block force pushes, restrict deletions | on | relied on: approvals and evidence bind to commit SHAs, and a rewritten base history would change what a merge base means |

### Signing the change record

With `--record`, the gate writes the agent change record beside the gate record: `change-record.intoto.json`, an in-toto statement whose subject is the head commit ([METHOD.md §7](METHOD.md#change-record)). It is kept in the gate's artifact with the record. To sign a passing one:

1. Use a public repository, or GitHub Enterprise Cloud for a private or internal one: artifact attestations are not offered on other plans. Without them, leave signing off; `aidd verify --allow-unsigned` still checks the record's shape, subject, decision, and approvals.
2. Set the repository variable `AIDD_ATTEST_CHANGE_RECORD` to `true`. The `attest` job in `aidd-gate.yml` then downloads the record and signs it with `actions/attest` (pinned by commit SHA). Only that job holds `id-token: write` and `attestations: write`.
3. Check one: download the artifact (`gh run download`), then, in a checkout of the repository, `aidd verify <head sha> --online --tenant <tenant>`. It takes the repository from the checkout's github.com `origin` (or `--repo <owner>/<repo>`), never from the record, and fails when the record names another one or was not made from a trusted CI context. It runs `gh attestation verify` on the file with `--signer-workflow <owner>/<repo>/.github/workflows/aidd-gate.yml` (change it with `--signer-workflow`), `--source-ref refs/heads/<default branch>` (from `origin/HEAD`, else `main`; change it with `--default-branch`), and `--deny-self-hosted-runners`, and compares the signed predicate with the file. `--bundle <file>` verifies against a bundle from `gh attestation download` instead.

The attest action takes SHA-2 digests only, so the attestation's subject is the sha256 of the statement file; the file names the commit. aidd issues no SLSA Source verification summary attestation for the branch.

### Repository variables

`AIDD_PROTECTED_BRANCHES`, `AIDD_APP_ID`, and `AIDD_ATTEST_CHANGE_RECORD` change without a pull request, so a repository admin can steer the gate through them. Write `protected-branches` literally in the caller workflow, a protected file, and keep the App ID where only organization admins edit it.

## GitLab

The GitLab adapter is **experimental** in 1.0.0: it is tested end to end against a real git repository with a merge request ref and a faked GitLab API (`tests/test_gitlab_e2e.py`), not yet against a live instance.

### Setup on GitLab

`aidd init --ci gitlab` writes `.gitlab/aidd.gitlab-ci.yml`. Include it from `.gitlab-ci.yml`. The template needs GitLab 16.7 or later; for air-gapped instances, mirror the aidd repository, change `aidd_host` in the template script, keep the pinned ref, and mirror the image by digest.

1. An MR can edit its own pipeline. Enforce `aidd-tests` and `aidd-gate` with a **pipeline execution policy** (GitLab Ultimate) or a compliance pipeline, and turn on "Pipelines must succeed".
   - Lock pipeline variables, so nobody can change how the gate installs or runs: `variables_override: { allowed: false }` in the execution policy, and "Minimum role to use pipeline variables" set to "No one allowed" in the project's CI/CD settings.
   - The gate's mode comes from the base branch's config: `AIDD_MODE` can never relax it, and only `mode = "advisory"` in `.aidd/config.toml` makes the gate advisory.
2. The execution policy injects `AIDD_GITLAB_TOKEN` into the gate job only: a project access token with `read_api` and the Reporter role. Do not define it as a project CI/CD variable, where every job, including MR code, could read it. To also post an `aidd/gate` external status, run the gate with `--post-status` and an `api` token.
3. MR approval settings:
   - prevent approval by author
   - prevent approvals by users who add commits
   - remove all approvals when commits are added
   - add approval rules that match your owners

### How it behaves

- **Approvals.** The gate reads the project's approval settings through the API; with "prevent approvals by users who add commits" on, unlinked commit emails need no finding.
- **One pipeline decides.** Only the pipeline for the MR's current head decides.
- **Approving starts no pipeline.** GitLab starts no pipeline when someone approves, so the common path (approve after CI is green) ends in a pending gate job: re-run it, or schedule a pipeline for open MRs.
- **Edited notes.** A note counts as edited when its `updated_at` differs from `created_at`, which GitLab also bumps for some non-edit events; if a real approval is ignored, post it again.
- **Pending approvals.** The gate job fails while approvals are pending. Re-run it after approving, or run it with `--pending-ok` if your approval rules alone block merging. In advisory mode (`mode = "advisory"` in the base config) the job never fails.
- **Forks.** Fork MR pipelines fail closed. Run MR pipelines in the parent project.
- **Merged results pipelines.** They work: the tests run on the MR's source commit.
- **Merge trains.** Not supported yet: turn them off on gated branches, because a train merges a result the gate never judged.

### Identities on GitLab

- The MR author (username) is an author, and commit authors are `email:` identities, which mark authors but never match an Approver.
- Approvals come from the "approved this merge request" system notes. An approval counts on head only if it was given after the pipeline for that head was created.
- Edited notes are ignored.

### Policy on GitLab

The Policy command runs in a clean worktree of the target branch.

## Any other CI

Build a context JSON that matches `schemas/context.schema.json`, from your code platform's API and a base-branch checkout, then run:

```sh
aidd gate --context context.json --record record.json --events events.jsonl
```

The exit codes are 0 for pass, 3 for pending, 1 for fail, and 2 for an error. Post the result as a required status from an identity nobody else can write as.

`examples/*/context.json` show the shape, but they inline the Spec and base config, which the conformance suite expands; build real contexts from the schema.

## Vendor services that plug into the loop

aidd is harness-neutral, and nothing below is required. These services fit the loop at a named point, and none of them changes who decides: findings and proposals still go through the gate like any change.

| Service | Where it fits | How |
| --- | --- | --- |
| A managed AI code review, such as Claude Code Review | Review | Point it at `REVIEW.md`, so it runs the same passes and severities as the team's reviewer. Its findings inform; the Merge approval stays human. |
| A scheduled model-based security scan, such as Claude Security | Learn, on a cadence | Weekly per active repository, beside your CodeQL or other static analysis. A bounded finding becomes a pull request through the gate; a wider one becomes a draft Spec; the fixed class gets a regression test. |
| A chat-channel agent for on-call, such as Claude Tag | the emergency lane and Learn | It diagnoses in the incident channel under its own identity, acts only through gated tools, and writes the postmortem where the Spec's `outcome.learn_ref` points. The commander stays a human. |
| A read-only agent in CI | Implement ⟲ Verify | `templates/github/aidd-triage.yml`: when the test workflow fails on a pull request, an agent with read-only tools reads the failed log and the base branch and comments with what failed, the likely cause, and the next step. It never checks out the pull request, edits, re-runs, or suggests changing a frozen test; the log is data, never instructions. |
| Metrics and alerting | Learn, on a signal | Export a series for `aidd watch` (`templates/github/aidd-watch.yml`); a breach opens the triage issue with a draft Spec. |

## Notifications

aidd runs no server and no bot. To tell people in Slack or Microsoft Teams what waits on them, run a notifier in CI that only posts text to an incoming webhook: no buttons, and every approval still happens on the pull request or merge request, where the gate reads it. A notification is never evidence or an approval.

**GitHub.** Copy `templates/github/aidd-notify.yml` into `.github/workflows/`, and add a repository secret `SLACK_WEBHOOK_URL` (a Slack incoming webhook), `TEAMS_WEBHOOK_URL` (a Teams Workflows webhook, "When a Teams webhook request is received"; the Office 365 connector webhooks were retired in 2026), or both. With neither set it posts nothing. It sends three messages:

| Message | When | What it says |
| --- | --- | --- |
| status | `aidd/gate` changes on a pull request | one line, such as `SPEC-9 waits for Spec approval: @alice, @org/leads -> <pull request>`, or that it is red or passed. A status the gate App posts triggers it through the `status` event; a status posted with `GITHUB_TOKEN` triggers no workflow, so the aidd-gate run that posted it stands in. A status is announced once, and only when it differs from the one before. |
| digest | weekday mornings | what waits on each approver: `aidd next --json` on every open pull request's head, where a Spec waiting for approval lives, and `aidd next --all --json` on the default branch, grouped by approver. `aidd next --waiting-on-me` is the same list for one person at their own terminal. |
| weekly | Monday | `aidd metrics` over the last seven days of gate events: the changes and their decisions, the first-pass test rate, the approval waits, and the major changes merge-approved within 10 minutes of the gate asking (`fast_major_merge_approvals`), a rubber-stamp signal to look at again. |

Every action is pinned by commit SHA, each job asks for read permissions only, the webhook secrets reach only the job that posts, and that job runs no checkout. The digest reads pull request heads as data in a step with no token.

**GitLab.** A scheduled pipeline on the default branch does the same. Create two pipeline schedules with the variable `AIDD_NOTIFY` set to `digest` (weekday mornings) and `weekly` (Monday), and add `SLACK_WEBHOOK_URL` or `TEAMS_WEBHOOK_URL` as a masked, protected CI/CD variable. The jobs reuse the `.aidd` template from `.gitlab/aidd.gitlab-ci.yml`, which runs aidd from its pinned commit. This digest covers the Specs on the default branch; to include open merge requests, fetch each one's `refs/merge-requests/<iid>/head` and run `aidd next --json` in it, as the GitHub template does with pull requests.

```yaml
# .gitlab-ci.yml, after the include of .gitlab/aidd.gitlab-ci.yml
.aidd-notify:
  extends: .aidd
  after_script:
    - |
      [ -s notify.txt ] || exit 0
      python3 - <<'PY'
      import json, os, urllib.request
      text = open("notify.txt", encoding="utf-8").read().strip()
      def post(url, payload):
          req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
          urllib.request.urlopen(req, timeout=30).read()
      if os.environ.get("SLACK_WEBHOOK_URL"):
          safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
          post(os.environ["SLACK_WEBHOOK_URL"], {"text": safe})
      if os.environ.get("TEAMS_WEBHOOK_URL"):
          body = [{"type": "TextBlock", "text": line, "wrap": True} for line in text.splitlines()]
          card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.2", "body": body}
          post(os.environ["TEAMS_WEBHOOK_URL"], {"type": "message", "attachments": [
              {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]})
      PY

aidd-notify-digest:
  extends: .aidd-notify
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule" && $AIDD_NOTIFY == "digest"
  script:
    - |
      aidd next --all --json > next.json
      python3 - <<'PY' > notify.txt
      import json
      by = {}
      for s in json.load(open("next.json", encoding="utf-8")):
          for who in s.get("approvers") or []:
              by.setdefault(who, []).append(s["what"])
      for who, waits in sorted(by.items()):
          print(f"{who}: " + "; ".join(waits))
      PY

aidd-notify-weekly:
  extends: .aidd-notify
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule" && $AIDD_NOTIFY == "weekly"
  script:
    - |
      # Point this at the gate events you keep (aidd gate --events), such as a file your gate job appends to.
      aidd metrics events/*.jsonl --since "$(date -u -d '7 days ago' +%Y-%m-%d)" > notify.txt
```

## Deploy commands held for a person

The gate governs merges; a deploy is the other place a person must stay in the loop, and the only one during the build. Give agents autonomy per environment: they build, test, and deploy to staging on their own, and a production deploy waits for a person. Two layers do it:

1. **On the platform, the control.** Deploy production from CI only, behind a GitHub environment with required reviewers, or a GitLab protected environment with deployment approvals, so no agent credential can deploy by itself.
2. **In the agent session, the guide.** Name the deploy commands in `.aidd/config.toml`, and the aidd hook denies them to every agent until a person approves:

```toml
[[guard.gated_commands]]
name = "production deploy"
match = ["deploy", "production"]
environment = "production"
requires = "RELEASE_APPROVAL"
message = "Production deploys go through the release train: ask in #release."
```

With this, `make deploy ENV=production` is denied, and the deny names the held command and what to do: the person who approves starts the session with the variable set, `RELEASE_APPROVAL=CHG-1234 claude`, or runs the command themselves. An agent cannot approve itself: the hook reads the environment Claude Code started with, never the agent's shell, and denies a command that names the variable. Staging deploys match nothing and run. The fields are in [CONFIG.md](CONFIG.md#guard); the matching is best-effort parsing, which is why the platform layer stays the control.

The edit-time hook never prompts mid-build: it answers allow or deny, and each deny names what to do next. An approval prompt during the build would put a person back on the critical path of every session running in parallel, so people decide at Spec approval, at Merge approval, and when they allow a held deploy command, never in between.

## Issue trackers

Jira, Linear, or GitHub Issues can mirror a Spec under its `id` and carry its `status`; the Spec file in the repository stays the approved source, and the verifier reads only the repository.
