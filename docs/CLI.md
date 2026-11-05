# CLI reference

Commands that work on a repository run from its root, wherever you start them. `--base` defaults to the remote default branch. aidd tries `origin/HEAD` first, then `origin/main`, `origin/master`, `main`, and `master`. `aidd <command> --help` prints the same flags with a sentence each.

## Which command when

Four commands cover a normal day, and they come first. Your agent runs them as it works, and you can too. `aidd --help` lists only those, `aidd help --all` lists every command by group, and `aidd help <command>` shows one command's arguments and flags.

<!-- aidd:gen cli:when -->
| Use | Command | When |
| --- | --- | --- |
| Every day | `aidd status` | to see the open work, and what waits on whom; `--mine` for what waits on you; with an id or a path, what stands behind it |
|  | `aidd risk --paths` | before the first edit: the route the planned paths need, whether a Spec comes first, and the level of the edit |
|  | `aidd new spec` | when the route needs a Spec: start the Spec from its template |
|  | `aidd test` | once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file |
| Now and then | `aidd init` | once in each repository: write the config, the skill, the ask rules, and the CI workflow |
|  | `aidd upgrade` | after you install a new aidd: bring the repository's aidd files up to it |
|  | `aidd self-update` | to update the CLI now; it also checks once a day by itself, after a command you run at a terminal |
|  | `aidd uninstall` | to remove aidd from a repository |
|  | `aidd doctor` | after `init` or `upgrade`, or when something looks wrong: check the wiring |
|  | `aidd standard` | to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`), or a stack of them (`add --stack python-cli`) |
|  | `aidd records` | to see what was asked and answered, and what the agent did on its own; the agent writes each record (`add`); share them with `pull` and `push` |
|  | `aidd delegate` | under a standing delegation, before a delegated ask: whether it may go to the delegate (`check`); `stop` turns it off |
|  | `aidd recall` | before you decide or write: find what the team already wrote about it, then read the file each match names |
|  | `aidd validate` | to check the whole repository, or the files you name |
|  | `aidd explain` | when a word or a step puzzles you: what it means and why, from the data that owns it (`aidd explain --list` lists them) |
|  | `aidd explore` | when an exploration is ready for a person: show its comparison page (`aidd new exploration` starts it) |
|  | `aidd prototype` | to click through the whole product: assemble the product prototype into one page and check it (`aidd new product-prototype` starts it) |
|  | `aidd help` | to find a command: the everyday ones, every one (`--all`), or one command's arguments and flags (`aidd help <command>`) |
| Maintainers and harnesses | `aidd eval` | maintainers: run the agent evals, the standards check, or the pack check |
|  | `aidd mcp` | harnesses: serve aidd to agents as MCP tools; `aidd init` wires it |
|  | `aidd gen-docs` | maintainers: after a change to a schema or to the help, regenerate the generated blocks |
<!-- aidd:end -->

## Commands

The table is generated from the CLI's own argument parser, so it lists every command and flag the installed version has. `aidd help --all` groups the same commands into **Setup**, **Work**, and the commands for **maintainers and harnesses**.

<!-- aidd:gen cli:commands -->
| Command | What it does | Flags |
| --- | --- | --- |
| `init` `[path]` | adopt aidd in a repository | `--dry-run`, `--profile solo\|team`, `--ci github\|gitlab\|none`, `--ref SHA_OR_TAG`, `--approvers WHO ...`, `--specialist POOL=WHO` (repeatable), `--test COMMAND`, `--team`, `--harness AGENT` (repeatable), `--claude-plugins`, `--devcontainer`, `--compliance-target soc2\|iso27001\|gdpr\|hipaa\|pci-dss\|fedramp\|cra\|other` (repeatable), `--security-ci`, `--delegate`, `--merge-deploys yes\|no\|unsure`, `--link DIR` (repeatable), `--no-skill`, `--force` |
| `upgrade` `[path]` | bring a repository's aidd files up to this aidd: the skill, the team files, the text between aidd's marks in AGENTS.md, each agent's ask rules, the CI pins, aidd_version, the config fields this aidd removed, which stay as comments, and the work items an older aidd wrote above the Spec, folded into Intents; a dry run unless --yes | `--ref SHA_OR_TAG`, `--yes`, `--collapse-unstarted` |
| `self-update` | update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line installer), from the release's wheel once it matches the release's SHA256SUMS, or to the tip of main while no release exists; AIDD_NO_UPDATE_CHECK=1 turns the daily check off | `--check`, `--main` |
| `uninstall` `[path]` | reverse `aidd init`: list what it would remove, or remove it with --yes | `--yes`, `--link DIR` (repeatable) |
| `doctor` `[path]` | check that a repository is wired correctly | `--json` |
| `standard` `[list\|add]` `[ID ...]` | the choices the domain packs and practice skills leave open, each with aidd's default, and aidd's library of opinionated standards that fill them, and its stacks; `add` copies standards or a stack into docs/standards/ with their `standards` entries and their `tests` | `--stack NAME`, `--stacks`, `--json` |
| `status` `[ID\|PATH]` | the open work: each Spec, Intent, and proposal with its status and its next step, and who takes it | `--commits N`, `--mine`, `--all-branches`, `--delivery-team NAME`, `--json`, `--html` |
| `risk` | advice before an action: the route for planned paths (--paths), the level of a shell command (--command) or an action (--action), or every risk rule in force (--list); a level is allow, report, or ask | `--paths PATH ...`, `--command LINE`, `--action ID`, `--list`, `--suggest`, `--change-type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--irreversible`, `--area AREA`, `--branch own\|default\|shared`, `--folder PATH`, `--role ROLE`, `--json` |
| `records` `[list\|add\|push\|pull]` `[remote]` | the history in .git/aidd/records/, newest first: each ask a person answered (decision) and each action the agent reported (report); `add` writes one, checked against schemas/records.json. A record is the agent's account, never a yes and never evidence | `--type TYPE`, `--subject ID`, `--by HARNESS/MODEL`, `--data JSON`, `--json` |
| `delegate` `check\|packet\|hook\|stop` | a standing delegation: `check` says whether a delegated ask may go to the delegate, recomputed from git, the default branch's config, and the platform (exit 0 eligible, 1 defer); `packet` is what the delegate reads; `hook` is Claude Code's hook; `stop` turns the delegation off in this clone | `--action ID`, `--command LINE`, `--head SHA`, `--spec ID`, `--cwd DIR`, `--json` |
| `recall` `WORD ...` | search what the team already wrote: the records, the Specs and their documents, the ADRs, the glossary, the product brief, the improvement log, and the commit subjects. Each match has its file and line, a record's id, or a commit's short sha, newest first where it has a date. It reads through the index in .git/aidd/, a cache of the files: never a source of truth, never evidence, never a yes | `--limit N` (default `20`), `--json` |
| `new` `spec\|intent\|proposal\|runbook\|postmortem\|tech-spec\|test-plan\|adr\|threat-model\|authz\|design-spec\|api\|slo\|compliance\|analytics\|migration\|acceptance\|feedback\|service-card\|srs\|design-system\|architecture\|data-map\|vendors\|glossary\|vulnerability-policy\|agents\|product-brief\|metrics-dictionary\|control-register\|improvement-log\|contract\|exploration\|product-prototype` `[id]` | create a work item or a document from its template. A document a Spec links is added to the Spec's `docs`; `aidd new --list` lists every type | `--title TITLE`, `--route normal\|major\|emergency`, `--change-type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--paths PATH ...`, `--dimension data\|security\|privacy\|financial\|compliance\|availability\|third_party\|cost\|performance` (repeatable), `--irreversible`, `--force`, `--full`, `--owner-team OWNER_TEAM`, `--parent PARENT`, `--audience client\|internal` (default `client`), `--addressee ADDRESSEE`, `--spec SPEC`, `--area AREA`, `--no-link`, `--prototype`, `--owner OWNER`, `--timebox TIMEBOX` (default `45 minutes`), `--list` |
| `test` | run the tests (green on head, red on base) and write evidence | `--base BASE`, `--spec SPEC`, `--out OUT` (default `.aidd/evidence`), `--no-red`, `--red-in-place`, `--pass-env NAME` (repeatable), `--changed`, `--watch` |
| `validate` `[PATH ...]` | validate the repository, or the files given | `--json` |
| `explain` `[WORD ...]` | say what one of aidd's words means and why it matters: an action, an area, a route, a lane, a stage, a loop step, a gate, a decision, a role, a document type, a status, or a profile, read from the data that owns it | `--list`, `--json` |
| `explore` `folder` | render an exploration's one comparison page: two or three divergent directions side by side, the trade-offs under each, and each round's screenshots; the owning role writes the pick and its reason in the Spec, DESIGN.md, or an ADR | `--out PATH` |
| `prototype` `[file]` | assemble the whole-product prototype from docs/design/app/ (sitemap.json, shell.html, and flows/) into aidd's prototype viewer, .aidd/views/prototype.html, and check it: every link and navigation item opens a screen, no flow draws its own navigation, and every flow is reachable | `--check`, `--example`, `--open`, `--serve`, `--lan`, `--port PORT` (default `8765`), `--components`, `--screens`, `--new-design FILE`, `--title TITLE` (default `A direction`), `--stories INDEX` |
| `help` `[COMMAND ...]` | the everyday commands, the same as `aidd --help`; with --all, every command by group; with a command, its arguments and flags | `--all` |
| `eval` `routing\|roles\|standards\|packs\|tasks\|report\|transcript\|compare\|work` `[PATH ...]` | run an agent routing eval, the role evals, the standards check, the pack and practice template check, or your own agent tasks; report and compare recorded runs; read a repository's work history (work) | `--root ROOT`, `--scenarios SCENARIOS`, `--agent-command AGENT_COMMAND`, `--case ID` (repeatable), `--no-embed`, `--with-skills`, `--min-accuracy MIN_ACCURACY` (default `0.9`), `--repeat K` (default `1`), `--max-output-tokens N`, `--min-pass-k SHARE`, `--without-aidd`, `--record PATH`, `--model-label TEXT`, `--online`, `--strict`, `--due DAYS`, `--json`, `--timeout SECONDS` (default `15.0`), `--max-seconds SECONDS` (default `600.0`), `--max-bytes N` (default `3000000`), `--concurrency 1\|2` (default `2`) |
| `mcp` | serve aidd to agents as MCP tools over stdio: the risk level of an action, the open work, validation, records, and a search of what the team wrote | none |
| `gen-docs` | maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills | `--check` |
<!-- aidd:end -->

What the table cannot say:

- **`init`** writes the config, the skill, `AGENTS.md`, the CI workflow, the PR template, and each detected coding agent's ask rules ([every coding agent](GUIDE.md#every-coding-agent)). It never replaces a file that exists without `--force`. `--dry-run` prints what it finds, and the config it proposes, and writes nothing.
- **`status`** shows every open work item with its stored status and its next step, and who takes it: the agent, a person, or nobody, while an approved Spec waits on other work. A draft that holds no placeholder and passes `aidd validate` reads as finished, so its step is to set `ready` and ask for Spec approval. `--all-branches` does not validate a branch tip, so a draft there keeps "finish it". `--mine` keeps only what waits on a person. An open exploration comes first, with its question, because a person owes its pick. `--json` lists it in `explorations`. When no open step is a person's, both end with each root blocker and the choice (`--json` carries the line as `root_blocker`), such as "SPEC-1 blocks 23 Specs: finish it, or choose a Spec to specify". `--delivery-team <name>` keeps only one delivery team's work, from the config's `delivery_teams`: its Intents, their Specs, the Specs whose `owner_team` names it (in any case), and the Specs whose Task scope touches its areas. With `--json`, an item may also carry `owner`, `owner_team`, `delivery_teams`, `blockers`, `tasks`, `emergency` (only when it is whole), `evidence`, and `unsaved`, and a step may carry `person`, `words`, and `why`; the answer lists the config's `delivery_teams`. `unsaved` names the paths nobody committed yet on the branch for that item, such as `spec/SPEC-1`. `handoff` gives where the work stopped, from the note in the last commit's message. It shows on a branch of your own whose Spec holds no note. `--html` writes the work-items page to `.aidd/views/status-work.html`, or to `status-work-<team>.html`, `status-work-all-branches.html`, or `status-<ID>.html` for a filtered run, so no run overwrites another. With an id, it shows that item even when it is finished.
- **`status <path or id>`** shows what stands behind a path, a Spec, or an Intent, after a work item's status and history. That is the Specs whose Task scope covers it, the open Specs in flight there, and their tests, docs, and interfaces. It adds the route from `risk --paths`, and the last commits with their work ids and `Assisted-by` trailers. For a work item, it also lists the work that shares its `trace_id`. It reads git and the work items' files on demand and stores nothing. `--commits N` reads at most N commits (1 to 100, default 20), and says it does nothing with no id, or with a proposal's. For a path, `--json` follows `schemas/trace.schema.json`. For a Spec or an Intent, it follows `schemas/status.schema.json`, with the trace nested as `trace`.
- **`risk --paths`** gives a change's route before the first edit, and the level of editing those paths. In a subfolder, a relative path reads from there and from the repository's top, as `git diff --name-only` prints it, and the stricter reading routes, with a hint when they differ. A folder keeps its trailing slash, even when typed without one. A link reads as typed and also where it leads, and the stricter wins. A path outside the repository, or an empty one, is an error. `status <path>` and `new spec --paths` read paths the same way. **`risk --command`** gives the level of a shell command line, reading the branch a `git push` reaches from git. A `git merge` that lands other work, or a `git pull` with any word that is no option, is `git.merge`, so it asks while the default branch is checked out, and is allowed on your own branch. `pr.merge`, a PR/MR merged into its base, asks on any branch. `--folder <path>` reads the branch in the folder the command runs in, when that is not this one. Outside every git repository, the branch is unknown, so a command that turns on the branch asks, and a note says to run it inside the repository the change touches. A reader such as `cat`, `grep`, or `source` on a file that holds secrets, from its own list in `schemas/risks.json`, such as `cat .env`, is `secret.use`, which asks, while an example file such as `.env.example` stays allowed. **`risk --list`** shows every rule in force and where it comes from, whether the built-in rules, the profile, or the config. Each answer is advice. aidd enforces nothing, and a command pattern is a net, not a control.
- **`recall WORD ...`** searches what the team already wrote: the records, the Specs and the documents in their folders, the ADRs, the glossary, the product brief, the improvement log, and the last 1000 commit subjects. It shows each line that holds every word, with its file and line, a record's id, or a commit's short sha. Dated matches come first, newest first. Each word matches the start of a word, through SQLite's full-text search in the index. Where SQLite has no full-text search, it matches the word anywhere in a line. A file over 256 KiB or a link is skipped and named. It is a cache of the files: never a source of truth, never evidence, never a yes. `--limit N` shows at most N matches (1 to 200, default 20), and `--json` follows `schemas/recall.schema.json`.
- **`test`** runs the repository suite and the Spec's commands on the head, and each new-behavior command on the base too, where it must fail. `--changed` runs only what the working tree's changes select, green only, and marks the evidence partial. It is a quick check between steps. A command that names `report: <path>`, a JUnit XML file it writes, adds its failed test cases to its result in the evidence. A missing, stale, or unreadable report is a finding, and the exit code stays the evidence.
- **`validate`** with no paths checks the whole repository, including overdue emergency reviews. It warns, without failing, when a Spec has leftover TODO placeholders, or when a normal or major Spec has no Intent. A planned Spec, a draft whose every Task still holds a placeholder, gets a note instead, because Specify fills it in. A note never fails the run, and `--json` lists notes in `notes`.
- **`explain WORD`** says what one of aidd's words means and why it matters, read from the file that owns it. It knows the actions and areas of the risk rules in force, the routes, and the lanes. It also knows the loop steps, the decisions a person makes, the roles, the document types, the statuses, and the profiles. A word of two kinds, such as `emergency`, gets both. `--list` lists every word it knows, by kind. An unknown word exits 1 and points to `--list`. `--json` follows `schemas/explain.schema.json`.
- **`explore FOLDER`** renders an exploration's comparison page into `.aidd/views/explore-<folder>.html`. The page records nothing and approves nothing: the owning role writes the pick and its reason.
- **`gen-docs`** regenerates every `aidd:gen` block in the Markdown files, the skill's references, and the domain-pack skills. With `--check` it changes nothing and fails when any is stale, or when a generated table would have no rows.

## Scripts on `aidd status --json`

`aidd status --json` follows `schemas/status.schema.json`, and its `schema_version` changes only when a field changes meaning. Each next step has a stable `code`, such as `spec.approval`, so a script matches the code, never the sentence. These four `jq` recipes answer the common questions:

```sh
aidd status --json | jq -r '.items[] | select(.next.who == "person") | "\(.id)\t\(.next.what)"'   # what waits on me
aidd status --json | jq -r '.items[] | select(.next.code == "spec.blocked" or .next.code == "spec.blocked_by") | .id'   # what is blocked
aidd status --json | jq -r '.due[] | "\(.path)\t\(.what)"'   # what is past due
aidd status --json | jq -r '.items[] | select(.id == "SPEC-3") | .next.what'   # one Spec's next step
```

## Exit codes

<!-- aidd:gen cli:exit -->
| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `test` | every command passed (and every new-behavior command failed on the base) | a test failed | error |
| `validate`, `doctor` | no errors | an error or a failed check | error |
| everything else | success | a check failed | error |
<!-- aidd:end -->

A crash is always 2, never 1.

## Environment variables

Every variable aidd reads, and every variable it sets for your test commands. A test fails when the code reads an `AIDD_*` variable this table does not list.

<!-- aidd:gen cli:env -->
| Variable | Read by | Meaning |
| --- | --- | --- |
| `AIDD_OFFLINE` | every command that loads the config, and `aidd self-update` | `1` stops every optional network call: `extends` parents by URL are skipped with a warning, no update check runs, and `aidd init --claude-plugins` wires the repository instead |
| `AIDD_ORG_PRESET` | every command that loads the config | the path of an org preset, read as the first parent of every config |
| `AIDD_DEBUG` | every command | `1` prints the traceback of an error to stderr; a crash then asks you to report it |
| `AIDD_AGENT` | `aidd self-update`'s daily check | any non-empty value tells aidd an agent runs the shell, so the daily update check stays off |
| `AIDD_NO_UPDATE_CHECK` | every command a person runs at a terminal | `1` turns off the daily check for a newer release |
| `AIDD_AUTO_UPDATE` | every command a person runs at a terminal | `1` installs a newer release, verified, instead of only saying it is out |
| `AIDD_REF` | the one-line installer | the release tag or commit to install, such as `v1.0.0` |
| `AIDD_WORKTREE` | your test commands (set by `aidd test`) | the worktree's folder name as a slug, so a project can name its test database by it |
| `GH_TOKEN` | `aidd eval standards --online`, `aidd self-update` | a read-only GitHub token, for a higher rate limit; never required |

Stripped from the environment of every test command: `GITHUB_TOKEN`, `GH_TOKEN`, `AIDD_GITLAB_TOKEN`, `CI_JOB_TOKEN`, `ACTIONS_RUNTIME_TOKEN`, `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.
<!-- aidd:end -->

One more belongs to [`install.sh`](GUIDE.md#install) alone. `AIDD_REF`, in the table above, takes a `vX.Y.Z` tag or a commit SHA. A tag installs that version's wheel from its GitHub Release, once the wheel matches the release's `SHA256SUMS`. `AIDD_SHA256`, when set, must match too. `AIDD_RELEASE_URL` points the installer at a mirror of the releases, which needs `AIDD_SHA256` or `gh` too. A commit SHA builds from source, for testing unreleased code only. With no `AIDD_REF` and no release yet, the installer resolves `main` to one commit and builds from source there, and says it is unreleased and unverified.
