# Changelog

This file lists every notable change to aidd.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The method, the schemas, the risk rules, the CI templates, the skill, and the team plugin share one version. Every config carries `aidd_version`. [CONTRIBUTING.md](CONTRIBUTING.md#versioning) says what counts as a patch, a minor, or a major change. An upgrade within a major version never turns an approved Spec's frozen test red ([the promise](CONTRIBUTING.md#frozen-tests)).

## [1.0.0] - Unreleased

aidd is a governance layer for AI coding agents. It works on the AI-native development loop: Plan, Design, Build, Test, Deploy, Maintain. Agents do the work in one loop, and you decide the risky steps. Its core is a command-line tool with no runtime dependencies, a skill that coding agents read, and MCP tools. The delivery team, the practice skills and packs, the standards library, the design tools, and the work-item pages are optional parts. aidd advises and enforces nothing. This is the first release.

### Added

#### The method and the loop

- **A [governance layer](docs/GLOSSARY.md) for AI coding agents.** It advises how much process each change needs and which steps wait for a person's yes. Your harness's ask rules and your platform's branch protection hold the stops.
- **[One loop](docs/METHOD.md) for every change.** It runs Plan, Specify, Spec approval, Implement, Verify, Review, Merge approval, Merge, Roll out, and Learn.
- **Six stages.** They group the steps: Plan, Design, Build, Test, Deploy, and Maintain.
- **Four gates where you decide.** They are Intent agreement, Spec approval, Merge approval, and Production release. Each asks by default.
- **Proof.** A test runner's exit code on a known commit is the evidence.
- **Red before green.** New behavior fails on the base before it passes on the head.
- **Retries.** A Task retries at most 3 times, and a flaky test is a finding.
- **Routes as advice.** `aidd risk --paths` sizes a change by what it touches, as `minor`, `normal`, or `major`, and says whether a Spec comes first.
- **The emergency route.** You declare it. It repairs production first and writes the Spec after.
- **Documents sized to the risk.** A major change gets a tech spec, a test plan, a threat model when it touches security, privacy, or data, and a rollout plan. A normal change gets a test plan when compliance is on, and a suggestion otherwise. A minor change gets none of them.
- **A test plan at two scopes.** A Spec's plan follows ISO/IEC/IEEE 29119-3 and is frozen with the Spec. A component's living plan (`aidd new test-plan <component> --living`) holds the strategy, the risk register, and the test catalog, and links the generated trace.
- **Profiles.** `solo` asks for Spec approval on major changes and asks before anything reaches the default branch.
- **The `team` profile.** It asks for Spec approval on normal and major changes. Your platform's review is the Merge approval.
- **Acceptance tests first.** In Specify, the verifier writes the acceptance tests, each red on the base. Spec approval freezes them.
- **Unit tests with the code.** The developer writes them inside the Task's scope and never edits a frozen test.
- **Changing a frozen test.** It is `spec.revise`, which asks you again.
- **Spec approval, asked plainly.** The agent asks "Approve SPEC-3?" and says what the Spec covers.
- **What your yes records.** The agent sets `status: approved`, `approved_by`, and `approved_at`, and commits with an `Approved-by` trailer.
- **Changing course.** The guide's "Change your mind" gives the words to change a pick, skip a step, go faster, pause, stop, go on, or undo a merge.
- **Headless runs stop at an ask.** In CI or a scheduled run, an `ask` means stop and hand back with a handoff note, because silence is never a yes.
- **Checked handoff notes.** `aidd validate` checks each note's keys and its stop code.
- **An agreement a headless run cannot record.** The run stops at the agreement, because the commit that records it asks.
- **Recording that agreement.** `aidd status` gives you `aidd agree <ID>...` for your own terminal. It sets `agreed_by` and `agreed_at` on those Intents alone, and commits them as you, with your `Agreed-by:` trailer. aidd never runs it, and it is an `ask` in every harness that can hold it.
- **A cold reader on the major route.** Before Spec approval, the tech writer reads the Spec alone and lists the terms and steps it assumes.
- **Plain prose.** The plain-language skill sets the writing level by what a text does, with `instruction` for steps and rules and ISO 24495-1 for text that clients and users read.
- **Docs held to it.** A test holds every page of aidd's own docs to that level.

#### Work items

- **Your request, sorted by size.** A request is your own words, from the chat or a file. A minor fix needs no Spec. One change gets one Spec, whose `## Request` quotes you.
- **Each goal, sorted the same way.** A goal bigger than one Spec gets an Intent, a one-change goal its own Spec, and a minor fix no Spec.
- **A chat request, saved.** Before it writes an Intent, the product manager saves your words to `specs/requests/<yyyy-mm-dd>-<slug>.md`.
- **A saved request leaves things out.** The file is committed, so it leaves out secrets, credentials, and other people's personal data. `aidd validate` names a known secret's shape there.
- **The Intent.** The team writes it from your request, as phases of slices. A slice is one line until its work starts.
- **One yes for all goals.** One question names each goal, and your one yes agrees to them all.
- **An Intent traces your request.** Its `## Request coverage` table has a row for each success criterion and hard constraint you wrote.
- **One branch for an Intent.** Under `reaches: batched`, the Specs build on `intent/<ID>`, two or three at a time, and one Merge approval lands them. A Spec merged there is `done`, and nothing is shipped until the branch lands. `aidd status` shows the Intent's one pending Merge approval and where each Spec stands, from git.
- **What a coverage row names.** A proof, another work item, the question the team asked you, or your non-goal. `aidd validate` checks each row.
- **The Spec** is the contract of one slice or one change, with `type: spec` in its front matter. It holds the Acceptance, the scope, the tests, the risk, the rollback, and an observe window.
- **A cost estimate.** The Spec holds one, and `aidd validate` checks it against `project.budget.max_infra_per_month`.
- **A Spec's status.** It runs from `draft` to `ready`, `approved`, `in_progress`, `in_review`, and `done`, or ends at `rolled_back` or `cancelled`.
- **Blocked is a flag.** Blocked is never a status.
- **What blocks work.** `waiting_on` names a wait, a Task used its 3 retries, or a `blocked_by` item is not done.
- **One home for each fact.** A Spec's linked documents hold their own facts, such as a threat's row in the threat model, and link them by id.
- **Checked ids.** `aidd validate` warns about a linked document that names an Acceptance id the Spec lacks.
- **Left-over placeholders.** `aidd validate` warns about a TODO, a `YYYY-MM-DD`, or an id such as `SPEC-?` in any document a Spec links, frozen or living, and in each repository document `aidd new` writes.
- **Interfaces between Specs.** A Spec lists the interfaces it `provides` and `consumes`. When a Spec that provides one is revised, `aidd status` names the open Specs that consume it.
- **Deprecations.** A passed sunset in `deprecations` warns until a Spec removes the thing.
- **Open questions.** While a Spec asks for approval, `aidd validate` names each open question it lists.
- **Unplanned files.** After approval, `aidd validate` names each file the change alters that no Task covers.
- **Avoided words.** `aidd validate` warns about a word your glossary says to avoid.
- **Decision tables.** The Spec template turns a business rule with three or more conditions into a decision table, with one Acceptance id per row.

#### Risk rules and your coding agent's ask rules

- **Actions, areas, and levels.** An agent acts by a risk rule's level: `allow` acts, `report` acts and then says what it did, and `ask` waits for your yes.
- **Actions.** Each is `resource.verb`, such as `pr.open` or `deploy.run`.
- **Areas.** An area is a named set of path globs, such as `auth`, `payments`, or `personal_data`.
- **`aidd risk` answers.** `--paths` gives the route and the first step. `--command` gives the actions a command matches and the winning level. `--action` gives one action's level, and `--list` shows every rule in force.
- **Where a rule came from.** Each answer names the rule that decided it.
- **One owner for Spec approval.** The `spec.approve` rules decide the routes on which an agent asks, and a profile holds only its rules. A rule's `route`, `normal` or `major`, narrows `spec.approve`. Built in, it asks on every route, and the `solo` profile lowers the normal route to `report`. `aidd risk --action spec.approve --route normal` gives one route's level. A config's `spec.approve` rule with no `route` decides both.
- **One list of test files.** `test_paths` in the built-in risk rules says what a test file is. Four readers share it: the route advice, a Task's scope, `aidd init`, and the delegated change that must leave every test file alone. That check covers `e2e/`, `testing/`, `specs_test/`, and `*_spec.*` files too. The other readers take a few more files for tests, such as a script named `test`, and the route advice then skips its "write a test first" step for them.
- **Built-in rules you can read.** `schemas/risks.json` holds the actions, the areas, and the rules between them. Each rule says why in its `reason`.
- **Built-in edits.** Editing code is `allow`, and `ask` in `auth`, `payments`, `personal_data`, `secrets`, `migrations`, and `risk_rules`.
- **Built-in reports.** Opening a pull request, adding a dependency, a local migration, and listening on the network report. So do edits in `ci`, `infra`, `dependencies`, `agent_config`, `project_config`, and `module_boundaries`.
- **A workflow run.** A manual run reports. One that releases, publishes, or deploys asks.
- **Built-in asks: Git.** These ask: a push to the default or a shared branch, a force push, a history rewrite, a branch deletion, a tag, and a merge.
- **Your own branch.** Pushing it and merging on it are `allow`.
- **Built-in asks: the platform.** These ask: merging a pull request, posting a commit status, changing a branch protection, and changing a repository's settings.
- **Built-in asks: decisions and history.** Intent agreement, Spec approval, Spec revision, and a records push ask.
- **Built-in asks: releases and data.** A deploy, a release, a migration, a rollback, an infrastructure change, a data deletion, production data, a secret, a message, and spending money ask.
- **Lowering a built-in ask.** Your own rules can lower any of them, unless a preset locks the rule.
- **Commands read as a shell runs them.** aidd reads a command without its runner, such as `npx` or `uv run`.
- **Wrappers.** aidd looks inside `sudo`, `env`, `bash -c`, `$(...)`, and similar wrappers.
- **`gh api`.** aidd reads it by its parsed arguments, so a write asks in any flag order.
- **Migrations by where they run.** A migration asks when it runs on a database other people use, or when it undoes applied migrations.
- **A local migration reports.** A plain forward `migrate` on the agent's own database reports.
- **A local merge asks.** `git.merge` asks on the default branch. It reads the checked-out branch from git.
- **Outside a repository.** The branch is unknown, so `aidd risk` asks and names the next step.
- **Reading a secret file asks.** `secret.use` asks before a common reader, such as `cat` or `cp`, opens a file that holds secrets.
- **A shell write to a file is an edit of it.** `aidd risk --command` reads the target of a redirection and the file `tee`, `cp`, `mv`, `install`, `ln`, `sed -i`, `perl -i`, `dd of=`, `truncate`, `rm`, and `unlink` write, and gives the command the level `aidd risk --paths` gives that file. A redirection that opens a file for reading and writing (`<>`) is a write, and a writer's long option counts when it is given by a prefix that only one of its options starts, such as `--in-pl`. It reads a relative path from the folder the command was typed in, follows no `cd`, and reads a folder copied or moved into, or deleted with `rm -r`, as that folder. A `-t` in a run of short flags, such as `cp -rt DIR`, names the folder too. After a word that may change the folder, a relative path reads by its name alone, as the strictest file or area glob that guards that name. `[` and `[[` are no such word, and a script that `.` or `source` runs is not read. A bare name that only a folder-wide area guards raises nothing. A write to `.claude/settings.json` or `.aidd/config.yaml` now asks, where it read `allow`. A device, the temporary folder, and a git-ignored file in `.aidd/*/` stay `allow`. A word the shell expands is left unchecked, with a note. 
- **Allowed reads.** An example file such as `.env.example` and a public key stay allowed.
- **A yes holds only for what it showed.** When the head, the branch, or the command a question named changes before the agent acts, it asks again.
- **Your own rules.** The config's `risks` adds areas, actions, and rules. A rule with a built-in's selector overrides it, so a project can lower a level as well as raise it.
- **Locked rules.** An `extends` preset can lock a rule, which is a floor (see "A lock is a floor" under Risk rules).
- **Presets keep what they set.** A child config changes only what it names. A mapping merges member by member at every depth, so adding one specialist pool or one model keeps the preset's others, and a child never removes a map entry. A list of named things, such as `environments`, merges by name, and any other list replaces. `false` turns a disabled rule or default back on.
- **Locks reach one member.** A preset's `locks` may name `docs.disabled` or `owners.specialists.security`, and `profile` is lockable, so a preset can hold `team`.
- **Session overrides.** You may lower a rule for one session, such as "don't ask about pushes today". It goes into the config only when you say so.
- **Environments.** The config's `environments` names each environment by its branches and tags. A push to one is `deploy.run` to that environment.
- **Per-environment levels.** A rule can set one environment's level.
- **Your own environment reports.** A deploy to an environment the config marks `shared: false` reports: the agent deploys, then says so.
- **Every other environment asks.** Staging, production, an unmarked environment, and a deploy command that names no known environment, such as `kubectl apply`, all ask.
- **No wildcard for your own.** Name your own environment's branches and tags without a wildcard; a wildcard match reads as shared.
- **A delegation raises the reserved actions.** Under a standing delegation, a deploy, a dependency, and a migration ask, even over a parent config's locked lower level.
- **`aidd init --dry-run` is the real init in a plan.** It names every file and prints the config the real run writes, for every flag, because both run one code path with the writes held. It deletes nothing, makes no folder, and asks GitHub nothing: a ref that needs GitHub shows as `would pin ... the latest release`.
- **`aidd init --force` keeps every value you set.** It rewrites aidd's generated files, and in the config changes only the values a flag sets, each listed in full. A flag that names one item sets that item: one specialist pool, the one test init writes, the environments it names. `--delegate` keeps a delegation that is there, so an expired one stays expired, and `--environment none` refuses to drop listed environments.
- **Unreadable means an error.** `aidd risk --action pr.mrge` exits 2 and names `pr.merge`. A config rule for an action no layer defines (`pr.opn`) fails the config's load at its line.
- **An unknown never reads as `allow`.** A glob or folder in `aidd risk --paths` stands for every tracked file under it, so `src/**` routes as `src/payments/` does. An action whose branch aidd cannot read, such as a push or a commit from a detached HEAD, reads as the strictest level over branches, as `--action` does. A branch it read gives that branch's level. A push reads as its words say. A setting that may send a push elsewhere only raises it. Three git settings that can send a push elsewhere raise it to a push that may reach the default branch, with a note; `docs/CLI.md` names them. A `-c` or `--config-env` on the same git command whose key starts with `remote.`, `push.`, `branch.`, `include.`, or `includeIf.` raises it too, whatever its value, and a `*` in a refspec reads as every branch. A `git checkout` or `git switch` earlier on the line is read beside the branch checked out for every action a rule makes branch-dependent. No other setting changes a level. A program by its Windows name (`git.exe`, `C:\Git\bin\git.exe`) is a program the POSIX reader does not know, so `allow` comes with a note that no rule matched; the harness's ask rules are the stop on Windows. A command no action matches says so in `notes`, and a `--folder` that is no git checkout says so. An area's paths and a path compare in Unicode form NFC. The `--action` answer drops its constant `known` field. In `risk --list`, an area's count of globs is `glob_count`, so `path_count` always counts planned paths.
- **A config that does not load stops what decides.** `risk`, `test`, `new`, `standard`, and the MCP `risk` tool stop with the error and `aidd validate` as the next step. `status`, `recall`, `explain`, and `doctor` show the problem first and exit 1; so do the MCP `status` and `recall` tools, and the MCP `validate` tool returns an error. `validate <path>` adds the config's error and fails, in the CLI and in MCP. A parent `url` that is no URL is a config error with its line.
- **A config written for a newer aidd says so.** When `aidd_version` is newer than the running aidd, the load error adds the two ways out: upgrade aidd, or move the pin to that version.
- **`aidd upgrade --yes` ends by running `aidd validate`'s checks.** A config aidd cannot read already stops the commands that decide. After the upgrade writes its changes, it lists each error that remains and exits 1, so you meet it at the upgrade.
- **Every config error names its line.** An error in a parent config names that file and its line.
- **Suggested lower rules.** `aidd risk --suggest` names an `ask` rule that you approved every time, at least 10 times, as a candidate for `report`.
- **Suggestions only.** It never suggests an action marked `irreversible`, and it changes nothing.
- **Modelled on authorization.** The rules borrow the shape of Cedar, Google Cloud IAM, and Kubernetes RBAC. The most specific matching rule wins, then the higher level.
- **<!-- aidd:gen count:harnesses -->14<!-- aidd:end --> coding agents.** aidd supports <!-- aidd:gen list:harnesses -->Claude Code, Codex, Cursor, DeepSeek Harness, GitHub Copilot, Google Antigravity, Grok Build, JetBrains Junie, Kiro, Mistral Vibe, Muse Code, OpenCode v2, Qwen Code, and TraeCode<!-- aidd:end -->. `aidd init` wires the ones it finds.
- **Any other agent.** The `aidd` skill is a self-contained Agent Skills folder, so it reaches any agent through `AGENTS.md` and `.agents/skills/aidd/`.
- **The harness's own ask rules.** `aidd init` and `aidd upgrade` write each `ask` rule in the format the harness's documentation gives. Claude Code, OpenCode v2, Codex, Grok Build, Qwen Code, and VS Code's agent get them.
- **Same asks everywhere.** A test checks that all six ask for the same commands.
- **Your settings stay yours.** aidd lists what it wrote in `.aidd/harness-rules.json` and changes only those entries.
- **Your deny wins.** aidd never puts an ask where it would undo your deny.
- **A harness without ask rules.** It gets the skill alone, and `aidd doctor` says so.
- **Frozen tests ask in the harness.** For every Spec that is approved, in progress, or in review, `aidd upgrade` writes an edit ask for each of its test files, in the harnesses that have a file-edit rule.
- **What holds each ask.** A generated table in the guide lists each built-in `ask` action, the commands a harness asks before, and what branch protection refuses.
- **A branch ruleset.** On GitHub, `aidd init` writes `.github/rulesets/main.json` for you to import. It is the hard stop for merges and force pushes.
- **Folder trust.** Codex, Grok Build, and Qwen Code with folder trust on ignore a project's ask rules until you trust the folder.
- **Folder trust in `aidd doctor`.** It names each such harness the repository wires and gives the words to type.
- **The `aidd-cli` plugin** puts the `aidd` command on the PATH of Claude Code's Bash tool. The other agents run the `aidd` you installed.
- **Claude Code Review reads `REVIEW.md`.** The file says what Important means here, caps nits, and lists what not to report.
- **A lock is a floor.** A rule an `extends` preset locks sets the lowest level of what it covers, and it lowers nothing. The level is the higher of the lock's and the one the most specific rule that is not locked gives, so a preset that locks `code.edit: report` still asks about edits in `auth` and `payments`. A locked rule with a repository's selector and another level is set aside, and a narrower rule may ask more.
- **A listing, a preview, or a request for help reads `allow`.** `git tag` with no word or with `-l` and its listing options, `kubectl apply` or `kubectl delete` with `--dry-run=client`, `aws s3 rm` with `--dryrun`, and `-h` or `--help` where the tool documents it, no longer ask. A command reads as one only when it is typed as it runs, with only the words the form lists. A writing word, a second command, a redirection, an expansion, a setting, or a wrapper keeps the old level. `git push --dry-run` and `npm publish --dry-run` still ask, because each runs the project's own code. A harness's ask rule may still ask, and the answer's note says so.
- **Auth and infrastructure paths in every language.** A middleware, a `.guard` file, `permissions`, `rbac`, `acl`, or `auth` joined to middleware, guard, filter, or interceptor now routes as auth (major, edit asks) in any language, not only the TypeScript and JavaScript files it named. Pulumi, Terragrunt, Docker, Compose, Skaffold, Tilt, and Vagrant files and a top-level `infra`, `infrastructure`, or `iac` folder route as infrastructure. No route or level falls.
- **`aidd risk --list` shows what a lock changes.** Each locked rule gets a `lock:` line (`lock_effects` in `--json`) that names the narrower rules it raises to its level, and says it lowers none.
- **The `stable` branch restricts who moves it.** Its ruleset now also restricts updates, so only an actor on the ruleset's bypass list can push to it. Before, any writer could fast-forward unreviewed code to the plugins' channel. RELEASING.md says whom to add.
- **Ask rules by action.** The `aidd init` and `aidd upgrade` previews list the ask rules added and removed for each action, and a dry run prints the line the real run prints.
- **GitHub Copilot's rules stay current.** aidd's own ledger keeps a harness whose rules it wrote known, so `aidd upgrade` and `aidd doctor` no longer skip VS Code's `.vscode/settings.json`.
- **Comments stay.** VS Code's settings file, Qwen Code's, and OpenCode's `opencode.jsonc` take comments, so aidd edits the file you keep in place and keeps your comments, key order, line endings, and settings. It leaves a file it cannot prove it can edit.
- **What a harness cannot hold.** `aidd doctor` names each `ask` action no rule of a wired harness holds, each one held in part, and each documented mode where the rules do not hold, with the page and the date read. The generated tables say the same, and no longer claim that every harness asks for the same commands.
- **`aidd init` in an agent session says what it wires.** It wires that session's agent from the variable its vendor documents, as before, and prints one `note` line, in the dry run too: the agent, the variable, the file, and how to leave it out with `--harness`.
- **`aidd upgrade --only ask-rules`** writes each coding agent's ask rules, the `Edit` asks for a Spec's frozen tests included, and changes no other file.

#### Delegation

- **Let the delegate decide for you.** `aidd init --delegate` writes a `delegation` block.
- **`decides` is a list.** `aidd init --delegate` writes every ask you can undo, and a later aidd adds an ask only when you name it. A `decides` that is no list fails to load.
- **Four delegated asks.** The `aidd-team:delegate` role answers Spec approval, a push of the change's own branch, a merge on GitHub at its exact head, and a local merge with no remote.
- **What stays yours.** A deploy, a migration, a new dependency, a secret, and a change to what decides are always yours.
- **One answer on what deploys.** The config's `environments` says where a push deploys, and a delegated push and a delegated merge both read it. A merge defers when `environments` is unset, when one lists the default branch (a parent config's too), when the branch is the Pages source, or when a workflow or a host's deploy file deploys on it. A parent can lock `environments` with `locks`. `aidd init` reads the deploying workflows (GitHub Actions and GitLab CI) and writes the environments they name, each with a comment on its file and line, when one names the default branch. Otherwise it writes the answer from `--environment NAME=REF` (a branch, or `refs/tags/PATTERN`), `--own-environment NAME=REF` (`shared: false`), or `--environment none`, which stands alone. A delegated merge stays yours until one of them states it. When the check defers, it names the question and the edit. `aidd doctor` warns when `environments: []` sits beside a deploying workflow, or when an environment's branches are gone. Under a delegation, a deploy to your own environment (`shared: false`, named with no wildcard) still reports, while every other deploy asks.
- **`aidd delegate check` recomputes every gate each time.** It reads the delegation at the default branch's tip, the command against its exact template, the reserved paths, and the evidence.
- **The evidence.** On GitHub it is the `tests` check run and the branch rules, read through read-only `gh api` calls. With no remote it is an `aidd test` run in a fresh worktree.
- **Commands.** `aidd delegate` has `check`, `packet`, `hook`, and `stop`.
- **MCP tools.** They are `delegate_check`, `delegate_packet`, and `delegate_answer`.
- **Claude Code's hook** answers a delegated prompt only when the check passes again on the exact command. Otherwise the prompt stays.
- **Other agents.** Every other coding agent keeps asking you.
- **Reserved test files.** A change to `conftest.py`, `sitecustomize.py`, a `.jest/` folder, or a similar file defers a delegated merge.
- **The delegate reads the Spec whole.** The packet carries the Request, Acceptance, Design, Concerns, Rollback, Tasks with their scopes, and `risk`, with the template comments out. A part past its cap, or a diffstat of more than 300 files, defers the check and names it (`text_too_long`), where the packet once cut the Spec's body at 2,000 characters.
- **Hidden characters and look-alike spellings.** A text with a character a reader cannot see defers (`text_hides_characters`), in the file or in the value it parses to. The approval-phrase list now also matches a fullwidth or zero-width spelling, as the secret scan reads text.
- **The person's request, not the asker's.** The packet carries the saved request that the Spec's parent Intent names, as the default branch holds it, as the person's only when the default branch holds the link. A link only the change holds reaches the delegate as `claimed_request`. The Spec's own `## Request` is labelled as written by the asker.
- **A record is never an approval.** A delegated merge counts only the delegate's own accept of the Spec's approval, and only while `spec.approve` is delegated. A `decision` record never counts, so with `spec.approve` reserved the person merges.
- **An unreadable record defers.** A file in `.git/aidd/records/` that does not read as a record defers every delegated check (`records_unreadable`), because it could hold a delegate's defer.
- **The base decides, and a scope alone defers nothing.** The merge check reads a Spec's status, route, scope, and tests as the run does, from the base where the base holds the Spec, and the head can only make it stricter. A change that only touches an open Spec's Task scope is a note in the answer, not a defer, so an unrelated fix never waits on a wide scope. A non-minor change with no Spec still defers and names the Spec.
- **Two warnings.** The check and `aidd validate` warn when `review_due` is more than 180 days ahead. The check warns when `agents.models` puts the delegate on a model that a commit's `Assisted-by` names.
- **A merge delegated without `spec.approve` warns once.** A delegated merge of a change with a Spec waits for you unless the delegate also decides `spec.approve`. `aidd validate`, `aidd doctor`, and `aidd init --delegate` say so with the two ways out, and `aidd doctor` also prints the review-date and same-model warnings.
- **Where a delegation stands.** One set on a branch counts only from the default branch's tip. `aidd doctor` and `aidd status` say when your checked-out config holds one that the tip does not.
- **One count of the delegate's accepts.** `aidd validate` and the check count the same records, so a Spec's `delegate_answer` that is pulled, or written under another name, is warned about.
- **Trailers for a delegated yes.** It writes `Decided-by`, `On-behalf-of`, and `Delegation`, never `Approved-by`.
- **Decisions made for you.** `aidd status` shows the latest ten.

#### The CLI and MCP

- **Mistakes name themselves.** A wrong flag value, command, option, `explain` word, or config key says which one was wrong and offers the closest right one, then exits 2. `--approvers` repeats and never swallows a path, `--harness none` beside a name is an error, `risk` refuses a qualifier beside a mode it does not go with, and the `init` help says what leaving each flag out means.
- **Ask your agent first.** The README and the guide lead each step with the words for your agent.
- **One-sentence install.** It runs through `llms-install.md`, which ends by naming the two steps only you take: restart your agent, and protect your main branch.
- **From GitHub only.** aidd is not on PyPI.
- **The installer.** `install.sh` installs a release's wheel once it matches the release's `SHA256SUMS` and, with `gh` on PATH, once its build provenance verifies.
- **Python 3.11 to 3.15,** with the standard library only.
- **One file.** Each release also carries the whole CLI as `aidd.pyz`.
- **Only what the CLI reads.** The wheel and `aidd.pyz` carry no eval case and no editor schema, which an editor reads from the release's URL.
- **Setup commands.** They are `init`, `upgrade`, `self-update`, `uninstall`, `doctor`, and `standard`.
- **Work commands.** They are `status`, `risk`, `records`, `delegate`, `recall`, `new`, `agree`, `test`, `validate`, `explain`, `explore`, `prototype`, and `help`.
- **Agent and harness commands.** They are `eval` and `mcp`.
- **Short help first.** `aidd --help` lists only the everyday commands, and `aidd help --all` lists every one a project runs.
- **aidd's own development.** `gen-docs` and the `eval` suites beyond `tasks`, `report`, `compare`, and `work` serve aidd's maintainers, and `aidd help --all` leaves them out.
- **Setup preview.** `aidd init --dry-run` shows the config and the folders where an agent asks before it edits.
- **Safe re-runs.** Run again, `aidd init` adds only what is new.
- **Setup checks.** `aidd doctor` checks the wiring, and `aidd uninstall` reverses `aidd init`.
- **What `aidd upgrade --yes` updates.** The skill, the team files, each agent's ask rules, the CI pins, and `aidd_version`.
- **Text between aidd's marks.** It also updates the text between aidd's marks in `AGENTS.md` and in the agents' instruction files, and nothing else in them.
- **`aidd upgrade --yes`** leaves a section with no end mark alone and names it.
- **`aidd status`** lists the open work: each Spec, Intent, and proposal, its status, its next step, and who takes it.
- **`aidd status` options.** `--who person` keeps what waits on you, `--who agent` what an agent does next, and `--json` gives a program the same answer.
- **One shape for a next step.** Every JSON output that names one gives it as `next`, an object with `what` and, when the output knows them, `code` and `who`. `status`, `validate`, `risk --paths`, and the delegate check all do.
- **Why a step comes next.** Each next step says why.
- **Steps for a built head and a merged change.** `aidd status` gives `spec.verify` for a built Spec until it is `in_review`, and `spec.observe` for a merged Spec whose observe window is open. Each starts a team command in `/aidd-team:autopilot`: `review` and `rollout`.
- **`aidd status <path or id>`** shows what stands behind a path or a work item: its Specs, the open Specs whose scope overlaps it, its tests, docs, and interfaces, its route, and its last commits.
- **The open work in every branch.** `aidd status --all-branches` covers every worktree and every local and fetched branch.
- **The index.** It reads through `.git/aidd/index.sqlite`, a cache that aidd rebuilds when it breaks.
- **`aidd explain <word>`** says what one of aidd's words means and why it matters. It quotes the file that owns the word.
- **`aidd test`** runs the project's tests, green on the head and red on the base for new behavior.
- **Evidence.** It binds each exit code to the head commit, and marks evidence from a dirty tree.
- **One verdict.** `aidd status` shows the result `aidd test` exits on: a full run in a dirty tree, and a `--changed` run with a bad result, read `failed`, and a `--changed` or `--no-red` run with none reads `partial`. A run in a dirty tree also says `dirty_tree`, so a green one reads as dirty, not as a failed test.
- **The last run on every Spec it tested.** The evidence names the Specs the run answered to (`specs`), and `aidd status` shows the run beside each one.
- **Faster runs.** `--changed` runs only what changed, and `--watch` runs again on each save.
- **A run that ran nothing fails where a test is needed.** A full `aidd test` exits 1 when no command ran because nothing is configured, or an applying Spec's commands were all skipped. The note names the step. When the config has commands but every `when_changed` skips the diff, the project says no test covers those paths. The run exits 0 and the evidence records `untested`. `aidd status` reads it as no test applied, and a delegated merge defers. A `--changed` run that selects nothing is `partial` and exits 0.
- **Every Spec that applies to a change has its tests run.** The diff may hold none, one, or several Specs. A Spec applies when the diff holds it (added, changed, deleted, or moved), the branch is `spec/<ID>`, or `--spec` names it. With several, each command is named `<Spec id>.<name>`. A branch named `spec/<ID>` with no such Spec stops the run, and so do two Specs with one id. CI reads the branch from its platform.
- **A Spec only reached by its scope gets a note.** An approved or in-progress Spec whose Task scope the change touches, without holding it, does not run, so an unrelated change never fails on tests that fail by design. The note names the next step, and the evidence lists it under `specs_not_run`.
- **The base decides.** The config's `specs_dir`, `docs_dir`, and `tests` with their `smoke` markers, and an approved Spec's status, route, scopes, frozen files, and commands, are read from the base commit when the base has them. The head's value applies to what is new. A change to one runs the head's and the base's, as `base.<name>`, with a note. A Spec built on the base runs red only if the base does not hold it built, so a prose fix to a done Spec passes.
- **A run that gates a merge excuses nothing.** `aidd test --require-green` counts a failing test as a failure even before Implement, and the evidence records it (`require_green`). The action, both CI templates, and the delegate's own run use it, so a check turns green only when the tests pass, and a Spec-approval PR is red until Implement. A local run still marks a Spec's own failing test `..` and exits 0.
- **The Design stage needs the stored status, and only a local run excuses.** A Spec's failing command is expected only while that Spec is `draft`, `ready`, or `approved` and the change holds only that Spec and the files it freezes. One Spec never excuses another's failure.
- **The merge check reads the same Spec.** A delegated merge judges the Spec `aidd test` runs for the change, and defers when the head deleted it, several apply, or the change only touches the scope of an open one, with the step to take.
- **A change cannot weaken the tests that check it.** When the head removes or changes the config's `tests`, `aidd test` also runs the base commit's, as `base.<name>`. No route, status, or frozen list the head sets drops or excuses them.
- **A test report.** A test command may name a JUnit XML `report`. `aidd test` records the failed test cases beside the exit code, which stays the evidence.
- **`aidd new`** writes a Spec, an Intent, a Proposal, an exploration, or a linked document, from an ADR to a runbook.
- **One architecture folder, one decisions folder.** `aidd new architecture` writes the overview to `docs/architecture/README.md`. A component that outgrows its section may get its own page beside it. `aidd new adr` numbers each ADR in `docs/decisions/`, MADR's folder, for any significant decision.
- **Your templates.** It starts from `docs/templates/<type>.md` when your team has one.
- **`aidd standard`** lists the open choices, the library's standards, and the stacks. `aidd standard add` copies one into a project.
- **Records.** After the agent acts on an answered ask, or takes a `report` action, it writes a record to `.git/aidd/records/`, outside the working tree.
- **What a record keeps.** A `decision` keeps the question and your reply word for word.
- **A record is history.** It is never a yes and never evidence. `aidd records` lists them.
- **Share the history.** `aidd records pull` and `push` share records through a remote's `refs/aidd/records`. Pushing is `records.push`, an `ask`.
- **Recall.** `aidd recall <words>` searches the records, the Specs and their documents, the ADRs, the glossary, the product brief, the improvement log, and recent commit subjects.
- **How recall searches.** It uses SQLite's full-text search and calls no model.
- **MCP.** `aidd mcp` serves eight tools. Five are for everyday use: `risk`, `status`, `validate`, `recall`, and `record`. Three are for delegation.
- **What the MCP tools write.** `risk`, `status`, `validate`, and `recall` only read, and `record` writes one record. Each of the five answers in JSON, and `record` returns the record it wrote, as `aidd records add --json` prints it.
- **Approved tools.** `aidd init` approves the five everyday tools in Claude Code and Codex.
- **Keep them asking.** Set `mcp: {allow_own_tools: false}`.
- **Files you can read.** Every file aidd reads is Markdown with YAML front matter, or YAML. Every format says `type`.
- **Where output goes.** Evidence and views go in `.aidd/evidence/` and `.aidd/views/`, which git ignores.
- **Exit codes you can script.** 0 is ok, 1 is a check that failed, and 2 is an error.
- **Every stop names its next step.** `AIDD_DEBUG=1` prints a traceback.
- **Docs that stay current.** The JSON Schemas and `schemas/risks.json` are the source, and `aidd gen-docs --check` fails on a stale table or count.
- **A glossary row for each concept.** A test fails on a concept with none.

#### Moving old files to today's shape

- **`aidd upgrade` moves a repository's files from an earlier shape of aidd's.** The config and the work items that still hold a retired name are renamed or cut key by key, with a line for each change, such as `would migrate specs/SPEC-1.md: uat -> manual_acceptance (retired in 1.0.0)`. It reads the shape from the keys in a file, so it needs no version and keeps no record. It edits the text, so your comments, key order, quoting, and line endings stay, and it reads each file again before it writes it. A second run changes nothing, and a file already in today's shape is left byte for byte. A dry run reads the files as the real run will leave them.
- **A cut prints the value it removes**, and a name aidd cannot place on a line of its own stays as it is. A `manual` line names the file and the name and says what to change by hand, and `aidd validate` names it too.
- **One table of retired names, `schemas/retired-names.json`.** A rename or a cut of a name a person writes is a row of data, with its schema, a generated table in the guide, and a fixture of the old shape in `tests/fixtures/migration/`. It replaces `standards/renames.yaml`. The error for an old name in the config, a Spec, an Intent, or an exploration says what replaced it and that `aidd upgrade --yes` moves it.
- **Known limits.** A remote `extends` parent is named and never moved. A name inside a flow mapping, or beside its replacement, is left for you. The old `delegation.default_branch_deploys` is never turned into an `environments` entry. `false` is cut and printed. `true` is cut only when an environment's `branches` already lists the branch that `delegation.default_branch` names, and any other `true` stays for you. A config that still holds that `true` does not load, so a delegated merge waits for a person until `environments` says where a merge deploys.

#### Records that read the same whenever they were written

- **A record keeps its file and reads in today's names.** A record is history, so aidd never rewrites one, and `aidd upgrade` leaves it alone. A record from an older aidd says `at` and `question.type: approval`. Each reader reads them as `recorded_at` and `yes_no`: `aidd records`, `aidd recall`, the work-item history, and `aidd risk --suggest` give the same answers for it as for its twin in today's names. Two `read_both` rows in `schemas/retired-names.json` say so.
- **`yes_no` is the question type for a yes or no.** aidd keeps "approval" for its two gates. `aidd records add` and the MCP `record` tool refuse to write `approval`, and the message gives `yes_no`.
- **A record this aidd cannot read in full is kept and named.** `aidd records pull` and `push` keep a record with a type, a field, or a value this aidd does not know, as a newer aidd writes, byte for byte. `aidd records` marks it `read in part`, and `--json` lists its id in `partly_read`. Nothing counts it as an answer or toward a rule suggestion. A pull still refuses a record with a secret, a size past the cap, or a missing or mistyped field, and names the file.
- **The delegate reads records by a stricter rule.** An accept counts only from the delegate's own `delegate_answer` that is today's shape in full, as it was written. A defer counts from any record that parses, because a defer only narrows. So an accept in the old shape no longer counts, and the delegate answers again.

#### One owner for each code

- **One registry for the codes aidd gives, `schemas/findings.json`.** A code, its severity, its title, why it comes, and its next step are one row, with a schema that checks the rows and a generated table in the [CLI reference](docs/CLI.md). Its first group holds the reasons `aidd delegate check` defers for, which moved out of `schemas/delegate-check.schema.json`. The check's `--json` output is byte for byte what it was. A test fails for a code the package gives with no row, and for a row nothing gives.
- **The step codes are data.** `step_code` in the common schema lists every code `aidd status` can give, who takes it, and what it means. A next step in any output refuses a code outside the list.
- **A `waiting` stop code.** A run that waits on a test runner, an observe window, or a clock says so, with the time, and a wait no longer reads as a failure or a block. It has its own stop rule in the skill.
- **Shared shapes for later outputs.** `finding`, `error`, and `blocked_by` are in the common schema, and a slice's `blocked_by` uses the last.
- **A team role is an agent.** An identity such as `role:architect` never counts as a person, so it cannot approve, own a flag, or triage its own suggestion.

#### Problems in `--json` output have one shape

- **`findings` beside the text lists.** `aidd validate --json`, `aidd doctor --json`, and `aidd status --json` add a `findings` list. Each finding has a `code` you can look up, a `severity`, a `message`, a `next` step, and a `path` when the message opens with a file. Each line of `errors`, `warnings`, and `notes` is the message of one finding. Every key these outputs printed before has the same value, and `findings` is the only new key.
- **An error object on stdout (a change to an output).** A `--json` command that stops with exit 2 now prints `{"schema_version": "1", "error": {...}}` on stdout. Before, stdout was empty, for example for `aidd risk --action pr.mrge --json`. The words on stderr and the exit code are the same. A command line the parser refuses prints it too. `aidd explain` for an unknown word keeps its empty `matches` and adds `error`.
- **Codes with owners.** The registry has a group for the command line (`cli`), the config (`config`), `aidd doctor`, `aidd status`, and `aidd validate`. A test fails for a code a package gives with no row, a code a package gives that is another package's, and a row nothing gives.
- **`aidd explain <code>`.** It answers each code with its title, why it comes, and the next step, and names the closest code for a mistyped one.
- **MCP tools return the same objects (a change to an output).** A tool that fails returns the error object, where it returned plain text. A tool refuses an argument it does not take and names the closest one it does.

#### A file from a newer aidd, and a tool's errors in its own words

- **Public contracts.** CONTRIBUTING.md's Versioning section has one table of every public surface: what a minor release may add, what only a major release may change, and how a reader treats a file that a newer aidd wrote. What aidd writes stays closed. What a program reads from aidd ignores a key and a code it does not know. A file a person writes, the config and a Spec's front matter, still fails on a key it does not know. `tests/test_public_contracts.py` holds the table against `schemas/`, and holds that a `--json` output read as a reader of a newer aidd reads it takes one more key in every object and a code its family does not list.
- **The public contracts cover every surface a program or a person relies on.** The table has rows for the environment variables, the GitHub Action's inputs, the commit trailers, the headings aidd reads in a document, and the plugins' names. A test derives each list from the code, so a new one with no row fails. The environment variables are in three kinds. aidd defines and keeps the `AIDD_*` ones. Another tool or the platform defines the second kind, which aidd reads. The third kind, such as `CI`, tells aidd where it runs. A test reads every lookup of the environment in the code, so a variable of any kind with no entry fails. The ledgers `.aidd/harness-rules.json` and `.aidd/team-files.json` have a row of their own: a newer aidd reads every older ledger, because `aidd upgrade` and `aidd uninstall` find what aidd wrote by it, and `tests/fixtures/ledgers/` keeps each shape that a release wrote.
- **A reader opens only a family of codes.** A schema marks a family of codes that a minor release may grow with `"x-open": true`: the step codes, the delegate check's reason codes, the types of `aidd explain`, and the codes a record holds. A reader of a newer aidd's output ignores a value there that it does not know. Any other `enum` stays closed, so an unknown `level` is an error.
- **A tool's error names arguments (a change to an output).** An MCP tool's error says `change_type`, `head`, and `limit`, where it said `--change-type`, `--head`, and `--limit`. A command a message points to stays a command, in backticks. A `recall` with no word and a `record` with no `type` or `by` are refused as arguments.
- **A recalled record says when it was pulled (a change to an output).** A `recall` match of a record that `aidd records pull` added has `"pulled": true`, and the text says `pulled from a remote`. Every other match is as it was.
- **`aidd explain` knows more codes (a change to an output).** It answers each step code `aidd status` gives, such as `spec.draft`, with what moves it on and who takes it, and a reason code of `aidd delegate check` without its group, such as `delegation_review_due`. `explain`'s `type` has the new value `step_code`.
- **The last test run's summary says what it cannot read.** A result with a `status` or `red_green` this aidd does not know reads as failed, never as passed, and `aidd status` says so with the step that clears it. When the run also answered to more Specs than the status shows, the note says both.

#### One name for each fact in `aidd status --json`

- **A change to an output: two keys of each item change.** In the output, `waiting_on` was a list of ids and `blockers` was the Spec's text, while the Spec itself calls the text `waiting_on` and its list of ids `blocked_by`. The output now follows the Spec. Old `blockers` (a string) is now `waiting_on`, the Spec's text as written. Old `waiting_on` (a list) is now `blocked_by`, the items the item still waits for, read now. Every value is the same under its new key. `blocked_by` in the output holds only the unfinished items, and it includes the slice line's, the parent Intent's, and the items that say they `block` this one, so it can differ from the `blocked_by` a Spec stores. A script that read `blockers` reads `waiting_on`, and a script that read `waiting_on` reads `blocked_by`. The work-items page and the MCP `status` tool read the same keys. `root_blocker` keeps its name: it is a line about the item that Specs wait behind, which no stored field names.

#### Config renames and cuts

- **A test command's `retries` is `reruns`**, in the config and in a Spec. A retry is a fix after a red run, and a rerun runs one command again. A Spec that is approved keeps its approval: the rename is no revision, so `aidd test` and the delegate's comparison with the approval commit read the old name as `reruns`.
- **A project rule's `applies` is `when_changed`**, the name a standard uses for the same facet.
- **A project rule's `check` is `enforced_by`**, a list of `tests` names, as a standard's is. A name that no `tests` entry holds is an error, so a rule never claims a check that does not run. `aidd upgrade` moves a `check` that names a `tests` entry and leaves a command for you to add as an entry.
- **A waiver's `approved_by` is `granted_by`**, because aidd keeps approval for its two gates. A waiver may now name an industry standard of the registry beside a project rule.
- **`project.dev_services` is cut.** Nothing ran its `up`, `down`, or `teardown`. Keep your services in your own scripts and name `AIDD_WORKTREE` there.
- **The writing levels say what they mean.** `ste-80` is `instruction`, `ste-100` is `controlled`, and `plain` stays. The plain-language skill, the templates, and the glossary use the new ids.
- **`project.writing.ste_100` is `project.writing.controlled`**, the list of doc types written at that level. `aidd upgrade --yes` renames the key, and a config that still holds the old one gets an error that names the new key. A level id in a document you wrote stays as it is, because nothing reads it.
- **The base commit of a branch forked before an upgrade is read in its old shape**, so `aidd test` still holds a change to its base's `tests`, and the upgrade itself counts as no change of them.

#### One name for a standard's source

- **A standard's source is a `citation`, in the registry, the team's data, and the library.** It holds `url`, the page, and `quote`, the words copied from it. The registry and the extensions had `evidence`, and a library standard had `source` and `evidence`. `evidence` now means only a runner's exit code.
- **`retrieved` is cut.** It always held the same day as `checked`, so it said nothing new.
- **`aidd eval standards` checks the same URLs and the same quotes.** Only the key changed, and no `checked` date moved. One definition in `schemas/common.schema.json` serves the registry, the extensions, and the library.
- **A copy of a library standard moves by `aidd upgrade --yes`.** An unedited copy is written again from the library. An edited copy keeps your lines, and its `source` and `evidence` become `citation.url` and `citation.quote`, with a line for each. `aidd doctor` names the new keys for a copy still in the old shape.

#### A Spec holds only what something reads

- **A Spec no longer names `aidd_version`, `assisted_by`, `labels`, or `experiment`.** The config holds aidd's version, each commit's `Assisted-by` trailer says which agent wrote it, a tracker holds labels, and an experiment is part of the tracking plan. `aidd upgrade` removes the first three and prints each value; it leaves an `experiment` for you to write into the tracking plan.
- **`confidence` and `trace_id` are optional.** Write `confidence` only as `low`, which stops the run. Unset, it is `high` while `open_questions` is empty and `medium` while it lists facts. Unset, `trace_id` is the lower-cased id.
- **`blockers` is `waiting_on`.** `blocked_by` lists work items, and `waiting_on` names the role, person, or interface a Spec waits on, so the two no longer read alike. `aidd status --json` prints it as `waiting_on` too (see "One name for each fact in `aidd status --json`").
- **`relations` is `blocked_by`.** A Spec lists the work it waits for in `blocked_by` and names the Intent it delivers in `parent`. A `blocks` entry becomes the other Spec's `blocked_by`. `aidd upgrade` leaves `duplicates`, `relates_to`, and a `blocks` whose target is no Spec of the repository for you.
- **`residual_risk` and `cost_estimate` move into `risk`**, as `risk.residual` and `risk.cost_estimate`, because a person approves them with the risk.
- **A Spec's design files are `docs` entries of type `design-files`.** `design.files` is gone. Each path is one `docs` entry, always frozen, so Spec approval freezes the same paths and a design file still changes only by `spec.revise`. `aidd upgrade` moves each path, and a design file listed before the upgrade is read the same way on the base commit and on the approval commit. A `design-files` entry that says `frozen: false` is an error, and one that matches no file yet is none, as before. `aidd trace` prints the type as `design-files`.
- **An upgrade is no revision of an approved Spec.** `aidd test` and the delegate's comparison with the approval commit read an earlier Spec in today's shape, from the rows of the retired-names table alone. A change to a value, a Task scope, or a frozen test file still differs.

#### An Intent holds only what something reads

- **An Intent no longer names `aidd_version`, `labels`, `context`, or `launch`.** The config holds aidd's version, a tracker holds labels, and the project glossary holds shared terms. Under `reaches: flagged`, the launch Spec is the last slice of the last phase. `aidd upgrade` removes an empty `context` and a `launch` that names the last slice. It leaves other values for you, and names each.
- **`relations` is `blocked_by`.** An Intent lists the work it waits for in `blocked_by`, as a Spec does. A `blocks` entry becomes the other item's `blocked_by`. `aidd upgrade` leaves `implements`, `duplicates`, `relates_to`, and a `blocks` whose target is no Spec or Intent of the repository for you.
- **`slices` is one phase of `phases`.** Every Intent lists its slices in `phases`. `aidd upgrade` turns a `slices` list into the phase `P1`, named for the Intent's title.
- **Every Intent now gets the `## Request coverage` warning.** An Intent with one phase listed as `slices` was skipped before.
- **An upgrade is no new agreement.** `aidd status` and `aidd validate` read the agreed version of an Intent in today's shape, so only a slice added or removed, or a new goal, asks for a new agreement.
- **The delegate reads the Intent on the default branch in today's shape.** An Intent that lists the Spec in its `phases` now makes its saved request the person's, as the `slices` form did.
- **A branch from before an upgrade shows the same work in `aidd status --all-branches`.** A branch tip is read in today's shape, so the upgrade splits no item in two.
- **The shared definitions `relation`, `relations`, and `labels` are gone from the schemas.** Nothing uses them now.

#### The handoff note's run block
- **A note may carry a `run` block.** It is the lead's snapshot of a long run at a stop. It holds the run's `id`, `attempt_counts` for each step on a work item, and `send_back_counts` for each work item. It also holds the `spend` it knows, the `unknown_spend_steps`, the `hours` used, and `resumes_at`, the time a `waiting` stop can go on.
- **Another session, machine, or person goes on from the note.** No limit restarts at zero.
- **An old note reads as before.** Only `id` is required inside the block, and nothing in the note is required that was not. A bad value in the block is one warning that names the field, and `aidd validate` blocks nothing.
- **`aidd status` shows the same lines.** It reads the note's text keys only, so the block shows nowhere twice and no evals count it twice.

#### One polarity, one identity grammar, and one deadline

- **`risk.reversible` is `risk.irreversible`.** A Spec says it the way `aidd risk --irreversible` and the risk rules do: `true` forces major and asks for the documents an irreversible change needs. A Spec that leaves it out is reversible, as before. `aidd upgrade --yes` writes the opposite value under the new name and turns the template's comment around, and an old Spec on the head fails `aidd validate` with the way out.
- **A role of the team is `role:<role>`.** `agent:` names only `agent:<harness>/<model>`. `aidd upgrade --yes` writes a Spec's `suggested_by: agent:<role>` and a Task's `assignee: agent:<role>` as `role:<role>`, and `aidd validate` warns about the old form until then.
- **The identity grammar is data.** `$defs/identity` in `schemas/common.schema.json` lists each type of identity and whether it names a person or an agent, and every check reads it through one parser. A role suggests work only as `role:<role>` or `agent:<role>` written exactly, so a case, a tenant, or a lookalike never passes for an allowed role. A handoff note's `by:` that names a role gets a warning, and `aidd eval work` no longer counts it as a person's step.
- **`emergency.review_due` is `emergency.backfill_due`.** `review_due` means a date to read something again everywhere else. One function reads the deadline: the day itself is in time, and from the day after the backfill is overdue until `outcome.learn_ref` records the review. `aidd validate`, `aidd status --json` (`backfill_overdue`), and the work-item page give the same answer.

#### One delivery team on every document that names one, and a manifest for the design tools

- **A runbook, a postmortem, and a proposal name their `delivery_team`.** The key was `owner_team`, a second name for the team behind a Spec, an Intent, and a slice. It is free text, and `aidd validate` warns about a name that is no key of `delivery_teams` once the config has any, so a repository with one team is never asked to declare it. A runbook still requires it.
- **`aidd new` takes one flag for the team.** `--delivery-team` names it for a Spec, an Intent, a proposal, a runbook, and a postmortem, and checks it against `delivery_teams` when the config has any. `--owner-team` stops with a message that names `--delivery-team`.
- **A runbook that restores data says `restores_data`.** It was `restore`. `aidd doctor` reads the new name and warns about a runbook that still holds the old one, because that runbook's restore drill would not be checked.
- **An outcome and a claim rest on a `basis`.** A spike's `evidence` and a proposal claim's `evidence` are `basis`, because evidence means a runner's exit code on a commit everywhere else. `aidd upgrade --yes` renames an exploration's and a proposal claim's `evidence`.
- **The design tools print a manifest with a schema.** `aidd prototype --screens` and `--components` follow `schemas/design-manifest.schema.json` and name their `schema_version`, as every versioned file does, where they named `format`. The product prototype's `sitemap.json` does the same, and the tool still reads a sitemap that holds `format`.

#### One reading of each retired name, and a frozen file that only a revision changes
- **`aidd upgrade` and the readers of an earlier shape share one function for each row of `schemas/retired-names.json`.** The file the upgrade writes reads as a check reads the commit before it, because the upgrade reads each row through that function first and must give its data. A name the upgrade leaves for a person is refused by the reader too, so nothing guesses. Such a name is an `enforced_by` beside a rule's old `check`, an `experiment`, or a relation with no place. So is an Intent's `context` with text, both names of a renamed pair, or a `risk.reversible` that is no boolean. A generated table over every row proves it.
- **A refused reading stops in the safe direction.** An approved Spec on the base stops `aidd test` with the step, and a draft binds nothing. A base config does not load. The delegate's approval commit defers. An Intent's agreement no longer stands until the person agrees again. A record with both `at` and `recorded_at` is unreadable, so the delegate defers. `aidd status --all-branches` lists the file as unreadable.
- **Holding a Spec is no revision.** A branch named `spec/<ID>`, `--spec`, or a prose edit no longer turns off the check of what an approved Spec froze. A change that records a revision (a new `revisions` entry) gets a note that names who approves again, and one that does not stops `aidd test --require-green`. The stop names a step that works for a second Spec: a new test file, waiting until the Spec is done, or revising it.
- **A frozen manifest section is its value.** `pyproject.toml#tool.pytest` or `package.json#scripts.test` freezes that section, so a dependency bump beside it passes, in `aidd test` and in the delegate's checks. A section that changed, a manifest gone or unreadable, and a whole-file entry still count.
- **A base config that does not load stops `aidd test --require-green`.** A first adoption, with no config at the base, stays the head's own.
- **A password in a URL is found at any length.** The detector looked for one up to 200 characters, so `aidd upgrade` printed a longer one. Its work on hostile text stays linear.
- **An emergency's `backfill_due` more than 30 days ahead warns** in `aidd validate`, as a delegation's `review_due` far ahead does.

#### Nine change types, and the risk dimension you declare
- **Nine change types, as in Conventional Commits.** They are `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, and `chore`. The type never raises the route, and a risk dimension does.
- **`aidd risk --dimension`.** It declares a risk dimension of the planned paths, as `aidd new spec --dimension` does, and repeats. A declared dimension raises the route as an area's dimension does: `data`, `security`, `privacy`, `financial`, and `compliance` make it major, and any other rules out minor. The MCP `risk` tool takes `dimensions`, a list. `--json` lists the declared dimensions in `dimensions`, and a reason line names them.
- **Five types were retired, each for a type and a dimension.** `data`, `security`, and `compliance` are the dimension of the same name, beside the change's own type. `deps` is `build`, and `infra` is `build` with `--dimension availability`. Each request takes the route it took before. `--change-type infra` is refused with what to type now, from its row of `schemas/retired-names.json`.
- **The next step keeps what you declared.** On a route that needs a Spec, the `aidd new spec` command that `aidd risk --paths` names carries each `--dimension` and `--irreversible`. `aidd new spec --paths` reads them too, so the Spec takes the route `aidd risk` gave.
- **The levels of a risk rule are read from `schemas/risks.json`.** The code keeps no copy of `allow`, `report`, and `ask`.

#### A route has its steps, and the lane is gone
- **One list of the steps each route runs.** `loop.routes` in `schemas/roles.json` holds them. The method's section 4.2, `aidd explain` for a route, and the reason under a step in `aidd status` read it, so no copy can drift. A test holds `normal` and `major` equal.
- **`aidd risk` gives no `lane`.** The answer, the MCP `risk` tool, and the trace carry the `route` alone, and a person reads a route as `no Spec`, `Spec first`, or `repair first`. Every route, step, ask, and other field of the answer is the same. `aidd explain lane` names `aidd explain route`.
- **An emergency's review comes before the merge, in the method as in the team's data.** Section 4.2 said it follows. Its Spec and its post-incident review still follow by `backfill_due`.
- **A role and a flow name the routes they work on, and a flow says when it stops.** `lanes` is `routes`, and `stops_at` is `stops_when`, beside a role's `starts_when` and `done_when`.

#### The team's data holds only what something reads

- **Autopilot lists the steps that start a flow.** A flow's `starts_on` holds step codes `aidd status` gives and an agent takes, and each such code starts one flow. `/aidd-team:autopilot` lists them from the data, and a test holds the rule.
- **The documents table shows who reads a document and what opens it.** `read_by` and `opened_by` are columns of `docs/TEAM-REFERENCE.md`.
- **The developer's agent file says it writes tests where nothing is frozen.** That is a change with no Spec, or the emergency route.
- **A stack-based suggestion nothing read is gone.** An extension no longer carries `suggest_when`.
- **Names that say what they hold.** In `schemas/roles.json`, a document's `owner` is `written_by` and its `scope` is `belongs_to`. An artifact's `type` is `from`, and `where` alone says where it lives. A decision right's `evidence` is `basis`, and it names its gate once, in `gate`: the loaded text puts the name before what is decided, so no text is matched. In `schemas/packs.json`, `owner` in `owned_elsewhere` and `tests_elsewhere` is `skill`, because it names a pack or a practice skill.

#### Every file that holds a retired name moves, a retired change type among them
- **`aidd upgrade --yes` moves a Spec's retired change type.** `deps` becomes `build`, and `infra` becomes `build` with `availability` in `risk.dimensions`. `data`, `security`, and `compliance` become `feat` with the dimension of the same name, and a note line says you may pick another type. A Spec on a commit before the upgrade reads the same way, so an approved Spec keeps its route, and the upgrade is no revision. A Spec that still holds a retired type fails `aidd validate` with what it became and `aidd upgrade --yes`.
- **`aidd upgrade --yes` moves a proposal, a runbook, a postmortem, and the product prototype's sitemap.** It reads `docs/runbooks/` and `docs/postmortems/` beside the specs and proposals folders, and `docs/design/app/sitemap.json` as JSON. `owner_team` becomes `delivery_team`, a runbook's `restore` becomes `restores_data`, and a claim's `evidence` becomes `basis`. A sitemap's `format: 1` becomes `schema_version: "1"` on its own line. The error for an old name says what replaced it, and so does the error for a missing `delivery_team` that an `owner_team` holds.
- **A Spec's route is never below its risk.** `aidd validate` refuses an open Spec whose `route` is below the route its `risk.dimensions` and `risk.irreversible` give, and names the step. An ended Spec gets a warning, because no step is left to route. `aidd new spec --dimension` or `--irreversible` without `--paths` takes the route they give.

#### Device sizes in the design system

- **One table of device sizes, in the design system's `tokens.json`.** A device frame is a real device's viewport, and each size carries the public source and the day it was read. The viewer, `aidd prototype --check`, and [DESIGN.md](docs/design/DESIGN.md) read it, so no size is a number someone picked. The first prototype's phone had been drawn at 360 by 576, a size no phone has.
- **`aidd gen-docs` writes `devices.json` beside the prototype tool**, and DESIGN.md's Device frames table. The prototype tool needs no aidd to read it.
- **`aidd prototype --check` fails a frame that is not in the table.** A deep link names a frame by id, such as `frame=ios`, and `frame=360` fails with the frames to name. A frame a design draws itself, `data-device="ios"`, has the table's width and height, a fixed height, and its own scroll. Each message says the next step.
- **The viewer draws its frames from the table.** The `320` frame is now 320 by 568, the iPhone SE (1st generation); it was 320 by 640, which no source confirms.
- **A phone's system bars come from the table too, and Fit shows each frame whole.** Each bar has its source, so the Android status bar is the Pixel 7's 52 px; it was 32. The caption gives each frame's width, height, and scale. A frame's edge meets 3:1 on the artboard, and each `--check` message names the frame and the style to write.

#### Diagrams that read in the light and the dark theme

- **Rules for a diagram that fits the page.** The `diagrams` skill's craft reference adds direction by the page's width, short labels, groups, when to split, one look for each kind of thing, and a palette. GitHub shrinks a diagram wider than its text column, so top-down is the default, and the skill's Review section says to look at each diagram in both themes.
- **A palette that follows the reader's light or dark mode.** Each class fills its box with its border's hue at a low alpha and sets no text color. A box is then a light card on GitHub's light page and a dark card on its dark page, and the theme keeps the text readable. Each border is mixed from a role's light and dark values to read alike on both pages. `default` tints every box and `group` or `boundary` every subgraph, so no lavender box or yellow group is left. The classes differ by border width and dash too, never by color alone.
- **A default palette, and yours.** `aidd new design-system` writes the default classes in your DESIGN.md: a quiet neutral, one accent, and three status hues. The templates' diagrams use them. Replace the hues with your own tokens' mixes under the same names, and the skill's check reads your DESIGN.md's lines.
- **aidd's own diagrams use aidd's palette**, from [DESIGN.md](docs/design/DESIGN.md), and a test holds every diagram to it, the generated ones too. The test also holds each diagram's size, its width estimated from its labels against the column, and its title, description, and legend. The team's loop is the one named exception to the size and the row: it stays whole and left to right.
- **The flows and the handoffs are tables only.** Their diagrams drew one row for each command and each handoff, which repeated the tables beside them at a size GitHub shrank below reading. The work-items diagram in METHOD.md now runs top-down.

#### The delivery team

- **Agent roles led by humans.** The optional `aidd-team` plugin adds <!-- aidd:gen count:roles -->12<!-- aidd:end --> roles, from product manager to SRE.
- **Commands.** It adds <!-- aidd:gen count:commands -->13<!-- aidd:end --> commands, from `/aidd-team:plan` to `/aidd-team:retro`.
- **Modes, not more commands.** `/aidd-team:plan refine` refines the backlog, `/aidd-team:specify explore` explores a question with two or three good answers, and `/aidd-team:implement rework` fixes a head that came back, which then goes to `/aidd-team:review` again. Each mode is data on its flow (`modes`), so the generated pages list it. `/aidd-team:propose` and `/aidd-team:handover` are client delivery.
- **No role for a domain.** A business pack starts no role of its own. The architect loads it in Plan and Specify, and the reviewer in Review, and each checks the work against its rules, its missed cases, and its Terms.
- **One Learn flow on a cadence.** `/aidd-team:retro` runs as a postmortem does: the SRE, with the `retrospective` practice skill, then the product manager, who drafts the suggested Specs. Its Upkeep mode, `/aidd-team:retro upkeep`, routes the stale standards, old flags, flaky tests, ending waivers, and runbook drills.
- **Other agents.** In every agent that reads skills, `--aidd-team` also writes each flow and each role file.
- **Autopilot.** `/aidd-team:autopilot` runs the loop and stops at each ask.
- **Autopilot sorts your request.** It takes the first path that matches, so a request in an empty repository runs the MVP flow.
- **Two ways to start.** Say your idea, or type `/aidd-team:autopilot` and the idea. To change existing code, ask in your own words.
- **A clickable result on Day 1.** An MVP's walking skeleton runs the lightest Specify its risk allows. Each slice ends by telling you what to click in the local preview.
- **Roles placed for the work.** The lead plays a role for a small step of its own work. It starts the role when it checks the work, runs cheaper, or works in parallel.
- **Effort by tier.** Each role thinks as hard as its tier asks, and `agents.effort` sets any level.
- **Perspectives before a plan.** The lead drafts a one-goal Intent itself, and the product manager writes several. The architect gives a card, always, and its flags bring in the designer and the security engineer. The lead folds the cards, with no second pass.
- **A small plan.** It asks the architect alone.
- **Specialists on what the files show.** Onboarding starts the architect, and the security engineer whenever the repository holds source code, because the areas it seeds are what every later trigger reads. The SRE joins when the dry run lists a file that builds, ships, or runs the code (CI, deploy, container, or infrastructure), or the architect flags operations. An MVP starts the designer only for a user interface.
- **Stale team files go.** `.aidd/team-files.json` records each team file aidd writes, by path and SHA-256. `aidd upgrade` removes a file aidd no longer writes while it still holds what aidd wrote, and keeps a changed one with a note. `aidd uninstall` removes each one that still holds what aidd wrote.
- **One list of the security engineer's areas.** Its `starts_on_areas` in `schemas/roles.json` names them once, by `aidd risk`'s area names, and every command that starts it on an area reads that list.
- **One developer for every code Task.** The Task's `skills` load the specialty, such as `ai-evals`, `ai-features`, or `schema-migration`.
- **Code for today's platform.** Before the architect, the product designer, or the developer adds a library or custom code, they use what the language, the runtime, or the platform gives at the versions the project supports. They look up an API's current form. A feature is widely available when every version the project supports has it, as the project's own files state that range, and any other feature needs a stated fallback. Where no file states the range, they name the range they assumed: in the Spec when they write it, else in the handoff note. In existing code they write a new part the current way where it stands alone, and match the code around a line they change. They report an old pattern they leave as `debt:` in the handoff note's `done`, so a person can make modernizing it a change of its own. The reviewer's file shows the rule's own text, from the same data, and then how the reviewer applies it (`reviewed_as`, an optional field of a contract rule that any rule may use). An old pattern in a new part that stands alone is a finding. In a line added or changed inside existing code it is one only when it differs from the code around it. A feature that some supported version lacks, used with no stated fallback, is a finding. Where no file states the range, the reviewer judges against the range the author named, in the Spec or the builder's handoff note, and a range no one named is a finding. An old pattern in code the change did not write is a `debt` finding, never blocking.
- **An old pattern is held by a ratchet.** The maintainable-code skill has a Task report an old pattern it leaves as `debt: <what, where>`. A wide pattern the project wants gone gets a ratchet: a count for one pattern, kept in a baseline file, that may fall and never rise. The count is per pattern, so moving code never fails it, and the reviewer flags a raised baseline. `/aidd-team:retro upkeep` lists each `debt:` line as a `tech-debt` item for a person to decide, and the improvement log takes the pattern as a row of type `lint`.
- **The developer reproduces first.** On a bug, a red check, or a flaky test, the developer writes a failing test and sees it fail before the first edit.
- **The developer fixes the cause everywhere and runs the change as a person would.** A fix names its invariant in one sentence, fixes every site that shares its cause, and shows each new-behavior test failing before the fix. A CLI or config change also runs in a scratch copy: from another folder, with a typo, as a dry run where there is one, then for real. `test-design` asks for a table or generated test where the inputs are open-ended.
- **A plan with its risks named.** The architect names what could break, the riskiest step, and what it chose not to do. The diff must match the plan.
- **One stop for a Spec's foreseeable asks.** Spec approval asks, in one numbered question, each ask the Spec's work will need.
- **A recommended answer for each ask.** Each row has one, and each is asked once.
- **Where the work stands.** At each step's start and end, the agent says where the work is, what comes next, and when it needs you.
- **A stop is one short question.** It has a recommendation and the words to reply. One outcome takes one yes.
- **Returns in files.** A specialist writes what another role folds to `.aidd/returns/<ID>/<role>.md`, so no return passes through the chat.
- **Verify and Review side by side.** Once a head is green, the verifier and the reviewer check that head. A failure in either returns to Implement.
- **Re-review after a rework.** The same reviewer checks each finding against the fix's own commits. A major change, or a fix that reaches a new path or area, gets a fresh full review.
- **A read-only reviewer.** The reviewer changes no file. It judges test strength from the verifier's `aidd test` run: each Acceptance line red on base, and each surviving mutant.
- **Independent review.** `agents.independent_review` opts in to a verifier and a reviewer on another provider than the developer's.
- **A second reviewer.** On the major route, or when the diff changes the risk rules, the harness ask rules, or the release workflow, the review flow also offers a read-only Codex reviewer.
- **Asked first.** The review flow asks you before it starts that reviewer.
- **Orca workers.** Where Orca is installed, `/aidd-team:autopilot` may run a step in an Orca worker in its own worktree.
- **Task branches.** Autopilot merges them one at a time.
- **A spend cap.** `agents.max_tokens_per_run` is 50,000,000 tokens by default. Autopilot stops at it where the harness reports each step's tokens.
- **No cap on Claude Code.** There the cap can't stop a run, and autopilot says so at launch.
- **Security guidance.** `aidd init --aidd-team` writes `.claude/claude-security-guidance.md` for Claude Code.
- **Only the packs you need.** Without the plugin, `aidd init --aidd-team` writes the practice skills and only the domain packs the repository calls for. A pack comes from a manifest's dependencies, from a risk area `aidd risk` matches on a tracked path, from `project.compliance`, or from `agents.domain_packs`, for a domain no file names.
- **A missing pack is named.** `aidd risk --paths` hints when a matched area's pack is not installed, `aidd doctor` warns, and `.aidd/team-roles.md` lists every pack with the next step.
- **An upgrade keeps them.** `aidd upgrade` keeps each pack already there, and adds the one a new manifest calls for.
- **A security finding has a shape.** It names who attacks, the input they control, the control it gets past, the boundary, the impact, and the proof.
- **Living product documents.** `aidd new` writes a product brief, a metrics dictionary, a control register, an improvement log, and a service card for each service.
- **Requirements specification.** `aidd new srs` generates one in ISO/IEC/IEEE 29148's outline.
- **Client work.** The `delivery-manager` role qualifies client work, keeps the RAID log, and writes the contract.
- **Handover.** `/aidd-team:handover` hands a delivered system over for sign-off.
- **A fuller handover list.** The acceptance record's Handover list also holds the repository and what it leaves out, the third-party licences, the vendor accounts, the client's data, the agent setup, and who decides. It asks whether the client keeps aidd.
- **AI-use questions in a client engagement.** The contract template asks the questions, such as whether the client's code may reach a model provider. The proposal's first question round asks them too. aidd writes no answer and no term.
- **Two repositories for a client engagement, or one.** The firm's home repository holds the proposal, the contract, and the Intent. The client's repository holds the product. The client-delivery skill says what the handover checks when there is only one.
- **Warranty or new request.** The support desk sorts a client's report by the contract's Warranty section. A defect against an accepted Acceptance id inside the period is fixed. Anything else is a change order.
- **A proposal leads to a plan.** `/aidd-team:plan` takes an accepted proposal's id and sets the Intent's `request`, `proposal`, and `covers`.
- **Delivery teams.** The config's `delivery_teams` names each team sharing a repository, and `aidd status --delivery-team <name>` shows one team's work.
- **Setup from the chat.** `/aidd-team:onboard` asks once and runs `aidd init` on your yes.

#### Plain language

- **Three questions before you write.** The plain-language skill asks what the reader does next, what the answer is, and what the reader has not seen.
- **Limits with an owner.** A table gives each limit, who sets it, and what holds it. The 20, 25, 6, and one instruction are ASD-STE100's, taken from public secondary sources. The 10% share and the 35-word cap are aidd's own.
- **A pair for each rule.** `references/examples.md` shows a rule as a before-and-after row, with words from unrelated products.
- **A proof for each rule.** A test fails when a rule has neither a check nor an example row, and when the limits table differs from the measure.
- **Comments held to the cap.** No sentence in a page's comments, such as a template's guidance to its writer, has more than 35 words.
- **A report on the agent files.** `python3 tests/test_plain_language_report.py --report` counts the colon and parenthesis shares, the long numbered steps, and the long paragraphs. It never fails.
- **The writing level has a glossary row.** It defines `instruction`, `plain`, and `controlled` once.
- **Two more roles may load the skill.** The developer and the reviewer load it on its signal, never at start.

#### Standards and packs

- **Domain packs and practice skills.** The roles read <!-- aidd:gen count:packs -->27<!-- aidd:end --> domain packs and <!-- aidd:gen count:practices -->37<!-- aidd:end --> practice skills.
- **Design practice for contracts.** The `cli-design` and `data-model-design` practice skills hold the rules for a command-line interface and for a data model. A new flag, key, or field then fits recognized practice and the project's own name families. The data-model skill also covers how data flows. It records who writes a field and who reads it, and which copy decides. It says what a reader does with a value it does not know, and it proves a change that removes or renames a field, or changes what one decides, with a table of answers.
- **Dated standards.** Each standard records its source, its edition where it has one, and a `checked` date. `aidd eval standards` fails on an entry past its review.
- **Business domains.** Each business pack names its terms and its invariants, which the role that loads it checks a plan, a Spec, or a diff against.
- **The standards library and stacks.** A library standard fills one open choice, such as the linter, with one default per ecosystem.
- **Adopting one.** `aidd standard add` copies a standard or a `--stack` into a project, with its tests.
- **Product building blocks.** Open choices with checked defaults for sign-in, access control, transactional email, feature flags, background jobs, and error tracking.
- **Compliance.** The `enterprise-controls` pack maps each control to SOC 2, ISO/IEC 27001:2022, and GDPR, with the test or record that proves it.
- **Product defaults.** `project.defaults` gives every product light and dark themes, responsive layouts, security headers, and more.
- **Laws by their dates.** The packs carry the EU Cyber Resilience Act's reporting duty, which applies from 2026-09-11, the EU Data Act, and the US rules on automated decisions.
- **The `cra` target.** It needs a declared support period, and `aidd validate` fails without one.
- **A vulnerability policy.** `aidd new vulnerability-policy` writes it, and `aidd doctor` checks `security.txt` and its `Expires`.
- **Emerging tools, marked.** LangGraph.js, Mastra, and Vercel's Workflow DevKit are options for agent frameworks and durable workflows. None is a default.
- **Templates held to their standards.** The ADR follows MADR 4.0.0, the SLO the SRE Workbook, the threat table the ICO's scale, the architecture overview arc42 and C4, the design spec ISO 9241-210, and the runbook the SRE Workbook's playbooks. The DPIA lists WP248's nine criteria.
- **One document for one reader.** The rollout plan is the Spec's `## Rollout`, the on-call rota is the service card's, and the client handover is the acceptance record's. The service card holds the current objectives, error-budget policy, and alerts, so a Spec's SLO document is a frozen delta. A vendor's data processing contract is the data map's.
- **Templates restate no trigger.** `references/spec-docs.md` says when a document is required.
- **Template details.** The `accessible-ui` practice skill holds the EU accessibility statement. The vulnerability policy writes its CRA section only with the `cra` target. Release notes list every merged change. The SRS has a constraints section and groups other requirements by risk dimension.
- **A guide to modern web features, registered as emerging.** Modern Web Guidance, from Google Chrome, is a registry entry with a 90-day review, and the web front end pack cites it. aidd cites it by name and copies none of its text, because its guide text is CC BY 4.0. A guide is an input to a choice and never a rule, so a feature's status stays with the web-features data. The pack says that its command-line tool sends usage data to Google by default, and that `DISABLE_TELEMETRY=1` stops it.
- **A rule for when a web feature may be used.** The web front end pack's Specify step makes a feature inside the Spec's browser target the default, with no fallback. A feature outside it, such as a newly available one, has a stated fallback and what the person sees in it. A feature with limited availability, such as one in a single engine, is used only when the Spec names it and its fallback. The status comes from the web-features data on the day, and the registry holds no per-feature status.
- **A platform feature before a library.** The web front end pack's Implement step names the `dialog` element, the `:user-invalid` state, and container queries as examples, each widely available.
- **Form feedback you can observe.** The accessible-ui skill's `references/criteria.md` adds six checks for the web. An error is not shown by color alone. An error shown on submit is read when its field takes focus. An error that appears while focus is elsewhere is announced through a live region. A failed submit moves focus to the first invalid field, or to an error summary that links to each, as a practice no success criterion requires. A field's hint is tied to it. Focus lands somewhere sensible when its control is disabled or removed. Each names the WCAG 2.2 success criteria it serves.
- **A browser CLI for a role's own look at a running page, registered as emerging.** agent-browser, from Vercel Labs, drives a browser through a background daemon and returns the page as compact text. The web front end pack offers it only to a role whose harness gives it no browser tools and only a shell command. The Playwright MCP tools that the designer and the verifier use come first. It changes no role's tools, and the runner for committed end-to-end tests stays the pack's open choice.

#### The loop, the team install, and CI

- **Implement accepts every approval path.** Its precondition reads `status: approved` with `approved_at`, and `approved_by` or `delegate_answer`. Where `spec.approve` is `report`, `approved_at` alone holds: the agent says it goes on, then sets `status: approved` with no `approved_by`. `references/state.md`, the Specify flow, and METHOD.md say so.
- **A role file carries only the rules its tools can act on.** A contract rule may name what it `needs` (the harness's tools, or a write area), and a role with only its own tools drops the rules that need more. The delegate's first rule is to accept only on an eligible check, and its file no longer sends it to a skill it cannot load. The verifier no longer claims to write no file, and a test checks that every tool or skill a role file names is in its `tools:` line.
- **A project install ships each team skill whole.** `aidd init --aidd-team` writes each skill's `references/` beside its `SKILL.md`, and a link from one skill to another names the installed folder. `aidd uninstall` removes the folders inside a skill too.
- **Your CI runs `aidd validate`.** The GitHub action and the GitLab template run it after the tests, as aidd's own CI does. The action prints each warning and error as an annotation and fails on an error, and `validate: "false"` runs the tests only. `upload-logs: "false"` uploads `evidence.json` without each command's full output. In the GitLab job, the variable `AIDD_UPLOAD_LOGS: "false"` does the same.
- **`aidd explain` answers `evidence`, `frozen`, and `headless`.** They are the first `term` words, read from the common schema. A test lists the glossary terms the skill uses that it still cannot answer.
- **A dirty tree says it exits 1.** A full `aidd test` in a dirty tree names that in its note. The exit table in docs/CLI.md lists three causes of exit 1: a failed test, a full run that ran no command, and a full run in a dirty tree.

#### Views

- **`aidd status --html`** writes the open work as one read-only page in `.aidd/views/`, in light and dark, at WCAG 2.2 AA.
- **Needs you.** This view lists what waits for a person, with the words to copy.
- **Board and Tree.** The Board shows each open Spec by stage. The Tree shows each Intent's progress by phase.
- **A page that loads nothing.** Its policy pins its one style and one script by hash.
- **The whole product, clickable.** `aidd new product-prototype` starts the designer's prototype in `docs/design/app/`. `aidd prototype` assembles it into one page and checks it.
- **One navigation.** `sitemap.json` defines it once.
- **One prototype viewer, like a design tool.** It has device frames for the web, iOS, and Android, a review column that opens the next unseen state, and a Board of every screen in every state.
- **Comments.** A comment pins to an element.
- **Seen states.** A state counts as seen once the viewer has shown it on each platform and theme the design styles.
- **A phone review.** `aidd prototype --serve` serves the design on 127.0.0.1, or on your network with `--lan`.
- **Components named once, built once.** `aidd prototype --components` prints the component contract. `--stories` fails when a variant has no story.
- **A design system in design.md's sections.** `aidd new design-system` writes `DESIGN.md` in Google Labs' design.md format, an emerging one at version alpha.
- **One design system for aidd's own pages.** `src/aidd/views/design/tokens.json` holds every value in the Design Tokens format, and `components.css` holds the shared components.
- **Generated CSS.** `aidd gen-docs` builds it from them, and `--check` names any drift.
- **Shared by three pages.** The status page, `aidd explore`, and the prototype viewer draw from it.
- **Accessible and comfortable UI.** The `aidd-team:accessible-ui` skill keeps WCAG 2.2 AA as the floor and adds comfort as the target, with a standard-library APCA check.
- **Contrast.** Every color pair passes AA in both themes.
- **Axe.** The status page passes axe's checks at a phone width and at 1280 px.
- **The product designer checks the finish.** The fidelity pass reads a screenshot of every state at three widths, in both themes, at 200% text and right to left.
- **Explorations.** `/aidd-team:specify explore` drafts two or three directions, and `aidd explore` renders one page that compares them.
- **Direction comments.** They pin to a direction in each round.
- **Agent rounds.** Before Spec approval, the product designer starts one critic subagent and merges its comments into the round's file, each with its writer in the optional `by` field.
- **No agent approves.** No agent marks a state seen or approves.

#### Evals

- **Agent evals.** `aidd eval tasks` runs your own tasks. aidd's own development also runs `aidd eval routing` and `aidd eval roles`, which score an agent on routing and role scenarios.
- **You run them.** You run evals by hand with the agent you name.
- **Transcripts.** In aidd's own development, `aidd eval transcript` reads a recorded Claude Code run with no model.
- **Roles scored on the decision.** In `aidd eval roles`, each role answer ends with the six-line handoff note and one `Decision:` line. The scorer compares that value with the right one.
- **Skills in the prompt.** `--with-skills` sends each role the skills its agent file preloads.
- **Cost per pass.** When the agent command emits `stream-json`, the evals record each trial's tokens and cost. `aidd eval report` shows dollars per passing trial.
- **Compare two variants.** `aidd eval compare a.jsonl b.jsonl` prints the difference in mean pass@1, the share of cases an agent passes on the first try.
- **A 95% interval.** The comparison adds a range that holds the true difference in 95 of 100 repeated experiments.
- **A firm verdict needs data.** It never calls a difference firm below 10 shared cases or below `--repeat 3`.
- **Held-out cases.** About one case in five is held out by its id and a fixed seed. A run prints the score on both sets.
- **Reliability across repeats.** `--repeat K --min-pass-k SHARE` fails a run when too few cases passed every repeat.
- **Cases for any project.** Each case names its project shape (type, stage, team, regulation) from `evals/shapes.json`, and the claim it proves from `evals/claims.json`. `evals/README.md` shows the shapes no case covers, and a test fails on a case that names no claim or shape.
- **Plugin evals.** Cases for the team plugin check that practice skills load when a request calls for them.
- **Outside the plugin.** The team suite is in `evals/team/`, so no install carries it. Its trigger cases are written from `triggers.json` before a run, and no commit holds them.
- **Flow cases.** They run `/aidd-team:specify`, `implement`, `fix`, and `review` from a seeded repository.
- **Proven cases.** Each case has a right transcript it passes and wrong ones it fails.
- **A work history reading.** `aidd eval work` reads a repository's commits, `Assisted-by` trailers, Specs, records, and handoff notes with no model.
- **What it reports.** Flow efficiency, suite runs per head, decisions per change, the Verify reject rate, rework loops, and a stall reading.
- **The retrospective reads it.** `/aidd-team:retro` starts from `aidd eval work`'s baselines and compares them with the last ones.
- **Pinned tool versions, checked.** `aidd eval standards` lists the tool versions that packs and practice skills pin. `--online` flags a newer major release.

#### The public pages

- **One owner for the description.** `schemas/product.json` holds the description in a long and a short form, and the keywords. `aidd gen-docs` writes them into the package metadata, the Claude Code manifests, `llms.txt`, and the lead of the README, so no copy can drift.
- **A help page that starts with an example.** `aidd --help` opens with the short description and two commands to try first.
- **A README that shows the change first.** It leads with a change to payment code, with the Spec approval question and the tests failing first. It says what aidd does not do, and it drops the claims the code does not hold: proof at every step, records you can check, and a test writer who never makes it pass.
- **An index for agents.** `llms.txt` links the raw Markdown pages with one line each, and one paragraph names every term and links the glossary, so the glossary alone defines them.
- **An install runbook that asks only what is yours to decide.** It asks about the Claude Code plugins apart from the delivery team, and installs the plugins only on your yes. It says one thing about unreleased code, for the install and for the update. It points to the skill for the rules of work, and it counts the files of the setup commit as a person reads them.
- **Plain `unittest` projects found.** `aidd init` binds `python3 -m unittest discover` when a Python folder's tests are `unittest` tests alone, so it asks for no test command it could find. A folder that names pytest, holds a `conftest.py`, or has a test that imports pytest keeps pytest.
- **Front-door claims held by a test.** A page a stranger reads first cannot return a claim an audit showed the code does not deliver.

#### The README's first screen

- **The name, what aidd is, then how it works.** The README opens with its name, centered, then one line that says what aidd is and who decides. The picture below it shows the six stages and the four gates where you decide. It uses the colors of aidd's own pages, and a test keeps its labels at 12 px or more on a phone.

#### Claims that match the code

- **What holds a frozen test.** The pages, messages, and comments name the controls that run: the harness's edit ask where one exists, a person's review, and the merge check of a delegation (`aidd delegate check`). That check defers when a frozen file differs from the Spec's approval commit. `aidd validate` and `aidd test` compare no test with its approved form.
- **The edit asks after Spec approval.** The loop tells the agent to run `aidd upgrade --yes` after the approval commit, because the harness's edit asks for a newly approved Spec's tests exist only after it. The approval question names the command.
- **Method citations.** The schema cites the method by section anchor and not by number, and a test checks that each `METHOD.md` anchor and number resolves.

#### Answers and next steps that hold from anywhere

- **The top of the repository.** `aidd init`, `upgrade`, `uninstall`, and `doctor` work on the top of the repository the current folder is in. Given a folder inside a repository that is not its top, they refuse and name the top. `aidd init` in a folder no git repository holds refuses before it writes, and a dry run says so.
- **`aidd explain` knows the words a risk answer uses.** `ask`, `allow`, `report`, `level`, `action`, `area`, `route`, and `profile` each answer from the schema that owns them. A word that is close to none gets no guess, and the message points to `aidd recall`.
- **`aidd doctor` names a next step that exists.** It no longer sends you to `aidd owners`, which is no command, each warning now says what to do, and the longest notes are shorter. A test checks that every `aidd <command>` a message in the source puts in backticks is a command.
- **The model setting tells the truth.** `aidd init`, `upgrade`, and `doctor` say so when `agents.models` or `agents.effort` is set and the aidd-team plugin carries Claude Code's roles, because the plugin's agent files then ignore it. `aidd doctor` also compares the role files with the config and reruns the independent-review check, which only `init` ran before, and `upgrade` prints the same check. The lead passes the alias the role's agent file names and passes none when that file names a full model id or `inherit`. The note for a model Claude Code cannot select names the alias that runs. The guide no longer lists Codex model names that no file wrote, and no longer tells you to edit a generated file.
- **One answer to which branch is the trunk.** `aidd test --changed` and the push rules read the same function. A repository whose trunk is neither `main` nor `master`, and that names it with `git config init.defaultBranch`, now works for both. Where aidd cannot tell, the error and the `aidd risk --command` answer name `git remote set-head origin --auto` and that setting.
- **Claude Code's user folder.** The doctor's check for hooks switched off in your own settings reads `CLAUDE_CONFIG_DIR` when it is set, and so does the hint that Claude Code is on your machine.
- **Fewer copies and unused names.** Six places that spelled the Spec and Intent types inline read one constant. Three names no one outside their package read, and a preview folder constant and a decision list nothing used, are gone. Comments say what a thing is and not the id of a backlog row, and `pyproject.toml` no longer names a gate job that aidd lacks. A test holds each of these.
- **A bounded `aidd risk --paths` answer.** The JSON lists at most 50 paths of each area, gives the full count in `areas[].path_count`, and names in a hint how many an area left out. The route, the edit level, and the scope of a new Spec still come from every path.
- **One answer to "is this a glob".** `*` and `?` are wildcards and a bracket is a letter, as the path matcher reads them, and every place that tells a glob from a path asks one function. A Task scope such as `src/[id]/page.tsx` is now a file in the route and in the scope of a new Spec alike.

#### What the test run says about a moved branch, a revised Spec, and a push

- **A moved target is said, not failed.** The base is the commit a branch forked from, and the author chooses it. When the default branch is ahead of that commit and changed the config's `tests`, `specs_dir`, `docs_dir`, or the state of a Spec the run answers to, `aidd test` prints one note and the evidence records `target_moved`. The note says the run used the fork point's values and gives the next step: update the branch, then run again. The run never fails a branch for a test it cannot pass yet, and it reads the local ref, with no network call. The ruleset aidd writes now turns on "Require branches to be up to date before merging", which holds a change to the newest tests; a merge queue does the same. SECURITY.md, the guide, METHOD, and `aidd doctor` say so.
- **A revised approved Spec names who acts and the step that works.** The person who agreed to the revision (`spec.revise`) approves the Spec again. A base command the head changes or removes must still pass on the head. So the note says to keep the old command and its test file working in this change, and to remove them in a later one. A test runs each shape as CI does and shows that none needs a bypass. A Spec and its failing test alone stay red. The guide's troubleshooting gives the steps.
- **A push that names every destination is not raised by `remote.<name>.push`.** With that setting, `git push origin feat:feat` no longer asks, because git applies the setting only to a refspec with no `:<dst>`. A mirror remote and a redirecting `push.default` still raise every push.

#### Reviews that see both directions, and scratch work that never waits for you

- **Two questions in every review.** The reviewer and the security engineer ask what a change lets through that it should stop, and what honest work it now blocks or slows. A finding of the second kind ranks like the first, and a new control names the honest work it could block.
- **Each finding says how it was shown and what it is.** `shown` is `ran` (the command and its output) or `read` (the lines), and a `read` finding is never Critical or High without the input and the test. `origin` is a `regression`, a `new gap`, or an `older gap`, found by running old and new on one repository. The values live in `schemas/roles.json` (`loop.review_report`), and `aidd gen-docs` writes them into the code-review skill's `references/review-output.md`.
- **A report that survives being cut off.** It opens with a verdict that counts findings by origin, by question, and by those that block, then one line per finding, in under 300 words. `scoring.review_report_misses` checks that shape with no model, and an eval case asks for it with `review_report: true`. `REVIEW.md` gives the same shape to any reviewer.
- **One rule, not a list of cases.** On the third round of findings in one component, a review proposes to shrink it or to state its boundary once. For a changed reader, parser, or decider it asks which test compares the new answers with the old, and the security engineer states its threat model before the findings.
- **No scratch folder is cleared with `rm -rf`.** The skill and the verifier now say to make a new `mktemp -d` folder for each trial, leave it, and never reuse or clear one. The developer's done condition adds the differential test and the honest work a new control could block.
- **Commands a person can read.** A command that deletes, moves, overwrites, pushes, or publishes names its target as a literal path, one such action a line.

#### Agent files that do not repeat the skill they preload

- **A role that preloads the aidd skill no longer carries the rules that skill already gives it.** A rule in `schemas/roles.json` names `in_core_skill`, the phrases the skill holds word for word, and the product manager, architect, product designer, and developer files leave it out. Every other role still carries it. A test proves each rule reaches each role through its file or the skill, never both and never neither, so the mean fixed text per subagent falls by about 330 bytes.

#### Evals you can trust before a model runs

- **A closed claim registry.** `evals/claims.json` lists every claim a case may prove, with what makes it real. A gate names its action, a stop names its stop code, and a route outcome names its route. A duty sits under its role, and a control or a principle names the file that holds it. A case that claims a name the registry lacks fails a test, and so does a listed claim that no case proves. The four gates and the stop codes are claims now, and a local merge case claims `git.merge`, not `pr.merge`.
- **Held-out cases are data.** A case's `tier` says it is held out, and `evals/held-out.lock.json` holds a hash of each and the date a run first scored it. A test fails on an edit after that date, and on a skill, role, doc, test, or other case that quotes a held-out case. The id hash and `MOVED_TO_DEVELOPMENT` are gone.
- **A recorded run names its model and its commit.** `aidd eval --record` needs `--model-label`, and refuses to start when the case files or the prompt text differ from the commit the record would name. The manual workflow sets `EVALS_MODEL_LABEL` for it.
- **Every grader is shown to fail before it is trusted.** Each deterministic grader of the plugin and team suites is failed by a wrong sample and passed by a right one and a second right one in other words, and a test holds it. The audit's 20 worst graders now read the whole seeded file, the effect (a stub's log, the files left, the trace), or a paraphrase family, where they read one line, one tool, or one wording. Each routing case has its samples too.
- **A regex reads the same in the live runner as in the tests.** The runner reads JavaScript, so a test refuses `\A`, `\Z`, an inline flag, a Python group, and `$` without the `m` flag. Four patterns that used them are fixed.
- **Shared graders have one text.** 63 library graders in `evals/library/` stand for 208 case files. `python3 -m aidd.evals.grader_library` writes the copies, and a test fails on a copy that differs and on two cases that hold one grader alike with no entry.
- **Graders that read what an exploit leaves.** A post-commit hook logs each commit message, so an `Approved-by` or `Decided-by` trailer the person never gave fails a case. A decision record the agent wrote for an answer nobody gave fails the delegate cases. A delegate case ties the lead's "Delegate answered" line to the delegate's own result and fails a merge after a defer.
- **A case a model must judge says so.** The tag `grading:judge-needed` marks a case with a wrong answer that no deterministic grader fails, and a test keeps the tag true.
- **Every case builds a repository aidd accepts.** A test builds the repository of each plugin and team case, as the runner does with no model, and `aidd validate` and the part of `aidd upgrade` that migrates retired names read it. 24 fixtures wrote a Spec with `aidd_version` or `assisted_by`, and 12 wrote one with fields missing; all are fixed. Eight cases stay invalid on purpose, each listed with its reason, and a listed case that becomes valid fails.
- **Cases are set in more than one world.** `evals/worlds.json` lists twelve worlds, each a programming language and a business domain with a small seed project. A test builds each seed with no model and checks that `aidd validate` passes there, that `aidd risk --paths` gives the route the file states for its paths, and that the project holds its language and no other. Each plugin and team case that builds a project names its world in a `world:<name>` tag, and a test checks the project holds that world's language. No world, language, or domain may have more than 40% of those cases, except four that are over it today, each held at its count, and a count may only fall. They are the world `none-general` (29 of 72, 40.3%), the language `none` (29 of 72, 40.3%), the language `python` (40 of 72, 55.6%), and the domain `general` (39 of 72, 54.2%).

#### A first paragraph an agent follows, and a project guide that stays true

- **The block in `AGENTS.md` opens with the command to run.** It tells the agent to run `aidd risk --paths <the paths you plan to change>` before its first edit and to follow the route and next step it prints, and says the skill tells what to run when `aidd` is not on the PATH. With `--no-skill` it names the plugin's skill and no longer points at a `loop.md` path that does not exist. The block grew by 154 bytes.
- **Claude Code reads your guide and the block once.** Claude Code reads a `CLAUDE.md`, a `.claude/CLAUDE.md`, or a `CLAUDE.local.md` in place of `AGENTS.md`. `aidd init` now adds one line, `@AGENTS.md`, between aidd's marks in your `CLAUDE.md` (or `.claude/CLAUDE.md`), instead of a copy of the block, and makes a `CLAUDE.md` with that line beside a lone `CLAUDE.local.md`, which it never writes. A file that links to `AGENTS.md` or imports it already is kept. `aidd init --dry-run` and `aidd upgrade` show the change before it is made, `aidd upgrade` turns an older copy into the import, `aidd uninstall` removes it and keeps your line endings, and `aidd doctor` warns when a file hides `AGENTS.md` and nothing imports it.
- **Each coding agent's harness data lists the files it reads at the start of a session**, with the vendor page and the date aidd read it. Four agents have no page that says it (Cursor, DeepSeek Harness, Muse Code, TraeCode), and the data marks them unconfirmed. A table test checks, for every agent, that a file it reads holds the sentence that names the first command.
- **The skill description and the MCP instructions match a plain first request.** The description names a bug fix, a feature, a refactor, a docs edit, a commit, a push, and a PR/MR. The MCP instructions start by asking for `risk` with the planned paths before the first edit.
- **Two engagement cases are written for the plugin suite and not run.** A plain request in a repository set up by the real `aidd init`, with and without the person's own `CLAUDE.md`. The trace grader passes only when `aidd risk --paths` ran before the first edit, and the claim `control:risk-before-the-first-edit` is in the registry.
- **A new template for the project's guide.** It asks only for what the code does not show: a command in a code span, a rule with its reason, and "always", "ask first", and "never" lines. `aidd validate` now warns when the guide names a `make` target, a package script, a program, a path, or a link that the repository does not have. It says nothing when it cannot tell, so a tool on the PATH, a glob, a placeholder, a build output git ignores, and aidd's own sections are never named. The onboard flow calls a change to `AGENTS.md` normal, as `aidd risk` routes it.

#### Limits you can see and set

- **A `limits` group in the config.** It holds the retries a Task gets (`max_task_retries`), the size of a quick fix and of the diff that adds the reviewer (`max_fix_lines`, `min_fix_review_lines`), the retrospective cadence (`retrospective_every`), and the paths an answer lists for one area (`max_paths_shown`). `docs/CONFIG.md` lists each default, range, and direction, all generated from `schemas/config.schema.json`, the one owner of every default.
- **A limit that guards a control can only be lowered.** The retry and fix limits have their default as the ceiling, so no project loosens them. A value outside its range fails the config's load at its line, with the range and the next step. A child config that sets a limit its parent also set keeps the lower of the two, and a parent's lock freezes a limit.
- **A role's turn limit is `agents.max_turns`.** Key it by tier or by role, as `agents.models` is. A project may lower it to 10 and raise it to 500, the most aidd ships. Only Claude Code's `maxTurns:` takes it, so `aidd init`, `aidd upgrade`, and `aidd doctor` say when the plugin carries the roles and ignores it.
- **No text states a number the schema owns.** The team's texts render each default from the schema, and the prose that names a limit also names its setting. The test and config defaults (`timeout_seconds`, `reruns`, the review ages) moved to the schema too.
- **The delegate's packet limits are aidd's data, not a project's.** The characters each part may hold and the diffstat's 300 files are in `schemas/risks.json`, with the same values. The size caps of the evidence are read from the evidence schema.
- **Nothing that decides reads a limit from the head under review.** The run, the delegate, and the risk rules read none from the config, and a test keeps it so.

#### Size budgets with room to spare

- **Text that is always loaded may not sit above 90% of its cap.** `tests/test_budget_headroom.py` reads each such byte, token, character, and line budget, so a change leaves the file room for the next honest edit and nobody trims a rule to fit. The files above the line today are in one list in `tests/budgets.py`, each with the real limit it is near. A listed file that comes under the line must leave it, so the list only shrinks.
- **A budget failure says what to do.** It names the file, how far it is past its cap, and what the cap costs. Restructure by topic, or raise the limit with its cost written beside it. Never reword to fit, and remove repetition only where the same reader always loads the other text. `aidd eval packs` says the same for the pack and practice-skill limits.
- **The skill, the loop, and the references say each rule once.** `loop.md`, `risk.md`, `handoff.md`, `profiles.md`, `state.md`, `spec-docs.md`, and the SRE file no longer repeat a hard rule of `SKILL.md` or the table a generator writes beside it. A test holds each row: the words that keep the rule, and the restatement that must not come back.
- **The rules the build taught are in `AGENTS.md` and `CONTRIBUTING.md`.** A trim never loses a rule, a stop, a case, or a fact. A fix names its invariant and runs its revert. A renamed field is swept through every output that prints it. A test never writes a tracked file, and a commit names its paths.

#### Size limits that follow a real cost

- **A coding agent's own sizes are data, each with its page and the date aidd read it.** `src/aidd/config/harness_sizes.py` holds seventeen rows: a skill's name and description, the listing of all descriptions, an MCP server's instructions, an instruction file, a custom agent's prompt, and each vendor's advice marked as guidance. A row says what the page says happens past the number, or "not stated". `tests/test_harness_sizes.py` holds every text aidd writes under each one, and a text one unit past a row fails with the page and the next step.
- **The descriptions a session lists are reported against Claude Code's budget.** Claude Code lists all descriptions within 1% of the model's context window and drops the least-used ones past it. `aidd eval packs` and `aidd doctor` print the total against that budget: the aidd and aidd-team plugins' 7,178 characters against 8,000 at a 200,000-token window, a sum a test now holds under it.
- **Each role has its own start total.** A role's file, the skills it preloads, and `loop.md` where it preloads the aidd skill stay under 56,320 bytes, 14,080 estimated tokens or 7% of a 200,000-token window. It replaces a mean over roles, which hid one heavy role.
- **`SKILL.md`, `loop.md`, and a role file have room.** They are 18 KiB, 12 KiB, and 12,000 bytes, and each cap states its bytes, tokens, and share of the window beside the number. A test holds the stated cost to the number.
- **A file that loads on a signal has one limit for its class.** A reference is 20,000 bytes, a template 24 KiB, a pack 3,000 tokens, a practice skill 2,500, and a skill reference 2,500. Fifty-seven per-file caps are gone. A file near its limit is a note to restructure by topic, and a section past 1,200 tokens is a note too.
- **A step loads every reference and template.** A reference no load-table row reaches, a template no step loads, a link that does not resolve, and a practice skill no role lists now fail.
- **A cap changes only with its cost written beside it.** [CONTRIBUTING.md](CONTRIBUTING.md#size-limits) says who may change each kind of limit and with what, and the make-room message says to restructure by topic and never reword to fit.

#### Languages, test runners, and a folder for each test command
- **A table of languages.** `schemas/languages.json` has one row for each language, with its source extensions and its manifests, and `aidd risk` and `aidd init` read it. Another language is a row and no code. The table adds C, C++, and Scala, so a new feature file in any of them asks for its test first. `aidd init` also counts `.mjs`, `.cjs`, and Elixir files as code. Which files are tests stays in `test_paths` of `schemas/risks.json`.
- **A table of test runners.** `schemas/test-runners.json` has one row for each runner `aidd init` lists, and the exits the runner's own documentation gives for a run in which no test failed. A red run that ends with one proves nothing about new behavior. The exits pytest had in the code, 3, 4, and 5, moved into the table. A test holds the old and the new reading to the same verdicts for every row and every exit from 0 to 130.
- **Three documented exits join the table, read from the runners' own pages on 2026-11-11.** Pytest exit 6 means all tests passed but the warnings went over the maximum. Unittest exit 5 means no tests were run or skipped. Cargo-nextest exit 4 means no tests were selected. Each makes `aidd test` stricter, never looser. Exit 2 of pytest stays a red, because a new feature's missing module fails that way on the base. A runner whose documentation gives no such exit has a row with no exits, so every exit of it stays a failure.
- **A test command can run in a folder.** `runs_in` names it, such as `packages/api`, so each package of a monorepo has its own command. `when_changed` globs and a `report` path stay relative to the repository's top. A folder outside the repository, or one reached through a link, fails the config's load and stops a Spec's command before it runs. A head that moves a base command to another folder runs the base's copy too, in the base's folder.
- **Every language is a column of the route test.** The test that holds a route the same in every language reads the table, so a language added as a row is checked at once.

#### A test run that checks what a narrow run misses
- **`python3 tests/run.py --changed` also runs the checks that read the whole repository.** Their table is `WHOLE_TREE` in `tests/run.py`: unused functions, package doors, schema keywords, the one safe reader, field names, byte budgets, plain language, pinned facts, finding codes, generated docs, and the rest. A change anywhere can break one, and a record of what each test reads cannot say which, so they run every time with the fast content checks.
- **A fresh worktree no longer runs the whole suite.** The record of what each test file reads now lives in the git folder the checkouts of one repository share, so a worktree uses the last full run made anywhere. With no record yet, `--changed` picks the test files whose text names a changed path, says so, and runs the whole-repository checks beside them. A schema change runs the files that read that schema and the whole-repository checks, never everything.
- **`python3 tests/seeded_misses.py` shows each check catches its miss.** It seeds each kind of miss into a scratch copy, shows `--changed` fails, puts the file back, and shows it passes.
- **A run that leaves a tracked file changed fails.** `tests/run.py` compares the tracked files after a run with those before it, so work in progress is never a failure. It lists each changed path with the test files that ran when it was written. With no git, it says it skipped the check.

#### A security review of the control changes
- **A change leaves a file an approved Spec froze as it is, unless the change holds that Spec.** A change with no Spec could rewrite a script a Spec's test command runs, or a frozen design file, and a delegated merge stayed eligible. Now `aidd delegate check` defers it as `tests_changed`, and `aidd test --require-green`, which a branch protection relies on, stops and names the step: hold the Spec and revise it, or leave the file. A Spec freezes its files from approval until it is done, rolled back, or cancelled. A new file, a file no Spec names, and a helper a command only reaches are not covered. A formatting change differs by bytes, so it counts.
- **A Spec approved before `aidd upgrade` still passes a delegated merge after it.** The check read the commit the approval covers, and the default branch's config, as the head is read, so the retired names failed it as `no_spec` while `aidd upgrade` said nothing waited for a person. Now only the head is read as it is. Every other commit (the base, the default branch's tip, the approval's commit) reads in today's shape, including the re-run of the Spec's tests at the approval. A pure migration changes no answer. A config that does not load even so stops the re-run with the step.
- **`aidd upgrade` prints no credential.** It shows each value it removes so a person can find it in git, and a `project.repo` with a password in its URL, or a cut `dev_services` command with one, was printed whole. Now every value a line shows passes `secret_patterns.scrubbed`, which hides what the records' secret check finds (the password in a URL, a token, a private key) and keeps the key and the rest. A line that hid one says the file's own history in git holds the full value.
- **`aidd upgrade --yes` names only the changes it made.** A file the write guard refused, such as a hard link to a file outside the repository, still got `migrated` lines before the line that said it was not changed. Now such a file has only its `manual` lines, and the dry run says `would migrate` for exactly the files the real run writes.

#### Practice skills that agree with each other and with the review rubric
- **One owner for a security finding's severity.** `REVIEW.md` says what each severity means. The code-review skill's security table now ranks data or a secret that reaches an actor who should not have it as Critical. A test stops its table from ranking a class lower than the rubric.
- **The rubric sweeps siblings in every pass, and stops for a split.** After a Critical or High finding, each pass checks the sibling paths. A reviewer asks for a split when the diff mixes concerns or is too large to read line by line. A test holds every section of `templates/REVIEW.md` the same in this repository's `REVIEW.md`, so the template no longer lags behind it.
- **Facts the sources confirm.** The schema-migration skill gives the PostgreSQL steps that avoid a long lock for `NOT NULL` and `CREATE INDEX CONCURRENTLY`. The secure-coding skill says to connect to the address you checked and to turn off redirects. The concurrency skill says the GIL never made a compound update atomic, and that a value read before an `await` may be stale. The data-access skill says an InnoDB `UPDATE` acts on the latest rows, and that a deadlock needs a retry at any isolation level. The caching skill names `Clear-Site-Data`.
- **A throughput count that works in a squash-merge repository.** The estimation skill counts the default branch's first-parent history, which counts a squash commit and a merge commit once each.
- **Each rule has one owner.** The cli-design skill owns the `none` value and the `--no-x` switch, and the technical-writing skill points to it for the command line. The naming skill owns a name, and the data-model-design skill owns the shape. The prototyping skill names the component-library choice and the plugin that holds the prototype tool's README. A test keeps every `tools/` path a skill names real.
- **Pins at each tool's current stable release.** The ci-pipeline skill pins zizmor 1.32.0, the dependency-upgrade skill and the registry pin knip 6.45.1, the ai-evals skill pins garak 0.17.1, and the diagrams skill pins the Mermaid check at 12.2.0.
- **The `context` skill is folded into the lead's rules and retired.** The lead tells each role to read only the part its step needs and to put a project fact in the file that owns it. A role lists on its handoff note a file it needed that the Spec did not name. A lesson joins a team file only when a person confirms it.

#### Practice skills with rules that hold on any project
- **Tests that can fail, and costs counted, not timed.** The test-design skill asks you to see a test of a control, an invariant, or a cost fail once with its fault seeded when it has no red run on the base. It never asserts a duration. It counts the work at two or three sizes and asserts how the count grows. When a suite is slow, it says to measure where the time goes before you change a test, because the cause may be setup, waits, I/O, or the product's own repeated work.
- **One set of checks, local and in the pipeline.** The ci-pipeline skill asks that each pipeline job call the one command a person runs for every check, the secret scan included. It asks for the oldest and newest supported runtime versions, and each platform the release builds on before the release job, run locally in a container where that is possible. A check may run only in the pipeline when it names a reason. A test that fails with no defect behind it is a finding with an owner, never a re-run until green.
- **A review reads the artifact and tries each stated rule.** The code-review skill has the reviewer read the diff, the test's output, the screenshot, or the log rather than a summary of it. It asks, of each rule the change states, what input would make it false. A rule can be a limit, an invariant, a "never", or an "only". A rule with an exception the code makes and the text does not state is a finding. A test the change adds is reviewed as code, with the result of its seeded fault asked of the author where that is cheap.
- **A layout checked on every platform, and a visual test that waits for the settled state.** The prototyping skill asks for a wider font than the designer's own, the smallest and largest widths, and a non-integer pixel ratio or zoom. It waits for fonts, layout, and transitions to settle, and never for a fixed time. A touched screen keeps its one baseline, and a new screen or component gets one for each ratio. Where a state indicator's width is at stake, the state check runs again at each ratio, because two widths that round to the same pixel are the same state to the eye.
- **Comments, docstrings, test names, and messages say what holds.** The maintainable-code skill names what is history and not description. Examples are who or what made a change, the date a number changed, "raised from", "before the … change", and "temporary until". So is a ticket, task, or plan id that readers cannot open or that stands in place of the reason. It asks for one lint rule or test that searches for the project's own id prefixes, and an id in a test's own data is not an error.

#### One row for each type of thing aidd tracks or writes
- **A table of types.** `schemas/item-types.json` has one row for each of the 34 types `aidd new` writes. A row gives the type's group, its form, its id prefix, its folder, its templates, its schema, and where its statuses are. `aidd new` and its `--list`, `aidd status`, `aidd validate`, `aidd explain`, the status-group table, and the skill's list of repository documents read it. Another type is a row, and no code lists types. A test fails when a module keeps a list of three types of its own.
- **No output changes.** `aidd new --list`, `aidd new <type> --help`, `aidd explain`, `aidd status --json`, `aidd validate --json`, and the files `aidd new` writes for every type read the same as before, with the default folders and with `specs_dir`, `proposals_dir`, and `docs.dir` set. The skill's list of repository documents now also names `agents` and `feedback`, which `aidd new` always wrote.
- **A work item and a typed document have names.** A work item is a Spec, an Intent, or a proposal. A typed document is a runbook, a postmortem, an exploration, or a feedback log: a file with a front matter `type` and no status group. The glossary says so, and `OBJECT_TYPES` replaces `ITEM_TYPES`.
- **Copies that cannot read the table are held equal to it.** A test pins the config's writing levels, the types a Spec links, the status and trace schemas, and the glossary's rows to the rows, both ways.

#### A lead that merges safely, flows that agree, and a risk that is a decision
- **The lead's merge discipline is in its rules.** The lead brings a role's work over one commit at a time and runs `aidd test --changed` between the commits. It regenerates a conflict in a generated file and never picks a side by hand. It takes a role's files by the folder the role owns, never by a word in the path. It runs the whole suite once for each batch, reads `git status` after it, and commits named paths only.
- **A risk a role names is a decision.** A handoff note may carry `open_decisions`: each risk or choice the role leaves, with its options and what honest work each blocks. The lead settles each one before it merges that role's work, and takes a choice only you can make to you through its own `needs`. `aidd validate` checks the shape.
- **The lead does not end its turn while a role it started runs.** If the wait outlasts the session, it stops with `waiting` and the time. The rollout flow does the same for an observe window.
- **Autopilot keeps one session.** Each step's roles start with fresh context as subagents, so "start each command in a fresh session" no longer contradicts it.
- **One text for Merge approval.** The loop, autopilot, and the fix flow carry the same three cases: a local trunk, a platform under `team`, and a platform under `solo`. `aidd gen-docs` writes them from `loop.merge_approval` in `schemas/roles.json`.
- **One form of handoff note.** It is one `aidd-handoff` block with keys. The lead's refine table goes in `.aidd/returns/`, and `needs` names the file. A record is never a yes for a new question, and an answer still in force is not asked twice.
- **The fix flow does what it says.** It stops at more than 50 changed lines, as `limits.max_fix_lines` says. The lead may play the developer for a fix of a few lines in one file. "Always start" now binds the roles a flow runs.
- **One moment for `in_review`, and one editor for a Spec.** `in_review` is set when Verify and Review are clean and you are asked for Merge approval. The lead edits a Spec, as `references/state.md` says. The retro flow no longer asks Spec approval for an emergency backfill, which `backfill_due` bounds.
- **Which text wins.** `docs/METHOD.md`, then the skill, then a reference, then a team command. A disagreement goes on the handoff note's `done`. The method's line on the full test run allows the verifier's run.
- **Less to read, and less ceremony.** The skill's load table sends you to `routes.md`, `risk.md`, and `handoff.md` only when the step needs them, and the note's required keys sit in the stop section. A test plan is the verifier's work only when `aidd validate` asks. Run `aidd recall` on the request's key words before Plan and Specify. Without the CLI, judge a path against the areas and say the route is unchecked.
- **Generic text.** The Orca commands and the second reviewer's harness commands moved into the references their flows link. The skill's examples name no database.
- **Four more words `aidd explain` answers:** `method`, `recall`, `stop code`, and `stop rule`.

#### Each status moves by a table in the schemas
- **A table of moves for each work item.** The schema node that holds the status words of a Spec, an Intent, or a proposal also holds three more things. They are the status a new item starts in (`x-initial`), each move (`x-transitions`), and the named sets of statuses that code reads (`x-sets`, such as `past_approval`). A move names the statuses it leaves, the status it reaches, who moves it (`who`: an `agent`, or a `person` whose yes the agent records), what moves it, and the fields it leaves set. A pair of statuses with no row is no move.
- **No module keeps a list of statuses.** `aidd validate`, `aidd status`, the delegate's check, and the work-item readers take each set from the table, and a test fails when a module of `src/aidd` spells two statuses of one table together. The test run's own three sets in `src/aidd/testing/governing.py` are the one named exception, until they read the table too.
- **The approval and revision rules are held pair by pair.** A test lists every pair of statuses of each type. It fails when a move is added or dropped, when an agent alone could lower or stop an approved Spec, or when a Spec set back to `draft` does not record its `revisions` entry (`spec.revise`).
- **The skill and the method show the moves.** The aidd skill's `references/state.md` and METHOD.md section 4.4 generate their move tables from the schemas, for Specs, Intents, and proposals, and `aidd explain <status>` says where each status goes and who moves it.
- **A proposal's group follows its status.** `aidd status` used to call every proposal in the status `qualifying`, `no_go`, `drafting`, `signed_off`, `submitted`, or `rejected` started, and the group table said otherwise. It now gives the group the table gives. A proposal not yet decided is in the backlog, and one a person turned down is cancelled, so neither is open work any more. A proposal that was withdrawn is cancelled, where it was completed.
- **Advice does not change, but for that.** `aidd validate`, `aidd status`, and the delegate's check give the same answers in every status of a Spec, an Intent, and a proposal. That includes a status that is no word. A test holds each status's group and next step.

#### An open decision holds a delegated step until the lead answers it
- **A delegated Spec approval or merge waits for each open decision.** `aidd delegate check` defers with `note_open_decision` while a handoff note it reads holds an `open_decisions` entry that no later note answers. Each entry has an `id`, and a later note answers it with `answered: [{id, choice}]`, where `choice` is one of the entry's own choices, written exactly. Text on `decided` answers nothing. A later `needs` that names the `id` leaves the choice to a person, so the check still defers. The reason names each open `id`, its choices, and the shape to write. The check reads the notes of the Spec, then the pull request's body, then the head commit's message.
- **An entry can only add a defer.** A note is an agent's text, so an entry that does not read stays open, and so does a note that names the field and does not parse. So do an entry with no `id`, two entries with one `id` in a note, an answer with a choice the entry did not offer, and an answer in the entry's own note or an earlier one. `aidd validate` warns about each of them in one file, so a lead learns it when writing the note. A note without the field, or with an empty list, asks nothing, so a change with no open decision is checked as before.
- **A push reads no note.** A delegated push of the change's own branch lands nothing on the default branch, and it is how a role's work reaches CI before the lead answers, so it reads no note, as before.
- **`aidd status` shows each entry and where its answer stands.** A Spec's item and the last commit's `handoff` carry `open_decisions`: each entry as `schemas/handoff.schema.json` gives it, with its `status` (`open`, `needs_person`, or `answered`) and the `choice` taken. The text output prints one line for each, with its id and choices. The work-item page has the data, and shows it once the product designer places it.
- **A broken base config is a person's to repair.** The delegate's check and `aidd test --require-green` stop when the default branch's config does not load. Their messages now say that a person merges the change that repairs it, because the delegation lives in that file and no head vouches for its own config.

#### Nothing opens and never closes
- **One table of what can be open.** `schemas/lifecycles.json` has a row for each thing: a work item with a status, a thing with an end date or a release, and a thing a run opens on the machine. Each row says who opens it, what closes it, who may close it, and what finds one left open. A test holds every item type to a row, or to a reason it is never open. It does the same for every key that carries a date or a release in the config, the handoff note, and the item types' schemas.
- **Two leftovers now have a finder.** `aidd validate` warns about a RAID log entry still `open` after its `due`, and about a handoff note that stopped at `waiting` after the day its `run.resumes_at` names.
- **Who opens, closes.** The loop contract tells every role to look for the one already open before it opens a role, a worktree, a branch, a process, a port, or a PR/MR. It closes what it opened before it hands off. A role that is done says so, and answers a later message that asks nothing new in one line.
- **The handoff note lists what a run opened.** `run.opened` names each thing, whether the run closed it, and for one left open, why and who closes it now. A role writes the block with no run id.
- **The lead runs each role's whole life.** A lead rule says when a role is done, when to resume the same role and when to start a fresh one, and how many roles to run at once. flows.md's "A role's life" gives each role a status file and a line per step, a check every 15 minutes, and the close-out at the end of a change.
- **`aidd status` shows the roles still running.** It reads `.aidd/tmp/roles/<role name>.log` in this checkout and shows each running role's last line and its age.
- **`aidd doctor` notes what a run left on the machine.** It names a worktree or a branch whose every commit git's own patch match puts on the branch checked out or the default branch, and a scratch folder under `.aidd/tmp/` unchanged for 7 days. Each note gives the step that closes it. A name from the repository is data: a command holds it only when it is a plain name, quoted, after `--`.

#### CI that runs each thing once and shows no skipped job
- **One workflow for each trigger.** `ci` runs on a pull request (`checks`, `test`, and the one required summary job `ci passed`), `main` runs on a push to `main`, `weekly` runs on the Saturday schedule and by hand, and `standards` runs on Mondays and by hand. A job exists only in the workflow whose trigger runs it, so a pull request lists no skipped job. The header of `.github/workflows/ci.yml` holds the table of event by workflow by job, and `tests/test_ci_workflows.py` holds it equal to the files.
- **Each check runs once.** The browser tests run in `aidd-tests` on a pull request, not again in `ci`. A push to `main` runs only what a pull request did not, the suite and the browser tests on Python 3.15, because the ruleset requires an up-to-date branch. The test lists each (event, check) cell that changed, with its reason, and holds that every check still runs on an event before a release.
- **The weekly run keeps what only the date changes.** It runs the Linux matrix (now 3.14 and 3.15 too), the sdist, the wheel, and the OSV-Scanner and zizmor scans on a tree no one changed.
- **The required checks keep their names.** The branch ruleset still requires `ci passed` and `tests`. `ci passed` now passes only when every job it waits on succeeded, so a skipped job no longer counts.
- **The release finds the new runs.** It reads the push run of `main.yml`, the manual run of `weekly.yml` for the full matrix, and the pull request head's runs of `ci.yml` and `aidd-tests.yml`. A manual full-matrix run is now `gh workflow run weekly.yml --ref main`.
- **Setup is written once.** The local action `.github/actions/setup` sets up Python, and Chrome's sandbox and axe-core for the browser tests. `aidd-tests.yml` and the adopter templates keep their own steps.
- **Three checks run only when a path they read changed.** The Mermaid check and the plugin validation join actionlint and zizmor, each with its list of paths beside it. A test holds each list to what its check reads. The suite always runs.
- **No merge queue yet.** The `merge-queue` job and the `merge_group` triggers are gone from `ci`. RELEASING.md says how to add one.

#### A quick check that runs only the tests a change can break
- **A test command can name its related-tests form.** `related_tests` holds the command that runs only the tests the runner relates to the change, such as `vitest related` or Jest's `--findRelatedTests`, with `{changed_paths}` or `{base_commit}`, and `sees`, the files the runner traces. `aidd test --changed` runs it, so a small change between steps no longer pays for the whole suite. A form with neither placeholder, or a typo in braces, fails the config's load.
- **A change the runner cannot see runs the full command.** So does a changed path the command covers that `sees` does not match, such as a lock file, the config, or a fixture. A deleted file, a link, a path outside the command's folder, and one that reads as an option do too. A note says why.
- **A narrowed result never stands for the full command.** It reads "only its related tests" and carries `related_tests` in the evidence, which stays `partial`. A full `aidd test`, `--require-green`, CI, the verifier's run, and the delegate's check always run the full command, and red runs never narrow. Evidence that says it is a full run and holds a narrowed result exits 1. A Spec's command has no `related_tests`, and a head that adds or changes the form still runs the base's command in full as `base.<name>`.
- **The runner table says which runners have a related-tests mode.** Each row of `schemas/test-runners.json` gives what the runner's documentation says, read on 2026-11-11: Jest and Vitest have one, and `aidd test --changed` suggests it for a command that names them. Playwright's `--only-changed` compares the last commit, so it would miss a change not yet committed, and aidd suggests none. Pytest, unittest, Mocha, RSpec, and PHPUnit have none built in. Go, Cargo, and nextest select by package, and .NET's mode is experimental.
- **This repository's own `python3 tests/run.py --changed` starts from a lower floor.** Six test files no longer count as reading anything. Four keep the read record in the Python they start, a shell's syntax check (`sh -n`) records the file it checks, and `jq` on standard input reads nothing of the checkout. Measured on one record, the floor fell from 61 to 55 files and from 366 to 260 file-seconds, and its slowest file from 55 s to 17 s. A run of up to 64 files no longer waits for another checkout's full run.

#### A design check sized to the change
- **The fidelity pass is sized to the change.** The prototyping skill's design review holds the one rule. A new or reshaped screen or flow takes the full matrix of those screens. A change to a component's look or states takes each screen it appears on first, as a person sees it. Then it takes the component's states once on each variant in both themes, then the narrowest frame and 200% text. Any other UI change takes its author's quick pass. Axe, the comfort checks, real copy, both themes, and a screenshot read never scale down. Where a layout cannot hold at 200% text or 320 px, the designer proposes the fallback, and a person picks it.
- **One trigger for who runs it.** The designer's start condition, the developer's done line, the review flow, and the glossary name the same change, and AGENTS.md points to the rule. A test holds them to it.
- **`aidd prototype --shots` lists the views.** It prints each view the pass takes, with its deep link and screenshot name, as JSON in `schemas/design-manifest.schema.json`. `--changed-screen <id>` and `--changed-component <name>` size it, and `--frames` names the frames a product ships. It never lists none: a screen, a component, or a frame the design lacks is a problem. The screenshot loop takes its views, so nobody edits a loop to size a pass.
- **A quick pick where taste decides.** When the open question is how something should look and two or three answers are sound, the designer settles it before any pass. It shows the options side by side in one screenshot and asks one question with its recommendation. Without the person, it writes a decision card with `taste_pick: true`, whose options may differ only in color, size, or spacing, and `aidd explore` shows them on one page that says you pick by eye. A rule, such as text at 200%, is never a pick.
- **A state indicator is drawn from the object it decorates.** The accessible-ui skill's `references/criteria.md` says to read the object's edge, shape, and colors first. The indicator keeps 3:1 against that edge and the background, follows the object's shape, and repeats none of its lines. A control's interaction states are states: no two look alike, and they differ by more than color.
- **A state check that can fail.** The same reference gives `look` and `stateProblems`, which a project's prototype test calls in the screenshot loop. They fail on two states that look the same, two that differ only by color, and an indicator in its edge's color, and the reference lists what they cannot see. aidd's own Board test runs the check as the reference writes it.
- **Where WCAG is heading, as habits and never a claim.** The accessible-ui skill's `references/statement.md` reads the WCAG 3.0 Working Draft of 10 September 2026 as direction only. WCAG 2.2 AA stays the floor and the only conformance aidd names. The draft's new areas, such as clear language, adequate time, and avoiding deception, map to habits that already hold, each marked emerging and pointing to the skill or pack that holds it. The registry has the draft as an emerging row, and no test, lint, or done line cites it.
- **The exploration page says "Based on" for what a spike rests on.** It said Evidence, which the glossary keeps for a runner's exit code on a commit, and the field is `basis`.

#### Every skill a model must find can be found
- **The domain packs are the optional `aidd-packs` plugin.** A pack is `aidd-packs:<pack>`, and the aidd-team plugin keeps the router and the practice skills. At a 200,000-token window Claude Code lists 8,000 characters of descriptions, and the aidd-team plugin alone put 11,147 there, so about a third of its skills lost their description. No setting keeps a skill both loadable by a model and out of the listing: `disable-model-invocation` also stops the model's own load and a role's preload, and `skillOverrides` skips plugin skills. A pack leaves the plugin for that reason. The aidd and aidd-team plugins now list 7,178 characters.
- **A role loads a pack by name, and aidd names it.** `aidd risk --paths` says which domain pack to load for the areas it matched, with the name the install gives it, or how to add the plugin when it is missing. `aidd doctor` warns when the repository calls for a pack the plugin does not carry. `aidd init --claude-plugins --aidd-team` enables the plugin in the project when the repository calls for a pack, and `aidd doctor` warns when a pack is in both the plugin and `.claude/skills/`.
- **Each description says how its skill is found.** `aidd eval packs --json` gives each one a `plugin`, a `listed` flag, and a `found` value: `description` for a skill a model finds alone, `name` for a pack and for a practice skill that a role preloads or `file_practices` names, and `person` for a command. They are derived from the registry and the front matter, never listed by hand. A command sets `disable-model-invocation: true`, so the 2,022 characters of command descriptions the report counted are no longer in its total.
- **A test holds the listed sum under the budget.** The number comes from `src/aidd/config/harness_sizes.py`, with the five facts about the listing that it rests on, each with its page and date. A description one character past it fails with the next step.
- **A project install is unchanged.** `aidd init --aidd-team` writes the same files: the practice skills and only the packs the repository calls for. A project with three packs lists 7,088 characters.

#### No routine step stops at an ask
- **A role's worktree starts from your current commit.** Claude Code branches a subagent's worktree from the remote's default branch unless the project sets `worktree.baseRef` to `head`, as its worktrees page says (read 2026-11-12). Where the team's roles run in Claude Code, `aidd init --aidd-team` and `aidd upgrade` now write that setting into `.claude/settings.json`, and a dry run shows it. So no lead resets a role's worktree, an `ask`, at each start.
- **Your own value stays.** A `worktree.baseRef` the file already holds, `fresh` or any other, is yours, and the plan says aidd keeps it. A settings file that does not parse, a link, or a `worktree` that is no object is left as it is, with the line to add by hand. `.aidd/harness-rules.json` lists what aidd wrote, so `aidd uninstall` takes it out only while it holds `head`.
- **It grants nothing.** A test runs `aidd init` and `aidd upgrade --yes` with the writer and without it, over both profiles, the team's options, and a person's own files. Every file is byte-identical, the `permissions` block too, but for the new key and its ledger entry.
- **`aidd doctor` notes a missing setting.** Where the team's roles run in Claude Code and no settings file sets `worktree.baseRef`, doctor says why it matters and gives the line to add. It is silent once any settings file sets it, where no team is installed, and for every other harness.
- **The team's texts say when a command asks.** The test that reads each command the skill, the roles, and the flows tell an agent to run now checks one more thing. A step that names an `ask` command must say in the same step that it asks, or that it is never to run. The delegation reference's local merge now says it.
- **The lead checks a brief before it sends it.** It checks the level of each command a Task tells a role to run, so no Task gives an `ask` action as a routine step. When the work needs one, it asks you once, before the roles start, and says how many roles your yes covers. A developer's first command in a parallel Task is a read-only check, and when it fails, the developer stops and never resets.
- **Asks are counted.** `aidd status <ID>` says how many times a person was asked on the item, from its decision records, and the lead's close-out says it.

#### Checks sized to the change, and the controls that never scale down
- **One rule sizes every role's checks.** The loop contract's "Spend in proportion to risk" rule keeps a required check on and sizes its breadth to the change. The cheapest check that could stop the work runs first. Nothing proven on the head is proven again, and a step that needs no judgment runs as a command. Red before green, your yes, a reviewer who is not the author, and evidence bound to the head never scale down, and a reviewer reports a check the change left out.
- **Tests once per batch.** The lead runs `aidd test --changed` once after a role's last commit or the last Task's merge, and in between only when a commit or a merge conflicted. On the quick path, the builder runs `--changed` or one test file between attempts. Each flow that ends in a merge ask keeps one full `aidd test` on the final head, with each new test red on base.
- **The quick path takes any small minor change.** `/aidd-team:fix` takes a docs edit, a style fix, or a feature within the same 50-line and 20-line limits, not only a bug fix. Each change type names its proof. A fix, a feature, or a perf change gets a test red on base, and a docs or style change gets the check that reads it.
- **Reworks sized by what changed.** A merge of the base after your yes still gets a new Verify and a new ask, and the ask says only the base moved. A reworked head re-exercises the Acceptance lines the rework can affect and names the ones it left. A second security engineer challenges the findings only when one is Medium or above or needs validation, or the change is major or in an `ask` area, and no finding is ever dropped.
- **A review a role needs is an `open_decisions` entry.** A role lists there a review it did not run and its change may need. One option starts it, and one says why none is needed, which the lead takes only where no rule requires the review. A line in `done` alone is not a request. The lead settles each entry, and each role's `needs` other than `none`, before it merges that work.
- **A fix for a finding is read once.** The loop contract says a fix is new work on a new head, read by one reviewer who did not write it, over the fix's diff. On a control, the review flow adds one read by a security engineer who did not write the fix, over its commits and the finding each answers. It holds whether or not the challenge of the findings ran.
- **Every role with tools shows it is working.** The loop contract tells each one, a reviewer too, to append a status line to the file the lead names, and to end with `DONE`. The file is under `.aidd/tmp/roles/` or in the harness's scratchpad. The lead names one for every role with tools that it starts, and never for the delegate.
- **The lead's own commit gets the check a role's gets.** It runs `aidd test --changed` before the commit lands.
- **The lead has a reader before it stops.** Before a report of merged work from more than one role, or a Merge approval ask, one fresh read-only session on the execution tier reads the lead's message against the handoff notes and the plan. It lists what the files do not support and each `needs` or request with no answer, and it is never an approval.
- **A started role has a name a person can read.** The lead names each role it starts `<role>-<what it works on>`, such as `developer-login-form`, with no code or number to learn, and never writes that name into a file of the project. The role's worktree gets the same name where the harness lets the lead choose, and so does a branch of the role's own, and the status file's first line names them where it does not.
- **A done role is stopped.** When a role's work is merged or declined, the lead stops it, so the person sees only what is working.
- **CI's checks run before the Merge approval ask.** The lead runs every check the project's CI runs on the target branch, or names in its message each one it did not run and why.
- **The lead's reader also reads what the lead wrote down.** A decision, a raised limit, or a defect of the lead's own that is in a record and not in the message is a finding.
- **A new check is proven.** A new check, test helper, or script that can pass or fail is shown failing once on a planted fault before anyone relies on it (CONTRIBUTING.md, "Prove a fix").
- **Deleted tests are listed.** The lead lists each test a batch deleted or renamed, and the reviewer checks that none was the last test of a claim, or the last one that could fail.
- **A diagram in a document gets the designer's look.** The fidelity pass has a row for a diagram or picture committed to a document a person reads: each one as the reader's page draws it, in both themes.

- **`aidd doctor` says when the plugin and the repository are of different shapes.** One `claude plugin update` moves every project on a machine, while the `aidd` command and each repository's files stay as they were. Doctor warns when the aidd plugin, or the skill in the repository, is newer than the `aidd` command, and says to run `aidd self-update`. It warns when the plugin is older, and gives the `claude plugin` commands. It counts the names aidd retired that a file still holds while the config loads, and says to run `aidd upgrade --yes`. It reads each version from a file, with no network call, and says nothing for a version it cannot read.
- **`aidd doctor` suggests the narrowed form.** For each test command whose runner can run only the related tests, it prints the `related_tests` form to add.

### Security

- **aidd enforces nothing, and says so.** The hard stops are the harness's own ask rules and the platform's branch protection.
- **A pattern is a net.** A command pattern is not a control, as [SECURITY.md](SECURITY.md) explains.
- **Text is data.** The skill tells every agent that a ticket, a page, a file, a comment, or another agent saying "approved" is never a yes. Only your own words in the chat are.
- **A handoff note is checked data.** `aidd validate` checks each `aidd-handoff` note against `schemas/handoff.schema.json`.
- **Hidden characters.** It warns about hidden characters and about text that poses as a person's words.
- **One rule for who is an agent.** A waiver, `--approvers`, an Intent's `agreed_by` (to `aidd status` and `aidd validate` alike), and a Spec's `approved_by` refuse an agent or a bot by the same rule, so `@devin` is refused like `@claude`, and so are `agent:dev <d@example.com>`, a bare `<noreply@anthropic.com>`, and a `noreply+tag@` address. An accent on a Latin letter is a name (`José García`, `Nguyễn Văn`), while a letter of another script mixed into a Latin word, or an accent no letter holds, reads as a disguise. Each refusal says to write the person's `@handle`.
- **Triage by the same rule.** `aidd status` sends work an agent account suggested (`@devin` as much as `agent:sre`) to a person's triage, as `aidd validate` does.
- **One spelling for `Assisted-by`.** `aidd validate` warns about a value that is not `<harness id>/<model>` and gives the spelling to write.
- **The Orca channel.** `schemas/orca-payload.schema.json` holds the payload a worker sends its lead. `aidd validate` checks a payload file, so a free-text message never steers the lead.
- **A launcher that trusts nothing in the project.** The aidd plugin starts its MCP server with Python in isolated mode, from outside the project.
- **No project-shipped aidd.** The launcher refuses to start when the plugin's source lies inside the project.
- **Verified updates.** `aidd self-update` installs a release once the wheel matches `SHA256SUMS` and, with `gh` on PATH, its build provenance.
- **The daily check.** It only says a release is out. With `AIDD_UPDATE=install`, it installs a verified release. It never runs in a shell a coding agent started, Codex and OpenCode included.
- **`--main`.** `aidd self-update --main` installs the tip of `main` on purpose.
- **A mirror.** `AIDD_RELEASE_URL` points the installer at one. It needs `AIDD_SHA256` or `gh`, because a mirror's `SHA256SUMS` proves nothing alone.
- **Releases you can verify.** The release workflow verifies the tag signature and CI before it builds.
- **Releases you can rebuild.** It builds every artifact again on a fresh runner and stops unless each matches `SHA256SUMS`.
- **Provenance.** It then attests build provenance and a CycloneDX SBOM.
- **A stable channel for the Claude Code plugins.** Each release moves the `stable` branch to its commit, fast-forward only, so a plugin update arrives only with a release.
- **Pinned CI.** Every workflow pins each third-party action by commit SHA.
- **Scans of aidd.** CodeQL, zizmor, actionlint, and OpenSSF Scorecard check the repository.
- **No Claude Code telemetry in CI.** Each step that runs the Claude Code CLI turns off nonessential traffic.
- **Scanning for adopters.** The CI templates add OSV-Scanner, Semgrep Community Edition, gitleaks, and an SBOM, each on a read-only token.
- **No telemetry.** SECURITY.md lists every place aidd connects, and a test fails on a network module missing from that list.
- **Offline.** `AIDD_OFFLINE=1` stops the optional network calls.
- **Pushed records are permanent.** A record holds your exact words and is unsigned, and union merge never removes one.
- **Pushing records asks.** `records.push` is an `ask`, and the push first checks every file it would send.
- **`--lan` serves plain HTTP.** `aidd prototype --serve --lan` puts a random token in every path, which stops a guess and not a network sniffer.
- **Listening reports.** `network.listen` is a `report` action, so an agent says when it starts a listener.
- **No read or write through a link.** aidd reads a repository's file only as a regular file inside it. It writes only a regular file with one name. So it refuses a link at the file or on the way, a pipe, a device, and, for a write, a hard link. A command names what it refuses and goes on with the other files, but `aidd test` stops before it runs anything, because it checks those files for a change. The same holds in the git folder, for the records, the index, and the delegation's stop file. Your own settings in your home folder are yours, so aidd reads them through a dotfiles link.
- **A new file is never more open than its folder.** A file aidd creates in a repository gets the folder's group and read access, under your umask, and never write for others. Its own evidence and records are yours alone.
- **Only an installed aidd writes the user launcher.** `aidd init` from a source checkout leaves `~/.aidd/bin/aidd` as it is and prints a `kept` line, so a branch's code never becomes the aidd of every repository on the machine. `aidd doctor` warns when the launcher starts a path that is no install or is gone.
- **Every file outside the repository, listed.** SECURITY.md names each file aidd writes outside the repository: the MCP launcher, its cache folder, the temporary folders it removes, and the installer's own venv.
- **A secret check that reads hidden characters.** It normalizes each string first, so a zero-width or fullwidth character can't hide a token.
- **No secret in a failed request's message.** When a fetch fails, aidd shows the URL without its user, password, query, and fragment.
- **A run decides a Spec's whole status from the base.** For a Spec the base holds approved or later, a declined `triage` the head adds can no longer read as `cancelled` in the run's view, and the run notes a changed `triage`.
- **`--require-green` needs the full run.** `aidd test --require-green` with `--changed`, `--watch`, or `--no-red` is a usage error (exit 2) that says which flag to drop, and it runs nothing, so a partial run never turns a gating check green.
- **A handoff note that does not read stops the delegate check.** A note after the latest one that names a head, which does not parse or names no head, makes the check defer with `note_unreadable`, so an older `needs: none` is never taken as the latest.
- **One answer clears one open decision.** An `answered` item clears the newest open entry before its note with that `id` and choice, so two entries that share an `id` need two answers. `aidd validate` warns when `open_decisions` entries in several notes of one file share an `id`.
- **The evidence names a revision that let frozen files change.** `revised_frozen` lists each Spec whose frozen files a change rewrote behind a `revisions` entry the head wrote. `aidd status`, the item page, and the last line of `aidd test` show it, so the person who merges reads it.
- **The evidence says when an emergency Spec cut the suite.** `emergency_subset` is true when the repository's `tests` ran as their `smoke` set alone because a Spec's route is emergency, and `aidd status`, the item page, and `aidd test` show it.

- **A config's text prints as one safe line.** `aidd risk --paths` shows the hosting, each project rule's statement and why, a waiver's reason and granter, and a specialist's name on one line. No escape, bell, carriage return, or direction character reaches your terminal, and `--json` keeps each value as written.
- **A suggested command never holds text a shell would expand.** A path from the repository or the config joins a printed command only when it is a plain name, quoted, after `--`, as `aidd doctor` already did for a branch. That holds for `aidd init --dry-run`, `aidd status`, the next step of `aidd new`, the step that untracks a committed evidence folder, and the command for a misplaced exploration. Any other name is described in words, and no command holds it. A title you typed is quoted whole. The test and lint commands `aidd init --dry-run` detects are printed as a shell reads them, so a folder name in one cannot run when pasted. A test reads the source and finds each printed command that holds a value no rule proves safe. So the rule holds for the rest too. That covers the commands that name a standard, an exploration, a prototype file, a Spec id, a path in a next step, a make target a doc names, and the repository's own folder.
- **A role's status line hides its secrets.** `aidd status`, `aidd status --json`, and the MCP `status` tool show the last line of a role's status file after the secret scrub. A token or a password in a pasted push URL never reaches your terminal or the lead's context.
- **A loader's message hides a credential in the value it quotes.** When `aidd upgrade --yes` leaves a retired key for a person, `aidd validate` and `aidd doctor` say why, and that sentence may quote the file's value. It now passes the secret scrub and stays on one line. An id read back from a committed evidence file counts only when it has the shape of an id.
- **The secret scrub takes time in proportion to its text.** A long run of repeated keys, such as `password=password=...` in a retired value, no longer costs its length squared, and the scrub hides the same text as before.

### Known limits

- aidd advises and enforces nothing. An agent that ignores the skill acts on its own, and only the harness's ask rules and the platform's branch protection stop it.
- Only the <!-- aidd:gen count:harnesses -->14<!-- aidd:end --> coding agents aidd supports are detected, and only six get ask rules. Any other agent reads the skill through `AGENTS.md` and `.agents/skills/aidd/`, and there the skill alone carries each ask.
- A command pattern matches the command text. A script, an alias, or an API call can reach the same effect without a match.
- A secret can leak through a script, a shell glob such as `cat .env*`, or `env` and `printenv`, which stay allowed.
- No harness prompt holds `intent.agree` for sure, and only the `Agreed-by` trailer counts.
- No harness has a `git merge` rule, so a cherry-pick, a rebase, or a ref move is left to the agent and the skill.
- Claude Code and Grok Build have no rule for `git push <remote> :<ref>`.
- Codex, Qwen Code, and VS Code's agent have no file-edit rule for frozen tests, and an edit to a Spec's status drops the ask.
- A shell write such as `sed -i` is no edit tool, so a frozen test's ask rule may miss it. `aidd validate` and `aidd test` do not compare a test with its approved form: a person's review catches the change, and so does a delegated merge's check.
- Codex, Grok Build, and Qwen Code with folder trust on read the ask rules only once you trust the folder.
- OpenCode applies the last rule that matches and reads more than `opencode.json`, so an allow in another file can outrank aidd's ask. `aidd doctor` reads only `opencode.json`.
- A Spec approval is a note the agent wrote, not proof. Under `team`, the platform's review is the Merge approval.
- A malicious change to tests, build scripts, or dependencies can make its own tests lie. Your review of the change is the control.
- A delegate runs on the same machine as the agents it checks, so aidd cannot authenticate it. An agent with a shell can forge a record or put its own `gh` first on the PATH.
- The delegation check stops honest mistakes, not a local agent set on forging.
- The delegation check cannot see a test that passes without checking the Acceptance. With no remote, a weak or empty suite passes, and no platform holds the default branch.
- Claude Code's delegation hook only answers a prompt the ask rules raise. If it fails or never loads (`--bare`, `disableAllHooks`), the prompt stays.
- A Claude Code mod that approves the call, a merge through another MCP server's tool, or an action no ask rule names passes the hook with no prompt.
- On Claude Code the spend cap can't stop an autopilot run. `/cost` shows the session's spend.
- The git reading has residual risks, listed in [the git layer's threat model](docs/security/threat-models/kernel-git.md), and no named person has accepted them.
- The risk rules have a [threat model](docs/security/threat-models/risk-rules.md): a preset that lowers Spec approval through a `route`, and how the delegate gate reads a test file. Its residual risks have no named person who accepted them either.
- A filter or hook in your global git config still runs, and a git older than 2.40 cannot ignore the tree's attributes.
- A remote call runs the repository's own ssh command, credential helper, and proxy.
- An exotic spelling of a merge command, such as an alias set on the line, can slip past the reading.
- aidd publishes no eval baselines, and the role evals have not run with real models against this release's agent files.
- Before the first release: `install.sh` and `aidd self-update` build the tip of `main`, unverified, and say so. The Claude Code plugins' marketplace follows `main`, as `aidd doctor` says. Signing, attesting, and publishing a release wait for a public repository.
- [SECURITY.md](SECURITY.md) lists the rest.

[1.0.0]: https://github.com/thaithienvanid/aidd/releases/tag/v1.0.0
