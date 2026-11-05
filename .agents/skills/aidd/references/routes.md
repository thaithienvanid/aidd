# Routes

The route is advice. `aidd risk --paths <planned paths>` computes the least route for what a change touches, and the author may declare higher. The lane follows from the route, and the fast lane is the default. The route is one choice: **no Spec (`minor`), a Spec (`normal`), or a production repair (`emergency`)**. You do not need to guess `major`: an area or a dimension raises the change to it, and `aidd risk --paths` says so. Then add what major needs: a tech spec, a threat model when a dimension is security, privacy, or data, a rollout runbook, and an `observe` block. On the branch, check again with every path the diff touches.

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
| 1 | emergency | Production is broken now (an outage, a degradation, an active security or data incident), and this change is the repair. The author declares it; no path computes it. |
| 2 | major | The change touches an area whose route is major; a dimension is `data`, `security`, `privacy`, `financial`, or `compliance`; the change cannot be reverted; or `change_type` is `data`, `security`, or `compliance`. |
| 3 | minor | Confidence is high, one Task, no risk dimension, no area that raises the route, no binary file, no contract change (a judgment), and a diff small enough to review at a glance, about 50 changed lines. |
| 4 | normal | Anything else. |

Stops before any route:

- `confidence: low`: a missing fact could change the route. Ask for it.
- No owner: nobody can be named as `owner_team`, or nobody owns the decision (`SKILL.md` stop 1).

## Areas

An area is a named set of paths (`references/risk.md`). A change that touches one takes at least its route, and an edit inside it takes its edit level. Docs and Markdown files inside an area do not count, so a fix to `docs/auth/overview.md` stays minor. A config adds areas under `risks.areas`.

| Area | What it holds | Route | Dimensions |
| --- | --- | --- | --- |
| `auth` | sign-in and permissions: authentication, authorization, roles, sessions, tokens | major | security |
| `payments` | where money moves or prices change: checkout, billing, payouts, invoices | major | financial |
| `personal_data` | data about people: users, customers, accounts, profiles, contacts, patients | major | privacy |
| `secrets` | secrets, keys, certificates, and cryptography | major | security |
| `migrations` | database schema changes and data migrations | major | data |
| `module_boundaries` | import contracts and architecture tests | major | none |
| `ci` | CI pipelines, git hooks, and code owners | normal | third_party |
| `infra` | infrastructure as code, containers, and deploy config | normal | availability |
| `dependencies` | manifests, lockfiles, and the bots that update them | normal | third_party |
| `agent_config` | AGENTS.md, skills, harness settings, and aidd's config | normal | none |
| `project_config` | test, lint, and type settings, app manifests, the design system, and standards | normal | none |

To find the area a path hits, run `aidd risk --paths <path>`. Never match a glob by hand. An added package that moves money or signs people in, such as a payment SDK or an auth library, brings that area's risk wherever its code sits. Declare the dimension, so the route is major.

## Risk dimensions

Pick every dimension the change can harm. `aidd risk --paths` names the ones the areas imply. `data`, `security`, `privacy`, `financial`, and `compliance` make the change major, and each names the specialists the change asks (`owners.specialists`). The others only rule out minor. Irreversibility is not a dimension: set `risk.reversible: false`, which also makes the change major. `confidence: medium` changes no route. It tells the person who approves which facts you could not check, so list them in `open_questions`.

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
| `minor` | Small and reversible, one Task, with no risk dimension. The fast lane: no Spec file, then implement, verify, review, and Merge approval before the merge to the default branch. |
| `normal` | Everything that is not minor, major, or emergency. A Spec, with tests that fail on the base commit (red) and pass on head (green), and Spec approval where the profile asks for it. |
| `major` | Touches data, security, privacy, money, or compliance, edits an area that raises the route to major, or cannot be reverted. A Spec with more: a tech spec, a threat model for security, privacy, or data, a rollout plan, and an observe block. |
| `emergency` | Production is broken now and this change is the repair. Smoke tests still run, and the Spec and the review follow by `review_due`. |
<!-- aidd:end -->

## Change types

Conventional Commits vocabulary, so the type in the Spec is the type in the commit message.

<!-- aidd:gen vocab:change_type -->
| Token | Meaning |
| --- | --- |
| `feat` | New or changed behavior someone can see. Needs a new-behavior test on normal and major. |
| `fix` | Restores intended behavior. Needs a test that fails before the fix (red) and passes after (green). |
| `refactor` | Structure changes, behavior does not. Existing tests must stay green. |
| `perf` | Same behavior, different cost. Acceptance is a threshold. |
| `docs` | Documentation, content, or generated reference only. |
| `test` | Tests only; no behavior changes. |
| `build` | Build system, packaging, or developer tooling. |
| `ci` | Continuous integration or delivery pipelines and agent configuration. |
| `chore` | Housekeeping that changes no behavior: formatting, renames, cleanup. |
| `deps` | Adds, removes, or upgrades a third-party package. |
| `infra` | Runtime, network, or deployment infrastructure, including infrastructure as code. |
| `data` | Schema, migration, backfill, or production data. Always major. |
| `security` | Identity, access, roles, secrets, or cryptography. Always major. |
| `compliance` | Driven by a legal or regulatory control. Always major. |
<!-- aidd:end -->

## Confidence

<!-- aidd:gen vocab:confidence -->
| Token | Meaning |
| --- | --- |
| `high` | Every fact that could change the route is known. open_questions is empty. |
| `medium` | Some facts are missing, and none of them could change the route. List them, and go on. |
| `low` | A missing fact could change the route. Stop and ask. |
<!-- aidd:end -->
