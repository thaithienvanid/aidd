# Contributing

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

This repository uses aidd on itself. Every change is a PR whose description holds a `toml aidd` block (the few lines that tell the gate the change's route, type, and agents; `aidd change` prints one). No pull request has gone through a live gate yet ([ENTERPRISE.md](docs/ENTERPRISE.md#1-release-status-and-maturity)); once the first one does, a change will merge only when `aidd/gate` is green.

## Develop

```sh
uv venv && . .venv/bin/activate && uv pip install -e .   # or: python3 -m venv .venv && . .venv/bin/activate && pip install -e .
aidd gen-docs                          # regenerate every generated block and domain pack after changing a schema
aidd validate                          # config, objects, and overdue emergency reviews
aidd eval standards                    # the team's standards registry: nothing older than a year
```

Without activating the venv, prefix each command with `uv run` (`uv run aidd gen-docs`), or run it without installing as `PYTHONPATH=src python3 -m aidd <command>`.

**Before you open a pull request**, run the same checks every agent runs ([AGENTS.md](AGENTS.md)), and paste their output. If one fails, fix the code, not the test.

1. `python3 -m unittest discover -s tests`: unit, red-team, security, adapter, CLI, scale, team, eval, and git end-to-end tests
2. `uvx ruff check src tests`, `uvx ruff format --check src tests`, and `uvx mypy`
3. `aidd gen-docs --check` and `aidd eval examples`: the generated docs are current, and the verifier passes its conformance suite
4. For a change with a Spec, `aidd test --spec specs/<ID>.md` and then the local gate, `aidd gate --spec specs/<ID>.md` (only approvals may still be pending)

- **Single source of truth.** Schemas, profile gates (`schemas/profiles.json`), and baseline rules (`schemas/baseline.json`) are data. Never hand-edit a block between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`; change the source and run `aidd gen-docs`.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` may point outside that folder.
- **A new gate rule.** It is a function in `src/aidd/gates.py`, added to `GATES`, with its description in `src/aidd/rulebook.py` (from which the rule tables are generated) and one passing and one failing conformance case, preferably as a mutation in `examples/<case>/mutations/` (data any reimplementation can replay). Rules an organization owns belong in its Policy command instead (`examples/policy/`).
- **Workflows.** They must pass `actionlint`, and every action is pinned by commit SHA.
- **What CI runs.** A pull request and a push to `main` run the `ci` workflow's `checks` and `test` jobs on Linux (the suite on Python 3.11, the wheel on 3.11 and 3.14, and the zipapp), and `aidd-tests` runs the suite on 3.14 for every pull request. The full matrix, Linux, macOS, and Windows on Python 3.11 to 3.15, runs weekly and by hand (`workflow_dispatch`), and a release requires it, so a change that touches paths, subprocesses, or line endings is worth a manual run before it merges. CodeQL and Scorecard run weekly while the repository is public. Every checkout has LF line endings (`.gitattributes`).
- **The schema validator and globs.** They are held to independent references (`tests/test_schema_suite.py`): keep them green, and vendor more suite files when you support a new keyword.
- **Commits by agents.** They carry `Assisted-by: <harness>/<model>`.
- **Two spellings, on purpose.** `AIDD` in capitals is the method (the AIDD loop, an AIDD Spec); `aidd` in lowercase is the software (the CLI, the plugins, the skill, `aidd/gate`), even at the start of a sentence. The expansion is written `AI-Driven Development`.

## Extend aidd

The repository is built to grow: the core plugin at the root, more plugins under `plugins/`, and the team's know-how as data and as skill folders. [plugins/README.md](plugins/README.md) is the map: where each kind of contribution lives, what it must carry, and the check that keeps it honest.

| To add | Change | Proof |
| --- | --- | --- |
| A domain pack | a `domains` entry in `schemas/roles.json`, then `aidd gen-docs` | `aidd eval standards`; `tests/test_team.py` |
| A practice skill | `plugins/aidd-team/skills/<name>/SKILL.md` with `metadata.checked`, listed in a role's `practices` | the same |
| A role or an extension | `schemas/roles.json`, then `aidd gen-docs` (a new role also gets an agent file and a role eval) | `aidd eval roles`; `tests/test_team.py` |
| A plugin | `plugins/<name>/` with `.claude-plugin/plugin.json`, listed in `.claude-plugin/marketplace.json` | `claude plugin validate plugins/<name>` (CI runs it for every plugin) |
| A gate rule | an RFC, then `src/aidd/gates.py`, `src/aidd/rulebook.py`, and cases in `examples/` | `aidd eval examples` |

## Extending the CLI

A Python package extends the `aidd` command without a fork, through entry points in its own `pyproject.toml` (aidd reads them with the standard library's `importlib.metadata`, so nothing new is installed):

```toml
[project.entry-points."aidd.commands"]
cost-report = "acme_aidd.cli:register"        # register(subparsers): add_parser(...), set_defaults(func=run); run(args) -> exit code

[project.entry-points."aidd.exporters"]
parquet = "acme_aidd.export:to_parquet"      # export(kind, items) -> str | bytes, for `aidd export events DIR --format parquet`

[project.entry-points."aidd.renderers"]
slack = "acme_aidd.render:slack"             # render(summary) -> str, for `aidd metrics events.jsonl --render slack`

[project.entry-points."aidd.packs"]
payments = "acme_aidd.packs:payments"        # pack() -> the directory of a domain-pack skill holding SKILL.md
```

The rules an extension lives by:

- **It never reaches the gate.** `gate`, `test`, `validate`, `hash`, `approve`, `ship`, `hook`, `mcp`, `change`, and `next` never discover extensions: `aidd` seals discovery before it builds their parser, so no extension module is imported in their process (`src/aidd/ext.py`, `tests/test_extensions.py`, which installs a plugin that tries to rewrite the verifier and checks the gate's output and record stay byte-identical).
- **It adds, never replaces.** A command named like a built-in one is ignored; one that fails to import or register is skipped with a warning.
- **Its output is not evidence.** A renderer or an exporter formats what aidd computed; nothing an extension prints is read back by the gate.
- **Discovery is deterministic**: entry points are sorted by name, and the first of two with one name wins.

## Change the method

Changes to routes, profiles, gate rules, schemas, or the loop need an RFC.

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-name.md` and open a PR with only the RFC. RFCs live under `docs/` and not at the root because nothing in the code reads them; `specs/` is at the root because the gate does.
2. Discussion stays open for at least 7 days, or 14 for anything that loosens a gate rule.
3. The maintainers accept or decline in the PR. An accepted RFC is implemented in its own PR, with a Spec.

## Versioning

This section owns the versioning policy; other documents link here.

- **Patch.** Clarifications and bug fixes that no conforming repo can observe.
- **Minor.** New optional fields, rules that only add information, and new modules.
- **Major.** Any change that can turn a passing change into a failing one, or the reverse, under an unchanged config.

A gate may be tightened in a minor release only behind a new profile or an opt-in `[gates]` key.

**Deprecation.** A config key, rule name, or CLI flag being replaced keeps working for at least one minor release, with a warning naming the replacement; the changelog lists it under Deprecated before the next major removes it.

**Cadence.** None fixed: a release ships when the changelog earns it; a security fix ships as a patch as soon as it is ready ([GOVERNANCE.md](GOVERNANCE.md)).

## Release

Maintainers follow [RELEASING.md](RELEASING.md).

## Security

A way to merge without the gate's evidence or approvals is a security bug. Report it privately, as [SECURITY.md](SECURITY.md) describes.
