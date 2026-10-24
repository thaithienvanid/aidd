# Platforms

How to set up the gate on GitHub, GitLab, and any other CI, and how to [leave one](#leave-a-ci-provider-or-a-git-platform). This page owns the setup of the gate's GitHub App, its environment, and the branch ruleset. Other pages link here. Why the gate is safe to run, and what it relies on, is in [METHOD.md §14](METHOD.md#14-platform-bindings-and-trust). To try the loop locally first, with none of this, follow the [Quickstart](QUICKSTART.md).

## What holds without the full setup

The gate blocks a merge only when four things are in place:

- `mode: enforce` in the base branch's `.aidd/config.yaml`
- a platform rule that requires `aidd/gate`
- a status source pinned to the gate's GitHub App, or a pipeline execution policy on GitLab
- a plan that allows that rule on the repository

This page owns that list. Other pages link here. Take one away, and this is what remains:

| Missing | What still holds | What does not |
| --- | --- | --- |
| Enforce mode | the gate runs and reports every finding on `aidd/gate (advisory)` | nothing is blocked |
| A required check (a ruleset or branch protection) | the status is posted on every pull request | anyone who can merge can merge a red change |
| The gate's GitHub App | the status is computed the same way | anyone with write access can post a green `aidd/gate` by hand |
| A plan with rulesets on a private repository (GitHub Free) | advisory reports, as above | the check cannot be required: the gate stays advisory until the repository is public or on GitHub Pro, Team, or Enterprise |
| A wired agent hook (`aidd init --harness <agent>`) | the gate still sees every out-of-scope or unapproved change at merge | nothing stops the agent at edit time |
| A platform at all | `aidd gate` and `aidd land` on your machine, after a yes from a person at a terminal ([local-first](ADOPTION.md#local-first-no-github-or-gitlab)) | a person's own git commands can still move the base branch |

## GitHub

`aidd init --ci github` installs three workflows:

| Workflow | Trigger | Runs PR code? | Token | Role |
| --- | --- | --- | --- | --- |
| `aidd-tests` | `pull_request`, `merge_group` | yes (untrusted) | read-only, no secrets | runs tests green on head and red on base through the composite action `thaithienvanid/aidd@v1.0.0` (in a merge queue: on the merge-group commit); uploads `aidd-evidence` |
| `aidd-relay` | `pull_request_review` | no | none | relays review events |
| `aidd-gate` | `pull_request_target`, `issue_comment`, `workflow_run` | **never** | GitHub App, `statuses: write` | a thin caller of the reusable workflow `.github/workflows/gate.yml@v1.0.0`; builds the trusted context, verifies, and posts `aidd/gate` |

### Setup

**You need:**

- admin rights on the repository
- permission to create a GitHub App for the account or organization that owns the repository. An organization owner has it, or a member an owner allowed to manage Apps.
- for a private repository, a plan with rulesets, such as GitHub Pro, Team, or Enterprise

Allow about an hour the first time.

1. **Connect your test suite.** In `.github/workflows/aidd-tests.yml`, install your toolchain before the aidd step. Make `tests` in `.aidd/config.yaml` run your suite, with the [recipes below](#3-connect-your-test-suite). Run `aidd doctor` until nothing fails. Commit everything `aidd init` wrote. Open the setup pull request.
2. **Merge the setup PR first.** Under the solo and team profiles, `aidd init` installs the gate in advisory mode, so it reports on `aidd/gate (advisory)` and blocks nothing until you set `mode: enforce` in `.aidd/config.yaml`. The org and audited profiles start it in enforce mode. The gate runs from the default branch, so it cannot judge anything until it is merged there. A change whose base has no config never passes.
3. **Create a GitHub App for the gate.** Settings → Developer settings → GitHub Apps, with webhooks off.
   - Permissions are `Commit statuses: write`, plus read access to `Contents`, `Pull requests`, `Issues`, `Actions`, and `Checks`. Add the organization permission `Members: read` if you list `@org/team` approvers.
   - Install it on the repository, or on the organization for a fleet.
4. **Create an environment named `aidd-gate`.**
   - Deployment branches are the protected bases only, which is the default branch plus any `AIDD_PROTECTED_BRANCHES`. For `pull_request_target`, the job runs on the PR's base branch.
   - Add the variable `AIDD_APP_ID` and the secret `AIDD_APP_PRIVATE_KEY`. Keep the key here only, never as a repository or organization secret. Pass no secrets from the caller.
   - Do not add required reviewers to the environment, or every gate run waits.
5. **Protect the default branch.** In Settings → Rules → Rulesets:
   - require a pull request
   - require the status check `aidd/gate`, with its expected source set to your App
   - block force pushes
   - we recommend "Require approval of the most recent reviewable push", which also stops whoever pushed last from approving

   `aidd init --ci github` writes these rules as `.github/rulesets/main.json`. Import it under Settings → Rules → Rulesets → Import a ruleset, then set the expected source of `aidd/gate` to your App. Its `goal.json` protects the goal branches, `goal/**`. It blocks force pushes and deletion, so nobody rewrites or deletes a goal's integrated Specs. Only `aidd integrate` and `aidd sync` move a goal branch, and the guard holds agents to that locally. aidd never changes a platform's settings itself.

   Rulesets on private repositories need GitHub Pro, Team, or Enterprise.

   `aidd doctor` checks these rules when it can reach GitHub, with a `GH_TOKEN` or after `gh auth login`. Offline, it says it skipped. It warns when `aidd/gate` is not required or not pinned to an App. It also warns when a GitHub App may bypass the ruleset, when the last pusher may approve, and when a goal branch allows force pushes or deletion.

   Make `aidd/gate` the required check, not the review count, for the reasons [below](#github-rulesets-and-aidd). GitHub's own "required approvals" count an approval from any account with write access, a bot or an agent's App token included. aidd never counts an agent account, whether one in `identities.bots`, Copilot's `copilot-pull-request-reviewer[bot]`, or a `[bot]` named for an agent. It warns `merge_approval.agent_approval` when one approves. It counts another bot only when `owners.approvers` names it.
6. **Other protected branches.** The default branch is always protected. Release branches, for example, are not. List the others in the repository variable `AIDD_PROTECTED_BRANCHES` or the `protected-branches` input, comma-separated. Globs such as `release/*` work. PRs to any other base get the status `aidd/gate (<base>)`, which cannot satisfy the rule.
7. **Enforce.** Watch the advisory reports for a while. `aidd metrics` [summarizes them](ADOPTION.md#team). When they look right, set `mode: enforce` in `.aidd/config.yaml`. The base branch's config wins. The workflow's `mode` input applies only when the config sets no mode, and `aidd init` writes one only with `--enforce`. Set it in the config, so the gate and the guard agree, because the guard reads only the config. `aidd init --enforce` starts enforced.

<a id="3-connect-your-test-suite"></a>
### Toolchain recipes

| Stack | Install step in aidd-tests.yml | `tests` command |
| --- | --- | --- |
| Node | `actions/setup-node`, then `npm ci` | `["npm", "test"]` |
| Python | `actions/setup-python`, then `uv sync --frozen` or `pip install -r requirements.txt` | `["python", "-m", "pytest", "-q"]` |
| Go | `actions/setup-go`, then `go mod download` | `["go", "test", "./..."]` |
| Java | `actions/setup-java` (temurin) | `["./mvnw", "-B", "test"]` or `["./gradlew", "test"]` |
| Terraform | `hashicorp/setup-terraform` | `["terraform", "validate"]` (plan needs secrets, so keep it out of tests) |

Use lockfile-exact installs such as `npm ci`, not `npm install`, because the red run needs a clean tracked tree.

### Why the App matters

Anyone with push access can write a commit status, so only [a status source pinned to the App](METHOD.md#14-platform-bindings-and-trust) makes `aidd/gate` trustworthy. Without an App, the workflow falls back to `GITHUB_TOKEN`, and the gate is advisory against anyone with write access.

### Reusable workflow inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `mode` | `advisory` in the caller `aidd init` writes; `enforce` when you call the reusable workflow yourself | used when the base config sets no `mode`. `advisory` posts `aidd/gate (advisory)`, which never satisfies the rule: use it to roll out without blocking |
| `protected-branches` | `vars.AIDD_PROTECTED_BRANCHES` | protected bases besides the default branch |
| `org-preset-url`, `org-preset-sha256` | empty | an org preset and its pin, applied as the root parent of every repository's config ([ADOPTION.md](ADOPTION.md#organization)) |
| `runs-on` | `ubuntu-latest` | runner label, for self-hosted runners |
| `timeout-minutes` | `15` | gate job timeout |

The gate runs aidd from the exact commit of the reusable workflow you call, so pinning `uses: thaithienvanid/aidd/.github/workflows/gate.yml@<ref>` pins the gate's code too. Pin a commit SHA for the strongest integrity. GitHub Enterprise Server lacks the `job.workflow_sha` context, so copy `gate.yml` into your own repository there.

### Identities on GitHub

- The PR author, commit authors, and committers are authors. `web-flow` is ignored.
- Reviews come from the Reviews API. An approval counts only on the head commit, and a later comment-only review changes nothing.
- Comments come from the Issues API. Edited comments are ignored.
- More than 250 commits cannot be verified and fail. More than 3,000 reviews or comments is a gate error, never a silent cut.
- A commit author GitHub can't map to an account, such as an unlinked email, might be an Approver. The gate warns, or fails under `unlinked_authors: fail`, the audited default. Link the email, or list agent emails in `identities.bots`.
- Only comments that carry, or carried, an `/aidd` command re-run the gate.
- Bot PRs from Dependabot or Renovate without an `aidd` block are read as standard dependency changes. See [FAQ](FAQ.md#bots).

### Reuse what you already have

- **Owners from CODEOWNERS.** `owners.codeowners: true` reads the base branch's CODEOWNERS, in `.github/`, the root, or `docs/`. For every changed path, the last matching rule's owners must approve, at Spec approval and Merge approval. aidd applies separation of duties and team resolution to them, which GitHub's own code-owner review does not do. `owners.paths` still adds areas CODEOWNERS does not cover.
- **Your CI as evidence.** `evidence.status_checks: ["build", "test"]` requires those check runs to succeed on the head, where neutral and skipped count as success. Only check runs count, from an app listed in `status_check_apps` and on the pull request's own branch. Commit statuses never count. The repository suite then runs once, in your CI, and `aidd-tests` runs only the Spec's new-behavior tests for red-then-green. This is as trustworthy as your required checks, so pin their source in the ruleset too.
- **Rulesets.** Keep "Require approval of the most recent reviewable push" on beside `aidd/gate`.

### Evidence the pull request cannot touch

By default, the test workflow lives in each repository, so changing it is a protected, major change. For a stronger guarantee:

1. Put [`templates/github/aidd-tests-central.yml`](../templates/github/aidd-tests-central.yml) in a platform repository only the platform team can change.
2. Require it on the gated repositories with an organization ruleset, under "Require workflows to pass before merging". A pull request then cannot change how its tests run.
3. Set `evidence.signer_workflow: "<org>/<platform-repo>/.github/workflows/aidd-tests.yml"` in the org preset. It locks once a parent sets it.

The central workflow runs tests in one job. A second job, which runs no pull request code, attests `evidence.json` with GitHub artifact attestations. The gate then verifies the attestation with `gh attestation verify --signer-workflow` and refuses anything else.

This closes evidence from any other workflow and edits to the test workflow itself. It cannot make the pull request's own test code honest. Spec approval and Merge approval still cover that.

This path is new in 1.0.0 and has not yet been exercised on a live organization.

### GitHub Enterprise Server and restricted Actions

- **GHES.** It lacks the `job.workflow_sha` context the reusable workflow uses to run aidd from its own commit. Copy `gate.yml` into a repository of your own. Pin the aidd checkout inside it to a commit SHA. Call that copy from `aidd-gate.yml`. Artifact attestations and `actions/create-github-app-token` need a GHES version that ships them. Without attestations, skip the central evidence workflow.
- **Actions allowlists.** Under "Allow select actions and reusable workflows", allow `thaithienvanid/aidd` or your copy, and the actions the gate pins. These are `actions/checkout`, `actions/setup-python`, `actions/create-github-app-token`, `actions/upload-artifact`, `actions/download-artifact`, `actions/attest-build-provenance` for the central evidence workflow, and `actions/attest` for the optional change-record signing. An air-gapped instance mirrors them the same way it mirrors any action.
- **Egress.** At run time the gate reaches only:
  - the platform's API, at `GITHUB_API_URL` and `GITHUB_SERVER_URL` on GitHub and `CI_API_V4_URL` on GitLab, so GHES and self-managed GitLab work
  - the platform's git server, which serves the change's commits
  - the artifact storage the API redirects evidence downloads to
  - the URL of an org preset or an `extends` parent, when you configure one
  - the attestation endpoints that `gh attestation verify` calls, when `evidence.signer_workflow` is set

  It sends nothing else anywhere, with no telemetry and no vendor service. At gate time, the GitLab template fetches aidd from github.com at the pinned commit. To mirror it, change `aidd_host` in the template script. The secret scan template, `aidd-security.gitlab-ci.yml`, downloads gitleaks from github.com and checks its SHA-256. To mirror gitleaks, host the same file and change the URL. The CLI commands that reach the network outside the gate are in [SECURITY.md](../SECURITY.md#data-handling). What the gate reads and writes is in [ENTERPRISE.md](ENTERPRISE.md#7-data-handling-and-privacy).

**Description edits.** The `aidd-tests.yml` template re-runs the tests on a pull request's description edit only when the edit changes the Change Request block. A small `block` job compares the old and new blocks from the event. A title-only edit, or an edit elsewhere in the description, starts no test. The gate then reads the newest earlier run of the same head, and within a run, the newest attempt's artifact. So a re-run's evidence replaces the first attempt's.

### Merge queues

The gate judges every queue entry and posts `aidd/gate` on its merge-group commit, which is what the queue waits for. Approvals stay on the pull request head. The tests run again on the merge-group commit. That commit must hold exactly the approved head, [merged into the commit the entry was built on](METHOD.md#merge-queue-evidence).

1. **Run the tests in the queue.** The `aidd-tests.yml` template triggers on `merge_group`, and the aidd action then runs `aidd test --merge-queue`. A copy written before merge queues needs these parts of the template:
   - its `merge_group` trigger
   - its `pull-requests: read` permission, to read the queued pull request's description
   - its concurrency group and checkout ref, which keep one queue entry from cancelling another

   Keep `aidd-gate.yml` as it is, because the queue reaches the gate when that `aidd-tests` run completes, through `workflow_run`. Never add `merge_group` to the gate workflow. That would run the workflow file from the merge-group commit.
2. **Turn on the queue** in the branch ruleset with "Require merge queue", and keep `aidd/gate` required and pinned to your App. The `aidd-gate` environment needs no change, because the gate job runs on the default branch, as for pull requests.
3. **Only merge non-failing pull requests.** When the queue builds more than one entry at a time, turn it on with the grouping strategy `ALLGREEN`. An entry built on another entry carries that entry's changes too. The gate fails such an entry until the queue is confirmed to merge only groups whose every entry passed. `aidd doctor` warns when the setting is off.

What fails, and why:

| Finding | Meaning | Fix |
| --- | --- | --- |
| `merge_queue.diff_mismatch` | the entry's commit is not the approved head merged into its parent | remove the entry and queue the pull request again |
| `merge_queue.conflict` | the approved head no longer merges cleanly into the queue | update the pull request, get it approved on the new head, queue it again |
| `merge_queue.stacked_unverified` | the entry is stacked on another, and the queue may merge a failing entry | turn on "Only merge non-failing pull requests" |
| `tests.evidence_other_head` | the evidence is for the pull request head, not the entry's commit | wait for the queue's `aidd-tests` run |

GitLab merge trains work the same way, as [Merge trains](#merge-trains) describes.

### GitHub rulesets and aidd

A ruleset setting either does work aidd relies on, or duplicates a rule aidd enforces itself. What each one does beside the gate:

| Ruleset setting | Set it to | The aidd rule that covers it, or relies on it |
| --- | --- | --- |
| Require status checks: `aidd/gate` | required, with its expected source set to your App | the whole gate: every rule posts through this one status. Without the App pin anyone with write access can post it ([METHOD.md §14](METHOD.md#14-platform-bindings-and-trust)); `aidd doctor` warns |
| Required approvals (count) | 0 or more; aidd does not need it | `merge_approval` counts eligible Approvers itself (`gates.approvals` per route), excluding authors, co-authors, committers, and agent accounts. GitHub's count takes any write-access account, a bot or an agent included. So it must never be the only check. aidd warns `merge_approval.agent_approval` when an agent approved |
| Dismiss stale pull request approvals when new commits are pushed | on, recommended | `merge_approval` already counts only approvals of the head commit, or of an earlier head a trivial rebase carries ([Approvals across rebases](#approvals-across-rebases)). It ignores approvals given before the base changed. The setting keeps GitHub's own count honest too |
| Require approval of the most recent reviewable push | on | relied on: GitHub stops the last pusher from approving, including a person who pushed on an agent's behalf. aidd's author rule covers commit authors and committers, and `aidd doctor` warns when this is off |
| Require review from Code Owners | optional | `owners.codeowners: true` makes aidd read CODEOWNERS and require the owners at Spec approval and Merge approval, with separation of duties and team resolution applied (`merge_approval.owner_area`, `spec_approval.owner_area`) |
| Required status checks from your CI, pinned to their app | optional | `evidence.status_checks` with `evidence.status_check_apps` counts only check runs from the apps you name (`tests.check_failed`, `tests.check_waiting`); pin the same apps in the ruleset |
| Bypass list | empty, or humans only | aidd has no bypass: an actor on the bypass list merges past `aidd/gate`, and no gate record is written for it. `aidd doctor` warns when a GitHub App may bypass, because an agent's App could merge unreviewed |
| Require merge queue, "Only merge non-failing pull requests" | on for a queue that builds more than one entry | relied on by `merge_queue`: a stacked entry fails (`merge_queue.stacked_unverified`) until the grouping strategy is `ALLGREEN`; `aidd doctor` warns |
| Copilot code review, "Automatically request Copilot code review" | optional | Copilot reviews as `copilot-pull-request-reviewer[bot]`. Its review is a comment. If an agent account ever approves, the approval never counts toward Merge approval. The gate warns `merge_approval.agent_approval`, so you can check the ruleset's own count |
| Block force pushes, restrict deletions | on | relied on: approvals and evidence bind to commit SHAs, and a rewritten base history would change what a merge base means |

### Signing the change record

With `--record`, the gate writes the [agent change record](METHOD.md#change-record) beside the gate record. It's `change-record.intoto.json`, an in-toto statement whose subject is the head commit. It is kept in the gate's artifact with the record. To sign a passing one:

1. Use a public repository, or GitHub Enterprise Cloud for a private or internal one. Artifact attestations are not offered on other plans. Without them, leave signing off. `aidd record verify --allow-unsigned` still checks the record's shape, subject, decision, and approvals.
2. Set the repository variable `AIDD_ATTEST_CHANGE_RECORD` to `true`. The `attest` job in `aidd-gate.yml` then downloads the record and signs it with `actions/attest`, pinned by commit SHA. Only that job holds `id-token: write` and `attestations: write`.
3. To check one, download the artifact with `gh run download`. Then, in a checkout of the repository, run `aidd record verify <head sha> --online --tenant <tenant>`. It takes the repository from the checkout's github.com `origin`, or from `--repo <owner>/<repo>`, never from the record. It fails when the record names another repository, or was not made from a trusted CI context. It runs `gh attestation verify` on the file with `--signer-workflow <owner>/<repo>/.github/workflows/aidd-gate.yml`, `--source-ref refs/heads/<default branch>`, and `--deny-self-hosted-runners`. Change the first with `--signer-workflow`. The default branch comes from `origin/HEAD`, else `main`, and `--default-branch` changes it. It also compares the signed predicate with the file. `--bundle <file>` verifies against a bundle from `gh attestation download` instead.

The attest action takes SHA-2 digests only, so the attestation's subject is the sha256 of the statement file. The file names the commit. aidd issues no SLSA Source verification summary attestation for the branch.

### Repository variables

`AIDD_PROTECTED_BRANCHES`, `AIDD_APP_ID`, and `AIDD_ATTEST_CHANGE_RECORD` change without a pull request, so a repository admin can steer the gate through them. Write `protected-branches` literally in the caller workflow, which is a protected file. Keep the App ID where only organization admins edit it.

## GitLab

The GitLab adapter is **experimental** in 1.0.0. `tests/test_gitlab_e2e.py` tests it end to end against a real git repository with a merge request ref and a faked GitLab API. It is not yet tested against a live instance.

### Setup on GitLab

`aidd init --ci gitlab` writes `.gitlab/aidd.gitlab-ci.yml`. Include it from `.gitlab-ci.yml`. The template needs GitLab 16.7 or later. For air-gapped instances:

- mirror the aidd repository
- change `aidd_host` in the template script
- keep the pinned ref
- mirror the image by digest

On every instance:

1. An MR can edit its own pipeline. Enforce `aidd-tests` and `aidd-gate` with a **pipeline execution policy**, on GitLab Ultimate, or with a compliance pipeline. Turn on "Pipelines must succeed".
   - Lock pipeline variables, so nobody can change how the gate installs or runs. Set `variables_override: {allowed: false}` in the execution policy. In the project's CI/CD settings, set "Minimum role to use pipeline variables" to "No one allowed".
   - The gate's mode comes from the base branch's config, so `AIDD_MODE` can never relax it. Only `mode: advisory` in `.aidd/config.yaml` makes the gate advisory.
2. The execution policy injects `AIDD_GITLAB_TOKEN` into the gate job only. It's a project access token with `read_api` and the Reporter role. Do not define it as a project CI/CD variable, where every job, including MR code, could read it. To also post an `aidd/gate` external status, run the gate with `--post-status` and an `api` token.
3. MR approval settings:
   - prevent approval by author
   - prevent approvals by users who add commits
   - remove all approvals when commits are added
   - add approval rules that match your owners

### How it behaves

- **Approvals.** The gate reads the project's approval settings through the API. With "prevent approvals by users who add commits" on, unlinked commit emails need no finding. With "remove all approvals when commits are added" off, the gate warns with `merge_approval.survives_push`.
- **Retargeting.** A new target branch voids every approval given before it. GitLab records the new target branch as a system note, whether a person or GitLab set it.
- **One pipeline decides.** Only the pipeline for the MR's current head decides.
- **Approving starts no pipeline.** GitLab starts no pipeline when someone approves. So the common path, approving after CI is green, ends in a pending gate job. Re-run the job, or schedule a pipeline for open MRs.
- **Edited notes.** A note counts as edited when its `updated_at` differs from `created_at`. GitLab also bumps `updated_at` for some non-edit events. If a real approval is ignored, post it again.
- **Pending approvals.** The gate job fails while approvals are pending. Re-run it after approving, or run it with `--pending-ok` if your approval rules alone block merging. In advisory mode, with `mode: advisory` in the base config, the job never fails.
- **Forks.** Fork MR pipelines fail closed. Run MR pipelines in the parent project.
- **Merged results pipelines.** They work, and the tests run on the MR's source commit.
- **Merge trains.** They work, as [Merge trains](#merge-trains) describes.
- **Publishing.** `aidd publish` pushes the branch and opens its merge request as you, or finds the open one. Then it posts each Spec approval you recorded on this machine as a note there, the line the gate counts. It uses your own token, from `GITLAB_TOKEN` when `GITLAB_HOST` names the project's host (gitlab.com by default), or else the token `glab` stored for that host and port. aidd asks `glab` with its token and host variables removed, because `glab` reads those first, for every host. It posts nothing with a bot's token, such as a service account's or an access token's. It takes only the project's own merge request of the branch, never a fork's of the same name. It posts a line only when that merge request names the head it just pushed. Otherwise it says why, and you type `publish` again once GitLab has caught up. Your Merge approval stays your approval of the merge request on GitLab.

### Identities on GitLab

- The MR author's username is an author, and commit authors are `email:` identities, which mark authors but never match an Approver.
- Approvals come from the "approved this merge request" system notes. An approval counts on head only if it was given after the pipeline for that head was created. In a merge train pipeline, it counts once the merge request had that head, by the head's diff version. An earlier approval names the head the merge request had then, read from its diff versions. It counts only when [a trivial rebase carries it](#approvals-across-rebases).
- Edited notes are ignored.
- Only GitLab's user lookup, `GET /users/:id`, says whether an account is a bot. So a pool that names a group includes only the members it calls people (`bot: false`). A service account, an access token's bot user, and a member GitLab doesn't answer for are left out. The gate's log names each pool that shrank, and the gate waits for a person's approval.
- An approval or an approval line from a bot account is recorded as `<username>[bot]`, as GitHub names a bot, so it never counts as a person's.

### Merge trains

Merge trains are experimental, like the rest of the GitLab adapter. They're built against GitLab's documentation and a faked API, and not yet run against a production instance.

In a train pipeline, where `CI_MERGE_REQUEST_EVENT_TYPE` is `merge_train`, the gate judges the merge request's entry in the train as it judges a GitHub queue entry. Approvals stay on the merge request head, and `CI_MERGE_REQUEST_SOURCE_BRANCH_SHA` must name it. The tests run again on the entry's commit, `CI_COMMIT_SHA`, which the train ref `refs/merge-requests/<iid>/train` must still name, and the gate job's checkout must be. That commit's tree must be exactly the approved head merged onto the commit the entry was built on. That's the target branch, or the entry ahead of it.

The commit an entry was built on is on its first-parent chain, and in a merge-commit train it's the entry's first parent. So the gate and `aidd test --merge-queue` both walk that chain back to the target branch, newest first. They take the first commit whose merge with the head gives the entry's tree, and skip a rebased copy of the merge request's own commits. So an entry names the same parent before and after the entry ahead merges. An entry built on the entry ahead carries that entry's changes too. GitLab merges an entry only once every entry ahead merged, and an entry that fails leaves the train. So a failing entry never merges with yours.

The template's `aidd-tests` job runs `aidd test --merge-queue` in a train pipeline. A copy written before merge trains checks out the merge request head instead, and its evidence never counts in a train. The findings are the ones in [Merge queues](#merge-queues). To fix `merge_queue.diff_mismatch` or `merge_queue.conflict`, remove the merge request from the train, and add it again once its head is approved.

### Policy on GitLab

The Policy command runs in a clean worktree of the target branch.

## Approvals across rebases

A Merge approval binds to the head commit. Rebasing a branch onto a newer base, or merging the base into it, makes a new head. By default, a new head needs a new approval. When the rebase was trivial, in the sense of Gerrit's `TRIVIAL_REBASE`, the approval of the earlier head carries to the new one under `gates.approval_carry: trivial_rebase`, and only then:

- **The same diff.** The change's diff from where the earlier head met the base equals the new head's diff from its base, byte for byte. That covers every added, removed, and context line, every mode, every binary patch, and whitespace. Only what a rebase moves is left out, which is the blob ids on `index` lines and the line numbers on hunk headers. It is never the default `git patch-id`, which ignores whitespace.
- **A newer base.** The new base descends from the approved head's base on the protected branch.
- **Nobody new.** Whoever authored or committed the new head's commits also authored or committed the approved head's. A rebase by someone else, the Approver included, needs a new approval. Separation of duties is checked again against the new head's authors and committers.
- **No protected path** in the change, and the route is one the profile carries in `gates.approval_carry_routes`. An emergency never carries.
- **The tests run again** on the new head, by the usual rules, because a carried approval never carries evidence.

The adapters compute the comparison, `approval_equivalents` in the context, for each earlier head an approval names:

- GitHub fetches a force-pushed head by its id.
- GitLab reads which head the merge request had when the approval was given, from its diff versions.
- Locally, the decision records name the head.

The gate decides, and warns `merge_approval.carried` naming both heads. It records the approval with `approved_sha`, `carried_to`, and `carry_reason` in the gate record and the change record. An approval that doesn't carry says why, with `merge_approval.not_carried`. A Spec approval is never carried. It binds to the hash of the Spec and its tests, which a rebase does not change. A Spec commit that a rebase replaced still proves Spec approval came first, when both of these hold:

- its own diff held only the frozen files
- its Spec hashes to the approved hash

<!-- aidd:gen profiles:carry -->
| Profile | A Merge approval carries across a trivial rebase | On routes |
| --- | --- | --- |
| solo | trivial_rebase | minor, normal, major |
| team | trivial_rebase | minor, normal, major |
| org | trivial_rebase | minor, normal |
| audited | none | none |
<!-- aidd:end -->

A config may only tighten it, with `approval_carry: none` or fewer routes. On GitHub, "Dismiss stale pull request approvals when new commits are pushed" dismisses GitHub's own approval on every push. That approval is part of GitHub's review count, which aidd does not read, so the setting can stay on. On GitLab, "Remove all approvals when commits are added" removes the approval itself, so nothing is left to carry. Turn it off to let aidd decide.

## Any other CI

Build a context JSON that matches `schemas/context.schema.json`, from your code platform's API and a base-branch checkout. Then run:

```sh
aidd gate --context context.json --record record.json --events events.jsonl
```

The exit codes are 0 for pass, 3 for pending, 1 for fail, and 2 for an error. Post the result as a required status from an identity nobody else can write as.

`examples/*/context.json` show the shape, but they inline the Spec and base config, which the conformance suite expands. Build real contexts from the schema.

## Leave a CI provider or a git platform

aidd keeps its state in git, so most of it moves with the repository. What the platform holds stays behind, so export it before you turn the old platform off.

**What moves with the repository:**

- the Specs, the config in `.aidd/config.yaml` and `.aidd/allowed_signers`, the work items, and every commit. A mirror keeps each commit ID, so a line that names a commit still names the same one.
- the decision records, on the ref `refs/aidd/decisions`. A plain clone fetches only branches and tags, so it leaves this ref behind.

**What stays on the platform:**

- the Spec approvals, which are the `/aidd approve-spec <ID> <commit>` comments, and the Merge approvals, which are the platform's reviews and GitLab's approval notes
- the `aidd/gate` statuses and the check runs
- the workflow artifacts, with the test evidence, the gate record, the change record, and the events. They expire after the retention in [ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence). The records name each approval the gate counted, so an export of them keeps the audit trail.
- the attestations that sign change records, which `aidd record verify --online` checks on GitHub
- the setup, meaning the ruleset or branch protection, the gate's GitHub App, the `aidd-gate` environment and its secret, the repository variables, and GitLab's pipeline execution policy

**The gate runs on any CI.** It decides from one context file, as `schemas/context.schema.json` defines it. On GitHub and GitLab, `aidd init` writes the jobs that build it. On [any other CI](#any-other-ci), build it yourself and run `aidd gate --context`.

Run the git steps in your own terminal, because the guard denies an agent a push under `refs/aidd/`.

1. **Export the records** while the old platform still serves them. Download the gate runs' artifacts as in [Reading the metrics](ADOPTION.md#reading-the-metrics). Then run `aidd record export records <dir> --out <folder>` and `aidd record export events <dir> --out <folder>`.
2. **Mirror the repository with its refs:**

   ```sh
   git clone --mirror <old-url> repo.git
   git -C repo.git push <new-url> 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*' 'refs/aidd/*:refs/aidd/*'
   git ls-remote <new-url> 'refs/aidd/*'
   ```

   Name the refs instead of `git push --mirror`. A mirror also holds the old platform's own refs, such as `refs/pull/*` and `refs/merge-requests/*`, which the new platform may refuse. If only a local repository holds `refs/aidd/decisions`, push it from there the same way.
3. **Write the new CI files.** In a checkout of the new repository, run `aidd init --ci github` with `--dry-run` first, then without it. Use `gitlab` instead, or `none` for any other CI. It keeps the existing config. Never add `--force`, which [replaces the config](TROUBLESHOOTING.md#aidd-init---force-replaced-my-config). On GitHub, set `project.repo` to the new `owner/name`. Delete the old CI's files in the same change, and merge it first, as on a first setup.
4. **Set up the new platform** as on a first setup, for [GitHub](#setup) or [GitLab](#setup-on-gitlab). Require `aidd/gate` on the default branch, with its source pinned, as [What holds without the full setup](#what-holds-without-the-full-setup) explains.
5. **Open each open pull request again** on the new platform. The tests run again there. A person posts each `/aidd approve-spec <ID> <commit>` line again, and since the commit is the same, the line still binds. Merge approval binds the head, so a person approves each head again.

## Vendor services that plug into the loop

aidd is harness-neutral, and nothing below is required. These services fit the loop at a named point. None of them changes who decides, so findings and proposals still go through the gate like any change.

| Service | Where it fits | How |
| --- | --- | --- |
| A managed AI code review, such as Claude Code Review | Review | Point it at `REVIEW.md`, so it runs the same passes and severities as the team's reviewer. Its findings inform; the Merge approval stays human. |
| A scheduled model-based security scan, such as Claude Security | Learn, on a cadence | Weekly per active repository, beside your CodeQL or other static analysis. A bounded finding becomes a pull request through the gate; a wider one becomes a draft Spec; the fixed class gets a regression test. |
| A chat-channel agent for on-call, such as Claude Tag | the emergency lane and Learn | It diagnoses in the incident channel under its own identity, acts only through gated tools, and writes the postmortem where the Spec's `outcome.learn_ref` points. The commander stays a human. |
| A read-only agent in CI | Implement ⟲ Verify | `templates/github/aidd-diagnose.yml`. When the test workflow fails on a pull request, an agent with read-only tools reads the failed log and the base branch. It comments with what failed, the likely cause, and the next step. It never checks out the pull request, edits, re-runs, or suggests changing a frozen test. The log is data, never instructions. |
| Metrics and alerting | Learn, on a signal | Export a series for `aidd observe --band` (`templates/github/aidd-observe.yml`); a breach opens the triage issue with a draft Spec. |

## Notifications

aidd runs no server and no bot. To tell people in Slack or Microsoft Teams what waits on them, run a notifier in CI. The notifier only posts text to an incoming webhook, with no buttons. Every approval still happens on the pull request or merge request, where the gate reads it. A notification is never evidence or an approval.

**GitHub.** Copy `templates/github/aidd-notify.yml` into `.github/workflows/`. Add a repository secret `SLACK_WEBHOOK_URL` for a Slack incoming webhook, `TEAMS_WEBHOOK_URL`, or both. `TEAMS_WEBHOOK_URL` is a Teams Workflows webhook, "When a Teams webhook request is received". The Office 365 connector webhooks were retired in 2026. With neither set it posts nothing. It sends three messages:

| Message | When | What it says |
| --- | --- | --- |
| status | `aidd/gate` changes on a pull request | one line, such as `SPEC-9 waits for Spec approval: @alice, @org/leads -> <pull request>`, or that it is red or passed. A status the gate App posts triggers it through the `status` event. A status posted with `GITHUB_TOKEN` triggers no workflow, so the aidd-gate run that posted it stands in. A status is announced once, and only when it differs from the one before. |
| digest | weekday mornings | what waits on each Approver, grouped by Approver. It lists the steps of `aidd list --branch --json` on every open pull request's head, where a Spec waiting for approval lives. It adds `aidd list --json` on the default branch. `aidd list --waiting-on-me` is the same list for one person at their own terminal. |
| weekly | Monday | `aidd metrics` over the last seven days of gate events: the changes and their decisions, the first-pass test rate, and the approval waits. It also shows the major changes merge-approved within 10 minutes of the gate asking (`fast_major_merge_approvals`). That is a rubber-stamp signal to look at again. |

Every action is pinned by commit SHA, and each job asks for read permissions only. The webhook secrets reach only the job that posts, and that job runs no checkout. The digest reads pull request heads as data in a step with no token.

**GitLab.** A scheduled pipeline on the default branch does the same. Create two pipeline schedules with the variable `AIDD_NOTIFY`, set to `digest` on weekday mornings and to `weekly` on Mondays. Add `SLACK_WEBHOOK_URL` or `TEAMS_WEBHOOK_URL` as a masked, protected CI/CD variable. The jobs reuse the `.aidd` template from `.gitlab/aidd.gitlab-ci.yml`, which runs aidd from its pinned commit. This digest covers the Specs on the default branch. To include open merge requests, fetch each one's `refs/merge-requests/<iid>/head`. Then run `aidd list --branch --json` in it and read its `steps`, as the GitHub template does with pull requests.

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
      aidd list --json > list.json
      python3 - <<'PY' > notify.txt
      import json
      by = {}
      for s in json.load(open("list.json", encoding="utf-8"))["steps"]:
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

## Environments: local preview first

This page owns which environment a change is seen in before it reaches users. Climb only as far as the change needs. Use what the project already runs:

| Rung | When | What it proves | What it does not |
| --- | --- | --- | --- |
| 1. Local preview (default, no cost) | every user-facing change: `preview` starts the app with seed data on the verifier's machine ([CONFIG.md](CONFIG.md#preview)) | the head commit, built from a clean checkout, does what each Acceptance item says, with screenshots, a trace, and API transcripts under `.aidd/evidence/preview/<head-sha>/` | the real configuration, secrets, data volume, and network of production |
| 2. Hosted preview | only when the client must click through it themselves and already has hosting that makes one per branch | the same, on shared hosting a person outside the team can reach | the same as local: preview config, seed data, no real load |
| 3. Staging | when the project already runs one: a change to infrastructure, a migration, or an integration with a third party's sandbox | the deploy itself, the migration against realistic data, the integrations' configuration | production traffic, production data, and scale |
| 4. Production | every release, behind a flag or a canary where the project has one | the release, for real | nothing before it: it is proven after release |

Keep the inventory of the environments you do run as one table. Put it in the Deployment view of your architecture overview, `docs/architecture/README.md`, which `aidd new architecture` starts. Then an agent and a new teammate read where a change can be seen, and who may deploy it:

| Environment | Purpose | Data | Who deploys | URL |
| --- | --- | --- | --- | --- |
| local | the verifier's preview of each head | seed data | anyone, on their machine | `http://localhost:3000` |
| staging | the deploy, the migration, the third-party sandboxes | masked or synthetic, never production personal data | CI on merge | `https://staging.example.com` |
| production | users | real | CI, after a person approves the held deploy | `https://example.com` |

No preview proves the production configuration, the secrets, or the scale. Those are proven after release, by the Spec's `observe` window, which `aidd observe` runs, and the runbook its rollback names. The gate decides on exit codes at every rung. Screenshots and traces are for people. A hosted preview or a staging environment is never a requirement the method adds. Without one, rung 1 and the observe window cover the change.

## Deploy commands held for a person

The gate governs merges. A deploy is the other place a person must stay in the loop, and the only one during the build. Give agents autonomy per environment. They build, test, and deploy to staging on their own, and a production deploy waits for a person. Two layers do it:

1. **On the platform, the control.** Deploy production from CI only. Put the deploy behind a GitHub environment with required reviewers, or a GitLab protected environment with deployment approvals. Then no agent credential can deploy by itself.
2. **In the agent session, the guide.** Name the deploy commands in `.aidd/config.yaml`. The aidd hook then denies them to every agent until a person approves. `aidd init` already writes an entry for [each deploy command it finds](CONFIG.md#guard):

```yaml
guard:
  held_commands:
    - name: production deploy
      match: [deploy, production]
      environment: production
      requires: RELEASE_APPROVAL
      message: "Production deploys go through the release train: ask in #release."
```

With this, `make deploy ENV=production` is denied. The deny names the held command and what to do. The person who approves starts the session with the variable set, as in `RELEASE_APPROVAL=CHG-1234 claude`, or runs the command themselves. An agent cannot approve itself. The hook reads the environment Claude Code started with, never the agent's shell. And the hook denies a command that names the variable. Staging deploys match nothing and run. The fields are in [CONFIG.md](CONFIG.md#guard). The matching is best-effort parsing, which is why the platform layer stays the control.

The guard hook never prompts mid-build. It answers allow or deny, and each deny names what to do next. An approval prompt during the build would put a person back on the critical path of every session running in parallel. So humans decide at Spec approval, at Merge approval, and when they allow a held deploy command, never in between.

## Issue trackers

Jira, Linear, or GitHub Issues can mirror a Spec under its `id` and carry its `status`. The Spec file in the repository stays the approved source, and the gate reads only the repository.
