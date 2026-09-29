# AIDD: the method

AI-Driven Development (AIDD) is a method for delivering software with AI agents: one loop from intent to production, with change control at its core. It works in new repositories (greenfield) and existing ones (brownfield) alike. Agents implement.

AIDD is the method, and aidd is the toolkit that runs it, with a verifier at its center. The verifier decides the route a change takes, demands evidence a machine can check, puts humans at the two points where their judgment is cheapest and matters most, and stops unsafe work. It is not an agent, a model, a tracker, or a CI system. It binds to the ones you already run.

**The core rule: the agent proposes; the verifier decides.** Every control is either computed by `aidd gate` from platform facts, or it is a named human decision recorded on the platform. Model prose is never evidence.

Version 1.0.0. License Apache-2.0. Why the method is built this way, and how it maps to Agile and to the frameworks you know: [RATIONALE.md](RATIONALE.md).

## Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119), [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals, as shown here.

Every requirement names who it binds:

| Subject | Who that is |
| --- | --- |
| **verifier** | the function that turns a context into a decision (`aidd gate`, or any reimplementation) |
| **adapter** | the code that builds a context from a platform and posts the decision (the reference GitHub and GitLab adapters, or yours) |
| **repository** | the adopting repository: its config, its Specs, and its Change Requests |
| **operator** | the people who administer the platform: branch rules, the gate's identity, its secrets |

Only a sentence with a capitalized keyword is a requirement, together with the rows of the generated rule table in §7, where each row states when its rule holds and the level a verifier emits when it does not. Everything else, in any section, explains.

**Section status.** A normative section contains requirements; an informative one describes practice the verifier does not check, which you adopt as guidance.

| Section | Status |
| --- | --- |
| [1. Scope and conformance](#1-scope-and-conformance) | Normative |
| [2. Principles](#2-principles) | Informative |
| [3. Roles](#3-roles) | Normative |
| [4. Objects](#4-objects) | Normative |
| [5. The loop](#5-the-loop) | Informative |
| [6. Routes](#6-routes) | Normative |
| [7. Evidence and the verifier](#7-evidence-and-the-verifier) | Normative |
| [8. Approvals and separation of duties](#8-approvals-and-separation-of-duties) | Normative |
| [9. Profiles](#9-profiles) | Normative |
| [10. Scale modules](#10-scale-modules) | Informative, except the config fields it names |
| [11. AI-era security controls](#11-ai-era-security-controls) | Informative, except the rules it names |
| [12. Ship and Learn](#12-ship-and-learn) | Informative, except the recorded fields and the emergency backfill |
| [13. Interfaces and configuration](#13-interfaces-and-configuration) | Normative |
| [14. Platform bindings and trust](#14-platform-bindings-and-trust) | Normative |
| [15. Distribution and versioning](#15-distribution-and-versioning) | Informative |
| [16. Conformance checklist](#16-conformance-checklist) | Informative (a checklist of §1) |

## 1. Scope and conformance

*Normative.*

This is the one conformance list; §16 restates it as a checklist.

**A repository conforms at a profile (§9) when:**

1. **R1.** The repository MUST hold `.aidd/config.toml` on every protected branch, and it MUST validate against `schemas/config.schema.json` ([CONFIG.md](CONFIG.md)).
2. **R2.** The operator MUST require the `aidd/gate` status on every protected branch, posted by a trusted gate job (§14) whose status source is pinned to the gate's own identity.
3. **R3.** The repository MUST bind the owners its profile needs (§9): `owners.approvers` on every profile; from team up, at least a `security` reviewer pool before any major change can ship; and a Policy command on the routes where the profile requires one.
4. **R4.** Every merged change MUST carry a Change Request block (§4.4), or be a bot PR/MR that matches a configured standard change class. Every normal or major change MUST have a Spec (§4.2).
5. **R5.** Test evidence MUST come from a runner the change cannot rewrite without a major review (§14). The repository SHOULD configure a repository suite in `[[tests]]`; without one, every Spec MUST bring its own commands (Characterization, §10).
6. **R6.** The repository MUST list every agent account that commits to it in `identities.bots`.
7. **R7.** The agent skill, or instructions equivalent to it, MUST be available to every agent that writes to the repository (§15). The gate cannot check this; the protected paths (§6) keep it from being edited silently.
8. **R8.** The operator SHOULD retain gate records and events for as long as their audit regime requires ([ENTERPRISE.md §6](ENTERPRISE.md#6-audit-evidence)).

**A tool conforms when:**

1. **T1.** A verifier MUST produce the same decision, and the same failed, pending, and warning rules, as the reference verifier on every case in `examples/`, including each case's `mutations/`. A mutation is a data file that replays a JSON-patch-like edit of the case and states the expected result; `aidd eval examples --root <checkout>` runs them.
2. **T2.** An adapter MUST build contexts that validate against `schemas/context.schema.json` from platform facts only, and MUST meet §14.

## 2. Principles

*Informative. The requirements that realize these principles are in §6 to §9 and §14.*

1. **Evidence, not prose.** The only pass is a runner exit code of 0, bound to the head commit. The agent's claims, summaries, and PR/MR text never count.
2. **Tests before implementation.** Tests are written in Specify and frozen by the Spec approval hash. New behavior is proven red on the base commit and green on head.
3. **Two human approvals.** The Spec approval decides *what* will be built (the Spec and its tests). The Merge approval decides *what was* built (the head commit). Nobody approves their own work, except under the solo profile, where the waiver is recorded.
4. **Scope is declared, then enforced.** Every changed path lies inside a Task's `scope`, the Spec, a test file, or a configured exemption.
5. **Routes only go up.** The verifier recomputes the minimum route from the real diff and rejects a lower declaration. Protected paths (the gate's own config, CI, and agent instructions) are always major.
6. **Interfaces, not brands.** Repo, CI, test runner, Secrets, Policy, Observe, and Release are bound in config. A vendor name is never a step.
7. **Minimum ceremony.** Initiative and Epic are optional. Minor and standard changes need no Spec file. Modules stay off until their signal is true.
8. **Gates only tighten.** A config can only tighten its profile, and a child config can only tighten its parent. Rules, exemptions, and standard changes can widen what passes, so every config change is itself protected and major.
9. **Single source of truth.** Schemas and data files define every field, token, profile gate, and path rule. Docs and skill tables are generated from them.
10. **Close the loop.** Rollbacks, rejects, incidents, and exhausted retries feed lessons back into the repository's agent instructions, tests, or rules.
11. **Priced to value.** Control and cost scale with risk: the least ceremony, the fewest roles, and the lowest model tier that pass. Extra cost or complexity needs a stated reason, in the Spec or the handoff note.
12. **Proven over new.** The method, the gate, and the team apply established standards and tools. An emerging one is marked as such in the registry and applied only when a change clearly needs it.

## 3. Roles

*Normative.*

| Role | Who | Does | MUST NOT |
| --- | --- | --- | --- |
| Author | the person who directs agents and opens the PR/MR, plus every commit author and committer | runs the loop, answers the stops | approve their own change (except under solo, §8) |
| Implementer | an agent or a person | edits inside the `scope` | edit the tests after Spec approval, approve, merge, write statuses |
| Approver | a person in `owners.approvers`, narrowed by the Spec's `approvers` | Spec approval and Merge approval decisions | approve a change they authored (except under solo, §8) |
| Specialist reviewer | a person in an `owners.reviewers` pool: `security`, `data`, `privacy`, `finance`, `compliance`, or a pool a risk rule names | reviews major changes that touch the pool's dimension before merge | be an author of the change |
| Incident commander | named in the emergency block | owns an emergency change | skip the post-incident review |
| Verifier | the `aidd/gate` job | computes every rule in §7 | run code from the change |
| Maintainer | owns `.aidd/config.toml` | binds interfaces and owners | loosen a profile silently |

The verifier MUST NOT count an approval from an account in `identities.bots`, and MUST count any other bot account (a login ending in `[bot]`) only when the approver pool names it. The role names are functional: the gate trusts platform accounts, not titles, and the same person may hold several roles under the profile's rules (§8).

## 4. Objects

*Normative.*

Seven object kinds: Proposal, Initiative, Epic, Spec, Task, Tests, and Change Request. Proposal, Initiative, and Epic are optional. Tasks and Tests live inside the Spec file. An issue tracker MAY mirror an object under its `id`; the verifier reads only the repository. Story, Issue, Ticket, and Feature are human aliases of Spec, and "Feature" is never a route or a type.

```text
accepted:     Proposal ─▶ Initiative (proposal) ─▶ Epic (covers the proposal's needs)
containment:  Initiative ─▶ Epic ─▶ Spec ─┬─▶ Task (1..n)
                                          ├─▶ Tests (1)
                                          └─▶ Change Request (1 per repo)
trace:        Spec ─▶ diff ─▶ test evidence (head SHA) ─▶ approvals ─▶ merge ─▶ Observe ─▶ outcome
```

Every table in this section is generated from `schemas/`; the schema is the source of truth. The config is specified in [CONFIG.md](CONFIG.md).

### 4.1 Vocabulary

<!-- aidd:gen vocab:type -->
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

### 4.2 Spec

A Spec is `specs/<ID>.md`. It has TOML front matter between `+++` lines, and a Markdown body. `aidd new spec` writes the short Spec (Intent, Acceptance, Design, Rollback) for a normal change and the full one for major.

- On normal and major, the body MUST contain `## Context` (the short template's `## Intent` counts: the why, in the originator's words) and `## Acceptance`.
- Acceptance is Gherkin for user-visible behavior; otherwise it is a schema, a table, a threshold, or an invariant. Each acceptance line SHOULD map to a test command.
- The `## Design` section SHOULD open with one diagram of the change (a Mermaid block in the file), so a human reads its shape before the words at Spec approval; `aidd validate` warns when a major Spec has neither a diagram nor enough prose.

Two more sections help a person at Spec approval. `aidd validate` warns (never errors) when either is missing or empty; the gate does not read them.

- The body SHOULD open with `## Intent`: the originator's own words, captured before any design (the problem, the outcome they want, who is affected, the constraints, and the open questions), so a reviewer can check the Spec's reading of the request against the request itself.
- A major Spec, or one whose risk names more than one specialist pool, SHOULD carry `## Policy conflicts`: each place where specialist input, a domain pack, or org policy contradict each other, and the human who must decide it, or `none`. An agent records a conflict; it never settles one.

<!-- aidd:gen fields:spec -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `kind` | `"spec"` | yes | Object kind. Always `spec`. |
| `id` | string | yes | Spec key, such as SPEC-220. |
| `parent` | string | no | Optional Epic id. |
| `title` | string | yes | One line. `locale` may apply. |
| `owner_team` | string | yes | Team accountable for the change. |
| `approvers` | list of string | no | Eligible Approvers for this Spec. Can only narrow the config's `owners.approvers`. |
| `type` | `type` | yes | What kind of change this is, in Conventional Commits vocabulary. `data`, `security`, and `compliance` are always major. |
| `route` | `normal` \| `major` \| `emergency` | yes | normal (the gate raises it to major when the diff demands it), major, or emergency for a backfill Spec. Minor and standard changes have no Spec file. |
| `confidence` | `confidence` | yes | Confidence in the assessment. `low` stops the run. |
| `open_questions` | list of string | no | Facts still unknown at assessment. Empty when confidence is high. |
| `trace_id` | string | no | Joins the Specs and changes of one piece of work across repositories. Defaults to the id. |
| `status` | `status` | no | Optional bookkeeping; the gate derives the state from the PR/MR. |
| `blocked_on` | string | when status is `blocked` | Role, person, or interface the Spec waits on. Required when status is blocked. |
| `labels` | list of string | no | Up to 8 labels, lowercase letters, digits, `:` and `-`, such as `area:billing` or `customer-ask`, for filtering (`aidd next --all --label`). They never change the route or the gate, and the Spec approval hash ignores them. |
| `relations` | list of table (`relation`) | no | Typed links to other Specs, Epics, or Initiatives: blocks, blocked_by, duplicates, relates_to, implements. Bookkeeping: the gate never reads them and the Spec approval hash ignores them. |
| `proposed_by` | string | no | Who proposed work nobody asked for: `agent:<role>` for an agent in `[agents] proactive_roles` (or an agent account). Such a Spec stays a draft until a person records `triage`. |
| `triage` | table (`triage`) | no | A person's decision on proposed work. Required, by a person, before a Spec whose proposed_by is an agent moves past draft. |
| `risk` | table (`risk`) | yes | Blast radius: what changes, which dimensions it touches, and whether a revert restores the prior state. |
| `rollback` | string | yes | How to undo. Name the steps on major and emergency. |
| `hypothesis` | string | no | The measurable result the change should produce after Ship, written before Spec approval and frozen by the approval hash: a metric, its baseline, the expected move, and by when. Learn records `outcome.result` against it. |
| `residual_risk` | string | no | What stays true after release. `none` when nothing remains. |
| `assisted_by` | list of string | yes | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `decisions` | list of string | no | ADR paths or links this Spec depends on. |
| `tasks` | list of table (`task`) | yes | Slices of the change. Parallel only when their scope is disjoint. |
| `tests` | table (`tests`) | yes | How the change is proven: the test files and the commands that run them. |
| `design` | table | no | The approved look and flow of a user-facing change. Optional; the product designer writes it before Spec approval. |
| `observe` | table (`observe`) | when route is `major` | Post-release check. Required on the profile's observe_required_routes: major, and normal under regulated. |
| `emergency` | table (`emergency`) | when route is `emergency` | Required when route is emergency. |
| `outcome` | table (`outcome`) | no | What happened after Ship. Written during the observe window and in Learn. |
<!-- aidd:end -->

Tasks:

<!-- aidd:gen fields:task -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line describing the slice. |
| `scope` | list of string | yes | Globs this Task's diff may change. Never a test or design file, never a catch-all. |
| `depends_on` | list of string | no | Task ids that must finish first. Required between Tasks whose scope overlaps. |
| `assignee` | string | no | Implementer: `agent:<role>` or a person. |
| `skills` | list of string | no | Skills loaded only for this Task, by directory name: a practice skill such as `api-design` or a stack skill, at most two. Domain packs are named in Context instead. |
| `risk` | string | no | What this Task could break, and how it guards against it. Approved content: frozen by the Spec approval hash. |
| `proof` | string | no | How this Task is shown to work: the test command, screenshot, or check a reviewer reads. Approved content: frozen by the Spec approval hash. |
| `retry_count` | integer | no | Implementation retries used. At 3 the Spec is blocked. |
<!-- aidd:end -->

Tasks whose `scope` overlap MUST be ordered by `depends_on`. No Task's `scope` may cover a test file.

A Task SHOULD say what it could break and how it guards against that (`risk`), and how it is shown to work (`proof`: a test command, a screenshot, or a check). With `scope` (the files) and `depends_on` (the order), a Task is a complete plan. Both are approved content, frozen by the Spec approval hash.

### 4.3 Tests

<!-- aidd:gen fields:tests -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `files` | list of string | yes | The test files, and the configuration they run through. Frozen by the Spec approval hash and never inside a Task's scope. |
| `commands` | list of table (`test_command`) | yes | Commands the runner executes. Exit 0 is the only pass. |
<!-- aidd:end -->

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. The gate never reads it. |
<!-- aidd:end -->

The repository suite (`[[tests]]` in config) runs on every change, in addition to the Spec's commands; its entries never carry `new_behavior`. With no repository suite, the Characterization module (§10) applies.

### 4.4 Change Request

The Change Request is the PR/MR. Its description MUST hold exactly one fenced block with the info string `toml aidd`. On normal and major, the block MUST name the Spec. Minor, standard, and emergency changes MAY declare inline. The verifier derives everything else (§7). Nothing in the block counts as evidence.

A bot PR/MR with no block is treated as the configured standard change class that every one of its authors belongs to; if none matches, the block is missing and the gate fails. `aidd change` prints a starting block for the current branch.

<!-- aidd:gen fields:change-request -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `spec` | string | no | Repo path of the Spec. Required on normal and major. When set, the Spec supplies every other field. |
| `trace_id` | string | no | Copy of the Spec trace_id. Child changes in other repos use the same value. |
| `route` | `minor` \| `standard` \| `emergency` | when spec is absent | Inline only: minor, standard, or emergency. Normal and major need a Spec. |
| `type` | `type` | no | Default chore. |
| `confidence` | `confidence` | no | Default high. |
| `risk` | table (`risk`) | no | Inline blast radius. Default: no dimensions, reversible. The gate fails when the paths imply a dimension the block omits. |
| `scope` | list of string | when route is `emergency` and spec is absent | Inline scope: globs the diff may change. Required on emergency. On minor it defaults to the changed paths and is recorded as undeclared. |
| `rollback` | string | no | How to undo. Default: revert the change. |
| `residual_risk` | string | no | What stays true after release. |
| `assisted_by` | list of string | when spec is absent | `harness/model` for each AI agent that wrote code or tests. Empty when only humans did. |
| `tests` | table (`tests`) | no | Inline tests, such as smoke tests on an emergency. They add to the repository suite, never replace it. |
| `emergency` | table (`emergency`) | when route is `emergency` and spec is absent | Required when route is emergency. |
| `backfill` | string | when route is `emergency` and spec is absent | Emergency only: the repo path of the backfill Spec, committed as a stub with the repair (`aidd new spec <ID> --title "<incident>" --route emergency`). `aidd validate` fails once its review_due passes without outcome.learn_ref. |
| `standard_change` | string | when route is `standard` and spec is absent | Name of the config standard_changes entry this change claims. |
<!-- aidd:end -->

### 4.5 Risk, observe, emergency, and outcome

The tables a Spec or an inline block nests.

`risk`:

<!-- aidd:gen fields:risk -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `summary` | string | yes | Blast radius in one or two sentences: who or what changes behavior. |
| `dimensions` | list of `dimension` | yes | Every dimension the change touches. Empty means none. |
| `reversible` | boolean | yes | False when a revert does not restore the prior state, such as a destructive migration or an external side effect. False forces major. |
<!-- aidd:end -->

`observe`:

<!-- aidd:gen fields:observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Post-release check. Exit 0 means healthy. |
| `signals` | string | no | Dashboards, SLOs, or queries a human watches. |
| `window` | string | yes | How long to watch, such as 30m, 24h, or 7d. |
| `rollback_trigger` | string | yes | The condition that starts the rollback. |
<!-- aidd:end -->

`emergency`:

<!-- aidd:gen fields:emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `severity` | `sev1` \| `sev2` \| `sev3` | yes | Incident severity. |
| `kind` | `outage` \| `degradation` \| `security` \| `data` | yes | What is broken in production. |
| `commander` | string | yes | The incident commander, a human. Named before the repair starts. |
| `ref` | string | no | Incident ticket or page id. |
| `review_due` | string | yes | Date the postmortem and the Spec backfill are due. The config sets the SLA. |
<!-- aidd:end -->

`outcome`, written after Ship and never part of the approval hash:

<!-- aidd:gen fields:outcome -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `released_at` | string | no | Date the change reached production. |
| `observe_result` | `pass` \| `fail` \| `skipped` | no | Result of the observe window. |
| `rolled_back` | boolean | no | True when the rollback ran. |
| `restored_at` | string | no | Date service was restored after a failed change (a rollback or a fix). With `released_at`, it gives the time to restore. |
| `learn_ref` | string | no | Link to the retro or the PR that fed lessons back into AGENTS.md, skills, or tests. |
| `result` | string | no | What the metric named in `hypothesis` did after the observe window: met, missed, or inconclusive, with the number. A missed hypothesis is a Learn signal for the author and the product-manager, not a rollback. |
<!-- aidd:end -->

### 4.6 Epic and Initiative

Optional containers, in the Specs folder with the same `+++` front matter. The verifier does not gate them; `aidd validate` checks them.

Epic:

<!-- aidd:gen fields:epic -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `kind` | `"epic"` | yes | Object kind. Always `epic`. |
| `id` | string | yes | Stable key. |
| `parent` | string | no | Optional Initiative id. |
| `title` | string | yes | One line. `locale` may apply. |
| `goal` | string | yes | The measurable goal of an Epic or Initiative. |
| `status` | `container_status` | yes | Initiative and Epic status. |
| `labels` | list of string | no | Up to 8 labels, lowercase letters, digits, `:` and `-`, such as `area:billing` or `customer-ask`, for filtering (`aidd next --all --label`). They never change the route or the gate, and the Spec approval hash ignores them. |
| `relations` | list of table (`relation`) | no | Typed links to other Specs, Epics, or Initiatives: blocks, blocked_by, duplicates, relates_to, implements. Bookkeeping: the gate never reads them and the Spec approval hash ignores them. |
| `owner_teams` | list of string | no | Teams with Specs under this Epic. Two or more turns on Multi-team. |
| `context` | string | no | Shared terms and constraints for every Spec under this Epic. |
| `covers` | list of string | no | The ids of the proposal needs this Epic delivers, when it came from an accepted proposal. |
<!-- aidd:end -->

Initiative:

<!-- aidd:gen fields:initiative -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `kind` | `"initiative"` | yes | Object kind. Always `initiative`. |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line. `locale` may apply. |
| `goal` | string | yes | The measurable goal of an Epic or Initiative. |
| `status` | `container_status` | yes | Initiative and Epic status. |
| `labels` | list of string | no | Up to 8 labels, lowercase letters, digits, `:` and `-`, such as `area:billing` or `customer-ask`, for filtering (`aidd next --all --label`). They never change the route or the gate, and the Spec approval hash ignores them. |
| `relations` | list of table (`relation`) | no | Typed links to other Specs, Epics, or Initiatives: blocks, blocked_by, duplicates, relates_to, implements. Bookkeeping: the gate never reads them and the Spec approval hash ignores them. |
| `owner_team` | string | no | Team accountable for the outcome. |
| `proposal` | string | no | The accepted proposal this Initiative delivers, so every change under it traces back to what was promised. |
<!-- aidd:end -->

### 4.7 Proposal

A Proposal asks someone outside the team to decide whether work happens and on what terms, before any code: a client choosing a supplier (a bid, a pitch, a response to a request for proposal), or the company's own leadership, an investment committee, or an architecture board deciding on a change. It lives in its own folder under `proposals_dir` (default `proposals/`), one folder per proposal, where each role writes its part beside `proposal.md`. The verifier does not gate it; `aidd validate` checks it.

**Proposal or Initiative?** Ask who decides. When someone outside the team must agree before anyone commits, write a Proposal. When the team already has the mandate, skip it and plan an Initiative, or go straight to a Spec. A Proposal asks for a decision; an Initiative organizes work already decided. An accepted Proposal becomes an Initiative with `aidd proposal convert`: the Initiative names the Proposal, and each Epic `covers` the needs it delivers, so every Spec written later traces back to what was promised. Needs answered `not_met` promise nothing and reach no Epic.

**Two decisions, both a person's.** A Proposal has its own pair of human decisions, like a Spec's: `go_no_go` before the team spends effort drafting, and `sign_off` before it is sent, with its price, commitments, assumptions, and exclusions. The status records how far it has come (exploring, no_go, drafting, ready, submitted, accepted, rejected, withdrawn), and `aidd validate` refuses a status the decisions do not support, and a decision recorded by an agent account. The file is a record, not proof: when the proposal lives in a repository behind the gate, the pull request that records a decision needs that person's approval.

**Confidential by default.** A proposal's material belongs to its addressee: it stays in its folder, is never copied into another proposal, and a client's proposals live where only people cleared for that client can read them.

<!-- aidd:gen fields:proposal -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `kind` | `"proposal"` | yes | Object kind. Always `proposal`. |
| `id` | string | yes | Stable key. |
| `title` | string | yes | One line. `locale` may apply. |
| `audience` | `client` \| `internal` | yes | `client`: a bid, pitch, or response to a request for proposal. `internal`: a change put to the company's own decision makers, such as leadership, an investment committee, or an architecture board. |
| `addressee` | string | yes | Who receives the proposal and decides, such as "Acme Corp procurement" or "the executive committee". |
| `goal` | string | yes | What the addressee gets if they say yes, as an outcome they can check. |
| `status` | `exploring` \| `no_go` \| `drafting` \| `ready` \| `submitted` \| `accepted` \| `rejected` \| `withdrawn` | yes | exploring: qualifying, before the go/no-go decision. no_go: a person decided not to pursue it. drafting: a person decided to go. ready: a person signed it off. submitted: sent to the addressee. accepted, rejected, or withdrawn: the outcome. |
| `due` | string | no | When the addressee needs it. |
| `confidential` | boolean | no | The material stays in this proposal's folder and is never reused for another addressee without permission. Default true. |
| `owner_team` | string | no | Team accountable for the proposal. |
| `go_no_go` | table | no | The first human decision: pursue it or not, before the team spends effort drafting. |
| `sign_off` | table | no | The second human decision: the proposal may be sent, with its price, commitments, assumptions, and exclusions. |
| `needs` | list of table | no | What the addressee needs, one entry each, and how the proposal answers it: the compliance matrix of a bid, or the concerns a business case must meet. |
| `options` | list of table | no | The real alternatives, doing nothing included when it is one. |
| `estimate` | table | no | A range, never a single number: low, most likely, and high, and what it rests on. |
| `assumptions` | list of string | no | What must hold for the proposal to stand. Each is a risk if it turns out false. |
| `exclusions` | list of string | no | What the proposal does not include, said plainly. |
| `risks` | list of table | no |  |
| `questions` | list of table | no | Questions for the addressee, with the answer once known: the clarification log. |
<!-- aidd:end -->

## 5. The loop

*Informative. The verifier checks the gate rules (§7), not the steps.*

Five core steps, two human approvals, three lanes; Plan before and Learn after are optional. Each lane runs only the steps its risk needs.

```text
(Plan) → Specify → [Spec approval] → Implement ⟲ Verify → Review → [Merge approval] → Ship → (Learn)
```

The loop is a versioned contract: `loop.version` in `schemas/roles.json` (1.0.0, shown in §5.2) follows semantic versioning. A change that adds, removes, or reorders a step, a human approval, or a lane is a major change and bumps the major number; gate events record the version as `loop_version`, so metrics never mix two loops without saying so.

**The entry rule.** Every change starts with `aidd next`, which computes the minimum route from the paths and picks the lane; the gate recomputes it from the real diff and can only raise it (§6). Assessment is not a step of the loop but the way into it, and it takes seconds. The fast lane is the default: a change starts on the fast lane unless the computed minimum route needs a Spec. A production repair is the one lane a person declares rather than computes (emergency).

**Clarify** is the entry rule's precondition. Before the lane is chosen, the open questions go to the author, at most five, ordered by whether the answer changes the route, the scope, or the acceptance. A question that could change the route keeps confidence low, and low confidence stops the agent; the rest become assumptions in the Spec. The readings of an ambiguous request are presented, not picked.

Plan runs before the loop only when the work is bigger than one Spec. Learn runs after it on a signal (a Merge approval rejection, a rollback, an incident, a missed hypothesis, or three failed retries) and on a cadence, as a retrospective on the loop itself.

| Lane | Routes | Steps | Human decisions |
| --- | --- | --- | --- |
| **Fast** (the default) | minor, standard | Implement ⟲ Verify → Review → Ship | one Merge approval (none for standard) |
| **Spec** | normal, major (computed) | Specify → Spec approval → Implement ⟲ Verify → Review → Merge approval → Ship | Spec approval and Merge approval; a specialist reviewer on major |
| **Emergency** | emergency (declared) | Implement ⟲ Verify → Review → Ship → Learn | the incident commander and the route's required approvals; the review is due by `review_due` |

| Step | Done when | Stops |
| --- | --- | --- |
| Plan *(optional)* | an Initiative, Epics, and ranked Spec stubs that a human agrees to | the outcome or the owner is unclear |
| Specify | a Spec with Context, executable Acceptance, Tasks with scope, the test files written, rollback; observe and a pre-mortem on major; the route computed from the Spec's scope (`aidd new spec --paths`, then `aidd next`) | missing owner; acceptance not executable |
| Spec approval | an eligible Approver approves the current hash of the Spec and its tests, ideally naming the commit (§8) | changes requested (back to Specify); the Spec or a test changes (the approval voids) |
| Implement | each Task's diff stays inside its scope and holds the minimum change; every command is green on head and every new_behavior command was red on base | at most 3 retries per Task on implementation errors or flakes; a wrong Spec returns to Specify |
| Verify | the Spec's tests run again on the exact head, and the built change is exercised against each Acceptance line; the report starts with the head SHA it checked | a failure or a mismatch returns to Implement; a new push makes the report stale |
| Review | the PR/MR is ready; findings (human, or an agent reviewer's) are answered | changes requested (back to Implement) |
| Merge approval | as many eligible Approvers as the profile requires for the route approve the head commit; a specialist reviewer on major; Policy allows | changes requested (back to Implement); a freeze (except emergency) |
| Ship | the platform merges; the release interface deploys, progressively on major; the observe window passes or the rollback trigger fires | rollback: status rolled_back |
| Learn *(on a signal or a cadence)* | on a signal: a lesson PR/MR (AGENTS.md, tests, rules, skill) linked in outcome.learn_ref; on a cadence: a retrospective whose improvements re-enter the loop at Plan as new changes ([§12](#12-ship-and-learn)) | the incident review is overdue (`aidd validate`) |

**Implement ⟲ Verify** is one tight loop.

- **Implement.** Scope is checked at every edit, every changed line traces to an Acceptance line or the Task, and `aidd test` runs the commands locally.
- **Verify**, a step of its own with its own role, runs the Spec's tests on the exact head the Approver will see, and exercises the built change the way a user or caller would.
- **The evidence** is still the runner's exit codes, in CI and in `aidd test`. The verifier role's report only routes the work: clean, on to Review; a failure or a mismatch, back to Implement.

**Human feedback** sends work back on four paths, each a normal part of the loop and drawn dashed in the loop diagram ([TEAM.md](TEAM.md#the-loop-by-role)): Spec approval with changes requested returns to Specify; Merge approval with changes requested, or a review comment, returns to Implement; Ship sends an incident, a rollback, or a missed hypothesis to Learn; and Learn's lesson re-enters at Plan as a new change. A missed hypothesis is a product decision, taken at Plan, not a fix an agent starts on its own.

Spec approval is enforced by hash: the approved Spec and tests must be the ones shipped. The skill obtains Spec approval before implementation, on a Spec-first draft PR/MR; an approval that names its commit proves it (§8).

### 5.1 Status

Status is derived from the gate and the PR/MR; the Spec's `status` is optional bookkeeping, written only through these transitions:

<!-- aidd:gen vocab:status -->
| Token | Meaning |
| --- | --- |
| `draft` | Being assessed or specified; nothing approved yet. |
| `ready` | Spec approval: a human approved the Spec hash. Implementation may start. |
| `in_progress` | Tasks are being implemented inside their scope, verified as they go. |
| `in_review` | Tests are green on head; the change waits for Merge approval. |
| `released` | Merged and deployed. The observe window runs now. |
| `done` | The observe window passed, or none was required. Terminal. |
| `rolled_back` | The rollback trigger fired, or a person rolled it back. Terminal; Learn follows. |
| `blocked` | Waiting on blocked_on. |
| `cancelled` | Stopped by a decision, a freeze, or a final reject. Terminal. |
<!-- aidd:end -->

`draft → ready → in_progress → in_review → released → done | rolled_back`. There are also shortcuts:

- `draft → in_progress` on routes without Spec approval
- `in_progress → draft` or `in_review → draft` for a wrong Spec
- `in_review → in_progress` for a wrong diff
- any non-terminal status to `blocked` (with `blocked_on`) or to `cancelled`

A failed gate adds no status.

**Status groups.** Every status of every object falls into one of five groups, so a board, a report, or a tracker mirrors any object by its group without learning each vocabulary. `aidd next --json` gives each step's `group`. The gate never reads it.

<!-- aidd:gen status:groups -->
| Group | Meaning | Spec | Epic and Initiative | Proposal |
| --- | --- | --- | --- | --- |
| `backlog` | Written down, not yet planned or approved: a draft, or a proposal still being qualified. | `draft` | `draft` | `exploring` |
| `unstarted` | Approved and ready; nobody has started it. | `ready` | none | none |
| `started` | Open work: being built, waiting for a person, blocked, or watched after release. | `in_progress`, `in_review`, `released`, `blocked` | `active`, `blocked` | `drafting`, `ready`, `submitted` |
| `completed` | Finished: done, rolled back (the work ended and Learn follows), or a proposal the addressee accepted. | `done`, `rolled_back` | `done` | `accepted` |
| `cancelled` | Stopped without delivery: cancelled, rejected, withdrawn, or a no-go. | `cancelled` | `cancelled` | `no_go`, `rejected`, `withdrawn` |
<!-- aidd:end -->

**Triage.** A Spec an agent proposed on its own (`proposed_by = "agent:<role>"`, from a role in `[agents] proactive_roles`) stays a draft until a person records `triage`: accepted, declined, duplicate (with `duplicate_of`), or snoozed (with `until`), with who and when. `aidd next` puts the triage in front of a person first, hides a snoozed Spec until its date, and drops a declined or duplicate one. `aidd validate` fails a Spec an agent proposed that is past draft without an accepted triage, and a triage recorded by an agent or an agent account.

<!-- aidd:gen fields:triage -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `decision` | `accepted` \| `declined` \| `duplicate` \| `snoozed` | yes | accepted: the work goes ahead. declined: it does not (set the status to cancelled). duplicate: another item carries it (name it in duplicate_of). snoozed: decide again on `until`; `aidd next` hides it until then. |
| `by` | string | yes | The person who decided. Never an agent or an agent account: `aidd validate` fails one. |
| `on` | string | yes | The date of the decision. |
| `until` | string | when decision is `snoozed` | Snoozed only: the date the item comes back for a decision. |
| `duplicate_of` | string | when decision is `duplicate` | Duplicate only: the item that carries the work. |
<!-- aidd:end -->

**Relations and labels.** A Spec, Epic, or Initiative MAY carry `relations` (typed links to other items) and up to eight `labels`. `aidd validate` checks that each relation's target exists and that `blocks` and `blocked_by` form no cycle; `aidd next` shows an item `blocked_by` unfinished work as blocked, naming what it waits on, and treats a duplicate as cancelled. A Task's `depends_on`, which orders Tasks inside one Spec, is unchanged. Both are bookkeeping: the gate never reads them, a label never changes the route, and the Spec approval hash ignores them, as it ignores `triage`.

<!-- aidd:gen fields:relation -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `type` | `blocks` \| `blocked_by` \| `duplicates` \| `relates_to` \| `implements` | yes | blocks: the other item waits for this one. blocked_by: this one waits for the other. duplicates: this one repeats the other, which carries the work, so `aidd next` treats this one as cancelled. relates_to: see also. implements: this one delivers the other. |
| `id` | string | yes | The other Spec, Epic, or Initiative, by id, in the Specs folder. |
<!-- aidd:end -->

**The handoff note.** When an agent stops, it ends with a handoff note, and writes it into the Spec (or the PR/MR body) as a fenced block with the info string `aidd-handoff`, holding TOML:

````text
```aidd-handoff
done = "T1: total() returns 0 for an empty cart (src/cart.py)"
next = "verifier"                 # a role id, or "spec-approval" or "merge-approval"
needs = "none"                    # a decision only a person can give, or "none"
stopped_at = "none"               # the stop rule that fired, or "none"
spend = "41k tokens"              # optional
```
````

`aidd next` reads the latest block in the Spec: `next` names the role that has the work ("your agent (verifier)"), or puts the Spec in the Approver inbox when it asks for Spec approval or Merge approval, and a `needs` other than none becomes a step for a person. `aidd validate` warns about a block it cannot read. The gate never reads the note, and the Spec approval hash leaves out every `aidd-handoff` block, so writing one never voids an approval.

**The why chain and the backlog.**

- **Why.** Each Spec step in `aidd next` says why the work matters, widest first: the config's `mission`, its `goal`, the Spec's Initiative and Epic, and its `hypothesis` (or, once measured, its outcome).
- **The backlog.** `aidd next --all` reads every object under the Specs folder at HEAD, not only this branch's, and filters it: `--mine`, `--agent[=ROLE]` (Tasks an agent may start now), `--blocked`, `--label`, and `--waiting-on-me`, the Approver inbox.
- **History.** `aidd log <spec>` shows one Spec's status transitions with the time spent in each (from `git log`), its locally recorded approvals, and the `Assisted-by:` trailers of the commits touching its scope.

**The human queue.** Approvals are the scarce resource. `gates.max_open_per_approver` (3 under team, org, and regulated; off under solo) makes `aidd next --waiting-on-me` and `aidd next --all` warn when one Approver holds more open waits, and `gates.escalate_after_minutes` with `owners.backup_approvers` makes `aidd next` mark a wait past the limit and name the backup pool. Both only change what `aidd next` says: they never approve anything, never make anyone eligible, and never change the gate's decision.

### 5.2 The two loops: human governance and agentic execution

The loop is two loops, and naming them is what makes the two approvals legible.

<!-- aidd:gen roles:loops -->
*Loop contract version 1.0.0: a change that adds, removes, or reorders a step, an approval, or a lane bumps its major number.*

**The way in.** Every change starts with `aidd next`, which computes the minimum route from the paths and picks the lane; the gate recomputes it from the real diff and can only raise it. The fast lane is the default: a change starts there unless the computed route needs a Spec. Clarify first: at most five questions to the author, and a question whose answer could change the route keeps confidence low, which stops the agent.

**Outer loop — human strategy and governance.** It decides what is worth doing at all (Plan), whether the Spec an agent drafted may be built (Spec approval), whether the built head may merge (Merge approval), whether it ships and how it rolls out (Ship), and what the change and the process teach (Learn). An agent drafts for every one of these and decides none: no role approves, merges, or adopts. Where the outer loop needs a specialist it names a pool — security, data, privacy, finance, compliance — or an incident commander, and those are humans too.

**Inner loop — autonomous agentic execution.** An agent drafts the contract, then builds against it. In Specify it writes the Spec and its tests, which Spec approval then freezes; in Implement ⟲ Verify it builds inside that frozen contract while the verifier role re-runs the Spec's tests on the exact head, until the runner is green or the work is blocked; in Review it reads what it built adversarially. It is bounded, not free: the Task's scope is the write area the edit-time guard checks, a failing test returns to Implement rather than being weakened, three retries make it blocked, and the stop list hands it back.

**What crosses between them.** Two artifacts cross, and both are machine-checkable. Inward: the Spec approval hash, which freezes the Spec, its test files, and its design files, so the inner loop cannot move the target it is graded against. Outward: the gate record and the commit status, which carry the runner's exit codes bound to a head and base SHA, the diff the platform measured, and the approvals it saw. Prose is never evidence: the gate binds to the hash, the exit codes, and the SHAs, and never to a summary, a claim that tests pass, or a chat handoff. Humans do read the ranked review report and the handoff note's Needs line — that is what Merge approval and the stop list are for — but nothing a human reads that way can make the gate pass.

| Loop | Who decides | Steps |
| --- | --- | --- |
| Outer | a human: by approval at Spec approval and Merge approval, by recorded agreement for Plan, Ship, and Learn | Plan, Spec approval, Merge approval, Ship, Learn |
| Inner | the agent: it drafts the contract in Specify, then works inside it once Spec approval freezes it | Specify, Implement ⟲ Verify, Review |

Control passes at the two approvals on machine-checkable evidence, and at Plan, Ship, and Learn on a recorded human decision:

- Spec approval: a human approves the Spec and its tests, and the hash freezes them
- Merge approval: a human approves the head commit, on the evidence the platform collected

**Human feedback.** A person sends work back on these paths, drawn dashed in the loop diagram; each is a normal part of the loop, not a failure:

- **Spec approval → Specify** (changes requested): the author asks for a different Spec, tests, or design; the Specify roles revise them and ask for a new Spec approval.
- **Merge approval → Implement** (changes requested): the head is not approved; review comments, a person's or an agent reviewer's, go back to Implement the same way, and the new head needs a new Verify and a new Merge approval.
- **Ship → Learn** (incident, rollback, missed hypothesis): what production showed goes to Learn, never straight back into code.
- **Learn → Plan** (a new change): a lesson becomes a new change that starts with `aidd next`; a missed hypothesis is a product decision, taken at Plan (keep, change, or remove the feature), not a fix an agent starts on its own.
<!-- aidd:end -->

Agile rewritten for agents, why the loop is fast, and its mapping to the DevOps loop, ISO/IEC/IEEE 12207, ITIL 4, and PDCA are explained in [RATIONALE.md](RATIONALE.md#the-loop-compared).

## 6. Routes

*Normative.*

Computing the route is the loop's entry rule (§5), not one of its steps: `aidd next` (and `aidd new spec --paths`, before any code) runs it on the planned paths before the first step, and the verifier runs it again on the real diff at every gate run.

**The core: an author makes one of three choices.** No Spec (`minor`), a Spec (`normal`), or a production repair (`emergency`). Bots use `standard`. The route names follow ITIL change types, so a change manager reads them without a glossary, and `standard_changes` and `risk_rules` are ITIL change models: pre-assessed classes of change with a known route and known reviewers.

The verifier MUST compute the minimum route from the real diff, in this order (first match wins):

| Order | Route | Select when |
| --- | --- | --- |
| 1 | emergency | production is broken now (outage, degradation, active security or data incident) and this change is the repair |
| 2 | major | protected path; dimension data, security, privacy, financial, or compliance; not reversible; type data, security, or compliance; or a risk rule says so |
| 3 | standard | the change matches a configured standard change class exactly, with platform-signed commits, and nothing requires major |
| 4 | minor | confidence high, one Task, no risk dimension, no rule above minor, no binary file, no contract change (a judgment rule the verifier cannot check), within the minor budget |
| 5 | normal | otherwise |

- The verifier MUST fail a declared route below the computed minimum, with one exception: when a Spec-backed `normal` change's diff requires major, the verifier MUST raise it to major, apply the major route's rules (each specialist pool the reasons name, an observe block, the profile's stricter settings), and warn instead of failing.
- A repository MAY declare `major` up front. A declared route that needs a Spec it does not have (a `minor` block whose diff requires `normal` or more) fails.
- The verifier MUST fail a change whose paths imply a dimension that an inline block omits (a Spec gets a warning).
- `emergency` is declared, never computed: only a person can say production is broken. It still passes through every computed rule; its position 1 in the table means only that it is checked first.
- A standard change class covers rules up to normal, never major.

**The minor route trusts its declaration.** An inline block has no human before the diff: its `scope` and tests are the agent's word. A minor block MAY leave `scope` out, in which case the changed paths are its scope and the record says so. The controls are the computed minimum route; the minor budget and the binary-file rule; the ban on catch-all scope; the requirement of a repository suite (or `evidence.status_checks`) that inline tests can only add to; and the Merge approval review of the actual diff.

A major change names the specialist pools that must review it: the pool of each major dimension it carries (the table below), the `reviewers` of every risk rule that made it major, and `security` for a protected path. A major change with no other pool needs `security`.

| Dimension | Pool |
| --- | --- |
| `data` | `data` |
| `security` | `security` |
| `privacy` | `privacy` |
| `financial` | `finance` |
| `compliance` | `compliance` |

<!-- aidd:gen vocab:route -->
| Token | Meaning |
| --- | --- |
| `standard` | A pre-approved change class from config standard_changes, such as a bot's dependency patch. Merges on green tests with no human approval. Never touches protected paths. |
| `minor` | Small, reversible, one Task, no risk dimension, within the minor budget. No Spec file needed; one Merge approval. |
| `normal` | Everything that is not minor, standard, major, or emergency. Spec, Spec approval, SHA-bound tests with red-then-green, one Merge approval. |
| `major` | Touches a protected path, data, security, privacy, money, or compliance, or cannot be reverted. Normal plus a specialist review, an observe block, and stricter profile gates. Computed by the gate, never guessed. |
| `emergency` | Production is broken now and this change is the repair. Allowed under a freeze. Smoke tests still run; the Spec and the review follow by review_due. |
<!-- aidd:end -->

Risk dimensions:

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
<!-- aidd:end -->

Confidence:

<!-- aidd:gen vocab:confidence -->
| Token | Meaning |
| --- | --- |
| `high` | Every fact that could change the route is known. open_questions is empty. |
| `medium` | Some facts are missing, and none of them could change the route. List them; the gate does not act on medium. |
| `low` | A missing fact could change the route. Stop and ask. |
<!-- aidd:end -->

**Built-in path rules.** Matching ignores case. The verifier MUST treat every protected path as major, and a repository cannot disable them. Every repository file a bound Policy command runs (such as `./scripts/aidd-policy`) is protected too, because it executes inside the trusted gate, and so is every file a bound Observe command runs, because release tooling trusts it. A repository MAY disable a `baseline:` rule by name, or narrow it with `rule_exclusions`; that change is itself protected.

<!-- aidd:gen baseline -->
| Rule | Minimum route | Dimensions | Paths | Excluded |
| --- | --- | --- | --- | --- |
| protected (cannot be disabled) | major | none | <details><summary>110 paths</summary>`.aidd/**`, `.github/workflows/**`, `.github/actions/**`, `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS`, `.gitlab-ci.yml`, `.gitlab/**`, `**/AGENTS.md`, `**/CLAUDE.md`, `**/GEMINI.md`, `.agents/**`, `.claude/**`, `.codex/**`, `.cursor/**`, `.cursorrules`, `.windsurfrules`, `.github/copilot-instructions.md`, `.github/instructions/**`, `.github/skills/**`, `.mcp.json`, `.vscode/mcp.json`, `**/AGENTS.override.md`, `**/CLAUDE.local.md`, `.gemini/**`, `.github/prompts/**`, `.github/agents/**`, `.devcontainer/**`, `orca.yaml`, `.worktreeinclude`, `.husky/**`, `.githooks/**`, `.pre-commit-config.yaml`, `lefthook.yml`, `.lefthook.yml`, `.gitmodules`, `.github/dependabot.yml`, `.github/dependabot.yaml`, `renovate.json`, `renovate.json5`, `.renovaterc`, `.renovaterc.json`, `.github/renovate.json`, `.github/renovate.json5`, `Jenkinsfile`, `**/Jenkinsfile`, `.circleci/**`, `azure-pipelines.yml`, `.azure-pipelines/**`, `.buildkite/**`, `bitbucket-pipelines.yml`, `.drone.yml`, `.travis.yml`, `.kiro/**`, `.roo/**`, `.clinerules`, `.clinerules/**`, `.windsurf/**`, `.continue/**`, `.aider*`, `.junie/**`, `.amazonq/**`, `.trae/**`, `.augment/**`, `**/AGENT.md`, `.github/copilot/**`, `action.yml`, `action.yaml`, `**/.github/actions/**`, `cloudbuild.yaml`, `cloudbuild.yml`, `.tekton/**`, `.woodpecker.yml`, `.woodpecker.yaml`, `.woodpecker/**`, `install.sh`, `**/install.sh`, `pyproject.toml`, `**/pyproject.toml`, `SECURITY.md`, `**/SECURITY.md`, `GOVERNANCE.md`, `RELEASING.md`, `REVIEW.md`, `setup.py`, `setup.cfg`, `.github/hooks/**`, `.agent/rules/**`, `.devin/**`, `.cline/**`, `.roorules`, `.roomodes`, `.amp/**`, `opencode.json`, `opencode.jsonc`, `.opencode/**`, `.zed/**`, `.rules`, `WARP.md`, `.warp/**`, `QWEN.md`, `.qwen/**`, `.augment-guidelines`, `.factory/**`, `.goosehints`, `.goose/**`, `.grok/**`, `.vibe/**`, `.aiderignore/**`, `CONVENTIONS.md`</details> | none; also every file a bound Policy or Observe command runs |
| `baseline:dependencies` | normal | third_party | `**/package.json`, `**/package-lock.json`, `**/pnpm-lock.yaml`, `**/yarn.lock`, `**/bun.lockb`, `**/bun.lock`, `**/requirements*.txt`, `**/pyproject.toml`, `**/poetry.lock`, `**/uv.lock`, `**/Pipfile`, `**/Pipfile.lock`, `**/go.mod`, `**/go.sum`, `**/Cargo.toml`, `**/Cargo.lock`, `**/Gemfile`, `**/Gemfile.lock`, `**/pom.xml`, `**/build.gradle`, `**/build.gradle.kts`, `**/*.csproj`, `**/packages.lock.json`, `**/composer.json`, `**/composer.lock`, `**/Package.swift`, `**/Package.resolved`, `**/pubspec.yaml`, `**/pubspec.lock`, `**/.npmrc`, `**/.yarnrc`, `**/.yarnrc.yml`, `**/.pnpmfile.cjs`, `**/setup.py`, `**/setup.cfg`, `**/requirements*.in`, `**/go.work`, `**/go.work.sum`, `**/*.gradle`, `**/*.gradle.kts`, `**/gradle.properties`, `**/libs.versions.toml`, `**/.terraform.lock.hcl`, `**/Podfile`, `**/Podfile.lock`, `**/Chart.lock`, `**/nuget.config`, `**/NuGet.Config`, `**/settings.xml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:build-tooling` | normal | third_party | `**/gradle/wrapper/**`, `**/gradlew`, `**/gradlew.bat`, `**/mvnw`, `**/mvnw.cmd`, `**/.mvn/**`, `**/Makefile`, `**/justfile`, `**/Taskfile.yml`, `**/Taskfile.yaml`, `**/noxfile.py`, `.tool-versions`, `.nvmrc`, `.node-version`, `.python-version`, `mise.toml`, `.mise.toml`, `.gitattributes` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:containers` | normal | third_party | `**/Dockerfile`, `**/*.dockerfile`, `**/Containerfile`, `**/docker-compose*.yml`, `**/docker-compose*.yaml`, `**/compose.yaml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:test-config` | normal | none | `**/jest.config.*`, `**/vitest.config.*`, `**/pytest.ini`, `**/conftest.py`, `**/tox.ini`, `**/.coveragerc`, `**/phpunit.xml`, `**/karma.conf.*`, `**/playwright.config.*`, `**/cypress.config.*` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:quality-config` | normal | none | `**/.eslintrc`, `**/.eslintrc.*`, `**/eslint.config.*`, `**/tsconfig.json`, `**/tsconfig.*.json`, `**/.prettierrc`, `**/.prettierrc.*`, `**/prettier.config.*`, `**/biome.json`, `**/biome.jsonc`, `**/ruff.toml`, `**/.ruff.toml`, `**/mypy.ini`, `**/.mypy.ini`, `**/.flake8`, `**/.pylintrc`, `**/.golangci.yml`, `**/.golangci.yaml`, `**/.golangci.toml`, `**/.golangci.json`, `**/clippy.toml`, `**/.clippy.toml`, `**/rustfmt.toml`, `**/.rustfmt.toml`, `**/.rubocop.yml`, `**/phpstan.neon`, `**/phpstan.neon.dist`, `**/detekt.yml`, `**/.swiftlint.yml`, `**/analysis_options.yaml`, `**/.eslintignore`, `**/.prettierignore`, `**/.stylelintrc*`, `**/pyrightconfig.json`, `**/.clang-tidy`, `**/.swiftformat`, `**/.scalafmt.conf`, `**/.markdownlint*`, `**/deno.json`, `**/deno.jsonc` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:iac` | normal | availability | `**/*.tf`, `**/*.tfvars`, `**/terraform/**`, `**/k8s/**`, `**/kubernetes/**`, `**/helm/**`, `**/Chart.yaml`, `**/charts/*/templates/**`, `**/*.bicep`, `**/cloudformation/**`, `**/pulumi/**`, `**/kustomization.yaml` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:migrations` | major | data | `**/migrations/**`, `**/migrate/**`, `**/alembic/**`, `**/db/migration/**`, `**/db/changelog/**`, `**/db/schema.rb`, `**/schema.prisma`, `**/flyway/**`, `**/liquibase/**` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:auth` | major | security | `**/auth/**`, `**/authn/**`, `**/authz/**`, `**/iam/**`, `**/rbac/**`, `**/permissions/**`, `**/*.rego` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**` |
| `baseline:secrets-crypto` | major | security | `**/crypto/**`, `**/secrets/**`, `**/.env`, `**/.env.*`, `**/*.pem`, `**/*.key`, `**/*.p12` | `**/vendor/**`, `**/node_modules/**`, `**/third_party/**`, `**/.env.example`, `**/.env.sample`, `**/.env.template`, `**/.env.dist` |
<!-- aidd:end -->

### 6.1 Paths and globs

Paths are repository-relative with `/` separators. A verifier MUST match globs this way:

- `*` and `?` stay inside one path segment, `**` spans segments, and `**/` may match nothing.
- A pattern without a wildcard matches that path and everything under it (`src/checkout` covers `src/checkout/x.py`). A trailing `/` or `/**` means the same, so `.claude/**` also covers a file named `.claude`.
- Brackets are literal characters, never a class.
- Matching that adds a requirement ignores case: protected paths, risk rules, `when_changed`, and `owners.paths`. Matching that grants scope or an exemption is exact: `scope`, `tests.files`, `scope_exempt_paths`, `budget_exclude_paths`, and rule exceptions.

## 7. Evidence and the verifier

*Normative.*

The verifier MUST be a pure function from a context (`schemas/context.schema.json`) to a decision: `pass`, `pending` (waiting on a human or a runner), or `fail` (something must change). Adapters build the context; any CI MAY build one and call `aidd gate --context`.

For every rule below, the verifier MUST emit the listed level when the rule does not hold, and the decision is `fail` if any rule fails, else `pending` if any rule is pending, else `pass`.

<!-- aidd:gen rules:method -->
| Rule | Level on miss | Holds when |
| --- | --- | --- |
| `context` | fail | the adapter's context validates against its schema |
| `internal` | fail | the verifier ran without error; any crash fails closed and the gate posts `error` |
| `config` | fail, pending, or warn | the base branch has a valid `.aidd/config.toml` (pending when only the change itself adds one, fail when there is none); outside solo, `owners.approvers` is not empty |
| `change_request` | fail or warn | exactly one valid `toml aidd` block; with `spec`, only `spec` and `trace_id`; an inline emergency names its `backfill`; a bot PR without a block matches its standard change class |
| `spec` | fail | normal and major name a Spec that exists at head, validates, and lints |
| `confidence` | fail | not `low` |
| `route` | fail or warn | the declared route is at least the computed minimum, except that a Spec-backed normal change is raised to major (warn); an inline block declares every implied dimension (a Spec gets a warning) |
| `scope` | fail or warn | every changed path (rename sources too) is inside a Task's scope, the Spec, its backfill, a test or design file, or `scope_exempt_paths`; no scope pattern matches every path; a declared inline scope and the test files do not overlap (a minor change that declares no scope takes its changed paths); every Task of a Spec changes something in its scope (warn: the plan and the diff disagree) |
| `budget` | fail | changed lines are within `max_changed_lines` for the route, excluding `budget_exclude_paths` and, for a Spec, the Spec and its test and design files Spec approval froze (standard uses its class limit; emergency has none) |
| `merge_queue` | fail | for a merge-queue entry (`merge_group` in the context): its commit's tree is exactly the approved head merged into the commit the entry was built on; an entry built on another entry passes only when the queue merges a group once every entry passed |
| `authors` | fail or warn | the platform returned the whole commit list (fail); every commit author maps to a platform account, unless the platform itself blocks committers from approving (`unlinked_authors`: warn, fail under regulated) |
| `tests` | pending, fail, or warn | the repository has tests (a suite, `evidence.status_checks`, or the Spec's); a minor change has the suite or `status_checks`; every applicable command (`when_changed` included) has a green result on this exact head and base, from a test run of the change's own branch, with the declared command; names are unique; every `status_checks` name succeeded on head, from an allowed app and the change's own branch; with `evidence.signer_workflow`, the evidence carries that workflow's attestation; the evidence is not partial (`aidd test --changed`); in a merge queue, the head and base are the merge-group commit and the commit it was built on |
| `red_green` | fail (warn in solo) | on Spec-backed normal and major: every `new_behavior` command failed on base (a non-zero exit other than 126 or 127; a compile or import error counts) with the declared command, and a feat or fix change has one |
| `spec_approval` | pending or warn | on the profile's routes, an eligible Approver (not an author, except under solo) approved the current Spec hash; each owner area the Spec touches has an approval from its owners; under `spec_approval_proof = require`, the approval names a commit that held only the Spec and its frozen files; on a local context under `gates.local_approvals = "signed"`, only approvals the adapter marked `verified` count (warn when one was dropped); with a `tenant`, an approval by another tenant's identity never counts (warn) |
| `merge_approval` | pending or warn | as many eligible Approvers as the route requires (`gates.approvals`) approved the head commit; each owner area the diff touches has an approval from its owners; no Approver, specialist reviewer, or path owner's latest review requests changes; on a local context under `gates.local_approvals = "signed"`, only approvals the adapter marked `verified` count (warn when one was dropped); an agent account never approves, and its platform approval warns; with a `tenant`, an approval by another tenant's identity never counts (warn) |
| `edited_comments` | warn | no edited comment was ignored |
| `specialist_review` | pending or fail | major, and emergency when a protected path changes: `specialist_approvals` approvals on head from each pool the reasons name (`owners.reviewers`; an unbound pool falls back to `security`); under `specialist_spec_approval`, each pool also approved the Spec hash |
| `policy` | fail or warn | Policy allows; a freeze passes only emergency; a required Policy is bound; unreachable is deny |
| `policy:<rule>` | as reported | each finding the Policy command reports |
| `emergency` | fail, pending, or warn | the emergency block is complete; `review_due` falls within `emergency.review_sla_days` (default 2) of the day the change opened or its head was last pushed, whichever is later; the backfill Spec is committed with the same `review_due`; the commander is a human eligible Approver, not an author or agent, and approved the head |
| `observe` | fail | the profile's routes carry an `observe` block |
| `provenance` | fail or warn | `assisted_by` is set whenever a commit names an agent: an `Assisted-by:` trailer, a `Co-authored-by:` agent (the baseline's `agent_coauthors`), or an author in `identities.bots`; under regulated, every non-merge commit carries a trailer (`Assisted-by: none` when no agent wrote it) |
| `standard_change` | fail | the class exists and the profile allows it; paths, authors, and the line limit fit; every commit has a platform-verified signature |
| `draft` | pending | the PR/MR is not a draft |
<!-- aidd:end -->

Evidence (`aidd test`) records, for every command and phase, the command, exit, status (`passed`, `failed`, `timeout`, `not_started`), log, and times, all bound to `head_sha`:

<!-- aidd:gen fields:evidence -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `head_sha` | string | yes | The commit the green results ran on. |
| `base_sha` | string | yes | The merge base the red results ran on. |
| `runner` | table | no | Which CI run produced this file. |
| `results` | list of table | yes | One entry per command and phase. |
| `partial` | boolean | no | True when `aidd test --changed` ran only the commands the working-tree diff selects. A local convenience: the gate never accepts partial evidence. |
<!-- aidd:end -->

The verifier MUST count a red result only when its status is `failed` with an exit code other than 126 or 127. A timeout or a missing command proves nothing.

The verifier MUST NOT accept partial evidence (`partial = true`, written by `aidd test --changed` or `--watch`, which run only the commands the working tree's changes select): it holds `tests` pending until a full run.

<a id="merge-queue-evidence"></a>For a merge-queue entry the context carries `merge_group`, and the rules bind as follows:

- Approvals, Spec approval, scope, and every other rule still judge the pull request head (`head_sha`) and its diff from where it meets the entry's parent: an approval of the head is what the queue may ship.
- The evidence MUST be for the merge-group commit (`merge_group.sha`) and MUST have run red against the commit the entry was built on (`merge_group.base_sha`); green on the pull request head does not count, because the merge-group commit also holds whatever landed on the base since.
- The `merge_queue` rule fails unless the merge-group commit's tree is exactly the approved head merged into `merge_group.base_sha` (the adapter computes both trees with git; a conflict fails too), so an entry can carry nothing nobody approved and lack nothing they did.
- An entry built on another entry (`stacked`) also carries that entry's changes, which only its own gate run judged; it passes only when the platform is confirmed to merge a group once every entry in it passed (`all_green`).

<a id="change-record"></a>**The agent change record.** With `--record`, the gate MUST also write, beside the gate record, an [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) of the decision (`change-record.intoto.json`; `change-record-<n>.intoto.json` when one run gates several changes):

- The subject is the head commit, named `git+<repository URL>@<sha>` with the digest `{"gitCommit": "<sha>"}`. No statement is written when the gate could not name the head.
- The `predicateType` is the URL of [`schemas/change-record.schema.json`](../schemas/change-record.schema.json) on the aidd repository, and the predicate validates against it. The predicate is a draft at `predicate_version` 0.1. It holds:
  - the tenant, the repository, the change, the route and its lane, the base and head, and the config digest;
  - the Spec with its approval hash, whether the route required Spec approval, each Spec approval (who, when, the commit it named), each Merge approval (who, when, the head it binds to), and the specialists;
  - every required test's exit on base (red) and on head (green) with the runner, the scope result, the authors, and `assisted_by`;
  - the decision, and every finding as `level code`, with `aidd_version` and `loop_version`.
- The file is unsigned: it is a statement, not proof. A signature is the platform's (§14). `aidd verify <sha|path>` MUST refuse a record whose shape, subject, tenant (with `--tenant`), or decision does not hold, one without a Spec approval its route required or without a Merge approval (the standard route excepted), and one whose approver is a bot or an agent account; it MUST say `unsigned` and exit non-zero for a record whose signature it did not check, unless `--allow-unsigned`.

## 8. Approvals and separation of duties

*Normative. This section owns the approval rules, including solo approval and the cool-off; other documents link here.*

- **Spec approval.** The comment `/aidd approve-spec <ID> <hash> [<commit>]`, which `aidd hash <spec> --comment` prints.
  - The hash is the first 128 bits (32 hex digits) of a SHA-256 over one canonical JSON document: the stable Spec fields (not the bookkeeping `status`, `blocked_on`, `outcome`, `labels`, `relations`, `triage`, or a Task's `retry_count`), the body with normalized line endings and without its `aidd-handoff` blocks (§5.1), and a map from every test file (`tests.files`) and design file (`design.files`) to its blob ID. Because JSON escapes every character, no field can absorb another. A Spec that contains a control character other than tab, carriage return, or line feed is invalid, and the verifier and `aidd validate` MUST reject it.
  - Bookkeeping never voids an approval. A changed acceptance or test always does.
- **Merge approval.** A platform approval of the head commit. The verifier MUST NOT count an approval of an earlier commit. Under solo only, the author MAY instead comment `/aidd approve <full head SHA>`.
- <a id="local-approvals"></a>**Local approvals.** With no platform, a person records either approval on their own machine: `aidd approve spec <Spec>` records the Spec approval line for the committed Spec, and `aidd approve merge` records a Merge approval of the current head.
  - Each is a commit on the private ref `refs/aidd/approvals`, outside every branch and tag, authored by the person's git identity (`email:<address>` in `owners.approvers`). The local gate reads it as it reads a platform's comment or review.
  - `aidd ship` then merges a passing branch into the base branch, keeping its history or squashing it with every `Assisted-by` trailer.
  - A local approval is weaker than a platform's, because the agent runs as the same user. So the commands refuse to run without a person at an interactive terminal who types back a one-time code the prompt shows, the edit-time hook denies them to agents, and once git commit signing is set up only approvals with a good signature count.
  - With no platform there is no platform time either: the solo cool-off starts at the head commit's committer date, which the committer sets, so locally it is a reminder, not a control.
  - A determined agent with the person's keys defeats all of that; push to a platform when the work matters to other people.
- **Specialist review.** A Merge approval from a member of each pool a major change names (§6), `specialist_approvals` per pool; under `specialist_spec_approval` (regulated) each pool also approves the Spec hash. A pool with no members in `owners.reviewers` falls back to the `security` pool; with neither bound, the gate fails and names the pool to bind. An emergency change that touches a protected path keeps its specialist review.
- **What counts as an approval command.** The verifier MUST count a command only when:
  - it starts at column 0 of a line of its own, in a comment that was never edited;
  - it is outside quotes, fenced code (an unclosed fence runs to the end), indented code, and HTML comments.
  - A Spec approval MAY name the commit it was given on: `/aidd approve-spec <ID> <hash> <sha>`. When that commit had changed nothing but the Spec, its tests, and its design files, the record shows `spec_approval_before_implementation = true`; under `gates.spec_approval_proof = "require"` (regulated), only such approvals count.
  - A later comment-only review does not clear an approval or a change request.
- **The authors.** The change author plus every commit author and committer. `identities.system_accounts` can exempt only bot accounts (`*[bot]`, `web-flow`, `github-actions`), never a person or the change author.
  - Under every profile except solo, the verifier MUST NOT count an author or a bot toward Spec approval, Merge approval, or a specialist review.
  - A commit author the platform cannot map to an account (an `email:` identity) might be an Approver, so the verifier warns, or fails under regulated, unless the platform itself blocks committers from approving.
  - Under team, one second person can be the Spec approval Approver, the Merge approval Approver, and the specialist reviewer. That is by design: team is two-party review, not three. Use org or regulated for more.
- <a id="solo"></a>**Solo.** The solo profile is for one person directing agents, who is also the only Approver. It waives the rule that an Approver differs from the authors, and its gates (§9) are looser in four more ways: Spec approval is required on major changes only, red-then-green is a warning rather than a failure, no specialist pool must approve, and the changed-line budget is larger. Everything else stands: evidence bound to the head commit, scope, protected paths, and a Merge approval on every route but standard.
  - `owners.approvers` is required under solo as under every profile. An approval counts only from an account in it, including the author's own; an author who is not listed MUST NOT count, so a stranger's fork PR cannot approve itself. A bot counts only when the pool names it, and an agent account never does. The incident commander checks do not apply.
  - The record shows `separation_of_duties = "waived_solo"`.
  - **Cool-off.** On the routes in `gates.cooloff_minutes` (major, 30 minutes), an approval counts only when it comes at least that long after the platform first saw the head commit: on GitHub, the creation time of the earliest check suite for the head SHA on the pull request's own branch (with no such suite, the cool-off does not pass); on GitLab, the creation time of the head's pipeline. On a platform a commit date never counts, because the committer sets it. Locally there is no platform time, so the cool-off starts at the head commit's committer date, which the committer sets: a reminder, not a control. A determined solo developer can still wait out the cool-off: it is a second look, not a control against yourself.
- **Per-path owners.** `[[owners.paths]]` names the approvers for an area of a monorepo, and `owners.codeowners = true` adds the base branch's CODEOWNERS (the last matching rule wins). A change that touches an area needs at least one approval from that area's approvers, for Spec approval and Merge approval, on top of the approvals the route requires.
- **Approver pools.** Users or `@org/team` entries, resolved through the platform.
  - The repository MUST NOT leave the pool empty.
  - An unresolvable team holds the gate as pending; it never passes.
  - Bots approve only when listed by name; an agent account never approves: one in `identities.bots`, a login the baseline names in `agent_accounts` (such as `copilot-pull-request-reviewer[bot]`, the account GitHub Copilot code review uses), or a `[bot]` account whose name carries a known agent name. When an agent or an unnamed bot approves on the platform, the verifier MUST warn (`merge_approval.agent_approval`), because a branch rule's own review count may take that approval.
  - <a id="tenants"></a>With a `tenant` in the config, pools and approvals are scoped to it: an identity MAY be written `<tenant>:<login>` or `<tenant>:email:<address>`, and an unqualified one belongs to the config's tenant. The verifier MUST NOT count an approval by an identity qualified with another tenant (it warns: `spec_approval.other_tenant`, `merge_approval.other_tenant`), and a pool entry of another tenant names nobody. A child config cannot change a parent's tenant.
  - A Spec's own `approvers` can only narrow the config's pool.
  - Anyone whose approval a change could need (an Approver, a member of any reviewer pool, a path owner) can block it by requesting changes.

## 9. Profiles

*Normative.*

<!-- aidd:gen profiles -->
| Gate | solo | team | org | regulated |
| --- | --- | --- | --- | --- |
| Approvers must differ from the authors | no | yes | yes | yes |
| Spec approval on routes | major | normal, major | normal, major | normal, major |
| Specialist pools also approve the Spec on major | no | no | no | yes |
| Merge approvals per route | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 2, emergency 1 |
| Approvals from each specialist pool on major | 0 | 1 | 1 | 1 |
| Cool-off minutes before an approval counts | major 30 | none | none | none |
| Bound Policy required on routes | none | none | major, emergency | minor, normal, major, emergency |
| AI provenance | declare | declare | declare | every_commit |
| Red-then-green proof for new behavior | warn | require | require | require |
| Standard changes allowed | yes | yes | yes | no |
| Observe block required on routes | major | major | major | normal, major |
| Changed-line budget per route | minor 50, normal 800, major 800 | minor 50, normal 400, major 400 | minor 50, normal 400, major 400 | minor 50, normal 400, major 300 |
| Commit authors with no platform account | warn | warn | warn | fail |
| Spec approval proven before implementation | optional | optional | optional | require |
| Open waits per Approver before `aidd next` warns (0: off; never gated) | 0 | 3 | 3 | 3 |
| Minutes before `aidd next` escalates a wait (0: off; never gated) | 0 | 0 | 0 | 0 |
<!-- aidd:end -->

A repository SHOULD choose the weakest profile that fits who approves. A `[gates]` value MUST only tighten the profile: the verifier ignores a looser value and warns. A child config (through `extends`, or under an org preset) MUST NOT lower its parent's profile or replace its reviewer pools, Policy, evidence source, or identity exemptions, and cannot add to a key its parent `locks`. The merge rules and the org preset are specified in [CONFIG.md](CONFIG.md#parents-presets-and-locks).

## 10. Scale modules

*Informative, except the config fields the modules name.*

### 10.1 One loop at every scale

The loop, the Change Request, and the gate decision are the same for one founder and for many companies. Growing adds Approvers, owners, and presets; it never adds a second loop or forks the method.

| Scale | What you add | How it holds |
| --- | --- | --- |
| A solo founder | `profile = "solo"`, with the founder in `owners.approvers`; the aidd-team roles as agents | the founder approves with an explicit second look: a full-SHA approval, and a cool-off on major (§8) |
| Many solo founders | a shared public preset, `extends = [{ url = "<url>", sha256 = "<digest>" }]` | each repository gates itself; the sha256 pin means no one else's edit reaches you unreviewed |
| A team | `profile = "team"`, an `@org/team` approver pool | an Approver other than the author for Spec approval and Merge approval; Locks and Parallel Tasks when changes overlap |
| Many teams | `[[owners.paths]]` or CODEOWNERS per area; Epics with `owner_teams`; `team:ID` in `depends_on`; `when_changed` tests | each touched area's owners approve on top of the approvals the route requires |
| Many projects | one org preset through `extends` or `AIDD_ORG_PRESET`; `trace_id` across repositories | repositories can only tighten the preset; each repository gates its own child change; `aidd metrics --by repo` |
| Many companies | each company's own preset, `tenant`, approvers, and GitHub App or GitLab token | a gate decides only for its own repositories; a contributor from another company (vendor, agency, open source) is an author there, never an Approver; an approval by another tenant's identity never counts; `aidd metrics --tenant`, `--by owner` |

### 10.2 Modules

Each module is off until its signal is true. A module adds fields and stops, never a new object kind or a second loop.

| Module | Signal | Adds |
| --- | --- | --- |
| Parallel Tasks | two or more Tasks with disjoint scope | a worktree or branch per Task, one merge at a time, and the first Task proves the approach |
| Locks | two open changes with overlapping scope | the later one waits (`blocked_on`), with CODEOWNERS routing and one merge at a time |
| Multi-team | an Epic with two or more `owner_teams`, or a monorepo | the Epic `context` as the only shared glossary; cross-team `depends_on` as `team:ID`; `[[owners.paths]]` requires each touched area's approvers for Spec approval and Merge approval; `when_changed` scopes `[[tests]]` to an area |
| Multi-repo | one change spans repos | children share `trace_id`; each repo gates its own child |
| Specialists | a Task needs extra craft | at most two `skills` per Task; a specialist never decides scope, route, or approval |
| Docs-as-code | docs, schemas, or generated files | never hand-edit generated output; the generator's `--check` is a test |
| Greenfield | a new repository with no code on the default branch | Day 0 commits the aidd setup and the project scaffold straight to the default branch; every later change is gated; the first Spec brings the test runner and the first test, which is red on the empty base; Initiative and Epics hold the product intent, and architecture choices go in the Spec's `decisions` |
| Brownfield | an existing codebase adopts aidd | advisory mode first; protected paths and risk rules bound to the real layout; Characterization before changing untested code; `budget_exclude_paths` for generated and vendored files; legacy code outside `scope` stays untouched |
| Characterization | no repo suite | one command that pins today's behavior before implementation; aidd runs it on head (it should pass on base too) |
| Locale | non-English titles | `locale` (BCP 47) for titles and summaries only; tokens stay English |

## 11. AI-era security controls

*Informative, except the rules each row names: those are enforced by the verifier as §7 specifies.*

| Control | What the gate enforces, and by which rule | What stays guidance for agents and operators |
| --- | --- | --- |
| **Untrusted input.** Issue, ticket, comment, web, log, and dependency text is data. | nothing | instructions found in such text are reported to the author, never followed |
| **Secrets.** Secrets never appear in prompts, diffs, logs, Specs, or PR/MR text; they resolve in the runner only. | secret-like paths are major (`route`, through `baseline:secrets-crypto`); tokens are stripped from every test, Policy, and Observe command | keeping secrets out of prompts and PR text |
| **Least privilege.** Agents run without production credentials, with egress limited to registries and the code platform, and without push-to-protected or approval rights. | agent accounts in `identities.bots` never count as Approvers (`spec_approval`, `merge_approval`, `specialist_review`); the test job has no secrets (§14) | the agent's own credentials and egress, which your harness and platform settings control |
| **Self-modification.** Agent instructions, skills, hooks, MCP config, CI, CODEOWNERS, and aidd's config are protected paths. | every protected path makes the change major (`route`) and needs a specialist (`specialist_review`) | |
| **Supply chain.** A new dependency exists on the official registry under that exact name, with credible provenance, and is pinned by lockfile. | dependency, container, and build-tool manifests add `third_party`, which rules out minor (`route`, through `baseline:dependencies`, `baseline:containers`, `baseline:build-tooling`) | verifying the package and its provenance |
| **Provenance.** Agent commits carry `Assisted-by: <harness>/<model>`, or a `Co-authored-by:` trailer naming the agent. | `assisted_by` declares every agent a commit names, and under regulated every commit has a trailer (`provenance`) | adding the trailer, which only the committing agent can do |
| **Review load.** Route budgets cap changed lines, so human approval stays meaningful. | `budget` | |
| **Agent hooks.** Where the harness supports hooks, the guard (`aidd hook pre-edit`) stops an agent from approving, merging, shipping, force-pushing, editing outside its role, or typing approval text into another terminal; session hooks brief it on the next step and flag missing evidence before it stops (`[hooks] level`). | nothing: the hooks run on the agent's machine, so the gate never trusts them | defence in depth that catches mistakes early; every denial is logged to `.aidd/work/guard.jsonl` for `aidd metrics --guard` |

[CONTROLS.md](CONTROLS.md) maps these controls to NIST SSDF (SP 800-218 and 800-218A), OWASP LLM Top 10, ISO/IEC 42001, the EU AI Act, SOC 2, SLSA, and DORA.

## 12. Ship and Learn

*Informative, except the recorded fields and the emergency backfill.*

**Release.** Release is the configured release interface; progressive delivery (flags, canaries) SHOULD be used for major.

**Observe.** The verifier MUST require an `observe` block on the profile's routes (the `observe` rule): the Spec names a `window`, a post-release `command` or `signals`, and a `rollback_trigger`. `aidd observe <spec>` runs the command once and can record `outcome.observe_result`; watching the window and rolling back stay with your release tooling.

**Hypothesis.** A Spec MAY state a `hypothesis` (the metric, its baseline, the expected move, and by when), frozen by Spec approval. Learn records `outcome.result` against it, and a missed hypothesis is a product decision, never a rollback.

**Learn.** Learn runs after every Merge approval reject, rollback, incident, and Task that exhausted its retries. The result is a PR/MR that improves the repository's agent instructions, tests, or rules, linked in `outcome.learn_ref`. Incident reviews are due by `review_due`.

- After an emergency or a rollback, the lesson SHOULD be a regression test that reproduces the failure, plus an eval scenario when an agent's behavior caused it, so every incident becomes a permanent check.
- When an agent makes the same mistake twice, the correction SHOULD go into the agent instructions (`AGENTS.md`, or `CLAUDE.md`) as part of the fix. Those files load into every session, so they SHOULD stay about one page: `aidd doctor` warns past 200 lines or 12 KiB.

**Runbooks and postmortems.** Operating knowledge lives in the repository beside the code it operates, and `aidd validate` checks both against their schemas.

- A **runbook** (`aidd new runbook`, in `docs/runbooks/`) says how to run, check, and recover one part of the system, and records `last_tested`, the date someone last followed it for real. `aidd doctor` warns when an active runbook was never tested or is older than `runbook_max_age_days` (180 by default), because an untested runbook fails when it is needed most.
- A **postmortem** (`aidd new postmortem`, in `docs/postmortems/`) records an incident blamelessly, names the Spec that carries its fix when there is one, and feeds Learn.

**House standards.** A team's own rules (a style guide, an API guideline, a security baseline) are listed in the config under `[[standards]]`, each with the roles that must read it, the paths that trigger it, and the `[[tests]]` that enforce it, if any. `aidd owners` shows each role what to read before its step, and `aidd doctor` flags a missing document or an enforcing test that does not exist. A house standard with no enforcing test is guidance; one with a test is a rule the gate checks.

**Verified before done.** The agent instructions `aidd init` writes tell an agent to run the repository's tests, `aidd test`, and `aidd gate`, and to paste their output, before it reports any task complete, and to fix the code rather than the test when one fails. The pasted output is for the human; the runner's exit code stays the evidence.

**Emergency backfill.** Every inline emergency MUST name its backfill Spec (`backfill`) and commit it as a stub with the repair, so `aidd validate` sees the debt and fails once `review_due` passes without `outcome.learn_ref`.

Every gate decision MAY append one event (`schemas/event.schema.json`), carrying the platform, author, base branch, mode, config digest, test durations, and the deciding run's URL. `aidd metrics` reports:

- final decisions and routes
- first-pass test rate
- route corrections
- top failing rules
- median change size
- the AI-assisted share
- the median wait per approval and the median time to a pass, which show where changes wait
- loop speed, each speed metric beside the quality metric it must not degrade: time to first feedback (a head's push to its first test result) with the first-pass test rate, approval wait p50 and p90 per approval with Spec rework after Spec approval, and flow efficiency (lead time not spent waiting on an approval) with the first-pass share; `[targets]` for them make `aidd metrics` exit 1 when missed
- with `--cost`, cost per change from a ledger the host exports, beside the first-pass share; display only, never a gate rule

`aidd metrics --dora` reports proxies for the five DORA software delivery metrics against the `[targets]` in the config, and `--specs` adds change fail rate and recovery time from the Specs' `outcome`. Pair them with your deployment data where it measures more directly. `aidd metrics --autonomy --propose` drafts a standard-change class from the evidence, for a person to merge.

<a id="continuous-improvement"></a>
### 12.1 Continuous improvement

The loop improves itself with the loop. A retrospective runs on a cadence (every two weeks or 20 merged changes, whichever comes first) and after every Learn signal. It reads `aidd metrics --since <last retrospective>`, the postmortems, and the review findings; checks last cycle's improvements against their targets (Plan-Do-Check-Act); and proposes at most three new ones, each with a metric, a target, and a check date. Each improvement re-enters the loop at Plan as a new change, which starts with `aidd next`, on the lowest rung that fixes it:

| Rung | What changes | How it ships |
| --- | --- | --- |
| Repository | `.aidd/config.toml`, tests, Spec templates, agent instructions and roles | a Spec; these are protected paths, so it is major and a specialist reviewer approves |
| Organization | the org preset | a Spec in the platform team's preset repository; every repository picks it up by pin |
| Standard | routes, profiles, gate rules, schemas, or the loop | an RFC to the method (`docs/rfcs/`), then a Spec in its repository |
| Escaped defect | a defect reached production, or a change was mis-assessed | a test that reproduces it; a routing eval scenario or a baseline risk rule |

Two rules keep self-improvement safe. Agents may propose any improvement but never adopt one: process files are protected paths, so a human decides. And a change that loosens a control (a higher budget, a disabled rule, a wider `scope_exempt_paths`, a weaker profile) must cite the metric that justifies it. Pair every speed metric with a quality metric, so the loop cannot improve one by degrading the other.

Agent evals (`aidd eval routing`, `aidd eval roles`) are a young practice: treat their scores as a trend to watch across releases, never as a certificate, and record them per model in the evals READMEs.

## 13. Interfaces and configuration

*Normative.*

| Interface | Bound by | Contract |
| --- | --- | --- |
| Repo | the platform adapter | diff, commits, tree, blobs of the head; base-branch config |
| CI and test runner | `aidd-tests` job | runs `[[tests]]` and Spec commands; uploads evidence for the head SHA |
| Policy | `policy.command` | prints `allow`, `deny`, or `freeze`, or a JSON object `{verdict, detail, findings}` whose findings join the decision as `policy:<rule>` |
| Observe | Spec `observe.command` or config `observe.command` | exit 0 when healthy. `aidd observe` runs it once, after release; your release tooling watches the window and rolls back |
| Secrets | the runner's secret store | values only inside the runner |
| Release | the platform's merge, then your deploy | requires `aidd/gate` green |

**Policy** is the extension point for org rules in any language (see `examples/policy/`). The gate runs it from a clean worktree of the base branch, with the change described in `AIDD_INPUT_FILE` and the other variables in [CLI.md](CLI.md#environment-variables), and with every token stripped. The verifier MUST treat no verdict, a timeout, or `allow` with a non-zero exit as unreachable, which counts as deny. An unbound Policy is decided by the profile: §9 lists the routes that require one.

**Observe** runs with `AIDD_SPEC_ID`, `AIDD_WINDOW`, and `AIDD_ROLLBACK_TRIGGER` set, and the same tokens stripped.

**Configuration.** Every key of `.aidd/config.toml`, and how parents and org presets merge, is specified in [CONFIG.md](CONFIG.md), generated from `schemas/config.schema.json`. The verifier MUST read the config from the base branch, never from the change.

## 14. Platform bindings and trust

*Normative. This section owns the trust model; [SECURITY.md](../SECURITY.md) summarizes it and [PLATFORMS.md](PLATFORMS.md) has the setup steps.*

- **Gate job (trusted).**
  - The adapter MUST run from the default-branch workflow definition and check out the default branch.
  - The adapter MUST NOT execute code from the change. It fetches the PR/MR head as git objects only.
  - The reference GitHub gate runs the verifier from the exact commit of the reusable workflow it calls (`job.workflow_sha`): no package build, nothing fetched from a package index. Callers pin that workflow by ref; a commit SHA pins it immutably.
  - The adapter MUST run Policy in a clean worktree of the PR/MR's base branch, with no tokens in its environment.
  - The adapter MUST read identities, reviews, unedited comments, and evidence from the platform API.
  - The adapter MUST post `aidd/gate` only for protected base branches, and only if the PR/MR head has not moved while it verified. A commit status belongs to the commit, so when one head is shared by pull requests into several protected bases, it MUST post the worst of their decisions.
  - When the adapter cannot finish (an API error, an unreadable artifact), it MUST post `error`, so an older success never stands.
  - On GitHub the gate is triggered by `pull_request_target`, `issue_comment`, and `workflow_run`, with one concurrency queue per pull request. Reviews reach it through a permissionless relay workflow, because `pull_request_review` runs the PR's own workflow file. Repositories call the reusable workflow `.github/workflows/gate.yml` from a thin caller that keeps these triggers, so the definition still comes from the default branch. The checkout keeps no credentials, and the PR head is fetched with a one-off header.
- **Advisory mode.** Advisory reports on `aidd/gate (advisory)` and never blocks, so a repository can shadow the gate before requiring it. The config's top-level `mode` (`enforce` or `advisory`), read from the base branch, wins over any CI setting, and a child config cannot relax a parent's `mode = "enforce"`. When the config sets no mode, GitHub uses the reusable workflow's `mode` input (which also runs from the base branch). On GitLab the `AIDD_MODE` pipeline variable can never relax the gate: advisory is set only by `mode = "advisory"` in the base config.
- **Status source (GitHub).** Anyone with push access can write a commit status, including a same-repository PR workflow that grants itself `statuses: write`. So:
  - The operator MUST post from a dedicated GitHub App whose key lives only in an `aidd-gate` environment whose deployment branches are the protected bases, and MUST NOT store the key as a repository or organization secret, which any workflow on any branch could read. The caller passes no secrets.
  - The operator MUST pin the required `aidd/gate` check's expected source to that App. Without it, the gate is advisory against anyone with write access.
- **Test job (untrusted).** It runs the change's code with a read-only token and no secrets, through the `thaithienvanid/aidd` composite action or `aidd test`.
  - Existing CI: `evidence.workflow_path` can point the gate at an existing CI workflow that runs `aidd test`, and `evidence.status_checks` can accept your existing CI checks for the repository suite, so the suite runs once.
  - Central evidence: for evidence a pull request cannot touch, run the tests from an organization required workflow in a platform repository and set `evidence.signer_workflow`. The gate then accepts only evidence with a GitHub artifact attestation signed by that workflow.
  - The adapter MUST accept evidence only from the workflow file named by `evidence.workflow_path` (default `.github/workflows/aidd-tests.yml`), only from a completed run of the change's own head branch and repository, only for the PR's head and base (for a merge-queue entry: a `merge_group` run on the queue branch, for the merge-group commit and the commit it was built on), and only as a root `evidence.json`.
  - The adapter MUST refuse skipped and cancelled runs, and any evidence while another pull request from the same branch at the same commit targets a different base, because its runs would be indistinguishable.
  - The runner kills each test's process group once the test exits. That is hygiene, not containment: the job runs the change's code, which can write anything the job can, including its own evidence.
  - Evidence is therefore as honest as the code under test; the Spec approval and Merge approval human reviews cover the tests and the diff. List the files tests run through (test config, Makefile targets) in `tests.files` so Spec approval freezes them too.
- **Signing the change record (GitHub, optional).** The gate workflow template has an `attest` job, off unless the repository variable `AIDD_ATTEST_CHANGE_RECORD` is `true`, that signs a passing change record ([§7](#change-record)) with `actions/attest`, pinned by commit SHA.
  - Only that job holds `id-token: write` and `attestations: write`; the gate job never does. It is a caller job rather than part of the reusable workflow, because GitHub checks a reusable workflow's permissions even for the jobs it skips.
  - The action takes SHA-2 subjects only, so the attestation's subject is the sha256 of the statement file and its predicate is the change-record predicate; the file names the commit. `aidd verify --online` (or `--bundle`) runs `gh attestation verify` on the file with the predicate type, then compares the signed predicate with the file's.
  - GitHub offers artifact attestations on public repositories, and on private or internal ones only with GitHub Enterprise Cloud. Elsewhere leave the job off: the record stays unsigned, and the commit status and the run log remain the anchors.
  - aidd issues no SLSA Source verification summary attestation (VSA) for a protected branch.
- **GitLab.** An MR can change its own pipeline, so the operator MUST enforce the jobs with a pipeline execution policy or a compliance pipeline.
  - Give only the gate job a `read_api` token.
  - Keep the MR approval settings on: prevent approval by the author, prevent approvals by users who add commits, and remove approvals when commits are added. The gate reads the committer setting, because GitLab commit authors are emails it cannot map to users.
  - Only the pipeline for the MR's current head decides; approvals bind to that pipeline's creation time.
  - Fork MR pipelines fail closed.
- **Merge queues (GitHub).** The gate judges each queue entry and posts `aidd/gate` on its merge-group commit ([§7](#merge-queue-evidence) has the rules).
  - The adapter MUST NOT run on `merge_group` itself, which runs the workflow file from the merge-group commit (the pull request's own changes). The `aidd-tests` run the queue starts runs untrusted as always; its completion starts the gate through `workflow_run`, from the default branch.
  - The adapter takes the pull request number and the entry's parent from the queue branch's name (`gh-readonly-queue/<base>/pr-<n>-<sha>`), and believes the parent only when git confirms that the base's merge base with the entry is its ancestor and that it is the entry's; otherwise the parent is that merge base. Neither needs to be trusted: a wrong pull request or parent makes the trees differ, and the gate fails.
  - It posts on the merge-group commit alone, which no other pull request shares, so the shared-head rule does not apply.
  - The operator MUST turn on "Only merge non-failing pull requests" (grouping strategy `ALLGREEN`) for a queue that builds more than one entry at a time; the gate fails a stacked entry until it can read that setting.
  - GitLab merge trains are not supported yet: turn them off on gated branches, because a train merges a result the gate never judged.

## 15. Distribution and versioning

*Informative.*

- **The skill.** The folder `.agents/skills/aidd/`. It is self-contained and has no references outside itself. It is distributed three ways: vendored by `aidd init` (with `aidd doctor` detecting drift), as a Claude Code plugin from this repository's marketplace, or referenced from `AGENTS.md`.
- **The verifier.** The `aidd` Python package, which bundles the schemas, the skill, the templates, and the team plugin with its domain packs and practice skills.
- **Agent tools.** `aidd mcp` serves the route and next steps (`next`), edit checks, validation, the Spec hash, the Change Request block, and a local gate over MCP; `aidd hook pre-edit` is a Claude Code PreToolUse hook that answers allow or deny, never a mid-build prompt: it denies edits outside the active Spec's `scope`, protected paths outside an approved scope, test and design files once the Spec's status says it was approved, and commands `[[guard.gated_commands]]` holds for approval; each denial names its route. Both are local guides; only the gate decides. The Claude Code plugin ships both.
- **Maturity.** MCP tools, hooks, and skill folders are young formats (2024 and 2025). The CLI, `AGENTS.md`, and the vendored skill are the stable path; the agent tools are conveniences on top of it.
- **Interop.** Other planning tools keep their folders: `aidd import` (or an agent) drafts the AIDD Spec from them, linking the plan instead of copying it, and AIDD objects coexist with Spec Kit's files under `specs/` (only files with `+++` front matter are AIDD objects).
- **Version.** One semantic version covers the method, schemas, verifier, and skill, and every record carries `aidd_version`. What makes a change patch, minor, or major, and the deprecation policy, are in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning).

## 16. Conformance checklist

*Informative: a checklist form of §1, which is normative. When the two disagree, §1 wins.*

- [ ] R1: `.aidd/config.toml` on every protected branch, valid; `aidd doctor` has no failures.
- [ ] R2: `aidd/gate` required on every protected branch, posted by a trusted job from a pinned source.
- [ ] R3: owners bound: approvers on every profile; a `security` pool at least from team up; Policy where the profile requires it.
- [ ] R4: a Change Request block on every change (or a matching standard change class), and a Spec on normal and major.
- [ ] R5: evidence from a runner the change cannot rewrite without major review; a repository suite in `[[tests]]`, or Characterization in every Spec.
- [ ] R6: agent bot accounts listed in `identities.bots`.
- [ ] R7: the agent skill (or `AGENTS.md`) reaches every agent that writes code.
- [ ] R8: gate records and events retained for your audit period.
- [ ] T1 and T2, for a reimplementation: the reference verifier and yours agree on `examples/`, and your adapter meets §14.
