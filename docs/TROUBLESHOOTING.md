# Troubleshooting

Each entry is a symptom, its cause, and the fix. Start with `aidd doctor`, which checks the setup, and `aidd gate --explain <rule>`, which says why a rule holds or not. Every finding code the gate can emit, with what fires it, is listed under "Finding codes" in [examples/README.md](../examples/README.md).

## Approving and shipping

### `aidd approve` or `aidd ship` refuses: "an agent started this shell"

**Cause.** Approving and shipping are a person's decisions. The commands refuse in a shell where `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT` is set (a shell an agent started), and without an interactive terminal.

**Fix.** Type the decision at the prompt yourself: `approve <ID>`, `approve merge`, or `ship it`. aidd records your own words ([Your words decide](ADOPTION.md#your-words-decide)). To let the agents approve for you, type `approve all`. Or open a terminal yourself, outside the agent, and run the command the refusal printed.

### `aidd approve` refuses, or the gate never counts a local approval

**Cause.** A local approval is recorded as `email:<git user.email>`. When `owners.approvers` does not list that email, the approval is not an Approver's. `aidd doctor` warns about it.

**Fix.** Add `"email:you@example.com"` (the email your commits use) to `owners.approvers`, or set `git config user.email` to the one listed.

### The gate waits for a specialist or a Merge approval that never comes

**Cause.** The gate stays pending on `specialist_approval` or `merge_approval`. Outside solo, nobody approves their own change. When a specialist pool has one member and that person wrote the change, or when `owners.approvers` names only the author, no eligible Approver exists. Every change to a protected path (the config, CI, agent instructions) is major, so a one-person `security` pool blocks that person's setup changes.

**Fix.** Name at least two humans in every specialist pool and in `owners.approvers`; `aidd doctor` warns about a pool of one. One person on their own uses the `solo` profile ([Adoption: Team](ADOPTION.md#team)).

### An approval I gave no longer counts

**Cause.** Approvals bind to exact content. A Merge approval names the head commit, so a new push needs a new approval unless a trivial rebase carried it (`merge_approval.not_carried` says why it did not). A Spec approval names the Spec's hash, which covers the Spec and its frozen test files, so any edit to them voids it (`spec_approval.voided`, `spec_approval.missing`). Retargeting the change to another base branch voids earlier approvals too, and an approval line posted through an App (`merge_approval.via_app`, `spec_approval.via_app`) never counted.

**Fix.** Review what changed, then approve again: the new head, or the new Spec hash (`aidd hash specs/<ID>.md --line`). Post an approval line yourself, not through an App or an agent's integration.

### A major change waits even though I approved it

**Cause.** The cool-off: under solo, a major change waits 30 minutes after its head reached the platform (locally, after the head commit's date) before your approval counts.

**Fix.** Wait. Locally, `aidd ship --skip-cooloff` skips it, and the gate record names you.

## The gate

### The gate never blocks anything

**Cause.** The gate starts in advisory mode: it reports on `aidd/gate (advisory)`, which no rule requires. It also blocks nothing when the platform does not require `aidd/gate`. Editing `mode` in the workflow changes nothing, because the base branch's `.aidd/config.yaml` wins and `aidd init` always writes a `mode`.

**Fix.** Set `mode: enforce` in `.aidd/config.yaml` on the base branch, then require `aidd/gate` in a ruleset with its source pinned to the gate's App ([Platforms](PLATFORMS.md#setup)).

### On a private repository, the gate cannot be required

**Cause.** Rulesets and required checks on private repositories need GitHub Pro, Team, or Enterprise. On GitHub Free, a private repository's `aidd/gate` is advisory: it reports, and anyone who can merge still can.

**Fix.** Use a paid GitHub plan, make the repository public, or treat the gate as advisory and say so. Locally, `aidd ship` is the gate either way.

### The gate warns that a commit author is unlinked

**Cause.** A commit's author email maps to no platform account (`authors.unlinked`). That author might be an Approver under another name, so the gate cannot prove separation of duties. Locally, and in the Quickstart's dry run, every commit carries only an email, so the warning is expected there.

**Fix.** Link the email to its account on the platform, list agent emails in `identities.bots`, or rewrite the commits. Under `unlinked_authors: fail` (the audited default) it fails instead of warning.

### `tests` fails with "no tests" (`tests.none`, `tests.minor_without_suite`)

**Cause.** The config has no `tests`, and the change brings none of its own. A minor change needs the repository suite (or `evidence.status_checks`), never only its own inline tests.

**Fix.** Add a `tests` entry that runs your suite (`aidd init --test "<command>"` writes one), or list your CI checks in `evidence.status_checks`.

### `tests` is pending on a branch that holds only the Spec (`tests.spec_phase`)

**Cause.** The Spec phase: the new tests fail because the code does not exist yet. That is expected, and the gate waits instead of failing.

**Fix.** Nothing. Approve the Spec, and the implementation turns them green.

### The gate raised my route

**Cause.** The gate computes the minimum route from the real diff and rejects a lower declaration. A path your risk rules or the baseline mark as sensitive, or a protected path, makes the change major.

**Fix.** Run `aidd gate` to see why, then declare the route it names (a Spec, for normal and major).

### A flag is past its cleanup date

**Cause.** A Spec's `flags` entry has a `cleanup_due` date that has passed, and no Spec lists the flag in `removes_flags`. `aidd validate` warns, and `aidd list` shows the cleanup as the flag owner's work. The gate never blocks on it.

**Fix.** Write the cleanup Spec: it deletes the flag, its dead branch, and the test of the state that no longer ships. It also lists the flag in `removes_flags: ["<name>"]`. If the flag must live longer (a kill switch, say), a new Spec declares it again in `flags` with a later `cleanup_due`. That Spec says why in its Context, and the later date wins. The old Spec's date is approved content and stays as it is.

## Setup

### The agent is not stopped when it edits outside its scope or runs `git push`

**Cause.** The guard runs only where a hook is wired. `aidd init` wires one for each coding agent it detects or that you name with `--harness`; an agent with no hook gets the skill and `AGENTS.md` only.

**Fix.** Run `aidd init --harness claude-code` (or your agent's name, [INSTALL.md](INSTALL.md#your-coding-agent)), then `aidd doctor`, which reports whether the hook is wired and starts. Without a hook, the gate still catches out-of-scope changes at merge.

### Claude Code shows "aidd: the guard could not run on this machine"

**Cause.** The repository's hooks start aidd through `~/.aidd/bin/aidd`, a launcher that each contributor writes on their own machine. Here it is missing, it names a Python that moved, or `aidd doctor` does not trust it. Until it runs, the guard allows each call. Under `AIDD_HOOK_FAIL_CLOSED=1`, it blocks each call instead.

**Fix.** Install aidd ([INSTALL.md](INSTALL.md)), run `aidd init --agent-hooks` in the repository, then run `aidd doctor`. Restart Claude Code so that it loads the hooks again.

### `aidd init --force` replaced my config

**Cause.** `--force` rewrites every file `aidd init` writes, `.aidd/config.yaml` included, with a fresh one. Its `mode`, owners, and rules are the flags you passed, not your edits.

**Fix.** Restore the config from git (`git restore .aidd/config.yaml`). To refresh the skill, the team files, and the CI pins, run `aidd upgrade --yes` instead (with `--ref <sha>` to pin a commit). It changes only the config's `aidd_version`, and leaves the rest as you wrote it.

### `aidd validate` fails: "the waiver of 'rule-id' expired"

**Cause.** A `project.waivers` entry's `until` date has passed, so the rule it waived binds again. `aidd validate` warned 14 days before.

**Fix.** Meet the rule, then remove the waiver. If it still cannot hold, a person (never an agent) approves a new waiver with a new `until` and reason, as a config change ([ADOPTION.md](ADOPTION.md#project-constraints-and-rules)).

### `aidd doctor` warns that a specialist pool has one member

**Cause.** See [pending forever](#the-gate-waits-for-a-specialist-or-a-merge-approval-that-never-comes): that person can never approve a change they wrote.

**Fix.** Add a second person to the pool, or use a team handle such as `@org/security`.

### `aidd init` did not write `aidd-security.yml`

**Cause.** The security-scanning workflow is written only when compliance is on (`project.compliance` names a target, or the profile is audited) or with `--security-ci`. On GitLab, `aidd init` writes `.gitlab/aidd-security.gitlab-ci.yml` instead, with the secret scan only.

**Fix.** `aidd init --security-ci --force` (which also rewrites the config, so check its diff), or copy `templates/github/aidd-security.yml` from the aidd package into `.github/workflows/`. On GitLab, include `.gitlab/aidd-security.gitlab-ci.yml`, and run the other scans (OSV-Scanner, Semgrep, Syft) as jobs of your pipeline.

## Reminders after the work

These are warnings from `aidd validate` and `aidd doctor`; the gate never reads them.

### `aidd validate` says the hypothesis was due: "record the outcome"

**Cause.** The Spec shipped (its status is shipped or done, or `outcome.released_on` is set), its `hypothesis` is past due, and nobody recorded `outcome.result`. The due date is the latest date the hypothesis names ("by 2026-12-31"), else the release date plus the observe window. `aidd list` shows the same reminder as a step, `spec.outcome_due`.

**Fix.** Measure the metric the hypothesis names and record `result` in the Spec's `outcome` block: met, missed, or inconclusive, with the number. A missed hypothesis is a Learn signal, not a rollback. Recording it never voids Spec approval.

### `aidd validate` warns that a `uat: true` Spec has no acceptance record

**Cause.** The client accepts this change by hand, the Spec is in review or shipped, and it links no acceptance record, or the acceptance record does not list every Acceptance id.

**Fix.** `aidd new acceptance "<topic>" --spec <ID>` writes the record as a living doc; a person fills one row per Acceptance id from the client's own record before ship.

### `aidd doctor` warns about a restore drill

**Cause.** A runbook with `restore: true` has no `rto` or `rpo`, has never been drilled, or its `tested_on` is older than `runbook_max_age_days` (180 days by default).

**Fix.** Restore from a real backup into a scratch environment by following the runbook. Check that the restore met the RTO and the RPO, and record the day in `tested_on`. Write the objectives in `rto` and `rpo` (such as `"4h"` and `"15m"`).

### A change to a user or customer file is major on the privacy dimension

**Cause.** `baseline:personal-data` matched, on one of these:

- the path is a user, customer, account, member, patient, or contact model or folder
- the path is a file named for personal data
- the diff adds an auth library

Personal data is the privacy dimension, which forces major and names the privacy pool. `aidd validate` then warns until the Spec links a compliance doc with its DPIA.

**Fix.** Declare `privacy` in the Spec's risk, write the compliance doc (`aidd new compliance <topic> --spec <ID>`) and the data map, and load `aidd-team:privacy-by-default`. When the path holds no personal data (a `profile` folder of performance traces, say), add it to `rule_exclusions` for `baseline:personal-data` in the config, in its own change.

### `aidd validate` warns that the Spec links no authz doc

**Cause.** The required-docs matrix asks for an authorization matrix when both of these hold:

- a Task's scope touches an authentication or authorization path (the `baseline:auth` paths)
- either the Spec's risk names security, or compliance is on (`project.compliance` names a target, or the profile is audited)

**Fix.** `aidd new authz "<topic>" --spec <ID>`, filled in before Spec approval ([How do I…](HOW-TO.md#before-the-work)). When the change grants and checks no access, turn the rule off for that kind in `docs.required.authz`.

### `aidd validate` refuses the config: a product default is off with no reason

**Cause.** `project.defaults.disabled` names a default with an empty reason, or a key that is not a default. Every product default is on unless a person turns it off. The reason is what tells the next reader, and the agents, that it was a decision.

**Fix.** Write the reason as the value (`off: {dark_mode: "a print-first report"}`), or delete the key to turn the default back on ([How do I…](HOW-TO.md#product-defaults-and-how-to-turn-one-off)).

### `aidd validate` warns that a design spec has no dark column

**Cause.** `dark_mode` is on (the default) and the Screen inventory of a design spec the Spec links names no dark theme: no row or header says "dark".

**Fix.** Add the Theme column (`light, dark`) and the dark screenshots, `<screen>-<state>-<target>-dark.png`. When the product has one theme, turn `dark_mode` off with its reason in `project.defaults.disabled`.
### `aidd validate` warns that the Spec links no threat-model doc, though its risk names no security

**Cause.** Compliance is on (`project.compliance` names a target, or the profile is audited), and a Task's scope touches an authentication, authorization, secrets, or cryptography path (the `baseline:auth` and `baseline:secrets-crypto` paths). With compliance on, a change there gets a threat model whatever its risk says.

**Fix.** `aidd new threat-model <component> --spec <ID>` writes the component's living model, or links it again when an earlier Spec wrote it. Put this Spec's delta in the tech spec's `### Security and privacy` before Spec approval. To keep compliance on and drop only this rule, set `docs.required.threat-model` to your own triggers.

### `aidd validate` warns that a postmortem action is past its due date

**Cause.** A postmortem in review or published lists an `actions` item whose `due` date has passed and that is not `done: true`. This is problem management, so an action item nobody finishes is seen.

**Fix.** Finish the action and record `done: true` (and `tracked_in`, the Spec or ticket that carried it). Or have its owner set a new `due` date, with the reason in the postmortem.
