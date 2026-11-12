# Plugins, skills, and packs: how to extend aidd

This repository is a Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) and the home of everything a plugin or a skill needs. This page is the map for a contribution: where each kind of thing lives, what it must carry, and the check that proves it.

## Layout

| Path | What it is | Listed in |
| --- | --- | --- |
| `./` (the repository root) | The core plugin, `aidd`: the skill at `.agents/skills/aidd/`, and the MCP server in `src/aidd/` | `marketplace.json` as `source: "./"` |
| `plugins/aidd-team/` | The development team plugin: <!-- aidd:gen count:roles -->12<!-- aidd:end --> agent roles, <!-- aidd:gen count:commands -->13<!-- aidd:end --> commands, and <!-- aidd:gen count:practices -->37<!-- aidd:end --> practice skills | `marketplace.json` as `source: "./plugins/aidd-team"` |
| `plugins/aidd-packs/` | Optional: the <!-- aidd:gen count:packs -->27<!-- aidd:end --> domain packs, one skill each. A plugin of its own, because no Claude Code setting keeps a skill both loadable by a model and out of the skill listing, whose budget is 1% of the model's window and shared by every skill; a role loads a pack by name | `marketplace.json` as `source: "./plugins/aidd-packs"`, which needs `aidd-team` |
| `plugins/aidd-cli/` | Optional: `bin/aidd`, the `aidd` command on the PATH of Claude Code's Bash tool. It is links to `scripts/aidd`, the source, and the data, which Claude Code copies into its cache. It is not the core plugin, because claude.ai and Cowork refuse a plugin with a `bin/` folder | `marketplace.json` as `source: "./plugins/aidd-cli"` |
| `plugins/<name>/` | Any further plugin | `marketplace.json`, one entry per plugin |
| `schemas/roles.json` | The team registry: roles, the loop contract, handoffs, flows, domains (packs, in `schemas/packs.json`), the industry standards (in `schemas/industry-standards.json`), extensions, and each role's practice skills | rendered by `aidd gen-docs` |
| `plugins/aidd-packs/skills/<slug>/` | A domain pack, generated from the registry; never edited by hand | `domains` in the registry |
| `plugins/aidd-team/skills/<name>/` | A practice skill, hand-written | a role's `skills` in the registry |
| `standards/<group>/<topic>.md` | A library standard: one opinionated choice that fills an open choice | `aidd standard`, [STANDARDS.md](../docs/STANDARDS.md) |
| `stacks/<name>.yaml` | A stack: library standards that go together | `aidd standard`, [STANDARDS.md](../docs/STANDARDS.md) |

**Why the core plugin is the root and not `plugins/aidd/`.** A plugin's root must contain everything it runs, and the marketplace validator rejects a source path that climbs out of the plugin with `..`. The core plugin's `plugin.json` points at `.agents/skills/aidd/`, and its MCP server runs `python3 -m aidd` from `${CLAUDE_PLUGIN_ROOT}/src`. Moving the core under `plugins/` would mean a second copy of the skill and the CLI, and two copies drift. So the root is the plugin, and `plugins/` holds the additional ones.

## The `aidd` command in other coding agents

Only Claude Code has a documented plugin folder that puts a plugin's executable on the agent's PATH (`bin/`), so only `aidd-cli` ships. We read each other harness's plugin documentation on 2026-11-04 and found no such mechanism, so aidd ships no package for it. A package ships only where the documentation says it works, and it reuses `scripts/aidd`, never a second copy of the source.

| Harness | What its documentation says | Read at |
| --- | --- | --- |
| Codex | A plugin bundles skills, MCP servers, apps, and hooks. It says nothing about an executable on the PATH, and nothing about links. | developers.openai.com/codex/plugins/build |
| OpenCode | A plugin is a JavaScript or TypeScript file, or an npm package. A `shell.env` hook sets environment variables for shell commands, and the page does not name PATH. | opencode.ai/docs/plugins |
| Google Antigravity | A plugin's helper programs go in `scripts/`. It names no `bin/` folder and no PATH, and says nothing about links. | antigravity.google/docs/build-plugins |
| Grok Build | It reads Claude Code plugins. Its page names no `bin/` folder, no PATH, and no manifest. | docs.x.ai/build/features/skills-plugins-marketplaces |

In these four harnesses the agent runs the `aidd` you installed, with uv, pipx, or `install.sh`, from your PATH. Add a package when a harness's documentation names a way to put a command on the agent's PATH.

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
   - `## Standards`: only the generated block `<!-- aidd:gen practice:<name> -->`; the standards are ids in `schemas/roles.json` `skills.<name>.standards`
   - the loop steps it works in, in loop order and titled by the step: `## Plan`, `## Specify`, `## Implement`, `## Verify`, `## Review`, `## Roll out`, `## Learn`
   - `## Test commands`: a table `| Command | Proves | How |` of the tests it owns. Each test has a name unique across every pack and practice skill, and pinned tool versions. A test another skill owns is a line `- From \`aidd-team:<owner>\`: <name>.`
   - `## Stop if` and `## Hand off` (what the handoff note carries)

   At most 1,500 estimated tokens (four characters a token) and three files in `references/`, each at most 1,500. Name the domain pack it works with as `aidd-packs:<slug>`; the prefix is stripped when `aidd init --aidd-team` installs it as a project skill.
4. List it in each role that does that work (`skills` in `schemas/roles.json`), and give it a `skills` entry with its standards. Run `aidd gen-docs`, which renders its Standards table, the agent files, and the tables.
5. Proof: `python3 -m unittest tests.test_team`, `aidd eval standards` (every standard and `metadata.checked`), and `aidd eval packs`.

Conventions:

- no model or vendor names
- worked examples that teach judgment, not a domain. Put criteria first, then contrast pairs: a weak version, a strong one, and the line that tells them apart. Use placeholders such as `<handler>` in place of a product or a stack, in a reference the skill loads only when needed
- no link outside this repository unless it is an authoritative source
- nothing a role could read as permission to skip an `ask` or widen its write area

A practice skill is a playbook, never a rule; the rules live in the aidd skill and the risk rules.

## Add a domain pack

A pack is data in `schemas/packs.json`, rendered in the pack template (`aidd eval packs` checks it):

1. Add a `domains` entry with `name`, `slug`, `signal` (when the change touches it), `triggers`, and `scope` (`not_when` and the `neighbours`; the Scope is 60 words at most).
2. Add at most ten `standards`, as ids in the `standards` object (each with its edition, source, date, and citation); an edition's history goes in `notes`. A regulated or platform pack adds its dated `obligations`.
3. Add one to four `checklist` rows per loop step you use. Each row cites the standards it applies (`cites`), and every standard is cited by a row or a test. List the product defaults the domain builds in `defaults` (one generated row), never as rows.
4. Add at most eight `tests`, each with `name` (unique across every pack and practice skill), `proves`, `how` (tool versions pinned), and `cites`. A test another skill owns goes in `tests_elsewhere`, and a topic another skill owns in `owned_elsewhere`.
5. At most two `references`, decision guides of 1,500 estimated tokens each at most. The SKILL.md stays under 2,000.
6. Run `aidd gen-docs`; it writes `plugins/aidd-packs/skills/<slug>/SKILL.md`.

Proof: `aidd gen-docs --check`, `aidd eval standards`, `aidd eval packs`, and `tests/test_team.py`.

## Add a library standard or a stack

A library standard is one opinionated choice, such as Ruff for Python. It fills an open choice that a pack or a practice skill declares, and it never restates the pack's rule. Add one only when two projects use it. A new standard or stack is a Spec, not an RFC: it never changes the loop, the routes, or the risk rules.

1. Find the open choice in `aidd standard`. If no pack declares it, add it first to the pack's or skill's `open_choices` in `schemas/roles.json`, with aidd's default and the options. The method (routes, approvals, the risk rules, commit format, `Assisted-by:`) is never an open choice.
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
   owner: "@<person or team>"
   maturity: established
   tool: {name: "<tool>", registry: pypi, package: "<name in the feed>"}
   version_policy: current_stable
   checked_version: "<the newest release, read at the feed>"
   checked: "YYYY-MM-DD"
   checked_by: "agent:<harness>/<model>"
   citation:
     url: "<the page the version was read at>"
     quote: "<the sentence read there>"
   pin: "<the version the commands run>"
   alternatives: ["<another valid option>"]
   status: active
   enforced_by: [{name: "<suffix>", command: ["<tool>", "<args>"]}]
   ---

   # <What the team uses, in one line>

   It answers the <choice> choice of `aidd-team:<pack or skill>`.

   ## What the team does

   - <how to set it up and use it, one instruction a line>

   ## What the tests run

   <the `tests` entries, and what fails the change>
   ```

   The body has 300 words at most. [STANDARDS.md](../docs/STANDARDS.md#the-format) lists every field.
3. A stack is `stacks/<name>.yaml`: a `name`, a `description`, the `standards` ids, a `checked` date and the `checked_by` agent, an `owner`, and its `project.stack` entries. It may `extends` one other stack, one level deep.
4. Run `aidd gen-docs`, which updates [STANDARDS.md](../docs/STANDARDS.md).

Proof: `aidd eval standards` and `tests/test_standards.py`. Their generic checks run over every library file, so a new entry needs no new test code. They check the schema, that `fills` names a declared open choice, and one standard per choice and ecosystem. They also check that a stack holds active library ids, that one standard owns each tool, the size cap, no sentence copied from a pack, renames, and deprecation.

## Add a role or an extension

Both are data in `schemas/roles.json`, validated by `schemas/roles.schema.json`.

- **An extension** is a row in a role's `extensions`. It is a starting point a team verifies, pins, and installs through a change, and it never widens a role's write area.
  - **Fields:** `name`, `type` (`skill`, `plugin`, `mcp`, `tool`, `harness`), `publisher`, `source` (https), `adds`, `access`, `license` (with a `license_note` for a term a team must know first), `pin`, and `checked`. The `pin` is a tag resolved to its commit, or `vendor-hosted <URL>` for a server only its vendor runs. A tool, a plugin, or a skill without a license or a pin fails `aidd eval standards`.
  - **`publisher`** says who made it: `official` only when the harness vendor did. An entry its official directory lists keeps its maker as publisher and records `listed_in`.
  - **`access`** lists what the extension itself can touch, read from its own source: `network`, `writes_repo`, `runs_commands`, `reads_secrets`, and `telemetry` (with `telemetry_opt_out`), or nothing when it only guides the agent or only reads. When the source does not settle one, list it. A team sees it before installing, and the security review of the installing change looks hardest at the first three.
- **A role** needs three things:
  - data: its `steps`, `routes`, `starts_when`, `done_when`, `reads` (the artifacts in `graph.artifacts` it acts on), `writes`, `standards`, `extensions`, `skills`, and `preload`. `preload` lists `aidd` first for a role that writes a Spec or tests and needs the rulebook on every run (the verifier loads it by name), then at most two other skills it loads on most runs. It also needs a place in `order`, in `graph.handoffs` (each naming its `artifact`), and in the `flows` of the commands it runs in.
  - files: an agent file `plugins/aidd-team/agents/<role>.md` with a `<!-- aidd:gen role:<role> -->` block, a playbook, a Definition of Done, and stop rules
  - proof: a role eval in `evals/roles/` with a seeded defect

  A new role changes the loop, so it goes through an RFC ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## Domain experts

A role never stands in for a domain expert. The product manager interviews one before planning a change whose outcome rests on specialist knowledge, and quotes them, attributed, in the Spec's `## Request`. The expert is a person in a named specialist pool, and an area marks the code they know. An edit there makes the change major and asks first, so the humans who explained the domain also review the change that touches it:

```yaml
owners:
  specialists:
    clinical: ["@org/clinical-safety"]

risks:
  areas:
    clinical: {paths: ["src/triage/**", "src/dosing/**"], route: major}
  rules:
    - {action: code.edit, area: clinical, level: ask}
```

Without such a pool, the product manager asks the author who the expert is and stops.

## Add a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` (`name`, `version`, `description`, `license`), and the `agents/`, `commands/`, `skills/`, or `hooks/` it needs. Paths inside the manifest stay inside the plugin.
2. Add an entry to `.claude-plugin/marketplace.json` with `source: "./plugins/<name>"` and the same version.
3. Give the entry a `relevance` block (a file the plugin's work reads, a command it runs). Then Claude Code can suggest the plugin to a teammate who needs it.
4. Proof: `claude plugin validate --strict plugins/<name>`; CI runs it for every folder under `plugins/`.
5. An eval suite in `evals/<name>/`, in Claude Code's case format. It sits outside the plugin's folder, so an install never carries it, and each case names the plugins it loads by their paths from its folder, as `evals/team/` does. It has at least one case where the plugin must change what the agent does, and one where it must stay out of the way. `claude plugin eval . --eval-dir evals/<name>` scores it against a no-plugin baseline (from the repository root, so a case can load the aidd plugin beside yours). A manual run of the evals workflow runs it. See `evals/plugin/` for the aidd plugin's suite.
6. A plugin that needs aidd calls the `aidd` CLI or MCP tools; it never copies `src/aidd/`.

A plugin that the team's roles should know about is also an extension row (above), so the agent files name it. Bump the plugin's `version` in both manifests on every release: Claude Code updates an installed plugin only when it changes.

## Add a built-in risk rule

A built-in risk rule changes what every agent asks before it acts, so it starts as an RFC. Then:

1. Add an action (with its `description`, `commands`, and `examples`), an area (with its `paths` and `route`), or a rule to `schemas/risks.json`.

Proof: `aidd risk --list` shows the rule and where it came from, and `aidd eval routing` checks the routes.

## What keeps it honest

- `schemas/*.json` are the source of truth; every table and every pack is generated, and `aidd gen-docs --check` fails in CI when one is stale.
- Every standard, extension, and practice skill carries a `checked` date (an edition with the source and citation read; an unversioned practice with no citation). `aidd eval standards` fails on these:
  - one past its review cadence: emerging entries every 90 days, established ones every year, or the entry's own `review_every_days` or `review_due`
  - an edition without its citation
  - a tool, plugin, or skill without a license and a pin

  The SRE re-checks them at every retrospective.
- Front matter is strict YAML with quoted values (a test reads every `.md`), so GitHub renders it and every harness parses it.
- The core skill links nowhere outside its folder, and agents never approve or merge. A change to `.claude/**`, `.mcp.json`, or `AGENTS.md` changes what agents may do, so a person who reviews security reads it.
- Every change to this repository runs its own loop: the risk rules, `aidd test` green on the head, and a person's Merge approval.

## Wanted

Contributions that would help most, in order:

1. Role evals with new seeded defects.
2. Built-in risk rules for actions the list lacks, each with its commands and examples.
3. Extensions for coding agents other than Claude Code.
4. Domain packs for domains the registry lacks, and practice skills for kinds of work with none yet. Check the lists in [TEAM-REFERENCE](../docs/TEAM-REFERENCE.md) first.
