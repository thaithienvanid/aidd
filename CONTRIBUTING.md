# Contributing

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

This repository uses aidd on itself. Every change is a PR whose description holds a Change Request block. The block is the few lines that tell the gate the change's route, type, and agents; `aidd describe` prints one. No pull request has gone through a [live gate](docs/ENTERPRISE.md#1-release-status-and-maturity) yet. Once the first one does, a change will merge only when `aidd/gate` is green.

## Develop

```sh
uv venv && . .venv/bin/activate && uv pip install -e .   # or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
aidd gen-docs                          # regenerate every generated block and domain pack after changing a schema
aidd validate                          # config, objects, and overdue emergency reviews
aidd eval standards                    # the team's standards registry: nothing past its review cadence
aidd eval packs                        # every pack and practice skill in its template and under its size cap
```

Without activating the venv, prefix each command with `uv run`, as in `uv run aidd gen-docs`. Or run it without installing as `PYTHONPATH=src python3 -m aidd <command>`.

**Before you open a pull request**, run the same checks every agent runs in [AGENTS.md](AGENTS.md), and paste their output. If one fails, fix the code, not the test.

0. Before each commit, the fast content checks take seconds: `python3 tests/run.py plain_language knowledge_templates team_roles_and_flows loop_contract code_shape doc_currency` and `aidd gen-docs --check`.
1. `python3 tests/run.py` runs the unit, red-team, security, adapter, CLI, scale, team, eval, and git end-to-end tests. Each test file runs in its own process, as many at once as the machine has cores. It ends with the slowest files. `python3 tests/run.py test_autopilot` runs one file. The same suite in one process, `python3 -m unittest discover -s tests`, is slower and gives the same result.
2. `uvx ruff check src tests`, `uvx ruff format --check src tests`, `uvx mypy`, and `PYTHONPATH=src uvx --from import-linter==2.15 lint-imports`
3. `aidd gen-docs --check` and `aidd eval examples`, so the generated docs are current and the gate passes its conformance suite
4. For a change with a Spec, `aidd test --spec specs/<ID>.md` and then the local gate, `aidd gate --spec specs/<ID>.md`. Only approvals may still be pending
5. For a change without a Spec, a review sized to the change before it lands, as AGENTS.md says. A wording fix needs only checks 0 to 3, and docs that state facts get the execution tier. Code, schemas, skills, agent files, the guard, and the gate get the `aidd-team:reviewer` agent

- **Single source of truth.** Schemas, the profile gates in `schemas/profiles.json`, and the baseline rules in `schemas/baseline.json` are data. Never hand-edit a block between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`; change the source and run `aidd gen-docs`.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` may point outside that folder.
- **A new gate rule.** It is a function in the module of `src/aidd/gate/rules/` its concern belongs to, added to `GATES` in `src/aidd/gate/rules/__init__.py`. Its description is in `src/aidd/gate/rulebook.py`, from which the rule tables are generated, and it joins one of the five `QUESTIONS` there. It has one passing and one failing conformance case, preferably as a mutation in `examples/<case>/mutations/`, which is data any reimplementation can replay. Rules an organization owns belong in its Policy command instead, as `examples/policy/` shows.
- **Workflows.** They must pass `actionlint`, and every action is pinned by commit SHA.
- **Dependabot.** Its bumps of the dev tools are a standard change, `dependabot-dev-tools` in `.aidd/config.yaml`. Its pull request merges on green tests with no approval, a major bump included, when it touches only `tools/mermaid/package.json`, `tools/mermaid/package-lock.json`, or the lint and coverage locks in `.github/requirements/`, stays within 1,200 changed lines, and has signed commits. These tools run only in CI, so a break shows as red CI. A bump of the release's build backend or SBOM generator (`build.*`, `sbom.*`) needs an approval, because a bad one would pass the reproducible rebuild. Everything else it opens needs an approval as usual. Actions bumps in `.github/workflows/` and `action.yml`, and `pyproject.toml`, are protected paths. An actions bump or a Claude Code CLI bump also needs its pins copied into `templates/github/`, which `python3 tools/sync_pins.py` does in one command ([RELEASING.md](RELEASING.md#toolchain-pins)).
- **What CI runs.** A pull request and a push to `main` run the `ci` workflow's `checks` and `test` jobs on Linux. The jobs byte-compile on Python 3.11, install the wheel on 3.11, 3.14, and 3.15, and run the zipapp on 3.14. `aidd-tests` runs the suite on 3.14 for every pull request. The full matrix, Linux, macOS, and Windows on Python 3.11 to 3.15, runs weekly and by hand through `workflow_dispatch`. A release requires it, so a change that touches paths, subprocesses, or line endings is worth a manual run before it merges. CodeQL and Scorecard run weekly while the repository is public. Every checkout has LF line endings, which `.gitattributes` sets.
- **The schema validator and globs.** `tests/test_schema_suite.py` holds them to independent references. Keep them green, and vendor more suite files when you support a new keyword.
- **Commits by agents.** They carry `Assisted-by: <harness>/<model>`.
- **Two spellings, on purpose.** `AIDD` in capitals is the method, as in the AIDD loop or an AIDD Spec. `aidd` in lowercase is the software, meaning the CLI, the plugins, the skill, and `aidd/gate`, even at the start of a sentence. The expansion is written `AI-Driven Development`.

## Code and imports

aidd is one Python package, `src/aidd/`, with no runtime dependency. It is fourteen packages, one per capability, and these rules keep them apart and the tests honest. [ARCHITECTURE.md](docs/ARCHITECTURE.md#the-python-package) lists them, says what each holds, and why.

- **Layers.** `.importlinter` lists the packages from the top, `cli`, to the bottom, `kernel`, and a package imports only from the ones below it. `guard` and `evals` share a layer and never import each other. Import Linter checks it in CI with `lint-imports`, and `tests/test_import_boundaries.py` runs the same contracts. The file has no `ignore_imports`, so you fix a new wrong-way import and never list it there. The file is a protected path, so a change to it takes the major route.
- **Doors.** Other packages use a package only through its `__init__.py`, its door. Write `from aidd import gate`, then `gate.decide(...)`, never `from aidd.gate import routing`. A door is only its names, so it defines no function or class, and every body lives in a child. It names each export twice. Under `TYPE_CHECKING` it imports the child's name for mypy, as in `from aidd.tracking.metrics import metrics_markdown as metrics_markdown`. It also lists the name in the map `aidd.kernel.doors.exports` reads at run time. It never binds the name, so importing a package loads none of its children until a caller uses one. A door name is its child's name. One that isn't unique enough at the door gets a fuller one in the child too, so `tracking.metrics_markdown` is `metrics.metrics_markdown`, and a search finds both. No child module is named like an export. `tests/test_package_doors.py` checks every door, and a door contract per package in `.importlinter` checks that no other package imports a child. `kernel` has no door, so import its modules, as in `from aidd.kernel import git`.
- **No cycle inside a package.** A package's modules may import each other, but never in a circle, however far round, which `acyclic_siblings` in `.importlinter` checks. A name one child reads from another is public, so it has no leading underscore.
- **Extension discovery stays at the top.** Only `cli` discovers installed extensions, through `aidd.kernel.extensions`, and passes what it found down; `config`, `workitems`, `gate`, `platforms`, and `guard` never reach it, which `.importlinter` checks.
- **Absolute imports.** Write `from aidd.kernel import git`, never `from . import git`. A module that moves keeps its own imports, and a search for `aidd.kernel.git` finds every importer. Ruff enforces it with `TID252`.
- **Patch where the name is defined.** `mock.patch.object(module, "name")` replaces one binding, so patch the child module that defines and calls the name, never a door or a module that only re-exports it. A door reads its child on every access, so the patch reaches callers through the door too. Import modules, not names, for anything a test patches, so write `from aidd.kernel import git`, then `git.run(...)`. `tests/test_patch_targets.py` checks every patch in the suite.
- **The guard starts fast.** `aidd hook pre-tool` runs before every edit and command an agent makes. The grammar names each command's handler, such as `"setup:cmd_init"`, and `aidd.cli.parser.Handler` imports it only when the command runs; a handler imports a heavy module inside the function that needs it. `tests/test_startup_cost.py` caps the code the hook loads, and `tests/test_cli_handlers.py` checks that building the parser loads no command.
- **Small functions, held by ceilings.** `tests/test_code_shape.py` counts the functions over 60 lines, the functions over 5 parameters, the modules over 700 lines, the one-letter parameters in public functions, and the widest public signature. Each count has a ceiling that only goes down. A change that lowers a count lowers its ceiling too, and a person raises one only on purpose, with the reason in that change. A wide function takes a parameter object, as `aidd init`'s options do.
- **Every module imports on its own.** `tests/test_isolated_imports.py` imports each module first, in a fresh interpreter, so an import cycle cannot hide behind the order the suite imports them in.

## Extend aidd

The repository is built to grow, with the core plugin at the root, more plugins under `plugins/`, and the team's know-how as data and as skill folders. [plugins/README.md](plugins/README.md) is the map. It says where each kind of contribution lives, what it must carry, and the check that keeps it honest.

| To add | Change | Proof |
| --- | --- | --- |
| A domain pack | an entry in `schemas/packs.json`, then `aidd gen-docs` | `aidd eval standards` and `aidd eval packs`; `tests/test_team.py` |
| A practice skill | `plugins/aidd-team/skills/<name>/SKILL.md` with `metadata.checked`, listed in a role's `practices` and in `practices` | the same |
| A role or an extension | `schemas/roles.json`, then `aidd gen-docs` (a new role also gets an agent file and a role eval) | `aidd eval roles`; `tests/test_team.py` |
| A library standard or a stack | `standards/<group>/<topic>.md` or `stacks/<name>.yaml`, then `aidd gen-docs` | `aidd eval standards`; `tests/test_standards.py` |
| A plugin | `plugins/<name>/` with `.claude-plugin/plugin.json`, listed in `.claude-plugin/marketplace.json` | `claude plugin validate plugins/<name>` (CI runs it for every plugin) |
| A coding agent | a `Harness` in `src/aidd/config/harnesses.py`, then `aidd gen-docs`; for its team files, a renderer in `src/aidd/setup/harness_files.py` and a `Voice` in `harness_text.py`; for aidd's hooks, a `Dialect` in `src/aidd/guard/dialects.py` and its wiring in `src/aidd/setup/` (as `antigravity_wiring.py`) | `tests/test_harness_text.py`; for hooks, a test like `tests/test_antigravity.py` |
| An `/aidd` verb, or a change to one | both homes in one change: `plugins/aidd-mods/hooks/` for Claude Code and `templates/opencode/aidd-tui/` for OpenCode, then `aidd upgrade --yes` for this repository's copy | `claude plugin test plugins/aidd-mods` and `tests/test_opencode.py`, which also holds the verb list equal |
| A gate rule | an RFC, then `src/aidd/gate/rules/`, `src/aidd/gate/rulebook.py`, and cases in `examples/` | `aidd eval examples` |

**A change to what a role does carries its eval.** Each gate rule carries its cases, and the team's text works the same way. A change that means to change a role's behavior in its agent file, which carries its playbook and the loop contract, adds a scenario to `evals/roles/`. The scenario fails before the change and passes after it. Run `aidd eval roles --agent-command "<your agent>" --repeat 3 --without-aidd` before and after, and keep the change only when the lift doesn't fall. [evals/roles/README.md](evals/roles/README.md) says how to write the scenario and what the merge check reads. The suite sends a role only its agent file, so a change to a practice skill or to the aidd skill gets a reviewer's pass instead. A wording fix that changes no behavior needs no scenario.

## Update a standard

The registry of standards is `schemas/industry-standards.json`, and every pack and practice skill reads it. To update an entry, whether a new edition, a moved page, or a lesson from a postmortem:

1. **Read the source.** Open the entry's `source` and confirm the edition. Copy one full sentence from the page that shows it. The sentence has eight words or more and ends like a sentence; it is not the page title. That's the evidence rule, because a `checked` date always names what was read. So set `checked` to today, and `checked_by` to your handle, or to `agent:<harness>/<model>` for an agent's check. Set `evidence` to the `url`, the `quote`, and the day `retrieved`. A practice with no versioned source carries `reviewed` instead, with no edition.
2. **Set the cadence when it differs.** Set `review_every_days` for a source that changes faster than the default, and `review_due` for an obligation on a known calendar. [The review cadence](docs/TEAM.md#keeping-the-knowledge-current) explains both.
3. **Check it.** `aidd eval standards` must pass, and `aidd eval standards --online` should report the entry `ok`. Run `aidd gen-docs` so the packs, the agent files, and the reference tables show the new edition; never edit a generated file.
4. **Take the route.** A change to `schemas/roles.json` is a change to a protected path, so it takes the major route. That is a pull request with its Change Request block, the tests, and a person's approval. A maintainer reviews it.

**A person's review.** An agent's check proves a source was read, not that the practice matches it. So a person reviews the entries too, the laws and regulations first. `aidd eval standards --unreviewed` lists them, and says how to record the review. A review is the same update as above, with your own identity in `checked_by`. `aidd eval standards` reports how much of the registry a person has reviewed.

## Extending the CLI

A Python package extends the `aidd` command without a fork, through entry points in its own `pyproject.toml`. aidd reads them with the standard library's `importlib.metadata`, so nothing new is installed:

```toml
[project.entry-points."aidd.commands"]
cost-report = "acme_aidd.cli:register"        # register(subparsers): add_parser(...), set_defaults(func=run); run(args) -> exit code

[project.entry-points."aidd.exporters"]
parquet = "acme_aidd.export:to_parquet"      # export(kind, items) -> str | bytes, for `aidd record export events DIR --format parquet`

[project.entry-points."aidd.renderers"]
slack = "acme_aidd.render:slack"             # render(summary) -> str, for `aidd metrics events.jsonl --render slack`

[project.entry-points."aidd.packs"]
payments = "acme_aidd.packs:payments"        # pack() -> the directory of a domain-pack skill holding SKILL.md
```

The rules an extension lives by:

- **It never reaches the gate.** `gate`, `test`, `validate`, `hash`, `approve`, `land`, `publish`, `hook`, `mcp`, `describe`, `list`, and `record verify` never discover extensions. `aidd` seals discovery before it builds their parser, so no extension module is imported in their process. `src/aidd/kernel/extensions.py` does that. `tests/test_extensions.py` installs a plugin that tries to rewrite the gate, and checks that the gate's output and record stay byte-identical.
- **It adds, never replaces.** A command named like a built-in one is ignored; one that fails to import or register is skipped with a warning.
- **Its output is not evidence.** A renderer or an exporter formats what aidd computed; nothing an extension prints is read back by the gate.
- **Discovery is deterministic.** Entry points are sorted by name, and the first of two with one name wins.

## Add a standard or a stack

A library standard fills one open choice of a pack or a practice skill, and a stack lists standards that go together, as [STANDARDS.md](docs/STANDARDS.md) explains. Each new one, or a change to one, is a Spec, not an RFC. It never changes the loop, the routes, or the gate rules. A new open choice in `schemas/roles.json` is a Spec too, unless it names the method; the method is never an open choice.

1. **Wait for two projects.** A choice joins the library once two projects use it. Until then, it stays in the project's own `docs/standards/`.
2. **Read the version at the source.** Read the tool's newest release at its feed on the day you write the file. Set `checked_version`, `pin`, and `checked`; never type a version from memory.
3. **Use the template.** [plugins/README.md](plugins/README.md#add-a-library-standard-or-a-stack) has it. Link the pack rule with `implements`; never restate it.
4. **Rename or retire with care.** A new id keeps the old one in `standards/renames.yaml`. A retired standard sets `status: deprecated` and names `replaced_by`, so projects that copied it hear about it.
5. **Check it.** `aidd eval standards` must pass, and `aidd gen-docs` updates [STANDARDS.md](docs/STANDARDS.md).

## Keeping the docs current

Three things keep the docs in step with the code, so a change updates one place and a test catches the rest.

- **Generated blocks.** Tables, counts, and lists that come from data sit between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`. Change the source, such as a schema, `schemas/roles.json`, or the rulebook, then run `aidd gen-docs`. `aidd gen-docs --check` fails while a block is stale.
- **Retired wording.** When a change renames or retires a concept, add its old wording to `RETIRED` in `tests/test_doc_currency.py`, with what replaced it. The test then fails on every page that still says it, including the pages a later change writes.
- **Concepts by name.** A concept a reader must meet by name goes in `CONCEPTS` there. It then needs a row in the [glossary](docs/GLOSSARY.md) and a mention in `llms.txt`, the page an agent reads first.

Before you finish a change that adds or renames a concept, search the docs for the old name with `git grep -n -i "<old name>"`. Then read README, `llms.txt`, and `llms-install.md` once, because most readers, human or agent, read them first.

## Change the method

Changes to routes, profiles, gate rules, schemas, or the loop need an RFC.

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-name.md` and open a PR with only the RFC. RFCs live under `docs/` and not at the root because nothing in the code reads them; `specs/` is at the root because the gate does.
2. Discussion stays open for at least 7 days, or 14 for anything that loosens a gate rule.
3. The maintainers accept or decline in the PR. An accepted RFC is implemented in its own PR, with a Spec.

1.0.0 itself is the one exception. It was built before this repository had a live gate, so it carries no Specs and no RFCs. The reasons behind its one-way decisions are in [RATIONALE.md](docs/RATIONALE.md). From the first public pull request on, every change follows the loop and this section.

## Naming

Every public name follows these conventions. From 1.0.0 on, a public name changes only under the deprecation policy below.

1. Commands, subcommands, and flags are kebab-case. A noun group is a singular noun and then a verb, such as `standard add` or `record verify`. Every command that reads takes `--json`.
2. YAML keys, JSON fields, and enum values are snake_case with no spaces. A value that is also a CLI word or a file name, such as a doc kind or a hook, is kebab-case.
3. A limit has a `max_` or `min_` prefix, and a unit is a spelled-out suffix, such as `_seconds`, `_minutes`, `_hours`, or `_days`.
4. A date ends in `_on` or `due`, and a timestamp ends in `_at`. A decision is `{decision, by, on, reason}`.
5. Every JSON output has `schema_version` and a schema in `schemas/`.
6. Codes are stable. A finding is `<rule>.<snake>`, and a step is `<object>.<state>`.
7. A standard's id is `<group>/<topic>`, a test is `std.<group>.<topic>.<name>`, and a choice is `<pack>:<choice>`. An identity is `@login`, `email:<address>`, or `agent:<harness>/<model>`.
8. An environment variable is `AIDD_<NOUN>`, and a git trailer is `Aidd-<Noun>`.
9. "Gate" means only `aidd gate` and `aidd/gate`. A person gives an approval, and a held command waits for a person.
10. A hook takes the name of the harness event it serves, such as `pre-tool` for PreToolUse.
11. An ordinal scale is low, medium, and high, and priority adds urgent.
12. Names inside an experimental feature may change in a minor release (Versioning).

## Versioning

This section owns the versioning policy; other documents link here.

- **Patch.** Clarifications and bug fixes that no conforming repo can observe.
- **Minor.** New optional fields, rules that only add information, and new modules.
- **Major.** Any change that can turn a passing change into a failing one, or the reverse, under an unchanged config.

A gate may be tightened in a minor release only behind a new profile or an opt-in `gates` key.

**Experimental names.** Names inside a feature marked experimental (`aidd context`) may change in a minor release. The CHANGELOG says so in that release.

<a id="deprecation"></a>**Deprecation.** This is the one deprecation policy; other pages link here. From 1.0.0 on, a config key, Spec field, rule name, CLI command, or flag being replaced keeps working until the next major release. A warning names the replacement. The changelog lists it under Deprecated in the release that deprecates it. Names changed before 1.0.0 were never released, so 1.0.0 keeps none of them, except two that adopters' setups already call: `aidd hook pre-edit` (now `pre-tool`) and the comment `/aidd approve <sha>` (now `/aidd approve-merge <sha>`).

**Cadence.** There's no fixed cadence. A release goes out when the changelog earns it, and a security fix goes out as a patch as soon as it's ready. [GOVERNANCE.md](GOVERNANCE.md) sets the cadence.

## Release

Maintainers follow [RELEASING.md](RELEASING.md).

## Security

A way to merge without the gate's evidence or approvals is a security bug. Report it privately, as [SECURITY.md](SECURITY.md) describes.
