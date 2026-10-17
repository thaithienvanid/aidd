# CLI reference

Commands that work on a repository run from its root, wherever you start them. `--base` defaults to the remote default branch (`origin/HEAD`, then `origin/main`, `origin/master`, `main`, `master`). `aidd <command> --help` prints the same flags with a sentence each.

## Which command when

Seven commands cover a normal day, and they come first. The other commands do less frequent jobs. `aidd --help` lists the commands by group, and `aidd --help --all` also lists the commands for maintainers and harnesses.

<!-- aidd:gen cli:when -->
| Use | Command | When |
| --- | --- | --- |
| Every day | `aidd gate --paths` | before the first edit: see the route the planned paths need, its lane, and its first step (a Spec, or the fast lane) |
|  | `aidd new spec` | when the route needs a Spec: start the Spec from its template |
|  | `aidd hash --line`, or `aidd approve spec` | to get Spec approval: an Approver posts the line; with no platform, a person approves at the terminal |
|  | `aidd test` | once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file |
|  | `aidd gate` | before you ask for Merge approval: run every gate rule on this branch; CI runs it on every pull request or merge request |
|  | `aidd ship` | with no platform: merge a passing branch and record the Merge approval |
|  | `aidd list` | to see all open work and who holds each step; `--branch` for the change in hand |
| Now and then | `aidd init` | once in each repository: write the config, the skill, and the CI workflows |
|  | `aidd upgrade` | after you install a new aidd: bring the repository's aidd files up to it |
|  | `aidd self-update` | to update the CLI now; it also checks once a day by itself, after a command you run at a terminal |
|  | `aidd uninstall` | to remove aidd from a repository |
|  | `aidd doctor` | after `init` or `upgrade`, or when something looks wrong: check the wiring |
|  | `aidd extensions` | to see which plugins from aidd's registry fit this repository, and the line a person runs to install each (`suggest`) |
|  | `aidd standard` | to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`) |
|  | `aidd stack` | to adopt a set of opinionated standards that go together, such as `python-cli` (`add`) |
|  | `aidd log` | to read one Spec's history: its status changes, its approvals, and its Assisted-by trailers |
|  | `aidd owners` | to see who decides and who does the work in the repository; `--changed` lists only the standards and project rules for some paths |
|  | `aidd worktrees` | to see what each worktree holds and whether it is merged or stale, and to remove the merged ones (`clean`) |
|  | `aidd metrics` | every week, or at a retrospective: see where changes wait, the DORA metrics, and agent autonomy |
|  | `aidd digest` | for a status report since a date or a tag: for the team, or for a client (`--client`) |
|  | `aidd new <kind>` | to start other work or a document: an Epic, an Initiative, a Proposal, an exploration, an ADR, a runbook |
|  | `aidd import` | to start from a plan in another planning tool, or from tracker issues |
|  | `aidd describe` | on the fast lane: print the Change Request block for the change description |
|  | `aidd revise` | when an approved Spec turns out wrong before it ships: record why and reopen it for its owners and a new approval |
|  | `aidd proposal` | to make a proposal's tables (`matrix`), or to turn an accepted proposal into an Initiative and Epics (`convert`) |
|  | `aidd explore` | when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it) |
|  | `aidd validate` | to check the whole repository, or the files you name |
|  | `aidd record` | to check an agent change record (`verify`), or to export gate records and events (`export`) |
|  | `aidd autopilot` | run the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide |
|  | `aidd context` | experimental: before a role's step, list what it reads by path, with a token estimate each |
|  | `aidd goal` | once you agree to a plan: open the goal branch of each small goal that ships batched |
|  | `aidd integrate` | on a goal: once a Spec is verified and reviewed, land its branch in the goal branch (the release asks the person) |
|  | `aidd sync` | on a goal: after a sibling Spec integrates, or the default branch moves, merge the newer work in |
|  | `aidd observe` | after a release: watch a Spec's rollback trigger, or a metric's control band |
|  | `aidd release-notes` | at a release: write the release notes from the Specs that shipped |
| Maintainers and harnesses | `aidd eval` | maintainers: run the example suite, the agent evals, or the standards check |
|  | `aidd mcp` | harnesses: serve aidd to agents as MCP tools; `aidd init` wires it |
|  | `aidd hook` | harnesses: the agent hooks that `aidd init` wires; you do not run them yourself |
|  | `aidd gen-docs` | maintainers: after a change to a schema or to the help, regenerate the generated blocks |
<!-- aidd:end -->

## Commands

The table is generated from the CLI's own argument parser, so it lists every command and flag the installed version has. `aidd --help` groups the same commands by what you are doing: **Setup**, **Understand**, **Author**, **Decide**, **Check**, **Autopilot**, and **Operate**. It hides the commands for **maintainers and harnesses** (`eval`, `mcp`, `hook`, `gen-docs`); `aidd --help --all` lists them too, and they work either way.

<!-- aidd:gen cli:commands -->
| Command | What it does | Flags |
| --- | --- | --- |
| `init` `[path]` | adopt aidd in a repository | `--dry-run`, `--profile solo\|team\|org\|audited` (default `team`), `--ci github\|gitlab\|none` (default `github`), `--ref SHA_OR_TAG`, `--approvers WHO ...`, `--specialist POOL=WHO` (repeatable), `--test COMMAND`, `--goal SENTENCE`, `--team`, `--agent-hooks`, `--no-agent-hooks`, `--harness AGENT` (repeatable), `--claude-plugins`, `--mods`, `--enforce`, `--policy COMMAND`, `--devcontainer`, `--compliance-target soc2\|iso27001\|gdpr\|hipaa\|pci-dss\|fedramp\|other` (repeatable), `--security-ci`, `--link DIR` (repeatable), `--no-skill`, `--force` |
| `upgrade` `[path]` | bring a repository's aidd files up to this aidd: the skill, the team files, the CI pins, and aidd_version; a dry run unless --yes | `--ref SHA_OR_TAG`, `--yes` |
| `self-update` | update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line installer), from the release's wheel once it matches the release's SHA256SUMS (and its build provenance, with gh); once a day after a command a person runs at a terminal, aidd says when a release is out, never in CI, an agent's shell, or a hook (AIDD_NO_AUTO_UPDATE=1 turns that off; AIDD_AUTO_UPDATE=1 installs it instead) | `--check`, `--main` |
| `uninstall` `[path]` | reverse `aidd init`: list what it would remove, or remove it with --yes | `--yes`, `--link DIR` (repeatable) |
| `doctor` `[path]` | check that a repository is wired correctly | `--autopilot`, `--json` |
| `extensions` `suggest` | suggest the plugins from aidd's registry that fit this repository's stacks and the roles that use them, each with its tier, what it can touch, its pin, and the line a person runs to install it; it installs nothing | `--role ROLE`, `--json` |
| `standard list` | the open choices and the library standards, with the company's policy and what this repository has | `--json` |
| `standard add` `ID ...` | copy library standards into this repository, all or nothing: each file into docs/standards/, a `standards` entry that records its id, aidd's version, and its hash, and its `tests` (std.<group>.<topic>.<name>) | none |
| `stack list` | the library's stacks and their standards | `--json` |
| `stack add` `NAME` | copy one stack's standards into this repository and merge its `project.stack` entries | none |
| `list` `[REPO ...]` | all open work, one copy of each item from the base branch and every open branch, with its derived status, its next step, and who holds it: the agent, the author, an Approver, a triager, or a decision maker; --branch shows only this branch's change | `--json`, `--mine`, `--agent [ROLE]`, `--blocked`, `--waiting-on-me`, `--label LABEL`, `--priority LEVEL`, `--branch`, `--html [PATH]`, `--upkeep`, `--events PATH` (repeatable) |
| `log` `spec` | one Spec's history from git: status transitions with time in state, approvals, and Assisted-by trailers | `--record PATH` (repeatable), `--json` |
| `owners` | who decides and who does the work: the Approvers, the specialist Approver pools, and every agent role | `--json`, `--changed PATH ...` |
| `worktrees` `[clean]` | every worktree of this repository: its work item, its state (active, new, merged, stale, uncommitted work, missing), its loop, and its AIDD_WORKTREE name; clean removes the missing and the merged ones, after a person's yes | `--json`, `--dry-run` |
| `metrics` `[events ...]` | summarize gate events | `--tenant TENANT`, `--guard [PATH]`, `--since DATE`, `--by repo\|org\|team\|profile\|route\|author`, `--target-wait MINUTES`, `--autonomy`, `--dora`, `--flaky`, `--specs DIR`, `--cost LEDGER`, `--suggest-standard-changes`, `--autopilot`, `--render NAME`, `--json` |
| `digest` | a status rollup since a date or a git ref, from what aidd already knows: what shipped, what is in progress, who it waits on, what is blocked, the risks, the overdue items, feedback themes, and the gate metrics; --client for the client's view: a RAG status with its rules, milestones, what shipped in plain words, what we need from them, and next steps | `--since DATE_OR_REF`, `--client`, `--events PATH ...`, `--cost LEDGER`, `--include-cost`, `--blocked-days N` (default `5`), `--html [PATH]`, `--json` |
| `new` `spec\|epic\|initiative\|proposal\|runbook\|postmortem\|tech-spec\|test-plan\|adr\|threat-model\|authz\|design-spec\|api\|slo\|compliance\|analytics\|migration\|acceptance\|feedback\|design-system\|architecture\|data-map\|vendors\|glossary\|agents\|contract\|exploration` `[id]` | create a Spec, Epic, Initiative (a solo founder's brief too), Proposal, runbook, postmortem, or feedback log from the template; or a document a Spec links (tech-spec, test-plan, adr, threat-model, authz, design-spec (--prototype for its HTML prototype), api, slo, compliance, analytics, migration, acceptance), written from its template and added to the Spec's `docs`; or the repository's one design-system (DESIGN.md, design/tokens.json, and design/build.mjs), architecture overview (docs/architecture/README.md), data-map, vendors register, or glossary (docs/GLOSSARY.md); or a proposal's contract, then each change order (`aidd new contract <proposal id>`); or an exploration (`aidd new exploration <folder> --title <question>`), rendered by `aidd explore` | `--title TITLE`, `--route normal\|major\|emergency`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--paths PATH ...`, `--dimension data\|security\|privacy\|financial\|compliance\|availability\|third_party\|cost` (repeatable), `--irreversible`, `--force`, `--full`, `--base BRANCH`, `--owner-team OWNER_TEAM`, `--parent PARENT`, `--audience client\|internal` (default `client`), `--addressee ADDRESSEE`, `--spec SPEC`, `--area AREA`, `--no-link`, `--prototype`, `--owner OWNER`, `--timebox TIMEBOX` (default `45 minutes`) |
| `import` `speckit\|openspec\|kiro\|bmad\|issues` `[path]` | write a short Spec from another planning tool's files (Spec Kit, OpenSpec, Kiro, BMAD): Intent, Acceptance ids, Tasks with the paths it names, and the computed route; it links the plan instead of copying it. `issues`: one suggested Spec per new issue of a tracker (--github or --file), its text quoted as data, waiting for a person's triage; an issue already imported is skipped | `--github OWNER/REPO`, `--file PATH`, `--label LABEL`, `--limit N`, `--id ID`, `--out DIR`, `--title TITLE`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` |
| `describe` | print the Change Request block that describes the current branch's change, with the reasons for its route | `--base BASE`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance`, `--commit` |
| `revise` `spec` `why` | reopen an approved Spec: record what was wrong (`revisions` in its front matter), which voids its approval, so its owners change the Spec, its tests, its design files, and its frozen docs, and the next Spec approval freezes them again | none |
| `test` | run the tests (green on head, red on base) and write evidence | `--base BASE`, `--spec SPEC`, `--body-file BODY_FILE`, `--out OUT` (default `.aidd/evidence`), `--no-red`, `--red-in-place`, `--pass-env NAME` (repeatable), `--changed`, `--watch`, `--interval SECONDS` (default `1.0`), `--merge-group` |
| `proposal` `matrix\|convert\|decide\|sign-off` `file` `[go\|no-go]` | a proposal's tables for the document you send (matrix), an accepted proposal as an Initiative and Epics (convert), or a person's go/no-go (decide) and sign-off (sign-off), asked at their terminal | `--reason REASON`, `--by IDENTITY`, `--show`, `--confirmed DECISION|HASH`, `--confirmed-in WHERE` (default `claude-code`) |
| `hash` `spec` | print the Spec hash of a Spec and its frozen test and design files, or the approval line an Approver posts; for a proposal, the hash its sign-off records | `--ref REF` (default `HEAD`), `--worktree`, `--line`, `--summary`, `--html`, `--out PATH` |
| `approve` `[spec\|merge\|all\|stop]` `[spec]` `[SPEC ...]` | local-first: record a person's Spec approval or Merge approval on this machine, with no platform | `--base BASE`, `--ref BRANCH_OR_COMMIT` (default `HEAD`), `--show`, `--confirmed HASH_OR_HEAD`, `--confirmed-in WHERE` (default `claude-code`), `--evidence EVIDENCE`, `--skip-cooloff`, `--auto-merge`, `--but-major`, `--until YYYY-MM-DD` |
| `explore` `folder` | render an exploration's one comparison page: two or three divergent directions side by side (stacked on a phone), the trade-offs under each, each round's screenshots beside the round before with the feedback each change answers, and a choice to copy. The page records nothing and approves nothing: the owning role writes the pick and its reason in the Spec's Design section, DESIGN.md, or an ADR | `--out PATH` |
| `gate` `[github\|gitlab]` | run every gate rule: locally as a preflight, in CI for a platform, or against any context; before any code, --paths forecasts the route of planned paths | `--context CONTEXT`, `--base BASE`, `--spec SPEC`, `--body-file BODY_FILE`, `--approvals APPROVALS`, `--evidence EVIDENCE` (default `.aidd/evidence/evidence.json`), `--no-policy`, `--markdown`, `--json`, `--mode enforce\|advisory`, `--dry-run`, `--pending-ok`, `--post-status`, `--resolve`, `--record PATH`, `--events PATH`, `--explain RULE`, `--paths GLOB ...`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance`, `--dimension data\|security\|privacy\|financial\|compliance\|availability\|third_party\|cost` (repeatable), `--irreversible`, `--html [PATH]` |
| `validate` `[paths ...]` | validate files or directories; with none, the whole repository, including overdue emergency reviews | `--json` |
| `record verify` `SHA\|PATH` | check an agent change record (the in-toto statement `aidd gate --record` writes): its subject, tenant, decision, and human approvals, and, with --bundle or --online, its signature through `gh attestation verify` | `--dir DIR` (default `.aidd/evidence`), `--sha SHA`, `--tenant TENANT`, `--bundle PATH`, `--online`, `--repo OWNER/NAME`, `--signer-workflow WORKFLOW`, `--default-branch BRANCH`, `--allow-unsigned` |
| `record preview` `SHA` | list what the verifier saved under <evidence>/preview/<head-sha>/ in its artifacts.json, each file with its kind and SHA-256, so the Merge approval page shows it; aidd writes the list, so the verifier stays read-only | `--dir DIR` (default `.aidd/evidence`) |
| `record export` `records\|events` `PATH ...` | export gate records or gate events as JSON or CSV, deterministically, for a log store or a spreadsheet | `--since DATE`, `--format FORMAT` (default `json`), `--tenant TENANT`, `--out DIR`, `--by-control` |
| `autopilot start` | start autopilot on a piece of work for a session; a live lease of another session refuses it, a stale one is replaced, and starting again after the run ended (a plan ready, a limit, nothing open) begins a new run | `--work WORK` (default `all`), `--session ID`, `--timebox DURATION` |
| `autopilot next` | the one next action, decided by the engine from the open work, the step-to-flow map, the lease and journal, and the autopilot limits: run a team command, ask a person (with the decision page), or stop (with why); a stop for a person lists every decision that waits, how to take each, and the command that goes on | `--work WORK`, `--session ID` (required), `--ask TEXT`, `--json` |
| `autopilot note` `NOTE` | record a step's result in the journal, as "<code> <result>", with the head it ran on; the result is ok, fail, waiting, or blocked | `--session ID` (required), `--spec ID`, `--tokens N`, `--cost AMOUNT`, `--currency CODE`, `--ask TEXT` |
| `autopilot status` | print every lease, whether its timebox ended, and the journal's last lines | `--json` |
| `autopilot stop` | stop autopilot: remove the session's lease | `--session ID` (required) |
| `context` `spec` | experimental: the minimal context pack for a step of a Spec, as paths with a one-line reason and a token estimate each: the summary, the Task, the linked docs, the exemplar Specs on the Specify step, the latest handoff note, and the standards for its paths. It never prints a file's contents | `--role ROLE`, `--step CODE`, `--json` |
| `ship` | local-first: merge the current branch into the base branch once the gate passes, keeping its history or squashing it | `--base BASE`, `--squash`, `--message MESSAGE`, `--body-file BODY_FILE`, `--out OUT` (default `.aidd/evidence`), `--pass-env NAME` (repeatable), `--skip-cooloff`, `--show`, `--confirmed HEAD`, `--confirmed-in WHERE` (default `claude-code`) |
| `goal` `open\|list` `[EPIC_ID]` | open the goal branch, goal/<EPIC>, of a small goal that ships batched, cut from the default branch once the plan holding the Epic is there; or list each goal and the branches with unmerged work, from git alone | `--json` |
| `integrate` | the team's step: merge this Spec's branch into its goal branch (the Spec's `base: goal/<name>`) as a merge commit, once its approval holds, its tests pass on the merged tree, and the gate against the goal waits only for the release decisions; no person is asked, as the goal's release to the default branch proves each Spec again | `--goal BRANCH`, `--undo SPEC_ID`, `--out OUT` (default `.aidd/evidence`), `--pass-env NAME` (repeatable) |
| `sync` | merge newer work in, never rebasing: the goal branch into a Spec's branch cut from it, and the default branch into a goal branch or any other branch, daily; a conflict merges nothing and lists the files | `--from BRANCH` |
| `observe` `SPEC\|SERIES` | after release: run a Spec's observe command once, or poll it for the observe window (--window); exit 0 healthy (the window ended with the rollback trigger never firing), 1 unhealthy (the trigger fired), 2 error. It never rolls back. With --band METRIC, judge a metric series against its control band instead (no model); exit 1 when an agent may diagnose or suggest a change | `--window [DURATION]`, `--every DURATION` (default `5m`), `--consecutive N` (default `1`), `--write [SPEC_ID]`, `--timeout TIMEOUT` (default `600`), `--pass-env NAME` (repeatable), `--band METRIC`, `--baseline N`, `--diagnose-sigma DIAGNOSE_SIGMA`, `--propose-sigma PROPOSE_SIGMA`, `--json` |
| `release-notes` | release notes from the Specs shipped since a tag or a date: each one's title, intent, and flags, grouped as Added, Changed, Deprecated, Removed, Fixed, and Security (Keep a Changelog), for users or for developers | `--since TAG_OR_DATE` (required), `--audience users\|developers` (default `users`), `--json` |
| `eval` `examples\|routing\|roles\|standards\|packs\|tasks\|report` `[PATH ...]` | run the example suite, an agent routing eval, the role evals, the standards check, the pack and practice template check, or your own agent tasks; report recorded runs | `--root ROOT`, `--scenarios SCENARIOS`, `--cmd CMD`, `--no-embed`, `--min-accuracy MIN_ACCURACY` (default `0.9`), `--repeat K` (default `1`), `--control`, `--record PATH`, `--model-label TEXT`, `--max-days MAX_DAYS`, `--online`, `--strict`, `--due DAYS`, `--unreviewed`, `--json`, `--timeout SECONDS` (default `15.0`), `--max-seconds SECONDS` (default `600.0`), `--max-bytes N` (default `3000000`), `--concurrency 1\|2` (default `2`), `--materialize DIR` |
| `mcp` | serve aidd to agents as MCP tools over stdio (check_edit, validate, approval_line, approve_spec, approve_merge, ship, and approve_all, which ask the person in the client's own dialog, describe, and gate, which also forecasts the route of planned paths) | none |
| `hook` `pre-tool\|pre-edit\|session-start\|prompt-submit\|stop\|pre-compact` | agent harness hooks; pre-tool (pre-edit, its earlier name, still works) reads a Claude Code PreToolUse event and denies edits outside the active Spec; session-start adds this change's route and next steps to a new session; prompt-submit adds the next step to each prompt (UserPromptSubmit); stop reminds the agent to run `aidd test` (Stop and SubagentStop); pre-compact saves the state of the work in the git directory | none |
| `gen-docs` | maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills | `--check` |
<!-- aidd:end -->

What the table cannot say:

- **`init`** writes the config, the skill, `AGENTS.md`, the CI workflows, and the PR template, and wires every coding agent it detects ([INSTALL.md](INSTALL.md#your-coding-agent)). Every profile needs someone in `owners.approvers`, or no change can merge, so every profile except `solo` needs `--approvers`. Under `solo`, init names you when you leave it out. It uses your GitHub login, found in the local configuration, or else the email your commits use. The gate starts in advisory mode unless `--enforce`.
- **`validate`** with no paths checks the whole repository, including overdue emergency reviews. It warns, without failing, when a Spec has leftover TODO placeholders, or when a normal or major Spec has no Intent. It also warns, without failing, when a major Spec has no diagram (or little Design prose), no Alternatives, or no Pre-mortem. A normal Spec written from the short template (`aidd new spec` without `--full`) validates with no warning once its TODOs are filled.
- **`gate --paths GLOB...`** (with `--type`, `--dimension`, `--irreversible`) gives a change's route before the first edit. A change's route is a property of the change. aidd computes the minimum from what it touches, the author may declare higher, and the gate enforces the higher of the two. The lane follows from the route. It prints the route as a header ("Route: normal (spec lane), needed by the planned paths (1 path)") with the reasons, then the lane's first step. It records nothing. On the branch, `gate` computes the route again from the real diff, and prints it with the reasons and the other branches whose Specs change the same code. Before any code, **`new spec --paths`** computes the same route, and writes it and the Task's scope. When the fast lane needs no Spec, it writes nothing, says so on stderr, and exits 1 (`--force` writes one anyway). **`describe`** prints the same reasons above its block, and a local **`gate`** prints the route it computed from the diff.
- **`list`** shows all open work: one copy of every item, from the base branch and every open branch. Each item has its derived status, its next step, and who holds it (the agent, the author, an Approver, a triager, or a decision maker). Which change to work on is a person's choice. `--mine` keeps your own work, `--waiting-on-me` is the Approver inbox, and `--agent [ROLE]` keeps the Tasks an agent may start. `--blocked`, `--label`, and `--priority` narrow it further. `--branch` keeps only this branch's change: the steps of the Specs it changes, read from the working tree, and the other branches that change the same code. Several REPO paths list a project in several repositories.
- **`list --upkeep`** lists the upkeep that is due instead of the open work. That is library standards past review, flags past `cleanup_due`, open emergency backfills, and flaky tests (from the gate events `--events` names). It is also waivers ending within 30 days, runbooks past their drill, and doctor warnings. Each item names the command or skill that takes it. `--json` prints `{schema_version, items}` (`schemas/upkeep.schema.json`). `/aidd-team:maintain` runs it on a rhythm.
- **`describe`** prints the Change Request block for the branch's change. With `--commit`, it records the block in an empty commit on the branch, for a local ship with no PR/MR description.
- **`hash --line`** prints the whole approval line, including the commit, which proves Spec approval came before implementation. `--summary` prints what the Spec hash approves on one phone screen first.
- **`gate`** runs three ways. With no platform, it is a local preflight of the branch. The preflight is untrusted: it cannot see real approvals, so `--approvals` supplies a dry-run file. With `--context`, it judges a context file from any CI. With `github` or `gitlab`, it is the CI entry point that gathers a trusted context and posts `aidd/gate`.
- **`record verify`** checks an agent change record: its subject, tenant, decision, and human approvals, and, with `--bundle` or `--online`, its signature. **`record export`** writes gate records or events as JSON or CSV.
- **`list --json`** prints `{schema_version, steps}` for scripts (`{schema_version, repos}` for several repositories), and **`standard list --json`** and **`stack list --json`** carry `schema_version` too; **`gate --paths --json`** prints `{schema_version, route, steps, overlaps}` with the same steps (`schemas/forecast.schema.json`), and **`gate --json`** prints the decision record (`schemas/record.schema.json`) with `schema_version` and nothing else. A Spec's step also lists its Tasks under `tasks`, each with `id`, `title`, `scope`, `depends_on`, `skills` and `role` when the Spec names them, and `status`. The `status` is `todo`, `in_progress`, `blocked` with `why` and any `waiting_on`, `stopped`, or `done`. `todo` is the one an agent may start, so a coordinator can start one agent per todo Task ([How do I…](HOW-TO.md#many-agents-at-once)).
- **`observe`** runs the Spec's observe command once, with the environment below. With `--window`, it runs the command every `--every` until the Spec's window ends, and stops when the rollback trigger fires. It never rolls back. With `--band METRIC SERIES`, it judges a metric series against its control band instead (`--baseline N` values make the baseline). With `--write`, it turns a breach into a draft Spec for a person to triage.
- **`aidd explore FOLDER`** renders an exploration's comparison page into `.aidd/views/explore-<folder>.html`. The page shows the directions side by side with their trade-offs, the rounds, and a choice to copy. `aidd new exploration FOLDER --title "..."` writes `exploration.md` from its template first, and never overwrites one. Its front matter follows `schemas/exploration.schema.json`.
- **`autopilot`** runs the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide ([METHOD §5.3](METHOD.md#53-autopilot)). The autopilot command starts it with `aidd autopilot start --work SPEC-1`, which prints the session id. Then, each turn, it runs `aidd autopilot next --session ID --json` and does what the action says. After that, it records the result with `aidd autopilot note "<code> <result>" --session ID`. It ends with `aidd autopilot stop`. `aidd autopilot status` shows the lease and the journal. `aidd autopilot next --json` prints `{action, why, code, ...}` (`schemas/autopilot-next.schema.json`): `run` with the team command, `ask` with who decides and the decision page, or `stop` with the reason.
- **`context`** is **experimental**. `aidd context SPEC-1 --role developer` lists what a step reads, by path, with a token estimate each. It never prints a file's contents, and it never reads a path outside the repository.
- **`list --html`** writes the decision page: every listed step, a person's decisions first, each with how to decide it and the command for its own page. With `--waiting-on-me`, the page holds every decision waiting on you. Like every view, it never approves.
- **`doctor --autopilot`** checks what aidd can see of an autopilot run's settings, and prints the `permissions.allow` rules a run needs that the settings lack. It also says whether an advisor (`advisorModel`) is configured, as information only. Then it lists what only you can check, such as the sandbox and the permission mode.
- **`hook`** runs one Claude Code hook. The aidd plugin and `aidd init --agent-hooks` wire them. `pre-tool` is the guard, with `agents.delegate`. `session-start` briefs the agent, `prompt-submit` adds the next step to each prompt, `stop` reminds the agent to run `aidd test`, and `pre-compact` saves the state of the work in the git directory.
- **`gen-docs`** regenerates every `aidd:gen` block in the Markdown files, the skill's references, and the domain-pack skills. With `--check` it changes nothing and fails when any is stale, or when a generated table would have no rows.

## Exit codes

| Command | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| `gate` (local or `--context`) | pass | fail | error | pending |
| `gate github` | posted (pass or pending; advisory always) | fail | error (an `error` status is posted) | |
| `gate gitlab` | pass (pending with `--pending-ok`; advisory always) | fail, pending, or a stale pipeline | error | |
| `record verify` | the change record holds and is signed (or unsigned with `--allow-unsigned`) | it does not hold, its signature does not verify, or it is unsigned | error (no such record) | |
| everything else | success | a check failed | error | |

A crash is always 2, never 1.

The two CI entry points differ on pending on purpose. On GitHub, the control is the posted `aidd/gate` status, which a ruleset or branch protection requires from the gate App. The job's exit code is not the control. A pull request that waits for a person is not a failed job, so pending exits 0. A failure still exits 1 in enforce mode. On GitLab the job itself is the check a merge request waits for, so pending fails it unless `--pending-ok`. Where the platform cannot require a status, as on a private repository on GitHub Free, nothing blocks a merge on GitHub. The gate reports, and a person reads it.

## The approvals file

`gate --approvals` takes the context format, for local dry runs:

```json
{"comments": [{"user": "bob", "body": "/aidd approve-spec SPEC-1 <hash> <commit>"}],
 "reviews": [{"user": "bob", "state": "approved", "commit_sha": "<head sha>"}]}
```

## Environment variables

Every variable aidd reads, and every variable it sets for your Policy and Observe commands. A test fails when the code reads an `AIDD_*` variable this table does not list.

<!-- aidd:gen cli:env -->
| Variable | Read by | Meaning |
| --- | --- | --- |
| `AIDD_MODE` | `aidd gate github` and `aidd gate gitlab` | `enforce` when neither the base config's `mode` nor `--mode` sets one (the default either way): any job or pipeline can set an environment variable, so it can never relax the gate. On GitHub the reusable workflow passes its `mode` input as `--mode`; on GitLab only `mode: advisory` in the base config makes the gate advisory |
| `AIDD_PROTECTED_BRANCHES` | `aidd gate github` | extra protected bases besides the default branch, comma-separated, globs allowed |
| `AIDD_ORG_PRESET` | every command that loads the config (the gate, `test`, `doctor`, `validate`, the guard) | path to an org preset file, applied as the root parent of the repository config |
| `GITHUB_TOKEN` | `aidd gate github`, `aidd eval standards --online` | the token for the GitHub API (the App installation token in the reusable workflow; for the online standards check, a read-only token sent to api.github.com alone) |
| `AIDD_GITLAB_TOKEN` | `aidd gate gitlab` | the token for the GitLab API (`read_api`; `api` with `--post-status`) |
| `AIDD_SPEC` | `aidd hook pre-tool`, `aidd mcp` | the active Spec, when a branch changes more than one |
| `AIDD_WORKTREE` | your test commands (set by `aidd test`), `project.dev_services.teardown` (set by `aidd worktrees clean`) | a stable name for the worktree, such as `shop_3f9a1c`: name the database, bucket, and ports each worktree uses in the shared dev stack by it |
| `AIDD_HOOK_OFFLINE` | `aidd hook pre-tool`, the session hooks | `1` makes the guard skip network fetches of `extends` parents, and the session hooks skip the doctor's network checks; the aidd plugin's hook and the session hooks set it |
| `AIDD_HOOK_FAIL_CLOSED` | `aidd hook pre-tool`, the guard hook `aidd init` writes, the plugin's hook launcher | `1` blocks when the guard cannot run, crashes, or runs past its deadline, and denies a shell command it cannot parse, only in a repository with `.aidd/config.yaml`. An organization sets it in its managed settings; a project needs no variable, since the audited profile does the same. Never set it in user settings |
| `AIDD_HELPERS_MAY_WRITE` | `aidd hook pre-tool` | `1`, in the environment Claude Code starts with, lets a subagent that is not an aidd-team role write; by default such a helper only reads |
| `AIDD_AGENT` | `aidd approve`, `aidd ship` | any value marks a shell started by an agent, so both refuse; set it in agent runners that set neither `CLAUDECODE` nor `CLAUDE_CODE_CHILD_SESSION` (Claude Code) nor `AI_AGENT`, which count the same |
| `AIDD_OFFLINE` | `aidd init`, `aidd upgrade`, `aidd doctor` | `1` keeps the CI files at the release tag instead of asking GitHub (`git ls-remote`) for the commit it names, when aidd runs from an installed wheel; it also skips the doctor's pin and branch-protection checks, which `aidd gate --paths`, `aidd list`, and `aidd digest` run too, and the daily update check |
| `AIDD_NO_AUTO_UPDATE` | every command run at a terminal | `1` turns off the daily note that a newer release is out; `aidd self-update` still works |
| `AIDD_SESSION_ID` | aidd's OpenCode plugin | not a variable: the word `${AIDD_SESSION_ID}` in a shell command, which the plugin replaces with the OpenCode session's id before the command runs, so `/aidd-autopilot` binds its lease to that session |
| `AIDD_AUTO_UPDATE` | every command run at a terminal | `1` lets the daily check install a newer release itself instead of only saying it is out, from the release's wheel once it matches the release's SHA256SUMS (and its build provenance, with gh); never the tip of main |
| `ORCA_PANE_KEY` | `aidd hook session-start`, `aidd hook stop` | set by Orca in the terminals it manages; this, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` means the hook runs inside Orca, so it puts this change's next step on the worktree's Orca card (`hooks.orca_status`). The guard never reads any of them |
| `ORCA_WORKTREE_ID` | `aidd hook session-start`, `aidd hook stop` | set by Orca, like `ORCA_PANE_KEY` |
| `ORCA_AGENT_HOOK_PORT` | `aidd hook session-start`, `aidd hook stop` | set by Orca, like `ORCA_PANE_KEY` |
| `ORCA_CLI_COMMAND` | `aidd hook session-start`, `aidd hook stop` | set by Orca in managed WSL sessions: the Orca CLI to call instead of `orca` |
| `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` | `aidd doctor --autopilot` | Claude Code's own switch: `1` turns its advisor off, so the doctor says a configured `advisorModel` does not apply |
| `AIDD_REF` | the one-line installer | the release tag or commit to install, such as `v1.0.0`; `aidd upgrade` names it in its upgrade hint |
| `AIDD_INPUT_FILE` | your Policy command (set by the gate) | path to a JSON file with `change_id`, `base_sha`, `head_sha`, `route`, `type`, `paths`, and `body` |
| `AIDD_CHANGE_ID` | your Policy command (set by the gate) | the PR/MR number, or the local ref |
| `AIDD_BASE_SHA` | your Policy command (set by the gate) | the base commit |
| `AIDD_HEAD_SHA` | your Policy command (set by the gate) | the head commit |
| `AIDD_ROUTE` | your Policy command (set by the gate) | the route the gate will enforce: the declared route, raised to what the diff requires |
| `AIDD_REQUIRED_ROUTE` | your Policy command (set by the gate) | the minimum route the changed paths, dimensions, and type require |
| `AIDD_TYPE` | your Policy command (set by the gate) | the declared change type |
| `AIDD_CHANGED_PATHS_FILE` | your Policy command (set by the gate) | path to a file listing the changed paths, one per line |
| `AIDD_SPEC_ID` | your Observe command (set by `aidd observe`) | the Spec's `id` |
| `AIDD_WINDOW` | your Observe command (set by `aidd observe`) | the Spec's `observe.window` |
| `AIDD_ROLLBACK_TRIGGER` | your Observe command (set by `aidd observe`) | the Spec's `observe.rollback_trigger` |
| `AIDD_NOTICE` | your `autopilot.notify` command (set by `aidd autopilot next`) | the stop message, also passed as the command's last argument |

Stripped from the environment of every test, Policy, and Observe command: `GITHUB_TOKEN`, `GH_TOKEN`, `AIDD_GITLAB_TOKEN`, `CI_JOB_TOKEN`, `ACTIONS_RUNTIME_TOKEN`, `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.
<!-- aidd:end -->

One more belongs to `install.sh` alone ([INSTALL.md](INSTALL.md#the-cli)): `AIDD_SHA256`, when set, checks the downloaded wheel before installing it. `AIDD_REF`, in the table above, takes a `vX.Y.Z` tag or a commit SHA. A tag installs that version's wheel from PyPI (until aidd is published there, only with `AIDD_SHA256` set). A commit SHA builds from source, for testing unreleased code only. The GitLab template reads no install variable: its aidd pin is written in the file ([PLATFORMS.md](PLATFORMS.md#setup-on-gitlab)).
