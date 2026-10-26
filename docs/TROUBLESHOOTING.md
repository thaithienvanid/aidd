# Troubleshooting

Each entry is a symptom, its cause, and the fix. Start with `aidd doctor`, which checks the setup, and `aidd gate --explain <rule>`, which says why a rule holds or not. [Error codes](ERRORS.md) lists every code aidd shows, with what it means and its fix. That covers the gate's finding codes, the step codes, the guard's reason codes, and the exit codes.

## The guard denied a step

The guard denies a step it can't allow, and its reason names the next step that works. It logs each denial with a reason code. Run `aidd metrics --guard` to count the denials by code and by role, so you see which ones fire most. [Error codes](ERRORS.md#guard-reason-codes) lists every reason code.

### The file belongs to another role or to no Task (`role_area`, `out_of_scope`, `no_active_spec`)

**Cause.** Each aidd-team role writes only its own area, and each Task writes only inside its scope. `role_area` means the file is outside the role's area, or the role is read-only. `out_of_scope` means no Task of the active Spec covers the file. `no_active_spec` means the branch has no Spec, so nothing approved a scope.

**Fix.** Hand the edit to the role the denial names, because its area holds the file. When the plan needs the file, add it to a Task's scope in the Spec. After Spec approval, that change voids the approval, so the person approves the Spec again. With no Spec, start one with `aidd new spec`, or `/aidd-team:specify`. On a branch with several Specs, name the branch `spec/<ID>` or set `AIDD_SPEC=specs/<ID>.md`.

### The guard can't read a shell command (`shell_opaque`, `shell_unknown_target`)

**Cause.** The guard checks the target of every shell write before it runs. It can't follow some commands. These include a command substitution where a command starts, a shell fed by a here-document or a pipe, `source`, `xargs`, and `find -exec`. Nor can it check a target in `$VAR`, in a glob, or in a patch read from a pipe.

**Fix.** Write the file with the Write or Edit tool and a literal path. Or run one plain command that names the file. Never route around the guard through another shell, because the next check denies that too.

### A file is frozen by Spec approval (`frozen_file`)

**Cause.** Spec approval binds the Spec, its tests, and its design as they read at the approved commit. So the guard denies an edit to a test or design file, or a frozen doc, while that approval holds.

**Fix.** Run `aidd revise <ID> "<what was wrong>"`. It records why, and makes the Spec a draft again. Then the file's owner changes it, and the person approves the new hash with one typed `approve <ID>`.

### An agent typed or ran a person's decision (`decision_typed`, `approve_or_merge`, `approval_post`)

**Cause.** Approving, landing, merging, and publishing are a person's decisions. `approve_or_merge` means an agent ran a command that approves or merges, such as `aidd approve` or `gh pr merge`. `approval_post` means a command carries an `/aidd approve` line. `decision_typed` means a command typed a decision word into another terminal, where it would pass for the person's keyboard.

**Fix.** The person types the decision at the agent's prompt, such as `approve <ID>`, `land it`, `merge it`, or `publish`. aidd records it from their own words, and the agent goes on. To let the agents approve for you, type `approve all`.

## Gate findings

### `change_request.several_specs`: no Change Request block, and the diff carries several Specs

**Cause.** With no block, the gate takes the one Spec the diff adds or changes as the change's. This diff carries several, so it can't tell which one the change is.

**Fix.** Run `aidd describe`, and paste the block it prints into the PR/MR description. It names the change's Spec as `spec`, or a goal's Specs as `specs`. With no PR/MR, `aidd describe --commit` records the block in an empty commit on the branch.

### `spec.not_at_head`: the named Spec is not in the head commit

**Cause.** The block's `spec` names a file the head commit doesn't hold. The Spec was never committed on this branch, it moved, or the path has a typo.

**Fix.** Commit the Spec on this branch, or correct the `spec` path in the block. Then run `aidd validate specs/<ID>.md` until it reports 0 errors.

### `scope.outside`: a changed file is outside every Task's scope

**Cause.** A changed path, or a rename's source, is in no Task's scope and in no exempt path. Spec approval covered only the scope the Spec declared.

**Fix.** Take the change to that file out, or widen a Task's `scope` in the Spec. Widening it voids Spec approval, so the person approves again. For a file that is never product code, such as a generated one, add it to `scope_exclude_paths` in its own config change.

### `changed_lines.over_limit`: the change is too big for its route

**Cause.** The changed lines exceed the route's `max_changed_lines`. A big change is hard to review well, so the route caps it.

**Fix.** Split the change into smaller ones, each with its own Spec or block. List generated files, such as a lockfile or a snapshot, in `changed_lines_exclude_paths`.

### `red_green.passes_on_base`: a new test already passes on the base commit

**Cause.** A `new_behavior` command passed on the base commit, so it proves nothing new. Either the test doesn't reach the new behavior, or the behavior already exists.

**Fix.** Make the test assert the new behavior, so it fails on base for the right reason. Then run `aidd test`, which runs it on base and on head. Once the Spec is approved, its tests are frozen, so start with `aidd revise`.

### `tests.evidence_other_head`: the test evidence is for another commit

**Cause.** The evidence names another head commit. You committed, amended, or rebased after `aidd test` ran.

**Fix.** Run `aidd test` again on the current head. In CI, wait for `aidd-tests` to finish on the new head.

### `tests.dirty_tree`: the tests ran in a dirty tree

**Cause.** `aidd test` ran while the tree held something the head commit doesn't. That's an uncommitted change, or an untracked file that no `.gitignore` in the repository ignores. Your own `.git/info/exclude` and global excludes don't count, because CI doesn't have them. Results from that tree prove nothing about the commit, so the gate waits. The finding, the `aidd test` note, and `aidd doctor` name the first paths. Often they're what an earlier test run or build left behind, or a file your computer makes, such as `.DS_Store`. So the next run is dirty even though you changed nothing.

**Fix.** Add each path a test run or a build left to `.gitignore`, and commit or stash your own changes. Then run `aidd test` again. `aidd init` and `aidd upgrade` add the common outputs for each stack they find, and the files macOS and Windows leave, unless the repository's `.gitignore` already ignores them or the project commits them:

| Stack | What tests and builds leave |
|---|---|
| Python | `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `.mypy_cache/`, `.ruff_cache/` |
| JavaScript and TypeScript | `node_modules/`, `coverage/`, `.nyc_output/`, `test-results/`, `playwright-report/` |
| Rust, and Java with Maven | `target/` |
| Go | `coverage.out`, `*.test` |
| Gradle | `build/`, `.gradle/` |
| .NET | `bin/`, `obj/`, `TestResults/` |
| C and C++ with CMake | `build/`, `CMakeFiles/`, `CMakeCache.txt`, `*.gcda`, `*.gcno` |
| Dart and Flutter | `.dart_tool/`, `build/` |
| Every project, for macOS and Windows | `.DS_Store`, `Thumbs.db`, `desktop.ini` |

They write the stack lines once, in a block marked `# aidd: what tests and builds leave stays out of git`, and the macOS and Windows files once, in their own block. So a line you delete stays deleted, a stack you add later still gets its lines, and `aidd uninstall` takes back those blocks alone. `dist/` is never added, because some projects commit it. If your tests write somewhere else, add that path to `.gitignore` yourself.

### `provenance.undeclared_trailer`: a commit names an agent that `assisted_by` doesn't list

**Cause.** A commit's `Assisted-by:` trailer names a `harness/model` that the Spec's or the block's `assisted_by` lacks.

**Fix.** Add that `harness/model` to `assisted_by`. That field is bookkeeping, so the edit never voids Spec approval. If the trailer itself is wrong, amend the commit instead.

### `config.newer_version`: the config asks for a newer aidd

**Cause.** The config's `aidd_version` is newer than the aidd that ran the gate. Someone upgraded the repository, and this CLI or CI pin is older.

**Fix.** Run `aidd self-update` for the CLI. Then upgrade the CI pins with the config, using `aidd upgrade --ref <sha> --yes`, as [Install](INSTALL.md) says.

## The loop

### `aidd list --waiting-on-me` is empty, though work waits for you

**Cause.** aidd matches each step's Approvers against who you are, from `git config user.email`, then `git config github.user`, then gh's signed-in account. When `owners.approvers` names `@you` and gh is signed in as another account, nothing matches. The empty list then says how many items wait on an Approver, and who aidd took you for.

**Fix.** Run `git config github.user <your login>`. Or add the email your commits use, such as `"email:you@example.com"`, to `owners.approvers`. The gate counts only the identities `owners.approvers` lists, so check once with `aidd gate --spec specs/<ID>.md`.

### A plan branch fails `aidd validate`

**Cause.** A Spec stub from `aidd new spec` holds placeholders in its required fields until Specify fills them. So a branch that carries the stubs never validates.

**Fix.** Merge the plan as soon as the person agrees to it, with the Initiative and the Epics only. Each Spec then starts on its own branch from the base branch, and Specify fills it there.

### An approval line no longer counts after a rebase

**Cause.** An approval line names a commit. A rebase or an amend after you read the Spec can leave that commit on no branch. The gate then can't find it, so the approval never counts, and it reports `spec_approval.missing`.

**Fix.** Never rebase or amend between reading the Spec and the approval. If you did, type `approve <ID>` again on the new head.

### An agent stops without a report

**Cause.** A role ran out of turns at its cap, its agent file's `maxTurns`, so it returned nothing.

**Fix.** Never take silence as done. The lead starts the role again on what is left, from the files it wrote. After two silent runs, the lead asks you. If it doesn't, type `start <role> again from the files it wrote` at the agent's prompt.

## Approving, landing, and publishing

### `aidd approve` or `aidd land` refuses: "an agent started this shell"

**Cause.** Approving, landing, and publishing are a person's decisions. The commands refuse in a shell an agent started, which they tell by `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `AI_AGENT`, or `AIDD_AGENT`. They also refuse without an interactive terminal.

**Fix.** Type the decision at the prompt yourself, such as `approve <ID>`, `approve merge`, `land it`, or `publish`. aidd records your own words, as [Your words decide](ADOPTION.md#your-words-decide) explains. To let the agents approve for you, type `approve all`. Or open a terminal yourself, outside the agent, and run the command the refusal printed.

### `aidd approve` refuses, or the gate never counts a local approval

**Cause.** A local approval is recorded as `email:<git user.email>`. When `owners.approvers` does not list that email, the approval is not an Approver's. `aidd doctor` warns about it.

**Fix.** Add the email your commits use, such as `"email:you@example.com"`, to `owners.approvers`. Or set `git config user.email` to the one listed.

### The gate waits for a specialist or a Merge approval that never comes

**Cause.** The gate stays pending on `specialist_approval` or `merge_approval`. Outside solo, nobody approves their own change. When a specialist pool has one member and that person wrote the change, or when `owners.approvers` names only the author, no eligible Approver exists. Every change to a protected path, such as the config, CI, or agent instructions, is major. So a one-person `security` pool blocks that person's setup changes.

**Fix.** Name at least two humans in every specialist pool and in `owners.approvers`; `aidd doctor` warns about a pool of one. If you work on your own, use the `solo` profile, as [Adoption: Team](ADOPTION.md#team) explains.

### An approval I gave no longer counts

**Cause.** Approvals bind to exact content. A Merge approval names the head commit, so a new push needs a new approval unless a trivial rebase carried it. When it didn't, `merge_approval.not_carried` says why. A Spec approval names a commit, and binds the Spec and its frozen test files as that commit holds them. So any edit to them voids it, and the gate reports `spec_approval.voided` or `spec_approval.missing`. Retargeting the change to another base branch voids earlier approvals too. An approval line posted through an App never counted, and the gate reports `merge_approval.via_app` or `spec_approval.via_app`.

**Fix.** Review what changed, then approve again: type `approve <ID>`, `land it`, or `merge it` at the prompt, or post the line yourself, never through an App or an agent's integration.

### The gate never blocks anything

**Cause.** Under the solo and team profiles, the gate starts in advisory mode, so it reports on `aidd/gate (advisory)`, which no rule requires. It also blocks nothing when the platform does not require `aidd/gate`. `aidd init` writes a `mode` into the config only with `--enforce`. Without one, the gate workflow's `mode` input decides on GitHub, and a `mode` in the base branch's `.aidd/config.yaml` always wins over it.

**Fix.** Set `mode: enforce` in `.aidd/config.yaml` on the base branch, then require `aidd/gate` in a ruleset with its source pinned to the gate's App. [Platforms](PLATFORMS.md#setup) shows how.

### On a private repository, the gate cannot be required

**Cause.** Rulesets and required checks on private repositories need GitHub Pro, Team, or Enterprise. On GitHub Free, a private repository's `aidd/gate` is advisory: it reports, and anyone who can merge still can.

**Fix.** Use a paid GitHub plan, make the repository public, or treat the gate as advisory and say so. Locally, `aidd land` is the gate either way.

### The gate warns that a commit author is unlinked

**Cause.** A commit's author email maps to no platform account, so the gate reports `authors.unlinked`. That author might be an Approver under another name, so the gate cannot prove separation of duties. Locally, and in the Quickstart's dry run, every commit carries only an email, so the warning is expected there.

**Fix.** Link the email to its account on the platform, list agent emails in `identities.bots`, or rewrite the commits. Under `unlinked_authors: fail`, the audited default, it fails instead of warning.

### `tests` fails with "no tests" (`tests.none`, `tests.minor_without_suite`)

**Cause.** The config has no `tests`, and the change brings none of its own. A minor change needs the repository suite or `evidence.status_checks`, never only its own inline tests.

**Fix.** Add a `tests` entry that runs your suite, which `aidd init --test "<command>"` writes for you. Or list your CI checks in `evidence.status_checks`.

### `tests` is pending on a branch that holds only the Spec (`tests.spec_phase`)

**Cause.** The Spec phase: the new tests fail because the code does not exist yet. That is expected, and the gate waits instead of failing.

**Fix.** Nothing. Approve the Spec, and the implementation turns them green.

### The gate raised my route

**Cause.** The gate computes the minimum route from the real diff and rejects a lower declaration. A path your risk rules or the baseline mark as sensitive, or a protected path, makes the change major.

**Fix.** Run `aidd gate` to see why, then declare the route it names. Normal and major need a Spec.

### A flag is past its cleanup date

**Cause.** A Spec's `flags` entry has a `cleanup_due` date that has passed, and no Spec lists the flag in `removes_flags`. `aidd validate` warns, and `aidd list` shows the cleanup as the flag owner's work. The gate never blocks on it.

**Fix.** Write the cleanup Spec. It deletes the flag, its dead branch, and the test of the state that no longer ships. It also lists the flag in `removes_flags: ["<name>"]`. If the flag must live longer, as a kill switch does, a new Spec declares it again in `flags` with a later `cleanup_due`. That Spec says why in its Context, and the later date wins. The old Spec's date is approved content and stays as it is.

### A deprecation is past its sunset

**Cause.** A Spec's `deprecations` entry has a `sunset` date that has passed, and no Spec lists its `what` in `removes_deprecations`. `aidd validate` warns, `aidd list` shows the removal as the author's work, and `aidd digest` lists it as overdue. The gate never blocks on it.

**Fix.** Check that the known consumers have moved to the replacement. Then write the removal Spec, with the `aidd-team:api-design` skill. It deletes the old code and its tests, and lists the deprecation in `removes_deprecations: ["<what>"]`. If consumers need longer, a new Spec declares the same `what` again with a later `sunset`, and the running API sends the new `Sunset` date. That Spec says why in its Context.

### `aidd doctor` warns about security.txt

**Cause.** The config targets `cra`, and the repository has no `.well-known/security.txt`, or its `Expires` has passed or is within 30 days. RFC 9116 makes `Contact` and `Expires` required, so finders know the file is current.

**Fix.** Write or renew the file where the site serves it from, as the vulnerability policy says (`aidd new vulnerability-policy`). Set `Expires` less than a year ahead, and check that the `Contact` still reaches the security team.

## Setup

### The agent is not stopped when it edits outside its scope or runs `git push`

**Cause.** The guard runs only where a hook is wired. `aidd init` wires one for each coding agent it detects or that you name with `--harness`; an agent with no hook gets the skill and `AGENTS.md` only.

**Fix.** Run `aidd init --harness claude-code`, or name your own agent from [INSTALL.md](INSTALL.md#your-coding-agent). Then run `aidd doctor`, which reports whether the hook is wired and starts. Without a hook, the gate still catches out-of-scope changes at merge.

### Claude Code shows "aidd: the guard could not run on this machine"

**Cause.** The repository's hooks start aidd through `~/.aidd/bin/aidd`, a launcher that each contributor writes on their own machine. Here it is missing, it names a Python that moved, or `aidd doctor` does not trust it. Until it runs, the guard allows each call. Under `AIDD_HOOK_FAIL_CLOSED=1`, it blocks each call instead.

**Fix.** [Install aidd](INSTALL.md), run `aidd init --claude-hooks` in the repository, then run `aidd doctor`. Restart Claude Code so that it loads the hooks again.

### `aidd init --force` replaced my config

**Cause.** `--force` rewrites every file `aidd init` writes, `.aidd/config.yaml` included, with a fresh one. Its `mode`, owners, and rules are the flags you passed, not your edits.

**Fix.** Restore the config from git with `git restore .aidd/config.yaml`. To refresh the skill, the team files, and the CI pins, run `aidd upgrade --yes` instead, adding `--ref <sha>` to pin a commit. It changes only the config's `aidd_version`, and leaves the rest as you wrote it.

### `aidd validate` fails: "the waiver of 'rule-id' expired"

**Cause.** A `project.waivers` entry's `until` date has passed, so the rule it waived binds again. `aidd validate` warned 14 days before.

**Fix.** Meet the rule, then remove the waiver. If it still can't hold, a person approves a new waiver with a new `until` and reason, as a config change. An agent never does, as [ADOPTION.md](ADOPTION.md#project-constraints-and-rules) says.

### `aidd doctor` warns that a specialist pool has one member

**Cause.** That person can never approve a change they wrote, as [pending forever](#the-gate-waits-for-a-specialist-or-a-merge-approval-that-never-comes) explains.

**Fix.** Add a second person to the pool, or use a team handle such as `@org/security`.

### `aidd init` did not write `aidd-security.yml`

**Cause.** The security-scanning workflow is written only with `--security-ci`, or when compliance is on. Compliance is on when `project.compliance` names a target, or the profile is audited. On GitLab, `aidd init` writes `.gitlab/aidd-security.gitlab-ci.yml` instead, with the secret scan only.

**Fix.** Run `aidd init --security-ci --force`, and check its diff, because it also rewrites the config. Or copy `templates/github/aidd-security.yml` from the aidd package into `.github/workflows/`. On GitLab, include `.gitlab/aidd-security.gitlab-ci.yml`, and run the other scans, such as OSV-Scanner, Semgrep, and Syft, as jobs of your pipeline.

## Reminders after the work

These are warnings from `aidd validate` and `aidd doctor`; the gate never reads them.

### `aidd validate` says the hypothesis was due: "record the outcome"

**Cause.** The Spec landed, so its status is landed or done, or `outcome.released_on` is set. Its `hypothesis` is past due, and nobody recorded `outcome.result`. The due date is the latest date the hypothesis names, such as "by 2026-12-31". Without one, it's the release date plus the observe window. `aidd list` shows the same reminder as a step, `spec.outcome_due`.

**Fix.** Measure the metric the hypothesis names and record `result` in the Spec's `outcome` block: met, missed, or inconclusive, with the number. A missed hypothesis is a Learn signal, not a rollback. Recording it never voids Spec approval.

### `aidd validate` warns that a `uat: true` Spec has no acceptance record

**Cause.** The client accepts this change by hand, the Spec is in review or landed, and it links no acceptance record, or the acceptance record does not list every Acceptance id.

**Fix.** `aidd new acceptance "<topic>" --spec <ID>` writes the record as a living doc; a person fills one row per Acceptance id from the client's own record before it lands.

### `aidd doctor` warns about a restore drill

**Cause.** A runbook with `restore: true` has no `rto` or `rpo`, has never been drilled, or its `tested_on` is older than `docs.max_runbook_age_days`, which is 180 days by default.

**Fix.** Restore from a real backup into a scratch environment by following the runbook. Check that the restore met the RTO and the RPO, and record the day in `tested_on`. Write the objectives in `rto` and `rpo`, such as `"4h"` and `"15m"`.

### A change to a user or customer file is major on the privacy dimension

**Cause.** `baseline:personal-data` matched, on one of these:

- the path is a user, customer, account, member, patient, or contact model or folder
- the path is a file named for personal data
- the diff adds an auth library

Personal data is the privacy dimension, which forces major and names the privacy pool. `aidd validate` then warns until the Spec links a compliance doc with its DPIA.

**Fix.** Declare `privacy` in the Spec's risk, and load `aidd-team:privacy-by-default`. Then write the data map and the compliance doc, which `aidd new compliance <topic> --spec <ID>` starts. When the path holds no personal data, such as a `profile` folder of performance traces, add it to `rule_exclusions` for `baseline:personal-data` in the config, in its own change.

### `aidd validate` warns that the Spec links no authz doc

**Cause.** The required-docs matrix asks for an authorization matrix when both of these hold:

- a Task's scope touches an authentication or authorization path, one of the `baseline:auth` paths
- either the Spec's risk names security, or compliance is on, because `project.compliance` names a target or the profile is audited

**Fix.** Run `aidd new authz "<topic>" --spec <ID>`, and fill it in before Spec approval. [How do I…](HOW-TO.md#before-the-work) shows how. When the project grants and checks no access, set `docs.required.authz: "off"`.

### `aidd validate` refuses the config: a product default is off with no reason

**Cause.** `project.defaults.disabled` names a default with an empty reason, or a key that is not a default. Every product default is on unless a person turns it off. The reason is what tells the next reader, and the agents, that it was a decision.

**Fix.** Write the reason as the value, such as `off: {dark_mode: "a print-first report"}`. Or delete the key to turn the default back on, as [How do I…](HOW-TO.md#product-defaults-and-how-to-turn-one-off) explains.

### `aidd validate` warns that a design spec has no dark column

**Cause.** `dark_mode` is on, as it is by default, and the Screen inventory of a design spec the Spec links names no dark theme. No row or header says "dark".

**Fix.** Add the Theme column with `light, dark`, and the dark screenshots, `<screen>-<state>-<target>-dark.png`. When the product has one theme, turn `dark_mode` off with its reason in `project.defaults.disabled`.
### `aidd validate` warns that the Spec links no threat-model doc, though its risk names no security

**Cause.** Compliance is on, because `project.compliance` names a target or the profile is audited. And a Task's scope touches an authentication, authorization, secrets, or cryptography path, one of the `baseline:auth` and `baseline:secrets-crypto` paths. With compliance on, a change there gets a threat model whatever its risk says.

**Fix.** `aidd new threat-model <component> --spec <ID>` writes the component's living model, or links it again when an earlier Spec wrote it. Put this Spec's delta in the tech spec's `### Security and privacy` before Spec approval. To keep compliance on and drop this rule, set `docs.required.threat-model: "off"`. That turns off every threat-model warning, so the security engineer then asks for one by hand.

### `aidd validate` warns that a postmortem action is past its due date

**Cause.** A postmortem in review or published lists an `actions` item whose `due` date has passed and that is not `done: true`. This is problem management, so an action item nobody finishes is seen.

**Fix.** Finish the action, and record `done: true` with `tracked_in`, the Spec or ticket that carried it. Or have its owner set a new `due` date, with the reason in the postmortem.
