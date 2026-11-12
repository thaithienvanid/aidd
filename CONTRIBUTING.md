# Contributing

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

This repository uses aidd on itself. Every change is a pull request that follows the loop in [METHOD.md](docs/METHOD.md): `aidd risk --paths` gives its route, a normal or major change brings a Spec, and a maintainer reviews and merges it.

Until the v1.0.0 tag, a pull request needs no Spec and no RFC, even when `aidd risk` says Spec first. Before the tag, the owner folds the whole history back into one 1.0.0 commit from time to time, a step called a re-squash, so the owner approves a plan for each batch instead. The review that [AGENTS.md](AGENTS.md#verifying-your-work) sizes to the change takes the Spec's place. Only a person creates the release tag, as [RELEASING.md](RELEASING.md) says.

## Develop

```sh
PYTHONPATH=src python3 -m aidd gen-docs         # regenerate every generated block and domain pack after changing a schema
PYTHONPATH=src python3 -m aidd validate         # the repository's aidd files: the config, the risk rules, and the work items
PYTHONPATH=src python3 -m aidd eval standards   # the team's standards registry: nothing past its review cadence
PYTHONPATH=src python3 -m aidd eval packs       # every pack and practice skill in its template and under its class size limit
```

You need no install, and `python3 tests/run.py` needs none either. On the rest of this page, `aidd <command>` means `PYTHONPATH=src python3 -m aidd <command>`, run from the repository's top.

**Before you open a pull request**, run the checks every agent runs in [AGENTS.md](AGENTS.md#verifying-your-work), and paste their output. If one fails, fix the code, not the test. `python3 tests/run.py test_strict_yaml` runs one test file. `python3 tests/run.py --changed` runs the files that read what changed and the checks of the whole repository (`WHOLE_TREE` in `tests/run.py`). A run fails when a test leaves a tracked file changed, so a test writes only to a temporary folder. A record is never rewritten, so its retired-names row has the rule `read_both`: a reader reads the old name as the new one, and `aidd upgrade` leaves the file. The viewer's behavior tests drive a real headless Chrome, which opens a window on a desktop, so locally they run only with `AIDD_BROWSER_TESTS=1`. CI runs them on Linux on every pull request.

- **Single source of truth.** Schemas, the built-in risk rules in `schemas/risks.json`, and the profiles in `schemas/profiles.json` are data. Never hand-edit a block between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`; change the source and run `aidd gen-docs`.
- **The skill stays self-contained.** Nothing under `.agents/skills/aidd/` may point outside that folder.
- **Commits by agents.** They carry `Assisted-by: <harness>/<model>`. A commit a delegate decided carries `Decided-by`, `On-behalf-of`, and `Delegation` instead of `Approved-by`.
- **Workflows.** They must pass `actionlint`, and every action is pinned by commit SHA.
- **Dependabot.** It bumps the dev tools and the actions monthly, and a person reviews and merges each pull request it opens. An actions bump also needs its pins copied into `templates/github/`, which `python3 tools/sync_pins.py` does in one command ([RELEASING.md](RELEASING.md#toolchain-pins)).
- **What CI runs.** A pull request runs the `ci` workflow's `checks` and `test` jobs on Linux. The jobs byte-compile on Python 3.11, install the wheel on 3.11, 3.14, and 3.15, run the zipapp on 3.14, and run the suite on 3.14 under coverage. `aidd-tests` runs the suite and the browser tests on 3.14 for every pull request. A push to `main` runs the `main` workflow: the suite and the browser tests on 3.15, which a pull request does not run. The `weekly` workflow runs the Linux matrix, the sdist, and the wheel. macOS and Windows run only in the manual `weekly` run, under Actions, weekly, Run workflow, as [RELEASING.md](RELEASING.md) and the header of `.github/workflows/weekly.yml` say. The table in the header of `.github/workflows/ci.yml` lists each workflow's jobs and events. A release requires that run, so a change that touches paths, subprocesses, or line endings is worth one before it merges. While the repository is public, CodeQL runs on each pull request and push to `main` and weekly, and Scorecard runs weekly. Every checkout has LF line endings, which `.gitattributes` sets.
- **The schema validator and globs.** `tests/test_schema_suite.py` holds them to independent references. Keep them green, and vendor more suite files when you support a new keyword.
- **One spelling.** `aidd` in lowercase is the name of the software and of the method it runs, meaning the CLI, the plugins, the skill, and the loop, even at the start of a sentence. The method has no second name, and no expansion.

## Code and imports

aidd is one Python package, `src/aidd/`, with no runtime dependency. It holds one package per capability, and these rules keep them apart and the tests honest. [The architecture overview](docs/architecture/README.md#module-map) lists them, says what each holds, and why.

- **Layers.** `.importlinter` lists the packages from the top, `cli`, to the bottom, `kernel`, and a package imports only from the ones below it. `docsgen` sits just above `evals`. Import Linter checks it in CI with `lint-imports`, and `tests/test_import_boundaries.py` runs the same contracts. The file has no `ignore_imports`, so you fix a new wrong-way import and never list it there.
- **Doors.** Other packages use a package only through its `__init__.py`, its door. Write `from aidd import config`, then `config.load_file(...)`, never `from aidd.config import loading`. A door is only its names, so it defines no function or class, and every body lives in a child. It names each export twice. Under `TYPE_CHECKING` it imports the child's name for mypy, as in `from aidd.config.loading import load_file as load_file`. It also lists the name in the map `aidd.kernel.doors.exports` reads at run time. It never binds the name, so importing a package loads none of its children until a caller uses one. A door name is its child's name. One that isn't unique enough at the door gets a fuller one in the child too, so a search finds both. No child module is named like an export. `tests/test_package_doors.py` checks every door, and a door contract per package in `.importlinter` checks that no other package imports a child. `kernel` has no door, so import its modules, as in `from aidd.kernel import git`.
- **No cycle inside a package.** A package's modules may import each other, but never in a circle, however far round, which `acyclic_siblings` in `.importlinter` checks. A name one child reads from another is public, so it has no leading underscore.
- **Absolute imports.** Write `from aidd.kernel import git`, never `from . import git`. A module that moves keeps its own imports, and a search for `aidd.kernel.git` finds every importer. Ruff enforces it with `TID252`.
- **Patch where the name is defined.** `mock.patch.object(module, "name")` replaces one binding, so patch the child module that defines and calls the name, never a door or a module that only re-exports it. A door reads its child on every access, so the patch reaches callers through the door too. Import modules, not names, for anything a test patches, so write `from aidd.kernel import git`, then `git.run(...)`. `tests/test_patch_targets.py` checks every patch in the suite.
- **Commands start fast.** The grammar names each command's handler, such as `"setup:cmd_init"`, and `aidd.cli.parser.Handler` imports it only when the command runs; a handler imports a heavy module inside the function that needs it. `tests/test_cli_handlers.py` checks that building the parser loads no command.
- **Small functions, held by ceilings.** `tests/test_code_shape.py` counts the functions over 60 lines, the functions over 5 parameters, the modules over 700 lines, the one-letter parameters in public functions, and the widest public signature. It also counts the functions over McCabe complexity 15, as ruff's `C901` measures it, and the highest complexity of any function. Each count has a ceiling that only goes down. A change that lowers a count lowers its ceiling too, and a person raises one only on purpose, with the reason in that change. A wide function takes a parameter object, as `aidd init`'s options do.
- **Every module imports on its own.** `tests/test_isolated_imports.py` imports each module first, in a fresh interpreter, so an import cycle cannot hide behind the order the suite imports them in.

## Control tests

A control decides whether an agent may act or a run counts as proof, such as the risk rules, the test verdict, and the delegate's check. Its tests follow these rules, in the order a test is built.

- **State the invariant.** Each control's test class docstring says its invariant as one sentence about every input, never an example.
- **Cover the edges.** Each control's table holds the empty case, one, many, the cap, and one past the cap.
- **Say when a cap decides.** A cap that changes a decision says so in the output, and a test covers the input just past it.
- **Give a limit one owner.** A number a person may want to change is a key of `limits` in `schemas/config.schema.json`, with its default, range, and direction there. A limit that guards a control keeps its default as the ceiling or the floor. A limit of the delegate or the run stays in aidd's data. Code reads the default from the schema, and a text renders it or names the setting.
- **Compare two deciders.** When two functions decide one fact, one test compares them on a generated product of inputs.
- **Read "unsure" as the stricter level.** Test each unreadable input, such as a variable, a substitution, or an unknown ref, against the strictest reading.
- **Test a precedence both ways.** A strict rule meets a loose one, and a loose rule meets a strict one.
- **Test the decision.** Assert what a reader can see or do, never only a length, a flag, or a count.
- **Justify a skip.** A test never asserts a cut, a skip, or a default as correct unless its docstring says why it is safe.
- **Table the pure function.** Each control has a unit table on its pure function. An end-to-end run proves the wiring, never the decision space.
- **Prove the relation can fail.** A relation test seeds a broken variant and shows the relation catches it, as `tests/test_route_metamorphic.py` does.
- **Generate open-ended inputs.** Build paths, command lines, branches, and Spec bodies from a small grammar, with a fixed seed and a bounded count.
- **Pin no wording.** Assert codes, levels, and fields. Check a message only for what it must name, such as an id.

## Prove a fix

A fix is proven by a test and by a run as a person would make it. These rules hold for every fix, in the order the work goes. The developer's done condition in `schemas/roles.json` asks the team's developer for the same.

- **Revert it.** Each fix has a test that fails when the fix is reverted. Run that revert before handoff, and list the result.
- **State the invariant.** Say in one sentence what the fix restores. Then `git grep` its siblings, and fix each one or say why it differs.
- **Run it as a person.** For a CLI, config, or UI change, run the real command in a scratch repository with a scratch `HOME`, and paste the output. Try it from another folder, with a typo, and as a dry run where there is one, then for real.
- **Compare old and new.** A change to how a command, a path, a config, or a status is read ships a test that compares the new answers with the old over a generated set.
- **Name the honest work.** A new control says what honest work it could block, and a test shows that work still passes.
- **Prove a check.** A new check, test helper, or script that can pass or fail is shown failing once on a fault you plant, before anyone relies on it. List the fault and the result.

## Size limits

A limit tracks a cost, and the cost is what a session holds. Three kinds of limit exist, and each says whose it is.

| Kind | Where it lives | Who changes it, and with what |
| --- | --- | --- |
| A coding agent's own limit: a skill's description, an MCP server's instructions, an instruction file | a row of `src/aidd/config/harness_sizes.py`, with the vendor's page and the date you read it | Only the vendor's page. The change carries the page's words and your date, and nothing of ours raises it. |
| A budget for text a session or a role always loads: a role's start total, `SKILL.md`, `graph.md`, a role file, doctor's bound for an instruction file | `CAPS` in `tests/budgets.py` | A maintainer, in a change of its own. |
| A limit for a class of files that load on a signal: references, templates, packs, practice skills, skill references | `tests/budgets.py` and `src/aidd/docsgen/token_caps.py` | A maintainer, in a change of its own. |

- **Write the cost beside the number.** A cap states what it bounds, who loads the text and when, and its cost: bytes, estimated tokens (four bytes a token), and the share of a 200,000-token window. `tests/test_budget_headroom.py` holds the stated tokens and share to the cap's number, so a raised number with an old cost fails.
- **Never raise a cap to pass, and never leave one as a snapshot.** A file's size on a day is not a cost. If a true sentence needs room, raise the cap by what the cost allows, and say what that costs in every session or load.
- **Never reword to fit a number.** Do not shorten a sentence, merge two, or move a fact to another file because of a size. A file near its class limit is a signal to restructure by topic. Keep a short main file, and put each detail in a reference that the step needing it loads. Name that reference in the skill's load table. Remove repetition only where the same reader always loads the other text.
- **Always-loaded text stays at or under 90% of its cap.** `tests/budgets.py` lists each file above that line with the real limit it is near and what would relieve it. A listed file that comes under the line leaves the list. A class limit has no line: `tests/run.py` notes a file above 90% of it, and a section past 1,200 tokens.

## Extend aidd

The repository is built to grow, with the core plugin at the root, more plugins under `plugins/`, and the team's know-how as data and as skill folders. [plugins/README.md](plugins/README.md) is the map. It says where each kind of contribution lives, what it must carry, and the check that keeps it honest.

| To add | Change | Proof |
| --- | --- | --- |
| A domain pack | an entry in `schemas/packs.json`, then `aidd gen-docs` | `aidd eval standards` and `aidd eval packs`; `tests/test_team.py` |
| A practice skill | `plugins/aidd-team/skills/<name>/SKILL.md` with `metadata.checked`, listed in a role's `skills` and in `skills` | the same |
| A role | `schemas/roles.json`, then `aidd gen-docs` (a new role also gets an agent file and a role eval) | `aidd eval roles`; `tests/test_team.py` |
| A library standard or a stack | `standards/<group>/<topic>.md` or `stacks/<name>.yaml`, then `aidd gen-docs` | `aidd eval standards`; `tests/test_standards.py` |
| A type of thing aidd tracks or writes: a work item, a typed document, or a document | a row in `schemas/item-types.json`, with its template in the skill's `assets/` and, for a front matter type, its schema; a schema's enum or a page's list that spells types out is a new line in `tests/test_item_types.py`; then `aidd gen-docs` | `tests/test_item_types.py` |
| A status of a work item, or a move between two | the status node of its type (`schemas/common.schema.json`, or `schemas/proposal.schema.json` for a proposal): the word, its meaning and group, each move it takes part in, and the set of statuses a reader asks about; then `aidd gen-docs` | `tests/test_status_transitions.py`, whose table lists every pair of statuses |
| A thing that can be open: a key with a date or a release, or a thing a run opens | a row in `schemas/lifecycles.json` with who opens it, what closes it, who may close it, and what finds one left open, or an entry under `never_open` with why | `tests/test_lifecycles.py` |
| A plugin | `plugins/<name>/` with `.claude-plugin/plugin.json`, listed in `.claude-plugin/marketplace.json` | `claude plugin validate plugins/<name>` (CI runs it for every plugin) |
| A built-in action, area, or risk rule | an RFC, then `schemas/risks.json`, `aidd gen-docs`, and `aidd upgrade --yes`, which writes this repository's own ask rules again | `aidd risk --list`; the `risk` package's tests |
| A coding agent | a `Harness` in `src/aidd/config/harnesses.py`, and a row in `src/aidd/config/harness_sizes.py` for each size its vendor documents, then `aidd gen-docs`; for its team files, a renderer in `src/aidd/setup/harness_files.py` and a `Voice` in `harness_text.py`; for its ask rules, its format in `src/aidd/risk/`, written from the harness's own documentation | `tests/test_harness_text.py`; a test of its ask rules |

**A change to what a role does carries its eval.** A change that means to change a role's behavior in its agent file, which carries its playbook and the loop contract, adds a scenario to `evals/roles/`. The scenario fails before the change and passes after it. Run `aidd eval roles --agent-command "<your agent>" --repeat 3 --without-aidd` before and after, and keep the change only when the lift doesn't fall. [evals/roles/README.md](evals/roles/README.md) says how to write the scenario and what the merge check reads. The suite sends a role only its agent file, so a change to a practice skill or to the aidd skill gets a reviewer's pass instead. A wording fix that changes no behavior needs no scenario.

## Keep aidd generic

aidd never knows what a person will build, so every part it ships must hold for a project nobody tuned it on. Each of four properties needs its own proof, because no one test shows them all:

- **Sound:** no advice is wrong. Tests on the controls show it, and each must be able to fail.
- **Complete:** aidd covers what any software change needs. Check a gap against a published catalog, such as ISO/IEC 25010, SWEBOK, or OWASP ASVS, never against the projects you happen to see.
- **General:** aidd works on a kind of project nobody tuned it on, and the held-out cases show it.
- **Worth it:** an agent does better with aidd than without it, as the lift that `--without-aidd` reports on `aidd eval routing`, `roles`, or `tasks` shows.

When you change the skill, the team, a pack, a standard, a template, or an eval:

1. Take examples from common domains, such as orders or invoices, never from aidd's own internals or one product, stack, or vendor. Never ban a word a domain uses.
2. Keep domain and stack knowledge in its pack or stack, so the core stays small.
3. Change the core only for a failure seen twice, in two different kinds of project, or seen once when it is severe. A failure in one kind of project goes to a pack, or to that project's own memory.
4. Write the failing case before the fix, and a twin case in another domain. Tune on the development cases, then read the held-out score to see whether the change generalized.
5. Test the rule, not one example. Renaming a project or swapping its stack must never change a route, and adding a risky path must never lower one.

**Fit the change, neither under nor over.** A change can miss in two ways, so review checks both:

- **Underfit:** a cut loses something that worked. When you fold, merge, or remove a part, move each claim, eval case, and test it held to its new owner, and say so in the commit. A claim never loses its last case, and every check keeps a test that can fail. A faster test or a smaller matrix proves it still catches what the old one caught, with a seeded fault that only the dropped part saw.
- **Overfit:** a change fits one project, one eval run, or one wording. Steps 3 to 5 guard against it: two sightings in different kinds of project, a twin case, and the held-out score.

## Update a standard

The registry of standards is `schemas/industry-standards.json`, and every pack and practice skill reads it. An agent checks every entry against its source. To update an entry, whether a new edition, a moved page, or a lesson from a postmortem:

1. **Read the source.** Open the entry's `source` and confirm the edition. Copy one full sentence from the page that shows it. The sentence has eight words or more and ends like a sentence; it is not the page title. That's the citation rule, because a `checked` date always names what was read. So set `checked` to today, and `checked_by` to `agent:<harness>/<model>`, the agent that read the source. Set `citation` to the `url` and the `quote`; the day it was read is `checked`. A practice with no versioned source has no edition, so it needs no `citation`; its `checked` date says an agent re-read the practice.
2. **Set the cadence when it differs.** Set `review_every_days` for a source that changes faster than the default, and `review_due` for an obligation on a known calendar. [The review cadence](docs/TEAM.md#keeping-the-knowledge-current) explains both.
3. **Check it.** `aidd eval standards` must pass, and `aidd eval standards --online` should report the entry `ok`. Run `aidd gen-docs` so the packs, the agent files, and the reference tables show the new edition; never edit a generated file.
4. **Take the route.** `aidd risk --paths schemas/industry-standards.json` gives it. Open a pull request with the tests, and a maintainer reviews it.

**Which laws join.** A law or a regulation joins the registry only when it changes what the software does: a screen, a data flow, a deadline, a record it keeps, or a test. Tax rates, company filings, and workplace policy stay out. The packs cover the EU, the US, and the UK. A law from another market joins when it is the first or the strictest of its kind, so others follow it. For any other market, the agent says that no pack covers its law, and the team checks it with counsel.

## Add a standard or a stack

A library standard fills one open choice of a pack or a practice skill, and a stack lists standards that go together, as [STANDARDS.md](docs/STANDARDS.md) explains. Each new one, or a change to one, is a Spec, not an RFC. It never changes the loop, the routes, or the risk rules. A new open choice in `schemas/roles.json` is a Spec too, unless it names the method; the method is never an open choice.

1. **Wait for two projects.** A choice joins the library once two projects use it. Until then, it stays in the project's own `docs/standards/`.
2. **Read the version at the source.** Read the tool's newest release at its feed on the day you write the file. Set `checked_version`, `checked`, and `checked_by`; never type a version from memory. The `checked` date also says an agent found the choice still right, so it comes due again after a year when `maturity` is established and after 90 days when it is emerging. A standard names no version a project must use: its tool runs from the project's lock.
3. **Use the template.** [plugins/README.md](plugins/README.md#add-a-library-standard-or-a-stack) has it. Link the pack rule with `implements`; never restate it.
4. **Rename or retire with care.** A new id keeps the old one as a `standard_id` row in `schemas/retired-names.json`. A retired standard sets `status: deprecated` and names `replaced_by`, so projects that copied it hear about it.
5. **Check it.** `aidd eval standards` must pass, and `aidd gen-docs` updates [STANDARDS.md](docs/STANDARDS.md).

## Keeping the docs current

Three things keep the docs in step with the code, so a change updates one place and a test catches the rest.

- **Generated blocks.** Tables, counts, and lists that come from data sit between `<!-- aidd:gen ... -->` and `<!-- aidd:end -->`. Change the source, such as a schema, `schemas/risks.json`, or `schemas/roles.json`, then run `aidd gen-docs`. `aidd gen-docs --check` fails while a block is stale.
- **Retired names.** A change that renames or cuts a key, a value, or a library standard id that a person writes adds a row to `schemas/retired-names.json`, and no code. Then `aidd upgrade --yes` moves an adopter's files, and the loaders name the replacement in their errors. `tests/test_retired_names.py` checks that the old name is gone from the schemas and the new one is there. Prove a row with rows made for the test, as `tests/test_upgrade_engine.py` does with `made_up_row` and `only_rows` from `tests/helpers.py`, and keep no fixture of an old shape. A change that moves a value to another place needs a function in `aidd.setup.migrating`, named by the row's `id`.
- **Codes.** A code that a check gives, such as a reason a delegate check defers for, is one row of `schemas/findings.json`: its severity, title, why it comes, and next step. Add the row in the change that adds the code. A package gives a code with `findings.finding("<group>.<code>", message)`, which takes the severity and the next step from the row. `tests/test_findings.py` fails for a code the package gives with no row, for a code that belongs to another package's group, and for a row nothing gives. A new group names its owner package and how that package gives its codes in `GIVEN_BY` there. A step code is an entry of `step_code` in the common schema, with who takes it and what it means, and a stop code is an entry of `stop_code`.
- **Retired wording.** Before the 1.0.0 tag, a rename is a plain change, swept with `git grep`. After the tag, a change that renames or retires a concept adds its old wording to `RETIRED` in `tests/test_doc_currency.py`, with what replaced it. The test then fails on every page that still says it, including the pages a later change writes.
- **Concepts by name.** A concept a reader must meet by name goes in `CONCEPTS` there. It then needs a row in the [glossary](docs/GLOSSARY.md) and a mention in `llms.txt`, the page an agent reads first. Each name a schema defines needs a glossary row too, such as a route, a status, a document type, or a role. The same test reads those names from the schemas, so you never list them.

Before you finish a change that adds or renames a concept, search the docs for the old name with `git grep -n -i "<old name>"`. Then read README, the [guide](docs/GUIDE.md), `llms.txt`, and `llms-install.md` once, because most readers, human or agent, read them first.

## Change the method

Changes to routes, profiles, the built-in risk rules, schemas, or the loop need an RFC.

1. Copy `docs/rfcs/0000-template.md` to `docs/rfcs/NNNN-short-name.md` and open a PR with only the RFC. RFCs live under `docs/` and not at the root because nothing in the code reads them; `specs/` is at the root because aidd does.
2. Discussion stays open for at least 7 days, or 14 for anything that lowers a built-in rule's level.
3. The maintainers accept or decline in the PR. An accepted RFC is implemented in its own PR, with a Spec.

1.0.0 itself is the one exception, as the top of this page says. From the tag on, every change follows the loop and this section.

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
- **Design and diagram tools (2026-11-05, reopened in part 2026-11-10).** diagram-design's HTML and SVG diagrams can't be diffed or reviewed line by line, and they load Google Fonts. Its contrast script is covered by the prototyping skill's lint. archify's renderers are heavy Node code an agent must run, and it checks for updates daily. Impeccable's `--github` annotations are a project's own CI choice. On 2026-11-10 the owner listed both diagram tools as pinned, emerging extensions of the tech writer, the product designer, and the delivery manager. They serve a visual a person reads, never a diagram committed for review, which stays Mermaid. Reopen the committed case when a diagram tool writes text that diffs, with no network call.
- **Awesome Claude Skills (2026-11-05).** Superpowers' TDD, verification, debugging, worktrees, brainstorming, and planning skills are covered by the skill's rules and the team's roles. Its "merge locally" option breaks one PR/MR and Merge approval. One collection is GPL-3.0, so no text is copied from it. lean-ctx rewrites the command output the agent reads, which is evidence, and it has telemetry. Changelog and docs generators write model prose. aidd points to no skill that sends code to another service, fuzzes live targets, or drives a logged-in browser. Reopen a skill when it fills a gap the team names, and keeps one PR/MR and Merge approval.
- **Spec Kit's extension system (2026-11-05).** It has hooks before and after each command, runtime events, YAML workflows with run state and `resume`, bundles, and community catalogs with sign-in. aidd's flows are skills an agent reads, and autopilot works out the next step from git and the files, so a stopped run needs no run state. Hooks around aidd's commands would add a part each harness must load, and the harness's own hooks and ask rules already do the job. Bundles are aidd's profiles with `aidd init --aidd-team`. Reopen the catalog once adopters ask to share flows.

## Naming

Every public name follows these conventions. From 1.0.0 on, a public name changes only under the deprecation policy below.

1. Commands, subcommands, and flags are kebab-case. A noun group is a singular noun and then a verb, such as `standard add`. Every command that reads takes `--json`.
2. YAML keys, JSON fields, and enum values are snake_case with no spaces. A code, such as a stop code or a reason code, matches `^[a-z][a-z0-9_]*$`, and `tests/test_field_names.py` checks it. A step code is the one exception: it is `<object>.<state>`, such as `spec.approve`. A value that is also a CLI word or a file name, such as a doc type, is kebab-case.
3. An action is `resource.verb`, in lowercase snake_case words, with a dot for a narrower action, such as `git.push.force`. An area is one snake_case word or more, such as `personal_data`.
4. A limit has a `max_` or `min_` prefix, and a unit is a spelled-out suffix, such as `_seconds`, `_minutes`, `_hours`, or `_days`.
5. A date ends in `_on` or `due`, and a timestamp ends in `_at`.
6. Every JSON output has `schema_version` and a schema in `schemas/`.
7. A standard's id is `<group>/<topic>`, a test is `std.<group>.<topic>.<name>`, and a choice is `<pack>:<choice>`. An identity is `@login`, `email:<address>`, `agent:<harness>/<model>`, or `role:<role>` for a role of the team, as `$defs/identity` in `schemas/common.schema.json` lists them.
8. An environment variable is `AIDD_<NOUN>`. A git trailer takes git's own form, as in `Assisted-by` and `Approved-by`.
9. An ordinal scale is low, medium, and high, and priority adds urgent.
10. Names inside an experimental feature may change in a minor release (Versioning).

## Versioning

This section owns the versioning policy; other documents link here.

- **Patch.** Clarifications and bug fixes that no repository using aidd can observe.
- **Minor.** New optional fields, new actions, areas, and rules, and new modules.
- **Major.** Any change that can turn a passing check into a failing one under an unchanged config, or that removes or renames a key, a command, a flag, or an action.

A change to a built-in rule's level is listed in the CHANGELOG under its own heading, so a project can set its own rule back.

<a id="public-contracts"></a>**Public contracts.** Each public surface has a row below. A minor release may do what its third column lists and nothing in its fourth, and a patch release changes none of it. The last column says how a reader treats a file that a newer aidd wrote. aidd's own readers do it, and so should a program that reads aidd's files.

| Surface | Versioned by | A minor release may | Only a major release may | A reader of a newer file |
| --- | --- | --- | --- | --- |
| CLI commands, flags, and their values | `aidd_version`, the release | add a command, a flag, or a value | rename or remove one | A person upgrades aidd, so there is no newer file. |
| Exit codes | `aidd_version`, the release | add a code for a new case | change what a code means for a command (`0` passed, `1` a check failed, `2` an error, `130` stopped) | A script treats a code it does not know as a failure. |
| `--json` outputs and the results of the MCP tools | `schema_version`, `"1"`, and the output's schema in `schemas/` | add an optional key; add a value to a family of codes (finding, step, and reason codes, and the types of `aidd explain`) | rename, remove, or retype a key; make a key required; change what a key or a code means | Ignores a key and a code it does not know, and acts on the rest. The schemas hold the keys and codes of this release, because they check what aidd writes. A program that validates with one drops `additionalProperties: false` and the `enum` of each family of codes, the ones that carry `x-open: true`. Every other `enum` stays closed to a reader, so an unknown `level` is an error. |
| MCP tool names and parameters | `aidd_version`, the release | add a tool or an optional parameter | rename or remove a tool or a parameter, make a parameter required, or narrow its values, because an adopter's permission rule names the tool | The tool refuses a parameter it does not know and names the closest one it does. |
| The environment variables, listed in [docs/CLI.md](docs/CLI.md#environment-variables): those aidd defines (`AIDD_*`), those another tool defines that it reads, and those it reads only to tell where it runs | `aidd_version`, the release | add an `AIDD_*` variable; read one more variable of another tool, or stop reading one, since that tool owns its name | rename or remove an `AIDD_*` variable, or change what its value means | A person sets them, so there is no newer file. aidd ignores a variable it does not know, and reads a value it does not know as the default. |
| The GitHub Action's inputs, in `action.yml`, in alphabetical order: `artifact`, `base-ref`, `red-in-place`, `upload-logs`, `validate` | the ref a workflow pins | add an input whose default keeps today's behavior | rename or remove an input, or change a default so that a passing workflow fails | GitHub warns about an input the Action does not declare, and the Action runs without it. |
| Records | the record's `type` | add a type; add a key to a type's `data`; add a value to a code of a record (an outcome, a question's `type`, or `written_with`) | change what a type's `data` means; rewrite a record, which aidd never does | Keeps a record of a type, with a key, or with a code's value it does not know, byte for byte, and shows the fields it knows. `aidd records` lists it in `partly_read`, and no count of a person's yes or of a delegate's answer includes it. |
| The evidence file | `aidd_version` in the file | add an optional key | rename, remove, or retype a key; change what a status means | Reads the keys it knows. A result with a status it does not know reads as failed, never as passed, and `aidd status` says so. |
| The handoff block | `aidd_version` of the config | add an optional key | rename, remove, or retype a key | Ignores a key it does not know. `aidd validate` warns and blocks nothing. |
| The config | `aidd_version` | add an optional key; widen the values of a key | rename, remove, or retype a key; narrow the values of a key; change a default so a control asks less | Fails closed on a key it does not know, and says the config may be for a newer aidd. |
| A Spec's front matter, and an Intent's | `aidd_version` of the config | add an optional field | rename, remove, or retype a field | `aidd validate` fails on a field it does not know, and `aidd status` still shows the work item. |
| The `##` headings aidd reads in a document's body, in alphabetical order: `Acceptance`, `Alternatives considered`, `Concerns`, `Constraints`, `Context`, `Design`, `Events`, `Goals`, `Learn`, `Out of scope`, `Policy conflicts`, `Pre-mortem`, `Problem`, `Request`, `Rollback`, `Rollout`, `Screen inventory`, `SLI changes`, `SLOs`, `Test approach` | `aidd_version` of the config | read one more heading, and report a missing one as a warning only | rename a heading, stop reading one, or fail on a missing one | Ignores a heading it does not know. A heading is read without regard to case. |
| The commit trailers aidd writes and reads, in alphabetical order: `Aidd-Skipped`, `Approved-by`, `Approves`, `Assisted-by`, `Decided-by`, `Delegation`, `On-behalf-of` | `aidd_version`, the release | add a trailer | rename or remove a trailer, or change what its value means | Ignores a trailer it does not know, and counts none of them as a person's or a delegate's yes. |
| The ids an adopter names: actions, areas, roles, document types, change types, risk dimensions, test runners, and languages | `aidd_version`, the release | add an id | rename or remove an id; lower a built-in rule's level | A file that names an id this aidd does not know fails closed, as the config does, because aidd cannot tell it from a typo. |
| The plugins' names: the aidd-team commands (`/aidd-team:<flow>`), its agents and skills (`aidd-team:<role>`, `aidd-team:<practice>`), and the aidd-packs skills (`aidd-packs:<pack>`) | `aidd_version`, the release | add a command, an agent, or a skill | rename or remove one, because an adopter's permission rule, Task, or script names it | A person updates a plugin with aidd, so there is no newer file. |
| The retired-names table, `schemas/retired-names.json` | `aidd_version`, the release | add a row | remove a row | A name a row lists gets its replacement and `aidd upgrade --yes` in the error. |
| The ledgers aidd keeps to know what it wrote: `.aidd/harness-rules.json` and `.aidd/team-files.json` | none | add a key | — | A newer aidd reads every older ledger, because `aidd upgrade` and `aidd uninstall` read it to find the ask rules, allowed tools, and team files that are aidd's. It leaves a key it does not know where it is. |
| The files aidd writes and rewrites: the harness and agent files of `aidd init` | none | change anything, while `aidd upgrade` rewrites the skill and ask rules and keeps an edited team file | — | Nothing reads an old one. |

**What a reader does with a newer file.** What aidd writes is closed: a test checks that aidd emits no key its schema lacks. What a program reads from aidd is open to a key and a code it does not know. A file a person writes, the config and a Spec's front matter, stays closed, because a typo there must fail and never be ignored: a guess could read an `ask` as an `allow`. A family of codes is an `enum` with `x-open: true` in its schema. Any other `enum` stays closed to a reader, so a value it does not list is an error. A reader of a newer file acts on what it knows and says what it skipped. It never refuses without a word, and it never guesses: a value it cannot read counts neither as a pass nor as an approval.

**Renames and the version.** `schema_version` stays `"1"` through every additive change. It changes only in a major release, and the CHANGELOG names the change. A rename after 1.0.0 is expand and contract: a minor release ships the new name and keeps reading the old one with a warning, and the next major release stops reading it. `tests/test_public_contracts.py` lists each file of `schemas/` under its surface, so a schema added with no row fails.

<a id="frozen-tests"></a>**Frozen tests stay green across upgrades.** A Spec's tests may run an aidd command, such as `aidd validate` or `aidd prototype --check`. Within one major version, each such command accepts every input an earlier release of that major accepted. So an upgrade never turns an approved Spec's frozen test red. A new or stricter check arrives as a warning, or behind the format version a file names, and fails only from the next major.

**Experimental names.** Names inside a feature marked experimental may change in a minor release. The CHANGELOG says so in that release.

<a id="deprecation"></a>**Deprecation.** This is the one deprecation policy; other pages link here. From 1.0.0 on, a config key, Spec field, action, CLI command, or flag being replaced keeps working until the next major release. A warning names the replacement. The changelog lists it under Deprecated in the release that deprecates it. Names changed before 1.0.0 were never released, so 1.0.0 keeps none of them.

**Cadence.** There's no fixed cadence. A release goes out when the changelog earns it, and a security fix goes out as a patch as soon as it's ready. [GOVERNANCE.md](GOVERNANCE.md) sets the cadence.

## Release

Maintainers follow [RELEASING.md](RELEASING.md).

## Security

Report a vulnerability privately, as [SECURITY.md](SECURITY.md) describes. That includes a way for aidd to run a project's code it should only read, to leak a secret, or to write a harness ask rule that is looser than the config.
