# How do I…

Short answers for everyone on the team, engineer or not, each with the command and where the details are. When you are not sure what comes next, run `aidd next`: it reads the repository and tells you the next step for each open piece of work, and who takes it.

## Every day

**…know what to do next?**
`aidd next`. It lists each open piece of work (the Specs this branch changes and your proposals) with the step, who takes it (you, your agent, or an Approver), and the command. `aidd next --json` prints the same for scripts, and lists each Spec's Tasks under `tasks`, each `ready`, `blocked`, or `done`.

**…see the whole backlog, not only my branch?**
`aidd next --all`: every Spec under the Specs folder at HEAD, each with why it matters (mission, goal, Initiative, Epic, hypothesis) and its status group. Narrow it with `--mine`, `--agent` (or `--agent=tester`: Tasks an agent may start now), `--blocked`, and `--label area:billing`.

**…see what waits on me as an Approver?**
`aidd next --waiting-on-me`, or with `--all` for every branch's Specs at HEAD: the Spec approvals and Merge approvals you are eligible for, oldest first to escalate. It warns when you hold more than `gates.max_open_per_approver`, and marks a wait past `gates.escalate_after_minutes` with the `owners.backup_approvers` to ask ([METHOD.md §5.1](METHOD.md#51-status)). It never approves anything.

**…triage work an agent proposed?**
It shows up first in `aidd next` as a triage step. Record your decision in the Spec: `triage = { decision = "accepted", by = "@you", on = 2026-09-28 }`, or `declined`, `duplicate` (with `duplicate_of`), or `snoozed` (with `until`, and it stays out of `aidd next` until then).

**…say one Spec waits for another?**
`relations = [{ type = "blocked_by", id = "SPEC-12" }]` in its front matter. `aidd next` shows it blocked until SPEC-12 is done, and `aidd validate` refuses a target that does not exist or a cycle.

**…see a Spec's history?**
`aidd log specs/SPEC-12.md` (or `aidd log SPEC-12`): each status with the time it held, the approvals recorded on this machine or in a gate record, and the agents named in the `Assisted-by:` trailers of the commits touching its scope. `--json` for scripts.

**…build a feature?**
Tell your agent what you want. It starts with `aidd next`, which computes the route and picks the lane: on the fast lane it builds straight away; when the change needs a Spec, it writes the Spec and its tests and stops for your Spec approval. With the delivery team: `/aidd-team:specify`, then `/aidd-team:implement` once the Spec is approved, `/aidd-team:verify` on the head it built, then `/aidd-team:review`. The whole walk-through: [Quickstart](QUICKSTART.md).

**…fix a small bug quickly?**
Tell your agent. A small, reversible fix goes on the fast lane: no Spec file, a short `toml aidd` block in the pull request (`aidd change` prints it), and one approval.

**…get test feedback while I work?**
`aidd test --changed` runs only the commands your working tree's changes select (a matching `when_changed`, a Spec's command when you touched its Task scope or tests, and the suite), green only; `aidd test --watch` re-runs that whenever you save, until Ctrl-C. Both write evidence marked partial, which the gate never accepts: run a full `aidd test` (or let `aidd-tests` run) before you ask for review.

**…take a pull request to green?**
`/aidd-team:sweep`: it answers every review comment and fixes failing checks inside the scope, and stops when only your Merge approval is left.

## Many agents at once

**…start one agent per Task?**
Once the Spec is approved, `aidd next --json` lists its Tasks with their `scope`, `depends_on`, and a `status`. Start one agent for each `ready` Task, each in its own worktree branched from the Spec's branch (`git worktree add ../SPEC-9-T1 -b SPEC-9-T1 feat/spec-9`). Ready Tasks never share files: Tasks whose scopes overlap must depend on one another. When a Task's branch is merged into the Spec's branch, start the Tasks that waited for it (`waiting_on`).

**…let two or three agents try a hard Task, and keep the best?**
Give the same Task to 2 or 3 agents, each in its own worktree, all against the same frozen tests. Results pick the winner, not taste:

```bash
git worktree add ../t1-a -b t1-a feat/spec-9      # one worktree and branch per attempt
git worktree add ../t1-b -b t1-b feat/spec-9
# start one agent in each, with the same prompt; when they are done, in each worktree:
aidd test --spec specs/SPEC-9.md                  # the frozen tests, green on head
aidd gate --spec specs/SPEC-9.md                  # every rule; only approvals may still be pending (exit 3)
git diff --stat feat/spec-9...HEAD                # how big the change is
```

1. Drop every attempt whose tests fail or whose gate fails for anything but a pending approval. An attempt that changed a frozen test voids the Spec approval, so its gate fails.
2. Of the rest, keep the smallest diff; when two are close, a reviewer reads both and picks one.
3. Delete the others: `git worktree remove ../t1-b && git branch -D t1-b`.
4. Only the winner opens a pull request and goes to Merge approval.

**…run aidd inside Orca?**
It works as it is: Orca's worktrees are git worktrees, local approvals are shared between them, and the guard runs for the agents Orca starts. aidd also shows its next step on the Orca workspace card. The setup, the card, parallel Tasks, and what to watch out for: [Running aidd inside Orca](ORCA.md).

**…run aidd under Paperclip?**
[Paperclip](https://github.com/paperclipai/paperclip) is an optional host that organizes agents like a company, with tasks, budgets, and approvals of its own. aidd works under it the way it works under any host: the agents do the work in the repository, and aidd decides what may merge.

- **Its approvals and its "done" are display only.** Neither is a Spec approval, a Merge approval, or evidence, and the gate reads neither. A person still approves on the PR/MR, or with `aidd approve` at their own terminal.
- **Each agent still follows the loop:** it starts with `aidd next`, runs `aidd test`, and stops for a person at Spec approval and Merge approval. `aidd next --json` lists a Spec's ready Tasks, one per agent.
- **Check that your Paperclip adapter runs the repository's own hooks.** aidd's guard works only where the agent's harness loads the hooks `aidd init` wired (such as `.claude/` for Claude Code). Start an agent through the adapter in the repository and run `aidd doctor` there. Without the hooks, nothing stops an agent's edit early, but the gate still decides every merge.

**…run agents in a sandbox?**
aidd does not sandbox anything: the guard and the gate stop approving, merging, and out-of-scope edits, not a command that reads your credentials or sends data out. For a real boundary, run the agent in a container. `aidd init --devcontainer` (or copying `templates/devcontainer/` to `.devcontainer/`) gives a starting point:

- **The firewall** denies outbound traffic except HTTPS and SSH to an allow-list: the code platform, the model API host, and the package registries. The list is set as build arguments in `devcontainer.json` and baked into the image, so nothing inside the container can widen it.
- **The agent** runs as a non-root user.
- **To adapt it,** change the hosts to your mirror and your model API, then rebuild. `.devcontainer/**` is a protected path, so a change to the allow-list is a major change.
- **Its limit:** it reduces what a misled agent can reach, but DNS and the allowed hosts can still carry data out, so keep secrets out of the container.

Your own `PreToolUse` rules can sit beside aidd's guard as well: [examples/hooks](../examples/hooks/README.md).

## Without GitHub or GitLab

**…work entirely on my own machine?**
Set up the solo profile with the email your commits use and no CI ([Local-first](ADOPTION.md#local-first-no-github-or-gitlab) has the one-line setup). Then approve at your own terminal with `aidd approve spec specs/<ID>.md` and `aidd approve merge`, and merge with `aidd ship` (`--squash` for one commit that keeps every agent's trailer). Each of these shows a six-character one-time code and continues only when you type it back; they refuse to run without an interactive terminal or in a shell an agent started, so run them in a terminal you opened yourself.

**…run several agents in parallel?**
One git worktree per Task or per agent: `git worktree add ../task-2 -b task-2`. Each keeps its own files and evidence; the approvals are shared. More in [Many agents at once](#many-agents-at-once).

## Approving

**…approve a Spec?**
Read the Spec (the Intent, the Acceptance, the scope, the rollback) and its tests. If they are right, post the approval line, `/aidd approve-spec <ID> <hash> <commit>`, as a comment on the pull request. Changing the Spec or its tests afterwards voids it. [Quickstart §4](QUICKSTART.md#4-spec-approval-the-approval-hash).

- **You need no CLI.** The line is in the tester's handoff note or the pull request description, and anyone can reproduce it with `aidd hash specs/<ID>.md --comment`.
- **On a phone,** `aidd hash specs/<ID>.md --comment --digest` prints the Spec on one screen above that line: the intent, each Acceptance item, the scope, the risk, the rollback, and the frozen test files.
- **Without a platform,** run `aidd approve spec specs/<ID>.md` instead.

**…see the tests fail before I approve the Spec?**
Open the pull request with the Spec and its tests only, before any implementation. `aidd-tests` runs them red against the base (and green on the head, where they fail too, as they should before the code exists), and the gate's summary says **Red on base: yes** under "Merge approval digest". Locally, `aidd test` on that commit shows the same red results. The gate's `tests` rule fails on that commit; that is expected until the implementation lands.

**…approve a merge?**
Read the gate's report: open the Details link of the `aidd/gate` check on the pull request, which shows the run summary. Its "Merge approval digest" puts each Acceptance item beside the test that covers it (`covers`) and its result, the review report's Critical and High findings, the residual risk, and what changed since the last approval. Then approve the head commit with a platform review. Under the solo profile, post `/aidd approve <full head SHA>`; without a platform, run `aidd approve merge`. A new push needs a new approval.

**…get notified when something waits on me?**
Copy `templates/github/aidd-notify.yml` into `.github/workflows/` and add a `SLACK_WEBHOOK_URL` or `TEAMS_WEBHOOK_URL` secret. It posts one line when `aidd/gate` changes on a pull request ("SPEC-9 waits for Spec approval: @alice -> link"), a weekday digest of what waits on each approver, and a weekly `aidd metrics` summary that names major changes approved suspiciously fast. It only posts text: you still approve on the pull request. On GitLab, a scheduled pipeline does the same. [Platforms](PLATFORMS.md#notifications).

**…let an agent's routine work merge without me?**
`aidd metrics --autonomy` shows which agents have a clean record on which kind of work. When one earns it, add that class of change to `[[standard_changes]]`, through the gate like any config change. [Adoption](ADOPTION.md#multiplayer-one-team-humans-and-agents).

**…make a production deploy wait for a person?**
Name the deploy command in `[[guard.gated_commands]]`, and keep the platform's own environment protection. [Platforms](PLATFORMS.md#deploy-commands-held-for-a-person).

## When something breaks

**…handle a production incident?**
Restore service first: the emergency lane lets a fix merge on the incident commander's say, with the full review due within the deadline in `[emergency]`. Then `/aidd-team:postmortem` writes the postmortem and the backfill Spec. [The method §6](METHOD.md#6-routes).

**…watch a release through its observe window?**
`aidd observe specs/<ID>.md --window` runs the Spec's observe command every 5 minutes (`--every`) until its `window` ends, and stops the moment the rollback trigger fires (after `--consecutive` unhealthy checks in a row). Exit 0: the window ended clean; 1: the trigger fired; 2: an error. It never rolls back: that is your release tooling's job, or yours. `--write` records the result in the Spec.

**…use a merge queue?**
On GitHub, turn it on in the branch ruleset: the gate judges each queue entry on its merge-group commit. [Platforms](PLATFORMS.md#merge-queues). GitLab merge trains are not supported yet.

**…catch a problem before users report it?**
`aidd watch` judges a metric against its recent baseline and, with `--write`, writes a draft Spec when it breaches. Run it from any scheduler, such as cron, with a series exported from whatever records the metric; on GitHub, `templates/github/aidd-watch.yml` runs it on a schedule. `templates/github/aidd-triage.yml` diagnoses a failed test run on a pull request.

**…write a runbook, and keep it working?**
`aidd new runbook RB-1 --title "Restore the orders database"` writes one in `docs/runbooks/`. After you follow it for real (a drill counts), set its `last_tested` date. `aidd doctor` warns when an active runbook was never tested or is older than 180 days (`runbook_max_age_days`). For an incident, `aidd new postmortem PM-1 --title "Checkout outage" --spec SPEC-12` writes the postmortem and links the Spec that fixes it.

## Before the work

**…propose a change to leadership, or bid for a client?**
`aidd new proposal PROP-1 --title "Move checkout to the new payment provider" --audience internal --addressee "the executive committee"` (or `--audience client --addressee "Acme Corp"`), then `/aidd-team:propose`. A person decides go or no-go before the team drafts, and signs it off before it is sent; `aidd proposal matrix` prints the tables for the document. [Adoption](ADOPTION.md#proposals-bids-and-internal-cases).

**…turn an accepted proposal into work?**
`aidd proposal convert proposals/PROP-1/proposal.md` writes the Initiative and Epics; `/aidd-team:plan` ranks them and writes the Spec stubs.

**…bring in a plan from Spec Kit, OpenSpec, Kiro, or BMAD?**
`aidd import speckit specs/001-photo-albums` (or `openspec openspec/changes/<change>`, `kiro .kiro/specs/<feature>`, `bmad <story file>`) writes a short Spec that quotes the plan's problem, turns its acceptance scenarios or EARS requirements into Acceptance items `A1`, `A2`, ..., takes each Task's scope from the paths the plan names, computes the route, and links the plan instead of copying it. It leaves the tests to you: name them, write them, then `aidd validate`. [Adoption](ADOPTION.md#coming-from-spec-kit-openspec-kiro-or-bmad).

**…plan something bigger than one change?**
`/aidd-team:plan`: an Initiative, Epics, and ranked Spec stubs, which you agree to before any Spec is filled in.

## Running the team

**…set up aidd in a repository?**
Ask your agent: "Install thaithienvanid/aidd and apply it to this project." Or `aidd init` and `aidd doctor`. [Install](INSTALL.md).

**…bring the delivery team into a project, new or old?**
`aidd init --dry-run` to see what it finds and proposes, `aidd init --team` in a setup change, then `/aidd-team:onboard` to map the codebase before the first change. Monorepos, projects in several repositories, a client's repository, and the rest: [Adoption](ADOPTION.md#bring-the-delivery-team-to-a-project).

**…see what is next across a project in several repositories?**
`aidd next api web infra`, with the repository paths.

**…work as a small team of two or three, each person with their own agents?**
One change, one branch, one author; nobody approves their own work; `aidd next` warns when two branches change the same code. Who decides what, the config, and what happens when only some people use agents: [Adoption](ADOPTION.md#a-small-team-two-or-three-people).

**…onboard a new teammate?**
They run `aidd doctor` (their machine and the repository), `aidd owners` (who decides what, and every agent role), and `aidd next`. One shared config, skill, and set of roles: nobody needs a private agent setup.

**…make the agents follow our own standards?**
List each document under `[[standards]]` in the config, with the roles that must read it and, if a test enforces it, that test's name ([Config](CONFIG.md#standards)). `aidd owners` then shows each role what to read before its step, and `aidd doctor` flags a missing document. A standard with an enforcing test is a rule the gate checks; without one it is guidance.

**…change how much the agent hooks do?**
Set `[hooks] level` in the config ([Config](CONFIG.md#hooks)):

- `minimal`: the agent is briefed with `aidd next` when a session starts.
- `standard`: it is also reminded to run the tests before it stops, and to write a handoff note after a compaction.
- `strict`: the reminder holds the agent back instead, so it runs the tests before it stops.

Each profile has a default, and a repository can raise its organization's level but never lower it. The same holds for each hook your organization turns on; only `orca_status`, which is display only, can always be turned off. The guard that stops an agent from approving or merging is on at every level, and `aidd metrics --guard` shows what it stopped, and why.

<a id="run-the-routine-checks-on-a-schedule"></a>
**…run the routine checks on a schedule?**
Run them weekly from a scheduled CI job, or from cron, at the repository root, with aidd installed and the gate events downloaded ([Reading the metrics](ADOPTION.md#reading-the-metrics) shows how):

```sh
aidd validate                                          # reports an emergency whose full review is overdue
aidd doctor                                            # warns about a runbook not tested within runbook_max_age_days
aidd metrics events/*.jsonl --since 2026-09-21         # the last week: where changes waited, and the first-pass rate
aidd metrics events/*.jsonl --dora --specs specs       # exits 1 when a [targets] value is missed
aidd metrics events/*.jsonl --autonomy                 # which agents have earned lighter review
aidd watch series.txt --metric http_5xx_rate --write   # exits 1 on a breach, and writes a draft Spec
```

On GitHub, two templates already do part of it: `templates/github/aidd-notify.yml` posts the weekly metrics summary to Slack or Teams, and `templates/github/aidd-watch.yml` runs `aidd watch` on a schedule. A failing exit is the job's way to ask a person to look; nothing in the job approves, merges, or changes code.

**…see how we are doing?**
`aidd metrics` for lead time, first-pass rate, and where changes wait; `aidd metrics --dora` for proxies of the five DORA metrics against your `[targets]` ([Config](CONFIG.md#targets)), with `--specs` for change fail rate and recovery time; `aidd metrics --autonomy` for each agent's record.

**…show an auditor what happened?**
Every change carries a gate record: who approved what, on which evidence, and which agent wrote what. What platform, security, and compliance teams check: [Enterprise readiness](ENTERPRISE.md).

**…check our process covers what an engineering firm does?**
The team maps every ISO/IEC/IEEE 12207 life cycle process to what covers it, and says who acts: [The delivery team reference](TEAM-REFERENCE.md#what-the-team-covers).

**…upgrade aidd?**
Upgrade the CLI (`uv tool upgrade aidd` or `pipx upgrade aidd`), then `aidd upgrade` in each repository to see what it would change, and `aidd upgrade --yes` to change it: the skill, the team files, the CI pins, and `aidd_version`, never your own edits. Merge it as one change. [Install](INSTALL.md#versions).

**…remove aidd?**
`aidd uninstall` lists what it would remove; `aidd uninstall --yes` removes it. [Install](INSTALL.md#remove-it).
