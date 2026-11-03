# CLI reference

Commands that work on a repository run from its root, wherever you start them. `--base` defaults to the remote default branch. aidd tries `origin/HEAD` first, then `origin/main`, `origin/master`, `main`, and `master`. `aidd <command> --help` prints the same flags with a sentence each.

## Which command when

Four commands cover a normal day, and they come first. Your agent runs them as it works, and you can too. `aidd --help` lists only those, `aidd help --all` lists every command by group, and `aidd help <command>` shows one command's arguments and flags.

<!-- aidd:gen cli:when -->
| Use | Command | When |
| --- | --- | --- |
| Every day | `aidd status` | to see the open work, and what waits on whom; `--mine` for what waits on you |
|  | `aidd risk --paths` | before the first edit: the route the planned paths need, its lane, and the level of the edit |
|  | `aidd new spec` | when the route needs a Spec: start the Spec from its template |
|  | `aidd test` | once on the final head: the tests, red on the base and green on the head; between steps, `--no-red`, `--changed`, or one test file |
| Now and then | `aidd init` | once in each repository: write the config, the skill, the ask rules, and the CI workflow |
|  | `aidd upgrade` | after you install a new aidd: bring the repository's aidd files up to it |
|  | `aidd self-update` | to update the CLI now; it also checks once a day by itself, after a command you run at a terminal |
|  | `aidd uninstall` | to remove aidd from a repository |
|  | `aidd doctor` | after `init` or `upgrade`, or when something looks wrong: check the wiring |
|  | `aidd standard` | to see the choices the packs leave open, or to adopt one of aidd's opinionated standards (`add`), or a stack of them (`add --stack python-cli`) |
|  | `aidd validate` | to check the whole repository, or the files you name |
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
| `init` `[path]` | adopt aidd in a repository | `--dry-run`, `--profile solo\|team`, `--ci github\|gitlab\|none` (default `github`), `--ref SHA_OR_TAG`, `--approvers WHO ...`, `--specialist POOL=WHO` (repeatable), `--test COMMAND`, `--team`, `--harness AGENT` (repeatable), `--claude-plugins`, `--devcontainer`, `--compliance-target soc2\|iso27001\|gdpr\|hipaa\|pci-dss\|fedramp\|cra\|other` (repeatable), `--security-ci`, `--link DIR` (repeatable), `--no-skill`, `--force` |
| `upgrade` `[path]` | bring a repository's aidd files up to this aidd: the skill, the team files, each agent's ask rules, the CI pins, and aidd_version, and remove what an older aidd wrote for its guard, hooks, and gate; a dry run unless --yes | `--ref SHA_OR_TAG`, `--yes` |
| `self-update` | update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line installer), from the release's wheel once it matches the release's SHA256SUMS; AIDD_NO_UPDATE_CHECK=1 turns the daily check off | `--check`, `--main` |
| `uninstall` `[path]` | reverse `aidd init`: list what it would remove, or remove it with --yes | `--yes`, `--link DIR` (repeatable) |
| `doctor` `[path]` | check that a repository is wired correctly | `--json` |
| `standard` `[list\|add]` `[ID ...]` | the choices the domain packs and practice skills leave open, each with aidd's default, and aidd's library of opinionated standards that fill them, and its stacks; `add` copies standards or a stack into docs/standards/ with their `standards` entries and their `tests` | `--stack NAME`, `--stacks`, `--json` |
| `status` `[id]` | the open work: each Spec, Epic, Initiative, and proposal with its status and its next step, and who takes it | `--mine`, `--json` |
| `risk` | advice before an action: the route for planned paths (--paths), the level of a shell command (--command) or an action (--action), or every risk rule in force (--list); a level is allow, report, or ask | `--paths PATH ...`, `--command LINE`, `--action ID`, `--list`, `--change-type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--irreversible`, `--area AREA`, `--branch own\|default\|shared`, `--role ROLE`, `--json` |
| `new` `spec\|epic\|initiative\|proposal\|runbook\|postmortem\|tech-spec\|test-plan\|adr\|threat-model\|authz\|design-spec\|api\|slo\|compliance\|analytics\|migration\|acceptance\|feedback\|design-system\|architecture\|data-map\|vendors\|glossary\|vulnerability-policy\|agents\|contract\|exploration\|product-prototype` `[id]` | create a Spec, Epic, Initiative, Proposal, runbook, postmortem, or feedback log from the template; or a document a Spec links, written from its template and added to the Spec's `docs`; or the repository's one design-system, product-prototype, architecture overview, data-map, vendors register, glossary, or vulnerability-policy; or a proposal's contract; or an exploration | `--title TITLE`, `--route normal\|major\|emergency`, `--change-type feat\|fix\|refactor\|perf\|docs\|test\|build\|ci\|chore\|deps\|infra\|data\|security\|compliance` (default `feat`), `--paths PATH ...`, `--dimension data\|security\|privacy\|financial\|compliance\|availability\|third_party\|cost\|performance` (repeatable), `--irreversible`, `--force`, `--full`, `--owner-team OWNER_TEAM`, `--parent PARENT`, `--audience client\|internal` (default `client`), `--addressee ADDRESSEE`, `--spec SPEC`, `--area AREA`, `--no-link`, `--prototype`, `--owner OWNER`, `--timebox TIMEBOX` (default `45 minutes`) |
| `test` | run the tests (green on head, red on base) and write evidence | `--base BASE`, `--spec SPEC`, `--out OUT` (default `.aidd/evidence`), `--no-red`, `--red-in-place`, `--pass-env NAME` (repeatable), `--changed`, `--watch` |
| `validate` `[PATH ...]` | validate the repository, or the files given | `--json` |
| `explore` `folder` | render an exploration's one comparison page: two or three divergent directions side by side, the trade-offs under each, and each round's screenshots; the owning role writes the pick and its reason in the Spec, DESIGN.md, or an ADR | `--out PATH` |
| `prototype` `[file]` | assemble the whole-product prototype from docs/design/app/ (sitemap.json, shell.html, and flows/) into aidd's prototype viewer, .aidd/views/prototype.html, and check it: every link and navigation item opens a screen, no flow draws its own navigation, and every flow is reachable | `--check`, `--example`, `--open`, `--components`, `--screens`, `--new-design FILE`, `--title TITLE` (default `A direction`), `--stories INDEX` |
| `help` `[COMMAND ...]` | the everyday commands, the same as `aidd --help`; with --all, every command by group; with a command, its arguments and flags | `--all` |
| `eval` `routing\|roles\|standards\|packs\|tasks\|report` `[PATH ...]` | run an agent routing eval, the role evals, the standards check, the pack and practice template check, or your own agent tasks; report recorded runs | `--root ROOT`, `--scenarios SCENARIOS`, `--agent-command AGENT_COMMAND`, `--no-embed`, `--min-accuracy MIN_ACCURACY` (default `0.9`), `--repeat K` (default `1`), `--without-aidd`, `--record PATH`, `--model-label TEXT`, `--online`, `--strict`, `--due DAYS`, `--unreviewed`, `--json`, `--timeout SECONDS` (default `15.0`), `--max-seconds SECONDS` (default `600.0`), `--max-bytes N` (default `3000000`), `--concurrency 1\|2` (default `2`) |
| `mcp` | serve aidd to agents as MCP tools over stdio: the risk level of an action, the open work, and validation | none |
| `gen-docs` | maintainers: regenerate the schema tables in the docs and the skill, and the domain-pack skills | `--check` |
<!-- aidd:end -->

What the table cannot say:

- **`init`** writes the config, the skill, `AGENTS.md`, the CI workflow, the PR template, and each detected coding agent's ask rules ([every coding agent](GUIDE.md#every-coding-agent)). It never replaces a file that exists without `--force`. `--dry-run` prints what it finds, and the config it proposes, and writes nothing.
- **`upgrade`** also removes what an older aidd wrote for its guard, its hooks, and its gate. That covers the hook entries in each agent's settings, the OpenCode plugin, and the gate's workflows. It keeps every entry a person wrote.
- **`risk --paths`** gives a change's route before the first edit, and the level of editing those paths. **`risk --command`** gives the level of a shell command line, reading the branch a `git push` reaches from git. **`risk --list`** shows every rule in force and where it comes from, whether the built-in rules, the profile, or the config. Each answer is advice. aidd enforces nothing, and a command pattern is a net, not a control.
- **`status`** shows every open work item with its stored status and its next step, and whether the agent or a person takes it. `--mine` keeps only what waits on a person. With an id, it shows that item even when it is finished.
- **`validate`** with no paths checks the whole repository, including overdue emergency reviews. It warns, without failing, when a Spec has leftover TODO placeholders, or when a normal or major Spec has no Intent.
- **`test`** runs the repository suite and the Spec's commands on the head, and each new-behavior command on the base too, where it must fail. `--changed` runs only what the working tree's changes select, green only, and marks the evidence partial. It is a quick check between steps.
- **`explore FOLDER`** renders an exploration's comparison page into `.aidd/views/explore-<folder>.html`. The page records nothing and approves nothing: the owning role writes the pick and its reason.
- **`gen-docs`** regenerates every `aidd:gen` block in the Markdown files, the skill's references, and the domain-pack skills. With `--check` it changes nothing and fails when any is stale, or when a generated table would have no rows.

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
| `AIDD_OFFLINE` | every command that loads the config, `aidd self-update`, `aidd eval standards --online` | `1` stops every optional network call: `extends` parents by URL are skipped with a warning, and no update check runs |
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

One more belongs to [`install.sh`](GUIDE.md#install) alone. `AIDD_REF`, in the table above, takes a `vX.Y.Z` tag or a commit SHA. A tag installs that version's wheel from its GitHub Release, once the wheel matches the release's `SHA256SUMS`. `AIDD_SHA256`, when set, must match too. `AIDD_RELEASE_URL` points the installer at a mirror of the releases, which needs `AIDD_SHA256` or `gh` too. A commit SHA builds from source, for testing unreleased code only.
