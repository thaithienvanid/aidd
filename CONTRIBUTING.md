# Contributing

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

This repository uses aidd on itself. Every change is a PR whose description holds a Change Request block. The block is the few lines that tell the gate the change's route, type, and agents; `aidd describe` prints one. No pull request has gone through a live gate yet ([ENTERPRISE.md](docs/ENTERPRISE.md#1-release-status-and-maturity)). Once the first one does, a change will merge only when `aidd/gate` is green.

## Develop

```sh
uv venv && . .venv/bin/activate && uv pip install -e .   # or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
aidd gen-docs                          # regenerate every generated block and domain pack after changing a schema
aidd validate                          # config, objects, and overdue emergency reviews
aidd eval standards                    # the team's standards registry: nothing past its review cadence
aidd eval packs                        # every pack and practice skill in its template and under its size cap
```

Without activating the venv, prefix each command with `uv run` (`uv run aidd gen-docs`), or run it without installing as `PYTHONPATH=src python3 -m aidd <command>`.

**Before you open a pull request**, run the same checks every agent runs ([AGENTS.md](AGENTS.md)), and paste their output. If one fails, fix the code, not the test.

1. `python3 -m unittest discover -s tests`: unit, red-team, security, adapter, CLI, scale, team, eval, and git end-to-end tests
2. `uvx ruff check src tests`, `uvx ruff format --check src tests`, and `uvx mypy`
3. `aidd gen-docs --check` and `aidd eval examples`: the generated docs are current, and the gate passes its conformance suite
4. For a change with a Spec, `aidd test --spec specs/<ID>.md` and then the local gate, `aidd gate --spec specs/<ID>.md` (only approvals may still be pending)

- **Single source of truth.** Schemas, profile gates (`schemas/profiles.json`), and baseline rules (`schemas/baseline.json`) are data. Never hand-edit a block between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`; change the source and run `aidd gen-docs`.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` may point outside that folder.
- **A new gate rule.** It is a function in `src/aidd/gates.py`, added to `GATES`. Its description is in `src/aidd/rulebook.py`, from which the rule tables are generated. It has one passing and one failing conformance case, preferably as a mutation in `examples/<case>/mutations/` (data any reimplementation can replay). Rules an organization owns belong in its Policy command instead (`examples/policy/`).
- **Workflows.** They must pass `actionlint`, and every action is pinned by commit SHA.
- **Dependabot.** Its routine tooling bumps are a standard change, `dependabot-tooling` in `.aidd/config.toml`. Its pull request merges on green tests with no approval when it touches only `tools/mermaid/package.json`, `tools/mermaid/package-lock.json`, or `.github/requirements/`, stays within 1,200 changed lines, and has signed commits. Everything else it opens needs an approval as usual. Actions bumps (`.github/workflows/`, `action.yml`) and `pyproject.toml` are protected paths. A Claude Code CLI bump also needs the `templates/github/aidd-diagnose.yml` pin updated by hand ([RELEASING.md](RELEASING.md#toolchain-pins)).
- **What CI runs.** A pull request and a push to `main` run the `ci` workflow's `checks` and `test` jobs on Linux. The jobs run the suite on Python 3.11, the wheel on 3.11 and 3.14, and the zipapp. `aidd-tests` runs the suite on 3.14 for every pull request. The full matrix, Linux, macOS, and Windows on Python 3.11 to 3.15, runs weekly and by hand (`workflow_dispatch`). A release requires it, so a change that touches paths, subprocesses, or line endings is worth a manual run before it merges. CodeQL and Scorecard run weekly while the repository is public. Every checkout has LF line endings (`.gitattributes`).
- **The schema validator and globs.** They are held to independent references (`tests/test_schema_suite.py`): keep them green, and vendor more suite files when you support a new keyword.
- **Commits by agents.** They carry `Assisted-by: <harness>/<model>`.
- **Two spellings, on purpose.** `AIDD` in capitals is the method (the AIDD loop, an AIDD Spec). `aidd` in lowercase is the software (the CLI, the plugins, the skill, `aidd/gate`), even at the start of a sentence. The expansion is written `AI-Driven Development`.

## Extend aidd

The repository is built to grow: the core plugin at the root, more plugins under `plugins/`, and the team's know-how as data and as skill folders. [plugins/README.md](plugins/README.md) is the map: where each kind of contribution lives, what it must carry, and the check that keeps it honest.

| To add | Change | Proof |
| --- | --- | --- |
| A domain pack | a `domains` entry in `schemas/roles.json`, then `aidd gen-docs` | `aidd eval standards` and `aidd eval packs`; `tests/test_team.py` |
| A practice skill | `plugins/aidd-team/skills/<name>/SKILL.md` with `metadata.checked`, listed in a role's `practices` and in `practices` | the same |
| A role or an extension | `schemas/roles.json`, then `aidd gen-docs` (a new role also gets an agent file and a role eval) | `aidd eval roles`; `tests/test_team.py` |
| A library standard or a stack | `standards/<group>/<topic>.md` or `stacks/<name>.toml`, then `aidd gen-docs` | `aidd eval standards`; `tests/test_standards.py` |
| A plugin | `plugins/<name>/` with `.claude-plugin/plugin.json`, listed in `.claude-plugin/marketplace.json` | `claude plugin validate plugins/<name>` (CI runs it for every plugin) |
| A gate rule | an RFC, then `src/aidd/gates.py`, `src/aidd/rulebook.py`, and cases in `examples/` | `aidd eval examples` |

## Update a standard

The registry of standards is `schemas/roles.json` (its `standards` table), and every pack and practice skill reads it. To update an entry, whether a new edition, a moved page, or a lesson from a postmortem:

1. **Read the source.** Open the entry's `source` and confirm the edition. Copy one full sentence from the page that shows it. The sentence has eight words or more and ends like a sentence; it is not the page title. That is the evidence rule: a `checked` date always names what was read. So set `checked` to today, and `checked_by` to your handle (or `agent:<harness>/<model>` for an agent's check). Set `evidence` to the `url`, the `quote`, and the day `retrieved`. A practice with no versioned source carries `reviewed` instead, with no edition.
2. **Set the cadence when it differs.** `review_every_days` for a source that changes faster than the default, and `review_due` for an obligation on a known calendar ([the review cadence](docs/TEAM.md#keeping-the-knowledge-current)).
3. **Check it.** `aidd eval standards` must pass, and `aidd eval standards --online` should report the entry `ok`. Run `aidd gen-docs` so the packs, the agent files, and the reference tables show the new edition; never edit a generated file.
4. **Take the route.** A change to `schemas/roles.json` is a change to a protected path, so it takes the major route. That is a pull request with its Change Request block, the tests, and a person's approval. The pack's or skill's steward (`aidd owners` lists them) reviews it; while none is named, a maintainer does.

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

- **It never reaches the gate.** `gate`, `test`, `validate`, `hash`, `approve`, `ship`, `hook`, `mcp`, `describe`, `assess`, `list`, and `record verify` never discover extensions. `aidd` seals discovery before it builds their parser, so no extension module is imported in their process (`src/aidd/ext.py`). `tests/test_extensions.py` installs a plugin that tries to rewrite the gate, and checks that the gate's output and record stay byte-identical.
- **It adds, never replaces.** A command named like a built-in one is ignored; one that fails to import or register is skipped with a warning.
- **Its output is not evidence.** A renderer or an exporter formats what aidd computed; nothing an extension prints is read back by the gate.
- **Discovery is deterministic**: entry points are sorted by name, and the first of two with one name wins.

## Add a standard or a stack

A library standard fills one open choice of a pack or a practice skill, and a stack lists standards that go together ([STANDARDS.md](docs/STANDARDS.md)). Each new one, or a change to one, is a Spec, not an RFC. It never changes the loop, the routes, or the gate rules. A new open choice in `schemas/roles.json` is a Spec too, unless it names the method; the method is never an open choice.

1. **Wait for two projects.** A choice joins the library once two projects use it. Until then, it stays in the project's own `docs/standards/`.
2. **Read the version at the source.** Read the tool's newest release at its feed on the day you write the file. Set `checked_version`, `pin`, and `checked`; never type a version from memory.
3. **Use the template.** [plugins/README.md](plugins/README.md#add-a-library-standard-or-a-stack) has it. Link the pack rule with `implements`; never restate it.
4. **Rename or retire with care.** A new id keeps the old one in `standards/renames.toml`. A retired standard sets `status = "deprecated"` and names `replaced_by`, so projects that copied it hear about it.
5. **Check it.** `aidd eval standards` must pass, and `aidd gen-docs` updates [STANDARDS.md](docs/STANDARDS.md).

## Change the method

Changes to routes, profiles, gate rules, schemas, or the loop need an RFC.

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-name.md` and open a PR with only the RFC. RFCs live under `docs/` and not at the root because nothing in the code reads them; `specs/` is at the root because the gate does.
2. Discussion stays open for at least 7 days, or 14 for anything that loosens a gate rule.
3. The maintainers accept or decline in the PR. An accepted RFC is implemented in its own PR, with a Spec.

## Naming

Every public name follows these conventions. From 1.0.0 on, a public name changes only under the deprecation policy below.

1. Commands, subcommands, and flags are kebab-case. A noun group is a singular noun and then a verb (`standard add`, `record verify`). Every command that reads takes `--json`.
2. TOML keys, JSON fields, and enum values are snake_case with no spaces. A value that is also a CLI word or a file name (a doc kind, a hook) is kebab-case.
3. A limit has a `max_` or `min_` prefix, and a unit is a spelled-out suffix (`_seconds`, `_minutes`, `_hours`, `_days`).
4. A date ends in `_on` or `due`, and a timestamp ends in `_at`. A decision is `{decision, by, on, reason}`.
5. Every JSON output has `schema_version` and a schema in `schemas/`.
6. Codes are stable: a finding is `<rule>.<snake>`, and a step is `<object>.<state>`.
7. A standard's id is `<group>/<topic>`, a test is `std.<group>.<topic>.<name>`, and a choice is `<pack>:<choice>`. An identity is `@login`, `email:<address>`, or `agent:<harness>/<model>`.
8. An environment variable is `AIDD_<NOUN>`, and a git trailer is `Aidd-<Noun>`.
9. "Gate" means only `aidd gate` and `aidd/gate`. A person gives an approval, and a held command waits for a person.
10. A hook takes the name of the harness event it serves (`pre-tool` for PreToolUse).
11. An ordinal scale is low, medium, and high (and urgent, for priority).
12. Names inside an experimental feature may change in a minor release (see Versioning).

## Versioning

This section owns the versioning policy; other documents link here.

- **Patch.** Clarifications and bug fixes that no conforming repo can observe.
- **Minor.** New optional fields, rules that only add information, and new modules.
- **Major.** Any change that can turn a passing change into a failing one, or the reverse, under an unchanged config.

A gate may be tightened in a minor release only behind a new profile or an opt-in `[gates]` key.

**Experimental names.** Names inside a feature marked experimental (autopilot, `aidd context`, `/aidd-team:autopilot`) may change in a minor release. The CHANGELOG says so in that release.

<a id="deprecation"></a>**Deprecation.** This is the one deprecation policy; other pages link here. From 1.0.0 on, a config key, Spec field, rule name, CLI command, or flag being replaced keeps working until the next major release. A warning names the replacement. The changelog lists it under Deprecated in the release that deprecates it. Names changed before 1.0.0 were never released, so 1.0.0 keeps none of them, except two that adopters' setups already call: `aidd hook pre-edit` (now `pre-tool`) and the comment `/aidd approve <sha>` (now `/aidd approve-merge <sha>`).

**Cadence.** None fixed: a release ships when the changelog earns it; a security fix ships as a patch as soon as it is ready ([GOVERNANCE.md](GOVERNANCE.md)).

## Release

Maintainers follow [RELEASING.md](RELEASING.md).

## Security

A way to merge without the gate's evidence or approvals is a security bug. Report it privately, as [SECURITY.md](SECURITY.md) describes.
