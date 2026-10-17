# Plugins, skills, and packs: how to extend aidd

This repository is a Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) and the home of everything a plugin or a skill needs. This page is the map for a contribution: where each kind of thing lives, what it must carry, and the check that proves it.

## Layout

| Path | What it is | Listed in |
| --- | --- | --- |
| `./` (the repository root) | The core plugin, `aidd`: the skill at `.agents/skills/aidd/`, the hook in `hooks/`, the MCP server, and the gate in `src/aidd/` they run | `marketplace.json` as `source: "./"` |
| `plugins/aidd-team/` | The delivery team plugin: <!-- aidd:gen count:roles -->17<!-- aidd:end --> agent roles, <!-- aidd:gen count:commands -->19<!-- aidd:end --> commands, <!-- aidd:gen count:packs -->22<!-- aidd:end --> domain packs, and <!-- aidd:gen count:practices -->32<!-- aidd:end --> practice skills | `marketplace.json` as `source: "./plugins/aidd-team"` |
| `plugins/aidd-mods/` | Optional and experimental: `/aidd status|approve|ship|update|install` answered in Claude Code with no model turn, and a side pane that shows what the `aidd` CLI prints. A mod in TypeScript, with its tests beside it (`claude plugin test plugins/aidd-mods`) | `marketplace.json` as `source: "./plugins/aidd-mods"` |
| `plugins/<name>/` | Any further plugin | `marketplace.json`, one entry per plugin |
| `schemas/roles.json` | The team registry: roles, the loop contract, handoffs, flows, domains (packs), extensions, and each role's practice skills | rendered by `aidd gen-docs` |
| `plugins/aidd-team/skills/<slug>/` | A domain pack, generated from the registry; never edited by hand | `domains` in the registry |
| `plugins/aidd-team/skills/<name>/` | A practice skill, hand-written | a role's `practices` in the registry |
| `standards/<group>/<topic>.md` | A library standard: one opinionated choice that fills an open choice | `aidd standard list`, [STANDARDS.md](../docs/STANDARDS.md) |
| `stacks/<name>.yaml` | A stack: library standards that go together | `aidd stack list`, [STANDARDS.md](../docs/STANDARDS.md) |

**Why the core plugin is the root and not `plugins/aidd/`.** A plugin's root must contain everything it runs, and the marketplace validator rejects a source path that climbs out of the plugin with `..`. The core plugin's `plugin.json` points at `.agents/skills/aidd/`, and its hook and MCP server run `python3 -m aidd` from `${CLAUDE_PLUGIN_ROOT}/src`. Moving the core under `plugins/` would mean a second copy of the skill and the gate, and two copies drift. So the root is the plugin, and `plugins/` holds the additional ones.

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
3. Body, in the practice template (`aidd eval packs` checks it):
   - `**Use it when**` and `**Do not use when**`, before the first section
   - `## Standards`: only the generated block `<!-- aidd:gen practice:<name> -->`; the standards are ids in `schemas/roles.json` `practices.<name>.standards`
   - the loop steps it works in, in loop order and titled by the step: `## Plan`, `## Specify`, `## Implement`, `## Verify`, `## Review`, `## Ship`, `## Learn`
   - `## Test commands`: a table `| Command | Proves | How |` of the tests it owns. Each test has a name unique across every pack and practice skill, and pinned tool versions. A test another skill owns is a line `- From \`aidd-team:<owner>\`: <name>.`
   - `## Stop if` and `## Hand off` (what the four-line note carries)

   At most 1,500 estimated tokens (four characters a token) and three files in `references/`, each at most 1,500. Name the domain pack it works with as `aidd-team:<slug>`; the prefix is stripped when `aidd init --team` installs it as a project skill.
4. List it in each role that does that work (`practices` in `schemas/roles.json`), and give it a `practices` entry with its standards. Run `aidd gen-docs`, which renders its Standards table, the agent files, and the tables.
5. Proof: `python3 -m unittest tests.test_team`, `aidd eval standards` (every standard and `metadata.checked`), and `aidd eval packs`.

Conventions:

- no model or vendor names
- no link outside this repository unless it is an authoritative source
- nothing a role could read as permission to skip the gate or widen its write area

A practice skill is a playbook, never a rule; the rules live in the aidd skill and the gate.

## Add a domain pack

A pack is data in `schemas/roles.json`, rendered in the pack template (`aidd eval packs` checks it):

1. Add a `domains` entry with `name`, `slug`, `signal` (when the change touches it), `triggers`, and `scope` (`not_when` and the `neighbours`; the Scope is 60 words at most).
2. Add at most ten `standards`, as ids in the `standards` object (each with its edition, source, date, and evidence); an edition's history goes in `notes`. A regulated or platform pack adds its dated `obligations`.
3. Add one to four `checklist` rows per loop step you use. Each row cites the standards it applies (`cites`), and every standard is cited by a row or a test. List the product defaults the domain builds in `defaults` (one generated row), never as rows.
4. Add at most eight `tests`, each with `name` (unique across every pack and practice skill), `proves`, `how` (tool versions pinned), and `cites`. A test another skill owns goes in `tests_elsewhere`, and a topic another skill owns in `owned_elsewhere`.
5. At most two `references`, decision guides of 1,500 estimated tokens each at most. The SKILL.md stays under 2,000.
6. Run `aidd gen-docs`; it writes `plugins/aidd-team/skills/<slug>/SKILL.md`.

Proof: `aidd gen-docs --check`, `aidd eval standards`, `aidd eval packs`, and `tests/test_team.py`.

## Add a library standard or a stack

A library standard is one opinionated choice, such as Ruff for Python. It fills an open choice that a pack or a practice skill declares, and it never restates the pack's rule. Add one only when two projects use it. A new standard or stack is a Spec, not an RFC: it never changes the loop, the routes, or the gate rules.

1. Find the open choice in `aidd standard list`. If no pack declares it, add it first to the pack's or skill's `open_choices` in `schemas/roles.json`, with aidd's default and the options. The method (routes, approvals, the gate, commit format, `Assisted-by:`) is never an open choice.
2. Copy this template to `standards/<group>/<topic>.md`. Read the tool's version at its release feed on the day you write it, never from memory:

   ```markdown
   ---
   id: "<group>/<topic>"
   type: opinionated
   fills: ["<pack or skill>:<choice>"]
   implements: "<pack or skill>:<the rule it puts to work>"
   roles: [developer, reviewer]
   when_changed: ["<glob>"]
   why: "<one or two sentences: why this option>"
   reviewed: "YYYY-MM-DD"
   owner: "@<person or team>"
   maturity: established
   tool: {name: "<tool>", registry: pypi, package: "<name in the feed>"}
   version_policy: current_stable
   checked_version: "<the newest release, read at the feed>"
   checked: "YYYY-MM-DD"
   pin: "<the version the commands run>"
   alternatives: ["<another valid option>"]
   status: active
   enforced_by: [{name: "<suffix>", command: ["<tool>", "<args>"]}]
   ---

   # <What the team uses, in one line>

   It answers the <choice> choice of `aidd-team:<pack or skill>`.

   ## What the team does

   - <how to set it up and use it, one instruction a line>

   ## What the gate runs

   <the `tests` entries, and what fails the change>
   ```

   The body has 300 words at most. [STANDARDS.md](../docs/STANDARDS.md#the-format) lists every field.
3. A stack is `stacks/<name>.yaml`: a `name`, a `description`, the `standards` ids, a `reviewed` date, an `owner`, and its `project.stack` entries. It may `extends` one other stack, one level deep.
4. Run `aidd gen-docs`, which updates [STANDARDS.md](../docs/STANDARDS.md).

Proof: `aidd eval standards` and `tests/test_standards.py`. Their generic checks run over every library file, so a new entry needs no new test code. They check the schema, that `fills` names a declared open choice, and one standard per choice and ecosystem. They also check that a stack holds active library ids, that one standard owns each tool, the size cap, no sentence copied from a pack, renames, and deprecation.

## Add a role or an extension

Both are data in `schemas/roles.json`, validated by `schemas/roles.schema.json`.

- **An extension** is a row in a role's `extends`. It is a starting point a team verifies, pins, and installs through a change, and it never widens a role's write area.
  - **Fields:** `name`, `kind` (`skill`, `plugin`, `mcp`, `tool`, `harness`), `tier`, `source` (https), `adds`, `capabilities`, `license` (with a `license_note` for a term a team must know first), `pin`, and `checked`. The `pin` is a tag resolved to its commit, or `vendor-hosted <URL>` for a server only its vendor runs. A tool, a plugin, or a skill without a license or a pin fails `aidd eval standards`.
  - **`tier`** says who made it: `official` only when the harness vendor did. An entry its official directory lists keeps its maker's tier and records `listed_in`.
  - **`capabilities`** lists what the extension itself can touch, read from its own source: `network`, `writes_repo`, `runs_commands`, `reads_secrets`, and `telemetry` (with `telemetry_opt_out`), or nothing when it only guides the agent or only reads. When the source does not settle one, list it. A team sees it before installing, and the security review of the installing change (a protected path, so major) looks hardest at the first three.
- **A role** needs three things:
  - data: its `steps`, `lanes`, `starts_when`, `done_when`, `reads` (the artifacts in `loop.artifacts` it acts on), `writes`, `standards`, `extends`, `practices`, and `preload` (at most two it loads on most runs). It also needs a place in `order`, in `loop.handoffs` (each naming its `artifact`), and in the `flows` of the commands it runs in.
  - files: an agent file `plugins/aidd-team/agents/<role>.md` with a `<!-- aidd:gen role:<role> -->` block, a playbook, a Definition of Done, and stop rules
  - proof: a role eval in `evals/roles/` with a seeded defect

  A new role changes the loop, so it goes through an RFC ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## Domain experts

A role never stands in for a domain expert. The product manager interviews one before planning a change whose outcome rests on specialist knowledge, and quotes them, attributed, in the Spec's `## Intent`. The expert is a person in a named specialist pool, and a risk rule names the same pool. So the humans who explained the domain also approve the major change that touches it:

```yaml
owners:
  specialists:
    clinical: ["@org/clinical-safety"]

risk_rules:
  - name: clinical
    paths: ["src/triage/**", "src/dosing/**"]
    route: major
    specialists: [clinical]
```

Without such a pool, the product manager asks the author who the expert is and stops.

## Add a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` (`name`, `version`, `description`, `license`), and the `agents/`, `commands/`, `skills/`, or `hooks/` it needs. Paths inside the manifest stay inside the plugin.
2. Add an entry to `.claude-plugin/marketplace.json` with `source: "./plugins/<name>"` and the same version.
3. Give the entry a `relevance` block (a file the plugin's work reads, a command it runs). Then Claude Code can suggest the plugin to a teammate who needs it.
4. Proof: `claude plugin validate --strict plugins/<name>`; CI runs it for every folder under `plugins/`.
5. An eval suite in `plugins/<name>/evals/`, in Claude Code's case format. It has at least one case where the plugin must change what the agent does, and one where it must stay out of the way. `claude plugin eval . --eval-dir plugins/<name>/evals` scores it against a no-plugin baseline (from the repository root, so a case can load the aidd plugin beside yours). The scheduled evals run it. See `evals/plugin/` for the aidd plugin's suite.
6. A plugin that needs the gate calls the `aidd` CLI or MCP tools; it never copies `src/aidd/`.

A plugin that the team's roles should know about is also an extension row (above), so the agent files name it. Bump the plugin's `version` in both manifests on every release: Claude Code updates an installed plugin only when it changes.

## Add a gate rule

A gate rule changes what may merge, so it starts as an RFC. Then:

1. A function in the module of `src/aidd/gate/rules/` its concern belongs to, added to `GATES` in `src/aidd/gate/rules/__init__.py`.
2. A row in `src/aidd/gate/rulebook.py`.
3. A passing and a failing case in `examples/`; a mutation under `examples/<case>/mutations/` is best, because any reimplementation can replay it.

Proof: `aidd eval examples` and `tests/test_gate_rules.py`.

## What keeps it honest

- `schemas/*.json` are the source of truth; every table and every pack is generated, and `aidd gen-docs --check` fails in CI when one is stale.
- Every standard, extension, and practice skill carries a `checked` date (a standard with the source and evidence read; an unversioned practice a `reviewed` date instead). `aidd eval standards` fails on these:
  - one past its review cadence: emerging entries every 90 days, established ones every year, or the entry's own `review_every_days` or `review_due`
  - a checked standard without its evidence
  - a tool, plugin, or skill without a license and a pin

  The agile coach re-checks them at every retrospective.
- Front matter is strict YAML with quoted values (a test reads every `.md`), so GitHub renders it and every harness parses it.
- The core skill links nowhere outside its folder, and agents never approve or merge. A change to `.claude/**`, `.mcp.json`, `AGENTS.md`, or the hooks is a protected path: major, and reviewed by the security pool.
- Every change to this repository goes through its own gate: a PR with an `aidd` block, and `aidd/gate` green.

## Wanted

Contributions that would help most, in order:

1. Role evals with new seeded defects.
2. A second implementation of the gate that passes `aidd eval examples`.
3. Extensions for coding agents other than Claude Code.
4. Domain packs for domains the registry lacks, and practice skills for kinds of work with none yet. Check the lists in [TEAM-REFERENCE](../docs/TEAM-REFERENCE.md) first.
