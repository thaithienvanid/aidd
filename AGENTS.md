# Agents

<!-- aidd -->
## Change control

This repository uses aidd on itself. Before you plan, implement, or ship any change, load the skill at `.agents/skills/aidd/SKILL.md` and follow `.agents/skills/aidd/references/loop.md`. The `aidd/gate` status decides whether a change may merge. Agents never approve, merge, or edit the tests after the Spec is approved. Mark every commit you author with `Assisted-by: <harness>/<model>`.

## Working on this repository

- Run the tests with `python3 -m unittest discover -s tests`, and any command without installing as `PYTHONPATH=src python3 -m aidd <command>`.
- `schemas/*.json` are the source of truth. After changing them, run `aidd gen-docs`; never hand-edit a generated block.
- Every new gate rule needs a row in `src/aidd/rulebook.py` and a passing and a failing case in `examples/`, each pinning its finding code; `tests/test_conformance_coverage.py` fails when a level the rulebook declares has no case.
- `schemas/roles.json` defines the team: roles, the loop contract, handoffs, flows, and the domain packs. Every standard in it carries a `checked` date (or `reviewed`, for a practice with no versioned source); `aidd eval standards` must pass, and a changed edition is a change to that file, never to a generated agent file or pack.
- Keep `.agents/skills/aidd/` self-contained: no links outside the folder.
- Changes to routes, profiles, gate rules, schemas, or the loop need an RFC (`CONTRIBUTING.md`).

## Verifying your work

Before you report anything done, run these and paste their output. If one fails, fix the code, not the test: never skip, weaken, or delete a failing test.

1. `python3 -m unittest discover -s tests`
2. `uvx ruff check src tests`, `uvx ruff format --check src tests`, and `uvx mypy`
3. `PYTHONPATH=src python3 -m aidd gen-docs --check` and `PYTHONPATH=src python3 -m aidd eval examples`
4. For a change with a Spec, `PYTHONPATH=src python3 -m aidd test --spec specs/<ID>.md` and then the local gate, `PYTHONPATH=src python3 -m aidd gate --spec specs/<ID>.md` (only approvals may still be pending).
