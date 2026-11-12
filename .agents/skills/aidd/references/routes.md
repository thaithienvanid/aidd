# Routes

The route is advice. `aidd risk --paths <planned paths>` computes the least route for what a change touches, and the author may declare higher. No Spec is the default. The route is one choice: **no Spec (`minor`), a Spec (`normal`), or a production repair (`emergency`)**. Do not guess `major`: an area or a dimension raises the change to it, and `aidd risk --paths` says so. A major change adds what its route meaning lists. On the branch, check again with every path the diff touches.

**Contents**

<!-- aidd:gen toc -->
- [First match wins](#first-match-wins)
- [Areas](#areas)
- [Risk dimensions](#risk-dimensions)
- [Route meanings](#route-meanings)
- [Change types](#change-types)
- [Confidence](#confidence)
<!-- aidd:end -->

## First match wins

| Order | Route | Choose it when |
| --- | --- | --- |
| 1 | emergency | Production is broken now (an outage, a degradation, an incident), and this change is the repair. The author declares it. |
| 2 | major | An area's route is major; a dimension forces major (below); or the change cannot be reverted. |
| 3 | minor | Confidence is high, one Task, no risk dimension, no area that raises the route, no binary file, no contract change (a judgment), and a diff small enough to review at a glance, about 50 changed lines. |
| 4 | normal | Anything else. |

Stops before any route:

- `confidence: low`: ask for the missing fact.
- No owner: nobody owns the decision (`SKILL.md` stop 1).

## Areas

An area is a named set of paths (`references/risk.md`). A change that touches one takes at least its route, and an edit inside it takes its edit level. Docs and Markdown files inside an area do not count. A config adds areas under `risks.areas`.

<!-- aidd:gen risks:areas:short -->
| Area | What it holds | Raises the route to | Dimensions | Editing it |
| --- | --- | --- | --- | --- |
| `auth` | Who can sign in and what each person may do: authentication, authorization, roles, sessions, tokens. | major | security | ask |
| `payments` | Money moves or prices change: checkout, billing, payouts, invoices. | major | financial | ask |
| `personal_data` | Data about people: users, customers, accounts, profiles, contacts, patients. | major | privacy | ask |
| `secrets` | Secrets, keys, certificates, and cryptography. | major | security | ask |
| `migrations` | Database schema changes and data migrations. | major | data | ask |
| `module_boundaries` | The rules that keep modules apart: import contracts and architecture tests. | major | none | report |
| `ci` | What builds, tests, and ships the code: CI pipelines, git hooks, and code owners. | normal | third_party | report |
| `infra` | Infrastructure as code and containers: what runs the service. | normal | availability | report |
| `dependencies` | Third-party code and build tools: manifests, lockfiles, and the bots that update them. | normal | third_party | report |
| `agent_config` | What instructs or permits a coding agent: AGENTS.md, the skills, the harness settings, and aidd's config. | normal | none | report |
| `risk_rules` | The files that set when an agent asks: aidd's config and the record of the ask rules it wrote, and each harness's own ask rules. An agent asks before it changes what makes it ask. | normal | none | ask |
| `project_config` | How the project checks its code and draws its product: test, lint, and type settings, app manifests, the design system, standards, and module APIs. | normal | none | report |
| `product_scope` | What the product is for, as a person approved it: the brief, the BRD, the PRD, the standing outcomes, and the order of the Intents. An Intent's file is not here, because each slice start edits it. | minor | none | allow |
<!-- aidd:end -->

With the CLI, never match a glob by hand: run `aidd risk --paths <path>`. Without it, judge each path against the areas above by what it holds, and say the route is unchecked. A package that moves money or signs people in, such as a payment SDK or an auth library, brings that area's risk wherever its code sits. Declare the dimension, so the route is major: `aidd risk --paths <paths> --dimension <dimension>`.

## Risk dimensions

Pick every dimension the change can harm. A new tool, MCP server, or permission for an agent widens what it can do, so declare `security`, and `data` when it reads production data: the route is major, whatever its path says. `aidd risk --paths` names those the areas imply. Declare each other one with `--dimension`, which `aidd risk` and `aidd new spec` both take, so the route reads it. A dimension that forces major also names the specialists the change asks (`owners.specialists`). Irreversibility is no dimension: `risk.irreversible: true` (`--irreversible`) also makes the change major.

<!-- aidd:gen vocab:dimension -->
| Token | Meaning |
| --- | --- |
| `data` | Reads, writes, migrates, or deletes persistent or production data. Forces major; the `data` pool reviews. |
| `security` | Who can do what, and what can leak: authentication, authorization, roles, tokens, secrets, cryptography, attack surface. Forces major; the `security` pool reviews. |
| `privacy` | Personal data: collection, retention, sharing, deletion, consent. Forces major; the `privacy` pool reviews. |
| `financial` | Money moves or prices change: billing, payouts, pricing, ledgers, tax. Forces major; the `finance` pool reviews. |
| `compliance` | A legal, contractual, or regulatory control. Forces major; the `compliance` pool reviews. |
| `availability` | Can take a service down or degrade it: infrastructure, capacity, timeouts, limits. Rules out minor. |
| `third_party` | Adds or changes third-party code, services, images, or build inputs. Rules out minor. |
| `cost` | Can change spend materially: compute, storage, paid APIs, model tokens. Rules out minor. |
| `performance` | Can make a hot path slower or heavier: a new query, a loop over remote calls, a page asset, data that grows. Rules out minor; `aidd validate` warns until an Acceptance item states the budget and a test command covers it. |
<!-- aidd:end -->

## Route meanings

<!-- aidd:gen vocab:route -->
| Token | Meaning |
| --- | --- |
| `minor` | Small and reversible, one Task, with no risk dimension. No Spec file: implement, verify, review, and Merge approval before the merge to the default branch. |
| `normal` | Everything that is not minor, major, or emergency. A Spec, with tests that fail on the base commit (red) and pass on head (green), and Spec approval where the profile asks for it. |
| `major` | Touches data, security, privacy, money, or compliance, edits an area that raises the route to major, or cannot be reverted. A Spec with more: a tech spec, a threat model for security, privacy, or data, a rollout plan, and an observe block. |
| `emergency` | Production is broken now and this change is the repair. Smoke tests still run, the review comes before the merge, and the Spec and the post-incident review follow by `backfill_due`. |
<!-- aidd:end -->

## Change types

Conventional Commits vocabulary: the Spec's type is the commit's type. The type never raises the route, and a dimension does. A change to data, security, or compliance gives its own type, such as `feat` or `fix`, and declares the dimension of that name.

<!-- aidd:gen vocab:change_type -->
| Token | Meaning |
| --- | --- |
| `feat` | New or changed behavior someone can see. Needs a new-behavior test on normal and major. |
| `fix` | Restores intended behavior. Needs a test that fails before the fix (red) and passes after (green). |
| `refactor` | Structure changes, behavior does not. Existing tests must stay green. |
| `perf` | Same behavior, different cost. Acceptance is a threshold. |
| `docs` | Documentation, content, or generated reference only. |
| `test` | Tests only; no behavior changes. |
| `build` | Build system, packaging, developer tooling, third-party packages, or the infrastructure that runs the service. An infrastructure change also declares the dimension `availability`. |
| `ci` | Continuous integration or delivery pipelines and agent configuration. |
| `chore` | Housekeeping that changes no behavior: formatting, renames, cleanup. |
<!-- aidd:end -->

## Confidence

<!-- aidd:gen vocab:confidence -->
| Token | Meaning |
| --- | --- |
| `high` | Every fact that could change the route is known. open_questions is empty. |
| `medium` | Some facts are missing, and none of them could change the route. List them, and go on. |
| `low` | A missing fact could change the route. Stop and ask. |
<!-- aidd:end -->
