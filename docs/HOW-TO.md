# How do I…

Short answers for everyone on the team, engineer or not, each with the command and where the details are. When you are not sure what comes next, run `aidd list`. It reads the repository and tells you the next step for each open piece of work, and who holds it. On a branch, `aidd list --branch` says the same for the change in hand.

## Every day

**…know what to do next on this change?**
Run `aidd list --branch`. For each Spec this branch changes, it prints the next step, who takes it, and the command. That might be the agent, the author, an Approver, a triager, or a decision maker. Then it prints any other branch that changes the same code. `aidd gate` prints the change's route and why. `aidd list --branch --json` prints the same for scripts, and lists each Spec's Tasks under `tasks`, each `todo`, `in_progress`, `blocked`, `stopped`, or `done`. Every status comes from git, such as a counted Spec approval, commits in a Task's scope, the evidence, or the merge. You only record your decisions, as [METHOD.md §5.1](METHOD.md#51-status) explains.

**…see the whole backlog, not only my branch?**
Run `aidd list`. It shows one copy of every item, from the base branch and every open branch, and a branch's copy wins. Each item has its derived status, its status group, and why it matters: the mission, goal, Initiative, Epic with its progress, or hypothesis. The list also has the open proposals, and merged work drops out by itself. Narrow it with these flags:

- `--mine`: work you own, are assigned, or added
- `--agent` (or `--agent=verifier`): Tasks an agent may start now
- `--blocked`
- `--label area:billing`
- `--priority high`: that level or higher

It also suggests closing an Epic whose children are all finished. To limit work in progress, set `limits.max_in_progress_per_owner` to a number such as `2`. `aidd list` then warns when one person owns more Specs in progress. It's a warning, never a gate rule. Each Spec in progress also shows its age in days, such as `[age 12d]`, and it's marked as aging past `limits.max_in_progress_days`, which is 10 by default.

**…see what waits on me as an Approver?**
Run `aidd list --waiting-on-me`, your Approver inbox across every open branch. It lists the Spec approvals and Merge approvals you're eligible for. A Spec approval waits on a committed draft, on a route that needs one, and a Merge approval waits on a Spec that is green in review. The oldest come first, so you can escalate them. It warns when you hold more than `limits.max_open_per_approver`. A wait past `limits.escalate_after_minutes` is marked with the `owners.backup_approvers` to ask, as [METHOD.md §5.1](METHOD.md#51-status) describes. It never approves anything.

**…triage work an agent suggested?**
It shows up first in `aidd list` as a triage step. Record your decision in the Spec as `triage: {decision: "accepted", by: "@you", triaged_on: "2026-09-28"}`. The other decisions are `declined` and `snoozed`. A snoozed one takes an `until` date, and it stays out of `aidd list` until then.

**…track tech debt?**
Track it as suggested Specs with a label, never as a ledger file. A role that finds debt it shouldn't fix in the change in hand names it on its handoff note as `debt: ...`, or the reviewer names it as a `debt` finding. An agent in `agents.proactive_roles` writes a draft Spec with `suggested_by: agent:<role>` and `labels: ["debt"]`. You triage it like any other suggestion. `aidd list --label debt` is the debt list, and accepted debt is worked like any Spec.

**…say one Spec waits for another?**
Add `relations: [{type: "blocked_by", id: "SPEC-12"}]` to its front matter. `aidd list` then shows it blocked until SPEC-12 lands or ends, and `aidd validate` refuses a cycle or a target that doesn't exist.

**…see a Spec's history?**
Run `aidd log specs/SPEC-12.md`, or `aidd log SPEC-12` for short. It shows:

- the derived status now
- each stored status, with the time it held
- the approvals recorded on this machine or in a gate record
- the agents named in the `Assisted-by:` trailers of the commits touching its scope

`--json` for scripts.

**…build a feature?**
Tell your agent what you want. A change's route is a property of the change. aidd computes the minimum from what it touches, the author may declare higher, and the gate enforces the higher of the two. The lane follows from the route, and the agent asks the gate for it with `aidd gate --paths` before the first edit. You choose which change to work on, and `aidd list` shows the open work and who holds each step. On the fast lane, the agent builds straight away. When the change needs a Spec, the agent writes the Spec and its tests, then stops for your Spec approval. With the delivery team:

1. `/aidd-team:specify`
2. `/aidd-team:implement`, once the Spec is approved
3. `/aidd-team:verify`, on the head it built
4. `/aidd-team:review`

[Quickstart](QUICKSTART.md) walks through it all.

**…fix a small bug quickly?**
Tell your agent. A small, reversible fix goes on the fast lane, so it needs no Spec file and only one approval. It needs no Change Request block either, because the gate takes the route from the diff. Add one, which `aidd describe` prints, only to raise the route or declare a risk the paths don't show.

**…get test feedback while I work?**
`aidd test --changed` runs only the commands your working tree's changes select, green only. These are a matching `when_changed`, a Spec's command when you touched its Task scope or tests, and the suite. `aidd test --watch` re-runs that whenever you save, until Ctrl-C. Both write evidence marked partial, which the gate never accepts. So run a full `aidd test`, or let `aidd-tests` run, before you ask for review.

**…take a pull request to green?**
Run `/aidd-team:sweep`. It answers every review comment and fixes failing checks inside the scope, then stops when only your Merge approval is left.

**…release behind a feature flag?**
When users should get a change later than its code reaches production, the architect adds a `flags` entry to the Spec. The entry has the flag's name, `default: "off"`, a person as `owner`, and a `cleanup_due` date, as the [spec fields](../.agents/skills/aidd/references/spec.md#feature-flags-flags) describe. The verifier covers both states. The code checks the flag once per decision point through the OpenFeature API. The owner flips it in production, and an agent never does, so hold the flip command in [`guard.held_commands`](CONFIG.md#guard). Remove the flag in a later Spec that lists it in `removes_flags`, which counts once that Spec lands. Past its date, `aidd validate` warns and `aidd list` shows the cleanup. The Feature flags section of `aidd-team:release-rollout` has the practice, and the provider to pick for your budget.

**…deprecate an endpoint, a field, or an event?**
The architect adds a `deprecations` entry to the Spec. It has the `what`, the `announced` and `sunset` dates, the `replacement`, and the known `consumers`, as the [spec fields](../.agents/skills/aidd/references/spec.md#deprecations-deprecations) describe. The running API sends the same dates in the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers. Remove it in a later Spec that lists it in `removes_deprecations`, which counts once that Spec lands. Past its sunset, `aidd validate` warns, `aidd list` shows the removal, and `aidd digest` lists it as overdue. `aidd digest --client` shows your consumers the calendar of landed deprecations. The `aidd-team:api-design` skill has the practice.

**…sell a product in the EU under the Cyber Resilience Act?**
Add `cra` to `project.compliance.targets`, and declare `support_period: {ends: "YYYY-MM"}`, the last month of security updates. `aidd validate` fails without it. Run `aidd new vulnerability-policy` for the policy: intake, triage, fix times, advisories and VEX, the weekly rescan, and the reporting clocks. Serve `security.txt` with `Contact` and `Expires`, and `aidd doctor` warns before it expires.

**…run an A/B test?**
Give the Spec a `hypothesis` and an `experiment` block before Spec approval. The block has the `variants`, one primary `metric`, the `guardrails`, a `min_sample` or a `duration`, and the `decision` rule, as the [spec fields](../.agents/skills/aidd/references/spec.md#experiment-experiment) describe. A `flags` entry with `purpose` experiment serves the variants, and the tracking plan names the exposure event. `aidd validate` warns about an experiment with no guardrail or no hypothesis. Check the sample ratio daily. Stop early only on a guardrail breach or a mismatch. Record the number in `outcome.result`. The Experiments section of `aidd-team:release-rollout` has the practice.

**…preview and verify a change locally?**
Set [`preview`](CONFIG.md#preview) in `.aidd/config.yaml` to the one command that starts the app with seed data. `/aidd-team:verify` then starts it from a clean checkout of the head commit, and exercises each Acceptance item. It saves screenshots, a trace, and API transcripts under `.aidd/evidence/preview/<head-sha>/`, and names them in its report. Open them before you approve the merge, though the gate still decides on the test exit codes. [Platforms](PLATFORMS.md#environments-local-preview-first) says when a hosted preview or staging is worth it.

## Many agents at once

**…keep my own worktree while the team builds in theirs?**
Open a worktree for the change, such as `work/booking`, start Claude Code in it, and say what you want, for example `/aidd-team:autopilot build online booking`. That worktree is yours, where the plan, the Spec, and the finished change land.
1. The team plans and specifies in your worktree, and stops for your go and your Spec approval.
2. Each Task builds in a worktree of its own, beside yours. When a Task is green, it merges back into your worktree, and the tests run again. Your worktree never holds half-done work.
3. When every Task is in, your worktree holds the whole change, tested. Try it there. Run the app, or let the verifier start it with `preview`.
4. Then land it. Say `land it`, or run `aidd land`, and the tests run once more before the change lands on `main`. When you want it on GitHub, say `publish`, and aidd pushes the branch and opens its pull request. Once `aidd/gate` passes there, `merge it` merges it. On GitLab, `publish` opens the merge request, and you approve it there.

**…choose between a worktree and a branch?**
- Use one worktree for each change you run at the same time as another, each on one short branch such as `spec/<ID>` or `fix/<topic>`. One change at a time needs only a branch.
- Keep the main checkout on `main`, for reading and for `aidd list`. A change never builds there.
- Inside a change, the team may give parallel Tasks worktrees of their own and merge them back. You never open or clean those, because `aidd worktrees clean` removes the merged ones.
- Use a goal branch, `goal/<EPIC>`, only for a small goal that is batched. An experiment goes in its own worktree, on a `explore/` branch.

<a id="work-trunk-based"></a>
**…keep branches short and the default branch the one trunk?**
Each one works this way, as [METHOD.md §10.4](METHOD.md#104-trunk-based-flow) sets out:

| Who | Works this way |
| --- | --- |
| The person | Decides fast: the inbox (`aidd list --waiting-on-me`) holds only the four decisions ([METHOD.md §10.3](METHOD.md#103-goals-big-small-and-how-each-reaches-users)). Reviews small diffs the day they arrive. A slow review is what makes batches grow. A standing approval hands over Spec approvals and releases, never the plan or a launch |
| The lead (autopilot, or the session that runs the team) | Starts new work only while the open branches stay within `limits.max_open_branches` (3 while unset) and the Approvers' queue within `limits.max_open_per_approver`. Lands or integrates each Spec as soon as it is verified and reviewed, and runs `aidd sync` on the open branches after each landing |
| Each role | Works on a Task branch cut from its Spec's branch, for hours. Each green step is a commit with its `Assisted-by` trailer, run through `aidd test` first. A Task merges back into the Spec's branch when its tests pass, and never rebases a shared branch. Unfinished user-facing work merges behind the Spec's flag rather than waiting on a branch |
| A Spec branch | Lands on the default branch (or integrates into its goal) within `limits.max_branch_age_days` (2 while unset) of its first commit; past it, `aidd list` and `aidd doctor` warn. It takes the default branch in daily with `aidd sync`. A Spec that needs another's contract stacks on that Spec's branch, and lands after it, in order, through the merge queue |
| A goal branch | The one exception to short branches, for a slice that must land at once: a week at most (`limits.max_goal_age_days`), kept current with `aidd sync` |

**…know which shape my work is?**
The product manager plans an ask into a big goal, an Initiative, made of small goals, its Epics. You agree to that plan. Each small goal says how it reaches users:
- `incremental`, the default: each piece is useful by itself, so each Spec merges to `main` when it's done.
- `flagged`: useful only when complete, but it can be hidden. Each Spec merges behind a flag that stays off, and a last launch Spec turns it on. The launch is always yours to approve.
- `batched`: it must land at once and cannot be hidden, such as renaming a public API with all its callers. It gets a goal branch.

<a id="goal-branches"></a>
**…build a small goal that is batched?**
- Once the plan is on `main`, `aidd goal open EPIC-3` cuts `goal/EPIC-3`. Each Spec gets its own branch from it, and `aidd new spec <ID> --parent EPIC-3` names the goal as its base.
- Autopilot specifies and builds independent Specs side by side when `autopilot.parallel` is set. Type `approve` once to approve every ready Spec that waits on you, or run `aidd approve spec SPEC-2 SPEC-3` at your terminal. No code is written for a Spec before its approval.
- Once a Spec is verified and reviewed, the team runs `aidd integrate` on its branch. It tests the merge with the goal and lands it there, with no question to you. A fast-lane fix cut from the goal integrates with `aidd integrate --goal goal/EPIC-3`, and `aidd integrate --undo SPEC-2` takes a Spec out again with one revert.
- When a sibling lands, `aidd sync` on a Spec's branch merges the goal in. On the goal branch, it merges in what moved on `main`. It never rebases. When another machine integrated, it first catches the goal up with its upstream, and it stops when the two went different ways.
- Only aidd moves the goal branch, so the guard denies an agent's merge, reset, or push there. A commit of plan files alone is allowed, such as dropping a Spec from the Epic's `specs` to release without it.
- When every planned Spec is integrated, `aidd list` says the goal is ready to release. Land it on `main` as one change. The gate judges each Spec as its own change again, and your one Merge approval lands them all. A goal older than `limits.max_goal_age_days`, 7 days while unset, gets a warning, so release what is integrated or split it.

Changes with no goal in common take one worktree each, each from `main`.

**…start one agent per Task?**
Once the Spec is approved, `aidd list --branch --json` lists its Tasks under `steps`, with their `scope`, `depends_on`, and a `status`. The status is `todo`, `in_progress`, `blocked`, `stopped`, or `done`, and [ORCA.md](ORCA.md#one-agent-per-task) says what each means. Start one agent for each `todo` Task, each in its own worktree branched from the Spec's branch, such as `git worktree add ../SPEC-9-T1 -b SPEC-9-T1 feat/spec-9`. Todo Tasks never share files, because Tasks whose scopes overlap must depend on one another. When a Task's branch is merged into the Spec's branch, start the Tasks that waited for it, listed in `waiting_on`.

**…let two or three agents try a hard Task, and keep the best?**
Give the same Task to 2 or 3 agents, each in its own worktree, all against the same frozen tests. Then results pick the winner, not taste.

```bash
git worktree add ../t1-a -b t1-a feat/spec-9      # one worktree and branch per attempt
git worktree add ../t1-b -b t1-b feat/spec-9
# start one agent in each, with the same prompt; when they are done, in each worktree:
aidd test --spec specs/SPEC-9.md                  # the frozen tests, green on head
aidd gate --spec specs/SPEC-9.md                  # every rule; only approvals may still be pending (exit 3)
git diff --stat feat/spec-9...HEAD                # how big the change is
```

1. Drop every attempt whose tests fail or whose gate fails for anything but a pending approval. An attempt that changed a frozen test voids the Spec approval, so its gate fails.
2. Of the rest, keep the smallest diff. When two are close, a reviewer reads both and picks one.
3. Delete the others with `git worktree remove ../t1-b && git branch -D t1-b`.
4. Only the winner opens a pull request and goes to Merge approval.

**…know which worktree holds what, and clean up the old ones?**
`aidd worktrees` lists every worktree with its work item, which it reads from the branch name, such as `spec/SPEC-3`. It also shows each one's state: `active`, `new`, `merged`, `stale` after 14 days with no commit, `uncommitted work`, or `missing` when its folder is gone. It reads them from git each time, so nothing can drift. After your yes, `aidd worktrees clean` removes the missing ones and the merged ones with nothing uncommitted. It never removes the main worktree, the one you're in, uncommitted work, or a branch. A coding agent lists its saved sessions by the folder they started in, so a removed worktree's sessions stop showing when you resume. They stay on disk, and `git worktree add` at the same path shows them again. An agent may run `aidd worktrees clean --dry-run` and show you the list, but you run the real one. `aidd doctor` and the session start say when some can go.

**…share one dev stack between worktrees?**
Start one stack per machine and give each worktree its own namespace in it, never a second Postgres for the same project. Name the commands in `project.dev_services`:

```yaml
project:
  dev_services:
    up: [docker, compose, -p, shop, up, -d]       # the shared stack, once per machine
    down: [docker, compose, -p, shop, down]
    teardown: [./scripts/drop-worktree-db.sh]      # removes one worktree's database, bucket, and tracing project
```

`aidd test` gives your test commands `AIDD_WORKTREE`, a stable name per worktree such as `shop_3f9a1c`. Name the database, the bucket, the Langfuse project, and the ports each worktree uses by it. `aidd worktrees clean` runs `teardown` with it for each worktree it removes. The session start tells each agent the stack is shared and names its worktree, so no agent starts another.

**…run aidd inside Orca?**
It works as it is. Orca's worktrees are git worktrees, local approvals are shared between them, and the guard runs for the agents Orca starts. aidd also shows its next step on the Orca workspace card. [Running aidd inside Orca](ORCA.md) covers the setup, the card, parallel Tasks, and what to watch out for.

**…run aidd under Paperclip?**
[Paperclip](https://github.com/paperclipai/paperclip) is an optional host that organizes agents like a company, with tasks, budgets, and approvals of its own. aidd works under it the way it works under any host. The agents do the work in the repository, and aidd decides what may merge.

- **Its approvals and its "done" are display only.** Neither is a Spec approval, a Merge approval, or evidence, and the gate reads neither. A person still approves on the PR/MR, or with `aidd approve` at their own terminal.
- **Each agent still follows the loop.** It asks the gate for the route with `aidd gate --paths`, runs `aidd test`, and stops for a person at Spec approval and Merge approval. `aidd list --branch --json` lists a Spec's `todo` Tasks, one per agent.
- **Check that your Paperclip adapter runs the repository's own hooks.** aidd's guard works only where the agent's harness loads the hooks `aidd init` wired, such as `.claude/` for Claude Code. Start an agent through the adapter in the repository and run `aidd doctor` there. Without the hooks, nothing stops an agent's edit early, but the gate still decides every merge.

**…run agents in a sandbox?**
aidd does not sandbox anything. The guard and the gate stop approving, merging, and out-of-scope edits. They do not stop a command that reads your credentials or sends data out. For a real boundary, run the agent in a container. `aidd init --devcontainer` gives you a starting point, and so does copying `templates/devcontainer/` to `.devcontainer/`:

- **The firewall** denies outbound traffic except HTTPS and SSH to an allow-list: the code platform, the model API host, and the package registries. The list is set as build arguments in `devcontainer.json` and baked into the image, so nothing inside the container can widen it.
- **The agent** runs as a non-root user.
- **To adapt it,** change the hosts to your mirror and your model API, then rebuild. `.devcontainer/**` is a protected path, so a change to the allow-list is a major change.
- **Its limit.** It reduces what a misled agent can reach. But DNS and the allowed hosts can still carry data out, so keep secrets out of the container.

Your own `PreToolUse` rules can sit beside aidd's guard as well, as [examples/hooks](../examples/hooks/README.md) shows.

## Without GitHub or GitLab

**…work entirely on my own machine?**
Set up the solo profile with the email your commits use and no CI. `/aidd init` does it, and so does [Local-first](ADOPTION.md#local-first-no-github-or-gitlab). Then type your decisions at the prompt: `approve SPEC-1`, `approve merge`, `land it`, and `publish` when the work should leave your machine. aidd records your own words, as [Your words decide](ADOPTION.md#your-words-decide) explains. The terminal commands `aidd approve spec`, `aidd approve merge`, and `aidd land` do the same at a terminal you opened yourself.

**…let the agents approve and land for me?**
Type `approve all`, or `approve all but major` to keep the risky changes for yourself. The agents then record each approval and land the work, until you type `stop approving`. Nothing leaves your machine unless you type `approve all and publish`, which lets them publish too. [Hands-off](ADOPTION.md#hands-off-approve-all) has the details. An agent never starts it for you, and never edits the config so that nothing needs approval.

**…run several agents in parallel?**
Give each Task or agent its own git worktree, such as `git worktree add ../task-2 -b task-2`. Each keeps its own files and evidence, while the approvals are shared. [Many agents at once](#many-agents-at-once) has more.

## Approving

**…approve when I already said yes to the agent?**
Say it in aidd's words: `approve SPEC-1`, `approve merge`, `land it`, `publish`, or `merge it`, and aidd records them before the agent reads them. A yes in other words isn't an approval. So the agent calls the matching aidd MCP tool, and you click once in its dialog. [Your words decide](ADOPTION.md#your-words-decide) explains why.

**…approve a Spec?**
Read the Spec and its tests, especially the Intent, the Acceptance, the scope, and the rollback. If they're right, type `approve <ID>` at your coding agent's prompt, and aidd posts `/aidd approve-spec <ID> <commit>` on the pull request as you. You can also post that line yourself. Changing the Spec or its tests afterwards voids it. [Quickstart, With a team](QUICKSTART.md#with-a-team) has a worked example.

- **You need no CLI.** The line names the Spec and the commit you read, which is the pull request's head.
- **On a phone,** `aidd approve spec <ID> --show` prints what you approve on one screen. It shows the intent, each Acceptance item, the scope, the risk, the rollback, and the frozen test files.
- **Without a platform,** run `aidd approve spec specs/<ID>.md` instead.

**…see the tests fail before I approve the Spec?**
Open the pull request with the Spec and its tests only, before any implementation. `aidd-tests` runs them red against the base. It also runs them green on the head, where they fail too, as they should before the code exists. The gate's summary says **Red on base: yes** under "Merge approval summary". Locally, `aidd test` on that commit shows the same red results. While the branch holds only the Spec and its tests, the gate's `tests` rule is pending rather than failed, with the finding `tests.spec_phase`. The failing tests are early proof, and the gate waits for Spec approval and the implementation.

**…approve a merge?**
Read the gate's report by opening the Details link of the `aidd/gate` check on the pull request. It shows the run summary, where each finding's code links to its row in [ERRORS.md](ERRORS.md), at the aidd commit the workflow pins. Its "Merge approval summary" puts each Acceptance item beside its result and the test that `covers` it. It also shows the review report's Critical and High findings, the residual risk, and what changed since the last approval. Then approve the head commit with a platform review. Under the solo profile, post `/aidd approve-merge <full head SHA>`. Without a platform, run `aidd approve merge`. A new push needs a new approval.

**…read a change on one page?**
Each approval has a page, one self-contained HTML file you open in any browser, offline. It is rendered from the Spec, the evidence, and the diff, so it says only what they say. It never approves. Its buttons copy a line, and you still post or run it yourself.

- **Before Spec approval,** an agent runs `aidd hash specs/<ID>.md --summary --html` for you. It writes `.aidd/views/spec-<ID>.html`, or the path you give with `--out PATH`. The page shows:
  - the intent, and each Acceptance item beside the test commands that cover it
  - the route and why, and the risk and rollback
  - each frozen test file and doc
  - the diagrams (Mermaid shows as its source)
  - what changed in the frozen files since the last approval
  - the approval line to copy
- **Before Merge approval,** `aidd gate --html` writes `.aidd/views/merge-<head>.html`, or the PATH you give. The page shows:
  - the decision and each finding with its fix, grouped by level
  - Acceptance against the evidence
  - the review report's findings by severity, from the pull request or from `.aidd/evidence/review.md`
  - the verification: the test results, red and green, and the screenshots and traces the verifier recorded for this head (`.aidd/evidence/preview/<head>/artifacts.json`)
  - the scope and the changed lines
  - the diff, file by file

  In CI, the gate job keeps it as `aidd-merge.html` beside the gate record.

A screenshot shows on the page only when its SHA-256 matches the one `artifacts.json` records. The folders in `.aidd/` are ignored by version control, so the pages never land in the repository.

**…get notified when something waits on me?**
Copy `templates/github/aidd-notify.yml` into `.github/workflows/`. Add a `SLACK_WEBHOOK_URL` or `TEAMS_WEBHOOK_URL` secret. It posts three things:

- one line when `aidd/gate` changes on a pull request ("SPEC-9 waits for Spec approval: @alice -> link")
- a weekday digest of what waits on each approver
- a weekly `aidd metrics` summary that names major changes approved suspiciously fast

It only posts text, so you still approve on the pull request. On GitLab, a scheduled pipeline does the same, as [Platforms](PLATFORMS.md#notifications) shows.

**…change a Spec I already approved?**
`aidd revise SPEC-12 "the limit is per card, not per user"` reopens it, on the Spec's own branch. It records what was wrong in the Spec's `revisions`, with the hash you approved, and commits that alone. The hash changes, so your approval no longer holds. The verifier, the designer, and each document's owner change their frozen files again, and then you approve it again. The card shows why it was reopened and what changed since your last approval. A landed Spec is never reopened, so a new Spec changes what it landed.

**…give my project's agents a guide (AGENTS.md)?**
The team writes it, as it writes the architecture overview and the design system. `/aidd-team:onboard` drafts it from the repository, and `aidd new agents` writes the template above aidd's own section of AGENTS.md: what the project is, how it builds and tests, its layout, its conventions, and its rules. The architect owns it, and it's living, so a change that makes a line untrue updates it in the same change. A lesson from a retro or an incident comes back as a change to it. AGENTS.md steers every agent, so each change to it is major, and you agree to it.

**…give the agents the tools that fit my project?**
`aidd extensions suggest` lists the plugins from aidd's registry that fit this repository's stacks, for the roles that use them: a language server for each language, `claude-security`, and Anthropic's knowledge-work plugins. Each comes with its tier, what it can touch, its pin, and the `claude plugin install …` line that installs it. aidd installs none of them, so read each at its pin, then install it yourself. `--role developer` keeps one role's, as [Team](TEAM.md#extensions-per-role) explains.

**…let an agent's routine work merge without me?**
`aidd metrics --autonomy` shows which agents have a clean record on which kind of work. When one earns it, add that class of change to `standard_changes`, through the gate like any config change. [Adoption](ADOPTION.md#multiplayer-one-team-humans-and-agents) shows how.

**…make a production deploy wait for a person?**
`aidd init` already holds the deploy commands it finds in `guard.held_commands`, such as deploy scripts, Makefile deploy targets, and `terraform apply`. `aidd doctor` lists them. To drop one, delete its entry from `.aidd/config.yaml`, and name any other deploy command there yourself. Keep the platform's own environment protection too, as [Platforms](PLATFORMS.md#deploy-commands-held-for-a-person) explains.

## When something breaks

**…handle a production incident?**
Restore service first. The emergency lane lets a fix merge on the incident commander's say, with the full review due within the deadline in `emergency`. Then `/aidd-team:postmortem` writes the postmortem and the backfill Spec. [The method §6](METHOD.md#6-routes) has the rules.

**…watch a release through its observe window?**
`aidd observe specs/<ID>.md --window` runs the Spec's observe command every 5 minutes until its `window` ends, and `--every` changes how often. It stops the moment the rollback trigger fires, after `--consecutive` unhealthy checks in a row. It exits 0 when the window ended clean, 1 when the trigger fired, and 2 on an error. It never rolls back, because that's your release tooling's job, or yours. `--write` records the result in the Spec.

**…use a merge queue?**
On GitHub, turn it on in the branch ruleset, and the gate judges each queue entry on its merge-group commit. [Platforms](PLATFORMS.md#merge-queues) has the setup. On GitLab, merge trains are experimental, and the gate judges each entry on its train commit ([Merge trains](PLATFORMS.md#merge-trains)).

**…catch a problem before users report it?**
`aidd observe --band METRIC SERIES` judges a metric against its recent baseline. With `--write`, it writes a draft Spec when the metric breaches. Run it from any scheduler, such as cron, with a series exported from whatever records the metric. On GitHub, `templates/github/aidd-observe.yml` runs it on a schedule. `templates/github/aidd-diagnose.yml` diagnoses a failed test run on a pull request.

**…write a runbook, and keep it working?**
`aidd new runbook RB-1 --title "Restore the orders database"` writes one in `docs/runbooks/`. After you follow it for real, and a drill counts, set its `tested_on` date. `aidd doctor` warns when an active runbook was never tested, or is older than `docs.max_runbook_age_days`, 180 by default. A living doc, such as the glossary or an SLO, may record the day you last reviewed it as `reviewed_on: YYYY-MM-DD` in `---` front matter. `aidd doctor` then warns once it's older than `docs.max_review_age_days`, also 180. For an incident, `aidd new postmortem PM-1 --title "Checkout outage" --spec SPEC-12` writes the postmortem and links the Spec that fixes it.

## Before the work

**…propose a change to leadership, or bid for a client?**
`aidd new proposal PROP-1 --title "Move checkout to the new payment provider" --audience internal --addressee "the executive committee"` (or `--audience client --addressee "Acme Corp"`), then `/aidd-team:propose`. You decide go or no-go before the team drafts, and you sign it off before it's sent. `aidd proposal matrix` prints the tables for the document. [Adoption](ADOPTION.md#proposals-bids-and-internal-cases).

**…turn an accepted proposal into work?**
`aidd proposal convert proposals/PROP-1/proposal.md` writes the Initiative and Epics. `/aidd-team:plan` ranks them and writes the Spec stubs.

**…bring in a plan from Spec Kit, OpenSpec, Kiro, or BMAD?**
`aidd import speckit specs/001-photo-albums` (or `openspec openspec/changes/<change>`, `kiro .kiro/specs/<feature>`, `bmad <story file>`) writes a short Spec:

- It quotes the plan's problem.
- It turns the plan's acceptance scenarios or EARS requirements into Acceptance items (`A1`, `A2`, ...).
- It takes each Task's scope from the paths the plan names.
- It computes the route.
- It links the plan instead of copying it.

It leaves the tests to you:

1. Name them.
2. Write them.
3. Run `aidd validate`.

[Adoption](ADOPTION.md#coming-from-spec-kit-openspec-kiro-or-bmad).

**…write a tech spec, test plan, prototype, ADR, or threat model for a Spec?**
`aidd new tech-spec rate-limits --spec SPEC-12` writes the file from its template under `docs/` (an ADR as `docs/adr/NNNN-<topic>.md`). It names the Spec in the file's header, and adds a `docs` entry to the Spec. Instead of `tech-spec`, you can name another kind:

- `test-plan`, `adr`, `threat-model`
- `authz` for the authorization matrix
- `design-spec` for the design spec (`--prototype` for its HTML prototype, `specs/<ID>/design/prototype.html`)
- `api`, `slo`, `compliance`
- `analytics` for a tracking plan
- `migration`, `acceptance`

`--area checkout` groups an area's docs. The Spec stays the short contract, and the doc holds the detail. Spec approval freezes the doc with the Spec, so fill it in before you ask for approval. A threat model is the exception: it belongs to a component (`aidd new threat-model checkout --spec SPEC-12` writes `docs/security/threat-models/checkout.md`, or links it again when it exists), it stays living, and the Spec freezes only its delta. A runbook or an SLO that stays current after the merge is linked with `frozen: false` (`aidd new runbook RB-3 --title "..." --spec SPEC-12` does it). Nothing is required on a small change. `aidd validate` only warns in these cases ([METHOD.md §4.2](METHOD.md#42-spec)):

- on a major Spec without a tech spec or runbook
- on a security, privacy, or data risk without a threat model
- when a trigger asks for a test plan, a migration plan, or a tracking plan

Testing lives in the Spec's Acceptance and the tech spec's Test strategy. The separate test plan is for a regulator, a QA owner, a device matrix, or a client's UAT.

**…test access control with a matrix?**
Test access control with a matrix: `aidd new authz "Admin API" --spec SPEC-12` writes one row per subject, action, and resource or endpoint. Each row has its row-level condition, the expected allow or deny, and the test id. The matrix also has rows that a caller from another tenant is denied, and the short list of public endpoints. Everything else requires authentication. The security engineer fills it in Specify from the threat model's Elevation of privilege rows. The verifier writes one test per row, red on base where the check is missing. It is frozen with the Spec. `aidd validate` asks for one when the risk names security and a Task touches an auth path.

**…handle personal data by default?**
Let the route find it. A change matches `baseline:personal-data` when it has one of these:

- a change to a user, customer, account, member, patient, or contact model or folder
- a file named for personal data (`pii`, `consent`, `gdpr`, `privacy`)
- an added auth library

Then `aidd gate --paths` names the privacy dimension, the route is major, and the privacy pool reviews. Bind the pool in `owners.specialists`. Security stands in until you do. The compliance analyst starts. `aidd validate` warns until the Spec links a compliance doc with its DPIA (`aidd new compliance <topic> --spec <ID>`). It suggests the data map too. The data map is the repository's own: `aidd new data-map` writes `docs/data-map.md` once. Each Spec that touches personal data revises it, and links it as a living doc. The data map is the inventory and the records of processing (GDPR Art. 30) in one file. Name `aidd-team:privacy-by-default` in the Spec's Context. Its checklist covers the lawful basis per purpose, retention and deletion jobs, and the data-subject rights endpoints. It also covers consent, the privacy notice, processors, transfers, breach handling, and masked test data. Its tests go in `tests.commands`: an erase request clears every mapped store, and an export returns every mapped field. A docs page or a test fixture under `users/` stays out of the rule. To exclude more, use `rule_exclusions` ([CONFIG.md](CONFIG.md)).

**…know which design artifact I need?**
Start from the prototype. Add only what the change needs. A solo founder writes the prototype and the design spec's light variant, and stops there. Draw the rough directions in the prototype's wireframe mode (`?mode=wireframe`). Then build the picked one at full fidelity in the same file. A prototype is interactive, and it is ours. A mockup is a static picture (an export from another tool, kept in `design.files`). Wireframe is a mode of the prototype, not a file. Each artifact has one home, so there is nothing else to create.

| Artifact | When | Who | Frozen or living |
| --- | --- | --- | --- |
| Prototype (`aidd new design-spec --prototype`) | any user-facing Spec: every screen of the flow in one file; wireframe mode for the rough directions | product designer | frozen |
| Design spec (`aidd new design-spec`) | a user-facing feat: screens by states by targets; the light variant for a small change | product designer | frozen |
| User flows: the design spec's `## Flows` | a feat with new screens or more than one journey: the sitemap and one diagram per journey | product designer | frozen |
| Component: a row and subsection in `DESIGN.md`'s Components | a component is new or changes, as its own design-system change | product designer | living |
| Journey: the Initiative's `## Brief`, `### Journey` | discovery, before the solution | product manager | living |
| Usability test: the design spec's `## Usability test` | before launch, a risky flow needs evidence from real users; after launch, the feedback log | product designer | frozen |

**…keep one design system and one architecture overview?**
`aidd new design-system` writes three files:

- `DESIGN.md` at the repository root (Google Labs' design.md format: a token front matter, then prose)
- `design/tokens.json`, the one source, in the Design Tokens Format Module 2025.10
- `design/build.mjs`, which writes the CSS, one preset per theme, and `DESIGN.md`'s token mirror. Its `--check` is the drift test.

`aidd new architecture` writes `docs/architecture/README.md`, with a C4 container diagram and a place for fitness functions. There is one of each per repository, never one per Spec. A prototype or a design spec uses the design system where it is. A token the design system lacks is proposed as its own change, which `baseline:design-system` routes normal. `aidd validate` warns when a Spec's design files carry their own tokens file beside `design/tokens.json`. The overview is living. A tech spec starts from it and draws only what changes. After Roll out, the approved design is folded back in as a docs change. On `/aidd-team:mvp`, the product designer and the architect write both on Day 0. `/aidd-team:onboard` drafts both from an existing product for a person to accept. [Glossary](GLOSSARY.md).

`aidd new glossary` writes `docs/GLOSSARY.md`, which holds the project's terms, one meaning each, with the words to avoid. It's living too. Clarify adds a term once the author settles it, and `/aidd-team:onboard` drafts the first version. Its Avoid column holds only the words, separated by commas, so `aidd validate` can warn when a Spec's Goals, Acceptance, or Design uses one.

**…pitch an MVP or an Initiative on one page?**
`aidd new initiative INIT-1 --title "Pet sitter MVP"` writes the Initiative. Its `## Brief` is the one-page pitch: the problem, the appetite, a solution sketch, the rabbit holes, the no-gos, and the success metric. The brief also has a `### Journey` for discovery. A solo founder writes the Initiative's brief, a short Spec, and the prototype. The founder writes nothing else until a trigger asks, as Ceremony by team size in [METHOD.md §4.2](METHOD.md#42-spec) explains.

**…handle a client's change of scope, or record their acceptance?**
Once the contract exists, `aidd new contract PROP-7` writes the next change order, `proposals/PROP-7/change-orders/CO-1.md`. It holds the scope, price, and time delta, and the affected Acceptance ids. The client decision is left for humans to fill. The Spec then changes to match, and goes back through Spec approval. aidd's Change Request is the block in a PR/MR that points at the Spec, so it is not an agency change order. After the release, `aidd new acceptance "Release 3" --spec SPEC-12` records which Acceptance ids the client accepted, when, by whom, and on what evidence. Both are living docs, with `frozen: false`. Set `uat: true` in the Spec when the client accepts by hand.

**…plan something bigger than one change?**
Run `/aidd-team:plan`. It writes an Initiative, Epics, and ranked Spec stubs, and you agree to them before any Spec is filled in.

**…tidy a backlog that has grown?**
Run `/aidd-team:refine` when there are more than about 20 open items, or before planning. `refine EPIC-3` or `refine label:billing` narrows it. The product manager and the delivery manager propose a new order, splits, duplicates, finished Epics to close, and triage for suggestions. You accept or reject each line in one table. The roles prepare only the lines you accept, on a branch, and you commit them.

## Explore, get feedback, iterate — fast

**…try two or three directions before committing to one?**
Run `/aidd-team:explore "how should a customer split a bill?"`. For a UI question the product designer takes it, and for an architecture one the architect does. That role writes `exploration.md` with `aidd new exploration specs/SPEC-12/explore/split-bill --title "..." --timebox "45 minutes"`. Then it draws two or three directions that differ in approach, in the prototype's `?mode=wireframe` or in Mermaid. It writes the trade-offs under each, and stops when the timebox runs out. `aidd explore specs/SPEC-12/explore/split-bill` renders one comparison page in `.aidd/views/`. The page shows the directions side by side on a wide screen and stacked on a phone, and a choice to copy. You pick and say why. The owning role records the pick in the Spec's Design section, `DESIGN.md`'s Decisions, or an ADR. The page loads nothing, records nothing, and approves nothing, because its buttons only copy text.

**…prototype a whole flow, and link to one screen of it?**
`aidd new design-spec checkout --spec SPEC-12 --prototype` writes `specs/SPEC-12/design/prototype.html`. It is one self-contained file with:

- every screen of the flow, each a `<section data-screen="<id>">`
- a screen menu, as a sidebar beside a wide frame and a drawer on a phone
- buttons that move between screens with `data-go`, and a working back button
- the same screens in web frames from 320 to 1440, with header navigation
- the same screens in iOS and Android frames, with a tab bar and a back affordance

Its address is a deep link, `#<screen>/<state>?theme=dark&frame=ios&mode=wireframe&round=2`, each key optional. Open one, and you see that screen, state, theme, frame, and fidelity. Every switch updates it, so a link in a review comment or a test opens exactly what it names. A second flow of the same Spec gets its own folder in the Spec's design folder, so `--area checkout` writes `specs/SPEC-12/design/checkout/prototype.html`. A product with many flows keeps one prototype per flow or Spec. It also keeps a short `docs/design/index.md` that lists each prototype with its path and the screens it holds.

**…give feedback on a prototype?**
1. Open the prototype with `?round=1`.
2. Press Feedback mode.
3. Click an element, or pick its test id.
4. Type a note.
5. Add it.
6. Press Copy feedback.

You get `{"round": 1, "items": [{"id": "r1-1", "screen": "checkout", "state": "error", "testid": "...", "note": "...", "link": "#checkout/error?theme=dark"}]}`. Each note has the screen, state, frame, and theme it was given on. Save it as `specs/SPEC-12/explore/split-bill/feedback-round-1.json`, or paste it to the agent. Copy as a prompt adds the instructions for you. The notes stay in the browser tab and are never sent anywhere.

**…see what changed between rounds?**
Each round's screenshots go in `rounds/<N>/` as `<screen>-<state>-<target>-<theme>.png`, by the prototype's screen ids. A `changes.json` names the feedback ids each change answers. `aidd explore` shows each screen beside the round before, and marks it changed, unchanged, new, or gone. It lists the feedback given on that screen and state beside it. It also lists the feedback no change answered yet. Before each round, the designer runs axe and contrast in both themes and the 320 to 1440 frames. `aidd validate` warns when a round has no dark screenshot while `dark_mode` is on, or when a design folder holds lorem ipsum.

**…ask a person to decide between options?**
Write a decision card, which is an exploration with no visuals, in the folder of the work item it decides for. `aidd new exploration specs/SPEC-12/explore/refund-limit --title "..."` starts one. Its directions are the options with their trade-offs, and it has a recommendation. Name its path on the handoff note's Needs line, and `aidd explore` renders it as one page. You decide, and the card only lays it out.

## Run a client engagement end to end

One engagement, from the first call to the first month of support, in the files aidd already has. The delivery manager keeps the paperwork, and the product manager triages what comes in after go-live. A person makes every decision and sets every price.

1. **Qualify.** `/aidd-team:propose <the request>` starts with the delivery manager. The delivery manager creates the proposal and fills `qualification` with the fit, budget, authority, and decision process, each known or `unknown`, and a `recommendation`. The product manager adds the needs and questions. You record the decision by typing `/aidd decide PROP-7 go`, or `no-go` with the reason after it. You can also say it to the agent, which asks you in a dialog. At a terminal, `aidd proposal decide PROP-7 go` does the same.
2. **Propose.** After go, the specialists write their parts. The delivery manager writes the proposal's Delivery section, the `milestones`, and the RAID log. Each milestone has its trigger, which is the acceptance of listed Acceptance ids, the listed Specs landed, or an event. The RAID log is `assumptions`, `issues`, and `dependencies` beside `risks`, each with an owner and a status. `aidd proposal matrix` renders them. You sign it off with `aidd proposal sign-off PROP-7`, which records the proposal's hash, and then you send it.
3. **Contract.** Once it is accepted, `aidd proposal convert` writes the Initiative. The Initiative takes over the milestones and the RAID log as the delivery record. `aidd new contract PROP-7` writes the statement-of-work base in the proposal's folder. It holds scope by Acceptance ids, deliverables, the milestones by id, change control, the acceptance period, and warranty. It also holds the clauses a person or a lawyer writes. It is a base to review, never legal advice.
4. **Start.** The brief's `## Kickoff` and the proposal's Delivery section hold the kickoff agenda, access provisioning, tenant and environment setup, and the communication cadence. Each access item becomes a dependency with an owner and a date.
5. **Deliver.** The loop runs as usual, Spec by Spec. On the cadence, the delivery manager updates the Initiative's RAID statuses. You record each milestone's `reached_on`, though a milestone whose trigger Specs all landed is reached by itself. Then you send the status digest from `aidd digest --client`.
6. **Change the scope.** A new request, or an assumption that proved false, becomes a change order. `aidd new contract <proposal id>` writes the next one beside the contract. It holds the delta and the affected ids, with the price and the client's decision left to humans. The Spec then goes back through Spec approval.
7. **Accept.** `aidd new acceptance` lists the ids to accept and their evidence. You record the client's decision per id from the client's own record. A milestone whose trigger names those ids is ready to invoice, by a person.
8. **Hand over.** `/aidd-team:handover` fills the `## Handover` sections of the acceptance record and the runbook. They hold the docs index, the credentials transfer log, training sessions, open issues, and the warranty start. The log never holds a secret. The tech writer and the SRE write their parts. A person records the sign-off.
9. **Support.** The contract's Support and service levels schedule holds the support tiers, targets by severity, and escalation. `aidd new vendors` writes the repository's vendor register, with each vendor's SLA and renewal date. `aidd validate` warns 30 days before a renewal. The product manager turns incoming issues into suggested Specs with `aidd import issues`, and keeps the feedback log. An agent drafts each feedback entry with its source, and a person confirms it. The tech writer writes the knowledge-base articles. The delivery manager reports support against the contract's levels in `aidd digest --client`.

## Use only the parts you want

**…see what I can set?**
Run `aidd config`. It lists the settings your config sets, with each value and where it comes from, then the few settings people most often change, such as `mode` and `goal`. `aidd config --all` lists every setting `.aidd/config.yaml` may hold, with its value here, what it does, and where that value comes from. The source is this config, a parent, the profile, or the default. `aidd config mode` shows one setting in full, with the values it allows. The config's first line names its schema, so an editor with a YAML language server completes each key and explains it as you type. VS Code's YAML extension, JetBrains, Zed, and Neovim all do.

**…use the team, the skills, or the standards without the loop?**
aidd is made of parts that work alone. Each one is on until you turn it off:

| Part | What it does | Turn it off |
| --- | --- | --- |
| the gate | checks each change before it merges, and posts `aidd/gate` | `mode: advisory`: it reports and never blocks. Without its CI workflow, it does not run |
| the guard | the hook that checks each step an agent takes: each edit and command | `mode: advisory` (the solo and team default): it notes what is outside the rules and lets the edit through. With the Spec steps off, or on an explore branch, it allows every edit. It always keeps its rules on approving, landing, merging, publishing, decision records, the default branch, deploy commands, and loosening the config |
| the session hooks | the summary at session start, the stop check, the compaction note, the prompt hint | `hooks: {level: "off"}` |
| the Spec steps | Spec first, then the approvals | `components.spec_steps: false`, for a repository that wants the gate without them (autopilot stops with it). Every session start, `aidd list`, and `aidd doctor` then say so, with the day it went off. To skip a step for one change, say so instead ([always on](METHOD.md#always-on)) |
| autopilot | runs the loop between your decisions | `components.autopilot: false` |
| the team | the aidd-team roles and commands | leave the aidd-team plugin uninstalled |

For the team and the skills with no Spec or approval stops:

```yaml
mode: advisory
components:
  spec_steps: false
```

To go faster without turning anything off, type `approve all`, and the agent records each approval for you until you type `stop approving`. For a throwaway prototype, type `explore branch <topic>`. aidd switches this worktree to `explore/<topic>`, where every edit is free and nothing merges from it as it is. To keep the work, rename the branch with `git branch -m <name>`, and the gate then checks it as it checks any change.

A part that is off says nothing, and the others keep working. With the Spec steps off, a role does the work you ask, inside its write area. Its other rules still hold, so it never approves, treats untrusted text as data, and keeps the change minimal. `aidd doctor` prints which parts are on. It warns when the loop is off but the gate still blocks, since a change on the spec route then needs a Spec to merge.

Turning a part off is a change to `.aidd/config.yaml`, a protected path, so a person makes it. A parent config that turns a part on binds every child config. aidd works per project, so a plugin installed for your user does nothing in a repository without `.aidd/config.yaml`. When the guard itself can't run, it allows the call. The exception is a project that fails closed, under the `audited` profile or where an organization's managed settings set `AIDD_HOOK_FAIL_CLOSED=1`. The guard reads the profile on each call, so nothing needs a new session. Never set the variable in your own user settings, and `aidd doctor` warns if you do. [Config](CONFIG.md#components) lists every switch.

## Product defaults and how to turn one off

**…know what every product gets without asking?**
Thirteen product defaults, each on unless `project.defaults.disabled` in `.aidd/config.yaml` names it with its reason:

- light and dark themes (`dark_mode`)
- responsive layouts and forms (`responsive`)
- i18n-ready strings and formats (`i18n_ready`)
- a Core Web Vitals budget (`perf_budget`)
- titles, social previews, icons, and error pages (`public_page_basics`)
- API conventions (`api_conventions`)
- data conventions (`data_conventions`)
- health endpoints, structured logs, and graceful shutdown (`operability`)
- security headers and cookies (`security_headers`)
- privacy policy and terms placeholders a person writes (`legal_placeholders`)
- a plain-text part and unsubscribe in email (`transactional_email`)
- formatter, linter, type check, pre-commit, and a dependency bot (`dev_basics`)
- a new project as a modular monolith in one repository: `apps/`, `modules/`, and `packages/`, with boundaries checked in CI (`modular_monolith`)

`/aidd-team:mvp` builds them on Day 0. The roles build them whenever a change touches the area, each with a test. `aidd-team:product-defaults` owns each one and its test, and [Config](CONFIG.md#project) says what each one means.

**…turn a product default off?**
Name it in `off` with the reason, in the same change:

```yaml
project:
  defaults:
    "off": {dark_mode: a print-first report; the screen is a preview}
```

The config refuses an empty reason or a key that is not a default. `aidd init` writes the list commented. In a repository it detects as a command-line tool or a library, it writes `dark_mode`, `responsive`, `perf_budget`, and `public_page_basics` off, with the reason "no user interface". In a repository that already has code, it writes `modular_monolith` off, so the existing structure stays, and a client project or an existing codebase records the decision in an ADR. Turn one back on by deleting its line. While `dark_mode` is on, `aidd validate` also warns when a Spec's design spec has no dark column in its Screen inventory. A child config's `off` replaces its parent's. When the parent locks `project`, the child may only drop keys to turn a default back on, and never add one.

## Standards and stacks

**…pick a linter, a type checker, or a package manager once for every repository?**
Each pack and practice skill leaves some decisions open, such as `ci-pipeline:linter`, and gives aidd's default for each one. List them, with aidd's library of opinionated standards that fill them:

```sh
aidd standard list
aidd standard add python/ruff-lint-format     # one standard
aidd stack add python-cli                     # a set that goes together
```

Each command copies the file into `docs/standards/`. It adds the `standards` entry and the `tests` that enforce it, so review the result as one change. Never edit a copy. `aidd doctor` reports an edited copy, and `aidd upgrade --yes` refreshes an unedited one. [Standards](STANDARDS.md) lists the library.

**…make every project carry a standard, or keep one out?**
Write `standards_policy` in the org preset, with its `require`, `exclude`, `replace`, and `allow_stacks` lists. It takes opinionated library ids only. An industry standard, such as WCAG, is only waived per project, with a reason and an expiry. A project can tighten the [policy](CONFIG.md#standards-policy) and never loosen it, and `aidd doctor` fails on a breach.

## Reporting and intake

**…report status to the team and the client?**
`aidd digest --since 2026-09-01` prints the team's rollup in Markdown. `--since` takes any git ref, such as `v1.4.0`. The rollup holds:

- the Specs that landed in the window
- what is in progress
- who each open step waits on
- what is blocked, and for how long
- open decisions and Needs
- the scope decisions reversed in the window, each a `decisions` entry with `replaces`
- risks, milestones, overdue flags, outcomes, waivers, and runbook drills
- feedback themes
- the gate metrics, when `aidd-events.jsonl` is there or `--events` names a file

`aidd digest --since 2026-09-01 --client --html` writes the page you send a client instead:

- a red, amber, or green status, with the three rules that set it
- the `milestones` from the Initiative, or from a proposal still being decided
- what landed, in plain words, from each Spec's title and intent
- what you need from them, which is a proposal question with no answer, or a Needs line that starts with `client:`
- the next steps

Cost stays out of the client's view unless you add `--include-cost`. `--json` prints the same for scripts, in the shape its [schema](../schemas/digest.schema.json) sets. Nothing in it approves anything, and the gate never reads it.

**…write release notes?**
`aidd release-notes --since v1.4.0` lists the Specs that landed since the tag, each with its title, intent, and the flags it hides behind. It groups them under Added, Changed, Deprecated, Removed, Fixed, and Security. Users see only the changes they notice, and `--audience developers` shows every one. A Spec's type picks the group, and a label such as `changelog:removed` overrides it. A `breaking` label also lists the Spec first, under Upgrade notes. The tech writer starts from that output and the [`release-notes.md`](../.agents/skills/aidd/assets/release-notes.md) template in the skill's assets. The tech writer edits the words, never the facts.

**…import issues from GitHub or another tracker?**
`aidd import issues --github acme/shop --label customer-ask --limit 20` turns each open issue into a draft Spec, with the product manager as `suggested_by`. So it shows up first in `aidd list` as a triage step, and `aidd validate` keeps it a draft until a person records `triage`. The issue's title becomes the Spec's title, and its labels the Spec's labels. Its body is quoted in Intent as data, escaped, with a link back. The rest stays for the person who takes it on. It reads `GITHUB_TOKEN` or `GH_TOKEN` when set, and public repositories without one. For any other tracker, export a JSON array of `{title, body, url, labels}`, then run `aidd import issues --file issues.json`. Run it again whenever you like, because an issue whose link a Spec already names is skipped.

**…capture feedback after launch?**
`aidd new feedback launch` writes `docs/feedback/launch.md`, a living log with one row per piece of feedback. Each row has the date, the channel, and the customer or segment, but never a name. It also has a short quote, a theme, a severity, an optional 0-10 score, and the Spec or hypothesis it concerns. `aidd digest` counts the themes, the severities, and the NPS in its window. The product manager reads the log at Learn.

## Running the team

**…set up aidd in a repository?**
Ask your agent: "Install thaithienvanid/aidd and apply it to this project." Or run `aidd init` and `aidd doctor`, as [Install](INSTALL.md) shows. The gate reports without blocking until you enforce it and the platform requires it. [What holds until then](PLATFORMS.md#what-holds-without-the-full-setup) explains the gap.

**…bring the delivery team into a project, new or old?**
1. `aidd init --dry-run`, to see what it finds and proposes
2. `aidd init --team`, in a setup change
3. `/aidd-onboard`, to map the codebase before the first change

A team command's name depends on how the team is installed. From the files `aidd init --team` writes, it is
`/aidd-<flow>`, such as `/aidd-onboard`. From the `aidd-team` plugin, it is `/aidd-team:<flow>`, such as
`/aidd-team:onboard`. Type `/aidd-team:` to list them all, since no command is named `/aidd-team` alone. After you
install the plugin, run `/reload-plugins` or start a new session, as [Install](INSTALL.md#claude-code-plugins) says.
These pages write the plugin's names.

[Adoption](ADOPTION.md#bring-the-delivery-team-to-a-project) covers monorepos, projects in several repositories, a client's repository, and the rest.

**…let the agents run the loop between my decisions?**
Run `/aidd-team:autopilot "<goal>"`, or `/aidd-team:autopilot SPEC-1` for open work. aidd decides each next step, the roles do it, and the run stops whenever you must decide. A goal starts with a plan, and nothing is built until you agree to it. Stop the run with Esc. Pause one change with `blockers` in its Spec. `aidd autopilot status` shows the lease and the steps done. When the run stops, it lists what waits on you, how to decide each, and the command that goes on, such as `/aidd-team:autopilot all`. Run it in the same session or a new one; after a long run, a new session or `/clear` keeps the context small. To wait for your decisions, Claude Code can poll your inbox slowly with `/loop 30m aidd list --waiting-on-me`. Before an autopilot run, check the harness with `aidd doctor --autopilot`, which prints the permission rules a run needs. [Autopilot](AUTOPILOT.md) is the whole guide.

A run stops at its limits. The timebox is 6 hours by default, and the token and cost caps are off until you set
them. Set them in `.aidd/config.yaml`, which only a person edits, since the guard denies an agent's edit there and the
run never extends a limit itself:

```yaml
autopilot:
  timebox: "6h"        # how long one run may last, in quotes: "90m", "6h", up to "9999h"
  max_tokens: 5000000  # optional: the most tokens one run may record
  max_cost:            # optional: the most one run may cost
    amount: 50
    currency: USD
```

A run also stops whenever you must decide, so how often you approve paces it more than the timebox does. For a
long run, start it on work that is already approved, such as `--work all`, an Epic, or a label. Several shorter runs
lose nothing, because the journal in the git directory keeps every step, as [Config](CONFIG.md) explains.

**…make the main session hand every edit to a role?**
Install the team with `aidd init --team`, then set `delegate: always` under [`agents`](CONFIG.md#mission-goal-and-agents). The guard then denies the main session's edits of repository content and names the role that owns each file. The default, `auto`, denies them only in an autopilot run's session, and elsewhere tells the agent which role owns the file.

**…see what is next across a project in several repositories?**
`aidd list api web infra`, with the repository paths.

**…work as a small team of two or three, each person with their own agents?**
One change, one branch, one author. Nobody approves their own work, and `aidd list --branch` warns when two branches change the same code. [Adoption](ADOPTION.md#a-small-team-two-or-three-people) covers who decides what, the config, and what happens when only some people use agents.

<a id="grow-the-scale"></a>
**…grow from one founder to many companies?**
Keep the same loop, and add only what the scale needs. [METHOD.md §10.1](METHOD.md#101-one-loop-at-every-scale) has the reasons.

| Scale | What you add | How it holds |
| --- | --- | --- |
| A solo founder | `profile: solo`, with the founder in `owners.approvers`; the aidd-team roles as agents | the founder approves with an explicit second look: a full-SHA approval ([METHOD.md §8](METHOD.md#solo)) |
| Many solo founders | a shared public preset, `extends: [{url: "<url>", sha256: "<digest>"}]` | each repository gates itself; the sha256 pin means no one else's edit reaches you unreviewed |
| A team | `profile: team`, an `@org/team` approver pool | an Approver other than the author for Spec approval and Merge approval; Locks and Parallel Tasks when changes overlap |
| Many teams | `owners.paths` or CODEOWNERS per area; an Epic's Specs across teams (`owner_team`); `team:ID` in `depends_on`; `when_changed` tests | each touched area's owners approve on top of the approvals the route requires |
| Many projects | one org preset through `extends` or `AIDD_ORG_PRESET`; `trace_id` across repositories | repositories can only tighten the preset; each repository gates its own child change; `aidd metrics --by repo` |
| Many companies | each company's own preset, `tenant`, approvers, and GitHub App or GitLab token | a gate decides only for its own repositories. A contributor from another company (vendor, agency, open source) is an author there, never an Approver. An approval by another tenant's identity never counts. `aidd metrics --tenant`, `--by org` |

**…onboard a new teammate?**
They run `aidd doctor` to check their machine and the repository, `aidd owners` to see who decides what and every agent role, and `aidd list`. Everyone shares one config, skill, and set of roles, so nobody needs a private agent setup.

**…make the agents follow our own standards?**
List each document under [`standards`](CONFIG.md#standards) in the config, with the roles that must read it. If a test enforces the document, add that test's name. `aidd owners` then shows each role what to read before its step, and `aidd doctor` flags a missing document. A standard with an enforcing test is a rule the gate checks. Without one, it is guidance.

**…add our own practice skill?**
A practice skill tells a role how to do one kind of work well, such as posting to your ledger. Write your own as a project skill:

1. Make the file `.claude/skills/<name>/SKILL.md` for Claude Code. For agents that read `.agents/skills/`, make `.agents/skills/<name>/SKILL.md`.
2. Use a lowercase name with hyphens. In `.claude/skills/`, do not start the name with `aidd-` when `aidd init --team` wrote the team's files there. `aidd upgrade` then reports such a folder as a team file that aidd no longer ships.
3. Use the headings of the team's practice template, in this order: **Use it when** and **Do not use when**, `## Standards`, the loop steps it works in (`## Plan` to `## Learn`), `## Test commands`, `## Stop if`, and `## Hand off`. Write the standards as a plain list. The generated block is only for the team's own skills.
4. In the Spec, the architect names it in a Task's `skills` by its folder name. A Task names at most two skills. The role that takes the Task loads it with its `Skill` tool.

aidd does not check a project skill. `aidd eval packs` reads only the team's own packs and skills, and `aidd validate` checks only that a Task names at most two. You review the skill in the change that adds it. Both skill folders are protected paths, so that change takes the major route.

An example, `.claude/skills/ledger-posting/SKILL.md`:

```markdown
---
name: ledger-posting
description: "Practice skill: post money movements to our ledger. Use when a Task writes or changes a ledger entry."
metadata:
  checked: "2026-10-07"
---

**Use it when** a Task writes to `src/ledger/`. **Do not use when** a Task only reads balances.

## Standards

- Double-entry: the debits and the credits of every posting are equal.

## Implement

- Post through `ledger.post()`, never with raw SQL.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Ledger balance | every posting balances | `python3 -m pytest tests/ledger -q` |

## Stop if

- The Task needs a new account type.

## Hand off

- The postings that changed, and the result of the balance test.
```

The Task that uses it, in the Spec:

```yaml
tasks:
  - id: SPEC-12-T1
    title: Post refunds to the ledger
    scope: [src/ledger/refunds.py]
    assignee: agent:developer
    skills: [ledger-posting]
```

**…change how much the agent hooks do?**
Set [`hooks.level`](CONFIG.md#hooks) in the config:

- With `"off"`, no session hook speaks.
- With `minimal`, the agent is briefed with this change's route and next steps when a session starts.
- With `balanced`, it's also reminded to run the tests before it stops, and to write a handoff note after a compaction.
- With `strict`, the reminder holds the agent back instead, so it runs the tests before it stops.

Each profile has a default. A repository can raise its organization's level, but never lower it. Only `orca_status`, which is display only, can always be turned off. The guard that stops an agent from approving or merging is on at every level. `aidd metrics --guard` shows what it stopped, and why.

<a id="run-the-routine-checks-on-a-schedule"></a>
**…run the routine checks on a schedule?**
Run them weekly at the repository root, from a scheduled CI job or from cron. aidd must be installed, and the gate events downloaded, as [Reading the metrics](ADOPTION.md#reading-the-metrics) shows:

```sh
aidd validate                                          # reports an emergency whose full review is overdue
aidd doctor                                            # warns about a runbook not tested within docs.max_runbook_age_days
                                                       # and a living doc not reviewed within max_review_age_days
aidd metrics --since 2026-09-21                        # this machine's own gate runs (.git/aidd/events.jsonl)
aidd metrics events/*.jsonl --since 2026-09-21         # the last week: where changes waited, and the first-pass rate
aidd metrics events/*.jsonl --dora --specs specs       # exits 1 when a [targets] value is missed
aidd metrics events/*.jsonl --autonomy                 # which agents have earned lighter review
aidd observe --band http_5xx_rate series.txt --write   # exits 1 on a breach, and writes a draft Spec
```

On GitHub, three templates already do part of it:

- `templates/github/aidd-notify.yml` posts the weekly metrics summary to Slack or Teams.
- `templates/github/aidd-observe.yml` runs `aidd observe --band` on a schedule.
- `templates/github/aidd-standards.yml` re-reads the standards' evidence every week with `aidd eval standards --online`.

A failing exit is the job's way to ask a person to look. Nothing in the job approves, merges, or changes code.

**…see how we are doing?**
- `aidd metrics` for lead time, first-pass rate, and where changes wait
- `aidd metrics --dora` for proxies of the five DORA metrics against your [`targets`](CONFIG.md#targets), with `--specs` for change fail rate and recovery time
- `aidd metrics --autonomy` for each agent's record

**…show an auditor what happened?**
Every change carries a gate record of who approved what, on which evidence, and which agent wrote what. [Enterprise readiness](ENTERPRISE.md) lists what platform, security, and compliance teams check.

**…check our process covers what an engineering firm does?**
The team maps every ISO/IEC/IEEE 12207 life cycle process to what covers it, and says who acts. See [The delivery team reference](TEAM-REFERENCE.md#what-the-team-covers).

**…upgrade aidd?**
1. Once a day, the CLI says when a newer release is out. `aidd self-update` installs it, after it checks the download against the [release](INSTALL.md#updates).
2. In each repository, run `aidd upgrade` to see what it would change.
3. Run `aidd upgrade --yes` to change it. It updates the skill, the team files, the CI pins, and `aidd_version`, and never your own edits.
4. Merge it as one change.

[Install](INSTALL.md#versions).

**…remove aidd?**
`aidd uninstall` lists what it would remove. `aidd uninstall --yes` removes it. [Install](INSTALL.md#remove-it).
