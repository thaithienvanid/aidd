# Plugins, skills, and packs: how to extend aidd

This repository is a Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) and the home of everything a plugin or a skill needs. This page is the map for a contribution: where each kind of thing lives, what it must carry, and the check that proves it.

## Layout

| Path | What it is | Listed in |
| --- | --- | --- |
| `./` (the repository root) | The core plugin, `aidd`: the skill at `.agents/skills/aidd/`, the hook in `hooks/`, the MCP server, and the verifier in `src/aidd/` they run | `marketplace.json` as `source: "./"` |
| `plugins/aidd-team/` | The delivery team plugin: <!-- aidd:gen count:roles -->15<!-- aidd:end --> agent roles, <!-- aidd:gen count:commands -->12<!-- aidd:end --> commands, <!-- aidd:gen count:packs -->14<!-- aidd:end --> domain packs, and <!-- aidd:gen count:practices -->23<!-- aidd:end --> practice skills | `marketplace.json` as `source: "./plugins/aidd-team"` |
| `plugins/<name>/` | Any further plugin | `marketplace.json`, one entry per plugin |
| `schemas/roles.json` | The team registry: roles, the loop contract, handoffs, flows, domains (packs), extensions, and each role's practice skills | rendered by `aidd gen-docs` |
| `plugins/aidd-team/skills/<slug>/` | A domain pack, generated from the registry; never edited by hand | `domains` in the registry |
| `plugins/aidd-team/skills/<name>/` | A practice skill, hand-written | a role's `practices` in the registry |

**Why the core plugin is the root and not `plugins/aidd/`.** A plugin's root must contain everything it runs, and the marketplace validator rejects a source path that climbs out of the plugin with `..`. The core plugin's `plugin.json` points at `.agents/skills/aidd/`, and its hook and MCP server run `python3 -m aidd` from `${CLAUDE_PLUGIN_ROOT}/src`. Moving the core under `plugins/` would mean a second copy of the skill and the verifier, and two copies drift. So the root is the plugin, and `plugins/` holds the additional ones.

## Add a practice skill

A practice skill is the how-to for one kind of work (design an API, migrate a schema, threat-model a change). It is loaded per Task, named in the Task's `skills`.

1. Create `plugins/aidd-team/skills/<name>/SKILL.md`. The name is lowercase with hyphens, and it is not a domain slug.
2. Front matter, strict YAML with the values quoted:
   ```yaml
   ---
   name: <name>
   description: "Practice skill: <what it does>. Use when <the Task it fits>: <what it covers>."
   metadata:
     checked: "YYYY-MM-DD"
   ---
   ```
   The description's first sentence is the summary the role tables show; the `Use when` sentence is what the harness matches a Task against.
3. Body, with these sections:
   - `## Standards`: the standards it applies, with editions
   - the steps per loop step it applies to: `## Specify, before Spec approval`, `## Implement`, `## Review`, `## Ship`
   - `## Test commands`: where a command can prove the practice; they go into the Spec's `[[tests.commands]]`
   - `## Hand off`: what the four-line note carries

   Name the domain pack it works with as `aidd-team:<slug>`; the prefix is stripped when `aidd init --team` installs it as a project skill.
4. List it in each role that does that work: `practices` in `schemas/roles.json`. Run `aidd gen-docs`, which renders it into the agent files and the tables.
5. Proof: `python3 -m unittest tests.test_team`, and `aidd eval standards`, which reads `metadata.checked`.

Conventions: no model or vendor names, no link outside this repository unless it is an authoritative source, and nothing a role could read as permission to skip the gate or widen its write area. A practice skill is a playbook, never a rule; the rules live in the aidd skill and the gate.

## Add a domain pack

A pack is data in `schemas/roles.json`:

1. Add a `domains` entry with `name`, `slug`, and `signal` (when the change touches it).
2. Add its `standards`, each with `name`, `edition`, `checked`, and `source`.
3. Add a `checklist` item per loop step, at least Specify and Implement.
4. Add its `tests`, each with `name`, `proves`, and `how`.
5. Run `aidd gen-docs`; it writes `plugins/aidd-team/skills/<slug>/SKILL.md`.

Proof: `aidd gen-docs --check`, `aidd eval standards`, and `tests/test_team.py`.

## Add a role or an extension

Both are data in `schemas/roles.json`, validated by `schemas/roles.schema.json`.

- **An extension** is a row in a role's `extends`. It is a starting point a team verifies, pins, and installs through a change, and it never widens a role's write area.
  - **Fields:** `name`, `kind` (`skill`, `plugin`, `mcp`, `tool`, `harness`), `tier`, `source` (https), `adds`, `capabilities`, `license` (with a `license_note` for a term a team must know first), `pin` (a tag resolved to its commit, or `vendor-hosted <URL>` for a server only its vendor runs), and `checked`. A tool, a plugin, or a skill without a license or a pin fails `aidd eval standards`.
  - **`tier`** says who made it: `official` only when the harness vendor did. An entry its official directory lists keeps its maker's tier and records `listed_in`.
  - **`capabilities`** lists what the extension itself can touch, read from its own source: `network`, `writes_repo`, `runs_commands`, `reads_secrets`, and `telemetry` (with `telemetry_opt_out`), or nothing when it only guides the agent or only reads. When the source does not settle one, list it. A team sees it before installing, and the security review of the installing change (a protected path, so major) looks hardest at the first three.
- **A role** needs three things:
  - data: its `steps`, `lanes`, `starts_when`, `done_when`, `reads` (the artifacts in `loop.artifacts` it acts on), `writes`, `standards`, `extends`, `practices`, and `preload` (at most two it loads on most runs), and a place in `order`, `loop.handoffs` (each naming its `artifact`), and the `flows` of the commands it runs in
  - files: an agent file `plugins/aidd-team/agents/<role>.md` with a `<!-- aidd:gen role:<role> -->` block, a playbook, a Definition of Done, and stop rules
  - proof: a role eval in `evals/roles/` with a seeded defect

  A new role changes the loop, so it goes through an RFC ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## Domain experts

A role never stands in for a domain expert. The product manager interviews one before planning a change whose outcome rests on specialist knowledge, and quotes them, attributed, in the Spec's `## Intent`. The expert is a person in a named specialist pool, and a risk rule names the same pool, so the people who explained the domain also approve the major change that touches it:

```toml
[owners.reviewers]
clinical = ["@org/clinical-safety"]

[[risk_rules]]
name = "clinical"
paths = ["src/triage/**", "src/dosing/**"]
route = "major"
reviewers = ["clinical"]
```

Without such a pool, the product manager asks the author who the expert is and stops.

## Add a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` (`name`, `version`, `description`, `license`), and the `agents/`, `commands/`, `skills/`, or `hooks/` it needs. Paths inside the manifest stay inside the plugin.
2. Add an entry to `.claude-plugin/marketplace.json` with `source: "./plugins/<name>"` and the same version.
3. Give the entry a `relevance` block (a file the plugin's work reads, a command it runs), so Claude Code can suggest it to a teammate who needs it.
4. Proof: `claude plugin validate --strict plugins/<name>`; CI runs it for every folder under `plugins/`.
5. An eval suite in `plugins/<name>/evals/`, in Claude Code's case format: at least one case where the plugin must change what the agent does, and one where it must stay out of the way. `claude plugin eval . --eval-dir plugins/<name>/evals` scores it against a no-plugin baseline (from the repository root, so a case can load the aidd plugin beside yours); the scheduled evals run it. See `evals/plugin/` for the aidd plugin's suite.
6. A plugin that needs the verifier calls the `aidd` CLI or MCP tools; it never copies `src/aidd/`.

A plugin that the team's roles should know about is also an extension row (above), so the agent files name it. Bump the plugin's `version` in both manifests on every release: Claude Code updates an installed plugin only when it changes.

## Add a gate rule

A gate rule changes what may merge, so it starts as an RFC. Then:

1. A function in `src/aidd/gates.py`, added to `GATES`.
2. A row in `src/aidd/rulebook.py`.
3. A passing and a failing case in `examples/`; a mutation under `examples/<case>/mutations/` is best, because any reimplementation can replay it.

Proof: `aidd eval examples` and `tests/test_gate_rules.py`.

## What keeps it honest

- `schemas/*.json` are the source of truth; every table and every pack is generated, and `aidd gen-docs --check` fails in CI when one is stale.
- Every standard, extension, and practice skill carries a `checked` date (a standard with the source and evidence read; an unversioned practice a `reviewed` date instead); `aidd eval standards` fails on one older than a year, on a checked standard without its evidence, and on a tool, plugin, or skill without a license and a pin, and the agile coach re-checks them at every retrospective.
- Front matter is strict YAML with quoted values (a test reads every `.md`), so GitHub renders it and every harness parses it.
- The core skill links nowhere outside its folder, agents never approve or merge, and a change to `.claude/**`, `.mcp.json`, `AGENTS.md`, or the hooks is a protected path: major, and reviewed by the security pool.
- Every change to this repository goes through its own gate: a PR with an `aidd` block, and `aidd/gate` green.

## Wanted

Contributions that would help most, in order:

1. Practice skills for kinds of work with none yet: performance work, data privacy reviews, mobile release, incident response, dependency upgrades.
2. Domain packs for domains the registry lacks.
3. Role evals with new seeded defects.
4. Extensions for coding agents other than Claude Code.
5. A second implementation of the verifier that passes `aidd eval examples`.
