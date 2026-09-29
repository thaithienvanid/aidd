# CLI reference

Commands that work on a repository run from its root, wherever you start them. `--base` defaults to the remote default branch (`origin/HEAD`, then `origin/main`, `origin/master`, `main`, `master`). `aidd <command> --help` prints the same flags with a sentence each.

## Commands

The table is generated from the CLI's own argument parser, so it lists every command and flag the installed version has.

<!-- aidd:gen cli:commands -->
| Command | What it does | Flags |
| --- | --- | --- |
| `init` `[path]` | adopt aidd in a repository | `--dry-run`, `--profile solo\|team\|org\|regulated` (default `team`), `--ci github\|gitlab\|none` (default `github`), `--ref SHA_OR_TAG`, `--approvers WHO ...`, `--reviewer POOL=WHO` (repeatable), `--test COMMAND`, `--goal SENTENCE`, `--team`, `--agent-hooks`, `--no-agent-hooks`, `--harness AGENT` (repeatable), `--claude-plugins`, `--enforce`, `--policy COMMAND`, `--devcontainer`, `--link DIR` (repeatable), `--no-skill`, `--force` |
| `upgrade` `[path]` | bring a repository's aidd files up to this aidd: the skill, the team files, the CI pins, and aidd_version; a dry run unless --yes | `--ref SHA_OR_TAG`, `--yes` |
| `uninstall` `[path]` | reverse `aidd init`: list what it would remove, or remove it with --yes | `--yes`, `--link DIR` (repeatable) |
| `doctor` `[path]` | check that a repository is wired correctly | none |
| `new` `spec\|epic\|initiative\|proposal\|runbook\|postmortem` `id` | create a Spec, Epic, Initiative, Proposal, runbook, or postmortem from the template | `--title TITLE` (required), `--route normal\|major\|emergency`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--paths PATH ...`, `--dimension data\|security\|privacy\|financial\|compliance\|availability\|third_party\|cost` (repeatable), `--irreversible`, `--force`, `--full`, `--owner-team OWNER_TEAM`, `--parent PARENT`, `--audience client\|internal` (default `client`), `--addressee ADDRESSEE`, `--spec SPEC` |
| `import` `speckit\|openspec\|kiro\|bmad` `path` | write a short Spec from another planning tool's files (Spec Kit, OpenSpec, Kiro, BMAD): Intent, Acceptance ids, Tasks with the paths it names, and the computed route; it links the plan instead of copying it | `--id ID`, `--out DIR`, `--title TITLE`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` |
| `validate` `[paths ...]` | validate files or directories; with none, the whole repository, including overdue emergency reviews | none |
| `hash` `spec` | print the approval hash of a Spec and its frozen test and design files | `--ref REF` (default `HEAD`), `--worktree`, `--comment`, `--digest` |
| `change` | print a starting toml aidd block for the current branch | `--base BASE`, `--type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` |
| `test` | run the tests (green on head, red on base) and write evidence | `--base BASE`, `--spec SPEC`, `--body-file BODY_FILE`, `--out OUT` (default `aidd-evidence`), `--no-red`, `--red-in-place`, `--pass-env NAME` (repeatable), `--changed`, `--watch`, `--interval SECONDS` (default `1.0`), `--merge-group` |
| `gate` `[github\|gitlab]` | run every gate rule: locally as a preflight, in CI for a platform, or against any context | `--context CONTEXT`, `--base BASE`, `--spec SPEC`, `--body-file BODY_FILE`, `--approvals APPROVALS`, `--evidence EVIDENCE` (default `aidd-evidence/evidence.json`), `--no-policy`, `--markdown`, `--mode enforce\|advisory`, `--dry-run`, `--pending-ok`, `--post-status`, `--resolve`, `--record PATH`, `--events PATH`, `--explain RULE` |
| `metrics` `[events ...]` | summarize gate events | `--tenant TENANT`, `--guard PATH`, `--since DATE`, `--by repo\|owner\|team\|profile\|route\|author`, `--target-wait MINUTES`, `--autonomy`, `--dora`, `--specs DIR`, `--cost LEDGER`, `--propose`, `--render NAME`, `--json` |
| `eval` `examples\|routing\|roles\|standards\|tasks\|report` `[PATH ...]` | run the example suite, an agent routing eval, the role evals, the standards currency check, or your own agent tasks; report recorded runs | `--root ROOT`, `--scenarios SCENARIOS`, `--cmd CMD`, `--no-embed`, `--min-accuracy MIN_ACCURACY` (default `0.9`), `--repeat K` (default `1`), `--control`, `--record PATH`, `--model-label TEXT`, `--max-days MAX_DAYS` (default `365`), `--materialize DIR` |
| `observe` `spec` | run a Spec's observe command once after release, or poll it for the observe window (--window); exit 0 healthy (the window ended with the rollback trigger never firing), 1 unhealthy (the trigger fired), 2 error. It never rolls back | `--window DURATION`, `--every DURATION` (default `5m`), `--consecutive N` (default `1`), `--write`, `--timeout TIMEOUT` (default `600`), `--pass-env NAME` (repeatable) |
| `proposal` `matrix\|convert` `file` | a proposal's tables for the document you send (matrix), or an accepted proposal as an Initiative and Epics (convert) | none |
| `approve` `spec\|merge` `[spec]` | local-first: record a person's Spec approval or Merge approval on this machine, with no platform | none |
| `ship` | local-first: merge the current branch into the base branch once the gate passes, keeping its history or squashing it | `--base BASE`, `--squash`, `--message MESSAGE`, `--out OUT` (default `aidd-evidence`), `--pass-env NAME` (repeatable) |
| `next` `[REPO ...]` | what to do now in this repository, and who does it: you, your agent, or an Approver; it starts every change with the route and lane computed for the branch's diff | `--json`, `--all`, `--mine`, `--agent ROLE`, `--blocked`, `--waiting-on-me`, `--label LABEL` |
| `log` `spec` | one Spec's history from git: status transitions with time in state, approvals, and Assisted-by trailers | `--record PATH` (repeatable), `--json` |
| `owners` | who decides and who does the work: the approvers, the specialist pools, and every agent role | `--json`, `--changed PATH ...` |
| `watch` `series` | judge a metric series against its control band (no model); exit 1 when an agent may diagnose or propose | `--metric METRIC` (required), `--window WINDOW`, `--diagnose-sigma DIAGNOSE_SIGMA`, `--propose-sigma PROPOSE_SIGMA`, `--write SPEC_ID`, `--json` |
| `mcp` | serve aidd to agents as MCP tools over stdio (next, check_edit, validate, hash, change, gate) | none |
| `hook` `pre-edit\|session-start\|stop\|pre-compact` | agent harness hooks; pre-edit reads a Claude Code PreToolUse event and denies edits outside the active Spec; session-start adds `aidd next` to a new session; stop reminds the agent to run `aidd test` (Stop and SubagentStop); pre-compact is a no-op | none |
| `gen-docs` | maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills | `--check` |
| `export` `records\|events` `PATH ...` | export gate records or gate events as JSON or CSV, deterministically, for a log store or a spreadsheet | `--since DATE`, `--format FORMAT` (default `json`), `--tenant TENANT`, `--out DIR` |
| `verify` `SHA\|PATH` | check an agent change record (the in-toto statement `aidd gate --record` writes): its subject, tenant, decision, and human approvals, and, with --bundle or --online, its signature through `gh attestation verify` | `--dir DIR` (default `aidd-evidence`), `--sha SHA`, `--tenant TENANT`, `--bundle PATH`, `--online`, `--repo OWNER/NAME`, `--signer-workflow WORKFLOW`, `--default-branch BRANCH`, `--allow-unsigned` |
<!-- aidd:end -->

What the table cannot say:

- **`init`** writes the config, the skill, `AGENTS.md`, the CI workflows, and the PR template, and wires every coding agent it detects ([INSTALL.md](INSTALL.md#your-coding-agent)). Every profile needs someone in `owners.approvers`, or no change can merge, so every profile except `solo` needs `--approvers`. Under `solo`, init names you when you leave it out: your GitHub login, found in the local configuration, or else the email your commits use. The gate starts in advisory mode unless `--enforce`.
- **`validate`** with no paths checks the whole repository, including overdue emergency reviews. It warns, without failing, when a Spec has leftover TODO placeholders, when a normal or major Spec has no Intent, and when a major Spec has no diagram (or little Design prose), no Alternatives, or no Pre-mortem. A normal Spec written from the short template (`aidd new spec` without `--full`) validates with no warning once its TODOs are filled.
- **`next`** starts every change: for the branch's diff it shows the computed route, its lane, and the reasons, before the open work. Before any code, **`new spec --paths`** computes the route from the planned paths, writes it and the Task's scope, and says when the fast lane needs no Spec (`--force` writes one anyway). **`change`** prints the same reasons above its block, and a local **`gate`** prints the route it computed from the diff.
- **`hash --comment`** prints the whole approval line, including the commit, which proves Spec approval came before implementation.
- **`gate`** runs three ways. With no platform, it is a local preflight of the branch (untrusted: it cannot see real approvals, so `--approvals` supplies a dry-run file). With `--context`, it judges a context file from any CI. With `github` or `gitlab`, it is the CI entry point that gathers a trusted context and posts `aidd/gate`.
- **`next --json`** prints the steps for scripts. A Spec's step also lists its Tasks under `tasks`: `id`, `title`, `scope`, `depends_on`, `skills` and `role` when the Spec names them, and `status` (`ready`, `blocked` with `why` and any `waiting_on`, or `done`), so a coordinator can start one agent per ready Task ([How do I…](HOW-TO.md#many-agents-at-once)).
- **`observe`** runs the Spec's observe command once, with the environment below. With `--window`, it runs the command every `--every` until the Spec's window ends, and stops when the rollback trigger fires. It never rolls back.
- **`gen-docs`** regenerates every `aidd:gen` block in the Markdown files, the skill's references, and the domain-pack skills. With `--check` it changes nothing and fails when any is stale, or when a generated table would have no rows.

## Exit codes

| Command | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| `gate` (local or `--context`) | pass | fail | error | pending |
| `gate github` | posted (pass or pending; advisory always) | fail | error (an `error` status is posted) | |
| `gate gitlab` | pass (pending with `--pending-ok`; advisory always) | fail, pending, or a stale pipeline | error | |
| `verify` | the change record holds and is signed (or unsigned with `--allow-unsigned`) | it does not hold, its signature does not verify, or it is unsigned | error (no such record) | |
| everything else | success | a check failed | error | |

A crash is always 2, never 1.

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
| `AIDD_MODE` | `aidd gate github` and `aidd gate gitlab` | `enforce` or `advisory` when neither the base config's `mode` nor `--mode` sets one (default `enforce`); on GitLab it can never relax the gate, so only `mode = "advisory"` in the base config makes it advisory |
| `AIDD_PROTECTED_BRANCHES` | `aidd gate github` | extra protected bases besides the default branch, comma-separated, globs allowed |
| `AIDD_ORG_PRESET` | every command that loads the config (the gate, `test`, `doctor`, `validate`, the edit-time guard) | path to an org preset file, applied as the root parent of the repository config |
| `GITHUB_TOKEN` | `aidd gate github` | the token for the GitHub API (the App installation token in the reusable workflow) |
| `AIDD_GITLAB_TOKEN` | `aidd gate gitlab` | the token for the GitLab API (`read_api`; `api` with `--post-status`) |
| `AIDD_SPEC` | `aidd hook pre-edit`, `aidd mcp` | the active Spec, when a branch changes more than one |
| `AIDD_HOOK_OFFLINE` | `aidd hook pre-edit` | `1` makes the edit-time guard skip network fetches of `extends` parents; the aidd plugin's hook sets it |
| `AIDD_HOOK_FAIL_CLOSED` | `aidd hook pre-edit`, the plugin's hook launcher | `1` (the regulated managed settings set it) blocks when the guard cannot run or crashes, and denies a shell command it cannot parse |
| `AIDD_HELPERS_MAY_WRITE` | `aidd hook pre-edit` | `1`, in the environment Claude Code starts with, lets a subagent that is not an aidd-team role write; by default such a helper only reads |
| `AIDD_AGENT` | `aidd approve`, `aidd ship` | any value marks a shell started by an agent, so both refuse; set it in agent runners that set neither `CLAUDECODE` nor `CLAUDE_CODE_CHILD_SESSION` (Claude Code) nor `AI_AGENT`, which count the same |
| `AIDD_OFFLINE` | `aidd init`, `aidd upgrade` | `1` keeps the CI files at the release tag instead of asking GitHub (`git ls-remote`) for the commit it names, when aidd runs from an installed wheel |
| `ORCA_PANE_KEY` | `aidd hook session-start`, `aidd hook stop` | set by Orca in the terminals it manages; this, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` means the hook runs inside Orca, so it puts `aidd next` on the worktree's Orca card (`[hooks] orca_status`). The edit-time guard never reads any of them |
| `ORCA_WORKTREE_ID` | `aidd hook session-start`, `aidd hook stop` | set by Orca, like `ORCA_PANE_KEY` |
| `ORCA_AGENT_HOOK_PORT` | `aidd hook session-start`, `aidd hook stop` | set by Orca, like `ORCA_PANE_KEY` |
| `ORCA_CLI_COMMAND` | `aidd hook session-start`, `aidd hook stop` | set by Orca in managed WSL sessions: the Orca CLI to call instead of `orca` |
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

Stripped from the environment of every test, Policy, and Observe command: `GITHUB_TOKEN`, `GH_TOKEN`, `AIDD_GATE_TOKEN`, `AIDD_GITLAB_TOKEN`, `CI_JOB_TOKEN`, `ACTIONS_RUNTIME_TOKEN`, `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.
<!-- aidd:end -->

One more belongs to `install.sh` alone ([INSTALL.md](INSTALL.md#the-cli)): `AIDD_SHA256`, when set, checks the downloaded wheel before installing it. `AIDD_REF`, in the table above, takes a `vX.Y.Z` tag, which installs that version's wheel from PyPI (until aidd is published there, only with `AIDD_SHA256` set), or a commit SHA, which builds from source, for testing unreleased code only. The GitLab template reads no install variable: its aidd pin is written in the file ([PLATFORMS.md](PLATFORMS.md#setup-on-gitlab)).
