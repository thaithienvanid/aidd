# Contributing

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

This repository uses aidd on itself. Every change is a pull request that follows the loop in [METHOD.md](docs/METHOD.md): `aidd risk --paths` gives its route, a normal or major change brings a Spec, and a maintainer reviews and merges it.

## Develop

```sh
uv venv && . .venv/bin/activate && uv pip install -e .   # or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
aidd gen-docs                          # regenerate every generated block and domain pack after changing a schema
aidd validate                          # the repository's aidd files: the config, the risk rules, and the work items
aidd eval standards                    # the team's standards registry: nothing past its review cadence
aidd eval packs                        # every pack and practice skill in its template and under its size cap
```

Without activating the venv, prefix each command with `uv run`, as in `uv run aidd gen-docs`. Or run it without installing as `PYTHONPATH=src python3 -m aidd <command>`.

**Before you open a pull request**, run the same checks every agent runs in [AGENTS.md](AGENTS.md), and paste their output. If one fails, fix the code, not the test.

0. Before each commit, the fast content checks take seconds: `python3 tests/run.py plain_language knowledge_templates team_roles_and_flows loop_contract code_shape doc_currency` and `aidd gen-docs --check`.
1. `python3 tests/run.py` runs the unit, security, CLI, team, eval, and git end-to-end tests. Each test file runs in its own process, as many at once as the machine has cores. It ends with the slowest files and the test budget: each file over 20 s, and the wall time against 2 minutes. `python3 tests/run.py test_strict_yaml` runs one file. A full run records which files of the checkout each test file reads, so between steps `python3 tests/run.py --changed` runs only the files that read what changed since then. Add `--base main` to include everything the branch changes. The same suite in one process, `python3 -m unittest discover -s tests`, is slower and gives the same result. The viewer's behavior tests drive a real headless Chrome, which opens a window on a desktop, so locally they run only with `AIDD_BROWSER_TESTS=1` and skip with that reason otherwise. CI runs them on Linux on every pull request, where the runner has Chrome, and a run that opts in with no Chrome fails.
2. `uvx ruff check src tests plugins/aidd-team/tools tools`, `uvx ruff format --check src tests plugins/aidd-team/tools tools`, `uvx mypy`, and `PYTHONPATH=src uvx --from import-linter==2.15 lint-imports`
3. `aidd gen-docs --check`, so the generated docs are current
4. For a change with a Spec, `aidd test --spec specs/<ID>.md`
5. For a change without a Spec, a review sized to the change before it lands, as AGENTS.md says. A wording fix needs only checks 0 to 3, and docs that state facts get the execution tier. Code, schemas, skills, agent files, and the risk rules get the `aidd-team:reviewer` agent

- **Single source of truth.** Schemas, the built-in risk rules in `schemas/risks.json`, and the profiles in `schemas/profiles.json` are data. Never hand-edit a block between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`; change the source and run `aidd gen-docs`.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` may point outside that folder.
- **Workflows.** They must pass `actionlint`, and every action is pinned by commit SHA.
- **Dependabot.** It bumps the dev tools and the actions monthly, and a person reviews and merges each pull request it opens. An actions bump also needs its pins copied into `templates/github/`, which `python3 tools/sync_pins.py` does in one command ([RELEASING.md](RELEASING.md#toolchain-pins)).
- **What CI runs.** A pull request and a push to `main` run the `ci` workflow's `checks` and `test` jobs on Linux. The jobs byte-compile on Python 3.11, install the wheel on 3.11, 3.14, and 3.15, and run the zipapp on 3.14. `aidd-tests` runs the suite on 3.14 for every pull request. The full matrix, Linux, macOS, and Windows on Python 3.11 to 3.15, runs weekly and by hand through `workflow_dispatch`. A release requires it, so a change that touches paths, subprocesses, or line endings is worth a manual run before it merges. CodeQL and Scorecard run weekly while the repository is public. Every checkout has LF line endings, which `.gitattributes` sets.
- **The schema validator and globs.** `tests/test_schema_suite.py` holds them to independent references. Keep them green, and vendor more suite files when you support a new keyword.
- **Commits by agents.** They carry `Assisted-by: <harness>/<model>`.
- **Two spellings, on purpose.** `AIDD` in capitals is the method, as in the AIDD loop or an AIDD Spec. `aidd` in lowercase is the software, meaning the CLI, the plugins, and the skill, even at the start of a sentence. The expansion is written `AI-Driven Development`.

## Code and imports

aidd is one Python package, `src/aidd/`, with no runtime dependency. It is eleven packages, one per capability, and these rules keep them apart and the tests honest. [ARCHITECTURE.md](docs/ARCHITECTURE.md#the-python-package) lists them, says what each holds, and why.

- **Layers.** `.importlinter` lists the packages from the top, `cli`, to the bottom, `kernel`, and a package imports only from the ones below it. `docsgen` sits just above `evals`. Import Linter checks it in CI with `lint-imports`, and `tests/test_import_boundaries.py` runs the same contracts. The file has no `ignore_imports`, so you fix a new wrong-way import and never list it there.
- **Doors.** Other packages use a package only through its `__init__.py`, its door. Write `from aidd import config`, then `config.load_file(...)`, never `from aidd.config import loading`. A door is only its names, so it defines no function or class, and every body lives in a child. It names each export twice. Under `TYPE_CHECKING` it imports the child's name for mypy, as in `from aidd.config.loading import load_file as load_file`. It also lists the name in the map `aidd.kernel.doors.exports` reads at run time. It never binds the name, so importing a package loads none of its children until a caller uses one. A door name is its child's name. One that isn't unique enough at the door gets a fuller one in the child too, so a search finds both. No child module is named like an export. `tests/test_package_doors.py` checks every door, and a door contract per package in `.importlinter` checks that no other package imports a child. `kernel` has no door, so import its modules, as in `from aidd.kernel import git`.
- **No cycle inside a package.** A package's modules may import each other, but never in a circle, however far round, which `acyclic_siblings` in `.importlinter` checks. A name one child reads from another is public, so it has no leading underscore.
- **Absolute imports.** Write `from aidd.kernel import git`, never `from . import git`. A module that moves keeps its own imports, and a search for `aidd.kernel.git` finds every importer. Ruff enforces it with `TID252`.
- **Patch where the name is defined.** `mock.patch.object(module, "name")` replaces one binding, so patch the child module that defines and calls the name, never a door or a module that only re-exports it. A door reads its child on every access, so the patch reaches callers through the door too. Import modules, not names, for anything a test patches, so write `from aidd.kernel import git`, then `git.run(...)`. `tests/test_patch_targets.py` checks every patch in the suite.
- **Commands start fast.** The grammar names each command's handler, such as `"setup:cmd_init"`, and `aidd.cli.parser.Handler` imports it only when the command runs; a handler imports a heavy module inside the function that needs it. `tests/test_cli_handlers.py` checks that building the parser loads no command.
- **Small functions, held by ceilings.** `tests/test_code_shape.py` counts the functions over 60 lines, the functions over 5 parameters, the modules over 700 lines, the one-letter parameters in public functions, and the widest public signature. Each count has a ceiling that only goes down. A change that lowers a count lowers its ceiling too, and a person raises one only on purpose, with the reason in that change. A wide function takes a parameter object, as `aidd init`'s options do.
- **Every module imports on its own.** `tests/test_isolated_imports.py` imports each module first, in a fresh interpreter, so an import cycle cannot hide behind the order the suite imports them in.

## Extend aidd

The repository is built to grow, with the core plugin at the root, more plugins under `plugins/`, and the team's know-how as data and as skill folders. [plugins/README.md](plugins/README.md) is the map. It says where each kind of contribution lives, what it must carry, and the check that keeps it honest.

| To add | Change | Proof |
| --- | --- | --- |
| A domain pack | an entry in `schemas/packs.json`, then `aidd gen-docs` | `aidd eval standards` and `aidd eval packs`; `tests/test_team.py` |
| A practice skill | `plugins/aidd-team/skills/<name>/SKILL.md` with `metadata.checked`, listed in a role's `practices` and in `practices` | the same |
| A role | `schemas/roles.json`, then `aidd gen-docs` (a new role also gets an agent file and a role eval) | `aidd eval roles`; `tests/test_team.py` |
| A library standard or a stack | `standards/<group>/<topic>.md` or `stacks/<name>.yaml`, then `aidd gen-docs` | `aidd eval standards`; `tests/test_standards.py` |
| A plugin | `plugins/<name>/` with `.claude-plugin/plugin.json`, listed in `.claude-plugin/marketplace.json` | `claude plugin validate plugins/<name>` (CI runs it for every plugin) |
| A built-in action, area, or risk rule | an RFC, then `schemas/risks.json` and `aidd gen-docs` | `aidd risk --list`; the `risk` package's tests |
| A coding agent | a `Harness` in `src/aidd/config/harnesses.py`, then `aidd gen-docs`; for its team files, a renderer in `src/aidd/setup/harness_files.py` and a `Voice` in `harness_text.py`; for its ask rules, its format in `src/aidd/risk/`, written from the harness's own documentation | `tests/test_harness_text.py`; a test of its ask rules |

**A change to what a role does carries its eval.** A change that means to change a role's behavior in its agent file, which carries its playbook and the loop contract, adds a scenario to `evals/roles/`. The scenario fails before the change and passes after it. Run `aidd eval roles --agent-command "<your agent>" --repeat 3 --without-aidd` before and after, and keep the change only when the lift doesn't fall. [evals/roles/README.md](evals/roles/README.md) says how to write the scenario and what the merge check reads. The suite sends a role only its agent file, so a change to a practice skill or to the aidd skill gets a reviewer's pass instead. A wording fix that changes no behavior needs no scenario.

## Update a standard

The registry of standards is `schemas/industry-standards.json`, and every pack and practice skill reads it. An agent checks every entry against its source. To update an entry, whether a new edition, a moved page, or a lesson from a postmortem:

1. **Read the source.** Open the entry's `source` and confirm the edition. Copy one full sentence from the page that shows it. The sentence has eight words or more and ends like a sentence; it is not the page title. That's the evidence rule, because a `checked` date always names what was read. So set `checked` to today, and `checked_by` to `agent:<harness>/<model>`, the agent that read the source. Set `evidence` to the `url`, the `quote`, and the day `retrieved`. A practice with no versioned source has no edition, so it needs no `evidence`; its `checked` date says an agent re-read the practice.
2. **Set the cadence when it differs.** Set `review_every_days` for a source that changes faster than the default, and `review_due` for an obligation on a known calendar. [The review cadence](docs/TEAM.md#keeping-the-knowledge-current) explains both.
3. **Check it.** `aidd eval standards` must pass, and `aidd eval standards --online` should report the entry `ok`. Run `aidd gen-docs` so the packs, the agent files, and the reference tables show the new edition; never edit a generated file.
4. **Take the route.** `aidd risk --paths schemas/industry-standards.json` gives it. Open a pull request with the tests, and a maintainer reviews it.

**Which laws join.** A law or a regulation joins the registry only when it changes what the software does: a screen, a data flow, a deadline, a record it keeps, or a test. Tax rates, company filings, and workplace policy stay out. The packs cover the EU, the US, and the UK. A law from another market joins when it is the first or the strictest of its kind, so others follow it. For any other market, the agent says that no pack covers its law, and the team checks it with counsel.

## Add a standard or a stack

A library standard fills one open choice of a pack or a practice skill, and a stack lists standards that go together, as [STANDARDS.md](docs/STANDARDS.md) explains. Each new one, or a change to one, is a Spec, not an RFC. It never changes the loop, the routes, or the risk rules. A new open choice in `schemas/roles.json` is a Spec too, unless it names the method; the method is never an open choice.

1. **Wait for two projects.** A choice joins the library once two projects use it. Until then, it stays in the project's own `docs/standards/`.
2. **Read the version at the source.** Read the tool's newest release at its feed on the day you write the file. Set `checked_version`, `checked`, and `checked_by`; never type a version from memory. The `checked` date also says an agent found the choice still right, so it comes due again after a year when `maturity` is established and after 90 days when it is emerging. A standard names no version a project must use: its tool runs from the project's lock.
3. **Use the template.** [plugins/README.md](plugins/README.md#add-a-library-standard-or-a-stack) has it. Link the pack rule with `implements`; never restate it.
4. **Rename or retire with care.** A new id keeps the old one in `standards/renames.yaml`. A retired standard sets `status: deprecated` and names `replaced_by`, so projects that copied it hear about it.
5. **Check it.** `aidd eval standards` must pass, and `aidd gen-docs` updates [STANDARDS.md](docs/STANDARDS.md).

## Keeping the docs current

Three things keep the docs in step with the code, so a change updates one place and a test catches the rest.

- **Generated blocks.** Tables, counts, and lists that come from data sit between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`. Change the source, such as a schema, `schemas/risks.json`, or `schemas/roles.json`, then run `aidd gen-docs`. `aidd gen-docs --check` fails while a block is stale.
- **Retired wording.** After the first release, when a change renames or retires a concept, add its old wording to `RETIRED` in `tests/test_doc_currency.py`, with what replaced it. Before it, a rename is a plain change, so the list stays empty. The test then fails on every page that still says it, including the pages a later change writes.
- **Concepts by name.** A concept a reader must meet by name goes in `CONCEPTS` there. It then needs a row in the [glossary](docs/GLOSSARY.md) and a mention in `llms.txt`, the page an agent reads first. Each name a schema defines needs a glossary row too, such as a route, a status, a document type, or a role. The same test reads those names from the schemas, so you never list them.

Before you finish a change that adds or renames a concept, search the docs for the old name with `git grep -n -i "<old name>"`. Then read README, the [guide](docs/GUIDE.md), `llms.txt`, and `llms-install.md` once, because most readers, human or agent, read them first.

## Change the method

Changes to routes, profiles, the built-in risk rules, schemas, or the loop need an RFC.

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-name.md` and open a PR with only the RFC. RFCs live under `docs/` and not at the root because nothing in the code reads them; `specs/` is at the root because aidd does.
2. Discussion stays open for at least 7 days, or 14 for anything that lowers a built-in rule's level.
3. The maintainers accept or decline in the PR. An accepted RFC is implemented in its own PR, with a Spec.

1.0.0 itself is the one exception. It was built before this repository ran the loop, so it carries no Specs and no RFCs. While 1.0.0 is re-squashed, the owner approves a re-squash plan instead of an RFC. From the first public pull request on, every change follows the loop and this section.

## Considered and not adopted

These ideas were read and turned down. Each gives the date, the reason, and what would reopen it. Before you propose one again, read its entry. A proposal that answers the reason is welcome.

- **Cognee, a memory layer for agents (2026-11-06).** It calls a paid model or downloads local ones, runs Docker for its MCP service, and sends telemetry by default. aidd calls no model, uses the standard library only, and stays quiet, so aidd keeps its memory in files a person can read. Its idea of linking a decision to the discussion and code behind it is `aidd status <ID>`. Reopen when it runs with no model call, no service to host, and no telemetry by default.
- **OpenWiki, a wiki a model writes (2026-11-06).** A model writes a wiki of the repository, and a daily job rewrites it. Generated prose restates the code and drifts, so an agent may act on a stale claim. Its installer also edits AGENTS.md, which `aidd init` owns. A person writes the docs instead, and a site only publishes them: the `docs-site` open choice of the `technical-writing` practice. Reopen when the wiki is checked against the code on each change, with no model call in aidd.
- **Context and ontology (2026-11-05).** A vector store, embeddings, or a memory or wiki that a model writes for agents: aidd calls no model, and generated prose drifts from the code. An RDF or OWL ontology with a reasoner: SKOS's fields in plain JSON give the checks what they need, with no new dependency. Records as an agent's memory: a record is history about a work item, never a note an agent writes for itself. Reopen when a check needs what plain files and full-text search cannot give.
- **pm-brain (2026-11-05).** It agrees with aidd on no vector store, no embeddings, and promotion as a person's judgment. Its six provenance grades add ceremony that the Spec's evidence warnings and the feedback log's channel already cover. Its raw transcript copies in git work against privacy by default. Its drift sweep needs a model's judgment, and it runs in Claude Code only. Reopen when it keeps no raw transcripts and runs in more than one harness.
- **Skill, product, and writing packs (2026-11-05):** agent-skills, pm-skills, product-engineering, humanizer, and work-humanizer, with one more skills pack.
  - agent-skills' `interview-me`, doubt-driven and constraint-driven development, and its ratchets are covered by the plan command, the refute pass, and the coverage floors. Its `simplify-ignore` and `sdd-cache` hooks rewrite files on read and run a home-made cache.
  - The other skills pack's `sling` sends identifiers to a vendor, and its scanner needs PyYAML, where zizmor is the proven tool.
  - pm-skills' discovery frameworks are covered by `product-discovery`, and its strategy, go-to-market, and legal drafting are outside aidd.
  - product-engineering's intent-versus-code, test derivation, guard hooks, reachability, and flight deck are covered by the verifier, Acceptance `covers`, the harness ask rules, the generated links, and the handoff notes.
  - Both humanizers frame writing as passing a detector, which is not aidd's goal.
  - Run beside aidd-team, these packs add skills that fire on the same prompts. Reopen one when it covers a step aidd-team leaves open.
- **Design and diagram tools (2026-11-05).** diagram-design's HTML and SVG diagrams can't be diffed or reviewed line by line, and they load Google Fonts. Its contrast script is covered by the prototyping skill's lint. archify's renderers are heavy Node code an agent must run, and it checks for updates daily and installs through an unpinned `npx -y skills@latest`. Impeccable's `--github` annotations are a project's own CI choice. Reopen when a diagram tool writes text that diffs, with no network call.
- **Awesome Claude Skills (2026-11-05).** Superpowers' TDD, verification, debugging, worktrees, brainstorming, and planning skills are covered by the skill's rules and the team's roles. Its "merge locally" option breaks one PR/MR and Merge approval. One collection is GPL-3.0, so no text is copied from it. lean-ctx rewrites the command output the agent reads, which is evidence, and it has telemetry. Changelog and docs generators write model prose. aidd points to no skill that sends code to another service, fuzzes live targets, or drives a logged-in browser. Reopen a skill when it fills a gap the team names, and keeps one PR/MR and Merge approval.
- **Spec Kit's extension system (2026-11-05).** It has hooks before and after each command, runtime events, YAML workflows with run state and `resume`, bundles, and community catalogs with sign-in. aidd's flows are skills an agent reads, and autopilot works out the next step from git and the files, so a stopped run needs no run state. Hooks around aidd's commands would add a part each harness must load, and the harness's own hooks and ask rules already do the job. Bundles are aidd's profiles with `aidd init --team`. Reopen the catalog once adopters ask to share flows.

## Naming

Every public name follows these conventions. From 1.0.0 on, a public name changes only under the deprecation policy below.

1. Commands, subcommands, and flags are kebab-case. A noun group is a singular noun and then a verb, such as `standard add`. Every command that reads takes `--json`.
2. YAML keys, JSON fields, and enum values are snake_case with no spaces. A value that is also a CLI word or a file name, such as a doc type, is kebab-case.
3. An action is `resource.verb`, in lowercase snake_case words, with a dot for a narrower action, such as `git.push.force`. An area is one snake_case word or more, such as `personal_data`.
4. A limit has a `max_` or `min_` prefix, and a unit is a spelled-out suffix, such as `_seconds`, `_minutes`, `_hours`, or `_days`.
5. A date ends in `_on` or `due`, and a timestamp ends in `_at`.
6. Every JSON output has `schema_version` and a schema in `schemas/`.
7. A standard's id is `<group>/<topic>`, a test is `std.<group>.<topic>.<name>`, and a choice is `<pack>:<choice>`. An identity is `@login`, `email:<address>`, or `agent:<harness>/<model>`.
8. An environment variable is `AIDD_<NOUN>`. A git trailer takes git's own form, as in `Assisted-by` and `Approved-by`.
9. An ordinal scale is low, medium, and high, and priority adds urgent.
10. Names inside an experimental feature may change in a minor release (Versioning).

## Versioning

This section owns the versioning policy; other documents link here.

- **Patch.** Clarifications and bug fixes that no repository using aidd can observe.
- **Minor.** New optional fields, new actions, areas, and rules, and new modules.
- **Major.** Any change that can turn a passing check into a failing one under an unchanged config, or that removes or renames a key, a command, a flag, or an action.

A change to a built-in rule's level is listed in the CHANGELOG under its own heading, so a project can set its own rule back.

<a id="frozen-tests"></a>**Frozen tests stay green across upgrades.** A Spec's tests may run an aidd command, such as `aidd validate` or `aidd prototype --check`. Within one major version, each such command accepts every input an earlier release of that major accepted. So an upgrade never turns an approved Spec's frozen test red. A new or stricter check arrives as a warning, or behind the format version a file names, and fails only from the next major.

**Experimental names.** Names inside a feature marked experimental may change in a minor release. The CHANGELOG says so in that release.

<a id="deprecation"></a>**Deprecation.** This is the one deprecation policy; other pages link here. From 1.0.0 on, a config key, Spec field, action, CLI command, or flag being replaced keeps working until the next major release. A warning names the replacement. The changelog lists it under Deprecated in the release that deprecates it. Names changed before 1.0.0 were never released, so 1.0.0 keeps none of them.

**Cadence.** There's no fixed cadence. A release goes out when the changelog earns it, and a security fix goes out as a patch as soon as it's ready. [GOVERNANCE.md](GOVERNANCE.md) sets the cadence.

## Release

Maintainers follow [RELEASING.md](RELEASING.md).

## Security

Report a vulnerability privately, as [SECURITY.md](SECURITY.md) describes. That includes a way for aidd to run a project's code it should only read, to leak a secret, or to write a harness ask rule that is looser than the config.
